"""校验流水线脚手架与交接契约检查器。"""

import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_ROOT / "scripts" / "pipeline.py"


def run(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )


class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "pipeline"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---------- init ----------

    def test_init_creates_run_directory_with_templates(self):
        result = run("init", "--root", str(self.root), "--date", "2026-10-23", "--slug", "豆包双11")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        run_dir = self.root / "2026-10-23-豆包双11"
        self.assertTrue(run_dir.is_dir())
        for name in ("00_style.md", "01_选题卡.md", "02_案例决策卡.md", "03_证据与实测.md",
                     "04_正文.md", "05_检查报告.md", "06_标题.md", "09_发布记录.md"):
            self.assertTrue((run_dir / name).is_file(), name)
        text = (run_dir / "00_style.md").read_text(encoding="utf-8")
        self.assertIn("created: 2026-10-23", text)
        self.assertNotIn("{{日期}}", text)

    def test_init_refuses_to_overwrite_existing_directory(self):
        first = run("init", "--root", str(self.root), "--date", "2026-10-23", "--slug", "选题")
        self.assertEqual(first.returncode, 0)
        second = run("init", "--root", str(self.root), "--date", "2026-10-23", "--slug", "选题")
        self.assertEqual(second.returncode, 1)
        self.assertIn("不覆盖", second.stdout)

    def test_init_rejects_bad_date(self):
        result = run("init", "--root", str(self.root), "--date", "2026/10/23", "--slug", "选题")
        self.assertEqual(result.returncode, 1)
        self.assertIn("YYYY-MM-DD", result.stdout)

    def test_init_reuses_shared_constitution(self):
        self.root.mkdir(parents=True)
        (self.root / "00_style.md").write_text("---\nstage: S0 定盘\n---\n共享宪法\n", encoding="utf-8")
        result = run("init", "--root", str(self.root), "--date", "2026-10-23", "--slug", "选题")
        self.assertEqual(result.returncode, 0)
        copied = (self.root / "2026-10-23-选题" / "00_style.md").read_text(encoding="utf-8")
        self.assertIn("共享宪法", copied)

    # ---------- check ----------

    def _fresh_run(self):
        run("init", "--root", str(self.root), "--date", "2026-10-23", "--slug", "选题")
        return self.root / "2026-10-23-选题"

    def _rewrite(self, path: Path, **fields):
        text = path.read_text(encoding="utf-8")
        match = re.match(r"\A---\n(.*?)\n---\n", text, re.S)
        front = dict(re.findall(r"^(\w+):\s*(.*)$", match.group(1), re.M))
        front.update(fields)
        block = "\n".join(f"{key}: {value}" for key, value in front.items())
        path.write_text(match.group(0).replace(match.group(1), block) + text[match.end():], encoding="utf-8")

    def _fill(self, path: Path):
        text = path.read_text(encoding="utf-8")
        path.write_text(re.sub(r"\{\{[^{}]+\}\}", "已填写", text), encoding="utf-8")

    def test_check_passes_on_fresh_run(self):
        run_dir = self._fresh_run()
        result = run("check", "--dir", str(run_dir))
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("交接校验通过", result.stdout)

    def test_check_reports_missing_file(self):
        run_dir = self._fresh_run()
        (run_dir / "01_选题卡.md").unlink()
        result = run("check", "--dir", str(run_dir))
        self.assertEqual(result.returncode, 1)
        self.assertIn("01_选题卡.md：缺少文件", result.stdout)

    def test_check_reports_invalid_status(self):
        run_dir = self._fresh_run()
        self._rewrite(run_dir / "01_选题卡.md", status="完成了")
        result = run("check", "--dir", str(run_dir))
        self.assertEqual(result.returncode, 1)
        self.assertIn("status 取值不合法", result.stdout)

    def test_check_reports_missing_frontmatter_field(self):
        run_dir = self._fresh_run()
        path = run_dir / "01_选题卡.md"
        text = path.read_text(encoding="utf-8")
        path.write_text(text.replace("source_skill: gzh-topic-planning\n", "", 1), encoding="utf-8")
        result = run("check", "--dir", str(run_dir))
        self.assertEqual(result.returncode, 1)
        self.assertIn("缺少字段 source_skill", result.stdout)

    def test_check_reports_stage_order_violation(self):
        run_dir = self._fresh_run()
        self._rewrite(run_dir / "04_正文.md", status="已确认")
        result = run("check", "--dir", str(run_dir))
        self.assertEqual(result.returncode, 1)
        self.assertIn("前置阶段", result.stdout)

    def test_check_reports_placeholder_left_in_confirmed_stage(self):
        run_dir = self._fresh_run()
        for name in ("00_style.md", "01_选题卡.md"):
            self._rewrite(run_dir / name, status="已确认")
        result = run("check", "--dir", str(run_dir))
        self.assertEqual(result.returncode, 1)
        self.assertIn("还留着占位符", result.stdout)

    def test_check_blocks_body_without_measurement_record(self):
        run_dir = self._fresh_run()
        for name in ("00_style.md", "01_选题卡.md", "02_案例决策卡.md"):
            self._rewrite(run_dir / name, status="已确认")
        self._rewrite(run_dir / "03_证据与实测.md", status="已确认")
        self._rewrite(run_dir / "04_正文.md", status="已确认")
        result = run("check", "--dir", str(run_dir))
        self.assertEqual(result.returncode, 1)
        self.assertIn("缺实测记录", result.stdout)

    def test_check_allows_body_after_measurement_filled(self):
        run_dir = self._fresh_run()
        for name in ("00_style.md", "01_选题卡.md", "02_案例决策卡.md", "03_证据与实测.md"):
            self._rewrite(run_dir / name, status="已确认")
            self._fill(run_dir / name)
        self._rewrite(run_dir / "04_正文.md", status="已确认")
        self._fill(run_dir / "04_正文.md")
        result = run("check", "--dir", str(run_dir))
        self.assertNotIn("缺实测记录", result.stdout)

    def test_check_blocks_unresolved_review_items(self):
        run_dir = self._fresh_run()
        for name in ("00_style.md", "01_选题卡.md", "02_案例决策卡.md", "03_证据与实测.md", "04_正文.md"):
            self._rewrite(run_dir / name, status="已确认")
            self._fill(run_dir / name)
        report = run_dir / "05_检查报告.md"
        self._rewrite(report, status="已确认")
        self._fill(report)
        result = run("check", "--dir", str(run_dir))
        self.assertEqual(result.returncode, 1)
        self.assertIn("必须修改还有", result.stdout)

    def test_check_requires_cover_after_title_confirmed(self):
        run_dir = self._fresh_run()
        for name in ("00_style.md", "01_选题卡.md", "02_案例决策卡.md", "03_证据与实测.md", "04_正文.md"):
            self._rewrite(run_dir / name, status="已确认")
            self._fill(run_dir / name)
        report = run_dir / "05_检查报告.md"
        self._rewrite(report, status="已确认")
        self._fill(report)
        title = run_dir / "06_标题.md"
        self._rewrite(title, status="已确认")
        self._fill(title)
        result = run("check", "--dir", str(run_dir))
        self.assertEqual(result.returncode, 1)
        self.assertIn("缺少 07_封面.png", result.stdout)

    # ---------- status ----------

    def test_status_reports_next_gate(self):
        run_dir = self._fresh_run()
        result = run("status", "--dir", str(run_dir))
        self.assertEqual(result.returncode, 0)
        self.assertIn("下一个关口", result.stdout)
        self.assertIn("S0 定盘", result.stdout)


if __name__ == "__main__":
    unittest.main()
