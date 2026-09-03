"""Collection loop and top-level application orchestration."""

from datetime import datetime, timezone

from .analysis import build_csv_rows, get_items
from .api import SearchApiError, search_api
from .config import (
    KEYWORDS_PATH,
    MARKDOWN_MARKET_LIMIT,
    MARKETS_PATH,
    OUTPUT_DIR,
    SEARCH_ENGINE,
    load_api_key,
    load_keywords,
    load_markets,
)
from .outputs import (
    create_run_paths,
    make_report,
    safe_filename,
    save_raw_response,
    unique_safe_filename,
    write_csv,
    write_run_manifest,
)


def run_plan_message(keyword_count, market_count):
    """Explain output formats and request volume before any credits are spent."""
    request_count = keyword_count * market_count
    lines = [
        f"{keyword_count} keywords × {market_count} markets = {request_count} requests.",
    ]
    if market_count <= MARKDOWN_MARKET_LIMIT:
        lines.append("Markdown reports, CSV, and raw JSON will be generated.")
    else:
        lines.extend(
            [
                "Markdown reports will not be generated because v1 supports up to "
                f"{MARKDOWN_MARKET_LIMIT} report markets.",
                f"CSV and raw JSON will include all {market_count} markets.",
            ]
        )
    return "\n".join(lines)


def collect_keyword_data(
    keyword,
    api_key,
    locations,
    raw_dir=None,
    keyword_stem=None,
    market_stems=None,
    failures=None,
):
    """Fetch one keyword across locations and preserve safe partial results."""
    results = {}
    market_stems = market_stems or {}
    failures = failures if failures is not None else []
    for loc in locations:
        print(f"\nFetching '{keyword}' for {loc['name']}...")
        try:
            data = search_api(
                SEARCH_ENGINE,
                keyword,
                api_key,
                location=loc["location"],
                gl=loc["gl"],
                hl=loc["hl"],
            )
        except SearchApiError as exc:
            # Request errors are already credential-safe. Recording them lets
            # the run continue while keeping the missing evidence explicit.
            failures.append(
                {
                    "keyword": keyword,
                    "market": loc["name"],
                    "error": str(exc),
                }
            )
            print(f"Failed '{keyword}' for {loc['name']}: {exc}")
            continue

        if raw_dir is not None:
            # Save immediately after the request, before parsing or report code
            # can select, normalize, or otherwise transform the evidence.
            raw_path = save_raw_response(
                data,
                raw_dir,
                keyword_stem or safe_filename(keyword),
                market_stems.get(loc["name"], safe_filename(loc["name"])),
            )
            print(f"Saved raw response to: {raw_path}")

        results[loc["name"]] = data
        organic_results = get_items(data)
        if organic_results:
            print(f"Got {len(organic_results)} organic results for {loc['name']}.")
        else:
            # Empty parsing is a data-quality warning, not evidence that a
            # market has no competition or no search results.
            print(
                f"Warning: no organic results were parsed for {loc['name']}. "
                "Review the saved raw response before drawing conclusions."
            )
    return results


def main(keywords_path=KEYWORDS_PATH, markets_path=MARKETS_PATH, output_root=OUTPUT_DIR):
    """Coordinate one complete run and return 1 when request failures occurred."""
    # Configuration errors stop before credentials, output folders, or API calls.
    keywords = load_keywords(keywords_path)
    locations = load_markets(markets_path)
    markdown_enabled = len(locations) <= MARKDOWN_MARKET_LIMIT
    print(run_plan_message(len(keywords), len(locations)))

    api_key = load_api_key()
    started_at = datetime.now(timezone.utc)
    run_paths = create_run_paths(output_root, started_at)

    # Reserve unique slugs once per run so similarly punctuated labels cannot
    # point to the same raw file or report.
    used_market_stems = set()
    market_stems = {
        loc["name"]: unique_safe_filename(loc["name"], used_market_stems)
        for loc in locations
    }
    used_keyword_stems = set()
    csv_rows = []
    failures = []
    requests_attempted = 0
    requests_completed = 0
    markdown_report_count = 0

    for keyword in keywords:
        safe_name = unique_safe_filename(keyword, used_keyword_stems)
        keyword_failures = []
        requests_attempted += len(locations)
        raw_results = collect_keyword_data(
            keyword,
            api_key,
            locations,
            raw_dir=run_paths["raw_dir"],
            keyword_stem=safe_name,
            market_stems=market_stems,
            failures=keyword_failures,
        )
        failures.extend(keyword_failures)
        requests_completed += len(raw_results)
        csv_rows.extend(
            build_csv_rows(
                run_paths["run_id"],
                started_at.date(),
                keyword,
                raw_results,
                locations,
            )
        )

        if markdown_enabled and not keyword_failures:
            report_path = run_paths["reports_dir"] / f"{safe_name}.md"
            report_path.write_text(
                make_report(
                    keyword,
                    raw_results,
                    locations,
                    run_id=run_paths["run_id"],
                    research_date=started_at.date(),
                ),
                encoding="utf-8",
            )
            markdown_report_count += 1
            print(f"Saved comparison report to: {report_path}")
        elif markdown_enabled:
            # A report with a missing requested market could look complete even
            # though its comparison is not. Raw and CSV partial evidence remain.
            print(
                f"Skipped Markdown report for '{keyword}' because one or more "
                "market requests failed."
            )

    csv_path = write_csv(csv_rows, run_paths["run_dir"] / "results.csv")
    print(f"Saved CSV results to: {csv_path}")

    markdown_reports_skipped = len(keywords) - markdown_report_count
    markdown_reports_generated = markdown_report_count == len(keywords)
    markdown_skip_reason = None
    if not markdown_enabled:
        markdown_skip_reason = (
            f"More than {MARKDOWN_MARKET_LIMIT} markets were configured; "
            "CSV and raw JSON were generated instead."
        )
    elif failures:
        markdown_skip_reason = (
            "One or more keyword reports were skipped because request evidence "
            "was incomplete."
        )

    manifest_path = write_run_manifest(
        run_paths["run_dir"],
        run_paths["run_id"],
        started_at,
        SEARCH_ENGINE,
        locations,
        keyword_count=len(keywords),
        requests_attempted=requests_attempted,
        requests_completed=requests_completed,
        markdown_reports_generated=markdown_reports_generated,
        markdown_skip_reason=markdown_skip_reason,
        markdown_report_count=markdown_report_count,
        markdown_reports_skipped=markdown_reports_skipped,
        failures=failures,
    )
    print(f"Saved run manifest to: {manifest_path}")
    print(
        f"Completed {requests_completed} of {requests_attempted} requests. "
        f"Run folder: {run_paths['run_dir']}"
    )
    return 1 if failures else 0
