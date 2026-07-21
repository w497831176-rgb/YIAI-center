import dataclasses
import os
import tempfile
import unittest
from pathlib import Path

from app import db
from app.git_skill_import import GitSkillImportError, parse_github_url, scan_directory


class GitSkillImportTests(unittest.TestCase):
    def test_parse_public_github_tree_url(self):
        result = parse_github_url(
            "https://github.com/example/repository/tree/main/skills/plain"
        )
        self.assertEqual(result["repo_url"], "https://github.com/example/repository")
        self.assertEqual(result["ref"], "main")
        self.assertEqual(result["subpath"], "skills/plain")

    def test_url_with_credentials_is_rejected(self):
        with self.assertRaises(GitSkillImportError):
            parse_github_url("https://token@github.com/example/repository")

    def test_plain_text_skill_passes_without_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "SKILL.md").write_text(
                "# Safe Skill\n\nUse evidence and state unknown facts clearly.",
                encoding="utf-8",
            )
            result = scan_directory(root)
            self.assertEqual(result["findings"], [])
            self.assertEqual(result["skill_path"], "SKILL.md")

    def test_scripts_directory_and_executable_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "SKILL.md").write_text("# Unsafe Skill", encoding="utf-8")
            scripts = root / "scripts"
            scripts.mkdir()
            executable = scripts / "run.py"
            executable.write_text("raise SystemExit('must not run')", encoding="utf-8")
            os.chmod(executable, 0o755)
            result = scan_directory(root)
            self.assertTrue(any("scripts 目录" in item for item in result["findings"]))
            self.assertTrue(any("脚本扩展名" in item for item in result["findings"]))

    def test_import_attempt_and_git_provenance_are_persisted(self):
        original_settings = db.settings
        with tempfile.TemporaryDirectory() as directory:
            db.settings = dataclasses.replace(
                original_settings, db_path=f"{directory}/test.sqlite"
            )
            try:
                db.init_db()
                payload = {
                    "name": "Imported Draft",
                    "description": "Git import",
                    "applicability": "Review before use",
                    "non_applicability": "Not published",
                    "content": "# Imported\n\nThis is enough immutable text for a draft Skill.",
                    "output_requirements": "Use only verified facts.",
                    "agent_ids": [],
                }
                source = {
                    "repo_url": "https://github.com/example/repository",
                    "commit_sha": "a" * 40,
                    "skill_path": "SKILL.md",
                    "file_list": ["SKILL.md"],
                    "findings": [],
                }
                skill = db.save_skill(payload, source_type="GIT", source=source)
                attempt = db.save_skill_import_attempt(
                    repo_url=source["repo_url"],
                    commit_sha=source["commit_sha"],
                    skill_path="SKILL.md",
                    status="IMPORTED",
                    file_list=["SKILL.md"],
                    findings=[],
                    reason=None,
                    skill_id=skill["id"],
                )
                self.assertEqual(skill["status"], "DRAFT")
                self.assertEqual(skill["agent_ids"], [])
                self.assertEqual(skill["current_version"]["source_type"], "GIT")
                self.assertEqual(attempt["commit_sha"], "a" * 40)
                self.assertNotIn(directory, str(attempt))
            finally:
                db.settings = original_settings


if __name__ == "__main__":
    unittest.main()
