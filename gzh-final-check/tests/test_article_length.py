"""最小字数边界、统计排除项和只读CLI；不代替写作质量/行为评审。"""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/check_article_length.py'
spec = importlib.util.spec_from_file_location('article_length', SCRIPT)
counter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(counter)


class ArticleLengthTest(unittest.TestCase):
    def test_exact_boundary_and_shortfall(self):
        for count in [0, 2499, 2500, 2501]:
            with self.subTest(count=count):
                result = counter.check_length('文'*count)
                self.assertEqual(result['body_characters'], count)
                self.assertEqual(result['passed'], count >= 2500)
                self.assertEqual(result['shortfall'], max(0, 2500-count))

    def test_characters_not_punctuation_or_spaces(self):
        self.assertEqual(counter.check_length('中 文 AI 2.6，。！？\n')['body_characters'], 6)

    def test_titles_metadata_media_urls_code_and_quotes_do_not_pad(self):
        noise = '''---
title: 不计标题
tags: [不计元数据]
---
# 不计文章标题
## 不计章节标题
```prompt
不计提示词
```
~~~python
print('不计代码')
~~~
    不计缩进代码
> 不计引用块
![不计图片说明](nested(1).png)
![[不计图片.png|不计别名]]
`不计行内代码`
<!-- 不计注释 -->
[ref]: https://example.com/ignored
【待插入：不计视频占位】
'''
        self.assertEqual(counter.check_length(noise+'\n'+'文'*2499)['body_characters'], 2499)

    def test_visible_link_label_counts_without_target_and_url_keeps_following_sentence(self):
        source = '[可见文字](https://example.com/nested(1))\n访问 https://example.com。继续\n[[页面|别名]]'
        self.assertEqual(counter.check_length(source)['body_characters'], 10)

    def test_reference_and_prompt_sections_end_at_peer_heading(self):
        source = '正文\n## 参考资料\n不计来源\n### 来源细节\n仍不计\n## 正文继续\n继续\n## 提示词\n不计提示词\n## 结果\n结果'
        self.assertEqual(counter.check_length(source)['body_characters'], 6)

    def test_intro_bio_and_unclosed_code_cannot_pass_threshold(self):
        source = '文'*2499+'\n\n'+counter.AUTHOR_BIO+'\n\n```\n'+'字'*3000
        self.assertFalse(counter.check_length(source)['passed'])
        self.assertEqual(counter.check_length(source)['body_characters'], 2499)

    def test_setext_headings_and_plain_reference_label(self):
        source = '不计标题\n===\n正文\n参考资料：\n不计来源'
        self.assertEqual(counter.check_length(source)['body_characters'], 2)

    def test_read_only_cli_returns_measured_result_and_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            article = Path(tmp) / '稿件.md'
            for count, status in [(2499, 1), (2500, 0)]:
                data = ('# 标题\n\n'+'文'*count).encode('utf8')
                article.write_bytes(data)
                process = subprocess.run([sys.executable, '-X', 'utf8', str(SCRIPT), str(article)], capture_output=True, text=True, encoding='utf8')
                self.assertEqual(process.returncode, status, process.stderr)
                self.assertEqual(json.loads(process.stdout)['body_characters'], count)
                self.assertEqual(article.read_bytes(), data)


if __name__ == '__main__':
    unittest.main()
