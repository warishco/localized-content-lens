"""Small shared helpers for the offline test suite."""

import json
from pathlib import Path


FIXTURE_DIR = Path(__file__).parent / "fixtures"
PROJECT_ROOT = Path(__file__).parent.parent


def load_fixture(filename):
    """Load a fixed local response so tests never spend SearchApi credits."""
    return json.loads((FIXTURE_DIR / filename).read_text(encoding="utf-8"))
