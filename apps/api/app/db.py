from __future__ import annotations

import json
import hashlib
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


MIGRATION_2 = """
CREATE TABLE IF NOT EXISTS skills (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    applicability TEXT NOT NULL,
    non_applicability TEXT NOT NULL,
    output_requirements TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('DRAFT','VALIDATED','DISABLED')),
    current_version_id TEXT NOT NULL,
    agent_ids_json TEXT NOT NULL,
    validation_errors_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS skill_versions (
    id TEXT PRIMARY KEY,
    skill_id TEXT NOT NULL REFERENCES skills(id),
    version_number INTEGER NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    applicability TEXT NOT NULL,
    non_applicability TEXT NOT NULL,
    content TEXT NOT NULL,
    output_requirements TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'MANUAL',
    source_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    UNIQUE(skill_id, version_number)
);
CREATE TABLE IF NOT EXISTS release_bindings (
    release_id TEXT NOT NULL REFERENCES releases(id),
    capability_type TEXT NOT NULL,
    component_version_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    config_json TEXT NOT NULL,
    PRIMARY KEY(release_id, capability_type, component_version_id, agent_id)
);
CREATE INDEX IF NOT EXISTS idx_skill_versions_skill ON skill_versions(skill_id, version_number DESC);
CREATE INDEX IF NOT EXISTS idx_release_bindings_release ON release_bindings(release_id, capability_type);
"""


MIGRATION_3 = """
CREATE TABLE IF NOT EXISTS skill_import_attempts (
    id TEXT PRIMARY KEY,
    repo_url TEXT NOT NULL,
    commit_sha TEXT,
    skill_path TEXT,
    status TEXT NOT NULL CHECK(status IN ('IMPORTED','REJECTED','FAILED')),
    file_list_json TEXT NOT NULL,
    findings_json TEXT NOT NULL,
    reason TEXT,
    skill_id TEXT REFERENCES skills(id),
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_skill_import_attempts_created
ON skill_import_attempts(created_at DESC);
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
    "skills": [],
}


def init_db() -> None:
    with connection() as conn:
        conn.executescript(SCHEMA)
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES(1, ?)",
            (now_iso(),),
        )
        applied = {
            row["version"]
            for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
        }
        if 2 not in applied:
            conn.executescript(MIGRATION_2)
            conn.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES(2, ?)",
                (now_iso(),),
            )
            applied.add(2)
        if 3 not in applied:
            conn.executescript(MIGRATION_3)
            conn.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES(3, ?)",
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


def _cost_to_cny(estimated_cost: float | None, price_snapshot: dict[str, Any]) -> float | None:
    if estimated_cost is None:
        return None
    currency = str(price_snapshot.get("currency", "USD")).upper()
    if currency == "CNY":
        return estimated_cost
    if currency == "USD":
        rate = (
            price_snapshot.get("exchange_rate_snapshot", {}).get("rate")
            or settings.usd_cny_rate
        )
        return estimated_cost * float(rate)
    return None


def _price_snapshot_cny(price_snapshot: dict[str, Any]) -> dict[str, Any] | None:
    currency = str(price_snapshot.get("currency", "USD")).upper()
    if currency == "CNY":
        return price_snapshot
    if currency != "USD":
        return None
    rate = settings.usd_cny_rate
    return {
        "currency": "CNY",
        "unit": price_snapshot.get("unit", "per_1m_tokens"),
        "cache_hit_input": float(price_snapshot.get("cache_hit_input", 0)) * rate,
        "cache_miss_input": float(price_snapshot.get("cache_miss_input", 0)) * rate,
        "output": float(price_snapshot.get("output", 0)) * rate,
        "provider_list_price_usd": {
            "cache_hit_input": price_snapshot.get("cache_hit_input"),
            "cache_miss_input": price_snapshot.get("cache_miss_input"),
            "output": price_snapshot.get("output"),
        },
        "exchange_rate_snapshot": {
            "base": "USD",
            "quote": "CNY",
            "rate": rate,
            "source": "YIAI_USD_CNY_RATE demo configuration",
        },
        "source": price_snapshot.get("source"),
    }


def _run_cost_cny(conn: sqlite3.Connection, run_id: str) -> float | None:
    rows = conn.execute(
        """
        SELECT usage_status, estimated_cost, price_snapshot_json
        FROM cloud_call_snaps WHERE run_id=?
        """,
        (run_id,),
    ).fetchall()
    if not rows or any(
        row["usage_status"] != "COMPLETE" or row["estimated_cost"] is None for row in rows
    ):
        return None
    costs = [
        _cost_to_cny(row["estimated_cost"], json.loads(row["price_snapshot_json"]))
        for row in rows
    ]
    if any(cost is None for cost in costs):
        return None
    return sum(costs)


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
        config = _candidate_config(conn, json.loads(active["config_json"]))
        config_json = json.dumps(config, ensure_ascii=False)
        conn.execute(
            """
            INSERT INTO releases(id, version, status, change_summary, config_json, created_at)
            VALUES(?, ?, 'CANDIDATE', ?, ?, ?)
            """,
            (release_id, version, change_summary, config_json, now_iso()),
        )
        _save_release_bindings(conn, release_id, config)
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


def _skill_validation_errors(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    fields = {
        "name": 80,
        "description": 500,
        "applicability": 1000,
        "non_applicability": 1000,
        "content": 20000,
        "output_requirements": 2000,
    }
    for field, maximum in fields.items():
        value = str(payload.get(field, "")).strip()
        if not value:
            errors.append(f"{field} 不能为空")
        elif len(value) > maximum:
            errors.append(f"{field} 超过 {maximum} 字符")
    if len(str(payload.get("content", "")).strip()) < 20:
        errors.append("content 至少需要 20 个字符")
    agent_ids = payload.get("agent_ids")
    allowed_agents = {agent["id"] for agent in DEFAULT_CONFIG["agents"]}
    if not isinstance(agent_ids, list) or not agent_ids:
        errors.append("至少绑定一个垂直 Agent")
    elif any(not isinstance(item, str) or item not in allowed_agents for item in agent_ids):
        errors.append("agent_ids 包含未知垂直 Agent")
    return errors


def _skill_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": str(payload.get("name", "")).strip(),
        "description": str(payload.get("description", "")).strip(),
        "applicability": str(payload.get("applicability", "")).strip(),
        "non_applicability": str(payload.get("non_applicability", "")).strip(),
        "content": str(payload.get("content", "")).strip(),
        "output_requirements": str(payload.get("output_requirements", "")).strip(),
        "agent_ids": list(dict.fromkeys(payload.get("agent_ids") or [])),
    }


def save_skill(
    payload: dict[str, Any],
    skill_id: str | None = None,
    source_type: str = "MANUAL",
    source: dict[str, Any] | None = None,
) -> dict[str, Any]:
    values = _skill_payload(payload)
    timestamp = now_iso()
    with connection() as conn:
        if skill_id is None:
            skill_id = new_id("skill")
            version_number = 1
            created_at = timestamp
        else:
            current = conn.execute("SELECT * FROM skills WHERE id=?", (skill_id,)).fetchone()
            if current is None:
                raise KeyError(skill_id)
            version_number = conn.execute(
                "SELECT COALESCE(MAX(version_number), 0) + 1 AS n FROM skill_versions WHERE skill_id=?",
                (skill_id,),
            ).fetchone()["n"]
            created_at = current["created_at"]
        version_id = new_id("skillv")
        canonical = json.dumps(values, ensure_ascii=False, sort_keys=True).encode("utf-8")
        content_hash = hashlib.sha256(canonical).hexdigest()
        errors = _skill_validation_errors(values)
        if version_number == 1:
            conn.execute(
                """
                INSERT INTO skills(
                    id, name, description, applicability, non_applicability,
                    output_requirements, status, current_version_id, agent_ids_json,
                    validation_errors_json, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, 'DRAFT', ?, ?, ?, ?, ?)
                """,
                (
                    skill_id, values["name"], values["description"], values["applicability"],
                    values["non_applicability"], values["output_requirements"], version_id,
                    json.dumps(values["agent_ids"], ensure_ascii=False),
                    json.dumps(errors, ensure_ascii=False), created_at, timestamp,
                ),
            )
        else:
            conn.execute(
                """
                UPDATE skills SET name=?, description=?, applicability=?, non_applicability=?,
                    output_requirements=?, status='DRAFT', current_version_id=?, agent_ids_json=?,
                    validation_errors_json=?, updated_at=? WHERE id=?
                """,
                (
                    values["name"], values["description"], values["applicability"],
                    values["non_applicability"], values["output_requirements"], version_id,
                    json.dumps(values["agent_ids"], ensure_ascii=False),
                    json.dumps(errors, ensure_ascii=False), timestamp, skill_id,
                ),
            )
        conn.execute(
            """
            INSERT INTO skill_versions(
                id, skill_id, version_number, name, description, applicability,
                non_applicability, content, output_requirements, content_hash,
                source_type, source_json, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                version_id, skill_id, version_number, values["name"], values["description"],
                values["applicability"], values["non_applicability"], values["content"],
                values["output_requirements"], content_hash, source_type,
                json.dumps(source or {}, ensure_ascii=False), timestamp,
            ),
        )
    return get_skill(skill_id)


def get_skill(skill_id: str) -> dict[str, Any]:
    with connection() as conn:
        skill = conn.execute("SELECT * FROM skills WHERE id=?", (skill_id,)).fetchone()
        if skill is None:
            raise KeyError(skill_id)
        versions = conn.execute(
            "SELECT * FROM skill_versions WHERE skill_id=? ORDER BY version_number DESC",
            (skill_id,),
        ).fetchall()
        result = dict(skill)
        result["agent_ids"] = json.loads(result.pop("agent_ids_json"))
        result["validation_errors"] = json.loads(result.pop("validation_errors_json"))
        result["versions"] = rows_to_dicts(versions)
        result["current_version"] = next(
            item for item in result["versions"] if item["id"] == result["current_version_id"]
        )
        for item in result["versions"]:
            item["source"] = json.loads(item.pop("source_json"))
        return result


def list_skills() -> list[dict[str, Any]]:
    with connection() as conn:
        ids = [row["id"] for row in conn.execute("SELECT id FROM skills ORDER BY updated_at DESC")]
    return [get_skill(skill_id) for skill_id in ids]


def save_skill_import_attempt(
    *,
    repo_url: str,
    commit_sha: str | None,
    skill_path: str | None,
    status: str,
    file_list: list[str],
    findings: list[str],
    reason: str | None,
    skill_id: str | None = None,
) -> dict[str, Any]:
    attempt_id = new_id("skillimport")
    created_at = now_iso()
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO skill_import_attempts(
                id, repo_url, commit_sha, skill_path, status, file_list_json,
                findings_json, reason, skill_id, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                attempt_id, repo_url, commit_sha, skill_path, status,
                json.dumps(file_list, ensure_ascii=False),
                json.dumps(findings, ensure_ascii=False), reason, skill_id, created_at,
            ),
        )
    return get_skill_import_attempt(attempt_id)


def get_skill_import_attempt(attempt_id: str) -> dict[str, Any]:
    with connection() as conn:
        row = conn.execute(
            "SELECT * FROM skill_import_attempts WHERE id=?", (attempt_id,)
        ).fetchone()
        if row is None:
            raise KeyError(attempt_id)
        result = dict(row)
        result["file_list"] = json.loads(result.pop("file_list_json"))
        result["findings"] = json.loads(result.pop("findings_json"))
        return result


def list_skill_import_attempts(limit: int = 50) -> list[dict[str, Any]]:
    with connection() as conn:
        ids = [
            row["id"]
            for row in conn.execute(
                "SELECT id FROM skill_import_attempts ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        ]
    return [get_skill_import_attempt(attempt_id) for attempt_id in ids]


def validate_skill(skill_id: str) -> dict[str, Any]:
    skill = get_skill(skill_id)
    payload = {
        **skill["current_version"],
        "agent_ids": skill["agent_ids"],
    }
    errors = _skill_validation_errors(payload)
    with connection() as conn:
        conn.execute(
            "UPDATE skills SET status=?, validation_errors_json=?, updated_at=? WHERE id=?",
            (
                "VALIDATED" if not errors else "DRAFT",
                json.dumps(errors, ensure_ascii=False), now_iso(), skill_id,
            ),
        )
    return get_skill(skill_id)


def disable_skill(skill_id: str) -> dict[str, Any]:
    with connection() as conn:
        if conn.execute("SELECT 1 FROM skills WHERE id=?", (skill_id,)).fetchone() is None:
            raise KeyError(skill_id)
        conn.execute(
            "UPDATE skills SET status='DISABLED', updated_at=? WHERE id=?",
            (now_iso(), skill_id),
        )
    return get_skill(skill_id)


def _candidate_config(conn: sqlite3.Connection, active_config: dict[str, Any]) -> dict[str, Any]:
    config = json.loads(json.dumps(active_config, ensure_ascii=False))
    rows = conn.execute(
        """
        SELECT s.id AS skill_id, s.agent_ids_json, v.*
        FROM skills s JOIN skill_versions v ON v.id=s.current_version_id
        WHERE s.status='VALIDATED' ORDER BY s.created_at, s.id
        """
    ).fetchall()
    config["skills"] = [
        {
            "skill_id": row["skill_id"],
            "skill_version_id": row["id"],
            "version_number": row["version_number"],
            "name": row["name"],
            "description": row["description"],
            "applicability": row["applicability"],
            "non_applicability": row["non_applicability"],
            "content": row["content"],
            "output_requirements": row["output_requirements"],
            "content_hash": row["content_hash"],
            "agent_ids": json.loads(row["agent_ids_json"]),
        }
        for row in rows
    ]
    return config


def _save_release_bindings(conn: sqlite3.Connection, release_id: str, config: dict[str, Any]) -> None:
    for skill in config.get("skills", []):
        for agent_id in skill.get("agent_ids", []):
            conn.execute(
                """
                INSERT INTO release_bindings(
                    release_id, capability_type, component_version_id, agent_id, config_json
                ) VALUES(?, 'SKILL', ?, ?, ?)
                """,
                (
                    release_id, skill["skill_version_id"], agent_id,
                    json.dumps(skill, ensure_ascii=False),
                ),
            )


def get_release_detail(release_id: str) -> dict[str, Any]:
    target = get_release(release_id)
    with connection() as conn:
        active_id = conn.execute(
            "SELECT active_release_id FROM workspaces WHERE id='default'"
        ).fetchone()["active_release_id"]
    active = get_release(active_id)
    def ids(config: dict[str, Any], key: str, id_key: str) -> set[str]:
        return {str(item[id_key]) for item in config.get(key, [])}
    target_skills = ids(target["config"], "skills", "skill_version_id")
    active_skills = ids(active["config"], "skills", "skill_version_id")
    target["diff"] = {
        "base_release_id": active_id,
        "skills_added": sorted(target_skills - active_skills),
        "skills_removed": sorted(active_skills - target_skills),
        "skills_unchanged": sorted(target_skills & active_skills),
    }
    return target


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
        "user_message_id": message_id,
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


def list_conversations(limit: int = 100) -> list[dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT c.id,
                   c.created_at,
                   MAX(m.created_at) AS updated_at,
                   COUNT(m.id) AS message_count,
                   (
                       SELECT first_user.content
                       FROM messages first_user
                       WHERE first_user.conversation_id=c.id
                         AND first_user.role='user'
                       ORDER BY first_user.created_at, first_user.id
                       LIMIT 1
                   ) AS first_user_message
            FROM conversations c
            JOIN messages m ON m.conversation_id=c.id
            GROUP BY c.id, c.created_at
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        result = rows_to_dicts(rows)
        for item in result:
            title = (item.pop("first_user_message") or "新对话").strip()
            item["title"] = title[:32] + ("…" if len(title) > 32 else "")
        return result


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
        estimated_cost_cny = _run_cost_cny(conn, run_id)
    return {
        "message_id": message_id,
        "estimated_cost": cost,
        "estimated_cost_cny": estimated_cost_cny,
    }


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
        result = rows_to_dicts(rows)
        for item in result:
            item["estimated_cost_cny"] = _run_cost_cny(conn, item["id"])
            item["display_currency"] = "CNY"
        return result


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
            snap["price_snapshot_cny"] = _price_snapshot_cny(snap["price_snapshot"])
            snap["estimated_cost_cny"] = _cost_to_cny(
                snap["estimated_cost"], snap["price_snapshot"]
            )
            snap["display_currency"] = "CNY"
        run_result = dict(run)
        run_result["estimated_cost_cny"] = _run_cost_cny(conn, run_id)
        run_result["display_currency"] = "CNY"
        input_message = conn.execute(
            """
            SELECT id, role, content, created_at
            FROM messages WHERE id=?
            """,
            (run_result["user_message_id"],),
        ).fetchone()
        output_message = conn.execute(
            """
            SELECT id, role, content, agent_id, created_at
            FROM messages
            WHERE run_id=? AND role='assistant'
            ORDER BY created_at DESC LIMIT 1
            """,
            (run_id,),
        ).fetchone()
        return {
            "run": run_result,
            "messages": {
                "input": dict(input_message) if input_message else None,
                "output": dict(output_message) if output_message else None,
            },
            "trace_events": events,
            "cloud_call_snaps": snaps,
        }


def get_messages(conversation_id: str) -> list[dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT m.*, rel.version AS release_version, rel.config_json,
                   run.status AS run_status, run.started_at AS run_started_at,
                   run.finished_at AS run_finished_at
            FROM messages m
            LEFT JOIN releases rel ON rel.id=m.release_id
            LEFT JOIN runs run ON run.id=m.run_id
            WHERE m.conversation_id=? ORDER BY m.created_at
            """,
            (conversation_id,),
        ).fetchall()
        result = rows_to_dicts(rows)
        for message in result:
            config_json = message.pop("config_json", None)
            agent_id = message.get("agent_id")
            message["agent_name"] = None
            if config_json and agent_id:
                config = json.loads(config_json)
                match = next(
                    (agent for agent in config.get("agents", []) if agent["id"] == agent_id),
                    None,
                )
                message["agent_name"] = match["name"] if match else agent_id
        return result
