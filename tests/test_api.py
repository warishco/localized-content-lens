"""Offline tests for the SearchApi request boundary."""

import unittest
from unittest.mock import Mock, patch

import requests

from content_lens.analysis import get_items
from content_lens.api import SearchApiError, search_api


class SearchApiRequestTests(unittest.TestCase):
    """Exercise the request boundary without contacting the live service."""

    def setUp(self):
        self.api_key = "test-secret"
        self.params = {
            "engine": "google",
            "query": "example keyword",
            "api_key": self.api_key,
            "location": "New York, New York, United States",
            "gl": "us",
            "hl": "en",
        }

    def successful_response(self, data=None):
        """Build the smallest response mock needed for a successful request."""
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = data or {"organic_results": []}
        return response

    @patch("content_lens.api.requests.get")
    def test_search_api_sends_expected_parameters(self, mock_get):
        expected_data = {"organic_results": [{"position": 1, "title": "Example"}]}
        mock_get.return_value = self.successful_response(expected_data)

        result = search_api(**self.params)

        self.assertEqual(result, expected_data)
        mock_get.assert_called_once_with(
            "https://www.searchapi.io/api/v1/search",
            params={
                "engine": "google",
                "q": "example keyword",
                "api_key": self.api_key,
                "location": "New York, New York, United States",
                "gl": "us",
                "hl": "en",
            },
            timeout=30,
        )

    @patch("content_lens.api.requests.get")
    def test_search_api_explains_a_timeout(self, mock_get):
        mock_get.side_effect = requests.exceptions.Timeout("request timed out")

        with self.assertRaisesRegex(SearchApiError, "timed out"):
            search_api(**self.params)

    @patch("content_lens.api.requests.get")
    def test_search_api_explains_a_connection_error(self, mock_get):
        mock_get.side_effect = requests.exceptions.ConnectionError("network unavailable")

        with self.assertRaisesRegex(SearchApiError, "connect"):
            search_api(**self.params)

    @patch("content_lens.api.requests.get")
    def test_search_api_redacts_the_key_from_http_errors(self, mock_get):
        response = self.successful_response()
        response.status_code = 401
        response.url = f"https://www.searchapi.io/api/v1/search?api_key={self.api_key}"
        response.text = f"Invalid API key: {self.api_key}"
        response.raise_for_status.side_effect = requests.exceptions.HTTPError(response=response)
        mock_get.return_value = response

        with self.assertRaises(SearchApiError) as raised:
            search_api(**self.params)

        message = str(raised.exception)
        self.assertIn("HTTP 401", message)
        self.assertIn("REDACTED", message)
        self.assertNotIn(self.api_key, message)

    @patch("content_lens.api.requests.get")
    def test_search_api_explains_invalid_json(self, mock_get):
        response = self.successful_response()
        response.json.side_effect = ValueError("not JSON")
        mock_get.return_value = response

        with self.assertRaisesRegex(SearchApiError, "valid JSON"):
            search_api(**self.params)

    @patch("content_lens.api.requests.get")
    def test_search_api_preserves_a_response_without_organic_results(self, mock_get):
        # A valid response can omit organic results; parsing decides how to show
        # that absence rather than the request layer inventing an API failure.
        expected_data = {"search_metadata": {"status": "Success"}}
        mock_get.return_value = self.successful_response(expected_data)

        result = search_api(**self.params)

        self.assertEqual(result, expected_data)
        self.assertEqual(get_items(result), [])


if __name__ == "__main__":
    unittest.main()
