import time

from campus_locations import resolve_location
from navigation_flow import handle_route_info, missing_or_unresolved_message
from route_parser import normalize_algorithm, parse_route_continuation_query, parse_route_query


PENDING_ROUTE_STATE = {}
LAST_ROUTE_CONTEXT = {}
PENDING_ROUTE_TIMEOUT_SECONDS = 300
LAST_ROUTE_CONTEXT_TIMEOUT_SECONDS = 600
PENDING_ROUTE_MAX_FAILED_FILLS = 2
CANCEL_PENDING_ROUTE_WORDS = {"cancel", "nevermind", "never mind", "stop"}

INFO_QUESTION_STARTERS = (
    "where ",
    "what ",
    "when ",
    "who ",
    "why ",
    "tell me",
    "can i ",
    "can you ",
    "is there ",
    "are there ",
    "how much ",
)


def current_time() -> float:
    return time.time()


def clear_pending_route() -> None:
    PENDING_ROUTE_STATE.clear()


def clear_last_route_context() -> None:
    LAST_ROUTE_CONTEXT.clear()


def pending_route_is_active(now: float | None = None) -> bool:
    if not PENDING_ROUTE_STATE:
        return False

    checked_at = current_time() if now is None else now
    created_at = PENDING_ROUTE_STATE.get("created_at", checked_at)
    if checked_at - created_at > PENDING_ROUTE_TIMEOUT_SECONDS:
        clear_pending_route()
        return False

    return True


def has_active_last_route_context(now: float | None = None) -> bool:
    if not LAST_ROUTE_CONTEXT:
        return False

    checked_at = current_time() if now is None else now
    created_at = LAST_ROUTE_CONTEXT.get("created_at", checked_at)
    if checked_at - created_at > LAST_ROUTE_CONTEXT_TIMEOUT_SECONDS:
        clear_last_route_context()
        return False

    return True


def get_last_route_context(now: float | None = None) -> dict | None:
    if not has_active_last_route_context(now=now):
        return None
    return dict(LAST_ROUTE_CONTEXT)


def _display_name(route_info: dict, slot: str) -> str | None:
    resolved_key = f"resolved_{slot}"
    return route_info.get(resolved_key) or route_info.get(slot)


def _store_resolution(route_info: dict, slot: str) -> dict | None:
    return route_info.get(f"{slot}_resolution")


def start_pending_route(route_info: dict, now: float | None = None) -> str:
    clear_pending_route()

    PENDING_ROUTE_STATE.update(
        {
            "missing": route_info.get("missing"),
            "start": _display_name(route_info, "start"),
            "destination": _display_name(route_info, "destination"),
            "resolved_start": route_info.get("resolved_start"),
            "resolved_destination": route_info.get("resolved_destination"),
            "start_resolution": _store_resolution(route_info, "start"),
            "destination_resolution": _store_resolution(route_info, "destination"),
            "algorithm": normalize_algorithm(route_info.get("algorithm")),
            "route_preference": route_info.get("route_preference"),
            "created_at": current_time() if now is None else now,
            "failed_fills": 0,
        }
    )

    return missing_or_unresolved_message(route_info) or (
        "I can help with that route. Where are you starting from?"
    )


def set_last_route_context(route_info: dict, now: float | None = None) -> None:
    start = _display_name(route_info, "start")
    destination = _display_name(route_info, "destination")
    if not start or not destination:
        return

    LAST_ROUTE_CONTEXT.clear()
    LAST_ROUTE_CONTEXT.update(
        {
            "active": True,
            "last_start": start,
            "last_destination": destination,
            "current_location": destination,
            "algorithm": normalize_algorithm(route_info.get("algorithm")),
            "route_preference": route_info.get("route_preference") or "default",
            "created_at": current_time() if now is None else now,
        }
    )


def _is_successful_route_response(response: str | None) -> bool:
    return bool(
        isinstance(response, str)
        and response.startswith("Route found:")
        and "Status: Route generated successfully." in response
    )


def handle_route_info_with_context(route_info: dict, get_route, now: float | None = None) -> str:
    response = handle_route_info(route_info, get_route)
    if _is_successful_route_response(response):
        set_last_route_context(route_info, now=now)
    return response


def _is_cancel_message(user_query: str) -> bool:
    return user_query.strip().lower() in CANCEL_PENDING_ROUTE_WORDS


def _is_clear_non_route_info_question(user_query: str) -> bool:
    lowered = user_query.strip().lower()
    return any(lowered.startswith(starter) for starter in INFO_QUESTION_STARTERS)


def _unresolved_follow_up_message(missing: str | None) -> str:
    if missing == "destination":
        return (
            "I can help with that route, but I could not confidently identify your "
            "destination. Can you rephrase it using a campus building name?"
        )

    return (
        "I can help with that route, but I could not confidently identify your "
        "starting location. Can you rephrase it using a campus building name?"
    )


def _route_info_from_pending(filled_resolution: dict, user_query: str) -> dict:
    missing = PENDING_ROUTE_STATE.get("missing")

    start = PENDING_ROUTE_STATE.get("start")
    destination = PENDING_ROUTE_STATE.get("destination")
    start_resolution = PENDING_ROUTE_STATE.get("start_resolution")
    destination_resolution = PENDING_ROUTE_STATE.get("destination_resolution")
    resolved_start = PENDING_ROUTE_STATE.get("resolved_start")
    resolved_destination = PENDING_ROUTE_STATE.get("resolved_destination")

    if missing == "start":
        start = filled_resolution["canonical_name"]
        resolved_start = filled_resolution["canonical_name"]
        start_resolution = filled_resolution
    else:
        destination = filled_resolution["canonical_name"]
        resolved_destination = filled_resolution["canonical_name"]
        destination_resolution = filled_resolution

    return {
        "is_route": True,
        "start": start,
        "destination": destination,
        "resolved_start": resolved_start,
        "resolved_destination": resolved_destination,
        "start_resolution": start_resolution,
        "destination_resolution": destination_resolution,
        "algorithm": PENDING_ROUTE_STATE.get("algorithm"),
        "route_preference": PENDING_ROUTE_STATE.get("route_preference") or "default",
        "needs_clarification": False,
        "missing": None,
        "clarification_reason": None,
        "raw_query": user_query,
    }


def _complete_pending_route(user_query: str, get_route) -> str:
    missing = PENDING_ROUTE_STATE.get("missing")
    filled_resolution = resolve_location(user_query)

    if filled_resolution.get("status") != "resolved":
        PENDING_ROUTE_STATE["failed_fills"] = PENDING_ROUTE_STATE.get("failed_fills", 0) + 1
        if PENDING_ROUTE_STATE["failed_fills"] >= PENDING_ROUTE_MAX_FAILED_FILLS:
            clear_pending_route()
            return (
                "I still could not confidently identify that campus location, so I "
                "canceled this route request. Please start again with two campus building names."
            )
        return _unresolved_follow_up_message(missing)

    route_info = _route_info_from_pending(filled_resolution, user_query)
    clear_pending_route()
    return handle_route_info_with_context(route_info, get_route)


def try_complete_pending_route(user_query: str, get_route, now: float | None = None) -> str | None:
    if not pending_route_is_active(now=now):
        return None

    if _is_cancel_message(user_query):
        clear_pending_route()
        return "Okay, I canceled that route request."

    route_info = parse_route_query(user_query)
    if route_info["is_route"]:
        if missing_or_unresolved_message(route_info):
            return start_pending_route(route_info, now=now)

        clear_pending_route()
        return handle_route_info_with_context(route_info, get_route, now=now)

    if _is_clear_non_route_info_question(user_query):
        return None

    return _complete_pending_route(user_query, get_route)


def _resolved_name(resolution: dict | None) -> str | None:
    if resolution and resolution.get("status") == "resolved":
        return resolution.get("canonical_name")
    return None


def _route_info_from_locations(
    raw_query: str,
    start_text: str | None,
    destination_text: str | None,
    algorithm: str | None,
    route_preference: str | None,
) -> dict:
    start_resolution = resolve_location(start_text) if start_text else None
    destination_resolution = resolve_location(destination_text) if destination_text else None
    resolved_start = _resolved_name(start_resolution)
    resolved_destination = _resolved_name(destination_resolution)
    clarification_reason = None
    missing = None

    if start_text and not resolved_start:
        clarification_reason = "unresolved_start"
        missing = "start"
    elif destination_text and not resolved_destination:
        clarification_reason = "unresolved_destination"
        missing = "destination"

    return {
        "is_route": True,
        "start": start_text,
        "destination": destination_text,
        "resolved_start": resolved_start,
        "resolved_destination": resolved_destination,
        "start_resolution": start_resolution,
        "destination_resolution": destination_resolution,
        "algorithm": normalize_algorithm(algorithm),
        "route_preference": route_preference or "default",
        "needs_clarification": clarification_reason is not None or not start_text or not destination_text,
        "missing": missing,
        "clarification_reason": clarification_reason,
        "raw_query": raw_query,
    }


def handle_route_continuation_query(user_query: str, get_route, now: float | None = None) -> str | None:
    continuation = parse_route_continuation_query(user_query)
    if not continuation["is_continuation"]:
        return None

    context = get_last_route_context(now=now)
    explicit_start = continuation.get("explicit_start")
    if explicit_start:
        start = explicit_start
    elif context:
        start = context.get("current_location")
    else:
        return (
            "I can help with that route, but I need your starting location first. "
            "Where are you starting from?"
        )

    route_info = _route_info_from_locations(
        continuation["raw_query"],
        start,
        continuation.get("destination"),
        continuation.get("algorithm"),
        continuation.get("route_preference"),
    )
    return handle_route_info_with_context(route_info, get_route, now=now)
