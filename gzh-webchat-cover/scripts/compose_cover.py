#!/usr/bin/env python3
"""Crop a background to WeChat cover ratio and add deterministic Chinese type."""

from __future__ import annotations

import argparse
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps

SIZE = (900, 383)


def find_font(bold: bool) -> str:
    roots = [Path("C:/Windows/Fonts"), Path("/usr/share/fonts"), Path("/System/Library/Fonts")]
    names = (
        ["msyhbd.ttc", "simhei.ttf", "SourceHanSansSC-Bold.otf", "NotoSansCJK-Bold.ttc"]
        if bold
        else ["msyh.ttc", "simsun.ttc", "SourceHanSansSC-Regular.otf", "NotoSansCJK-Regular.ttc"]
    )
    for root in roots:
        for name in names:
            matches = list(root.rglob(name)) if root.exists() else []
            if matches:
                return str(matches[0])
    raise SystemExit("No Chinese font found. Pass --font and --subtitle-font explicitly.")


def hex_color(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    if len(value) != 6:
        raise argparse.ArgumentTypeError("Color must be #RRGGBB")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    lines, current = [], ""
    for ch in text:
        trial = current + ch
        if current and draw.textbbox((0, 0), trial, font=font)[2] > max_width:
            lines.append(current)
            current = ch
        else:
            current = trial
    if current:
        lines.append(current)
    return lines[:2]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--background", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--subtitle", default="")
    p.add_argument("--accent", type=hex_color, default=(242, 201, 76))
    p.add_argument("--font")
    p.add_argument("--subtitle-font")
    p.add_argument("--overlay", type=float, default=0.48)
    args = p.parse_args()

    bg = Image.open(args.background).convert("RGB")
    canvas = ImageOps.fit(bg, SIZE, method=Image.Resampling.LANCZOS).convert("RGBA")

    overlay = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    px = overlay.load()
    for x in range(SIZE[0]):
        t = max(0.0, 1.0 - x / (SIZE[0] * 0.64))
        alpha = int(255 * args.overlay * t * t)
        for y in range(SIZE[1]):
            px[x, y] = (0, 0, 0, alpha)
    canvas = Image.alpha_composite(canvas, overlay)
    draw = ImageDraw.Draw(canvas)

    title_font = ImageFont.truetype(args.font or find_font(True), 48)
    sub_font = ImageFont.truetype(args.subtitle_font or find_font(False), 20)
    lines = wrap(draw, args.title, title_font, 405)
    line_h = 62
    total_h = len(lines) * line_h + (34 if args.subtitle else 0)
    y = max(44, (SIZE[1] - total_h) // 2)
    x = 48
    for i, line in enumerate(lines):
        color = args.accent if i == len(lines) - 1 and len(lines) > 1 else (255, 255, 255)
        draw.text((x, y), line, font=title_font, fill=color, stroke_width=1, stroke_fill=(0, 0, 0, 110))
        y += line_h
    if args.subtitle:
        draw.text((x, y + 4), args.subtitle, font=sub_font, fill=(230, 230, 230, 230))

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(out, quality=95)


if __name__ == "__main__":
    main()
