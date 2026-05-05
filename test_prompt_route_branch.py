import unittest
from unittest.mock import Mock

from route_state import clear_last_route_context, clear_pending_route


class PromptRouteBranchTests(unittest.TestCase):
    def setUp(self):
        clear_pending_route()
        clear_last_route_context()

    def tearDown(self):
        clear_pending_route()
        clear_last_route_context()

    def test_handle_query_route_branch_calls_beaconnav_without_rag_lookup(self):
        import prompt

        original_get_route = prompt.get_route
        try:
            prompt.get_route = Mock(
                return_value={
                    "success": True,
                    "distance_miles": 0.12,
                    "walk_time_minutes": 3.5,
                    "path": ["a", "b"],
                }
            )

            response = prompt.handle_query("take me from u hall to quin building")

            prompt.get_route.assert_called_once_with(
                "University Hall",
                "Quinn Administration Building",
                algorithm="astar",
                show_map=False,
            )
            self.assertIn("Route found", response)
            self.assertIn("University Hall", response)
            self.assertIn("Quinn Administration Building", response)
        finally:
            prompt.get_route = original_get_route

    def test_handle_query_completes_pending_route_without_rag_lookup(self):
        import prompt

        original_get_route = prompt.get_route
        try:
            prompt.get_route = Mock(
                return_value={
                    "success": True,
                    "distance_miles": 0.12,
                    "walk_time_minutes": 3.5,
                    "path": ["a", "b"],
                }
            )

            clarification = prompt.handle_query("How do I get to Healey Library?")
            response = prompt.handle_query("Campus Center")

            prompt.get_route.assert_called_once_with(
                "Campus Center",
                "Healey Library",
                algorithm="astar",
                show_map=False,
            )
            self.assertIn("Where are you starting from?", clarification)
            self.assertIn("Route found: Campus Center → Healey Library", response)
        finally:
            prompt.get_route = original_get_route


if __name__ == "__main__":
    unittest.main()
