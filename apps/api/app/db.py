from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from .config import settings


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    os.makedirs(os.path.dirname(os.path.abspath(settings.db_path)), exist_ok=True)
    conn = sqlite3.connect(settings.db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS releases (
    id TEXT PRIMARY KEY,
    version TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK(status IN ('CANDIDATE','ACTIVE','HISTORICAL')),
    change_summary TEXT NOT NULL,
    config_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    published_at TEXT
);
CREATE TABLE IF NOT EXISTS workspaces (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    active_release_id TEXT NOT NULL REFERENCES releases(id)
);
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id),
    role TEXT NOT NULL CHECK(role IN ('user','assistant')),
    content TEXT NOT NULL,
    run_id TEXT,
    release_id TEXT REFERENCES releases(id),
    agent_id TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id),
    release_id TEXT NOT NULL REFERENCES releases(id),
    user_message_id TEXT NOT NULL REFERENCES messages(id),
    agent_id TEXT,
    status TEXT NOT NULL CHECK(status IN ('RUNNING','DONE','ERROR')),
    started_at TEXT NOT NULL,
    finished_at TEXT,
    latency_ms INTEGER,
    estimated_cost REAL
);
CREATE TABLE IF NOT EXISTS trace_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES runs(id),
    release_id TEXT NOT NULL REFERENCES releases(id),
    sequence INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(run_id, sequence)
);
CREATE TABLE IF NOT EXISTS cloud_call_snaps (
    cloud_call_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id),
    phase TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    request_started_at TEXT NOT NULL,
    response_finished_at TEXT NOT NULL,
    latency_ms INTEGER NOT NULL,
    status TEXT NOT NULL,
    prompt_cache_miss_tokens INTEGER,
    prompt_cache_hit_tokens INTEGER,
    completion_tokens INTEGER,
    total_tokens INTEGER,
    usage_status TEXT NOT NULL,
    price_snapshot_json TEXT NOT NULL,
    estimated_cost REAL,
    provider_request_id TEXT,
    error_code TEXT
);
CREATE TABLE IF NOT EXISTS badcase_candidates (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id),
    rule_code TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'SUSPECTED',
    created_at TEXT NOT NULL,
    UNIQUE(run_id, rule_code)
);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id, created_at);
CREATE INDEX IF NOT EXISTS idx_runs_started ON runs(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_trace_run ON trace_events(run_id, sequence);
"""


DEFAULT_CONFIG: dict[str, Any] = {
    "router": {
        "id": "router-default",
        "name": "唯一 Router",
        "model_profile": "DEFAULT",
    },
    "agents": [
        {
            "id": "general-service",
            "name": "一般客服",
            "description": "处理一般咨询、说明和澄清",
            "system_prompt": "你是领域无关的一般客服。回答清晰、克制，不编造外部事实。",
        },
        {
            "id": "complaint-service",
            "name": "投诉客服",
            "description": "处理不满、投诉和服务补救沟通",
            "system_prompt": "你是领域无关的投诉客服。先确认问题与感受，再给出可执行的下一步；不要虚构处理结果。",
        },
        {
            "id": "work-order-service",
            "name": "工单处理",
            "description": "识别工单意图并形成下一步说明",
            "system_prompt": "你是领域无关的工单处理 Agent。当前版本尚未接入工单 Tool，只能说明准备执行的步骤，不得声称已创建、更新或关闭工单。",
        },
    ],
    "model_policy": {
        "default_profile": {
            "provider": "deepseek",
            "model": "deepseek-v4-flash",
            "thinking": True,
            "reasoning_effort": "high",
        },
        "expert_profile": {
            "provider": "deepseek",
            "model": "deepseek-v4-pro",
            "thinking": True,
            "enabled_workflows": [],
        },
    },
}


def init_db() -> None:
    with connection() as conn:
        conn.executescript(SCHEMA)
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES(1, ?)",
            (now_iso(),),
        )
        count = conn.execute("SELECT COUNT(*) AS n FROM releases").fetchone()["n"]
        if count == 0:
            release_id = "rel_v055_default"
            conn.execute(
                """
                INSERT INTO releases(id, version, status, change_summary, config_json, created_at, published_at)
                VALUES(?, ?, 'ACTIVE', ?, ?, ?, ?)
                """,
                (
                    release_id,
                    "V0.5.5-default",
                    "初始化唯一 Router 与三个默认垂直 Agent",
                    json.dumps(DEFAULT_CONFIG, ensure_ascii=False),
                    now_iso(),
                    now_iso(),
                ),
            )
            conn.execute(
                "INSERT INTO workspaces(id, name, active_release_id) VALUES('default', 'YIAI Center', ?)",
                (release_id,),
            )


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def get_workspace() -> dict[str, Any]:
    with connection() as conn:
        row = conn.execute(
            """
            SELECT w.id, w.name, w.active_release_id, r.version AS active_release_version
            FROM workspaces w JOIN releases r ON r.id=w.active_release_id
            WHERE w.id='default'
            """
        ).fetchone()
        return dict(row)


def list_releases() -> list[dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT id, version, status, change_summary, created_at, published_at
            FROM releases
            ORDER BY created_at DESC
            """
        ).fetchall()
        return rows_to_dicts(rows)


def create_candidate(version: str, change_summary: str) -> dict[str, Any]:
    release_id = new_id("rel")
    with connection() as conn:
        active = conn.execute(
            """
            SELECT r.config_json FROM releases r
            JOIN workspaces w ON w.active_release_id=r.id
            WHERE w.id='default'
            """
        ).fetchone()
        if active is None:
            raise RuntimeError("Active Release not found")
        conn.execute(
            """
            INSERT INTO releases(id, version, status, change_summary, config_json, created_at)
            VALUES(?, ?, 'CANDIDATE', ?, ?, ?)
            """,
            (release_id, version, change_summary, active["config_json"], now_iso()),
        )
        row = conn.execute(
            "SELECT id, version, status, change_summary, created_at, published_at FROM releases WHERE id=?",
            (release_id,),
        ).fetchone()
        return dict(row)


def activate_release(release_id: str) -> dict[str, Any]:
    with connection() as conn:
        target = conn.execute("SELECT * FROM releases WHERE id=?", (release_id,)).fetchone()
        if target is None:
            raise KeyError(release_id)
        old_id = conn.execute(
            "SELECT active_release_id FROM workspaces WHERE id='default'"
        ).fetchone()["active_release_id"]
        if old_id != release_id:
            conn.execute("UPDATE releases SET status='HISTORICAL' WHERE id=?", (old_id,))
            conn.execute(
                "UPDATE releases SET status='ACTIVE', published_at=? WHERE id=?",
                (now_iso(), release_id),
            )
            conn.execute(
                "UPDATE workspaces SET active_release_id=? WHERE id='default'",
                (release_id,),
            )
        return {
            "previous_release_id": old_id,
            "active_release_id": release_id,
            "active_release_version": target["version"],
        }


def get_release(release_id: str) -> dict[str, Any]:
    with connection() as conn:
        row = conn.execute("SELECT * FROM releases WHERE id=?", (release_id,)).fetchone()
        if row is None:
            raise KeyError(release_id)
        result = dict(row)
        result["config"] = json.loads(result.pop("config_json"))
        return result


def prepare_run(conversation_id: str | None, content: str) -> dict[str, Any]:
    conversation_id = conversation_id or new_id("conv")
    message_id = new_id("msg")
    run_id = new_id("run")
    started_at = now_iso()
    with connection() as conn:
        exists = conn.execute(
            "SELECT 1 FROM conversations WHERE id=?", (conversation_id,)
        ).fetchone()
        if exists is None:
            conn.execute(
                "INSERT INTO conversations(id, created_at) VALUES(?, ?)",
                (conversation_id, started_at),
            )
        active = conn.execute(
            """
            SELECT r.id, r.version, r.config_json FROM releases r
            JOIN workspaces w ON w.active_release_id=r.id WHERE w.id='default'
            """
        ).fetchone()
        if active is None:
            raise RuntimeError("Active Release not found")
        conn.execute(
            """
            INSERT INTO messages(id, conversation_id, role, content, run_id, release_id, created_at)
            VALUES(?, ?, 'user', ?, ?, ?, ?)
            """,
            (message_id, conversation_id, content, run_id, active["id"], started_at),
        )
        conn.execute(
            """
            INSERT INTO runs(id, conversation_id, release_id, user_message_id, status, started_at)
            VALUES(?, ?, ?, ?, 'RUNNING', ?)
            """,
            (run_id, conversation_id, active["id"], message_id, started_at),
        )
    return {
        "run_id": run_id,
        "conversation_id": conversation_id,
        "release_id": active["id"],
        "release_version": active["version"],
        "release_config": json.loads(active["config_json"]),
        "started_at": started_at,
        "content": content,
    }


def append_trace(run_id: str, release_id: str, event_type: str, payload: dict[str, Any]) -> int:
    with connection() as conn:
        sequence = conn.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 AS n FROM trace_events WHERE run_id=?",
            (run_id,),
        ).fetchone()["n"]
        conn.execute(
            """
            INSERT INTO trace_events(run_id, release_id, sequence, event_type, payload_json, created_at)
            VALUES(?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                release_id,
                sequence,
                event_type,
                json.dumps(payload, ensure_ascii=False),
                now_iso(),
            ),
        )
        return sequence


def save_cloud_snap(run_id: str, phase: str, snap: dict[str, Any]) -> None:
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO cloud_call_snaps(
                cloud_call_id, run_id, phase, provider, model, request_started_at,
                response_finished_at, latency_ms, status, prompt_cache_miss_tokens,
                prompt_cache_hit_tokens, completion_tokens, total_tokens, usage_status,
                price_snapshot_json, estimated_cost, provider_request_id, error_code
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snap["cloud_call_id"],
                run_id,
                phase,
                snap["provider"],
                snap["model"],
                snap["request_started_at"],
                snap["response_finished_at"],
                snap["latency_ms"],
                snap["status"],
                snap.get("prompt_cache_miss_tokens"),
                snap.get("prompt_cache_hit_tokens"),
                snap.get("completion_tokens"),
                snap.get("total_tokens"),
                snap["usage_status"],
                json.dumps(snap["price_snapshot"], ensure_ascii=False),
                snap.get("estimated_cost"),
                snap.get("provider_request_id"),
                snap.get("error_code"),
            ),
        )
        if snap["usage_status"] != "COMPLETE":
            conn.execute(
                """
                INSERT OR IGNORE INTO badcase_candidates(id, run_id, rule_code, evidence_json, created_at)
                VALUES(?, ?, 'MODEL_USAGE_INCOMPLETE', ?, ?)
                """,
                (
                    new_id("badcase"),
                    run_id,
                    json.dumps({"cloud_call_id": snap["cloud_call_id"]}),
                    now_iso(),
                ),
            )


def conversation_history(conversation_id: str, limit: int = 12) -> list[dict[str, str]]:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT role, content FROM messages WHERE conversation_id=?
            ORDER BY created_at DESC LIMIT ?
            """,
            (conversation_id, limit),
        ).fetchall()
        return [dict(row) for row in reversed(rows)]


def finish_run(
    run_id: str,
    release_id: str,
    conversation_id: str,
    agent_id: str,
    answer: str,
    latency_ms: int,
) -> dict[str, Any]:
    message_id = new_id("msg")
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO messages(id, conversation_id, role, content, run_id, release_id, agent_id, created_at)
            VALUES(?, ?, 'assistant', ?, ?, ?, ?, ?)
            """,
            (message_id, conversation_id, answer, run_id, release_id, agent_id, now_iso()),
        )
        cost_row = conn.execute(
            """
            SELECT COUNT(*) AS total_calls,
                   SUM(CASE WHEN usage_status='COMPLETE' THEN 1 ELSE 0 END) AS complete_calls,
                   SUM(estimated_cost) AS complete_cost
            FROM cloud_call_snaps WHERE run_id=?
            """,
            (run_id,),
        ).fetchone()
        cost = (
            cost_row["complete_cost"]
            if cost_row["total_calls"] > 0
            and cost_row["total_calls"] == cost_row["complete_calls"]
            else None
        )
        conn.execute(
            """
            UPDATE runs SET agent_id=?, status='DONE', finished_at=?, latency_ms=?, estimated_cost=?
            WHERE id=?
            """,
            (agent_id, now_iso(), latency_ms, cost, run_id),
        )
    return {"message_id": message_id, "estimated_cost": cost}


def fail_run(run_id: str, error_code: str) -> None:
    with connection() as conn:
        conn.execute(
            "UPDATE runs SET status='ERROR', finished_at=? WHERE id=?",
            (now_iso(), run_id),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO badcase_candidates(id, run_id, rule_code, evidence_json, created_at)
            VALUES(?, ?, 'RUN_ERROR', ?, ?)
            """,
            (new_id("badcase"), run_id, json.dumps({"error_code": error_code}), now_iso()),
        )


def list_runs(limit: int = 50) -> list[dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT r.*, rel.version AS release_version
            FROM runs r JOIN releases rel ON rel.id=r.release_id
            ORDER BY r.started_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return rows_to_dicts(rows)


def get_run_detail(run_id: str) -> dict[str, Any]:
    with connection() as conn:
        run = conn.execute(
            """
            SELECT r.*, rel.version AS release_version
            FROM runs r JOIN releases rel ON rel.id=r.release_id WHERE r.id=?
            """,
            (run_id,),
        ).fetchone()
        if run is None:
            raise KeyError(run_id)
        events = rows_to_dicts(
            conn.execute(
                """
                SELECT sequence, event_type, payload_json, created_at
                FROM trace_events WHERE run_id=? ORDER BY sequence
                """,
                (run_id,),
            ).fetchall()
        )
        for event in events:
            event["payload"] = json.loads(event.pop("payload_json"))
        snaps = rows_to_dicts(
            conn.execute(
                "SELECT * FROM cloud_call_snaps WHERE run_id=? ORDER BY request_started_at",
                (run_id,),
            ).fetchall()
        )
        for snap in snaps:
            snap["price_snapshot"] = json.loads(snap.pop("price_snapshot_json"))
        return {"run": dict(run), "trace_events": events, "cloud_call_snaps": snaps}


def get_messages(conversation_id: str) -> list[dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT m.*, r.version AS release_version
            FROM messages m LEFT JOIN releases r ON r.id=m.release_id
            WHERE m.conversation_id=? ORDER BY m.created_at
            """,
            (conversation_id,),
        ).fetchall()
        return rows_to_dicts(rows)
