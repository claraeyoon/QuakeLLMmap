from __future__ import annotations
import mimetypes
from pathlib import Path
from datetime import datetime
from typing import List, Optional

from quake_agent.core.models import RawContentItem
from quake_agent.harvesters.pdf_extractor import PDFExtractor

class LocalFileWatcher:
    """
    Scans a local directory for earthquake damage media
    (PDFs, images, and videos), converting them to RawContentItems.
    """

    def __init__(self, inbound_dir: str | Path, event_id: str):
        self.inbound_dir = Path(inbound_dir)
        self.event_id = event_id
        self.inbound_dir.mkdir(parents=True, exist_ok=True)
        self.pdf_extractor = PDFExtractor(output_dir=self.inbound_dir / ".extracted_pages")

    def scan(self) -> List[RawContentItem]:
        items: List[RawContentItem] = []
        if not self.inbound_dir.exists():
            return items

        supported_extensions = {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov", ".txt"}

        for path in sorted(self.inbound_dir.iterdir()):
            if path.name.startswith(".") or not path.is_file():
                continue

            ext = path.suffix.lower()
            if ext not in supported_extensions:
                continue

            content_type = "image"
            if ext == ".pdf":
                content_type = "pdf"
            elif ext in {".mp4", ".mov"}:
                content_type = "video"
            elif ext == ".txt":
                content_type = "text"

            text_content = ""
            if content_type == "pdf":
                text_content = self.pdf_extractor.extract_text(path)
            elif content_type == "text":
                text_content = path.read_text(encoding="utf-8", errors="ignore")

            # Check for accompanying sidecar text/metadata file (e.g., photo.jpg + photo.txt)
            if not text_content:
                sidecar_txt = path.with_suffix(".txt")
                sidecar_json = path.with_suffix(".json")
                if sidecar_txt.exists():
                    text_content = sidecar_txt.read_text(encoding="utf-8", errors="ignore")
                elif sidecar_json.exists():
                    text_content = sidecar_json.read_text(encoding="utf-8", errors="ignore")

            stat = path.stat()
            file_mtime = datetime.utcfromtimestamp(stat.st_mtime)

            item = RawContentItem(
                event_id=self.event_id,
                source_platform="local",
                content_type=content_type,
                file_path=str(path.resolve()),
                source_url=None,
                published_at=file_mtime,
                harvested_at=datetime.utcnow(),
                title=path.name,
                text_content=text_content or None,
                raw_metadata={"file_size": stat.st_size, "extension": ext}
            )
            items.append(item)

        return items
