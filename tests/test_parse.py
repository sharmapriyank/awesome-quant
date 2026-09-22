import io
import json
import unittest
from unittest.mock import patch
from urllib.error import URLError

import parse

ENTRY_LINE = "- [Widget](https://github.com/o/widget) - `Python` - A widget."


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
        return False


def fake_pypi_payload(releases):
    return FakeResponse(json.dumps({"releases": releases}).encode())


class PypiLastUpdatedTests(unittest.TestCase):
    def test_lexical_version_sort_does_not_pick_wrong_latest(self):
        # Lexically "9.9" > "10.0"; the newer upload must win on date.
        releases = {
            "9.9": [{"upload_time_iso_8601": "2024-01-01T00:00:00"}],
            "10.0": [{"upload_time_iso_8601": "2025-06-01T00:00:00"}],
        }
        with patch(
            "parse.urlopen", return_value=fake_pypi_payload(releases)
        ):
            self.assertEqual(
                parse.get_pypi_last_updated(
                    "https://pypi.org/project/example/"
                ),
                "2025-06-01",
            )

    def test_picks_newest_file_across_releases(self):
        releases = {
            "1.0": [
                {"upload_time_iso_8601": "2020-01-01T00:00:00"},
                {"upload_time_iso_8601": "2020-01-02T00:00:00"},
            ],
            "1.1": [{"upload_time_iso_8601": "2020-01-01T12:00:00"}],
        }
        with patch(
            "parse.urlopen", return_value=fake_pypi_payload(releases)
        ):
            self.assertEqual(
                parse.get_pypi_last_updated(
                    "https://pypi.org/project/example/"
                ),
                "2020-01-02",
            )

    def test_empty_or_missing_upload_times(self):
        releases = {"1.0": [{}], "1.1": []}
        with patch(
            "parse.urlopen", return_value=fake_pypi_payload(releases)
        ):
            self.assertEqual(
                parse.get_pypi_last_updated(
                    "https://pypi.org/project/example/"
                ),
                "",
            )

    def test_non_pypi_url_returns_empty(self):
        self.assertEqual(
            parse.get_pypi_last_updated("https://example.com"), ""
        )


class StarCountTests(unittest.TestCase):
    def test_plain_and_grouped_counts(self):
        self.assertEqual(parse._parse_star_count("20,948"), 20948)
        self.assertEqual(parse._parse_star_count("42"), 42)

    def test_suffixes(self):
        self.assertEqual(parse._parse_star_count("63.7k"), 63700)
        self.assertEqual(parse._parse_star_count("1.2M"), 1200000)

    def test_garbage_returns_zero(self):
        self.assertEqual(parse._parse_star_count(""), 0)
        self.assertEqual(parse._parse_star_count("many"), 0)


class FetchTextTests(unittest.TestCase):
    def test_retries_transient_transport_errors(self):
        calls = []
        def flaky(req, timeout=0):
            calls.append(req)
            if len(calls) < 3:
                raise URLError("temporary failure in name resolution")
            return FakeResponse(b"ok")

        with patch("parse.urlopen", side_effect=flaky), patch(
            "parse.time.sleep"
        ), patch("parse.random.uniform", return_value=0):
            self.assertEqual(parse._fetch_text("https://example.com"), "ok")
        self.assertEqual(len(calls), 3)

    def test_gives_up_after_attempts(self):
        with patch(
            "parse.urlopen", side_effect=URLError("nxdomain")
        ), patch("parse.time.sleep"), patch(
            "parse.random.uniform", return_value=0
        ), self.assertRaises(URLError):
            parse._fetch_text("https://does-not-resolve.invalid", attempts=2)


class ProjectRunTests(unittest.TestCase):
    def _project(self):
        m = parse.ENTRY_RE.match(ENTRY_LINE)
        p = parse.Project(m, "Python", "Trading & Backtesting", "Trading & Backtesting")
        p.languages = ["Python"]
        p.clean_description = "A widget."
        return p

    def test_error_last_commit_normalizes_to_empty(self):
        # A failed enrichment must not leak "error" into the CSV.
        p = self._project()
        with patch(
            "parse.get_repo_info", return_value=("error", 0, False)
        ):
            p.run()
        self.assertEqual(p.regs["last_commit"], "")
        self.assertEqual(p.regs["repo"], "o/widget")

    def test_github_entry_populates_regs(self):
        p = self._project()
        with patch(
            "parse.get_repo_info", return_value=("2025-01-02", 1234, False)
        ):
            p.run()
        self.assertEqual(p.regs["last_commit"], "2025-01-02")
        self.assertEqual(p.regs["stars"], 1234)
        self.assertTrue(p.regs["github"])
        self.assertEqual(p.regs["section_slug"], "trading-backtesting")


if __name__ == "__main__":
    unittest.main()
