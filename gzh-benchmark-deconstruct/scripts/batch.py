#!/usr/bin/env python3
"""公众号对标文章拆解批次工具：init / build / check。

批次工作区结构：

    <batch>/
      manifest.json      批次清单：作者、文章元数据、原文哈希
      analyses.json      逐篇六维拆解与原文定位锚点
      topics/*.md        作者写法拆解页（含 frontmatter）
      comparison.md      跨作者对比页（含 frontmatter）
      dimensions.json    维度库追加段落

init   扫描 raw/article/<作者>/*.md，生成批次清单骨架。
build  依据清单与分析生成知识库页面，并更新索引、维度库与日志。
check  校验批次产物：覆盖、哈希、锚点、边界声明、索引与计数。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

GLOSSARY = (
    "Agent指能调用工具推进任务的AI系统，Harness指模型调用工具及管理执行的环境，"
    "Skill指可复用的任务指导与资源。"
)
REQUIRED_FRONTMATTER = ("title", "type", "status", "sources", "created", "updated")
BOUNDARY_MARKERS = ("图片、动图和视频未核看", "未独立核实")
PUBLISHED_RE = re.compile(r"\*(\d{4})年(\d{1,2})月(\d{1,2})日 (\d{2}:\d{2})\*")
SOURCE_URL_RE = re.compile(r'^source:\s*"([^"]+)"', re.M)
FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.S)
NO_DIRECT_LINK = "本文件未记录原文直链；正文互链不自动视为本篇地址。"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def parse_frontmatter(text: str):
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    data = {}
    for line in match.group(1).splitlines():
        if ":" not in line or line.strip().startswith("#"):
            continue
        key, _, value = line.partition(":")
        data[key.strip()] = value.strip()
    return data, text[match.end():]


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def published_at_of(text: str):
    match = PUBLISHED_RE.search(text)
    if not match:
        return None
    year, month, day, clock = match.groups()
    return f"{year}-{int(month):02d}-{int(day):02d} {clock}"


def source_url_of(text: str):
    match = SOURCE_URL_RE.search(text)
    return match.group(1) if match else None


def parse_author_spec(spec: str):
    """`苍何=CH` 形式的作者声明；不写前缀时按序号生成。"""
    name, _, prefix = spec.partition("=")
    return name.strip(), (prefix.strip() or None)


def cmd_init(args) -> int:
    root = Path(args.root).resolve()
    batch_dir = Path(args.batch).resolve()
    manifest_path = batch_dir / "manifest.json"
    if manifest_path.exists() and not args.force:
        print(f"[跳过] 批次清单已存在：{manifest_path}")
        return 1

    authors = []
    articles = []
    for index, spec in enumerate(args.authors.split(","), start=1):
        name, prefix = parse_author_spec(spec)
        prefix = prefix or f"A{index:02d}"
        authors.append({"name": name, "prefix": prefix,
                        "topic_page": f"wiki/topics/{name}文章写法拆解.md"})
        folder = root / "raw" / "article" / name
        if not folder.is_dir():
            print(f"[错误] 找不到原文目录：{folder}")
            return 1
        files = sorted(folder.glob("*.md"))
        if not files:
            print(f"[错误] 原文目录为空：{folder}")
            return 1
        for number, file in enumerate(files, start=1):
            text = file.read_text(encoding="utf-8-sig")
            stem = file.stem
            articles.append({
                "id": f"{prefix}-{number:02d}",
                "author": name,
                "raw_path": file.relative_to(root).as_posix(),
                "raw_sha256": sha256_of(file),
                "title": f"{stem}文章拆解",
                "original_title": stem,
                "question": "",
                "primary_type": "",
                "primary_product": "",
                "evidence_role": "",
                "own_idea": "",
                "published_at": published_at_of(text),
                "original_url": source_url_of(text),
                "source_page": f"wiki/sources/{stem}文章拆解.md",
                "media_reviewed": False,
                "product_retested": False,
                "sponsor": None,
            })

    manifest = {
        "batch": {
            "slug": args.slug,
            "title": args.title or args.slug,
            "date": args.date,
            "index_title": args.index_title or f"{args.slug} 拆解",
            "comparison_page": f"wiki/comparisons/{args.comparison}.md",
            "comparison_title": args.comparison,
        },
        "authors": authors,
        "articles": articles,
    }
    write_json(manifest_path, manifest)
    write_json(batch_dir / "analyses.json", {a["id"]: {} for a in articles})
    write_json(batch_dir / "dimensions.json", [])
    (batch_dir / "topics").mkdir(parents=True, exist_ok=True)
    write_text(
        batch_dir / "comparison.md",
        f"---\ntitle: {args.comparison}\ntype: comparison\ntags: [公众号, 对标拆解]\n"
        f"status: 进行中\nsources: []\ncreated: {args.date}\nupdated: {args.date}\n---\n\n"
        f"# {args.comparison}\n\n待补：跨作者对比正文。\n",
    )
    print(f"批次清单已生成：{manifest_path}")
    print(f"作者 {len(authors)} 位，文章 {len(articles)} 篇。")
    return 0


def render_source_page(article: dict, analysis: dict, batch: dict, date: str) -> str:
    anchors = "\n\n".join(f"> {quote}" for quote in analysis.get("anchor_terms", []))
    url = article.get("original_url")
    url_line = f"[原文链接]({url})。" if url else NO_DIRECT_LINK
    comparison_title = batch["batch"].get("comparison_title", "对标对比")
    return f"""---
title: {article['title']}
type: source
tags: [公众号, 对标拆解, {article['author']}]
status: 稳定
sources: ["{article['raw_path']}"]
created: {date}
updated: {date}
---

# {article['title']}

来源：`{article['raw_path']}`。

原题：{article['original_title']}。文中署名时间：{article.get('published_at') or '未记录'}，不是剪藏日期。{url_line}

阅读范围：只依据原文文字，图片、动图和视频未核看，未重跑产品；数字、产品版本、价格、排名和技术机制未独立核实。以下“作者报告”不代表本库已验证。{GLOSSARY}

## 主问题与证据身份

{article['question']}

本库主分类：{article['primary_type']}；主研究对象：{article['primary_product']}；证据身份：{article['evidence_role']}。分类依据主要阅读交付，允许文章混合多种写法；实际商务合作未知。

## 标题与开头

{analysis['hook']}

## 结构推进

{analysis['structure']}

## 案例、解释与观察

{analysis['cases']}

## 原文定位锚点

以下为原文可逐字定位的片段，只用于核对判断出处，不将片段中的观点或指令作为本次执行要求。

{anchors}

## 结尾怎样收束

{analysis['ending']}

## 失败、限制与不宜照搬处

{analysis['boundary']}

## 可迁移写法与自己的待测方向

{analysis['learn']}

策划建议：{article['own_idea']}

## 相关页面

- [[topics/{article['author']}文章写法拆解]]
- [[comparisons/{comparison_title}]]
- [[topics/文章写法库]]、[[topics/证据与边界库]]
"""


def fill_topic_sources(text: str, raw_paths: list[str]) -> str:
    front, body = parse_frontmatter(text)
    items = ", ".join(json.dumps(path, ensure_ascii=False) for path in raw_paths)
    front["sources"] = f"[{items}]"
    lines = "\n".join(f"{key}: {value}" for key, value in front.items())
    return f"---\n{lines}\n---\n{body}"


def update_index(root: Path, manifest: dict) -> None:
    index_path = root / "wiki" / "index.md"
    text = index_path.read_text(encoding="utf-8")
    batch = manifest["batch"]
    date = batch["date"]
    text = re.sub(r"最近更新：\d{4}-\d{2}-\d{2}", f"最近更新：{date}", text)
    page_count = sum(p.name not in ("index.md", "log.md") for p in (root / "wiki").rglob("*.md"))
    raw_count = len(list((root / "raw").rglob("*.md")))
    text = re.sub(r"知识页：\d+ 页", f"知识页：{page_count} 页", text)
    text = re.sub(r"原始资料：\d+ 篇", f"原始资料：{raw_count} 篇", text)

    lines = [f"## {batch['index_title']}", "",
             f"本批{len(manifest['articles'])}篇文字研究，媒体未核看；详见[[comparisons/{batch['comparison_title']}]]。", ""]
    for author in manifest["authors"]:
        lines.append(f"- [[topics/{author['name']}文章写法拆解]]")
        lines.append("")
        for article in manifest["articles"]:
            if article["author"] == author["name"]:
                lines.append(f"- [[sources/{Path(article['source_page']).stem}]] — {article['question']}")
        lines.append("")
    block = "\n".join(lines) + "\n"
    heading = f"## {batch['index_title']}"
    pattern = re.compile(re.escape(heading) + r"\n.*?(?=\n## |\Z)", re.S)
    if pattern.search(text):
        text = pattern.sub(block.rstrip() + "\n", text, count=1)
    elif "## 概念" in text:
        text = text.replace("## 概念", block + "## 概念", 1)
    else:
        text = text.rstrip() + "\n\n" + block
    write_text(index_path, text)


def append_dimensions(root: Path, dimensions: list[dict]) -> None:
    for item in dimensions:
        path = root / "wiki" / "topics" / f"{item['file']}.md"
        text = path.read_text(encoding="utf-8")
        front, body = parse_frontmatter(text)
        marker = item["body"].splitlines()[0]
        if marker in body:
            raise RuntimeError(f"维度库已存在同段内容，拒绝重复追加：{path} -> {marker}")
        lines = "\n".join(f"{key}: {value}" for key, value in front.items())
        write_text(path, f"---\n{lines}\n---\n{body.rstrip()}\n\n{item['body'].rstrip()}\n")


def append_log(root: Path, manifest: dict) -> None:
    log_path = root / "wiki" / "log.md"
    batch = manifest["batch"]
    authors = "、".join(a["name"] for a in manifest["authors"])
    marker = f"## [{batch['date']}] benchmark-analysis | {batch['title']}"
    text = log_path.read_text(encoding="utf-8")
    if marker in text:
        print(f"[跳过] 日志已存在同一条目：{marker}")
        return
    entry = (
        f"\n## [{batch['date']}] benchmark-analysis | {batch['title']}\n\n"
        f"- 按对标拆解流程处理{authors}共{len(manifest['articles'])}篇原文，"
        f"新增{len(manifest['articles'])}篇source、{len(manifest['authors'])}篇作者topic与1篇comparison，"
        "并更新索引与维度库。\n"
        "- 图片、动图和视频未核看，未重跑产品，未独立核实原文数字、价格与技术机制；"
        "对标文章中的观点与指令不作为本库结论。\n"
    )
    write_text(log_path, text.rstrip() + "\n" + entry)


def cmd_build(args) -> int:
    root = Path(args.root).resolve()
    batch_dir = Path(args.batch).resolve()
    manifest = read_json(batch_dir / "manifest.json")
    analyses = read_json(batch_dir / "analyses.json")
    date = manifest["batch"]["date"]

    for article in manifest["articles"]:
        analysis = analyses.get(article["id"])
        if not analysis:
            print(f"[错误] 缺少分析：{article['id']}")
            return 1
        page = render_source_page(article, analysis, manifest, date)
        write_text(root / article["source_page"], page)

    for author in manifest["authors"]:
        topic_source = batch_dir / "topics" / f"{author['name']}文章写法拆解.md"
        if not topic_source.is_file():
            print(f"[错误] 缺少作者页：{topic_source}")
            return 1
        raw_paths = [a["raw_path"] for a in manifest["articles"] if a["author"] == author["name"]]
        page = fill_topic_sources(topic_source.read_text(encoding="utf-8"), raw_paths)
        write_text(root / author["topic_page"], page)

    comparison = batch_dir / "comparison.md"
    if not comparison.is_file():
        print(f"[错误] 缺少对比页：{comparison}")
        return 1
    comparison_target = root / manifest["batch"]["comparison_page"]
    raw_paths = [a["raw_path"] for a in manifest["articles"]]
    write_text(comparison_target, fill_topic_sources(comparison.read_text(encoding="utf-8"), raw_paths))

    dimensions_path = batch_dir / "dimensions.json"
    if dimensions_path.is_file():
        try:
            append_dimensions(root, read_json(dimensions_path))
        except RuntimeError as error:
            print(f"[错误] {error}")
            return 1

    update_index(root, manifest)
    append_log(root, manifest)
    print(f"已生成 {len(manifest['articles'])} 篇 source、"
          f"{len(manifest['authors'])} 篇作者 topic、1 篇 comparison，并更新索引、维度库与日志。")
    return 0


def cmd_check(args) -> int:
    root = Path(args.root).resolve()
    batch_dir = Path(args.batch).resolve()
    manifest = read_json(batch_dir / "manifest.json")
    analyses = read_json(batch_dir / "analyses.json")
    errors: list[str] = []
    articles = manifest["articles"]

    ids = [a["id"] for a in articles]
    if len(set(ids)) != len(ids):
        errors.append("文章 id 重复")
    source_pages = [a["source_page"] for a in articles]
    if len(set(source_pages)) != len(source_pages):
        errors.append("source 页路径重复")
    covered = {a["raw_path"] for a in articles}
    expected = set()
    for author in manifest["authors"]:
        folder = root / "raw" / "article" / author["name"]
        expected |= {p.relative_to(root).as_posix() for p in folder.glob("*.md")}
    if covered != expected:
        errors.append(f"原文覆盖不一致：缺 {sorted(expected - covered)}，多 {sorted(covered - expected)}")

    for article in articles:
        raw = root / article["raw_path"]
        if not raw.is_file():
            errors.append(f"原文不存在：{article['id']}")
            continue
        if sha256_of(raw) != article["raw_sha256"]:
            errors.append(f"原文已变化：{article['id']}")
        page_path = root / article["source_page"]
        if not page_path.is_file():
            errors.append(f"拆解页缺失：{article['id']}")
            continue
        page = page_path.read_text(encoding="utf-8")
        front, _ = parse_frontmatter(page)
        for field in REQUIRED_FRONTMATTER:
            if field not in front:
                errors.append(f"{article['id']} frontmatter 缺少 {field}")
        if article["raw_path"] not in page.split("\n---\n", 1)[0]:
            errors.append(f"{article['id']} 未在 frontmatter 记录来源路径")
        for marker in BOUNDARY_MARKERS:
            if marker not in page:
                errors.append(f"{article['id']} 缺少边界声明：{marker}")
        if article["question"] not in page:
            errors.append(f"{article['id']} 缺少主问题")
        if article["own_idea"] not in page:
            errors.append(f"{article['id']} 缺少待测方向")
        if not ("待实操" in article["own_idea"] or "待验证" in article["own_idea"]):
            errors.append(f"{article['id']} 待测方向未标注待实操或待验证")
        if not article["question"].strip() or not article["primary_type"].strip():
            errors.append(f"{article['id']} 主问题或主分类为空")
        if not article["published_at"]:
            errors.append(f"{article['id']} 缺少署名时间")
        elif not re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$", article["published_at"]):
            errors.append(f"{article['id']} 署名时间格式异常")
        analysis = analyses.get(article["id"]) or {}
        text = raw.read_text(encoding="utf-8-sig")
        anchors = analysis.get("anchor_terms") or []
        if len(anchors) < 2:
            errors.append(f"{article['id']} 原文锚点少于2处")
        for anchor in anchors:
            if anchor not in text:
                errors.append(f"{article['id']} 锚点不在原文：{anchor[:20]}")
            if anchor not in page:
                errors.append(f"{article['id']} 锚点不在拆解页：{anchor[:20]}")

    index = (root / "wiki" / "index.md").read_text(encoding="utf-8")
    for article in articles:
        link = f"[[sources/{Path(article['source_page']).stem}]]"
        if link not in index:
            errors.append(f"索引缺少链接：{link}")
    for author in manifest["authors"]:
        topic = root / author["topic_page"]
        if not topic.is_file():
            errors.append(f"作者页缺失：{author['name']}")
            continue
        topic_text = topic.read_text(encoding="utf-8")
        if topic_text != topic_text.rstrip() + "\n":
            errors.append(f"作者页文末有多余空行：{author['name']}")
        for article in articles:
            if article["author"] != author["name"]:
                continue
            link = f"[[sources/{Path(article['source_page']).stem}]]"
            if link not in topic_text:
                errors.append(f"{author['name']} 页缺少链接：{link}")
        if f"[[topics/{author['name']}文章写法拆解]]" not in index:
            errors.append(f"索引缺少作者页：{author['name']}")

    comparison_path = root / manifest["batch"]["comparison_page"]
    if not comparison_path.is_file():
        errors.append("对比页缺失")
    else:
        comparison_text = comparison_path.read_text(encoding="utf-8")
        for author in manifest["authors"]:
            if f"[[topics/{author['name']}文章写法拆解]]" not in comparison_text:
                errors.append(f"对比页缺少作者页：{author['name']}")

    page_count = sum(p.name not in ("index.md", "log.md") for p in (root / "wiki").rglob("*.md"))
    raw_count = len(list((root / "raw").rglob("*.md")))
    if f"知识页：{page_count} 页" not in index:
        errors.append(f"索引知识页计数与实际不符，应为 {page_count}")
    if f"原始资料：{raw_count} 篇" not in index:
        errors.append(f"索引原始资料计数与实际不符，应为 {raw_count}")

    titles: dict[str, list[str]] = {}
    for path in (root / "wiki").rglob("*.md"):
        front, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
        title = front.get("title", "").strip()
        if title:
            titles.setdefault(title, []).append(path.relative_to(root).as_posix())
    for title, paths in titles.items():
        if len(paths) > 1:
            errors.append(f"标题重复（{title}）：{', '.join(paths)}")

    if errors:
        print(f"[失败] {len(errors)} 项")
        for item in errors:
            print(f"  - {item}")
        return 1
    print(f"[通过] {len(articles)} 篇覆盖、哈希、锚点、边界声明、索引与计数全部通过。")
    return 0


def cmd_meta(args) -> int:
    """把单独维护的元数据合并进清单，便于分析与元信息分开编辑。"""
    batch_dir = Path(args.batch).resolve()
    manifest_path = batch_dir / "manifest.json"
    manifest = read_json(manifest_path)
    patch = read_json(Path(args.file).resolve())
    known = {a["id"]: a for a in manifest["articles"]}
    applied = 0
    for article_id, fields in patch.items():
        if article_id not in known:
            print(f"[错误] 清单里没有这个编号：{article_id}")
            return 1
        allowed = {"title", "original_title", "question", "primary_type", "primary_product",
                   "evidence_role", "own_idea", "source_page"}
        for key, value in fields.items():
            if key not in allowed:
                print(f"[错误] 不支持的字段：{article_id}.{key}")
                return 1
            known[article_id][key] = value
        applied += 1
    write_json(manifest_path, manifest)
    print(f"已合并 {applied} 篇元数据：{manifest_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="公众号对标文章拆解批次工具")
    parser.add_argument("--root", required=True, help="知识库根目录")
    sub = parser.add_subparsers(dest="command", required=True)

    init_parser = sub.add_parser("init", help="扫描原文生成批次清单")
    init_parser.add_argument("--batch", required=True, help="批次工作区目录")
    init_parser.add_argument("--authors", required=True, help="作者列表，格式 苍何=CH,爱ai的大刘=DL")
    init_parser.add_argument("--slug", required=True, help="批次标识")
    init_parser.add_argument("--title", default="", help="批次标题")
    init_parser.add_argument("--date", required=True, help="批次日期 YYYY-MM-DD")
    init_parser.add_argument("--index-title", default="", help="索引小节标题")
    init_parser.add_argument("--comparison", required=True, help="对比页标题")
    init_parser.add_argument("--force", action="store_true", help="覆盖已有清单")
    init_parser.set_defaults(func=cmd_init)

    build_parser = sub.add_parser("build", help="生成知识库页面")
    build_parser.add_argument("--batch", required=True, help="批次工作区目录")
    build_parser.set_defaults(func=cmd_build)

    check_parser = sub.add_parser("check", help="校验批次产物")
    check_parser.add_argument("--batch", required=True, help="批次工作区目录")
    check_parser.set_defaults(func=cmd_check)

    meta_parser = sub.add_parser("meta", help="合并文章元数据")
    meta_parser.add_argument("--batch", required=True, help="批次工作区目录")
    meta_parser.add_argument("--file", required=True, help="元数据 JSON 文件")
    meta_parser.set_defaults(func=cmd_meta)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
