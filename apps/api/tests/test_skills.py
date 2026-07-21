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
    "agent_ids": ["general-service"],
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

    def test_skill_requires_validation_and_release_before_prompt(self):
        skill = db.save_skill(VALID_SKILL)
        self.assertEqual(skill["status"], "DRAFT")
        before = db.prepare_run(None, "发布前消息")
        self.assertEqual(before["release_config"].get("skills", []), [])

        skill = db.validate_skill(skill["id"])
        self.assertEqual(skill["status"], "VALIDATED")
        still_before = db.prepare_run(before["conversation_id"], "候选前消息")
        self.assertEqual(still_before["release_config"].get("skills", []), [])

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

    def test_unbound_skill_fails_validation_and_text_is_never_executed(self):
        payload = {
            **VALID_SKILL,
            "content": "raise RuntimeError('这只是自然语言正文，系统不得执行')；" + VALID_SKILL["content"],
            "agent_ids": [],
        }
        skill = db.save_skill(payload)
        validated = db.validate_skill(skill["id"])
        self.assertEqual(validated["status"], "DRAFT")
        self.assertTrue(any("至少绑定" in item for item in validated["validation_errors"]))


if __name__ == "__main__":
    unittest.main()
