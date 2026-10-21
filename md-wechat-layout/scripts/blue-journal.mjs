// 洛洛AI说参考版式的蓝色变体；编号以文字生成，不依赖原文图片。
const WECHAT_FONT = `"PingFang SC NEW",system-ui,-apple-system,BlinkMacSystemFont,"Helvetica Neue","Hiragino Sans GB","Microsoft YaHei UI","Microsoft YaHei",Arial,sans-serif`;
const BLUE = '#8dd6ff';

export const blueJournal = {
  id: 'blue-journal',
  name: '晴蓝手记',
  primary: '#46b7ff',
  font: 'sans',
  extractH2Index: true,
  autoH2Index: true,
  separateH2Index: true,
  lastH2Index: 'END',
  styles: (primary, size, font) => ({
    container: `font-family:${WECHAT_FONT};font-size:${size}px;line-height:1.6;color:#1a1a1a;letter-spacing:1px;padding:0;word-break:break-word;overflow-wrap:anywhere;`,
    h1: `font-size:${size * 1.5}px;line-height:${size * 2.2}px;font-weight:700;text-align:center;color:#222222;margin:24px 10px;`,
    h2: `font-size:${size * 1.25}px;line-height:${size * 2}px;font-weight:700;text-align:center;color:#333333;margin:0 10px 24px;padding:0;border:none;`,
    h2Index: `font-family:Arial,Helvetica,sans-serif;font-size:${size * 4.5}px;line-height:${size * 5.25}px;font-weight:700;font-style:italic;text-align:center;color:${BLUE};margin:32px 0 8px;letter-spacing:-2px;`,
    h3: `font-size:${size * 1.125}px;line-height:${size * 1.875}px;font-weight:700;color:#333333;margin:28px 10px 16px;padding:0;border:none;`,
    h4: `font-size:${size}px;line-height:${size * 1.75}px;font-weight:700;color:#333333;margin:24px 10px 16px;`,
    p: 'margin:0 10px 24px;text-align:left;text-indent:0;',
    liP: 'margin:0 0 8px;text-align:left;text-indent:0;',
    strong: 'font-weight:700;color:#1a1a1a;',
    mark: `background-color:${BLUE};color:#1a1a1a;padding:0;border-radius:0;`,
    blockquote: `margin:24px 10px;padding:12px 16px;background-color:#f3faff;border-left:3px solid #8dd6ff;border-radius:0;color:#4c6072;`,
    bqP: 'margin:0;text-indent:0;text-align:left;',
    hr: 'border:none;border-top:1px solid #e7edf3;margin:32px 10px;',
    th: 'border:1px solid #cfeaff;padding:8px 12px;background-color:#ecf8ff;font-weight:700;text-align:left;',
    td: 'border:1px solid #cfeaff;padding:8px 12px;text-align:left;',
    pre: 'background-color:#ffffff;border:1px solid #cfe8f7;border-radius:10px;margin:1.2em 8px;overflow:hidden;',
    preHeader: 'padding:10px 14px;background-color:#e1f3ff;border-bottom:1px solid #cfe8f7;font-size:12px;line-height:20px;',
    preLabel: 'font-family:Menlo,Consolas,monospace;color:#4c87b3;font-size:12px;line-height:20px;margin-left:10px;vertical-align:middle;',
  }),
};
