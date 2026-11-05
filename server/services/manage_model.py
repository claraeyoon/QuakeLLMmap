import vertexai
import os
import time
from dotenv import load_dotenv
from vertexai.generative_models import GenerativeModel, Part, SafetySetting, HarmBlockThreshold, HarmCategory, GenerationConfig
from google.auth.transport.requests import Request
from google.oauth2.service_account import Credentials
from functools import lru_cache
from google.api_core.exceptions import ResourceExhausted, TooManyRequests

load_dotenv()

projectID = os.environ.get('projectID') or os.environ.get('GCS_PROJECT_ID')

def init_vertexai(project: str = None, location: str = None, credentials = None) -> bool:
    """
    Initializes Vertex AI with support for multi-region ('us', 'eu') and 'global' locations.
    Automatically patches legacy google-cloud-aiplatform SDKs that restrict locations to a single-region frozenset.
    """
    try:
        import google.cloud.aiplatform.constants.base as aiplatform_constants
        import google.cloud.aiplatform.utils as aiplatform_utils

        # 1. Monkey-patch SUPPORTED_REGIONS and validate_region to allow 'global', 'us', and 'eu'
        if hasattr(aiplatform_constants, "SUPPORTED_REGIONS"):
            aiplatform_constants.SUPPORTED_REGIONS = frozenset(
                set(aiplatform_constants.SUPPORTED_REGIONS) | {"global", "us", "eu"}
            )
        orig_validate = aiplatform_utils.validate_region
        def safe_validate_region(region: str) -> bool:
            if region and str(region).lower() in ("global", "us", "eu"):
                return True
            return orig_validate(region)
        aiplatform_utils.validate_region = safe_validate_region
    except Exception as patch_err:
        print(f"Notice: aiplatform region patch skipped: {patch_err}")

    if not project:
        project = os.environ.get("projectID") or os.environ.get("GCS_PROJECT_ID")
    if not credentials:
        try:
            from services.utilities import load_credentials
            credentials = load_credentials()
        except Exception:
            pass

    model_name = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
    if not location:
        location = (
            os.environ.get("VERTEX_LOCATION")
            or ("global" if "3.8" in model_name else os.environ.get("GCS_REGION", "us-central1"))
        )

    loc_lower = str(location).lower()
    api_endpoint = None
    if loc_lower == "global":
        api_endpoint = "aiplatform.googleapis.com"
    elif loc_lower == "us":
        api_endpoint = "aiplatform.us.rep.googleapis.com"
    elif loc_lower == "eu":
        api_endpoint = "aiplatform.eu.rep.googleapis.com"
    elif loc_lower:
        api_endpoint = f"{loc_lower}-aiplatform.googleapis.com"

    try:
        vertexai.init(
            project=project,
            location=location,
            api_endpoint=api_endpoint,
            credentials=credentials
        )
        return True
    except Exception as e:
        print(f"Notice: vertexai.init error for location '{location}': {e}")
        return False

# Initialize on module load
try:
    init_vertexai()
except Exception:
    pass

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

def ensure_vertexai_initialized(model_name: str = None):
    try:
        import google.cloud.aiplatform.initializer as aiplatform_initializer
        curr_loc = getattr(aiplatform_initializer.global_config, "location", None)
        
        # If using gemini-3.8-flash, location must be 'global' or 'us'
        if model_name and "3.8" in model_name:
            desired_loc = (
                os.environ.get("VERTEX_LOCATION")
                or "global"
            )
            if curr_loc not in ("global", "us") or (desired_loc in ("global", "us") and curr_loc != desired_loc):
                init_vertexai(location=desired_loc)
        elif not curr_loc:
            init_vertexai()
    except Exception as e:
        print(f"Notice: ensure_vertexai_initialized skipped: {e}")

@lru_cache
def get_model(model_name: str = None):
    if not model_name:
        model_name = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
    ensure_vertexai_initialized(model_name)
    return GenerativeModel(model_name)

def get_response(contents: list, json_mode: bool = True, max_retries: int = 5):
    config = geminiConfig if json_mode else geminiTextConfig
    preferred_model = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
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

            # Auto-recovery: If gemini-3.8-flash failed because of region endpoint or model availability
            if ("not found" in err_str or "not available" in err_str or "404" in err_str) and "3.8" in current_model_name:
                import google.cloud.aiplatform.initializer as aiplatform_initializer
                curr_loc = getattr(aiplatform_initializer.global_config, "location", "")

                # If currently on a single region or 'us', try switching to 'global'
                if curr_loc != "global":
                    print(f"⚠️ Model '{current_model_name}' not found in location '{curr_loc}'. Switching Vertex AI location to 'global'...")
                    init_vertexai(location="global")
                    get_model.cache_clear()
                    continue
                else:
                    # If global also fails, fall back to gemini-2.5-flash in us-central1
                    print(f"⚠️ Model '{current_model_name}' not accessible in global endpoint. Falling back to gemini-2.5-flash (us-central1)...")
                    init_vertexai(location="us-central1")
                    current_model_name = "gemini-2.5-flash"
                    get_model.cache_clear()
                    continue

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
                    # If gemini-3.8-flash keeps hitting limits, try gemini-2.5-flash
                    if attempt >= 2 and current_model_name == "gemini-3.8-flash":
                        print("Switching temporarily to gemini-2.5-flash to bypass model quota...")
                        init_vertexai(location="us-central1")
                        current_model_name = "gemini-2.5-flash"
                        get_model.cache_clear()
                else:
                    raise e
            else:
                raise e
