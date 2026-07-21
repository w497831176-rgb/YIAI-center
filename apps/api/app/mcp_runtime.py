from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from typing import Any

from . import db
from .mcp_client import McpClientError, StreamableHttpMcpClient


MAX_CONTEXT_CHARS = 60_000
MAX_SUMMARY_FIELD_CHARS = 14_000


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def matching_servers(config: dict[str, Any], content: str) -> list[dict[str, Any]]:
    lowered = content.casefold()
    matches: list[dict[str, Any]] = []
    for server in config.get("mcp", []):
        runtime_config = server.get("runtime_config") or {}
        keywords = runtime_config.get("activation_keywords") or []
        if any(str(keyword).casefold() in lowered for keyword in keywords if str(keyword).strip()):
            matches.append(server)
    return matches


def tool_bound_to_agent(server: dict[str, Any], tool_name: str, agent_id: str) -> bool:
    """Support new per-Tool Agent bindings and historical Server-level snapshots."""
    tool_agent_ids = server.get("tool_agent_ids")
    if isinstance(tool_agent_ids, dict):
        agent_ids = tool_agent_ids.get(tool_name)
        return isinstance(agent_ids, list) and agent_id in agent_ids
    return agent_id in server.get("agent_ids", [])


def preflight_messages(servers: list[dict[str, Any]], content: str) -> list[dict[str, str]]:
    candidates = []
    for server in servers:
        candidates.append(
            {
                "server_id": server["server_id"],
                "allowed_tools": server.get("allowed_tools", []),
                "tools": server.get("tools", []),
                "business_instructions": (server.get("runtime_config") or {}).get(
                    "business_instructions", ""
                ),
                "required_fields": (server.get("runtime_config") or {}).get(
                    "required_fields", []
                ),
                "argument_examples": (server.get("runtime_config") or {}).get(
                    "argument_examples", []
                ),
            }
        )
    return [
        {
            "role": "system",
            "content": (
                "You are a strict remote Tool input preflight. Select at most one listed server and "
                "exactly one allowed Tool. Extract only facts explicitly present in the user message. "
                "Never infer missing personal facts, calendar modes, times, locations, flags, or consent. "
                "Follow the supplied business instructions and JSON Schema. Return only one JSON object: "
                '{"matched":true,"server_id":"...","tool_name":"...","arguments":{},'
                '"raw_extracted":{},"missing_fields":[]}. If no candidate applies, set matched false. '
                "missing_fields must contain every required field absent from the message."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {"user_message": content, "candidates": candidates},
                ensure_ascii=False,
            ),
        },
    ]


def parse_preflight(content: str, servers: list[dict[str, Any]]) -> dict[str, Any]:
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if not match:
        raise ValueError("MCP preflight did not return JSON")
    result = json.loads(match.group(0))
    if not isinstance(result, dict):
        raise ValueError("MCP preflight result must be an object")
    if not result.get("matched"):
        return {"matched": False, "arguments": {}, "raw_extracted": {}, "missing_fields": []}
    server_by_id = {server["server_id"]: server for server in servers}
    server_id = str(result.get("server_id", ""))
    server = server_by_id.get(server_id)
    if server is None:
        raise ValueError("MCP preflight selected an unavailable server")
    tool_name = str(result.get("tool_name", ""))
    if tool_name not in server.get("allowed_tools", []):
        raise ValueError("MCP preflight selected a Tool outside the Release allowlist")
    arguments = result.get("arguments")
    raw_extracted = result.get("raw_extracted")
    missing_fields = result.get("missing_fields")
    if not isinstance(arguments, dict) or not isinstance(raw_extracted, dict):
        raise ValueError("MCP preflight arguments are invalid")
    if not isinstance(missing_fields, list):
        raise ValueError("MCP preflight missing_fields is invalid")
    defaults = (server.get("runtime_config") or {}).get("default_arguments") or {}
    if isinstance(defaults, dict):
        arguments = {**defaults, **arguments}
    return {
        "matched": True,
        "server": server,
        "server_id": server_id,
        "tool_name": tool_name,
        "arguments": arguments,
        "raw_extracted": raw_extracted,
        "missing_fields": list(dict.fromkeys(str(item) for item in missing_fields if str(item))),
    }


def config_preflight(server: dict[str, Any], content: str) -> dict[str, Any]:
    """Apply Release-owned declarative extractors without domain-specific code."""
    config = server.get("runtime_config") or {}
    extractors = config.get("argument_extractors") or []
    arguments: dict[str, Any] = {}
    raw_extracted: dict[str, Any] = {}
    for extractor in extractors:
        if not isinstance(extractor, dict):
            continue
        target = str(extractor.get("target", ""))
        pattern = str(extractor.get("pattern", ""))
        if not target or not pattern:
            continue
        match = re.search(pattern, content, re.IGNORECASE)
        if not match:
            continue
        value: Any = match.groupdict().get("value") if match.groupdict() else match.group(1)
        value_map = extractor.get("value_map") or {}
        if isinstance(value_map, dict) and str(value) in value_map:
            value = value_map[str(value)]
        value_type = extractor.get("type")
        if value_type == "integer":
            value = int(value)
        elif value_type == "number":
            value = float(value)
        elif value_type == "boolean" and not isinstance(value, bool):
            value = str(value).casefold() in {"true", "1", "yes"}
        elif value_type == "string":
            value = str(value)
        raw_extracted[target] = value
        if extractor.get("trace_only") is not True:
            arguments[target] = value
    for rule in config.get("conditional_defaults") or []:
        if not isinstance(rule, dict):
            continue
        when = rule.get("when") or {}
        values = rule.get("set") or {}
        if isinstance(when, dict) and isinstance(values, dict) and all(
            arguments.get(key) == value for key, value in when.items()
        ):
            for key, value in values.items():
                arguments.setdefault(key, value)
    for lookup in config.get("range_lookups") or []:
        if not isinstance(lookup, dict):
            continue
        source = str(lookup.get("source", ""))
        target = str(lookup.get("target", ""))
        source_value = arguments.get(source, raw_extracted.get(source))
        if not isinstance(source_value, (int, float)) or not target:
            continue
        for item in lookup.get("ranges") or []:
            if (
                isinstance(item, dict)
                and isinstance(item.get("min"), (int, float))
                and isinstance(item.get("max"), (int, float))
                and item["min"] <= source_value <= item["max"]
            ):
                arguments[target] = item.get("value")
                break
    defaults = config.get("default_arguments") or {}
    if isinstance(defaults, dict):
        arguments = {**defaults, **arguments}
    required = [str(item) for item in config.get("required_arguments") or []]
    for rule in config.get("conditional_required") or []:
        if not isinstance(rule, dict):
            continue
        when = rule.get("when") or {}
        if isinstance(when, dict) and all(arguments.get(key) == value for key, value in when.items()):
            required.extend(str(item) for item in rule.get("arguments") or [])
    missing = [name for name in required if name not in arguments]
    missing.extend(
        str(name)
        for name in config.get("required_extracted") or []
        if str(name) not in raw_extracted
    )
    tool_name = str(config.get("default_tool") or "")
    if tool_name not in server.get("allowed_tools", []):
        raise ValueError("declarative fallback Tool is outside the Release allowlist")
    return {
        "matched": True,
        "server": server,
        "server_id": server["server_id"],
        "tool_name": tool_name,
        "arguments": arguments,
        "raw_extracted": raw_extracted,
        "missing_fields": missing,
        "source": "release_declarative_fallback",
    }


def enrich_preflight(result: dict[str, Any], content: str) -> dict[str, Any]:
    """Merge explicit declarative extraction into a model result for trace fidelity."""
    if not result.get("matched") or not result.get("server"):
        return result
    server = result["server"]
    config = server.get("runtime_config") or {}
    if not config.get("argument_extractors"):
        return result
    extracted = config_preflight(server, content)
    return {
        **result,
        "arguments": {**result.get("arguments", {}), **extracted["arguments"]},
        "raw_extracted": {**result.get("raw_extracted", {}), **extracted["raw_extracted"]},
        "missing_fields": extracted["missing_fields"],
        "source": "model_plus_release_declarative_extraction",
    }


def tool_for(server: dict[str, Any], tool_name: str) -> dict[str, Any]:
    matches = [tool for tool in server.get("tools", []) if tool.get("name") == tool_name]
    if len(matches) != 1 or matches[0].get("allowed") is not True:
        raise ValueError("Release does not contain exactly one allowed Tool schema")
    return matches[0]


def validate_arguments(tool: dict[str, Any], arguments: dict[str, Any]) -> list[str]:
    schema = tool.get("input_schema") or {}
    properties = schema.get("properties") if isinstance(schema, dict) else {}
    required = schema.get("required") if isinstance(schema, dict) else []
    errors: list[str] = []
    if isinstance(required, list):
        for name in required:
            if name not in arguments or arguments[name] is None or arguments[name] == "":
                errors.append(f"required argument missing: {name}")
    if not isinstance(properties, dict):
        return errors
    for name, value in arguments.items():
        rule = properties.get(name)
        if not isinstance(rule, dict):
            errors.append(f"unknown argument: {name}")
            continue
        expected = rule.get("type")
        if expected == "string" and not isinstance(value, str):
            errors.append(f"{name} must be string")
        elif expected == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
            errors.append(f"{name} must be integer")
        elif expected == "number" and (not isinstance(value, (int, float)) or isinstance(value, bool)):
            errors.append(f"{name} must be number")
        elif expected == "boolean" and not isinstance(value, bool):
            errors.append(f"{name} must be boolean")
        if "enum" in rule and value not in rule["enum"]:
            errors.append(f"{name} is outside enum")
        if isinstance(value, (int, float)):
            if "minimum" in rule and value < rule["minimum"]:
                errors.append(f"{name} is below minimum")
            if "maximum" in rule and value > rule["maximum"]:
                errors.append(f"{name} exceeds maximum")
    return errors


def _extract_path(value: Any, path: str) -> Any:
    current = value
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _trim_value(value: Any, limit: int = MAX_SUMMARY_FIELD_CHARS) -> Any:
    encoded = json.dumps(value, ensure_ascii=False)
    if len(encoded) <= limit:
        return value
    if isinstance(value, list):
        kept: list[Any] = []
        for item in value:
            candidate = kept + [item]
            if len(json.dumps(candidate, ensure_ascii=False)) > limit:
                break
            kept.append(item)
        return {"items": kept, "truncated": True, "original_count": len(value)}
    if isinstance(value, dict):
        kept_dict: dict[str, Any] = {}
        for key, item in value.items():
            candidate = {**kept_dict, key: item}
            if len(json.dumps(candidate, ensure_ascii=False)) > limit:
                break
            kept_dict[key] = item
        kept_dict["_truncated"] = True
        return kept_dict
    return encoded[:limit] + "…"


def summarize_result(payload: dict[str, Any], result_paths: list[str]) -> dict[str, Any]:
    result = payload.get("result") if isinstance(payload, dict) else None
    content = result.get("content") if isinstance(result, dict) else None
    decoded: Any = result
    if isinstance(content, list):
        texts = [item.get("text") for item in content if isinstance(item, dict) and isinstance(item.get("text"), str)]
        if texts:
            joined = "\n".join(texts)
            try:
                decoded = json.loads(joined)
            except json.JSONDecodeError:
                decoded = {"text": joined}
    summary: dict[str, Any] = {
        "is_error": bool(result.get("isError")) if isinstance(result, dict) else False,
        "available_top_level_fields": sorted(decoded.keys()) if isinstance(decoded, dict) else [],
    }
    selected: dict[str, Any] = {}
    for path in result_paths:
        value = _extract_path(decoded, path)
        if value is not None:
            selected[path] = _trim_value(value)
    if not selected:
        selected["result"] = _trim_value(decoded, MAX_CONTEXT_CHARS - 2000)
    summary["selected_data"] = selected
    encoded = json.dumps(summary, ensure_ascii=False)
    if len(encoded) > MAX_CONTEXT_CHARS:
        summary["selected_data"] = _trim_value(selected, MAX_CONTEXT_CHARS - 3000)
    return summary


def call_release_tool(
    run: dict[str, Any], server: dict[str, Any], tool_name: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    started_at = now_iso()
    started = time.perf_counter()
    status = "FAILED"
    error_message: str | None = None
    result_summary: dict[str, Any] = {}
    result_length = 0
    try:
        tool = tool_for(server, tool_name)
        errors = validate_arguments(tool, arguments)
        if errors:
            raise ValueError("; ".join(errors))
        client = StreamableHttpMcpClient(server["endpoint"], server.get("auth_type", "NONE"))
        client.initialize()
        response = client.call_tool(tool_name, arguments)
        result_length = response.length
        result_paths = (server.get("runtime_config") or {}).get("result_paths") or []
        result_summary = summarize_result(response.payload, result_paths)
        if result_summary.get("is_error"):
            raise McpClientError("MCP Tool returned isError=true")
        status = "SUCCESS"
    except Exception as exc:
        error_message = f"{type(exc).__name__}: {str(exc)}"[:2000]
    finished_at = now_iso()
    snap = {
        "server_id": server["server_id"],
        "server_name": server["name"],
        "git_url": server["git_url"],
        "version_ref": server["version_ref"],
        "endpoint": server["endpoint"],
        "transport": server["transport"],
        "tool_name": tool_name,
        "request_args": arguments,
        "result_summary": result_summary,
        "result_length": result_length,
        "started_at": started_at,
        "finished_at": finished_at,
        "latency_ms": round((time.perf_counter() - started) * 1000),
        "status": status,
        "error_message": error_message,
        "model_api_cost": 0,
    }
    snap["id"] = db.save_mcp_call_snap(run["run_id"], run["release_id"], snap)
    if status != "SUCCESS":
        raise McpClientError(error_message or "MCP Tool call failed")
    return snap


def prompt_context(snap: dict[str, Any], server: dict[str, Any] | None = None) -> str:
    answer_instructions = ((server or {}).get("runtime_config") or {}).get(
        "answer_instructions", ""
    )
    return (
        "\n\nThe following data was returned by an allowed remote read-only Tool in this Release. "
        "Answer only from the returned data. Do not invent missing fields or claim that another Tool ran. "
        "If the user asks only for structured output, organize the available fields without adding interpretation.\n"
        + (f"Release business answer instructions:\n{answer_instructions}\n" if answer_instructions else "")
        + json.dumps(
            {
                "server": snap["server_name"],
                "tool": snap["tool_name"],
                "result": snap["result_summary"],
            },
            ensure_ascii=False,
        )[:MAX_CONTEXT_CHARS]
    )
