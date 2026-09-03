"""SearchApi request boundary and credential-safe errors."""

import requests


class SearchApiError(RuntimeError):
    """Describe a SearchApi failure without exposing request credentials."""


def _redact_secret(value, secret):
    """Replace a credential in diagnostic text before it reaches the terminal."""
    text = str(value) if value is not None else "unavailable"
    return text.replace(secret, "REDACTED") if secret else text


def search_api(engine, query, api_key, location=None, gl=None, hl=None):
    """Send one request to SearchApi and return the parsed JSON."""
    url = "https://www.searchapi.io/api/v1/search"
    params = {
        "engine": engine,
        "q": query,
        "api_key": api_key,
    }
    if location:
        params["location"] = location
    if gl:
        params["gl"] = gl
    if hl:
        params["hl"] = hl

    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
    except requests.exceptions.Timeout:
        # A timeout is different from an API rejection: the server did not
        # answer within our limit, so the user can safely retry later.
        raise SearchApiError("SearchApi request timed out after 30 seconds.") from None
    except requests.exceptions.ConnectionError:
        raise SearchApiError(
            "Could not connect to SearchApi. Check the internet connection and try again."
        ) from None
    except requests.exceptions.HTTPError as exc:
        error_response = exc.response
        status = getattr(error_response, "status_code", "unknown")
        requested_url = _redact_secret(getattr(error_response, "url", None), api_key)
        response_preview = _redact_secret(
            getattr(error_response, "text", ""), api_key
        )[:500]
        # Suppress the original requests traceback because it may contain the
        # unredacted query URL, including the API key.
        raise SearchApiError(
            f"SearchApi returned HTTP {status}. "
            f"URL: {requested_url}. Response preview: {response_preview}"
        ) from None
    except requests.exceptions.RequestException:
        raise SearchApiError(
            "SearchApi request failed before a response was received."
        ) from None

    try:
        return response.json()
    except ValueError:
        # Successful HTTP status does not guarantee that the body is JSON.
        raise SearchApiError(
            "SearchApi returned a response that was not valid JSON."
        ) from None
