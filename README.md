# Localized Content Lens

The same keyword often produces very different results depending on where the
search comes from. A term that ranks authoritative B2B content in New York may
return entirely different domains in Singapore. Those differences are content
signals, and finding them manually is slow.

**Localized Content Lens** is a lightweight Python command-line tool that
**compares Google search results for the same keyword across cities or
countries**. For each keyword and market pair, it collects organic SERP data
through
[SearchApi](https://www.searchapi.io/?utm_source=dev&utm_medium=ambassador&utm_campaign=warish.co)
and produces a source-backed report for content gap analysis.

---

## Who it is for

- SEO specialists and international SEO teams
- Content strategists planning localized content
- Technical marketers and developers who want a small workflow rather than a
  large platform

---

## What it does

For each keyword and market pair, the tool:

1. Sends a localized Google search request to SearchApi
2. Saves the complete API response as raw JSON
3. Extracts organic results and compares the domains that appear across
   locations
4. Generates a Markdown report per keyword and a CSV summary across the run

The automated comparison provides evidence. Content decisions stay with you.

---

## Requirements

- Python 3.8 or later
- A
  [SearchApi](https://www.searchapi.io/?utm_source=dev&utm_medium=ambassador&utm_campaign=warish.co)
  account and API key

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/warishco/localized-content-lens.git
cd localized-content-lens
```

### 2. Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate   # macOS/Linux
.venv\Scripts\activate      # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure your API key

Copy the included example file and add your key:

```bash
cp .env.example .env
```

Open `.env` and replace the placeholder with your SearchApi key:

```
SEARCHAPI_KEY=your_key_here
```

`.env` is listed in `.gitignore` and will not be committed.

---

## Inputs

### `keywords.txt`

One keyword per line. Blank lines are ignored.

```
best CRM for small business
AI for sales teams
account-based marketing software
```

### `markets.json`

A list of market objects. Each market requires four fields:

| Field      | Description                                     |
| ---------- | ----------------------------------------------- |
| `name`     | A readable label used in reports and file names |
| `location` | The physical search location sent to SearchApi  |
| `gl`       | The Google country parameter                    |
| `hl`       | The Google interface language                   |

```json
[
	{
		"name": "US",
		"location": "New York, New York, United States",
		"gl": "us",
		"hl": "en"
	},
	{
		"name": "Singapore",
		"location": "Singapore, Singapore",
		"gl": "sg",
		"hl": "en"
	}
]
```

---

## Run

```bash
python3 compare_markets.py
```

On Windows, or in an activated environment where the command is named `python`:

```bash
python compare_markets.py
```

The tool validates your inputs before making any API requests. A missing field
or blank keyword will stop the run with an error message before any credits are
used.

---

## Output

Each run produces a timestamped folder inside `market_comparison/`:

```
market_comparison/
└── 20260902-155900/
    ├── raw/
    │   └── best_crm_for_small_business/
    │       ├── US.json
    │       └── Singapore.json
    ├── reports/
    │   └── best_crm_for_small_business.md
    ├── results.csv
    └── run_manifest.json
```

### Raw JSON (`raw/`)

One file per keyword-market request, saved before any normalization. This is the
evidence trail. Formatting changes never require new API requests because the
raw files remain intact.

### Markdown reports (`reports/`)

One report per keyword. Each report includes:

- The keyword and research date
- Market parameters
- Top organic results per market (position, title, linked URL, snippet, domain)
- Domains unique to each market and domains shared across markets
- Blank fields for human analysis: content gap, opportunity, and verification
  notes

### CSV summary (`results.csv`)

One row per organic result across the complete run. Columns include `run_id`,
`keyword`, `market`, `position`, `title`, `domain`, `link`, `snippet`, and
`unique_to_market`. All values come from the API, market configuration, or
automated set comparison.

### Run manifest (`run_manifest.json`)

Records the run time, market labels, keyword count, and request count. Does not
contain the API key.

---

## Tests

You can run the test suite without an API key or internet connection:

```bash
python3 -m unittest
```

Tests use saved JSON fixtures. They do not make live API requests and cost no
credits.

---

## Troubleshooting

- `SEARCHAPI_KEY not found`: The `.env` file is missing or the key variable is
  not set. Copy `.env.example` to `.env` and add your key.

- `No usable keywords found`: `keywords.txt` is empty or contains only blank
  lines. Add at least one keyword.

- `Market is missing required field`: A market object in `markets.json` is
  missing `name`, `location`, `gl`, or `hl`. The error message names the missing
  field.

- `Empty organic results for [keyword] in [market]`: The API request succeeded
  but returned no organic results for that combination. This appears as a
  warning in the console and does not produce a report for that keyword-market
  pair.

- `python3: command not found`: Use `python compare_markets.py` instead, or
  confirm that your virtual environment is activated.

---

## Limitations

- **Snapshot, not history.** Each run captures a point in time. It does not
  prove a lasting ranking trend or guarantee that a new page will rank.
- **Two or three markets per Markdown report.** The per-keyword report is
  designed for readability at two or three markets. The CSV scales to any number
  of markets.
- **Domain differences are signals, not conclusions.** A domain appearing in one
  captured SERP and not another does not prove why that difference exists.

---

## Further developments

- `google_rank_tracking` support for up to 100 results per market
- Topic clustering to surface theme-level gaps faster
- Lightweight web or dashboard UI
- Multi-language keyword input
- Google News, Images, and Videos verticals
- Scheduled re-runs and trend charts

---

## License

MIT

---

## Acknowledgements

Search data powered by
[SearchApi](https://www.searchapi.io/?utm_source=dev&utm_medium=ambassador&utm_campaign=warish.co).
