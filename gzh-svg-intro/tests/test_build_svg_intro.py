"""Automated unit tests for gzh-svg-intro skill."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "build_svg_intro.py"
spec = importlib.util.spec_from_file_location("build_svg_intro", SCRIPT)
kit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kit)


class BuildSvgIntroTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fe = kit.FontEngine()

    def test_font_engine_converts_text_to_closed_svg_path(self):
        path_tag = self.fe.text("程序员梦哥 76.29%", 18, 20, 50, "#1E6FFF", bold=True)
        self.assertTrue(path_tag.startswith('<path d="M'))
        self.assertTrue(path_tag.endswith('" fill="#1E6FFF"/>'))
        self.assertNotIn("<text", path_tag)

    def test_console_3act_template_passes_wechat_svg_compliance(self):
        svg = kit.render_console_3act({}, self.fe)
        errors = kit.validate_svg_compliance(svg)
        self.assertEqual(errors, [])
        self.assertIn('viewBox="0 0 1246 220"', svg)
        self.assertIn("WorkBuddy", svg)

    def test_showcase_4card_template_passes_wechat_svg_compliance(self):
        svg = kit.render_showcase_4card({}, self.fe)
        errors = kit.validate_svg_compliance(svg)
        self.assertEqual(errors, [])
        self.assertIn("76.29%", svg)
        self.assertIn("国模一哥 K3.1 Pro", svg)

    def test_non_card_templates_pass_wechat_svg_compliance(self):
        for name, renderer in (
            ("pipeline-nodes", kit.render_pipeline_nodes),
            ("viewport-3d", kit.render_viewport_3d),
            ("split-editor", kit.render_split_editor),
        ):
            with self.subTest(template=name):
                svg = renderer({}, self.fe)
                self.assertEqual(kit.validate_svg_compliance(svg), [])
                self.assertIn('viewBox="0 0 1246 220"', svg)

        v3d = kit.render_viewport_3d({}, self.fe)
        self.assertIn('attributeName="stroke-dashoffset"', v3d)
        self.assertIn('attributeName="points"', v3d)
        self.assertIn('type="skewY"', v3d)

    def test_new_smil_primitives(self):
        stroke_anim = kit.smil_stroke_draw(120, 0.25, 0.45, dur="6s")
        self.assertIn('attributeName="stroke-dashoffset"', stroke_anim)
        self.assertIn('dur="6s"', stroke_anim)
        rot = kit.rotate_around(100, 100, "0;45;0", "0;.5;1", "<rect/>", dur="5s")
        self.assertIn('type="rotate"', rot)
        self.assertIn('dur="5s"', rot)

    def test_cli_generates_svg_and_preview_html(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_svg = Path(tmp) / "intro.svg"
            out_html = Path(tmp) / "preview.html"
            res = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--template",
                    "showcase-4card",
                    "--out-svg",
                    str(out_svg),
                    "--out-preview",
                    str(out_html),
                    "--title",
                    "测试片头",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            )
            self.assertTrue(out_svg.is_file())
            self.assertTrue(out_html.is_file())
            self.assertIn('"animate":', res.stdout)
            html = out_html.read_text(encoding="utf-8")
            self.assertIn("一键复制片头", html)
            self.assertIn("<svg ", html)


if __name__ == "__main__":
    unittest.main()
