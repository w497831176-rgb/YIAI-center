import dataclasses
import json
import tempfile
import unittest
from pathlib import Path

from app import action_gateway, codrive, db, work_orders
from app.runtime import deterministic_route, execute_chat


class WorkOrderActionCodriveTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.original_settings = db.settings
        db.settings = dataclasses.replace(
            self.original_settings,
            db_path=f"{self.directory.name}/test.sqlite",
            deepseek_api_key="",
        )
        db.init_db()

    def tearDown(self):
        db.settings = self.original_settings
        self.directory.cleanup()

    @staticmethod
    def agent_payload(agent, tool_ids):
        return {
            "name": agent["name"],
            "description": agent["description"],
            "system_prompt": agent["system_prompt"],
            "skill_ids": agent["skill_ids"],
            "rag_document_ids": agent["rag_document_ids"],
            "mcp_tool_bindings": agent["mcp_tool_bindings"],
            "tool_ids": tool_ids,
        }

    def publish_tools(self, tool_ids):
        agent = db.get_agent_config("work-order-service")
        db.save_agent_config(agent["id"], self.agent_payload(agent, tool_ids))
        candidate = db.create_candidate(
            f"V0.5.13-tools-{len(tool_ids)}", "测试工单 Tool Release 快照"
        )
        db.activate_release(candidate["id"])
        return candidate

    def create_conversation(self):
        run = db.prepare_run(None, "建立测试会话")
        db.finish_run_without_answer(run["run_id"], agent_id=None, latency_ms=0)
        return run["conversation_id"]

    def test_read_tools_use_real_seeded_data_and_user_scope(self):
        user_orders = work_orders.list_orders(scope="USER")
        employee_orders = work_orders.list_orders(scope="EMPLOYEE")
        self.assertEqual(len(user_orders), 2)
        self.assertEqual(len(employee_orders), 3)
        detail = work_orders.execute_read(
            "get_work_order", {"work_order_id": "WO-20260721-001"}
        )
        self.assertEqual(detail["work_order"]["subject"], "联系信息更新")

    def test_runtime_calls_released_read_tool_and_falls_back_to_exact_result(self):
        self.publish_tools(["list_work_orders", "get_work_order"])
        chunks = list(execute_chat(None, "请查询我的工单进度"))
        self.assertTrue(any("event: done" in chunk for chunk in chunks))
        conversations = db.list_conversations()
        messages = db.get_messages(conversations[0]["id"])
        self.assertIn("共查询到 2 条工单", messages[-1]["content"])
        run = db.list_runs(1)[0]
        detail = db.get_run_detail(run["id"])
        event_types = [item["event_type"] for item in detail["trace_events"]]
        self.assertIn("preset_tool_request", event_types)
        self.assertIn("preset_tool_response", event_types)
        response_event = next(
            item for item in detail["trace_events"] if item["event_type"] == "preset_tool_response"
        )
        self.assertEqual(response_event["payload"]["model_api_cost"], 0)

    def test_router_fallback_uses_released_tool_capability_instead_of_agent_order(self):
        release = self.publish_tools(["list_work_orders", "get_work_order"])
        release_config = db.get_release(release["id"])["config"]
        route = deterministic_route(
            "请查询我的工单进度", release_config["agents"], release_config
        )
        self.assertEqual(route["target_agent"], "work-order-service")
        self.assertIn("已发布 Tool", route["reason"])

    def test_create_confirmation_is_required_one_time_and_idempotent(self):
        release = self.publish_tools(["create_work_order"])
        before = len(work_orders.list_orders(scope="EMPLOYEE"))
        action = action_gateway.create_draft(
            tool_name="create_work_order",
            payload={
                "subject": "确认机制测试",
                "description": "确认前不能写入数据库。",
                "category": "测试",
                "priority": "NORMAL",
            },
            release_id=release["id"],
            idempotency_key="create-once",
        )
        self.assertEqual(len(work_orders.list_orders(scope="EMPLOYEE")), before)
        completed = action_gateway.confirm_action(
            action["id"], confirmation_token=action["confirmation_token"]
        )
        self.assertEqual(completed["status"], "SUCCEEDED")
        self.assertEqual(len(work_orders.list_orders(scope="EMPLOYEE")), before + 1)
        replay = action_gateway.confirm_action(
            action["id"], confirmation_token=action["confirmation_token"]
        )
        self.assertTrue(replay["idempotent_replay"])
        self.assertEqual(len(work_orders.list_orders(scope="EMPLOYEE")), before + 1)

    def test_employee_write_executes_immediately_without_confirmation(self):
        release = self.publish_tools(["update_work_order"])
        action = action_gateway.execute_staff_action(
            tool_name="update_work_order",
            payload={
                "work_order_id": "WO-20260721-001",
                "changes": {"description": "员工已直接更新"},
            },
            release_id=release["id"],
            idempotency_key="staff-direct-update",
        )
        self.assertEqual(action["status"], "SUCCEEDED")
        self.assertEqual(action["required_confirmations"], 0)
        self.assertFalse(action["requires_confirmation"])
        self.assertEqual(action["receipt"]["actor"], "STAFF")
        self.assertEqual(
            work_orders.get_order("WO-20260721-001")["description"],
            "员工已直接更新",
        )

    def test_multiturn_create_collects_fields_and_text_confirmation_cannot_fake_write(self):
        self.publish_tools(["create_work_order"])
        before = len(work_orders.list_orders(scope="EMPLOYEE"))
        first = "".join(execute_chat(None, "我房子在漏水，我要报修创建工单"))
        self.assertIn("missing_fields", first)
        conversation_id = db.list_conversations(1)[0]["id"]
        second = "".join(
            execute_chat(
                conversation_id,
                """- **subject**（工单标题）：房屋漏水紧急报修
- **description**（详细描述）：厨房天花板严重漏水，需要立即维修
- **category**（工单类别）：房屋维修
- **priority**（优先级）：紧急""",
            )
        )
        self.assertIn("event: action_pending", second)
        collection = db.get_open_action_collection(conversation_id)
        self.assertEqual(collection["status"], "AWAITING_CONFIRMATION")
        self.assertEqual(collection["payload"]["priority"], "URGENT")
        action = action_gateway.get_action(collection["action_id"], include_audit=False)
        self.assertEqual(action["payload"]["subject"], "房屋漏水紧急报修")
        third = "".join(execute_chat(conversation_id, "正确"))
        self.assertIn("不能由模型文字代替执行", third)
        self.assertEqual(len(work_orders.list_orders(scope="EMPLOYEE")), before)
        with db.connection() as conn:
            route = conn.execute(
                """
                SELECT payload_json FROM trace_events
                WHERE run_id=(SELECT id FROM runs ORDER BY started_at DESC, id DESC LIMIT 1)
                  AND event_type='route_decision'
                ORDER BY sequence DESC LIMIT 1
                """
            ).fetchone()
        self.assertEqual(json.loads(route["payload_json"])["target_agent"], "work-order-service")

    def test_markdown_english_labels_are_parsed_without_cloud_guessing(self):
        plan = work_orders.plan_write(
            """创建工单
**subject**（工单标题）：漏水维修
**description**（详细描述）：厨房漏水
**category**（工单类别）：房屋维修
**priority**（优先级）：紧急""",
            {"create_work_order"},
        )
        self.assertEqual(plan["missing_fields"], [])
        self.assertEqual(plan["payload"]["priority"], "URGENT")

    def test_update_close_and_soft_delete_share_gateway(self):
        release = self.publish_tools(
            ["update_work_order", "close_work_order", "delete_work_order"]
        )
        update = action_gateway.create_draft(
            tool_name="update_work_order",
            payload={
                "work_order_id": "WO-20260721-001",
                "changes": {"priority": "HIGH"},
            },
            release_id=release["id"],
            idempotency_key="update-once",
        )
        updated = action_gateway.confirm_action(
            update["id"], confirmation_token=update["confirmation_token"]
        )
        self.assertEqual(updated["result"]["priority"], "HIGH")

        close = action_gateway.create_draft(
            tool_name="close_work_order",
            payload={"work_order_id": "WO-20260721-001", "result": "已核对完成"},
            release_id=release["id"],
            idempotency_key="close-once",
        )
        closed = action_gateway.confirm_action(
            close["id"], confirmation_token=close["confirmation_token"]
        )
        self.assertEqual(closed["result"]["status"], "CLOSED")

        delete = action_gateway.create_draft(
            tool_name="delete_work_order",
            payload={"work_order_id": "WO-20260721-001"},
            release_id=release["id"],
            idempotency_key="delete-once",
        )
        first = action_gateway.confirm_action(
            delete["id"], confirmation_token=delete["confirmation_token"]
        )
        self.assertEqual(first["status"], "AWAITING_CONFIRMATION")
        self.assertEqual(first["remaining_confirmations"], 1)
        self.assertIsNotNone(work_orders.get_order("WO-20260721-001"))
        second = action_gateway.confirm_action(
            delete["id"], confirmation_token=first["confirmation_token"]
        )
        self.assertEqual(second["status"], "SUCCEEDED")
        with self.assertRaises(KeyError):
            work_orders.get_order("WO-20260721-001")
        audited = work_orders.get_order("WO-20260721-001", include_deleted=True)
        self.assertIsNotNone(audited["deleted_at"])
        self.assertGreaterEqual(len(action_gateway.get_action(delete["id"])["audit_events"]), 6)

    def test_unreleased_write_tool_is_rejected(self):
        active = db.get_workspace()["active_release_id"]
        with self.assertRaises(ValueError):
            action_gateway.create_draft(
                tool_name="delete_work_order",
                payload={"work_order_id": "WO-20260721-001"},
                release_id=active,
                idempotency_key="not-released",
            )

    def test_codrive_allows_unlimited_staff_rounds_and_has_no_closed_state(self):
        conversation_id = self.create_conversation()
        requested = codrive.request_human(
            conversation_id,
            actor="USER",
            reason="需要员工协助",
            summary="首次交接",
        )
        active = codrive.accept_handoff(
            conversation_id, expected_version=requested["version"]
        )
        for index in range(5):
            result = codrive.add_staff_message(
                conversation_id,
                f"员工连续回复 {index + 1}",
                expected_version=active["version"],
            )
            active = result["session"]
        self.assertEqual(active["state"], "HUMAN_ACTIVE")
        self.assertEqual(len(codrive.staff_messages(conversation_id)), 5)
        resuming = codrive.begin_return_to_ai(
            conversation_id,
            summary="员工已补充信息",
            expected_version=active["version"],
        )
        restored = codrive.complete_return_to_ai(
            conversation_id, run_id="run-demo", success=True
        )
        self.assertEqual(resuming["state"], "AI_RESUMING")
        self.assertEqual(restored["state"], "AI_ACTIVE")
        self.assertTrue(restored["ai_standby"])
        self.assertNotIn("CLOSED", json.dumps(codrive.get_session(conversation_id)))

        requested_again = codrive.request_human(
            conversation_id,
            actor="AI",
            reason="能力失败，建议员工继续协同",
            expected_version=restored["version"],
        )
        self.assertEqual(requested_again["state"], "HANDOFF_REQUESTED")

    def test_stale_staff_reply_is_rejected_and_ai_is_suppressed(self):
        conversation_id = self.create_conversation()
        requested = codrive.request_human(
            conversation_id, actor="USER", reason="并发测试"
        )
        active = codrive.accept_handoff(
            conversation_id, expected_version=requested["version"]
        )
        first = codrive.add_staff_message(
            conversation_id, "第一条", expected_version=active["version"]
        )
        with self.assertRaises(RuntimeError):
            codrive.add_staff_message(
                conversation_id, "并发旧版本", expected_version=active["version"]
            )
        chunks = list(execute_chat(conversation_id, "我再补充一条信息"))
        self.assertTrue(any("event: human_active" in chunk for chunk in chunks))
        self.assertFalse(any("event: delta" in chunk for chunk in chunks))
        self.assertEqual(first["session"]["state"], "HUMAN_ACTIVE")

    def test_employee_ui_exposes_return_to_ai_without_completion_action(self):
        test_file = Path(__file__).resolve()
        candidates = [
            test_file.parents[2] / "web" / "static" / "app.js",
            test_file.parents[1] / "static" / "app.js",
        ]
        script_path = next((item for item in candidates if item.exists()), None)
        self.assertIsNotNone(script_path, "找不到前端静态文件，无法执行共驾 UI 契约检查")
        script = script_path.read_text(encoding="utf-8")
        self.assertIn("交还 AI", script)
        self.assertIn("/codrive/messages", script)
        self.assertNotIn("<button>结束会话", script)
        self.assertNotIn("<button>结束共驾", script)
        self.assertIn("/api/employee/work-orders/actions", script)
        self.assertIn("员工提交后直接写入", script)
        self.assertNotIn("填写要更新的工单描述（只生成草稿", script)
        self.assertNotIn(">删除草稿</button>", script)
        self.assertIn("confirmableActions", script)


if __name__ == "__main__":
    unittest.main()
