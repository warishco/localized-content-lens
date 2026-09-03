"""Organic-result normalization and cross-market domain analysis."""

from urllib.parse import urlparse


def first_value(item, *keys):
    """Return the first non-empty value from the given keys."""
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return value
    return ""


def normalize_domain(domain):
    """Normalize a domain so equivalent sites compare as the same value."""
    if not domain:
        return ""
    normalized = domain.strip().casefold().rstrip(".")
    # Google may return either example.com or www.example.com for the same site;
    # removing only a leading www keeps set comparisons consistent.
    return normalized[4:] if normalized.startswith("www.") else normalized


def get_domain(link):
    """Extract a normalized hostname from a complete URL."""
    if not link:
        return ""
    return normalize_domain(urlparse(link).hostname or "")


def normalize_result(item):
    """Turn a raw result item into a consistent internal shape."""
    link = first_value(item, "link", "url")
    supplied_domain = first_value(item, "domain")
    return {
        "position": item.get("position"),
        "title": first_value(item, "title", "name"),
        "link": link,
        "snippet": first_value(item, "snippet", "description"),
        "domain": normalize_domain(supplied_domain) or get_domain(link),
    }


def get_items(data):
    """Return organic Google results, or an empty list for a missing/wrong shape."""
    # News and generic result collections are deliberately excluded from v1 so
    # every downstream comparison has one clear meaning: organic web results.
    organic_results = data.get("organic_results")
    return organic_results if isinstance(organic_results, list) else []


def compare_domains(results_by_market):
    """Compare normalized organic domains across any number of markets."""
    market_names = list(results_by_market)
    domains_by_market = {}
    for market_name, response in results_by_market.items():
        domains = {
            normalize_result(item)["domain"] for item in get_items(response)
        }
        # Missing links or domains normalize to an empty string; discarding it
        # prevents missing data from appearing as a real shared domain.
        domains.discard("")
        domains_by_market[market_name] = domains

    # The presence map is a compact domain-by-market table. It preserves market
    # order so later Markdown and CSV output remains predictable for users.
    all_domains = set().union(*domains_by_market.values()) if market_names else set()
    presence_by_domain = {
        domain: [
            market_name
            for market_name in market_names
            if domain in domains_by_market[market_name]
        ]
        for domain in sorted(all_domains)
    }

    # "Unique" means present only in one captured result set for this run. It
    # does not claim that the domain can never rank in another market.
    unique_by_market = {
        market_name: {
            domain
            for domain in domains
            if len(presence_by_domain[domain]) == 1
        }
        for market_name, domains in domains_by_market.items()
    }
    shared_by_all = {
        domain
        for domain, present_markets in presence_by_domain.items()
        if len(present_markets) == len(market_names)
    }

    return {
        "domains_by_market": domains_by_market,
        "presence_by_domain": presence_by_domain,
        "unique_by_market": unique_by_market,
        "shared_by_all": shared_by_all,
    }


def build_csv_rows(run_id, research_date, keyword, raw, locations):
    """Flatten one keyword's organic results into sortable CSV row dictionaries."""
    market_names = [loc["name"] for loc in locations]
    comparison = compare_domains(
        {name: raw.get(name, {}) for name in market_names}
    )
    rows = []
    for loc in locations:
        market_name = loc["name"]
        unique_domains = comparison["unique_by_market"][market_name]
        for item in get_items(raw.get(market_name, {})):
            result = normalize_result(item)
            rows.append(
                {
                    "run_id": run_id,
                    "research_date": str(research_date),
                    "keyword": keyword,
                    "market": market_name,
                    "location": loc["location"],
                    "gl": loc["gl"],
                    "hl": loc["hl"],
                    "position": result["position"],
                    "title": result["title"],
                    "domain": result["domain"],
                    "link": result["link"],
                    "snippet": result["snippet"],
                    "unique_to_market": result["domain"] in unique_domains,
                }
            )
    return rows
