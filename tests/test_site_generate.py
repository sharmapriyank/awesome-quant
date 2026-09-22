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

    def test_rows_are_keyboard_navigable(self):
        entries = [
            {
                "project": "Example",
                "language": "Python",
                "languages": "Python",
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
        self.assertIn('tabindex="-1" aria-expanded="false"', html)
        self.assertIn('role="status" aria-live="polite"', html)

        js = (ROOT / "site" / "static" / "main.js").read_text(encoding="utf-8")
        self.assertIn("setExpanded", js)
        self.assertIn("moveRowFocus", js)
        self.assertIn("aria-expanded", js)
        # Row keydown must not swallow Enter/Space on focused child elements
        self.assertIn("e.target !== row", js)

    def _entry(self, **overrides):
        entry = {
            "project": "Example",
            "language": "Python",
            "languages": "Python",
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
        entry.update(overrides)
        return entry

    def test_javascript_scheme_url_is_never_rendered_as_href(self):
        html = self.module.generate_html(
            [self._entry(url="javascript:alert(1)")]
        )
        self.assertNotIn("javascript:", html)
        self.assertNotIn('href="alert', html)
        # Name still renders (without a link) so the entry is not lost
        self.assertIn("Example", html)

    def test_javascript_scheme_github_url_is_never_rendered_as_href(self):
        html = self.module.generate_html(
            [
                self._entry(
                    github_url="javascript:alert(2)",
                    url="https://example.com",
                )
            ]
        )
        self.assertNotIn("javascript:", html)

    def test_markup_in_fields_is_escaped(self):
        html = self.module.generate_html(
            [
                self._entry(
                    project='<img src=x onerror="alert(1)">',
                    description='<script>alert(2)</script> "quoted"',
                    category='<b>&amp;',
                    languages='Python,<svg onload=alert(3)>',
                )
            ]
        )
        self.assertNotIn("<script>", html)
        self.assertNotIn('<img src=x onerror="alert(1)">', html)
        self.assertIn("&lt;img", html)
        self.assertIn("&lt;script&gt;", html)

    def test_quote_breakout_in_attributes_is_escaped(self):
        html = self.module.generate_html(
            [
                self._entry(
                    category='" onmouseover="alert(4)',
                    languages='Python," onfocus=alert(5)',
                )
            ]
        )
        self.assertNotIn('" onmouseover="', html)
        self.assertIn("&quot;", html)


if __name__ == "__main__":
    unittest.main()
