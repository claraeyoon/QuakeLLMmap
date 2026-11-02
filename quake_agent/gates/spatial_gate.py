from __future__ import annotations
from typing import Tuple, Optional, List
from quake_agent.config import EventConfig

class SpatialGate:
    """
    Gate 2: Spatial Grounding.
    Ensures extracted coordinates or location mentions fall strictly
    inside the event's affected regional bounding box.
    """

    def __init__(self, event_config: EventConfig):
        self.event = event_config
        self.bounds = event_config.spatial_bounds

    def check_coordinates(self, lat: Optional[float], lon: Optional[float]) -> Tuple[bool, str]:
        if lat is None or lon is None:
            return True, "Coordinates unknown, requires landmark name resolution"

        min_lat = self.bounds.get("min_lat", -90.0)
        max_lat = self.bounds.get("max_lat", 90.0)
        min_lon = self.bounds.get("min_lon", -180.0)
        max_lon = self.bounds.get("max_lon", 180.0)

        if not (min_lat <= lat <= max_lat and min_lon <= lon <= max_lon):
            return False, f"Coordinates [{lat}, {lon}] lie outside event bounding box [{min_lat}-{max_lat}, {min_lon}-{max_lon}]"

        return True, f"Coordinates [{lat}, {lon}] verified within event bounds"

    def match_known_townships(self, text: str) -> List[str]:
        """Detects if any of the event's known townships or landmarks are mentioned."""
        if not text:
            return []
        matched = []
        text_lower = text.lower()
        for township in self.event.townships:
            if township.lower() in text_lower:
                matched.append(township)
        return matched
