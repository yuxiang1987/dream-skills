"""Check that the shipped skills expose discoverable local resources.

Behavioral checks are the synthetic requests in each skill's tests/ directory;
these automated checks verify packaging, not editorial judgment.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
EDITORIAL_SKILLS = ("wechat-article-writing", "gzh-final-check")
SKILLS = EDITORIAL_SKILLS + ("gzh-daily-pipeline",)


class EditorialResourcesTest(unittest.TestCase):
    def test_local_markdown_links_resolve(self):
        for name in SKILLS:
            for page in (ROOT / name).rglob("*.md"):
                for target in re.findall(r"\]\(([^)]+)\)", page.read_text(encoding="utf-8")):
                    if "://" in target or target.startswith("#"):
                        continue
                    with self.subTest(page=page, target=target):
                        resource = (page.parent / target.split("#")[0]).resolve()
                        self.assertTrue(resource.is_relative_to((ROOT / name).resolve()),
                                        "Installed skills must not depend on external local files")
                        self.assertTrue(resource.is_file())

    def test_behavior_cases_are_discoverable(self):
        for name in SKILLS:
            folder = ROOT / name
            entry = (folder / "SKILL.md").read_text(encoding="utf-8")
            cases = list((folder / "tests").glob("*.md"))
            self.assertTrue(cases, name)
            for case in cases:
                with self.subTest(case=case):
                    self.assertIn(f"]({case.relative_to(folder).as_posix()})", entry)
                    self.assertTrue(case.read_text(encoding="utf-8").strip())

    def test_bilingual_indexes_link_both_skills(self):
        for index in ("README.md", "README.en.md"):
            content = (ROOT / index).read_text(encoding="utf-8")
            for name in EDITORIAL_SKILLS:
                with self.subTest(index=index, skill=name):
                    self.assertIn(f"]({name}/SKILL.md)", content)

    def test_bilingual_indexes_link_the_pipeline_skill(self):
        for index in ("README.md", "README.en.md"):
            content = (ROOT / index).read_text(encoding="utf-8")
            with self.subTest(index=index):
                self.assertIn("](gzh-daily-pipeline/SKILL.md)", content)

    def test_pipeline_templates_match_the_scaffold(self):
        """Every stage file the checker expects has a matching template."""
        templates = {path.name for path in (ROOT / "gzh-daily-pipeline" / "templates").glob("*.md")}
        script = (ROOT / "gzh-daily-pipeline" / "scripts" / "pipeline.py").read_text(encoding="utf-8")
        for name in ("00_style.md", "01_选题卡.md", "02_案例决策卡.md", "03_证据与实测.md",
                     "04_正文.md", "05_检查报告.md", "06_标题.md", "09_发布记录.md"):
            with self.subTest(template=name):
                self.assertIn(name, templates)
                self.assertIn(name, script)


if __name__ == "__main__":
    unittest.main()
