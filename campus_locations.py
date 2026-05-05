import re
from difflib import SequenceMatcher


# Fallback coordinates are optional routing points, not official door locations.
# Keep them as None until a coordinate is verified from local project data/cache.
CAMPUS_LOCATIONS = {
    "university hall": {
        "canonical_name": "University Hall",
        "aliases": [
            "university hall",
            "u hall",
            "uhall",
            "u-hall",
            "univ hall",
            "university hall umb",
        ],
        "routing_candidates": [
            "University Hall",
            "University Hall UMass Boston",
            "University Hall, University of Massachusetts Boston",
        ],
        "fallback_coordinate": {
            "lat": 42.3130367,
            "lon": -71.0357383,
        },
        "type": "building",
    },
    "mccormack hall": {
        "canonical_name": "McCormack Hall",
        "aliases": [
            "mccormack",
            "mccormack hall",
            "mccormack building",
        ],
        "routing_candidates": [
            "McCormack Hall",
            "McCormack",
            "McCormack Building",
            "McCormack Hall UMass Boston",
            "McCormack Hall, University of Massachusetts Boston",
        ],
        "fallback_coordinate": {
            "lat": 42.3130494,
            "lon": -71.0388723,
        },
        "type": "building",
    },
    "quinn administration building": {
        "canonical_name": "Quinn Administration Building",
        "aliases": [
            "quinn",
            "quin",
            "quinn building",
            "quin building",
            "quinn administration",
            "quinn administration building",
        ],
        "routing_candidates": [
            "Quinn Administration Building",
            "Quinn Building",
            "Quinn",
            "Quinn Administration Building UMass Boston",
            "Quinn Administration Building, University of Massachusetts Boston",
        ],
        "fallback_coordinate": {
            "lat": 42.3141970,
            "lon": -71.0397057,
        },
        "type": "building",
    },
    "healey library": {
        "canonical_name": "Healey Library",
        "aliases": [
            "healey",
            "healey library",
            "library",
            "the library",
        ],
        "routing_candidates": [
            "Healey Library",
            "Joseph P. Healey Library",
            "Healey Library UMass Boston",
            "Healey Library, University of Massachusetts Boston",
        ],
        "fallback_coordinate": {
            "lat": 42.3135543,
            "lon": -71.0394469,
        },
        "type": "building",
    },
    "campus center": {
        "canonical_name": "Campus Center",
        "aliases": [
            "campus center",
            "campus centre",
            "cc",
            "student center",
        ],
        "routing_candidates": [
            "Campus Center",
            "Campus Center UMass Boston",
            "Campus Center, University of Massachusetts Boston",
        ],
        "fallback_coordinate": {
            "lat": 42.312818,
            "lon": -71.037887,
        },
        "type": "building",
    },
    "wheatley hall": {
        "canonical_name": "Wheatley Hall",
        "aliases": [
            "wheatley",
            "wheatley hall",
            "wheatley building",
        ],
        "routing_candidates": [
            "Wheatley Hall",
            "Wheatley",
            "Wheatley Building",
            "Wheatley Hall UMass Boston",
            "Wheatley Hall, University of Massachusetts Boston",
        ],
        "fallback_coordinate": {
            "lat": 42.31205,
            "lon": -71.03823,
        },
        "type": "building",
    },
    "integrated sciences complex": {
        "canonical_name": "Integrated Sciences Complex",
        "aliases": [
            "isc",
            "integrated sciences complex",
            "science center",
            "science building",
        ],
        "routing_candidates": [
            "Integrated Sciences Complex",
            "ISC",
            "Integrated Sciences Complex UMass Boston",
            "Integrated Sciences Complex, University of Massachusetts Boston",
        ],
        "fallback_coordinate": {
            "lat": 42.313862,
            "lon": -71.040647,
        },
        "type": "building",
    },
    "parking garage": {
        "canonical_name": "Parking Garage",
        "aliases": [
            "garage",
            "the garage",
            "parking garage",
            "west garage",
            "campus garage",
        ],
        "routing_candidates": [
            "Parking Garage",
            "West Garage",
            "UMass Boston Parking Garage",
            "Parking Garage UMass Boston",
        ],
        "fallback_coordinate": {
            "lat": 42.314943,
            "lon": -71.041591,
        },
        "type": "parking",
    },
    "bus stop": {
        "canonical_name": "Bus Stop",
        "aliases": [
            "bus stop",
            "the bus stop",
            "mbta stop",
            "shuttle stop",
        ],
        "routing_candidates": [
            "Bus Stop",
            "UMass Boston Bus Stop",
            "Campus Center Bus Stop",
            "MBTA UMass Boston",
        ],
        "fallback_coordinate": None,
        "type": "transit",
    },
    "harborwalk": {
        "canonical_name": "HarborWalk",
        "aliases": [
            "harborwalk",
            "harbor walk",
            "the harborwalk",
            "the harbor walk",
        ],
        "routing_candidates": [
            "HarborWalk",
            "Boston HarborWalk",
            "Harbor Walk UMass Boston",
            "HarborWalk UMass Boston",
        ],
        "fallback_coordinate": None,
        "type": "landmark",
    },
    "food court": {
        "canonical_name": "Food Court",
        "aliases": [
            "food court",
            "cafeteria",
            "dining area",
            "where to eat",
        ],
        "routing_candidates": [
            "Food Court",
            "UMass Boston Food Court",
            "Campus Center Food Court",
        ],
        "fallback_coordinate": None,
        "type": "service",
    },
}

FUZZY_THRESHOLD = 0.78
VAGUE_LOCATION_TERMS = {"hall", "building", "campus", "walk", "center", "science"}


def normalize_location_text(text: str) -> str:
    normalized = (text or "").strip().lower()
    normalized = re.sub(r"[-_/]", " ", normalized)
    normalized = re.sub(r"[^\w\s]", "", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def unresolved_result(user_text: str) -> dict:
    return {
        "input": user_text,
        "canonical_name": None,
        "matched_alias": None,
        "confidence": 0.0,
        "status": "unresolved",
        "type": None,
        "routing_candidates": [],
        "fallback_coordinate": None,
    }


def location_routing_candidates(location: dict) -> list[str]:
    candidates = location.get("routing_candidates") or [location["canonical_name"]]
    deduped = []
    for candidate in candidates:
        if candidate and candidate not in deduped:
            deduped.append(candidate)
    return deduped


def resolved_result(user_text: str, location: dict, matched_alias: str, confidence: float) -> dict:
    return {
        "input": user_text,
        "canonical_name": location["canonical_name"],
        "matched_alias": matched_alias,
        "confidence": confidence,
        "status": "resolved",
        "type": location["type"],
        "routing_candidates": location_routing_candidates(location),
        "fallback_coordinate": location.get("fallback_coordinate"),
    }


def iter_location_aliases():
    for key, location in CAMPUS_LOCATIONS.items():
        yield normalize_location_text(key), location
        for alias in location["aliases"]:
            yield normalize_location_text(alias), location


def resolve_location(user_text: str) -> dict:
    normalized_input = normalize_location_text(user_text)
    if not normalized_input:
        return unresolved_result(user_text)

    for canonical_key, location in CAMPUS_LOCATIONS.items():
        if normalized_input == normalize_location_text(canonical_key):
            return resolved_result(user_text, location, canonical_key, 1.0)

    for normalized_alias, location in iter_location_aliases():
        if normalized_input == normalized_alias:
            return resolved_result(user_text, location, normalized_alias, 1.0)

    if normalized_input in VAGUE_LOCATION_TERMS:
        return unresolved_result(user_text)

    best_alias = None
    best_location = None
    best_score = 0.0
    for normalized_alias, location in iter_location_aliases():
        score = SequenceMatcher(None, normalized_input, normalized_alias).ratio()
        if score > best_score:
            best_alias = normalized_alias
            best_location = location
            best_score = score

    if best_score >= FUZZY_THRESHOLD and best_location is not None:
        return resolved_result(user_text, best_location, best_alias, round(best_score, 2))

    return unresolved_result(user_text)
