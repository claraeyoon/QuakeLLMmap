"""
rrup_calculator.py

Computes Rrup (closest distance from a site to the rupture plane) from a
USGS ShakeMap-style rupture.json finite-fault file.

Method
------
1. Parse the rupture.json GeoJSON. USGS finite-fault rupture files describe
   the fault as a polygon ring: the top edge trace (depth = 0 or top depth)
   followed by the bottom edge trace (depth = down-dip depth), tracing the
   perimeter of a ribbon (or, for multi-segment ruptures, multiple such
   ribbons, one per MultiPolygon element).
2. Each consecutive pair of (top_i, top_i+1, bottom_i+1, bottom_i) points
   forms a quadrilateral sub-patch of the fault surface. We triangulate each
   quad into two triangles, forming a triangulated mesh approximating the
   (possibly non-planar / listric / multi-segment) rupture surface.
3. Convert all fault points and the site location to a local flat-Earth
   East-North-Up (ENU) Cartesian frame centered near the rupture, since
   geodetic (lon/lat/depth) coordinates are not directly Euclidean.
4. Compute Rrup as the minimum 3D point-to-triangle distance from the site
   to every triangle in the mesh. This is the standard definition of Rrup
   used in NGA-West2 GMPEs (Abrahamson et al., 2014; Boore et al., 2014;
   etc.) and in ShakeMap's own rupture distance calculations.

Notes on accuracy
------------------
- The local ENU (tangent-plane) approximation is very accurate at regional
  scales (tens to a few hundred km) but will accumulate small distortion at
  larger scales (>~500 km) because it does not account for Earth's
  curvature. For continental-to-teleseismic distances, a full geodetic
  (ellipsoidal) point-to-surface calculation would be more rigorous. This
  is more than adequate for near-fault to regional ShakeMap-scale distances
  (which is what Rrup / GMPE application actually requires).
- Depth is assumed positive-down in kilometers, matching the GeoJSON
  rupture format (z-coordinate = depth in km).
"""

import json
import numpy as np


EARTH_RADIUS_KM = 6371.0088  # mean Earth radius (IUGG)


def load_rupture(filepath):
    """Load a ShakeMap rupture.json file."""
    with open(filepath, "r") as f:
        return json.load(f)


def geodetic_to_enu(lon, lat, depth_km, lon0, lat0):
    """
    Convert geodetic coordinates (lon, lat in decimal degrees, depth in km,
    positive down) to a local East-North-Up Cartesian frame (km) centered
    at (lon0, lat0), using an equirectangular tangent-plane approximation.

    East  = R * cos(lat0) * (lon - lon0) [in radians]
    North = R * (lat - lat0) [in radians]
    Up    = -depth  (since depth is positive down, Up is negative depth)
    """
    lon = np.asarray(lon, dtype=float)
    lat = np.asarray(lat, dtype=float)
    depth_km = np.asarray(depth_km, dtype=float)

    lat0_rad = np.radians(lat0)
    dlon_rad = np.radians(lon - lon0)
    dlat_rad = np.radians(lat - lat0)

    east = EARTH_RADIUS_KM * np.cos(lat0_rad) * dlon_rad
    north = EARTH_RADIUS_KM * dlat_rad
    up = -depth_km

    return np.stack([east, north, up], axis=-1)


def extract_rupture_rings(rupture_geojson):
    """
    Extract all polygon rings from a rupture.json FeatureCollection.

    Returns a list of rings, where each ring is an (N, 3) array of
    [lon, lat, depth_km] points (as they appear in the GeoJSON, i.e. still
    in geodetic coordinates -- not yet converted to ENU).
    """
    rings = []
    for feature in rupture_geojson["features"]:
        geom = feature["geometry"]
        geom_type = geom["type"]

        if geom_type == "MultiPolygon":
            # coordinates: [ [ [ring1], [ring2], ... ], [ [ring1], ... ], ... ]
            for polygon in geom["coordinates"]:
                for ring in polygon:
                    rings.append(np.array(ring, dtype=float))
        elif geom_type == "Polygon":
            # coordinates: [ [ring1], [ring2], ... ]
            for ring in geom["coordinates"]:
                rings.append(np.array(ring, dtype=float))
        else:
            raise ValueError(f"Unsupported geometry type: {geom_type}")

    return rings


def ring_to_quad_mesh(ring_lonlatdepth):
    """
    Convert a single perimeter ring (top edge forward, then bottom edge
    backward, as produced by USGS finite-fault rupture files) into a list
    of quadrilateral patches, each defined by 4 corner points in order
    (top_i, top_i+1, bottom_i+1, bottom_i).

    Assumes the ring has the structure:
        [top_0, top_1, ..., top_{n-1}, bottom_{n-1}, ..., bottom_1, bottom_0, top_0]
    i.e. length = 2n + 1 (last point repeats the first to close the ring).

    Returns a list of (4, 3) arrays of [lon, lat, depth] corner points.
    """
    # Drop the final closing point if it duplicates the first
    pts = ring_lonlatdepth
    if np.allclose(pts[0], pts[-1]):
        pts = pts[:-1]

    n_total = len(pts)
    if n_total % 2 != 0:
        raise ValueError(
            f"Ring has odd number of points ({n_total}) after removing "
            "closing point; expected an even number (top edge + bottom edge)."
        )

    n = n_total // 2
    top_edge = pts[:n]
    bottom_edge = pts[n:][::-1]  # reverse back to same along-strike order as top_edge

    quads = []
    for i in range(n - 1):
        quad = np.array([
            top_edge[i],
            top_edge[i + 1],
            bottom_edge[i + 1],
            bottom_edge[i],
        ])
        quads.append(quad)

    return quads


def quad_to_triangles(quad_enu):
    """
    Split a quadrilateral (4, 3) array of ENU points into two triangles.
    Returns a list of two (3, 3) arrays.
    """
    p0, p1, p2, p3 = quad_enu
    tri1 = np.array([p0, p1, p2])
    tri2 = np.array([p0, p2, p3])
    return [tri1, tri2]


def point_triangle_distance(point, triangle):
    """
    Compute the minimum Euclidean distance from a 3D point to a 3D triangle
    (including its interior, edges, and vertices).

    Uses the classic closest-point-on-triangle algorithm
    (Ericson, "Real-Time Collision Detection", 2005, Section 5.1.5).

    Parameters
    ----------
    point : (3,) array
    triangle : (3, 3) array -- rows are vertices A, B, C

    Returns
    -------
    float : minimum distance from point to triangle
    """
    a, b, c = triangle
    p = point

    ab = b - a
    ac = c - a
    ap = p - a

    d1 = np.dot(ab, ap)
    d2 = np.dot(ac, ap)
    if d1 <= 0.0 and d2 <= 0.0:
        return np.linalg.norm(p - a)  # closest to vertex A

    bp = p - b
    d3 = np.dot(ab, bp)
    d4 = np.dot(ac, bp)
    if d3 >= 0.0 and d4 <= d3:
        return np.linalg.norm(p - b)  # closest to vertex B

    vc = d1 * d4 - d3 * d2
    if vc <= 0.0 and d1 >= 0.0 and d3 <= 0.0:
        v = d1 / (d1 - d3)
        closest = a + v * ab
        return np.linalg.norm(p - closest)  # closest to edge AB

    cp = p - c
    d5 = np.dot(ab, cp)
    d6 = np.dot(ac, cp)
    if d6 >= 0.0 and d5 <= d6:
        return np.linalg.norm(p - c)  # closest to vertex C

    vb = d5 * d2 - d1 * d6
    if vb <= 0.0 and d2 >= 0.0 and d6 <= 0.0:
        w = d2 / (d2 - d6)
        closest = a + w * ac
        return np.linalg.norm(p - closest)  # closest to edge AC

    va = d3 * d6 - d5 * d4
    if va <= 0.0 and (d4 - d3) >= 0.0 and (d5 - d6) >= 0.0:
        w = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        closest = b + w * (c - b)
        return np.linalg.norm(p - closest)  # closest to edge BC

    # Closest point is inside the triangle face
    denom = 1.0 / (va + vb + vc)
    v = vb * denom
    w = vc * denom
    closest = a + ab * v + ac * w
    return np.linalg.norm(p - closest)


def compute_rrup(rupture_geojson, site_lon, site_lat, site_depth_km=0.0):
    """
    Compute Rrup: the minimum 3D distance from a site to the rupture surface
    described in a ShakeMap rupture.json FeatureCollection.

    Parameters
    ----------
    rupture_geojson : dict
        Parsed rupture.json content.
    site_lon, site_lat : float
        Site longitude / latitude in decimal degrees.
    site_depth_km : float, optional
        Site depth in km, positive down. Default 0.0 (surface site), which
        is standard for ground-motion sites.

    Returns
    -------
    float
        Rrup in kilometers.
    """
    rings = extract_rupture_rings(rupture_geojson)
    if not rings:
        raise ValueError("No rupture geometry found in rupture.json")

    # Use the hypocenter (or first ring's centroid) as the ENU projection
    # origin to minimize tangent-plane distortion near the area of interest.
    meta = rupture_geojson.get("metadata", {})
    lon0 = meta.get("lon", rings[0][:, 0].mean())
    lat0 = meta.get("lat", rings[0][:, 1].mean())

    site_enu = geodetic_to_enu(site_lon, site_lat, site_depth_km, lon0, lat0)

    min_dist = np.inf
    for ring in rings:
        quads = ring_to_quad_mesh(ring)
        for quad in quads:
            quad_enu = geodetic_to_enu(
                quad[:, 0], quad[:, 1], quad[:, 2], lon0, lat0
            )
            for tri in quad_to_triangles(quad_enu):
                d = point_triangle_distance(site_enu, tri)
                if d < min_dist:
                    min_dist = d

    return min_dist


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Compute Rrup from a site location to a ShakeMap rupture.json fault surface."
    )
    parser.add_argument("rupture_file", help="Path to rupture.json")
    parser.add_argument("lon", type=float, help="Site longitude (decimal degrees)")
    parser.add_argument("lat", type=float, help="Site latitude (decimal degrees)")
    parser.add_argument(
        "--depth", type=float, default=0.0,
        help="Site depth in km, positive down (default: 0.0, surface)"
    )
    args = parser.parse_args()

    rupture_geojson = load_rupture(args.rupture_file)
    rrup = compute_rrup(rupture_geojson, args.lon, args.lat, args.depth)

    print(f"Site:  lon={args.lon}, lat={args.lat}, depth={args.depth} km")
    print(f"Rrup = {rrup:.3f} km")


if __name__ == "__main__":
    main()
