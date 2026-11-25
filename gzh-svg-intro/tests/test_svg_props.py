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

        svg = kit.assemble_svg(kit.wrap_stage("".join(combined)), "八大高精细拟物道具测试")
        self.assertEqual(kit.validate_svg_compliance(svg), [])


if __name__ == "__main__":
    unittest.main()
