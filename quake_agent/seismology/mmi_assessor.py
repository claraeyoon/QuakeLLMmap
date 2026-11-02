from __future__ import annotations
import os
import json
from pathlib import Path
from typing import Dict, Any, Optional, List

from quake_agent.config import Settings, EventConfig
from quake_agent.core.models import RawContentItem, SeismicEvaluation, EvidenceType
from quake_agent.seismology.pinecone_retriever import PineconeMMIRetriever
from quake_agent.seismology.gemini_bridge import GeminiBridge

SEISMIC_ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "blob_name": {"type": "string"},
        "description": {"type": "string"},
        "location": {
            "type": "object",
            "properties": {
                "address": {"type": "string"},
                "coordinates": {"type": "array", "items": {"type": "number"}}
            }
        },
        "auditory_cues": {"type": "string"},
        "background_noise": {"type": "string"},
        "sounds_of_distress": {"type": "string"},
        "visual_observation": {"type": "string"},
        "video_evidence": {"type": "string"},
        "building_type": {"type": "string"},
        "building_materials": {"type": "string"},
        "evidence_analysis": {"type": "string"},
        "has_damage_photos": {"type": "boolean"},
        "mmi_estimation": {"type": "number"},
        "reasoning": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0}
    },
    "required": ["blob_name", "description", "location", "has_damage_photos", "mmi_estimation", "reasoning", "confidence"]
}

from quake_agent.seismology.geolocation_resolver import GeolocationResolver

DESCRIPTION_PROMPT = """
<System Prompt>
You are an expert seismologist, studying earthquake impact using the Modified Mercalli Intensity Scale (MMI). 
Your task is to carefully analyze image or video evidence to identify visual and auditory indicators of seismic shaking.
Avoid making assumptions or what is not visible or audible in the media. 
Carefully analyze and describe the contents of the image or video in detail.
</System Prompt>

For images:
    - Look for visible surface damage, collapsed buildings, cracks, dust clouds, displaced infrastructure.
    - If it's a satellite or aerial view, analyze top-down damage: roof collapses, ruptured roads, debris zones, or displaced land features.
For videos:
    - Detect dynamic events such as shaking lights, falling debris, swaying structures, ground rupture, or displacement.
    - Audio may be absent but it does not mean there is no earthquake.
    - If audio is present, analyze for screams, panic, structural sounds (crashing, creaking), or silence after impact.

CRITICAL GEOLOCATION EXTRACTION:
    - Inspect the file (text, annotations, title, headers, or captions) for any section labeled "Geolocation (Address/Coordinates)".
    - Look for any latitude/longitude coordinates (DMS: e.g. 21°52'49.27"N, 95°59'5.57"E or decimal: e.g. 21.880353, 95.984881) or links to a location on a map (e.g. Google Maps or OpenStreetMap).
    - If any geolocation or map link is provided, you MUST extract and record it prominently.
"""

class MMIAssessor:
    """
    Multimodal Seismologist Agent.
    Implements the exact two-stage CRAG pipeline from the original code:
    Stage 1: Initial visual/auditory analysis via Gemini.
    Stage 2: RAG retrieval from Pinecone / MMI knowledge base using initial analysis as context.
    Stage 3: Final analysis combining initial analysis + RAG references into 'final_analysis'.
    """

    def __init__(self, event_config: EventConfig, settings: Optional[Settings] = None):
        self.event = event_config
        self.settings = settings or Settings()
        self.retriever = PineconeMMIRetriever()
        model_name = self.settings.deep_reasoning_model or os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
        self.bridge = GeminiBridge(
            model_name=model_name,
            thinking_level=getattr(self.settings, "thinking_level", "low"),
            timeout=getattr(self.settings, "timeout_seconds", 30.0),
            fallback_model=getattr(self.settings, "fallback_model", "gemini-3.6-flash")
        )

    def assess(self, item: RawContentItem) -> SeismicEvaluation:
        blob_name = item.title or (Path(item.file_path).name if item.file_path else item.id[:8])

        # ── Step 1: Initial Analysis from Gemini (First-Pass Media Inspection) ──
        print(f"\n🚀 [Step 1] Running Initial Gemini Media Analysis for '{blob_name}'...")
        prompt_stage1 = DESCRIPTION_PROMPT
        if item.text_content:
            prompt_stage1 += f"\n\nAccompanying Text Report / Caption:\n{item.text_content}"

        initial_analysis_text = self.bridge.generate_content(
            prompt=prompt_stage1,
            media_path=item.file_path,
            json_schema=None  # Freeform detailed text description
        )
        if isinstance(initial_analysis_text, dict):
            initial_analysis_text = json.dumps(initial_analysis_text)

        print("\n" + "-"*50)
        print("🔍 Initial Analysis Result:")
        print("-"*50)
        print(initial_analysis_text)
        print("-"*50)

        # ── Step 2: RAG Retrieval from Pinecone using initial analysis as context ──
        print(f"\n🚀 [Step 2] Retrieving MMI scale definitions from Pinecone for '{blob_name}'...")
        retrieved_docs = self.retriever.retrieve_documents(initial_analysis_text, top_k=4)
        doc_context = "\n\n".join([f"- {d}" for d in retrieved_docs])
        print(f"   Retrieved {len(retrieved_docs)} MMI reference definitions.")

        # ── Step 3: Final Analysis (Combining Initial Analysis + RAG References) ──
        print(f"\n🚀 [Step 3] Generating 'final_analysis' structured report...")
        final_prompt = f"""
        You are an expert seismologist providing MMI assessment.
        Using the initial analysis and retrieved seismic reference documents, provide a complete assessment
        including MMI estimation with reasoning and confidence score.

        Initial Analysis:
        {initial_analysis_text}

        Reference Documents (from MMI Knowledge Base / Pinecone):
        {doc_context}

        Provide complete seismic analysis for {blob_name} including:
        - Detailed description of damages and observations
        - Location: If the input document/media contains "Geolocation (Address/Coordinates)", latitude/longitude coordinates (DMS or decimal), or a map link (Google Maps, OpenStreetMap, etc.), you MUST extract and resolve them into [latitude, longitude] in decimal degrees, and set the address to the place name. Only fall back to [0, 0] or hypocenter if no geolocation information or map link is provided in the input.
        - Relevant damage photos (has_damage_photos): Set to True if the file contains actual photographs/visuals of earthquake damage, ground failure, or structural shaking. Set to False if the file is only a title slide, author credits, overview text, or template without damage photos.
        - Auditory and visual evidence summary
        - Building type and materials assessment
        - Evidence analysis: detailed breakdown of structural failure vs ground motion
        - Context summary: concise summary of the initial analysis
        - MMI estimation (as float: 1.0 to 12.0; use 0.0 if has_damage_photos is false) with detailed reasoning
        - Confidence score (0.0 to 1.0)
        """

        raw_final = self.bridge.generate_content(
            prompt=final_prompt,
            media_path=None,  # Step 3 uses initial_analysis + RAG text; avoids redundant PDF re-upload
            json_schema=SEISMIC_ANALYSIS_SCHEMA
        )

        final_analysis = raw_final if isinstance(raw_final, dict) else json.loads(raw_final)
        
        file_name = Path(item.file_path).name if item.file_path else (item.title or blob_name)
        model_name = getattr(self.bridge, "last_model_used", None) or self.bridge.model_name

        final_analysis["file_name"] = file_name
        final_analysis["model_name"] = model_name
        final_analysis["blob_name"] = final_analysis.get("blob_name") or blob_name
        final_analysis["initial_analysis"] = initial_analysis_text
        final_analysis["mmi_documents"] = retrieved_docs

        # ── Resolve Geolocation with high priority for provided coordinates/map links ──
        geo_res = GeolocationResolver.resolve(
            text=item.text_content,
            file_path=item.file_path,
            gemini_location=final_analysis.get("location")
        )

        loc_name = None
        if geo_res.is_valid:
            lat = geo_res.latitude
            lon = geo_res.longitude
            loc_name = geo_res.address
            loc_precision = "exact"
            print(f"📍 [Geolocation Resolved] ({lat:.6f}, {lon:.6f}) via {geo_res.source} for '{loc_name or blob_name}'")
        else:
            lat = self.event.hypocenter.get("latitude")
            lon = self.event.hypocenter.get("longitude")
            loc_name = self.event.townships[0] if self.event.townships else "Epicentral Area"
            loc_precision = "hypocenter_fallback"
            print(f"ℹ️ [Geolocation Fallback] No coordinates or map link found in input; defaulting to hypocenter ({lat}, {lon})")

        # Update final_analysis dictionary so the output json records the resolved coordinates
        if "location" not in final_analysis or not isinstance(final_analysis["location"], dict):
            final_analysis["location"] = {}
        final_analysis["location"]["address"] = loc_name
        final_analysis["location"]["coordinates"] = [lat, lon]

        has_damage = bool(final_analysis.get("has_damage_photos", True))
        mmi = float(final_analysis.get("mmi_estimation", 6.0))
        if not has_damage or mmi <= 0.0:
            has_damage = False
            mmi = 0.0

        conf = float(final_analysis.get("confidence", 0.8))
        reasoning = final_analysis.get("reasoning", "")
        desc = final_analysis.get("description", "")
        bldg_type = final_analysis.get("building_type", "")
        ev_analysis = final_analysis.get("evidence_analysis", "")

        # Exact generation format matching original crag.py
        generation = f"""
EARTHQUAKE ASSESSMENT REPORT
============================
File: {file_name}
Model: {model_name}
MMI Estimation: {mmi if has_damage else 'N/A (No Damage Photos)'}
Confidence: {conf}
Has Damage Photos: {has_damage}

Description: {desc}
Location: {loc_name} ({[lat, lon] if lat and lon else 'Unknown'})
Building Type: {bldg_type}
Evidence Analysis: {ev_analysis}
Reasoning: {reasoning}
"""

        # Save to sample_test.txt exactly as original crag.py
        try:
            with open("sample_test.txt", "w", encoding="utf-8") as f:
                f.write(generation.strip())
        except Exception:
            pass

        return SeismicEvaluation(
            content_id=item.id,
            event_id=self.event.event_id,
            file_name=file_name,
            model_name=model_name,
            latitude=lat,
            longitude=lon,
            location_name=loc_name,
            location_precision=loc_precision,
            building_type=bldg_type,
            building_materials=final_analysis.get("building_materials"),
            damage_description=desc,
            evidence_analysis=ev_analysis,
            auditory_cues=final_analysis.get("auditory_cues"),
            visual_cues=final_analysis.get("visual_observation"),
            mmi_estimation=mmi,
            confidence=conf,
            reasoning=reasoning,
            has_damage_photos=has_damage,
            initial_analysis=initial_analysis_text,
            final_analysis=final_analysis,
            generation_report=generation.strip()
        )
