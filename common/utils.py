#!/usr/bin/env python3
"""
KhetSense AI — Common Utility Functions
Independent shared utilities with zero dependencies on pipeline or whatsapp packages.
"""

import re
import unicodedata
from typing import Optional


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
    "राम राम", "नमस्कार", "नमस्ते", "प्रणाम", "शुरू"
}

GREETING_PREFIXES = (
    "hi ", "hello ", "hey ", "namaste ", "i want to", "hi, i want",
    "hello, i want", "please register", "want to register", "namaskar ",
    "राम राम", "नमस्कार ", "नमस्ते ", "प्रणाम "
)

AFFIRMATIVE_RESPONSES = {
    "yes", "y", "haan", "ha", "ho", "हाँ", "हो", "yes please",
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
