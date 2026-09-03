"""Offline tests for result normalization and cross-market analysis."""

import unittest
from datetime import date

from content_lens.analysis import (
    build_csv_rows,
    compare_domains,
    first_value,
    get_domain,
    get_items,
    normalize_result,
)
from content_lens.config import CSV_FIELDS
from tests.helpers import load_fixture


class HelperFunctionTests(unittest.TestCase):
    """Check the small pure functions against predictable inputs."""

    def test_first_value_uses_the_first_non_empty_key(self):
        item = {"title": "", "name": "Fallback title"}
        self.assertEqual(first_value(item, "title", "name"), "Fallback title")

    def test_first_value_returns_empty_string_when_keys_are_missing(self):
        self.assertEqual(first_value({}, "title", "name"), "")

    def test_get_domain_extracts_a_domain_and_removes_www(self):
        self.assertEqual(get_domain("https://www.example.com/guide"), "example.com")

    def test_get_domain_handles_an_empty_link(self):
        self.assertEqual(get_domain(""), "")

    def test_normalize_result_supports_fallback_field_names(self):
        singapore_result = load_fixture("sg_response.json")["organic_results"][1]

        self.assertEqual(
            normalize_result(singapore_result),
            {
                "position": 2,
                "title": "Singapore-only guide",
                "link": "https://sg-only.example/guide",
                "snippet": "A fictional result using fallback field names.",
                "domain": "sg-only.example",
            },
        )

    def test_normalize_result_keeps_missing_fields_visible(self):
        self.assertEqual(
            normalize_result({}),
            {
                "position": None,
                "title": "",
                "link": "",
                "snippet": "",
                "domain": "",
            },
        )

    def test_normalize_result_cleans_an_api_supplied_domain(self):
        result = {
            "position": 1,
            "title": "Example",
            "link": "https://www.example.com/guide",
            "domain": " WWW.Example.COM. ",
        }
        self.assertEqual(normalize_result(result)["domain"], "example.com")

    def test_both_market_fixtures_share_the_normalized_shape(self):
        expected_keys = {"position", "title", "link", "snippet", "domain"}
        for filename in ("us_response.json", "sg_response.json"):
            with self.subTest(filename=filename):
                normalized_results = [
                    normalize_result(item) for item in get_items(load_fixture(filename))
                ]
                self.assertTrue(normalized_results)
                self.assertTrue(
                    all(set(result) == expected_keys for result in normalized_results)
                )

    def test_get_items_returns_organic_results(self):
        response = load_fixture("us_response.json")
        self.assertEqual(len(get_items(response)), 2)

    def test_get_items_ignores_non_organic_collections(self):
        response = {
            "results": [{"title": "Generic result"}],
            "top_stories": [{"title": "News result"}],
        }
        self.assertEqual(get_items(response), [])

    def test_get_items_rejects_a_non_list_organic_value(self):
        self.assertEqual(get_items({"organic_results": {"title": "Wrong shape"}}), [])

    def test_get_items_returns_empty_list_when_results_are_missing(self):
        self.assertEqual(get_items({"search_metadata": {"status": "Success"}}), [])


class DomainComparisonTests(unittest.TestCase):
    """Check domain presence across two or more localized result sets."""

    def response_with_domains(self, *domains):
        """Build a minimal organic response from a predictable domain list."""
        return {
            "organic_results": [
                {
                    "position": position,
                    "title": f"Result {position}",
                    "link": f"https://{domain}/page-{position}" if domain else "",
                    "domain": domain,
                }
                for position, domain in enumerate(domains, start=1)
            ]
        }

    def test_compare_domains_finds_shared_and_unique_domains(self):
        responses = {
            "US": load_fixture("us_response.json"),
            "SG": load_fixture("sg_response.json"),
        }

        comparison = compare_domains(responses)

        self.assertEqual(comparison["shared_by_all"], {"shared.example"})
        self.assertEqual(comparison["unique_by_market"]["US"], {"us-only.example"})
        self.assertEqual(comparison["unique_by_market"]["SG"], {"sg-only.example"})

    def test_compare_domains_removes_duplicates_and_empty_values(self):
        responses = {
            "US": self.response_with_domains("shared.example", "shared.example", ""),
            "SG": self.response_with_domains("shared.example", "sg-only.example"),
        }

        comparison = compare_domains(responses)

        self.assertEqual(comparison["domains_by_market"]["US"], {"shared.example"})
        self.assertNotIn("", comparison["presence_by_domain"])

    def test_compare_domains_supports_three_markets(self):
        responses = {
            "US": self.response_with_domains(
                "shared.example", "us-sg.example", "us-only.example"
            ),
            "SG": self.response_with_domains(
                "shared.example", "us-sg.example", "sg-only.example"
            ),
            "TH": self.response_with_domains("shared.example", "th-only.example"),
        }

        comparison = compare_domains(responses)

        self.assertEqual(comparison["shared_by_all"], {"shared.example"})
        self.assertEqual(
            comparison["presence_by_domain"]["us-sg.example"], ["US", "SG"]
        )
        self.assertEqual(comparison["unique_by_market"]["US"], {"us-only.example"})
        self.assertEqual(comparison["unique_by_market"]["SG"], {"sg-only.example"})
        self.assertEqual(comparison["unique_by_market"]["TH"], {"th-only.example"})


class CsvRowTests(unittest.TestCase):
    """Check flattened API-derived rows across small and larger market sets."""

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

    def test_build_csv_rows_uses_one_row_per_organic_result(self):
        markets = [self.market("US"), self.market("SG")]
        raw = {
            "US": load_fixture("us_response.json"),
            "SG": load_fixture("sg_response.json"),
        }

        rows = build_csv_rows(
            "run-1", date(2026, 9, 1), "example keyword", raw, markets
        )

        self.assertEqual(len(rows), 4)
        self.assertTrue(all(tuple(row) == CSV_FIELDS for row in rows))
        shared_row = next(row for row in rows if row["domain"] == "shared.example")
        us_only_row = next(row for row in rows if row["domain"] == "us-only.example")
        self.assertFalse(shared_row["unique_to_market"])
        self.assertTrue(us_only_row["unique_to_market"])
        self.assertEqual(us_only_row["market"], "US")

    def test_build_csv_rows_supports_five_markets(self):
        markets = [self.market(name) for name in ("US", "SG", "TH", "AU", "UK")]
        raw = {
            market["name"]: self.response(f"{market['name'].lower()}-only.example")
            for market in markets
        }

        rows = build_csv_rows(
            "run-5", date(2026, 9, 1), "example keyword", raw, markets
        )

        self.assertEqual(len(rows), 5)
        self.assertEqual({row["market"] for row in rows}, {"US", "SG", "TH", "AU", "UK"})
        self.assertTrue(all(row["unique_to_market"] for row in rows))


if __name__ == "__main__":
    unittest.main()
