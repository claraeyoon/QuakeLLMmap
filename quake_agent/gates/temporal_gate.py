from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from typing import Tuple, Optional
from quake_agent.config import EventConfig
from quake_agent.core.models import RawContentItem

class TemporalGate:
    """
    Gate 1: Temporal Validation.
    Verifies that the content was created or published AFTER the earthquake origin time (T0).
    Extracts EXIF DateTimeOriginal if the file is a local image.
    """

    def __init__(self, event_config: EventConfig):
        self.event = event_config
        self.t0 = datetime.fromisoformat(self.event.origin_time_utc.replace("Z", "+00:00"))

    def check(self, item: RawContentItem) -> Tuple[bool, str, Optional[datetime]]:
        published_dt = item.published_at

        # If it's a local JPEG/TIFF, attempt reading EXIF metadata
        if item.file_path and item.content_type == "image":
            exif_dt = self._extract_exif_datetime(item.file_path)
            if exif_dt:
                published_dt = exif_dt

        if not published_dt:
            # If no timestamp is available at all, allow through with a notice
            return True, "No timestamp found; accepted with lower provenance", None

        # Ensure timezone-aware comparison
        if published_dt.tzinfo is None:
            published_dt = published_dt.replace(tzinfo=timezone.utc)

        # Allow 5 minutes of clock drift prior to T0
        from datetime import timedelta
        if published_dt < (self.t0 - timedelta(minutes=5)):
            return False, f"Content timestamp ({published_dt.isoformat()}) predates earthquake T0 ({self.t0.isoformat()})", published_dt

        return True, f"Valid timestamp ({published_dt.isoformat()} is after T0)", published_dt

    def _extract_exif_datetime(self, file_path: str) -> Optional[datetime]:
        try:
            from PIL import Image, ExifTags
            img = Image.open(file_path)
            exif = img.getexif()
            if not exif:
                return None
            for tag_id, value in exif.items():
                tag_name = ExifTags.TAGS.get(tag_id, tag_id)
                if tag_name in ("DateTimeOriginal", "DateTimeDigitized", "DateTime"):
                    # Format: "YYYY:MM:DD HH:MM:SS"
                    return datetime.strptime(str(value), "%Y:%m:%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except Exception:
            pass
        return None
