import dataclasses
import json
import tempfile
import unittest
from pathlib import Path

from app import db


SKILL = {
    "name": "Agent 装配测试 Skill",
    "description": "验证 Skill 与 Agent 的配置归属。",
    "applicability": "测试 Agent 装配时使用。",
    "non_applicability": "非测试场景不使用。",
    "content": "这是只作为自然语言执行说明保存的测试 Skill，必须从 Agent 页面装配后才能进入 Release。",
    "output_requirements": "只输出可验证的测试结论。",
}


class AgentConfigTests(unittest.TestCase):
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

    @staticmethod
    def payload(agent, **changes):
        values = {
            "name": agent["name"],
            "description": agent["description"],
            "system_prompt": agent["system_prompt"],
            "skill_ids": agent["skill_ids"],
            "rag_document_ids": agent["rag_document_ids"],
            "mcp_tool_bindings": agent["mcp_tool_bindings"],
            "tool_ids": agent["tool_ids"],
        }
        values.update(changes)
        return values

    def test_migration_six_initializes_three_agent_drafts(self):
        agents = db.list_agent_configs()
        self.assertEqual(
            [item["id"] for item in agents],
            ["general-service", "complaint-service", "work-order-service"],
        )
        with db.connection() as conn:
            versions = {
                row["version"]
                for row in conn.execute("SELECT version FROM schema_migrations")
            }
        self.assertIn(6, versions)
        self.assertTrue(all("mcp_tool_bindings" in item for item in agents))
        self.assertTrue(all(item["available_preset_tools"] == [] for item in agents))

    def test_agent_draft_is_binding_authority_and_does_not_change_active_release(self):
        skill = db.validate_skill(db.save_skill(SKILL)["id"])
        self.assertEqual(skill["status"], "VALIDATED")
        self.assertEqual(skill["bound_agent_ids"], [])
        active_before = db.get_workspace()["active_release_id"]

        agent = db.get_agent_config("general-service")
        saved = db.save_agent_config(
            agent["id"], self.payload(agent, skill_ids=[skill["id"]])
        )
        self.assertEqual(saved["skill_ids"], [skill["id"]])
        self.assertEqual(db.get_workspace()["active_release_id"], active_before)
        self.assertEqual(db.get_skill(skill["id"])["bound_agent_ids"], [agent["id"]])

        candidate = db.create_candidate(
            "V0.5.9-agent-authority", "Agent draft owns Skill binding"
        )
        detail = db.get_release_detail(candidate["id"])
        self.assertEqual(detail["config"]["skills"][0]["agent_ids"], [agent["id"]])
        self.assertIn(agent["id"], detail["diff"]["agent_bindings_changed"])

    def test_existing_release_binding_migrates_without_overwriting_history(self):
        skill = db.validate_skill(db.save_skill(SKILL)["id"])
        active_id = db.get_workspace()["active_release_id"]
        active = db.get_release(active_id)
        active["config"]["skills"] = [
            {
                "skill_id": skill["id"],
                "skill_version_id": skill["current_version_id"],
                "agent_ids": ["complaint-service"],
            }
        ]
        encoded = json.dumps(active["config"], ensure_ascii=False)
        with db.connection() as conn:
            conn.execute("UPDATE releases SET config_json=? WHERE id=?", (encoded, active_id))
            conn.execute("DELETE FROM agent_configs")
            db._ensure_agent_configs(conn)
        complaint = db.get_agent_config("complaint-service")
        self.assertEqual(complaint["skill_ids"], [skill["id"]])
        self.assertEqual(db.get_release(active_id)["config"]["skills"][0]["agent_ids"], ["complaint-service"])

    def test_mcp_is_bound_per_tool_and_invalid_tools_are_rejected(self):
        server = db.save_mcp_server(
            {
                "name": "Agent Tool Test MCP",
                "git_url": "https://github.com/example/mcp",
                "version_ref": "commit-1",
                "endpoint": "http://127.0.0.1:9999/mcp",
                "transport": "STREAMABLE_HTTP",
                "auth_type": "NONE",
                "allowed_tools": ["read_one", "read_two"],
                "declared_read_only_tools": ["read_one", "read_two"],
                "runtime_config": {"activation_keywords": ["read"]},
            }
        )
        tools = [
            {"name": "read_one", "allowed": True, "input_schema": {"type": "object"}},
            {"name": "read_two", "allowed": True, "input_schema": {"type": "object"}},
        ]
        with db.connection() as conn:
            conn.execute(
                "UPDATE mcp_servers SET status='CONNECTED', tools_json=? WHERE id=?",
                (json.dumps(tools), server["id"]),
            )

        general = db.get_agent_config("general-service")
        complaint = db.get_agent_config("complaint-service")
        db.save_agent_config(
            general["id"],
            self.payload(
                general,
                mcp_tool_bindings=[
                    {"server_id": server["id"], "tool_name": "read_one"}
                ],
            ),
        )
        db.save_agent_config(
            complaint["id"],
            self.payload(
                complaint,
                mcp_tool_bindings=[
                    {"server_id": server["id"], "tool_name": "read_two"}
                ],
            ),
        )
        candidate = db.create_candidate("V0.5.9-tool-granularity", "per Tool binding")
        released = db.get_release(candidate["id"])["config"]["mcp"][0]
        self.assertEqual(released["tool_agent_ids"]["read_one"], ["general-service"])
        self.assertEqual(released["tool_agent_ids"]["read_two"], ["complaint-service"])

        with self.assertRaises(ValueError):
            db.save_agent_config(
                general["id"],
                self.payload(
                    general,
                    mcp_tool_bindings=[
                        {"server_id": server["id"], "tool_name": "delete_everything"}
                    ],
                ),
            )

    def test_resource_forms_do_not_edit_agent_bindings(self):
        candidates = [
            Path(__file__).resolve().parents[1] / "static" / "app.js",
            Path(__file__).resolve().parents[2] / "web" / "static" / "app.js",
        ]
        source_path = next(path for path in candidates if path.exists())
        source = source_path.read_text(encoding="utf-8")
        self.assertIn('id="agent-form"', source)
        self.assertIn('name="mcp_tool_bindings"', source)
        self.assertNotIn('name="agent_ids"', source)
        self.assertNotIn('getAll("agent_ids")', source)


if __name__ == "__main__":
    unittest.main()
