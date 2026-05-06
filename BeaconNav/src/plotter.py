import pickle
import matplotlib
matplotlib.use('Agg')  # Set non-interactive backend BEFORE importing pyplot
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.io.img_tiles as cimgt
import numpy as np
import base64
from io import BytesIO


def __zoom_level(extent: np.ndarray) -> int:
    """
    automatically selects the openstreetmap tile zoom level based on the size of the map being shown
    :param extent: top right and bottom left corner of the map being shown
    :return: the zoom level number
    """
    m = np.max([np.abs(extent[1] - extent[0]), np.abs(extent[3] - extent[2])])
    if m < 0.0055:
        return 18
    elif m < 0.007749:
        return 17
    else:
        return 16


def plot_points(ways: list[np.ndarray], directions: str, crop_to_route=True) -> None:
    """
    plots a line given a list of points on openstreetmap
    :param ways: list of points to plot
    :param directions: a string describing the directions to get from point a to point b
    :param crop_to_route: crops the map to the route given if true otherwise shows the route on the whole UMB campus
    :return: None
    """
    request = cimgt.OSM()
    fig = plt.figure(figsize=(10, 10))
    # Bounds: (lon_min, lon_max, lat_min, lat_max):
    if crop_to_route:
        allways = np.concat(ways, axis=0, dtype=np.double)
        extent = [
            allways[:, 1].min() - 0.002,
            allways[:, 1].max() + 0.002,
            allways[:, 0].min() - 0.002,
            allways[:, 0].max() + 0.002,
        ]
    else:
        extent = [-71.0324853, -71.0521287, 42.3099378, 42.3235297]
    ax = plt.axes(projection=request.crs)
    ax.set_extent(extent)
    ax.add_image(request, __zoom_level(extent))
    for way in ways:
        ax.plot(
            way[:, 1],
            way[:, 0],
            transform=ccrs.PlateCarree(),
            linewidth=2.0,
            color="red",
        )
    ax.text(
        1,
        0.0,
        "© OpenStreetMap contributors  ",
        size=8,
        ha="right",
        va="bottom",
        transform=ax.transAxes,
        backgroundcolor="white",
    )
    ax.text(1.01, 0.9, directions, va="top", ha="left", transform=ax.transAxes, wrap=True)
    ax.margins(x=5)
    plt.margins(x=1)
    fig.tight_layout()
    ax.axis('off')


def plot_route(path: list, graph, text = "", crop_to_route=True, show=True, save_file=None, return_image=True):
    """
    plots a route given by a list of nodes in the graph onto OpenStreetMap
    :param path: the list of nodes in the graph onto which to plot
    :param graph: the networkx graph
    :param text: text displayed next to the map
    :param crop_to_route: crops the map to only show the route if false it shows the entire UMass Boston campus
    :param show: deprecated - ignored (always runs in headless mode)
    :param save_file: save the figure to a file with the name given by save_file
    :param return_image: if True, returns image as base64-encoded PNG bytes
    :return: base64-encoded image string if return_image=True, otherwise None
    """
    points = []
    for i in range(1, len(path)):
        points.append(np.array(graph.get_edge_data(path[i - 1], path[i])["points"]))
    plot_points(points, text, crop_to_route=crop_to_route)
    
    image_data = None
    
    if return_image:
        # Capture figure as base64-encoded PNG
        buffer = BytesIO()
        plt.savefig(buffer, format='png', bbox_inches="tight", pad_inches=0, dpi=150)
        buffer.seek(0)
        image_bytes = buffer.read()
        image_data = base64.b64encode(image_bytes).decode('utf-8')
        buffer.close()
    
    if save_file is not None and save_file != "":
        plt.savefig(save_file, bbox_inches="tight", pad_inches=0, dpi=450)
    
    # Always close the figure to prevent GUI operations and memory leaks
    plt.close('all')
    
    return image_data


if __name__ == "__main__":
    with open("umb_graph.pkl", "rb") as f:
        graph = pickle.load(f)
    plot_route([7672450750, 12660053764, 12660053770, 12660053773], graph, show=False)
    plt.savefig("demo.png", dpi=300)
    plt.show()
