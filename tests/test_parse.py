import io
import json
import unittest
from unittest.mock import patch

import parse


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


if __name__ == "__main__":
    unittest.main()
