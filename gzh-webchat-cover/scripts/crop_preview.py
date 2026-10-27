#!/usr/bin/env python3
"""Generate the other crops WeChat may show, so one cover stays legible everywhere.

WeChat exposes each article's cover at several ratios (235_1 / 16_9 / 3_4 / 1_1).
The feed card and share card do not always use the 2.35:1 banner, so a cover that
only works as a wide banner can lose its subject or its text elsewhere.

Usage:
    python scripts/crop_preview.py --cover 07_封面.png --outdir 07_裁剪预览
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

TARGETS = {
    "1x1": (1, 1),
    "16x9": (16, 9),
    "3x4": (3, 4),
}


def center_crop(image: Image.Image, ratio: float) -> Image.Image:
    width, height = image.size
    if width / height > ratio:
        new_width = int(round(height * ratio))
        left = (width - new_width) // 2
        return image.crop((left, 0, left + new_width, height))
    new_height = int(round(width / ratio))
    top = (height - new_height) // 2
    return image.crop((0, top, width, top + new_height))


def main() -> int:
    parser = argparse.ArgumentParser(description="导出封面的 1:1 / 16:9 / 3:4 居中裁剪预览")
    parser.add_argument("--cover", required=True, help="已完成的封面图（通常 900×383）")
    parser.add_argument("--outdir", required=True, help="裁剪预览输出目录")
    parser.add_argument("--order", default="subject-left",
                        help="构图提示：subject-left / subject-center / subject-right，仅用于提示文字")
    args = parser.parse_args()

    cover_path = Path(args.cover)
    if not cover_path.is_file():
        raise SystemExit(f"找不到封面：{cover_path}")
    image = Image.open(cover_path).convert("RGB")
    width, height = image.size
    ratio = width / height

    print(f"封面尺寸：{width}×{height}，比例 {ratio:.3f}:1")
    if abs(ratio - 2.35) > 0.06:
        print("提示：常规公众号首图约为 2.35:1，当前比例偏离，先确认是否上传的是首图。")

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    for name, (rw, rh) in TARGETS.items():
        cropped = center_crop(image, rw / rh)
        path = outdir / f"{cover_path.stem}-{name}{cover_path.suffix}"
        cropped.save(path)
        print(f"  {name:5s} {cropped.width}×{cropped.height} → {path.name}")

    if args.order == "subject-left":
        print("检查：主体在左侧时，居中裁剪后右侧可能只剩背景；确认 1:1 仍能看到主体与主文案。")
    elif args.order == "subject-right":
        print("检查：主体在右侧时，1:1 裁剪可能切掉主体边缘；确认关键物体没有被裁断。")
    else:
        print("检查：主体居中时，宽幅两侧多为留白；确认 16:9 与 3:4 不显得空。")
    print("三张预览都要在手机缩略图大小下看一眼，再决定是否调整主文案位置。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
