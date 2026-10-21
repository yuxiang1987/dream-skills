# 上游来源

- 项目：https://github.com/laogou717/md-wechat
- 固定版本：`8a21962efdc44b83d1673e557a52cf963c72b669`
- 下载日期：2026-09-30
- 许可证：MIT；完整声明在 `assets/upstream/LICENSE`。
- 复用：`src/lib/renderer.js`、`src/lib/themes.js`，保留原主题字体、配色和内联样式。适配普通附件解析、参考资料行高，以及青绿山水小节标题的纯色背景和可换行布局。完整项目在创建时下载到工作区的 `vendor/md-wechat`，运行 skill 不依赖该目录。
- 上游主题对外开放 `cyan-scape`（青山绿水）和 `mint-soda`（薄荷气泡），默认雾蓝气泡基于薄荷气泡做配色适配；本地新增 `blue-journal`（晴蓝手记），实现位于 `scripts/blue-journal.mjs`，参考与使用边界见 [晴蓝手记](blue-journal.md)。
- `renderer.js` 另支持主题主动开启的二级标题自动编号与编号独立段落，避免大号数字与标题共用一行；未开启时保持原渲染方式。
- `scripts/render.mjs` 为本 skill 新增的 Obsidian 预处理、附件解析、CLI 和富文本复制预览页。
- 依据源码 `src/lib/clipboard.js`，复制使用 `text/html` 剪贴板格式；按钮另有选区复制回退。微信实际处理结果应在用户草稿内验收。
- 微信规范：https://developers.weixin.qq.com/doc/service/guide/product/plugin_spec.html；本地提供副本的 1.3 节说明多行文字行高小于字号的风险，4.1.2 节建议文字背景不用渐变，4.1.3 节允许无文字的纯背景渐变。
- 官方检测实现：https://github.com/wechatjs/verify-article-structure-spec。CLI 可用系统 Chrome：`node node_modules/tsx/dist/cli.mjs src/index.ts 正文.html --json --executable-path=Chrome绝对路径`，退出码 0 通过、1 违规、2 异常。检测通过不代表实际粘贴后已通过微信检测。
