#!/usr/bin/env python3
"""
KhetSense AI — WhatsApp Registration Flow State Machine
Handles:
1. Message deduplication for Meta webhook retries.
2. Multi-step conversational registration:
   - AWAITING_NAME -> AWAITING_CROP -> AWAITING_ACREAGE -> AWAITING_LOCATION -> REGISTERED
3. Crop name normalization with regional transliteration support.
4. Acreage parsing and boundary validation (0.1 to 50.0 acres).
5. Indian bounding box verification (Lat: 6.0–38.0, Lon: 68.0–98.0).
6. Outbound WhatsApp text messaging via Meta Graph API v21.0.
7. Phone number masking in logs (...last 4 digits).
"""

import os
import re
import sys
import logging
from typing import Dict, Any, Optional, Tuple
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
        REGISTRATION_SUCCESS,
        ALREADY_REGISTERED,
        ERROR_GENERIC,
        RESET_SUCCESS,
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
        REGISTRATION_SUCCESS,
        ALREADY_REGISTERED,
        ERROR_GENERIC,
        RESET_SUCCESS,
    )

try:
    from common.utils import (
        normalize_phone,
        mask_phone,
        is_valid_farmer_name,
        clean_farmer_name,
        is_affirmative_response,
    )
except ImportError:
    try:
        from khetsense.common.utils import (
            normalize_phone,
            mask_phone,
            is_valid_farmer_name,
            clean_farmer_name,
            is_affirmative_response,
        )
    except ImportError:
        # Fallback if executed directly inside whatsapp/
        from ..common.utils import (
            normalize_phone,
            mask_phone,
            is_valid_farmer_name,
            clean_farmer_name,
            is_affirmative_response,
        )

try:
    from pipeline.farmer_registration import register_farmer_from_pin
except ImportError:
    try:
        from khetsense.pipeline.farmer_registration import register_farmer_from_pin
    except ImportError:
        # Fallback for direct script execution inside pipeline dir
        from farmer_registration import register_farmer_from_pin

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
    # Soybean
    "soybean": "Soybean",
    "soya": "Soybean",
    "soyabean": "Soybean",
    "soya bean": "Soybean",
    # Wheat
    "wheat": "Wheat",
    "gehu": "Wheat",
    "gehun": "Wheat",
    "gahu": "Wheat",
    # Rice / Paddy
    "rice": "Rice",
    "paddy": "Rice",
    "dhan": "Rice",
    "chawal": "Rice",
    "tandul": "Rice",
    # Pigeon Pea / Tur / Arhar
    "pigeon pea": "Pigeon Pea",
    "pigeonpea": "Pigeon Pea",
    "tur": "Pigeon Pea",
    "toor": "Pigeon Pea",
    "arhar": "Pigeon Pea",
    "tuvar": "Pigeon Pea",
    # Chickpea / Chana / Gram
    "chickpea": "Chickpea",
    "chana": "Chickpea",
    "gram": "Chickpea",
    "bengal gram": "Chickpea",
    "harbara": "Chickpea",
    # Sugarcane
    "sugarcane": "Sugarcane",
    "sugar cane": "Sugarcane",
    "ganna": "Sugarcane",
    "us": "Sugarcane",
    # Maize / Corn
    "maize": "Maize",
    "corn": "Maize",
    "makka": "Maize",
    "makai": "Maize",
    "bhutta": "Maize",
    # Onion
    "onion": "Onion",
    "pyaz": "Onion",
    "pyaaz": "Onion",
    "kanda": "Onion",
}


def normalize_crop(text: Optional[str]) -> Optional[str]:
    """
    Normalizes a crop string against the supported crop dictionary,
    handling lowercase, extra punctuation, and regional terms.
    """
    if not text:
        return None

    cleaned = re.sub(r"[^\w\s]", "", text.strip().lower())

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

SKIP_KEYWORDS = {"skip", "no", "default", "dont know", "dont know", "none", "na", "n/a", "not sure"}


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


# ==============================================================================
# 4. PRIVACY LOGGING & UTILITIES (RE-EXPORTED FROM common.utils)
# ==============================================================================

# Note: normalize_phone, mask_phone, is_valid_farmer_name, clean_farmer_name,
# and is_affirmative_response are imported from common.utils above and re-exported
# here for backwards compatibility.
__all_utils__ = [
    "normalize_phone",
    "mask_phone",
    "is_valid_farmer_name",
    "clean_farmer_name",
    "is_affirmative_response",
]


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


# ==============================================================================
# 6. DATABASE HELPER FUNCTIONS (SESSIONS & ATOMIC DEDUPLICATION)
# ==============================================================================

def get_db_connection(db_url: Optional[str] = None):
    """Obtains a psycopg2 PostgreSQL connection."""
    url = db_url or os.getenv("DATABASE_URL")
    if not url:
        raise ValueError("DATABASE_URL is not set.")
    return psycopg2.connect(url)


def claim_message(msg_id: str, db_url: Optional[str] = None) -> bool:
    """
    Atomically claims message_id using INSERT ON CONFLICT DO NOTHING.
    Returns True if the message was successfully claimed (new message, row inserted),
    False if it was already processed/claimed (rowcount == 0).
    """
    if not msg_id:
        return True

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
    except psycopg2.Error as e:
        logger.debug("processed_messages claim failed: %s", e)
        # If DB error on deduplication table, allow message through to avoid dropping traffic
        return True


def unclaim_message(msg_id: str, db_url: Optional[str] = None) -> None:
    """
    Deletes the message_id from processed_messages if message handling fails,
    allowing Meta's automatic webhook delivery retry to succeed.
    """
    if not msg_id:
        return

    try:
        conn = get_db_connection(db_url)
        with conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM processed_messages WHERE message_id = %s;", (msg_id,))
                logger.info("Unclaimed message %s after handling failure", msg_id)
    except psycopg2.Error as e:
        logger.error("Failed to unclaim message %s: %s", msg_id, e)


def is_message_processed(msg_id: str, db_url: Optional[str] = None) -> bool:
    """Checks if an incoming message ID has already been claimed/processed."""
    if not msg_id:
        return False

    try:
        conn = get_db_connection(db_url)
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM processed_messages WHERE message_id = %s LIMIT 1;",
                    (msg_id,),
                )
                return cur.fetchone() is not None
    except psycopg2.Error as e:
        logger.debug("processed_messages check skipped/failed: %s", e)
        return False


def mark_message_processed(msg_id: str, db_url: Optional[str] = None) -> None:
    """Records message_id in processed_messages for deduplication."""
    claim_message(msg_id, db_url)


def get_registered_farm(phone: str, db_url: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Checks if a farm is already registered for this phone number in the `farms` table.
    """
    norm_phone = normalize_phone(phone)
    try:
        conn = get_db_connection(db_url)
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, farmer_name, crop_name, farm_area, farm_area_unit
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
                    }
                return None
    except psycopg2.Error as e:
        logger.error("Database query failed in get_registered_farm: %s", e)
        return None


def get_session(phone: str, db_url: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieves active registration session for a phone number."""
    norm_phone = normalize_phone(phone)
    try:
        conn = get_db_connection(db_url)
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT phone, state, name, crop, acreage_acres, updated_at
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
                        "updated_at": row[5],
                    }
                return None
    except psycopg2.Error as e:
        logger.debug("registration_sessions check skipped/failed: %s", e)
        return None


def save_session(
    phone: str,
    state: str,
    name: Optional[str] = None,
    crop: Optional[str] = None,
    acreage_acres: Optional[float] = None,
    db_url: Optional[str] = None,
) -> None:
    """Upserts registration session state."""
    norm_phone = normalize_phone(phone)
    try:
        conn = get_db_connection(db_url)
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO registration_sessions (phone, state, name, crop, acreage_acres, updated_at)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (phone) DO UPDATE SET
                        state = EXCLUDED.state,
                        name = COALESCE(EXCLUDED.name, registration_sessions.name),
                        crop = COALESCE(EXCLUDED.crop, registration_sessions.crop),
                        acreage_acres = COALESCE(EXCLUDED.acreage_acres, registration_sessions.acreage_acres),
                        updated_at = NOW();
                    """,
                    (norm_phone, state, name, crop, acreage_acres),
                )
    except psycopg2.Error as e:
        logger.error("Failed to save session for %s: %s", mask_phone(phone), e)


def clear_session(phone: str, db_url: Optional[str] = None) -> None:
    """Clears a registration session to allow restarting."""
    norm_phone = normalize_phone(phone)
    try:
        conn = get_db_connection(db_url)
        with conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM registration_sessions WHERE phone = %s;", (norm_phone,))
    except psycopg2.Error as e:
        logger.error("Failed to clear session for %s: %s", mask_phone(phone), e)


# ==============================================================================
# 7. INCOMING MESSAGE HANDLER & STATE MACHINE
# ==============================================================================

def handle_incoming(
    message_data: Dict[str, Any],
    contact_name: str = "Farmer",
    db_url: Optional[str] = None,
    outbound_sender=send_text,
) -> Dict[str, Any]:
    """
    Main entry point for handling an incoming WhatsApp message in the registration flow.

    Workflow:
    1. Mask phone in logs.
    2. Check message deduplication via processed_messages.
    3. Check for 'restart' / 'reset' command.
    4. Check if phone is already registered in farms table.
    5. Drive registration state machine:
       - No session -> send WELCOME_PROMPT -> state: AWAITING_NAME
       - AWAITING_NAME -> parse name -> send CROP_PROMPT -> state: AWAITING_CROP
       - AWAITING_CROP -> normalize crop -> send ACREAGE_PROMPT -> state: AWAITING_ACREAGE
       - AWAITING_ACREAGE -> parse acres -> send LOCATION_PROMPT -> state: AWAITING_LOCATION
       - AWAITING_LOCATION -> parse location pin -> validate India bounds ->
                              register_farmer_from_pin -> send REGISTRATION_SUCCESS -> state: REGISTERED
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

    # 1. Atomic Deduplication Claim (INSERT ON CONFLICT DO NOTHING)
    claimed = False
    if msg_id:
        if not claim_message(msg_id, db_url):
            logger.info("Ignoring duplicate message %s from %s", msg_id, masked_mobile)
            return {"status": "duplicate", "message_id": msg_id}
        claimed = True

    try:
        # Extract text content if applicable
        text_content = ""
        if msg_type == "text":
            text_content = message_data.get("text", {}).get("body", "").strip()

        # 2. Reset / Restart handling
        if text_content.lower() in {"restart", "reset"}:
            logger.info("Resetting session for %s", masked_mobile)
            clear_session(sender_mobile, db_url)
            save_session(sender_mobile, "AWAITING_NAME", db_url=db_url)
            outbound_sender(sender_mobile, RESET_SUCCESS)
            return {"status": "session_reset", "next_state": "AWAITING_NAME"}

        # 3. Check if phone already registered in PostGIS farms table
        registered_farm = get_registered_farm(sender_mobile, db_url)
        if registered_farm:
            logger.info("Phone %s is already registered as Farm ID %s", masked_mobile, registered_farm["id"])
            outbound_sender(
                sender_mobile,
                ALREADY_REGISTERED.format(
                    farm_id=registered_farm["id"],
                    name=registered_farm["farmer_name"],
                    crop=registered_farm["crop_name"],
                ),
            )
            return {"status": "already_registered", "farm_id": registered_farm["id"]}

        # 4. Retrieve existing session
        session = get_session(sender_mobile, db_url)

        # Brand new interaction -> Start onboarding
        if session is None:
            logger.info("Initiating new registration session for %s", masked_mobile)
            save_session(sender_mobile, "AWAITING_NAME", db_url=db_url)
            outbound_sender(sender_mobile, WELCOME_PROMPT)
            return {"status": "session_started", "next_state": "AWAITING_NAME"}

        current_state = session.get("state")
        logger.info("Active session for %s in state: %s", masked_mobile, current_state)

        # State: AWAITING_NAME
        if current_state == "AWAITING_NAME":
            if msg_type != "text" or not text_content:
                outbound_sender(sender_mobile, "Please reply with your full name in text.")
                return {"status": "invalid_input", "state": "AWAITING_NAME"}

            if not is_valid_farmer_name(text_content):
                outbound_sender(sender_mobile, "Please enter your actual full name (e.g., Ramesh Patil).")
                return {"status": "invalid_name", "state": "AWAITING_NAME"}

            candidate_name = clean_farmer_name(text_content)
            save_session(sender_mobile, "AWAITING_NAME_CONFIRMATION", name=candidate_name, db_url=db_url)
            outbound_sender(sender_mobile, NAME_CONFIRM_PROMPT.format(name=candidate_name))
            return {
                "status": "name_candidate_received",
                "next_state": "AWAITING_NAME_CONFIRMATION",
                "candidate_name": candidate_name,
            }

        # State: AWAITING_NAME_CONFIRMATION
        elif current_state == "AWAITING_NAME_CONFIRMATION":
            candidate_name = session.get("name") or "Farmer"
            if msg_type != "text" or not text_content:
                outbound_sender(sender_mobile, NAME_CONFIRM_INVALID_PROMPT.format(name=candidate_name))
                return {"status": "invalid_input", "state": "AWAITING_NAME_CONFIRMATION"}

            if is_affirmative_response(text_content):
                save_session(sender_mobile, "AWAITING_CROP", name=candidate_name, db_url=db_url)
                outbound_sender(sender_mobile, CROP_PROMPT.format(name=candidate_name))
                return {"status": "name_confirmed", "next_state": "AWAITING_CROP", "name": candidate_name}

            elif is_valid_farmer_name(text_content):
                new_name = clean_farmer_name(text_content)
                save_session(sender_mobile, "AWAITING_NAME_CONFIRMATION", name=new_name, db_url=db_url)
                outbound_sender(sender_mobile, NAME_CONFIRM_PROMPT.format(name=new_name))
                return {
                    "status": "name_candidate_updated",
                    "next_state": "AWAITING_NAME_CONFIRMATION",
                    "candidate_name": new_name,
                }

            else:
                outbound_sender(sender_mobile, NAME_CONFIRM_INVALID_PROMPT.format(name=candidate_name))
                return {"status": "name_confirmation_required", "state": "AWAITING_NAME_CONFIRMATION"}

        # State: AWAITING_CROP
        elif current_state == "AWAITING_CROP":
            if msg_type != "text" or not text_content:
                outbound_sender(sender_mobile, CROP_INVALID_PROMPT)
                return {"status": "invalid_input", "state": "AWAITING_CROP"}

            crop = normalize_crop(text_content)
            if not crop:
                outbound_sender(sender_mobile, CROP_INVALID_PROMPT)
                return {"status": "crop_unrecognized", "state": "AWAITING_CROP"}

            save_session(sender_mobile, "AWAITING_ACREAGE", crop=crop, db_url=db_url)
            outbound_sender(sender_mobile, ACREAGE_PROMPT.format(crop=crop))
            return {"status": "crop_saved", "next_state": "AWAITING_ACREAGE", "crop": crop}

        # State: AWAITING_ACREAGE
        elif current_state == "AWAITING_ACREAGE":
            if msg_type != "text" or not text_content:
                outbound_sender(sender_mobile, ACREAGE_INVALID_PROMPT)
                return {"status": "invalid_input", "state": "AWAITING_ACREAGE"}

            is_valid, acres = parse_acreage(text_content)
            if not is_valid:
                outbound_sender(sender_mobile, ACREAGE_INVALID_PROMPT)
                return {"status": "acreage_invalid", "state": "AWAITING_ACREAGE"}

            acreage_str = f"{acres:.2f} acres" if acres is not None else "Standard default (~2.5 acres / 1 ha)"
            save_session(sender_mobile, "AWAITING_LOCATION", acreage_acres=acres, db_url=db_url)
            outbound_sender(sender_mobile, LOCATION_PROMPT.format(acreage_str=acreage_str))
            return {
                "status": "acreage_saved",
                "next_state": "AWAITING_LOCATION",
                "acreage_acres": acres,
            }

        # State: AWAITING_LOCATION
        elif current_state == "AWAITING_LOCATION":
            if msg_type != "location":
                outbound_sender(sender_mobile, LOCATION_INVALID_PROMPT)
                return {"status": "location_required", "state": "AWAITING_LOCATION"}

            loc = message_data.get("location", {})
            lat = loc.get("latitude")
            lon = loc.get("longitude")

            if lat is None or lon is None:
                outbound_sender(sender_mobile, LOCATION_INVALID_PROMPT)
                return {"status": "invalid_coordinates", "state": "AWAITING_LOCATION"}

            try:
                lat = float(lat)
                lon = float(lon)
            except (ValueError, TypeError):
                outbound_sender(sender_mobile, LOCATION_INVALID_PROMPT)
                return {"status": "invalid_coordinates", "state": "AWAITING_LOCATION"}

            # Validate bounding box for India
            if not validate_india_bounds(lat, lon):
                logger.warning("Coordinates (%s, %s) outside India for %s", lat, lon, masked_mobile)
                outbound_sender(sender_mobile, LOCATION_OUT_OF_BOUNDS_PROMPT)
                return {"status": "location_out_of_bounds", "state": "AWAITING_LOCATION"}

            # Perform registration
            farmer_name = session.get("name") or contact_name
            crop_name = session.get("crop") or "Cotton"
            farm_area_acres = session.get("acreage_acres")

            logger.info(
                "Registering new farm for %s: %s, crop=%s, acres=%s, lat=%s, lon=%s",
                masked_mobile,
                farmer_name,
                crop_name,
                farm_area_acres,
                lat,
                lon,
            )

            try:
                reg_result = register_farmer_from_pin(
                    farmer_name=farmer_name,
                    mobile_number=sender_mobile,
                    lat=lat,
                    lon=lon,
                    crop_name=crop_name,
                    farm_area_acres=farm_area_acres,
                    db_url=db_url,
                    boundary_source="estimated_from_pin",
                    area_source="farmer_stated" if farm_area_acres is not None else "default",
                )

                farm_id = reg_result["farm_id"]
                final_area = reg_result.get("farm_area") or (farm_area_acres if farm_area_acres is not None else 2.47)
                boundary_source = reg_result.get("boundary_source", "estimated_from_pin")

                # Update session state to REGISTERED
                save_session(sender_mobile, "REGISTERED", db_url=db_url)

                # Send registration success confirmation
                success_text = REGISTRATION_SUCCESS.format(
                    farm_id=farm_id,
                    name=farmer_name,
                    crop=crop_name,
                    area=float(final_area),
                    boundary_source=boundary_source,
                    lat=lat,
                    lon=lon,
                )
                outbound_sender(sender_mobile, success_text)

                return {
                    "status": "registration_complete",
                    "farm_id": farm_id,
                    "farmer_name": farmer_name,
                    "crop_name": crop_name,
                    "area_acres": float(final_area),
                    "lat": lat,
                    "lon": lon,
                }

            except Exception as e:
                logger.error("Error during register_farmer_from_pin for %s: %s", masked_mobile, e)
                if claimed and msg_id:
                    unclaim_message(msg_id, db_url)
                outbound_sender(sender_mobile, ERROR_GENERIC)
                return {"status": "error", "message": str(e)}

        # State: REGISTERED (or unknown fallback)
        else:
            outbound_sender(
                sender_mobile,
                ALREADY_REGISTERED.format(
                    farm_id=session.get("name") or "Your Farm",
                    name=session.get("name") or "Farmer",
                    crop=session.get("crop") or "Registered Crop",
                ),
            )
            return {"status": "already_registered", "state": current_state}

    except Exception as e:
        if claimed and msg_id:
            unclaim_message(msg_id, db_url)
        raise
