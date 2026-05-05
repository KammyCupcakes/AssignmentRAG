import unittest
from unittest.mock import Mock

from navigation_flow import (
    MAX_ROUTE_ATTEMPTS,
    build_routing_attempts,
    format_route_response,
    handle_route_query,
)
from route_parser import parse_route_query
from route_parser import is_route_query


class NavigationFlowTests(unittest.TestCase):
    def test_route_branch_calls_beaconnav_with_resolved_names(self):
        get_route = Mock(
            return_value={
                "success": True,
                "distance_m": 250,
                "estimated_walk_time": 4.0,
                "path": ["node1", "node2"],
            }
        )

        response = handle_route_query("take me from u hall to quin building", get_route)

        get_route.assert_called_once_with(
            "University Hall",
            "Quinn Administration Building",
            algorithm="astar",
            show_map=False,
        )
        self.assertIn("Route found", response)
        self.assertIn("University Hall", response)
        self.assertIn("Quinn Administration Building", response)
        self.assertIn("A*", response)
        self.assertIn("250", response)
        self.assertIn("4", response)

    def test_route_response_uses_path_aware_navigation_sections(self):
        response = format_route_response(
            {
                "success": True,
                "distance_miles": 0.12,
                "walk_time_minutes": 2.3,
                "path": [7671135308, 12660081316],
            },
            "Healey Library",
            "Wheatley Hall",
            "astar",
        )

        self.assertIn("Route found: Healey Library → Wheatley Hall", response)
        self.assertIn("Estimated walk: 2.3 minutes", response)
        self.assertIn("Distance: 0.12 miles", response)
        self.assertIn("Route type: shortest walking route using A*", response)
        self.assertIn("Walking guidance:", response)
        self.assertIn("1. Start at Healey Library.", response)
        self.assertIn(
            "2. Follow the computed campus walking path from the Healey Library area toward Wheatley Hall.",
            response,
        )
        self.assertIn("3. Continue along the route for about 0.12 miles.", response)
        self.assertIn(
            "4. Arrive at the nearest available walkable point near Wheatley Hall.",
            response,
        )
        self.assertIn(
            "Note: This is campus walking guidance based on available map path data, not indoor turn-by-turn directions.",
            response,
        )
        self.assertIn("Status: Route generated successfully.", response)
        self.assertNotIn("7671135308", response)
        self.assertNotIn("12660081316", response)

    def test_route_response_omits_missing_distance_and_time_without_none(self):
        response = format_route_response(
            {
                "success": True,
                "path": ["node1", "node2"],
            },
            "Campus Center",
            "Healey Library",
            "astar",
        )

        self.assertIn("Route found: Campus Center → Healey Library", response)
        self.assertIn("Route type: shortest walking route using A*", response)
        self.assertIn("Walking guidance:", response)
        self.assertNotIn("Estimated walk:", response)
        self.assertNotIn("Distance:", response)
        self.assertNotIn("None", response)

    def test_route_response_without_path_data_uses_generic_guidance(self):
        response = format_route_response(
            {
                "success": True,
                "distance_miles": 0.15,
                "walk_time_minutes": 3.0,
            },
            "Campus Center",
            "Healey Library",
            "astar",
        )

        self.assertIn("Walking guidance:", response)
        self.assertIn("2. Follow the campus walking route toward Healey Library.", response)
        self.assertIn("3. Continue for about 0.15 miles.", response)
        self.assertIn("4. You should arrive near Healey Library in about 3.0 minutes.", response)
        self.assertNotIn("computed campus walking path from", response)
        self.assertNotIn("not indoor turn-by-turn directions", response)
        self.assertNotIn("None", response)

    def test_build_routing_attempts_uses_canonical_names_first(self):
        parsed = parse_route_query("How do I get from University Hall to McCormack?")

        attempts = build_routing_attempts(
            parsed["start_resolution"],
            parsed["destination_resolution"],
        )

        self.assertEqual(attempts[0], ("University Hall", "McCormack Hall"))
        self.assertIn(("University Hall", "McCormack"), attempts)
        self.assertIn(("University Hall", "McCormack Building"), attempts)
        self.assertLessEqual(len(attempts), MAX_ROUTE_ATTEMPTS)

    def test_first_mccormack_candidate_success_uses_one_call(self):
        get_route = Mock(
            return_value={
                "success": True,
                "distance_m": 300,
                "estimated_walk_time": 5.0,
                "path": ["n1", "n2"],
            }
        )

        response = handle_route_query("How do I get from University Hall to McCormack?", get_route)

        get_route.assert_called_once_with(
            "University Hall",
            "McCormack Hall",
            algorithm="astar",
            show_map=False,
        )
        self.assertIn("Route found", response)
        self.assertIn("University Hall", response)
        self.assertIn("McCormack Hall", response)

    def test_mccormack_fallback_candidate_can_succeed(self):
        get_route = Mock(
            side_effect=[
                RuntimeError("not found"),
                {
                    "success": True,
                    "distance_m": 300,
                    "estimated_walk_time": 5.0,
                    "path": ["n1", "n2"],
                },
            ]
        )

        response = handle_route_query("How do I get from University Hall to McCormack?", get_route)

        attempted_pairs = [
            (call.args[0], call.args[1])
            for call in get_route.call_args_list
        ]
        self.assertGreaterEqual(get_route.call_count, 2)
        self.assertIn(("University Hall", "McCormack Hall"), attempted_pairs)
        self.assertIn(("University Hall", "McCormack"), attempted_pairs)
        self.assertIn("Route found", response)
        self.assertIn("McCormack Hall", response)
        self.assertNotIn("McCormack Building ->", response)

    def test_all_mccormack_candidates_fail_safely(self):
        get_route = Mock(side_effect=RuntimeError("not found"))

        response = handle_route_query("How do I get from University Hall to McCormack?", get_route)

        self.assertLessEqual(get_route.call_count, MAX_ROUTE_ATTEMPTS)
        self.assertIn(
            "could not generate a route between University Hall and McCormack Hall",
            response,
        )

    def test_missing_start_does_not_call_beaconnav(self):
        get_route = Mock()

        response = handle_route_query("How do I get to Healey Library?", get_route)

        get_route.assert_not_called()
        self.assertIn("Where are you starting from?", response)

    def test_unresolved_start_does_not_call_beaconnav(self):
        get_route = Mock()

        response = handle_route_query("How do I get from fake place to Campus Center?", get_route)

        get_route.assert_not_called()
        self.assertIn("could not confidently identify your starting location", response)

    def test_same_start_and_destination_does_not_call_beaconnav(self):
        get_route = Mock()

        response = handle_route_query("How do I get from University Hall to UHall?", get_route)

        get_route.assert_not_called()
        self.assertIn("start and destination look the same", response)
        self.assertIn("University Hall", response)

    def test_beaconnav_exception_returns_safe_message(self):
        get_route = Mock(side_effect=RuntimeError("Graph failed"))

        response = handle_route_query("How do I get from University Hall to McCormack?", get_route)

        self.assertIn("I recognized the route request, but I could not generate a route", response)
        self.assertIn("University Hall", response)
        self.assertIn("McCormack Hall", response)

    def test_empty_beaconnav_result_returns_safe_failure(self):
        get_route = Mock(return_value={})

        response = handle_route_query("How do I get from University Hall to McCormack?", get_route)

        self.assertLessEqual(get_route.call_count, MAX_ROUTE_ATTEMPTS)
        self.assertIn("could not generate a route between University Hall and McCormack Hall", response)

    def test_harborwalk_false_positive_does_not_call_beaconnav(self):
        get_route = Mock()

        response = handle_route_query("Where is the HarborWalk?", get_route)

        self.assertFalse(is_route_query("Where is the HarborWalk?"))
        get_route.assert_not_called()
        self.assertIsNone(response)


if __name__ == "__main__":
    unittest.main()
