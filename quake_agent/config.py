from __future__ import annotations
import os
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional

# Load .env with fallback to manual parsing if python-dotenv is not installed
try:
    from dotenv import load_dotenv
    load_dotenv()
    if Path("server/.env").exists():
        load_dotenv("server/.env")
except ImportError:
    for p in [Path(".env"), Path("server/.env")]:
        if p.exists():
            for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

@dataclass
class EventConfig:
    """Configuration for a specific earthquake event workspace."""
    event_id: str = "us7000pn9s"
    name: str = "2025 Mw 7.7 Mandalay, Myanmar"
    magnitude: float = 7.7
    origin_time_utc: str = "2025-03-28T06:20:00Z"
    hypocenter: Dict[str, float] = field(default_factory=lambda: {"latitude": 21.95, "longitude": 96.10, "depth_km": 10.0})
    spatial_bounds: Dict[str, float] = field(default_factory=lambda: {"min_lat": 13.0, "max_lat": 27.0, "min_lon": 91.0, "max_lon": 103.0})
    languages: List[str] = field(default_factory=lambda: ["my", "en"])
    townships: List[str] = field(default_factory=lambda: ["Mandalay", "Sagaing", "Amarapura", "Pyin Oo Lwin"])
    local_lexicon: List[str] = field(default_factory=lambda: ["ငလျင်", "ပြိုကျ", "အက်ကွဲ", "earthquake", "collapse", "rupture"])
    building_typologies: List[str] = field(default_factory=lambda: [
        "Unreinforced brick masonry (pagodas, monasteries)",
        "Reinforced concrete frame with brick masonry infill",
        "Timber and bamboo residential structures"
    ])
    fault_trace_file: Optional[str] = "data/myanmar/rupture.json"
    attenuation_curve_file: Optional[str] = "data/myanmar/attenuation_curves.json"
    stationlist_file: Optional[str] = "data/myanmar/stationlist.json"

    @classmethod
    def from_file(cls, path: str | Path) -> EventConfig:
        p = Path(path)
        if not p.exists():
            return cls()
        with open(p, "r", encoding="utf-8") as f:
            if p.suffix in (".yaml", ".yml"):
                try:
                    import yaml
                    data = yaml.safe_load(f)
                except ImportError:
                    data = json.load(f)
            else:
                data = json.load(f)
        event_dict = data.get("event", data)
        return cls(
            event_id=event_dict.get("id", event_dict.get("event_id", "custom_event")),
            name=event_dict.get("name", "Earthquake Event"),
            magnitude=float(event_dict.get("magnitude", 7.0)),
            origin_time_utc=event_dict.get("origin_time_utc", "2025-01-01T00:00:00Z"),
            hypocenter=event_dict.get("hypocenter", {"latitude": 0.0, "longitude": 0.0, "depth_km": 10.0}),
            spatial_bounds=data.get("spatial_bounds", {"min_lat": -90.0, "max_lat": 90.0, "min_lon": -180.0, "max_lon": 180.0}),
            languages=data.get("regional_context", {}).get("languages", ["en"]),
            townships=data.get("regional_context", {}).get("townships", []),
            local_lexicon=data.get("regional_context", {}).get("local_lexicon", []),
            building_typologies=data.get("regional_context", {}).get("building_typologies", []),
            fault_trace_file=data.get("fault_model", {}).get("trace_file"),
            attenuation_curve_file=data.get("fault_model", {}).get("attenuation_curve_file"),
            stationlist_file=data.get("fault_model", {}).get("stationlist_file")
        )

@dataclass
class FilterConfig:
    """Pre-ingestion filtering rules."""
    allowed_locations: Optional[List[str]] = None
    bounding_box: Optional[List[float]] = None  # [min_lon, min_lat, max_lon, max_lat]
    max_rrup_km: Optional[float] = None
    allowed_media_types: List[str] = field(default_factory=lambda: ["pdf", "image", "video"])
    selected_documents: Optional[List[str]] = None
    included_platforms: List[str] = field(default_factory=lambda: ["local", "pdf", "reddit", "youtube", "facebook", "tiktok", "web"])
    excluded_platforms: List[str] = field(default_factory=list)
    provenance_tier: str = "all"  # 'all', 'verified_media', 'official_only'
    time_window_start: Optional[str] = None
    time_window_end: Optional[str] = None

@dataclass
class Settings:
    """Runtime model and API settings."""
    fast_triage_model: str = os.getenv("FAST_TRIAGE_MODEL") or "gemini-3.8-flash"
    deep_reasoning_model: str = os.getenv("DEEP_REASONING_MODEL") or "gemini-3.8-flash"
    fallback_model: str = os.getenv("FALLBACK_MODEL", "gemini-3.6-flash")
    thinking_level: str = os.getenv("GEMINI_THINKING_LEVEL", "low")
    timeout_seconds: float = float(os.getenv("GEMINI_TIMEOUT", "30.0"))
    gemini_api_key: Optional[str] = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    google_maps_api_key: Optional[str] = os.getenv("GOOGLE_MAPS_API_KEY")
    tavily_api_key: Optional[str] = os.getenv("TAVILY_API_KEY")
    data_dir: Path = Path(os.getenv("QUAKE_DATA_DIR", "./data"))
    storage_type: str = os.getenv("STORAGE_TYPE", "duckdb")  # 'duckdb' or 'sqlite'
