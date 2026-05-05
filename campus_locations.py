import re
from difflib import SequenceMatcher


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
        "type": "building",
    },
    "mccormack hall": {
        "canonical_name": "McCormack Hall",
        "aliases": [
            "mccormack",
            "mccormack hall",
            "mccormack building",
        ],
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
        "type": "building",
    },
    "wheatley hall": {
        "canonical_name": "Wheatley Hall",
        "aliases": [
            "wheatley",
            "wheatley hall",
            "wheatley building",
        ],
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
    }


def resolved_result(user_text: str, location: dict, matched_alias: str, confidence: float) -> dict:
    return {
        "input": user_text,
        "canonical_name": location["canonical_name"],
        "matched_alias": matched_alias,
        "confidence": confidence,
        "status": "resolved",
        "type": location["type"],
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
