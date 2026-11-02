from __future__ import annotations
import os
import sys
import json
import base64
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Union

# Auto-discover local venv site-packages if present for matching Python version
current_py_ver = f"python{sys.version_info.major}.{sys.version_info.minor}"
for venv_candidate in [Path("server/.venv"), Path(".venv"), Path("../server/.venv")]:
    if venv_candidate.exists():
        for sp in venv_candidate.glob(f"lib/{current_py_ver}/site-packages"):
            sp_str = str(sp.resolve())
            if sp_str not in sys.path:
                sys.path.append(sp_str)

class GeminiBridge:
    """
    Multimodal caller for Google Gemini API via `from google import genai` or direct REST.
    Uses GEMINI_API_KEY / GOOGLE_API_KEY from environment or .env file.
    Supports both freeform text (initial analysis) and constrained structured JSON (final analysis).
    """

    def __init__(
        self,
        model_name: Optional[str] = None,
        thinking_level: str = "low",
        timeout: float = 30.0,
        fallback_model: str = "gemini-3.6-flash"
    ):
        target = os.getenv("GEMINI_MODEL") or model_name or "gemini-3.8-flash"
        if target in ("gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"):
            target = "gemini-3.8-flash"
        self.model_name = target
        self.thinking_level = os.getenv("GEMINI_THINKING_LEVEL", thinking_level)
        self.timeout = float(os.getenv("GEMINI_TIMEOUT", str(timeout)))
        self.fallback_model = os.getenv("FALLBACK_MODEL", fallback_model)
        self.api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.last_model_used = self.model_name

    def generate_content(
        self,
        prompt: str,
        media_path: Optional[str] = None,
        json_schema: Optional[Dict[str, Any]] = None
    ) -> Union[Dict[str, Any], str]:
        """
        Calls Gemini API with active progress reporting, low thinking overhead, and automatic failover.
        """
        if not self.api_key:
            raise ValueError(
                "❌ GEMINI_API_KEY is not set.\n"
                "To use the Gemini API:\n"
                "1. Get an API key at https://aistudio.google.com/app/apikey\n"
                "2. Add it to your server/.env or .env file:\n"
                "   GEMINI_API_KEY=\"AIzaSy...\"\n"
                "3. Re-run your command."
            )

        models_to_try = [self.model_name]
        for candidate in [self.fallback_model, "gemini-3.6-flash", "gemini-3.5-flash-lite"]:
            if candidate and candidate not in models_to_try:
                models_to_try.append(candidate)

        all_errors = []

        for idx, model in enumerate(models_to_try):
            if idx > 0:
                print(f"\n   🔄 [Model Failover] Upstream spike/limit on previous model. Switching to '{model}'...")

            # Try with media first, then fallback to text-only if media upload stalls
            media_options = [media_path] if media_path else [None]
            if media_path:
                media_options.append(None)  # text-only fallback option

            for m_path in media_options:
                is_media_fallback = (m_path is None and media_path is not None)
                if is_media_fallback:
                    print(f"\n   🔄 [Payload Fallback] PDF upload stalled or overloaded; retrying with text prompt...")

                # Method 1: Official google.genai SDK
                try:
                    res = self._call_google_genai_sdk(prompt, m_path, json_schema, model)
                    self.last_model_used = model
                    return res
                except ImportError as e:
                    all_errors.append(f"google-genai SDK not installed ({e})")
                except Exception as e:
                    err_str = str(e)
                    all_errors.append(f"google-genai ({model}): {err_str}")
                    if "429" in err_str or "503" in err_str or "RESOURCE_EXHAUSTED" in err_str or "UNAVAILABLE" in err_str:
                        print(f"\n   ⚠️ [{model} Overloaded/Rate-Limited: 503/429] Fast-failing over to next model...")
                        break  # immediately skip to next model in models_to_try

                # Method 2: Direct Gemini API REST
                try:
                    res = self._call_ai_studio_rest(prompt, m_path, json_schema, model)
                    self.last_model_used = model
                    return res
                except Exception as e:
                    err_str = str(e)
                    all_errors.append(f"Gemini REST ({model}): {err_str}")
                    if "429" in err_str or "503" in err_str or "RESOURCE_EXHAUSTED" in err_str or "UNAVAILABLE" in err_str or "timed out" in err_str:
                        print(f"\n   ⚠️ [{model} Overloaded/Rate-Limited] Fast-failing over to next model...")
                        break  # immediately skip to next model in models_to_try

        # If all attempts fail, raise actionable message
        raise RuntimeError(
            f"❌ Gemini API call failed for models {models_to_try}.\n"
            f"Errors encountered:\n  " + "\n  ".join(all_errors[-4:]) + "\n"
            f"Tips:\n"
            f"  - Check your rate limits at https://aistudio.google.com\n"
            f"  - Try running with a lighter model: --model gemini-3.5-flash-lite\n"
            f"  - Ensure your network has access to generativelanguage.googleapis.com"
        )

    def _call_google_genai_sdk(
        self,
        prompt: str,
        media_path: Optional[str],
        json_schema: Optional[Dict[str, Any]],
        model: str
    ) -> Union[Dict[str, Any], str]:
        from google import genai
        from google.genai import types
        import time

        client = genai.Client(
            api_key=self.api_key,
            http_options={"timeout": int(self.timeout * 1000)}
        )
        contents = []

        if media_path and Path(media_path).exists():
            data = Path(media_path).read_bytes()
            mime_type = self._detect_mime(media_path)
            contents.append(types.Part.from_bytes(data=data, mime_type=mime_type))

        full_prompt = prompt
        if json_schema:
            full_prompt += f"\n\nRespond ONLY with a valid JSON object matching this schema:\n{json.dumps(json_schema, indent=2)}"

        contents.append(full_prompt)

        config_kwargs: Dict[str, Any] = {"temperature": 0.2}
        if json_schema:
            config_kwargs["response_mime_type"] = "application/json"

        try:
            config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_level=self.thinking_level)
        except Exception:
            pass

        config = types.GenerateContentConfig(**config_kwargs)

        print(f"   ⏳ [Gemini SDK] Calling {model} (thinking: {self.thinking_level}, timeout: {self.timeout:.0f}s)...", end="", flush=True)
        t0 = time.time()
        resp = client.models.generate_content(model=model, contents=contents, config=config)
        elapsed = time.time() - t0
        print(f" ✅ done ({elapsed:.1f}s)", flush=True)

        if json_schema:
            return self._clean_and_parse_json(resp.text)
        return resp.text.strip()

    def _call_ai_studio_rest(
        self,
        prompt: str,
        media_path: Optional[str],
        json_schema: Optional[Dict[str, Any]],
        model: str
    ) -> Union[Dict[str, Any], str]:
        import urllib.request
        import urllib.error
        import time

        parts = []
        if media_path and Path(media_path).exists():
            b64_data = base64.b64encode(Path(media_path).read_bytes()).decode("utf-8")
            mime_type = self._detect_mime(media_path)
            parts.append({"inlineData": {"mimeType": mime_type, "data": b64_data}})

        full_prompt = prompt
        if json_schema:
            full_prompt += f"\n\nRespond ONLY with a valid JSON object matching this schema:\n{json.dumps(json_schema, indent=2)}"
        parts.append({"text": full_prompt})

        gen_config: Dict[str, Any] = {
            "temperature": 0.2,
            "thinkingConfig": {"thinkingLevel": self.thinking_level}
        }
        if json_schema:
            gen_config["responseMimeType"] = "application/json"

        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": gen_config
        }

        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.api_key}"
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=data_bytes,
            headers={"Content-Type": "application/json"}
        )

        print(f"   ⏳ [Gemini REST] Calling {model} (payload: {len(data_bytes)//1024} KB, timeout: {self.timeout:.0f}s)...", end="", flush=True)
        t0 = time.time()

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            print(f" ❌ HTTP {e.code}", flush=True)
            raise RuntimeError(f"HTTP {e.code} from Gemini API: {err_body}")
        except Exception as e:
            print(f" ❌ timeout/error ({e})", flush=True)
            raise e

        elapsed = time.time() - t0
        print(f" ✅ done ({elapsed:.1f}s)", flush=True)

        candidates = data.get("candidates", [])
        if not candidates:
            raise RuntimeError(f"No candidates returned from Gemini API: {data}")

        raw_text = candidates[0]["content"]["parts"][0]["text"]
        if json_schema:
            return self._clean_and_parse_json(raw_text)
        return raw_text.strip()

    def _detect_mime(self, path: str) -> str:
        ext = Path(path).suffix.lower()
        if ext in (".jpg", ".jpeg"):
            return "image/jpeg"
        elif ext == ".png":
            return "image/png"
        elif ext == ".webp":
            return "image/webp"
        elif ext == ".pdf":
            return "application/pdf"
        elif ext in (".mp4", ".mov"):
            return "video/mp4"
        return "application/octet-stream"

    def _clean_and_parse_json(self, text: str) -> Dict[str, Any]:
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            import re
            m = re.search(r'\{.*\}', text, re.DOTALL)
            if m:
                return json.loads(m.group(0))
            raise ValueError(f"Could not parse valid JSON from Gemini response: {text[:200]}...")
