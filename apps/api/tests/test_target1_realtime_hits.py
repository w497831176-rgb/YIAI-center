import dataclasses
import json
import tempfile
import unittest

from app import codrive, db, rag, runtime, work_orders


def complete_snap(call_id: str) -> dict:
    return {
        "cloud_call_id": call_id,
        "provider": "deepseek",
        "model": "deepseek-v4-flash",
        "request_started_at": "2026-07-22T00:00:00+00:00",
        "response_finished_at": "2026-07-22T00:00:01+00:00",
        "latency_ms": 1000,
        "status": "SUCCEEDED",
        "prompt_cache_miss_tokens": 10,
        "prompt_cache_hit_tokens": 2,
        "completion_tokens": 4,
        "total_tokens": 16,
        "usage_status": "COMPLETE",
        "price_snapshot": {
            "currency": "CNY",
            "unit": "per_1m_tokens",
            "cache_hit_input": 0.0028 * 7.2,
            "cache_miss_input": 0.14 * 7.2,
            "output": 0.28 * 7.2,
            "exchange_rate_snapshot": {"rate": 7.2, "quote": "CNY"},
        },
        "estimated_cost": 0.0000028,
        "provider_request_id": call_id,
        "error_code": None,
    }


class RouterOnlyAdapter:
    def complete(self, _messages):
        return (
            json.dumps(
                {
                    "target_agent": "general-service",
                    "confidence": 0.92,
                    "reason": "一般请求",
                    "needs_clarification": False,
                }
            ),
            complete_snap("router-target1"),
        )

    def stream(self, _messages):
        raise AssertionError("模糊请求应在集中追问前结束，不进入回答模型")


class Target1RealtimeHitTests(unittest.TestCase):
    def setUp(self):
        self.original_settings = db.settings
        self.original_adapter = runtime.DeepSeekAdapter
        self.directory = tempfile.TemporaryDirectory()
        db.settings = dataclasses.replace(
            self.original_settings,
            db_path=f"{self.directory.name}/target1.sqlite",
        )
        db.init_db()

    def tearDown(self):
        runtime.DeepSeekAdapter = self.original_adapter
        db.settings = self.original_settings
        self.directory.cleanup()

    def test_ai_handoff_policy_honors_user_opt_out(self):
        trigger = codrive.assess_ai_handoff(
            "这个问题已经连续处理三次失败，而且现在可能继续造成损失。我非常着急。"
        )
        self.assertTrue(trigger["should_handoff"])
        self.assertEqual(trigger["rule_code"], "REPEATED_FAILURE_WITH_HIGH_RISK")
        opted_out = codrive.assess_ai_handoff(
            "已经连续三次处理失败，可能继续造成损失，但暂时不要转人工"
        )
        self.assertFalse(opted_out["should_handoff"])
        self.assertTrue(opted_out["signals"]["user_opt_out"])
        self.assertFalse(codrive.is_handoff_request("暂时不要转人工"))

    def test_rag_parenthesized_citation_is_normalized_to_clickable_contract(self):
        citation = "[RAG:通用服务规则#chunk_1]"
        answer, used, removed = rag.sanitize_citations(
            "依据如下（RAG:通用服务规则#chunk_1）", [citation]
        )
        self.assertIn(citation, answer)
        self.assertEqual(used, [citation])
        self.assertEqual(removed, [])

    def test_read_request_with_write_negation_never_creates_draft(self):
        prompt = "请查询我的全部工单，不要创建或修改工单。"
        write = work_orders.plan_write(
            prompt,
            {"create_work_order", "update_work_order", "close_work_order", "delete_work_order"},
        )
        read = work_orders.plan_read(prompt, {"list_work_orders"})
        self.assertIsNone(write)
        self.assertEqual(read["tool_id"], "list_work_orders")

    def test_ambiguous_run_creates_badcase_evaluation_and_summary(self):
        runtime.DeepSeekAdapter = RouterOnlyAdapter
        events = "".join(runtime.execute_chat(None, "帮我处理一下，越快越好。"))
        self.assertIn("ROUTER_LOW_CONFIDENCE", events)
        run = db.list_runs(1)[0]
        detail = db.get_run_detail(run["id"])
        summary = detail["capability_summary"]
        self.assertEqual(summary["badcases"][0]["rule_code"], "ROUTER_LOW_CONFIDENCE")
        self.assertEqual(summary["evaluation"]["status"], "WARN")
        self.assertEqual(summary["route"]["needs_clarification"], True)
        messages = db.get_messages(run["conversation_id"])
        assistant = next(item for item in messages if item["role"] == "assistant")
        self.assertEqual(
            assistant["capability_summary"]["evaluation"]["status"], "WARN"
        )

    def test_release_diff_is_agent_first_with_nested_capabilities(self):
        active_id = db.get_workspace()["active_release_id"]
        detail = db.get_release_detail(active_id)
        changes = detail["diff"]["agent_changes"]
        self.assertEqual(len(changes), 3)
        self.assertEqual(
            set(changes[0]["capabilities"]),
            {"skills", "rag", "mcp_tools", "tools"},
        )
        self.assertIn("before", changes[0])
        self.assertIn("after", changes[0])

    def test_message_summary_exposes_exact_citation_and_three_token_types(self):
        run = db.prepare_run(None, "请依据知识回答")
        db.append_trace(run["run_id"], run["release_id"], "route_decision", {
            "target_agent": "general-service", "confidence": 0.9,
            "reason": "一般咨询匹配", "needs_clarification": False,
            "source": "deepseek_router",
        })
        db.append_trace(run["run_id"], run["release_id"], "agent_selected", {
            "agent_id": "general-service", "agent_name": "一般客服",
        })
        citation = "[RAG:测试知识#chunk_1]"
        db.append_trace(run["run_id"], run["release_id"], "rag_retrieval_completed", {
            "evidence": [{
                "document_id": "rag_test", "document_name": "测试知识",
                "rag_version_id": "ragv_test", "chunk_id": "chunk_1",
                "heading": "安全降级", "content": "失败时不得伪造结果。",
                "content_hash": "hash", "hybrid_score": 0.8,
                "citation": citation,
            }],
        })
        db.append_trace(run["run_id"], run["release_id"], "rag_citation_validation", {
            "allowed_citations": [citation], "used_citations": [citation],
            "removed_unknown_citations": [],
        })
        db.save_cloud_snap(run["run_id"], "main_agent", complete_snap("main-target1"))
        result = db.finish_run(
            run["run_id"], run["release_id"], run["conversation_id"],
            "general-service", f"不得伪造。{citation}", 1200,
        )
        db.append_trace(run["run_id"], run["release_id"], "assistant_response_completed", {
            "message_id": result["message_id"], "agent_id": "general-service",
            "agent_name": "一般客服", "content": f"不得伪造。{citation}",
        })
        db.save_run_evaluation(run["run_id"])
        messages = db.get_messages(run["conversation_id"])
        assistant = next(item for item in messages if item["role"] == "assistant")
        summary = assistant["capability_summary"]
        self.assertEqual(summary["rag"]["citations"][0]["content"], "失败时不得伪造结果。")
        self.assertEqual(summary["usage"]["prompt_cache_miss_tokens"], 10)
        self.assertEqual(summary["usage"]["prompt_cache_hit_tokens"], 2)
        self.assertEqual(summary["usage"]["completion_tokens"], 4)


if __name__ == "__main__":
    unittest.main()
