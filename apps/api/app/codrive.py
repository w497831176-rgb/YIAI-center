from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


MIGRATION_9 = """
CREATE TABLE IF NOT EXISTS codrive_sessions (
    conversation_id TEXT PRIMARY KEY REFERENCES conversations(id),
    state TEXT NOT NULL CHECK(state IN (
        'AI_ACTIVE','HANDOFF_REQUESTED','HUMAN_ACTIVE','AI_RESUMING'
    )),
    version INTEGER NOT NULL DEFAULT 1,
    requested_by TEXT,
    request_reason TEXT NOT NULL DEFAULT '',
    handoff_summary TEXT NOT NULL DEFAULT '',
    requested_at TEXT,
    human_activated_at TEXT,
    returned_at TEXT,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS codrive_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL REFERENCES conversations(id),
    sequence INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    from_state TEXT,
    to_state TEXT NOT NULL,
    actor TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(conversation_id, sequence)
);
CREATE TABLE IF NOT EXISTS human_messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id),
    role TEXT NOT NULL CHECK(role IN ('staff')),
    content TEXT NOT NULL,
    codrive_version INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_codrive_state_updated
ON codrive_sessions(state, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_human_messages_conversation
ON human_messages(conversation_id, created_at);
"""


ACTIVE_STATES = {"HANDOFF_REQUESTED", "HUMAN_ACTIVE", "AI_RESUMING"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _event(
    conn,
    conversation_id: str,
    event_type: str,
    from_state: str | None,
    to_state: str,
    actor: str,
    payload: dict[str, Any],
    created_at: str,
) -> None:
    sequence = conn.execute(
        "SELECT COALESCE(MAX(sequence), 0) + 1 AS next FROM codrive_events WHERE conversation_id=?",
        (conversation_id,),
    ).fetchone()["next"]
    conn.execute(
        """
        INSERT INTO codrive_events(
            conversation_id, sequence, event_type, from_state, to_state,
            actor, payload_json, created_at
        ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            conversation_id,
            sequence,
            event_type,
            from_state,
            to_state,
            actor,
            json.dumps(payload, ensure_ascii=False),
            created_at,
        ),
    )


def ensure_session(conn, conversation_id: str, now: str | None = None):
    created_at = now or _now()
    exists = conn.execute(
        "SELECT 1 FROM conversations WHERE id=?", (conversation_id,)
    ).fetchone()
    if exists is None:
        raise KeyError(conversation_id)
    conn.execute(
        """
        INSERT OR IGNORE INTO codrive_sessions(
            conversation_id, state, version, requested_by, request_reason,
            handoff_summary, requested_at, human_activated_at, returned_at,
            updated_at
        ) VALUES(?, 'AI_ACTIVE', 1, NULL, '', '', NULL, NULL, NULL, ?)
        """,
        (conversation_id, created_at),
    )
    return conn.execute(
        "SELECT * FROM codrive_sessions WHERE conversation_id=?", (conversation_id,)
    ).fetchone()


def _session_dict(row) -> dict[str, Any]:
    result = dict(row)
    result["ai_standby"] = True
    result["human_has_output_right"] = result["state"] == "HUMAN_ACTIVE"
    result["can_return_to_ai"] = result["state"] == "HUMAN_ACTIVE"
    result["can_request_human"] = result["state"] == "AI_ACTIVE"
    return result


def get_state(conversation_id: str | None) -> str:
    if not conversation_id:
        return "AI_ACTIVE"
    from . import db

    with db.connection() as conn:
        row = conn.execute(
            "SELECT state FROM codrive_sessions WHERE conversation_id=?",
            (conversation_id,),
        ).fetchone()
    return row["state"] if row else "AI_ACTIVE"


def request_human(
    conversation_id: str,
    *,
    actor: str,
    reason: str,
    summary: str = "",
    expected_version: int | None = None,
) -> dict[str, Any]:
    from . import db

    actor = actor.upper()
    if actor not in {"USER", "AI"}:
        raise ValueError("actor 必须是 USER 或 AI")
    reason = str(reason).strip()
    if not reason:
        raise ValueError("请说明请求人机共驾的原因")
    now = _now()
    with db.connection() as conn:
        row = ensure_session(conn, conversation_id, now)
        if row["state"] in ACTIVE_STATES:
            return _session_dict(row)
        if row["state"] != "AI_ACTIVE":
            raise ValueError("当前状态不能发起人机共驾")
        if expected_version is not None and int(expected_version) != int(row["version"]):
            raise RuntimeError("会话状态已变化，请刷新后重试")
        next_version = int(row["version"]) + 1
        conn.execute(
            """
            UPDATE codrive_sessions
            SET state='HANDOFF_REQUESTED', version=?, requested_by=?,
                request_reason=?, handoff_summary=?, requested_at=?, updated_at=?
            WHERE conversation_id=?
            """,
            (next_version, actor, reason, summary, now, now, conversation_id),
        )
        _event(
            conn,
            conversation_id,
            "handoff_requested",
            "AI_ACTIVE",
            "HANDOFF_REQUESTED",
            actor,
            {"reason": reason, "summary": summary},
            now,
        )
        return _session_dict(
            conn.execute(
                "SELECT * FROM codrive_sessions WHERE conversation_id=?",
                (conversation_id,),
            ).fetchone()
        )


def accept_handoff(
    conversation_id: str,
    *,
    expected_version: int | None = None,
) -> dict[str, Any]:
    from . import db

    now = _now()
    with db.connection() as conn:
        row = ensure_session(conn, conversation_id, now)
        if row["state"] == "HUMAN_ACTIVE":
            return _session_dict(row)
        if row["state"] != "HANDOFF_REQUESTED":
            raise ValueError("当前没有待接受的人机共驾请求")
        if expected_version is not None and int(expected_version) != int(row["version"]):
            raise RuntimeError("会话状态已变化，请刷新后重试")
        next_version = int(row["version"]) + 1
        conn.execute(
            """
            UPDATE codrive_sessions
            SET state='HUMAN_ACTIVE', version=?, human_activated_at=?, updated_at=?
            WHERE conversation_id=?
            """,
            (next_version, now, now, conversation_id),
        )
        _event(
            conn,
            conversation_id,
            "human_activated",
            "HANDOFF_REQUESTED",
            "HUMAN_ACTIVE",
            "STAFF",
            {},
            now,
        )
        return _session_dict(
            conn.execute(
                "SELECT * FROM codrive_sessions WHERE conversation_id=?",
                (conversation_id,),
            ).fetchone()
        )


def add_staff_message(
    conversation_id: str,
    content: str,
    *,
    expected_version: int,
) -> dict[str, Any]:
    from . import db

    content = str(content).strip()
    if not content or len(content) > 8000:
        raise ValueError("员工回复必须为 1-8000 个字符")
    now = _now()
    message_id = db.new_id("humanmsg")
    with db.connection() as conn:
        row = ensure_session(conn, conversation_id, now)
        if row["state"] != "HUMAN_ACTIVE":
            raise ValueError("只有 HUMAN_ACTIVE 状态允许员工回复")
        if int(expected_version) != int(row["version"]):
            raise RuntimeError("已有其他回复或状态变化，请刷新后重试")
        next_version = int(row["version"]) + 1
        conn.execute(
            """
            INSERT INTO human_messages(
                id, conversation_id, role, content, codrive_version, created_at
            ) VALUES(?, ?, 'staff', ?, ?, ?)
            """,
            (message_id, conversation_id, content, next_version, now),
        )
        conn.execute(
            "UPDATE codrive_sessions SET version=?, updated_at=? WHERE conversation_id=?",
            (next_version, now, conversation_id),
        )
        _event(
            conn,
            conversation_id,
            "staff_message_added",
            "HUMAN_ACTIVE",
            "HUMAN_ACTIVE",
            "STAFF",
            {"message_id": message_id, "content": content},
            now,
        )
        return {
            "message": {
                "id": message_id,
                "conversation_id": conversation_id,
                "role": "staff",
                "content": content,
                "created_at": now,
            },
            "session": _session_dict(
                conn.execute(
                    "SELECT * FROM codrive_sessions WHERE conversation_id=?",
                    (conversation_id,),
                ).fetchone()
            ),
        }


def begin_return_to_ai(
    conversation_id: str,
    *,
    summary: str = "",
    expected_version: int,
) -> dict[str, Any]:
    from . import db

    now = _now()
    with db.connection() as conn:
        row = ensure_session(conn, conversation_id, now)
        if row["state"] != "HUMAN_ACTIVE":
            raise ValueError("只有 HUMAN_ACTIVE 状态可以交还 AI")
        if int(expected_version) != int(row["version"]):
            raise RuntimeError("会话状态已变化，请刷新后重试")
        next_version = int(row["version"]) + 1
        merged_summary = str(summary).strip() or row["handoff_summary"]
        conn.execute(
            """
            UPDATE codrive_sessions
            SET state='AI_RESUMING', version=?, handoff_summary=?,
                returned_at=?, updated_at=?
            WHERE conversation_id=?
            """,
            (next_version, merged_summary, now, now, conversation_id),
        )
        _event(
            conn,
            conversation_id,
            "returned_to_ai",
            "HUMAN_ACTIVE",
            "AI_RESUMING",
            "STAFF",
            {"summary": merged_summary},
            now,
        )
        return _session_dict(
            conn.execute(
                "SELECT * FROM codrive_sessions WHERE conversation_id=?",
                (conversation_id,),
            ).fetchone()
        )


def complete_return_to_ai(
    conversation_id: str,
    *,
    run_id: str | None,
    success: bool,
) -> dict[str, Any]:
    from . import db

    now = _now()
    with db.connection() as conn:
        row = ensure_session(conn, conversation_id, now)
        if row["state"] == "AI_ACTIVE":
            return _session_dict(row)
        if row["state"] != "AI_RESUMING":
            raise ValueError("当前不在 AI 恢复阶段")
        next_version = int(row["version"]) + 1
        conn.execute(
            """
            UPDATE codrive_sessions
            SET state='AI_ACTIVE', version=?, updated_at=?
            WHERE conversation_id=?
            """,
            (next_version, now, conversation_id),
        )
        _event(
            conn,
            conversation_id,
            "ai_resumed" if success else "ai_resume_failed",
            "AI_RESUMING",
            "AI_ACTIVE",
            "AI",
            {"run_id": run_id, "success": success, "ai_standby": True},
            now,
        )
        return _session_dict(
            conn.execute(
                "SELECT * FROM codrive_sessions WHERE conversation_id=?",
                (conversation_id,),
            ).fetchone()
        )


def get_session(conversation_id: str, *, include_events: bool = True) -> dict[str, Any]:
    from . import db

    with db.connection() as conn:
        row = ensure_session(conn, conversation_id)
        result = _session_dict(row)
        if include_events:
            events = []
            for item in conn.execute(
                "SELECT * FROM codrive_events WHERE conversation_id=? ORDER BY sequence",
                (conversation_id,),
            ).fetchall():
                event = dict(item)
                event["payload"] = json.loads(event.pop("payload_json"))
                events.append(event)
            result["events"] = events
        return result


def list_sessions(*, include_ai_active: bool = True, limit: int = 100) -> list[dict[str, Any]]:
    from . import db

    where = "" if include_ai_active else "WHERE s.state != 'AI_ACTIVE'"
    with db.connection() as conn:
        rows = conn.execute(
            f"""
            SELECT s.*,
                   (SELECT content FROM messages m
                    WHERE m.conversation_id=s.conversation_id AND m.role='user'
                    ORDER BY m.created_at LIMIT 1) AS title,
                   (SELECT COUNT(*) FROM human_messages hm
                    WHERE hm.conversation_id=s.conversation_id) AS staff_message_count,
                   (SELECT agent_id FROM runs r
                    WHERE r.conversation_id=s.conversation_id
                    ORDER BY r.started_at DESC LIMIT 1) AS last_agent_id,
                   (SELECT release_id FROM runs r
                    WHERE r.conversation_id=s.conversation_id
                    ORDER BY r.started_at DESC LIMIT 1) AS last_release_id,
                   (SELECT estimated_cost FROM runs r
                    WHERE r.conversation_id=s.conversation_id
                    ORDER BY r.started_at DESC LIMIT 1) AS last_estimated_cost
            FROM codrive_sessions s
            {where}
            ORDER BY CASE s.state
                WHEN 'HANDOFF_REQUESTED' THEN 0
                WHEN 'HUMAN_ACTIVE' THEN 1
                WHEN 'AI_RESUMING' THEN 2
                ELSE 3 END,
                s.updated_at DESC
            LIMIT ?
            """,
            (max(1, min(200, int(limit))),),
        ).fetchall()
        return [_session_dict(row) for row in rows]


def staff_messages(conversation_id: str) -> list[dict[str, Any]]:
    from . import db

    with db.connection() as conn:
        return [
            dict(row)
            for row in conn.execute(
                "SELECT id, conversation_id, role, content, created_at FROM human_messages WHERE conversation_id=? ORDER BY created_at",
                (conversation_id,),
            ).fetchall()
        ]


def is_human_output_state(conversation_id: str | None) -> bool:
    return get_state(conversation_id) in {"HANDOFF_REQUESTED", "HUMAN_ACTIVE"}


def is_handoff_request(content: str) -> bool:
    normalized = content.replace(" ", "")
    if is_handoff_opt_out(normalized):
        return False
    terms = (
        "我要人工",
        "转人工",
        "人工客服",
        "人工协助",
        "需要人工",
        "请员工处理",
    )
    return any(term in normalized for term in terms)


def is_handoff_opt_out(content: str) -> bool:
    normalized = content.replace(" ", "")
    return any(
        term in normalized
        for term in (
            "不要转人工",
            "暂时不要转人工",
            "无需转人工",
            "不用转人工",
            "不要人工客服",
            "先别转人工",
        )
    )


def assess_ai_handoff(content: str) -> dict[str, Any]:
    """Deterministic safety policy for a real, explainable AI handoff decision."""
    normalized = content.replace(" ", "")
    opted_out = is_handoff_opt_out(normalized)
    repeated_terms = (
        "连续三次",
        "连续处理三次",
        "多次失败",
        "反复失败",
        "一直失败",
        "仍未解决",
    )
    risk_terms = ("造成损失", "继续损失", "资金风险", "安全风险", "人身安全", "数据丢失")
    urgency_terms = ("非常着急", "立即升级", "马上处理", "紧急")
    repeated = [term for term in repeated_terms if term in normalized]
    risks = [term for term in risk_terms if term in normalized]
    urgency = [term for term in urgency_terms if term in normalized]
    should_handoff = not opted_out and bool(repeated) and bool(risks or urgency)
    if opted_out:
        reason = "用户明确要求本轮暂不转人工，AI 继续提供可执行建议"
        rule_code = "USER_OPT_OUT"
    elif should_handoff:
        reason = "检测到重复处理失败，并伴随潜在损失或紧急升级信号"
        rule_code = "REPEATED_FAILURE_WITH_HIGH_RISK"
    else:
        reason = "未同时满足重复失败与高风险升级条件"
        rule_code = "NO_HANDOFF_REQUIRED"
    return {
        "should_handoff": should_handoff,
        "source": "AI_POLICY",
        "rule_code": rule_code,
        "reason": reason,
        "signals": {
            "repeated_failure": repeated,
            "risk": risks,
            "urgency": urgency,
            "user_opt_out": opted_out,
        },
    }
