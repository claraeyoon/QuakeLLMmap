from __future__ import annotations
import fnmatch
from pathlib import Path
from typing import Optional, Tuple
from quake_agent.config import FilterConfig
from quake_agent.core.models import RawContentItem

class IngestionDispatcher:
    """
    Evaluates whether an inbound item matches the FilterConfig criteria.
    Discards out-of-scope files immediately before spending LLM tokens.
    """

    def __init__(self, filter_config: Optional[FilterConfig] = None):
        self.filter = filter_config or FilterConfig()

    def should_process(self, item: RawContentItem) -> Tuple[bool, str]:
        # 1. Media Type Filter
        if item.content_type not in self.filter.allowed_media_types:
            return False, f"Content type '{item.content_type}' not in allowed types {self.filter.allowed_media_types}"

        # 2. Platform Include / Exclude Filter
        if item.source_platform in self.filter.excluded_platforms:
            return False, f"Platform '{item.source_platform}' explicitly excluded"

        if self.filter.included_platforms and item.source_platform not in self.filter.included_platforms:
            return False, f"Platform '{item.source_platform}' not in included platforms"

        # 3. Selected Documents / Glob Pattern Filter
        if self.filter.selected_documents and item.file_path:
            file_name = Path(item.file_path).name
            matched = False
            for pattern in self.filter.selected_documents:
                if fnmatch.fnmatch(file_name, pattern) or fnmatch.fnmatch(item.file_path, pattern):
                    matched = True
                    break
            if not matched:
                return False, f"File '{file_name}' does not match any selected document patterns"

        # 4. Temporal Window Filter
        if self.filter.time_window_start and item.published_at:
            from datetime import datetime
            start_dt = datetime.fromisoformat(self.filter.time_window_start.replace("Z", "+00:00"))
            if item.published_at.tzinfo is None:
                from datetime import timezone
                item_dt = item.published_at.replace(tzinfo=timezone.utc)
            else:
                item_dt = item.published_at
            if item_dt < start_dt:
                return False, f"Published at {item.published_at} before window start {self.filter.time_window_start}"

        if self.filter.time_window_end and item.published_at:
            from datetime import datetime, timezone
            end_dt = datetime.fromisoformat(self.filter.time_window_end.replace("Z", "+00:00"))
            item_dt = item.published_at if item.published_at.tzinfo else item.published_at.replace(tzinfo=timezone.utc)
            if item_dt > end_dt:
                return False, f"Published at {item.published_at} after window end {self.filter.time_window_end}"

        return True, "Passed all pre-ingestion filters"
