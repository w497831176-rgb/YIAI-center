from __future__ import annotations

import json
import re
import time
from typing import Any, Iterator

from . import action_gateway, codrive, db, mcp_runtime, rag, work_orders
from .deepseek import DeepSeekAdapter


def _route_terms(text: str) -> set[str]:
    lowered = text.lower()
    terms = set(re.findall(r"[a-z0-9_-]{2,}", lowered))
    for block in re.findall(r"[\u4e00-\u9fff]+", lowered):
        terms.update(block[index : index + 2] for index in range(max(0, len(block) - 1)))
    return terms


def _released_tool_profile(
    release_config: dict[str, Any] | None, agent_id: str
) -> str:
    if not release_config:
        return ""
    blocks = []
    for tool in release_config.get("tools", []):
        if agent_id not in tool.get("agent_ids", []):
            continue
        blocks.append(
            " ".join(
                str(tool.get(key, ""))
                for key in ("tool_id", "name", "description")
            )
        )
    return " ".join(blocks)


def deterministic_route(
    text: str,
    agents: list[dict[str, Any]],
    release_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not agents:
        raise ValueError("Release does not contain an Agent")
    input_terms = _route_terms(text)
    ranked = []
    for index, item in enumerate(agents):
        profile = " ".join(
            [
                *(str(item.get(key, "")) for key in ("name", "description", "system_prompt")),
                _released_tool_profile(release_config, str(item.get("id", ""))),
            ]
        )
        score = len(input_terms & _route_terms(profile))
        ranked.append((score, -index, item))
    score, _index, selected = max(ranked, key=lambda item: (item[0], item[1]))
    agent = str(selected["id"])
    reason = (
        f"用户请求与该 Agent 的说明及已发布 Tool 能力匹配（得分 {score}）"
        if score
        else "模型 Router 不可用，按当前 Release 中的 Agent 顺序安全兜底"
    )
    return {
        "target_agent": agent,
        "confidence": 0.72,
        "reason": reason,
        "needs_clarification": False,
        "source": "deterministic_fallback",
    }


def parse_route(
    content: str, allowed_agent_ids: set[str] | None = None
) -> dict[str, Any]:
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if not match:
        raise ValueError("Router did not return a JSON object")
    result = json.loads(match.group(0))
    target = result.get("target_agent")
    if not isinstance(target, str) or (
        allowed_agent_ids is not None and target not in allowed_agent_ids
    ):
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


def select_released_skills(
    config: dict[str, Any], agent_id: str, content: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected = []
    decisions = []
    content_terms = _route_terms(content)
    for skill in released_skills(config, agent_id):
        positive_profile = " ".join(
            str(skill.get(key, ""))
            for key in ("name", "description", "applicability", "content", "output_requirements")
        )
        negative_profile = str(skill.get("non_applicability", ""))
        positive_score = len(content_terms & _route_terms(positive_profile))
        negative_score = len(content_terms & _route_terms(negative_profile))
        activated = positive_score > 0 and negative_score == 0
        decisions.append(
            {
                "skill_id": skill["skill_id"],
                "skill_version_id": skill["skill_version_id"],
                "name": skill["name"],
                "positive_match_score": positive_score,
                "negative_match_score": negative_score,
                "activated": activated,
                "reason": "用户请求命中适用条件且未命中不适用条件"
                if activated
                else "本次请求未满足该 Skill 的适用条件",
            }
        )
        if activated:
            selected.append(skill)
    return selected, decisions


def is_ambiguous_request(content: str) -> bool:
    normalized = re.sub(r"[\s，。！？、,.!?]", "", content)
    vague_phrases = (
        "帮我处理一下",
        "帮我弄一下",
        "尽快处理",
        "越快越好",
        "帮我看一下",
    )
    concrete_markers = (
        "工单",
        "投诉",
        "查询",
        "创建",
        "更新",
        "关闭",
        "删除",
        "MCP",
        "Streamable",
        "故障",
        "损失",
        "规则",
    )
    return (
        any(phrase in normalized for phrase in vague_phrases)
        and not any(marker.lower() in normalized.lower() for marker in concrete_markers)
        and len(normalized) <= 24
    )


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


def _evaluate_and_trace(run: dict[str, Any]) -> dict[str, Any]:
    evaluation = db.save_run_evaluation(run["run_id"])
    trace(
        run,
        "evaluation_completed",
        {
            "evaluation_id": evaluation["id"],
            "status": evaluation["status"],
            "score": evaluation["score"],
            "checks": evaluation["checks"],
            "badcase_codes": evaluation["badcase_codes"],
            "scope": "CURRENT_RUN_ONLY",
        },
    )
    return evaluation


def _finish_deterministic(
    run: dict[str, Any],
    agent: dict[str, Any],
    answer: str,
    started: float,
    *,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
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
    evaluation = _evaluate_and_trace(run)
    payload = {
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
        "evaluation": {
            "status": evaluation["status"],
            "score": evaluation["score"],
            "badcase_codes": evaluation["badcase_codes"],
        },
        **(extra or {}),
    }
    trace(run, "done", payload)
    return payload


def _action_summary(action: dict[str, Any]) -> str:
    tool_name = action["tool_name"]
    payload = action["payload"]
    before = action.get("before")
    if tool_name == "create_work_order":
        lines = [
            "已生成创建工单草稿，尚未写入数据库：",
            f"- 主题：{payload['subject']}",
            f"- 描述：{payload['description']}",
            f"- 类别：{payload['category']}",
            f"- 优先级：{payload['priority']}",
        ]
    elif tool_name == "update_work_order":
        lines = [
            f"已生成工单 {payload['work_order_id']} 的更新草稿，尚未写入：",
            f"- 更新前：{json.dumps(before, ensure_ascii=False)}",
            f"- 计划变化：{json.dumps(payload['changes'], ensure_ascii=False)}",
        ]
    elif tool_name == "close_work_order":
        lines = [
            f"已生成关闭工单 {payload['work_order_id']} 的草稿，尚未写入：",
            f"- 当前状态：{before.get('status') if before else '未知'}",
            f"- 处理结果：{payload['result']}",
        ]
    else:
        lines = [
            f"已生成删除工单 {payload['work_order_id']} 的草稿，尚未删除。",
            "删除采用软删除并保留完整审计，需要连续完成两次确认。",
        ]
    lines.append(f"操作编号：{action['id']}。请在确认卡中确认或取消。")
    return "\n".join(lines)


def execute_chat(
    conversation_id: str | None,
    content: str,
    *,
    release_id_override: str | None = None,
    resume_from_human: bool = False,
) -> Iterator[str]:
    run = db.prepare_run(
        conversation_id, content, release_id_override=release_id_override
    )
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

    if not resume_from_human and codrive.is_human_output_state(run["conversation_id"]):
        state = codrive.get_session(run["conversation_id"], include_events=False)
        trace(
            run,
            "codrive_ai_suppressed",
            {
                "conversation_id": run["conversation_id"],
                "state": state["state"],
                "reason": "当前输出权属于员工或等待员工接受",
                "ai_standby": True,
            },
        )
        latency_ms = round((time.perf_counter() - started) * 1000)
        db.finish_run_without_answer(run["run_id"], agent_id=None, latency_ms=latency_ms)
        done = {
            "run_id": run["run_id"],
            "status": "DONE",
            "release_id": run["release_id"],
            "release_version": run["release_version"],
            "latency_ms": latency_ms,
            "human_active": True,
            "codrive": state,
            "estimated_cost": None,
            "estimated_cost_cny": None,
            "display_currency": "CNY",
        }
        trace(run, "done", done)
        yield sse("human_active", state)
        yield sse("done", done)
        return

    adapter: DeepSeekAdapter | None = None
    adapter_init_error: Exception | None = None
    try:
        adapter = DeepSeekAdapter()
    except Exception as exc:
        adapter_init_error = exc
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
            if adapter is None:
                raise adapter_init_error or RuntimeError("Model Adapter unavailable")
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
    released_agents = run["release_config"].get("agents") or []
    allowed_agent_ids = {
        str(item.get("id")) for item in released_agents if item.get("id")
    }
    if not allowed_agent_ids:
        raise ValueError("Active Release does not contain an Agent")
    agent_catalog = [
        {
            "id": item["id"],
            "name": item.get("name", item["id"]),
            "description": item.get("description", ""),
            "released_tools": [
                {
                    "tool_id": tool.get("tool_id"),
                    "name": tool.get("name", ""),
                    "description": tool.get("description", ""),
                }
                for tool in run["release_config"].get("tools", [])
                if item["id"] in tool.get("agent_ids", [])
            ],
        }
        for item in released_agents
    ]
    router_prompt = [
        {
            "role": "system",
            "content": (
                "你是唯一 Router。只能从当前 Release 提供的 Agent 清单中"
                "选择一个，根据名称和业务说明匹配用户意图。\n"
                f"Agent 清单：{json.dumps(agent_catalog, ensure_ascii=False)}\n"
                "只输出一个 JSON 对象："
                '{"target_agent":"...","confidence":0到1,"reason":"...",'
                '"needs_clarification":false}。禁止数组和多个 Agent。'
            ),
        },
        {"role": "user", "content": content},
    ]

    route: dict[str, Any]
    try:
        if adapter is None:
            raise adapter_init_error or RuntimeError("Model Adapter unavailable")
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
        route = parse_route(router_content, allowed_agent_ids)
    except Exception as exc:
        route = deterministic_route(content, released_agents, run["release_config"])
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
        {
            "agent_id": agent["id"],
            "agent_name": agent["name"],
            "route_source": route.get("source"),
            "route_reason": route.get("reason"),
        },
    )

    if not resume_from_human and is_ambiguous_request(content):
        route["confidence"] = min(float(route.get("confidence", 0)), 0.45)
        route["needs_clarification"] = True
        route["reason"] = "请求缺少处理对象、问题事实和期望结果，无法可靠选择具体执行能力"
        candidate = db.record_badcase_candidate(
            run["run_id"],
            "ROUTER_LOW_CONFIDENCE",
            {
                "content": content,
                "confidence": route["confidence"],
                "reason": route["reason"],
                "selected_agent_id": agent["id"],
            },
        )
        trace(run, "route_decision", route)
        trace(
            run,
            "badcase_detected",
            {
                "candidate_id": candidate["id"],
                "rule_code": candidate["rule_code"],
                "status": candidate["status"],
                "evidence": candidate["evidence"],
                "scope": "CURRENT_RUN_ONLY",
            },
        )
        answer = (
            "可以帮你处理，但目前还缺少必要信息。请一次性告诉我："
            "要处理的对象、具体问题、已经发生了什么，以及你希望得到的结果。"
        )
        yield sse("route_decision", route)
        yield sse("agent_selected", {"agent_id": agent["id"], "agent_name": agent["name"]})
        yield sse("delta", {"content": answer})
        done = _finish_deterministic(
            run,
            agent,
            answer,
            started,
            extra={"clarification_required": True, "badcase": candidate},
        )
        yield sse("done", done)
        return

    explicit_handoff = not resume_from_human and codrive.is_handoff_request(content)
    ai_handoff = codrive.assess_ai_handoff(content)
    trace(
        run,
        "codrive_policy_evaluated",
        {
            **ai_handoff,
            "explicit_user_request": explicit_handoff,
            "selected_agent_id": agent["id"],
        },
    )
    if not resume_from_human and (explicit_handoff or ai_handoff["should_handoff"]):
        source = "USER_EXPLICIT" if explicit_handoff else "AI_POLICY"
        reason = content if explicit_handoff else ai_handoff["reason"]
        actor = "USER" if explicit_handoff else "AI"
        session = codrive.request_human(
            run["conversation_id"],
            actor=actor,
            reason=reason,
            summary=(
                "用户主动要求员工承接；请阅读完整会话、最近 Run 和未完成操作。"
                if explicit_handoff
                else "AI 根据重复失败与高风险信号发起升级；请核对风险、影响和既往处理记录。"
            ),
        )
        trace(
            run,
            "codrive_handoff_requested",
            {
                "conversation_id": run["conversation_id"],
                "state": session["state"],
                "version": session["version"],
                "ai_standby": True,
                "source": source,
                "reason": reason,
                "rule_code": ai_handoff["rule_code"] if not explicit_handoff else "USER_EXPLICIT_REQUEST",
                "signals": ai_handoff["signals"],
                "agent_id": agent["id"],
            },
        )
        answer = (
            "已按你的明确要求发起人机共驾。员工可在员工工作台查看完整对话和交接信息。"
            if explicit_handoff
            else "我判断本问题已出现重复失败，并伴随潜在损失或紧急升级信号，已发起人机共驾。"
        ) + "AI 会始终保持待命；员工点击“交还 AI”后，我会继续承接，而不是结束会话。"
        yield sse("route_decision", route)
        yield sse("agent_selected", {"agent_id": agent["id"], "agent_name": agent["name"]})
        yield sse("codrive", session)
        yield sse("delta", {"content": answer})
        done = _finish_deterministic(
            run,
            agent,
            answer,
            started,
            extra={
                "codrive": session,
                "handoff_source": source,
                "handoff_rule": ai_handoff["rule_code"] if not explicit_handoff else "USER_EXPLICIT_REQUEST",
            },
        )
        yield sse("done", done)
        return

    released_tool_ids = work_orders.tool_ids_for_agent(
        run["release_config"], agent["id"]
    )
    preset_read_result: dict[str, Any] | None = None
    preset_context = ""
    write_plan = work_orders.plan_write(content, released_tool_ids)
    if write_plan:
        trace(
            run,
            "preset_tool_selected",
            {
                "tool_name": write_plan["tool_id"],
                "read_only": False,
                "agent_id": agent["id"],
                "release_id": run["release_id"],
            },
        )
        yield sse("route_decision", route)
        yield sse(
            "agent_selected",
            {"agent_id": agent["id"], "agent_name": agent["name"]},
        )
        if write_plan["missing_fields"]:
            missing = "、".join(write_plan["missing_fields"])
            answer = (
                f"要生成 {write_plan['tool_id']} 草稿，还需要一次性补充：{missing}。"
                "信息完整后我只会生成确认卡，未经确认不会写入工单。"
            )
            trace(
                run,
                "action_draft_information_incomplete",
                {
                    "tool_name": write_plan["tool_id"],
                    "missing_fields": write_plan["missing_fields"],
                    "raw_user_input": content,
                },
            )
            yield sse("delta", {"content": answer})
            done = _finish_deterministic(
                run,
                agent,
                answer,
                started,
                extra={"action": {"draft_created": False, "missing_fields": write_plan["missing_fields"]}},
            )
            yield sse("done", done)
            return
        action = action_gateway.create_draft(
            tool_name=write_plan["tool_id"],
            payload=write_plan["payload"],
            release_id=run["release_id"],
            idempotency_key=f"{run['run_id']}:{write_plan['tool_id']}",
            conversation_id=run["conversation_id"],
            source_run_id=run["run_id"],
            actor="USER",
        )
        trace(
            run,
            "action_draft_created",
            {
                "action_id": action["id"],
                "tool_name": action["tool_name"],
                "payload": action["payload"],
                "before": action["before"],
                "status": action["status"],
                "required_confirmations": action["required_confirmations"],
                "confirmation_token_persisted": False,
            },
        )
        answer = _action_summary(action)
        yield sse("action_pending", action)
        yield sse("delta", {"content": answer})
        done = _finish_deterministic(
            run,
            agent,
            answer,
            started,
            extra={
                "action": {
                    "action_id": action["id"],
                    "tool_name": action["tool_name"],
                    "status": action["status"],
                    "required_confirmations": action["required_confirmations"],
                }
            },
        )
        yield sse("done", done)
        return

    read_plan = work_orders.plan_read(content, released_tool_ids)
    if read_plan:
        trace(
            run,
            "preset_tool_selected",
            {
                "tool_name": read_plan["tool_id"],
                "read_only": True,
                "agent_id": agent["id"],
                "release_id": run["release_id"],
            },
        )
        trace(
            run,
            "preset_tool_request",
            {
                "tool_name": read_plan["tool_id"],
                "arguments": read_plan["arguments"],
                "started_at": db.now_iso(),
                "model_api_cost": 0,
            },
        )
        tool_started = time.perf_counter()
        try:
            preset_read_result = work_orders.execute_read(
                read_plan["tool_id"], read_plan["arguments"]
            )
            tool_latency_ms = round((time.perf_counter() - tool_started) * 1000)
            trace(
                run,
                "preset_tool_response",
                {
                    "tool_name": read_plan["tool_id"],
                    "status": "SUCCESS",
                    "result": preset_read_result,
                    "result_length": len(json.dumps(preset_read_result, ensure_ascii=False)),
                    "latency_ms": tool_latency_ms,
                    "finished_at": db.now_iso(),
                    "model_api_cost": 0,
                },
            )
            preset_context = (
                "\n\n以下是当前 Release 允许的预置只读 Tool 返回的真实工单数据。"
                "只能依据这些字段回答，不得补造：\n"
                + json.dumps(preset_read_result, ensure_ascii=False)
            )
        except Exception as exc:
            candidate = db.record_badcase_candidate(
                run["run_id"],
                "PRESET_TOOL_CALL_FAILED",
                {
                    "tool_name": read_plan["tool_id"],
                    "error": f"{type(exc).__name__}: {str(exc)}"[:1000],
                },
            )
            trace(
                run,
                "preset_tool_response",
                {
                    "tool_name": read_plan["tool_id"],
                    "status": "FAILED",
                    "error": f"{type(exc).__name__}: {str(exc)}"[:1000],
                    "latency_ms": round((time.perf_counter() - tool_started) * 1000),
                    "finished_at": db.now_iso(),
                    "model_api_cost": 0,
                },
            )
            trace(
                run,
                "badcase_detected",
                {
                    "candidate_id": candidate["id"],
                    "rule_code": candidate["rule_code"],
                    "status": candidate["status"],
                    "evidence": candidate["evidence"],
                    "scope": "CURRENT_RUN_ONLY",
                },
            )
            preset_context = "\n\n预置工单 Tool 调用失败。必须明确说明暂时无法取得工单事实，不得编造。"
    mcp_snap: dict[str, Any] | None = None
    mcp_context = ""
    if mcp_preflight.get("matched"):
        server = mcp_preflight["server"]
        if not mcp_runtime.tool_bound_to_agent(
            server, str(mcp_preflight.get("tool_name", "")), agent["id"]
        ):
            trace(
                run,
                "mcp_binding_rejected",
                {
                    "server_id": server["server_id"],
                    "agent_id": agent["id"],
                    "reason": "Tool is not bound to selected Agent in this Release",
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
            evaluation = _evaluate_and_trace(run)
            done_payload = {
                "run_id": run["run_id"], "status": "DONE", "agent_id": agent["id"],
                "agent_name": agent["name"], "release_id": run["release_id"],
                "release_version": run["release_version"], "latency_ms": latency_ms,
                "estimated_cost": result["estimated_cost"],
                "estimated_cost_cny": result["estimated_cost_cny"],
                "display_currency": "CNY", "clarification_required": True,
                "missing_fields": mcp_preflight["missing_fields"],
                "evaluation": {
                    "status": evaluation["status"],
                    "score": evaluation["score"],
                    "badcase_codes": evaluation["badcase_codes"],
                },
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
                candidate = db.record_badcase_candidate(
                    run["run_id"],
                    "MCP_CALL_FAILED",
                    {
                        "server_id": server["server_id"],
                        "tool_name": mcp_preflight["tool_name"],
                        "error": f"{type(exc).__name__}: {str(exc)}"[:1000],
                    },
                )
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
                trace(
                    run,
                    "badcase_detected",
                    {
                        "candidate_id": candidate["id"],
                        "rule_code": candidate["rule_code"],
                        "status": candidate["status"],
                        "evidence": candidate["evidence"],
                        "scope": "CURRENT_RUN_ONLY",
                    },
                )
                mcp_context = (
                    "\n\nThe selected remote read-only Tool failed. State that the requested live data "
                    "is temporarily unavailable and do not fabricate a result."
                )
    skills, skill_decisions = select_released_skills(
        run["release_config"], agent["id"], content
    )
    trace(
        run,
        "skill_considered",
        {
            "agent_id": agent["id"],
            "published_binding_count": len(skill_decisions),
            "activated_count": len(skills),
            "skill_version_ids": [skill["skill_version_id"] for skill in skills],
            "decisions": skill_decisions,
        },
    )
    for decision in skill_decisions:
        if not decision["activated"]:
            trace(run, "skill_skipped", decision)
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
            "content": agent["system_prompt"] + skill_prompt(skills) + rag.prompt_context(rag_result) + mcp_context + preset_context,
        },
        *history,
    ]
    answer_parts: list[str] = []
    final_snap: dict[str, Any] | None = None
    try:
        if adapter is None:
            raise adapter_init_error or RuntimeError("Model Adapter unavailable")
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
        if removed_citations:
            candidate = db.record_badcase_candidate(
                run["run_id"],
                "RAG_UNKNOWN_CITATION_REMOVED",
                {"removed_unknown_citations": removed_citations},
            )
            trace(
                run,
                "badcase_detected",
                {
                    "candidate_id": candidate["id"],
                    "rule_code": candidate["rule_code"],
                    "status": candidate["status"],
                    "evidence": candidate["evidence"],
                    "scope": "CURRENT_RUN_ONLY",
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
        evaluation = _evaluate_and_trace(run)
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
            "evaluation": {
                "status": evaluation["status"],
                "score": evaluation["score"],
                "badcase_codes": evaluation["badcase_codes"],
            },
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
            "preset_tool": {
                "called": preset_read_result is not None,
                "tool_name": preset_read_result.get("tool_name") if preset_read_result else None,
                "model_api_cost": 0,
            },
        }
        trace(run, "done", done_payload)
        yield sse("done", done_payload)
    except Exception as exc:
        if preset_read_result is not None:
            trace(
                run,
                "cloud_call_failed",
                {
                    "phase": "main_agent",
                    "model": "deepseek-v4-flash",
                    "error_code": type(exc).__name__,
                    "fallback": "deterministic_preset_tool_answer",
                },
            )
            answer = work_orders.format_read_answer(preset_read_result)
            for index in range(0, len(answer), 96):
                yield sse("delta", {"content": answer[index : index + 96]})
            done = _finish_deterministic(
                run,
                agent,
                answer,
                started,
                extra={
                    "degraded": True,
                    "degraded_reason": "main_agent_model_unavailable",
                    "preset_tool": {
                        "called": True,
                        "tool_name": preset_read_result.get("tool_name"),
                        "model_api_cost": 0,
                    },
                },
            )
            yield sse("done", done)
            return
        error_code = type(exc).__name__
        db.fail_run(run["run_id"], error_code)
        trace(run, "error", {"error_code": error_code})
        _evaluate_and_trace(run)
        yield sse(
            "error",
            {
                "run_id": run["run_id"],
                "status": "ERROR",
                "error_code": error_code,
                "message": "本轮运行失败，请在平台管理的 Run 与 Trace 中查看证据。",
            },
        )
