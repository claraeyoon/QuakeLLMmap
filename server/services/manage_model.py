import vertexai
import os
from dotenv import load_dotenv
from vertexai.generative_models import GenerativeModel, Part, SafetySetting, HarmBlockThreshold, HarmCategory, GenerationConfig
from google.auth.transport.requests import Request
from google.oauth2.service_account import Credentials
from functools import lru_cache

geminiConfig= GenerationConfig(
        temperature=0.4,
        top_p=0.95,
        top_k=20,
        candidate_count=1,
        seed=5,
        max_output_tokens=8100,
        stop_sequences=["STOP!"],
        presence_penalty=0.0,
        frequency_penalty=0.0,
        response_logprobs=False,  # Set to True to get logprobs, Note this can only be run once per day
        response_mime_type="application/json"
    )

sf_settings = [
    SafetySetting(
        category=HarmCategory.HARM_CATEGORY_HARASSMENT,
        threshold=HarmBlockThreshold.BLOCK_NONE,
    ),
    SafetySetting(
        category=HarmCategory.HARM_CATEGORY_HATE_SPEECH,
        threshold=HarmBlockThreshold.BLOCK_NONE,
    ),
    SafetySetting(
        category=HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
        threshold=HarmBlockThreshold.BLOCK_NONE,
    ),
    SafetySetting(
        category=HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
        threshold=HarmBlockThreshold.BLOCK_NONE,
    )
]

geminiTextConfig = GenerationConfig(
    temperature=0.4,
    top_p=0.95,
    top_k=20,
    candidate_count=1,
    seed=5,
    max_output_tokens=8100,
    stop_sequences=["STOP!"],
    presence_penalty=0.0,
    frequency_penalty=0.0,
    response_logprobs=False,
)

import time
from google.api_core.exceptions import ResourceExhausted, TooManyRequests

@lru_cache
def get_model(model_name: str = None):
    if not model_name:
        model_name = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    return GenerativeModel(model_name)

def get_response(contents: list, json_mode: bool = True, max_retries: int = 5):
    config = geminiConfig if json_mode else geminiTextConfig
    preferred_model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    current_model_name = preferred_model
    
    backoff = 4.0
    for attempt in range(max_retries + 1):
        try:
            model = get_model(current_model_name)
            response = model.generate_content(
                generation_config=config, 
                safety_settings=sf_settings, 
                contents=contents,    
                stream=False
            )
            return response.text
        except Exception as e:
            err_str = str(e).lower()
            is_rate_limit = (
                "resource_exhausted" in err_str or 
                "429" in err_str or 
                "resource exhausted" in err_str or 
                "quota" in err_str or
                isinstance(e, (ResourceExhausted, TooManyRequests))
            )
            if is_rate_limit:
                if attempt < max_retries:
                    print(f"⚠️ Vertex AI rate limit hit ({e}). Waiting {backoff:.1f}s before retry ({attempt+1}/{max_retries})...")
                    time.sleep(backoff)
                    backoff *= 2.0
                    # If gemini-2.5-flash keeps hitting limits, try gemini-2.0-flash
                    if attempt >= 2 and current_model_name == "gemini-2.5-flash":
                        print("Switching temporarily to gemini-2.0-flash to bypass model quota...")
                        current_model_name = "gemini-2.0-flash"
                else:
                    raise e
            else:
                raise e
