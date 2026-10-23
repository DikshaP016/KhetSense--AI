#!/usr/bin/env python3
"""
KhetSense AI — Common Utility Functions
Independent shared utilities with zero dependencies on pipeline or whatsapp packages.
"""

import ipaddress
import logging
import os
import re
import socket
import unicodedata
import urllib.parse
from typing import Optional, Tuple, Set, List, Any, Dict

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.connection import HTTPSConnection
    from urllib3.connectionpool import HTTPSConnectionPool
except ImportError:
    requests = None
    HTTPAdapter = None
    HTTPSConnection = None
    HTTPSConnectionPool = None

logger = logging.getLogger("khetsense_utils")


# ==============================================================================
# 1. PHONE NORMALIZATION & PII MASKING
# ==============================================================================

def normalize_phone(phone: Optional[str]) -> str:
    """
    Normalizes a phone number to digits only, matching Meta's WhatsApp Cloud API format.
    Strips '+', '-', '(', ')', spaces, and any non-digit characters.
    If a 10-digit Indian national number is provided (starting with 6, 7, 8, 9),
    prefixes '91' to align with Meta's international format without '+'.
    If an 11-digit number starting with '0' is provided, replaces '0' with '91'.
    """
    if not phone:
        return ""
    digits = re.sub(r"\D", "", str(phone).strip())
    if len(digits) == 10 and digits[0] in "6789":
        digits = "91" + digits
    elif len(digits) == 11 and digits.startswith("0"):
        digits = "91" + digits[1:]
    return digits


def mask_phone(phone: Optional[str]) -> str:
    """
    Masks phone numbers to protect PII in logs, displaying only the last 4 digits.
    Example: '919876543210' -> '...+3210'
    """
    if not phone or len(str(phone)) < 4:
        return "...+xxxx"
    return f"...+{str(phone)[-4:]}"


# ==============================================================================
# 2. FARMER NAME VALIDATION & SANITIZATION
# ==============================================================================

COMMON_GREETINGS = {
    "hi", "hello", "hey", "namaste", "namaskar", "start", "register",
    "khetsense", "help", "good morning", "good afternoon", "good evening",
    "ok", "yes", "no", "test", "demo", "haan", "ho", "shuru", "ram ram",
    "status", "language", "restart", "reset", "bhasha", "report", "advisory", "check",
    "राम राम", "नमस्कार", "नमस्ते", "प्रणाम", "शुरू", "भाषा", "स्थिती", "स्थिति"
}

GREETING_PREFIXES = (
    "hi ", "hello ", "hey ", "namaste ", "i want to", "hi, i want",
    "hello, i want", "please register", "want to register", "namaskar ",
    "राम राम", "नमस्कार ", "नमस्ते ", "प्रणाम "
)

AFFIRMATIVE_RESPONSES = {
    "yes", "y", "haan", "ha", "ho", "हाँ", "हो", "होय", "yes please",
    "correct", "right", "sahi", "barobar", "ok", "okay"
}


def is_affirmative_response(text: Optional[str]) -> bool:
    """
    Checks if a user's text reply is an affirmative confirmation (e.g., YES, HO, HAAN).
    Supports English, Hindi, and Marathi common affirmatives.
    """
    if not text:
        return False
    cleaned = text.strip().lower()
    # Remove trailing punctuation like '.', '!'
    cleaned = re.sub(r"[^\w\s\u0900-\u097F]", "", cleaned).strip()
    return cleaned in AFFIRMATIVE_RESPONSES


NEGATIVE_RESPONSES = {
    "no", "n", "nahi", "nahin", "na", "cancel", "नाही", "नहीं", "stop", "exit", "no thanks"
}


def is_negative_response(text: Optional[str]) -> bool:
    """
    Checks if a user's text reply is a negative response (e.g., NO, NAHI, CANCEL).
    Supports English, Hindi, and Marathi common negatives.
    """
    if not text:
        return False
    cleaned = text.strip().lower()
    cleaned = re.sub(r"[^\w\s\u0900-\u097F]", "", cleaned).strip()
    return cleaned in NEGATIVE_RESPONSES


def clean_farmer_name(text: Optional[str]) -> Optional[str]:
    """
    Strips conversational prefixes like 'My name is ...' from name input,
    supporting English, Hindi (मेरा नाम), and Marathi (माझे नाव).
    """
    if not text:
        return None
    trimmed = text.strip()
    lower = trimmed.lower()
    if lower.startswith("my name is "):
        return trimmed[11:].strip()
    if lower.startswith("mera naam "):
        rem = trimmed[10:].strip()
        if rem.lower().endswith(" hai"):
            rem = rem[:-4].strip()
        return rem
    if lower.startswith("maze nav "):
        rem = trimmed[9:].strip()
        if rem.lower().endswith(" ahe"):
            rem = rem[:-4].strip()
        return rem
    # Devanagari conversational prefixes
    if trimmed.startswith("माझे नाव "):
        rem = trimmed[9:].strip()
        if rem.endswith(" आहे"):
            rem = rem[:-4].strip()
        return rem
    if trimmed.startswith("मेरा नाम "):
        rem = trimmed[9:].strip()
        if rem.endswith(" है"):
            rem = rem[:-3].strip()
        return rem
    return trimmed


def is_valid_farmer_name(text: Optional[str]) -> bool:
    """
    Validates whether input is a realistic farmer name using structural checks:
    1. Overall length between 2 and 80 characters.
    2. Word count between 1 and 4 words.
    3. Structural character check: each character must be an alphabetic letter
       (via str.isalpha() or Unicode mark for Devanagari vowel signs/matras)
       or one of spaces, '.', '-', '''.
    4. Each token must contain at least one genuine letter.
    5. Greeting blocklist check: single-word greetings or conversational intents rejected.
    """
    if not text:
        return False

    cleaned_name = clean_farmer_name(text)
    if not cleaned_name:
        return False

    trimmed = cleaned_name.strip()
    if len(trimmed) < 2 or len(trimmed) > 80:
        return False

    # Blocklist check on raw lowercase
    lowered = trimmed.lower()
    if lowered in COMMON_GREETINGS:
        return False

    if any(lowered.startswith(p) for p in GREETING_PREFIXES):
        return False

    # Word count check: 1 to 4 words
    words = trimmed.split()
    if len(words) < 1 or len(words) > 4:
        return False

    # Structural character check:
    # Character must be alphabetic (L category), Unicode mark (M category for Devanagari matras),
    # or one of allowed punctuation symbols: space, '.', '-', '''
    for c in trimmed:
        if c in " .-'":
            continue
        if c.isalpha() or unicodedata.category(c).startswith("M"):
            continue
        return False

    # Ensure each word has at least one alphabetic letter
    for w in words:
        has_alpha = any(c.isalpha() for c in w)
        if not has_alpha:
            return False

    # If all checks pass
    return True


# ==============================================================================
# 3. SPATIAL COORDINATE EXTRACTION & GOOGLE MAPS SHORTLINK RESOLUTION
# ==============================================================================

def validate_lat_lon_bounds(lat: Any, lon: Any) -> bool:
    """
    Validates mathematical latitude and longitude boundaries:
    Latitude: -90.0 through 90.0
    Longitude: -180.0 through 180.0
    """
    if lat is None or lon is None:
        return False
    try:
        lat_f = float(lat)
        lon_f = float(lon)
        return (-90.0 <= lat_f <= 90.0) and (-180.0 <= lon_f <= 180.0)
    except (ValueError, TypeError):
        return False


def validate_india_bounds(lat: Any, lon: Any) -> bool:
    """
    Validates whether coordinates fall within India's geographical bounding box:
    Latitude: 6.0 through 38.0°N
    Longitude: 68.0 through 98.0°E
    """
    if lat is None or lon is None:
        return False
    try:
        lat_f = float(lat)
        lon_f = float(lon)
        return (6.0 <= lat_f <= 38.0) and (68.0 <= lon_f <= 98.0)
    except (ValueError, TypeError):
        return False


ALLOWED_SHORTLINK_INITIAL_HOSTS: Set[str] = {
    "maps.app.goo.gl",
    "goo.gl",
}

ALLOWED_REDIRECT_HOSTS: Set[str] = {
    "maps.app.goo.gl",
    "goo.gl",
    "www.google.com",
    "maps.google.com",
    "google.com",
    "www.google.co.in",
    "google.co.in",
}


def extract_direct_coordinates(text: Optional[str]) -> Optional[Tuple[float, float]]:
    """
    Extracts latitude and longitude from direct Google Maps URLs, labeled coordinates,
    directional coordinates, or unambiguous raw coordinate text.
    Does NOT follow redirects or execute network requests.
    Validates mathematical coordinate ranges (-90..90, -180..180).
    """
    if not text or not isinstance(text, str):
        return None
    t = text.strip()

    # 1. Google Maps URL patterns:
    # Query parameter q=, query=, ll=, daddr= (e.g. ?q=19.34634,74.31100 or ?q=19.34634%2C74.31100)
    # Also place searches: /place/19.34634,74.31100 or /search/19.34634,74.31100
    m = re.search(
        r"(?:[?&](?:q|query|ll|daddr)=|\bplace/|\bsearch/)([+-]?\d{1,2}(?:\.\d+)?)(?:,|%2C|\+)([+-]?\d{1,3}(?:\.\d+)?)",
        t,
        re.IGNORECASE,
    )
    if m:
        try:
            lat, lon = float(m.group(1)), float(m.group(2))
            if validate_lat_lon_bounds(lat, lon):
                return lat, lon
        except ValueError:
            pass

    # Viewport /@lat,lon (e.g. https://www.google.com/maps/@19.34634,74.31100,15z)
    m = re.search(r"/@([+-]?\d{1,2}(?:\.\d+)?),([+-]?\d{1,3}(?:\.\d+)?)", t)
    if m:
        try:
            lat, lon = float(m.group(1)), float(m.group(2))
            if validate_lat_lon_bounds(lat, lon):
                return lat, lon
        except ValueError:
            pass

    # Google Maps protobuf data: !3d<lat>!4d<lon> (e.g. data=!3d19.34634!4d74.31100)
    m = re.search(r"!3d([+-]?\d{1,2}(?:\.\d+)?)[^!]*!4d([+-]?\d{1,3}(?:\.\d+)?)", t)
    if m:
        try:
            lat, lon = float(m.group(1)), float(m.group(2))
            if validate_lat_lon_bounds(lat, lon):
                return lat, lon
        except ValueError:
            pass

    # 2. Labeled coordinates: Lat: 19.34634, Lon: 74.31100
    m = re.search(
        r"(?:lat(?:itude)?\s*[:=]?\s*([+-]?\d{1,2}(?:\.\d+)?)[,\s]+lon(?:gitude)?\s*[:=]?\s*([+-]?\d{1,3}(?:\.\d+)?))",
        t,
        re.IGNORECASE,
    )
    if m:
        try:
            lat, lon = float(m.group(1)), float(m.group(2))
            if validate_lat_lon_bounds(lat, lon):
                return lat, lon
        except ValueError:
            pass

    # 3. Directional coordinates: 19.34634 N, 74.31100 E
    m = re.search(
        r"([+-]?\d{1,2}(?:\.\d+)?)\s*°?\s*N[,\s]+([+-]?\d{1,3}(?:\.\d+)?)\s*°?\s*E",
        t,
        re.IGNORECASE,
    )
    if m:
        try:
            lat, lon = float(m.group(1)), float(m.group(2))
            if validate_lat_lon_bounds(lat, lon):
                return lat, lon
        except ValueError:
            pass

    # 4. Standalone raw coordinates string: whole message is essentially coordinates
    m = re.match(r"^\s*([+-]?\d{1,2}(?:\.\d+)?)[,\s]+([+-]?\d{1,3}(?:\.\d+)?)\s*$", t)
    if m:
        try:
            # Reject if both are single-digit integers (e.g. '1 2' or '1, 2')
            if m.group(1).isdigit() and len(m.group(1)) == 1 and m.group(2).isdigit() and len(m.group(2)) == 1:
                return None
            lat, lon = float(m.group(1)), float(m.group(2))
            if validate_lat_lon_bounds(lat, lon):
                return lat, lon
        except ValueError:
            pass

    # 5. Embedded coordinates in conversational text: require >=2 decimal places
    for m in re.finditer(r"(?:^|[^\w.-])([+-]?\d{1,2}\.\d{2,})[,\s]+([+-]?\d{1,3}\.\d{2,})(?:[^\w.-]|$)", t):
        sub_text = t[max(0, m.start() - 10) : min(len(t), m.end() + 15)].lower()
        if any(
            unit in sub_text
            for unit in ["acre", "acres", "cow", "cows", "buffalo", "guntha", "bigha", "ha", "hectare", "kg", "quintal"]
        ):
            continue
        try:
            lat, lon = float(m.group(1)), float(m.group(2))
            if validate_lat_lon_bounds(lat, lon):
                return lat, lon
        except ValueError:
            pass

    return None


if HTTPAdapter and HTTPSConnection and HTTPSConnectionPool:
    class _PinnedHTTPSConnection(HTTPSConnection):
        def __init__(self, *args, **kwargs):
            self._pinned_ip = kwargs.pop("pinned_ip", None)
            super().__init__(*args, **kwargs)

        def _new_conn(self):
            if self._pinned_ip:
                self._dns_host = self._pinned_ip
            return super()._new_conn()

    class _PinnedHTTPSConnectionPool(HTTPSConnectionPool):
        ConnectionCls = _PinnedHTTPSConnection

        def __init__(self, *args, **kwargs):
            self._pinned_ip = kwargs.pop("pinned_ip", None)
            super().__init__(*args, **kwargs)

        def _new_conn(self):
            return self.ConnectionCls(
                host=self.host,
                port=self.port,
                timeout=self.timeout.connect_timeout,
                pinned_ip=self._pinned_ip,
                **self.conn_kw,
            )

    class _PinnedHTTPAdapter(HTTPAdapter):
        def __init__(self, pinned_ip: Optional[str] = None, *args, **kwargs):
            self.pinned_ip = pinned_ip
            super().__init__(*args, **kwargs)

        def get_connection(self, url, proxies=None):
            conn_pool = super().get_connection(url, proxies=proxies)
            if self.pinned_ip and hasattr(conn_pool, "_pinned_ip"):
                conn_pool._pinned_ip = self.pinned_ip
            return conn_pool

        def init_poolmanager(self, *args, **kwargs):
            super().init_poolmanager(*args, **kwargs)
            if hasattr(self, "poolmanager") and hasattr(self.poolmanager, "pool_classes_by_scheme"):
                self.poolmanager.pool_classes_by_scheme["https"] = _PinnedHTTPSConnectionPool
else:
    _PinnedHTTPAdapter = None


def validate_destination_safety(
    url_or_location: str,
    allowed_hosts: Set[str],
) -> Optional[Tuple[urllib.parse.SplitResult, str]]:
    """
    Validates destination safety against strict Anti-SSRF policies:
    1. HTTPS scheme only (no http, file, gopher, ftp, etc.).
    2. Hostname must be in allowed_hosts.
    3. goo.gl path must start with /maps or /maps/.
    4. Port must be 443 or default (None).
    5. URL must not contain embedded user credentials (user:pass).
    6. DNS resolution must succeed and ALL returned IPs must be public, global addresses:
       - No loopback (127.0.0.0/8, ::1)
       - No private RFC1918 (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
       - No link-local / cloud metadata (169.254.169.254, fe80::/10)
       - No reserved / multicast / unspecified
       - No IPv4-mapped IPv6 (::ffff:x.x.x.x)

    Returns (parsed_url, verified_ip) on success, or None on any validation failure.
    Fails closed immediately.
    """
    if not url_or_location or not isinstance(url_or_location, str):
        return None

    try:
        parsed = urllib.parse.urlsplit(url_or_location.strip())
    except Exception:
        return None

    if parsed.scheme.lower() != "https":
        logger.warning("Destination safety blocked non-HTTPS scheme: %s", url_or_location)
        return None

    host = (parsed.hostname or "").lower()
    if not host or host not in allowed_hosts:
        logger.warning("Destination safety blocked disallowed host: %s", host)
        return None

    if host == "goo.gl" and not parsed.path.startswith(("/maps/", "/maps")):
        logger.warning("Destination safety blocked non-maps goo.gl path: %s", parsed.path)
        return None

    if parsed.port not in (None, 443):
        logger.warning("Destination safety blocked non-standard port: %s", parsed.port)
        return None

    if parsed.username or parsed.password:
        logger.warning("Destination safety blocked embedded credentials in URL")
        return None

    try:
        addr_info = socket.getaddrinfo(host, 443, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except (socket.gaierror, socket.error) as err:
        logger.warning("Destination DNS resolution failed for %s: %s", host, err)
        return None

    if not addr_info:
        return None

    verified_ip: Optional[str] = None
    for family, socktype, proto, canonname, sockaddr in addr_info:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            return None
        if (
            ip.is_loopback
            or ip.is_private
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or not ip.is_global
        ):
            logger.warning("Shortlink DNS resolved to non-public/private IP: %s", ip_str)
            return None
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            logger.warning("Shortlink DNS resolved to non-public/private IP: %s", ip_str)
            return None
        if verified_ip is None:
            verified_ip = ip_str

    if not verified_ip:
        return None

    return parsed, verified_ip


def resolve_google_maps_shortlink(
    url: str,
    max_redirects: int = 3,
    timeout: float = 3.0,
) -> Optional[Tuple[float, float]]:
    """
    Safely resolves Google Maps short links (e.g. maps.app.goo.gl, goo.gl/maps)
    with strict Anti-SSRF and concurrency-safe connection protections.

    Security Controls:
    1. HTTPS scheme only (no http, file, ftp, or other schemes).
    2. Initial host strictly restricted to ALLOWED_SHORTLINK_INITIAL_HOSTS.
    3. All redirect destinations strictly restricted to ALLOWED_REDIRECT_HOSTS.
    4. Port restricted to default HTTPS (443 or None). Reject embedded credentials.
    5. Block loopback, private, link-local, reserved, multicast, and non-global IPs (IPv4 & IPv6).
    6. Concurrency-safe DNS pinning: Rather than a process-wide monkeypatch of socket.getaddrinfo
       (which would introduce race conditions in multi-threaded/async servers), session-scoped connection
       pinning is implemented via custom HTTPAdapter and HTTPSConnectionPool. This connects
       directly to the verified public IP while preserving TLS SNI and standard certificate verification.
    7. Maximum redirect limit of 3 hops; loop detection via visited set.
    8. Pre-extraction destination validation: every redirect Location header is fully validated
       against all destination safety rules (scheme, host, port, credentials, DNS resolution, and IP safety)
       BEFORE coordinates are extracted or trusted. Only trust coordinates from validated destinations.
    9. Head-first execution with stream=True fallback; no arbitrary response body consumption.
    10. Strict connection/read timeout (timeout parameter).
    11. Sanitized logging (no credentials, internal headers, or token leaks).
    12. Fails closed on any error, timeout, or disallowed target by returning None.
    """
    if not url or not isinstance(url, str) or not requests:
        return None

    # Pre-flight destination safety validation of initial shortlink URL
    init_check = validate_destination_safety(url, ALLOWED_SHORTLINK_INITIAL_HOSTS)
    if not init_check:
        return None

    curr_url = url.strip()
    visited: Set[str] = set()

    for hop in range(max_redirects + 1):
        if curr_url in visited:
            logger.warning("Shortlink redirect loop detected: %s", curr_url)
            return None
        visited.add(curr_url)

        # Check if current URL directly contains coordinates
        direct_coords = extract_direct_coordinates(curr_url)
        if direct_coords:
            return direct_coords

        if hop >= max_redirects:
            logger.warning("Shortlink exceeded max redirect hops (%d)", max_redirects)
            return None

        # Validate destination safety for curr_url
        dest_check = validate_destination_safety(curr_url, ALLOWED_REDIRECT_HOSTS)
        if not dest_check:
            return None
        parsed_dest, pinned_ip = dest_check

        session = requests.Session()
        if _PinnedHTTPAdapter is not None:
            adapter = _PinnedHTTPAdapter(pinned_ip)
            session.mount("https://", adapter)

        resp = None
        try:
            try:
                resp = session.head(curr_url, allow_redirects=False, timeout=(2.0, timeout))
                if resp.status_code == 405:
                    resp.close()
                    resp = session.get(curr_url, allow_redirects=False, stream=True, timeout=(2.0, timeout))
            except requests.RequestException as req_err:
                logger.debug("Shortlink request failed: %s", req_err)
                return None

            if resp is None:
                return None

            if resp.status_code in (301, 302, 303, 307, 308):
                loc = resp.headers.get("Location")
                if not loc:
                    return None
                resolved_loc = urllib.parse.urljoin(curr_url, loc.strip())

                # Validate destination safety of Location URL BEFORE
                # extracting or trusting any coordinates from it!
                loc_dest_check = validate_destination_safety(resolved_loc, ALLOWED_REDIRECT_HOSTS)
                if not loc_dest_check:
                    logger.warning("Shortlink redirect destination safety validation failed: %s", resolved_loc)
                    return None

                # Direct coordinate extraction only from fully validated Location header
                loc_coords = extract_direct_coordinates(resolved_loc)
                if loc_coords:
                    return loc_coords

                curr_url = resolved_loc
            elif resp.status_code == 200:
                return extract_direct_coordinates(curr_url)
            else:
                return None
        finally:
            if resp is not None:
                resp.close()
            session.close()

    return None


# ==============================================================================
# DEMO AGRICULTURAL PRESETS (For demonstration without owning a farm)
# ==============================================================================
DEMO_AGRICULTURAL_PRESETS: Dict[str, Dict[str, Any]] = {
    "default": {
        "name": "Akola Cropland (Borgaon Manju), Maharashtra",
        "lat": 20.68500,
        "lon": 77.15000,
        "crop": "Cotton",
        "acres": 2.5,
        "district": "Akola",
        "state": "Maharashtra",
        "land_cover": "Cropland",
        "land_cover_code": 40,
    },
    "akola": {
        "name": "Akola Cropland (Borgaon Manju), Maharashtra",
        "lat": 20.68500,
        "lon": 77.15000,
        "crop": "Cotton",
        "acres": 2.5,
        "district": "Akola",
        "state": "Maharashtra",
        "land_cover": "Cropland",
        "land_cover_code": 40,
    },
    "baramati": {
        "name": "Baramati Cropland (Malegaon), Pune, Maharashtra",
        "lat": 18.18000,
        "lon": 74.52000,
        "crop": "Sugarcane",
        "acres": 3.0,
        "district": "Pune",
        "state": "Maharashtra",
        "land_cover": "Cropland",
        "land_cover_code": 40,
    },
    "nagpur": {
        "name": "Nagpur Cropland (Katol Rural), Vidarbha, Maharashtra",
        "lat": 21.28500,
        "lon": 78.61000,
        "crop": "Citrus",
        "acres": 4.0,
        "district": "Nagpur",
        "state": "Maharashtra",
        "land_cover": "Cropland",
        "land_cover_code": 40,
    },
}


def extract_place_query_from_maps_url(url: str) -> Optional[str]:
    """
    Extracts a text search query or place name from Google Maps URLs where direct
    coordinates are absent (e.g. https://www.google.com/maps/place/Baramati+MIDC
    or https://maps.google.com/?q=Akola+Agriculture+College).
    """
    if not url or not isinstance(url, str):
        return None
    try:
        parsed = urllib.parse.urlsplit(url.strip())
    except Exception:
        return None

    # Check query parameters q=, query=
    qs = urllib.parse.parse_qs(parsed.query)
    for k in ["q", "query"]:
        if k in qs and qs[k]:
            q_val = qs[k][0].strip()
            # If not already raw numeric coordinates
            if not re.match(r"^[+-]?\d+(?:\.\d+)?[,\s]+[+-]?\d+(?:\.\d+)?$", q_val):
                return q_val

    # Check /search/<query> or /place/<query>
    m = re.search(r"/(?:place|search)/([^/@?]+)", parsed.path)
    if m:
        val = urllib.parse.unquote_plus(m.group(1)).strip()
        if not re.match(r"^[+-]?\d+(?:\.\d+)?[,\s]+[+-]?\d+(?:\.\d+)?$", val):
            return val

    return None


def geocode_address(
    address: str,
    timeout: float = 4.0,
    user_agent: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Geocodes a typed address string using OpenStreetMap / Nominatim API with:
    - Provider compliance: identification via User-Agent and strict timeout
    - Country restriction: restricted to India ('countrycodes=in')
    - Ambiguity detection: detects multiple candidates across different districts/regions
    - India bounding box verification (-90..90, -180..180 and Lat 6-38°N, Lon 68-98°E)
    - Safe error handling and fail-closed design

    Returns:
        Dict with keys:
        - "status": "success" | "ambiguous" | "not_found" | "out_of_bounds" | "error"
        - "lat": float (if success)
        - "lon": float (if success)
        - "display_name": str (if success)
        - "candidates": List[str] (if ambiguous)
        - "query": str
    """
    if not address or not isinstance(address, str) or not address.strip():
        return {"status": "not_found", "query": "", "reason": "empty_query"}

    query = address.strip()

    # Reject obvious conversational filler or commands that shouldn't be geocoded
    lower_q = query.lower()
    excluded_keywords = {
        "restart", "reset", "language", "lang", "bhasha", "भाषा",
        "status", "yes", "no", "हो", "नाही", "हाँ", "नहीं", "ok", "help",
        "1", "2", "3", "4", "5", "1.", "2.", "3.", "1)", "2)", "3)",
    }
    if lower_q in excluded_keywords:
        return {"status": "not_found", "query": query, "reason": "command_keyword"}

    if not requests:
        logger.warning("Requests library not available for geocoding.")
        return {"status": "error", "query": query, "reason": "requests_unavailable"}

    ua = user_agent or os.getenv(
        "NOMINATIM_USER_AGENT",
        "KhetSense-AI/1.0 (Smart Irrigation Advisory; https://github.com/khetsense)",
    )
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": query,
        "format": "jsonv2",
        "limit": 5,
        "countrycodes": "in",
        "addressdetails": 1,
    }
    headers = {
        "User-Agent": ua,
        "Accept-Language": "en,mr,hi",
    }

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=timeout)
        if resp.status_code != 200:
            logger.warning("Nominatim geocoding HTTP %s for query: %s", resp.status_code, query)
            return {"status": "error", "query": query, "raw_input": query, "reason": f"http_{resp.status_code}"}
        results = resp.json()
    except Exception as e:
        logger.warning("Nominatim geocoding request exception for '%s': %s", query, e)
        return {"status": "error", "query": query, "raw_input": query, "reason": str(e)}

    if not results or not isinstance(results, list):
        return {"status": "not_found", "query": query, "raw_input": query, "reason": "no_results_found"}

    # Filter candidates to valid numeric coordinates in India
    valid_candidates = []
    for r in results:
        try:
            r_lat = float(r["lat"])
            r_lon = float(r["lon"])
            if validate_lat_lon_bounds(r_lat, r_lon):
                valid_candidates.append({
                    "lat": r_lat,
                    "lon": r_lon,
                    "display_name": r.get("display_name", ""),
                    "importance": float(r.get("importance", 0.5)),
                    "address": r.get("address", {}),
                    "type": r.get("type", ""),
                })
        except (ValueError, KeyError, TypeError):
            continue

    if not valid_candidates:
        return {"status": "not_found", "query": query, "raw_input": query, "reason": "no_valid_coordinates"}

    # Check for Ambiguity among top candidates
    if len(valid_candidates) > 1:
        top1 = valid_candidates[0]
        top2 = valid_candidates[1]
        dist_approx = ((top1["lat"] - top2["lat"]) ** 2 + (top1["lon"] - top2["lon"]) ** 2) ** 0.5
        # If coordinates differ by > 0.15 deg (~15km) and top1 importance is not overwhelmingly higher
        if dist_approx > 0.15 and (top1["importance"] - top2["importance"] < 0.25):
            candidate_names = [c["display_name"] for c in valid_candidates[:3]]
            logger.info("Ambiguous address '%s': %d diverse candidates found", query, len(candidate_names))
            return {
                "status": "ambiguous",
                "query": query,
                "raw_input": query,
                "candidates": candidate_names,
                "reason": "multiple_distinct_locations",
            }

    top = valid_candidates[0]
    lat, lon = top["lat"], top["lon"]

    # Verify India bounds
    if not validate_india_bounds(lat, lon):
        return {
            "status": "out_of_bounds",
            "lat": lat,
            "lon": lon,
            "display_name": top["display_name"],
            "query": query,
            "raw_input": query,
        }

    return {
        "status": "success",
        "lat": lat,
        "lon": lon,
        "display_name": top["display_name"],
        "address_details": top["address"],
        "query": query,
        "raw_input": query,
        "source": "typed_address",
    }


def resolve_farm_location_input(
    message_data_or_text: Any,
    resolve_shortlinks: bool = True,
    allow_geocoding: bool = True,
    geocode_timeout: float = 4.0,
) -> Dict[str, Any]:
    """
    Unified multi-method farm location resolver for KhetSense AI:
    1. WhatsApp location pin (message_data['type'] == 'location')
    2. Direct Google Maps URLs (coordinates in path, query, viewport, or protobuf !3d/!4d)
    3. Google Maps Shortlinks (maps.app.goo.gl, goo.gl/maps) via anti-SSRF resolver
    4. Google Maps Place search URLs without coordinates (extracted and geocoded)
    5. Demo Mode ("demo", "demo mode", "डेमो", preset demo farms)
    6. Typed address strings (geocoded via Nominatim with ambiguity checks)

    Returns:
        Dict containing:
        - "status": "success" | "ambiguous" | "not_found" | "out_of_bounds" | "invalid" | "error"
        - "lat": float (if success)
        - "lon": float (if success)
        - "display_name": str
        - "source": "whatsapp_pin" | "direct_coordinates" | "google_maps_shortlink" | "demo_mode" | "typed_address"
        - "is_demo": bool
        - "candidates": List[str] (if ambiguous)
    """
    if not message_data_or_text:
        return {"status": "invalid", "reason": "empty_input"}

    # 1. Native WhatsApp location pin
    if isinstance(message_data_or_text, dict):
        msg_type = message_data_or_text.get("type")
        if msg_type == "location":
            loc = message_data_or_text.get("location", {})
            lat = loc.get("latitude")
            lon = loc.get("longitude")
            if lat is not None and lon is not None:
                try:
                    lat_f = float(lat)
                    lon_f = float(lon)
                    if validate_lat_lon_bounds(lat_f, lon_f):
                        name = loc.get("name")
                        addr = loc.get("address")
                        disp = name or addr or None
                        return {
                            "status": "success",
                            "lat": lat_f,
                            "lon": lon_f,
                            "display_name": disp,
                            "source": "whatsapp_pin",
                            "is_demo": False,
                        }
                except (ValueError, TypeError):
                    return {"status": "invalid", "reason": "malformed_pin_coordinates"}

        # If it's a text message dict
        if msg_type == "text":
            text = message_data_or_text.get("text", {}).get("body", "")
        else:
            text = str(message_data_or_text.get("body", ""))
    else:
        text = str(message_data_or_text)

    clean_text = text.strip()
    if not clean_text:
        return {"status": "invalid", "reason": "empty_text"}

    lower_text = clean_text.lower()

    # 2. Demo Mode
    if lower_text in {"demo", "demo mode", "डेमो", "sample farm", "test farm"} or lower_text.startswith("demo "):
        preset_key = "default"
        if "baramati" in lower_text or "2" in lower_text:
            preset_key = "baramati"
        elif "nagpur" in lower_text or "3" in lower_text:
            preset_key = "nagpur"
        elif "akola" in lower_text or "1" in lower_text:
            preset_key = "akola"

        preset = DEMO_AGRICULTURAL_PRESETS.get(preset_key, DEMO_AGRICULTURAL_PRESETS["default"])
        return {
            "status": "success",
            "lat": preset["lat"],
            "lon": preset["lon"],
            "display_name": preset["name"],
            "source": "demo_mode",
            "is_demo": True,
            "crop": preset.get("crop"),
            "acres": preset.get("acres"),
        }

    # 3. Direct Coordinate Extraction (zero network calls)
    direct = extract_direct_coordinates(clean_text)
    if direct:
        lat, lon = direct
        return {
            "status": "success",
            "lat": lat,
            "lon": lon,
            "display_name": None,
            "source": "direct_coordinates",
            "is_demo": False,
        }

    # 4. Google Maps Shortlinks (maps.app.goo.gl / goo.gl/maps)
    if resolve_shortlinks:
        short_match = re.search(
            r"https://(?:maps\.app\.goo\.gl/[A-Za-z0-9_-]+|goo\.gl/maps/[A-Za-z0-9_-]+)",
            clean_text,
        )
        if short_match:
            coords = resolve_google_maps_shortlink(short_match.group(0))
            if coords:
                lat, lon = coords
                return {
                    "status": "success",
                    "lat": lat,
                    "lon": lon,
                    "display_name": None,
                    "source": "google_maps_shortlink",
                    "is_demo": False,
                }
            return {
                "status": "error",
                "query": clean_text,
                "reason": "shortlink_resolution_failed",
            }

    # 5. Google Maps Place URL with text search query
    place_query = extract_place_query_from_maps_url(clean_text)
    if place_query and allow_geocoding:
        geo_res = geocode_address(place_query, timeout=geocode_timeout)
        if geo_res.get("status") == "success":
            geo_res["display_name"] = f"Google Maps Place: {geo_res.get('display_name')}"
        return geo_res

    # 6. Reject unsupported URLs before address geocoding
    if clean_text.startswith("http://") or clean_text.startswith("https://"):
        return {"status": "invalid", "reason": "unsupported_or_non_maps_url"}

    # 7. Reject pure numeric inputs (e.g. '2.5', '5', '123')
    try:
        float(clean_text)
        return {"status": "invalid", "reason": "numeric_input_not_an_address"}
    except ValueError:
        pass

    # 8. Reject conversational phrases and command chatter
    if lower_text in {"yes", "no", "ok", "y", "n", "होय", "नाही", "हाँ", "नहीं", "restart", "reset", "status", "language", "crop", "acres"}:
        return {"status": "invalid", "reason": "command_or_response"}

    conversational_prefixes = (
        "i am", "i'm", "im ", "i have", "i own", "we have", "we are",
        "my farm", "my field", "my crop", "this is", "here is", "there is",
        "hello", "hi", "hey", "please", "can you", "what is",
        "शेतावर", "शेतात आहे", "माझे शेत", "खेत पर हूँ", "खेत में हूँ", "मेरा खेत"
    )
    if any(lower_text.startswith(pfx) for pfx in conversational_prefixes):
        return {"status": "invalid", "reason": "conversational_text"}

    conversational_keywords = {"acres", "acre", "cows", "animals", "buffaloes", "cattle", "bullocks", "farmer"}
    tokens = set(re.findall(r"\w+", lower_text))
    if tokens & conversational_keywords and "," not in clean_text:
        return {"status": "invalid", "reason": "conversational_text"}

    # 9. Typed Address Geocoding
    if allow_geocoding:
        geo_res = geocode_address(clean_text, timeout=geocode_timeout)
        if geo_res.get("status") in ("success", "ambiguous", "out_of_bounds"):
            return geo_res
        if geo_res.get("status") == "not_found":
            return geo_res

    return {"status": "invalid", "reason": "unrecognized_location_input"}


def parse_location_from_text(
    text: Optional[str],
    resolve_shortlinks: bool = True,
    allow_geocoding: bool = False,
) -> Optional[Tuple[float, float]]:
    """
    Unified location parser for text messages:
    1. Extracts coordinates from direct Google Maps URLs, labeled coordinates, or raw pairs.
    2. Safely resolves Google Maps shortlinks (maps.app.goo.gl, goo.gl/maps).
    3. Resolves typed addresses via Nominatim geocoding if enabled.
    4. Validates mathematical bounds (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0).

    Returns (lat, lon) as a float tuple, or None if no valid location input is found.
    """
    if not text or not isinstance(text, str):
        return None

    res = resolve_farm_location_input(
        text,
        resolve_shortlinks=resolve_shortlinks,
        allow_geocoding=allow_geocoding,
    )
    if res.get("status") == "success":
        return res["lat"], res["lon"]

    return None


# ==============================================================================
# 6. SENSOR DATA SANITIZATION & BOUNDARY VALIDATION
# ==============================================================================

def sanitize_sensor_float(
    val: Any,
    min_val: Optional[float] = None,
    max_val: Optional[float] = None,
) -> Optional[float]:
    """
    Sanitizes sensor floating-point inputs against IEEE 754 non-finite values and corrupt types:
    - Rejects None, boolean flags, non-numeric strings, and unconvertible objects.
    - Rejects IEEE 754 NaN, positive infinity, and negative infinity.
    - Enforces [min_val, max_val] boundaries if specified.
    - Returns valid float or None (treated as unavailable/unknown by decision rules).
    """
    if val is None or isinstance(val, bool):
        return None
    try:
        f = float(val)
    except (ValueError, TypeError):
        return None
    import math
    if math.isnan(f) or math.isinf(f):
        return None
    if min_val is not None and f < min_val:
        return None
    if max_val is not None and f > max_val:
        return None
    return f

