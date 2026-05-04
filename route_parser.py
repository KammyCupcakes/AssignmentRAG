import re


DEFAULT_ALGORITHM = "astar"


FROM_TO_PATTERNS = [
    r"\bhow\s+do\s+i\s+get\s+from\s+(.+?)\s+to\s+(.+)$",
    r"\bhow\s+can\s+i\s+get\s+from\s+(.+?)\s+to\s+(.+)$",
    r"\bhow\s+(?:do\s+i\s+)?go\s+from\s+(.+?)\s+to\s+(.+)$",
    r"\bhow\s+to\s+go\s+from\s+(.+?)\s+to\s+(.+)$",
    r"\btake\s+me\s+from\s+(.+?)\s+to\s+(.+)$",
    r"\bget\s+me\s+from\s+(.+?)\s+to\s+(.+)$",
    r"\bdirections\s+from\s+(.+?)\s+to\s+(.+)$",
    r"\broute\s+from\s+(.+?)\s+to\s+(.+)$",
    r"\bshortest\s+path\s+from\s+(.+?)\s+to\s+(.+)$",
    r"\bfastest\s+way\s+from\s+(.+?)\s+to\s+(.+)$",
    r"\bbest\s+way\s+from\s+(.+?)\s+to\s+(.+)$",
    r"\beasiest\s+way\s+from\s+(.+?)\s+to\s+(.+)$",
    r"\bnavigate\s+from\s+(.+?)\s+to\s+(.+)$",
    r"\bfrom\s+(.+?)\s+to\s+(.+)$",
]

TO_FROM_PATTERNS = [
    r"\bdirections\s+to\s+(.+?)\s+from\s+(.+)$",
    r"\bhow\s+do\s+i\s+get\s+to\s+(.+?)\s+from\s+(.+)$",
    r"\bhow\s+can\s+i\s+get\s+to\s+(.+?)\s+from\s+(.+)$",
    r"\bhow\s+(?:do\s+i\s+)?go\s+to\s+(.+?)\s+from\s+(.+)$",
    r"\bhow\s+to\s+go\s+to\s+(.+?)\s+from\s+(.+)$",
]

MISSING_START_PATTERNS = [
    r"\bhow\s+do\s+i\s+get\s+to\s+(.+)$",
    r"\bhow\s+can\s+i\s+get\s+to\s+(.+)$",
    r"\bdirections\s+to\s+(.+)$",
    r"\broute\s+to\s+(.+)$",
    r"\bnavigate\s+to\s+(.+)$",
]

MISSING_DESTINATION_PATTERNS = [
    r"\bhow\s+do\s+i\s+get\s+from\s+(.+)$",
    r"\bhow\s+can\s+i\s+get\s+from\s+(.+)$",
    r"\bdirections\s+from\s+(.+)$",
    r"\broute\s+from\s+(.+)$",
    r"\bnavigate\s+from\s+(.+)$",
]


def clean_location_text(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    cleaned = re.sub(
        r"\s+(?:using|with)\s+(?:a\s*\*|astar|dijkstra)\b.*$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\s+(?:a\s*\*|astar|dijkstra)\s+algorithm\b.*$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    return cleaned.strip(" \t\r\n.,!?;:")


def detect_algorithm(query: str) -> str:
    if re.search(r"\b(?:using|with)\s+dijkstra\b|\bdijkstra\s+algorithm\b", query, re.IGNORECASE):
        return "dijkstra"
    return DEFAULT_ALGORITHM


def detect_route_preference(query: str) -> str:
    lowered = query.lower()
    if "avoid stairs" in lowered or "accessible" in lowered:
        return "accessible"
    if "fastest" in lowered or "quickest" in lowered:
        return "fastest"
    if "shortest" in lowered:
        return "shortest"
    if "easiest" in lowered:
        return "easiest"
    if re.search(r"\bbest\b", lowered):
        return "best"
    return "default"


def route_result(
    query: str,
    is_route: bool,
    start=None,
    destination=None,
    needs_clarification=False,
    missing=None,
):
    return {
        "is_route": is_route,
        "start": start,
        "destination": destination,
        "algorithm": detect_algorithm(query),
        "route_preference": detect_route_preference(query) if is_route else None,
        "needs_clarification": needs_clarification,
        "missing": missing,
        "raw_query": query,
    }


def parse_route_query(query: str) -> dict:
    raw_query = query or ""
    normalized_query = re.sub(r"\s+", " ", raw_query).strip()

    if not normalized_query:
        return route_result(raw_query, False)

    for pattern in FROM_TO_PATTERNS:
        match = re.search(pattern, normalized_query, re.IGNORECASE)
        if match:
            start = clean_location_text(match.group(1))
            destination = clean_location_text(match.group(2))
            return route_result(
                raw_query,
                True,
                start=start or None,
                destination=destination or None,
                needs_clarification=not (start and destination),
                missing=None if start and destination else ("start" if not start else "destination"),
            )

    for pattern in TO_FROM_PATTERNS:
        match = re.search(pattern, normalized_query, re.IGNORECASE)
        if match:
            destination = clean_location_text(match.group(1))
            start = clean_location_text(match.group(2))
            return route_result(
                raw_query,
                True,
                start=start or None,
                destination=destination or None,
                needs_clarification=not (start and destination),
                missing=None if start and destination else ("start" if not start else "destination"),
            )

    for pattern in MISSING_START_PATTERNS:
        match = re.search(pattern, normalized_query, re.IGNORECASE)
        if match:
            destination = clean_location_text(match.group(1))
            return route_result(
                raw_query,
                True,
                destination=destination or None,
                needs_clarification=True,
                missing="start",
            )

    for pattern in MISSING_DESTINATION_PATTERNS:
        match = re.search(pattern, normalized_query, re.IGNORECASE)
        if match:
            start = clean_location_text(match.group(1))
            return route_result(
                raw_query,
                True,
                start=start or None,
                needs_clarification=True,
                missing="destination",
            )

    return route_result(raw_query, False)


def is_route_query(query: str) -> bool:
    return parse_route_query(query)["is_route"]
