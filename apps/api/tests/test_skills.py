import dataclasses
import tempfile
import unittest

from app import db, runtime


VALID_SKILL = {
    "name": "简洁答复规范",
    "description": "让一般客服先给结论，再列出核对依据。",
    "applicability": "用户提出一般咨询并希望快速得到明确答复时。",
    "non_applicability": "投诉和工单操作请求不适用。",
    "content": "先用一句话直接回答核心问题，再用不超过三点列出依据；无法确认的事实明确说明未知。",
    "output_requirements": "使用简洁中文，不补造没有证据的事实。",
}


class SkillReleaseTests(unittest.TestCase):
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

    def bind_skill(self, skill_id):
        agent = db.get_agent_config("general-service")
        return db.save_agent_config(
            agent["id"],
            {
                "name": agent["name"],
                "description": agent["description"],
                "system_prompt": agent["system_prompt"],
                "skill_ids": [skill_id],
                "rag_document_ids": agent["rag_document_ids"],
                "mcp_tool_bindings": agent["mcp_tool_bindings"],
                "tool_ids": agent["tool_ids"],
            },
        )

    def test_skill_requires_validation_and_release_before_prompt(self):
        skill = db.save_skill(VALID_SKILL)
        self.assertEqual(skill["status"], "DRAFT")
        before = db.prepare_run(None, "发布前消息")
        self.assertEqual(before["release_config"].get("skills", []), [])

        skill = db.validate_skill(skill["id"])
        self.assertEqual(skill["status"], "VALIDATED")
        still_before = db.prepare_run(before["conversation_id"], "候选前消息")
        self.assertEqual(still_before["release_config"].get("skills", []), [])
        self.bind_skill(skill["id"])

        candidate = db.create_candidate("V0.5.6-skill-test", "发布自然语言 Skill")
        candidate_detail = db.get_release_detail(candidate["id"])
        self.assertEqual(
            candidate_detail["config"]["skills"][0]["skill_version_id"],
            skill["current_version_id"],
        )
        after_candidate = db.prepare_run(before["conversation_id"], "仅创建候选")
        self.assertEqual(after_candidate["release_config"].get("skills", []), [])

        db.activate_release(candidate["id"])
        after_publish = db.prepare_run(before["conversation_id"], "发布后消息")
        released = runtime.released_skills(
            after_publish["release_config"], "general-service"
        )
        self.assertEqual(len(released), 1)
        self.assertIn("先用一句话", runtime.skill_prompt(released))
        self.assertEqual(before["release_id"], "rel_v055_default")
        self.assertNotEqual(after_publish["release_id"], before["release_id"])

    def test_edit_creates_immutable_version_and_active_snapshot_stays_old(self):
        first = db.validate_skill(db.save_skill(VALID_SKILL)["id"])
        self.bind_skill(first["id"])
        release_one = db.create_candidate("V0.5.6-skill-v1", "Skill v1")
        db.activate_release(release_one["id"])
        old_version_id = first["current_version_id"]

        changed = {**VALID_SKILL, "content": VALID_SKILL["content"] + " 最后给出下一步。"}
        second = db.save_skill(changed, first["id"])
        self.assertEqual(second["status"], "DRAFT")
        self.assertEqual(len(second["versions"]), 2)
        self.assertNotEqual(second["current_version_id"], old_version_id)
        active = db.get_release(release_one["id"])
        self.assertEqual(active["config"]["skills"][0]["skill_version_id"], old_version_id)

    def test_unbound_skill_validates_but_does_not_enter_release(self):
        payload = {
            **VALID_SKILL,
            "content": "raise RuntimeError('这只是自然语言正文，系统不得执行')；" + VALID_SKILL["content"],
        }
        skill = db.save_skill(payload)
        validated = db.validate_skill(skill["id"])
        self.assertEqual(validated["status"], "VALIDATED")
        self.assertEqual(validated["bound_agent_ids"], [])
        candidate = db.create_candidate("V0.5.9-unbound-skill", "unbound Skill")
        self.assertEqual(db.get_release(candidate["id"])["config"]["skills"], [])


if __name__ == "__main__":
    unittest.main()
