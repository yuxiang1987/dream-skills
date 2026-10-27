"""Consumer-visible title preservation and overflow checks."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from PIL import Image, ImageDraw, ImageFont

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "compose_cover.py"
spec = importlib.util.spec_from_file_location("compose_cover", SCRIPT)
cover = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cover)


class ComposeCoverTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.font = cover.find_font(True)
            cls.subfont = cover.find_font(False)
        except SystemExit:
            raise unittest.SkipTest("Chinese fonts unavailable")

    def test_wrap_preserves_every_character(self):
        text = "用人工智能做一个完整的视频创作教程"
        draw = ImageDraw.Draw(Image.new("RGB", (900, 383)))
        lines = cover.wrap(draw, text, ImageFont.truetype(self.font, 48), 405)
        self.assertEqual("".join(lines), text)
        self.assertGreater(len(lines), 2)

    def test_cli_reports_overflow_without_creating_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            bg, out = Path(tmp) / "bg.png", Path(tmp) / "cover.png"
            Image.new("RGB", (900, 383), "black").save(bg)
            result = subprocess.run([sys.executable, str(SCRIPT), "--background", str(bg),
                                     "--output", str(out), "--title", "用人工智能做一个完整的视频创作教程",
                                     "--font", self.font, "--subtitle-font", self.subfont],
                                    capture_output=True, text=True, encoding="utf-8")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("超过两行", result.stderr)
            self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
