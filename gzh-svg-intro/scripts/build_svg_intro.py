"""公众号 SVG 片头动画构建引擎（纯内嵌 SVG + SMIL 1:1 摸鱼小李架构，零 <text>/<image>/<script>/<defs>）。

用法：
1. 作为 Python 模块导入（推荐用于高度定制每一篇文章的专属道具与动作）：
   from svg_intro_kit import FontEngine, load_brand_opener, wrap_stage, save_intro_bundle, smil_opacity, smil_transform, scale_around

2. 作为 CLI 根据分镜 JSON 构建或导出两个已验证范例（console-3act / showcase-4card）：
   python scripts/build_svg_intro.py --spec spec.json --out-svg intro.svg --out-preview preview.html
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import struct

SKILL_ROOT = Path(__file__).resolve().parents[1]
OPENER_ASSET = SKILL_ROOT / "assets" / "brand-opener.svg.frag"
W = 1246
H = 220
DUR = "8s"


def escape_xml(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


class TrueTypeSVG:
    """Zero-dependency TrueType (.ttf/.ttc) outline extractor -> SVG <path>."""

    def __init__(self, path: str | Path, font_index: int = 0):
        self.data = Path(path).read_bytes()
        if self.data[:4] == b"ttcf":
            num_fonts = struct.unpack(">I", self.data[8:12])[0]
            off = struct.unpack(f">{num_fonts}I", self.data[12 : 12 + 4 * num_fonts])[font_index]
        else:
            off = 0
        num_tables = struct.unpack(">H", self.data[off + 4 : off + 6])[0]
        self.tables: dict[str, tuple[int, int]] = {}
        for i in range(num_tables):
            p = off + 12 + i * 16
            tag, _, toff, tlen = struct.unpack(">4sIII", self.data[p : p + 16])
            self.tables[tag.decode("latin1")] = (toff, tlen)
        head_off, _ = self.tables["head"]
        self.upem = struct.unpack(">H", self.data[head_off + 18 : head_off + 20])[0]
        self.idx_fmt = struct.unpack(">h", self.data[head_off + 50 : head_off + 52])[0]
        hhea_off, _ = self.tables["hhea"]
        self.num_hmetrics = struct.unpack(">H", self.data[hhea_off + 34 : hhea_off + 36])[0]
        maxp_off, _ = self.tables["maxp"]
        self.num_glyphs = struct.unpack(">H", self.data[maxp_off + 4 : maxp_off + 6])[0]
        self._load_loca()
        self._load_hmtx()
        self._load_cmap()
        self._cache: dict[int, list[list[tuple[float, float, bool]]]] = {}

    def _load_loca(self) -> None:
        off, _ = self.tables["loca"]
        n = self.num_glyphs + 1
        if self.idx_fmt == 0:
            self.loca = [x * 2 for x in struct.unpack(f">{n}H", self.data[off : off + 2 * n])]
        else:
            self.loca = list(struct.unpack(f">{n}I", self.data[off : off + 4 * n]))

    def _load_hmtx(self) -> None:
        off, _ = self.tables["hmtx"]
        self.adv = []
        for i in range(self.num_hmetrics):
            aw, _ = struct.unpack(">Hh", self.data[off + i * 4 : off + i * 4 + 4])
            self.adv.append(aw)
        last = self.adv[-1] if self.adv else self.upem
        while len(self.adv) < self.num_glyphs:
            self.adv.append(last)

    def _load_cmap(self) -> None:
        off, _ = self.tables["cmap"]
        _, num_sub = struct.unpack(">HH", self.data[off : off + 4])
        sub_off = None
        for i in range(num_sub):
            pid, _, soff = struct.unpack(">HHI", self.data[off + 4 + i * 8 : off + 12 + i * 8])
            fmt = struct.unpack(">H", self.data[off + soff : off + soff + 2])[0]
            if fmt == 12:
                sub_off = off + soff
                break
            if fmt == 4 and pid in (0, 3):
                sub_off = off + soff
        self.cmap: dict[int, int] = {}
        if sub_off is None:
            return
        fmt = struct.unpack(">H", self.data[sub_off : sub_off + 2])[0]
        if fmt == 12:
            num_groups = struct.unpack(">I", self.data[sub_off + 12 : sub_off + 16])[0]
            p = sub_off + 16
            for _ in range(num_groups):
                sc, ec, sg = struct.unpack(">III", self.data[p : p + 12])
                for c in range(sc, ec + 1):
                    self.cmap[c] = sg + (c - sc)
                p += 12
        elif fmt == 4:
            seg_count = struct.unpack(">H", self.data[sub_off + 6 : sub_off + 8])[0] // 2
            p = sub_off + 14
            end_c = struct.unpack(f">{seg_count}H", self.data[p : p + 2 * seg_count])
            p += 2 * seg_count + 2
            start_c = struct.unpack(f">{seg_count}H", self.data[p : p + 2 * seg_count])
            p += 2 * seg_count
            delta = struct.unpack(f">{seg_count}h", self.data[p : p + 2 * seg_count])
            p += 2 * seg_count
            ro_pos = p
            ro = struct.unpack(f">{seg_count}H", self.data[p : p + 2 * seg_count])
            for i in range(seg_count):
                for c in range(start_c[i], end_c[i] + 1):
                    if c == 0xFFFF:
                        continue
                    if ro[i] == 0:
                        gid = (c + delta[i]) & 0xFFFF
                    else:
                        gpos = ro_pos + i * 2 + ro[i] + (c - start_c[i]) * 2
                        gid = struct.unpack(">H", self.data[gpos : gpos + 2])[0]
                        if gid != 0:
                            gid = (gid + delta[i]) & 0xFFFF
                    self.cmap[c] = gid

    def _glyph_contours(self, gid: int) -> list[list[tuple[float, float, bool]]]:
        if gid in self._cache:
            return self._cache[gid]
        glyf_off, _ = self.tables["glyf"]
        s, e = self.loca[gid], self.loca[gid + 1]
        if s == e:
            self._cache[gid] = []
            return []
        p = glyf_off + s
        num_c = struct.unpack(">h", self.data[p : p + 2])[0]
        p += 10
        if num_c >= 0:
            ends = struct.unpack(f">{num_c}H", self.data[p : p + 2 * num_c])
            p += 2 * num_c
            inst_len = struct.unpack(">H", self.data[p : p + 2])[0]
            p += 2 + inst_len
            num_pts = ends[-1] + 1
            flags: list[int] = []
            while len(flags) < num_pts:
                fl = self.data[p]
                p += 1
                flags.append(fl)
                if fl & 8:
                    rep = self.data[p]
                    p += 1
                    flags.extend([fl] * rep)
            xs, ys = [], []
            x = 0
            for fl in flags:
                if fl & 2:
                    dx = self.data[p]
                    p += 1
                    x += dx if (fl & 16) else -dx
                elif not (fl & 16):
                    x += struct.unpack(">h", self.data[p : p + 2])[0]
                    p += 2
                xs.append(x)
            y = 0
            for fl in flags:
                if fl & 4:
                    dy = self.data[p]
                    p += 1
                    y += dy if (fl & 32) else -dy
                elif not (fl & 32):
                    y += struct.unpack(">h", self.data[p : p + 2])[0]
                    p += 2
                ys.append(y)
            contours = []
            start = 0
            for end in ends:
                contours.append([(xs[i], ys[i], bool(flags[i] & 1)) for i in range(start, end + 1)])
                start = end + 1
            self._cache[gid] = contours
            return contours
        else:
            contours = []
            while True:
                fl, cgid = struct.unpack(">HH", self.data[p : p + 4])
                p += 4
                if fl & 2:
                    if fl & 1:
                        dx, dy = struct.unpack(">hh", self.data[p : p + 4])
                        p += 4
                    else:
                        dx, dy = struct.unpack(">bb", self.data[p : p + 2])
                        p += 2
                else:
                    dx = dy = 0
                    p += 4 if (fl & 1) else 2
                a, b, c, d = 1.0, 0.0, 0.0, 1.0
                if fl & 8:
                    a = d = struct.unpack(">h", self.data[p : p + 2])[0] / 16384.0
                    p += 2
                elif fl & 64:
                    a, d = [v / 16384.0 for v in struct.unpack(">hh", self.data[p : p + 4])]
                    p += 4
                elif fl & 128:
                    a, b, c, d = [v / 16384.0 for v in struct.unpack(">hhhh", self.data[p : p + 8])]
                    p += 8
                for sub in self._glyph_contours(cgid):
                    contours.append([(a * x + c * y + dx, b * x + d * y + dy, on) for x, y, on in sub])
                if not (fl & 32):
                    break
            self._cache[gid] = contours
            return contours

    def text_to_path(self, text: str, size: float, x: float, y: float, fill: str) -> str:
        scale = size / self.upem
        cx = x
        cmds: list[str] = []

        def fmt(v: float) -> str:
            s = f"{v:.1f}".rstrip("0").rstrip(".")
            return "0" if s in ("-0", "") else s

        for ch in text:
            gid = self.cmap.get(ord(ch), 0)
            for contour in self._glyph_contours(gid):
                if not contour:
                    continue
                pts = [(cx + px * scale, y - py * scale, on) for px, py, on in contour]
                n = len(pts)
                if not pts[0][2]:
                    if pts[-1][2]:
                        pts = [pts[-1]] + pts[:-1]
                    else:
                        mx, my = (pts[0][0] + pts[-1][0]) / 2, (pts[0][1] + pts[-1][1]) / 2
                        pts = [(mx, my, True)] + pts
                        n = len(pts)
                cmds.append(f"M{fmt(pts[0][0])} {fmt(pts[0][1])}")
                i = 1
                while i < n:
                    px, py, on = pts[i]
                    if on:
                        cmds.append(f"L{fmt(px)} {fmt(py)}")
                        i += 1
                    else:
                        nx, ny, non = pts[(i + 1) % n]
                        if non:
                            cmds.append(f"Q{fmt(px)} {fmt(py)} {fmt(nx)} {fmt(ny)}")
                            i += 2
                        else:
                            mx, my = (px + nx) / 2, (py + ny) / 2
                            cmds.append(f"Q{fmt(px)} {fmt(py)} {fmt(mx)} {fmt(my)}")
                            i += 1
                cmds.append("Z")
            cx += self.adv[gid] * scale
        return f'<path d="{"".join(cmds)}" fill="{fill}"/>' if cmds else ""

    def text_to_char_paths(
        self, text: str, size: float, x: float, y: float, fill: str
    ) -> list[tuple[str, float, float]]:
        """逐字输出闭合 <path> 及其中心锚点 (path_tag, cx, cy)，用于 SplitText 错峰动效。"""
        scale = size / self.upem
        cx = x
        cy = y - size * 0.36
        out: list[tuple[str, float, float]] = []
        for ch in text:
            gid = self.cmap.get(ord(ch), 0)
            adv_w = self.adv[gid] * scale
            tag = self.text_to_path(ch, size, cx, y, fill)
            if tag:
                out.append((tag, round(cx + adv_w * 0.5, 1), round(cy, 1)))
            cx += adv_w
        return out


class FontEngine:
    """Automatic Chinese TrueType font loader (supports Bold and Regular)."""

    def __init__(self, bold_path: str | None = None, regular_path: str | None = None):
        windir = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        bold_candidates = [
            bold_path,
            windir / "msyhbd.ttc",
            windir / "simhei.ttf",
            "/System/Library/Fonts/PingFang.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        ]
        reg_candidates = [
            regular_path,
            windir / "msyh.ttc",
            windir / "simhei.ttf",
            "/System/Library/Fonts/PingFang.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        ]
        b_file = next((Path(p) for p in bold_candidates if p and Path(p).is_file()), None)
        r_file = next((Path(p) for p in reg_candidates if p and Path(p).is_file()), b_file)
        if not b_file:
            raise FileNotFoundError("未找到可用的中文字体（如 msyhbd.ttc / simhei.ttf）")
        self.bold_font = TrueTypeSVG(b_file)
        self.reg_font = TrueTypeSVG(r_file) if r_file else self.bold_font

    def text(self, text: str, size: float, x: float, y: float, fill: str, bold: bool = True) -> str:
        font = self.bold_font if bold else self.reg_font
        return font.text_to_path(text, size, x, y, fill)

    def chars(
        self, text: str, size: float, x: float, y: float, fill: str, bold: bool = True
    ) -> list[tuple[str, float, float]]:
        font = self.bold_font if bold else self.reg_font
        return font.text_to_char_paths(text, size, x, y, fill)


# ─── SMIL 动画原语与常用物理反馈组件 ───

def smil_opacity(values: str, key_times: str, dur: str = DUR) -> str:
    return f'<animate attributeName="opacity" values="{values}" keyTimes="{key_times}" dur="{dur}" repeatCount="indefinite"/>'


def smil_attr(
    attr: str,
    values: str,
    key_times: str,
    spline: str = "0.45 0 0.55 1",
    dur: str = DUR,
) -> str:
    """通用属性 SMIL 补间（支持 points/width/height/x/y/r/fill/stroke-dashoffset）。"""
    segs = len(key_times.split(";")) - 1
    splines = ";".join([spline] * segs)
    return (
        f'<animate attributeName="{attr}" values="{values}" keyTimes="{key_times}" '
        f'dur="{dur}" repeatCount="indefinite" calcMode="spline" keySplines="{splines}"/>'
    )


def smil_stroke_draw(
    length: float,
    t_start: float,
    t_end: float,
    dur: str = DUR,
    reverse: bool = False,
    spline: str = "0.23 1 0.32 1",
    erase_start: float | None = None,
    erase_end: float | None = None,
) -> str:
    """生成 stroke-dashoffset 描边生长动画，可选后半程反向擦除实现转场退场。"""
    v0 = 0 if reverse else length
    v1 = length if reverse else 0
    if erase_start is not None and erase_end is not None:
        v2 = -length if not reverse else length
        kt = f"0;{t_start:.3f};{t_end:.3f};{erase_start:.3f};{erase_end:.3f};1"
        vals = f"{v0:.1f};{v0:.1f};{v1:.1f};{v1:.1f};{v2:.1f};{v2:.1f}"
    else:
        kt = f"0;{t_start:.3f};{t_end:.3f};1"
        vals = f"{v0:.1f};{v0:.1f};{v1:.1f};{v1:.1f}"
    return smil_attr("stroke-dashoffset", vals, kt, spline=spline, dur=dur)


def smil_transform(
    kind: str,
    values: str,
    key_times: str,
    spline: str = "0.23 1 0.32 1",
    dur: str = DUR,
) -> str:
    segs = len(key_times.split(";")) - 1
    splines = ";".join([spline] * segs)
    return (
        f'<animateTransform attributeName="transform" type="{kind}" values="{values}" '
        f'keyTimes="{key_times}" dur="{dur}" repeatCount="indefinite" '
        f'calcMode="spline" keySplines="{splines}"/>'
    )


def scale_around(
    cx: float,
    cy: float,
    values: str,
    key_times: str,
    inner: str,
    spline: str = "0.23 1 0.32 1",
    dur: str = DUR,
) -> str:
    return (
        f'<g transform="translate({cx} {cy})"><g>'
        f'{smil_transform("scale", values, key_times, spline, dur=dur)}'
        f'<g transform="translate({-cx} {-cy})">{inner}</g></g></g>'
    )


def rotate_around(
    cx: float,
    cy: float,
    values: str,
    key_times: str,
    inner: str,
    spline: str = "0.23 1 0.32 1",
    dur: str = DUR,
) -> str:
    """围绕中心点 (cx, cy) 做旋转动画。"""
    return (
        f'<g transform="translate({cx} {cy})"><g>'
        f'{smil_transform("rotate", values, key_times, spline, dur=dur)}'
        f'<g transform="translate({-cx} {-cy})">{inner}</g></g></g>'
    )


def skew_around(
    axis: str,
    cx: float,
    cy: float,
    values: str,
    key_times: str,
    inner: str,
    spline: str = "0.23 1 0.32 1",
    dur: str = DUR,
) -> str:
    """围绕中心点 (cx, cy) 做 2.5D 轴测斜切动画（skewX / skewY）。"""
    return (
        f'<g transform="translate({cx} {cy})"><g>'
        f'{smil_transform(axis, values, key_times, spline, dur=dur)}'
        f'<g transform="translate({-cx} {-cy})">{inner}</g></g></g>'
    )


def perspective_grid(
    cx: float,
    y_horizon: float,
    y_bottom: float,
    top_w: float,
    bot_w: float,
    cols: int = 6,
    rows: int = 4,
    stroke: str = "#CBD5E1",
) -> str:
    """生成纯矢量 3D 透视地面网格（无 <defs>）。"""
    lines: list[str] = []
    for i in range(cols + 1):
        t = i / cols - 0.5
        x1 = cx + t * top_w
        x2 = cx + t * bot_w
        lines.append(f'<line x1="{x1:.1f}" y1="{y_horizon:.1f}" x2="{x2:.1f}" y2="{y_bottom:.1f}" stroke="{stroke}" stroke-width="1"/>')
    for j in range(rows + 1):
        p = (j / rows) ** 1.35
        y = y_horizon + p * (y_bottom - y_horizon)
        w = top_w + p * (bot_w - top_w)
        lines.append(f'<line x1="{cx - w / 2:.1f}" y1="{y:.1f}" x2="{cx + w / 2:.1f}" y2="{y:.1f}" stroke="{stroke}" stroke-width="1"/>')
    return "".join(lines)


def check_badge(cx: float, cy: float, r: float, t_appear: float, dur: str = DUR) -> str:
    t1 = f"{t_appear:.3f}"
    t2 = f"{t_appear + 0.025:.3f}"
    t3 = f"{t_appear + 0.045:.3f}"
    s = r / 11.0
    inner = (
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="#10B981" stroke="#FFFFFF" stroke-width="{2 * s:.1f}"/>'
        f'<path d="M{cx - 4.5 * s:.1f} {cy:.1f}l{3 * s:.1f} {3.2 * s:.1f}l{6.5 * s:.1f}-{6.5 * s:.1f}" '
        f'fill="none" stroke="#FFFFFF" stroke-width="{2.4 * s:.1f}" stroke-linecap="round" stroke-linejoin="round"/>'
    )
    return scale_around(cx, cy, "0;0;1.28;1;1", f"0;{t1};{t2};{t3};1", inner, dur=dur)


def launch_recoil(
    cx: float,
    cy: float,
    inner: str,
    t_shake: float = 0.68,
    t_recoil: float = 0.74,
    t_launch: float = 0.85,
    dx: float = 980.0,
    dy: float = 0.0,
    recoil_dx: float = -26.0,
    dur: str = DUR,
) -> str:
    """三段式物理发射：高频微震 -> 后坐挤压蓄力 -> 加速拉伸冲出（参考摸鱼小李火箭发射）。"""
    ts = [t_shake, t_shake + 0.01, t_shake + 0.02, t_shake + 0.03, t_shake + 0.04, t_recoil, t_launch]
    tr_vals = f"0 0;0 0;0 -1.6;0 1.6;0 -1.6;0 0;{recoil_dx:.1f} 0;{dx:.1f} {dy:.1f};{dx:.1f} {dy:.1f}"
    tr_kt = f"0;{ts[0]:.3f};{ts[1]:.3f};{ts[2]:.3f};{ts[3]:.3f};{ts[4]:.3f};{ts[5]:.3f};{ts[6]:.3f};1"
    tr_sp = "0.45 0 0.55 1;0 0 1 1;0 0 1 1;0 0 1 1;0 0 1 1;0.23 1 0.32 1;0.55 0 0.85 0.45;0.45 0 0.55 1"
    sc_vals = "1 1;1 1;.94 1.07;1.1 .93;1.1 .93"
    sc_kt = f"0;{ts[4]:.3f};{ts[5]:.3f};{ts[6]:.3f};1"
    return (
        f'<g><animateTransform attributeName="transform" type="translate" values="{tr_vals}" '
        f'keyTimes="{tr_kt}" dur="{dur}" repeatCount="indefinite" calcMode="spline" keySplines="{tr_sp}"/>'
        f'<g transform="translate({cx} {cy})"><g>'
        f'{smil_transform("scale", sc_vals, sc_kt, spline="0.23 1 0.32 1", dur=dur)}'
        f'<g transform="translate({-cx} {-cy})">{inner}</g></g></g></g>'
    )


def particle_fountain(
    ox: float,
    oy: float,
    particles: list[tuple[str, float, float, float]],
    t_start: float = 0.28,
    step: float = 0.015,
    span: float = 0.10,
    dur: str = DUR,
) -> str:
    """多段抛物线粒子喷泉：particles 每项为 (inner_svg, dx, dy_peak, dy_end)。"""
    out: list[str] = []
    for idx, (inner, dx, dy_peak, dy_end) in enumerate(particles):
        t0 = t_start + idx * step
        t1 = t0 + span * 0.5
        t2 = min(0.87, t0 + span)
        kt = f"0;{t0:.3f};{t1:.3f};{t2:.3f};1"
        vals = f"0 0;0 0;{dx * 0.55:.1f} {dy_peak:.1f};{dx:.1f} {dy_end:.1f};{dx:.1f} {dy_end:.1f}"
        op = smil_opacity("0;0;1;1;0;0", f"0;{t0:.3f};{t0 + 0.01:.3f};{max(t2, 0.84):.3f};0.88;1", dur=dur)
        out.append(
            f'<g transform="translate({ox} {oy})" opacity="0">{op}'
            f'<g>{smil_transform("translate", vals, kt, spline="0.23 1 0.32 1", dur=dur)}{inner}</g></g>'
        )
    return "".join(out)


def stagger_bounce(
    items: list[str],
    t_start: float = 0.62,
    step: float = 0.025,
    jump: float = -6.4,
    dur: str = DUR,
) -> str:
    """队列错峰波浪弹跳：适合多角色/多图标依次轻跳收尾。"""
    out: list[str] = []
    for idx, inner in enumerate(items):
        t0 = t_start + idx * step
        t1 = t0 + 0.024
        t2 = min(0.87, t0 + 0.05)
        kt = f"0;{t0:.3f};{t1:.3f};{t2:.3f};1"
        vals = f"0 0;0 0;0 {jump:.1f};0 0;0 0"
        out.append(f'<g>{smil_transform("translate", vals, kt, spline="0.23 1 0.32 1", dur=dur)}{inner}</g>')
    return "".join(out)


def ripple_pulse(
    cx: float,
    cy: float,
    r_start: float = 8.0,
    r_end: float = 34.0,
    t_hit: float = 0.40,
    span: float = 0.14,
    color: str = "#10B981",
    dur: str = DUR,
) -> str:
    """节点命中/落地瞬间的同心圆波纹扩散（animate:r + opacity）。"""
    t1 = min(0.88, t_hit + span)
    kt = f"0;{t_hit:.3f};{t1:.3f};1"
    r_anim = smil_attr("r", f"{r_start:.1f};{r_start:.1f};{r_end:.1f};{r_end:.1f}", kt, spline="0.23 1 0.32 1", dur=dur)
    op_anim = smil_opacity("0;0;.65;0;0", f"0;{max(0.0, t_hit - 0.005):.3f};{t_hit:.3f};{t1:.3f};1", dur=dur)
    return f'<circle cx="{cx}" cy="{cy}" r="{r_start:.1f}" fill="none" stroke="{color}" stroke-width="2" opacity="0">{r_anim}{op_anim}</circle>'


def smil_motion(
    path_d: str,
    inner: str,
    t_start: float = 0.28,
    t_end: float = 0.56,
    rotate: str = "auto",
    dur: str = DUR,
) -> str:
    """沿任意 SVG 贝塞尔路径做 <animateMotion> 轨迹运动（保持循环同步）。"""
    kt = f"0;{t_start:.3f};{t_end:.3f};1"
    kp = "0;0;1;1"
    sp = "0.45 0 0.55 1;0.23 1 0.32 1;0.45 0 0.55 1"
    op = smil_opacity("0;0;1;1;0;0", f"0;{t_start:.3f};{t_start + 0.015:.3f};{t_end:.3f};{min(0.90, t_end + 0.02):.3f};1", dur=dur)
    return (
        f'<g opacity="0">{op}'
        f'<animateMotion path="{path_d}" keyPoints="{kp}" keyTimes="{kt}" '
        f'dur="{dur}" repeatCount="indefinite" calcMode="spline" keySplines="{sp}" rotate="{rotate}"/>'
        f'{inner}</g>'
    )


def split_text_stagger(
    chars: list[tuple[str, float, float]],
    t_start: float = 0.28,
    step: float = 0.018,
    mode: str = "pop",
    dur: str = DUR,
) -> str:
    """GSAP SplitText 风格逐字错峰动画：支持 pop（过冲弹出）/ rise（上浮显影）/ wave（波浪轻跳）。"""
    out: list[str] = []
    for idx, (tag, cx, cy) in enumerate(chars):
        t0 = min(0.82, t_start + idx * step)
        t1 = min(0.85, t0 + 0.03)
        t2 = min(0.88, t0 + 0.06)
        if mode == "rise":
            op = smil_opacity("0;0;1;1", f"0;{t0:.3f};{t2:.3f};1", dur=dur)
            tr = smil_transform("translate", "0 16;0 16;0 -3;0 0;0 0", f"0;{t0:.3f};{t1:.3f};{t2:.3f};1", dur=dur)
            out.append(f'<g opacity="0">{op}<g>{tr}{tag}</g></g>')
        elif mode == "wave":
            tr = smil_transform("translate", "0 0;0 0;0 -8;0 0;0 0", f"0;{t0:.3f};{t1:.3f};{t2:.3f};1", dur=dur)
            out.append(f'<g>{tr}{tag}</g>')
        else:
            op = smil_opacity("0;0;1;1", f"0;{t0:.3f};{t1:.3f};1", dur=dur)
            sc = scale_around(cx, cy, "0;0;1.26;1;1", f"0;{t0:.3f};{t1:.3f};{t2:.3f};1", tag, dur=dur)
            out.append(f'<g opacity="0">{op}{sc}</g>')
    return "".join(out)


def resample_ring(pts: list[tuple[float, float]], n: int = 24) -> list[tuple[float, float]]:
    """将任意闭合顶点环等弧长重采样为固定 n 个点，用于纯 SMIL MorphSVG 变形。"""
    import math

    closed = list(pts) + [pts[0]]
    dists = [0.0]
    for i in range(len(pts)):
        dx = closed[i + 1][0] - closed[i][0]
        dy = closed[i + 1][1] - closed[i][1]
        dists.append(dists[-1] + math.hypot(dx, dy))
    total = dists[-1] or 1.0
    out: list[tuple[float, float]] = []
    seg = 0
    for k in range(n):
        target = (k / n) * total
        while seg < len(pts) - 1 and dists[seg + 1] < target:
            seg += 1
        span = (dists[seg + 1] - dists[seg]) or 1.0
        t = (target - dists[seg]) / span
        x = closed[seg][0] + t * (closed[seg + 1][0] - closed[seg][0])
        y = closed[seg][1] + t * (closed[seg + 1][1] - closed[seg][1])
        out.append((round(x, 1), round(y, 1)))
    return out


def morph_d(
    rings: list[list[tuple[float, float]]],
    key_times: str,
    fill: str,
    stroke: str = "none",
    stroke_width: float = 0,
    n_points: int = 24,
    spline: str = "0.45 0 0.55 1",
    dur: str = DUR,
) -> str:
    """GSAP MorphSVG 风格纯 SMIL 路径变形：预对齐锚点数后通过 animate attributeName='d' 补间。"""
    paths = []
    for ring in rings:
        sampled = resample_ring(ring, n_points)
        d = "M" + " L".join(f"{x} {y}" for x, y in sampled) + " Z"
        paths.append(d)
    anim = smil_attr("d", ";".join(paths), key_times, spline=spline, dur=dur)
    sw = f' stroke-width="{stroke_width}"' if stroke_width else ""
    return f'<path d="{paths[0]}" fill="{fill}" stroke="{stroke}"{sw}>{anim}</path>'


def bounce_drop(
    cx: float,
    cy: float,
    inner: str,
    y_from: float = -56.0,
    t_start: float = 0.28,
    dur: str = DUR,
) -> str:
    """GSAP CustomBounce 风格多段衰减落地弹跳（含触地挤压拉伸）。"""
    ts = [t_start, t_start + 0.06, t_start + 0.085, t_start + 0.12, t_start + 0.145, t_start + 0.17]
    tr_vals = f"0 {y_from:.1f};0 {y_from:.1f};0 0;0 -14;0 0;0 -4;0 0;0 0"
    tr_kt = f"0;{ts[0]:.3f};{ts[1]:.3f};{ts[2]:.3f};{ts[3]:.3f};{ts[4]:.3f};{ts[5]:.3f};1"
    tr_sp = ";".join(["0.45 0 0.55 1", "0.55 0 0.85 0.45", "0.23 1 0.32 1", "0.55 0 0.85 0.45", "0.23 1 0.32 1", "0.55 0 0.85 0.45", "0.45 0 0.55 1"])
    sc_vals = "1 1;1 1;1.18 .84;.95 1.06;1.06 .95;1 1;1 1"
    sc_kt = f"0;{ts[0]:.3f};{ts[1]:.3f};{ts[2]:.3f};{ts[3]:.3f};{ts[5]:.3f};1"
    op = smil_opacity("0;0;1;1", f"0;{t_start:.3f};{t_start + 0.015:.3f};1", dur=dur)
    return (
        f'<g opacity="0">{op}'
        f'<g><animateTransform attributeName="transform" type="translate" values="{tr_vals}" '
        f'keyTimes="{tr_kt}" dur="{dur}" repeatCount="indefinite" calcMode="spline" keySplines="{tr_sp}"/>'
        f'{scale_around(cx, cy, sc_vals, sc_kt, inner, dur=dur)}</g></g>'
    )


def grid_stagger(
    cx: float,
    cy: float,
    cols: int = 7,
    rows: int = 5,
    gap: float = 18.0,
    r: float = 4.2,
    color: str = "#38BDF8",
    t_start: float = 0.28,
    step: float = 0.032,
    dur: str = DUR,
) -> str:
    """Anime.js v4 gridStagger(from:'center') 风格：按欧氏距离从中心向外辐射脉冲点阵。"""
    import math

    mx, my = (cols - 1) / 2.0, (rows - 1) / 2.0
    out: list[str] = []
    for row in range(rows):
        for col in range(cols):
            px = cx + (col - mx) * gap
            py = cy + (row - my) * gap
            dist = math.hypot(col - mx, row - my)
            t0 = min(0.80, t_start + dist * step)
            t1 = min(0.84, t0 + 0.04)
            t2 = min(0.88, t0 + 0.09)
            kt = f"0;{t0:.3f};{t1:.3f};{t2:.3f};1"
            dot = f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{r:.1f}" fill="{color}"/>'
            out.append(scale_around(px, py, ".5;.5;1.45;.85;.85", kt, dot, dur=dur))
    return "".join(out)


def radial_dial(
    cx: float,
    cy: float,
    r: float = 54.0,
    segments: list[tuple[str, str]] | None = None,
    t_start: float = 0.28,
    dur: str = DUR,
) -> str:
    """Anime.js v4 精密表盘：径向刻度圈 + 分段彩色弧顺时针点亮。"""
    import math

    segs = segments or [
        ("#F43F5E", "A"),
        ("#F97316", "B"),
        ("#EAB308", "C"),
        ("#22C55E", "D"),
        ("#06B6D4", "E"),
        ("#3B82F6", "F"),
    ]
    ticks = []
    for i in range(24):
        ang = math.radians(i * 15)
        r1 = r - 8
        r2 = r - 2 if i % 2 == 0 else r - 5
        x1, y1 = cx + r1 * math.cos(ang), cy + r1 * math.sin(ang)
        x2, y2 = cx + r2 * math.cos(ang), cy + r2 * math.sin(ang)
        ticks.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#64748B" stroke-width="1.4"/>')

    arcs = []
    n = len(segs)
    span_deg = 360.0 / n
    arc_r = r + 7
    for idx, (col, _) in enumerate(segs):
        a0 = math.radians(-90 + idx * span_deg + 4)
        a1 = math.radians(-90 + (idx + 1) * span_deg - 4)
        x0, y0 = cx + arc_r * math.cos(a0), cy + arc_r * math.sin(a0)
        x1, y1 = cx + arc_r * math.cos(a1), cy + arc_r * math.sin(a1)
        d = f"M{x0:.1f} {y0:.1f} A{arc_r:.1f} {arc_r:.1f} 0 0 1 {x1:.1f} {y1:.1f}"
        t0 = min(0.82, t_start + idx * 0.05)
        t1 = min(0.86, t0 + 0.04)
        arcs.append(
            f'<path d="{d}" fill="none" stroke="{col}" stroke-width="4" stroke-linecap="round" opacity=".2">'
            f'{smil_opacity(".2;.2;1;1", f"0;{t0:.3f};{t1:.3f};1", dur=dur)}</path>'
        )
    return f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#334155" stroke-width="1.5"/>{"".join(ticks)}{"".join(arcs)}'


def spring_oscillate(
    axis: str,
    inner: str,
    target: float = 0.0,
    amp: float = 28.0,
    t_start: float = 0.30,
    dur: str = DUR,
) -> str:
    """Anime.js v4 createSpring 风格：围绕目标值做正负衰减阻尼震荡归位。"""
    pts = [target + amp * 1.0, target - amp * 0.48, target + amp * 0.22, target - amp * 0.08, target]
    ts = [t_start, t_start + 0.08, t_start + 0.14, t_start + 0.20, t_start + 0.26, min(0.90, t_start + 0.32)]
    if axis == "rotate":
        vals = ";".join([f"{pts[0]:.1f}", f"{pts[0]:.1f}"] + [f"{v:.1f}" for v in pts[1:]] + [f"{target:.1f}"])
        kt = f"0;{';'.join(f'{t:.3f}' for t in ts)};1"
        return f'<g>{smil_transform("rotate", vals, kt, spline="0.45 0 0.55 1", dur=dur)}{inner}</g>'
    fmt = (lambda v: f"{v:.1f} 0") if axis == "x" else (lambda v: f"0 {v:.1f}")
    vals = ";".join([fmt(pts[0]), fmt(pts[0])] + [fmt(v) for v in pts[1:]] + [fmt(target)])
    kt = f"0;{';'.join(f'{t:.3f}' for t in ts)};1"
    return f'<g>{smil_transform("translate", vals, kt, spline="0.45 0 0.55 1", dur=dur)}{inner}</g>'


def load_brand_opener(dur: str = DUR) -> str:
    """加载预烘焙的「像素梦哥 + 16 组点阵字坍缩粒子」固定母版片段，支持同步主周期 dur。"""
    frag = OPENER_ASSET.read_text(encoding="utf-8")
    if dur != DUR:
        frag = frag.replace(f'dur="{DUR}"', f'dur="{dur}"')
    return frag


def wrap_stage(stage_inner: str, dur: str = DUR) -> str:
    """包一层主舞台 0.22 淡入、0.88 淡出控制器。"""
    return (
        f'<g opacity="0">'
        f'{smil_opacity("0;0;1;1;0;0", "0;.22;.26;.88;.91;1", dur=dur)}'
        f"{stage_inner}</g>"
    )


def assemble_svg(stage_svg: str, aria_label: str, dur: str = DUR) -> str:
    """将主舞台与品牌开场母版组装为完整的 1246×220 纯 SVG+SMIL 源码。"""
    opener = load_brand_opener(dur=dur)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
        f'preserveAspectRatio="xMidYMid meet" role="img" aria-label="{escape_xml(aria_label)}" '
        f'style="display:block;width:100%;height:auto;max-width:{W}px;margin:0 auto;background:transparent;">'
        f"{stage_svg}{opener}</svg>"
    )


def validate_svg_compliance(svg: str) -> list[str]:
    """检查 SVG 是否满足微信公众号内嵌 SMIL 规范（零 text/image/script/defs/foreignObject，含缓动与双周期）。"""
    errors: list[str] = []
    for forbidden in ("text", "image", "script", "foreignObject", "defs", "style"):
        if re.search(rf"<{forbidden}\b", svg, re.I):
            errors.append(f"包含禁止的标签 <{forbidden}>")
    if 'viewBox="0 0 1246 220"' not in svg:
        errors.append('缺少标准 viewBox="0 0 1246 220"')
    if len(re.findall(r"<animate\b", svg)) < 30:
        errors.append("<animate> 数量过少（需包含点阵坍缩与场景显隐）")
    if len(re.findall(r"<animateTransform\b", svg)) < 30:
        errors.append("<animateTransform> 数量过少")
    if 'calcMode="spline"' not in svg:
        errors.append('缺少 calcMode="spline" 缓动曲线')
    return errors


def build_preview_html(svg: str, title: str, stops: list[tuple[float, str]] | None = None) -> str:
    """生成带「一键复制公众号富文本片头」与多时间点定格检视的独立 HTML 预览页。"""
    if not stops:
        stops = [
            (0.5, "品牌口号"),
            (1.55, "粒子坍缩"),
            (2.9, "第一幕"),
            (4.5, "第二幕"),
            (6.5, "收尾打勾"),
        ]
    btns = "\n      ".join(
        f'<button class="sec" onclick="seek({t})">定格 {t}s ({escape_xml(label)})</button>'
        for t, label in stops
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<title>{escape_xml(title)} · SVG 片头预览</title>
<style>
  body {{ font-family: -apple-system, "Microsoft YaHei", sans-serif; background: #f4f6f9; margin: 0; padding: 28px; color: #1e293b; }}
  .wrap {{ max-width: 1280px; margin: 0 auto; }}
  h1 {{ font-size: 20px; margin: 0 0 8px; }}
  p.sub {{ margin: 0 0 18px; color: #64748b; font-size: 14px; }}
  .card {{ background: #fff; border-radius: 14px; padding: 22px; box-shadow: 0 4px 16px rgba(15,23,42,.06); margin-bottom: 20px; }}
  .toolbar {{ display: flex; gap: 10px; align-items: center; margin-bottom: 14px; flex-wrap: wrap; }}
  button {{ background: #1e6fff; color: #fff; border: none; border-radius: 8px; padding: 8px 16px; font-size: 13.5px; font-weight: 600; cursor: pointer; }}
  button.sec {{ background: #e2e8f0; color: #1e293b; }}
  button:hover {{ opacity: .92; }}
  .status {{ font-size: 13px; color: #10b981; font-weight: 600; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>{escape_xml(title)}</h1>
  <p class="sub">1246×220 · 8s 循环 · 纯内嵌 SVG + SMIL（零 &lt;text&gt;、零 &lt;image&gt;、零 &lt;script&gt;、零 &lt;defs&gt;）</p>
  <div class="card">
    <div class="toolbar">
      <button onclick="copyWechat()">一键复制片头（可直接 Ctrl+V 粘贴到公众号后台）</button>
      <button class="sec" onclick="seek(null)">正常循环播放</button>
      {btns}
      <span id="msg" class="status"></span>
    </div>
    <div id="wechat-clip" style="background:#ffffff;padding:4px 0;">{svg}</div>
  </div>
</div>
<script>
function seek(t) {{
  const s = document.querySelector('#wechat-clip svg');
  if (t === null) {{ s.unpauseAnimations(); document.getElementById('msg').textContent = '已恢复循环播放'; }}
  else {{ s.pauseAnimations(); s.setCurrentTime(t); document.getElementById('msg').textContent = '已定格在 ' + t + 's'; }}
}}
function copyWechat() {{
  const s = document.querySelector('#wechat-clip svg');
  s.unpauseAnimations();
  const node = document.getElementById('wechat-clip');
  const range = document.createRange();
  range.selectNodeContents(node);
  const sel = window.getSelection();
  sel.removeAllRanges();
  sel.addRange(range);
  document.execCommand('copy');
  sel.removeAllRanges();
  document.getElementById('msg').textContent = '已复制富文本片头！去公众号草稿正文直接 Ctrl+V 即可';
}}
</script>
</body>
</html>"""


def save_intro_bundle(
    svg: str,
    out_svg: str | Path,
    out_preview: str | Path | None = None,
    title: str = "程序员梦哥 · 公众号 SVG 片头",
    stops: list[tuple[float, str]] | None = None,
) -> dict[str, str | int]:
    """校验并落盘 intro.svg 与 preview.html。"""
    errors = validate_svg_compliance(svg)
    if errors:
        raise ValueError("SVG 片头合规检查未通过：" + "；".join(errors))
    svg_path = Path(out_svg).resolve()
    svg_path.parent.mkdir(parents=True, exist_ok=True)
    svg_path.write_text(svg, encoding="utf-8")
    result: dict[str, str | int] = {
        "svg": str(svg_path),
        "bytes": len(svg.encode("utf-8")),
        "animate": len(re.findall(r"<animate\b", svg)),
        "animateTransform": len(re.findall(r"<animateTransform\b", svg)),
    }
    if out_preview:
        prev_path = Path(out_preview).resolve()
        prev_path.parent.mkdir(parents=True, exist_ok=True)
        prev_path.write_text(build_preview_html(svg, title, stops), encoding="utf-8")
        result["preview"] = str(prev_path)
    return result


# ─── 内置模板 A：console-3act（三卡带落槽调校舱 + 右侧伙伴机器人 + 7 格点亮柱） ───
def render_console_3act(spec: dict, fe: FontEngine) -> str:
    console_title = spec.get("console_title", "WorkBuddy 设置")
    console_sub = spec.get("console_subtitle", "7 处关键调校 · 待装填")
    robot_name = spec.get("robot_name", "大黄")
    bubble_text = spec.get("bubble_text", "Boss，越用越懂你！")
    meter_labels = spec.get(
        "meter_labels",
        ["存储路径", "自定义指令", "回复风格", "人设设定", "长期记忆", "记忆与进化", "模型与导入"],
    )
    acts = spec.get(
        "acts",
        [
            {
                "card_label": "存储路径",
                "card_tag": "D盘",
                "color": "#1E6FFF",
                "screen_top": "WorkBuddy · 通用存储",
                "screen_main": "默认路径：C盘 > 迁入 D盘",
                "screen_pill": "释放 C 盘 · 1TB 空间就绪",
                "pill_bg": "#1E3A5F",
                "pill_fg": "#60A5FA",
            },
            {
                "card_label": "指令·风格",
                "card_tag": "务实",
                "color": "#F59E0B",
                "screen_top": "WorkBuddy · 个性化与规范",
                "screen_main": "4条编码准则 + 高效务实风格",
                "screen_pill": "少废话直给结论 · 外科修改",
                "pill_bg": "#3B2F1E",
                "pill_fg": "#FBBF24",
            },
            {
                "card_label": "长期记忆",
                "card_tag": "7/7",
                "color": "#10B981",
                "screen_top": "WorkBuddy · 记忆进化 & 模型",
                "screen_main": "长期记忆 · 沉淀Skill · 省Token",
                "screen_pill": "7/7 设置拉满 · 越用越懂你",
                "pill_bg": "#123E35",
                "pill_fg": "#34D399",
            },
        ],
    )

    timings = [
        {"appear": 0.255, "lift": 0.30, "over": 0.335, "drop": 0.36, "settle": 0.375, "hold": 0.49, "out1": 0.51, "out2": 0.535, "waitY": 36, "stackX": 132, "stackY": 148},
        {"appear": 0.35, "lift": 0.48, "over": 0.515, "drop": 0.54, "settle": 0.555, "hold": 0.67, "out1": 0.69, "out2": 0.715, "waitY": 64, "stackX": 132, "stackY": 98},
        {"appear": 0.365, "lift": 0.66, "over": 0.695, "drop": 0.72, "settle": 0.735, "hold": 0.85, "out1": 0.86, "out2": 0.88, "waitY": 114, "stackX": None, "stackY": None},
    ]

    cards_svg = []
    for act, tm in zip(acts[:3], timings):
        kt = f"0;{tm['appear']};{tm['lift']};{tm['over']};{tm['drop']};{tm['settle']};{tm['hold']};{tm['out1']};{tm['out2']};1"
        if tm["stackX"] is not None:
            vals = f"636 {tm['waitY']};636 {tm['waitY']};620 4;376 4;376 23;376 20;376 20;245 4;{tm['stackX']} {tm['stackY']};{tm['stackX']} {tm['stackY']}"
        else:
            vals = f"636 {tm['waitY']};636 {tm['waitY']};620 4;376 4;376 23;376 20;376 20;376 20;376 20;376 20"
        pins = "".join(f'<rect x="{x}" y="39" width="10" height="6" rx="1.5" fill="#9AA8B8"/>' for x in (16, 36, 56, 76, 96))
        body = (
            f"{pins}"
            f'<rect x="0" y="0" width="130" height="41" rx="8" fill="#EEF2F6" stroke="#7E8FA3" stroke-width="2.5"/>'
            f'<rect x="7" y="6" width="8" height="29" rx="3" fill="{act["color"]}"/>'
            f'<rect x="20" y="6" width="103" height="29" rx="4.5" fill="#FFFFFF" stroke="#CBD4E0" stroke-width="1.6"/>'
            f'{fe.text(act["card_label"], 13.5, 26, 26, "#223042", True)}'
            f'{fe.text(act["card_tag"], 10.5, 95, 25, act["color"], True)}'
        )
        t_pre = f"{tm['appear'] - 0.02:.3f}"
        t_ap = tm["appear"]
        scaled = scale_around(65, 20, ".65;.65;1.06;1;1", f"0;{t_pre};{t_ap};{tm['lift']};1", body)
        cards_svg.append(
            f'<g opacity="0">{smil_opacity("0;0;1;1", f"0;{t_pre};{t_ap};1")}'
            f'<g>{smil_transform("translate", vals, kt)}{scaled}</g></g>'
        )

    screen_init = (
        f'<g opacity="1">{smil_opacity("1;1;0;0", "0;.358;.368;1")}'
        f'{fe.text(console_title, 22, 360, 128, "#FFFFFF", True)}'
        f'{fe.text(console_sub, 12.5, 382, 152, "#94A3B8", False)}</g>'
    )
    act_windows = [
        ("0;.362;.372;.535;.545;1", "0;0;1;1;0;0", 0.38),
        ("0;.542;.552;.715;.725;1", "0;0;1;1;0;0", 0.56),
        ("0;.722;.732;1", "0;0;1;1", 0.74),
    ]
    screens_svg = [screen_init]
    for act, (kt, ov, t_pill) in zip(acts[:3], act_windows):
        pill_inner = (
            f'<rect x="364" y="141" width="164" height="22" rx="11" fill="{act["pill_bg"]}"/>'
            f'{fe.text(act["screen_pill"], 12, 374, 156, act["pill_fg"], True)}'
        )
        screens_svg.append(
            f'<g opacity="0">{smil_opacity(ov, kt)}'
            f'{fe.text(act["screen_top"], 11.5, 342, 102, "#94A3B8", False)}'
            f'{fe.text(act["screen_main"], 15.5, 342, 128, "#FFFFFF", True)}'
            f'{scale_around(446, 154, "0;0;1.22;1;1", f"0;{t_pill};{t_pill + 0.025:.3f};{t_pill + 0.045:.3f};1", pill_inner)}</g>'
        )

    flashes = "".join(
        f'<rect x="330" y="80" width="236" height="94" rx="8" fill="#FFFFFF" opacity="0">'
        f'{smil_opacity("0;0;.82;0;0", f"0;{t};{t + 0.008:.3f};{t + 0.035:.3f};1")}</rect>'
        for t in (0.36, 0.54, 0.72)
    )
    leds = "".join(
        f'<circle cx="{cx}" cy="82" r="5.2" fill="#C6CFD9"/>'
        f'<g opacity="0">{smil_opacity("0;0;1;1", f"0;{t};{t + 0.018:.3f};1")}'
        f'{scale_around(cx, 82, "0;0;1.55;1;1", f"0;{t};{t + 0.018:.3f};{t + 0.036:.3f};1", f"<circle cx=\"{cx}\" cy=\"82\" r=\"5.2\" fill=\"{col}\"/>")}</g>'
        for cx, t, col in ((292, 0.365, acts[0]["color"]), (306, 0.545, acts[1]["color"]), (320, 0.725, acts[2]["color"]))
    )

    console_bounce = smil_transform(
        "translate",
        "0 0;0 0;0 4.5;0 -1;0 0;0 0;0 4.5;0 -1;0 0;0 0;0 4.5;0 -1;0 0;0 0",
        "0;.355;.37;.39;.41;.535;.55;.57;.59;.715;.73;.75;.77;1",
    )
    console_svg = (
        f"<g>{console_bounce}"
        f'<ellipse cx="448" cy="197" rx="168" ry="8" fill="#CBD5E1" opacity=".45"/>'
        f'<rect x="370" y="50" width="156" height="12" rx="5" fill="#64748B"/>'
        f'<rect x="270" y="58" width="356" height="132" rx="26" fill="#F1F5F9" stroke="#7E8FA3" stroke-width="3.2"/>'
        f"{leds}"
        f'<path d="M297 114h12v14h14v12h-14v14h-12v-14h-14v-12h14z" fill="#8291A5"/>'
        f'<rect x="324" y="74" width="248" height="104" rx="12" fill="#475569"/>'
        f'<rect x="330" y="80" width="236" height="92" rx="8" fill="#1E293B"/>'
        f'{"".join(screens_svg)}{flashes}'
        f'<path d="M342 89H400" stroke="#FFFFFF" stroke-opacity=".14" stroke-width="3" stroke-linecap="round"/>'
        f'<circle cx="600" cy="116" r="10.5" fill="#F59E0B" stroke="#7E8FA3" stroke-width="2"/>'
        f'<circle cx="586" cy="140" r="10.5" fill="#10B981" stroke="#7E8FA3" stroke-width="2"/>'
        f'<path d="M580 162v10M589 162v10M598 162v10M607 162v10" stroke="#94A3B8" stroke-width="2.5" stroke-linecap="round"/>'
        f"</g>"
    )

    pulses = "".join(
        f'<g opacity="0">{smil_opacity("0;0;1;1;0;0", f"0;{t};{t + 0.006:.3f};{t + 0.048:.3f};{t + 0.055:.3f};1")}'
        f'<g>{smil_transform("translate", "628 128;628 128;778 128;778 128", f"0;{t};{t + 0.055:.3f};1")}'
        f'<rect x="-14" y="-3.5" width="28" height="7" rx="3.5" fill="{col}" opacity=".35"/>'
        f'<circle cx="6" cy="0" r="6" fill="{col}"/><circle cx="6" cy="0" r="2.8" fill="#FFFFFF"/></g></g>'
        for t, col in ((0.365, acts[0]["color"]), (0.545, acts[1]["color"]), (0.725, acts[2]["color"]))
    )

    meter_times = [0.415, 0.43, 0.595, 0.61, 0.625, 0.775, 0.79]
    meter_cols = [acts[0]["color"], acts[0]["color"], acts[1]["color"], acts[1]["color"], acts[1]["color"], acts[2]["color"], acts[2]["color"]]
    meters = "".join(
        f'<rect x="946" y="{172 - i * 17}" width="26" height="12" rx="4" fill="#E6ECF2" stroke="#9AA8B8" stroke-width="1.6"/>'
        f'<g opacity="0">{smil_opacity("0;0;1;1", f"0;{t};{t + 0.018:.3f};1")}'
        f'{scale_around(959, 178 - i * 17, "0;0;1.28;1;1", f"0;{t};{t + 0.018:.3f};{t + 0.036:.3f};1", f"<rect x=\"946\" y=\"{172 - i * 17}\" width=\"26\" height=\"12\" rx=\"4\" fill=\"{c}\"/>")}</g>'
        f'{fe.text(label, 10.5, 978, 182 - i * 17, "#526275", True)}'
        for i, (t, c, label) in enumerate(zip(meter_times, meter_cols, meter_labels[:7]))
    )

    robot_inner = (
        f'<path d="M848 54V38" stroke="#475569" stroke-width="4" stroke-linecap="round"/>'
        f'<circle cx="848" cy="34" r="7" fill="#F59E0B" stroke="#475569" stroke-width="2.8"/>'
        f'<rect x="774" y="132" width="16" height="40" rx="8" fill="#FBBF24" stroke="#475569" stroke-width="3"/>'
        f'<g>{smil_transform("rotate", "0 912 140;0 912 140;-145 912 140;-115 912 140;-145 912 140;0 912 140", "0;.775;.805;.835;.865;1")}'
        f'<rect x="906" y="132" width="16" height="40" rx="8" fill="#FBBF24" stroke="#475569" stroke-width="3"/></g>'
        f'<rect x="794" y="124" width="108" height="62" rx="18" fill="#FBBF24" stroke="#475569" stroke-width="3.2"/>'
        f'<rect x="814" y="136" width="68" height="28" rx="9" fill="#FFFBEB" stroke="#D97706" stroke-width="2"/>'
        f'{fe.text(robot_name, 15, 833, 156, "#92400E", True)}'
        f'<rect x="814" y="185" width="20" height="9" rx="3.5" fill="#475569"/>'
        f'<rect x="862" y="185" width="20" height="9" rx="3.5" fill="#475569"/>'
        f'<rect x="784" y="52" width="128" height="78" rx="24" fill="#FBBF24" stroke="#475569" stroke-width="3.2"/>'
        f'<rect x="776" y="78" width="9" height="26" rx="4" fill="#64748B"/>'
        f'<rect x="911" y="78" width="9" height="26" rx="4" fill="#64748B"/>'
        f'<rect x="798" y="64" width="100" height="54" rx="14" fill="#1E293B"/>'
        f'<g opacity="1">{smil_opacity("1;1;0;0", "0;.77;.78;1")}'
        f'<rect x="818" y="79" width="13" height="22" rx="6" fill="#34D399"/>'
        f'<rect x="865" y="79" width="13" height="22" rx="6" fill="#34D399"/></g>'
        f'<g opacity="0">{smil_opacity("0;0;1;1", "0;.77;.78;1")}'
        f'<path d="M815 92q10-14 20 0M861 92q10-14 20 0" fill="none" stroke="#34D399" stroke-width="5" stroke-linecap="round"/>'
        f'<path d="M837 103q11 9 22 0" fill="none" stroke="#34D399" stroke-width="4.2" stroke-linecap="round"/>'
        f'<circle cx="809" cy="102" r="4.5" fill="#FB7185" opacity=".85"/>'
        f'<circle cx="887" cy="102" r="4.5" fill="#FB7185" opacity=".85"/></g>'
    )
    robot_squash = scale_around(
        848,
        192,
        "1 1;1 1;1.06 .93;.98 1.04;1 1;1 1;1.06 .93;.98 1.04;1 1;1 1;1.08 .91;.97 1.06;1 1;1 1",
        "0;.41;.425;.445;.465;.59;.605;.625;.645;.77;.785;.805;.828;1",
        robot_inner,
    )
    bubble_inner = (
        f'<rect x="668" y="6" width="166" height="34" rx="17" fill="#10B981"/>'
        f'<path d="M824 38l14 10l-4-14z" fill="#10B981"/>'
        f'{fe.text(bubble_text, 13.5, 686, 28, "#FFFFFF", True)}'
    )
    stage = wrap_stage(
        "".join(cards_svg)
        + console_svg
        + '<path d="M628 128H778" stroke="#CBD5E1" stroke-width="4" stroke-dasharray="7 7" stroke-linecap="round"/>'
        + pulses
        + '<ellipse cx="848" cy="197" rx="58" ry="7" fill="#CBD5E1" opacity=".5"/>'
        + robot_squash
        + meters
        + check_badge(612, 64, 15, 0.785)
        + scale_around(848, 24, "0;0;1.12;1;1", "0;.79;.82;.845;1", bubble_inner)
    )
    aria = spec.get(
        "aria_label",
        f"程序员梦哥，分享AI少踩坑；像素文字变成粒子；{console_title}依次插入三张配置卡并向{robot_name}发射脉冲点亮七格指标，最后弹出对勾与{bubble_text}",
    )
    return assemble_svg(stage, aria)


def render_showcase_4card(spec: dict, fe: FontEngine) -> str:
    """内置模板 B：主机发招 + 连续抛物线弹出 4 张微缩作品卡 + 右侧额度/结论面板（如 Kimi K3.1 Pro 篇）。"""
    host_code = spec.get("host_code", "K3.1")
    host_sub = spec.get("host_sub", "PRO")
    host_foot = spec.get("host_foot", "3万亿参数 · 1M上下文")
    cards = spec.get(
        "cards",
        [
            {"title": "01 布料模拟器", "badge": "褶皱阴影 · 动字不糊", "color": "#1E6FFF", "kind": "cloth"},
            {"title": "02 云海古城 3D", "badge": "4图参考 · 浮岛巨像", "color": "#0284C7", "kind": "island"},
            {"title": "03 卡丁车竞速", "badge": "3圈5对手 · 漂移氮气", "color": "#10B981", "kind": "kart"},
            {"title": "04 纯代码 MV", "badge": "红白几何 · 音乐律动", "color": "#E11D48", "kind": "mv"},
        ],
    )
    panel_good = spec.get("panel_good", "惊喜：4案全通")
    panel_bad = spec.get("panel_bad", "槽点：额度肉疼")
    panel_metric = spec.get("panel_metric", "5 小时用量 (Kimi Code)")
    panel_val = spec.get("panel_val", "76.29%")
    panel_note = spec.get("panel_note", "1个项目干掉 76% 额度 · 肝疼!")
    panel_top = spec.get("panel_top", "国模一哥 K3.1 Pro · 实测过关")

    pc_bounce = smil_transform(
        "translate",
        "0 0;0 0;0 -6;0 4;0 0;0 -6;0 4;0 0;0 -6;0 4;0 0;0 -6;0 4;0 0;0 0",
        "0;.265;.28;.305;.33;.38;.405;.43;.48;.505;.53;.58;.605;.63;1",
    )
    scan_lines = "".join(
        f'<line x1="196" y1="{y}" x2="274" y2="{y}" stroke="#090D16" stroke-width="1.3" opacity=".55"/>'
        for y in (66, 70, 74, 78, 82, 86, 90)
    )
    host_svg = (
        f"<g>{pc_bounce}"
        f'<ellipse cx="236" cy="196" rx="86" ry="7" fill="#CBD5E1" opacity=".55"/>'
        f'{fe.text("KI", 34, 142, 162, "#94A3B8", True)}'
        f'{fe.text("MI", 34, 290, 162, "#94A3B8", True)}'
        f'<rect x="174" y="56" width="18" height="46" rx="5" fill="#949B96" stroke="#475569" stroke-width="2.4"/>'
        f'<rect x="176" y="132" width="116" height="32" rx="6" fill="#B8BEB8" stroke="#475569" stroke-width="2.8"/>'
        f'<line x1="186" y1="142" x2="206" y2="142" stroke="#64748B" stroke-width="2.4" stroke-linecap="round"/>'
        f'<line x1="186" y1="148" x2="206" y2="148" stroke="#64748B" stroke-width="2.4" stroke-linecap="round"/>'
        f'<line x1="186" y1="154" x2="206" y2="154" stroke="#64748B" stroke-width="2.4" stroke-linecap="round"/>'
        f'<rect x="224" y="144" width="32" height="4.5" rx="2" fill="#1E293B"/>'
        f'<rect x="196" y="162" width="88" height="10" rx="3" fill="#D6DBD6" stroke="#475569" stroke-width="2.4"/>'
        f'<rect x="288" y="162" width="18" height="10" rx="4" fill="#D6DBD6" stroke="#475569" stroke-width="2.4"/>'
        f'<rect x="184" y="42" width="102" height="88" rx="12" fill="#D6DBD6" stroke="#475569" stroke-width="3"/>'
        f'<rect x="194" y="52" width="82" height="62" rx="7" fill="#090D16" stroke="#475569" stroke-width="2.2"/>'
        f'<circle cx="272" cy="121" r="2.8" fill="#00C8FF"/>'
        f'<rect x="258" y="119.5" width="8" height="3" rx="1.5" fill="#64748B"/>'
        f'<rect x="200" y="58" width="38" height="3" rx="1.5" fill="#00C8FF" opacity=".85"/>'
        f'<g opacity="0">{smil_opacity("0;0;1;.35;1;1", "0;.23;.26;.275;.29;1")}'
        f'{fe.text(host_code, 22, 202, 82, "#00C8FF", True)}'
        f'{fe.text(host_sub, 14.5, 210, 100, "#38BDF8", True)}</g>'
        f"{scan_lines}"
        f'<rect x="172" y="177" width="128" height="19" rx="9.5" fill="#1E293B"/>'
        f'{fe.text(host_foot, 10.5, 184, 190, "#38BDF8", True)}</g>'
    )

    def card_art(kind: str) -> str:
        if kind == "cloth":
            return (
                '<rect x="9" y="9" width="124" height="88" rx="10" fill="#EFF6FF" stroke="#CBD5E1" stroke-width="1.5"/>'
                '<line x1="16" y1="22" x2="126" y2="22" stroke="#64748B" stroke-width="2"/>'
                '<ellipse cx="72" cy="88" rx="34" ry="4.5" fill="#94A3B8" opacity=".45">'
                '<animate attributeName="cx" values="70;80;66;70" keyTimes="0;.35;.7;1" dur="1.8s" repeatCount="indefinite"/>'
                '<animate attributeName="rx" values="32;38;29;32" keyTimes="0;.35;.7;1" dur="1.8s" repeatCount="indefinite"/></ellipse>'
                f'<g>{smil_transform("skewX", "0;7;-4;0", "0;.35;.7;1", ".45 0 .55 1", "1.8s")}'
                '<path d="M36 22 H106 L110 76 Q92 81 72 74 Q52 67 34 77 Z" fill="#1E293B" stroke="#334155" stroke-width="1.5">'
                '<animate attributeName="d" values="M36 22 H106 L110 76 Q92 81 72 74 Q52 67 34 77 Z;M36 22 H106 L115 73 Q95 66 75 77 Q55 83 39 74 Z;M36 22 H106 L104 77 Q86 82 68 72 Q48 68 31 76 Z;M36 22 H106 L110 76 Q92 81 72 74 Q52 67 34 77 Z" keyTimes="0;.35;.7;1" dur="1.8s" repeatCount="indefinite"/></path>'
                '<path d="M52 28 Q58 50 48 70 M86 28 Q92 50 84 70" fill="none" stroke="#475569" stroke-width="1.6" stroke-linecap="round" opacity=".7"/>'
                '<rect x="52" y="36" width="38" height="24" rx="4" fill="#090D16" stroke="#94A3B8" stroke-width="1.5"/>'
                f'<g><animate attributeName="opacity" values="1;.35;1" keyTimes="0;.5;1" dur="1.2s" repeatCount="indefinite"/>{fe.text(host_code, 10.5, 59, 51, "#00C8FF", True)}</g></g>'
                '<rect x="40" y="17" width="5" height="9" rx="1.5" fill="#F59E0B"/><rect x="97" y="17" width="5" height="9" rx="1.5" fill="#F59E0B"/>'
            )
        if kind == "island":
            return (
                '<rect x="9" y="9" width="124" height="88" rx="10" fill="#DCE7F3" stroke="#CBD5E1" stroke-width="1.5"/>'
                '<g opacity=".85"><animateTransform attributeName="transform" type="translate" values="-4 0;6 0;-4 0" keyTimes="0;.5;1" dur="2.6s" repeatCount="indefinite"/>'
                '<circle cx="28" cy="70" r="16" fill="#FFFFFF"/><circle cx="46" cy="74" r="14" fill="#FFFFFF"/><circle cx="20" cy="56" r="12" fill="#F8FAFC"/></g>'
                '<g><animateTransform attributeName="transform" type="translate" values="0 0;0 -2.5;0 0" keyTimes="0;.5;1" dur="2.4s" repeatCount="indefinite"/>'
                '<path d="M44 64 L124 58 L116 78 L84 86 L52 76 Z" fill="#475569"/><path d="M42 62 L124 56 L112 67 L54 69 Z" fill="#64748B"/>'
                '<path d="M88 22 L96 22 L99 48 L85 48 Z" fill="#CBD5E1" stroke="#64748B" stroke-width="1.2"/><rect x="89" y="16" width="6" height="6" rx="1" fill="#94A3B8"/>'
                '<path d="M56 52 L74 44 L92 52 Z" fill="#1E293B"/><rect x="61" y="52" width="26" height="12" fill="#7F1D1D"/>'
                '<path d="M88 54 L104 48 L118 54 Z" fill="#1E293B"/><rect x="92" y="54" width="22" height="10" fill="#334155"/></g>'
                '<g opacity=".92"><animateTransform attributeName="transform" type="translate" values="5 0;-5 0;5 0" keyTimes="0;.5;1" dur="2.2s" repeatCount="indefinite"/>'
                '<circle cx="38" cy="78" r="15" fill="#FFFFFF"/><circle cx="58" cy="80" r="13" fill="#FFFFFF"/><circle cx="78" cy="82" r="11" fill="#F1F5F9"/><rect x="14" y="76" width="72" height="14" rx="7" fill="#FFFFFF"/></g>'
            )
        if kind == "kart":
            return (
                '<rect x="9" y="9" width="124" height="88" rx="10" fill="#ECFDF5" stroke="#CBD5E1" stroke-width="1.5"/>'
                '<ellipse cx="71" cy="56" rx="48" ry="26" fill="none" stroke="#475569" stroke-width="14"/>'
                '<ellipse cx="71" cy="56" rx="48" ry="26" fill="none" stroke="#F8FAFC" stroke-width="1.6" stroke-dasharray="5 5"/>'
                '<rect x="67" y="23" width="8" height="14" fill="#FFFFFF" stroke="#1E293B" stroke-width="1"/>'
                f'<rect x="15" y="14" width="44" height="15" rx="4" fill="#1E293B"/>{fe.text("LAP 3/3", 8.5, 19, 25, "#34D399", True)}'
                '<g><animateTransform attributeName="transform" type="rotate" values="160 71 56;520 71 56" keyTimes="0;1" dur="2.4s" repeatCount="indefinite"/>'
                '<rect x="65" y="26" width="12" height="7" rx="2.5" fill="#F59E0B" stroke="#1E293B" stroke-width="1.2"/></g>'
                '<g><animateTransform attributeName="transform" type="rotate" values="0 71 56;360 71 56" keyTimes="0;1" dur="1.7s" repeatCount="indefinite"/>'
                '<path d="M52 29 L40 26 L43 32 Z" fill="#00C8FF"><animate attributeName="opacity" values="1;.3;1" keyTimes="0;.5;1" dur="0.3s" repeatCount="indefinite"/></path>'
                '<rect x="52" y="25" width="15" height="9" rx="3" fill="#EF4444" stroke="#1E293B" stroke-width="1.4"/><circle cx="61" cy="29.5" r="2.5" fill="#FEF08A"/></g>'
            )
        bars = "".join(
            f'<rect x="{x}" y="34" width="6.5" height="22" rx="3" fill="{c}">'
            f'<animate attributeName="height" values="{hv}" keyTimes="0;.35;.7;1" dur="{d}" repeatCount="indefinite"/>'
            f'<animate attributeName="y" values="{yv}" keyTimes="0;.35;.7;1" dur="{d}" repeatCount="indefinite"/></rect>'
            for x, hv, yv, d, c in (
                (42, "12;30;14;12", "50;32;48;50", "0.7s", "#EF4444"),
                (54, "24;10;32;24", "38;52;30;38", "0.55s", "#FFFFFF"),
                (66, "32;14;34;32", "30;48;28;30", "0.65s", "#EF4444"),
                (78, "16;32;12;16", "46;30;50;46", "0.6s", "#FFFFFF"),
                (90, "26;12;28;26", "36;50;34;36", "0.75s", "#EF4444"),
            )
        )
        return (
            '<rect x="9" y="9" width="124" height="88" rx="10" fill="#0F172A" stroke="#334155" stroke-width="1.5"/>'
            '<circle cx="71" cy="43" r="24" fill="none" stroke="#EF4444" stroke-width="1.6" stroke-dasharray="8 6" opacity=".65">'
            '<animateTransform attributeName="transform" type="rotate" values="0 71 43;360 71 43" keyTimes="0;1" dur="3s" repeatCount="indefinite"/></circle>'
            f'{bars}{fe.text("world.execute(me)", 9.5, 24, 86, "#F8FAFC", True)}'
        )

    cards_svg = []
    for idx, c in enumerate(cards[:4]):
        tx = 356 + idx * 152
        t_ap = 0.28 + idx * 0.10
        t_pop = f"{t_ap + 0.035:.3f}"
        t_set = f"{t_ap + 0.065:.3f}"
        kt = f"0;{t_ap:.3f};{t_pop};{t_set};1"
        mid_x = round((220 + tx) / 2)
        tr_vals = f"210 52;210 52;{mid_x} 14;{tx} 38;{tx} 38"
        inner = (
            '<rect x="0" y="5" width="142" height="144" rx="16" fill="#DCE4EE"/>'
            '<rect x="0" y="0" width="142" height="144" rx="16" fill="#FFFFFF" stroke="#8291A5" stroke-width="2.6"/>'
            f'{card_art(c.get("kind", "mv"))}'
            f'{fe.text(c["title"], 13, 12, 114, "#1E293B", True)}'
            f'<rect x="10" y="121" width="122" height="17" rx="8.5" fill="{c["color"]}" opacity=".13"/>'
            f'{fe.text(c["badge"], 10.5, 18, 133, c["color"], True)}'
            f'{check_badge(134, 8, 11, t_ap + 0.08)}'
        )
        scaled = scale_around(71, 72, ".35;.35;1.06;1;1", kt, inner)
        cards_svg.append(
            f'<g opacity="0">{smil_opacity("0;0;1;1", f"0;{t_ap - 0.008:.3f};{t_ap + 0.015:.3f};1")}'
            f'<g>{smil_transform("translate", tr_vals, kt)}{scaled}</g></g>'
        )

    top_badge = (
        '<rect x="988" y="4" width="216" height="28" rx="14" fill="#1E293B"/>'
        '<circle cx="1004" cy="18" r="8" fill="#10B981"/>'
        '<path d="M1000.5 18l2.5 2.5l5-5" fill="none" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'
        f'{fe.text(panel_top, 12, 1018, 22, "#FFFFFF", True)}'
    )
    panel_inner = (
        '<rect x="970" y="43" width="252" height="140" rx="16" fill="#DCE4EE"/>'
        '<rect x="970" y="38" width="252" height="140" rx="16" fill="#FFFFFF" stroke="#8291A5" stroke-width="2.6"/>'
        f'<rect x="984" y="50" width="96" height="20" rx="10" fill="#ECFDF5"/>{fe.text(panel_good, 11, 994, 64, "#10B981", True)}'
        f'<rect x="1088" y="50" width="120" height="20" rx="10" fill="#FEF2F2"/>{fe.text(panel_bad, 11, 1098, 64, "#EF4444", True)}'
        f'{fe.text(panel_metric, 11.5, 986, 94, "#64748B", False)}'
        f'{fe.text(panel_val, 20, 1134, 96, "#EF4444", True)}'
        '<rect x="986" y="108" width="220" height="14" rx="7" fill="#E2E8F0"/>'
        '<rect x="986" y="108" width="170" height="14" rx="7" fill="#3B82F6">'
        '<animate attributeName="width" values="18;18;170;170" keyTimes="0;.66;.755;1" dur="8s" repeatCount="indefinite" calcMode="spline" keySplines="0.45 0 0.55 1;0.22 1 0.36 1;0.45 0 0.55 1"/>'
        '<animate attributeName="fill" values="#3B82F6;#3B82F6;#F97316;#EF4444;#EF4444" keyTimes="0;.68;.73;.76;1" dur="8s" repeatCount="indefinite"/></rect>'
        f'<rect x="986" y="134" width="220" height="28" rx="8" fill="#FFF7ED" stroke="#FDBA74" stroke-width="1.5"/>{fe.text(panel_note, 12, 998, 153, "#C2410C", True)}'
        f'{scale_around(1096, 20, "0;0;1.15;1;1", "0;.76;.795;.82;1", top_badge)}'
    )
    panel_svg = (
        f'<g opacity="0">{smil_opacity("0;0;1;1", "0;.62;.65;1")}'
        f'{scale_around(1096, 110, ".75;.75;1.05;1;1", "0;.62;.655;.68;1", panel_inner)}</g>'
    )
    stage = wrap_stage(host_svg + "".join(cards_svg) + panel_svg)
    aria = spec.get(
        "aria_label",
        f"程序员梦哥，分享AI少踩坑；像素文字变成粒子；复古电脑亮起{host_code} {host_sub}并连续弹出四张动态实测卡逐一打勾，右侧{panel_metric}飙到{panel_val}，弹出{panel_note}与{panel_top}",
    )
    return assemble_svg(stage, aria)


# ─── 内置模板 C：pipeline-nodes（无卡片节点连线与光点传输，适合 Agent / 自动化 / 流程） ───
def render_pipeline_nodes(spec: dict, fe: FontEngine) -> str:
    dur = spec.get("dur", "6s")
    source_label = spec.get("source_label", "灵感输入")
    target_label = spec.get("target_label", "自动交付")
    badge_text = spec.get("badge_text", "4 步自动跑通")
    nodes = spec.get(
        "nodes",
        [
            {"label": "拆解意图", "tag": "01", "color": "#1E6FFF"},
            {"label": "工具调用", "tag": "02", "color": "#8B5CF6"},
            {"label": "结果校验", "tag": "03", "color": "#0EA5E9"},
        ],
    )
    coords = [(505, 76), (705, 136), (905, 76)]
    sx, sy = 310, 110
    tx, ty = 1100, 110

    # 源头：发光核心（无矩形外框）
    bulb_inner = (
        f'<circle cx="{sx}" cy="{sy}" r="38" fill="#FEF3C7" opacity=".55">'
        f'{smil_attr("r", "30;30;44;38;38", "0;.26;.32;.38;1", dur=dur)}</circle>'
        f'<circle cx="{sx}" cy="{sy}" r="26" fill="#F59E0B" stroke="#FFFFFF" stroke-width="3"/>'
        f'<path d="M{sx-9} {sy-2}a9 9 0 1 1 18 0c0 4-3 6-4 9h-10c-1-3-4-5-4-9z" fill="#FFFFFF"/>'
        f'<rect x="{sx-5}" y="{sy+9}" width="10" height="4" rx="2" fill="#FEF3C7"/>'
        f'{fe.text(source_label, 13, sx - 26, sy + 56, "#475569", True)}'
    )
    bulb_svg = scale_around(sx, sy, ".6;.6;1.12;1;1", "0;.24;.29;.34;1", bulb_inner, dur=dur)

    # 虚线主路径（分段描边生长）
    pts = [(sx + 34, sy)] + coords + [(tx - 42, ty)]
    links_svg = []
    for i in range(len(pts) - 1):
        x1, y1 = pts[i]
        x2, y2 = pts[i + 1]
        cx_mid = (x1 + x2) / 2
        d = f"M{x1} {y1} C{cx_mid:.1f} {y1} {cx_mid:.1f} {y2} {x2} {y2}"
        t0 = 0.28 + i * 0.10
        t1 = t0 + 0.09
        links_svg.append(
            f'<path d="{d}" fill="none" stroke="#CBD5E1" stroke-width="2.5" stroke-dasharray="6 6"/>'
            f'<path d="{d}" fill="none" stroke="#1E6FFF" stroke-width="3" stroke-linecap="round" stroke-dasharray="260">'
            f'{smil_stroke_draw(260, t0, t1, dur=dur)}</path>'
        )

    # 沿节点跳跃的脉冲光球
    orb_x = ";".join([f"{sx}"] + [f"{x}" for x, _ in coords] + [f"{tx}"])
    orb_y = ";".join([f"{sy}"] + [f"{y}" for _, y in coords] + [f"{ty}"])
    orb_kt = "0;.30;.42;.54;.66;1"
    # translate keyTimes 需要与节点对齐
    orb_vals = f"{sx} {sy};{sx} {sy};{coords[0][0]} {coords[0][1]};{coords[1][0]} {coords[1][1]};{coords[2][0]} {coords[2][1]};{tx} {ty}"
    orb_svg = (
        f'<g opacity="0">{smil_opacity("0;0;1;1;0;0", "0;.28;.31;.68;.73;1", dur=dur)}'
        f'<g>{smil_transform("translate", orb_vals, orb_kt, spline="0.45 0 0.55 1", dur=dur)}'
        f'<circle cx="0" cy="0" r="11" fill="#10B981" opacity=".28"/>'
        f'<circle cx="0" cy="0" r="6" fill="#10B981" stroke="#FFFFFF" stroke-width="2"/></g></g>'
    )

    # 中间 3 个圆形里程碑节点（无卡片）
    nodes_svg = []
    for idx, (nx, ny) in enumerate(coords):
        nd = nodes[idx] if idx < len(nodes) else {"label": f"步骤 {idx+1}", "tag": f"0{idx+1}", "color": "#1E6FFF"}
        t_hit = 0.38 + idx * 0.12
        kt = f"0;{t_hit:.2f};{t_hit+0.03:.2f};{t_hit+0.07:.2f};1"
        label_y = ny - 36 if ny > 110 else ny + 50
        inner = (
            f'<circle cx="{nx}" cy="{ny}" r="26" fill="#FFFFFF" stroke="{nd["color"]}" stroke-width="3"/>'
            f'<circle cx="{nx}" cy="{ny}" r="20" fill="{nd["color"]}" opacity=".12"/>'
            f'{fe.text(nd["tag"], 14, nx - 9, ny + 5, nd["color"], True)}'
            f'{fe.text(nd["label"], 12.5, nx - 26, label_y, "#1E293B", True)}'
        )
        nodes_svg.append(scale_around(nx, ny, ".7;.7;1.22;1;1", kt, inner, dur=dur))

    # 右侧终点：地球/云端交付徽章 + 绿勾
    target_inner = (
        f'<circle cx="{tx}" cy="{ty}" r="38" fill="#ECFDF5" stroke="#10B981" stroke-width="3"/>'
        f'<ellipse cx="{tx}" cy="{ty}" rx="18" ry="36" fill="none" stroke="#10B981" stroke-width="1.6" opacity=".6"/>'
        f'<line x1="{tx-36}" y1="{ty}" x2="{tx+36}" y2="{ty}" stroke="#10B981" stroke-width="1.6" opacity=".6"/>'
        f'{fe.text(target_label, 13, tx - 26, ty + 56, "#065F46", True)}'
        f'{check_badge(tx + 28, ty - 28, 12, 0.70, dur=dur)}'
    )
    target_svg = scale_around(tx, ty, ".7;.7;1.14;1;1", "0;.65;.70;.75;1", target_inner, dur=dur)

    pill = (
        f'<g opacity="0">{smil_opacity("0;0;1;1", "0;.72;.76;1", dur=dur)}'
        f'<rect x="975" y="16" width="160" height="28" rx="14" fill="#1E293B"/>'
        f'{fe.text(badge_text, 12, 995, 34, "#FFFFFF", True)}</g>'
    )
    stage = wrap_stage(bulb_svg + "".join(links_svg) + orb_svg + "".join(nodes_svg) + target_svg + pill, dur=dur)
    aria = spec.get(
        "aria_label",
        f"程序员梦哥，分享AI少踩坑；像素文字变成粒子；{source_label}发出光点依次点亮{'、'.join(n['label'] for n in nodes[:3])}三个节点，最终抵达{target_label}并弹出对勾与{badge_text}",
    )
    return assemble_svg(stage, aria, dur=dur)


# ─── 内置模板 D：viewport-3d（3D 透视视口 + 旋转立方体 + 2.5D 轴测图层炸开） ───
def render_viewport_3d(spec: dict, fe: FontEngine) -> str:
    import math

    dur = spec.get("dur", "6s")
    viewport_tag = spec.get("viewport_tag", "3D VIEWPORT")
    summary_text = spec.get("summary_text", "多模态空间生成 · 实测通过")
    layers = spec.get(
        "layers",
        [
            {"title": "线框拓扑", "color": "#3B82F6", "bg": "#EFF6FF"},
            {"title": "材质光影", "color": "#10B981", "bg": "#ECFDF5"},
            {"title": "多轮精修", "color": "#8B5CF6", "bg": "#F5F3FF"},
        ],
    )

    # 左侧 3D 取景框角标 + 透视地面网格 + XYZ 坐标轴
    vx, vy = 450, 108
    brackets = (
        f'<path d="M290 44V26h22 M610 44V26h-22 M290 176v18h22 M610 176v18h-22" '
        f'fill="none" stroke="#64748B" stroke-width="2.5" stroke-linecap="round" stroke-dasharray="120">'
        f'{smil_stroke_draw(120, 0.24, 0.33, dur=dur)}</path>'
    )
    grid = (
        f'<g opacity="0">{smil_opacity("0;0;.85;.85", "0;.25;.34;1", dur=dur)}'
        f'{perspective_grid(vx, 128, 192, 160, 310, cols=6, rows=4, stroke="#CBD5E1")}</g>'
    )
    axes = (
        f'<line x1="{vx}" y1="128" x2="{vx}" y2="42" stroke="#10B981" stroke-width="2.2" stroke-dasharray="90">'
        f'{smil_stroke_draw(90, 0.28, 0.36, dur=dur)}</line>'
        f'<line x1="{vx}" y1="128" x2="{vx+125}" y2="128" stroke="#EF4444" stroke-width="2.2" stroke-dasharray="130">'
        f'{smil_stroke_draw(130, 0.28, 0.36, dur=dur)}</line>'
        f'<line x1="{vx}" y1="128" x2="{vx-78}" y2="174" stroke="#3B82F6" stroke-width="2.2" stroke-dasharray="100">'
        f'{smil_stroke_draw(100, 0.28, 0.36, dur=dur)}</line>'
        f'{fe.text(viewport_tag, 11, 320, 40, "#64748B", True)}'
    )

    # 3D 透视投影旋转立方体（animate:points 驱动顶面、左面、右面）
    def proj_cube(angle_deg: float, s: float = 34.0) -> tuple[str, str, str]:
        rad = math.radians(angle_deg)
        tilt = math.radians(24)
        verts = []
        for sx_i in (-1, 1):
            for sy_i in (-1, 1):
                for sz_i in (-1, 1):
                    x0, y0, z0 = sx_i * s, sy_i * s, sz_i * s
                    xr = x0 * math.cos(rad) - z0 * math.sin(rad)
                    zr = x0 * math.sin(rad) + z0 * math.cos(rad)
                    yr = y0 * math.cos(tilt) - zr * math.sin(tilt)
                    verts.append((vx + xr, 96 + yr))

        # 顶面 (y=-1: 0,1,3,2), 前/侧面按视角选两面
        def fmt_pts(idxs: tuple[int, ...]) -> str:
            return " ".join(f"{verts[i][0]:.1f},{verts[i][1]:.1f}" for i in idxs)

        top = fmt_pts((0, 1, 5, 4))
        front = fmt_pts((1, 3, 7, 5))
        side = fmt_pts((0, 1, 3, 2))
        return top, front, side

    angles = [20, 35, 50, 65, 80, 65, 50, 35, 20]
    kts = ";".join(f"{0.34 + i * 0.06:.2f}" for i in range(len(angles)))
    tops, fronts, sides = [], [], []
    for a in angles:
        t_p, f_p, s_p = proj_cube(a)
        tops.append(t_p)
        fronts.append(f_p)
        sides.append(s_p)

    cube_svg = (
        f'<g opacity="0">{smil_opacity("0;0;1;1", "0;.33;.38;1", dur=dur)}'
        f'<polygon points="{tops[0]}" fill="#6EE7B7" stroke="#065F46" stroke-width="1.6">'
        f'{smil_attr("points", ";".join(tops), kts, dur=dur)}</polygon>'
        f'<polygon points="{fronts[0]}" fill="#10B981" stroke="#065F46" stroke-width="1.6">'
        f'{smil_attr("points", ";".join(fronts), kts, dur=dur)}</polygon>'
        f'<polygon points="{sides[0]}" fill="#047857" stroke="#065F46" stroke-width="1.6">'
        f'{smil_attr("points", ";".join(sides), kts, dur=dur)}</polygon>'
        f'</g>'
    )

    # 右侧 2.5D 轴测图层炸开（skewY=-12）
    layer_svgs = []
    for idx, ly in enumerate(layers[:3]):
        dx = (idx - 1) * 115
        lx = 910
        tr_vals = f"0 0;0 0;{dx} 0;{dx} 0;0 0;0 0"
        tr_kt = "0;.46;.58;.74;.82;1"
        plate = (
            f'<rect x="{lx - 52}" y="58" width="104" height="106" rx="12" fill="{ly["bg"]}" stroke="{ly["color"]}" stroke-width="2.4" opacity=".94"/>'
            f'<circle cx="{lx}" cy="96" r="16" fill="{ly["color"]}" opacity=".18"/>'
            f'{fe.text(f"L{idx+1}", 13, lx - 8, 101, ly["color"], True)}'
            f'{fe.text(ly["title"], 12.5, lx - 26, 140, "#1E293B", True)}'
        )
        skewed = skew_around("skewY", lx, 111, "-12;-12;-12", "0;.5;1", plate, dur=dur)
        layer_svgs.append(
            f'<g opacity="0">{smil_opacity("0;0;1;1", "0;.42;.46;1", dur=dur)}'
            f'<g>{smil_transform("translate", tr_vals, tr_kt, dur=dur)}{skewed}</g></g>'
        )

    pill = (
        f'<g opacity="0">{smil_opacity("0;0;1;1", "0;.70;.75;1", dur=dur)}'
        f'<rect x="785" y="182" width="260" height="28" rx="14" fill="#1E293B"/>'
        f'{fe.text(summary_text, 12, 804, 200, "#FFFFFF", True)}'
        f'{check_badge(1056, 196, 12, 0.74, dur=dur)}</g>'
    )
    stage = wrap_stage(brackets + grid + axes + cube_svg + "".join(layer_svgs) + pill, dur=dur)
    aria = spec.get(
        "aria_label",
        f"程序员梦哥，分享AI少踩坑；像素文字变成粒子；{viewport_tag}透视网格与坐标轴生长，三维立方体渲染旋转，右侧三层2.5D玻璃图层横向炸开再吸合，弹出对勾与{summary_text}",
    )
    return assemble_svg(stage, aria, dur=dur)


# ─── 内置模板 E：split-editor（单视口左文右对话就地改写，无多卡堆叠） ───
def render_split_editor(spec: dict, fe: FontEngine) -> str:
    dur = spec.get("dur", "5.5s")
    file_name = spec.get("file_name", "report.md")
    prompt_text = spec.get("prompt_text", "提炼 3 条结论并高亮")
    result_text = spec.get("result_text", "已就地改写保存")

    # 左侧文件图标 + 右键脉冲标签
    file_icon = (
        f'<g opacity="0">{smil_opacity("0;0;1;1", "0;.24;.28;1", dur=dur)}'
        f'<rect x="278" y="60" width="76" height="96" rx="10" fill="#ECFDF5" stroke="#10B981" stroke-width="2.4"/>'
        f'<path d="M332 60v22h22" fill="#A7F3D0" stroke="#10B981" stroke-width="2"/>'
        f'{fe.text(file_name, 11, 288, 138, "#065F46", True)}'
        f'<rect x="296" y="166" width="94" height="24" rx="12" fill="#1E293B">'
        f'{smil_attr("opacity", "0;0;1;1", "0;.29;.33;1", dur=dur)}</rect>'
        f'{fe.text("右键 AI 打开", 10.5, 309, 182, "#FFFFFF", True)}</g>'
    )

    # 中右侧单视口分栏工作台（左栏文本行就地改写，右栏对话指令触发）
    rows = []
    for i, (y, w0, w1, c1) in enumerate([
        (66, 220, 260, "#1E6FFF"),
        (92, 180, 290, "#10B981"),
        (118, 240, 210, "#10B981"),
        (144, 150, 275, "#8B5CF6"),
    ]):
        t0 = 0.50 + i * 0.04
        t1 = t0 + 0.08
        kt = f"0;{t0:.2f};{t1:.2f};1"
        rows.append(
            f'<rect x="448" y="{y}" width="{w0}" height="12" rx="6" fill="#CBD5E1">'
            f'{smil_attr("width", f"{w0};{w0};{w1};{w1}", kt, dur=dur)}'
            f'{smil_attr("fill", f"#CBD5E1;#CBD5E1;{c1};{c1}", kt, dur=dur)}</rect>'
        )

    workbench = (
        f'<g opacity="0">{smil_opacity("0;0;1;1", "0;.30;.35;1", dur=dur)}'
        f'<rect x="424" y="30" width="750" height="168" rx="14" fill="#DCE4EE"/>'
        f'<rect x="420" y="24" width="750" height="168" rx="14" fill="#FFFFFF" stroke="#8291A5" stroke-width="2.4"/>'
        f'<line x1="806" y1="36" x2="806" y2="180" stroke="#E2E8F0" stroke-width="2"/>'
        f'{fe.text(file_name + " · 预览", 12, 448, 48, "#64748B", True)}'
        f'{"".join(rows)}'
        f'<rect x="828" y="44" width="318" height="42" rx="10" fill="#EFF6FF" stroke="#93C5FD" stroke-width="1.6">'
        f'{smil_attr("opacity", "0;0;1;1", "0;.36;.42;1", dur=dur)}</rect>'
        f'{fe.text(prompt_text, 12.5, 844, 70, "#1E40AF", True)}'
        f'<rect x="828" y="106" width="318" height="14" rx="7" fill="#E2E8F0"/>'
        f'<rect x="828" y="106" width="20" height="14" rx="7" fill="#10B981">'
        f'{smil_attr("width", "20;20;318;318", "0;.46;.64;1", dur=dur)}</rect>'
        f'<rect x="828" y="138" width="220" height="32" rx="10" fill="#ECFDF5" stroke="#6EE7B7" stroke-width="1.6">'
        f'{smil_attr("opacity", "0;0;1;1", "0;.66;.72;1", dur=dur)}</rect>'
        f'{fe.text(result_text, 12.5, 846, 159, "#065F46", True)}'
        f'{check_badge(1162, 32, 12, 0.70, dur=dur)}</g>'
    )
    stage = wrap_stage(file_icon + workbench, dur=dur)
    aria = spec.get(
        "aria_label",
        f"程序员梦哥，分享AI少踩坑；像素文字变成粒子；右键本地文件{file_name}打开分栏工作台，右侧输入指令「{prompt_text}」，左侧文档行实时改写高亮并弹出对勾与{result_text}",
    )
    return assemble_svg(stage, aria, dur=dur)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", help="分镜 JSON 配置文件路径")
    parser.add_argument(
        "--template",
        choices=("console-3act", "showcase-4card", "pipeline-nodes", "viewport-3d", "split-editor"),
        default="console-3act",
        help="内置分镜模板类型",
    )
    parser.add_argument("--out-svg", required=True, help="输出的 .svg 文件路径")
    parser.add_argument("--out-preview", help="输出的交互预览 .html 文件路径")
    parser.add_argument("--title", default="程序员梦哥 · 公众号 SVG 片头", help="预览页标题")
    args = parser.parse_args(argv)

    spec = json.loads(Path(args.spec).read_text(encoding="utf-8")) if args.spec else {}
    template = spec.get("template", args.template)
    fe = FontEngine()
    renderers = {
        "console-3act": render_console_3act,
        "showcase-4card": render_showcase_4card,
        "pipeline-nodes": render_pipeline_nodes,
        "viewport-3d": render_viewport_3d,
        "split-editor": render_split_editor,
    }
    svg = renderers.get(template, render_console_3act)(spec, fe)
    info = save_intro_bundle(svg, args.out_svg, args.out_preview, title=args.title)
    print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
