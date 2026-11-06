from __future__ import annotations
import os
import json
import re
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List

@dataclass
class GeolocationResult:
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    address: Optional[str] = None
    source: str = "none"  # "text_dms", "text_map_url", "text_decimal", "exif", "gemini_extracted", "hypocenter"
    confidence: float = 0.0
    raw_match: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        return self.latitude is not None and self.longitude is not None

class GeolocationResolver:
    """
    Robust resolver for extracting geolocation (latitude, longitude, address) from:
    1. Geolocation (Address/Coordinates) sections in document text / captions.
    2. Map links (Google Maps, OpenStreetMap, Apple Maps, Bing Maps, geo: URIs, shortened links).
    3. Degrees-Minutes-Seconds (DMS) coordinates.
    4. Signed or directional decimal degrees.
    5. EXIF GPS metadata from media files.
    """

    @classmethod
    def resolve(
        cls,
        text: Optional[str] = None,
        file_path: Optional[str | Path] = None,
        gemini_location: Optional[Dict[str, Any] | str] = None
    ) -> GeolocationResult:
        """
        Resolves geolocation prioritizing explicit document inputs, map links, EXIF, and Gemini outputs.
        """
        # 1. Check document text / caption for explicit coordinates, map links, or Geolocation blocks
        if text:
            res_text = cls.extract_from_text(text)
            if res_text and res_text.is_valid:
                return res_text

        # 2. Check EXIF GPS from local image if available
        if file_path:
            res_exif = cls.extract_from_exif(file_path)
            if res_exif and res_exif.is_valid:
                return res_exif

        # 3. Check Gemini structured location output
        if gemini_location:
            res_gemini = cls.extract_from_gemini_location(gemini_location)
            if res_gemini and res_gemini.is_valid:
                return res_gemini

        # 4. Partial address match if only address was found in text
        if text:
            addr = cls.extract_section_address(text)
            if addr:
                return GeolocationResult(address=addr, source="text_address_only", confidence=0.4)

        return GeolocationResult()

    @classmethod
    def get_google_maps_api_key(cls) -> Optional[str]:
        """Retrieves GOOGLE_MAPS_API_KEY from environment or .env files."""
        key = os.getenv("GOOGLE_MAPS_API_KEY")
        if key:
            return key.strip().strip('"').strip("'")
        for p in [Path(".env"), Path("server/.env"), Path("../server/.env")]:
            if p.exists():
                for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                    line = line.strip()
                    if line.startswith("GOOGLE_MAPS_API_KEY=") and not line.startswith("#"):
                        _, v = line.split("=", 1)
                        v = v.strip().strip('"').strip("'")
                        if v:
                            os.environ["GOOGLE_MAPS_API_KEY"] = v
                            return v
        return None

    @classmethod
    def has_google_maps_url(cls, text: str) -> bool:
        """Checks if text contains a Google Maps link."""
        return bool(re.search(
            r'https?://(?:maps\.app\.goo\.gl|goo\.gl/maps|maps\.google\.[a-z.]+|[a-z0-9.-]*google\.[a-z.]+/maps)[^\s<>\"\')]*',
            text, re.IGNORECASE
        ))

    @classmethod
    def extract_from_text(cls, text: str) -> Optional[GeolocationResult]:
        """
        Extracts coordinates and address from text.

        Precedence Rules:
        1. Direct Latitude & Longitude in Text:
           If latitude and longitude are already provided in the input text (via DMS,
           directional decimal, or decimal coordinate pairs), they are extracted directly.
           This takes strict precedence over any Google Maps API, even if a Google Maps link
           is also provided in the input file.
        2. Google Maps link (e.g. page-62.pdf without direct coordinates):
           Uses the Google Geocoding API (using GOOGLE_MAPS_API_KEY from .env) to retrieve
           the latitude and longitude coordinates.
        3. Other Map URLs:
           Parses OpenStreetMap, Apple Maps, Bing Maps, or geo: URIs.
        """
        if not text:
            return None

        # Clean text
        text_clean = text.strip()

        # ── Precedence 1: Direct Latitude & Longitude in Text ──
        # 1a. Degrees, Minutes, Seconds (DMS)
        res_dms = cls.extract_from_dms(text_clean)
        if res_dms and res_dms.is_valid:
            addr = cls.extract_section_address(text_clean)
            if addr and not res_dms.address:
                res_dms.address = addr
            return res_dms

        # 1b. Decimal degrees with directional indicators (e.g. 21.880353 N, 95.984881 E)
        res_dec_dir = cls.extract_from_decimal_directional(text_clean)
        if res_dec_dir and res_dec_dir.is_valid:
            addr = cls.extract_section_address(text_clean)
            if addr and not res_dec_dir.address:
                res_dec_dir.address = addr
            return res_dec_dir

        # 1c. Decimal coordinate pairs (e.g. 21.87314, 95.97550 or [21.88, 95.98] or lat:... lon:...)
        res_dec = cls.extract_from_decimal(text_clean)
        if res_dec and res_dec.is_valid:
            addr = cls.extract_section_address(text_clean)
            if addr and not res_dec.address:
                res_dec.address = addr
            return res_dec

        # ── Precedence 2: Google Maps Link -> Google Geocoding API ──
        if cls.has_google_maps_url(text_clean):
            res_geocode = cls.extract_from_google_maps_geocoding(text_clean)
            if res_geocode and res_geocode.is_valid:
                return res_geocode

        # ── Precedence 3: Other Map URLs (OpenStreetMap, Apple Maps, etc.) ──
        res_url = cls.extract_from_map_url(text_clean)
        if res_url and res_url.is_valid:
            addr = cls.extract_section_address(text_clean)
            if addr and not res_url.address:
                res_url.address = addr
            return res_url

        return None

    @classmethod
    def _extract_surrounding_address(cls, text: str, match_pos: int) -> Optional[str]:
        """Extracts the address or place description immediately preceding the map link."""
        prefix_chunk = text[:match_pos].rstrip()
        lines = prefix_chunk.splitlines()
        addr_lines = []
        for l in reversed(lines):
            l_str = l.strip()
            if not l_str:
                if addr_lines:
                    break
                continue
            if re.search(r'^(?:Source|Created by|Short Description|Geolocation|\(Address)', l_str, re.IGNORECASE):
                m_sub = re.search(r'[:]\s*(.+)$', l_str)
                if m_sub and len(m_sub.group(1).strip()) > 3:
                    addr_lines.insert(0, m_sub.group(1).strip())
                break
            addr_lines.insert(0, l_str)
            if len(addr_lines) >= 3:
                break
        if addr_lines:
            cand = " ".join(addr_lines).strip(" ,;:-()")
            cand = re.sub(r'https?://\S+', '', cand).strip(" ,;:-()")
            if len(cand) >= 3:
                return cand
        return cls.extract_section_address(text)

    @classmethod
    def _get_ssl_context(cls):
        """Returns an SSL context suitable for macOS/sandboxed environments."""
        import ssl
        try:
            import certifi
            return ssl.create_default_context(cafile=certifi.where())
        except Exception:
            pass
        # Fallback to server/.venv certifi if it exists
        venv_certifi = Path("server/.venv/lib")
        if venv_certifi.exists():
            for p in venv_certifi.glob("**/certifi/cacert.pem"):
                try:
                    return ssl.create_default_context(cafile=str(p))
                except Exception:
                    pass
        try:
            return ssl.create_default_context()
        except Exception:
            return ssl._create_unverified_context()

    @classmethod
    def _call_google_geocoding_api(cls, params: Dict[str, str], api_key: str, timeout: float = 6.0) -> Optional[Dict[str, Any]]:
        """Makes an HTTP request to the Google Geocoding API."""
        import urllib.request
        import urllib.error
        try:
            query_str = urllib.parse.urlencode(params)
            endpoint = f"https://maps.googleapis.com/maps/api/geocode/json?{query_str}&key={api_key}"
            req = urllib.request.Request(endpoint, headers={"User-Agent": "QuakeAgent/1.0"})
            ctx = cls._get_ssl_context()
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                status = data.get("status")
                if status == "OK" and data.get("results"):
                    return data["results"][0]
                elif status == "ZERO_RESULTS":
                    return None
                else:
                    err_msg = data.get("error_message") or status
                    print(f"   ⚠️ [Google Geocoding API] Status: {err_msg}")
                    return None
        except Exception as e:
            return None

    @classmethod
    def extract_from_google_maps_geocoding(cls, text: str) -> Optional[GeolocationResult]:
        """
        Uses the Google Geocoding API (using GOOGLE_MAPS_API_KEY from .env) to retrieve
        latitude and longitude coordinates when a Google Maps link is provided.
        """
        gm_match = re.search(
            r'https?://(?:maps\.app\.goo\.gl|goo\.gl/maps|maps\.google\.[a-z.]+|[a-z0-9.-]*google\.[a-z.]+/maps)[^\s<>\"\')]*',
            text, re.IGNORECASE
        )
        if not gm_match:
            return None

        gm_url = gm_match.group(0).rstrip(".,;)")
        surrounding_addr = cls._extract_surrounding_address(text, gm_match.start())
        api_key = cls.get_google_maps_api_key()

        # Step 1: Expand shortened Google Maps URL if applicable
        expanded_url = gm_url
        if "goo.gl" in gm_url:
            expanded = cls._resolve_short_url(gm_url)
            if expanded:
                expanded_url = expanded

        place_name = None
        url_coords = None

        # Check for place name in expanded URL: /place/<name>/
        m_place = re.search(r'/place/([^/@]+)', expanded_url)
        if m_place:
            place_name = urllib.parse.unquote(m_place.group(1).replace("+", " ")).strip()

        # Check for exact POI coordinates in data parameters: !3d<lat>!4d<lon>
        m_poi = re.search(r'!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)', expanded_url)
        if m_poi:
            url_coords = (float(m_poi.group(1)), float(m_poi.group(2)))
        else:
            # Fallback to viewport coords: /@lat,lon or ?q=lat,lon or ll=lat,lon
            m_coords = re.search(r'[@?&](?:q|query|ll|loc:)?(-?\d+\.\d+),(-?\d+\.\d+)', expanded_url)
            if m_coords:
                url_coords = (float(m_coords.group(1)), float(m_coords.group(2)))

        # Step 2: Query Google Geocoding API
        if api_key:
            # Query candidate 1: Specific place name extracted from expanded URL (e.g. "Sky Villa, Mandalay, Myanmar")
            if place_name:
                queries = [
                    f"{place_name}, Mandalay, Myanmar",
                    f"{place_name}, Myanmar",
                    place_name
                ]
                for q in queries:
                    res = cls._call_google_geocoding_api({"address": q}, api_key)
                    if res:
                        lat = float(res["geometry"]["location"]["lat"])
                        lon = float(res["geometry"]["location"]["lng"])
                        # If result is within target country bounds (e.g. 13-27 N, 91-103 E)
                        if 13.0 <= lat <= 27.0 and 91.0 <= lon <= 103.0:
                            addr = place_name or res.get("formatted_address")
                            print(f"📍 [Google Geocoding API] Resolved ({lat:.6f}, {lon:.6f}) for '{addr}' via Geocoding API")
                            return GeolocationResult(
                                latitude=lat,
                                longitude=lon,
                                address=addr,
                                source="google_geocoding_api",
                                confidence=1.0,
                                raw_match=gm_url
                            )

            # Query candidate 2: Reverse-geocode coordinates from URL to get precise formatted address & geocoded pin
            if url_coords:
                res = cls._call_google_geocoding_api({"latlng": f"{url_coords[0]},{url_coords[1]}"}, api_key)
                lat, lon = url_coords
                addr = place_name or surrounding_addr
                if res:
                    addr = place_name or res.get("formatted_address") or addr
                print(f"📍 [Google Geocoding API] Resolved ({lat:.6f}, {lon:.6f}) for '{addr or 'Google Map Link'}' via Geocoding API")
                return GeolocationResult(
                    latitude=lat,
                    longitude=lon,
                    address=addr,
                    source="google_geocoding_api",
                    confidence=1.0,
                    raw_match=gm_url
                )

            # Query candidate 3: Surrounding address / plus code from slide
            if surrounding_addr:
                res = cls._call_google_geocoding_api({"address": surrounding_addr}, api_key)
                if res:
                    lat = float(res["geometry"]["location"]["lat"])
                    lon = float(res["geometry"]["location"]["lng"])
                    addr = place_name or res.get("formatted_address") or surrounding_addr
                    print(f"📍 [Google Geocoding API] Resolved ({lat:.6f}, {lon:.6f}) for '{addr}' via Geocoding API")
                    return GeolocationResult(
                        latitude=lat,
                        longitude=lon,
                        address=addr,
                        source="google_geocoding_api",
                        confidence=1.0,
                        raw_match=gm_url
                    )

        # Fallback if Google Geocoding API key is missing or offline:
        if url_coords:
            return GeolocationResult(
                latitude=url_coords[0],
                longitude=url_coords[1],
                address=place_name or surrounding_addr,
                source="google_maps_url_fallback",
                confidence=0.95,
                raw_match=gm_url
            )

        return None

    @classmethod
    def _extract_line_prefix(cls, text: str, match_start: int) -> Optional[str]:
        line_start = text.rfind("\n", 0, match_start)
        line_start = 0 if line_start == -1 else line_start + 1
        prefix = text[line_start:match_start].strip(" ,;:/-")
        prefix = re.sub(r"^(?:Location|Geolocation(?:\s*\([^)]*\))?|Address|Coordinates?)\s*[:\s]*", "", prefix, flags=re.IGNORECASE).strip(" ,;:/-")
        if prefix and len(prefix) >= 2 and not prefix.lower().startswith("http"):
            return prefix
        return None

    @classmethod
    def extract_from_map_url(cls, text: str) -> Optional[GeolocationResult]:
        """Parses Google Maps, OpenStreetMap, Apple Maps, Bing Maps, or geo: URIs."""
        # 1. Google Maps: query / q / ll / loc:lat,lon
        gm_q = re.search(
            r'https?://(?:maps\.google\.[a-z.]+|[a-z0-9.-]*google\.[a-z.]+/maps)[^\s<>\"\']*?[?&](?:q|query|ll|loc:?)=(-?\d+\.\d+),(-?\d+\.\d+)',
            text, re.IGNORECASE
        )
        if gm_q:
            lat = float(gm_q.group(1))
            lon = float(gm_q.group(2))
            addr = cls._extract_line_prefix(text, gm_q.start())
            return GeolocationResult(latitude=lat, longitude=lon, address=addr, source="text_map_url", confidence=1.0, raw_match=gm_q.group(0))

        # 2. Google Maps: /@lat,lon,zoom (with optional /place/<name>/)
        gm_at = re.search(
            r'https?://(?:maps\.google\.[a-z.]+|[a-z0-9.-]*google\.[a-z.]+/maps)[^\s<>\"\']*?(?:/place/([^/@]+))?/@(-?\d+\.\d+),(-?\d+\.\d+)',
            text, re.IGNORECASE
        )
        if gm_at:
            place_slug = gm_at.group(1)
            lat = float(gm_at.group(2))
            lon = float(gm_at.group(3))
            addr = None
            if place_slug:
                addr = urllib.parse.unquote(place_slug.replace("+", " ")).strip()
            if not addr:
                addr = cls._extract_line_prefix(text, gm_at.start())
            return GeolocationResult(latitude=lat, longitude=lon, address=addr, source="text_map_url", confidence=1.0, raw_match=gm_at.group(0))

        # 3. OpenStreetMap: ?mlat=lat&mlon=lon
        osm_q = re.search(
            r'https?://(?:www\.)?openstreetmap\.org[^\s<>\"\']*?[?&]mlat=(-?\d+\.\d+)&mlon=(-?\d+\.\d+)',
            text, re.IGNORECASE
        )
        if osm_q:
            lat = float(osm_q.group(1))
            lon = float(osm_q.group(2))
            return GeolocationResult(latitude=lat, longitude=lon, source="text_map_url", confidence=1.0, raw_match=osm_q.group(0))

        # 4. OpenStreetMap: #map=zoom/lat/lon
        osm_map = re.search(
            r'https?://(?:www\.)?openstreetmap\.org[^\s<>\"\']*?#map=\d+/(-?\d+\.\d+)/(-?\d+\.\d+)',
            text, re.IGNORECASE
        )
        if osm_map:
            lat = float(osm_map.group(1))
            lon = float(osm_map.group(2))
            return GeolocationResult(latitude=lat, longitude=lon, source="text_map_url", confidence=1.0, raw_match=osm_map.group(0))

        # 5. Apple Maps: ll=lat,lon
        apple_m = re.search(
            r'https?://maps\.apple\.com/[^\s<>\"\']*?[?&](?:ll|sll)=(-?\d+\.\d+),(-?\d+\.\d+)',
            text, re.IGNORECASE
        )
        if apple_m:
            lat = float(apple_m.group(1))
            lon = float(apple_m.group(2))
            return GeolocationResult(latitude=lat, longitude=lon, source="text_map_url", confidence=1.0, raw_match=apple_m.group(0))

        # 6. Bing Maps: cp=lat~lon or where1=lat,lon
        bing_m = re.search(
            r'https?://(?:www\.)?bing\.com/maps[^\s<>\"\']*?[?&]cp=(-?\d+\.\d+)~(-?\d+\.\d+)',
            text, re.IGNORECASE
        )
        if bing_m:
            lat = float(bing_m.group(1))
            lon = float(bing_m.group(2))
            return GeolocationResult(latitude=lat, longitude=lon, source="text_map_url", confidence=1.0, raw_match=bing_m.group(0))

        # 7. geo: URI
        geo_uri = re.search(r'geo:(-?\d+\.\d+),(-?\d+\.\d+)', text, re.IGNORECASE)
        if geo_uri:
            lat = float(geo_uri.group(1))
            lon = float(geo_uri.group(2))
            return GeolocationResult(latitude=lat, longitude=lon, source="text_map_url", confidence=1.0, raw_match=geo_uri.group(0))

        # 8. Shortened Google Maps links (e.g. https://maps.app.goo.gl/... or https://goo.gl/maps/...)
        short_link = re.search(r'https?://(?:maps\.app\.goo\.gl|goo\.gl/maps)/[a-zA-Z0-9_-]+', text)
        if short_link:
            expanded = cls._resolve_short_url(short_link.group(0))
            if expanded:
                res_exp = cls.extract_from_map_url(expanded)
                if res_exp and res_exp.is_valid:
                    res_exp.raw_match = short_link.group(0)
                    return res_exp

        return None

    @classmethod
    def _resolve_short_url(cls, url: str, timeout: float = 3.0) -> Optional[str]:
        try:
            import urllib.request
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})
            ctx = cls._get_ssl_context()
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                return resp.geturl()
        except Exception:
            return None

    @classmethod
    def extract_from_dms(cls, text: str) -> Optional[GeolocationResult]:
        """
        Parses Degrees, Minutes, Seconds with flexible formats:
        - 21°52'49.27"N, 95°59'5.57"E
        - 21° 52' 49.27" N, 95° 59' 5.57" E
        - 21d52m49.27s N, 95d59m5.57s E
        - 21°52.82'N, 95°59.09'E (decimal minutes)
        - Supports Latitude first or Longitude first.
        """
        # Full DMS pattern (degrees, minutes, seconds)
        # Lat first: 21°52'49.27"N, 95°59'5.57"E
        dms_lat_first = re.search(
            r'(\d{1,2})\s*[°ddeg\s]+\s*(\d{1,2})\s*[\'mmin\s]+\s*([\d.]+)\s*[\"ssec]?\s*([NS])\s*[,;\s/|]+\s*(\d{1,3})\s*[°ddeg\s]+\s*(\d{1,2})\s*[\'mmin\s]+\s*([\d.]+)\s*[\"ssec]?\s*([EW])',
            text, re.IGNORECASE
        )
        if dms_lat_first:
            lat_d, lat_m, lat_s, lat_dir, lon_d, lon_m, lon_s, lon_dir = dms_lat_first.groups()
            lat = float(lat_d) + float(lat_m) / 60.0 + float(lat_s) / 3600.0
            if lat_dir.upper() == "S":
                lat = -lat
            lon = float(lon_d) + float(lon_m) / 60.0 + float(lon_s) / 3600.0
            if lon_dir.upper() == "W":
                lon = -lon
            addr = cls._extract_line_prefix(text, dms_lat_first.start())
            return GeolocationResult(latitude=lat, longitude=lon, address=addr, source="text_dms", confidence=1.0, raw_match=dms_lat_first.group(0))

        # Lon first: 95°59'5.57"E, 21°52'49.27"N
        dms_lon_first = re.search(
            r'(\d{1,3})\s*[°ddeg\s]+\s*(\d{1,2})\s*[\'mmin\s]+\s*([\d.]+)\s*[\"ssec]?\s*([EW])\s*[,;\s/|]+\s*(\d{1,2})\s*[°ddeg\s]+\s*(\d{1,2})\s*[\'mmin\s]+\s*([\d.]+)\s*[\"ssec]?\s*([NS])',
            text, re.IGNORECASE
        )
        if dms_lon_first:
            lon_d, lon_m, lon_s, lon_dir, lat_d, lat_m, lat_s, lat_dir = dms_lon_first.groups()
            lat = float(lat_d) + float(lat_m) / 60.0 + float(lat_s) / 3600.0
            if lat_dir.upper() == "S":
                lat = -lat
            lon = float(lon_d) + float(lon_m) / 60.0 + float(lon_s) / 3600.0
            if lon_dir.upper() == "W":
                lon = -lon
            return GeolocationResult(latitude=lat, longitude=lon, source="text_dms", confidence=1.0, raw_match=dms_lon_first.group(0))

        # Decimal minutes without seconds: 21°52.82'N, 95°59.09'E
        dm_match = re.search(
            r'(\d{1,2})\s*[°ddeg\s]+\s*([\d.]+)\s*[\'mmin\s]*\s*([NS])\s*[,;\s/|]+\s*(\d{1,3})\s*[°ddeg\s]+\s*([\d.]+)\s*[\'mmin\s]*\s*([EW])',
            text, re.IGNORECASE
        )
        if dm_match:
            lat_d, lat_m, lat_dir, lon_d, lon_m, lon_dir = dm_match.groups()
            lat = float(lat_d) + float(lat_m) / 60.0
            if lat_dir.upper() == "S":
                lat = -lat
            lon = float(lon_d) + float(lon_m) / 60.0
            if lon_dir.upper() == "W":
                lon = -lon
            return GeolocationResult(latitude=lat, longitude=lon, source="text_dms", confidence=0.98, raw_match=dm_match.group(0))

        return None

    @classmethod
    def extract_from_decimal_directional(cls, text: str) -> Optional[GeolocationResult]:
        """Parses decimal degrees with N/S and E/W labels: 21.880353° N, 95.984881° E"""
        # Lat first
        dec_lat_first = re.search(
            r'(\d{1,2}\.\d{3,8})\s*°?\s*([NS])\s*[,;\s/|]+\s*(\d{1,3}\.\d{3,8})\s*°?\s*([EW])',
            text, re.IGNORECASE
        )
        if dec_lat_first:
            lat_v, lat_dir, lon_v, lon_dir = dec_lat_first.groups()
            lat = float(lat_v) if lat_dir.upper() == "N" else -float(lat_v)
            lon = float(lon_v) if lon_dir.upper() == "E" else -float(lon_v)
            return GeolocationResult(latitude=lat, longitude=lon, source="text_decimal", confidence=1.0, raw_match=dec_lat_first.group(0))

        # Lon first
        dec_lon_first = re.search(
            r'(\d{1,3}\.\d{3,8})\s*°?\s*([EW])\s*[,;\s/|]+\s*(\d{1,2}\.\d{3,8})\s*°?\s*([NS])',
            text, re.IGNORECASE
        )
        if dec_lon_first:
            lon_v, lon_dir, lat_v, lat_dir = dec_lon_first.groups()
            lat = float(lat_v) if lat_dir.upper() == "N" else -float(lat_v)
            lon = float(lon_v) if lon_dir.upper() == "E" else -float(lon_v)
            return GeolocationResult(latitude=lat, longitude=lon, source="text_decimal", confidence=1.0, raw_match=dec_lon_first.group(0))

        return None

    @classmethod
    def extract_from_decimal(cls, text: str) -> Optional[GeolocationResult]:
        """Parses bracketed [lat, lon], key-value lat:... lon:..., or Geolocation section decimal lines."""
        # Bracketed [21.880353, 95.984881] or (21.880353, 95.984881)
        bracket_m = re.search(r'[\[\(]\s*(-?\d{1,2}\.\d{3,8})\s*,\s*(-?\d{1,3}\.\d{3,8})\s*[\]\)]', text)
        if bracket_m:
            return GeolocationResult(
                latitude=float(bracket_m.group(1)),
                longitude=float(bracket_m.group(2)),
                source="text_decimal",
                confidence=0.95,
                raw_match=bracket_m.group(0)
            )

        # Labeled lat:... lon:...
        kv_m = re.search(
            r'lat(?:itude)?[:=\s]+(-?\d{1,2}\.\d{3,8})[^\n\r]*?lon(?:gitude)?[:=\s]+(-?\d{1,3}\.\d{3,8})',
            text, re.IGNORECASE
        )
        if kv_m:
            return GeolocationResult(
                latitude=float(kv_m.group(1)),
                longitude=float(kv_m.group(2)),
                source="text_decimal",
                confidence=0.95,
                raw_match=kv_m.group(0)
            )

        # Explicit section match: "Geolocation: 21.880353, 95.984881"
        sec_m = re.search(
            r'Geolocation[^\n\r:]*?:\s*.*?(-?\d{1,2}\.\d{3,8})\s*,\s*(-?\d{1,3}\.\d{3,8})',
            text, re.IGNORECASE
        )
        if sec_m:
            return GeolocationResult(
                latitude=float(sec_m.group(1)),
                longitude=float(sec_m.group(2)),
                source="text_decimal",
                confidence=0.95,
                raw_match=sec_m.group(0)
            )

        # General decimal coordinate pair (e.g. "Sagaing General Hospital, Sagaing 21.87314, 95.97550" or "13.728076, 100.580580")
        pair_m = re.search(
            r'(?<![\w/@&?=])([+-]?\d{1,2}\.\d{3,8})\s*,\s*([+-]?\d{1,3}\.\d{3,8})(?![\w./?&=])',
            text
        )
        if pair_m:
            lat = float(pair_m.group(1))
            lon = float(pair_m.group(2))
            if -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0:
                addr = cls._extract_line_prefix(text, pair_m.start())
                return GeolocationResult(
                    latitude=lat,
                    longitude=lon,
                    address=addr,
                    source="text_decimal",
                    confidence=0.95,
                    raw_match=pair_m.group(0)
                )

        return None

    @classmethod
    def extract_section_address(cls, text: str) -> Optional[str]:
        """
        Extracts address string from 'Geolocation (Address/Coordinates): ...' or 'Location: ...' blocks,
        stripping out coordinates or URLs.
        """
        # Look for Geolocation / Location line
        match = re.search(
            r'(?:Geolocation\s*(?:\([^)]*\))?|Location|Address)\s*[:\s]+\s*([^\n\r]+(?:\n[^\n\r]+)?)',
            text, re.IGNORECASE
        )
        if not match:
            return None

        candidate = match.group(1).strip()
        # Remove any URLs
        candidate = re.sub(r'https?://\S+', '', candidate).strip()
        # Remove coordinate substrings (DMS or decimal pairs)
        candidate = re.sub(r'\d+°\S+', '', candidate).strip()
        candidate = re.sub(r'[-+]?\d+\.\d+\s*,\s*[-+]?\d+\.\d+', '', candidate).strip()
        candidate = re.sub(r'\[\s*[-+]?\d+.*?\]', '', candidate)
        candidate = re.sub(r'\(\s*[-+]?\d+.*?\)', '', candidate)
        candidate = re.sub(r'\[\s*\]|\(\s*\)', '', candidate).strip(" ,;:/-[]()")

        # Take first meaningful line of address
        lines = [line.strip(" ,;:/-") for line in candidate.splitlines() if line.strip(" ,;:/-")]
        if lines:
            clean_addr = lines[0]
            # Avoid returning standard placeholders
            if clean_addr.lower() not in ("unknown", "n/a", "none", "see below", "image"):
                return clean_addr
        return None

    @classmethod
    def extract_from_exif(cls, image_path: str | Path) -> Optional[GeolocationResult]:
        """Extracts GPS coordinates from image EXIF metadata if present."""
        path = Path(image_path)
        if not path.exists() or path.suffix.lower() not in (".jpg", ".jpeg", ".tiff", ".png", ".webp"):
            return None

        try:
            from PIL import Image, ExifTags
            with Image.open(path) as img:
                exif = img._getexif()
                if not exif:
                    return None

                gps_info = {}
                for tag, value in exif.items():
                    decoded = ExifTags.TAGS.get(tag, tag)
                    if decoded == "GPSInfo":
                        for t in value:
                            sub_decoded = ExifTags.GPSTAGS.get(t, t)
                            gps_info[sub_decoded] = value[t]
                        break

                if not gps_info:
                    return None

                def _convert_to_degrees(value):
                    d = float(value[0])
                    m = float(value[1])
                    s = float(value[2])
                    return d + (m / 60.0) + (s / 3600.0)

                lat = _convert_to_degrees(gps_info["GPSLatitude"])
                if gps_info.get("GPSLatitudeRef", "N").upper() == "S":
                    lat = -lat

                lon = _convert_to_degrees(gps_info["GPSLongitude"])
                if gps_info.get("GPSLongitudeRef", "E").upper() == "W":
                    lon = -lon

                return GeolocationResult(latitude=lat, longitude=lon, source="exif", confidence=1.0)
        except Exception:
            return None

    @classmethod
    def extract_from_gemini_location(cls, location_val: Dict[str, Any] | str) -> Optional[GeolocationResult]:
        """Extracts or parses coordinates from Gemini's structured location dictionary or string."""
        if not location_val:
            return None

        lat, lon = None, None
        address = None

        if isinstance(location_val, dict):
            address = location_val.get("address")
            coords = location_val.get("coordinates")
            if isinstance(coords, (list, tuple)) and len(coords) >= 2:
                try:
                    lat = float(coords[0])
                    lon = float(coords[1])
                except (ValueError, TypeError):
                    pass

            # If coordinates were not numbers in coords, check if address field contains map link or DMS
            if (lat is None or lon is None) and address:
                res_addr = cls.extract_from_text(address)
                if res_addr and res_addr.is_valid:
                    return res_addr

            if lat is not None and lon is not None:
                return GeolocationResult(latitude=lat, longitude=lon, address=address, source="gemini_extracted", confidence=0.85)

        elif isinstance(location_val, str):
            address = location_val
            res_str = cls.extract_from_text(location_val)
            if res_str and res_str.is_valid:
                return res_str
            return GeolocationResult(address=address, source="gemini_address_only", confidence=0.5)

        return None
