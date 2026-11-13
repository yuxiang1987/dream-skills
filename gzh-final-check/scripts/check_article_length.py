"""统计Markdown正文有效字数；只读，2500字及以上通过，未通过退出码为1。"""
import argparse
import json
from pathlib import Path
import re

MINIMUM = 2500
AUTHOR_BIO = '我是梦哥，十年程序员，爱折腾 AI。分享实用工具、有趣玩法和实操心得，一起把想法做出来。'
EXCLUDED_HEADINGS = {
    '参考资料', '参考来源', '参考链接', '资料来源', '参考文献', '延伸阅读',
    'references', 'reference', 'sources', 'source',
    '提示词', '完整提示词', '测试提示词', '可复制提示词', '提示词原文', 'prompt', 'prompts',
}
LINK = re.compile(r'(!?)\[([^\]\n]*)\]\((?:[^()\n]|\([^()\n]*\))*\)')


def body_text(source):
    source = source.lstrip('\ufeff')
    front = re.match(r'^---[ \t]*\n([\s\S]*?)\n(?:---|\.\.\.)[ \t]*(?:\n|$)', source)
    if front and re.search(r'^\w[\w-]*:', front[1], re.M):
        source = source[front.end():]
    source = re.sub(r'<!--[\s\S]*?-->', '', source)
    source = re.sub(r'<(script|style|pre)\b[^>]*>[\s\S]*?</\1>', '', source, flags=re.I)
    lines = source.splitlines()
    kept, fence, excluded_level = [], None, None
    for i, line in enumerate(lines):
        if fence:
            char, length = fence
            if re.fullmatch(rf' {{0,3}}{re.escape(char)}{{{length},}}[ \t]*', line):
                fence = None
            continue
        opening = re.match(r'^ {0,3}(`{3,}|~{3,})', line)
        if opening:
            fence = (opening[1][0], len(opening[1]))
            continue
        if re.match(r'^(?: {4}|\t| {0,3}>)', line):
            continue
        heading = re.match(r'^ {0,3}(#{1,6})\s+(.+?)\s*#*\s*$', line)
        setext = i+1 < len(lines) and re.fullmatch(r' {0,3}(?:={3,}|-{3,})\s*', lines[i+1]) and line.strip()
        plain_label = line.strip().rstrip('：:').casefold()
        if heading or setext or plain_label in EXCLUDED_HEADINGS:
            level = len(heading[1]) if heading else (1 if setext and '=' in lines[i+1] else 2)
            title = heading[2] if heading else line
            title = re.sub(r'[*_`]', '', title).strip().rstrip('：:').casefold()
            if excluded_level is not None and level <= excluded_level:
                excluded_level = None
            if title in EXCLUDED_HEADINGS:
                excluded_level = level
            continue
        if excluded_level is not None or re.match(r'^ {0,3}\[[^\]]+\]:', line):
            continue
        kept.append(line)
    text = '\n'.join(kept)
    text = re.sub(r'!\[\[[^\]]*\]\]', '', text)
    text = LINK.sub(lambda m: '' if m[1] else m[2], text)
    text = re.sub(r'\[\[([^\]|]+)(?:\|([^\]]+))?\]\]', lambda m: m[2] or m[1], text)
    text = re.sub(r'(`+)[\s\S]*?\1', '', text)
    text = re.sub(r'https?://[^\s<>，。；！？、：）)\]}」』]+', '', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'【(?:待插入|待补图|图片占位|视频占位)[^】]*】', '', text)
    text = re.sub(r'\[\^[^\]]+\]', '', text)
    text = re.sub(r'[*_~]', '', text)
    # 固定简介不参与2500字门槛；允许Markdown标记与普通空白差异。
    compact = re.sub(r'\s+', '', text)
    return compact.replace(re.sub(r'\s+', '', AUTHOR_BIO), '')


def check_length(source):
    count = sum(char.isalnum() for char in body_text(source))
    return {
        'body_characters': count,
        'minimum': MINIMUM,
        'passed': count >= MINIMUM,
        'shortfall': max(0, MINIMUM-count),
        'basis': '正文汉字、字母、数字各计1字；不计空白、标点、标题、图片/链接地址、代码/提示词、引用块、参考资料和固定简介',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('article', type=Path, help='UTF-8 Markdown统计稿，边界按Skill说明标明')
    args = parser.parse_args()
    result = check_length(args.article.read_text(encoding='utf-8-sig'))
    print(json.dumps({'file': str(args.article.resolve()), **result}, ensure_ascii=False, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
