from __future__ import annotations
import json
from pathlib import Path
from typing import List, Dict, Any
from quake_agent.storage.repository import ContentRepository

class ShakeMapExporter:
    """
    Exports verified agentic MMI evaluations to the official
    USGS ShakeMap v4 Input Data Specification (*_dat.json).
    See: https://ghsc.code-pages.usgs.gov/esi/shakemap/input-data/index.html
    """

    def __init__(self, repository: ContentRepository):
        self.repo = repository

    def export_dat_json(self, event_id: str, output_path: str | Path, min_confidence: float = 0.4) -> Path:
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)

        features = self.repo.export_shakemap_features(event_id=event_id, min_confidence=min_confidence)

        geojson_doc = {
            "type": "FeatureCollection",
            "metadata": {
                "event_id": event_id,
                "source": "QuakeLLMmap Agentic Reconnaissance",
                "count": len(features)
            },
            "features": features
        }

        with open(out_p, "w", encoding="utf-8") as f:
            json.dump(geojson_doc, f, indent=2)

        return out_p
