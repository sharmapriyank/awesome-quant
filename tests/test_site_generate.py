import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_generate():
    spec = importlib.util.spec_from_file_location(
        "site_generate", ROOT / "site" / "generate.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class SiteGenerateContractTests(unittest.TestCase):
    def setUp(self):
        self.module = load_generate()

    def test_data_languages_uses_pipe_separator_for_spaced_tags(self):
        entries = [
            {
                "project": "Example",
                "language": "Pine Script",
                "languages": "Pine Script,Python",
                "category": "Trading & Backtesting",
                "section_slug": "trading-backtesting",
                "url": "https://example.com",
                "description": "Example.",
                "github": False,
                "cran": False,
                "pypi": False,
                "commercial": False,
                "archived": False,
                "github_url": "",
                "repo": "",
                "stars": 0,
                "last_commit": "",
            }
        ]
        html = self.module.generate_html(entries)
        self.assertIn('data-languages="Pine Script|Python"', html)

    def test_main_js_splits_languages_on_pipe(self):
        js = (ROOT / "site" / "static" / "main.js").read_text(encoding="utf-8")
        self.assertIn('split("|")', js)
        self.assertNotIn('languages || "").split(" ")', js)

    def test_archived_flag_reaches_data_sources(self):
        entries = [
            {
                "project": "Archived Example",
                "language": "Python",
                "languages": "Python",
                "category": "Historical & Archived Projects",
                "section_slug": "historical-archived-projects",
                "url": "https://example.com",
                "description": "Example.",
                "github": True,
                "cran": False,
                "pypi": False,
                "commercial": False,
                "archived": True,
                "github_url": "https://github.com/a/b",
                "repo": "a/b",
                "stars": 0,
                "last_commit": "",
            }
        ]
        html = self.module.generate_html(entries)
        self.assertIn('data-sources="github archived"', html)


if __name__ == "__main__":
    unittest.main()
