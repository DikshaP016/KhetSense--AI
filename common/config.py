#!/usr/bin/env python3
"""
KhetSense AI — Central Configuration for Decision Engine & Guardrails

Rainfall Policy Thresholds & Source:
- R2 (15.0 mm): Derived from India Meteorological Department (IMD) rainfall intensity
  classes (24 h categories: Moderate rain begins at 15.6 mm / day; adapted to 15.0 mm
  over a 48 h window for operational farm scheduling).
- R1 (5.0 mm): Ineffective-rainfall cutoff following irrigation-scheduling practice
  and the concept of effective rainfall per Dastane (1978), FAO Irrigation and Drainage
  Paper 25, "Effective rainfall in irrigated agriculture". Small rain events (< 5 mm)
  are largely lost to canopy interception and surface evaporation in dry soil, failing
  to penetrate the crop root zone.
- Thresholds adapted by the author to a 48 h forecast total; provisional.
"""

import os
import hmac
import hashlib
from dataclasses import dataclass
from typing import Optional, Set, Tuple


@dataclass(frozen=True)
class DataFreshnessConfig:
    # Maximum acceptable age for optical Sentinel-2 scenes (in days)
    MAX_SENTINEL2_AGE_DAYS: int = int(os.getenv("MAX_SENTINEL2_AGE_DAYS", "14"))
    # Maximum acceptable age for microwave radiometric SMAP observations (in days)
    MAX_SMAP_AGE_DAYS: int = int(os.getenv("MAX_SMAP_AGE_DAYS", "5"))
    # Minimum required 3-hour forecast slices covering 48 hours
    MIN_FORECAST_SLICES: int = int(os.getenv("MIN_FORECAST_SLICES", "16"))
    # Forecast horizon window (in hours)
    FORECAST_WINDOW_HOURS: int = int(os.getenv("FORECAST_WINDOW_HOURS", "48"))


FRESHNESS_CONFIG = DataFreshnessConfig()


@dataclass(frozen=True)
class RainfallPolicyConfig:
    # Rainfall thresholds over the forecast window (in mm)
    R1: float = 5.0   # Light/ineffective rainfall boundary (< R1 has negligible root infiltration)
    R2: float = 15.0  # Sufficient/heavy rainfall boundary (>= R2 provides substantial soil recharge)

    # Forecast time horizon
    FORECAST_HOURS: int = 48
    FORECAST_INTERVAL_HOURS: int = 3

    # Derived number of 3-hour slices (e.g. 48 // 3 = 16 slices)
    @property
    def FORECAST_SLICES(self) -> int:
        return self.FORECAST_HOURS // self.FORECAST_INTERVAL_HOURS

    # Provenance and scientific citations
    SOURCE: str = (
        "R2: IMD rainfall intensity classes (India Meteorological Department, 24 h categories). "
        "R1: ineffective-rainfall cutoff after common irrigation-scheduling practice; concept of "
        "effective rainfall per Dastane (1978), FAO Irrigation and Drainage Paper, 'Effective "
        "rainfall in irrigated agriculture'. Thresholds adapted by the author to a 48 h forecast "
        "total; provisional."
    )


# Recommended action strings (consistent system-wide)
ACTION_IRRIGATE_NOW = "irrigate now"
ACTION_IRRIGATE_LIGHTLY = "irrigate lightly, rain may not suffice"
ACTION_SCHEDULE_IRRIGATION = "schedule irrigation in 24-48h"
ACTION_DELAY_RECHECK = "delay, re-check after rain"
ACTION_HOLD_RECHECK = "hold, re-check after rain"
ACTION_NO_ACTION = "no action"
ACTION_INSUFFICIENT_DATA = "insufficient data"

# Singleton configuration instance
RAINFALL_CONFIG = RainfallPolicyConfig()


# ==============================================================================
# WHATSAPP SECURITY & INTEGRATION TEST CONFIGURATION (Phase 6H)
# ==============================================================================

def is_outbound_whatsapp_enabled() -> bool:
    """Explicit master kill-switch for outbound Meta WhatsApp Cloud API requests. Defaults to False."""
    return (os.getenv("ENABLE_OUTBOUND_WHATSAPP") or "false").strip().lower() == "true"


def is_auto_advisory_on_registration_enabled() -> bool:
    """Controls whether completing farmer registration automatically sends an advisory card. Defaults to False."""
    return (os.getenv("AUTO_DISPATCH_ADVISORY_ON_REGISTRATION") or "false").strip().lower() == "true"


def is_whatsapp_allowlist_enabled() -> bool:
    """Controls whether inbound WhatsApp messages are restricted to an explicit sender allowlist. Defaults to False."""
    return (os.getenv("WHATSAPP_ALLOWLIST_ENABLED") or "false").strip().lower() == "true"


def _normalize_allowlist_phone(phone: Optional[str]) -> str:
    """Normalizes phone numbers to standard Meta E.164 digits format (91XXXXXXXXXX)."""
    if not phone:
        return ""
    digits = "".join(ch for ch in str(phone) if ch.isdigit())
    if len(digits) == 10 and digits[0] in "6789":
        digits = "91" + digits
    elif len(digits) == 11 and digits.startswith("0"):
        digits = "91" + digits[1:]
    return digits


def get_allowed_sender_numbers() -> Set[str]:
    """Retrieves and normalizes the set of authorized recipient phone numbers."""
    raw = os.getenv("WHATSAPP_ALLOWED_NUMBERS") or ""
    allowed: Set[str] = set()
    for item in raw.split(","):
        cleaned = item.strip()
        if cleaned:
            norm = _normalize_allowlist_phone(cleaned)
            if norm:
                allowed.add(norm)
    return allowed


def is_sender_allowed(phone: Optional[str]) -> bool:
    """
    Checks if a sender phone number is permitted to interact with KhetSense.
    - If allowlisting is disabled (default): allows any non-empty valid phone number.
    - If allowlisting is enabled: checks normalized phone against normalized allowlist.
    - Denies empty, None, or unparseable phone numbers.
    """
    if not phone:
        return False

    norm = _normalize_allowlist_phone(phone)
    if not norm:
        return False

    if not is_whatsapp_allowlist_enabled():
        return True

    allowed_set = get_allowed_sender_numbers()
    return norm in allowed_set


def verify_meta_signature(
    raw_body: bytes,
    signature_header: Optional[str],
    app_secret: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Validates Meta Cloud API X-Hub-Signature-256 HMAC-SHA256 signature against raw request body.
    - Uses constant-time comparison (hmac.compare_digest).
    - Fails closed if app_secret is unconfigured, empty, or None.
    - Rejects missing or malformed signature headers.
    - Never logs or exposes the app_secret.
    """
    secret = app_secret if app_secret is not None else os.getenv("META_APP_SECRET")
    if not secret or secret.strip() == "":
        return False, "META_APP_SECRET is not configured; failing closed"

    if not signature_header:
        return False, "Missing X-Hub-Signature-256 header"

    clean_header = signature_header.strip()
    prefix = "sha256="
    if not clean_header.startswith(prefix):
        return False, "Malformed X-Hub-Signature-256 header format (expected 'sha256=<hex>')"

    expected_sig = clean_header[len(prefix):].strip()
    if not expected_sig:
        return False, "Empty signature digest in X-Hub-Signature-256 header"

    calculated_sig = hmac.new(
        secret.strip().encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_sig.lower(), calculated_sig.lower()):
        return False, "Invalid signature: HMAC-SHA256 mismatch"

    return True, "Signature verified"


# Default maximum request body size for WhatsApp webhooks (512 KB)
DEFAULT_MAX_WEBHOOK_BODY_BYTES: int = 512 * 1024


def get_max_webhook_body_bytes() -> int:
    """
    Returns the maximum permitted webhook request body size in bytes.
    Configurable via MAX_WEBHOOK_BODY_BYTES environment variable (defaults to 512 KB).
    """
    raw = os.getenv("MAX_WEBHOOK_BODY_BYTES")
    if raw:
        try:
            val = int(raw.strip())
            if val > 0:
                return val
        except ValueError:
            pass
    return DEFAULT_MAX_WEBHOOK_BODY_BYTES


def is_crop_validation_enabled() -> bool:
    """Controls whether satellite-based crop validation and discrepancy screening is active. Defaults to True."""
    return (os.getenv("ENABLE_CROP_VALIDATION") or "true").strip().lower() == "true"


def is_ml_advisory_enabled() -> bool:
    """Controls whether machine learning inference assists active advisory generation. Defaults to True."""
    return (os.getenv("ENABLE_ML_ADVISORY") or "true").strip().lower() == "true"



