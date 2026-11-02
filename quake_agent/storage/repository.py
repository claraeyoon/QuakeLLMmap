from __future__ import annotations
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from quake_agent.core.models import (
    RawContentItem,
    VerificationAudit,
    SeismicEvaluation,
    VerificationStatus,
)

class ContentRepository(ABC):
    """
    Abstract storage repository.
    Allows seamlessly running on DuckDB locally, and migrating later
    to Postgres, Supabase, BigQuery, or AWS with zero changes to agent logic.
    """

    @abstractmethod
    def save_raw_content(self, item: RawContentItem) -> str:
        """Saves a harvested content item. Returns its ID."""
        pass

    @abstractmethod
    def get_raw_content(self, content_id: str) -> Optional[RawContentItem]:
        """Retrieves raw content item by ID."""
        pass

    @abstractmethod
    def save_verification_audit(self, audit: VerificationAudit) -> None:
        """Saves forensic verification audit results."""
        pass

    @abstractmethod
    def save_seismic_evaluation(self, evaluation: SeismicEvaluation) -> None:
        """Saves MMI estimation, coordinates, and physical consistency notes."""
        pass

    @abstractmethod
    def get_verified_evaluations(
        self,
        event_id: str,
        min_confidence: float = 0.5,
        location_filter: Optional[List[str]] = None,
        max_rrup_km: Optional[float] = None
    ) -> List[SeismicEvaluation]:
        """Queries verified seismic evaluations for an event with optional filters."""
        pass

    @abstractmethod
    def export_shakemap_features(self, event_id: str, min_confidence: float = 0.6) -> List[Dict[str, Any]]:
        """Exports observations formatted for USGS ShakeMap v4 *_dat.json."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Closes the repository connection."""
        pass
