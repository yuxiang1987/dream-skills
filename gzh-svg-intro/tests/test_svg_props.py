"""Unit tests for reusable skeuomorphic vector props in svg_props.py."""
from pathlib import Path
import sys
import unittest

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

import build_svg_intro as kit
import svg_props as props


class SvgPropsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fe = kit.FontEngine()

    def test_all_8_props_render_and_pass_wechat_compliance(self):
        builders = [
            ("gamepad", lambda: props.prop_gamepad(340, 110, fe=self.fe, label="PLAY")),
            ("console", lambda: props.prop_console(460, 110, fe=self.fe, label="AI")),
            ("rocket", lambda: props.prop_rocket(580, 110, fe=self.fe, label="HY4")),
            ("coffee", lambda: props.prop_coffee_cup(700, 110, fe=self.fe, label="5x")),
            ("retro_pc", lambda: props.prop_retro_pc(830, 110, fe=self.fe)),
            ("clapper", lambda: props.prop_clapperboard(960, 110, fe=self.fe)),
            ("phone", lambda: props.prop_phone(1080, 110, fe=self.fe)),
            ("robot", lambda: props.prop_robot(1180, 110, fe=self.fe)),
        ]
        combined = []
        for name, fn in builders:
            with self.subTest(prop=name):
                frag = fn()
                self.assertTrue(frag.strip())
                self.assertNotIn("<text", frag)
                self.assertNotIn("<defs", frag)
                combined.append(frag)

        svg = kit.assemble_svg(kit.wrap_stage("".join(combined)), "第一批8个高精细拟物道具测试")
        self.assertEqual(kit.validate_svg_compliance(svg), [])

    def test_batch2_8_props_render_and_pass_wechat_compliance(self):
        builders = [
            ("telescope", lambda: props.prop_telescope(340, 110)),
            ("stethoscope", lambda: props.prop_stethoscope(460, 110)),
            ("gpu_box", lambda: props.prop_gpu_box(580, 110, fe=self.fe)),
            ("monitor", lambda: props.prop_monitor(710, 110, fe=self.fe)),
            ("filmstrip", lambda: props.prop_filmstrip(840, 110)),
            ("lightbulb", lambda: props.prop_lightbulb(960, 110)),
            ("globe", lambda: props.prop_globe(1070, 110)),
            ("doc_file", lambda: props.prop_doc_file(1180, 110, fe=self.fe)),
        ]
        combined = []
        for name, fn in builders:
            with self.subTest(prop=name):
                frag = fn()
                self.assertTrue(frag.strip())
                self.assertNotIn("<text", frag)
                self.assertNotIn("<defs", frag)
                combined.append(frag)

        svg = kit.assemble_svg(kit.wrap_stage("".join(combined)), "第二批8个摸鱼小李同款道具测试")
        self.assertEqual(kit.validate_svg_compliance(svg), [])


if __name__ == "__main__":
    unittest.main()
