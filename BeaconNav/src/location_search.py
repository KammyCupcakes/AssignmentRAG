import warnings
import numpy as np
import requests
import overpy
import networkx as nx
import pickle
import os 


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


def get_location_nodes(query: str, graph: nx.Graph, radius: int = 10):
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
                return get_location_nodes(query, graph, int(radius * 1.5))
        return nodes
    warnings.warn(f"no entrances found for {query}")


if __name__ == "__main__":
    osm_id, res = location_search("university hall")
    print(osm_id)
    print(res)
