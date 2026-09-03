"""Tests for the thin command-line entry point."""

import unittest

import compare_markets
from content_lens.workflow import main


class EntryPointTests(unittest.TestCase):
    """Keep the command wrapper wired to the package workflow."""

    def test_main_is_the_workflow_main(self):
        self.assertIs(compare_markets.main, main)


if __name__ == "__main__":
    unittest.main()
