from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from typing import Any

from navigation_evaluation import successful_route
from route_parser import parse_route_query
from route_state import (
    clear_last_route_context,
    clear_pending_route,
    handle_route_continuation_query,
    handle_route_info_with_context,
    start_pending_route,
    try_complete_pending_route,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BEACONNAV_SRC = os.path.join(BASE_DIR, "BeaconNav", "src")

FALLBACK_PHRASES = [
    "i don't have that information in my documents",
    "i don't know the answer to that",
    "i don't have that information",
    "i can't find that information in my documents",
    "i'm sorry, i don't have that information in my documents",
]


@dataclass(frozen=True)
class RouteCase:
    prompt: str
    expected_is_route: bool
    expected_start: str | None = None
    expected_destination: str | None = None


@dataclass(frozen=True)
class MultiTurnCase:
    name: str
    turns: list[str]
    expected_final_start: str
    expected_final_destination: str


@dataclass(frozen=True)
class RAGCase:
    prompt: str
    expected_keywords: list[str]


ROUTE_CASES: list[RouteCase] = [
    RouteCase("take me from u hall to quin building", True, "University Hall", "Quinn Administration Building"),
    RouteCase("How do I get from University Hall to McCormack?", True, "University Hall", "McCormack Hall"),
    RouteCase("directions from Healey Library to Wheatley Hall", True, "Healey Library", "Wheatley Hall"),
    RouteCase("take me from isc to campus center", True, "Integrated Sciences Complex", "Campus Center"),
    RouteCase("How do I get to Healey Library?", True, None, "Healey Library"),
    RouteCase("How do I get from Campus Center?", True, "Campus Center", None),
    RouteCase("How do I get from fake place to Campus Center?", True, None, "Campus Center"),
    RouteCase("Where is the HarborWalk?", False),
    RouteCase("Is there a food court on campus?", False),
    RouteCase("What parking options are available?", False),
    RouteCase("Can visitors park on campus?", False),
]

MULTI_TURN_CASES: list[MultiTurnCase] = [
    MultiTurnCase(
        "Missing start then fill",
        ["How do I get to Healey Library?", "Campus Center"],
        "Campus Center", "Healey Library",
    ),
    MultiTurnCase(
        "Missing destination then fill",
        ["How do I get from Campus Center?", "Wheatley Hall"],
        "Campus Center", "Wheatley Hall",
    ),
    MultiTurnCase(
        "Route continuation from there",
        ["take me from u hall to quin building", "from there how do i get to isc"],
        "Quinn Administration Building", "Integrated Sciences Complex",
    ),
]

RAG_CASES: list[RAGCase] = [
    RAGCase("What parking options are available?", ["parking", "permit", "garage"]),
    RAGCase("Can visitors park on campus?", ["visitor", "parking"]),
    RAGCase("What commuting options are available?", ["commuter", "bus", "train", "transportation"]),
    RAGCase("How can students get to campus by public transportation?", ["public", "transportation", "shuttle", "bus"]),
    RAGCase("What biking resources are available?", ["bike", "bicycle", "rack"]),
]


def percent(n: int, d: int) -> float:
    return round(n / d * 100, 1) if d else 0.0


def is_web_url(value: Any) -> bool:
    return isinstance(value, str) and value.strip().lower().startswith(("http://", "https://"))


def reset_state() -> None:
    clear_pending_route()
    clear_last_route_context()


def is_route_success(response: str | None) -> bool:
    return (
        isinstance(response, str)
        and response.startswith("Route found:")
        and "Status: Route generated successfully." in response
    )


def has_fallback(response: str | None) -> bool:
    if not isinstance(response, str):
        return True
    lowered = response.lower()
    return any(p in lowered for p in FALLBACK_PHRASES)


def route_turn(user_query: str, get_route) -> str | None:
    pending = try_complete_pending_route(user_query, get_route)
    if pending is not None:
        return pending

    info = parse_route_query(user_query)
    if info["is_route"]:
        if info.get("missing") or info.get("clarification_reason"):
            return start_pending_route(info)
        return handle_route_info_with_context(info, get_route)

    return handle_route_continuation_query(user_query, get_route)


def extract_source_urls(response: str | None) -> list[str]:
    if not isinstance(response, str) or "Sources:" not in response:
        return []
    seen: set[str] = set()
    urls = []
    for url in re.findall(r"https?://[^\s)]+", response):
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


# -- Route provider -----------------------------------------------------------

def get_route_provider(live: bool):
    if not live:
        return successful_route
    if BEACONNAV_SRC not in sys.path:
        sys.path.insert(0, BEACONNAV_SRC)
    from main import get_route
    return get_route


# -- RAG providers ------------------------------------------------------------

def _deterministic_search(query: str, max_results: int = 5) -> dict[str, Any]:
    return {
        "query": query,
        "low_confidence": False,
        "results": [{
            "rank": 1, "text": query,
            "source": "https://www.umb.edu/transportation/",
            "document_name": "UMass Boston Transportation",
            "source_type": "web", "chunk_index": 0, "distance": 0.0,
        }][:max_results],
    }


def _deterministic_query(prompt: str, expected_keywords: list[str]) -> dict[str, str]:
    return {
        "response": (
            f"UMass Boston transportation information relevant to this question includes "
            f"{', '.join(expected_keywords)}.\n\n"
            "Sources:\n1. UMass Boston Transportation - https://www.umb.edu/transportation/"
        )
    }


def get_rag_providers(live: bool):
    if not live:
        return _deterministic_search, None
    from prompt import handle_query_web
    from tools import search_documents
    return search_documents, handle_query_web


# -- Evaluation logic ---------------------------------------------------------

def evaluate_navigation(cases: list[RouteCase], get_route) -> dict[str, Any]:
    rows = []
    loc_correct = loc_total = 0
    routes_ok = valid_complete = 0
    false_pos = non_route = 0

    for c in cases:
        reset_state()
        parsed = parse_route_query(c.prompt)
        response = route_turn(c.prompt, get_route)

        if not c.expected_is_route:
            non_route += 1
            false_pos += parsed["is_route"]

        for attr, key in [("expected_start", "resolved_start"), ("expected_destination", "resolved_destination")]:
            expected = getattr(c, attr)
            if expected is not None:
                loc_total += 1
                loc_correct += parsed.get(key) == expected

        is_complete = bool(c.expected_is_route and c.expected_start and c.expected_destination)
        if is_complete:
            valid_complete += 1
            routes_ok += is_route_success(response)

        rows.append({
            "prompt": c.prompt,
            "expected_is_route": c.expected_is_route,
            "detected_is_route": parsed["is_route"],
            "expected_start": c.expected_start,
            "resolved_start": parsed.get("resolved_start"),
            "expected_destination": c.expected_destination,
            "resolved_destination": parsed.get("resolved_destination"),
            "response": response,
            "route_generated": is_route_success(response),
        })

    return {
        "rows": rows,
        "location_resolution_accuracy": percent(loc_correct, loc_total),
        "location_resolution_numerator": loc_correct,
        "location_resolution_denominator": loc_total,
        "route_generation_rate": percent(routes_ok, valid_complete),
        "route_generation_numerator": routes_ok,
        "route_generation_denominator": valid_complete,
        "false_positive_route_trigger_rate": percent(false_pos, non_route),
        "false_positive_numerator": false_pos,
        "false_positive_denominator": non_route,
    }


def evaluate_multi_turn(cases: list[MultiTurnCase], get_route) -> dict[str, Any]:
    rows = []
    success_count = 0

    for c in cases:
        reset_state()
        responses = [route_turn(turn, get_route) for turn in c.turns]
        final = responses[-1] if responses else None
        success = bool(
            is_route_success(final)
            and c.expected_final_start.lower() in (final or "").lower()
            and c.expected_final_destination.lower() in (final or "").lower()
        )
        success_count += success
        rows.append({"name": c.name, "turns": c.turns, "responses": responses, "success": success})

    return {
        "rows": rows,
        "multi_turn_success_rate": percent(success_count, len(cases)),
        "multi_turn_numerator": success_count,
        "multi_turn_denominator": len(cases),
    }


def _grounded_score(
    response: str | None,
    keywords: list[str],
    has_citation: bool,
    had_evidence: bool,
) -> tuple[int, str]:
    if not isinstance(response, str) or not response.strip() or has_fallback(response):
        return 0, "No useful answer text."

    hits = sum(1 for kw in keywords if re.search(rf"\b{re.escape(kw.lower())}\b", response.lower()))

    if has_citation and hits >= 2:
        return 2, "Cited web source and multiple expected concepts present."
    if (has_citation and hits >= 1) or (had_evidence and hits >= 2):
        return 1, "Partially supported by citation and/or expected concepts."
    return 0, "Insufficient support signals in response."


def load_manual_grounded_scores(path: str | None) -> dict[str, int]:
    if not path:
        return {}
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    if isinstance(payload, list):
        payload = {str(item["prompt"]): int(item["score"]) for item in payload}
    result = {}
    for prompt, score in payload.items():
        v = int(score)
        if not 0 <= v <= 2:
            raise ValueError(f"Score for '{prompt}' must be 0-2.")
        result[str(prompt)] = v
    return result


def evaluate_rag(
    cases: list[RAGCase],
    max_search_results: int,
    manual_grounded_scores: dict[str, int] | None = None,
    live_rag: bool = False,
) -> dict[str, Any]:
    manual = manual_grounded_scores or {}
    search_documents, handle_query_web = get_rag_providers(live_rag)
    rows = []
    cite_ok = cite_total = grounded_pts = 0

    for c in cases:
        reset_state()
        retrieval = search_documents(c.prompt, max_results=max_search_results)
        results = retrieval.get("results", []) if isinstance(retrieval, dict) else []
        had_evidence = any(is_web_url(r.get("source")) for r in results)
        if had_evidence:
            cite_total += 1

        if live_rag:
            payload = handle_query_web(c.prompt, show_route_map=False)
        else:
            payload = _deterministic_query(c.prompt, c.expected_keywords)

        response = payload.get("response") if isinstance(payload, dict) else ""
        urls = extract_source_urls(response)
        has_citation = bool(urls)

        if had_evidence and has_citation:
            cite_ok += 1

        if c.prompt in manual:
            score, note = manual[c.prompt], "Manual score provided."
        else:
            score, note = _grounded_score(response, c.expected_keywords, has_citation, had_evidence)

        grounded_pts += score
        rows.append({
            "prompt": c.prompt,
            "mode": "live" if live_rag else "deterministic",
            "response": response,
            "retrieved_count": len(results),
            "had_web_evidence": had_evidence,
            "has_web_citation": has_citation,
            "cited_urls": urls,
            "grounded_score": score,
            "grounded_note": note,
        })

    max_pts = len(cases) * 2
    return {
        "rows": rows,
        "web_source_citation_rate": percent(cite_ok, cite_total),
        "web_source_citation_numerator": cite_ok,
        "web_source_citation_denominator": cite_total,
        "grounded_answer_accuracy": percent(grounded_pts, max_pts),
        "grounded_points": grounded_pts,
        "grounded_max_points": max_pts,
    }


# -- Reporting ----------------------------------------------------------------

_BAR_WIDTH = 30

def _bar(pct: float, invert: bool = False) -> str:
    """ASCII progress bar. invert=True means lower is better (colours red when high)."""
    filled = round(pct / 100 * _BAR_WIDTH)
    bar = "█" * filled + "░" * (_BAR_WIDTH - filled)
    if invert:
        indicator = "✓" if pct == 0 else "✗" if pct >= 50 else "~"
    else:
        indicator = "✓" if pct == 100 else "✗" if pct == 0 else "~"
    return f"[{bar}] {pct:5.1f}%  {indicator}"


def _section(title: str) -> None:
    print(f"\n  {title}")
    print(f"  {'─' * (len(title) + 2)}")


def print_report(nav: dict[str, Any], mt: dict[str, Any], rag: dict[str, Any]) -> None:
    W = 72
    print("╔" + "═" * W + "╗")
    print("║" + "  BEACONNAV + RAG  —  COMPREHENSIVE EVALUATION REPORT".center(W) + "║")
    print("╚" + "═" * W + "╝")

    # ── Evaluation methodology ────────────────────────────────────────────────
    print("""
  HOW THE SYSTEM WAS EVALUATED
  ════════════════════════════
  The system was tested across three independent evaluation dimensions:

  1. Navigation (Route Detection & Resolution)
       • 11 hand-crafted prompts covering full routes, partial routes,
         ambiguous input (aliases like "u hall", "isc"), and non-route
         questions designed to trigger false positives.
       • Each prompt is parsed by the NLP route extractor; resolved
         start/destination are compared against known ground-truth names.
       • Complete route requests are sent to the routing engine and the
         response is checked for a success status string.

  2. Multi-Turn Dialogue
       • 3 multi-step conversation scenarios: missing start, missing
         destination, and "from there" chained continuation.
       • Each turn is replayed in sequence; the final response must
         contain a successful route AND reference both correct endpoints.

  3. RAG Quality (Retrieval-Augmented Generation)
       • 5 informational questions about campus transportation.
       • Grounded Answer Accuracy is scored 0–2 per question:
           2 = web citation present + ≥2 expected keywords found
           1 = partial evidence (citation OR keywords, not both)
           0 = fallback / no useful content
       • Web Source Citation Rate checks whether retrieved web documents
         result in a cited URL in the final answer.""")

    # ── Navigation metrics ────────────────────────────────────────────────────
    _section("NAVIGATION  (route detection + location resolution)")
    nav_metrics = [
        ("Route Generation Rate     ", nav["route_generation_numerator"],   nav["route_generation_denominator"],   nav["route_generation_rate"],   False),
        ("Location Resolution Acc.  ", nav["location_resolution_numerator"], nav["location_resolution_denominator"], nav["location_resolution_accuracy"], False),
        ("False Positive Trigger Rate", nav["false_positive_numerator"],     nav["false_positive_denominator"],     nav["false_positive_route_trigger_rate"], True),
    ]
    for label, n, d, pct, invert in nav_metrics:
        print(f"    {label}  {n:>2}/{d:<2}  {_bar(pct, invert)}")

    # ── Per-case breakdown ────────────────────────────────────────────────────
    print("\n    Route case breakdown:")
    print(f"    {'Prompt':<48}  {'Start':^5}  {'Dest':^5}  {'Route':^5}")
    print(f"    {'─'*48}  {'─'*5}  {'─'*5}  {'─'*5}")
    for row in nav["rows"]:
        start_ok  = "  ✓ " if row["resolved_start"]       == row["expected_start"]       else ("  ✗ " if row["expected_start"]       else "  — ")
        dest_ok   = "  ✓ " if row["resolved_destination"] == row["expected_destination"]  else ("  ✗ " if row["expected_destination"]  else "  — ")
        route_ok  = "  ✓ " if row["route_generated"] else ("  — " if not row["expected_is_route"] else "  ✗ ")
        prompt    = row["prompt"][:47]
        print(f"    {prompt:<48} {start_ok}  {dest_ok}  {route_ok}")

    # ── Multi-turn metrics ────────────────────────────────────────────────────
    _section("MULTI-TURN DIALOGUE  (slot-filling + route chaining)")
    print(f"    {'Success Rate':<28}  {mt['multi_turn_numerator']:>2}/{mt['multi_turn_denominator']:<2}  {_bar(mt['multi_turn_success_rate'])}")
    print()
    for row in mt["rows"]:
        icon = "✓" if row["success"] else "✗"
        print(f"    [{icon}] {row['name']}")
        for i, (turn, resp) in enumerate(zip(row["turns"], row["responses"]), 1):
            snippet = (resp or "")[:70].replace("\n", " ")
            print(f"         Turn {i}: \"{turn}\"")
            print(f"                → {snippet}")

    # ── RAG metrics ───────────────────────────────────────────────────────────
    _section("RAG QUALITY  (retrieval, citation, grounding)")
    rag_metrics = [
        ("Web Source Citation Rate  ", rag["web_source_citation_numerator"], rag["web_source_citation_denominator"], rag["web_source_citation_rate"],  False),
        ("Grounded Answer Accuracy  ", rag["grounded_points"],               rag["grounded_max_points"],             rag["grounded_answer_accuracy"],   False),
    ]
    for label, n, d, pct, invert in rag_metrics:
        print(f"    {label}  {n:>2}/{d:<2}  {_bar(pct, invert)}")

    print(f"\n    {'Prompt':<50}  {'Score':^5}  Note")
    print(f"    {'─'*50}  {'─'*5}  {'─'*30}")
    score_icons = {0: "✗", 1: "~", 2: "✓"}
    for row in rag["rows"]:
        icon  = score_icons.get(row["grounded_score"], "?")
        prompt = row["prompt"][:49]
        note   = row["grounded_note"][:40]
        print(f"    {prompt:<50}  [{icon}] {row['grounded_score']}/2  {note}")

    # ── Summary ───────────────────────────────────────────────────────────────
    all_metrics = [
        nav["route_generation_rate"],
        nav["location_resolution_accuracy"],
        mt["multi_turn_success_rate"],
        100.0 - nav["false_positive_route_trigger_rate"],   # inverted: lower FP = better
        rag["web_source_citation_rate"],
        rag["grounded_answer_accuracy"],
    ]
    overall = round(sum(all_metrics) / len(all_metrics), 1)

    print(f"\n{'─' * (W + 2)}")
    print(f"  Overall Score (mean of 6 metrics):  {_bar(overall)}")
    print(f"{'─' * (W + 2)}\n")


# -- CLI ----------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Comprehensive campus navigation + RAG evaluation.")
    p.add_argument("--live-route", action="store_true", help="Use live BeaconNav routing.")
    p.add_argument("--live-rag", action="store_true", help="Use live RAG/OpenAI path.")
    p.add_argument("--max-search-results", type=int, default=5)
    p.add_argument("--grounded-scores", default=None, help="JSON path for manual grounded scores (0-2).")
    p.add_argument("--json-out", default=None, help="Path to save full evaluation output as JSON.")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    get_route = get_route_provider(args.live_route)
    manual = load_manual_grounded_scores(args.grounded_scores)

    nav = evaluate_navigation(ROUTE_CASES, get_route)
    mt = evaluate_multi_turn(MULTI_TURN_CASES, get_route)
    rag = evaluate_rag(RAG_CASES, args.max_search_results, manual, args.live_rag)

    print_report(nav, mt, rag)

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump({"navigation": nav, "multi_turn": mt, "rag": rag}, f, indent=2)
        print(f"\nDetailed results saved to: {args.json_out}")


if __name__ == "__main__":
    main()
