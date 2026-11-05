import os, base64, json, re, shutil, subprocess
from typing import List, Dict, Any, Optional
try:
    from typing import TypedDict
except ImportError:
    from typing_extensions import TypedDict

import vertexai
from vertexai.generative_models import Part
from services.MMIRetriever import MMIRetriever
from services.manage_model import get_response, init_vertexai

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.service_account import Credentials
from langchain.schema import Document
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.tools.tavily_search import TavilySearchResults
from langgraph.graph import START, END, StateGraph

from services.utilities import load_credentials

load_dotenv()

projectID = os.environ.get('projectID') or os.environ.get('GCS_PROJECT_ID')
TRAVILY_API_KEY = os.environ.get('TAVILY_API_KEY')

try:
    init_vertexai()
except Exception as e:
    print(f"Notice: vertexai init deferred: {e}")


def parse_coordinates(text: str) -> Optional[List[float]]:
    """
    Parses geographic coordinates from text.
    Handles:
      - DMS / DDM with postfix direction: e.g. 21°52'49.27"N, 95°59'5.57"E or 21° 52.821' N, 95° 59.093' E
      - DMS / DDM with prefix direction: e.g. N21°52'49.27", E95°59'5.57"
      - Decimal Degrees with postfix direction: e.g. 21.88035 N, 95.98488 E or 21.88035° N, 95.98488° E
      - Decimal Degrees with prefix direction: e.g. N21.88035, E95.98488
      - Plain or labeled Decimal Degrees: e.g. Lat: 21.88035, Lon: 95.98488 or 21.88035, 95.98488
    Returns [latitude, longitude] in decimal degrees.
    """
    if not text:
        return None

    # Pattern 1A: DMS or DDM postfix direction: 21°52'49.27"N, 95°59'5.57"E
    dms_post = re.compile(
        r"(\d{1,3})\s*°\s*(\d{1,2}(?:\.\d+)?)\s*[\x27\u2019\u2032]?\s*([0-9.]+)?\s*[\x22\u201d\u2033]?\s*([NSEW])"
        r"[\s,;\/]+(\d{1,3})\s*°\s*(\d{1,2}(?:\.\d+)?)\s*[\x27\u2019\u2032]?\s*([0-9.]+)?\s*[\x22\u201d\u2033]?\s*([NSEW])",
        re.IGNORECASE
    )
    m = dms_post.search(text)
    if m:
        d1, m1, s1, dir1, d2, m2, s2, dir2 = m.groups()
        val1 = float(d1) + float(m1) / 60.0 + (float(s1) / 3600.0 if s1 else 0.0)
        if dir1.upper() in ["S", "W"]:
            val1 = -val1
        val2 = float(d2) + float(m2) / 60.0 + (float(s2) / 3600.0 if s2 else 0.0)
        if dir2.upper() in ["S", "W"]:
            val2 = -val2

        if dir1.upper() in ["N", "S"] and dir2.upper() in ["E", "W"]:
            return [round(val1, 6), round(val2, 6)]
        elif dir1.upper() in ["E", "W"] and dir2.upper() in ["N", "S"]:
            return [round(val2, 6), round(val1, 6)]
        return [round(val1, 6), round(val2, 6)]

    # Pattern 1B: DMS or DDM prefix direction: N21°52'49.27", E95°59'5.57"
    dms_pre = re.compile(
        r"([NSEW])\s*(\d{1,3})\s*°\s*(\d{1,2}(?:\.\d+)?)\s*[\x27\u2019\u2032]?\s*([0-9.]+)?\s*[\x22\u201d\u2033]?"
        r"[\s,;\/]+([NSEW])\s*(\d{1,3})\s*°\s*(\d{1,2}(?:\.\d+)?)\s*[\x27\u2019\u2032]?\s*([0-9.]+)?\s*[\x22\u201d\u2033]?",
        re.IGNORECASE
    )
    m = dms_pre.search(text)
    if m:
        dir1, d1, m1, s1, dir2, d2, m2, s2 = m.groups()
        val1 = float(d1) + float(m1) / 60.0 + (float(s1) / 3600.0 if s1 else 0.0)
        if dir1.upper() in ["S", "W"]:
            val1 = -val1
        val2 = float(d2) + float(m2) / 60.0 + (float(s2) / 3600.0 if s2 else 0.0)
        if dir2.upper() in ["S", "W"]:
            val2 = -val2

        if dir1.upper() in ["N", "S"] and dir2.upper() in ["E", "W"]:
            return [round(val1, 6), round(val2, 6)]
        elif dir1.upper() in ["E", "W"] and dir2.upper() in ["N", "S"]:
            return [round(val2, 6), round(val1, 6)]
        return [round(val1, 6), round(val2, 6)]

    # Pattern 2A: Decimal format with postfix N/S/E/W: 21.88035 N, 95.98488 E
    dd_post = re.compile(
        r"(\d{1,3}\.\d+)\s*°?\s*([NSEW])[\s,;\/]+(\d{1,3}\.\d+)\s*°?\s*([NSEW])",
        re.IGNORECASE
    )
    m = dd_post.search(text)
    if m:
        v1, d1, v2, d2 = m.groups()
        val1, val2 = float(v1), float(v2)
        if d1.upper() in ["S", "W"]:
            val1 = -val1
        if d2.upper() in ["S", "W"]:
            val2 = -val2
        if d1.upper() in ["N", "S"] and d2.upper() in ["E", "W"]:
            return [round(val1, 6), round(val2, 6)]
        elif d1.upper() in ["E", "W"] and d2.upper() in ["N", "S"]:
            return [round(val2, 6), round(val1, 6)]
        return [round(val1, 6), round(val2, 6)]

    # Pattern 2B: Decimal format with prefix N/S/E/W: N21.88035, E95.98488
    dd_pre = re.compile(
        r"([NSEW])\s*(\d{1,3}\.\d+)\s*°?[\s,;\/]+([NSEW])\s*(\d{1,3}\.\d+)\s*°?",
        re.IGNORECASE
    )
    m = dd_pre.search(text)
    if m:
        d1, v1, d2, v2 = m.groups()
        val1, val2 = float(v1), float(v2)
        if d1.upper() in ["S", "W"]:
            val1 = -val1
        if d2.upper() in ["S", "W"]:
            val2 = -val2
        if d1.upper() in ["N", "S"] and d2.upper() in ["E", "W"]:
            return [round(val1, 6), round(val2, 6)]
        elif d1.upper() in ["E", "W"] and d2.upper() in ["N", "S"]:
            return [round(val2, 6), round(val1, 6)]
        return [round(val1, 6), round(val2, 6)]

    # Pattern 3: Plain decimal coordinates: 21.88035, 95.98488 or lat: 21.88035, lon: 95.98488
    dd_regex = re.compile(
        r"(?:lat(?:itude)?[:\s]*)?([-+]?\d{1,3}\.\d{3,})[\s,;\/]+(?:lon(?:gitude)?[:\s]*)?([-+]?\d{1,3}\.\d{3,})",
        re.IGNORECASE
    )
    m = dd_regex.search(text)
    if m:
        val1, val2 = float(m.group(1)), float(m.group(2))
        return [round(val1, 6), round(val2, 6)]

    return None


def call_geocoding_api(query_or_address: str, api_key: str = None) -> Optional[Dict[str, Any]]:
    """
    Calls Google Geocoding API to resolve an address, place name, place_id, or coordinates.
    """
    import requests
    api_key = (
        api_key
        or os.environ.get("GOOGLE_MAPS_API_KEY")
        or os.environ.get("GEOCODING_API_KEY")
        or os.environ.get("GOOGLE_GEOCODING_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
    )
    if not api_key:
        print("Notice: No Google Maps / Geocoding API key found in environment (set GOOGLE_MAPS_API_KEY in server/.env).")
        return None

    try:
        url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {"key": api_key}
        clean_q = query_or_address.strip()

        # Check if coordinates were passed for reverse geocoding (e.g. "21.880353,95.984881")
        coord_m = re.match(r"^[-+]?\d{1,3}\.\d+[\s,]+[-+]?\d{1,3}\.\d+$", clean_q)
        if coord_m:
            params["latlng"] = clean_q.replace(" ", "")
        elif clean_q.startswith("place_id:"):
            params["place_id"] = clean_q.replace("place_id:", "").strip()
        else:
            params["address"] = clean_q

        print(f"🌐 [Google Geocoding API] Resolving '{clean_q}'...")
        resp = requests.get(url, params=params, timeout=15)
        data = resp.json()
        if data.get("status") == "OK" and data.get("results"):
            top = data["results"][0]
            loc = top["geometry"]["location"]
            lat = round(float(loc["lat"]), 6)
            lon = round(float(loc["lng"]), 6)
            formatted_address = top.get("formatted_address", clean_q)
            print(f"✅ [Google Geocoding API] Resolved '{clean_q}' -> [{lat}, {lon}] ({formatted_address})")
            return {
                "address": formatted_address,
                "coordinates": [lat, lon]
            }
        else:
            print(f"Notice: Google Geocoding API returned status '{data.get('status')}': {data.get('error_message', '')}")
    except Exception as e:
        print(f"Notice: Error calling Google Geocoding API: {e}")
    return None


def extract_google_maps_urls(text: str, pdf_bytes: bytes = None) -> List[str]:
    """
    Finds all Google Maps URLs from text, PDF hyperlinks, and/or PDF link annotations (/URI).
    """
    found = []

    # 1. Search text
    if text:
        pattern = re.compile(
            r"(?:https?://)?(?:maps\.app\.goo\.gl|goo\.gl/maps|(?:www\.)?google\.[a-z.]+/maps|maps\.google\.[a-z.]+)[^\s\"\'<>)]+",
            re.IGNORECASE
        )
        for m in pattern.finditer(text):
            u = m.group(0)
            if not u.lower().startswith("http"):
                u = "https://" + u
            found.append(u)

    # 2. Search PDF hyperlinks and annotations
    if pdf_bytes:
        # A. Try pdftohtml CLI to extract HTML <a href="..."> hyperlinks
        try:
            pdftohtml_path = shutil.which("pdftohtml") or "/opt/homebrew/bin/pdftohtml"
            if os.path.exists(pdftohtml_path):
                proc = subprocess.run(
                    [pdftohtml_path, "-stdout", "-xml", "-i", "-", "-"],
                    input=pdf_bytes,
                    capture_output=True,
                    check=False
                )
                if proc.returncode == 0 and proc.stdout:
                    html_links = re.findall(r'href="([^"]+)"', proc.stdout.decode("utf-8", errors="ignore"))
                    for link in html_links:
                        clean_link = link.strip().replace("&amp;", "&")
                        if any(k in clean_link.lower() for k in ["maps.app.goo.gl", "goo.gl/maps", "google.", "maps.google"]):
                            found.append(clean_link)
        except Exception:
            pass

        # B. Search PDF raw bytes annotations for /URI (...) handling escaped parens
        uri_matches = re.findall(rb"/URI\s*\(((?:\\\(|\\\)|[^()])+)\)", pdf_bytes)
        for u in uri_matches:
            try:
                dec = u.decode("utf-8", errors="ignore").replace(r"\(", "(").replace(r"\)", ")")
                if any(k in dec.lower() for k in ["maps.app.goo.gl", "goo.gl/maps", "google.", "maps.google"]):
                    found.append(dec)
            except Exception:
                pass

        # C. Search PDF raw bytes annotations for /URI <hex>
        hex_matches = re.findall(rb"/URI\s*<([0-9a-fA-F]+)>", pdf_bytes)
        for h in hex_matches:
            try:
                dec = bytes.fromhex(h.decode("ascii")).decode("utf-8", errors="ignore")
                if any(k in dec.lower() for k in ["maps.app.goo.gl", "goo.gl/maps", "google.", "maps.google"]):
                    found.append(dec)
            except Exception:
                pass

    # Deduplicate while preserving order and strip trailing punctuation
    seen = set()
    deduped = []
    for u in found:
        cleaned = u.rstrip(".,;)]}>\"'")
        if cleaned not in seen:
            seen.add(cleaned)
            deduped.append(cleaned)
    return deduped


def resolve_coords_from_google_maps_url(url: str, api_key: str = None) -> Optional[Dict[str, Any]]:
    """
    Given a Google Maps URL, resolves coordinates and address.
    1. Unshortens shortened links (maps.app.goo.gl, goo.gl/maps, etc.).
    2. Extracts coordinates directly from URL if present (!3d!4d, /@lat,lon, ?q=lat,lon, DMS).
    3. Uses Google Geocoding API if place name, query, or place_id is present.
    """
    import urllib.parse
    import requests

    resolved_url = url
    # Follow redirects for short links (e.g. maps.app.goo.gl or goo.gl/maps)
    if any(short in url.lower() for short in ["goo.gl", "maps.app", "bit.ly", "t.co", "tinyurl.com"]):
        try:
            print(f"🔗 Following Google Maps redirect for: {url}")
            resp = requests.get(
                url,
                allow_redirects=True,
                timeout=12,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            )
            resolved_url = resp.url
            # If Google redirects to a consent page, extract continue param
            if "consent.google." in resolved_url.lower():
                parsed_q = urllib.parse.parse_qs(urllib.parse.urlparse(resolved_url).query)
                cont = parsed_q.get("continue")
                if cont and cont[0]:
                    resolved_url = cont[0]
            print(f"   ↳ Expanded URL: {resolved_url}")
        except Exception as e:
            print(f"Notice: Could not follow redirect for '{url}': {e}")

    # Check 1: Extract coordinates embedded directly in URL parameters
    # Pattern A: Protobuf !3d(lat)!4d(lon)
    m_proto = re.search(r"!3d([-+]?\d+\.\d+)!4d([-+]?\d+\.\d+)", resolved_url)
    if m_proto:
        lat, lon = round(float(m_proto.group(1)), 6), round(float(m_proto.group(2)), 6)
        place_match = re.search(r"/place/([^/@?]+)", resolved_url)
        address = urllib.parse.unquote_plus(place_match.group(1)) if place_match else "Google Maps Location"
        return {"address": address, "coordinates": [lat, lon]}

    # Pattern B: /@(-?\d+\.\d+),(-?\d+\.\d+)
    m_at = re.search(r"/@(-?\d+\.\d+),(-?\d+\.\d+)", resolved_url)
    if m_at:
        lat, lon = round(float(m_at.group(1)), 6), round(float(m_at.group(2)), 6)
        place_match = re.search(r"/place/([^/@?]+)", resolved_url)
        address = urllib.parse.unquote_plus(place_match.group(1)) if place_match else "Google Maps Location"
        return {"address": address, "coordinates": [lat, lon]}

    # Pattern C: [?&](?:q|query|ll|center)=(-?\d+\.\d+)[,\s]+(-?\d+\.\d+)
    m_q = re.search(r"[?&](?:q|query|ll|center)=(-?\d+\.\d+)[,\s]+(-?\d+\.\d+)", resolved_url)
    if m_q:
        lat, lon = round(float(m_q.group(1)), 6), round(float(m_q.group(2)), 6)
        return {"address": "Google Maps Location", "coordinates": [lat, lon]}

    # Pattern D: /place/(-?\d+\.\d+)[+,](-?\d+\.\d+)
    m_pl = re.search(r"/place/(-?\d+\.\d+)[+,](-?\d+\.\d+)", resolved_url)
    if m_pl:
        lat, lon = round(float(m_pl.group(1)), 6), round(float(m_pl.group(2)), 6)
        return {"address": "Google Maps Location", "coordinates": [lat, lon]}

    # Pattern E: unquoted DMS in URL path or query
    unquoted = urllib.parse.unquote_plus(resolved_url)
    dms_coords = parse_coordinates(unquoted)
    if dms_coords:
        return {"address": "Google Maps Location", "coordinates": dms_coords}

    # Check 2: If no explicit coordinates are in the URL, extract place name / query / place_id and call Google Geocoding API
    place_id = None
    pid_match = re.search(r"[?&](?:place_id|ftid)=([a-zA-Z0-9_-]+)", resolved_url) or re.search(r"place_id:([a-zA-Z0-9_-]+)", resolved_url)
    if pid_match:
        place_id = pid_match.group(1)

    query = None
    q_match = re.search(r"[?&](?:q|query)=([^&]+)", resolved_url)
    if q_match:
        cand_query = urllib.parse.unquote_plus(q_match.group(1)).strip()
        cand_coords = parse_coordinates(cand_query)
        if cand_coords:
            return {"address": "Google Maps Location", "coordinates": cand_coords}
        query = cand_query

    if not query:
        p_match = re.search(r"/place/([^/@?]+)", resolved_url)
        if p_match:
            cand_place = urllib.parse.unquote_plus(p_match.group(1)).strip()
            cand_coords = parse_coordinates(cand_place)
            if cand_coords:
                return {"address": "Google Maps Location", "coordinates": cand_coords}
            query = cand_place

    if place_id:
        geo_result = call_geocoding_api(f"place_id:{place_id}", api_key=api_key)
        if geo_result:
            return geo_result

    if query:
        geo_result = call_geocoding_api(query, api_key=api_key)
        if geo_result:
            return geo_result

    return None


def parse_location_from_text(text: str, pdf_bytes: bytes = None) -> Dict[str, Any]:
    """
    Extracts address and coordinates from text and/or PDF bytes.
    PRIORITY ORDER:
    1. Direct latitude & longitude in input PDF text (DMS, DDM, or Decimal Degrees).
       Takes PRECEDENCE over any Google Maps link or Geocoding API.
    2. Google Maps URLs in text or PDF annotations/hyperlinks (resolving URL parameters
       or querying Google Geocoding API).
    3. Fallback to geocoding place names via Google Geocoding API if coordinates are missing.
    """
    text_clean = text or ""

    # 1. PRIORITY 1: Check for coordinates directly provided in the text (excluding URLs)
    text_without_urls = re.sub(r"https?://[^\s\"\'<>)]+", "", text_clean)
    coords = parse_coordinates(text_without_urls)

    address = "Unknown"
    if text_clean:
        if coords:
            dms_pos = re.search(r"(\d{1,3}\s*°\s*\d{1,2}|[-+]?\d{1,3}\.\d{3,})", text_clean)
            if dms_pos:
                candidate_lines = [ln.strip() for ln in text_clean[:dms_pos.start()].strip().split("\n") if ln.strip()]
                for line in reversed(candidate_lines):
                    cleaned_line = re.sub(
                        r"^(?:geolocation|address|location|coordinates|coords|lat(?:itude)?|lon(?:gitude)?|gps)[:\s]*",
                        "",
                        line,
                        flags=re.IGNORECASE
                    ).strip().rstrip(",")
                    if (
                        cleaned_line
                        and len(cleaned_line) > 2
                        and not cleaned_line.lower().startswith("http")
                        and not re.match(r"^(?:lat(?:itude)?|lon(?:gitude)?|coords?|gps)$", cleaned_line, re.IGNORECASE)
                    ):
                        address = cleaned_line
                        break

        if address == "Unknown":
            match_addr = re.search(
                r"(?:geolocation|location|address)[:\s]*(?:\(Address\/Coordinates\):)?\s*([^\n\r,]+(?:,\s*[^\n\r,]+)?)",
                text_clean,
                re.IGNORECASE
            )
            if match_addr:
                candidate = match_addr.group(1).strip()
                candidate = re.sub(r"\d{1,3}\s*°.*", "", candidate).strip().rstrip(",")
                if (
                    candidate
                    and len(candidate) > 2
                    and not candidate.lower().startswith("http")
                    and not re.match(r"^(?:lat(?:itude)?|lon(?:gitude)?|coords?|gps)$", candidate, re.IGNORECASE)
                ):
                    address = candidate

    if coords and coords != [0.0, 0.0]:
        print(f"📍 [Direct Extraction] Found coordinates directly in PDF text: {coords} (Address: '{address}') - Precedence over Google Maps API")
        return {
            "address": address,
            "coordinates": coords
        }

    # 2. PRIORITY 2: Check for Google Maps URLs (in text, PDF hyperlinks, or PDF link annotations)
    maps_urls = extract_google_maps_urls(text_clean, pdf_bytes=pdf_bytes)
    if maps_urls:
        for u in maps_urls:
            print(f"🗺️ Found Google Maps link: {u}")
            resolved = resolve_coords_from_google_maps_url(u)
            if resolved and resolved.get("coordinates") and resolved["coordinates"] != [0.0, 0.0]:
                print(f"📍 Successfully resolved Google Maps coordinates: {resolved['coordinates']} ({resolved['address']})")
                return resolved

    # 3. PRIORITY 3: If an address/place name is identified in text, try Google Geocoding API
    if address and address != "Unknown":
        geo_result = call_geocoding_api(address)
        if geo_result and geo_result.get("coordinates") and geo_result["coordinates"] != [0.0, 0.0]:
            return geo_result

    return {
        "address": address,
        "coordinates": [0.0, 0.0]
    }


def extract_text_from_pdf_bytes(data: bytes) -> str:
    """Extracts raw text from PDF bytes using pdftotext, pypdf, or zlib stream parsing."""
    if not data:
        return ""

    # 1. Try pdftotext CLI (installed on macOS Homebrew/Linux)
    try:
        pdftotext_path = shutil.which("pdftotext") or "/opt/homebrew/bin/pdftotext"
        if os.path.exists(pdftotext_path):
            proc = subprocess.run(
                [pdftotext_path, "-", "-"],
                input=data,
                capture_output=True,
                check=False
            )
            if proc.returncode == 0 and proc.stdout:
                text = proc.stdout.decode("utf-8", errors="ignore").strip()
                if len(text) > 10:
                    return text
    except Exception:
        pass

    # 2. Try pypdf / pypdf2 / pdfminer if installed
    try:
        import pypdf, io
        reader = pypdf.PdfReader(io.BytesIO(data))
        text = "\n".join([page.extract_text() or "" for page in reader.pages]).strip()
        if len(text) > 10:
            return text
    except Exception:
        pass

    try:
        import PyPDF2, io
        reader = PyPDF2.PdfReader(io.BytesIO(data))
        text = "\n".join([page.extract_text() or "" for page in reader.pages]).strip()
        if len(text) > 10:
            return text
    except Exception:
        pass

    # 3. Stream decompression fallback
    try:
        import zlib
        streams = re.findall(rb"stream[\r\n]+(.*?)[\r\n]+endstream", data, re.DOTALL)
        extracted = []
        for s in streams:
            try:
                decomp = zlib.decompress(s)
                matches = re.findall(rb"\(([^\)]+)\)", decomp)
                for m in matches:
                    try:
                        t = m.decode("utf-8", errors="ignore").strip()
                        if len(t) > 2 and any(c.isalnum() for c in t):
                            extracted.append(t)
                    except Exception:
                        pass
            except Exception:
                pass
        if extracted:
            return " ".join(extracted)
    except Exception:
        pass

    return ""


class State(TypedDict, total=False):
    """
    State of our graph

    Attributes: 
        **blob_name : name of media file
        **signed_url
        **mime_type
        **initial_analysis : first-pass analysis to LLM
        **context_summary : Summary of earthquake context
        **mmi_documents : Retrieved seismic reference documents
        **web_search : Whether to perform web search for additional context
        **final_analysis : final formatted response
        **generation : report text
        **extracted_text : text extracted from document/slide
        **extracted_location : pre-extracted address and coordinates
    """
    blob_name : str
    signed_url : str
    mime_type : str
    initial_analysis : str
    context_summary : str
    mmi_documents : List[Document]
    web_search : str
    final_analysis : Dict[str, Any]
    generation : str
    extracted_text : str
    extracted_location : Dict[str, Any]
    local_path : str

GRADE_DOCUMENTS_SCHEMA = {
    "type": "object",
    "properties": {
        "binary_score": {
            "type": "string",
            "description": "Documents are relevant to earthquake assessment, 'yes' or 'no'",
            "enum": ["yes", "no"]
        }
    },
    "required": ["binary_score"]
}

BATCH_GRADE_DOCUMENTS_SCHEMA = {
    "type": "object",
    "properties": {
        "grades": {
            "type": "array",
            "description": "Relevance evaluation for each retrieved document",
            "items": {
                "type": "object",
                "properties": {
                    "document_id": {
                        "type": "integer",
                        "description": "1-based index of the document"
                    },
                    "binary_score": {
                        "type": "string",
                        "description": "'yes' if relevant to earthquake intensity/damage assessment, 'no' otherwise",
                        "enum": ["yes", "no"]
                    }
                },
                "required": ["document_id", "binary_score"]
            }
        }
    },
    "required": ["grades"]
}

SEISMIC_ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "blob_name": {"type": "string"},
        "description": {"type": "string"},
        "location": {
            "type": "object",
            "properties": {
                "address": {
                    "type": "string",
                    "description": "Specific street address, city, town, or region identified from the media or document text (e.g. 'Sagaing city, Myanmar'). Use 'Unknown' only if completely indeterminable."
                },
                "coordinates": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "Exact geographic coordinates as [latitude, longitude] in decimal degrees (e.g. [21.880353, 95.984881]). If coordinates in media are DMS (e.g. 21°52'49.27\"N, 95°59'5.57\"E), accurately convert them to decimal numbers [latitude, longitude]. Use [0.0, 0.0] only if completely indeterminable."
                }
            },
            "required": ["address", "coordinates"]
        },
        "auditory_cues": {"type": "string"},
        "background_noise": {"type": "string"},
        "sounds_of_distress": {"type": "string"},
        "visual_observation": {"type": "string"},
        "video_evidence": {"type": "string"},
        "building_type": {"type": "string"},
        "building_materials": {"type": "string"},
        "evidence_analysis": {"type": "string"},
        "context_summary": {"type": "string"},
        "mmi_estimation": {"type": "number"},
        "reasoning": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0}
    },
    "required": ["blob_name", "description", "location", "mmi_estimation", "reasoning", "confidence"]
}


class MultimodalEarthquakeCRAG:
    def __init__(self):
        self.mmi_retriever = MMIRetriever()
        tavily_key = os.environ.get('TAVILY_API_KEY')
        if tavily_key:
            self.web_search_tool = TavilySearchResults(k=3, tavily_api_key=tavily_key)
        else:
            self.web_search_tool = None
        self._media_cache: Dict[str, bytes] = {}
        self.setup_graph()

    def setup_graph(self):
        workflow = StateGraph(State)
        workflow.add_node("initial_analysis", self.initial_analysis)
        workflow.add_node("retrieve_docs", self.retrieve_docs)
        workflow.add_node("grade_documents", self.grade_documents)
        workflow.add_node("web_search", self.web_search)
        workflow.add_node("transform_query", self.transform_query)
        workflow.add_node("final_analysis", self.final_analysis)

        workflow.add_edge(START, "initial_analysis")
        workflow.add_edge("initial_analysis", "retrieve_docs")
        workflow.add_edge("retrieve_docs", "grade_documents")
        workflow.add_conditional_edges(
                    "grade_documents",
                    self.decide_to_analyze,
                    {
                        "transform_query": "transform_query",
                        "final_analysis": "final_analysis",
                    },
                )
        workflow.add_edge("transform_query", "web_search")
        workflow.add_edge("web_search", "final_analysis")
        workflow.add_edge("final_analysis", END)

        self.app = workflow.compile()

    
    def analyze_media_and_traverse_states(self, blob_name : str, signed_url : str, mime_type : str = None, local_path : str = None):
        url_lower = signed_url.lower()
        if mime_type and mime_type in {"image/jpeg", "image/png", "image/webp", "video/mp4", "application/pdf"}:
            pass
        elif any(ext in url_lower for ext in [".jpg", ".jpeg"]):
            mime_type = "image/jpeg"
        elif ".png" in url_lower:
            mime_type = "image/png"
        elif ".webp" in url_lower:
            mime_type = "image/webp"
        elif ".mp4" in url_lower:
            mime_type = "video/mp4"
        elif ".pdf" in url_lower:
            mime_type = "application/pdf"
        elif mime_type:
            pass
        else:
            mime_type = "image/jpeg"
        
        # initial state
        inputs = {
            "blob_name": blob_name,
            "signed_url": signed_url,
            "mime_type": mime_type,
            "local_path": local_path or (blob_name if os.path.exists(blob_name) else None)
        }
        
        for output in self.app.stream(inputs):
            for key, value in output.items():
                # Node
                print(f"Node '{key}':")
                # Optional: print full state at each node
                print(value)
            print("\n---\n")
       
        return value
    
    def get_structured_response(self, contents : list, response_schema):
        """Get structured response from Gemini using JSON schema."""
        
        # Add schema instructions to the content
        schema_prompt = f"""
        Please respond with a valid JSON object that matches this exact schema:
        {json.dumps(response_schema, indent=2)}
        
        Ensure all required fields are included and data types match the schema.
        """
        
        # Combine schema prompt with original contents
        full_contents = [Part.from_text(schema_prompt)] + contents
        
        response = get_response(full_contents)
        
        # Parse JSON response
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            # Fallback: try to extract JSON from response
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            else:
                raise ValueError(f"Could not parse JSON from response: {response}")

    def decide_to_analyze(self, state):
        """Decide whether to proceed with analysis or search for more documents."""
        print("---ASSESS GRADED DOCUMENTS---")
        web_search = state["web_search"]
        
        if web_search == "Yes":
            print("---DECISION: INSUFFICIENT RELEVANT DOCUMENTS, SEARCH FOR MORE---")
            return "transform_query"
        else:
            print("---DECISION: SUFFICIENT DOCUMENTS, PROCEED TO ANALYSIS---")
            return "final_analysis"
    
    def get_media_bytes(self, blob_name: str, signed_url: str = None, local_path: str = None) -> Optional[bytes]:
        """Downloads or retrieves cached bytes for a media blob."""
        if blob_name in self._media_cache:
            return self._media_cache[blob_name]
        if local_path and local_path in self._media_cache:
            return self._media_cache[local_path]

        # 1. Direct local file check (Optimization #3: Avoids slow network GCS round-trip)
        candidate_paths = [p for p in (local_path, blob_name) if p]
        for path in candidate_paths:
            if os.path.exists(path) and os.path.isfile(path):
                try:
                    with open(path, "rb") as f:
                        data = f.read()
                    print(f"✅ Loaded {len(data)} bytes directly from local file '{path}'")
                    self._media_cache[blob_name] = data
                    if local_path:
                        self._media_cache[local_path] = data
                    return data
                except Exception as e:
                    print(f"Notice: Could not read local file '{path}': {e}")

        bucket = os.environ.get("GCS_BUCKET", "quakemap-media-data")

        # 2. Direct bytes via GCS storage client
        try:
            from services.utilities import lazy_clients
            from google.cloud.storage.retry import DEFAULT_RETRY
            storage_client, _ = lazy_clients()
            blob = storage_client.bucket(bucket).blob(blob_name)
            data = blob.download_as_bytes(timeout=180, retry=DEFAULT_RETRY.with_timeout(180))
            print(f"✅ Loaded {len(data)} bytes directly from GCS blob '{blob_name}'")
            self._media_cache[blob_name] = data
            return data
        except Exception as e:
            print(f"Notice: Direct GCS download notice: {e}")

        # 3. Download bytes via HTTP signed URL
        if signed_url and signed_url.startswith("http"):
            try:
                import requests
                resp = requests.get(signed_url, timeout=30)
                if resp.ok and resp.content:
                    print(f"✅ Downloaded {len(resp.content)} bytes via signed URL")
                    self._media_cache[blob_name] = resp.content
                    return resp.content
            except Exception as e:
                print(f"Notice: HTTP signed_url download notice: {e}")

        return None

    def get_media_part(self, blob_name: str, signed_url: str = None, mime_type: str = None, local_path: str = None) -> Part:
        """
        Builds a Part object for Vertex AI Gemini.
        Vertex AI requires 'gs://bucket/blob' format or raw bytes via Part.from_data.
        HTTPS signed URLs are NOT supported by Part.from_uri.
        """
        data = self.get_media_bytes(blob_name, signed_url, local_path=local_path)
        if data:
            return Part.from_data(data=data, mime_type=mime_type)

        bucket = os.environ.get("GCS_BUCKET", "quakemap-media-data")
        if bucket and blob_name:
            gcs_uri = f"gs://{bucket}/{blob_name}"
            print(f"Trying native GCS URI: {gcs_uri}")
            return Part.from_uri(gcs_uri, mime_type=mime_type)

        raise RuntimeError(f"Could not load media part for blob: {blob_name}")

    def initial_analysis(self, state):
        blob_name = state["blob_name"]
        signed_url = state["signed_url"]
        mime_type = state["mime_type"]
        local_path = state.get("local_path")

        # Attempt PDF text & location pre-extraction
        pdf_text = ""
        pre_extracted_loc = {"address": "Unknown", "coordinates": [0.0, 0.0]}
        if mime_type == "application/pdf" or blob_name.lower().endswith(".pdf"):
            data = self.get_media_bytes(blob_name, signed_url, local_path=local_path)
            if data:
                pdf_text = extract_text_from_pdf_bytes(data)
                pre_extracted_loc = parse_location_from_text(pdf_text, pdf_bytes=data)
                if pre_extracted_loc.get("coordinates") and pre_extracted_loc["coordinates"] != [0.0, 0.0]:
                    print(f"📍 [initial_analysis] Pre-extracted location from PDF: {pre_extracted_loc['coordinates']} (Address: '{pre_extracted_loc['address']}')")

        Description_Prompt = f"""
            <System Prompt>
            You are an expert seismologist and geospatial reconnaissance analyst, studying earthquake impact using the Modified Mercalli Intensity Scale (MMI). 
            Your task is to carefully analyze the media (image, PDF document, or video) to:
            1. Extract all geographic location and metadata:
               - Look for any text headers, captions, titles, or template fields such as "Geolocation", "Address/Coordinates", "Location", "Source", GPS coordinates, or city/town names (e.g. Sagaing, Mandalay, Naypyidaw).
               - If coordinates are present in any format (e.g. DMS like 21°52'49.27"N, 95°59'5.57"E or decimal degrees like 21.880353, 95.984881), transcribe them verbatim and calculate their decimal degree values [latitude, longitude].
            2. Identify visual and auditory indicators of seismic shaking:
               - Visible structural and non-structural damage, collapsed buildings, fallen walls, cracks in roads/ground, fault rupture, lateral offset, displaced infrastructure, debris zones.
               - If aerial/satellite view: top-down damage, roof collapses, ruptured roads, ground fissures.
               - If video: dynamic shaking, swaying lights/structures, falling objects, sounds of distress or collapse.
            
            Avoid making assumptions about what is not visible or audible in the media. 
            Carefully analyze and describe both the location/metadata and the earthquake damage in detail.
            </System Prompt>
        """

        media_part = self.get_media_part(blob_name, signed_url, mime_type, local_path=local_path)
        contents = [Part.from_text(Description_Prompt)]
        if pdf_text:
            contents.append(Part.from_text(f"Extracted Document Text from '{blob_name}':\n\"\"\"\n{pdf_text}\n\"\"\""))
        if pre_extracted_loc.get("coordinates") and pre_extracted_loc["coordinates"] != [0.0, 0.0]:
            contents.append(Part.from_text(f"Geographic Location resolved from document/map:\nAddress: {pre_extracted_loc.get('address')}\nCoordinates: {pre_extracted_loc.get('coordinates')}"))
        contents.append(media_part)

        analysis = get_response(contents, json_mode=False)

        return {
            **state,
            "initial_analysis": analysis,
            "context_summary": analysis,
            "extracted_text": pdf_text,
            "extracted_location": pre_extracted_loc
        }

    def retrieve_docs(self, state):
        print("---RETRIEVE MMI DOCUMENTS---")
        context = state["context_summary"]
        
        # retrieve from PineCone
        retrieved_docs = self.mmi_retriever.retrieveDocs(context)
        print("retrieved from PC: ", retrieved_docs)

        return {
            **state, 
            "mmi_documents": retrieved_docs
        }
    
    def grade_documents(self, state):
        print("---GRADE RETRIEVED DOCUMENTS (BATCH)---")

        context = state["context_summary"]
        documents = state.get("mmi_documents", [])
        filtered_docs = []
        web_search = "No"

        if not documents:
            return {
                **state,
                "mmi_documents": [],
                "web_search": "Yes"
            }

        docs_formatted = "\n\n".join(
            [f"[Document {i}]\n{doc.page_content}" for i, doc in enumerate(documents, 1)]
        )

        batch_grader_prompt = f"""
        You are a grader assessing the relevance of retrieved seismic reference documents to an earthquake damage assessment.
        For each document, determine if it contains information about earthquake intensity scales (like MMI), building damage patterns,
        seismic indicators, or earthquake impact assessment. Grade each as 'yes' (relevant) or 'no' (not relevant).

        Analysis context:
        {context}

        Retrieved Documents:
        {docs_formatted}
        """

        try:
            contents = [Part.from_text(batch_grader_prompt)]
            score_data = self.get_structured_response(contents, BATCH_GRADE_DOCUMENTS_SCHEMA)
            grades = score_data.get("grades", [])
            grade_map = {
                int(g.get("document_id", idx)): str(g.get("binary_score", "yes")).lower()
                for idx, g in enumerate(grades, 1)
            }

            for i, doc in enumerate(documents, 1):
                score = grade_map.get(i, "yes")
                if score == "yes":
                    print(f"---GRADE: DOCUMENT {i} RELEVANT---")
                    filtered_docs.append(doc)
                else:
                    print(f"---GRADE: DOCUMENT {i} NOT RELEVANT---")
                    web_search = "Yes"
        except Exception as e:
            print(f"Notice: Batch document grading notice ({e}). Defaulting all to RELEVANT.")
            filtered_docs = list(documents)

        if not filtered_docs:
            web_search = "Yes"

        return {
            **state, 
            "mmi_documents" : filtered_docs,
            "web_search" : web_search
        }

    def web_search(self, state):
        """Search web for additional seismic information."""
        print("---WEB SEARCH FOR SEISMIC INFO---")
        query = state["context_summary"]
        documents = list(state.get("mmi_documents", []))
        
        # Perform web search
        if self.web_search_tool:
            try:
                search_results = self.web_search_tool.invoke({"query": f"earthquake intensity scale MMI damage assessment {query}"})
                web_content = "\n".join([result.get("content", "") for result in search_results if isinstance(result, dict)])
                web_doc = Document(page_content=web_content)
                documents.append(web_doc)
            except Exception as e:
                print(f"Notice: Tavily search error: {e}")
        
        return {
            **state,
            "mmi_documents": documents
        }

    def transform_query(self, state):
        """Transform query for better web search results using custom Gemini."""
        print("---TRANSFORM QUERY---")
        context = state["context_summary"]
        
        query_prompt = f"""
        You are a query optimizer for seismic information retrieval.
        Improve the earthquake assessment query to better find relevant seismic reference materials.
        
        Original context: {context}
        
        Provide an improved query for finding relevant earthquake intensity and damage assessment information.
        """
        
        contents = [Part.from_text(query_prompt)]
        better_query = get_response(contents, json_mode=False)
        
        return {
            **state,
            "context_summary": better_query
        }
    
    def final_analysis(self, state):
        """Generate final seismic analysis with MMI estimation using custom Gemini."""
        print("---GENERATE FINAL SEISMIC ANALYSIS---")
        initial_analysis = state["initial_analysis"]
        documents = state.get("mmi_documents", [])
        blob_name = state["blob_name"]
        signed_url = state.get("signed_url", "")
        mime_type = state.get("mime_type", "")
        local_path = state.get("local_path")
        extracted_text = state.get("extracted_text", "")
        extracted_location = state.get("extracted_location", {})
        
        # Format documents for analysis
        doc_context = "\n\n".join([doc.page_content for doc in documents])
        
        location_guidance = ""
        if extracted_location and extracted_location.get("coordinates") and extracted_location["coordinates"] != [0.0, 0.0]:
            location_guidance = f"""
            Pre-extracted Location from document:
            - Address: "{extracted_location.get('address')}"
            - Coordinates: {extracted_location.get('coordinates')} [latitude, longitude]
            Please verify and use these exact coordinates in the location output.
            """

        # Create final analysis prompt
        final_prompt = f"""
        You are an expert seismologist and geospatial analyst providing an official MMI assessment.
        Using the media evidence, initial analysis, and retrieved seismic reference documents, provide a complete assessment
        including MMI estimation with reasoning, confidence score, and precise location coordinates.
        
        Initial Analysis:
        {initial_analysis}
        
        {location_guidance}
        
        Reference Documents:
        {doc_context}
        
        Provide complete seismic analysis for {blob_name} adhering strictly to the JSON schema:
        - Detailed description of damages and observations
        - Location:
          * Address: specific city, town, street, or region (e.g. "Sagaing city, Myanmar")
          * Coordinates: [latitude, longitude] as a list of two decimal degree numbers (e.g. [21.880353, 95.984881]).
            If coordinates in the document/image are DMS (e.g. 21°52'49.27"N, 95°59'5.57"E), convert to decimal degrees.
            Latitude MUST be the first number, longitude MUST be the second number.
            Only use [0.0, 0.0] if coordinates are completely absent from the media and cannot be determined.
        - Auditory and visual evidence summary
        - Building type and materials assessment
        - MMI estimation (as float from 1.0 to 10.0) with detailed reasoning based on reference documents
        - Confidence score (0.0 to 1.0)
        """
        
        # Provide both the prompt AND the media evidence to Gemini
        try:
            media_part = self.get_media_part(blob_name, signed_url, mime_type, local_path=local_path)
            contents = [Part.from_text(final_prompt), media_part]
        except Exception:
            contents = [Part.from_text(final_prompt)]
        
        # Generate structured analysis using custom function
        analysis = self.get_structured_response(contents, SEISMIC_ANALYSIS_SCHEMA)
        
        # Post-process location and coordinates to ensure 100% extraction accuracy
        loc = analysis.get("location")
        if not isinstance(loc, dict):
            loc = {"address": "Unknown", "coordinates": [0.0, 0.0]}
        
        # PRIORITY 1: Check if direct coordinates were provided in the input PDF document
        direct_pdf_coords = None
        if extracted_text:
            text_without_urls = re.sub(r"https?://[^\s\"\'<>)]+", "", extracted_text)
            direct_pdf_coords = parse_coordinates(text_without_urls)

        if not direct_pdf_coords and extracted_location and extracted_location.get("coordinates") and extracted_location["coordinates"] != [0.0, 0.0]:
            direct_pdf_coords = extracted_location["coordinates"]

        if direct_pdf_coords:
            # Direct coordinates from input PDF file ALWAYS take precedence over any Google Maps API or LLM output
            loc["coordinates"] = direct_pdf_coords
            if extracted_location and extracted_location.get("address") and extracted_location["address"] != "Unknown":
                loc["address"] = extracted_location["address"]
            has_valid_coords = True
        else:
            coords = loc.get("coordinates")
            has_valid_coords = (
                isinstance(coords, (list, tuple))
                and len(coords) >= 2
                and not (float(coords[0]) == 0.0 and float(coords[1]) == 0.0)
            )

        if not has_valid_coords:
            # PRIORITY 2: Check for direct coordinates in initial_analysis or description
            parsed = (
                parse_coordinates(initial_analysis)
                or parse_coordinates(analysis.get("description", ""))
            )
            if parsed:
                loc["coordinates"] = parsed
                has_valid_coords = True

            # PRIORITY 3: Check for any Google Maps URLs in initial_analysis, description, or extracted_text
            if not has_valid_coords:
                combined_text = f"{initial_analysis} {analysis.get('description', '')} {extracted_text}"
                maps_urls = extract_google_maps_urls(combined_text)
                for u in maps_urls:
                    found_map_loc = resolve_coords_from_google_maps_url(u)
                    if found_map_loc and found_map_loc.get("coordinates") and found_map_loc["coordinates"] != [0.0, 0.0]:
                        loc["coordinates"] = found_map_loc["coordinates"]
                        if not loc.get("address") or loc.get("address") == "Unknown":
                            loc["address"] = found_map_loc.get("address", "Google Maps Location")
                        has_valid_coords = True
                        break

            # PRIORITY 4: Fallback to Google Geocoding API using the address string
            if not has_valid_coords and loc.get("address") and loc.get("address") != "Unknown":
                geo_res = call_geocoding_api(loc["address"])
                if geo_res and geo_res.get("coordinates") and geo_res["coordinates"] != [0.0, 0.0]:
                    loc["coordinates"] = geo_res["coordinates"]
                    loc["address"] = geo_res.get("address", loc["address"])
        else:
            # Ensure coordinates are floats [lat, lon]
            try:
                loc["coordinates"] = [round(float(loc["coordinates"][0]), 6), round(float(loc["coordinates"][1]), 6)]
            except (ValueError, TypeError, IndexError):
                pass

        if (not loc.get("address") or loc.get("address") == "Unknown") and extracted_location and extracted_location.get("address") and extracted_location.get("address") != "Unknown":
            loc["address"] = extracted_location["address"]
            
        analysis["location"] = loc

        # Format final 
        generation = f"""
        EARTHQUAKE ASSESSMENT REPORT
        ============================
        File: {analysis.get('blob_name', blob_name)}
        MMI Estimation: {analysis.get('mmi_estimation', 'N/A')}
        Confidence: {analysis.get('confidence', 'N/A')}
        
        Description: {analysis.get('description', '')}
        Location: {analysis.get('location', '')}
        Building Type: {analysis.get('building_type', '')}
        Evidence Analysis: {analysis.get('evidence_analysis', '')}
        Reasoning: {analysis.get('reasoning', '')}
        """
        
        return {
            **state,
            "final_analysis": analysis,
            "generation": generation
        }

    
from google.cloud import bigquery
projectID = os.environ.get('projectID') or os.environ.get('GCS_PROJECT_ID')

if __name__ == "__main__":
    
    client = bigquery.Client(project=projectID)

    query = """
        SELECT *
        FROM `gen-lang-client-0175492774.earthquake_dataset.url_table`
    """

    rows = client.query_and_wait(query)  # Make an API request.

    signed_urls = []
    video_urls = []
    image_without_location = []

    for row in rows:
        if("pdf" in row["signed_url"]):
            signed_urls.append((row["blob_name"], row["signed_url"]))
        elif("jpg" in row["signed_url"] or "jpeg" in row["signed_url"]):
            image_without_location.append((row["blob_name"], row["signed_url"]))
        elif("mp4" in row["signed_url"]):
            video_urls.append((row["blob_name"], row["signed_url"]))

    # print("size: ", len(signed_urls))
    # print("size: ", len(image_without_location))
    # print("size: ", len(video_urls))

    # tuple (blob, signed_url)
    quake_CRAG = MultimodalEarthquakeCRAG()

    result = quake_CRAG.analyze_media_and_traverse_states(
        blob_name=signed_urls[0][0],
        signed_url=signed_urls[0][1],
        mime_type="application/pdf")
    
    print(result["generation"])

    with open("sample_test.txt", 'w') as f:
        f.write(result["generation"])

    lat = result["final_analysis"]["location"]["coordinates"][0]
    lon = result["final_analysis"]["location"]["coordinates"][1]
    mmi = result["final_analysis"]["mmi_estimation"]

    # add point to map
    with open("./assets/records.txt", "w") as f:
        f.write(f"{lon} {lat} {mmi}\n")

    # run gmt again to generate map
    try:
        subprocess.run(["plot.bat"])
    except subprocess.CalledProcessError as e:
        print("gmt failed: ", e)

