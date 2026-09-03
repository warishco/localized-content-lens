"""Offline tests for collection and top-level workflow orchestration."""

import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from content_lens.api import SearchApiError
from content_lens.outputs import create_run_paths
from content_lens.workflow import collect_keyword_data, main, run_plan_message
from tests.helpers import load_fixture


class RunPlanTests(unittest.TestCase):
    """Check the pre-run request and output summary."""

    def test_run_plan_notice_explains_markdown_skip_and_request_count(self):
        notice = run_plan_message(keyword_count=5, market_count=5)

        self.assertIn("25 requests", notice)
        self.assertIn("Markdown reports will not be generated", notice)
        self.assertIn("CSV and raw JSON will include all 5 markets", notice)


class CollectionTests(unittest.TestCase):
    """Check collection behavior without making live API requests."""

    def setUp(self):
        from datetime import datetime, timezone

        self.started_at = datetime(2026, 9, 1, 12, 34, 56, tzinfo=timezone.utc)

    @patch("content_lens.workflow.search_api")
    def test_collection_saves_each_market_response(self, mock_search_api):
        mock_search_api.side_effect = [
            load_fixture("us_response.json"),
            load_fixture("sg_response.json"),
        ]
        markets = [
            {"name": "US", "location": "New York", "gl": "us", "hl": "en"},
            {"name": "SG", "location": "Singapore", "gl": "sg", "hl": "en"},
        ]
        with tempfile.TemporaryDirectory() as directory:
            paths = create_run_paths(Path(directory), self.started_at)
            results = collect_keyword_data(
                "example keyword",
                "test-secret",
                markets,
                raw_dir=paths["raw_dir"],
                keyword_stem="example_keyword",
                market_stems={"US": "us", "SG": "sg"},
            )

            self.assertTrue((paths["raw_dir"] / "example_keyword" / "us.json").is_file())
            self.assertTrue((paths["raw_dir"] / "example_keyword" / "sg.json").is_file())

        self.assertEqual(set(results), {"US", "SG"})

    @patch("builtins.print")
    @patch("content_lens.workflow.search_api")
    def test_collection_warns_when_organic_results_are_missing(
        self, mock_search_api, mock_print
    ):
        mock_search_api.return_value = {"search_metadata": {"status": "Success"}}
        markets = [
            {"name": "US", "location": "New York", "gl": "us", "hl": "en"}
        ]

        collect_keyword_data("example keyword", "test-secret", markets)

        printed_text = " ".join(
            str(argument)
            for call in mock_print.call_args_list
            for argument in call.args
        )
        self.assertIn("Warning", printed_text)
        self.assertIn("no organic results", printed_text)


class MainWorkflowTests(unittest.TestCase):
    """Check orchestration and partial failures without live API requests."""

    def write_inputs(self, directory, market_names=("US", "SG")):
        """Create a test-only keyword file and configurable market list."""
        directory = Path(directory)
        keywords_path = directory / "keywords.txt"
        markets_path = directory / "markets.json"
        keywords_path.write_text("example keyword\n", encoding="utf-8")
        markets_path.write_text(
            json.dumps(
                [
                    {
                        "name": name,
                        "location": name,
                        "gl": name.lower(),
                        "hl": "en",
                    }
                    for name in market_names
                ]
            ),
            encoding="utf-8",
        )
        return keywords_path, markets_path

    @patch("builtins.print")
    @patch("content_lens.workflow.search_api")
    @patch("content_lens.workflow.load_api_key", return_value="test-secret")
    def test_main_preserves_partial_results_and_records_request_failure(
        self, mock_load_api_key, mock_search_api, mock_print
    ):
        mock_search_api.side_effect = [
            SearchApiError("US request failed safely."),
            load_fixture("sg_response.json"),
        ]
        with tempfile.TemporaryDirectory() as directory:
            keywords_path, markets_path = self.write_inputs(directory)
            output_root = Path(directory) / "output"

            exit_code = main(keywords_path, markets_path, output_root)

            run_dir = next(output_root.iterdir())
            manifest = json.loads(
                (run_dir / "run_manifest.json").read_text(encoding="utf-8")
            )
            with (run_dir / "results.csv").open(newline="", encoding="utf-8") as file:
                csv_rows = list(csv.DictReader(file))
            report_files = list((run_dir / "reports").glob("*.md"))
            raw_files = list((run_dir / "raw").glob("**/*.json"))

        self.assertEqual(exit_code, 1)
        self.assertEqual(mock_search_api.call_count, 2)
        mock_load_api_key.assert_called_once_with()
        self.assertEqual(manifest["requests_attempted"], 2)
        self.assertEqual(manifest["requests_completed"], 1)
        self.assertEqual(manifest["markdown_report_count"], 0)
        self.assertEqual(manifest["markdown_reports_skipped"], 1)
        self.assertEqual(manifest["failures"][0]["market"], "US")
        self.assertEqual({row["market"] for row in csv_rows}, {"SG"})
        self.assertEqual(report_files, [])
        self.assertEqual(len(raw_files), 1)

        printed_text = " ".join(
            str(argument)
            for call in mock_print.call_args_list
            for argument in call.args
        )
        self.assertIn("Failed", printed_text)
        self.assertNotIn("test-secret", printed_text)

    @patch("builtins.print")
    @patch("content_lens.workflow.search_api")
    @patch("content_lens.workflow.load_api_key", return_value="test-secret")
    def test_main_completes_a_two_market_run(
        self, mock_load_api_key, mock_search_api, mock_print
    ):
        mock_search_api.side_effect = [
            load_fixture("us_response.json"),
            load_fixture("sg_response.json"),
        ]
        with tempfile.TemporaryDirectory() as directory:
            keywords_path, markets_path = self.write_inputs(directory)
            output_root = Path(directory) / "output"

            exit_code = main(keywords_path, markets_path, output_root)

            run_dir = next(output_root.iterdir())
            manifest = json.loads(
                (run_dir / "run_manifest.json").read_text(encoding="utf-8")
            )
            report_files = list((run_dir / "reports").glob("*.md"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(manifest["failures"], [])
        self.assertTrue(manifest["markdown_reports_generated"])
        self.assertEqual(manifest["markdown_report_count"], 1)
        self.assertEqual(manifest["markdown_reports_skipped"], 0)
        self.assertEqual(len(report_files), 1)

    @patch("builtins.print")
    @patch("content_lens.workflow.search_api")
    @patch("content_lens.workflow.load_api_key", return_value="test-secret")
    def test_main_skips_markdown_but_keeps_five_market_csv(
        self, mock_load_api_key, mock_search_api, mock_print
    ):
        mock_search_api.side_effect = [load_fixture("us_response.json")] * 5
        with tempfile.TemporaryDirectory() as directory:
            keywords_path, markets_path = self.write_inputs(
                directory, ("US", "SG", "TH", "AU", "UK")
            )
            output_root = Path(directory) / "output"

            exit_code = main(keywords_path, markets_path, output_root)

            run_dir = next(output_root.iterdir())
            manifest = json.loads(
                (run_dir / "run_manifest.json").read_text(encoding="utf-8")
            )
            with (run_dir / "results.csv").open(newline="", encoding="utf-8") as file:
                csv_rows = list(csv.DictReader(file))
            report_files = list((run_dir / "reports").glob("*.md"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(mock_search_api.call_count, 5)
        self.assertEqual({row["market"] for row in csv_rows}, {"US", "SG", "TH", "AU", "UK"})
        self.assertFalse(manifest["markdown_reports_generated"])
        self.assertEqual(manifest["markdown_report_count"], 0)
        self.assertEqual(manifest["markdown_reports_skipped"], 1)
        self.assertIn("More than 3 markets", manifest["markdown_skip_reason"])
        self.assertEqual(report_files, [])

    @patch("content_lens.workflow.search_api")
    @patch("content_lens.workflow.load_api_key")
    def test_main_rejects_invalid_input_before_loading_key_or_requesting(
        self, mock_load_api_key, mock_search_api
    ):
        with tempfile.TemporaryDirectory() as directory:
            _, markets_path = self.write_inputs(directory)
            missing_keywords = Path(directory) / "missing-keywords.txt"
            output_root = Path(directory) / "output"

            with self.assertRaisesRegex(ValueError, "Keywords file not found"):
                main(missing_keywords, markets_path, output_root)

            self.assertFalse(output_root.exists())

        mock_load_api_key.assert_not_called()
        mock_search_api.assert_not_called()


if __name__ == "__main__":
    unittest.main()
