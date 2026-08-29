import json
import os
from datetime import date
from pathlib import Path

import requests
from dotenv import load_dotenv

# Load the API key from a private .env file so it is never committed.
load_dotenv()
API_KEY = os.getenv("SEARCHAPI_KEY")

if not API_KEY or API_KEY == "your_searchapi_key_here":
    raise ValueError("Please set SEARCHAPI_KEY in your .env file.")


# Part 3: Run the same keyword in two locations and save the raw responses.
keyword = "best CRM for small business"

locations = [
    {"name": "US", "location": "New York, New York, United States", "gl": "us", "hl": "en"},
    {"name": "SG", "location": "Singapore, Singapore", "gl": "sg", "hl": "en"},
]

url = "https://www.searchapi.io/api/v1/search"
output_dir = Path("market_comparison")
output_dir.mkdir(exist_ok=True)

safe_name = keyword.lower().replace(" ", "_").replace("/", "_")
raw_results = {}

for loc in locations:
    params = {
        "engine": "google",
        "q": keyword,
        "location": loc["location"],
        "gl": loc["gl"],
        "hl": loc["hl"],
        "api_key": API_KEY,
    }

    print(f"\nFetching {keyword} for {loc['name']}...")
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()

    print("Status code:", response.status_code)
    print("URL (redacted):", response.url.replace(API_KEY, "REDACTED"))

    data = response.json()
    raw_results[loc["name"]] = data

# Save the combined raw JSON for inspection and later parsing.
raw_path = output_dir / f"{safe_name}_raw.json"
raw_path.write_text(json.dumps(raw_results, indent=2), encoding="utf-8")
print(f"\nSaved raw responses to: {raw_path}")

# Print a quick side-by-side preview of the top domains for manual comparison.
print("\n--- Top domains by market ---")
for loc in locations:
    name = loc["name"]
    items = raw_results[name].get("organic_results", [])
    domains = []
    for item in items[:5]:
        link = item.get("link") or ""
        domain = item.get("domain") or ""
        if link and not domain:
            from urllib.parse import urlparse

            domain = urlparse(link).netloc.replace("www.", "")
        domains.append(domain)
    print(f"{name}: {domains}")
