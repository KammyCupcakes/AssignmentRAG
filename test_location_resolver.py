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

    def test_harborwalk_resolves_but_where_question_is_not_route(self):
        result = resolve_location("HarborWalk")

        self.assertEqual(result["canonical_name"], "HarborWalk")
        self.assertEqual(result["status"], "resolved")
        self.assertFalse(is_route_query("Where is the HarborWalk?"))


if __name__ == "__main__":
    unittest.main()
