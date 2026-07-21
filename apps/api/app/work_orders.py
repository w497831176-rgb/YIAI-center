from __future__ import annotations

import json
import re
from typing import Any


DEMO_USER_ID = "demo-user"

MIGRATION_7 = """
CREATE TABLE IF NOT EXISTS work_orders (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    subject TEXT NOT NULL,
    description TEXT NOT NULL,
    category TEXT NOT NULL,
    priority TEXT NOT NULL CHECK(priority IN ('LOW','NORMAL','HIGH','URGENT')),
    status TEXT NOT NULL CHECK(status IN ('OPEN','IN_PROGRESS','CLOSED')),
    result TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_work_orders_user_updated
ON work_orders(user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_work_orders_status_updated
ON work_orders(status, updated_at DESC);
"""


TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "id": "list_work_orders",
        "name": "查询工单列表",
        "description": "按固定演示用户或员工视角查询未删除工单列表。",
        "read_only": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "scope": {"type": "string", "enum": ["USER", "EMPLOYEE"]},
                "status": {"type": "string", "enum": ["OPEN", "IN_PROGRESS", "CLOSED"]},
            },
            "additionalProperties": False,
        },
    },
    {
        "id": "get_work_order",
        "name": "读取工单详情",
        "description": "按工单编号读取一条未删除工单的完整事实。",
        "read_only": True,
        "input_schema": {
            "type": "object",
            "properties": {"work_order_id": {"type": "string"}},
            "required": ["work_order_id"],
            "additionalProperties": False,
        },
    },
    {
        "id": "create_work_order",
        "name": "创建工单",
        "description": "生成创建草稿；只有用户确认后才经 Action Gateway 写入。",
        "read_only": False,
        "input_schema": {
            "type": "object",
            "properties": {
                "subject": {"type": "string"},
                "description": {"type": "string"},
                "category": {"type": "string"},
                "priority": {"type": "string", "enum": ["LOW", "NORMAL", "HIGH", "URGENT"]},
            },
            "required": ["subject", "description", "category", "priority"],
            "additionalProperties": False,
        },
    },
    {
        "id": "update_work_order",
        "name": "更新工单",
        "description": "生成更新差异草稿；确认后更新允许字段。",
        "read_only": False,
        "input_schema": {
            "type": "object",
            "properties": {
                "work_order_id": {"type": "string"},
                "changes": {"type": "object"},
            },
            "required": ["work_order_id", "changes"],
            "additionalProperties": False,
        },
    },
    {
        "id": "close_work_order",
        "name": "关闭工单",
        "description": "生成关闭草稿；确认后把工单状态改为已关闭并保存处理结果。",
        "read_only": False,
        "input_schema": {
            "type": "object",
            "properties": {
                "work_order_id": {"type": "string"},
                "result": {"type": "string"},
            },
            "required": ["work_order_id", "result"],
            "additionalProperties": False,
        },
    },
    {
        "id": "delete_work_order",
        "name": "删除工单",
        "description": "生成软删除草稿；必须经过两次确认，审计记录永久保留。",
        "read_only": False,
        "input_schema": {
            "type": "object",
            "properties": {"work_order_id": {"type": "string"}},
            "required": ["work_order_id"],
            "additionalProperties": False,
        },
    },
]


TOOL_BY_ID = {item["id"]: item for item in TOOL_DEFINITIONS}
WRITE_TOOL_IDS = {
    "create_work_order",
    "update_work_order",
    "close_work_order",
    "delete_work_order",
}


def ensure_demo_orders(conn, now: str) -> None:
    samples = [
        (
            "WO-20260721-001",
            DEMO_USER_ID,
            "联系信息更新",
            "希望把演示资料中的联系电话更新为新的号码。",
            "资料服务",
            "NORMAL",
            "OPEN",
            "",
        ),
        (
            "WO-20260721-002",
            DEMO_USER_ID,
            "设备使用咨询",
            "演示设备在启动后提示配置尚未完成，需要协助核对。",
            "使用支持",
            "HIGH",
            "IN_PROGRESS",
            "已安排员工继续核对配置。",
        ),
        (
            "WO-20260720-003",
            "demo-user-2",
            "服务记录补充",
            "希望补充上一轮服务记录中的说明。",
            "记录维护",
            "LOW",
            "CLOSED",
            "补充内容已核对并归档。",
        ),
    ]
    for values in samples:
        conn.execute(
            """
            INSERT OR IGNORE INTO work_orders(
                id, user_id, subject, description, category, priority, status,
                result, created_at, updated_at, deleted_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (*values, now, now),
        )


def available_tools() -> list[dict[str, Any]]:
    return json.loads(json.dumps(TOOL_DEFINITIONS, ensure_ascii=False))


def tool_definition(tool_id: str) -> dict[str, Any]:
    try:
        return json.loads(json.dumps(TOOL_BY_ID[tool_id], ensure_ascii=False))
    except KeyError as exc:
        raise ValueError(f"未知预置 Tool：{tool_id}") from exc


def released_tools(tool_agent_ids: dict[str, list[str]]) -> list[dict[str, Any]]:
    result = []
    for definition in TOOL_DEFINITIONS:
        agent_ids = list(dict.fromkeys(tool_agent_ids.get(definition["id"], [])))
        if agent_ids:
            result.append({**tool_definition(definition["id"]), "tool_id": definition["id"], "agent_ids": agent_ids})
    return result


def tool_ids_for_agent(release_config: dict[str, Any], agent_id: str) -> set[str]:
    return {
        str(item.get("tool_id"))
        for item in release_config.get("tools", [])
        if agent_id in item.get("agent_ids", []) and item.get("tool_id")
    }


def _row(row) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def list_orders(
    *,
    scope: str = "USER",
    user_id: str = DEMO_USER_ID,
    status: str | None = None,
    include_deleted: bool = False,
) -> list[dict[str, Any]]:
    from . import db

    scope = scope.upper()
    if scope not in {"USER", "EMPLOYEE"}:
        raise ValueError("scope 必须是 USER 或 EMPLOYEE")
    if status is not None and status not in {"OPEN", "IN_PROGRESS", "CLOSED"}:
        raise ValueError("未知工单状态")
    where = []
    params: list[Any] = []
    if scope == "USER":
        where.append("user_id=?")
        params.append(user_id)
    if status:
        where.append("status=?")
        params.append(status)
    if not include_deleted:
        where.append("deleted_at IS NULL")
    sql = "SELECT * FROM work_orders"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY updated_at DESC, id DESC"
    with db.connection() as conn:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]


def get_order(
    work_order_id: str,
    *,
    user_id: str | None = None,
    include_deleted: bool = False,
) -> dict[str, Any]:
    from . import db

    where = ["id=?"]
    params: list[Any] = [work_order_id]
    if user_id is not None:
        where.append("user_id=?")
        params.append(user_id)
    if not include_deleted:
        where.append("deleted_at IS NULL")
    with db.connection() as conn:
        row = conn.execute(
            "SELECT * FROM work_orders WHERE " + " AND ".join(where), params
        ).fetchone()
    if row is None:
        raise KeyError(work_order_id)
    return dict(row)


def execute_read(tool_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if tool_id == "list_work_orders":
        orders = list_orders(
            scope=str(arguments.get("scope", "USER")),
            status=str(arguments["status"]) if arguments.get("status") else None,
        )
        return {"tool_name": tool_id, "count": len(orders), "orders": orders}
    if tool_id == "get_work_order":
        work_order_id = str(arguments.get("work_order_id", "")).strip()
        if not work_order_id:
            raise ValueError("缺少 work_order_id")
        return {"tool_name": tool_id, "work_order": get_order(work_order_id)}
    raise ValueError("该 Tool 不是只读工单 Tool")


def _work_order_id(text: str) -> str | None:
    match = re.search(r"\bWO-\d{8}-[A-Z0-9]{3,12}\b", text.upper())
    return match.group(0) if match else None


def plan_read(content: str, allowed_tool_ids: set[str]) -> dict[str, Any] | None:
    if "工单" not in content:
        return None
    work_order_id = _work_order_id(content)
    detail_terms = ("详情", "明细", "具体", "查看", "读取")
    if work_order_id and "get_work_order" in allowed_tool_ids and any(term in content for term in detail_terms):
        return {"tool_id": "get_work_order", "arguments": {"work_order_id": work_order_id}}
    read_terms = ("查询", "列表", "进度", "有哪些", "查看", "我的工单")
    if "list_work_orders" in allowed_tool_ids and any(term in content for term in read_terms):
        return {"tool_id": "list_work_orders", "arguments": {"scope": "USER"}}
    if work_order_id and "get_work_order" in allowed_tool_ids:
        return {"tool_id": "get_work_order", "arguments": {"work_order_id": work_order_id}}
    return None


def _label_value(content: str, labels: tuple[str, ...]) -> str:
    label_group = "|".join(re.escape(label) for label in labels)
    match = re.search(
        rf"(?:{label_group})\s*[:：=]\s*([^；;\n]+)", content, re.IGNORECASE
    )
    return match.group(1).strip() if match else ""


def _priority(value: str) -> str:
    mapping = {
        "低": "LOW",
        "LOW": "LOW",
        "一般": "NORMAL",
        "普通": "NORMAL",
        "NORMAL": "NORMAL",
        "高": "HIGH",
        "HIGH": "HIGH",
        "紧急": "URGENT",
        "URGENT": "URGENT",
    }
    return mapping.get(value.strip().upper(), mapping.get(value.strip(), ""))


def plan_write(content: str, allowed_tool_ids: set[str]) -> dict[str, Any] | None:
    work_order_id = _work_order_id(content)
    if "创建" in content and "工单" in content and "create_work_order" in allowed_tool_ids:
        payload = {
            "subject": _label_value(content, ("主题", "标题")),
            "description": _label_value(content, ("描述", "问题")),
            "category": _label_value(content, ("类别", "分类")),
            "priority": _priority(_label_value(content, ("优先级",))),
        }
        missing = [key for key, value in payload.items() if not value]
        return {"tool_id": "create_work_order", "payload": payload, "missing_fields": missing}
    if "更新" in content and "工单" in content and "update_work_order" in allowed_tool_ids:
        changes: dict[str, Any] = {}
        for field, labels in (
            ("subject", ("主题", "标题")),
            ("description", ("描述", "补充信息")),
            ("category", ("类别", "分类")),
            ("result", ("处理结果", "结果")),
        ):
            value = _label_value(content, labels)
            if value:
                changes[field] = value
        priority = _priority(_label_value(content, ("优先级",)))
        if priority:
            changes["priority"] = priority
        missing = []
        if not work_order_id:
            missing.append("work_order_id")
        if not changes:
            missing.append("changes")
        return {
            "tool_id": "update_work_order",
            "payload": {"work_order_id": work_order_id or "", "changes": changes},
            "missing_fields": missing,
        }
    if "关闭" in content and "工单" in content and "close_work_order" in allowed_tool_ids:
        result = _label_value(content, ("处理结果", "结果", "说明"))
        missing = []
        if not work_order_id:
            missing.append("work_order_id")
        if not result:
            missing.append("result")
        return {
            "tool_id": "close_work_order",
            "payload": {"work_order_id": work_order_id or "", "result": result},
            "missing_fields": missing,
        }
    if "删除" in content and "工单" in content and "delete_work_order" in allowed_tool_ids:
        return {
            "tool_id": "delete_work_order",
            "payload": {"work_order_id": work_order_id or ""},
            "missing_fields": [] if work_order_id else ["work_order_id"],
        }
    return None


def validate_write_payload(tool_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    if tool_id not in WRITE_TOOL_IDS:
        raise ValueError("该 Tool 不是工单写 Tool")
    values = json.loads(json.dumps(payload, ensure_ascii=False))
    if tool_id == "create_work_order":
        for field in ("subject", "description", "category", "priority"):
            values[field] = str(values.get(field, "")).strip()
            if not values[field]:
                raise ValueError(f"缺少 {field}")
        if values["priority"] not in {"LOW", "NORMAL", "HIGH", "URGENT"}:
            raise ValueError("priority 不合法")
        for field, maximum in (("subject", 120), ("description", 4000), ("category", 80)):
            if len(values[field]) > maximum:
                raise ValueError(f"{field} 过长")
        return values
    work_order_id = str(values.get("work_order_id", "")).strip()
    if not work_order_id:
        raise ValueError("缺少 work_order_id")
    get_order(work_order_id, include_deleted=False)
    if tool_id == "update_work_order":
        raw_changes = values.get("changes")
        if not isinstance(raw_changes, dict) or not raw_changes:
            raise ValueError("changes 必须包含至少一个变化")
        allowed = {"subject", "description", "category", "priority", "result", "status"}
        changes = {str(key): value for key, value in raw_changes.items() if key in allowed}
        if not changes:
            raise ValueError("没有允许更新的字段")
        if "priority" in changes and changes["priority"] not in {"LOW", "NORMAL", "HIGH", "URGENT"}:
            raise ValueError("priority 不合法")
        if "status" in changes and changes["status"] not in {"OPEN", "IN_PROGRESS"}:
            raise ValueError("更新操作只能把状态设为 OPEN 或 IN_PROGRESS；关闭请使用 close_work_order")
        return {"work_order_id": work_order_id, "changes": changes}
    if tool_id == "close_work_order":
        result = str(values.get("result", "")).strip()
        if not result:
            raise ValueError("缺少 result")
        return {"work_order_id": work_order_id, "result": result}
    return {"work_order_id": work_order_id}


def before_snapshot(tool_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    if tool_id == "create_work_order":
        return None
    return get_order(str(payload["work_order_id"]), include_deleted=True)


def apply_write(conn, tool_id: str, payload: dict[str, Any], now: str, new_order_id: str | None = None) -> dict[str, Any]:
    if tool_id == "create_work_order":
        if not new_order_id:
            raise ValueError("创建工单缺少服务端编号")
        conn.execute(
            """
            INSERT INTO work_orders(
                id, user_id, subject, description, category, priority, status,
                result, created_at, updated_at, deleted_at
            ) VALUES(?, ?, ?, ?, ?, ?, 'OPEN', '', ?, ?, NULL)
            """,
            (
                new_order_id,
                DEMO_USER_ID,
                payload["subject"],
                payload["description"],
                payload["category"],
                payload["priority"],
                now,
                now,
            ),
        )
    elif tool_id == "update_work_order":
        changes = payload["changes"]
        assignments = [f"{field}=?" for field in changes]
        params = list(changes.values())
        assignments.append("updated_at=?")
        params.extend([now, payload["work_order_id"]])
        cursor = conn.execute(
            f"UPDATE work_orders SET {', '.join(assignments)} WHERE id=? AND deleted_at IS NULL",
            params,
        )
        if cursor.rowcount != 1:
            raise KeyError(payload["work_order_id"])
    elif tool_id == "close_work_order":
        cursor = conn.execute(
            """
            UPDATE work_orders SET status='CLOSED', result=?, updated_at=?
            WHERE id=? AND deleted_at IS NULL
            """,
            (payload["result"], now, payload["work_order_id"]),
        )
        if cursor.rowcount != 1:
            raise KeyError(payload["work_order_id"])
    elif tool_id == "delete_work_order":
        cursor = conn.execute(
            """
            UPDATE work_orders SET deleted_at=?, updated_at=?
            WHERE id=? AND deleted_at IS NULL
            """,
            (now, now, payload["work_order_id"]),
        )
        if cursor.rowcount != 1:
            raise KeyError(payload["work_order_id"])
    else:
        raise ValueError("未知工单写 Tool")
    target_id = new_order_id if tool_id == "create_work_order" else payload["work_order_id"]
    row = conn.execute("SELECT * FROM work_orders WHERE id=?", (target_id,)).fetchone()
    if row is None:
        raise RuntimeError("工单写入后无法读取回执")
    return dict(row)


def format_read_answer(result: dict[str, Any]) -> str:
    if result.get("tool_name") == "get_work_order":
        item = result["work_order"]
        return (
            f"工单 {item['id']}：{item['subject']}\n"
            f"类别：{item['category']}；优先级：{item['priority']}；状态：{item['status']}。\n"
            f"描述：{item['description']}\n"
            f"处理结果：{item['result'] or '暂无'}\n"
            f"更新时间：{item['updated_at']}"
        )
    orders = result.get("orders", [])
    if not orders:
        return "当前没有可见的工单。"
    lines = [f"共查询到 {len(orders)} 条工单："]
    lines.extend(
        f"- {item['id']}｜{item['subject']}｜{item['priority']}｜{item['status']}｜{item['updated_at']}"
        for item in orders
    )
    return "\n".join(lines)

