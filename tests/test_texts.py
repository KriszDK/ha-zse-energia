"""The dashboard texts: every language has the same keys; unsupported languages fall back to English."""
import importlib.util
import pathlib
import unittest

spec = importlib.util.spec_from_file_location(
    "texts", pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "zse_energia" / "texts.py"
)
texts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(texts)


class TextsTests(unittest.TestCase):
    def test_same_keys_everywhere(self) -> None:
        base = set(texts.TEXTS["en"])
        for lang, d in texts.TEXTS.items():
            self.assertEqual(set(d), base, lang)

    def test_language_pick(self) -> None:
        self.assertEqual(texts.pick_language("hu"), "hu")
        self.assertEqual(texts.pick_language("sk-SK"), "sk")
        self.assertEqual(texts.pick_language("SK_sk"), "sk")
        self.assertEqual(texts.pick_language("de"), "en")
        self.assertEqual(texts.pick_language(None), "en")
        self.assertEqual(texts.pick_language(""), "en")

    def test_average_template_has_placeholders(self) -> None:
        for lang, d in texts.TEXTS.items():
            for p in ("{y}", "{m}", "{n}"):
                self.assertIn(p, d["t_avg"], lang)


if __name__ == "__main__":
    unittest.main()
