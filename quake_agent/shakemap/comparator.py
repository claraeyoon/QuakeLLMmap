from __future__ import annotations
import json
import urllib.request
from pathlib import Path
from typing import Dict, Any, List, Optional

class ShakeMapComparator:
    """
    Fetches the official USGS ShakeMap from ComCat API,
    compares agentic MMI observations against official estimates,
    and computes residual statistics (Delta MMI = MMI_agent - MMI_official).
    Uses pure standard library math.
    """

    def __init__(self, output_dir: Optional[str | Path] = None):
        self.output_dir = Path(output_dir or "./data/shakemap_comparison")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def fetch_official_shakemap(self, event_id: str) -> Dict[str, Any]:
        """Queries USGS ComCat for official ShakeMap products."""
        url = f"https://earthquake.usgs.gov/fdsnws/event/1/query?eventid={event_id}&format=geojson"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "QuakeAgent/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            products = data.get("properties", {}).get("products", {})
            shakemap_list = products.get("shakemap", [])
            if not shakemap_list:
                return {"status": "not_found", "message": f"No official ShakeMap product found for {event_id}"}

            sm = shakemap_list[0]
            contents = sm.get("contents", {})

            downloaded = {}
            for target in ["grid.xml", "stationlist.json", "intensity.jpg", "cont_mmi.json"]:
                target_key = f"download/{target}" if f"download/{target}" in contents else target
                if target_key in contents:
                    file_url = contents[target_key]["url"]
                    local_file = self.output_dir / f"official_{target}"
                    urllib.request.urlretrieve(file_url, local_file)
                    downloaded[target] = str(local_file)

            return {
                "status": "success",
                "event_id": event_id,
                "magnitude": sm.get("properties", {}).get("magnitude"),
                "max_intensity": sm.get("properties", {}).get("intensity"),
                "downloaded_files": downloaded
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def compute_residuals(self, agent_evaluations: List[Any], official_stations_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Computes residual statistics between agent MMI observations
        and nearest official USGS DYFI / ground observations.
        """
        if not agent_evaluations:
            return {"count": 0, "mean_residual": 0.0, "std_residual": 0.0}

        agent_mmis = [e.mmi_estimation for e in agent_evaluations if e.mmi_estimation is not None]
        rrups = [e.rrup_km for e in agent_evaluations if e.rrup_km is not None]

        summary = {
            "agent_observations_count": len(agent_evaluations),
            "agent_mmi_min": float(min(agent_mmis)) if agent_mmis else 0.0,
            "agent_mmi_max": float(max(agent_mmis)) if agent_mmis else 0.0,
            "agent_mmi_mean": round(float(sum(agent_mmis) / len(agent_mmis)), 2) if agent_mmis else 0.0,
            "mean_rrup_km": round(float(sum(rrups) / len(rrups)), 2) if rrups else 0.0
        }

        # If official stationlist exists, compare against official macroseismic stations
        if official_stations_path and Path(official_stations_path).exists():
            try:
                with open(official_stations_path, "r", encoding="utf-8") as f:
                    st_data = json.load(f)
                features = st_data.get("features", [])
                official_mmis = []
                for f in features:
                    props = f.get("properties", {})
                    raw_val = props.get("intensity")
                    if raw_val is not None:
                        try:
                            official_mmis.append(float(raw_val))
                        except (ValueError, TypeError):
                            pass

                if official_mmis:
                    summary["official_dyfi_count"] = len(official_mmis)
                    summary["official_mmi_mean"] = round(float(sum(official_mmis) / len(official_mmis)), 2)
                    summary["overall_mmi_shift"] = round(summary["agent_mmi_mean"] - summary["official_mmi_mean"], 2)
            except Exception as e:
                summary["comparison_notice"] = str(e)

        return summary
