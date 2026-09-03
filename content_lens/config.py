"""Project paths, credentials, and user-editable input validation."""

import json
import os
from pathlib import Path

from dotenv import load_dotenv


# Resolve project files from the package location, not from whichever folder
# the user happens to be in when they run the command.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
KEYWORDS_PATH = PROJECT_ROOT / "keywords.txt"
MARKETS_PATH = PROJECT_ROOT / "markets.json"
OUTPUT_DIR = PROJECT_ROOT / "market_comparison"
REQUIRED_MARKET_FIELDS = ("name", "location", "gl", "hl")
MARKDOWN_MARKET_LIMIT = 3
SEARCH_ENGINE = "google"
CSV_FIELDS = (
    "run_id",
    "research_date",
    "keyword",
    "market",
    "location",
    "gl",
    "hl",
    "position",
    "title",
    "domain",
    "link",
    "snippet",
    "unique_to_market",
)


def load_api_key():
    """Load the private SearchApi key only when a live run starts."""
    # Delaying this check lets tests and other Python files import the offline
    # parsing helpers without needing access to a real SearchApi credential.
    load_dotenv()
    api_key = os.getenv("SEARCHAPI_KEY")
    if not api_key or api_key == "your_searchapi_key_here":
        raise ValueError("Please set SEARCHAPI_KEY in your .env file.")
    return api_key


def load_keywords(path):
    """Read a text file into an ordered list of non-empty keywords."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ValueError(f"Keywords file not found: {path}") from exc
    except OSError as exc:
        raise ValueError(f"Could not read keywords file: {path}") from exc

    # One keyword per line keeps the input easy to edit without Python syntax.
    keywords = [line.strip() for line in text.splitlines() if line.strip()]
    if not keywords:
        raise ValueError("Keywords file must contain at least one keyword.")
    return keywords


def load_markets(path):
    """Read and validate the market definitions used for localized searches."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ValueError(f"Markets file not found: {path}") from exc
    except OSError as exc:
        raise ValueError(f"Could not read markets file: {path}") from exc

    try:
        markets = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Markets file must contain valid JSON (line {exc.lineno}, column {exc.colno})."
        ) from exc

    if not isinstance(markets, list):
        raise ValueError("Markets file must contain a JSON list of market objects.")
    if len(markets) < 2:
        raise ValueError("Markets file must contain at least two markets.")

    # Raw JSON and long-form CSV grow by rows, so they can support more markets
    # than the three-column Markdown report without becoming unreadable.
    validated_markets = []
    seen_names = set()
    for index, market in enumerate(markets, start=1):
        if not isinstance(market, dict):
            raise ValueError(f"Market {index} must be a JSON object.")

        invalid_fields = [
            field
            for field in REQUIRED_MARKET_FIELDS
            if not isinstance(market.get(field), str) or not market[field].strip()
        ]
        if invalid_fields:
            fields = ", ".join(invalid_fields)
            raise ValueError(f"Market {index} must provide non-empty fields: {fields}.")

        # Copy rather than mutate the parsed input, then trim only the fields the
        # script owns so future optional settings can remain untouched.
        validated_market = dict(market)
        for field in REQUIRED_MARKET_FIELDS:
            validated_market[field] = validated_market[field].strip()

        # Case-insensitive comparison prevents labels such as US and us from
        # creating ambiguous report sections or overwriting the same output.
        comparable_name = validated_market["name"].casefold()
        if comparable_name in seen_names:
            raise ValueError(
                f"Market names must be unique; duplicate: {validated_market['name']}."
            )
        seen_names.add(comparable_name)
        validated_markets.append(validated_market)

    return validated_markets
