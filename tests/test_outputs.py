"""Offline tests for safe output paths and report writers."""

import csv
import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from content_lens.analysis import build_csv_rows
from content_lens.outputs import (
    create_run_paths,
    make_report,
    markdown_results,
    safe_filename,
    save_raw_response,
    unique_safe_filename,
    write_csv,
    write_run_manifest,
)
from tests.helpers import load_fixture


class FilenameTests(unittest.TestCase):
    """Check safe, readable output names."""

    def test_safe_filename_normalizes_punctuation_and_unicode(self):
        # Readable ASCII slugs work across operating systems and avoid repeated
        # separators when a keyword contains punctuation.
        self.assertEqual(safe_filename("Best CRM / Singapore!"), "best_crm_singapore")
        self.assertEqual(safe_filename("Crème brûlée"), "creme_brulee")
        self.assertEqual(safe_filename("!!!"), "item")


class ReportGenerationTests(unittest.TestCase):
    """Check that reports adapt cleanly to two or three configured markets."""

    def market(self, name, location, gl):
        """Build one minimal market configuration for report tests."""
        return {"name": name, "location": location, "gl": gl, "hl": "en"}

    def response_with_domains(self, *domains):
        """Build source-linked organic results for a report market."""
        return {
            "organic_results": [
                {
                    "position": position,
                    "title": f"{domain} guide",
                    "link": f"https://{domain}/guide",
                    "snippet": f"Evidence snippet for {domain}.",
                    "domain": domain,
                }
                for position, domain in enumerate(domains, start=1)
            ]
        }

    def test_markdown_results_preserves_link_domain_and_snippet(self):
        formatted = markdown_results(load_fixture("us_response.json"), limit=1)

        self.assertIn("[Shared market guide](https://shared.example/us-guide)", formatted)
        self.assertIn("shared.example", formatted)
        self.assertIn("A general guide that appears in both markets.", formatted)

    def test_markdown_results_escapes_brackets_in_link_text(self):
        response = {
            "organic_results": [
                {
                    "position": 1,
                    "title": "CRM Guide [2026]",
                    "link": "https://example.com/guide",
                    "domain": "example.com",
                }
            ]
        }

        formatted = markdown_results(response)

        self.assertIn(r"[CRM Guide \[2026\]](https://example.com/guide)", formatted)

    def test_make_report_adapts_to_two_markets(self):
        markets = [
            self.market("US", "New York, New York, United States", "us"),
            self.market("SG", "Singapore, Singapore", "sg"),
        ]
        raw = {
            "US": load_fixture("us_response.json"),
            "SG": load_fixture("sg_response.json"),
        }

        report = make_report(
            "example keyword",
            raw,
            markets,
            run_id="two-market-run",
            research_date=date(2026, 9, 1),
        )

        self.assertIn("# Market comparison: example keyword", report)
        self.assertIn("**Run ID:** two-market-run", report)
        self.assertIn("| Domain | US | SG |", report)
        self.assertNotIn("| Domain | US | SG | TH |", report)
        self.assertIn("#### US top organic results", report)
        self.assertIn("#### SG top organic results", report)
        self.assertIn("## Human analysis", report)
        self.assertIn("**Content gap:**", report)
        self.assertIn("**Opportunity:**", report)

    def test_make_report_adapts_to_three_markets(self):
        markets = [
            self.market("US", "New York", "us"),
            self.market("SG", "Singapore", "sg"),
            self.market("TH", "Bangkok", "th"),
        ]
        raw = {
            "US": self.response_with_domains("shared.example", "us-sg.example"),
            "SG": self.response_with_domains("shared.example", "us-sg.example"),
            "TH": self.response_with_domains("shared.example", "th-only.example"),
        }

        report = make_report(
            "example keyword",
            raw,
            markets,
            run_id="three-market-run",
            research_date=date(2026, 9, 1),
        )

        self.assertIn("| Domain | US | SG | TH |", report)
        self.assertIn("| us-sg.example | Yes | Yes | — |", report)
        self.assertIn("#### TH top organic results", report)
        self.assertIn("#### Unique to TH", report)
        self.assertIn("- th-only.example", report)

    def test_make_report_rejects_more_than_three_markets(self):
        markets = [
            self.market(name, name, name.lower()) for name in ("US", "SG", "TH", "AU")
        ]
        raw = {
            market["name"]: self.response_with_domains("shared.example")
            for market in markets
        }

        with self.assertRaisesRegex(ValueError, "two or three markets"):
            make_report("example keyword", raw, markets)

    def test_make_report_warns_when_a_market_has_no_organic_results(self):
        markets = [
            self.market("US", "New York", "us"),
            self.market("SG", "Singapore", "sg"),
        ]
        raw = {
            "US": load_fixture("us_response.json"),
            "SG": {"search_metadata": {"status": "Success"}},
        }

        report = make_report("example keyword", raw, markets)

        self.assertIn("**Data quality warning:**", report)
        self.assertIn("SG", report)
        self.assertIn("Domain comparisons may be incomplete", report)


class CsvWriterTests(unittest.TestCase):
    """Check CSV escaping for API-derived text."""

    def market(self, name):
        return {"name": name, "location": name, "gl": name.lower(), "hl": "en"}

    def response(self, domain, title="Example title", snippet="Example snippet"):
        return {
            "organic_results": [
                {
                    "position": 1,
                    "title": title,
                    "link": f"https://{domain}/guide",
                    "snippet": snippet,
                    "domain": domain,
                }
            ]
        }

    def test_write_csv_preserves_commas_unicode_and_newlines(self):
        markets = [self.market("US"), self.market("SG")]
        raw = {
            "US": self.response(
                "us.example",
                title="Café, CRM guide",
                snippet="First line\nSecond line",
            ),
            "SG": self.response("sg.example"),
        }
        rows = build_csv_rows(
            "run-1", date(2026, 9, 1), "example keyword", raw, markets
        )

        with tempfile.TemporaryDirectory() as directory:
            csv_path = write_csv(rows, Path(directory) / "results.csv")
            with csv_path.open(newline="", encoding="utf-8") as csv_file:
                saved_rows = list(csv.DictReader(csv_file))

        self.assertEqual(saved_rows[0]["title"], "Café, CRM guide")
        self.assertEqual(saved_rows[0]["snippet"], "First line\nSecond line")
        self.assertNotIn("content_gap", saved_rows[0])
        self.assertNotIn("opportunity", saved_rows[0])


class OutputFileTests(unittest.TestCase):
    """Verify that each run preserves evidence in its own safe directory."""

    def setUp(self):
        self.started_at = datetime(2026, 9, 1, 12, 34, 56, tzinfo=timezone.utc)

    def test_unique_safe_filename_adds_a_suffix_for_collisions(self):
        used_names = set()

        first = unique_safe_filename("CRM!", used_names)
        second = unique_safe_filename("CRM?", used_names)

        self.assertEqual(first, "crm")
        self.assertNotEqual(second, first)
        self.assertTrue(second.startswith("crm_"))

    def test_create_run_paths_builds_separate_raw_and_report_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = create_run_paths(Path(directory), self.started_at)

            self.assertEqual(paths["run_id"], "20260901-123456")
            self.assertTrue(paths["raw_dir"].is_dir())
            self.assertTrue(paths["reports_dir"].is_dir())

            # A suffix prevents two runs started in the same second from sharing
            # files or overwriting analysis from the first run.
            second_paths = create_run_paths(Path(directory), self.started_at)
            self.assertEqual(second_paths["run_id"], "20260901-123456-2")

    def test_save_raw_response_preserves_complete_json(self):
        response = load_fixture("us_response.json")
        with tempfile.TemporaryDirectory() as directory:
            paths = create_run_paths(Path(directory), self.started_at)
            raw_path = save_raw_response(
                response,
                paths["raw_dir"],
                "example_keyword",
                "US",
            )
            saved_response = json.loads(raw_path.read_text(encoding="utf-8"))

        self.assertEqual(saved_response, response)
        self.assertEqual(raw_path.name, "us.json")
        self.assertEqual(raw_path.parent.name, "example_keyword")

    def test_save_raw_response_refuses_to_overwrite_evidence(self):
        response = load_fixture("us_response.json")
        with tempfile.TemporaryDirectory() as directory:
            paths = create_run_paths(Path(directory), self.started_at)
            save_raw_response(response, paths["raw_dir"], "keyword", "US")

            # Reusing the same keyword-market path signals a workflow mistake;
            # preserving the first response is safer than silently replacing it.
            with self.assertRaises(FileExistsError):
                save_raw_response(response, paths["raw_dir"], "keyword", "US")

    def test_write_run_manifest_contains_metadata_but_no_api_key(self):
        markets = load_fixture("us_response.json")["search_parameters"]
        market_list = [
            {
                "name": "US",
                "location": markets["location"],
                "gl": markets["gl"],
                "hl": markets["hl"],
            }
        ]
        with tempfile.TemporaryDirectory() as directory:
            paths = create_run_paths(Path(directory), self.started_at)
            manifest_path = write_run_manifest(
                paths["run_dir"],
                paths["run_id"],
                self.started_at,
                "google",
                market_list,
                keyword_count=1,
                requests_attempted=1,
                requests_completed=1,
                markdown_reports_generated=False,
                markdown_skip_reason="More than three markets were configured.",
            )
            manifest_text = manifest_path.read_text(encoding="utf-8")
            manifest = json.loads(manifest_text)

        self.assertEqual(manifest["requests_completed"], 1)
        self.assertEqual(manifest["markets"][0]["name"], "US")
        self.assertFalse(manifest["markdown_reports_generated"])
        self.assertIn("three markets", manifest["markdown_skip_reason"])
        self.assertNotIn("api_key", manifest_text.lower())


if __name__ == "__main__":
    unittest.main()
