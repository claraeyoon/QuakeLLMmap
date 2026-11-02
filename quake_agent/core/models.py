from __future__ import annotations
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Dict, Any, List, Optional

class VerificationStatus(str, Enum):
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"

class EvidenceType(str, Enum):
    STRUCTURAL_DAMAGE = "STRUCTURAL_DAMAGE"
    DYNAMIC_SHAKING = "DYNAMIC_SHAKING"
    SURFACE_RUPTURE = "SURFACE_RUPTURE"
    LIQUEFACTION = "LIQUEFACTION"
    HUMAN_REACTION = "HUMAN_REACTION"

@dataclass
class RawContentItem:
    event_id: str
    source_platform: str  # 'local', 'pdf', 'reddit', 'youtube', 'facebook', 'tiktok', 'web'
    content_type: str     # 'pdf', 'image', 'video', 'text'
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    file_path: Optional[str] = None
    source_url: Optional[str] = None
    published_at: Optional[datetime] = None
    harvested_at: datetime = field(default_factory=datetime.utcnow)
    title: Optional[str] = None
    text_content: Optional[str] = None
    raw_metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if self.published_at:
            d["published_at"] = self.published_at.isoformat()
        if self.harvested_at:
            d["harvested_at"] = self.harvested_at.isoformat()
        return d

@dataclass
class VerificationAudit:
    content_id: str
    is_temporal_valid: bool = True
    temporal_reason: Optional[str] = None
    reverse_search_hit_prior: bool = False
    ai_generated_score: float = 0.0  # 0.0 (camera authentic) to 1.0 (synthetic/AI)
    forensic_reasoning: Optional[str] = None
    spatial_grounding_valid: bool = True
    spatial_reason: Optional[str] = None
    status: VerificationStatus = VerificationStatus.VERIFIED
    rejection_reason: Optional[str] = None
    audited_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        d["audited_at"] = self.audited_at.isoformat()
        return d

@dataclass
class SeismicEvaluation:
    content_id: str
    event_id: str
    mmi_estimation: float
    confidence: float
    reasoning: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_name: Optional[str] = None
    location_precision: str = "approximate"
    building_type: Optional[str] = None
    building_materials: Optional[str] = None
    damage_description: Optional[str] = None
    evidence_analysis: Optional[str] = None
    auditory_cues: Optional[str] = None
    visual_cues: Optional[str] = None
    rrup_km: Optional[float] = None
    physics_consistent: bool = True
    physics_notes: Optional[str] = None
    has_damage_photos: bool = True
    evidence_type: EvidenceType = EvidenceType.STRUCTURAL_DAMAGE
    file_name: Optional[str] = None
    model_name: Optional[str] = None
    initial_analysis: Optional[str] = None
    final_analysis: Optional[Dict[str, Any]] = None
    generation_report: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_shakemap_feature(self) -> Dict[str, Any]:
        """Convert into USGS ShakeMap v4 observation JSON format."""
        stddev = round(0.35 + (1.0 - max(0.0, min(1.0, self.confidence))) * 0.70, 2)
        return {
            "type": "Feature",
            "id": f"QUAKELLM.{self.content_id[:8]}",
            "properties": {
                "code": self.content_id[:8],
                "name": self.location_name or "AI Eyewitness Observation",
                "file_name": self.file_name,
                "model_name": self.model_name,
                "netid": "QUAKELLM",
                "source": "QuakeLLMmap Agentic Reconnaissance",
                "intensity": round(self.mmi_estimation, 1),
                "intensity_stddev": stddev,
                "intensity_flag": "0",
                "rrup_km": round(self.rrup_km, 2) if self.rrup_km is not None else None,
                "building_type": self.building_type
            },
            "geometry": {
                "type": "Point",
                "coordinates": [self.longitude, self.latitude]
            }
        }

    def to_dict(self) -> Dict[str, Any]:
        """Dictionary representation of evaluation for export and logging."""
        return {
            "content_id": self.content_id,
            "event_id": self.event_id,
            "file_name": self.file_name,
            "model_name": self.model_name,
            "mmi_estimation": self.mmi_estimation,
            "confidence": self.confidence,
            "rrup_km": round(self.rrup_km, 3) if self.rrup_km is not None else None,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "location_name": self.location_name,
            "location_precision": self.location_precision,
            "building_type": self.building_type,
            "building_materials": self.building_materials,
            "damage_description": self.damage_description,
            "evidence_analysis": self.evidence_analysis,
            "has_damage_photos": self.has_damage_photos,
            "physics_consistent": self.physics_consistent,
            "physics_notes": self.physics_notes,
            "reasoning": self.reasoning,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
