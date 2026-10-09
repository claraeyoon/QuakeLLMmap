"""
batch_rrup.py

Reads a whitespace-delimited text file with columns:
    longitude  latitude  intensity

and a ShakeMap rupture.json file, computes Rrup (closest distance to the
rupture surface) for every point, and writes an output text file with:
    longitude  latitude  intensity  rrup_distance

Assumes all input sites are at the surface (depth = 0 km), which is the
standard convention for MMI/DYFI/ground-motion observation points. If you
need per-site depths, see the --depth-col option below.

Requires rrup_calculator.py to be in the same directory (or on PYTHONPATH).
"""

import argparse
import numpy as np

from rrup_calculator import load_rupture, compute_rrup


def read_input_points(filepath, delimiter=None):
    """
    Read a text file with columns: longitude latitude intensity
    (whitespace-delimited by default; pass delimiter="," for CSV-style).

    Blank lines and lines starting with '#' are skipped.

    Returns a list of (lon, lat, intensity) tuples.
    """
    points = []
    with open(filepath, "r") as f:
        for line_num, line in enumerate(f, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            parts = stripped.split(delimiter) if delimiter else stripped.split()
            if len(parts) < 3:
                raise ValueError(
                    f"Line {line_num} in {filepath} does not have at least "
                    f"3 columns (lon, lat, intensity): '{line.rstrip()}'"
                )

            lon, lat, intensity = float(parts[0]), float(parts[1]), float(parts[2])
            points.append((lon, lat, intensity))

    return points


def compute_rrup_for_points(rupture_geojson, points, site_depth_km=0.0):
    """
    Compute Rrup for a list of (lon, lat, intensity) points.

    Returns a list of (lon, lat, intensity, rrup) tuples.
    """
    results = []
    for lon, lat, intensity in points:
        rrup = compute_rrup(rupture_geojson, lon, lat, site_depth_km)
        results.append((lon, lat, intensity, rrup))
    return results


def write_output(results, output_path, delimiter=" ", precision=4):
    with open(output_path, "w") as f:
        for lon, lat, intensity, rrup in results:
            f.write(
                f"{lon}{delimiter}{lat}{delimiter}{intensity}"
                f"{delimiter}{rrup:.{precision}f}\n"
            )


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Append Rrup (closest distance to rupture surface) as a 4th "
            "column to a (longitude, latitude, intensity) text file."
        )
    )
    parser.add_argument("rupture_file", help="Path to rupture.json")
    parser.add_argument(
        "input_file",
        help="Path to input text file with columns: longitude latitude intensity"
    )
    parser.add_argument(
        "output_file",
        help="Path to output text file (adds rrup_distance as 4th column)"
    )
    parser.add_argument(
        "--depth", type=float, default=0.0,
        help="Site depth in km, positive down, applied to all points (default: 0.0, surface)"
    )
    parser.add_argument(
        "--csv", action="store_true",
        help="Treat input as comma-delimited and write output as comma-delimited (default: whitespace)"
    )
    args = parser.parse_args()

    input_delim = "," if args.csv else None
    output_delim = "," if args.csv else " "

    rupture_geojson = load_rupture(args.rupture_file)
    points = read_input_points(args.input_file, delimiter=input_delim)

    print(f"Loaded {len(points)} points from {args.input_file}")
    print(f"Computing Rrup against rupture surface from {args.rupture_file} ...")

    results = compute_rrup_for_points(rupture_geojson, points, site_depth_km=args.depth)

    write_output(results, args.output_file, delimiter=output_delim)

    rrup_vals = np.array([r[3] for r in results])
    print(f"Wrote {len(results)} rows to {args.output_file}")
    print(f"Rrup range: {rrup_vals.min():.3f} - {rrup_vals.max():.3f} km "
          f"(mean {rrup_vals.mean():.3f} km)")


if __name__ == "__main__":
    main()
