from __future__ import annotations
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from quake_agent.storage.repository import ContentRepository
from quake_agent.core.models import (
    RawContentItem,
    VerificationAudit,
    SeismicEvaluation,
    VerificationStatus,
    EvidenceType,
)

# Try importing duckdb, fallback to sqlite3 if unavailable
try:
    import duckdb
    HAS_DUCKDB = True
except ImportError:
    HAS_DUCKDB = False

class LocalStorageRepository(ContentRepository):
    """
    Local-first embedded database implementation.
    Uses DuckDB by default for high-performance analytics,
    or SQLite fallback if DuckDB is not installed.
    """

    def __init__(self, db_path: str | Path, force_sqlite: bool = False):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.use_duckdb = HAS_DUCKDB and not force_sqlite
        self._init_db()

    def _get_connection(self):
        if self.use_duckdb:
            return duckdb.connect(str(self.db_path))
        else:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            return conn

    def _init_db(self):
        conn = self._get_connection()
        try:
            # 1. Raw Content Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS raw_content_items (
                    id VARCHAR PRIMARY KEY,
                    event_id VARCHAR NOT NULL,
                    source_platform VARCHAR NOT NULL,
                    content_type VARCHAR NOT NULL,
                    file_path VARCHAR,
                    source_url VARCHAR,
                    published_at TIMESTAMP,
                    harvested_at TIMESTAMP,
                    title VARCHAR,
                    text_content TEXT,
                    raw_metadata_json TEXT
                );
            """)

            # 2. Verification Audit Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS verification_audits (
                    content_id VARCHAR PRIMARY KEY,
                    is_temporal_valid BOOLEAN,
                    temporal_reason TEXT,
                    reverse_search_hit_prior BOOLEAN,
                    ai_generated_score DOUBLE,
                    forensic_reasoning TEXT,
                    spatial_grounding_valid BOOLEAN,
                    spatial_reason TEXT,
                    status VARCHAR NOT NULL,
                    rejection_reason TEXT,
                    audited_at TIMESTAMP
                );
            """)

            # 3. Seismic Evaluations Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS seismic_evaluations (
                    content_id VARCHAR PRIMARY KEY,
                    event_id VARCHAR NOT NULL,
                    latitude DOUBLE,
                    longitude DOUBLE,
                    location_name VARCHAR,
                    location_precision VARCHAR,
                    building_type VARCHAR,
                    building_materials VARCHAR,
                    damage_description TEXT,
                    auditory_cues TEXT,
                    visual_cues TEXT,
                    mmi_estimation DOUBLE NOT NULL,
                    confidence DOUBLE NOT NULL,
                    rrup_km DOUBLE,
                    physics_consistent BOOLEAN,
                    physics_notes TEXT,
                    evidence_type VARCHAR,
                    reasoning TEXT,
                    file_name VARCHAR,
                    model_name VARCHAR,
                    created_at TIMESTAMP
                );
            """)
            # Migration check: Ensure file_name and model_name columns exist in pre-existing tables
            for col in ["file_name", "model_name"]:
                try:
                    conn.execute(f"ALTER TABLE seismic_evaluations ADD COLUMN {col} VARCHAR;")
                except Exception:
                    pass

            if not self.use_duckdb:
                conn.commit()
        finally:
            conn.close()

    def save_raw_content(self, item: RawContentItem) -> str:
        conn = self._get_connection()
        try:
            query = """
                INSERT OR REPLACE INTO raw_content_items
                (id, event_id, source_platform, content_type, file_path, source_url, published_at, harvested_at, title, text_content, raw_metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            params = (
                item.id,
                item.event_id,
                item.source_platform,
                item.content_type,
                item.file_path,
                item.source_url,
                item.published_at,
                item.harvested_at,
                item.title,
                item.text_content,
                json.dumps(item.raw_metadata)
            )
            conn.execute(query, params)
            if not self.use_duckdb:
                conn.commit()
            return item.id
        finally:
            conn.close()

    def get_raw_content(self, content_id: str) -> Optional[RawContentItem]:
        conn = self._get_connection()
        try:
            cur = conn.execute("SELECT * FROM raw_content_items WHERE id = ?", [content_id])
            row = cur.fetchone()
            if not row:
                return None
            
            d = dict(row) if hasattr(row, "keys") else {
                "id": row[0], "event_id": row[1], "source_platform": row[2], "content_type": row[3],
                "file_path": row[4], "source_url": row[5], "published_at": row[6], "harvested_at": row[7],
                "title": row[8], "text_content": row[9], "raw_metadata_json": row[10]
            }
            return RawContentItem(
                id=d["id"],
                event_id=d["event_id"],
                source_platform=d["source_platform"],
                content_type=d["content_type"],
                file_path=d["file_path"],
                source_url=d["source_url"],
                published_at=d["published_at"],
                harvested_at=d["harvested_at"] or datetime.utcnow(),
                title=d["title"],
                text_content=d["text_content"],
                raw_metadata=json.loads(d["raw_metadata_json"] or "{}")
            )
        finally:
            conn.close()

    def save_verification_audit(self, audit: VerificationAudit) -> None:
        conn = self._get_connection()
        try:
            query = """
                INSERT OR REPLACE INTO verification_audits
                (content_id, is_temporal_valid, temporal_reason, reverse_search_hit_prior, ai_generated_score,
                 forensic_reasoning, spatial_grounding_valid, spatial_reason, status, rejection_reason, audited_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            params = (
                audit.content_id,
                audit.is_temporal_valid,
                audit.temporal_reason,
                audit.reverse_search_hit_prior,
                audit.ai_generated_score,
                audit.forensic_reasoning,
                audit.spatial_grounding_valid,
                audit.spatial_reason,
                audit.status.value,
                audit.rejection_reason,
                audit.audited_at
            )
            conn.execute(query, params)
            if not self.use_duckdb:
                conn.commit()
        finally:
            conn.close()

    def save_seismic_evaluation(self, evaluation: SeismicEvaluation) -> None:
        conn = self._get_connection()
        try:
            query = """
                INSERT OR REPLACE INTO seismic_evaluations
                (content_id, event_id, latitude, longitude, location_name, location_precision,
                 building_type, building_materials, damage_description, auditory_cues, visual_cues,
                 mmi_estimation, confidence, rrup_km, physics_consistent, physics_notes,
                 evidence_type, reasoning, file_name, model_name, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            params = (
                evaluation.content_id,
                evaluation.event_id,
                evaluation.latitude,
                evaluation.longitude,
                evaluation.location_name,
                evaluation.location_precision,
                evaluation.building_type,
                evaluation.building_materials,
                evaluation.damage_description,
                evaluation.auditory_cues,
                evaluation.visual_cues,
                evaluation.mmi_estimation,
                evaluation.confidence,
                evaluation.rrup_km,
                evaluation.physics_consistent,
                evaluation.physics_notes,
                evaluation.evidence_type.value,
                evaluation.reasoning,
                evaluation.file_name,
                evaluation.model_name,
                evaluation.created_at
            )
            try:
                conn.execute(query, params)
            except Exception:
                query_fallback = """
                    INSERT OR REPLACE INTO seismic_evaluations
                    (content_id, event_id, latitude, longitude, location_name, location_precision,
                     building_type, building_materials, damage_description, auditory_cues, visual_cues,
                     mmi_estimation, confidence, rrup_km, physics_consistent, physics_notes,
                     evidence_type, reasoning, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
                conn.execute(query_fallback, params[:18] + (params[-1],))
            if not self.use_duckdb:
                conn.commit()
        finally:
            conn.close()

    def get_verified_evaluations(
        self,
        event_id: str,
        min_confidence: float = 0.5,
        location_filter: Optional[List[str]] = None,
        max_rrup_km: Optional[float] = None
    ) -> List[SeismicEvaluation]:
        conn = self._get_connection()
        try:
            query = """
                SELECT e.*, r.file_path, r.title FROM seismic_evaluations e
                JOIN verification_audits a ON e.content_id = a.content_id
                LEFT JOIN raw_content_items r ON e.content_id = r.id
                WHERE e.event_id = ?
                  AND a.status = 'VERIFIED'
                  AND e.confidence >= ?
            """
            params: List[Any] = [event_id, min_confidence]

            if max_rrup_km is not None:
                query += " AND (e.rrup_km IS NULL OR e.rrup_km <= ?)"
                params.append(max_rrup_km)

            cur = conn.execute(query, params)
            rows = cur.fetchall()
            col_names = [desc[0] for desc in cur.description] if cur.description else []
            results = []
            for row in rows:
                d = dict(zip(col_names, row)) if col_names else (dict(row) if hasattr(row, "keys") else {})
                if not d:
                    d = {
                        "content_id": row[0], "event_id": row[1], "latitude": row[2], "longitude": row[3],
                        "location_name": row[4], "location_precision": row[5], "building_type": row[6],
                        "building_materials": row[7], "damage_description": row[8], "auditory_cues": row[9],
                        "visual_cues": row[10], "mmi_estimation": row[11], "confidence": row[12],
                        "rrup_km": row[13], "physics_consistent": bool(row[14]), "physics_notes": row[15],
                        "evidence_type": row[16], "reasoning": row[17]
                    }
                
                # Check location filter if specified
                if location_filter and d.get("location_name"):
                    if not any(loc.lower() in d["location_name"].lower() for loc in location_filter):
                        continue

                file_name = d.get("file_name")
                if not file_name:
                    if d.get("file_path"):
                        file_name = Path(d["file_path"]).name
                    elif d.get("title"):
                        file_name = d["title"]

                results.append(SeismicEvaluation(
                    content_id=d["content_id"],
                    event_id=d["event_id"],
                    file_name=file_name,
                    model_name=d.get("model_name"),
                    latitude=d["latitude"],
                    longitude=d["longitude"],
                    location_name=d["location_name"],
                    location_precision=d.get("location_precision") or "approximate",
                    building_type=d.get("building_type"),
                    building_materials=d.get("building_materials"),
                    damage_description=d.get("damage_description"),
                    auditory_cues=d.get("auditory_cues"),
                    visual_cues=d.get("visual_cues"),
                    mmi_estimation=float(d["mmi_estimation"]),
                    confidence=float(d["confidence"]),
                    rrup_km=float(d["rrup_km"]) if d.get("rrup_km") is not None else None,
                    physics_consistent=bool(d.get("physics_consistent", True)),
                    physics_notes=d.get("physics_notes"),
                    evidence_type=EvidenceType(d.get("evidence_type") or EvidenceType.STRUCTURAL_DAMAGE.value),
                    reasoning=d.get("reasoning") or "",
                    created_at=d.get("created_at") or datetime.utcnow()
                ))
            return results
        finally:
            conn.close()

    def export_shakemap_features(self, event_id: str, min_confidence: float = 0.4) -> List[Dict[str, Any]]:
        evals = self.get_verified_evaluations(event_id=event_id, min_confidence=min_confidence)
        features = []
        for ev in evals:
            if ev.latitude is not None and ev.longitude is not None:
                features.append(ev.to_shakemap_feature())
        return features

    def close(self) -> None:
        pass
