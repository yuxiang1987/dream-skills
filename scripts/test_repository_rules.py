"""Validate mandatory delivery rules in the repository instructions."""
from pathlib import Path
import unittest


class RepositoryRulesTest(unittest.TestCase):
    def test_delivery_rules(self):
        text = (Path(__file__).resolve().parents[1] / "AGENTS.md").read_text(encoding="utf-8-sig")
        self.assertIn("每次改动完成后，都必须创建一个对应的 Git Commit", text)
        self.assertIn("每次改动后，都必须编写和更新相关测试", text)
        self.assertIn("确保所有测试和验证都全部通过", text)


if __name__ == "__main__":
    unittest.main()
