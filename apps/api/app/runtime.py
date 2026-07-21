from __future__ import annotations

import json
import re
import time
from typing import Any, Iterator

from . import db, mcp_runtime, rag
from .deepseek import DeepSeekAdapter


ALLOWED_AGENTS = {
    "general-service",
    "complaint-service",
    "work-order-service",
}


def deterministic_route(text: str) -> dict[str, Any]:
    lowered = text.lower()
    if any(word in lowered for word in ("工单", "报修", "进度", "关闭", "创建单")):
        agent = "work-order-service"
        reason = "请求包含工单或事项处理意图"
    elif any(word in lowered for word in ("投诉", "不满", "差评", "生气", "太差", "骗人")):
        agent = "complaint-service"
        reason = "请求包含明确不满或投诉意图"
    else:
        agent = "general-service"
        reason = "请求属于一般咨询或尚无明确专项意图"
    return {
        "target_agent": agent,
        "confidence": 0.72,
        "reason": reason,
        "needs_clarification": False,
        "source": "deterministic_fallback",
    }


def parse_route(content: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if not match:
        raise ValueError("Router did not return a JSON object")
    result = json.loads(match.group(0))
    target = result.get("target_agent")
    if not isinstance(target, str) or target not in ALLOWED_AGENTS:
        raise ValueError("Router must select exactly one allowed Agent")
    confidence = float(result.get("confidence", 0))
    return {
        "target_agent": target,
        "confidence": max(0.0, min(1.0, confidence)),
        "reason": str(result.get("reason", ""))[:300],
        "needs_clarification": bool(result.get("needs_clarification", False)),
        "source": "deepseek_router",
    }


def sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def trace(run: dict[str, Any], event: str, payload: dict[str, Any]) -> None:
    db.append_trace(run["run_id"], run["release_id"], event, payload)


def agent_by_id(config: dict[str, Any], agent_id: str) -> dict[str, Any]:
    matches = [agent for agent in config["agents"] if agent["id"] == agent_id]
    if len(matches) != 1:
        raise ValueError("Release must contain exactly one matching Agent")
    return matches[0]


def released_skills(config: dict[str, Any], agent_id: str) -> list[dict[str, Any]]:
    return [
        skill
        for skill in config.get("skills", [])
        if agent_id in skill.get("agent_ids", [])
    ]


def skill_prompt(skills: list[dict[str, Any]]) -> str:
    if not skills:
        return ""
    blocks = []
    for skill in skills:
        blocks.append(
            "\n".join(
                (
                    f"Skill：{skill['name']}（不可变版本 {skill['skill_version_id']}）",
                    f"适用条件：{skill['applicability']}",
                    f"不适用条件：{skill['non_applicability']}",
                    f"执行正文：\n{skill['content']}",
                    f"输出要求：{skill['output_requirements']}",
                )
            )
        )
    return "\n\n以下是本 Release 已发布并绑定到你的自然语言 Skill，必须遵循：\n" + "\n\n".join(blocks)


def execute_chat(
    conversation_id: str | None, content: str
) -> Iterator[str]:
    run = db.prepare_run(conversation_id, content)
    started = time.perf_counter()
    trace(run, "run_started", {"conversation_id": run["conversation_id"]})
    trace(
        run,
        "user_message_received",
        {
            "message_id": run["user_message_id"],
            "role": "user",
            "content": content,
        },
    )
    trace(
        run,
        "release_pinned",
        {
            "release_id": run["release_id"],
            "release_version": run["release_version"],
        },
    )
    yield sse(
        "run_started",
        {
            "run_id": run["run_id"],
            "conversation_id": run["conversation_id"],
            "release_id": run["release_id"],
            "release_version": run["release_version"],
        },
    )

    adapter = DeepSeekAdapter()
    matching_mcp = mcp_runtime.matching_servers(run["release_config"], content)
    mcp_preflight: dict[str, Any] = {"matched": False}
    trace(
        run,
        "mcp_input_completeness_check",
        {
            "candidate_server_ids": [server["server_id"] for server in matching_mcp],
            "status": "STARTED" if matching_mcp else "NOT_APPLICABLE",
            "raw_user_input": content,
        },
    )
    if matching_mcp:
        try:
            trace(run, "cloud_call_started", {"phase": "mcp_preflight", "model": "deepseek-v4-flash"})
            preflight_content, preflight_snap = adapter.complete(
                mcp_runtime.preflight_messages(matching_mcp, content)
            )
            db.save_cloud_snap(run["run_id"], "mcp_preflight", preflight_snap)
            trace(
                run,
                "cloud_call_completed",
                {
                    "phase": "mcp_preflight",
                    "cloud_call_id": preflight_snap["cloud_call_id"],
                    "usage_status": preflight_snap["usage_status"],
                },
            )
            mcp_preflight = mcp_runtime.enrich_preflight(
                mcp_runtime.parse_preflight(preflight_content, matching_mcp), content
            )
            trace(
                run,
                "mcp_input_completeness_completed",
                {
                    "matched": mcp_preflight.get("matched", False),
                    "server_id": mcp_preflight.get("server_id"),
                    "tool_name": mcp_preflight.get("tool_name"),
                    "missing_fields": mcp_preflight.get("missing_fields", []),
                    "raw_extracted": mcp_preflight.get("raw_extracted", {}),
                },
            )
        except Exception as exc:
            try:
                mcp_preflight = mcp_runtime.config_preflight(matching_mcp[0], content)
                trace(
                    run,
                    "mcp_input_completeness_completed",
                    {
                        "matched": True,
                        "server_id": mcp_preflight["server_id"],
                        "tool_name": mcp_preflight["tool_name"],
                        "missing_fields": mcp_preflight["missing_fields"],
                        "raw_extracted": mcp_preflight["raw_extracted"],
                        "source": mcp_preflight["source"],
                        "model_preflight_error": type(exc).__name__,
                    },
                )
            except Exception as fallback_exc:
                mcp_preflight = {"matched": False, "preflight_error": type(exc).__name__}
                trace(
                    run,
                    "mcp_input_completeness_failed",
                    {"error": type(exc).__name__, "fallback_error": type(fallback_exc).__name__},
                )
    router_prompt = [
        {
            "role": "system",
            "content": (
                "你是唯一 Router。只能从 general-service、complaint-service、"
                "work-order-service 中选择一个。普通咨询选 general-service；"
                "明确不满或投诉选 complaint-service；工单、报修、创建、更新、"
                "关闭、查询进度选 work-order-service。只输出一个 JSON 对象："
                '{"target_agent":"...","confidence":0到1,"reason":"...",'
                '"needs_clarification":false}。禁止数组和多个 Agent。'
            ),
        },
        {"role": "user", "content": content},
    ]

    route: dict[str, Any]
    try:
        trace(run, "cloud_call_started", {"phase": "router", "model": "deepseek-v4-flash"})
        router_content, router_snap = adapter.complete(router_prompt)
        db.save_cloud_snap(run["run_id"], "router", router_snap)
        trace(
            run,
            "cloud_call_completed",
            {
                "phase": "router",
                "cloud_call_id": router_snap["cloud_call_id"],
                "usage_status": router_snap["usage_status"],
            },
        )
        route = parse_route(router_content)
    except Exception as exc:
        route = deterministic_route(content)
        route["fallback_reason"] = type(exc).__name__
        trace(
            run,
            "router_fallback",
            {"reason": type(exc).__name__, "target_agent": route["target_agent"]},
        )

    agent = agent_by_id(run["release_config"], route["target_agent"])
    trace(run, "route_decision", route)
    trace(
        run,
        "agent_selected",
        {"agent_id": agent["id"], "agent_name": agent["name"]},
    )
    mcp_snap: dict[str, Any] | None = None
    mcp_context = ""
    if mcp_preflight.get("matched"):
        server = mcp_preflight["server"]
        if agent["id"] not in server.get("agent_ids", []):
            trace(
                run,
                "mcp_binding_rejected",
                {
                    "server_id": server["server_id"],
                    "agent_id": agent["id"],
                    "reason": "server is not bound to selected Agent in this Release",
                },
            )
        elif mcp_preflight.get("missing_fields"):
            clarification = str(
                (server.get("runtime_config") or {}).get("clarification_prompt")
                or "请一次性补充缺少的信息后再试。"
            )
            trace(
                run,
                "mcp_clarification_requested",
                {
                    "server_id": server["server_id"],
                    "tool_name": mcp_preflight["tool_name"],
                    "missing_fields": mcp_preflight["missing_fields"],
                    "clarification": clarification,
                },
            )
            yield sse("route_decision", route)
            yield sse("agent_selected", {"agent_id": agent["id"], "agent_name": agent["name"]})
            yield sse("delta", {"content": clarification})
            latency_ms = round((time.perf_counter() - started) * 1000)
            result = db.finish_run(
                run["run_id"], run["release_id"], run["conversation_id"],
                agent["id"], clarification, latency_ms,
            )
            trace(
                run,
                "assistant_response_completed",
                {
                    "message_id": result["message_id"], "role": "assistant",
                    "agent_id": agent["id"], "agent_name": agent["name"],
                    "content": clarification,
                },
            )
            done_payload = {
                "run_id": run["run_id"], "status": "DONE", "agent_id": agent["id"],
                "agent_name": agent["name"], "release_id": run["release_id"],
                "release_version": run["release_version"], "latency_ms": latency_ms,
                "estimated_cost": result["estimated_cost"],
                "estimated_cost_cny": result["estimated_cost_cny"],
                "display_currency": "CNY", "clarification_required": True,
                "missing_fields": mcp_preflight["missing_fields"],
            }
            trace(run, "done", done_payload)
            yield sse("done", done_payload)
            return
        else:
            trace(
                run,
                "mcp_tool_selected",
                {
                    "server_id": server["server_id"], "server_name": server["name"],
                    "tool_name": mcp_preflight["tool_name"], "agent_id": agent["id"],
                    "release_id": run["release_id"], "release_version": run["release_version"],
                },
            )
            trace(
                run,
                "mcp_parameters_extracted",
                {
                    "raw_user_input": content,
                    "raw_extracted": mcp_preflight.get("raw_extracted", {}),
                    "tool_arguments": mcp_preflight["arguments"],
                },
            )
            trace(
                run,
                "mcp_request",
                {
                    "server_id": server["server_id"], "server_name": server["name"],
                    "git_url": server["git_url"], "version_ref": server["version_ref"],
                    "endpoint": server["endpoint"], "transport": server["transport"],
                    "tool_name": mcp_preflight["tool_name"],
                    "arguments": mcp_preflight["arguments"],
                    "release_id": run["release_id"], "model_api_cost": 0,
                },
            )
            try:
                mcp_snap = mcp_runtime.call_release_tool(
                    run, server, mcp_preflight["tool_name"], mcp_preflight["arguments"]
                )
                trace(
                    run,
                    "mcp_response",
                    {
                        **mcp_snap,
                        "request_args": mcp_preflight["arguments"],
                        "release_id": run["release_id"],
                    },
                )
                mcp_context = mcp_runtime.prompt_context(mcp_snap, server)
            except Exception as exc:
                trace(
                    run,
                    "mcp_response",
                    {
                        "server_id": server["server_id"], "server_name": server["name"],
                        "tool_name": mcp_preflight["tool_name"], "status": "FAILED",
                        "error_message": f"{type(exc).__name__}: {str(exc)}"[:1000], "model_api_cost": 0,
                        "release_id": run["release_id"],
                    },
                )
                mcp_context = (
                    "\n\nThe selected remote read-only Tool failed. State that the requested live data "
                    "is temporarily unavailable and do not fabricate a result."
                )
    skills = released_skills(run["release_config"], agent["id"])
    trace(
        run,
        "skill_considered",
        {
            "agent_id": agent["id"],
            "published_binding_count": len(skills),
            "skill_version_ids": [skill["skill_version_id"] for skill in skills],
        },
    )
    for skill in skills:
        trace(
            run,
            "skill_activated",
            {
                "skill_id": skill["skill_id"],
                "skill_version_id": skill["skill_version_id"],
                "version_number": skill["version_number"],
                "name": skill["name"],
                "content_hash": skill["content_hash"],
                "agent_id": agent["id"],
            },
        )
    trace(
        run,
        "rag_retrieval_requested",
        {
            "agent_id": agent["id"],
            "query": content,
            "release_id": run["release_id"],
            "published_rag_version_ids": [
                item["rag_version_id"]
                for item in run["release_config"].get("rag", [])
                if agent["id"] in item.get("agent_ids", [])
            ],
        },
    )
    rag_result = rag.retrieve_release(run["release_config"], agent["id"], content)
    trace(
        run,
        "rag_retrieval_completed",
        {
            **rag_result,
            "evidence": [
                {
                    "document_id": item["document_id"],
                    "document_name": item["document_name"],
                    "rag_version_id": item["rag_version_id"],
                    "chunk_id": item["chunk_id"],
                    "heading": item["heading"],
                    "keyword_score": item["keyword_score"],
                    "vector_score": item["vector_score"],
                    "hybrid_score": item["hybrid_score"],
                    "citation": item["citation"],
                    "content_hash": item["content_hash"],
                    "content_length": len(item["content"]),
                    "content": item["content"],
                }
                for item in rag_result["evidence"]
            ],
            "release_id": run["release_id"],
            "release_version": run["release_version"],
            "model_api_cost": 0,
        },
    )
    yield sse("route_decision", route)
    yield sse(
        "agent_selected",
        {"agent_id": agent["id"], "agent_name": agent["name"]},
    )

    history = db.conversation_history(run["conversation_id"], limit=12)
    messages = [
        {
            "role": "system",
            "content": agent["system_prompt"] + skill_prompt(skills) + rag.prompt_context(rag_result) + mcp_context,
        },
        *history,
    ]
    answer_parts: list[str] = []
    final_snap: dict[str, Any] | None = None
    try:
        trace(
            run,
            "cloud_call_started",
            {"phase": "main_agent", "model": "deepseek-v4-flash"},
        )
        yield sse(
            "cloud_call_started",
            {"phase": "main_agent", "model": "deepseek-v4-flash"},
        )
        for item in adapter.stream(messages):
            if item["kind"] == "delta":
                answer_parts.append(item["content"])
            elif item["kind"] == "result":
                final_snap = item["snap"]
        if final_snap is None:
            raise RuntimeError("DeepSeek stream ended without a final Snap")
        db.save_cloud_snap(run["run_id"], "main_agent", final_snap)
        trace(
            run,
            "cloud_call_completed",
            {
                "phase": "main_agent",
                "cloud_call_id": final_snap["cloud_call_id"],
                "usage_status": final_snap["usage_status"],
            },
        )
        answer, used_citations, removed_citations = rag.sanitize_citations(
            "".join(answer_parts), rag_result["citations"]
        )
        trace(
            run,
            "rag_citation_validation",
            {
                "allowed_citations": rag_result["citations"],
                "used_citations": used_citations,
                "removed_unknown_citations": removed_citations,
            },
        )
        for index in range(0, len(answer), 96):
            yield sse("delta", {"content": answer[index : index + 96]})
        latency_ms = round((time.perf_counter() - started) * 1000)
        result = db.finish_run(
            run["run_id"],
            run["release_id"],
            run["conversation_id"],
            agent["id"],
            answer,
            latency_ms,
        )
        trace(
            run,
            "assistant_response_completed",
            {
                "message_id": result["message_id"],
                "role": "assistant",
                "agent_id": agent["id"],
                "agent_name": agent["name"],
                "content": answer,
            },
        )
        done_payload = {
            "run_id": run["run_id"],
            "status": "DONE",
            "agent_id": agent["id"],
            "agent_name": agent["name"],
            "release_id": run["release_id"],
            "release_version": run["release_version"],
            "latency_ms": latency_ms,
            "estimated_cost": result["estimated_cost"],
            "estimated_cost_cny": result["estimated_cost_cny"],
            "display_currency": "CNY",
            "usage": {
                "prompt_cache_miss_tokens": final_snap.get(
                    "prompt_cache_miss_tokens"
                ),
                "prompt_cache_hit_tokens": final_snap.get(
                    "prompt_cache_hit_tokens"
                ),
                "completion_tokens": final_snap.get("completion_tokens"),
                "usage_status": final_snap["usage_status"],
            },
            "rag": {
                "evidence_count": len(rag_result["evidence"]),
                "citations": rag_result["citations"],
                "used_citations": used_citations,
                "injected_char_count": rag_result["injected_char_count"],
            },
            "mcp": {
                "called": mcp_snap is not None,
                "server_id": mcp_snap.get("server_id") if mcp_snap else None,
                "tool_name": mcp_snap.get("tool_name") if mcp_snap else None,
                "status": mcp_snap.get("status") if mcp_snap else None,
                "model_api_cost": 0,
            },
        }
        trace(run, "done", done_payload)
        yield sse("done", done_payload)
    except Exception as exc:
        error_code = type(exc).__name__
        db.fail_run(run["run_id"], error_code)
        trace(run, "error", {"error_code": error_code})
        yield sse(
            "error",
            {
                "run_id": run["run_id"],
                "status": "ERROR",
                "error_code": error_code,
                "message": "本轮运行失败，请在平台管理的 Run 与 Trace 中查看证据。",
            },
        )
