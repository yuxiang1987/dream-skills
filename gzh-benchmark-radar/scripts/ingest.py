#!/usr/bin/env python3
"""对标雷达：采集未入库文章、算阅读基线、聚事件簇、出候选素材。

用法（须从技能目录运行，或把 scripts/ingest.py 换成实际绝对路径）：
    python scripts/ingest.py plan    --root <知识库根目录> --accounts <账号清单.json>
    python scripts/ingest.py fetch   --root <知识库根目录> --accounts <账号清单.json> [--limit 30] [--dry-run]
    python scripts/ingest.py stats   --root <知识库根目录> --batch <批次目录>
    python scripts/ingest.py report  --root <知识库根目录> --batch <批次目录>

plan    只读本地：列出待采集、已入库、缺统计的账号与文章，不发任何网络请求。
fetch   调 TikHub 取各号最近文章并落盘 raw/，只新增不覆盖，按文章 ID 与已有原文去重。
stats   为批次内文章取阅读/点赞/在看/分享/收藏/评论数，并算各号中位数基线。
report  生成候选素材：异常样本、跨账号事件簇、未入库清单，供选题技能使用。

本脚本不发帖、不改已有原文、不删除文件；接口按次计费，fetch/stats 只在显式执行时请求。
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import hashlib
import html
import json
import os
import re
import statistics
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

API = "https://api.tikhub.io/api/v1/"
MODEL_WORDS = ("Claude", "Codex", "Gemini", "GPT", "DeepSeek", "Kimi", "豆包", "Qwen", "MiniMax", "Seedance",
               "LibTV", "Sora", "Veo", "WorkBuddy", "OiiOii", "Lovart", "Fotor", "Seko", "Hailuo", "即梦",
               "可灵", "Vidu", "Seedream", "Nano Banana", "Opus", "Sonnet")
CASE_SIGNALS = ("实测", "我测", "跑通", "测试", "对比", "对照", "复现", "试了", "跑了一遍")
STEP_SIGNALS = ("第一步", "步骤", "接下来", "然后我", "先让", "再让", "最后让")
UA = "Mozilla/5.0"
FM = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.S)


def read_key(key_file=None):
    """凭据读取顺序：显式文件、环境变量、知识库 .local/tikhub.json。"""
    if key_file is None and not os.environ.get("TIKHUB_API_KEY"):
        return None
    if key_file:
        content = Path(key_file).read_text(encoding="utf-8-sig").strip()
        try:
            obj = json.loads(content)
        except json.JSONDecodeError:
            obj = None
        key = (obj.get("TIKHUB_API_KEY") or obj.get("tikhub_api_key") or obj.get("api_key")
               if isinstance(obj, dict) else None)
        if key is None:
            match = re.search(r"(?m)^\s*(?:export\s+)?TIKHUB_API_KEY\s*=\s*(.+?)\s*$", content)
            key = match.group(1).strip().strip("\"'") if match else content
    else:
        key = os.environ.get("TIKHUB_API_KEY")
    if not isinstance(key, str) or not key.strip() or any(c.isspace() for c in key.strip()):
        raise ValueError("缺少有效 TikHub 配置")
    return key.strip()


def load_key(root, key_file=None):
    if key_file is None and not os.environ.get("TIKHUB_API_KEY"):
        local = Path(root) / ".local" / "tikhub.json"
        if local.is_file():
            key_file = local
        else:
            return None
    return read_key(key_file)


def clean_url(url):
    parts = urlsplit(html.unescape(url))
    if parts.netloc != "mp.weixin.qq.com":
        raise ValueError("不是微信公众号链接")
    query = parse_qs(parts.query)
    keep = {k: query[k][0] for k in ("__biz", "mid", "idx", "sn") if k in query}
    return urlunsplit(("https", parts.netloc, parts.path, urlencode(keep), ""))


def article_id(item):
    if item.get("app_msg_id") is not None:
        return f'{item["app_msg_id"]}:{item.get("idx", 1)}'
    return clean_url(item["url"])


def parse_frontmatter(text):
    match = FM.match(text)
    if not match:
        return None
    data = {}
    for line in match.group(1).splitlines():
        if ":" not in line or line.strip().startswith("#"):
            continue
        key, _, value = line.partition(":")
        data[key.strip()] = value.strip()
    return data


def frontmatter_list(value):
    value = (value or "").strip()
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
        return [v.strip().strip('"').strip("'") for v in value.split(",") if v.strip()]
    return [value.strip().strip('"').strip("'")] if value else []


def index_raw(root):
    """原始资料索引：路径 -> 文件内记录的 source 链接与标题。"""
    found = {}
    for path in (Path(root) / "raw").rglob("*.md"):
        front = parse_frontmatter(path.read_text(encoding="utf-8-sig", errors="replace"))
        if front:
            found[path.relative_to(root).as_posix()] = {
                "source": (front.get("source") or "").strip().strip('"'),
                "title": (front.get("title") or "").strip().strip('"'),
                "account": (front.get("account_username") or "").strip().strip('"'),
            }
    return found


def index_sources(root):
    """知识页引用索引：raw 路径 -> 引用它的 source 页列表。"""
    refs = {}
    for path in (Path(root) / "wiki" / "sources").glob("*.md"):
        front = parse_frontmatter(path.read_text(encoding="utf-8-sig", errors="replace"))
        if not front:
            continue
        for item in frontmatter_list(front.get("sources", "")):
            refs.setdefault(item, []).append(path.relative_to(root).as_posix())
    return refs


def load_accounts(path):
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    accounts = data["accounts"] if isinstance(data, dict) else data
    for item in accounts:
        for field in ("name", "username"):
            if not item.get(field):
                raise ValueError(f"账号清单缺少字段 {field}")
    return accounts


def cmd_plan(args):
    accounts = load_accounts(args.accounts)
    raw = index_raw(args.root)
    refs = index_sources(args.root)
    by_account = {}
    for path, meta in raw.items():
        by_account.setdefault(meta["account"], []).append(path)
    lines = [f"账号清单：{len(accounts)} 个"]
    for item in accounts:
        paths = by_account.get(item["username"], [])
        analysed = [p for p in paths if refs.get(p)]
        pending = [p for p in paths if not refs.get(p)]
        lines.append(
            f'- {item["name"]}（{item["username"]}）：原文 {len(paths)}，已入库 {len(analysed)}，未入库 {len(pending)}')
        for path in pending[:args.show]:
            lines.append(f"    待入库 {path}")
    print("\n".join(lines))
    return 0


class Client:
    def __init__(self, key):
        self.key = key

    def post(self, endpoint, payload, tries=3):
        if endpoint not in ("wechat_mp/v2/fetch_account_articles", "wechat_mp/v2/fetch_article_detail_h5",
                            "wechat_mp/v2/fetch_article_stats"):
            raise ValueError("不支持的接口")
        request = Request(API + endpoint, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                          headers={"Authorization": "Bearer " + self.key,
                                   "Content-Type": "application/json", "User-Agent": UA}, method="POST")
        last = None
        for _ in range(tries):
            try:
                with urlopen(request, timeout=45) as response:
                    result = json.load(response)
                if result.get("code") in (None, 0, 200) and isinstance(result.get("data"), dict):
                    return result["data"], result.get("request_id")
                last = f'业务状态 {result.get("code")}'
            except HTTPError as error:
                last = f"HTTP {error.code}"
            except (URLError, TimeoutError, OSError):
                last = "连接失败或超时"
            time.sleep(1.5)
        raise RuntimeError(f"请求未完成：{endpoint} {last}")


def cmd_fetch(args):
    accounts = load_accounts(args.accounts)
    out_dir = Path(args.root) / "raw" / "article"
    raw = index_raw(args.root)
    known_links = {meta["source"].rstrip("/") for meta in raw.values() if meta["source"]}
    plan = []
    for account in accounts:
        plan.append((account["username"], account["name"], account.get("directory") or account["name"]))
    if args.dry_run:
        print("dry-run：将采集 " + "、".join(name for _, name, _ in plan) + f"，每号 {args.limit} 篇；不发请求")
        return 0
    key = load_key(args.root, args.key_file)
    if not key:
        raise RuntimeError("未找到凭据：配置 TIKHUB_API_KEY 或知识库 .local/tikhub.json")
    client = Client(key)
    acquired = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(timespec="seconds")
    summary = []
    for username, name, directory in plan:
        page, _ = client.post("wechat_mp/v2/fetch_account_articles",
                              {"username": username, "page_size": 20, "raw": False})
        items, cursor, seen = list(page.get("articles") or []), "", set()
        while len(items) < args.limit and not page.get("is_end"):
            cursor = page.get("next_offset")
            if not cursor or cursor in seen:
                break
            seen.add(cursor)
            page, _ = client.post("wechat_mp/v2/fetch_account_articles",
                                  {"username": username, "page_size": 20, "raw": False, "offset": cursor})
            if page.get("biz_username") and page["biz_username"] != username:
                raise RuntimeError("分页账号身份不符，已停止")
            items.extend(page.get("articles") or [])
        unique, ids = [], set()
        for item in sorted(items, key=lambda x: int(x.get("create_time") or 0), reverse=True):
            key_id = article_id(item)
            if key_id in ids:
                continue
            ids.add(key_id)
            unique.append(item)
        folder = out_dir / directory / f"雷达-{args.date}"
        folder.mkdir(parents=True, exist_ok=True)
        added = skipped = failed = 0
        new_rows = []
        for item in unique[:args.limit]:
            link = clean_url(item["url"])
            if link in known_links:
                skipped += 1
                continue
            try:
                detail, _ = client.post("wechat_mp/v2/fetch_article_detail_h5", {"url": link, "raw": False})
            except RuntimeError:
                failed += 1
                continue
            content = detail.get("content") or {}
            body = content.get("content_noencode") or content.get("content_text") or ""
            if content.get("user_name") != username or len(re.sub(r"<[^>]+>", "", body).strip()) < 100:
                failed += 1
                continue
            title = (content.get("title") or item.get("title") or "未命名文章").strip()
            stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title)[:100].strip(" .") or "未命名文章"
            digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
            path = folder / f"{stem}-{digest[:10]}.md"
            meta = {"title": title, "source": link, "author": content.get("author") or content.get("nick_name"),
                    "account": content.get("nick_name"), "account_username": content.get("user_name"),
                    "published": content.get("create_time"), "downloaded_at": acquired,
                    "downloaded_via": "TikHub WeChat MP V2 H5", "body_sha256": digest}
            text = "---\n" + "\n".join(f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in meta.items()) + "\n---\n\n" + body + "\n"
            with path.open("x", encoding="utf-8") as handle:
                handle.write(text)
            known_links.add(link)
            new_rows.append({"id": article_id(item), "title": title, "url": link,
                             "published": content.get("create_time"),
                             "raw_path": path.relative_to(args.root).as_posix()})
            added += 1
        summary.append({"account": name, "username": username, "fetched": len(unique[:args.limit]),
                        "added": added, "skipped_existing": skipped, "failed": failed,
                        "directory": (folder.relative_to(args.root)).as_posix(),
                        "added_articles": new_rows})
        print(f'{name}：新增 {added}，已存在跳过 {skipped}，失败 {failed}', flush=True)
    out = Path(args.batch) if args.batch else Path(args.root) / "output" / "ai-wechat-methodology" / f"雷达-{args.date}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "fetch-summary.json").write_text(json.dumps({"acquired_at": acquired, "accounts": summary},
                                                       ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"清单：{(out / 'fetch-summary.json').as_posix()}")
    return 0


def cmd_stats(args):
    batch = Path(args.batch)
    manifest_path = batch / "manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError(f"批次清单不存在：{manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows = [(account["requested_name"], row) for account in manifest["accounts"] for row in account["articles"]]
    if args.from_fetch:
        fetched = json.loads(Path(args.from_fetch).read_text(encoding="utf-8"))
        rows = [(item["account"], article) for item in fetched["accounts"]
                for article in item.get("added_articles", [])]
        if not rows:
            print("本轮没有新增文章，跳过统计")
            return 0
    key = load_key(args.root, args.key_file)
    if not key:
        raise RuntimeError("未找到凭据：配置 TIKHUB_API_KEY 或知识库 .local/tikhub.json")
    client = Client(key)

    def one(pair):
        account, row = pair
        try:
            data, request_id = client.post("wechat_mp/v2/fetch_article_stats",
                                           {"url": clean_url(row["url"]), "raw": False})
            return {"account": account, "id": str(row["id"]), "title": row["title"],
                    "published": row.get("list_create_time"), "read_num": data.get("read_num"),
                    "like_count": data.get("like_count"), "old_like_count": data.get("old_like_count"),
                    "share_count": data.get("share_count"), "collect_count": data.get("collect_count"),
                    "comment_count": data.get("comment_count"), "request_id": request_id}
        except RuntimeError as error:
            return {"account": account, "id": str(row["id"]), "title": row["title"], "error": str(error)}

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        for item in pool.map(one, rows):
            results.append(item)
    folder = batch / f"stats-{args.date}"
    folder.mkdir(parents=True, exist_ok=True)
    by_account = {}
    for item in results:
        if item.get("read_num"):
            by_account.setdefault(item["account"], []).append(item)
    baseline = []
    for account, items in by_account.items():
        reads = [item["read_num"] for item in items]
        median = statistics.median(reads)
        for item in items:
            item["ratio"] = round(item["read_num"] / median, 2) if median else None
        baseline.append({"account": account, "n": len(items), "median": int(median),
                         "min": min(reads), "max": max(reads),
                         "median_like": int(statistics.median([i["like_count"] or 0 for i in items])),
                         "median_share": int(statistics.median([i["share_count"] or 0 for i in items])),
                         "median_comment": int(statistics.median([i["comment_count"] or 0 for i in items]))})
    (folder / "baseline.json").write_text(json.dumps(baseline, ensure_ascii=False, indent=2) + "\n",
                                          encoding="utf-8")
    (folder / "all-stats.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n",
                                            encoding="utf-8")
    ok = len([r for r in results if "error" not in r])
    print(f"统计完成：成功 {ok}，失败 {len(results) - ok}；输出 {folder.as_posix()}")
    return 0


def extract_case(text, title):
    """从原文里识别"带实测案例"的线索，只给待填模板，不代写结论。"""
    plain = html.unescape(re.sub(r"<[^>]+>", "", text))
    models = sorted({word for word in MODEL_WORDS if word in plain}, key=len, reverse=True)[:4]
    hits = sum(1 for word in CASE_SIGNALS if word in plain)
    steps = sum(1 for word in STEP_SIGNALS if word in plain)
    if hits < 2 or (not models and hits < 3):
        return None
    return {
        "article": title,
        "models": models,
        "angle": "",          # 待填：这篇在观察什么能力
        "steps": "",          # 待填：怎么测的，按步骤写
        "inputs": "",         # 待填：用了什么素材
        "checks": "",         # 待填：验收点
        "status": "待填写",
        "signals": {"case_hits": hits, "step_hits": steps},
    }


def cmd_report(args):
    batch = Path(args.batch)
    stats_dir = sorted(batch.glob("stats-*"))
    if not stats_dir:
        raise RuntimeError("未找到 stats-* 目录，请先运行 stats")
    folder = stats_dir[-1]
    results = json.loads((folder / "all-stats.json").read_text(encoding="utf-8"))
    baseline = json.loads((folder / "baseline.json").read_text(encoding="utf-8"))
    median_by = {item["account"]: item["median"] for item in baseline}
    for item in results:
        if "ratio" not in item and item.get("read_num") and median_by.get(item["account"]):
            item["ratio"] = round(item["read_num"] / median_by[item["account"]], 2)
    anomalies = sorted([r for r in results if r.get("ratio") and r["ratio"] >= args.threshold],
                       key=lambda r: -r["ratio"])
    refs = index_sources(args.root)
    account_rows = {}
    manifest = batch / "manifest.json"
    if manifest.is_file():
        data = json.loads(manifest.read_text(encoding="utf-8"))
        for account in data["accounts"]:
            account_rows[account["requested_name"]] = account["articles"]
    clusters = {}
    for account, rows in account_rows.items():
        for row in rows:
            object_name = row.get("primary_product") or ""
            if not object_name:
                continue
            clusters.setdefault(object_name, []).append((account, row))
    multi = []
    for object_name, rows in clusters.items():
        accounts = {account for account, _ in rows}
        if len(accounts) < 2:
            continue
        dates = sorted(str(row.get("published") or "")[:10] for _, row in rows)
        try:
            span = (dt.date.fromisoformat(dates[-1]) - dt.date.fromisoformat(dates[0])).days
        except ValueError:
            span = None
        if span is not None and span <= args.window:
            multi.append({"object": object_name, "articles": len(rows), "accounts": sorted(accounts),
                          "span_days": span, "from": dates[0], "to": dates[-1]})
    multi.sort(key=lambda item: (-item["articles"], item["span_days"]))
    pending = [path for path in index_raw(args.root) if not refs.get(path)]
    cases = []
    for path in sorted(index_raw(args.root)):
        try:
            text = (Path(args.root) / path).read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            continue
        title = index_raw(args.root)[path]["title"]
        case = extract_case(text, title)
        if case:
            case["raw_path"] = path
            case["source_page"] = (refs.get(path) or [None])[0]
            cases.append(case)
    out = {
        "batch": batch.as_posix(),
        "stats_dir": folder.as_posix(),
        "baseline": baseline,
        "anomalies": [{"account": r["account"], "title": r["title"], "read_num": r["read_num"],
                       "ratio": r["ratio"], "share_count": r.get("share_count"),
                       "comment_count": r.get("comment_count")} for r in anomalies],
        "event_clusters": multi,
        "raw_without_source": pending,
        "case_candidates": cases,
        "median_by_account": median_by,
    }
    (batch / "report.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"异常样本 {len(anomalies)} 篇，跨账号事件簇 {len(multi)} 组，未入库原文 {len(pending)} 篇，"
          f"待填案例卡 {len(cases)} 篇")
    print(f"报告：{(batch / 'report.json').as_posix()}")
    for item in multi[:10]:
        print(f'- {item["object"]}：{item["articles"]} 篇 / {len(item["accounts"])} 号 / {item["span_days"]} 天')
    return 0


BRIEFING = """---
title: 对标雷达简报 {date}
type: source
tags: [公众号, 对标, 雷达]
status: 草稿
sources: []
created: {date}
updated: {date}
---

# 对标雷达简报 {date}

## 本轮采集

{collection}

## 各号阅读基线（本轮统计）

{baseline}

## 异常样本（≥{threshold}× 本号中位数）

{anomalies}

## 跨账号同题事件簇

{clusters}

## 待填案例卡（带实测的文章）

{cases}

## 未入库原文

{pending}

## 口径与边界

单次快照，阅读数会继续增长；含系统推荐，不是自然阅读；10 万以上封顶；中位数只在该号内部成立，跨号比绝对值无意义。高阅读只说明在它自己的号里突出，不说明某个标题或结构导致传播，也不能推出我们照写能到同样量级。案例卡只填了模型与信号，角度、步骤、验收点留空待人工补。
"""


def _bullet(items, empty="无"):
    return "\n".join(f"- {item}" for item in items) if items else empty


def cmd_daily(args):
    """一条命令跑完：盘点多 → 采集新增 → 只统计新增 → 出简报。"""
    date = args.date
    batch = Path(args.batch) if args.batch else Path(args.root) / "output" / "ai-wechat-methodology" / f"雷达-{date}"
    batch.mkdir(parents=True, exist_ok=True)
    print("== 1/4 盘点本地状态 ==")
    main(["--root", args.root, "plan", "--accounts", args.accounts, "--show", "3"])
    print("== 2/4 采集新增 ==")
    fetch_args = ["--root", args.root, "fetch", "--accounts", args.accounts,
                  "--limit", str(args.limit), "--date", date, "--batch", str(batch)]
    if args.dry_run:
        fetch_args.append("--dry-run")
    main(fetch_args)
    summary_path = batch / "fetch-summary.json"
    if not summary_path.is_file():
        print("未生成采集清单，简报跳过")
        return 0
    collected = json.loads(summary_path.read_text(encoding="utf-8"))
    added_total = sum(item["added"] for item in collected["accounts"])
    if added_total and not args.dry_run:
        print("== 3/4 统计新增文章的互动数据 ==")
        main(["--root", args.root, "stats", "--batch", str(batch), "--date", date,
              "--from-fetch", str(summary_path)])
        print("== 4/4 汇总 ==")
        if any(batch.glob("stats-*")):
            main(["--root", args.root, "report", "--batch", str(batch)])
        else:
            print("没有统计产物，跳过汇总")
    elif not added_total:
        print("本轮无新增文章，仅生成空简报")
    report = {}
    report_path = batch / "report.json"
    if report_path.is_file():
        report = json.loads(report_path.read_text(encoding="utf-8"))
    collection = _bullet([f'{item["account"]}：新增 {item["added"]}，已存在 {item["skipped_existing"]}，失败 {item["failed"]}'
                          for item in collected["accounts"]])
    baseline = _bullet([f'{item["account"]}：{item["n"]} 篇，中位数 {item["median"]}，区间 {item["min"]}—{item["max"]}'
                        for item in report.get("baseline", [])])
    anomalies = _bullet([f'{item["account"]}《{item["title"][:30]}》{item["read_num"]}（{item["ratio"]}×）'
                         for item in report.get("anomalies", [])[:15]])
    clusters = _bullet([f'{item["object"]}：{item["articles"]} 篇 / {len(item["accounts"])} 号 / {item["span_days"]} 天'
                        for item in report.get("event_clusters", [])[:15]])
    cases = _bullet([f'{item["article"][:30]}（模型：{"、".join(item["models"]) or "未识别"}）' for item in
                     report.get("case_candidates", [])[:15]])
    pending = _bullet([f"`{item}`" for item in report.get("raw_without_source", [])[:20]])
    text = BRIEFING.format(date=date, collection=collection, baseline=baseline, anomalies=anomalies,
                           clusters=clusters, cases=cases, pending=pending, threshold=args.threshold)
    out = batch / f"雷达简报-{date}.md"
    out.write_text(text, encoding="utf-8")
    print(f"本轮新增 {added_total} 篇；简报：{out.as_posix()}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="对标雷达：采集、统计与事件簇")
    parser.add_argument("--root", required=True, help="知识库根目录")
    parser.add_argument("--key-file", help="TikHub 凭据文件；不写入任何仓库")
    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", help="本地盘点未入库原文，不发请求")
    plan.add_argument("--accounts", required=True)
    plan.add_argument("--show", type=int, default=5)
    plan.set_defaults(func=cmd_plan)

    fetch = sub.add_parser("fetch", help="采集各号最近文章")
    fetch.add_argument("--accounts", required=True)
    fetch.add_argument("--limit", type=int, default=30)
    fetch.add_argument("--date", default=dt.date.today().isoformat())
    fetch.add_argument("--batch")
    fetch.add_argument("--dry-run", action="store_true")
    fetch.set_defaults(func=cmd_fetch)

    stats = sub.add_parser("stats", help="取互动数据并算基线")
    stats.add_argument("--batch", required=True)
    stats.add_argument("--date", default=dt.date.today().isoformat())
    stats.add_argument("--workers", type=int, default=4)
    stats.add_argument("--from-fetch", help="只统计某次 fetch 的新增文章")
    stats.set_defaults(func=cmd_stats)

    report = sub.add_parser("report", help="汇总异常样本、事件簇与未入库清单")
    report.add_argument("--batch", required=True)
    report.add_argument("--threshold", type=float, default=2.0)
    report.add_argument("--window", type=int, default=60)
    report.set_defaults(func=cmd_report)

    daily = sub.add_parser("daily", help="一条命令跑完采集、统计与简报")
    daily.add_argument("--accounts", required=True)
    daily.add_argument("--limit", type=int, default=5, help="每号最多取几篇新文章，控制费用")
    daily.add_argument("--date", default=dt.date.today().isoformat())
    daily.add_argument("--batch")
    daily.add_argument("--threshold", type=float, default=2.0)
    daily.add_argument("--dry-run", action="store_true")
    daily.set_defaults(func=cmd_daily)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"未完成：{exc}")
        sys.exit(1)
