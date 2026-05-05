import csv
import json
import pickle
import re
from pathlib import Path


ENTRANCE_CACHE_DIR = Path("entrance_cache")
CSV_OUTPUT = Path("coordinate_candidates.csv")
MD_OUTPUT = Path("coordinate_candidates.md")
GEOJSON_OUTPUT = Path("coordinate_candidates.geojson")


def extract_way_id(cache_file: Path) -> str:
    match = re.search(r"entrances_way_(\d+)\.pkl$", cache_file.name)
    return match.group(1) if match else ""


def maps_url(lat: str, lon: str) -> str:
    return f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"


def osm_url(lat: str, lon: str) -> str:
    return f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=19/{lat}/{lon}"


def node_rows_from_cache(cache_file: Path) -> list[dict]:
    way_id = extract_way_id(cache_file)
    rows = []

    with cache_file.open("rb") as file:
        result = pickle.load(file)

    for index, node in enumerate(result.nodes, start=1):
        lat = str(node.lat)
        lon = str(node.lon)
        rows.append(
            {
                "cache_filename": cache_file.as_posix(),
                "osm_way_id": way_id,
                "node_id": str(node.id),
                "node_index": str(index),
                "latitude": lat,
                "longitude": lon,
                "google_maps_url": maps_url(lat, lon),
                "openstreetmap_url": osm_url(lat, lon),
                "verified_building": "",
                "notes": "",
            }
        )

    return rows


def collect_rows(cache_dir: Path = ENTRANCE_CACHE_DIR) -> list[dict]:
    rows = []
    if not cache_dir.exists():
        return rows

    for cache_file in sorted(cache_dir.glob("entrances_way_*.pkl")):
        rows.extend(node_rows_from_cache(cache_file))

    return rows


def write_csv(rows: list[dict], output_path: Path = CSV_OUTPUT) -> None:
    fieldnames = [
        "cache_filename",
        "osm_way_id",
        "node_id",
        "node_index",
        "latitude",
        "longitude",
        "google_maps_url",
        "openstreetmap_url",
        "verified_building",
        "notes",
    ]
    with output_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(rows: list[dict], output_path: Path = MD_OUTPUT) -> None:
    lines = [
        "# Coordinate Candidates",
        "",
        "These rows are exported from local BeaconNav entrance cache files.",
        "They are unlabeled until a human verifies which campus building each coordinate belongs to.",
        "",
        "| Cache file | OSM way ID | Node ID | Lat | Lon | Map links | Verified building | Notes |",
        "|---|---:|---:|---:|---:|---|---|---|",
    ]

    for row in rows:
        links = f"[Google]({row['google_maps_url']}) / [OSM]({row['openstreetmap_url']})"
        lines.append(
            "| "
            f"{row['cache_filename']} | "
            f"{row['osm_way_id']} | "
            f"{row['node_id']} | "
            f"{row['latitude']} | "
            f"{row['longitude']} | "
            f"{links} | "
            " | "
            " |"
        )

    lines.append("")
    output_path.write_text("\n".join(lines), encoding="utf-8")


def write_geojson(rows: list[dict], output_path: Path = GEOJSON_OUTPUT) -> None:
    features = []
    for row in rows:
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [
                        float(row["longitude"]),
                        float(row["latitude"]),
                    ],
                },
                "properties": {
                    "cache_filename": row["cache_filename"],
                    "osm_way_id": row["osm_way_id"],
                    "node_id": row["node_id"],
                    "node_index": row["node_index"],
                    "google_maps_url": row["google_maps_url"],
                    "openstreetmap_url": row["openstreetmap_url"],
                    "verified_building": row["verified_building"],
                    "notes": row["notes"],
                },
            }
        )

    output_path.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    rows = collect_rows()
    write_csv(rows)
    write_markdown(rows)
    write_geojson(rows)
    print(f"Exported {len(rows)} coordinate candidates.")
    print(f"Wrote {CSV_OUTPUT}")
    print(f"Wrote {MD_OUTPUT}")
    print(f"Wrote {GEOJSON_OUTPUT}")


if __name__ == "__main__":
    main()
