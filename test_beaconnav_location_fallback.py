import os
import sys
import unittest
from unittest.mock import Mock, mock_open, patch

import networkx as nx


BEACONNAV_SRC = os.path.join(os.path.dirname(__file__), "BeaconNav", "src")
if BEACONNAV_SRC not in sys.path:
    sys.path.insert(0, BEACONNAV_SRC)

from location_search import (
    load_resolved_node_cache,
    nearest_graph_node_from_coordinate,
    resolve_location_nodes,
)


class BeaconNavLocationFallbackTests(unittest.TestCase):
    def test_nearest_graph_node_from_coordinate_uses_graph_coord_data(self):
        graph = nx.Graph()
        graph.add_node(1, coord=(42.3140, -71.0390))
        graph.add_node(2, coord=(42.3200, -71.0500))

        node = nearest_graph_node_from_coordinate(graph, 42.3141, -71.0391)

        self.assertEqual(node, 1)

    def test_cache_miss_then_fallback_coordinate_is_cached(self):
        graph = nx.Graph()
        graph.add_node(123, coord=(42.3140, -71.0390))
        metadata = {
            "canonical_name": "Wheatley Hall",
            "fallback_coordinate": {"lat": 42.3140, "lon": -71.0390},
        }

        save_cache = Mock()

        with (
            patch("location_search.load_resolved_node_cache", return_value={}),
            patch("location_search.save_resolved_node_cache", save_cache),
            patch("location_search.get_entrance_nodes", return_value=[]),
        ):
            nodes = resolve_location_nodes(
                "Wheatley Hall",
                graph,
                location_metadata=metadata,
            )

        self.assertEqual(nodes, [123])
        written_cache = save_cache.call_args.args[0]
        self.assertEqual(written_cache["Wheatley Hall"]["graph_node"], 123)
        self.assertEqual(written_cache["Wheatley Hall"]["source"], "fallback_coordinate")

    def test_cache_hit_avoids_entrance_lookup(self):
        graph = nx.Graph()
        graph.add_node(123, coord=(42.3140, -71.0390))
        cache = {
            "Wheatley Hall": {
                "graph_node": 123,
                "source": "fallback_coordinate",
                "lat": 42.3140,
                "lon": -71.0390,
            }
        }
        entrance_lookup = Mock(return_value=[])

        with (
            patch("location_search.load_resolved_node_cache", return_value=cache),
            patch("location_search.get_entrance_nodes", entrance_lookup),
        ):
            nodes = resolve_location_nodes(
                "Wheatley Hall",
                graph,
                location_metadata={"canonical_name": "Wheatley Hall"},
            )

        self.assertEqual(nodes, [123])
        entrance_lookup.assert_not_called()

    def test_corrupted_cache_does_not_crash(self):
        with patch("builtins.open", mock_open(read_data="{broken json")):
            self.assertEqual(load_resolved_node_cache("cache.json"), {})

    def test_corrupted_cache_falls_back_to_coordinate(self):
        graph = nx.Graph()
        graph.add_node(123, coord=(42.3140, -71.0390))
        metadata = {
            "canonical_name": "Wheatley Hall",
            "fallback_coordinate": {"lat": 42.3140, "lon": -71.0390},
        }

        with (
            patch("location_search.load_resolved_node_cache", return_value={}),
            patch("location_search.save_resolved_node_cache"),
            patch("location_search.get_entrance_nodes", return_value=[]),
        ):
            nodes = resolve_location_nodes(
                "Wheatley Hall",
                graph,
                location_metadata=metadata,
            )

        self.assertEqual(nodes, [123])

    def test_missing_entrance_and_missing_coordinate_returns_empty_list(self):
        graph = nx.Graph()
        graph.add_node(123, coord=(42.3140, -71.0390))

        with (
            patch("location_search.load_resolved_node_cache", return_value={}),
            patch("location_search.get_entrance_nodes", return_value=[]),
        ):
            nodes = resolve_location_nodes(
                "Wheatley Hall",
                graph,
                location_metadata={
                    "canonical_name": "Wheatley Hall",
                    "fallback_coordinate": None,
                },
            )

        self.assertEqual(nodes, [])


if __name__ == "__main__":
    unittest.main()
