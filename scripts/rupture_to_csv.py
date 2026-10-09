"""
rupture_to_csv.py

Reads a USGS ShakeMap-style rupture.json file and writes all rupture
vertex coordinates (longitude, latitude, depth) to a CSV file.

Handles Polygon and MultiPolygon geometries, and multiple features, as
found in ShakeMap finite-fault rupture products.
"""

import json
import csv
import argparse


def load_rupture(filepath):
    with open(filepath, "r") as f:
        return json.load(f)


def extract_vertices(rupture_geojson):
    """
    Extract all (lon, lat, depth) vertices from every ring, in every
    polygon, in every feature of the rupture GeoJSON.

    Returns a list of (lon, lat, depth) tuples, in the order encountered.
    """
    vertices = []

    for feature in rupture_geojson["features"]:
        geom = feature["geometry"]
        geom_type = geom["type"]

        if geom_type == "MultiPolygon":
            # coordinates: [ [ [ring1], [ring2], ... ], [ [ring1], ... ], ... ]
            for polygon in geom["coordinates"]:
                for ring in polygon:
                    for point in ring:
                        vertices.append(tuple(point))
        elif geom_type == "Polygon":
            # coordinates: [ [ring1], [ring2], ... ]
            for ring in geom["coordinates"]:
                for point in ring:
                    vertices.append(tuple(point))
        else:
            raise ValueError(f"Unsupported geometry type: {geom_type}")

    return vertices


def write_csv(vertices, output_path):
    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["longitude", "latitude", "depth"])
        for lon, lat, depth in vertices:
            writer.writerow([lon, lat, depth])


def main():
    parser = argparse.ArgumentParser(
        description="Extract rupture vertices (lon, lat, depth) from a rupture.json file to CSV."
    )
    parser.add_argument("rupture_file", help="Path to rupture.json")
    parser.add_argument(
        "output_csv", nargs="?", default="rupture_vertices.csv",
        help="Path to output CSV file (default: rupture_vertices.csv)"
    )
    args = parser.parse_args()

    rupture_geojson = load_rupture(args.rupture_file)
    vertices = extract_vertices(rupture_geojson)
    write_csv(vertices, args.output_csv)

    print(f"Wrote {len(vertices)} vertices to {args.output_csv}")


if __name__ == "__main__":
    main()
