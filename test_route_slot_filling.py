import unittest
from unittest.mock import Mock

from route_parser import parse_route_query
from route_state import (
    PENDING_ROUTE_STATE,
    clear_last_route_context,
    clear_pending_route,
    start_pending_route,
    try_complete_pending_route,
)


def route_success():
    return {
        "success": True,
        "distance_miles": 0.12,
        "walk_time_minutes": 3.5,
        "path": ["a", "b"],
    }


class RouteSlotFillingTests(unittest.TestCase):
    def setUp(self):
        clear_pending_route()
        clear_last_route_context()

    def tearDown(self):
        clear_pending_route()
        clear_last_route_context()

    def test_missing_start_creates_pending_state(self):
        message = start_pending_route(parse_route_query("How do I get to Healey Library?"))

        self.assertIn("Where are you starting from?", message)
        self.assertEqual(PENDING_ROUTE_STATE["missing"], "start")
        self.assertEqual(PENDING_ROUTE_STATE["destination"], "Healey Library")

    def test_follow_up_start_completes_route_and_clears_pending_state(self):
        start_pending_route(parse_route_query("How do I get to Healey Library?"))
        get_route = Mock(return_value=route_success())

        response = try_complete_pending_route("Campus Center", get_route)

        get_route.assert_called_once_with(
            "Campus Center",
            "Healey Library",
            algorithm="astar",
            show_map=False,
        )
        self.assertIn("Route found: Campus Center → Healey Library", response)
        self.assertEqual(PENDING_ROUTE_STATE, {})

    def test_missing_destination_creates_pending_state(self):
        message = start_pending_route(parse_route_query("How do I get from Campus Center?"))

        self.assertIn("Where are you trying to go?", message)
        self.assertEqual(PENDING_ROUTE_STATE["missing"], "destination")
        self.assertEqual(PENDING_ROUTE_STATE["start"], "Campus Center")

    def test_follow_up_destination_completes_route_and_clears_pending_state(self):
        start_pending_route(parse_route_query("How do I get from Campus Center?"))
        get_route = Mock(return_value=route_success())

        response = try_complete_pending_route("Wheatley Hall", get_route)

        get_route.assert_called_once_with(
            "Campus Center",
            "Wheatley Hall",
            algorithm="astar",
            show_map=False,
        )
        self.assertIn("Route found: Campus Center → Wheatley Hall", response)
        self.assertEqual(PENDING_ROUTE_STATE, {})

    def test_unresolved_follow_up_keeps_pending_state_active(self):
        start_pending_route(parse_route_query("How do I get to Healey Library?"))
        get_route = Mock()

        response = try_complete_pending_route("some random place", get_route)

        get_route.assert_not_called()
        self.assertIn("could not confidently identify your starting location", response)
        self.assertEqual(PENDING_ROUTE_STATE["missing"], "start")

    def test_cancel_clears_pending_state(self):
        start_pending_route(parse_route_query("How do I get to Healey Library?"))

        response = try_complete_pending_route("cancel", Mock())

        self.assertEqual(response, "Okay, I canceled that route request.")
        self.assertEqual(PENDING_ROUTE_STATE, {})

    def test_new_full_route_overrides_pending_state(self):
        start_pending_route(parse_route_query("How do I get to Healey Library?"))
        get_route = Mock(return_value=route_success())

        response = try_complete_pending_route(
            "How do I get from University Hall to McCormack?",
            get_route,
        )

        get_route.assert_called_once_with(
            "University Hall",
            "McCormack Hall",
            algorithm="astar",
            show_map=False,
        )
        self.assertIn("Route found: University Hall → McCormack Hall", response)
        self.assertEqual(PENDING_ROUTE_STATE, {})

    def test_expired_pending_route_is_ignored_and_cleared(self):
        start_pending_route(parse_route_query("How do I get to Healey Library?"), now=0)
        get_route = Mock()

        response = try_complete_pending_route("Campus Center", get_route, now=301)

        self.assertIsNone(response)
        get_route.assert_not_called()
        self.assertEqual(PENDING_ROUTE_STATE, {})


if __name__ == "__main__":
    unittest.main()
