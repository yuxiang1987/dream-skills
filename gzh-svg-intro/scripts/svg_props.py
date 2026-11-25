"""高精细拟物矢量道具库（纯 SVG+SMIL，零 <text>/<image>/<script>/<defs>）。

用法：
    from svg_props import (
        prop_gamepad, prop_console, prop_rocket, prop_coffee_cup,
        prop_retro_pc, prop_clapperboard, prop_phone, prop_robot,
    )
"""
from __future__ import annotations

from build_svg_intro import (
    DUR,
    FontEngine,
    rotate_around,
    smil_opacity,
    smil_transform,
)


def prop_gamepad(cx: float, cy: float, accent: str = "#1E6FFF", label: str = "", fe: FontEngine | None = None, dur: str = DUR) -> str:
    """高精细双摇杆游戏手柄（立体底影、十字键、ABXY 四色键、摇杆微动）。"""
    x, y = cx, cy
    body_d = (
        f"M{x-46} {y-24} h92 c16 0 26 12 30 34 c3 16 -4 26 -14 26 c-9 0 -15 -8 -22 -14 "
        f"h-72 c-7 6 -13 14 -22 14 c-10 0 -17 -10 -14 -26 c4 -22 14 -34 30 -34 Z"
    )
    shadow_d = (
        f"M{x-46} {y-18} h92 c16 0 26 12 30 34 c3 16 -4 26 -14 26 c-9 0 -15 -8 -22 -14 "
        f"h-72 c-7 6 -13 14 -22 14 c-10 0 -17 -10 -14 -26 c4 -22 14 -34 30 -34 Z"
    )
    dpad = (
        f'<rect x="{x-46}" y="{y-8}" width="22" height="8" rx="2.5" fill="#334155"/>'
        f'<rect x="{x-39}" y="{y-15}" width="8" height="22" rx="2.5" fill="#334155"/>'
    )
    abxy = (
        f'<circle cx="{x+36}" cy="{y-13}" r="4.2" fill="#F59E0B"/>'
        f'<circle cx="{x+45}" cy="{y-4}" r="4.2" fill="#EF4444"/>'
        f'<circle cx="{x+27}" cy="{y-4}" r="4.2" fill="#3B82F6"/>'
        f'<circle cx="{x+36}" cy="{y+5}" r="4.2" fill="#10B981">'
        f'{smil_transform("scale", "1;1;.82;1;1", "0;.42;.45;.49;1", dur=dur)}</circle>'
    )
    sticks = (
        f'<circle cx="{x-16}" cy="{y+4}" r="9" fill="#CBD5E1" stroke="#64748B" stroke-width="1.8"/>'
        f'<circle cx="{x-16}" cy="{y+4}" r="5.5" fill="#475569"/>'
        f'<circle cx="{x+14}" cy="{y+4}" r="9" fill="#CBD5E1" stroke="#64748B" stroke-width="1.8"/>'
        f'<circle cx="{x+14}" cy="{y+4}" r="5.5" fill="#475569"/>'
    )
    lbl = fe.text(label, 9.5, x - 14, y - 9, accent, True) if (fe and label) else ""
    return (
        f'<path d="{shadow_d}" fill="#DCE4EE"/>'
        f'<rect x="{x-44}" y="{y-28}" width="22" height="6" rx="3" fill="{accent}"/>'
        f'<rect x="{x+22}" y="{y-28}" width="22" height="6" rx="3" fill="{accent}"/>'
        f'<path d="{body_d}" fill="#FFFFFF" stroke="#8291A5" stroke-width="2.5" stroke-linejoin="round"/>'
        f'{dpad}{abxy}{sticks}{lbl}'
    )


def prop_console(cx: float, cy: float, label: str = "AI", accent: str = "#1E6FFF", fe: FontEngine | None = None, dur: str = DUR) -> str:
    """高精细掌机/调校舱（立体底影、顶部卡槽、亮屏视窗、十字键与双按钮）。"""
    w, h = 112, 134
    x, y = cx - w / 2, cy - h / 2
    lbl = fe.text(label, 12, x + 22, y + 46, "#F8FAFC", True) if (fe and label) else ""
    return (
        f'<rect x="{x+4}" y="{y+6}" width="{w}" height="{h}" rx="16" fill="#DCE4EE"/>'
        f'<rect x="{x+28}" y="{y-6}" width="56" height="10" rx="3" fill="#475569"/>'
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="16" fill="#FFFFFF" stroke="#8291A5" stroke-width="2.6"/>'
        f'<rect x="{x+12}" y="{y+14}" width="88" height="58" rx="9" fill="#1E293B" stroke="#334155" stroke-width="2"/>'
        f'<rect x="{x+17}" y="{y+19}" width="78" height="48" rx="6" fill="#0F172A"/>'
        f'<circle cx="{x+24}" cy="{y+26}" r="3" fill="#10B981"/>{lbl}'
        f'<rect x="{x+18}" y="{y+94}" width="24" height="8" rx="2.5" fill="#475569"/>'
        f'<rect x="{x+26}" y="{y+86}" width="8" height="24" rx="2.5" fill="#475569"/>'
        f'<circle cx="{x+84}" cy="{y+94}" r="6" fill="{accent}"/>'
        f'<circle cx="{x+70}" cy="{y+106}" r="6" fill="#10B981"/>'
        f'<line x1="{x+44}" y1="{y+120}" x2="{x+56}" y2="{y+114}" stroke="#CBD5E1" stroke-width="2.5" stroke-linecap="round"/>'
        f'<line x1="{x+54}" y1="{y+120}" x2="{x+66}" y2="{y+114}" stroke="#CBD5E1" stroke-width="2.5" stroke-linecap="round"/>'
    )


def prop_rocket(cx: float, cy: float, label: str = "", accent: str = "#F97316", fe: FontEngine | None = None, dur: str = DUR) -> str:
    """高精细几何火箭（尖锥整流罩、玻璃舷窗、两侧尾翼、闪烁尾焰）。"""
    x, y = cx, cy
    flame = (
        f'<polygon points="{x-10},{y+40} {x},{y+66} {x+10},{y+40}" fill="#F97316">'
        f'{smil_opacity("1;.35;1;.45;1", "0;.25;.5;.75;1", dur="0.6s")}</polygon>'
        f'<polygon points="{x-5},{y+40} {x},{y+55} {x+5},{y+40}" fill="#FACC15"/>'
    )
    lbl = fe.text(label, 9, x - 9, y + 26, "#475569", True) if (fe and label) else ""
    return (
        f'{flame}'
        f'<polygon points="{x-22},{y+16} {x-36},{y+42} {x-18},{y+34}" fill="{accent}" stroke="#8291A5" stroke-width="2" stroke-linejoin="round"/>'
        f'<polygon points="{x+22},{y+16} {x+36},{y+42} {x+18},{y+34}" fill="{accent}" stroke="#8291A5" stroke-width="2" stroke-linejoin="round"/>'
        f'<rect x="{x-12}" y="{y+34}" width="24" height="8" rx="2" fill="#475569"/>'
        f'<path d="M{x} {y-54} c16 18 22 44 22 88 h-44 c0 -44 6 -70 22 -88 Z" fill="#FFFFFF" stroke="#8291A5" stroke-width="2.5"/>'
        f'<path d="M{x} {y-54} c9 11 15 24 18 38 h-36 c3 -14 9 -27 18 -38 Z" fill="{accent}"/>'
        f'<circle cx="{x}" cy="{y+2}" r="11" fill="#38BDF8" stroke="#1E293B" stroke-width="2.4"/>'
        f'<circle cx="{x-3}" cy="{y-1}" r="3.5" fill="#FFFFFF" opacity=".8"/>{lbl}'
    )


def prop_coffee_cup(cx: float, cy: float, label: str = "AI", fe: FontEngine | None = None, dur: str = DUR) -> str:
    """高精细立体白瓷咖啡杯（托盘投影、环形杯耳、咖啡液面、飘起热气）。"""
    x, y = cx, cy
    steam = "".join(
        f'<path d="M{x-16+i*16} {y-32} q-6 -10 0 -18 t0 -16" fill="none" stroke="#94A3B8" stroke-width="2.4" stroke-linecap="round">'
        f'{smil_transform("translate", "0 4;0 -6;0 4", "0;.5;1", spline="0.45 0 0.55 1", dur="2.2s")}</path>'
        for i in range(3)
    )
    lbl = fe.text(label, 11, x - 6, y + 18, "#475569", True) if (fe and label) else ""
    return (
        f'{steam}'
        f'<ellipse cx="{x}" cy="{y+42}" rx="46" ry="11" fill="#DCE4EE"/>'
        f'<ellipse cx="{x}" cy="{y+38}" rx="44" ry="10" fill="#FFFFFF" stroke="#8291A5" stroke-width="2.2"/>'
        f'<path d="M{x+32} {y-12} c18 0 18 32 0 32" fill="none" stroke="#8291A5" stroke-width="6" stroke-linecap="round"/>'
        f'<path d="M{x+32} {y-12} c18 0 18 32 0 32" fill="none" stroke="#FFFFFF" stroke-width="2.5" stroke-linecap="round"/>'
        f'<path d="M{x-34} {y-22} h68 v34 c0 18 -14 28 -34 28 s-34 -10 -34 -28 Z" fill="#FFFFFF" stroke="#8291A5" stroke-width="2.5"/>'
        f'<ellipse cx="{x}" cy="{y-22}" rx="34" ry="9" fill="#78350F" stroke="#8291A5" stroke-width="2.2"/>'
        f'<ellipse cx="{x-6}" cy="{y-22}" rx="12" ry="3.5" fill="#FEF3C7" opacity=".75"/>{lbl}'
    )


def prop_retro_pc(cx: float, cy: float, code: str = "AI", sub: str = "READY", accent: str = "#38BDF8", fe: FontEngine | None = None, dur: str = DUR) -> str:
    """高精细复古 CRT 台式电脑（立体侧影、深灰屏幕框、扫描线、软驱槽与底座）。"""
    w, h = 148, 116
    x, y = cx - w / 2, cy - h / 2 - 8
    c_svg = fe.text(code, 16, x + 28, y + 48, accent, True) if (fe and code) else ""
    s_svg = fe.text(sub, 9.5, x + 28, y + 66, "#94A3B8", True) if (fe and sub) else ""
    return (
        f'<rect x="{x+18}" y="{y+h+2}" width="{w-36}" height="14" rx="4" fill="#CBD1AA"/>'
        f'<rect x="{x+5}" y="{y+5}" width="{w}" height="{h}" rx="14" fill="#CBC1AA"/>'
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="#EEE7D7" stroke="#A79E88" stroke-width="2.5"/>'
        f'<rect x="{x+14}" y="{y+12}" width="{w-28}" height="68" rx="9" fill="#253241" stroke="#64748B" stroke-width="2"/>'
        f'<rect x="{x+19}" y="{y+17}" width="{w-38}" height="58" rx="6" fill="#0F172A"/>'
        f'{c_svg}{s_svg}'
        f'<rect x="{x+18}" y="{y+92}" width="64" height="7" rx="3.5" fill="#A79E88"/>'
        f'<circle cx="{x+124}" cy="{y+95}" r="4.5" fill="#10B981">'
        f'{smil_opacity("1;.4;1", "0;.5;1", dur="1.8s")}</circle>'
    )


def prop_clapperboard(cx: float, cy: float, scene: str = "01", fe: FontEngine | None = None, dur: str = DUR) -> str:
    """高精细电影场记板（黑白斜纹上拍板开合、深色板身与场记横线）。"""
    w, h = 128, 88
    x, y = cx - w / 2, cy - h / 2 + 8
    top_bar = (
        f'<rect x="{x}" y="{y-18}" width="{w}" height="18" rx="4" fill="#1E293B" stroke="#334155" stroke-width="2"/>'
        + "".join(f'<polygon points="{x+12+i*24},{y-18} {x+24+i*24},{y-18} {x+16+i*24},{y} {x+4+i*24},{y}" fill="#F8FAFC"/>' for i in range(5))
    )
    animated_bar = rotate_around(x + 8, y, "0;-24;0;0", "0;.30;.38;1", top_bar, dur=dur)
    lbl = fe.text(f"SCENE {scene}", 12, x + 16, y + 36, "#F8FAFC", True) if fe else ""
    return (
        f'<rect x="{x+5}" y="{y+5}" width="{w}" height="{h}" rx="10" fill="#CBD5E1"/>'
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="#243044" stroke="#475569" stroke-width="2.4"/>'
        f'{lbl}'
        f'<line x1="{x+14}" y1="{y+52}" x2="{x+w-14}" y2="{y+52}" stroke="#475569" stroke-width="2"/>'
        f'<line x1="{x+14}" y1="{y+68}" x2="{x+w-36}" y2="{y+68}" stroke="#475569" stroke-width="2"/>'
        f'{animated_bar}'
    )


def prop_phone(cx: float, cy: float, title: str = "APP", accent: str = "#A3E635", fe: FontEngine | None = None, dur: str = DUR) -> str:
    """高精细手机真机（立体投影、深色机身、微信胶囊、内置能量环）。"""
    w, h = 112, 166
    x, y = cx - w / 2, cy - h / 2
    lbl = fe.text(title, 10.5, x + 14, y + 20, "#F8FAFC", True) if (fe and title) else ""
    return (
        f'<rect x="{x+4}" y="{y+5}" width="{w}" height="{h}" rx="18" fill="#DCE4EE"/>'
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="18" fill="#111827" stroke="#8291A5" stroke-width="2.5"/>'
        f'<rect x="{x+70}" y="{y+9}" width="30" height="10" rx="5" fill="#1F2937" stroke="#475569" stroke-width="1"/>'
        f'{lbl}'
        f'<circle cx="{cx}" cy="{cy-4}" r="26" fill="none" stroke="#1F2937" stroke-width="7"/>'
        f'<circle cx="{cx}" cy="{cy-4}" r="26" fill="none" stroke="{accent}" stroke-width="7" stroke-linecap="round" stroke-dasharray="128 40"/>'
        f'<rect x="{x+14}" y="{y+134}" width="{w-28}" height="18" rx="9" fill="{accent}"/>'
    )


def prop_robot(cx: float, cy: float, name: str = "AI", accent: str = "#F59E0B", fe: FontEngine | None = None, dur: str = DUR) -> str:
    """高精细伙伴机器人（发光天线、深色面罩、双眼微笑、胸口指示灯）。"""
    x, y = cx, cy
    lbl = fe.text(name, 9.5, x - 5, y + 44, "#1E293B", True) if (fe and name) else ""
    return (
        f'<ellipse cx="{x}" cy="{y+56}" rx="34" ry="8" fill="#DCE4EE"/>'
        f'<line x1="{x}" y1="{y-46}" x2="{x}" y2="{y-32}" stroke="#64748B" stroke-width="3" stroke-linecap="round"/>'
        f'<circle cx="{x}" cy="{y-50}" r="5.5" fill="#10B981">'
        f'{smil_opacity(".4;1;.4", "0;.5;1", dur="1.6s")}</circle>'
        f'<rect x="{x-32}" y="{y-32}" width="64" height="44" rx="14" fill="{accent}" stroke="#8291A5" stroke-width="2.4"/>'
        f'<rect x="{x-22}" y="{y-22}" width="44" height="24" rx="8" fill="#1E293B"/>'
        f'<circle cx="{x-10}" cy="{y-10}" r="4.5" fill="#38BDF8"/>'
        f'<circle cx="{x+10}" cy="{y-10}" r="4.5" fill="#38BDF8"/>'
        f'<rect x="{x-26}" y="{y+14}" width="52" height="38" rx="12" fill="#FFFFFF" stroke="#8291A5" stroke-width="2.4"/>'
        f'<circle cx="{x}" cy="{y+26}" r="6.5" fill="{accent}" opacity=".25"/>'
        f'<circle cx="{x}" cy="{y+26}" r="3.2" fill="#10B981"/>{lbl}'
    )
