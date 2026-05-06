import unittest


class RetrievalMetricsTests(unittest.TestCase):
    def test_boilerplate_top_result_fails_but_relevant_evidence_exists(self):
        from retrieval_metrics import evaluate_retrieval_case

        results = [
            {
                "rank": 1,
                "document_name": "Registrar PDF",
                "source": "data/registrar.pdf",
                "text": "100 Morrissey Blvd",
            },
            {
                "rank": 2,
                "document_name": "Dean Office Guide",
                "source": "data/dean_office_guide.pdf",
                "text": "The Dean's Office is located in Wheatley Hall.",
            },
        ]

        metrics = evaluate_retrieval_case(
            "where is the dean's office?",
            results,
            threshold=0.5,
            expected_terms=["dean", "office", "wheatley"],
            expected_sources=["dean_office_guide.pdf"],
        )

        self.assertFalse(metrics["pass_fail"])
        self.assertTrue(metrics["has_relevant_evidence"])
        self.assertGreater(metrics["best_score"], metrics["top_rank_score"])

    def test_regression_is_reported_when_top_score_drops(self):
        from retrieval_metrics import evaluate_retrieval_case

        baseline_score = 0.8
        results = [
            {
                "rank": 1,
                "document_name": "Registrar PDF",
                "source": "data/registrar.pdf",
                "text": "100 Morrissey Blvd",
            }
        ]

        metrics = evaluate_retrieval_case(
            "where is the dean's office?",
            results,
            threshold=0.5,
            expected_terms=["dean", "office"],
            baseline_top_score=baseline_score,
        )

        self.assertTrue(metrics["regression"])
        self.assertLess(metrics["delta"], 0)
        self.assertFalse(metrics["pass_fail"])

    def test_non_boilerplate_relevant_result_passes(self):
        from retrieval_metrics import evaluate_retrieval_case

        results = [
            {
                "rank": 1,
                "document_name": "Dean Office Guide",
                "source": "data/dean_office_guide.pdf",
                "text": "The Dean's Office is located in Wheatley Hall.",
            }
        ]

        metrics = evaluate_retrieval_case(
            "where is the dean's office?",
            results,
            threshold=0.5,
            expected_terms=["dean", "office", "wheatley"],
            expected_sources=["dean_office_guide.pdf"],
        )

        self.assertTrue(metrics["pass_fail"])
        self.assertTrue(metrics["best_score_pass"])
        self.assertFalse(metrics["regression"])


if __name__ == "__main__":
    unittest.main()