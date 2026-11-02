from __future__ import annotations
import os
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

from quake_agent.config import EventConfig, FilterConfig, Settings
from quake_agent.core.models import (
    RawContentItem,
    VerificationAudit,
    VerificationStatus,
    SeismicEvaluation,
)
from quake_agent.storage.repository import ContentRepository
from quake_agent.storage.duckdb_repo import LocalStorageRepository
from quake_agent.harvesters.dispatcher import IngestionDispatcher
from quake_agent.harvesters.local_watcher import LocalFileWatcher
from quake_agent.harvesters.web_searcher import WebHarvester
from quake_agent.gates.temporal_gate import TemporalGate
from quake_agent.gates.spatial_gate import SpatialGate
from quake_agent.gates.recycled_gate import RecycledMediaGate
from quake_agent.gates.authenticity_gate import AuthenticityGate
from quake_agent.seismology.mmi_assessor import MMIAssessor
from quake_agent.seismology.physics_critic import PhysicsCritic
from quake_agent.shakemap.exporter import ShakeMapExporter
from quake_agent.shakemap.comparator import ShakeMapComparator

class QuakeAgentOrchestrator:
    """
    Main Agentic Workflow Orchestrator.
    Executes the end-to-end pipeline:
    Harvester -> Pre-Filter -> 4 Verification Gates -> MMI Assessment -> Physics Critic -> DuckDB -> ShakeMap Export.
    """

    def __init__(
        self,
        event_config: EventConfig,
        filter_config: Optional[FilterConfig] = None,
        settings: Optional[Settings] = None,
        repository: Optional[ContentRepository] = None
    ):
        self.event = event_config
        self.filter = filter_config or FilterConfig()
        self.settings = settings or Settings()

        # Database path: data/events/<event_id>/event.duckdb (or .sqlite)
        event_dir = self.settings.data_dir / "events" / self.event.event_id
        event_dir.mkdir(parents=True, exist_ok=True)
        db_path = event_dir / "event.duckdb"

        self.repo = repository or LocalStorageRepository(db_path=db_path)

        # Initialize sub-agents and gates
        self.dispatcher = IngestionDispatcher(self.filter)
        self.temporal_gate = TemporalGate(self.event)
        self.spatial_gate = SpatialGate(self.event)
        self.recycled_gate = RecycledMediaGate()
        self.authenticity_gate = AuthenticityGate(self.settings)

        self.mmi_assessor = MMIAssessor(self.event, self.settings)
        self.physics_critic = PhysicsCritic(
            fault_trace_path=self.event.fault_trace_file,
            attenuation_curves_path=self.event.attenuation_curve_file
        )

        self.shakemap_exporter = ShakeMapExporter(self.repo)
        self.shakemap_comparator = ShakeMapComparator(output_dir=event_dir / "shakemap")

    def run_on_single_file(self, file_path: str | Path) -> Dict[str, Any]:
        """Processes a single specific local file (PDF, image, or video)."""
        p = Path(file_path).resolve()
        if not p.exists():
            raise FileNotFoundError(f"File not found: {p}")

        ext = p.suffix.lower()
        content_type = "image"
        if ext == ".pdf":
            content_type = "pdf"
        elif ext in {".mp4", ".mov"}:
            content_type = "video"
        elif ext == ".txt":
            content_type = "text"

        text_content = ""
        if content_type == "pdf":
            from quake_agent.harvesters.pdf_extractor import PDFExtractor
            extractor = PDFExtractor()
            text_content = extractor.extract_text(p)
        elif content_type == "text":
            text_content = p.read_text(encoding="utf-8", errors="ignore")

        # Check for accompanying sidecar text/metadata file (e.g., photo.jpg + photo.txt)
        if not text_content:
            sidecar_txt = p.with_suffix(".txt")
            sidecar_json = p.with_suffix(".json")
            if sidecar_txt.exists():
                text_content = sidecar_txt.read_text(encoding="utf-8", errors="ignore")
            elif sidecar_json.exists():
                text_content = sidecar_json.read_text(encoding="utf-8", errors="ignore")

        from datetime import datetime
        file_mtime = datetime.utcfromtimestamp(p.stat().st_mtime)

        item = RawContentItem(
            event_id=self.event.event_id,
            source_platform="local",
            content_type=content_type,
            file_path=str(p),
            source_url=None,
            published_at=file_mtime,
            harvested_at=datetime.utcnow(),
            title=p.name,
            text_content=text_content or None,
            raw_metadata={"file_size": p.stat().st_size, "extension": ext}
        )

        print(f"\n📂 [Ingestion] Processing single target file: '{p.name}' ({content_type})")
        return self.process_items([item])

    def run_on_inbound_directory(self, inbound_dir: Optional[str | Path] = None) -> Dict[str, Any]:
        """Scans local folder, filters, audits, assesses, and records all items."""
        in_dir = Path(inbound_dir or (self.settings.data_dir / "events" / self.event.event_id / "inbound"))
        watcher = LocalFileWatcher(inbound_dir=in_dir, event_id=self.event.event_id)
        raw_items = watcher.scan()

        print(f"\n📂 [Ingestion] Discovered {len(raw_items)} local files in '{in_dir}'")
        return self.process_items(raw_items)

    def run_web_harvest(self, limit_per_source: int = 5) -> Dict[str, Any]:
        """Harvests Reddit and Web for event-grounded media and reports."""
        harvester = WebHarvester(self.event, self.settings)
        queries = harvester.generate_search_queries()

        all_items: List[RawContentItem] = []
        print(f"\n🌐 [Web Harvester] Running queries for {self.event.name}...")

        for q in queries[:3]:
            # Search web
            web_results = harvester.search_web_tavily(q, max_results=limit_per_source)
            all_items.extend(web_results)
            # Search reddit
            reddit_results = harvester.search_reddit_public(q, limit=limit_per_source)
            all_items.extend(reddit_results)

        print(f"   Harvested {len(all_items)} candidate posts/media from web.")
        return self.process_items(all_items)

    def process_items(self, items: List[RawContentItem]) -> Dict[str, Any]:
        processed_count = 0
        filtered_out_count = 0
        rejected_count = 0
        verified_evaluations: List[SeismicEvaluation] = []

        for item in items:
            # Step 1: Pre-Ingestion Filter
            passes_filter, filter_reason = self.dispatcher.should_process(item)
            if not passes_filter:
                filtered_out_count += 1
                continue

            # Persist raw item
            self.repo.save_raw_content(item)

            # Step 2: Gate 1 - Temporal Check
            is_temp_valid, temp_reason, resolved_dt = self.temporal_gate.check(item)
            if resolved_dt:
                item.published_at = resolved_dt

            # Step 3: Gate 2 - Recycled Media Check
            is_unique, recycled_reason, _ = self.recycled_gate.check(item.file_path)

            # Step 4: Gate 3 - Authenticity & AI-Slip Check
            ai_score, forensic_reason, is_authentic = self.authenticity_gate.inspect_authenticity(item)

            # Overall Verification Decision
            status = VerificationStatus.VERIFIED
            rejection_reasons = []

            if not is_temp_valid:
                status = VerificationStatus.REJECTED
                rejection_reasons.append(temp_reason)

            if not is_unique:
                status = VerificationStatus.REJECTED
                rejection_reasons.append(recycled_reason)

            if not is_authentic:
                status = VerificationStatus.REJECTED
                rejection_reasons.append(f"AI-Generated synthetic media detected: {forensic_reason}")

            audit = VerificationAudit(
                content_id=item.id,
                is_temporal_valid=is_temp_valid,
                temporal_reason=temp_reason,
                reverse_search_hit_prior=not is_unique,
                ai_generated_score=ai_score,
                forensic_reasoning=forensic_reason,
                status=status,
                rejection_reason="; ".join(rejection_reasons) if rejection_reasons else None
            )
            self.repo.save_verification_audit(audit)

            if status == VerificationStatus.REJECTED:
                rejected_count += 1
                print(f"🚫 [Gate Rejected] {item.title or item.id[:8]}: {audit.rejection_reason}")
                continue

            # Step 5: Seismologist MMI Assessment Agent
            print(f"🔬 [Analyzing] Assessing MMI for {item.title or item.id[:8]}...")
            try:
                evaluation = self.mmi_assessor.assess(item)
            except Exception as e:
                print(f"\n❌ [Assessment Failed] Gemini API evaluation failed for '{item.title or item.id[:8]}':\n{e}\n")
                continue
            # Step 5b: Damage Relevance Gate - Screen out files without relevant damage photos
            if not evaluation.has_damage_photos or evaluation.mmi_estimation < 1.0:
                print(f"ℹ️ [No Damage Photos] {item.title or item.id[:8]}: Screened out (slide/file lacks observable earthquake damage photos)")
                self.repo.save_seismic_evaluation(evaluation)
                continue

            # Step 6: Gate 4 - Spatial Grounding Check
            is_spatial_valid, spatial_reason = self.spatial_gate.check_coordinates(evaluation.latitude, evaluation.longitude)
            if not is_spatial_valid:
                evaluation.confidence = max(0.2, evaluation.confidence - 0.4)
                evaluation.reasoning += f" [Warning: {spatial_reason}]"

            # Step 7: Physics Critic ($R_{rup}$ & Attenuation Check)
            if evaluation.latitude and evaluation.longitude:
                is_consistent, rrup_km, phys_notes = self.physics_critic.evaluate_consistency(
                    mmi=evaluation.mmi_estimation,
                    lat=evaluation.latitude,
                    lon=evaluation.longitude
                )
                evaluation.rrup_km = rrup_km
                evaluation.physics_consistent = is_consistent
                evaluation.physics_notes = phys_notes
                if not is_consistent:
                    evaluation.confidence = max(0.3, evaluation.confidence - 0.3)
                    evaluation.reasoning += f" [Physics Critic: {phys_notes}]"

            # Persist Evaluation
            self.repo.save_seismic_evaluation(evaluation)
            verified_evaluations.append(evaluation)
            processed_count += 1
            print(f"✅ [Verified] {evaluation.location_name or 'Site'} -> MMI {evaluation.mmi_estimation:.1f} (conf: {evaluation.confidence:.2f}, Rrup: {evaluation.rrup_km or 0:.1f} km)")

        # Step 8: Export observations to official USGS ShakeMap format
        event_dir = self.settings.data_dir / "events" / self.event.event_id
        shakemap_out = event_dir / "agent_mmi_dat.json"
        self.shakemap_exporter.export_dat_json(self.event.event_id, shakemap_out)

        # Step 8b: Export detailed JSON evaluations (including file_name and model_name for each entry)
        evals_out = event_dir / "agent_evaluations.json"
        eval_records = [ev.to_dict() for ev in verified_evaluations]
        with open(evals_out, "w", encoding="utf-8") as f:
            json.dump(eval_records, f, indent=2)

        # Step 9: Residual comparison against official stations
        residuals = self.shakemap_comparator.compute_residuals(
            agent_evaluations=verified_evaluations,
            official_stations_path=self.event.stationlist_file
        )

        res_dict = {
            "event_id": self.event.event_id,
            "total_items": len(items),
            "processed_and_verified": processed_count,
            "filtered_out": filtered_out_count,
            "gate_rejected": rejected_count,
            "shakemap_export_file": str(shakemap_out),
            "evaluations_json_file": str(evals_out),
            "residual_summary": residuals
        }

        if verified_evaluations:
            last = verified_evaluations[-1]
            res_dict["initial_analysis"] = last.initial_analysis
            res_dict["final_analysis"] = last.final_analysis
            res_dict["generation"] = last.generation_report

        return res_dict
