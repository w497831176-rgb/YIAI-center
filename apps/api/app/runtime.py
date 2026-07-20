from __future__ import annotations

import json
import re
import time
from typing import Any, Iterator

from . import db
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
    yield sse("route_decision", route)
    yield sse(
        "agent_selected",
        {"agent_id": agent["id"], "agent_name": agent["name"]},
    )

    history = db.conversation_history(run["conversation_id"], limit=12)
    messages = [{"role": "system", "content": agent["system_prompt"]}, *history]
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
                yield sse("delta", {"content": item["content"]})
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
        answer = "".join(answer_parts)
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
