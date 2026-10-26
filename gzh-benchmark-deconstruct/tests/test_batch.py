"""对标拆解批次脚本的回归测试。"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "batch.py"

RAW_SAMPLE = """---
title: "示例文章"
source: "https://mp.weixin.qq.com/s/example"
author:
  - "[[示例作者]]"
published:
created: 2026-10-07
description: ""
tags:
  - "clippings"
---
示例作者 示例作者 *2026年9月13日 12:29*

这是一篇示例原文。第一句可作为锚点。

第二句也是可逐字定位的片段，用来验证锚点检查。
"""

INDEX_TEMPLATE = """# 知识库索引

> 最近更新：2026-01-01

## 规模

- 知识页：0 页
- 原始资料：0 篇

## 来源

## 概念
"""

DIMENSION_PAGE = """---
title: 文章写法库
type: topic
tags: [公众号]
status: 稳定
sources: []
created: 2026-01-01
updated: 2026-01-01
---

# 文章写法库

原有内容。
"""


class BatchScriptTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "kb"
        (self.root / "raw" / "article" / "示例作者").mkdir(parents=True)
        (self.root / "raw" / "article" / "示例作者" / "示例文章.md").write_text(RAW_SAMPLE, encoding="utf-8")
        (self.root / "wiki" / "sources").mkdir(parents=True)
        (self.root / "wiki" / "topics").mkdir(parents=True)
        (self.root / "wiki" / "comparisons").mkdir(parents=True)
        (self.root / "wiki" / "index.md").write_text(INDEX_TEMPLATE, encoding="utf-8")
        (self.root / "wiki" / "log.md").write_text("# 操作日志\n", encoding="utf-8")
        (self.root / "wiki" / "topics" / "文章写法库.md").write_text(DIMENSION_PAGE, encoding="utf-8")
        self.batch = self.root / "output" / "ai-wechat-methodology" / "demo-batch"

    def tearDown(self):
        self.temp.cleanup()

    def run_script(self, *args, expect=0):
        command = [sys.executable, str(SCRIPT), "--root", str(self.root), *args]
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, expect,
                         f"命令失败：{' '.join(args)}\n{result.stdout}\n{result.stderr}")
        return result.stdout

    def init_batch(self):
        return self.run_script(
            "init", "--batch", str(self.batch),
            "--authors", "示例作者=EX", "--slug", "demo-batch",
            "--title", "示例批次", "--date", "2026-10-23",
            "--index-title", "示例批次拆解", "--comparison", "示例对比页",
        )

    def fill_batch(self, anchor="第一句可作为锚点"):
        manifest = json.loads((self.batch / "manifest.json").read_text(encoding="utf-8"))
        article = manifest["articles"][0]
        article.update({
            "title": "示例文章拆解",
            "source_page": "wiki/sources/示例文章拆解.md",
            "question": "示例文章回答了什么问题？",
            "primary_type": "实操测评",
            "primary_product": "示例产品",
            "evidence_role": "作者亲测",
            "own_idea": "自己用同一素材复现一次，待实操。",
        })
        (self.batch / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        analyses = {article["id"]: {
            "hook": "开头写法观察。",
            "structure": "结构写法观察。",
            "cases": "案例写法观察。",
            "ending": "结尾写法观察。",
            "boundary": "边界写法观察。",
            "learn": "可迁移写法观察。",
            "anchor_terms": [anchor, "第二句也是可逐字定位的片段"],
        }}
        (self.batch / "analyses.json").write_text(
            json.dumps(analyses, ensure_ascii=False, indent=2), encoding="utf-8")
        (self.batch / "topics").mkdir(parents=True, exist_ok=True)
        (self.batch / "topics" / "示例作者文章写法拆解.md").write_text(
            "---\ntitle: 示例作者文章写法拆解\ntype: topic\ntags: [公众号, 对标拆解]\n"
            "status: 进行中\nsources: []\ncreated: 2026-10-23\nupdated: 2026-10-23\n---\n\n"
            "# 示例作者文章写法拆解\n\n- [[sources/示例文章拆解]]\n",
            encoding="utf-8")
        (self.batch / "comparison.md").write_text(
            "---\ntitle: 示例对比页\ntype: comparison\ntags: [公众号, 对标拆解]\n"
            "status: 进行中\nsources: []\ncreated: 2026-10-23\nupdated: 2026-10-23\n---\n\n"
            "# 示例对比页\n\n- [[topics/示例作者文章写法拆解]]\n",
            encoding="utf-8")
        (self.batch / "dimensions.json").write_text(json.dumps([
            {"file": "文章写法库", "body": "## 示例批次：写法增量\n\n一条新增观察。"}
        ], ensure_ascii=False, indent=2), encoding="utf-8")

    def test_init_collects_hash_published_time_and_url(self):
        output = self.init_batch()
        self.assertIn("文章 1 篇", output)
        manifest = json.loads((self.batch / "manifest.json").read_text(encoding="utf-8"))
        article = manifest["articles"][0]
        self.assertEqual(article["id"], "EX-01")
        self.assertEqual(article["published_at"], "2026-09-13 12:29")
        self.assertEqual(article["original_url"], "https://mp.weixin.qq.com/s/example")
        self.assertEqual(len(article["raw_sha256"]), 64)
        self.assertFalse(article["media_reviewed"])
        self.assertIsNone(article["sponsor"])

    def test_init_refuses_to_overwrite_without_force(self):
        self.init_batch()
        self.run_script(
            "init", "--batch", str(self.batch), "--authors", "示例作者=EX",
            "--slug", "demo-batch", "--title", "示例批次", "--date", "2026-10-23",
            "--comparison", "示例对比页", expect=1)

    def test_build_then_check_passes(self):
        self.init_batch()
        self.fill_batch()
        self.run_script("build", "--batch", str(self.batch))
        page = (self.root / "wiki" / "sources" / "示例文章拆解.md").read_text(encoding="utf-8")
        self.assertIn("第一句可作为锚点", page)
        self.assertIn("待实操", page)
        index = (self.root / "wiki" / "index.md").read_text(encoding="utf-8")
        self.assertIn("[[sources/示例文章拆解]]", index)
        self.assertIn("知识页：", index)
        dimension = (self.root / "wiki" / "topics" / "文章写法库.md").read_text(encoding="utf-8")
        self.assertIn("## 示例批次：写法增量", dimension)
        self.run_script("check", "--batch", str(self.batch))

    def test_check_fails_when_raw_changed(self):
        self.init_batch()
        self.fill_batch()
        self.run_script("build", "--batch", str(self.batch))
        raw = self.root / "raw" / "article" / "示例作者" / "示例文章.md"
        raw.write_text(RAW_SAMPLE + "\n改动\n", encoding="utf-8")
        output = self.run_script("check", "--batch", str(self.batch), expect=1)
        self.assertIn("原文已变化", output)

    def test_check_fails_when_anchor_missing_in_source(self):
        self.init_batch()
        self.fill_batch(anchor="这句话不在原文里")
        self.run_script("build", "--batch", str(self.batch))
        output = self.run_script("check", "--batch", str(self.batch), expect=1)
        self.assertIn("锚点不在原文", output)

    def test_build_refuses_duplicate_dimension_section(self):
        self.init_batch()
        self.fill_batch()
        self.run_script("build", "--batch", str(self.batch))
        output = self.run_script("build", "--batch", str(self.batch), expect=1)
        self.assertIn("拒绝重复追加", output)

    def test_check_requires_pending_marker_in_own_idea(self):
        self.init_batch()
        self.fill_batch()
        manifest = json.loads((self.batch / "manifest.json").read_text(encoding="utf-8"))
        manifest["articles"][0]["own_idea"] = "自己也可以试试。"
        (self.batch / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        self.run_script("build", "--batch", str(self.batch))
        output = self.run_script("check", "--batch", str(self.batch), expect=1)
        self.assertIn("未标注待实操或待验证", output)


if __name__ == "__main__":
    unittest.main()
