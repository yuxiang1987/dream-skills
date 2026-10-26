"""对标雷达脚本的离线回归测试：不发任何网络请求。"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ingest.py"

RAW_ONE = """---
title: "示例文章甲"
source: "https://mp.weixin.qq.com/s/example-a"
account: "示例号"
account_username: "gh_test01"
published: "2026-10-01 10:00"
---

正文略。
"""

RAW_TWO = """---
title: "示例文章乙"
source: "https://mp.weixin.qq.com/s/example-b"
account: "示例号"
account_username: "gh_test01"
published: "2026-10-02 10:00"
---

正文略。
"""

SOURCE_PAGE = """---
title: 示例文章甲拆解
type: source
status: 稳定
sources: ["raw/article/示例号/a.md"]
created: 2026-10-03
updated: 2026-10-03
---

示例。
"""

ACCOUNTS = {"accounts": [{"name": "示例号", "username": "gh_test01"}]}


class RadarTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "kb"
        folder = self.root / "raw" / "article" / "示例号"
        folder.mkdir(parents=True)
        (folder / "a.md").write_text(RAW_ONE, encoding="utf-8")
        (folder / "b.md").write_text(RAW_TWO, encoding="utf-8")
        (self.root / "wiki" / "sources").mkdir(parents=True)
        (self.root / "wiki" / "sources" / "甲拆解.md").write_text(SOURCE_PAGE, encoding="utf-8")
        self.accounts = self.root / "accounts.json"
        self.accounts.write_text(json.dumps(ACCOUNTS, ensure_ascii=False), encoding="utf-8")
        self.batch = self.root / "output" / "batch"
        self.batch.mkdir(parents=True)
        (self.batch / "manifest.json").write_text(json.dumps({
            "accounts": [{"requested_name": "示例号", "articles": [
                {"id": "1:1", "title": "甲", "url": "https://mp.weixin.qq.com/s/example-a",
                 "published": "2026-10-01 10:00", "list_create_time": 1790000000,
                 "primary_product": "示例产品 A"},
                {"id": "2:1", "title": "乙", "url": "https://mp.weixin.qq.com/s/example-b",
                 "published": "2026-10-02 10:00", "list_create_time": 1790100000,
                 "primary_product": "示例产品 A"}]}]}, ensure_ascii=False), encoding="utf-8")
        (self.batch / "stats-2026-10-26").mkdir()
        stats = [
            {"account": "示例号", "id": "1:1", "title": "甲", "read_num": 1000, "like_count": 10,
             "share_count": 5, "comment_count": 1},
            {"account": "示例号", "id": "2:1", "title": "乙", "read_num": 6000, "like_count": 60,
             "share_count": 50, "comment_count": 9},
            {"account": "另一个号", "id": "3:1", "title": "丙", "error": "HTTP 400"},
        ]
        (self.batch / "stats-2026-10-26" / "all-stats.json").write_text(
            json.dumps(stats, ensure_ascii=False), encoding="utf-8")
        (self.batch / "stats-2026-10-26" / "baseline.json").write_text(json.dumps([
            {"account": "示例号", "n": 2, "median": 3500, "min": 1000, "max": 6000,
             "median_like": 35, "median_share": 27, "median_comment": 5}], ensure_ascii=False),
            encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def run_script(self, *args, expect=0):
        result = subprocess.run([sys.executable, str(SCRIPT), "--root", str(self.root), *args],
                                capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, expect, result.stdout + result.stderr)
        return result.stdout

    def test_plan_separates_indexed_from_pending(self):
        output = self.run_script("plan", "--accounts", str(self.accounts), "--show", "5")
        self.assertIn("原文 2，已入库 1，未入库 1", output)
        self.assertIn("b.md", output)

    def test_dry_run_sends_no_request(self):
        output = self.run_script("fetch", "--accounts", str(self.accounts), "--dry-run")
        self.assertIn("不发请求", output)
        self.assertFalse((self.root / "output" / "ai-wechat-methodology").exists())

    def test_fetch_without_credential_fails_clearly(self):
        output = self.run_script("fetch", "--accounts", str(self.accounts), expect=1)
        self.assertIn("凭据", output)

    def test_report_flags_anomaly_cluster_and_pending(self):
        self.run_script("report", "--batch", str(self.batch), "--threshold", "1.5")
        report = json.loads((self.batch / "report.json").read_text(encoding="utf-8"))
        self.assertEqual([row["title"] for row in report["anomalies"]], ["乙"])
        self.assertGreater(report["anomalies"][0]["ratio"], 1.7)
        self.assertEqual(report["event_clusters"], [], "单账号不算跨账号事件簇")
        self.assertEqual(report["raw_without_source"], ["raw/article/示例号/b.md"])

    def test_case_candidates_surface_measured_articles(self):
        folder = self.root / "raw" / "article" / "示例号"
        (folder / "c.md").write_text("""---
title: "示例实测文"
source: "https://mp.weixin.qq.com/s/example-c"
account: "示例号"
account_username: "gh_test01"
---

我实测了 Kimi 和 Claude。第一步先让模型读需求，然后我改了两次提示词，再让它在 Codex 里跑通，
对比两轮结果，测试了输入规格与验收点是否一致。
""", encoding="utf-8")
        self.run_script("report", "--batch", str(self.batch), "--threshold", "1.5")
        report = json.loads((self.batch / "report.json").read_text(encoding="utf-8"))
        cases = {item["article"]: item for item in report["case_candidates"]}
        self.assertIn("示例实测文", cases)
        self.assertEqual(cases["示例实测文"]["status"], "待填写")
        self.assertIn("Kimi", cases["示例实测文"]["models"])
        self.assertEqual(cases["示例实测文"]["angle"], "", "角度必须留空待填，脚本不代写结论")
        self.assertNotIn("示例文章甲", cases, "无实测信号的文章不应生成案例卡")

    def test_daily_without_new_articles_still_writes_briefing(self):
        fetch_summary = {"acquired_at": "2026-10-26T09:30:00+08:00", "accounts": [
            {"account": "示例号", "username": "gh_test01", "fetched": 0, "added": 0,
             "skipped_existing": 0, "failed": 0, "directory": "raw/article/示例号", "added_articles": []}]}
        (self.batch / "fetch-summary.json").write_text(json.dumps(fetch_summary, ensure_ascii=False),
                                                       encoding="utf-8")
        result = subprocess.run([sys.executable, str(SCRIPT), "--root", str(self.root), "daily",
                                 "--accounts", str(self.accounts), "--date", "2026-10-26",
                                 "--batch", str(self.batch)], capture_output=True, text=True, encoding="utf-8")
        self.assertIn("未找到凭据", result.stdout + result.stderr, "无凭据时应明确报错而非静默")
        briefing = self.batch / "雷达简报-2026-10-26.md"
        self.assertFalse(briefing.exists(), "采集未成功时不应生成像样的简报")

    def test_cluster_requires_two_accounts(self):
        self.run_script("report", "--batch", str(self.batch), "--threshold", "1.5")
        report = json.loads((self.batch / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["event_clusters"], [], "单账号不应形成跨账号事件簇")


if __name__ == "__main__":
    unittest.main()
