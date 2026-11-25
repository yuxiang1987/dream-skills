---
name: gzh-svg-intro
description: 为中文 AI 实测、教程和工具评测公众号文章定制纯内嵌 SVG+SMIL 开头动画（1246×220，8秒循环，零 text/image/script/defs），输出可一键复制粘贴到公众号后台的交互预览页，并可传给 md-wechat-layout 替换默认开头 GIF。用户说「给这篇文章做个开头动画」「做个片头动画」「摸鱼小李同款片头」「生成 SVG 片头」时使用。
---

# 公众号 SVG 片头动画

先读 [references/storyboard-dna.md](references/storyboard-dna.md)，掌握 1246×220 画布规范、8 秒循环时间轴、点阵口号坍缩母版，以及从正文提取真实案例做物理因果反馈的设计法则。

## 目标

根据用户指定的公众号文章（标题 + 正文真实案例/数据），生成一段可直接内嵌进微信公众号草稿的 **纯 SVG + SMIL 声明式矢量开头动画**（零 `<text>`、零 `<image>`、零 `<script>`、零 `<defs>`、零外部依赖）。

固定品牌前奏（`0.0s – 1.92s`）由预烘焙母版 `assets/brand-opener.svg.frag` 提供：
- 左侧高清像素立绘「程序员梦哥」（`2.2s` 呼吸微摆 + `3.2s` 眨眼，与主时间轴异步）；
- 右侧带 0.5px 网格缝隙的大号点阵字「**程序员梦哥，分享AI少踩坑**」，在 `1.20s – 1.92s` 分为 16 个点阵区块同步向中心坍缩为像素方块粒子。

主舞台（`1.76s – 7.04s`）根据每篇文章的正文定制，杜绝千篇一律的通用模板感。

默认交付：
- `intro.svg`：1246×220 纯内嵌 SVG+SMIL 源文件。
- `preview.html`：带「一键复制片头（可直接 `Ctrl+V` 粘贴到公众号后台）」按钮和关键时间点定格检视的预览页。
- 如用户要求连同全文一起排版，可将生成的 `intro.svg` 通过 `--intro-svg` 传给 `md-wechat-layout`，替换默认品牌 GIF 片头。

## 工作流

1. **读取文章标题与全文**：
   - 提取文章主角（产品/模型名）、作者亲自实测的 **2–4 个核心案例/设置项**，以及正文中令读者印象最深的具体数字、惊喜点或槽点（如 `5 小时用量 76.29%`、`C 盘迁入 D 盘释放 1TB`、`4 条编码准则`）。
   - 严禁虚构正文没有测过的功能、价格或结论。
2. **按题材选型，避免“全员卡片化”也避免“全员线条串珠化”**：
   - 按 [references/storyboard-dna.md](references/storyboard-dna.md) 优先根据题材匹配舞台结构（**严禁**连续多篇都用“左圆+虚线连线串几个小图标”的单一管道套路！）：
     - **3D 透视视口 + 2.5D 图层炸开（`viewport-3d`，无连线无卡片）**：适合 3D 模型、生图/设计工具、空间计算与能力评测。左侧生长透视网格、坐标轴与 `animate:points` 旋转三维立方体，右侧 3 层 `skewY` 玻璃图层横向炸开再吸合。
     - **实景多维舞台（自定义，无连线）**：适合多项目/多场景实测（如「太空兔三道题」= 3D 透视月面巡视车撞石回弹 + 北京双层视差长卷 + 落沙物理沙盒），直接把 2–3 个真实物理场景铺满画布。
     - **单视口分栏工作台（`split-editor`，无连线无多卡）**：适合本地文件 AI、IDE/Coding Agent、单图多轮编辑。左侧文件右键触发，右侧分栏内左文右对话就地改写高亮。
     - **节点连线管道（`pipeline-nodes`，仅用于纯工作流）**：仅适合 Agent 工作流、Skill 流水线。左侧光源发出一颗光点，沿虚线贝塞尔路径依次点亮 3 个里程碑节点。
     - **调校舱插卡 + 伙伴点亮（`console-3act`）**：适合参数调优、多模型切换。左侧调校舱依次落入 3 张配置卡带，向右发射脉冲光球点亮伙伴机器人与 7 项进度柱。
     - **主机连弹微缩作品卡 + 结论/槽点仪表（`showcase-4card`）**：适合多案例模型横评。左侧复古主机连弹 4 张带卡内微动效的作品卡，右侧弹出惊喜与槽点仪表。
     - **全新题材自定义舞台**：导入 `scripts/build_svg_intro.py` 的 `FontEngine`、`smil_opacity`、`smil_attr`、`smil_stroke_draw`、`smil_motion`、`smil_transform`、`scale_around`、`rotate_around`、`skew_around`、`launch_recoil`、`particle_fountain`、`stagger_bounce`、`ripple_pulse`、`perspective_grid`、`check_badge`、`wrap_stage`、`assemble_svg`、`save_intro_bundle`，编写贴合该文章独特道具的舞台（支持自定义 `dur` 如 `5s`/`6s`/`8s`）。
3. **文字转纯矢量 `<path>` 并生成 SVG 与预览页**：
   - 所有画面文字必须通过 `FontEngine.text(...)` 转成闭合矢量 `<path>`。
   - 调用 `save_intro_bundle(svg, out_svg, out_preview, title=...)` 自动执行合规校验（禁止 `<text>`/`<image>`/`<script>`/`<defs>`/`<style>`，强制 `calcMode="spline"` 与 `viewBox="0 0 1246 220"`）。
   - 也可用 CLI 快速生成或基于 JSON 分镜配置生成：
     ```powershell
     python scripts/build_svg_intro.py --template pipeline-nodes --out-svg "输出目录/intro.svg" --out-preview "输出目录/preview.html"
     python scripts/build_svg_intro.py --template viewport-3d --out-svg "输出目录/intro.svg" --out-preview "输出目录/preview.html"
     python scripts/build_svg_intro.py --template split-editor --out-svg "输出目录/intro.svg" --out-preview "输出目录/preview.html"
     python scripts/build_svg_intro.py --template console-3act --out-svg "输出目录/intro.svg" --out-preview "输出目录/preview.html"
     python scripts/build_svg_intro.py --template showcase-4card --out-svg "输出目录/intro.svg" --out-preview "输出目录/preview.html"
     python scripts/build_svg_intro.py --spec "分镜配置.json" --out-svg "输出目录/intro.svg" --out-preview "输出目录/preview.html"
     ```
4. **多时间点定格视觉检查**：
   - 在浏览器打开 `preview.html`（或用无头浏览器截取 `0.5s`、`1.55s`、`2.8s`、`4.5s`、`6.5s` 关键帧），检查：
     - `0.5s` 点阵口号是否完整、无右侧裁切；
     - `1.55s` 点阵字坍缩成粒子时是否干净、无残字与舞台重叠；
     - 主舞台各幕中的待命卡、堆叠卡、频谱柱、印章绿勾是否遮挡任何文字；
     - 收尾绿勾、总结气泡与正文结论是否完全一致。
5. **与 `md-wechat-layout` 排版联动（可选）**：
   - 当用户需要把专属 SVG 片头直接嵌入整篇公众号排版时，在调用 `md-wechat-layout` 时传入 `--intro-svg "输出目录/intro.svg"`，即可用该内嵌 SVG 片头替换默认的品牌 GIF。
   - 提醒用户：本地浏览器预览通过后，仍需在微信公众号草稿箱粘贴、保存重载并在手机微信端确认动画播放效果。

维护与回归核对见 [tests/intro-cases.md](tests/intro-cases.md) 与自动化测试 `tests/test_build_svg_intro.py`。
