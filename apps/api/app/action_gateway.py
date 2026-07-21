from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timezone
from typing import Any

from . import work_orders


MIGRATION_8 = """
CREATE TABLE IF NOT EXISTS action_requests (
    id TEXT PRIMARY KEY,
    conversation_id TEXT REFERENCES conversations(id),
    source_run_id TEXT REFERENCES runs(id),
    confirmation_run_id TEXT REFERENCES runs(id),
    release_id TEXT NOT NULL REFERENCES releases(id),
    tool_name TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    before_json TEXT,
    status TEXT NOT NULL CHECK(status IN (
        'DRAFT','AWAITING_CONFIRMATION','CONFIRMED','EXECUTING',
        'SUCCEEDED','FAILED','INDETERMINATE','CANCELLED'
    )),
    confirmation_step INTEGER NOT NULL DEFAULT 0,
    required_confirmations INTEGER NOT NULL,
    current_token_hash TEXT,
    idempotency_key TEXT NOT NULL UNIQUE,
    version INTEGER NOT NULL DEFAULT 1,
    result_json TEXT,
    receipt_json TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    executed_at TEXT
);
CREATE TABLE IF NOT EXISTS action_audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action_id TEXT NOT NULL REFERENCES action_requests(id),
    sequence INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT NOT NULL,
    actor TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(action_id, sequence)
);
CREATE INDEX IF NOT EXISTS idx_action_conversation_created
ON action_requests(conversation_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_action_status_updated
ON action_requests(status, updated_at DESC);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _new_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(24)
    return token, _token_hash(token)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _decode(row) -> dict[str, Any]:
    result = dict(row)
    for source, target in (
        ("payload_json", "payload"),
        ("before_json", "before"),
        ("result_json", "result"),
        ("receipt_json", "receipt"),
    ):
        raw = result.pop(source)
        result[target] = json.loads(raw) if raw else None
    result.pop("current_token_hash", None)
    result["requires_confirmation"] = result["status"] == "AWAITING_CONFIRMATION"
    result["remaining_confirmations"] = max(
        0, result["required_confirmations"] - result["confirmation_step"]
    )
    return result


def _audit(
    conn,
    action_id: str,
    event_type: str,
    from_status: str | None,
    to_status: str,
    actor: str,
    payload: dict[str, Any],
    created_at: str,
) -> None:
    sequence = conn.execute(
        "SELECT COALESCE(MAX(sequence), 0) + 1 AS next FROM action_audit_events WHERE action_id=?",
        (action_id,),
    ).fetchone()["next"]
    conn.execute(
        """
        INSERT INTO action_audit_events(
            action_id, sequence, event_type, from_status, to_status, actor,
            payload_json, created_at
        ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            action_id,
            sequence,
            event_type,
            from_status,
            to_status,
            actor,
            _json(payload),
            created_at,
        ),
    )


def _work_order_number(conn, now: str) -> str:
    day = now[:10].replace("-", "")
    prefix = f"WO-{day}-"
    rows = conn.execute(
        "SELECT id FROM work_orders WHERE id LIKE ? ORDER BY id DESC LIMIT 1",
        (f"{prefix}%",),
    ).fetchall()
    maximum = 0
    for row in rows:
        try:
            maximum = max(maximum, int(str(row["id"]).split("-")[-1]))
        except ValueError:
            continue
    return f"{prefix}{maximum + 1:03d}"


def _get_with_conn(conn, action_id: str):
    row = conn.execute("SELECT * FROM action_requests WHERE id=?", (action_id,)).fetchone()
    if row is None:
        raise KeyError(action_id)
    return row


def create_draft(
    *,
    tool_name: str,
    payload: dict[str, Any],
    release_id: str,
    idempotency_key: str,
    conversation_id: str | None = None,
    source_run_id: str | None = None,
    actor: str = "USER",
) -> dict[str, Any]:
    from . import db

    idempotency_key = str(idempotency_key).strip()
    if not idempotency_key or len(idempotency_key) > 200:
        raise ValueError("idempotency_key 必须为 1-200 个字符")
    validated = work_orders.validate_write_payload(tool_name, payload)
    before = work_orders.before_snapshot(tool_name, validated)
    now = _now()
    token, token_hash = _new_token()
    action_id = db.new_id("action")
    required = 2 if tool_name == "delete_work_order" else 1
    with db.connection() as conn:
        release = conn.execute(
            "SELECT config_json FROM releases WHERE id=?", (release_id,)
        ).fetchone()
        if release is None:
            raise ValueError("Release 不存在")
        release_config = json.loads(release["config_json"])
        released_tool = next(
            (
                item
                for item in release_config.get("tools", [])
                if item.get("tool_id") == tool_name and item.get("agent_ids")
            ),
            None,
        )
        if released_tool is None:
            raise ValueError("该预置 Tool 未绑定到此 Release 的垂直 Agent")
        existing = conn.execute(
            "SELECT * FROM action_requests WHERE idempotency_key=?",
            (idempotency_key,),
        ).fetchone()
        if existing is not None:
            result = _decode(existing)
            result["idempotent_replay"] = True
            result["confirmation_token"] = None
            return result
        conn.execute(
            """
            INSERT INTO action_requests(
                id, conversation_id, source_run_id, confirmation_run_id,
                release_id, tool_name, payload_json, before_json, status,
                confirmation_step, required_confirmations, current_token_hash,
                idempotency_key, version, result_json, receipt_json,
                error_message, created_at, updated_at, executed_at
            ) VALUES(?, ?, ?, NULL, ?, ?, ?, ?, 'DRAFT', 0, ?, ?, ?, 1,
                     NULL, NULL, NULL, ?, ?, NULL)
            """,
            (
                action_id,
                conversation_id,
                source_run_id,
                release_id,
                tool_name,
                _json(validated),
                _json(before) if before is not None else None,
                required,
                token_hash,
                idempotency_key,
                now,
                now,
            ),
        )
        _audit(conn, action_id, "draft_created", None, "DRAFT", actor, {"tool_name": tool_name}, now)
        conn.execute(
            "UPDATE action_requests SET status='AWAITING_CONFIRMATION', version=2 WHERE id=?",
            (action_id,),
        )
        _audit(
            conn,
            action_id,
            "confirmation_requested",
            "DRAFT",
            "AWAITING_CONFIRMATION",
            actor,
            {
                "confirmation_step": 0,
                "required_confirmations": required,
                "before": before,
                "payload": validated,
            },
            now,
        )
        row = _get_with_conn(conn, action_id)
        result = _decode(row)
        result["confirmation_token"] = token
        result["idempotent_replay"] = False
        return result


def get_action(action_id: str, *, include_audit: bool = True) -> dict[str, Any]:
    from . import db

    with db.connection() as conn:
        result = _decode(_get_with_conn(conn, action_id))
        if include_audit:
            audit = []
            for row in conn.execute(
                "SELECT * FROM action_audit_events WHERE action_id=? ORDER BY sequence",
                (action_id,),
            ).fetchall():
                item = dict(row)
                item["payload"] = json.loads(item.pop("payload_json"))
                audit.append(item)
            result["audit_events"] = audit
        return result


def list_actions(
    *,
    conversation_id: str | None = None,
    pending_only: bool = False,
    limit: int = 100,
) -> list[dict[str, Any]]:
    from . import db

    where: list[str] = []
    params: list[Any] = []
    if conversation_id:
        where.append("conversation_id=?")
        params.append(conversation_id)
    if pending_only:
        where.append("status='AWAITING_CONFIRMATION'")
    sql = "SELECT * FROM action_requests"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(max(1, min(200, int(limit))))
    with db.connection() as conn:
        return [_decode(row) for row in conn.execute(sql, params).fetchall()]


def confirm_action(
    action_id: str,
    *,
    confirmation_token: str,
    expected_version: int | None = None,
    confirmation_run_id: str | None = None,
    actor: str = "USER",
) -> dict[str, Any]:
    from . import db

    now = _now()
    with db.connection() as conn:
        row = _get_with_conn(conn, action_id)
        if row["status"] == "SUCCEEDED":
            result = _decode(row)
            result["idempotent_replay"] = True
            result["confirmation_token"] = None
            return result
        if row["status"] != "AWAITING_CONFIRMATION":
            raise ValueError(f"当前状态 {row['status']} 不允许确认")
        if expected_version is not None and int(expected_version) != int(row["version"]):
            raise RuntimeError("操作版本已变化，请刷新后再确认")
        if not confirmation_token or not row["current_token_hash"] or not hmac.compare_digest(
            _token_hash(confirmation_token), row["current_token_hash"]
        ):
            raise PermissionError("确认令牌无效或已经使用")
        next_step = int(row["confirmation_step"]) + 1
        next_version = int(row["version"]) + 1
        if next_step < int(row["required_confirmations"]):
            next_token, next_hash = _new_token()
            conn.execute(
                """
                UPDATE action_requests
                SET confirmation_step=?, current_token_hash=?, version=?,
                    confirmation_run_id=COALESCE(?, confirmation_run_id), updated_at=?
                WHERE id=?
                """,
                (next_step, next_hash, next_version, confirmation_run_id, now, action_id),
            )
            _audit(
                conn,
                action_id,
                "confirmation_step_completed",
                "AWAITING_CONFIRMATION",
                "AWAITING_CONFIRMATION",
                actor,
                {"confirmation_step": next_step, "required_confirmations": row["required_confirmations"]},
                now,
            )
            result = _decode(_get_with_conn(conn, action_id))
            result["confirmation_token"] = next_token
            result["idempotent_replay"] = False
            return result

        conn.execute(
            """
            UPDATE action_requests
            SET status='CONFIRMED', confirmation_step=?, current_token_hash=NULL,
                version=?, confirmation_run_id=COALESCE(?, confirmation_run_id), updated_at=?
            WHERE id=?
            """,
            (next_step, next_version, confirmation_run_id, now, action_id),
        )
        _audit(
            conn,
            action_id,
            "confirmed",
            "AWAITING_CONFIRMATION",
            "CONFIRMED",
            actor,
            {"confirmation_step": next_step},
            now,
        )
        conn.execute(
            "UPDATE action_requests SET status='EXECUTING', version=version+1, updated_at=? WHERE id=?",
            (now, action_id),
        )
        _audit(conn, action_id, "execution_started", "CONFIRMED", "EXECUTING", actor, {}, now)
        payload = json.loads(row["payload_json"])
        new_order_id = _work_order_number(conn, now) if row["tool_name"] == "create_work_order" else None
        try:
            work_order = work_orders.apply_write(
                conn, row["tool_name"], payload, now, new_order_id=new_order_id
            )
            receipt = {
                "action_id": action_id,
                "tool_name": row["tool_name"],
                "status": "SUCCEEDED",
                "work_order_id": work_order["id"],
                "message": "操作已成功执行。",
                "executed_at": now,
            }
            conn.execute(
                """
                UPDATE action_requests
                SET status='SUCCEEDED', result_json=?, receipt_json=?, error_message=NULL,
                    version=version+1, updated_at=?, executed_at=?
                WHERE id=?
                """,
                (_json(work_order), _json(receipt), now, now, action_id),
            )
            _audit(
                conn,
                action_id,
                "execution_succeeded",
                "EXECUTING",
                "SUCCEEDED",
                actor,
                {"receipt": receipt, "result": work_order},
                now,
            )
        except Exception as exc:
            error = f"{type(exc).__name__}: {str(exc)}"[:1000]
            receipt = {
                "action_id": action_id,
                "tool_name": row["tool_name"],
                "status": "FAILED",
                "message": "操作执行失败，未自动重试。",
                "executed_at": now,
            }
            conn.execute(
                """
                UPDATE action_requests
                SET status='FAILED', receipt_json=?, error_message=?,
                    version=version+1, updated_at=?, executed_at=?
                WHERE id=?
                """,
                (_json(receipt), error, now, now, action_id),
            )
            _audit(
                conn,
                action_id,
                "execution_failed",
                "EXECUTING",
                "FAILED",
                actor,
                {"receipt": receipt, "error": error},
                now,
            )
        result = _decode(_get_with_conn(conn, action_id))
        result["confirmation_token"] = None
        result["idempotent_replay"] = False
        return result


def cancel_action(
    action_id: str,
    *,
    expected_version: int | None = None,
    actor: str = "USER",
) -> dict[str, Any]:
    from . import db

    now = _now()
    with db.connection() as conn:
        row = _get_with_conn(conn, action_id)
        if row["status"] == "CANCELLED":
            return _decode(row)
        if row["status"] != "AWAITING_CONFIRMATION":
            raise ValueError("只有待确认操作可以取消")
        if expected_version is not None and int(expected_version) != int(row["version"]):
            raise RuntimeError("操作版本已变化，请刷新后再取消")
        conn.execute(
            """
            UPDATE action_requests
            SET status='CANCELLED', current_token_hash=NULL, version=version+1,
                updated_at=? WHERE id=?
            """,
            (now, action_id),
        )
        _audit(
            conn,
            action_id,
            "cancelled",
            "AWAITING_CONFIRMATION",
            "CANCELLED",
            actor,
            {},
            now,
        )
        return _decode(_get_with_conn(conn, action_id))
