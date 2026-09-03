"""Safe output paths and JSON, CSV, and Markdown writers."""

import csv
import hashlib
import json
import re
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path

from .analysis import compare_domains, get_items, normalize_result
from .config import CSV_FIELDS, MARKDOWN_MARKET_LIMIT, REQUIRED_MARKET_FIELDS, SEARCH_ENGINE


def safe_filename(text):
    """Turn user-provided text into a readable, cross-platform ASCII slug."""
    # Unicode normalization keeps readable letters such as é as e, while the
    # regular expression converts every punctuation run into one underscore.
    normalized = unicodedata.normalize("NFKD", text.casefold())
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_text).strip("_")
    return slug[:80].rstrip("_") or "item"


def unique_safe_filename(text, used_names):
    """Reserve a safe filename and add a stable suffix only on collision."""
    base_name = safe_filename(text)
    if base_name not in used_names:
        used_names.add(base_name)
        return base_name

    # Different inputs can produce the same slug (for example CRM! and CRM?).
    # A short content hash preserves readability while preventing overwrites.
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
    candidate = f"{base_name[:71]}_{digest}"
    counter = 2
    while candidate in used_names:
        candidate = f"{base_name[:68]}_{digest}_{counter}"
        counter += 1

    used_names.add(candidate)
    return candidate


def create_run_paths(output_root, started_at=None):
    """Create one timestamped run directory with separate raw and report areas."""
    output_root = Path(output_root)
    started_at = started_at or datetime.now(timezone.utc)
    base_run_id = started_at.strftime("%Y%m%d-%H%M%S")
    run_id = base_run_id
    counter = 2

    # A numbered suffix handles two runs started in the same second without
    # allowing the newer run to overwrite evidence or human analysis.
    while True:
        run_dir = output_root / run_id
        try:
            run_dir.mkdir(parents=True)
            break
        except FileExistsError:
            run_id = f"{base_run_id}-{counter}"
            counter += 1

    raw_dir = run_dir / "raw"
    reports_dir = run_dir / "reports"
    raw_dir.mkdir()
    reports_dir.mkdir()
    return {
        "run_id": run_id,
        "run_dir": run_dir,
        "raw_dir": raw_dir,
        "reports_dir": reports_dir,
    }


def save_raw_response(response_data, raw_dir, keyword_stem, market_stem):
    """Save one complete API response before any parsing or normalization."""
    keyword_dir = Path(raw_dir) / safe_filename(keyword_stem)
    keyword_dir.mkdir(parents=True, exist_ok=True)
    raw_path = keyword_dir / f"{safe_filename(market_stem)}.json"

    # Exclusive creation makes raw evidence append-only within a run: an
    # accidental second write fails instead of silently replacing the first.
    with raw_path.open("x", encoding="utf-8") as raw_file:
        json.dump(response_data, raw_file, indent=2, ensure_ascii=False)
        raw_file.write("\n")
    return raw_path


def write_run_manifest(
    run_dir,
    run_id,
    started_at,
    engine,
    markets,
    keyword_count,
    requests_attempted,
    requests_completed,
    markdown_reports_generated=True,
    markdown_skip_reason=None,
    markdown_report_count=0,
    markdown_reports_skipped=0,
    failures=None,
):
    """Record reproducibility metadata without storing the SearchApi key."""
    # Copy only the public location fields so future additions to markets.json
    # cannot accidentally place an unrelated private value in the manifest.
    public_markets = [
        {field: market[field] for field in REQUIRED_MARKET_FIELDS}
        for market in markets
    ]
    manifest = {
        "run_id": run_id,
        "started_at": started_at.isoformat(),
        "engine": engine,
        "markets": public_markets,
        "keyword_count": keyword_count,
        "requests_attempted": requests_attempted,
        "requests_completed": requests_completed,
        "markdown_reports_generated": markdown_reports_generated,
        "markdown_skip_reason": markdown_skip_reason,
        "markdown_report_count": markdown_report_count,
        "markdown_reports_skipped": markdown_reports_skipped,
        # Failures contain only the keyword, market label, and the already
        # redacted SearchApiError message—never request credentials.
        "failures": failures or [],
    }
    manifest_path = Path(run_dir) / "run_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def write_csv(rows, csv_path):
    """Write API-derived rows with Python's CSV escaping and a fixed schema."""
    csv_path = Path(csv_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    # newline="" lets the csv module handle embedded line breaks correctly on
    # every operating system; exclusive mode protects an earlier run export.
    with csv_path.open("x", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return csv_path


def _single_line(value):
    """Collapse API text onto one line so it cannot break Markdown structure."""
    return " ".join(str(value).split())


def _table_cell(value):
    """Escape text that would otherwise create an extra Markdown table column."""
    return _single_line(value).replace("|", "\\|")


def _markdown_link_text(value):
    """Escape brackets from API titles before using them as Markdown link text."""
    # Search titles can contain labels such as [2026]; escaping prevents either
    # balanced or unmatched brackets from changing the generated link structure.
    text = _single_line(value)
    return text.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def markdown_results(data, limit=10):
    """Format a market's organic results as a sourced Markdown list."""
    lines = []
    for item in get_items(data)[:limit]:
        result = normalize_result(item)
        title = _markdown_link_text(result["title"]) or "Untitled result"
        link = result["link"]
        domain = result["domain"] or "Domain unavailable"
        position = result["position"]

        title_text = f"[{title}]({link})" if link else f"{title} *(link unavailable)*"
        if position in (None, ""):
            lines.append(f"- **Position unavailable:** {title_text} — {domain}")
        else:
            lines.append(f"{position}. {title_text} — {domain}")

        snippet = _single_line(result["snippet"])
        lines.append(f"   - **Snippet:** {snippet or 'Not available'}")

    if not lines:
        return "- No organic results were parsed. Review the raw JSON before drawing conclusions."
    return "\n".join(lines)


def markdown_market_table(locations):
    """Describe the exact location parameters used in this report."""
    lines = [
        "| Market | Location | `gl` | `hl` |",
        "| --- | --- | --- | --- |",
    ]
    for loc in locations:
        lines.append(
            f"| {_table_cell(loc['name'])} | {_table_cell(loc['location'])} | "
            f"{_table_cell(loc['gl'])} | {_table_cell(loc['hl'])} |"
        )
    return "\n".join(lines)


def markdown_domain_presence(comparison, market_names):
    """Build a domain-presence matrix with one dynamic column per market."""
    lines = [
        f"| Domain | {' | '.join(_table_cell(name) for name in market_names)} |",
        f"| --- | {' | '.join('---' for _ in market_names)} |",
    ]
    for domain, present_markets in comparison["presence_by_domain"].items():
        presence = ["Yes" if name in present_markets else "—" for name in market_names]
        lines.append(f"| {_table_cell(domain)} | {' | '.join(presence)} |")

    if not comparison["presence_by_domain"]:
        lines.append(f"| No parsed domains | {' | '.join('—' for _ in market_names)} |")
    return "\n".join(lines)


def make_report(keyword, raw, locations, run_id=None, research_date=None):
    """Build a source-backed comparison report for two or three markets."""
    if not 2 <= len(locations) <= MARKDOWN_MARKET_LIMIT:
        # Keep the presentation rule close to report generation; CSV and raw
        # output remain free to include larger market sets.
        raise ValueError("Markdown reports require two or three markets in v1.")

    research_date = research_date or date.today()
    market_names = [loc["name"] for loc in locations]
    comparison = compare_domains(
        {name: raw.get(name, {}) for name in market_names}
    )
    incomplete_markets = [
        name for name in market_names if not get_items(raw.get(name, {}))
    ]

    report = [
        f"# Market comparison: {keyword}",
        "",
        f"**Research date:** {research_date}",
        f"**Run ID:** {run_id or 'Not recorded'}",
        f"**Engine:** {SEARCH_ENGINE}",
        "",
        "## Markets compared",
        "",
        markdown_market_table(locations),
        "",
        "## Automated comparison",
        "",
        "This is a snapshot of the captured organic results. A domain marked as "
        "unique appeared in only one captured market in this run; it may rank "
        "elsewhere at another time or depth.",
        "",
    ]

    if incomplete_markets:
        report.extend(
            [
                "**Data quality warning:** No organic results were parsed for: "
                f"{', '.join(incomplete_markets)}. Domain comparisons may be "
                "incomplete; inspect the raw JSON before interpreting the gaps.",
                "",
            ]
        )

    report.extend(["### Top organic results", ""])
    for name in market_names:
        report.extend(
            [
                f"#### {name} top organic results",
                "",
                markdown_results(raw.get(name, {})),
                "",
            ]
        )

    report.extend(
        [
            "### Domain presence by market",
            "",
            markdown_domain_presence(comparison, market_names),
            "",
            "### Domains shared by all markets",
            "",
            "\n".join(
                f"- {domain}" for domain in sorted(comparison["shared_by_all"])
            )
            or "- None in this captured result set.",
            "",
            "### Domains unique to each market",
            "",
        ]
    )
    for name in market_names:
        unique_domains = comparison["unique_by_market"][name]
        report.extend(
            [
                f"#### Unique to {name}",
                "",
                "\n".join(f"- {domain}" for domain in sorted(unique_domains))
                or "- None in this captured result set.",
                "",
            ]
        )

    report.extend(
        [
            "## Human analysis",
            "",
            "Open the source links above before completing this section. Keep "
            "observations separate from conclusions.",
            "",
            "**Focus market(s):**",
            "",
            "**Content gap:**",
            "",
            "**Opportunity:**",
            "",
            "**Verification notes and source URLs:**",
            "",
        ]
    )
    return "\n".join(report)
