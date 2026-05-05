import unittest

from route_parser import is_route_query, normalize_algorithm, parse_route_query


class RouteParserTests(unittest.TestCase):
    def test_full_from_to_route_queries_parse_locations(self):
        cases = [
            (
                "How do I get from University Hall to McCormack?",
                "University Hall",
                "McCormack",
                "default",
            ),
            (
                "take me from university hall to quinn building",
                "university hall",
                "quinn building",
                "default",
            ),
            (
                "directions from Campus Center to Healey Library",
                "Campus Center",
                "Healey Library",
                "default",
            ),
            (
                "fastest way from the garage to University Hall",
                "the garage",
                "University Hall",
                "fastest",
            ),
            (
                "route from UHall to McCormack",
                "UHall",
                "McCormack",
                "default",
            ),
            (
                "shortest path from Campus Center to Wheatley",
                "Campus Center",
                "Wheatley",
                "shortest",
            ),
        ]

        for query, start, destination, preference in cases:
            with self.subTest(query=query):
                parsed = parse_route_query(query)
                self.assertTrue(parsed["is_route"])
                self.assertEqual(parsed["start"], start)
                self.assertEqual(parsed["destination"], destination)
                self.assertEqual(parsed["algorithm"], "astar")
                self.assertEqual(parsed["route_preference"], preference)
                self.assertFalse(parsed["needs_clarification"])
                self.assertIsNone(parsed["missing"])

    def test_to_from_route_query_parses_reversed_locations(self):
        parsed = parse_route_query("directions to Healey Library from Campus Center")

        self.assertTrue(parsed["is_route"])
        self.assertEqual(parsed["start"], "Campus Center")
        self.assertEqual(parsed["destination"], "Healey Library")
        self.assertEqual(parsed["algorithm"], "astar")
        self.assertFalse(parsed["needs_clarification"])

    def test_how_to_go_to_from_route_query_parses_reversed_locations(self):
        parsed = parse_route_query("how to go to University Hall from Quinn Building?")

        self.assertTrue(parsed["is_route"])
        self.assertEqual(parsed["start"], "Quinn Building")
        self.assertEqual(parsed["destination"], "University Hall")
        self.assertEqual(parsed["algorithm"], "astar")
        self.assertFalse(parsed["needs_clarification"])

    def test_incomplete_destination_route_requests_need_start(self):
        parsed = parse_route_query("How do I get to Healey Library?")

        self.assertTrue(parsed["is_route"])
        self.assertIsNone(parsed["start"])
        self.assertEqual(parsed["destination"], "Healey Library")
        self.assertTrue(parsed["needs_clarification"])
        self.assertEqual(parsed["missing"], "start")

    def test_incomplete_start_route_requests_need_destination(self):
        parsed = parse_route_query("How do I get from Campus Center?")

        self.assertTrue(parsed["is_route"])
        self.assertEqual(parsed["start"], "Campus Center")
        self.assertIsNone(parsed["destination"])
        self.assertTrue(parsed["needs_clarification"])
        self.assertEqual(parsed["missing"], "destination")

    def test_algorithm_detection_defaults_to_astar_and_allows_dijkstra(self):
        astar = parse_route_query("route from UHall to McCormack with madeup")
        dijkstra = parse_route_query("route from UHall to McCormack using dijkstra")
        invalid = parse_route_query("How do I get from University Hall to McCormack using banana?")

        self.assertEqual(astar["algorithm"], "astar")
        self.assertEqual(dijkstra["algorithm"], "dijkstra")
        self.assertEqual(dijkstra["destination"], "McCormack")
        self.assertEqual(invalid["algorithm"], "astar")
        self.assertEqual(invalid["destination"], "McCormack")

    def test_normalize_algorithm_handles_supported_and_invalid_values(self):
        cases = [
            (None, "astar"),
            ("", "astar"),
            ("astar", "astar"),
            ("A*", "astar"),
            ("a star", "astar"),
            ("dijkstra", "dijkstra"),
            ("dijkstras", "dijkstra"),
            ("dijkstra's", "dijkstra"),
            ("dfs", "astar"),
            ("banana", "astar"),
            ("fastest", "astar"),
        ]

        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(normalize_algorithm(value), expected)

    def test_parser_adds_resolved_location_fields(self):
        parsed = parse_route_query("take me from u hall to quin building")

        self.assertTrue(parsed["is_route"])
        self.assertEqual(parsed["start"], "u hall")
        self.assertEqual(parsed["destination"], "quin building")
        self.assertEqual(parsed["resolved_start"], "University Hall")
        self.assertEqual(parsed["resolved_destination"], "Quinn Administration Building")
        self.assertEqual(parsed["start_resolution"]["status"], "resolved")
        self.assertEqual(parsed["destination_resolution"]["status"], "resolved")
        self.assertFalse(parsed["needs_clarification"])

    def test_parser_marks_unresolved_locations_for_clarification(self):
        parsed = parse_route_query("how do i get from fake place to campus center")

        self.assertTrue(parsed["is_route"])
        self.assertEqual(parsed["start"], "fake place")
        self.assertEqual(parsed["destination"], "campus center")
        self.assertIsNone(parsed["resolved_start"])
        self.assertEqual(parsed["resolved_destination"], "Campus Center")
        self.assertTrue(parsed["needs_clarification"])
        self.assertEqual(parsed["missing"], "start")
        self.assertEqual(parsed["clarification_reason"], "unresolved_start")

    def test_parser_resolves_common_aliases(self):
        parsed = parse_route_query("directions from the garage to the library")

        self.assertEqual(parsed["resolved_start"], "Parking Garage")
        self.assertEqual(parsed["resolved_destination"], "Healey Library")

    def test_non_route_queries_do_not_trigger_route_mode(self):
        cases = [
            "Where is the HarborWalk?",
            "Can I walk around campus?",
            "Is there a food court on campus?",
            "What parking options are available?",
            "Where can visitors park?",
            "What is HarborWalk?",
            "Tell me about the campus map",
        ]

        for query in cases:
            with self.subTest(query=query):
                self.assertFalse(is_route_query(query))
                parsed = parse_route_query(query)
                self.assertFalse(parsed["is_route"])
                self.assertIsNone(parsed["start"])
                self.assertIsNone(parsed["destination"])
                self.assertFalse(parsed["needs_clarification"])


if __name__ == "__main__":
    unittest.main()
