#!/usr/bin/env python3
"""公众号流水线脚手架与交接校验器。

用法：
    python scripts/pipeline.py init --root <流水线根目录> --date 2026-10-23 --slug <选题短名>
    python scripts/pipeline.py check --dir <当次目录>
    python scripts/pipeline.py status --dir <当次目录>

init 生成一次生产的目录和模板文件；check 按交接契约检查各阶段产物；
status 打印阶段状态表，用于判断从哪一步接上。
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import shutil
import sys
from pathlib import Path

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

SKILL_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = SKILL_ROOT / "templates"

REQUIRED_FIELDS = ("stage", "status", "topic", "source_skill", "created", "updated")
VALID_STATUS = ("待办", "待确认", "已确认", "已跳过", "已废弃")
VALID_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PLACEHOLDER = re.compile(r"\{\{[^{}]+\}\}")
FM_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.S)

# 阶段顺序。每一项是 (阶段名, 产物文件, 是否必须存在)。
STAGES = (
    ("S0 定盘", "00_style.md", True),
    ("S1 选题", "01_选题卡.md", True),
    ("S2 案例与实测", "02_案例决策卡.md", True),
    ("S2 案例与实测", "03_证据与实测.md", True),
    ("S3 写作", "04_正文.md", True),
    ("S4 定稿检查", "05_检查报告.md", True),
    ("S5 标题封面排版", "06_标题.md", True),
    ("S6 发布与回流", "09_发布记录.md", True),
)

# 已确认的阶段额外要求存在的产物。
EXTRA_OUTPUTS = (
    ("S5 标题封面排版", "07_封面.png"),
    ("S6 发布与回流", "08_排版"),
)

STAGE_ORDER = (
    "S0 定盘",
    "S1 选题",
    "S2 案例与实测",
    "S3 写作",
    "S4 定稿检查",
    "S5 标题封面排版",
    "S6 发布与回流",
)


def parse_frontmatter(text: str) -> dict:
    match = FM_RE.match(text)
    if not match:
        return {}
    data = {}
    for line in match.group(1).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        data[key.strip()] = value.strip()
    return data


def read_stage(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    front = parse_frontmatter(text)
    body = text[FM_RE.match(text).end():] if FM_RE.match(text) else text
    return {"path": path, "front": front, "body": body, "text": text}


def slugify(value: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|\s]+", "-", value.strip()).strip("-.")
    return cleaned or "选题"


def command_init(args) -> int:
    root = Path(args.root).expanduser().resolve()
    date = args.date or dt.date.today().isoformat()
    if not VALID_DATE.match(date):
        print(f"[错误] 日期格式应为 YYYY-MM-DD，收到 {date}")
        return 1
    slug = slugify(args.slug or "选题")
    run_dir = root / f"{date}-{slug}"
    if run_dir.exists():
        print(f"[错误] 目录已存在，不覆盖：{run_dir}")
        return 1
    run_dir.mkdir(parents=True)

    for template in sorted(TEMPLATE_DIR.glob("*.md")):
        text = template.read_text(encoding="utf-8")
        text = text.replace("{{日期}}", date)
        (run_dir / template.name).write_text(text, encoding="utf-8")

    # 账号宪法跨轮复用：根目录已有 00_style.md 时复制它，不再用空模板。
    shared = root / "00_style.md"
    if shared.is_file():
        shutil.copyfile(shared, run_dir / "00_style.md")

    print(f"已创建流水线目录：{run_dir}")
    print("下一步：填写 00_style.md，把 status 改成「已确认」，再进入 S1 选题。")
    return 0


def _must_clear_rows(body: str, heading: str) -> int:
    """统计某个二级标题下的表格数据行数，用于判断是否清零。"""
    pattern = re.compile(rf"^##\s*{re.escape(heading)}\s*$(.*?)(?=^##\s|\Z)", re.S | re.M)
    match = pattern.search(body)
    if not match:
        return 0
    rows = 0
    for line in match.group(1).splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 2:
            continue
        if all(set(cell) <= set("-: ") for cell in cells):
            continue
        if cells[0] in ("原句", "场景", "#"):
            continue
        rows += 1
    return rows


def command_check(args) -> int:
    run_dir = Path(args.dir).expanduser().resolve()
    if not run_dir.is_dir():
        print(f"[错误] 找不到流水线目录：{run_dir}")
        return 1

    errors: list[str] = []
    warnings: list[str] = []
    states: dict[str, str] = {}

    for stage, filename, required in STAGES:
        path = run_dir / filename
        if not path.is_file():
            if required:
                errors.append(f"{filename}：缺少文件")
            continue
        data = read_stage(path)
        front = data["front"]
        if not front:
            errors.append(f"{filename}：缺少 frontmatter")
            continue
        for field in REQUIRED_FIELDS:
            if field not in front or not front[field]:
                errors.append(f"{filename}：frontmatter 缺少字段 {field}")
        status = front.get("status", "")
        if status and status not in VALID_STATUS:
            errors.append(f"{filename}：status 取值不合法（{status}），只允许 {', '.join(VALID_STATUS)}")
        for field in ("created", "updated"):
            value = front.get(field, "")
            if value and not VALID_DATE.match(value):
                errors.append(f"{filename}：{field} 格式应为 YYYY-MM-DD，收到 {value}")
        declared_stage = front.get("stage", "")
        if declared_stage and declared_stage != stage:
            errors.append(f"{filename}：stage 写成「{declared_stage}」，应为「{stage}」")
        states[stage] = status or "待办"

        if status == "已确认":
            leftovers = sorted(set(PLACEHOLDER.findall(data["body"])))
            if leftovers:
                errors.append(f"{filename}：已确认但还留着占位符 {', '.join(leftovers[:5])}")

    # 阶段顺序：前一阶段未完成时，后一阶段不能已确认。
    for index, stage in enumerate(STAGE_ORDER):
        if states.get(stage) != "已确认":
            continue
        for earlier in STAGE_ORDER[:index]:
            if states.get(earlier) in ("待办", "待确认", None):
                errors.append(f"{stage}：已确认，但前置阶段「{earlier}」还没完成")

    # 硬关口：正文已确认，实测记录必须填完。
    body_path = run_dir / "04_正文.md"
    evidence_path = run_dir / "03_证据与实测.md"
    if body_path.is_file() and evidence_path.is_file():
        body_status = read_stage(body_path)["front"].get("status", "")
        evidence = read_stage(evidence_path)
        if body_status == "已确认":
            if evidence["front"].get("status", "") != "已确认":
                errors.append("04_正文.md：已确认，但 03_证据与实测.md 未确认")
            leftovers = sorted(set(PLACEHOLDER.findall(evidence["body"])))
            if leftovers:
                errors.append(
                    "04_正文.md：已确认，但 03_证据与实测.md 还有占位符 "
                    f"{', '.join(leftovers[:5])}，缺实测记录"
                )

    # 定稿检查：必须修改项清零才能确认。
    report_path = run_dir / "05_检查报告.md"
    if report_path.is_file():
        report = read_stage(report_path)
        if report["front"].get("status", "") == "已确认":
            pending = _must_clear_rows(report["body"], "必须修改")
            if pending:
                errors.append(f"05_检查报告.md：已确认，但必须修改还有 {pending} 条")

    # 标题确认后要有封面；发布确认后要有排版产物。
    title_path = run_dir / "06_标题.md"
    if title_path.is_file() and read_stage(title_path)["front"].get("status", "") == "已确认":
        if not (run_dir / "07_封面.png").is_file():
            errors.append("06_标题.md：已确认，但缺少 07_封面.png")
    publish_path = run_dir / "09_发布记录.md"
    if publish_path.is_file() and read_stage(publish_path)["front"].get("status", "") == "已确认":
        if not (run_dir / "08_排版").is_dir():
            errors.append("09_发布记录.md：已确认，但缺少 08_排版 目录")

    for stage, extra in EXTRA_OUTPUTS:
        if states.get(stage) == "已确认" and not (run_dir / extra).exists():
            errors.append(f"{stage}：已确认，但缺少 {extra}")

    # 未确认阶段的占位符是正常待办，只在长期遗留时提示。
    for stage, filename, _ in STAGES:
        path = run_dir / filename
        if not path.is_file():
            continue
        data = read_stage(path)
        if data["front"].get("status", "") in ("已确认", "已跳过"):
            continue
        if PLACEHOLDER.search(data["body"]):
            warnings.append(f"{filename}：仍是模板状态，等待填写或确认")

    print(f"流水线校验：{run_dir}")
    print()
    for stage in STAGE_ORDER:
        print(f"  {stage:<12} {states.get(stage, '待办')}")
    print()
    if errors:
        print(f"[错误] {len(errors)} 项")
        for item in errors:
            print(f"  - {item}")
        print()
    if warnings:
        print(f"[警告] {len(warnings)} 项")
        for item in warnings:
            print(f"  - {item}")
        print()
    if not errors:
        print("交接校验通过。")
    return 1 if errors else 0


def command_status(args) -> int:
    run_dir = Path(args.dir).expanduser().resolve()
    if not run_dir.is_dir():
        print(f"[错误] 找不到流水线目录：{run_dir}")
        return 1
    rows = []
    for stage, filename, _ in STAGES:
        path = run_dir / filename
        status = "待办"
        if path.is_file():
            status = read_stage(path)["front"].get("status", "待办") or "待办"
        rows.append((stage, filename, status))
    width_stage = max(len(row[0]) for row in rows)
    width_file = max(len(row[1]) for row in rows)
    print(f"流水线状态：{run_dir}")
    print()
    for stage, filename, status in rows:
        print(f"  {stage:<{width_stage}}  {filename:<{width_file}}  {status}")
    print()
    pending = [row for row in rows if row[2] not in ("已确认", "已跳过", "已废弃")]
    if pending:
        print(f"下一个关口：{pending[0][0]}（{pending[0][1]}，当前 {pending[0][2]}）")
    else:
        print("所有阶段已完成。")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="公众号流水线脚手架与交接校验")
    sub = parser.add_subparsers(dest="command", required=True)

    init_parser = sub.add_parser("init", help="创建一次生产的目录和模板")
    init_parser.add_argument("--root", required=True, help="流水线根目录")
    init_parser.add_argument("--date", default=None, help="日期，YYYY-MM-DD")
    init_parser.add_argument("--slug", default=None, help="选题短名")
    init_parser.set_defaults(func=command_init)

    check_parser = sub.add_parser("check", help="按交接契约校验各阶段产物")
    check_parser.add_argument("--dir", required=True, help="当次流水线目录")
    check_parser.set_defaults(func=command_check)

    status_parser = sub.add_parser("status", help="打印阶段状态表")
    status_parser.add_argument("--dir", required=True, help="当次流水线目录")
    status_parser.set_defaults(func=command_status)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
