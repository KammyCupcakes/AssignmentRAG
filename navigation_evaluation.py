from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from statistics import mean
from typing import Callable

from navigation_flow import handle_route_query
from route_parser import parse_route_query


@dataclass(frozen=True)
class EvaluationCase:
    prompt: str
    expected_is_route: bool
    expected_start: str | None = None
    expected_destination: str | None = None


EVALUATION_CASES = [
    EvaluationCase(
        "How do I get from University Hall to McCormack?",
        True,
        "University Hall",
        "McCormack Hall",
    ),
    EvaluationCase(
        "Take me from u hall to quinn",
        True,
        "University Hall",
        "Quinn Administration Building",
    ),
    EvaluationCase(
        "Directions from Campus Center to Healey Library",
        True,
        "Campus Center",
        "Healey Library",
    ),
    EvaluationCase(
        "Fastest way from the garage to University Hall",
        True,
        "Parking Garage",
        "University Hall",
    ),
    EvaluationCase(
        "construct a path from campus center to quinn",
        True,
        "Campus Center",
        "Quinn Administration Building",
    ),
    EvaluationCase(
        "route from Wheatley to ISC",
        True,
        "Wheatley Hall",
        "Integrated Sciences Complex",
    ),
    EvaluationCase(
        "How do I get to Healey Library?",
        True,
        None,
        "Healey Library",
    ),
    EvaluationCase(
        "Where is the HarborWalk?",
        False,
    ),
]


def successful_route(start: str, destination: str, **kwargs) -> dict:
    return {
        "success": True,
        "start": start,
        "end": destination,
        "algorithm": kwargs.get("algorithm", "astar"),
        "distance_miles": 0.18,
        "walk_time_minutes": 3.6,
        "path": ["start_node", "middle_node", "end_node"],
    }


def get_route_provider(live: bool) -> Callable[..., dict]:
    if not live:
        return successful_route

    from main import get_route

    return get_route


def count_guidance_steps(response: str | None) -> int:
    if not response:
        return 0
    return len(re.findall(r"(?m)^\d+\.\s+", response))


def percent(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round((numerator / denominator) * 100, 1)


def evaluate_case(case: EvaluationCase, get_route: Callable[..., dict]) -> dict:
    parsed = parse_route_query(case.prompt)
    response = handle_route_query(case.prompt, get_route)

    actual_start = parsed.get("resolved_start")
    actual_destination = parsed.get("resolved_destination")
    route_detected_correctly = parsed["is_route"] == case.expected_is_route
    start_correct = actual_start == case.expected_start
    destination_correct = actual_destination == case.expected_destination

    if not case.expected_is_route:
        location_correct = route_detected_correctly
    else:
        location_correct = (
            route_detected_correctly
            and start_correct
            and destination_correct
        )

    route_generated = bool(response and response.startswith("Route found:"))
    needs_slot_fill = bool(parsed.get("missing"))
    if not case.expected_is_route:
        goal_completed = not parsed["is_route"] and response is None
    elif needs_slot_fill:
        goal_completed = response is not None and not route_generated
    else:
        goal_completed = route_generated

    wayfinding_error = (
        case.expected_is_route
        and not needs_slot_fill
        and not route_generated
    )

    return {
        "prompt": case.prompt,
        "expected_route": case.expected_is_route,
        "detected_route": parsed["is_route"],
        "expected_start": case.expected_start,
        "actual_start": actual_start,
        "expected_destination": case.expected_destination,
        "actual_destination": actual_destination,
        "location_correct": location_correct,
        "route_generated": route_generated,
        "goal_completed": goal_completed,
        "wayfinding_error": wayfinding_error,
        "turn_count": count_guidance_steps(response),
        "response": response,
    }


def summarize(results: list[dict]) -> dict:
    route_cases = [row for row in results if row["expected_route"]]
    complete_route_cases = [
        row
        for row in route_cases
        if row["expected_start"] and row["expected_destination"]
    ]
    generated_routes = [row for row in complete_route_cases if row["route_generated"]]

    return {
        "total_cases": len(results),
        "route_cases": len(route_cases),
        "location_detection_accuracy": percent(
            sum(row["location_correct"] for row in results),
            len(results),
        ),
        "route_generation_rate": percent(
            len(generated_routes),
            len(complete_route_cases),
        ),
        "goal_completion_rate": percent(
            sum(row["goal_completed"] for row in results),
            len(results),
        ),
        "wayfinding_error_rate": percent(
            sum(row["wayfinding_error"] for row in complete_route_cases),
            len(complete_route_cases),
        ),
        "average_turn_count_per_generated_route": round(
            mean(row["turn_count"] for row in generated_routes), 2
        )
        if generated_routes
        else 0.0,
        "false_positive_count": sum(
            row["detected_route"] and not row["expected_route"] for row in results
        ),
        "false_negative_count": sum(
            row["expected_route"] and not row["detected_route"] for row in results
        ),
    }


def print_report(results: list[dict], metrics: dict) -> None:
    print("Navigation Evaluation")
    print("=====================")
    print()
    for key, value in metrics.items():
        label = key.replace("_", " ").title()
        suffix = "%" if key.endswith(("accuracy", "rate")) else ""
        print(f"{label}: {value}{suffix}")

    print()
    print("Case Results")
    print("------------")
    for index, row in enumerate(results, start=1):
        status = "PASS" if row["goal_completed"] and not row["wayfinding_error"] else "FAIL"
        print(f"{index}. {status} - {row['prompt']}")
        print(f"   route detected: {row['detected_route']}")
        print(f"   start: {row['actual_start']}")
        print(f"   destination: {row['actual_destination']}")
        print(f"   route generated: {row['route_generated']}")
        print(f"   turn count: {row['turn_count']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate campus navigation routing behavior.")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Call real BeaconNav instead of the deterministic mock route provider.",
    )
    args = parser.parse_args()

    get_route = get_route_provider(args.live)
    results = [evaluate_case(case, get_route) for case in EVALUATION_CASES]
    print_report(results, summarize(results))


if __name__ == "__main__":
    main()
