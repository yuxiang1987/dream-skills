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


# ─── SMIL 动画原语与常用物理反馈组件 ───

def smil_opacity(values: str, key_times: str, dur: str = DUR) -> str:
    return f'<animate attributeName="opacity" values="{values}" keyTimes="{key_times}" dur="{dur}" repeatCount="indefinite"/>'


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


def scale_around(cx: float, cy: float, values: str, key_times: str, inner: str, spline: str = "0.23 1 0.32 1") -> str:
    return (
        f'<g transform="translate({cx} {cy})"><g>'
        f'{smil_transform("scale", values, key_times, spline)}'
        f'<g transform="translate({-cx} {-cy})">{inner}</g></g></g>'
    )


def check_badge(cx: float, cy: float, r: float, t_appear: float) -> str:
    t1 = f"{t_appear:.3f}"
    t2 = f"{t_appear + 0.025:.3f}"
    t3 = f"{t_appear + 0.045:.3f}"
    s = r / 11.0
    inner = (
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="#10B981" stroke="#FFFFFF" stroke-width="{2 * s:.1f}"/>'
        f'<path d="M{cx - 4.5 * s:.1f} {cy:.1f}l{3 * s:.1f} {3.2 * s:.1f}l{6.5 * s:.1f}-{6.5 * s:.1f}" '
        f'fill="none" stroke="#FFFFFF" stroke-width="{2.4 * s:.1f}" stroke-linecap="round" stroke-linejoin="round"/>'
    )
    return scale_around(cx, cy, "0;0;1.28;1;1", f"0;{t1};{t2};{t3};1", inner)


def load_brand_opener() -> str:
    """加载预烘焙的「像素梦哥 + 16 组点阵字坍缩粒子」固定母版片段。"""
    return OPENER_ASSET.read_text(encoding="utf-8")


def wrap_stage(stage_inner: str) -> str:
    """包一层主舞台 1.76s 淡入、7.04s 淡出控制器。"""
    return (
        f'<g opacity="0">'
        f'{smil_opacity("0;0;1;1;0;0", "0;.22;.26;.88;.91;1")}'
        f"{stage_inner}</g>"
    )


def assemble_svg(stage_svg: str, aria_label: str) -> str:
    """将主舞台与品牌开场母版组装为完整的 1246×220 纯 SVG+SMIL 源码。"""
    opener = load_brand_opener()
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", help="分镜 JSON 配置文件路径")
    parser.add_argument("--template", choices=("console-3act", "showcase-4card"), default="console-3act", help="内置分镜模板类型")
    parser.add_argument("--out-svg", required=True, help="输出的 .svg 文件路径")
    parser.add_argument("--out-preview", help="输出的交互预览 .html 文件路径")
    parser.add_argument("--title", default="程序员梦哥 · 公众号 SVG 片头", help="预览页标题")
    args = parser.parse_args(argv)

    spec = json.loads(Path(args.spec).read_text(encoding="utf-8")) if args.spec else {}
    template = spec.get("template", args.template)
    fe = FontEngine()
    svg = render_showcase_4card(spec, fe) if template == "showcase-4card" else render_console_3act(spec, fe)
    info = save_intro_bundle(svg, args.out_svg, args.out_preview, title=args.title)
    print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
