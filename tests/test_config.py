"""Offline tests for credentials and user-editable input files."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from content_lens.config import load_api_key, load_keywords, load_markets
from tests.helpers import PROJECT_ROOT


class ApiKeyConfigurationTests(unittest.TestCase):
    """Verify credential validation with test-only environment values."""

    @patch("content_lens.config.load_dotenv")
    def test_load_api_key_explains_when_key_is_missing(self, mock_load_dotenv):
        # Clearing the subprocess-style test environment proves the function does
        # not depend on the developer's real local .env contents.
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "Please set SEARCHAPI_KEY"):
                load_api_key()

        mock_load_dotenv.assert_called_once_with()

    @patch("content_lens.config.load_dotenv")
    def test_load_api_key_rejects_the_public_placeholder(self, mock_load_dotenv):
        with patch.dict(
            os.environ,
            {"SEARCHAPI_KEY": "your_searchapi_key_here"},
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "Please set SEARCHAPI_KEY"):
                load_api_key()

    @patch("content_lens.config.load_dotenv")
    def test_load_api_key_returns_a_configured_value(self, mock_load_dotenv):
        with patch.dict(os.environ, {"SEARCHAPI_KEY": "test-only-key"}, clear=True):
            self.assertEqual(load_api_key(), "test-only-key")


class InputFileTests(unittest.TestCase):
    """Check that user-editable files become safe, predictable Python data."""

    def write_temporary_file(self, directory, filename, content):
        """Create one input file inside a test-only temporary directory."""
        path = Path(directory) / filename
        path.write_text(content, encoding="utf-8")
        return path

    def test_load_keywords_strips_blanks_and_preserves_order(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_temporary_file(
                directory,
                "keywords.txt",
                "  first keyword  \n\nsecond keyword\n",
            )
            self.assertEqual(load_keywords(path), ["first keyword", "second keyword"])

    def test_load_keywords_rejects_an_empty_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_temporary_file(directory, "keywords.txt", " \n\n")
            with self.assertRaisesRegex(ValueError, "at least one keyword"):
                load_keywords(path)

    def test_load_keywords_explains_when_file_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "Keywords file not found"):
                load_keywords(Path(directory) / "missing.txt")

    def test_load_markets_returns_validated_market_data(self):
        markets = [
            {
                "name": " US ",
                "location": " New York, New York, United States ",
                "gl": " us ",
                "hl": " en ",
            },
            {
                "name": "SG",
                "location": "Singapore, Singapore",
                "gl": "sg",
                "hl": "en",
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_temporary_file(directory, "markets.json", json.dumps(markets))
            loaded = load_markets(path)

        self.assertEqual([market["name"] for market in loaded], ["US", "SG"])
        self.assertEqual(loaded[0]["gl"], "us")

    def test_load_markets_rejects_invalid_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_temporary_file(directory, "markets.json", "{not valid json")
            with self.assertRaisesRegex(ValueError, "valid JSON"):
                load_markets(path)

    def test_load_markets_requires_a_list(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_temporary_file(directory, "markets.json", '{"name": "US"}')
            with self.assertRaisesRegex(ValueError, "JSON list"):
                load_markets(path)

    def test_load_markets_requires_at_least_two_markets(self):
        market = [
            {
                "name": "US",
                "location": "New York, New York, United States",
                "gl": "us",
                "hl": "en",
            }
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_temporary_file(directory, "markets.json", json.dumps(market))
            with self.assertRaisesRegex(ValueError, "at least two markets"):
                load_markets(path)

    def test_load_markets_requires_every_field(self):
        markets = [
            {"name": "US", "location": "New York", "gl": "us", "hl": ""},
            {"name": "SG", "location": "Singapore", "gl": "sg", "hl": "en"},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_temporary_file(directory, "markets.json", json.dumps(markets))
            with self.assertRaisesRegex(ValueError, "non-empty fields: hl"):
                load_markets(path)

    def test_load_markets_rejects_duplicate_names(self):
        markets = [
            {"name": "US", "location": "New York", "gl": "us", "hl": "en"},
            {"name": "us", "location": "Chicago", "gl": "us", "hl": "en"},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_temporary_file(directory, "markets.json", json.dumps(markets))
            with self.assertRaisesRegex(ValueError, "Market names must be unique"):
                load_markets(path)

    def test_load_markets_accepts_more_than_three_for_csv_runs(self):
        markets = [
            {"name": name, "location": name, "gl": name.lower(), "hl": "en"}
            for name in ("US", "SG", "TH", "AU", "UK")
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_temporary_file(directory, "markets.json", json.dumps(markets))
            loaded = load_markets(path)

        self.assertEqual([market["name"] for market in loaded], ["US", "SG", "TH", "AU", "UK"])


class ImportBehaviorTests(unittest.TestCase):
    """Ensure the thin entry point can be imported without a live API key."""

    def test_import_does_not_require_api_key(self):
        environment = os.environ.copy()
        environment.pop("SEARCHAPI_KEY", None)
        # Disabling dotenv makes this subprocess behave like a fresh user who has
        # not created .env yet; importing the entry point should still be possible.
        environment["PYTHON_DOTENV_DISABLED"] = "1"

        result = subprocess.run(
            [sys.executable, "-c", "import compare_markets"],
            cwd=PROJECT_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
