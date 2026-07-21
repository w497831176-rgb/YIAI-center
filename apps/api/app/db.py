from __future__ import annotations

import json
import hashlib
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from . import action_gateway, codrive, work_orders
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


MIGRATION_4 = """
CREATE TABLE IF NOT EXISTS rag_documents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    tags_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('DRAFT','VALIDATED','DISABLED')),
    current_version_id TEXT NOT NULL,
    agent_ids_json TEXT NOT NULL,
    validation_errors_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rag_versions (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES rag_documents(id),
    version_number INTEGER NOT NULL,
    original_content TEXT NOT NULL,
    original_content_hash TEXT NOT NULL,
    version_note TEXT NOT NULL,
    chunker_json TEXT NOT NULL,
    keyword_engine TEXT NOT NULL,
    embedding_model TEXT NOT NULL,
    fusion_json TEXT NOT NULL,
    model_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(document_id, version_number)
);
CREATE TABLE IF NOT EXISTS rag_chunks (
    id TEXT PRIMARY KEY,
    rag_version_id TEXT NOT NULL REFERENCES rag_versions(id),
    ordinal INTEGER NOT NULL,
    heading TEXT NOT NULL,
    content TEXT NOT NULL,
    search_text TEXT NOT NULL,
    vector_json TEXT NOT NULL,
    char_count INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    UNIQUE(rag_version_id, ordinal)
);
CREATE VIRTUAL TABLE IF NOT EXISTS rag_chunks_fts USING fts5(
    chunk_id UNINDEXED,
    content,
    tokenize='unicode61'
);
CREATE INDEX IF NOT EXISTS idx_rag_versions_document ON rag_versions(document_id, version_number DESC);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_version ON rag_chunks(rag_version_id, ordinal);
"""


MIGRATION_5 = """
CREATE TABLE IF NOT EXISTS mcp_servers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    git_url TEXT NOT NULL,
    version_ref TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    transport TEXT NOT NULL CHECK(transport IN ('STREAMABLE_HTTP')),
    auth_type TEXT NOT NULL CHECK(auth_type IN ('NONE','BEARER')),
    auth_value TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL CHECK(status IN ('DRAFT','CONNECTED','FAILED','DISABLED')),
    allowed_tools_json TEXT NOT NULL,
    declared_read_only_tools_json TEXT NOT NULL,
    tools_json TEXT NOT NULL,
    rejected_tools_json TEXT NOT NULL,
    agent_ids_json TEXT NOT NULL,
    runtime_config_json TEXT NOT NULL,
    last_test_at TEXT,
    last_test_json TEXT NOT NULL,
    validation_errors_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS mcp_call_snaps (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id),
    release_id TEXT NOT NULL REFERENCES releases(id),
    server_id TEXT NOT NULL,
    server_name TEXT NOT NULL,
    git_url TEXT NOT NULL,
    version_ref TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    transport TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    request_args_json TEXT NOT NULL,
    result_summary_json TEXT NOT NULL,
    result_length INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    latency_ms INTEGER NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('SUCCESS','FAILED')),
    error_message TEXT,
    model_api_cost REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_mcp_servers_updated ON mcp_servers(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_mcp_calls_run ON mcp_call_snaps(run_id, started_at);
"""


MIGRATION_6 = """
CREATE TABLE IF NOT EXISTS agent_configs (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    system_prompt TEXT NOT NULL,
    skill_ids_json TEXT NOT NULL,
    rag_document_ids_json TEXT NOT NULL,
    mcp_tool_bindings_json TEXT NOT NULL,
    tool_ids_json TEXT NOT NULL,
    validation_errors_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_agent_configs_updated ON agent_configs(updated_at DESC);
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
    "rag": [],
    "mcp": [],
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
            applied.add(3)
        if 4 not in applied:
            conn.executescript(MIGRATION_4)
            conn.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES(4, ?)",
                (now_iso(),),
            )
            applied.add(4)
        if 5 not in applied:
            conn.executescript(MIGRATION_5)
            conn.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES(5, ?)",
                (now_iso(),),
            )
            applied.add(5)
        if 6 not in applied:
            conn.executescript(MIGRATION_6)
            conn.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES(6, ?)",
                (now_iso(),),
            )
            applied.add(6)
        if 7 not in applied:
            conn.executescript(work_orders.MIGRATION_7)
            conn.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES(7, ?)",
                (now_iso(),),
            )
            applied.add(7)
        if 8 not in applied:
            conn.executescript(action_gateway.MIGRATION_8)
            conn.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES(8, ?)",
                (now_iso(),),
            )
            applied.add(8)
        if 9 not in applied:
            conn.executescript(codrive.MIGRATION_9)
            conn.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES(9, ?)",
                (now_iso(),),
            )
            applied.add(9)
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
        _ensure_agent_configs(conn)
        conn.execute(
            """
            UPDATE agent_configs
            SET description='查询工单事实并通过统一确认网关处理工单变更',
                system_prompt='你是领域无关的工单处理 Agent。只使用当前 Release 已绑定的预置工单 Tool；查询结果必须来自 Tool，写操作必须先展示草稿并经过服务端确认，不得声称未执行的操作已经完成。',
                updated_at=?
            WHERE id='work-order-service'
              AND system_prompt='你是领域无关的工单处理 Agent。当前版本尚未接入工单 Tool，只能说明准备执行的步骤，不得声称已创建、更新或关闭工单。'
            """,
            (now_iso(),),
        )
        work_orders.ensure_demo_orders(conn, now_iso())


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


def _release_agent_bindings(config: dict[str, Any], agent_id: str) -> dict[str, Any]:
    skill_ids = [
        str(item["skill_id"])
        for item in config.get("skills", [])
        if agent_id in item.get("agent_ids", []) and item.get("skill_id")
    ]
    rag_document_ids = [
        str(item["document_id"])
        for item in config.get("rag", [])
        if agent_id in item.get("agent_ids", []) and item.get("document_id")
    ]
    mcp_tool_bindings: list[dict[str, str]] = []
    for server in config.get("mcp", []):
        server_id = str(server.get("server_id", ""))
        tool_agent_ids = server.get("tool_agent_ids")
        if isinstance(tool_agent_ids, dict):
            tool_names = [
                str(tool_name)
                for tool_name, agent_ids in tool_agent_ids.items()
                if isinstance(agent_ids, list) and agent_id in agent_ids
            ]
        elif agent_id in server.get("agent_ids", []):
            tool_names = [str(item) for item in server.get("allowed_tools", [])]
        else:
            tool_names = []
        mcp_tool_bindings.extend(
            {"server_id": server_id, "tool_name": tool_name}
            for tool_name in tool_names
            if server_id and tool_name
        )
    tool_ids = [
        str(item["tool_id"])
        for item in config.get("tools", [])
        if agent_id in item.get("agent_ids", []) and item.get("tool_id")
    ]
    return {
        "skill_ids": list(dict.fromkeys(skill_ids)),
        "rag_document_ids": list(dict.fromkeys(rag_document_ids)),
        "mcp_tool_bindings": list(
            {
                (item["server_id"], item["tool_name"]): item
                for item in mcp_tool_bindings
            }.values()
        ),
        "tool_ids": list(dict.fromkeys(tool_ids)),
    }


def _ensure_agent_configs(conn: sqlite3.Connection) -> None:
    active = conn.execute(
        """
        SELECT r.config_json FROM releases r
        JOIN workspaces w ON w.active_release_id=r.id
        WHERE w.id='default'
        """
    ).fetchone()
    config = json.loads(active["config_json"]) if active else DEFAULT_CONFIG
    agents = config.get("agents") or DEFAULT_CONFIG["agents"]
    for agent in agents:
        agent_id = str(agent.get("id", "")).strip()
        if not agent_id:
            continue
        bindings = _release_agent_bindings(config, agent_id)
        conn.execute(
            """
            INSERT OR IGNORE INTO agent_configs(
                id, name, description, system_prompt, skill_ids_json,
                rag_document_ids_json, mcp_tool_bindings_json, tool_ids_json,
                validation_errors_json, updated_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, '[]', ?)
            """,
            (
                agent_id,
                str(agent.get("name", agent_id)),
                str(agent.get("description", "")),
                str(agent.get("system_prompt", "")),
                json.dumps(bindings["skill_ids"], ensure_ascii=False),
                json.dumps(bindings["rag_document_ids"], ensure_ascii=False),
                json.dumps(bindings["mcp_tool_bindings"], ensure_ascii=False),
                json.dumps(bindings["tool_ids"], ensure_ascii=False),
                now_iso(),
            ),
        )


def _agent_row_dict(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    for source, target in (
        ("skill_ids_json", "skill_ids"),
        ("rag_document_ids_json", "rag_document_ids"),
        ("mcp_tool_bindings_json", "mcp_tool_bindings"),
        ("tool_ids_json", "tool_ids"),
        ("validation_errors_json", "validation_errors"),
    ):
        result[target] = json.loads(result.pop(source))
    return result


def _agent_binding_details(conn: sqlite3.Connection, agent: dict[str, Any]) -> dict[str, Any]:
    skills = []
    for skill_id in agent["skill_ids"]:
        row = conn.execute(
            "SELECT id, name, status, current_version_id FROM skills WHERE id=?",
            (skill_id,),
        ).fetchone()
        if row:
            skills.append(dict(row))
    rag_documents = []
    for document_id in agent["rag_document_ids"]:
        row = conn.execute(
            "SELECT id, name, status, current_version_id FROM rag_documents WHERE id=?",
            (document_id,),
        ).fetchone()
        if row:
            rag_documents.append(dict(row))
    mcp_tools = []
    for binding in agent["mcp_tool_bindings"]:
        row = conn.execute(
            "SELECT id, name, status FROM mcp_servers WHERE id=?",
            (binding.get("server_id"),),
        ).fetchone()
        if row:
            mcp_tools.append(
                {
                    "server_id": row["id"],
                    "server_name": row["name"],
                    "server_status": row["status"],
                    "tool_name": binding.get("tool_name"),
                }
            )
    tool_by_id = {item["id"]: item for item in work_orders.available_tools()}
    preset_tools = [tool_by_id[tool_id] for tool_id in agent["tool_ids"] if tool_id in tool_by_id]
    return {
        "skills": skills,
        "rag_documents": rag_documents,
        "mcp_tools": mcp_tools,
        "preset_tools": preset_tools,
    }


def get_agent_config(agent_id: str) -> dict[str, Any]:
    with connection() as conn:
        row = conn.execute("SELECT * FROM agent_configs WHERE id=?", (agent_id,)).fetchone()
        if row is None:
            raise KeyError(agent_id)
        result = _agent_row_dict(row)
        result["bindings"] = _agent_binding_details(conn, result)
        result["available_preset_tools"] = work_orders.available_tools()
        return result


def list_agent_configs() -> list[dict[str, Any]]:
    order = {agent["id"]: index for index, agent in enumerate(DEFAULT_CONFIG["agents"])}
    with connection() as conn:
        ids = [row["id"] for row in conn.execute("SELECT id FROM agent_configs").fetchall()]
    ids.sort(key=lambda item: (order.get(item, 999), item))
    return [get_agent_config(agent_id) for agent_id in ids]


def bound_agent_ids(
    conn: sqlite3.Connection,
    capability_type: str,
    component_id: str,
    tool_name: str | None = None,
) -> list[str]:
    result: list[str] = []
    for row in conn.execute("SELECT * FROM agent_configs ORDER BY id").fetchall():
        agent = _agent_row_dict(row)
        if capability_type == "SKILL" and component_id in agent["skill_ids"]:
            result.append(agent["id"])
        elif capability_type == "RAG" and component_id in agent["rag_document_ids"]:
            result.append(agent["id"])
        elif capability_type == "MCP":
            if any(
                item.get("server_id") == component_id
                and (tool_name is None or item.get("tool_name") == tool_name)
                for item in agent["mcp_tool_bindings"]
            ):
                result.append(agent["id"])
        elif capability_type == "TOOL" and component_id in agent["tool_ids"]:
            result.append(agent["id"])
    return result


def _agent_payload(payload: dict[str, Any]) -> dict[str, Any]:
    raw_mcp = payload.get("mcp_tool_bindings")
    mcp_bindings: list[dict[str, str]] = []
    if isinstance(raw_mcp, list):
        for item in raw_mcp:
            if not isinstance(item, dict):
                continue
            server_id = str(item.get("server_id", "")).strip()
            tool_name = str(item.get("tool_name", "")).strip()
            if server_id and tool_name:
                mcp_bindings.append({"server_id": server_id, "tool_name": tool_name})
    return {
        "name": str(payload.get("name", "")).strip(),
        "description": str(payload.get("description", "")).strip(),
        "system_prompt": str(payload.get("system_prompt", "")).strip(),
        "skill_ids": _string_list(payload.get("skill_ids")),
        "rag_document_ids": _string_list(payload.get("rag_document_ids")),
        "mcp_tool_bindings": list(
            {
                (item["server_id"], item["tool_name"]): item for item in mcp_bindings
            }.values()
        ),
        "tool_ids": _string_list(payload.get("tool_ids")),
    }


def _agent_validation_errors(
    conn: sqlite3.Connection,
    agent_id: str,
    values: dict[str, Any],
    *,
    require_existing: bool = True,
) -> list[str]:
    errors: list[str] = []
    if not values["name"] or len(values["name"]) > 80:
        errors.append("name 必须为 1-80 个字符")
    if not values["description"] or len(values["description"]) > 500:
        errors.append("description 必须为 1-500 个字符")
    if not values["system_prompt"] or len(values["system_prompt"]) > 20_000:
        errors.append("system_prompt 必须为 1-20000 个字符")
    if require_existing and conn.execute(
        "SELECT 1 FROM agent_configs WHERE id=?", (agent_id,)
    ).fetchone() is None:
        errors.append("未知垂直 Agent")
    for skill_id in values["skill_ids"]:
        row = conn.execute("SELECT status FROM skills WHERE id=?", (skill_id,)).fetchone()
        if row is None or row["status"] != "VALIDATED":
            errors.append(f"Skill {skill_id} 不存在或未通过校验")
    for document_id in values["rag_document_ids"]:
        row = conn.execute(
            "SELECT status FROM rag_documents WHERE id=?", (document_id,)
        ).fetchone()
        if row is None or row["status"] != "VALIDATED":
            errors.append(f"RAG {document_id} 不存在或未通过校验")
    for binding in values["mcp_tool_bindings"]:
        row = conn.execute(
            """
            SELECT status, allowed_tools_json, tools_json FROM mcp_servers WHERE id=?
            """,
            (binding["server_id"],),
        ).fetchone()
        if row is None or row["status"] != "CONNECTED":
            errors.append(f"MCP {binding['server_id']} 不存在或未连接")
            continue
        allowed = set(json.loads(row["allowed_tools_json"]))
        observed = {
            str(item.get("name"))
            for item in json.loads(row["tools_json"])
            if item.get("allowed") is True
        }
        if binding["tool_name"] not in allowed or binding["tool_name"] not in observed:
            errors.append(
                f"MCP Tool {binding['server_id']} / {binding['tool_name']} 不在可绑定只读清单"
            )
    known_tool_ids = {item["id"] for item in work_orders.available_tools()}
    for tool_id in values["tool_ids"]:
        if tool_id not in known_tool_ids:
            errors.append(f"预置 Tool {tool_id} 不存在")
    return errors


def save_agent_config(agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    values = _agent_payload(payload)
    with connection() as conn:
        errors = _agent_validation_errors(conn, agent_id, values)
        if errors:
            raise ValueError("；".join(errors))
        conn.execute(
            """
            UPDATE agent_configs SET name=?, description=?, system_prompt=?,
                skill_ids_json=?, rag_document_ids_json=?, mcp_tool_bindings_json=?,
                tool_ids_json=?, validation_errors_json='[]', updated_at=?
            WHERE id=?
            """,
            (
                values["name"], values["description"], values["system_prompt"],
                json.dumps(values["skill_ids"], ensure_ascii=False),
                json.dumps(values["rag_document_ids"], ensure_ascii=False),
                json.dumps(values["mcp_tool_bindings"], ensure_ascii=False),
                json.dumps(values["tool_ids"], ensure_ascii=False),
                now_iso(), agent_id,
            ),
        )
    return get_agent_config(agent_id)


def create_agent_config(payload: dict[str, Any]) -> dict[str, Any]:
    values = _agent_payload(payload)
    agent_id = new_id("agent")
    with connection() as conn:
        errors = _agent_validation_errors(
            conn, agent_id, values, require_existing=False
        )
        if errors:
            raise ValueError("；".join(errors))
        conn.execute(
            """
            INSERT INTO agent_configs(
                id, name, description, system_prompt, skill_ids_json,
                rag_document_ids_json, mcp_tool_bindings_json, tool_ids_json,
                validation_errors_json, updated_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, '[]', ?)
            """,
            (
                agent_id,
                values["name"],
                values["description"],
                values["system_prompt"],
                json.dumps(values["skill_ids"], ensure_ascii=False),
                json.dumps(values["rag_document_ids"], ensure_ascii=False),
                json.dumps(values["mcp_tool_bindings"], ensure_ascii=False),
                json.dumps(values["tool_ids"], ensure_ascii=False),
                now_iso(),
            ),
        )
    return get_agent_config(agent_id)


def delete_agent_config(agent_id: str) -> dict[str, Any]:
    with connection() as conn:
        row = conn.execute(
            "SELECT id, name FROM agent_configs WHERE id=?", (agent_id,)
        ).fetchone()
        if row is None:
            raise KeyError(agent_id)
        count = conn.execute("SELECT COUNT(*) AS count FROM agent_configs").fetchone()[
            "count"
        ]
        if count <= 1:
            raise ValueError("至少保留一个垂直 Agent")
        conn.execute("DELETE FROM agent_configs WHERE id=?", (agent_id,))
    return {
        "id": agent_id,
        "name": row["name"],
        "deleted": True,
        "active_release_unchanged": True,
    }


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
    return errors


def _skill_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": str(payload.get("name", "")).strip(),
        "description": str(payload.get("description", "")).strip(),
        "applicability": str(payload.get("applicability", "")).strip(),
        "non_applicability": str(payload.get("non_applicability", "")).strip(),
        "content": str(payload.get("content", "")).strip(),
        "output_requirements": str(payload.get("output_requirements", "")).strip(),
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
            legacy_agent_ids: list[str] = []
        else:
            current = conn.execute("SELECT * FROM skills WHERE id=?", (skill_id,)).fetchone()
            if current is None:
                raise KeyError(skill_id)
            version_number = conn.execute(
                "SELECT COALESCE(MAX(version_number), 0) + 1 AS n FROM skill_versions WHERE skill_id=?",
                (skill_id,),
            ).fetchone()["n"]
            created_at = current["created_at"]
            legacy_agent_ids = json.loads(current["agent_ids_json"])
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
                    json.dumps(legacy_agent_ids, ensure_ascii=False),
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
                    json.dumps(legacy_agent_ids, ensure_ascii=False),
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
        result["legacy_agent_ids"] = json.loads(result.pop("agent_ids_json"))
        result["bound_agent_ids"] = bound_agent_ids(conn, "SKILL", skill_id)
        result["agent_ids"] = list(result["bound_agent_ids"])
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
    payload = dict(skill["current_version"])
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


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))


def _mcp_payload(payload: dict[str, Any]) -> dict[str, Any]:
    runtime_config = payload.get("runtime_config")
    if not isinstance(runtime_config, dict):
        runtime_config = {}
    return {
        "name": str(payload.get("name", "")).strip(),
        "git_url": str(payload.get("git_url", "")).strip(),
        "version_ref": str(payload.get("version_ref", "")).strip(),
        "endpoint": str(payload.get("endpoint", "")).strip(),
        "transport": str(payload.get("transport", "STREAMABLE_HTTP")).strip().upper(),
        "auth_type": str(payload.get("auth_type", "NONE")).strip().upper(),
        "auth_value": str(payload.get("auth_value", "")),
        "allowed_tools": _string_list(payload.get("allowed_tools")),
        "declared_read_only_tools": _string_list(payload.get("declared_read_only_tools")),
        "runtime_config": runtime_config,
    }


def _mcp_validation_errors(values: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not values["name"] or len(values["name"]) > 120:
        errors.append("name is required and must not exceed 120 characters")
    if not values["git_url"].startswith("https://") or len(values["git_url"]) > 500:
        errors.append("git_url must be a public HTTPS URL")
    if not values["version_ref"] or len(values["version_ref"]) > 160:
        errors.append("version_ref is required")
    endpoint = values["endpoint"]
    if not endpoint.startswith(("http://", "https://")) or "@" in endpoint.split("//", 1)[-1].split("/", 1)[0]:
        errors.append("endpoint must be HTTP(S) and must not contain credentials")
    if values["transport"] != "STREAMABLE_HTTP":
        errors.append("only STREAMABLE_HTTP transport is supported")
    if values["auth_type"] not in {"NONE", "BEARER"}:
        errors.append("auth_type must be NONE or BEARER")
    if values["auth_type"] == "BEARER" and not values["auth_value"]:
        errors.append("BEARER authentication requires a secret")
    if not values["allowed_tools"]:
        errors.append("at least one allowed Tool is required")
    if not set(values["allowed_tools"]).issubset(set(values["declared_read_only_tools"])):
        errors.append("every allowed Tool must be explicitly declared read-only")
    if len(json.dumps(values["runtime_config"], ensure_ascii=False)) > 20000:
        errors.append("runtime_config exceeds 20000 characters")
    return errors


def save_mcp_server(payload: dict[str, Any], server_id: str | None = None) -> dict[str, Any]:
    values = _mcp_payload(payload)
    errors = _mcp_validation_errors(values)
    timestamp = now_iso()
    with connection() as conn:
        current = None
        if server_id is None:
            server_id = new_id("mcp")
            created_at = timestamp
            legacy_agent_ids: list[str] = []
            tools: list[dict[str, Any]] = []
            rejected: list[dict[str, Any]] = []
            last_test: dict[str, Any] = {}
            last_test_at = None
            status = "DRAFT"
        else:
            current = conn.execute("SELECT * FROM mcp_servers WHERE id=?", (server_id,)).fetchone()
            if current is None:
                raise KeyError(server_id)
            created_at = current["created_at"]
            legacy_agent_ids = json.loads(current["agent_ids_json"])
            tools = json.loads(current["tools_json"])
            rejected = json.loads(current["rejected_tools_json"])
            last_test = json.loads(current["last_test_json"])
            last_test_at = current["last_test_at"]
            connection_keys = (
                "endpoint", "transport", "auth_type", "auth_value",
                "allowed_tools_json", "declared_read_only_tools_json",
            )
            proposed = {
                "endpoint": values["endpoint"],
                "transport": values["transport"],
                "auth_type": values["auth_type"],
                "auth_value": values["auth_value"],
                "allowed_tools_json": json.dumps(values["allowed_tools"], ensure_ascii=False),
                "declared_read_only_tools_json": json.dumps(values["declared_read_only_tools"], ensure_ascii=False),
            }
            unchanged = all(current[key] == proposed[key] for key in connection_keys)
            status = current["status"] if unchanged and current["status"] == "CONNECTED" else "DRAFT"
            if not unchanged:
                tools, rejected, last_test, last_test_at = [], [], {}, None
        if errors:
            status = "DRAFT"
        conn.execute(
            """
            INSERT INTO mcp_servers(
                id, name, git_url, version_ref, endpoint, transport, auth_type, auth_value,
                status, allowed_tools_json, declared_read_only_tools_json, tools_json,
                rejected_tools_json, agent_ids_json, runtime_config_json, last_test_at,
                last_test_json, validation_errors_json, created_at, updated_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name, git_url=excluded.git_url, version_ref=excluded.version_ref,
                endpoint=excluded.endpoint, transport=excluded.transport,
                auth_type=excluded.auth_type, auth_value=excluded.auth_value,
                status=excluded.status, allowed_tools_json=excluded.allowed_tools_json,
                declared_read_only_tools_json=excluded.declared_read_only_tools_json,
                tools_json=excluded.tools_json, rejected_tools_json=excluded.rejected_tools_json,
                agent_ids_json=excluded.agent_ids_json, runtime_config_json=excluded.runtime_config_json,
                last_test_at=excluded.last_test_at, last_test_json=excluded.last_test_json,
                validation_errors_json=excluded.validation_errors_json, updated_at=excluded.updated_at
            """,
            (
                server_id, values["name"], values["git_url"], values["version_ref"],
                values["endpoint"], values["transport"], values["auth_type"], values["auth_value"],
                status, json.dumps(values["allowed_tools"], ensure_ascii=False),
                json.dumps(values["declared_read_only_tools"], ensure_ascii=False),
                json.dumps(tools, ensure_ascii=False), json.dumps(rejected, ensure_ascii=False),
                json.dumps(legacy_agent_ids, ensure_ascii=False),
                json.dumps(values["runtime_config"], ensure_ascii=False), last_test_at,
                json.dumps(last_test, ensure_ascii=False), json.dumps(errors, ensure_ascii=False),
                created_at, timestamp,
            ),
        )
    return get_mcp_server(server_id)


def record_mcp_test(server_id: str, result: dict[str, Any]) -> dict[str, Any]:
    timestamp = now_iso()
    with connection() as conn:
        current = conn.execute("SELECT * FROM mcp_servers WHERE id=?", (server_id,)).fetchone()
        if current is None:
            raise KeyError(server_id)
        configured = json.loads(current["allowed_tools_json"])
        observed = result.get("allowed_read_only_tools") or []
        success = (
            bool(result.get("initialize_success"))
            and bool(result.get("tools_list_success"))
            and not result.get("error")
            and set(configured) == set(observed)
        )
        conn.execute(
            """
            UPDATE mcp_servers SET status=?, tools_json=?, rejected_tools_json=?,
                last_test_at=?, last_test_json=?, validation_errors_json=?, updated_at=?
            WHERE id=?
            """,
            (
                "CONNECTED" if success else "FAILED",
                json.dumps(result.get("tools") or [], ensure_ascii=False),
                json.dumps(result.get("rejected_tools") or [], ensure_ascii=False),
                timestamp, json.dumps(result, ensure_ascii=False),
                json.dumps([] if success else [result.get("error") or "connection test failed"], ensure_ascii=False),
                timestamp, server_id,
            ),
        )
    return get_mcp_server(server_id)


def disable_mcp_server(server_id: str) -> dict[str, Any]:
    with connection() as conn:
        if conn.execute("SELECT 1 FROM mcp_servers WHERE id=?", (server_id,)).fetchone() is None:
            raise KeyError(server_id)
        conn.execute(
            "UPDATE mcp_servers SET status='DISABLED', updated_at=? WHERE id=?",
            (now_iso(), server_id),
        )
    return get_mcp_server(server_id)


def _mcp_dict(row: sqlite3.Row, conn: sqlite3.Connection) -> dict[str, Any]:
    result = dict(row)
    result.pop("auth_value", None)
    for source, target in (
        ("allowed_tools_json", "allowed_tools"),
        ("declared_read_only_tools_json", "declared_read_only_tools"),
        ("tools_json", "tools"),
        ("rejected_tools_json", "rejected_tools"),
        ("agent_ids_json", "legacy_agent_ids"),
        ("runtime_config_json", "runtime_config"),
        ("last_test_json", "last_test"),
        ("validation_errors_json", "validation_errors"),
    ):
        result[target] = json.loads(result.pop(source))
    result["bound_agent_ids"] = bound_agent_ids(conn, "MCP", result["id"])
    result["agent_ids"] = list(result["bound_agent_ids"])
    result["tool_agent_ids"] = {
        tool_name: bound_agent_ids(conn, "MCP", result["id"], tool_name)
        for tool_name in result["allowed_tools"]
    }
    return result


def get_mcp_server(server_id: str) -> dict[str, Any]:
    with connection() as conn:
        row = conn.execute("SELECT * FROM mcp_servers WHERE id=?", (server_id,)).fetchone()
        if row is None:
            raise KeyError(server_id)
        result = _mcp_dict(row, conn)
        refs: list[dict[str, Any]] = []
        for release in conn.execute(
            "SELECT id, version, status, config_json FROM releases ORDER BY created_at DESC"
        ).fetchall():
            config = json.loads(release["config_json"])
            if any(item.get("server_id") == server_id for item in config.get("mcp", [])):
                refs.append({"id": release["id"], "version": release["version"], "status": release["status"]})
        result["release_refs"] = refs
        return result


def list_mcp_servers() -> list[dict[str, Any]]:
    with connection() as conn:
        ids = [row["id"] for row in conn.execute("SELECT id FROM mcp_servers ORDER BY updated_at DESC")]
    return [get_mcp_server(server_id) for server_id in ids]


def get_mcp_connection_config(server_id: str) -> dict[str, Any]:
    with connection() as conn:
        row = conn.execute(
            """
            SELECT endpoint, auth_type, auth_value, allowed_tools_json,
                   declared_read_only_tools_json, runtime_config_json
            FROM mcp_servers WHERE id=?
            """,
            (server_id,),
        ).fetchone()
        if row is None:
            raise KeyError(server_id)
        result = dict(row)
        result["allowed_tools"] = json.loads(result.pop("allowed_tools_json"))
        result["declared_read_only_tools"] = json.loads(
            result.pop("declared_read_only_tools_json")
        )
        result["runtime_config"] = json.loads(result.pop("runtime_config_json"))
        return result


def _candidate_config(conn: sqlite3.Connection, active_config: dict[str, Any]) -> dict[str, Any]:
    config = json.loads(json.dumps(active_config, ensure_ascii=False))
    agent_rows = conn.execute("SELECT * FROM agent_configs ORDER BY id").fetchall()
    agents = [_agent_row_dict(row) for row in agent_rows]
    order = {agent["id"]: index for index, agent in enumerate(DEFAULT_CONFIG["agents"])}
    agents.sort(key=lambda item: (order.get(item["id"], 999), item["id"]))
    config["agents"] = [
        {
            "id": agent["id"],
            "name": agent["name"],
            "description": agent["description"],
            "system_prompt": agent["system_prompt"],
        }
        for agent in agents
    ]

    skill_agent_ids: dict[str, list[str]] = {}
    rag_agent_ids: dict[str, list[str]] = {}
    mcp_tool_agent_ids: dict[tuple[str, str], list[str]] = {}
    tool_agent_ids: dict[str, list[str]] = {}
    for agent in agents:
        for skill_id in agent["skill_ids"]:
            skill_agent_ids.setdefault(skill_id, []).append(agent["id"])
        for document_id in agent["rag_document_ids"]:
            rag_agent_ids.setdefault(document_id, []).append(agent["id"])
        for binding in agent["mcp_tool_bindings"]:
            key = (str(binding.get("server_id", "")), str(binding.get("tool_name", "")))
            if all(key):
                mcp_tool_agent_ids.setdefault(key, []).append(agent["id"])
        for tool_id in agent["tool_ids"]:
            tool_agent_ids.setdefault(tool_id, []).append(agent["id"])

    rows = conn.execute(
        """
        SELECT s.id AS skill_id, v.*
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
            "agent_ids": list(dict.fromkeys(skill_agent_ids[row["skill_id"]])),
        }
        for row in rows
        if row["skill_id"] in skill_agent_ids
    ]
    rag_rows = conn.execute(
        """
        SELECT d.id AS document_id, d.name, d.tags_json, v.*
        FROM rag_documents d JOIN rag_versions v ON v.id=d.current_version_id
        WHERE d.status='VALIDATED' ORDER BY d.created_at, d.id
        """
    ).fetchall()
    config["rag"] = [
        {
            "document_id": row["document_id"],
            "rag_version_id": row["id"],
            "version_number": row["version_number"],
            "name": row["name"],
            "tags": json.loads(row["tags_json"]),
            "version_note": row["version_note"],
            "original_content_hash": row["original_content_hash"],
            "chunker": json.loads(row["chunker_json"]),
            "keyword_engine": row["keyword_engine"],
            "embedding_model": row["embedding_model"],
            "fusion": json.loads(row["fusion_json"]),
            "agent_ids": list(dict.fromkeys(rag_agent_ids[row["document_id"]])),
            "chunk_ids": [
                item["id"]
                for item in conn.execute(
                    "SELECT id FROM rag_chunks WHERE rag_version_id=? ORDER BY ordinal",
                    (row["id"],),
                ).fetchall()
            ],
        }
        for row in rag_rows
        if row["document_id"] in rag_agent_ids
    ]
    mcp_rows = conn.execute(
        """
        SELECT * FROM mcp_servers
        WHERE status='CONNECTED'
        ORDER BY created_at, id
        """
    ).fetchall()
    config["mcp"] = []
    for row in mcp_rows:
        allowed_order = json.loads(row["allowed_tools_json"])
        observed = {
            str(tool.get("name")): tool
            for tool in json.loads(row["tools_json"])
            if tool.get("allowed") is True and tool.get("name")
        }
        selected_tools = [
            tool_name
            for tool_name in allowed_order
            if (row["id"], tool_name) in mcp_tool_agent_ids and tool_name in observed
        ]
        if not selected_tools:
            continue
        per_tool_agents = {
            tool_name: list(
                dict.fromkeys(mcp_tool_agent_ids[(row["id"], tool_name)])
            )
            for tool_name in selected_tools
        }
        server_agent_ids = list(
            dict.fromkeys(
                agent_id
                for tool_name in selected_tools
                for agent_id in per_tool_agents[tool_name]
            )
        )
        config["mcp"].append(
            {
                "server_id": row["id"],
                "name": row["name"],
                "git_url": row["git_url"],
                "version_ref": row["version_ref"],
                "endpoint": row["endpoint"],
                "transport": row["transport"],
                "auth_type": row["auth_type"],
                "allowed_tools": selected_tools,
                "tools": [observed[tool_name] for tool_name in selected_tools],
                "rejected_tools": json.loads(row["rejected_tools_json"]),
                "agent_ids": server_agent_ids,
                "tool_agent_ids": per_tool_agents,
                "runtime_config": json.loads(row["runtime_config_json"]),
                "last_test_at": row["last_test_at"],
                "last_test": json.loads(row["last_test_json"]),
            }
        )
    config["tools"] = work_orders.released_tools(tool_agent_ids)
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
    for document in config.get("rag", []):
        for agent_id in document.get("agent_ids", []):
            conn.execute(
                """
                INSERT INTO release_bindings(
                    release_id, capability_type, component_version_id, agent_id, config_json
                ) VALUES(?, 'RAG', ?, ?, ?)
                """,
                (
                    release_id, document["rag_version_id"], agent_id,
                    json.dumps(document, ensure_ascii=False),
                ),
            )
    for server in config.get("mcp", []):
        tool_agent_ids = server.get("tool_agent_ids")
        if isinstance(tool_agent_ids, dict):
            for tool_name, agent_ids in tool_agent_ids.items():
                for agent_id in agent_ids:
                    conn.execute(
                        """
                        INSERT INTO release_bindings(
                            release_id, capability_type, component_version_id, agent_id, config_json
                        ) VALUES(?, 'MCP_TOOL', ?, ?, ?)
                        """,
                        (
                            release_id, f"{server['server_id']}::{tool_name}", agent_id,
                            json.dumps(
                                {**server, "bound_tool_name": tool_name},
                                ensure_ascii=False,
                            ),
                        ),
                    )
        else:
            for agent_id in server.get("agent_ids", []):
                conn.execute(
                    """
                    INSERT INTO release_bindings(
                        release_id, capability_type, component_version_id, agent_id, config_json
                    ) VALUES(?, 'MCP', ?, ?, ?)
                    """,
                    (
                        release_id, server["server_id"], agent_id,
                        json.dumps(server, ensure_ascii=False),
                    ),
                )
    for tool in config.get("tools", []):
        for agent_id in tool.get("agent_ids", []):
            conn.execute(
                """
                INSERT INTO release_bindings(
                    release_id, capability_type, component_version_id, agent_id, config_json
                ) VALUES(?, 'TOOL', ?, ?, ?)
                """,
                (
                    release_id, tool["tool_id"], agent_id,
                    json.dumps(tool, ensure_ascii=False),
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
    target_rag = ids(target["config"], "rag", "rag_version_id")
    active_rag = ids(active["config"], "rag", "rag_version_id")
    target_mcp = ids(target["config"], "mcp", "server_id")
    active_mcp = ids(active["config"], "mcp", "server_id")
    target_tools = ids(target["config"], "tools", "tool_id")
    active_tools = ids(active["config"], "tools", "tool_id")
    target_mcp_by_id = {item["server_id"]: item for item in target["config"].get("mcp", [])}
    active_mcp_by_id = {item["server_id"]: item for item in active["config"].get("mcp", [])}
    mcp_changed = {
        server_id
        for server_id in target_mcp & active_mcp
        if json.dumps(target_mcp_by_id[server_id], ensure_ascii=False, sort_keys=True)
        != json.dumps(active_mcp_by_id[server_id], ensure_ascii=False, sort_keys=True)
    }

    target_agents = {
        str(item["id"]): item for item in target["config"].get("agents", [])
    }
    active_agents = {
        str(item["id"]): item for item in active["config"].get("agents", [])
    }
    target_agent_ids = set(target_agents)
    active_agent_ids = set(active_agents)
    agents_changed = {
        agent_id
        for agent_id in target_agent_ids & active_agent_ids
        if json.dumps(target_agents[agent_id], ensure_ascii=False, sort_keys=True)
        != json.dumps(active_agents[agent_id], ensure_ascii=False, sort_keys=True)
    }

    def binding_snapshot(config: dict[str, Any]) -> dict[str, dict[str, list[str]]]:
        snapshot: dict[str, dict[str, list[str]]] = {
            str(agent["id"]): {"skills": [], "rag": [], "mcp_tools": [], "tools": []}
            for agent in config.get("agents", [])
        }
        for skill in config.get("skills", []):
            for agent_id in skill.get("agent_ids", []):
                snapshot.setdefault(agent_id, {"skills": [], "rag": [], "mcp_tools": [], "tools": []})[
                    "skills"
                ].append(str(skill["skill_version_id"]))
        for document in config.get("rag", []):
            for agent_id in document.get("agent_ids", []):
                snapshot.setdefault(agent_id, {"skills": [], "rag": [], "mcp_tools": [], "tools": []})[
                    "rag"
                ].append(str(document["rag_version_id"]))
        for server in config.get("mcp", []):
            tool_agents = server.get("tool_agent_ids")
            if isinstance(tool_agents, dict):
                for tool_name, agent_ids in tool_agents.items():
                    for agent_id in agent_ids:
                        snapshot.setdefault(agent_id, {"skills": [], "rag": [], "mcp_tools": [], "tools": []})[
                            "mcp_tools"
                        ].append(f"{server['server_id']}::{tool_name}")
            else:
                for agent_id in server.get("agent_ids", []):
                    for tool_name in server.get("allowed_tools", []):
                        snapshot.setdefault(agent_id, {"skills": [], "rag": [], "mcp_tools": [], "tools": []})[
                            "mcp_tools"
                        ].append(f"{server['server_id']}::{tool_name}")
        for tool in config.get("tools", []):
            for agent_id in tool.get("agent_ids", []):
                snapshot.setdefault(agent_id, {"skills": [], "rag": [], "mcp_tools": [], "tools": []})[
                    "tools"
                ].append(str(tool["tool_id"]))
        for values in snapshot.values():
            for key in values:
                values[key] = sorted(set(values[key]))
        return snapshot

    target_bindings = binding_snapshot(target["config"])
    active_bindings = binding_snapshot(active["config"])
    agent_bindings_changed = sorted(
        agent_id
        for agent_id in set(target_bindings) | set(active_bindings)
        if target_bindings.get(agent_id) != active_bindings.get(agent_id)
    )
    target["diff"] = {
        "base_release_id": active_id,
        "agents_added": sorted(target_agent_ids - active_agent_ids),
        "agents_removed": sorted(active_agent_ids - target_agent_ids),
        "agents_changed": sorted(agents_changed),
        "agents_unchanged": sorted((target_agent_ids & active_agent_ids) - agents_changed),
        "agent_bindings_changed": agent_bindings_changed,
        "agent_binding_snapshot": target_bindings,
        "skills_added": sorted(target_skills - active_skills),
        "skills_removed": sorted(active_skills - target_skills),
        "skills_unchanged": sorted(target_skills & active_skills),
        "rag_added": sorted(target_rag - active_rag),
        "rag_removed": sorted(active_rag - target_rag),
        "rag_unchanged": sorted(target_rag & active_rag),
        "mcp_added": sorted(target_mcp - active_mcp),
        "mcp_removed": sorted(active_mcp - target_mcp),
        "mcp_changed": sorted(mcp_changed),
        "mcp_unchanged": sorted((target_mcp & active_mcp) - mcp_changed),
        "tools_added": sorted(target_tools - active_tools),
        "tools_removed": sorted(active_tools - target_tools),
        "tools_unchanged": sorted(target_tools & active_tools),
    }
    return target


def prepare_run(
    conversation_id: str | None,
    content: str,
    *,
    release_id_override: str | None = None,
) -> dict[str, Any]:
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
        if release_id_override:
            active = conn.execute(
                "SELECT id, version, config_json FROM releases WHERE id=?",
                (release_id_override,),
            ).fetchone()
        else:
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


def save_mcp_call_snap(run_id: str, release_id: str, snap: dict[str, Any]) -> str:
    snap_id = new_id("mcpcall")
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO mcp_call_snaps(
                id, run_id, release_id, server_id, server_name, git_url, version_ref,
                endpoint, transport, tool_name, request_args_json, result_summary_json,
                result_length, started_at, finished_at, latency_ms, status,
                error_message, model_api_cost
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snap_id, run_id, release_id, snap["server_id"], snap["server_name"],
                snap["git_url"], snap["version_ref"], snap["endpoint"], snap["transport"],
                snap["tool_name"], json.dumps(snap.get("request_args") or {}, ensure_ascii=False),
                json.dumps(snap.get("result_summary") or {}, ensure_ascii=False),
                int(snap.get("result_length") or 0), snap["started_at"], snap["finished_at"],
                int(snap.get("latency_ms") or 0), snap["status"], snap.get("error_message"),
                float(snap.get("model_api_cost") or 0),
            ),
        )
    return snap_id


def conversation_history(conversation_id: str, limit: int = 12) -> list[dict[str, str]]:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT role, content FROM (
                SELECT role, content, created_at, id
                FROM messages WHERE conversation_id=?
                UNION ALL
                SELECT role, content, created_at, id
                FROM human_messages WHERE conversation_id=?
            ) ORDER BY created_at DESC, id DESC LIMIT ?
            """,
            (conversation_id, conversation_id, limit),
        ).fetchall()
        result = []
        for row in reversed(rows):
            item = dict(row)
            if item["role"] == "staff":
                item = {"role": "user", "content": f"【员工回复】{item['content']}"}
            result.append(item)
        return result


def list_conversations(limit: int = 100) -> list[dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute(
            """
            WITH all_messages AS (
                SELECT conversation_id, created_at, id FROM messages
                UNION ALL
                SELECT conversation_id, created_at, id FROM human_messages
            )
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
            JOIN all_messages m ON m.conversation_id=c.id
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


def finish_run_without_answer(
    run_id: str,
    *,
    agent_id: str | None,
    latency_ms: int,
) -> dict[str, Any]:
    with connection() as conn:
        conn.execute(
            """
            UPDATE runs SET agent_id=?, status='DONE', finished_at=?, latency_ms=?, estimated_cost=NULL
            WHERE id=?
            """,
            (agent_id, now_iso(), latency_ms, run_id),
        )
    return {"estimated_cost": None, "estimated_cost_cny": None}


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
        mcp_snaps = rows_to_dicts(
            conn.execute(
                "SELECT * FROM mcp_call_snaps WHERE run_id=? ORDER BY started_at",
                (run_id,),
            ).fetchall()
        )
        for snap in mcp_snaps:
            snap["request_args"] = json.loads(snap.pop("request_args_json"))
            snap["result_summary"] = json.loads(snap.pop("result_summary_json"))
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
            "mcp_call_snaps": mcp_snaps,
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
        result.extend(
            {
                **dict(row),
                "run_id": None,
                "release_id": None,
                "agent_id": None,
                "release_version": None,
                "run_status": None,
                "run_started_at": None,
                "run_finished_at": None,
                "agent_name": None,
            }
            for row in conn.execute(
                """
                SELECT id, conversation_id, role, content, created_at
                FROM human_messages WHERE conversation_id=?
                """,
                (conversation_id,),
            ).fetchall()
        )
        result.sort(key=lambda item: (item["created_at"], item["id"]))
        return result
