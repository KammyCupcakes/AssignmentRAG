import networkx as nx

def build_campus_graph():
    graph = nx.Graph()

    graph.add_edge("jfk/umass", "bayside parking lot", distance=0.35)
    graph.add_edge("bayside parking lot", "west garage", distance=0.25)
    graph.add_edge("west garage", "campus center", distance=0.20)
    graph.add_edge("campus center", "university hall", distance=0.10)
    graph.add_edge("campus center", "wheatley hall", distance=0.08)
    graph.add_edge("campus center", "mccormack hall", distance=0.09)
    graph.add_edge("campus center", "integrated sciences complex", distance=0.12)
    graph.add_edge("campus center", "healey", distance=0.10)
    graph.add_edge("campus center", "east residence hall", distance=0.25)
    graph.add_edge("east residence hall", "west residence hall", distance=0.07)

    return graph


def get_walking_route(start_location, end_location):
    start = start_location.lower().strip()
    end = end_location.lower().strip()

    graph = build_campus_graph()

    if start not in graph.nodes:
        return f"I do not recognize the starting location: {start_location}"

    if end not in graph.nodes:
        return f"I do not recognize the ending location: {end_location}"

    path = nx.shortest_path(graph, source=start, target=end, weight="distance")
    distance = nx.shortest_path_length(graph, source=start, target=end, weight="distance")

    walking_speed_mph = 3.0
    estimated_minutes = (distance / walking_speed_mph) * 60

    pretty_path = " → ".join(path)

    return (
        f"The walking route from {start_location} to {end_location} is:\n"
        f"{pretty_path}\n\n"
        f"Estimated distance: {distance:.2f} miles\n"
        f"Estimated walk time: {estimated_minutes:.1f} minutes"
    )