from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


MAX_RESPONSE_BYTES = 5_000_000
PROTOCOL_VERSION = "2025-06-18"


class McpClientError(RuntimeError):
    pass


def _json_from_response(content_type: str, body: bytes) -> dict[str, Any]:
    if len(body) > MAX_RESPONSE_BYTES:
        raise McpClientError(f"MCP response exceeds {MAX_RESPONSE_BYTES} bytes")
    text = body.decode("utf-8")
    if "text/event-stream" in content_type:
        messages: list[dict[str, Any]] = []
        for line in text.replace("\r\n", "\n").split("\n"):
            if line.startswith("data:"):
                payload = line[5:].strip()
                if payload:
                    try:
                        value = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(value, dict):
                        messages.append(value)
        if not messages:
            raise McpClientError("MCP event stream contained no JSON-RPC message")
        return messages[-1]
    if not body:
        return {}
    value = json.loads(text)
    if not isinstance(value, dict):
        raise McpClientError("MCP response must be a JSON object")
    return value


@dataclass
class McpResponse:
    payload: dict[str, Any]
    length: int
    content_type: str


class StreamableHttpMcpClient:
    def __init__(self, endpoint: str, auth_type: str = "NONE", auth_value: str = ""):
        self.endpoint = endpoint
        self.auth_type = auth_type
        self.auth_value = auth_value
        self.session_id: str | None = None
        self.next_id = 1
        self.server_info: dict[str, Any] = {}
        self.protocol_version: str | None = None

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        if self.auth_type == "BEARER" and self.auth_value:
            headers["Authorization"] = f"Bearer {self.auth_value}"
        return headers

    def _post(self, payload: dict[str, Any], expect_response: bool = True) -> McpResponse:
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                session_id = response.headers.get("Mcp-Session-Id")
                if session_id:
                    self.session_id = session_id
                body = response.read(MAX_RESPONSE_BYTES + 1)
                content_type = response.headers.get("Content-Type", "")
        except urllib.error.HTTPError as exc:
            detail = exc.read(4000).decode("utf-8", errors="replace")
            raise McpClientError(f"MCP HTTP {exc.code}: {detail[:1000]}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise McpClientError(f"MCP transport failed: {type(exc).__name__}") from exc
        if not expect_response and not body:
            return McpResponse({}, 0, content_type)
        parsed = _json_from_response(content_type, body)
        if "error" in parsed:
            raise McpClientError(f"MCP JSON-RPC error: {json.dumps(parsed['error'], ensure_ascii=False)[:1000]}")
        return McpResponse(parsed, len(body), content_type)

    def request(self, method: str, params: dict[str, Any] | None = None) -> McpResponse:
        request_id = self.next_id
        self.next_id += 1
        return self._post(
            {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}
        )

    def initialize(self) -> dict[str, Any]:
        response = self.request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "yiai-center", "version": "0.5.9"},
            },
        )
        result = response.payload.get("result")
        if not isinstance(result, dict):
            raise McpClientError("MCP initialize result missing")
        self.server_info = result.get("serverInfo") or {}
        self.protocol_version = result.get("protocolVersion")
        self._post(
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            expect_response=False,
        )
        return result

    def list_tools(self) -> list[dict[str, Any]]:
        response = self.request("tools/list")
        result = response.payload.get("result")
        tools = result.get("tools") if isinstance(result, dict) else None
        if not isinstance(tools, list) or any(not isinstance(item, dict) for item in tools):
            raise McpClientError("MCP tools/list result invalid")
        return tools

    def call_tool(self, name: str, arguments: dict[str, Any]) -> McpResponse:
        return self.request("tools/call", {"name": name, "arguments": arguments})


def schema_hash(tool: dict[str, Any]) -> str:
    canonical = json.dumps(
        {
            "name": tool.get("name"),
            "description": tool.get("description"),
            "inputSchema": tool.get("inputSchema"),
            "outputSchema": tool.get("outputSchema"),
            "annotations": tool.get("annotations"),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def test_connection(
    endpoint: str,
    allowed_tools: list[str],
    declared_read_only_tools: list[str],
    auth_type: str = "NONE",
    auth_value: str = "",
) -> dict[str, Any]:
    started = time.perf_counter()
    client = StreamableHttpMcpClient(endpoint, auth_type, auth_value)
    result: dict[str, Any] = {
        "initialize_success": False,
        "tools_list_success": False,
        "tool_count": 0,
        "allowed_read_only_tools": [],
        "rejected_tools": [],
        "tools": [],
        "server_info": {},
        "protocol_version": None,
        "error": None,
    }
    try:
        initialized = client.initialize()
        result["initialize_success"] = True
        result["server_info"] = initialized.get("serverInfo") or {}
        result["protocol_version"] = initialized.get("protocolVersion")
        tools = client.list_tools()
        result["tools_list_success"] = True
        result["tool_count"] = len(tools)
        by_name = {str(tool.get("name")): tool for tool in tools}
        missing = [name for name in allowed_tools if name not in by_name]
        if missing:
            raise McpClientError(f"Allowed Tool not returned by server: {', '.join(missing)}")
        declared = set(declared_read_only_tools)
        allowed = set(allowed_tools)
        normalized: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        for tool in tools:
            name = str(tool.get("name", ""))
            annotations = tool.get("annotations") if isinstance(tool.get("annotations"), dict) else {}
            annotated_read_only = annotations.get("readOnlyHint") is True
            declared_read_only = name in declared
            is_allowed = name in allowed and (annotated_read_only or declared_read_only)
            access = "READ_ONLY" if annotated_read_only else "COMPUTE_READ_ONLY" if declared_read_only else "UNVERIFIED"
            rejection_reason = None
            if name in allowed and not (annotated_read_only or declared_read_only):
                rejection_reason = "allowed name lacks read-only evidence"
            elif name not in allowed:
                rejection_reason = "not in Release read-only Tool allowlist"
            item = {
                "name": name,
                "description": str(tool.get("description", "")),
                "input_schema": tool.get("inputSchema") or {},
                "output_schema": tool.get("outputSchema") or {},
                "annotations": annotations,
                "schema_hash": schema_hash(tool),
                "access": access,
                "allowed": is_allowed,
                "rejection_reason": rejection_reason,
            }
            normalized.append(item)
            if not is_allowed:
                rejected.append({"name": name, "reason": rejection_reason, "access": access})
        unsafe_allowed = [item["name"] for item in normalized if item["name"] in allowed and not item["allowed"]]
        if unsafe_allowed:
            raise McpClientError(f"Tool failed read-only validation: {', '.join(unsafe_allowed)}")
        result["tools"] = normalized
        result["allowed_read_only_tools"] = [item["name"] for item in normalized if item["allowed"]]
        result["rejected_tools"] = rejected
    except Exception as exc:
        result["error"] = str(exc)[:2000]
    result["latency_ms"] = round((time.perf_counter() - started) * 1000)
    return result
