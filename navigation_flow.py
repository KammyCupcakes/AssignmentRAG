from contextvars import ContextVar
from numbers import Real

from route_parser import normalize_algorithm, parse_route_query


# Context variable for storing route images (request-scoped, thread-safe)
_route_image_context: ContextVar[str | None] = ContextVar('route_image', default=None)

MAX_ROUTE_ATTEMPTS = 6

DISTANCE_KEYS = [
    "distance",
    "total_distance",
    "walking_distance",
    "distance_m",
    "distance_meters",
    "total_distance_m",
    "distance_miles",
]

TIME_KEYS = [
    "estimated_time",
    "walk_time",
    "walking_time",
    "estimated_walk_time",
    "time_minutes",
    "estimated_time_min",
    "walk_time_minutes",
]

ROUTE_KEYS = [
    "path",
    "route",
    "nodes",
    "coordinates",
]


def unique_values(values: list[str]) -> list[str]:
    deduped = []
    for value in values:
        if value and value not in deduped:
            deduped.append(value)
    return deduped


def routing_candidates_for(resolution: dict | None, display_name: str | None) -> list[str]:
    candidates = []
    if display_name:
        candidates.append(display_name)
    if resolution:
        candidates.extend(resolution.get("routing_candidates") or [])
    return unique_values(candidates)


def add_attempt(attempts: list[tuple[str, str]], start: str, destination: str) -> None:
    pair = (start, destination)
    if pair not in attempts and len(attempts) < MAX_ROUTE_ATTEMPTS:
        attempts.append(pair)


def build_routing_attempts(start_resolution: dict | None, destination_resolution: dict | None) -> list[tuple[str, str]]:
    start_display = start_resolution.get("canonical_name") if start_resolution else None
    destination_display = destination_resolution.get("canonical_name") if destination_resolution else None
    start_candidates = routing_candidates_for(start_resolution, start_display)
    destination_candidates = routing_candidates_for(destination_resolution, destination_display)

    if not start_candidates or not destination_candidates:
        return []

    attempts = []
    canonical_start = start_candidates[0]
    canonical_destination = destination_candidates[0]

    add_attempt(attempts, canonical_start, canonical_destination)

    for destination in destination_candidates[1:]:
        add_attempt(attempts, canonical_start, destination)

    for start in start_candidates[1:]:
        add_attempt(attempts, start, canonical_destination)

    for start in start_candidates[1:]:
        for destination in destination_candidates[1:]:
            add_attempt(attempts, start, destination)

    return attempts


def format_algorithm_name(algorithm: str) -> str:
    normalized = normalize_algorithm(algorithm)
    if normalized == "dijkstra":
        return "Dijkstra"
    return "A*"


def has_useful_value(value) -> bool:
    if value is None:
        return False
    if isinstance(value, (list, tuple, dict, set, str)):
        return len(value) > 0
    return True


def first_useful_field(route_result: dict, keys: list[str]):
    for key in keys:
        if key in route_result and has_useful_value(route_result[key]):
            return key, route_result[key]
    return None, None


def is_usable_route_result(route_result) -> bool:
    if not isinstance(route_result, dict) or not route_result:
        return False

    if route_result.get("success") is False:
        return False

    return route_result_has_path(route_result)


def format_distance(value, key: str) -> str:
    if isinstance(value, Real):
        if "mile" in key:
            return f"{value:.2f} miles"
        if key.endswith("_m") or "meter" in key:
            return f"{value:g} meters"
        return f"{value:g}"
    return str(value)


def format_time(value, key: str) -> str:
    if isinstance(value, Real):
        if "min" in key or "time" in key or "walk" in key:
            return f"{value:.1f} minutes"
        return f"{value:g}"
    return str(value)


def route_result_has_path(route_result: dict | None) -> bool:
    if not isinstance(route_result, dict):
        return False

    for key in ROUTE_KEYS:
        value = route_result.get(key)
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            return True
        if isinstance(value, set) and len(value) >= 2:
            return True

    return False


def validate_route_request(route_info: dict) -> tuple[str | None, str | None, str | None]:
    clarification = missing_or_unresolved_message(route_info)
    if clarification:
        return clarification, None, None

    start = route_info.get("resolved_start") or route_info.get("start")
    destination = route_info.get("resolved_destination") or route_info.get("destination")

    if not start:
        return "I can help with that route. Where are you starting from?", None, None

    if not destination:
        return "I can help with that route. Where are you trying to go?", None, None

    if start.strip().lower() == destination.strip().lower():
        return (
            f"Your start and destination look the same: {start}. "
            "Please provide two different campus locations.",
            None,
            None,
        )

    return None, start, destination


def route_failure_message(start: str, destination: str, detail: str | None = None) -> str:
    if detail == "no_nearby_paths":
        return (
            "I found your start and destination, but I could not find walkable campus paths "
            f"near one of those locations ({start} or {destination}). "
            "Please try a nearby campus building name."
        )

    if detail == "no_path":
        return (
            f"I found both locations, but I could not build a walkable path between {start} and {destination}. "
            "Please try a different nearby campus landmark."
        )

    return (
        "I recognized the route request, but I could not generate a route "
        f"between {start} and {destination} right now."
    )


def validate_route_result(route_result, start: str, destination: str) -> tuple[bool, str | None]:
    if not isinstance(route_result, dict) or not route_result:
        return False, None

    if route_result.get("success") is False:
        error_text = str(route_result.get("error") or "").strip().lower()
        if "no roads near your location" in error_text:
            return False, route_failure_message(start, destination, detail="no_nearby_paths")
        return False, None

    if not route_result_has_path(route_result):
        return False, route_failure_message(start, destination, detail="no_path")

    return True, None


def generate_basic_route_guidance(
    start: str,
    destination: str,
    distance: str | None = None,
    walk_time: str | None = None,
    route_result: dict | None = None,
    used_fallback_coordinate: bool = False,
) -> list[str]:
    guidance = [f"Start at {start}."]

    if route_result_has_path(route_result):
        guidance.append(f"Follow the computed campus walking route toward {destination}.")
    else:
        guidance.append(f"Follow the campus walking route toward {destination}.")

    if distance:
        guidance.append(f"Continue for about {distance}.")

    if walk_time:
        guidance.append(f"You should arrive near {destination} in about {walk_time}.")
    else:
        guidance.append(f"Continue until you reach the area near {destination}.")

    if used_fallback_coordinate:
        guidance.append("Location matching used verified campus coordinates where needed.")

    return guidance


def generate_path_aware_guidance(
    start: str,
    destination: str,
    route_result: dict,
    distance: str | None = None,
    walk_time: str | None = None,
) -> list[str]:
    if not route_result_has_path(route_result):
        return generate_basic_route_guidance(
            start,
            destination,
            distance=distance,
            walk_time=walk_time,
            route_result=None,
            used_fallback_coordinate=bool(route_result.get("used_fallback_coordinate")),
        )

    guidance = [
        f"Start at {start}.",
        f"Follow the computed campus walking path from the {start} area toward {destination}.",
    ]

    if distance:
        guidance.append(f"Continue along the route for about {distance}.")

    guidance.append(f"Arrive at the nearest available walkable point near {destination}.")
    return guidance


def format_route_response(route_result: dict, start: str, destination: str, algorithm: str) -> str:
    distance_key, distance_value = first_useful_field(route_result, DISTANCE_KEYS)
    distance = format_distance(distance_value, distance_key) if distance_key else None

    time_key, time_value = first_useful_field(route_result, TIME_KEYS)
    walk_time = format_time(time_value, time_key) if time_key else None

    lines = [
        f"Route found: {start} → {destination}",
        "",
    ]

    if walk_time:
        lines.append(f"Estimated walk: {walk_time}")

    if distance:
        lines.append(f"Distance: {distance}")

    lines.extend(
        [
            f"Route type: shortest walking route using {format_algorithm_name(algorithm)}",
            "",
            "Walking guidance:",
        ]
    )

    for index, step in enumerate(
        generate_path_aware_guidance(
            start,
            destination,
            route_result,
            distance=distance,
            walk_time=walk_time,
        ),
        start=1,
    ):
        lines.append(f"{index}. {step}")

    if route_result_has_path(route_result):
        lines.append("")
        lines.append(
            "Note: This is campus walking guidance based on available map path data, not indoor turn-by-turn directions."
        )

    lines.append("")
    lines.append("Status: Route generated successfully.")
    return "\n".join(lines)


def missing_or_unresolved_message(route_info: dict) -> str | None:
    if route_info.get("clarification_reason") == "unresolved_start":
        return (
            "I can help with that route, but I could not confidently identify your "
            "starting location. Can you rephrase it using a campus building name?"
        )

    if route_info.get("clarification_reason") == "unresolved_destination":
        return (
            "I can help with that route, but I could not confidently identify your "
            "destination. Can you rephrase it using a campus building name?"
        )

    if route_info.get("missing") == "start":
        return "I can help with that route. Where are you starting from?"

    if route_info.get("missing") == "destination":
        return "I can help with that route. Where are you trying to go?"

    return None


def handle_route_query(user_query: str, get_route) -> str | None:
    route_info = parse_route_query(user_query)
    if not route_info["is_route"]:
        return None

    return handle_route_info(route_info, get_route)


def handle_route_info(route_info: dict, get_route) -> str:
    """Process route info and return response text. Captures image in context variable if generated."""
    # Reset context at start of new route handling
    _route_image_context.set(None)
    
    validation_message, start, destination = validate_route_request(route_info)
    if validation_message:
        return validation_message

    algorithm = normalize_algorithm(route_info.get("algorithm"))

    route_attempts = build_routing_attempts(
        route_info.get("start_resolution"),
        route_info.get("destination_resolution"),
    )
    if not route_attempts:
        route_attempts = [(start, destination)]

    failure_message = None
    for route_start, route_destination in route_attempts:
        try:
            route_result = get_route(
                route_start,
                route_destination,
                algorithm=algorithm,
                show_map=True,
            )
        except Exception:
            continue

        is_valid, validation_failure_message = validate_route_result(route_result, start, destination)
        if validation_failure_message:
            failure_message = validation_failure_message

        if is_valid and is_usable_route_result(route_result):
            # Capture image in context if present
            if route_result.get("image"):
                _route_image_context.set(route_result["image"])
            return format_route_response(route_result, start, destination, algorithm)

    if failure_message:
        return failure_message

    return route_failure_message(start, destination)
