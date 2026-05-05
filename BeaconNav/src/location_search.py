import json
import math
import os
import pickle
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import networkx as nx
import numpy as np
import overpy
import requests


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from campus_locations import resolve_location
except Exception:
    resolve_location = None


RESOLVED_NODE_CACHE = Path(__file__).resolve().parents[1] / "cache" / "resolved_location_nodes.json"


def location_search(query: str):
    query = query.replace(" ", "+")
    headers = {"User-Agent": "CS310-Navigation"}  # user agent is required for OpenStreetMap APIs
    res = requests.get(
        f"https://nominatim.openstreetmap.org/search.php?q={query}&viewbox=-71.05409%2C42.32434%2C-71.03243%2C42.30935&bounded=1&format=jsonv2",
        headers=headers,
    )
    ids = []
    for result in res.json():
        ids.append((result["osm_type"], result["osm_id"]))
    return ids


def get_entrances(id, cache_dir="entrance_cache", force_download=False):
    """
    Gets building entrance nodes from Overpass API or local cache.
    """

    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir)

    cache_file = os.path.join(cache_dir, f"entrances_{id[0]}_{id[1]}.pkl")

    if os.path.isfile(cache_file) and not force_download:
        print(f"Loading entrances from cache: {cache_file}")
        with open(cache_file, "rb") as f:
            return pickle.load(f)

    print("Downloading entrances from Overpass...")

    api = overpy.Overpass(
        url="https://overpass.kumi.systems/api/interpreter"
    )

    res = api.query(
        f'[out:json][timeout:90];'
        f'{id[0]}({id[1]});'
        f'node(area)[entrance~"main|yes"];'
        f'out body;'
    )

    with open(cache_file, "wb") as f:
        pickle.dump(res, f)

    return res


def load_resolved_node_cache(cache_file=RESOLVED_NODE_CACHE):
    try:
        with open(cache_file, "r", encoding="utf-8") as file:
            data = json.load(file)
            return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except (json.JSONDecodeError, OSError, TypeError):
        return {}


def save_resolved_node_cache(cache: dict, cache_file=RESOLVED_NODE_CACHE):
    cache_path = Path(cache_file)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as file:
        json.dump(cache, file, indent=2, sort_keys=True)


def json_safe_node_id(node_id):
    if hasattr(node_id, "item"):
        return node_id.item()
    return node_id


def graph_node_if_present(graph: nx.Graph, node_id):
    if node_id in graph.nodes:
        return node_id
    try:
        int_node = int(node_id)
    except (TypeError, ValueError):
        return None
    return int_node if int_node in graph.nodes else None


def graph_node_coordinate(graph: nx.Graph, node_id):
    data = graph.nodes[node_id]
    coord = data.get("coord")
    if coord and len(coord) >= 2:
        return float(coord[0]), float(coord[1])

    lat = data.get("lat", data.get("y"))
    lon = data.get("lon", data.get("x"))
    if lat is None or lon is None:
        return None
    return float(lat), float(lon)


def haversine_distance_meters(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    earth_radius_meters = 6378137
    delta_lat = math.radians(lat_b - lat_a)
    delta_lon = math.radians(lon_b - lon_a)
    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(math.radians(lat_a))
        * math.cos(math.radians(lat_b))
        * math.sin(delta_lon / 2) ** 2
    )
    return earth_radius_meters * 2 * math.asin(math.sqrt(a))


def nearest_graph_node_from_coordinate(graph: nx.Graph, lat: float, lon: float):
    best_node = None
    best_distance = None

    for node_id in graph.nodes:
        coord = graph_node_coordinate(graph, node_id)
        if coord is None:
            continue

        node_lat, node_lon = coord
        distance = haversine_distance_meters(lat, lon, node_lat, node_lon)
        if best_distance is None or distance < best_distance:
            best_node = node_id
            best_distance = distance

    return best_node


def cache_resolved_node(cache: dict, cache_key: str, graph: nx.Graph, node_id, source: str, cache_file):
    node = graph_node_if_present(graph, node_id)
    if node is None:
        return

    coord = graph_node_coordinate(graph, node)
    lat = coord[0] if coord else None
    lon = coord[1] if coord else None
    cache[cache_key] = {
        "graph_node": json_safe_node_id(node),
        "source": source,
        "lat": lat,
        "lon": lon,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    save_resolved_node_cache(cache, cache_file)


def resolve_metadata(query: str, location_metadata: dict | None = None):
    if location_metadata is not None:
        return location_metadata
    if resolve_location is None:
        return None
    return resolve_location(query)


def cache_key_for(query: str, location_metadata: dict | None):
    if location_metadata and location_metadata.get("canonical_name"):
        return location_metadata["canonical_name"]
    return query


def cached_node_for(cache: dict, cache_key: str, graph: nx.Graph):
    cached = cache.get(cache_key)
    if not isinstance(cached, dict):
        return None
    return graph_node_if_present(graph, cached.get("graph_node"))


def fallback_coordinate_node(graph: nx.Graph, location_metadata: dict | None):
    if not location_metadata:
        return None

    coordinate = location_metadata.get("fallback_coordinate")
    if not coordinate:
        return None

    lat = coordinate.get("lat")
    lon = coordinate.get("lon")
    if lat is None or lon is None:
        return None

    return nearest_graph_node_from_coordinate(graph, float(lat), float(lon))


def get_entrance_nodes(query: str, graph: nx.Graph, radius: int = 10):
    ids = location_search(query)
    for id in ids:
        osm = get_entrances(id)
        nodes = []
        for node in osm.nodes:
            if node.id in graph.nodes:
                nodes.append(node.id)
        if len(nodes) > 0:
            return nodes
    if len(ids) > 0:
        api = overpy.Overpass()
        res = api.query(
            f'({ids[0][0]}({ids[0][1]});)->.poi;way(around.poi: {radius})["highway"~"pedestrian|footway|steps|sidewalk|cycleway|path|corridor"];>->.nodes_around;node.nodes_around(around.poi:  {radius});out;'
        )
        nodes = []
        for node in res.nodes:
            nodes.append(node.id)
        nodes.reverse()
        _, _, node_indices = np.intersect1d(graph.nodes, nodes, return_indices=True)
        nodes = np.take(np.array(nodes), np.sort(node_indices))
        if len(nodes) == 0:
            if radius < 50:
                return get_entrance_nodes(query, graph, int(radius * 1.5))
        return list(nodes)
    warnings.warn(f"no entrances found for {query}")
    return []


def resolve_location_nodes(query: str, graph: nx.Graph, location_metadata: dict | None = None, cache_file=RESOLVED_NODE_CACHE):
    metadata = resolve_metadata(query, location_metadata)
    cache_key = cache_key_for(query, metadata)
    cache = load_resolved_node_cache(cache_file)

    cached_node = cached_node_for(cache, cache_key, graph)
    if cached_node is not None:
        return [cached_node]

    try:
        entrance_nodes = get_entrance_nodes(query, graph)
    except Exception as error:
        warnings.warn(f"entrance lookup failed for {query}: {error}")
        entrance_nodes = []

    if entrance_nodes:
        cache_resolved_node(cache, cache_key, graph, entrance_nodes[0], "entrance_lookup", cache_file)
        return entrance_nodes

    fallback_node = fallback_coordinate_node(graph, metadata)
    if fallback_node is not None:
        cache_resolved_node(cache, cache_key, graph, fallback_node, "fallback_coordinate", cache_file)
        return [fallback_node]

    return []


def get_location_nodes(query: str, graph: nx.Graph, radius: int = 10):
    return resolve_location_nodes(query, graph)


if __name__ == "__main__":
    osm_id, res = location_search("university hall")
    print(osm_id)
    print(res)
