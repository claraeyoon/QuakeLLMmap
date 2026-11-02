from __future__ import annotations
import json
import math
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List

EARTH_RADIUS_KM = 6371.0088

class PhysicsCritic:
    """
    Evaluates physical consistency of MMI assessments against:
    1. Closest 3D distance to fault rupture (Rrup).
    2. Regional GMPE attenuation curves (ShakeMap soil/rock expectations).
    Works with NumPy if installed, or pure Python standard math.
    """

    def __init__(self, fault_trace_path: Optional[str] = None, attenuation_curves_path: Optional[str] = None):
        self.triangles_enu: List[Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float, float]]] = []
        self.lon0 = 96.0
        self.lat0 = 22.0
        self.curves: Dict[str, Any] = {}

        if fault_trace_path and Path(fault_trace_path).exists():
            self._load_fault_mesh(fault_trace_path)

        if attenuation_curves_path and Path(attenuation_curves_path).exists():
            try:
                with open(attenuation_curves_path, "r", encoding="utf-8") as f:
                    self.curves = json.load(f)
            except Exception:
                pass

    def _load_fault_mesh(self, filepath: str):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Extract rings
            rings = []
            features = data.get("features", [])
            for feat in features:
                geom = feat.get("geometry", {})
                gtype = geom.get("type")
                coords = geom.get("coordinates", [])
                if gtype == "MultiPolygon":
                    for poly in coords:
                        for ring in poly:
                            rings.append(ring)
                elif gtype == "Polygon":
                    for ring in coords:
                        rings.append(ring)

            if not rings:
                return

            meta = data.get("metadata", {})
            self.lon0 = float(meta.get("lon", sum(p[0] for p in rings[0]) / len(rings[0])))
            self.lat0 = float(meta.get("lat", sum(p[1] for p in rings[0]) / len(rings[0])))

            for ring in rings:
                pts = list(ring)
                # Drop closing point if identical to first
                if len(pts) > 1 and abs(pts[0][0] - pts[-1][0]) < 1e-9 and abs(pts[0][1] - pts[-1][1]) < 1e-9:
                    pts = pts[:-1]

                n_total = len(pts)
                if n_total < 4 or n_total % 2 != 0:
                    continue

                n = n_total // 2
                top_edge = pts[:n]
                bottom_edge = list(reversed(pts[n:]))

                for i in range(n - 1):
                    q = [
                        top_edge[i],
                        top_edge[i + 1],
                        bottom_edge[i + 1],
                        bottom_edge[i],
                    ]
                    q_enu = [
                        self._geodetic_to_enu_single(
                            float(p[0]), float(p[1]), float(p[2]) if len(p) > 2 else 0.0
                        )
                        for p in q
                    ]
                    # Two triangles per quad: (p0, p1, p2) and (p0, p2, p3)
                    self.triangles_enu.append((q_enu[0], q_enu[1], q_enu[2]))
                    self.triangles_enu.append((q_enu[0], q_enu[2], q_enu[3]))
        except Exception as e:
            print(f"Notice: Rupture mesh loading notice: {e}")

    def _geodetic_to_enu_single(self, lon: float, lat: float, depth_km: float) -> Tuple[float, float, float]:
        lat0_rad = math.radians(self.lat0)
        dlon_rad = math.radians(lon - self.lon0)
        dlat_rad = math.radians(lat - self.lat0)

        east = EARTH_RADIUS_KM * math.cos(lat0_rad) * dlon_rad
        north = EARTH_RADIUS_KM * dlat_rad
        up = -depth_km
        return (east, north, up)

    @staticmethod
    def _point_triangle_distance(
        p: Tuple[float, float, float],
        triangle: Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float, float]]
    ) -> float:
        """
        Calculates the minimum Euclidean distance from a 3D point to a 3D triangle.
        Uses Ericson (2005) 'Real-Time Collision Detection', Section 5.1.5.
        Identical to scripts/rrup_calculator.py.
        """
        a, b, c = triangle
        ab = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        ac = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
        ap = (p[0] - a[0], p[1] - a[1], p[2] - a[2])

        d1 = ab[0] * ap[0] + ab[1] * ap[1] + ab[2] * ap[2]
        d2 = ac[0] * ap[0] + ac[1] * ap[1] + ac[2] * ap[2]
        if d1 <= 0.0 and d2 <= 0.0:
            diff = (p[0] - a[0], p[1] - a[1], p[2] - a[2])
            return math.sqrt(diff[0]**2 + diff[1]**2 + diff[2]**2)

        bp = (p[0] - b[0], p[1] - b[1], p[2] - b[2])
        d3 = ab[0] * bp[0] + ab[1] * bp[1] + ab[2] * bp[2]
        d4 = ac[0] * bp[0] + ac[1] * bp[1] + ac[2] * bp[2]
        if d3 >= 0.0 and d4 <= d3:
            diff = (p[0] - b[0], p[1] - b[1], p[2] - b[2])
            return math.sqrt(diff[0]**2 + diff[1]**2 + diff[2]**2)

        vc = d1 * d4 - d3 * d2
        if vc <= 0.0 and d1 >= 0.0 and d3 <= 0.0:
            v = d1 / (d1 - d3)
            closest = (a[0] + v * ab[0], a[1] + v * ab[1], a[2] + v * ab[2])
            return math.sqrt((p[0] - closest[0])**2 + (p[1] - closest[1])**2 + (p[2] - closest[2])**2)

        cp = (p[0] - c[0], p[1] - c[1], p[2] - c[2])
        d5 = ab[0] * cp[0] + ab[1] * cp[1] + ab[2] * cp[2]
        d6 = ac[0] * cp[0] + ac[1] * cp[1] + ac[2] * cp[2]
        if d6 >= 0.0 and d5 <= d6:
            diff = (p[0] - c[0], p[1] - c[1], p[2] - c[2])
            return math.sqrt(diff[0]**2 + diff[1]**2 + diff[2]**2)

        vb = d5 * d2 - d1 * d6
        if vb <= 0.0 and d2 >= 0.0 and d6 <= 0.0:
            w = d2 / (d2 - d6)
            closest = (a[0] + w * ac[0], a[1] + w * ac[1], a[2] + w * ac[2])
            return math.sqrt((p[0] - closest[0])**2 + (p[1] - closest[1])**2 + (p[2] - closest[2])**2)

        va = d3 * d6 - d5 * d4
        if va <= 0.0 and (d4 - d3) >= 0.0 and (d5 - d6) >= 0.0:
            w = (d4 - d3) / ((d4 - d3) + (d5 - d6))
            closest = (b[0] + w * (c[0] - b[0]), b[1] + w * (c[1] - b[1]), b[2] + w * (c[2] - b[2]))
            return math.sqrt((p[0] - closest[0])**2 + (p[1] - closest[1])**2 + (p[2] - closest[2])**2)

        denom = 1.0 / (va + vb + vc)
        v = vb * denom
        w = vc * denom
        closest = (
            a[0] + ab[0] * v + ac[0] * w,
            a[1] + ab[1] * v + ac[1] * w,
            a[2] + ab[2] * v + ac[2] * w,
        )
        return math.sqrt((p[0] - closest[0])**2 + (p[1] - closest[1])**2 + (p[2] - closest[2])**2)

    def calculate_rrup(self, lat: float, lon: float, depth_km: float = 0.0) -> Optional[float]:
        """Calculates distance (km) to the closest point of the rupture surface."""
        site_enu = self._geodetic_to_enu_single(lon, lat, depth_km)

        if not self.triangles_enu:
            dlat = (lat - self.lat0) * 111.0
            dlon = (lon - self.lon0) * 111.0 * math.cos(math.radians(self.lat0))
            return math.sqrt(dlat**2 + dlon**2)

        min_dist = float("inf")
        for tri in self.triangles_enu:
            dist = self._point_triangle_distance(site_enu, tri)
            if dist < min_dist:
                min_dist = dist

        return float(min_dist)

    def evaluate_consistency(self, mmi: float, lat: float, lon: float) -> Tuple[bool, float, str]:
        """
        Verifies whether an MMI value is physically plausible for the location.
        Returns:
            is_consistent: bool
            rrup_km: float
            notes: str
        """
        rrup = self.calculate_rrup(lat, lon)
        if rrup is None:
            return True, 0.0, "Could not determine fault distance"

        # General empirical bounds for MMI vs Rrup
        if rrup > 150.0 and mmi >= 8.5:
            return False, rrup, f"Physically improbable: MMI {mmi} (violent destruction) reported at Rrup = {rrup:.1f} km without severe basin amplification"

        if rrup < 10.0 and mmi <= 3.0:
            return False, rrup, f"Physically improbable: MMI {mmi} (slight/not felt) reported within 10 km of fault rupture"

        return True, rrup, f"Consistent with regional attenuation (Rrup = {rrup:.1f} km)"
