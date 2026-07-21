import dataclasses
import tempfile
import unittest

from app import db, rag


DOCUMENT = """# 账户访问与身份核验

当使用者无法进入账号时，服务人员先确认登录标识是否准确，再核对最近一次成功登录时间。不得索要明文密码。需要重置密码时，只能引导使用正式验证流程，并说明验证码的有效期和失败后的重新申请方式。身份核验没有通过时，不得透露账号资料、历史记录或联系方式。

若连续多次尝试失败，应提示暂时停止重复提交，检查键盘状态、网络连接和登录入口。记录故障时间、客户端类型与可见错误码，便于后续排查。任何人工协助都要保留处理编号和下一步预计时间。

# 服务预约与变更

预约服务时应确认服务项目、期望日期、可联系时间段与必要的准备事项。预约尚未确认前，不得声称已经安排完成。需要改期时，先核对原预约编号，再提供可选时间；取消时应说明影响范围，并让使用者确认是否继续。

服务人员只能记录完成本次预约所需的信息。没有明确授权时，不得扩大信息用途。若资源暂时不可用，应给出候补方案或再次查询的时间点，不得虚构空余名额。

# 争议与升级处理

出现争议时，先复述事实和使用者诉求，区分已经核实的信息、等待核实的信息和主观感受。一般问题由当前服务人员处理；涉及权限、费用争议或多次处理无果时，升级到指定角色，并记录升级原因、证据和期待结果。

升级不等于已经解决。对外回答应说明当前状态、责任角色、预计反馈时间和查询方式。后续结果必须来自真实处理记录；如果没有新进展，就明确说明仍在处理中。
"""


class RagTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.original_settings = db.settings
        db.settings = dataclasses.replace(
            self.original_settings, db_path=f"{self.directory.name}/test.sqlite"
        )
        db.init_db()

    def tearDown(self):
        db.settings = self.original_settings
        self.directory.cleanup()

    def payload(self):
        return {
            "name": "通用服务规则",
            "tags": ["服务", "规则"],
            "version_note": "首版真实混合检索演示",
            "content": DOCUMENT,
        }

    def bind_document(self, document_id):
        agent = db.get_agent_config("general-service")
        db.save_agent_config(
            agent["id"],
            {
                "name": agent["name"],
                "description": agent["description"],
                "system_prompt": agent["system_prompt"],
                "skill_ids": agent["skill_ids"],
                "rag_document_ids": [document_id],
                "mcp_tool_bindings": agent["mcp_tool_bindings"],
                "tool_ids": agent["tool_ids"],
            },
        )

    def test_preview_is_deterministic_and_discloses_real_technology(self):
        first = rag.preview_document(DOCUMENT)
        second = rag.preview_document(DOCUMENT)
        self.assertEqual(first["chunks"], second["chunks"])
        self.assertGreaterEqual(first["chunk_count"], 3)
        self.assertEqual(first["keyword_engine"], "sqlite-fts5-bm25")
        self.assertEqual(first["embedding_model"], "local-tfidf-lsa-v1")

    def test_keyword_vector_and_hybrid_rank_relevant_chunk(self):
        document = rag.save_document(self.payload())
        version_id = document["current_version_id"]
        result = rag.retrieve(version_id, "登录失败后怎样重置密码并完成身份核验？")
        self.assertTrue(result["keyword_results"])
        self.assertTrue(result["vector_results"])
        self.assertTrue(result["hybrid_results"])
        self.assertEqual(result["hybrid_results"][0]["heading"], "账户访问与身份核验")
        self.assertIsInstance(result["hybrid_results"][0]["keyword_score"], float)
        self.assertIsInstance(result["hybrid_results"][0]["vector_score"], float)

    def test_out_of_vocabulary_query_returns_no_evidence_or_fake_citation(self):
        document = rag.save_document(self.payload())
        result = rag.retrieve(document["current_version_id"], "zzqv987654321")
        self.assertEqual(result["keyword_results"], [])
        self.assertEqual(result["vector_results"], [])
        self.assertEqual(result["hybrid_results"], [])
        answer, used, removed = rag.sanitize_citations(
            "没有证据 [RAG:虚构文档#fake]", []
        )
        self.assertNotIn("fake", answer)
        self.assertEqual(used, [])
        self.assertEqual(removed, ["[RAG:虚构文档#fake]"])

    def test_validated_binding_only_enters_new_release(self):
        document = rag.save_document(self.payload())
        before = db.prepare_run(None, "发布前")
        self.assertEqual(before["release_config"].get("rag", []), [])
        validated = rag.validate_document(document["id"])
        self.assertEqual(validated["status"], "VALIDATED")
        self.bind_document(document["id"])
        candidate = db.create_candidate("V0.5.8-rag-test", "发布真实混合检索")
        detail = db.get_release_detail(candidate["id"])
        self.assertEqual(detail["config"]["rag"][0]["rag_version_id"], document["current_version_id"])
        self.assertIn(document["current_version_id"], detail["diff"]["rag_added"])
        db.activate_release(candidate["id"])
        after = db.prepare_run(before["conversation_id"], "发布后")
        result = rag.retrieve_release(after["release_config"], "general-service", "重置密码")
        self.assertGreater(result["published_binding_count"], 0)
        self.assertTrue(result["evidence"])
        self.assertNotEqual(before["release_id"], after["release_id"])


if __name__ == "__main__":
    unittest.main()
