import unittest

from campus_locations import normalize_location_text, resolve_location
from route_parser import is_route_query


class LocationResolverTests(unittest.TestCase):
    def test_normalize_location_text(self):
        cases = [
            (" U-Hall ", "u hall"),
            ("Quin Building?", "quin building"),
            ("McCormack Hall.", "mccormack hall"),
            ("the library", "the library"),
            ("HarborWalk", "harborwalk"),
        ]

        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(normalize_location_text(value), expected)

    def test_exact_aliases_resolve_to_canonical_names(self):
        cases = [
            ("u hall", "University Hall"),
            ("uhall", "University Hall"),
            ("mccormack", "McCormack Hall"),
            ("quin", "Quinn Administration Building"),
            ("quin building", "Quinn Administration Building"),
            ("quinn", "Quinn Administration Building"),
            ("library", "Healey Library"),
            ("healey", "Healey Library"),
            ("campus center", "Campus Center"),
            ("garage", "Parking Garage"),
            ("isc", "Integrated Sciences Complex"),
        ]

        for value, expected in cases:
            with self.subTest(value=value):
                result = resolve_location(value)
                self.assertEqual(result["canonical_name"], expected)
                self.assertEqual(result["status"], "resolved")
                self.assertEqual(result["confidence"], 1.0)

    def test_unknown_location_is_unresolved(self):
        result = resolve_location("random fake building")

        self.assertIsNone(result["canonical_name"])
        self.assertEqual(result["status"], "unresolved")
        self.assertEqual(result["confidence"], 0.0)
        self.assertEqual(result["routing_candidates"], [])
        self.assertIsNone(result["fallback_coordinate"])

    def test_resolved_locations_expose_fallback_coordinate_field(self):
        result = resolve_location("wheatley")

        self.assertEqual(result["canonical_name"], "Wheatley Hall")
        self.assertIn("fallback_coordinate", result)

    def test_mccormack_has_routing_candidates(self):
        result = resolve_location("mccormack")

        self.assertEqual(result["canonical_name"], "McCormack Hall")
        self.assertIn("McCormack Hall", result["routing_candidates"])
        self.assertIn("McCormack", result["routing_candidates"])
        self.assertIn("McCormack Building", result["routing_candidates"])

    def test_quinn_has_routing_candidates(self):
        result = resolve_location("quin building")

        self.assertEqual(result["canonical_name"], "Quinn Administration Building")
        self.assertIn("Quinn Administration Building", result["routing_candidates"])
        self.assertIn("Quinn", result["routing_candidates"])

    def test_harborwalk_resolves_but_where_question_is_not_route(self):
        result = resolve_location("HarborWalk")

        self.assertEqual(result["canonical_name"], "HarborWalk")
        self.assertEqual(result["status"], "resolved")
        self.assertFalse(is_route_query("Where is the HarborWalk?"))


if __name__ == "__main__":
    unittest.main()
