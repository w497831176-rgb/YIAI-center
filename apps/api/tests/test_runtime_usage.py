import dataclasses
import json
import tempfile
import unittest

from app import db, runtime


def snap(call_id, usage_status):
    complete = usage_status == "COMPLETE"
    return {
        "cloud_call_id": call_id,
        "provider": "deepseek",
        "model": "deepseek-v4-flash",
        "request_started_at": "2026-07-20T00:00:00+00:00",
        "response_finished_at": "2026-07-20T00:00:01+00:00",
        "latency_ms": 1000,
        "status": "SUCCEEDED",
        "prompt_cache_miss_tokens": 10 if complete else None,
        "prompt_cache_hit_tokens": 0 if complete else None,
        "completion_tokens": 5 if complete else None,
        "total_tokens": 15 if complete else None,
        "usage_status": usage_status,
        "price_snapshot": {
            "currency": "USD",
            "unit": "per_1m_tokens",
            "cache_hit_input": 0.0028,
            "cache_miss_input": 0.14,
            "output": 0.28,
        },
        "estimated_cost": 0.0000028 if complete else None,
        "provider_request_id": call_id,
        "error_code": None,
    }


class FakeAdapter:
    def complete(self, _messages):
        return (
            json.dumps(
                {
                    "target_agent": "general-service",
                    "confidence": 0.9,
                    "reason": "test",
                    "needs_clarification": False,
                }
            ),
            snap("call_router_test", "COMPLETE"),
        )

    def stream(self, _messages):
        yield {"kind": "delta", "content": "答案仍然返回"}
        yield {"kind": "result", "snap": snap("call_main_test", "INCOMPLETE")}


class HallucinatingWriteAdapter(FakeAdapter):
    def stream(self, _messages):
        yield {
            "kind": "delta",
            "content": "工单已创建成功，系统返回工单编号为 WK240101-001。",
        }
        yield {"kind": "result", "snap": snap("call_main_fake_write", "COMPLETE")}


class RecordingAdapter(FakeAdapter):
    router_calls = []

    def complete(self, messages):
        self.__class__.router_calls.append(messages)
        return super().complete(messages)


class RuntimeUsageTests(unittest.TestCase):
    def test_answer_survives_missing_usage_without_fake_cost(self):
        original_settings = db.settings
        original_adapter = runtime.DeepSeekAdapter
        with tempfile.TemporaryDirectory() as directory:
            db.settings = dataclasses.replace(
                original_settings, db_path=f"{directory}/test.sqlite"
            )
            runtime.DeepSeekAdapter = FakeAdapter
            try:
                db.init_db()
                events = "".join(runtime.execute_chat(None, "测试 Usage 缺失"))
                self.assertIn("答案仍然返回", events)
                run = db.list_runs(1)[0]
                detail = db.get_run_detail(run["id"])
                self.assertEqual(detail["run"]["status"], "DONE")
                self.assertIsNone(detail["run"]["estimated_cost"])
                self.assertIsNone(detail["run"]["estimated_cost_cny"])
                self.assertEqual(
                    detail["cloud_call_snaps"][1]["usage_status"], "INCOMPLETE"
                )
                self.assertAlmostEqual(
                    detail["cloud_call_snaps"][0]["estimated_cost_cny"],
                    0.0000028 * 7.2,
                )
                self.assertIsNone(
                    detail["cloud_call_snaps"][1]["prompt_cache_miss_tokens"]
                )
                event_by_type = {
                    event["event_type"]: event for event in detail["trace_events"]
                }
                self.assertEqual(
                    event_by_type["user_message_received"]["payload"]["content"],
                    "测试 Usage 缺失",
                )
                self.assertEqual(
                    event_by_type["assistant_response_completed"]["payload"]["content"],
                    "答案仍然返回",
                )
                self.assertEqual(detail["messages"]["input"]["content"], "测试 Usage 缺失")
                self.assertEqual(detail["messages"]["output"]["content"], "答案仍然返回")
                conversations = db.list_conversations()
                self.assertEqual(len(conversations), 1)
                self.assertEqual(conversations[0]["message_count"], 2)
                self.assertEqual(conversations[0]["title"], "测试 Usage 缺失")
                with db.connection() as conn:
                    candidate_count = conn.execute(
                        "SELECT COUNT(*) AS n FROM badcase_candidates"
                    ).fetchone()["n"]
                self.assertEqual(candidate_count, 1)
            finally:
                runtime.DeepSeekAdapter = original_adapter
                db.settings = original_settings

    def test_router_cloud_call_receives_recent_conversation_context(self):
        original_settings = db.settings
        original_adapter = runtime.DeepSeekAdapter
        with tempfile.TemporaryDirectory() as directory:
            db.settings = dataclasses.replace(
                original_settings, db_path=f"{directory}/test.sqlite"
            )
            runtime.DeepSeekAdapter = RecordingAdapter
            RecordingAdapter.router_calls = []
            try:
                db.init_db()
                list(runtime.execute_chat(None, "我先说明：厨房天花板正在漏水"))
                conversation_id = db.list_conversations(1)[0]["id"]
                list(runtime.execute_chat(conversation_id, "请继续处理这个问题"))
                second_router_messages = RecordingAdapter.router_calls[-1]
                joined = json.dumps(second_router_messages, ensure_ascii=False)
                self.assertIn("厨房天花板正在漏水", joined)
                self.assertIn("请继续处理这个问题", joined)
                run = db.list_runs(1)[0]
                detail = db.get_run_detail(run["id"])
                context_event = next(
                    item
                    for item in detail["trace_events"]
                    if item["event_type"] == "router_context_prepared"
                )
                self.assertGreaterEqual(context_event["payload"]["message_count"], 3)
            finally:
                runtime.DeepSeekAdapter = original_adapter
                db.settings = original_settings

    def test_unverified_write_success_claim_is_blocked_and_recorded(self):
        original_settings = db.settings
        original_adapter = runtime.DeepSeekAdapter
        with tempfile.TemporaryDirectory() as directory:
            db.settings = dataclasses.replace(
                original_settings, db_path=f"{directory}/test.sqlite"
            )
            runtime.DeepSeekAdapter = HallucinatingWriteAdapter
            try:
                db.init_db()
                events = "".join(runtime.execute_chat(None, "请介绍一下你能提供什么帮助"))
                self.assertNotIn("WK240101-001", events)
                self.assertIn("没有获得真实写 Tool 回执", events)
                run = db.list_runs(1)[0]
                detail = db.get_run_detail(run["id"])
                event_types = [item["event_type"] for item in detail["trace_events"]]
                self.assertIn("output_guard_applied", event_types)
                with db.connection() as conn:
                    codes = [
                        row["rule_code"]
                        for row in conn.execute(
                            "SELECT rule_code FROM badcase_candidates WHERE run_id=?",
                            (run["id"],),
                        ).fetchall()
                    ]
                self.assertIn("UNVERIFIED_WRITE_CLAIM_BLOCKED", codes)
            finally:
                runtime.DeepSeekAdapter = original_adapter
                db.settings = original_settings


if __name__ == "__main__":
    unittest.main()
