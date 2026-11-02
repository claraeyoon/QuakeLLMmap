from __future__ import annotations
import os
import json
from pathlib import Path
from typing import Tuple, Dict, Any, Optional

from quake_agent.config import Settings
from quake_agent.core.models import RawContentItem
from quake_agent.seismology.gemini_bridge import GeminiBridge

AUTHENTICITY_SCHEMA = {
    "type": "object",
    "properties": {
        "ai_generated_score": {"type": "number"},
        "is_authentic": {"type": "boolean"},
        "forensic_reasoning": {"type": "string"}
    },
    "required": ["ai_generated_score", "is_authentic", "forensic_reasoning"]
}

class AuthenticityGate:
    """
    Gate 4: AI-Slip & Deepfake Forensic Inspection.
    Evaluates whether an image or video is synthetic (Midjourney/Flux/DALL-E)
    or an authentic camera capture of real earthquake damage.
    """

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or Settings()
        model_name = self.settings.fast_triage_model or "gemini-2.5-flash"
        self.bridge = GeminiBridge(model_name=model_name)

    def inspect_authenticity(self, item: RawContentItem) -> Tuple[float, str, bool]:
        if not item.file_path or not Path(item.file_path).exists():
            return 0.1, "No local file to perform pixel forensics; assumed authentic", True

        ext = Path(item.file_path).suffix.lower()
        if ext not in {".jpg", ".jpeg", ".png", ".webp", ".mp4"}:
            return 0.0, "Non-visual format; skipping visual forensics", True

        forensic_prompt = """
        You are a digital forensic analyst specialized in verifying earthquake disaster media.
        Carefully examine this image/media for signs of AI-generation or synthetic manipulation (e.g., Midjourney, Flux, Stable Diffusion, or CGI).
        
        Check for:
        1. Warped, illegible, or pseudo-gibberish text on store signs, street signs, and license plates.
        2. Architectural impossibilities (columns merging nonsensically, floating concrete, perfectly smooth unnatural rubble).
        3. Diffusion smoothing on human faces, debris textures, and impossible light/shadow consistency.
        4. Physically authentic structural failure: Does concrete spalling, unreinforced masonry failure, and rebar bending follow real physics?
        """

        try:
            data = self.bridge.generate_content(
                prompt=forensic_prompt,
                media_path=item.file_path,
                json_schema=AUTHENTICITY_SCHEMA
            )
            ai_score = float(data.get("ai_generated_score", 0.0))
            is_authentic = bool(data.get("is_authentic", True))
            reasoning = data.get("forensic_reasoning", "Forensic inspection complete")
            is_valid = is_authentic and (ai_score < 0.70)
            return ai_score, reasoning, is_valid
        except Exception as e:
            # If bridge fails, allow through with note
            return 0.15, f"Forensic check skipped ({str(e)[:80]}); defaulting to authentic", True
