from __future__ import annotations

import argparse
import json
import re
from typing import Any


STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "can",
    "do",
    "for",
    "from",
    "get",
    "how",
    "i",
    "in",
    "is",
    "it",
    "me",
    "of",
    "on",
    "or",
    "please",
    "tell",
    "the",
    "to",
    "was",
    "what",
    "where",
    "who",
    "why",
    "with",
    "you",
}


def _normalize_text(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _tokenize(text: str | None) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", _normalize_text(text))
        if token not in STOPWORDS
    }


def _result_text(result: dict[str, Any]) -> str:
    parts = [
        str(result.get("document_name") or ""),
        str(result.get("source") or ""),
        str(result.get("text") or result.get("evidence_snippet") or ""),
    ]
    return " ".join(part for part in parts if part).strip()


def is_boilerplate_result(result: dict[str, Any]) -> bool:
    text = _normalize_text(_result_text(result))
    if "100 morrissey blvd" not in text and "morrissey blvd" not in text:
        return False

    return len(_tokenize(text)) <= 12


def score_retrieval_result(
    query: str,
    result: dict[str, Any],
    expected_terms: list[str] | None = None,
    expected_sources: list[str] | None = None,
) -> float:
    query_terms = _tokenize(query)
    evidence_terms = _tokenize(_result_text(result))

    if not query_terms or not evidence_terms:
        return 0.0

    overlap = query_terms & evidence_terms
    recall = len(overlap) / len(query_terms)
    precision = len(overlap) / len(evidence_terms)

    score = (0.6 * recall) + (0.4 * precision)

    expected_terms = expected_terms or []
    expected_sources = expected_sources or []

    if expected_terms:
        expected_term_tokens = {
            token
            for term in expected_terms
            for token in _tokenize(term)
        }
        if expected_term_tokens & evidence_terms:
            score += 0.2
        else:
            score *= 0.6

    if expected_sources:
        evidence_text = _normalize_text(_result_text(result))
        if any(_normalize_text(source) in evidence_text for source in expected_sources):
            score += 0.2
        else:
            score *= 0.7

    if is_boilerplate_result(result):
        score *= 0.1

    return round(min(1.0, score), 3)


def evaluate_retrieval_case(
    query: str,
    results: list[dict[str, Any]],
    threshold: float = 0.65,
    expected_terms: list[str] | None = None,
    expected_sources: list[str] | None = None,
    baseline_top_score: float | None = None,
) -> dict[str, Any]:
    top_result = results[0] if results else {}
    top_rank_score = score_retrieval_result(
        query,
        top_result,
        expected_terms=expected_terms,
        expected_sources=expected_sources,
    )

    best_score = max(
        (
            score_retrieval_result(
                query,
                result,
                expected_terms=expected_terms,
                expected_sources=expected_sources,
            )
            for result in results
        ),
        default=0.0,
    )

    delta = None if baseline_top_score is None else round(top_rank_score - baseline_top_score, 3)

    expected_terms = expected_terms or []
    expected_sources = expected_sources or []
    top_text = _normalize_text(_result_text(top_result))
    top_expected_term_match = bool(
        expected_terms
        and any(_tokenize(term) & _tokenize(top_text) for term in expected_terms)
    )
    top_expected_source_match = bool(
        expected_sources
        and any(_normalize_text(source) in top_text for source in expected_sources)
    )
    strict_support = top_expected_term_match or top_expected_source_match

    return {
        "query": query,
        "threshold": threshold,
        "top_rank_score": top_rank_score,
        "best_score": best_score,
        "pass_fail": top_rank_score >= threshold and strict_support,
        "has_relevant_evidence": best_score >= threshold,
        "regression": delta is not None and delta < 0,
        "delta": delta,
        "top_rank_pass": top_rank_score >= threshold and strict_support,
        "best_score_pass": best_score >= threshold,
        "strict_support": strict_support,
    }


__all__ = [
    "evaluate_retrieval_case",
    "is_boilerplate_result",
    "score_retrieval_result",
]


def load_eval_questions(path: str) -> list[dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, list):
        raise ValueError("Evaluation file must contain a JSON list of question objects.")

    return data


def run_eval_questions(
    questions: list[dict[str, Any]],
    max_results: int = 5,
    threshold_override: float | None = None,
) -> list[dict[str, Any]]:
    from tools import search_documents

    rows = []
    for question in questions:
        query = str(question.get("query") or "").strip()
        if not query:
            continue

        search_result = search_documents(query, max_results=max_results)
        result_rows = search_result.get("results", []) if isinstance(search_result, dict) else []
        metrics = evaluate_retrieval_case(
            query,
            result_rows,
            threshold=threshold_override if threshold_override is not None else float(question.get("threshold", 0.65)),
            expected_terms=question.get("expected_terms"),
            expected_sources=question.get("expected_sources"),
            baseline_top_score=question.get("baseline_top_score"),
        )
        rows.append(
            {
                **question,
                **metrics,
                "retrieved_count": len(result_rows),
            }
        )

    return rows


def summarize_eval_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    pass_count = sum(1 for row in rows if row.get("pass_fail"))
    regression_count = sum(1 for row in rows if row.get("regression"))
    best_score_pass_count = sum(1 for row in rows if row.get("best_score_pass"))

    average_top_score = round(
        sum(float(row.get("top_rank_score", 0.0)) for row in rows) / total, 3
    ) if total else 0.0

    return {
        "total": total,
        "pass_count": pass_count,
        "pass_rate": round((pass_count / total) * 100, 1) if total else 0.0,
        "regression_count": regression_count,
        "best_score_pass_count": best_score_pass_count,
        "average_top_score": average_top_score,
    }


def _print_eval_report(rows: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    print("Retrieval Evaluation")
    print("====================")
    print()
    for key, value in summary.items():
        label = key.replace("_", " ").title()
        suffix = "%" if key == "pass_rate" else ""
        print(f"{label}: {value}{suffix}")

    print()
    print("Case Results")
    print("------------")
    for index, row in enumerate(rows, start=1):
        status = "PASS" if row.get("pass_fail") else "FAIL"
        regression_flag = " REGRESSION" if row.get("regression") else ""
        print(f"{index}. {status}{regression_flag} - {row.get('query')}")
        print(f"   top_rank_score: {row.get('top_rank_score')}")
        print(f"   best_score: {row.get('best_score')}")
        print(f"   delta: {row.get('delta')}")
        print(f"   retrieved_count: {row.get('retrieved_count')}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate retrieval quality against eval_questions.json.")
    parser.add_argument(
        "--questions",
        default="eval_questions.json",
        help="Path to the JSON file containing evaluation questions.",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=5,
        help="Maximum number of ChromaDB results to retrieve per question.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="Override per-question thresholds with a single global threshold.",
    )
    args = parser.parse_args()

    questions = load_eval_questions(args.questions)
    rows = run_eval_questions(questions, max_results=args.max_results, threshold_override=args.threshold)
    _print_eval_report(rows, summarize_eval_rows(rows))


if __name__ == "__main__":
    main()