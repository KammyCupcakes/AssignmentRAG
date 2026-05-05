import unittest
from unittest.mock import Mock

from route_parser import is_route_continuation_query, parse_route_continuation_query
from route_state import (
    LAST_ROUTE_CONTEXT,
    clear_last_route_context,
    clear_pending_route,
)


def route_success():
    return {
        "success": True,
        "distance_miles": 0.12,
        "walk_time_minutes": 3.5,
        "path": ["a", "b"],
    }


class RouteContinuationParserTests(unittest.TestCase):
    def test_from_there_is_route_continuation(self):
        parsed = parse_route_continuation_query("from there how do i get to isc")

        self.assertTrue(parsed["is_continuation"])
        self.assertIsNone(parsed["explicit_start"])
        self.assertEqual(parsed["destination"], "isc")
        self.assertTrue(parsed["use_last_destination_as_start"])

    def test_if_i_want_after_reaching_keeps_direction_order(self):
        parsed = parse_route_continuation_query(
            "if i want to go to isc after reaching quinn how do i go"
        )

        self.assertTrue(parsed["is_continuation"])
        self.assertEqual(parsed["explicit_start"], "quinn")
        self.assertEqual(parsed["destination"], "isc")
        self.assertFalse(parsed["use_last_destination_as_start"])

    def test_info_question_is_not_route_continuation(self):
        self.assertFalse(is_route_continuation_query("Where is the HarborWalk?"))
        self.assertFalse(parse_route_continuation_query("Where is the HarborWalk?")["is_continuation"])


class PromptRouteContinuationTests(unittest.TestCase):
    def setUp(self):
        clear_pending_route()
        clear_last_route_context()

    def tearDown(self):
        clear_pending_route()
        clear_last_route_context()

    def test_successful_route_stores_last_context(self):
        import prompt

        original_get_route = prompt.get_route
        try:
            prompt.get_route = Mock(return_value=route_success())

            prompt.handle_query("take me from u hall to quin building")

            self.assertEqual(
                LAST_ROUTE_CONTEXT["current_location"],
                "Quinn Administration Building",
            )
        finally:
            prompt.get_route = original_get_route

    def test_from_there_uses_last_destination_as_start(self):
        import prompt

        original_get_route = prompt.get_route
        try:
            prompt.get_route = Mock(return_value=route_success())

            prompt.handle_query("take me from u hall to quin building")
            response = prompt.handle_query("from there how do i get to isc")

            self.assertEqual(prompt.get_route.call_count, 2)
            prompt.get_route.assert_called_with(
                "Quinn Administration Building",
                "Integrated Sciences Complex",
                algorithm="astar",
                show_map=False,
            )
            self.assertIn(
                "Route found: Quinn Administration Building → Integrated Sciences Complex",
                response,
            )
        finally:
            prompt.get_route = original_get_route

    def test_then_uses_last_destination_as_start(self):
        import prompt

        original_get_route = prompt.get_route
        try:
            prompt.get_route = Mock(return_value=route_success())

            prompt.handle_query("take me from u hall to quin building")
            response = prompt.handle_query("then how do i get to campus center")

            prompt.get_route.assert_called_with(
                "Quinn Administration Building",
                "Campus Center",
                algorithm="astar",
                show_map=False,
            )
            self.assertIn("Route found: Quinn Administration Building → Campus Center", response)
        finally:
            prompt.get_route = original_get_route

    def test_explicit_after_reaching_start_overrides_context(self):
        import prompt

        original_get_route = prompt.get_route
        try:
            prompt.get_route = Mock(return_value=route_success())

            prompt.handle_query("take me from campus center to wheatley hall")
            response = prompt.handle_query(
                "if i want to go to isc after reaching quinn how do i go"
            )

            prompt.get_route.assert_called_with(
                "Quinn Administration Building",
                "Integrated Sciences Complex",
                algorithm="astar",
                show_map=False,
            )
            self.assertIn(
                "Route found: Quinn Administration Building → Integrated Sciences Complex",
                response,
            )
        finally:
            prompt.get_route = original_get_route

    def test_no_context_continuation_asks_for_start_without_rag(self):
        import prompt

        original_get_route = prompt.get_route
        original_get_collection = prompt.get_collection
        try:
            prompt.get_route = Mock()
            prompt.get_collection = Mock(side_effect=AssertionError("RAG should not run"))

            response = prompt.handle_query("from there how do i get to isc")

            prompt.get_route.assert_not_called()
            self.assertIn("I need your starting location", response)
        finally:
            prompt.get_route = original_get_route
            prompt.get_collection = original_get_collection

    def test_info_question_after_context_does_not_call_beaconnav_again(self):
        import prompt

        original_get_route = prompt.get_route
        original_get_collection = prompt.get_collection
        original_client = prompt.client
        try:
            prompt.get_route = Mock(return_value=route_success())
            prompt.handle_query("take me from u hall to quin building")

            prompt.get_collection = Mock(
                return_value=Mock(query=Mock(return_value={"documents": [[]]}))
            )
            prompt.client = Mock()
            prompt.client.chat.completions.create.return_value = Mock(
                choices=[Mock(message=Mock(content="HarborWalk information"))]
            )

            response = prompt.handle_query("Where is the HarborWalk?")

            self.assertEqual(prompt.get_route.call_count, 1)
            self.assertNotIn("Route found", response)
        finally:
            prompt.get_route = original_get_route
            prompt.get_collection = original_get_collection
            prompt.client = original_client

    def test_new_full_route_overrides_last_context(self):
        import prompt

        original_get_route = prompt.get_route
        try:
            prompt.get_route = Mock(return_value=route_success())

            prompt.handle_query("take me from u hall to quin building")
            response = prompt.handle_query("How do I get from Campus Center to Wheatley Hall?")

            prompt.get_route.assert_called_with(
                "Campus Center",
                "Wheatley Hall",
                algorithm="astar",
                show_map=False,
            )
            self.assertIn("Route found: Campus Center → Wheatley Hall", response)
        finally:
            prompt.get_route = original_get_route


if __name__ == "__main__":
    unittest.main()
