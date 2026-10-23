#!/usr/bin/env python3
"""
KhetSense AI — Multilingual WhatsApp Message Templates & Localization Engine

Supports:
- English ('en')
- Marathi ('mr')
- Hindi ('hi')

Provides:
- Legacy string constants for backwards compatibility.
- Comprehensive localized message dictionary MESSAGES.
- Localized crop dictionary LOCALIZED_CROPS.
- Multilingual irrigation advisory templates ADVISORY_TEMPLATES.
- Helper functions: get_message, get_localized_crop, get_localized_advisory,
  parse_language_choice, normalize_language.
"""

from typing import Dict, Any, Optional, List, Tuple
import os
import re

# ==============================================================================
# 1. LANGUAGE CODES & NORMALIZATION
# ==============================================================================

SUPPORTED_LANGUAGES = {"en", "mr", "hi"}
DEFAULT_LANGUAGE = "en"

LANGUAGE_LABELS: Dict[str, str] = {
    "en": "English",
    "mr": "मराठी (Marathi)",
    "hi": "हिंदी (Hindi)",
}


def normalize_language(lang: Optional[str]) -> str:
    """Normalizes a language code to 'en', 'mr', or 'hi'. Defaults to 'en'."""
    if not lang:
        return DEFAULT_LANGUAGE
    code = str(lang).strip().lower()
    if code in SUPPORTED_LANGUAGES:
        return code
    return DEFAULT_LANGUAGE


def parse_language_choice(text: Optional[str]) -> Optional[str]:
    """
    Parses user input into a supported language code ('en', 'mr', 'hi').
    Accepts numbers ('1', '2', '3') or text names in English, Marathi, or Hindi.
    Returns None if the input does not match any supported language.
    """
    if not text:
        return None

    cleaned = text.strip().lower()

    # Exact numeric choices
    if cleaned in {"1", "1.", "1)"}:
        return "en"
    if cleaned in {"2", "2.", "2)"}:
        return "mr"
    if cleaned in {"3", "3.", "3)"}:
        return "hi"

    # Word-based checks
    # English variations
    if cleaned in {"english", "en", "eng", "इंग्लिश", "इंग्रजी", "angrezi", "angreji"}:
        return "en"
    # Marathi variations
    if cleaned in {"marathi", "mr", "मराठी", "maratha"}:
        return "mr"
    # Hindi variations
    if cleaned in {"hindi", "hi", "hin", "हिंदी", "हिन्दी"}:
        return "hi"

    # Substring checks (e.g., "choose english", "select 2")
    if "english" in cleaned or "इंग्रजी" in cleaned:
        return "en"
    if "marathi" in cleaned or "मराठी" in cleaned:
        return "mr"
    if "hindi" in cleaned or "हिंदी" in cleaned or "हिन्दी" in cleaned:
        return "hi"

    return None


# ==============================================================================
# 2. LOCALIZED CROPS
# ==============================================================================

LOCALIZED_CROPS: Dict[str, Dict[str, str]] = {
    "Cotton": {
        "en": "Cotton",
        "mr": "कापूस (Cotton)",
        "hi": "कपास (Cotton)",
    },
    "Soybean": {
        "en": "Soybean",
        "mr": "सोयाबीन (Soybean)",
        "hi": "सोयाबीन (Soybean)",
    },
    "Wheat": {
        "en": "Wheat",
        "mr": "गहू (Wheat)",
        "hi": "गेहूं (Wheat)",
    },
    "Rice": {
        "en": "Rice",
        "mr": "तांदूळ / भात (Rice)",
        "hi": "चावल / धान (Rice)",
    },
    "Pigeon Pea": {
        "en": "Pigeon Pea",
        "mr": "तूर (Tur)",
        "hi": "अरहर / तुअर (Pigeon Pea)",
    },
    "Chickpea": {
        "en": "Chickpea",
        "mr": "हरभरा (Chana)",
        "hi": "चना (Chickpea)",
    },
    "Sugarcane": {
        "en": "Sugarcane",
        "mr": "ऊस (Sugarcane)",
        "hi": "गन्ना (Sugarcane)",
    },
    "Maize": {
        "en": "Maize",
        "mr": "मका (Maize)",
        "hi": "मक्का (Maize)",
    },
    "Onion": {
        "en": "Onion",
        "mr": "कांदा (Onion)",
        "hi": "प्याज (Onion)",
    },
}


def get_localized_crop(crop_name: Optional[str], lang: str = DEFAULT_LANGUAGE) -> str:
    """Returns the localized display name for a supported crop."""
    if not crop_name:
        return "Crop" if lang == "en" else ("पीक" if lang == "mr" else "फसल")
    code = normalize_language(lang)
    for std_crop, translations in LOCALIZED_CROPS.items():
        if std_crop.lower() == crop_name.lower():
            return translations.get(code, std_crop)
    return crop_name


# ==============================================================================
# 3. CONVERSATIONAL MESSAGE TEMPLATES (MESSAGES)
# ==============================================================================

MESSAGES: Dict[str, Dict[str, str]] = {
    "welcome_and_language": {
        "en": (
            "Welcome to KhetSense AI! 🌱\n\n"
            "Please choose your preferred language:\n\n"
            "1. English\n"
            "2. मराठी (Marathi)\n"
            "3. हिन्दी (Hindi)\n\n"
            "Please reply with 1, 2 or 3."
        ),
        "mr": (
            "खेतसेन्स (KhetSense AI) मध्ये आपले स्वागत आहे! 🌱\n\n"
            "कृपया तुमची पसंतीची भाषा निवडा:\n\n"
            "1. English\n"
            "2. मराठी (Marathi)\n"
            "3. हिन्दी (Hindi)\n\n"
            "कृपया 1, 2 किंवा 3 उत्तर पाठवा."
        ),
        "hi": (
            "खेतसेंस (KhetSense AI) में आपका स्वागत है! 🌱\n\n"
            "कृपया अपनी पसंदीदा भाषा चुनें:\n\n"
            "1. English\n"
            "2. मराठी (Marathi)\n"
            "3. हिन्दी (Hindi)\n\n"
            "कृपया 1, 2 या 3 लिखकर भेजें।"
        ),
    },
    "language_confirmed": {
        "en": (
            "Language set to English! 🌱\n\n"
            "Let's get your farm registered in just a few steps.\n\n"
            "What is your full name?"
        ),
        "mr": (
            "भाषा मराठी म्हणून सेट केली आहे! 🌱\n\n"
            "चला काही सोप्या चरणांमध्ये तुमच्या शेताची नोंदणी करूया.\n\n"
            "तुमचे पूर्ण नाव काय आहे?"
        ),
        "hi": (
            "भाषा हिंदी सेट की गई है! 🌱\n\n"
            "आइए कुछ आसान चरणों में आपके खेत का पंजीकरण करें।\n\n"
            "आपका पूरा नाम क्या है?"
        ),
    },
    "language_invalid": {
        "en": (
            "Please reply with a valid option:\n"
            "1. English\n"
            "2. मराठी (Marathi)\n"
            "3. हिंदी (Hindi)\n\n"
            "Send 1, 2, or 3."
        ),
        "mr": (
            "कृपया योग्य पर्याय निवडा:\n"
            "1. English\n"
            "2. मराठी\n"
            "3. हिंदी\n\n"
            "1, 2 किंवा 3 पाठवा."
        ),
        "hi": (
            "कृपया सही विकल्प चुनें:\n"
            "1. English\n"
            "2. मराठी\n"
            "3. हिंदी\n\n"
            "1, 2 या 3 भेजें।"
        ),
    },
    "language_change_prompt": {
        "en": (
            "Select your preferred language:\n\n"
            "1. English\n"
            "2. मराठी (Marathi)\n"
            "3. हिंदी (Hindi)\n\n"
            "Reply with 1, 2, or 3."
        ),
        "mr": (
            "तुमची पसंतीची भाषा निवडा:\n\n"
            "1. English\n"
            "2. मराठी (Marathi)\n"
            "3. हिंदी (Hindi)\n\n"
            "कृपया 1, 2 किंवा 3 उत्तर पाठवा."
        ),
        "hi": (
            "अपनी पसंदीदा भाषा चुनें:\n\n"
            "1. English\n"
            "2. मराठी (Marathi)\n"
            "3. हिंदी (Hindi)\n\n"
            "कृपया 1, 2 या 3 लिखकर भेजें।"
        ),
    },
    "language_updated": {
        "en": "Your preferred language has been updated to English. 🌱",
        "mr": "तुमची भाषा यशस्वीरीत्या मराठी म्हणून सेट केली आहे. 🌱",
        "hi": "आपकी भाषा सफलतापूर्वक हिंदी में बदल दी गई है। 🌱",
    },
    "name_prompt": {
        "en": "What is your full name?",
        "mr": "तुमचे पूर्ण नाव काय आहे?",
        "hi": "आपका पूरा नाम क्या है?",
    },
    "name_confirm": {
        "en": (
            "Is your name {name}?\n\n"
            "Reply YES to confirm, or send your name again."
        ),
        "mr": (
            "तुमचे नाव {name} आहे का?\n\n"
            "पुष्टी करण्यासाठी 'हो' (YES) पाठवा, किंवा तुमचे नाव पुन्हा पाठवा."
        ),
        "hi": (
            "क्या आपका नाम {name} है?\n\n"
            "पुष्टि के लिए 'हाँ' (YES) भेजें, या अपना नाम दोबारा भेजें।"
        ),
    },
    "name_confirm_invalid": {
        "en": "Please reply YES if your name is {name}, or send your full name again.",
        "mr": "तुमचे नाव {name} असल्यास कृपया 'हो' (YES) पाठवा, किंवा तुमचे पूर्ण नाव पुन्हा पाठवा.",
        "hi": "यदि आपका नाम {name} है तो कृपया 'हाँ' (YES) भेजें, या अपना पूरा नाम फिर से भेजें।",
    },
    "crop_prompt": {
        "en": (
            "Thanks, {name}!\n\n"
            "What crop are you growing on your farm?\n\n"
            "Supported crops:\n"
            "• Cotton (कपास / Kapas)\n"
            "• Soybean (सोयाबीन)\n"
            "• Wheat (गेहूं / Gehu)\n"
            "• Rice (चावल / Dhan)\n"
            "• Pigeon Pea (तुवर / Tur)\n"
            "• Chickpea (चना / Chana)\n"
            "• Sugarcane (गन्ना / Ganna)\n"
            "• Maize (मक्का / Makka)\n"
            "• Onion (प्याज / Pyaz)\n\n"
            "Please reply with your crop name."
        ),
        "mr": (
            "धन्यवाद, {name}!\n\n"
            "तुम्ही तुमच्या शेतात कोणते पीक घेत आहात?\n\n"
            "समर्थित पिके:\n"
            "• कापूस (Cotton / Kapas)\n"
            "• सोयाबीन (Soybean)\n"
            "• गहू (Wheat / Gehu)\n"
            "• तांदूळ / भात (Rice / Dhan)\n"
            "• तूर (Tur / Toor)\n"
            "• हरभरा (Chana / Gram)\n"
            "• ऊस (Sugarcane / Ganna)\n"
            "• मका (Maize / Makka)\n"
            "• कांदा (Onion / Pyaz)\n\n"
            "कृपया तुमच्या पिकाचे नाव पाठवा."
        ),
        "hi": (
            "धन्यवाद, {name}!\n\n"
            "आप अपने खेत में कौन सी फसल उगा रहे हैं?\n\n"
            "समर्थित फसलें:\n"
            "• कपास (Cotton / Kapas)\n"
            "• सोयाबीन (Soybean)\n"
            "• गेहूं (Wheat / Gehu)\n"
            "• चावल / धान (Rice / Dhan)\n"
            "• अरहर / तुअर (Tur / Arhar)\n"
            "• चना (Chickpea / Chana)\n"
            "• गन्ना (Sugarcane / Ganna)\n"
            "• मक्का (Maize / Makka)\n"
            "• प्याज (Onion / Pyaz)\n\n"
            "कृपया अपनी फसल का नाम लिखकर भेजें।"
        ),
    },
    "crop_invalid": {
        "en": (
            "Sorry, we couldn't recognize that crop. 🌱\n\n"
            "Please choose one of our supported crops:\n"
            "Cotton, Soybean, Wheat, Rice, Pigeon Pea (Tur), Chickpea (Chana), "
            "Sugarcane, Maize, or Onion."
        ),
        "mr": (
            "माफ करा, ते पीक ओळखता आले नाही. 🌱\n\n"
            "कृपया आमच्या समर्थित पिकांपैकी एक निवडा:\n"
            "कापूस, सोयाबीन, गहू, तांदूळ/भात, तूर, हरभरा, ऊस, मका, किंवा कांदा."
        ),
        "hi": (
            "क्षमा करें, हम उस फसल को पहचान नहीं सके। 🌱\n\n"
            "कृपया समर्थित फसलों में से एक चुनें:\n"
            "कपास, सोयाबीन, गेहूं, चावल/धान, अरहर/तुअर, चना, गन्ना, मक्का, या प्याज।"
        ),
    },
    "acreage_prompt": {
        "en": (
            "Great! Crop set to {crop}.\n\n"
            "How large is your farm in acres? (e.g., 2.5 or 5)\n\n"
            "If you're not sure, reply 'skip' to use our standard default "
            "(2.5 acres / 1.0 hectare)."
        ),
        "mr": (
            "छान! पीक {crop} सेट केले आहे.\n\n"
            "तुमचे शेत किती एकर आहे? (उदा. 2.5 किंवा 5)\n\n"
            "माहित नसल्यास, प्रमाणभूत आकार (2.5 एकर / 1.0 हेक्टर) वापरण्यासाठी 'skip' पाठवा."
        ),
        "hi": (
            "बहुत बढ़िया! फसल {crop} सेट की गई।\n\n"
            "आपका खेत कितने एकड़ का है? (उदा. 2.5 या 5)\n\n"
            "यदि निश्चित नहीं हैं, तो मानक आकार (2.5 एकड़ / 1.0 हेक्टेयर) उपयोग करने के लिए 'skip' भेजें।"
        ),
    },
    "acreage_invalid": {
        "en": (
            "Please enter a valid farm size in acres between 0.1 and 50.0 (e.g., 2.5), "
            "or reply 'skip' to use the default."
        ),
        "mr": (
            "कृपया 0.1 ते 50.0 एकर दरम्यान योग्य क्षेत्रफळ टाका (उदा. 2.5), "
            "किंवा डिफॉल्ट वापरण्यासाठी 'skip' पाठवा."
        ),
        "hi": (
            "कृपया 0.1 से 50.0 एकड़ के बीच एक मान्य आकार दर्ज करें (उदा. 2.5), "
            "या डिफ़ॉल्ट आकार के लिए 'skip' भेजें।"
        ),
    },
    "location_choice_prompt": {
        "en": (
            "Got it: {acreage_str}. 📍\n\n"
            "How would you like to share your farm location?\n\n"
            "1. I am currently at my farm (share your current WhatsApp location pin)\n"
            "2. I am not at my farm (select or drop a pin on the map / forward a pin from the farm)\n\n"
            "Please reply with 1 or 2."
        ),
        "mr": (
            "नोंद घेतली: {acreage_str}. 📍\n\n"
            "तुमच्या शेताचे स्थान (लोकेशन) कसे निवडायचे आहे?\n\n"
            "1. मी सध्या शेतावरच आहे (तुमचे चालू स्थान पाठवा)\n"
            "2. मी शेतावर नाही आहे (नकाशावरून शेताचे स्थान निवडा किंवा फॉरवर्ड केलेले पिन पाठवा)\n\n"
            "कृपया 1 किंवा 2 उत्तर पाठवा."
        ),
        "hi": (
            "दर्ज किया: {acreage_str}। 📍\n\n"
            "आप अपने खेत का स्थान (लोकेशन) कैसे चुनना चाहते हैं?\n\n"
            "1. मैं अभी खेत पर ही हूँ (अपनी वर्तमान लोकेशन भेजें)\n"
            "2. मैं अभी खेत पर नहीं हूँ (नक्शे पर खेत का स्थान चुनें या फॉरवर्ड किया गया पिन भेजें)\n\n"
            "कृपया 1 या 2 लिखकर भेजें।"
        ),
    },
    "location_choice_returning_prompt": {
        "en": (
            "Welcome back, {name}! For your farm #{farm_id} ({crop}):\n\n"
            "We have your previously saved farm location (Lat {lat:.4f}, Lon {lon:.4f}).\n\n"
            "1. Keep current saved farm location\n"
            "2. I am currently at my farm (share current pin)\n"
            "3. I am not at my farm (select or drop a pin on the map)\n\n"
            "Please reply with 1, 2, or 3."
        ),
        "mr": (
            "पुन्हा स्वागत आहे, {name}! शेत आयडी: #{farm_id} ({crop}):\n\n"
            "आमच्याकडे तुमचे आधीचे सेव्ह केलेले शेताचे स्थान आहे (अक्षांश {lat:.4f}, रेखांश {lon:.4f}).\n\n"
            "1. आधीचेच सेव्ह केलेले स्थान वापरा\n"
            "2. मी सध्या शेतावर आहे (नवीन चालू स्थान पाठवा)\n"
            "3. मी शेतावर नाही आहे (नकाशावरून नवीन स्थान निवडा)\n\n"
            "कृपया 1, 2 किंवा 3 उत्तर पाठवा."
        ),
        "hi": (
            "वापसी पर स्वागत है, {name}! फार्म आईडी: #{farm_id} ({crop}):\n\n"
            "हमारे पास आपके खेत का पहले से सहेजा गया स्थान है (अक्षांश {lat:.4f}, देशांतर {lon:.4f})।\n\n"
            "1. पहले से सहेजा गया स्थान ही रखें\n"
            "2. मैं अभी खेत पर हूँ (वर्तमान लोकेशन भेजें)\n"
            "3. मैं अभी खेत पर नहीं हूँ (नक्शे से नया स्थान चुनें)\n\n"
            "कृपया 1, 2 या 3 लिखकर भेजें।"
        ),
    },
    "location_at_farm_prompt": {
        "en": (
            "You selected: I am currently at my farm. 📍\n\n"
            "Please share your current WhatsApp location pin:\n"
            "1. Tap the attachment (+) icon\n"
            "2. Select 'Location'\n"
            "3. Tap 'Send your current location'\n\n"
            "⚠️ Use this only if you are physically standing at your farm."
        ),
        "mr": (
            "तुम्ही निवडले: मी सध्या शेतावरच आहे. 📍\n\n"
            "कृपया तुमचे चालू व्हॉट्सॲप लोकेशन पाठवा:\n"
            "1. अटॅचमेंट (+) चिन्हावर टॅप करा\n"
            "2. 'Location' निवडा\n"
            "3. 'Send your current location' वर टॅप करा\n\n"
            "⚠️ कृपया ही निवड फक्त तुम्ही स्वतः प्रत्यक्ष शेतात असतानाच करा."
        ),
        "hi": (
            "आपने चुना: मैं अभी खेत पर ही हूँ। 📍\n\n"
            "कृपया अपनी वर्तमान व्हाट्सएप लोकेशन भेजें:\n"
            "1. अटैचमेंट (+) आइकन पर टैप करें\n"
            "2. 'Location' चुनें\n"
            "3. 'Send your current location' पर टैप करें\n\n"
            "⚠️ इसका उपयोग केवल तभी करें जब आप वास्तव में अपने खेत पर मौजूद हों।"
        ),
    },
    "location_away_prompt": {
        "en": (
            "You selected: I am not at my farm. 📍\n\n"
            "Share your farm location using a WhatsApp location pin, Google Maps link, or typed address:\n"
            "1. WhatsApp Location: Tap attachment (+) > 'Location' > drop a pin on your farm field\n"
            "2. Google Maps link: Paste a Google Maps share link or URL\n"
            "3. Typed address: Send village, taluka, or district name (e.g., 'Baramati, Pune' or 'Akola, Maharashtra')\n"
            "(For demonstration without owning a farm, you can also reply 'demo')"
        ),
        "mr": (
            "तुम्ही निवडले: मी शेतावर नाही आहे. 📍\n\n"
            "तुमच्या शेताचे स्थान व्हॉट्सॲप लोकेशन पिन, गुगल मॅप्स लिंक किंवा पत्ता टाईप करून पाठवा:\n"
            "1. व्हॉट्सॲप लोकेशन: अटॅचमेंट (+) > 'Location' निवडून शेतावर पिन ठेवा\n"
            "2. गुगल मॅप्स लिंक: गुगल मॅप्सची शेअर लिंक पाठवा\n"
            "3. पत्ता टाईप करा: गाव, तालुका किंवा जिल्ह्याचे नाव पाठवा (उदा. 'बारामती, पुणे' किंवा 'अकोला')\n"
            "(शेत नसताना प्रात्यक्षिकासाठी तुम्ही 'demo' असेही पाठवू शकता)"
        ),
        "hi": (
            "आपने चुना: मैं अभी खेत पर नहीं हूँ। 📍\n\n"
            "अपने खेत का स्थान व्हाट्सएप लोकेशन पिन, गूगल मैप्स लिंक, या पता लिखकर साझा करें:\n"
            "1. व्हाट्सएप लोकेशन: अटैचमेंट (+) > 'Location' चुनकर खेत पर पिन लगाएं\n"
            "2. गूगल मैप्स लिंक: गूगल मैप्स शेयर लिंक पेस्ट करें\n"
            "3. पता लिखें: गांव, तहसील या जिले का नाम भेजें (जैसे 'बारामती, पुणे' या 'अकोला')\n"
            "(बिना खेत के प्रदर्शन के लिए आप 'demo' भी भेज सकते हैं)"
        ),
    },
    "location_confirm_prompt": {
        "en": (
            "Please confirm that the location you shared is your farm: 📍\n\n"
            "{location_line}"
            "Coordinates: Lat {lat:.5f}, Lon {lon:.5f}\n\n"
            "KhetSense AI uses this location to check your crop's condition and prepare irrigation advice.\n\n"
            "Reply YES to confirm and proceed, or NO to choose a different location."
        ),
        "mr": (
            "कृपया खात्री करा: आपण पाठवलेले स्थान हेच तुमचे शेत आहे का? 📍\n\n"
            "{location_line}"
            "स्थान: अक्षांश {lat:.5f}, रेखांश {lon:.5f}\n\n"
            "खेतसेन्स या स्थानाचा वापर पिकाची स्थिती तपासण्यासाठी आणि सिंचन सल्ला तयार करण्यासाठी करते.\n\n"
            "पुष्टी करण्यासाठी 'हो' (YES) पाठवा, किंवा दुसरे स्थान पाठवण्यासाठी 'नाही' (NO) पाठवा."
        ),
        "hi": (
            "कृपया पुष्टि करें कि आपके द्वारा भेजा गया स्थान आपका खेत है: 📍\n\n"
            "{location_line}"
            "स्थान: अक्षांश {lat:.5f}, देशांतर {lon:.5f}\n\n"
            "खेतसेंस इस स्थान का उपयोग फसल की स्थिति जांचने और सिंचाई सलाह तैयार करने के लिए करता है।\n\n"
            "पुष्टि के लिए 'हाँ' (YES) भेजें, या अन्य स्थान चुनने के लिए 'नहीं' (NO) भेजें।"
        ),
    },
    "location_reenter_prompt": {
        "en": (
            "Location not confirmed. 📍\n\n"
            "Share your farm location using a WhatsApp location pin, Google Maps link, or typed address, "
            "or reply with 1 if you are at the farm, 2 if you are away (or reply 'demo')."
        ),
        "mr": (
            "स्थान निश्चित झाले नाही. 📍\n\n"
            "तुमच्या शेताचे स्थान व्हॉट्सॲप लोकेशन पिन, गुगल मॅप्स लिंक किंवा पत्ता टाईप करून पाठवा, "
            "किंवा शेतावर असल्यास 1, शेतावर नसल्यास 2 पाठवा (किंवा 'demo' पाठवा)."
        ),
        "hi": (
            "स्थान की पुष्टि नहीं हुई। 📍\n\n"
            "अपने खेत का स्थान व्हाट्सएप लोकेशन पिन, गूगल मैप्स लिंक, या पता लिखकर साझा करें, "
            "या खेत पर होने पर 1, बाहर होने पर 2 भेजें (या 'demo' भेजें)।"
        ),
    },
    "location_ambiguous_prompt": {
        "en": (
            "⚠️ Multiple locations were found matching '{query}'. 📍\n\n"
            "To ensure we monitor the correct field, please provide a more specific address with village/taluka and district (e.g., 'Baramati, Pune' or 'Murtizapur, Akola').\n\n"
            "Alternatively, share a WhatsApp location pin or Google Maps link."
        ),
        "mr": (
            "⚠️ '{query}' या नावाशी जुळणारी एकापेक्षा जास्त स्थाने सापडली आहेत. 📍\n\n"
            "योग्य शेताची निवड करण्यासाठी, कृपया गाव, तालुका आणि जिल्ह्यासह अधिक अचूक पत्ता पाठवा (उदा. 'बारामती, पुणे' किंवा 'मुर्तिजापूर, अकोला').\n\n"
            "किंवा व्हॉट्सॲप लोकेशन पिन / गुगल मॅप्स लिंक शेअर करा."
        ),
        "hi": (
            "⚠️ '{query}' से मिलते-जुलते एक से अधिक स्थान मिले हैं। 📍\n\n"
            "सही खेत की निगरानी सुनिश्चित करने के लिए, कृपया गांव/तहसील और जिले सहित अधिक विशिष्ट पता भेजें (जैसे 'बारामती, पुणे' या 'मुर्तिजापुर, अकोला')।\n\n"
            "या व्हाट्सएप लोकेशन पिन अथवा गूगल मैप्स लिंक साझा करें।"
        ),
    },
    "location_not_found_prompt": {
        "en": (
            "📍 We could not find coordinates for '{query}'.\n\n"
            "Please check the spelling and include your district/state (e.g., 'Akola, Maharashtra'), or share your farm location using a WhatsApp location pin or Google Maps link."
        ),
        "mr": (
            "📍 '{query}' साठी भौगोलिक स्थान सापडले नाही.\n\n"
            "कृपया गावाचे/जिल्ह्याचे स्पेलिंग तपासा आणि जिल्ह्याचे नाव जोडा (उदा. 'अकोला, महाराष्ट्र'), किंवा व्हॉट्सॲप लोकेशन पिन अथवा गुगल मॅप्स लिंक पाठवा."
        ),
        "hi": (
            "📍 '{query}' के लिए भौगोलिक निर्देशांक नहीं मिल सके।\n\n"
            "कृपया नाम की वर्तनी जांचें और जिले का नाम शामिल करें (जैसे 'अकोला, महाराष्ट्र'), या व्हाट्सएप लोकेशन पिन अथवा गूगल मैप्स लिंक साझा करें।"
        ),
    },
    "location_validation_urban": {
        "en": (
            "⚠️ We could not confirm that this location is an agricultural field.\n\n"
            "The selected location appears to be in an urban or built-up area. KhetSense AI requires your actual crop field to monitor vegetation and soil moisture.\n\n"
            "Please check the location and share the correct farm field pin. We have not prepared an irrigation recommendation yet."
        ),
        "mr": (
            "⚠️ हे स्थान शेतजमीन असल्याचे निश्चित होऊ शकले नाही.\n\n"
            "आपण निवडलेले स्थान शहरी किंवा इमारतींचे क्षेत्र वाटत आहे. खेतसेन्सला पिकांची स्थिती तपासण्यासाठी प्रत्यक्ष शेताचे स्थान आवश्यक आहे.\n\n"
            "कृपया शेताचे अचूक स्थान तपासा आणि नवीन पिन पाठवा. आम्ही सध्या सिंचन सल्ला तयार केलेला नाही."
        ),
        "hi": (
            "⚠️ हम इस बात की पुष्टि नहीं कर सके कि यह स्थान एक कृषि क्षेत्र है।\n\n"
            "चुना गया स्थान शहरी या निर्माण क्षेत्र प्रतीत होता है। खेतसेंस को फसल की स्थिति की निगरानी के लिए वास्तविक खेत का स्थान चाहिए।\n\n"
            "कृपया स्थान की जांच करें और सही खेत का पिन भेजें। हमने अभी सिंचाई सलाह तैयार नहीं की है।"
        ),
    },
    "location_validation_fallow": {
        "en": (
            "🌱 We could not confirm active crop vegetation at this location.\n\n"
            "It may be a newly sown, fallow, harvested, or uncultivated field. Please verify your farm location and crop details.\n\n"
            "For your safety, irrigation recommendations are withheld until active crop growth is verified."
        ),
        "mr": (
            "🌱 या स्थानावर सध्या सक्रिय पीक दिसून येत नाही.\n\n"
            "हे शेत नांगरलेले, पडिक, नुकतीच पेरणी झालेले किंवा काढणी झालेले असू शकते. कृपया तुमच्या शेताचे स्थान आणि पिकाची खात्री करा.\n\n"
            "सुरक्षेसाठी सक्रिय पीक वाढीची खात्री होईपर्यंत सिंचन सल्ला राखून ठेवला आहे."
        ),
        "hi": (
            "🌱 इस स्थान पर सक्रिय फसल की पुष्टि नहीं हो सकी।\n\n"
            "यह हाल ही में बोया गया, परती, खाली या काटा हुआ खेत हो सकता है। कृपया अपने खेत के स्थान और फसल की पुष्टि करें।\n\n"
            "आपकी सुरक्षा के लिए सक्रिय फसल वृद्धि की पुष्टि होने तक सिंचाई सलाह रोक दी गई है।"
        ),
    },
    "location_validation_satellite_unavailable": {
        "en": (
            "🛰️ Recent satellite imagery for your farm is currently unavailable or obstructed by heavy clouds (>20%).\n\n"
            "KhetSense AI requires clear satellite observations to accurately assess crop health. Please check again later or send 'status' in a few days to get an updated advisory.\n\n"
            "No irrigation recommendation was generated at this time."
        ),
        "mr": (
            "🛰️ तुमच्या शेतासाठी उपग्रह छायाचित्रे सध्या उपलब्ध नाहीत किंवा ढगांमुळे (>२०%) स्पष्ट दिसत नाहीत.\n\n"
            "पिकांच्या अचूक विश्लेषणासाठी स्वच्छ उपग्रह डेटा आवश्यक आहे. कृपया काही दिवसांनी पुन्हा तपासा किंवा नवीन सल्ल्यासाठी 'status' पाठवा.\n\n"
            "सध्या सिंचन सल्ला तयार केलेला नाही."
        ),
        "hi": (
            "🛰️ आपके खेत के लिए उपग्रह चित्र वर्तमान में अनुपलब्ध हैं या घने बादलों (>20%) से ढके हैं।\n\n"
            "फसल के सटीक आकलन के लिए साफ़ उपग्रह डेटा आवश्यक है। कृपया कुछ दिनों बाद पुनः जांचें या ताज़ा सलाह के लिए 'status' लिखकर भेजें।\n\n"
            "इस समय कोई सिंचाई सलाह तैयार नहीं की गई है।"
        ),
    },
    "location_validation_demo_failed": {
        "en": (
            "[DEMO MODE — ILLUSTRATIVE LOCATION DATA]\n\n"
            "⚠️ Demonstration Location Validation Notice:\n\n"
            "We could not confirm that this demonstration location is active agricultural cropland ({reason}).\n\n"
            "No irrigation recommendation was generated. Safety guardrails and land-cover screening remain active in demonstration mode to prevent generating invalid advisories.\n\n"
            "To try another demonstration preset or enter a new location, reply 'restart' or 'demo'."
        ),
        "mr": (
            "[DEMO MODE — ILLUSTRATIVE LOCATION DATA]\n\n"
            "⚠️ प्रात्यक्षिक स्थान पडताळणी सूचना:\n\n"
            "हे प्रात्यक्षिक स्थान सक्रिय शेतजमीन असल्याचे निश्चित होऊ शकले नाही ({reason}).\n\n"
            "कोणताही सिंचन सल्ला तयार केलेला नाही. चुकीचा सल्ला जाण्यापासून रोखण्यासाठी प्रात्यक्षिक मोडमध्येही सुरक्षा नियम काटेकोरपणे पाळले जातात.\n\n"
            "दुसरे प्रात्यक्षिक स्थान निवडण्यासाठी 'restart' किंवा 'demo' पाठवा."
        ),
        "hi": (
            "[DEMO MODE — ILLUSTRATIVE LOCATION DATA]\n\n"
            "⚠️ प्रदर्शन स्थान सत्यापन सूचना:\n\n"
            "इस प्रदर्शन स्थान के सक्रिय कृषि क्षेत्र होने की पुष्टि नहीं हो सकी ({reason})।\n\n"
            "कोई सिंचाई सलाह तैयार नहीं की गई है। गलत सलाह से बचने के लिए प्रदर्शन मोड में भी सुरक्षा नियमों का पूरी तरह पालन किया जाता है।\n\n"
            "अन्य प्रदर्शन स्थान चुनने के लिए 'restart' या 'demo' भेजें।"
        ),
    },
    "crop_validation_mismatch": {
        "en": (
            "⚠️ *KhetSense Crop Verification Notice* 📍\n\n"
            "• Farm ID: #{farm_id}\n"
            "• Declared Crop: {declared_crop}\n"
            "• Detected Crop Indicator: {predicted_crop}\n\n"
            "Our satellite observations and regional crop calendar indicate a likely mismatch:\n"
            "{reason}\n\n"
            "To prevent incorrect irrigation recommendations, crop-specific advice has been withheld.\n\n"
            "• If this crop is correct, or if you need to update your farm crop, reply 'restart' or send your correct crop name."
        ),
        "mr": (
            "⚠️ *खेतसेन्स पीक पडताळणी सूचना* 📍\n\n"
            "• शेत आयडी: #{farm_id}\n"
            "• नोंदवलेले पीक: {declared_crop}\n"
            "• उपग्रह निर्देश: {predicted_crop}\n\n"
            "आमच्या उपग्रह विश्लेषणानुसार आणि प्रादेशिक पीक कॅलेंडरनुसार पिकाच्या माहितीत तफावत आढळली आहे:\n"
            "{reason}\n\n"
            "चुकीचा सल्ला जाण्यापासून रोखण्यासाठी पीक-विशिष्ट सिंचन सल्ला राखून ठेवला आहे.\n\n"
            "• जर हे पीक योग्य असेल, किंवा पीक बदलायचे असल्यास 'restart' पाठवा किंवा योग्य पिकाचे नाव पाठवा."
        ),
        "hi": (
            "⚠️ *खेतसेंस फसल सत्यापन सूचना* 📍\n\n"
            "• फार्म आईडी: #{farm_id}\n"
            "• घोषित फसल: {declared_crop}\n"
            "• उपग्रह संकेत: {predicted_crop}\n\n"
            "हमारे उपग्रह विश्लेषण और क्षेत्रीय फसल कैलेंडर के अनुसार फसल में अंतर पाया गया है:\n"
            "{reason}\n\n"
            "गलत सलाह से बचने के लिए फसल-विशिष्ट सिंचाई सलाह रोक दी गई है।\n\n"
            "• यदि यह फसल सही है, या फसल का नाम बदलना चाहते हैं, तो 'restart' भेजें या सही फसल का नाम भेजें।"
        ),
    },
    "crop_validation_inconclusive": {
        "en": (
            "ℹ️ *Crop Verification Note:* Satellite observations confirm active cropland, but specific crop species "
            "({declared_crop}) could not be independently verified from satellite data alone ({reason}). "
            "Irrigation advice is calibrated for your declared crop ({declared_crop}). Reply 'restart' if your crop is different."
        ),
        "mr": (
            "ℹ️ *पीक पडताळणी नोंद:* उपग्रह निरीक्षणावरून सक्रिय शेतजमिनीची खात्री होते, परंतु केवळ उपग्रहावरून "
            "विशिष्ट पीक ({declared_crop}) स्वतंत्रपणे ओळखता आले नाही ({reason}). "
            "सिंचन सल्ला आपण नोंदवलेल्या पिकासाठी ({declared_crop}) तयार केला आहे. पीक वेगळे असल्यास 'restart' पाठवा."
        ),
        "hi": (
            "ℹ️ *फसल सत्यापन टिप्पणी:* उपग्रह अवलोकनों से सक्रिय कृषि भूमि की पुष्टि होती है, लेकिन केवल उपग्रह से "
            "विशिष्ट फसल ({declared_crop}) की स्वतंत्र पहचान नहीं हो सकी ({reason})। "
            "सिंचाई सलाह आपकी घोषित फसल ({declared_crop}) के लिए तैयार की गई है। यदि फसल अलग है तो 'restart' भेजें।"
        ),
    },
    "location_prompt": {
        "en": (
            "Got it: {acreage_str}.\n\n"
            "Share your farm location using a WhatsApp location pin, Google Maps link, or typed address 📍:\n"
            "1. Tap (+) > 'Location' to drop or send a pin on your farm\n"
            "2. Paste a Google Maps link or share URL\n"
            "3. Type your village, taluka, or district name\n"
            "(Or reply 'demo' to use a sample agricultural plot)"
        ),
        "mr": (
            "नोंद घेतली: {acreage_str}.\n\n"
            "तुमच्या शेताचे स्थान व्हॉट्सॲप लोकेशन पिन, गुगल मॅप्स लिंक किंवा पत्ता टाईप करून पाठवा 📍:\n"
            "1. (+) > 'Location' निवडून शेताचे स्थान पाठवा\n"
            "2. गुगल मॅप्सची लिंक पेस्ट करा\n"
            "3. गाव, तालुका किंवा जिल्ह्याचे नाव टाईप करा\n"
            "(किंवा प्रात्यक्षिकासाठी 'demo' पाठवा)"
        ),
        "hi": (
            "दर्ज किया: {acreage_str}।\n\n"
            "अपने खेत का स्थान व्हाट्सएप लोकेशन पिन, गूगल मैप्स लिंक, या पता लिखकर साझा करें 📍:\n"
            "1. (+) > 'Location' चुनकर खेत का पिन भेजें\n"
            "2. गूगल मैप्स लिंक पेस्ट करें\n"
            "3. गांव, तहसील या जिले का नाम लिखकर भेजें\n"
            "(या प्रदर्शन हेतु 'demo' लिखें)"
        ),
    },
    "location_invalid": {
        "en": (
            "Share your farm location using a WhatsApp Location pin, Google Maps link, or typed address 📍:\n"
            "- Tap the attachment (+) icon, select 'Location', and send your farm's pin\n"
            "- Or paste a Google Maps link or share URL\n"
            "- Or type your village, taluka, or district name (e.g., 'Baramati, Pune' or 'Akola, Maharashtra')\n"
            "- Or reply 'demo' to test using a sample agricultural plot without owning a farm"
        ),
        "mr": (
            "तुमच्या शेताचे स्थान व्हॉट्सॲप लोकेशन पिन, गुगल मॅप्स लिंक किंवा पत्ता टाईप करून पाठवा 📍:\n"
            "- अटॅचमेंट (+) चिन्हावर टॅप करा, 'Location' निवडा आणि शेताचे पिन पाठवा\n"
            "- किंवा गुगल मॅप्स लिंक पेस्ट करा\n"
            "- किंवा गाव/तालुका/जिल्हा टाईप करा (उदा. 'बारामती, पुणे' किंवा 'अकोला')\n"
            "- किंवा प्रात्यक्षिकासाठी 'demo' पाठवा"
        ),
        "hi": (
            "अपने खेत का स्थान व्हाट्सएप लोकेशन पिन, गूगल मैप्स लिंक, या पता लिखकर साझा करें 📍:\n"
            "- अटैचमेंट (+) आइकन पर टैप करें, 'Location' चुनें और खेत का पिन भेजें\n"
            "- या गूगल मैप्स लिंक पेस्ट करें\n"
            "- या गांव/तहसील/जिला लिखें (जैसे 'बारामती, पुणे' या 'अकोला')\n"
            "- या प्रदर्शन के लिए 'demo' लिखें"
        ),
    },
    "location_out_of_bounds": {
        "en": (
            "The coordinates provided appear to be outside India (Lat 6.0–38.0°N, Lon 68.0–98.0°E).\n\n"
            "KhetSense currently monitors farm plots within India. "
            "Please share a valid farm location pin located in India."
        ),
        "mr": (
            "दिलेले निर्देशांक भारताबाहेरील वाटतात (अक्षांश 6.0–38.0°N, रेखांश 68.0–98.0°E).\n\n"
            "खेतसेन्स सध्या भारतातील शेतांचे निरीक्षण करते. "
            "कृपया भारतातील वैध लोकेशन पिन पाठवा."
        ),
        "hi": (
            "दिए गए निर्देशांक भारत के बाहर प्रतीत होते हैं (अक्षांश 6.0–38.0°N, देशांतर 68.0–98.0°E)।\n\n"
            "खेतसेंस वर्तमान में भारत के भीतर खेतों की निगरानी करता है। "
            "कृपया भारत में स्थित एक वैध पिन भेजें।"
        ),
    },
    "registration_success": {
        "en": (
            "🎉 Farm Registration Complete!\n\n"
            "Farm ID: #{farm_id}\n"
            "Farmer: {name}\n"
            "Crop: {crop}\n"
            "Estimated Area: {area:.2f} acres\n"
            "Boundary: {boundary_source}\n"
            "Pin Location: Lat {lat:.5f}, Lon {lon:.5f}\n\n"
            "Your farm details and estimated boundary have been recorded in KhetSense.\n\n"
            "🛰️ Satellite monitoring is starting now; your first irrigation advisory will be sent shortly."
        ),
        "mr": (
            "🎉 शेत नोंदणी यशस्वीरीत्या पूर्ण झाली!\n\n"
            "शेत आयडी: #{farm_id}\n"
            "शेतकरी: {name}\n"
            "पीक: {crop}\n"
            "अंदाजे क्षेत्रफळ: {area:.2f} एकर\n"
            "हद्द: {boundary_source}\n"
            "पिन स्थान: अक्षांश {lat:.5f}, रेखांश {lon:.5f}\n\n"
            "तुमच्या शेताचे तपशील खेतसेन्समध्ये नोंदवले गेले आहेत.\n\n"
            "🛰️ उपग्रह निरीक्षण सुरू होत आहे; तुमचा पहिला सिंचन सल्ला लवकरच पाठवला जाईल."
        ),
        "hi": (
            "🎉 खेत पंजीकरण सफलतापूर्वक पूरा हुआ!\n\n"
            "फार्म आईडी: #{farm_id}\n"
            "किसान: {name}\n"
            "फसल: {crop}\n"
            "अनुमानित क्षेत्रफल: {area:.2f} एकड़\n"
            "सीमा: {boundary_source}\n"
            "पिन स्थान: अक्षांश {lat:.5f}, देशांतर {lon:.5f}\n\n"
            "आपके खेत का विवरण खेतसेंस में दर्ज कर लिया गया है।\n\n"
            "🛰️ उपग्रह निगरानी शुरू हो रही है; आपकी पहली सिंचाई सलाह जल्द ही भेज दी जाएगी।"
        ),
    },
    "demo_registration_success": {
        "en": (
            "[DEMO MODE — ILLUSTRATIVE LOCATION DATA]\n\n"
            "🎉 Demonstration Farm Setup Recorded!\n\n"
            "Farm ID: #{farm_id}\n"
            "Farmer: {name}\n"
            "Crop: {crop}\n"
            "Estimated Area: {area:.2f} acres\n"
            "Boundary: {boundary_source}\n"
            "Demo Location: Lat {lat:.5f}, Lon {lon:.5f}\n\n"
            "This demonstration profile uses illustrative location data for evaluation.\n\n"
            "🛰️ Agricultural land-cover validation is running in the background. To check status and view the advisory report if validated, reply 'status'."
        ),
        "mr": (
            "[DEMO MODE — ILLUSTRATIVE LOCATION DATA]\n\n"
            "🎉 प्रात्यक्षिक शेत नोंदणी पूर्ण झाली!\n\n"
            "शेत आयडी: #{farm_id}\n"
            "शेतकरी: {name}\n"
            "पीक: {crop}\n"
            "अंदाजे क्षेत्रफळ: {area:.2f} एकर\n"
            "हद्द: {boundary_source}\n"
            "प्रात्यक्षिक स्थान: अक्षांश {lat:.5f}, रेखांश {lon:.5f}\n\n"
            "हे प्रात्यक्षिक प्रोफाइल मूल्यमापनासाठी प्रात्यक्षिक स्थान डेटा वापरते.\n\n"
            "🛰️ शेतजमीन पडताळणी पार्श्वभूमीत सुरू आहे. पडताळणी निकाल आणि सल्ला पाहण्यासाठी 'status' पाठवा."
        ),
        "hi": (
            "[DEMO MODE — ILLUSTRATIVE LOCATION DATA]\n\n"
            "🎉 प्रदर्शन खेत सेटअप दर्ज हुआ!\n\n"
            "फार्म आईडी: #{farm_id}\n"
            "किसान: {name}\n"
            "फसल: {crop}\n"
            "अनुमानित क्षेत्रफल: {area:.2f} एकड़\n"
            "सीमा: {boundary_source}\n"
            "प्रदर्शन स्थान: अक्षांश {lat:.5f}, देशांतर {lon:.5f}\n\n"
            "यह प्रदर्शन प्रोफ़ाइल मूल्यांकन के लिए केवल उदाहरणात्मक स्थान डेटा का उपयोग करती है।\n\n"
            "🛰️ पृष्ठभूमि में कृषि भूमि सत्यापन चल रहा है। सत्यापन परिणाम और सलाह देखने के लिए 'status' भेजें।"
        ),
    },
    "already_registered": {
        "en": (
            "You are already registered with KhetSense AI! 🌱\n\n"
            "Farm ID: #{farm_id}\n"
            "Farmer: {name}\n"
            "Crop: {crop}\n\n"
            "• To view your farm details or run a status check, reply 'status'.\n"
            "• To change your language preference, reply 'language'.\n"
            "• If you need to re-register with a new farm location, reply 'restart'."
        ),
        "mr": (
            "तुम्ही आधीच खेतसेन्स (KhetSense AI) मध्ये नोंदणीकृत आहात! 🌱\n\n"
            "शेत आयडी: #{farm_id}\n"
            "शेतकरी: {name}\n"
            "पीक: {crop}\n\n"
            "• शेतीचा अहवाल पाहण्यासाठी 'status' पाठवा.\n"
            "• भाषा बदलण्यासाठी 'language' किंवा 'भाषा' पाठवा.\n"
            "• नवीन शेताची नोंदणी करण्यासाठी 'restart' पाठवा."
        ),
        "hi": (
            "आप पहले से ही खेतसेंस (KhetSense AI) में पंजीकृत हैं! 🌱\n\n"
            "फार्म आईडी: #{farm_id}\n"
            "किसान: {name}\n"
            "फसल: {crop}\n\n"
            "• खेत की स्थिति जानने के लिए 'status' भेजें।\n• भाषा बदलने के लिए 'language' या 'भाषा' भेजें।\n"
            "• नए खेत के साथ पुनः पंजीकरण के लिए 'restart' भेजें।"
        ),
    },
    "error_generic": {
        "en": (
            "We encountered a temporary issue processing your message. "
            "Please try again in a few moments, or reply 'restart' to start registration over."
        ),
        "mr": (
            "तुमचा संदेश प्रक्रिया करताना तात्पुरती अडचण आली. "
            "कृपया काही क्षणांनंतर पुन्हा प्रयत्न करा किंवा पुन्हा सुरू करण्यासाठी 'restart' पाठवा."
        ),
        "hi": (
            "आपके संदेश को संसाधित करने में अस्थायी समस्या आई। "
            "कृपया कुछ पलों बाद पुनः प्रयास करें, या नए सिरे से शुरू करने के लिए 'restart' भेजें।"
        ),
    },
    "reset_success": {
        "en": (
            "Registration has been reset. Let's start fresh! 🌱\n\n"
            "Please choose your preferred language:\n\n"
            "1. English\n"
            "2. मराठी (Marathi)\n"
            "3. हिन्दी (Hindi)\n\n"
            "Please reply with 1, 2 or 3."
        ),
        "mr": (
            "नोंदणी रीसेट केली आहे. पुन्हा नवीन सुरुवात करूया! 🌱\n\n"
            "कृपया तुमची पसंतीची भाषा निवडा:\n\n"
            "1. English\n"
            "2. मराठी (Marathi)\n"
            "3. हिन्दी (Hindi)\n\n"
            "कृपया 1, 2 किंवा 3 उत्तर पाठवा."
        ),
        "hi": (
            "पंजीकरण रीसेट कर दिया गया है। आइए नए सिरे से शुरुआत करें! 🌱\n\n"
            "कृपया अपनी पसंदीदा भाषा चुनें:\n\n"
            "1. English\n"
            "2. मराठी (Marathi)\n"
            "3. हिन्दी (Hindi)\n\n"
            "कृपया 1, 2 या 3 लिखकर भेजें।"
        ),
    },
    "restart_confirm": {
        "en": (
            "⚠️ You are already registered with KhetSense AI!\n\n"
            "Farm ID: #{farm_id}\n"
            "Farmer: {name}\n"
            "Crop: {crop}\n\n"
            "Do you want to re-register and update your farm details and location pin?\n"
            "Your Farm ID (#{farm_id}) and advisory history will be preserved.\n\n"
            "Reply YES to proceed with re-registration, or NO to cancel."
        ),
        "mr": (
            "⚠️ तुम्ही आधीच खेतसेन्स (KhetSense AI) मध्ये नोंदणीकृत आहात!\n\n"
            "शेत आयडी: #{farm_id}\n"
            "शेतकरी: {name}\n"
            "पीक: {crop}\n\n"
            "तुम्हाला नक्की पुन्हा नोंदणी करून तुमच्या शेताचे तपशील आणि लोकेशन पिन अपडेट करायचे आहे का?\n"
            "तुमचा शेत आयडी (#{farm_id}) आणि आधीचा डेटा सुरक्षित राहील.\n\n"
            "पुढे जाण्यासाठी 'हो' (YES) पाठवा, किंवा रद्द करण्यासाठी 'नाही' (NO) पाठवा."
        ),
        "hi": (
            "⚠️ आप पहले से ही खेतसेंस (KhetSense AI) में पंजीकृत हैं!\n\n"
            "फार्म आईडी: #{farm_id}\n"
            "किसान: {name}\n"
            "फसल: {crop}\n\n"
            "क्या आप वाकई दोबारा पंजीकरण करके अपने खेत का विवरण और लोकेशन पिन अपडेट करना चाहते हैं?\n"
            "आपकी फार्म आईडी (#{farm_id}) और पुराना डेटा सुरक्षित रहेगा।\n\n"
            "आगे बढ़ने के लिए 'हाँ' (YES) भेजें, या रद्द करने के लिए 'नहीं' (NO) भेजें।"
        ),
    },
    "restart_confirm_invalid": {
        "en": "Please reply YES to re-register and update your farm, or NO to keep your current details.",
        "mr": "पुन्हा नोंदणी करण्यासाठी कृपया 'हो' (YES) पाठवा, किंवा सध्याचे तपशील ठेवण्यासाठी 'नाही' (NO) पाठवा.",
        "hi": "पुनः पंजीकरण के लिए कृपया 'हाँ' (YES) भेजें, या वर्तमान विवरण रखने के लिए 'नहीं' (NO) भेजें।",
    },
    "restart_cancelled": {
        "en": (
            "Re-registration cancelled. Your existing farm details remain unchanged. 🌱\n\n"
            "Farm ID: #{farm_id}\n"
            "Farmer: {name}\n"
            "Crop: {crop}\n\n"
            "• To view your farm details or run a status check, reply 'status'.\n"
            "• To change your language preference, reply 'language'."
        ),
        "mr": (
            "पुन्हा नोंदणी रद्द केली आहे. तुमच्या शेताचे तपशील जसेच्या तसे राहतील. 🌱\n\n"
            "शेत आयडी: #{farm_id}\n"
            "शेतकरी: {name}\n"
            "पीक: {crop}\n\n"
            "• शेतीचा अहवाल पाहण्यासाठी 'status' पाठवा.\n"
            "• भाषा बदलण्यासाठी 'language' पाठवा."
        ),
        "hi": (
            "पुनः पंजीकरण रद्द कर दिया गया है। आपके खेत का विवरण पहले जैसा ही रहेगा। 🌱\n\n"
            "फार्म आईडी: #{farm_id}\n"
            "किसान: {name}\n"
            "फसल: {crop}\n\n"
            "• खेत की स्थिति जानने के लिए 'status' भेजें।\n"
            "• भाषा बदलने के लिए 'language' भेजें।"
        ),
    },
    "re_registration_start": {
        "en": (
            "Re-registration started! 🌱\n"
            "Your Farm ID (#{farm_id}) will be updated with your new details.\n\n"
            "What is your full name?"
        ),
        "mr": (
            "पुन्हा नोंदणी सुरू झाली आहे! 🌱\n"
            "तुमचा शेत आयडी (#{farm_id}) नवीन तपशिलांसह अपडेट केला जाईल.\n\n"
            "तुमचे पूर्ण नाव काय आहे?"
        ),
        "hi": (
            "पुनः पंजीकरण शुरू हो गया है! 🌱\n"
            "आपकी फार्म आईडी (#{farm_id}) नए विवरण के साथ अपडेट की जाएगी।\n\n"
            "आपका पूरा नाम क्या है?"
        ),
    },
    "farm_updated_success": {
        "en": (
            "🎉 Farm Details Updated Successfully!\n\n"
            "Farm ID: #{farm_id}\n"
            "Farmer: {name}\n"
            "Crop: {crop}\n"
            "Estimated Area: {area:.2f} acres\n"
            "Boundary: {boundary_source}\n"
            "Pin Location: Lat {lat:.5f}, Lon {lon:.5f}\n\n"
            "Your updated farm details and estimated boundary have been recorded in KhetSense.\n\n"
            "🛰️ Satellite monitoring is updating now; your latest irrigation advisory will be sent shortly."
        ),
        "mr": (
            "🎉 शेताचे तपशील यशस्वीरीत्या अपडेट झाले!\n\n"
            "शेत आयडी: #{farm_id}\n"
            "शेतकरी: {name}\n"
            "पीक: {crop}\n"
            "अंदाजे क्षेत्रफळ: {area:.2f} एकर\n"
            "हद्द: {boundary_source}\n"
            "पिन स्थान: अक्षांश {lat:.5f}, रेखांश {lon:.5f}\n\n"
            "तुमचे अपडेट केलेले शेत तपशील खेतसेन्समध्ये नोंदवले गेले आहेत.\n\n"
            "🛰️ उपग्रह निरीक्षण अपडेट होत आहे; तुमचा नवीन सिंचन सल्ला लवकरच पाठवला जाईल."
        ),
        "hi": (
            "🎉 खेत का विवरण सफलतापूर्वक अपडेट हो गया!\n\n"
            "फार्म आईडी: #{farm_id}\n"
            "किसान: {name}\n"
            "फसल: {crop}\n"
            "अनुमानित क्षेत्रफल: {area:.2f} एकड़\n"
            "सीमा: {boundary_source}\n"
            "पिन स्थान: अक्षांश {lat:.5f}, देशांतर {lon:.5f}\n\n"
            "आपके खेत का अपडेट किया गया विवरण खेतसेंस में दर्ज कर लिया गया है।\n\n"
            "🛰️ उपग्रह निगरानी अपडेट हो रही है; आपकी नवीनतम सिंचाई सलाह जल्द ही भेज दी जाएगी।"
        ),
    },
    "status_advisory": {
        "en": (
            "📊 *KhetSense Farm Status & Advisory* 🌱\n\n"
            "• Farm ID: #{farm_id}\n"
            "• Farmer: {name}\n"
            "• Crop: {crop}\n"
            "• Status Date: {advisory_date}\n\n"
            "🌾 *Observed Stress:* {observed_stress}\n"
            "💧 *Recommended Action:* {recommended_action}\n"
            "🌧️ *48-Hour Forecast Rain:* {forecast_rain}\n\n"
            "📋 *Agronomic Advice:*\n"
            "{advisory_explanation}\n\n"
            "• Reply 'status' anytime for an updated advisory.\n"
            "• Reply 'language' to change your language."
        ),
        "mr": (
            "📊 *खेतसेन्स शेती अहवाल आणि सल्ला* 🌱\n\n"
            "• शेत आयडी: #{farm_id}\n"
            "• शेतकरी: {name}\n"
            "• पीक: {crop}\n"
            "• सल्ल्याचा दिनांक: {advisory_date}\n\n"
            "🌾 *निरीक्षण केलेला ताण:* {observed_stress}\n"
            "💧 *शिफारस केलेली कृती:* {recommended_action}\n"
            "🌧️ *48-तासांचा पावसाचा अंदाज:* {forecast_rain}\n\n"
            "📋 *कृषी सल्ला:*\n"
            "{advisory_explanation}\n\n"
            "• अद्ययावत अहवालासाठी कधीही 'status' पाठवा.\n"
            "• भाषा बदलण्यासाठी 'language' पाठवा."
        ),
        "hi": (
            "📊 *खेतसेंस खेत स्थिति एवं सलाह* 🌱\n\n"
            "• फार्म आईडी: #{farm_id}\n"
            "• किसान: {name}\n"
            "• फसल: {crop}\n"
            "• सलाह दिनांक: {advisory_date}\n\n"
            "🌾 *देखा गया तनाव:* {observed_stress}\n"
            "💧 *सलाह (सिंचाई कार्यवाही):* {recommended_action}\n"
            "🌧️ *48-घंटे बारिश का अनुमान:* {forecast_rain}\n\n"
            "📋 *कृषि सलाह:*\n"
            "{advisory_explanation}\n\n"
            "• अपडेटेड सलाह के लिए कभी भी 'status' भेजें।\n"
            "• भाषा बदलने के लिए 'language' भेजें।"
        ),
    },
    "status_no_advisory": {
        "en": (
            "🌾 *KhetSense Farm Status* 🌱\n\n"
            "• Farm ID: #{farm_id}\n"
            "• Farmer: {name}\n"
            "• Crop: {crop}\n"
            "• Status: Registered & Monitoring Active 🛰️\n\n"
            "Your farm is registered and satellite monitoring is active!\n"
            "We are currently processing the latest satellite and soil moisture observations for your field.\n\n"
            "Your first irrigation advisory will be available shortly. Please check back soon by sending 'status'.\n\n"
            "• Reply 'language' to change your language."
        ),
        "mr": (
            "🌾 *खेतसेन्स शेती स्थिती* 🌱\n\n"
            "• शेत आयडी: #{farm_id}\n"
            "• शेतकरी: {name}\n"
            "• पीक: {crop}\n"
            "• स्थिती: नोंदणीकृत आणि उपग्रह निरीक्षण सक्रिय 🛰️\n\n"
            "तुमच्या शेताची नोंदणी पूर्ण झाली आहे आणि उपग्रह निरीक्षण सक्रिय आहे!\n"
            "आम्ही सध्या तुमच्या शेतासाठी उपग्रह आणि मातीतील ओलाव्याच्या ताज्या माहितीवर प्रक्रिया करत आहोत.\n\n"
            "तुमचा पहिला सिंचन सल्ला लवकरच उपलब्ध होईल. कृपया थोड्या वेळाने 'status' पाठवून पुन्हा तपासा.\n\n"
            "• भाषा बदलण्यासाठी 'language' पाठवा."
        ),
        "hi": (
            "🌾 *खेतसेंस खेत स्थिति* 🌱\n\n"
            "• फार्म आईडी: #{farm_id}\n"
            "• किसान: {name}\n"
            "• फसल: {crop}\n"
            "• स्थिति: पंजीकृत और उपग्रह निगरानी सक्रिय 🛰️\n\n"
            "आपका खेत पंजीकृत है और उपग्रह निगरानी सक्रिय है!\n"
            "हम वर्तमान में आपके खेत के लिए नवीनतम उपग्रह और मिट्टी की नमी के आंकड़ों को संसाधित कर रहे हैं।\n\n"
            "आपकी पहली सिंचाई सलाह जल्द ही उपलब्ध होगी। कृपया कुछ समय बाद 'status' भेजकर पुनः जांचें।\n\n"
            "• भाषा बदलने के लिए 'language' भेजें।"
        ),
    },
    "status_no_advisory_demo": {
        "en": (
            "[DEMO MODE — ILLUSTRATIVE LOCATION DATA]\n\n"
            "🌾 *KhetSense Demo Status* 🌱\n\n"
            "• Farm ID: #{farm_id}\n"
            "• Farmer: {name}\n"
            "• Crop: {crop}\n"
            "• Status: Demonstration Profile (Illustrative Evaluation)\n\n"
            "Demonstration analysis is in progress. Agricultural land-cover validation and satellite screening are currently being evaluated for this plot.\n\n"
            "Once processing is complete, reply 'status' to view the outcome.\n\n"
            "• Reply 'language' to change your language."
        ),
        "mr": (
            "[DEMO MODE — ILLUSTRATIVE LOCATION DATA]\n\n"
            "🌾 *खेतसेन्स प्रात्यक्षिक स्थिती* 🌱\n\n"
            "• शेत आयडी: #{farm_id}\n"
            "• शेतकरी: {name}\n"
            "• पीक: {crop}\n"
            "• स्थिती: प्रात्यक्षिक प्रोफाइल (मूल्यमापन)\n\n"
            "प्रात्यक्षिक विश्लेषण सुरू आहे. या शेतासाठी शेतजमीन पडताळणी आणि उपग्रह तपासणीचे मूल्यमापन केले जात आहे.\n\n"
            "प्रक्रिया पूर्ण झाल्यावर निकाल पाहण्यासाठी 'status' पाठवा.\n\n"
            "• भाषा बदलण्यासाठी 'language' पाठवा."
        ),
        "hi": (
            "[DEMO MODE — ILLUSTRATIVE LOCATION DATA]\n\n"
            "🌾 *खेतसेंस प्रदर्शन स्थिति* 🌱\n\n"
            "• फार्म आईडी: #{farm_id}\n"
            "• किसान: {name}\n"
            "• फसल: {crop}\n"
            "• स्थिति: प्रदर्शन प्रोफ़ाइल (मूल्यांकन)\n\n"
            "प्रदर्शन विश्लेषण प्रगति पर है। इस भूखंड के लिए कृषि भूमि सत्यापन और उपग्रह स्क्रीनिंग का मूल्यांकन किया जा रहा है।\n\n"
            "प्रक्रिया पूरी होने के बाद परिणाम देखने के लिए 'status' भेजें।\n\n"
            "• भाषा बदलने के लिए 'language' भेजें।"
        ),
    },
    "status_not_registered": {
        "en": (
            "🌱 *Welcome to KhetSense AI!*\n\n"
            "You do not have a registered farm yet. To receive satellite-based crop stress monitoring "
            "and precision irrigation advisories, please register your farm first.\n\n"
            "Reply with *START* or send your full name to begin registration."
        ),
        "mr": (
            "🌱 *खेतसेन्स (KhetSense AI) मध्ये आपले स्वागत आहे!*\n\n"
            "तुमच्या शेताची अजून नोंदणी झालेली नाही. उपग्रह-आधारित पीक ताण निरीक्षण आणि अचूक सिंचन सल्ला "
            "मिळविण्यासाठी, कृपया प्रथम आपल्या शेताची नोंदणी करा.\n\n"
            "नोंदणी सुरू करण्यासाठी *START* पाठवा किंवा आपले पूर्ण नाव पाठवा."
        ),
        "hi": (
            "🌱 *खेतसेंस (KhetSense AI) में आपका स्वागत है!*\n\n"
            "आपका खेत अभी तक पंजीकृत नहीं है। उपग्रह-आधारित फसल तनाव निगरानी और सटीक सिंचाई सलाह "
            "प्राप्त करने के लिए, कृपया पहले अपने खेत का पंजीकरण करें।\n\n"
            "पंजीकरण शुरू करने के लिए *START* लिखकर भेजें या अपना पूरा नाम भेजें।"
        ),
    },
    "status_processing": {
        "en": (
            "⏳ *KhetSense Advisory Processing* 🛰️\n\n"
            "• Farm ID: #{farm_id}\n"
            "• Farmer: {name}\n"
            "• Crop: {crop}\n\n"
            "We are currently fetching the latest satellite observations (Sentinel-2), "
            "soil moisture (SMAP), and weather forecasts for your farm.\n\n"
            "Your personalized irrigation advisory is being generated and will be delivered shortly. "
            "Please check back in a few moments!\n\n"
            "• Reply 'language' to change your language."
        ),
        "mr": (
            "⏳ *खेतसेन्स सल्ला प्रक्रिया सुरू आहे* 🛰️\n\n"
            "• शेत आयडी: #{farm_id}\n"
            "• शेतकरी: {name}\n"
            "• पीक: {crop}\n\n"
            "आम्ही सध्या तुमच्या शेतासाठी उपग्रह माहिती (Sentinel-2), "
            "मातीतील ओलावा (SMAP) आणि हवामान अंदाजाचे विश्लेषण करत आहोत.\n\n"
            "तुमचा सिंचन सल्ला तयार केला जात असून लवकरच पाठवला जाईल. "
            "कृपया काही वेळाने तपासा!\n\n"
            "• भाषा बदलण्यासाठी 'language' पाठवा."
        ),
        "hi": (
            "⏳ *खेतसेंस सलाह प्रक्रिया जारी है* 🛰️\n\n"
            "• फार्म आईडी: #{farm_id}\n"
            "• किसान: {name}\n"
            "• फसल: {crop}\n\n"
            "हम वर्तमान में आपके खेत के लिए उपग्रह डेटा (Sentinel-2), "
            "मिट्टी की नमी (SMAP) और मौसम पूर्वानुमान का विश्लेषण कर रहे हैं।\n\n"
            "आपकी व्यक्तिगत सिंचाई सलाह तैयार की जा रही है और जल्द ही भेज दी जाएगी। "
            "कृपया कुछ पलों में जांचें!\n\n"
            "• भाषा बदलने के लिए 'language' भेजें।"
        ),
    },
    "pipeline_failed_notice": {
        "en": (
            "🌾 *KhetSense Satellite Monitoring Notice* 🌱\n\n"
            "• Farm ID: #{farm_id}\n"
            "• Farmer: {name}\n\n"
            "Your farm registration is complete and active! However, our satellite/weather data providers "
            "are temporarily delayed.\n\n"
            "Automatic monitoring is active, and your irrigation advisory will be delivered as soon as "
            "new satellite readings are processed.\n\n"
            "• Reply 'status' anytime to check current status."
        ),
        "mr": (
            "🌾 *खेतसेन्स उपग्रह निरीक्षण सूचना* 🌱\n\n"
            "• शेत आयडी: #{farm_id}\n"
            "• शेतकरी: {name}\n\n"
            "तुमच्या शेताची नोंदणी पूर्ण झाली आहे! तथापि, उपग्रह/हवामान माहिती मिळण्यात तात्पुरता विलंब होत आहे.\n\n"
            "स्वयंचलित निरीक्षण सक्रिय आहे आणि नवीन उपग्रह माहिती प्राप्त होताच तुमचा सिंचन सल्ला पाठवला जाईल.\n\n"
            "• सद्यस्थिती तपासण्यासाठी कधीही 'status' पाठवा."
        ),
        "hi": (
            "🌾 *खेतसेंस उपग्रह निगरानी सूचना* 🌱\n\n"
            "• फार्म आईडी: #{farm_id}\n"
            "• किसान: {name}\n\n"
            "आपके खेत का पंजीकरण पूरा हो चुका है! हालांकि, उपग्रह/मौसम डेटा प्रदाताओं से "
            "जानकारी मिलने में अस्थायी देरी हो रही है।\n\n"
            "स्वचालित निगरानी सक्रिय है और नया उपग्रह डेटा मिलते ही आपकी सिंचाई सलाह भेज दी जाएगी।\n\n"
            "• स्थिति जांचने के लिए कभी भी 'status' भेजें।"
        ),
    },
}


def get_message(key: str, lang: str = DEFAULT_LANGUAGE, **kwargs) -> str:
    """
    Retrieves and safely formats a localized message template.
    Falls back to English if the key or language is not found.
    """
    code = normalize_language(lang)
    template_dict = MESSAGES.get(key)
    if not template_dict:
        return f"[{key}]"

    raw_text = template_dict.get(code) or template_dict.get("en") or ""

    if not kwargs:
        return raw_text

    if key == "location_confirm_prompt":
        loc_name = kwargs.get("location_name")
        if loc_name:
            if code == "mr":
                kwargs["location_line"] = f"स्थान: {loc_name}\n"
            elif code == "hi":
                kwargs["location_line"] = f"स्थान: {loc_name}\n"
            else:
                kwargs["location_line"] = f"Location: {loc_name}\n"
        else:
            kwargs.setdefault("location_line", "")

    try:
        return raw_text.format(**kwargs)
    except KeyError:
        # Fallback safe replace for missing template keys
        formatted = raw_text
        for k, v in kwargs.items():
            formatted = formatted.replace(f"{{{k}}}", str(v))
        return formatted


# ==============================================================================
# 4. MULTILINGUAL IRRIGATION ADVISORY TEMPLATES
# ==============================================================================

# Recommended action keys matching common.config
from common.config import (
    ACTION_IRRIGATE_NOW,
    ACTION_IRRIGATE_LIGHTLY,
    ACTION_SCHEDULE_IRRIGATION,
    ACTION_DELAY_RECHECK,
    ACTION_HOLD_RECHECK,
    ACTION_NO_ACTION,
    ACTION_INSUFFICIENT_DATA,
)

ADVISORY_TEMPLATES: Dict[str, Dict[str, str]] = {
    ACTION_IRRIGATE_NOW: {
        "en": (
            "URGENT: Severe water stress detected for {crop_name}{stage_suffix}. "
            "Immediate irrigation recommended to prevent yield loss ({rain_info})."
        ),
        "mr": (
            "तातडीची सूचना: {crop_name}{stage_suffix} साठी तीव्र पाण्याचा ताण आढळला आहे. "
            "पिकाचे नुकसान टाळण्यासाठी तात्काळ पाणी देण्याची शिफारस केली जाते ({rain_info})."
        ),
        "hi": (
            "जरूरी सूचना: {crop_name}{stage_suffix} के लिए पानी का गंभीर तनाव पाया गया है। "
            "फसल नुकसान से बचाने के लिए तुरंत सिंचाई करने की सलाह दी जाती है ({rain_info})।"
        ),
    },
    ACTION_IRRIGATE_LIGHTLY: {
        "en": (
            "ATTENTION: Severe water stress detected for {crop_name}{stage_suffix}. "
            "Light irrigation recommended as {rain_str} forecast rain may not suffice."
        ),
        "mr": (
            "लक्ष द्या: {crop_name}{stage_suffix} साठी तीव्र पाण्याचा ताण आढळला आहे. "
            "{rain_str} पावसाचा अंदाज पुरेसा नसू शकतो, म्हणून हलके पाणी देण्याची शिफारस केली जाते."
        ),
        "hi": (
            "ध्यान दें: {crop_name}{stage_suffix} के लिए पानी का गंभीर तनाव पाया गया है। "
            "{rain_str} बारिश का पूर्वानुमान पर्याप्त नहीं हो सकता, इसलिए हल्की सिंचाई की सलाह दी जाती है।"
        ),
    },
    ACTION_HOLD_RECHECK: {
        "en": (
            "MONITOR: {stress_word} water stress detected for {crop_name}{stage_suffix}, "
            "but {rain_str} forecast rain expected. Hold irrigation and re-check after rain."
        ),
        "mr": (
            "निरीक्षण करा: {crop_name}{stage_suffix} साठी पाण्याचा ताण आढळला आहे, "
            "परंतु पुढील 48 तासांत {rain_str} पावसाचा अंदाज आहे. सध्या पाणी देणे थांबवा आणि पावसानंतर पुन्हा तपासा."
        ),
        "hi": (
            "निगरानी रखें: {crop_name}{stage_suffix} के लिए पानी का तनाव पाया गया है, "
            "लेकिन अगले 48 घंटों में {rain_str} बारिश का अनुमान है। सिंचाई रोकें और बारिश के बाद दोबारा स्थिति जांचें।"
        ),
    },
    ACTION_SCHEDULE_IRRIGATION: {
        "en": (
            "ATTENTION: Mild water stress detected for {crop_name}{stage_suffix}. "
            "Schedule regular irrigation in the next 24-48 hours ({rain_info})."
        ),
        "mr": (
            "लक्ष द्या: {crop_name}{stage_suffix} साठी हलका पाण्याचा ताण आढळला आहे. "
            "पुढील 24 ते 48 तासांत नियमित पाणी देण्याचे नियोजन करा ({rain_info})."
        ),
        "hi": (
            "ध्यान दें: {crop_name}{stage_suffix} के लिए पानी का हल्का तनाव पाया गया है। "
            "अगले 24-48 घंटों में नियमित सिंचाई का समय तय करें ({rain_info})।"
        ),
    },
    ACTION_DELAY_RECHECK: {
        "en": (
            "MONITOR: Mild water stress detected for {crop_name}{stage_suffix}. "
            "Delay irrigation and re-check after {rain_str} forecast rain."
        ),
        "mr": (
            "निरीक्षण करा: {crop_name}{stage_suffix} साठी हलका पाण्याचा ताण आढळला आहे. "
            "पुढील 24-48 तासांत {rain_str} पावसाचा अंदाज असल्याने पाणी देणे पुढे ढकला आणि पावसानंतर पुन्हा तपासा."
        ),
        "hi": (
            "निगरानी रखें: {crop_name}{stage_suffix} के लिए पानी का हल्का तनाव पाया गया है। "
            "{rain_str} बारिश के अनुमान को देखते हुए सिंचाई टालें और बारिश के बाद दोबारा जांचें।"
        ),
    },
    ACTION_NO_ACTION: {
        "en": (
            "OPTIMAL: Adequate soil moisture and healthy canopy for {crop_name}{stage_suffix}. "
            "No action required{rain_mention}."
        ),
        "mr": (
            "उत्कृष्ट: {crop_name}{stage_suffix} साठी जमिनीत पुरेसा ओलावा आणि पिकाची स्थिती उत्तम आहे. "
            "सध्या पाणी देण्याची आवश्यकता नाही{rain_mention}."
        ),
        "hi": (
            "उत्तम: {crop_name}{stage_suffix} के लिए मिट्टी में पर्याप्त नमी और फसल की स्थिति स्वस्थ है। "
            "किसी कार्रवाई की आवश्यकता नहीं है{rain_mention}।"
        ),
    },
    ACTION_INSUFFICIENT_DATA: {
        "en": "INSUFFICIENT DATA: Advisory could not be finalized due to missing sensor inputs.",
        "mr": "अपुरा डेटा: आवश्यक सेन्सर माहिती उपलब्ध नसल्यामुळे सिंचन सल्ला तयार करता आला नाही.",
        "hi": "अपर्याप्त डेटा: आवश्यक सेंसर इनपुट न मिलने के कारण सिंचाई सलाह पूरी नहीं हो सकी।",
    },
}


def get_localized_advisory(
    lang: str,
    observed_stress: str,
    recommended_action: str,
    crop: Optional[str] = None,
    stage: Optional[str] = None,
    rain_48h: Optional[float] = None,
) -> str:
    """
    Renders localized plain-language advisory text in English, Marathi, or Hindi.
    Reuses existing stress classifications, guardrail actions, and thresholds.
    """
    code = normalize_language(lang)
    crop_display = get_localized_crop(crop, code)

    # Format growth stage
    if stage and str(stage).strip() and str(stage).strip().lower() != "none":
        if code == "mr":
            stage_suffix = f" ({stage} टप्प्यात)"
        elif code == "hi":
            stage_suffix = f" ({stage} चरण में)"
        else:
            stage_suffix = f" at {stage} stage"
    else:
        stage_suffix = ""

    # Rainfall strings
    rain_str = f"{rain_48h:.1f} mm" if rain_48h is not None else "minimal"

    if code == "mr":
        if rain_48h is not None and rain_48h > 0:
            rain_info = f"किमान पावसाचा अंदाज: {rain_str}"
        elif rain_48h is not None:
            rain_info = "पावसाचा अंदाज नाही"
        else:
            rain_info = "पावसाचा अंदाज उपलब्ध नाही"
        rain_mention = f" ({rain_str} पावसाचा अंदाज)" if rain_48h is not None else ""
        stress_word = "तीव्र" if observed_stress == "Severe Stress" else "हलका"
    elif code == "hi":
        if rain_48h is not None and rain_48h > 0:
            rain_info = f"नाममात्र बारिश का अनुमान: {rain_str}"
        elif rain_48h is not None:
            rain_info = "बारिश का अनुमान नहीं"
        else:
            rain_info = "बारिश का पूर्वानुमान उपलब्ध नहीं"
        rain_mention = f" ({rain_str} बारिश का अनुमान)" if rain_48h is not None else ""
        stress_word = "गंभीर" if observed_stress == "Severe Stress" else "हल्का"
    else:
        if rain_48h is not None and rain_48h > 0:
            rain_info = f"minimal forecast rain: {rain_str}"
        elif rain_48h is not None:
            rain_info = "no forecast rain"
        else:
            rain_info = "forecast rain data unavailable"
        rain_mention = f" ({rain_str} forecast rain)" if rain_48h is not None else ""
        stress_word = "Severe" if observed_stress == "Severe Stress" else "Mild"

    template_dict = ADVISORY_TEMPLATES.get(recommended_action)
    if not template_dict:
        template_dict = ADVISORY_TEMPLATES.get(ACTION_INSUFFICIENT_DATA, {})

    raw_text = template_dict.get(code) or template_dict.get("en") or ""

    return raw_text.format(
        crop_name=crop_display,
        stage_suffix=stage_suffix,
        rain_info=rain_info,
        rain_str=rain_str,
        rain_mention=rain_mention,
        stress_word=stress_word,
    )


# ==============================================================================
# 5. STATUS COMMAND & ADVISORY CARD FORMATTING
# ==============================================================================

LOCALIZED_STRESS: Dict[str, Dict[str, str]] = {
    "Severe Stress": {
        "en": "Severe Stress",
        "mr": "तीव्र ताण (Severe Stress)",
        "hi": "गंभीर तनाव (Severe Stress)",
    },
    "Mild Stress": {
        "en": "Mild Stress",
        "mr": "हलका ताण (Mild Stress)",
        "hi": "हल्का तनाव (Mild Stress)",
    },
    "No Stress": {
        "en": "No Stress (Healthy)",
        "mr": "ताण नाही / निरोगी (Healthy)",
        "hi": "तनाव नहीं / स्वस्थ (Healthy)",
    },
    "Unknown": {
        "en": "Data Pending",
        "mr": "माहिती प्रलंबित (Pending)",
        "hi": "डेटा प्रतीक्षारत (Pending)",
    },
}


def get_localized_stress(stress: Optional[str], lang: str = DEFAULT_LANGUAGE) -> str:
    """Returns the localized display name for a stress category."""
    code = normalize_language(lang)
    if not stress:
        return "Not Available" if code == "en" else ("उपलब्ध नाही" if code == "mr" else "उपलब्ध नहीं")
    cleaned = str(stress).strip()
    for std_stress, trans in LOCALIZED_STRESS.items():
        if cleaned.lower() == std_stress.lower() or cleaned.lower() in std_stress.lower():
            return trans.get(code, std_stress)
    return cleaned


LOCALIZED_ACTIONS: Dict[str, Dict[str, str]] = {
    ACTION_IRRIGATE_NOW: {
        "en": "Irrigate Now",
        "mr": "तात्काळ पाणी द्या (Irrigate Now)",
        "hi": "तुरंत सिंचाई करें (Irrigate Now)",
    },
    ACTION_IRRIGATE_LIGHTLY: {
        "en": "Irrigate Lightly",
        "mr": "हलके पाणी द्या (Irrigate Lightly)",
        "hi": "हल्की सिंचाई करें (Irrigate Lightly)",
    },
    ACTION_SCHEDULE_IRRIGATION: {
        "en": "Schedule Irrigation (24-48h)",
        "mr": "24-48 तासांत पाणी द्या (Schedule Irrigation)",
        "hi": "24-48 घंटों में सिंचाई करें (Schedule Irrigation)",
    },
    ACTION_DELAY_RECHECK: {
        "en": "Delay Irrigation & Re-check",
        "mr": "पाणी पुढे ढकला आणि पुन्हा तपासा (Delay & Recheck)",
        "hi": "सिंचाई टालें और दोबारा जांचें (Delay & Recheck)",
    },
    ACTION_HOLD_RECHECK: {
        "en": "Hold Irrigation & Re-check",
        "mr": "पाणी देणे थांबवा आणि पुन्हा तपासा (Hold & Recheck)",
        "hi": "सिंचाई रोकें और दोबारा जांचें (Hold & Recheck)",
    },
    ACTION_NO_ACTION: {
        "en": "No Action Needed (Optimal)",
        "mr": "पाण्याची गरज नाही (No Action Needed)",
        "hi": "सिंचाई की आवश्यकता नहीं (No Action Needed)",
    },
    ACTION_INSUFFICIENT_DATA: {
        "en": "Data Insufficient",
        "mr": "अपुरा डेटा (Insufficient Data)",
        "hi": "अपर्याप्त डेटा (Insufficient Data)",
    },
}


def get_localized_action(action: Optional[str], lang: str = DEFAULT_LANGUAGE) -> str:
    """Returns the localized display string for an irrigation action."""
    code = normalize_language(lang)
    if not action:
        return "Under Review" if code == "en" else ("पुनरावलोकन सुरू" if code == "mr" else "समीक्षाधीन")
    cleaned = str(action).strip().lower()
    for std_action, trans in LOCALIZED_ACTIONS.items():
        if cleaned == std_action.lower():
            return trans.get(code, std_action)
    return str(action)


def infer_recommended_action(
    recommended_action: Optional[str],
    recommendation_text: Optional[str] = None,
    observed_stress: Optional[str] = None,
    rain_mm: Optional[float] = None,
) -> str:
    """
    Infers standard ACTION_* key from database fields, providing backwards
    compatibility for pre-Migration 003 advisories.
    """
    if recommended_action and str(recommended_action).strip():
        act = str(recommended_action).strip()
        for std in [
            ACTION_IRRIGATE_NOW,
            ACTION_IRRIGATE_LIGHTLY,
            ACTION_SCHEDULE_IRRIGATION,
            ACTION_DELAY_RECHECK,
            ACTION_HOLD_RECHECK,
            ACTION_NO_ACTION,
            ACTION_INSUFFICIENT_DATA,
        ]:
            if act.lower() == std.lower():
                return std
        return act

    if recommendation_text:
        rec_lower = recommendation_text.lower()
        if "immediate" in rec_lower or "irrigate now" in rec_lower:
            return ACTION_IRRIGATE_NOW
        if "lightly" in rec_lower or "light irrigation" in rec_lower:
            return ACTION_IRRIGATE_LIGHTLY
        if "schedule" in rec_lower:
            return ACTION_SCHEDULE_IRRIGATION
        if "delay" in rec_lower:
            return ACTION_DELAY_RECHECK
        if "hold" in rec_lower:
            return ACTION_HOLD_RECHECK
        if "no action" in rec_lower or "adequate" in rec_lower:
            return ACTION_NO_ACTION

    stress_lower = (observed_stress or "").lower()
    rain = rain_mm if rain_mm is not None else 0.0
    if "severe" in stress_lower:
        if rain >= 15.0:
            return ACTION_HOLD_RECHECK
        elif rain >= 5.0:
            return ACTION_IRRIGATE_LIGHTLY
        else:
            return ACTION_IRRIGATE_NOW
    elif "mild" in stress_lower:
        if rain >= 5.0:
            return ACTION_DELAY_RECHECK
        else:
            return ACTION_SCHEDULE_IRRIGATION
    elif "no stress" in stress_lower:
        return ACTION_NO_ACTION

    return ACTION_INSUFFICIENT_DATA


def _format_date(val: Any) -> str:
    """Safely formats observation / creation date to DD-MM-YYYY."""
    if val is None:
        return "Recent"
    if hasattr(val, "strftime"):
        return val.strftime("%d-%m-%Y")
    val_str = str(val).split("T")[0].split(" ")[0].strip()
    parts = val_str.split("-")
    if len(parts) == 3 and len(parts[0]) == 4:
        return f"{parts[2]}-{parts[1]}-{parts[0]}"
    return val_str or "Recent"


def format_status_advisory(
    farm: Dict[str, Any],
    advisory: Dict[str, Any],
    lang: str = DEFAULT_LANGUAGE,
) -> str:
    """
    Renders a complete, localized WhatsApp farm advisory status card.
    Supports English, Marathi, and Hindi with safe fallbacks for missing fields.
    """
    code = normalize_language(lang)
    farm_id = farm.get("id", "N/A")
    farmer_name = farm.get("farmer_name", "Farmer")
    crop_name = farm.get("crop_name", "Crop")
    crop_display = get_localized_crop(crop_name, code)

    is_demo = bool(
        farm.get("is_demo")
        or advisory.get("is_demo")
        or (isinstance(farm.get("notes"), str) and "demo" in farm.get("notes", "").lower())
        or os.getenv("DEMO_MODE", "").strip().lower() in ("true", "1", "yes")
    )

    # If the latest advisory record was an audited validation failure, render localized failure notice
    val_status = str(advisory.get("validation_status") or "").strip().upper()
    stress_str = str(advisory.get("observed_stress") or advisory.get("stress_level") or "").strip().upper()
    if val_status == "LIKELY_URBAN" or ("VALIDATION_FAILED" in stress_str and "URBAN" in stress_str):
        msg = get_message("location_validation_urban", lang=code)
        if is_demo:
            return f"[DEMO MODE — ILLUSTRATIVE LOCATION DATA]\n\n⚠️ Demonstration Location Validation Notice:\n\n{msg}"
        return msg
    elif val_status == "BARREN_OR_UNCERTAIN" or ("VALIDATION_FAILED" in stress_str and ("BARREN" in stress_str or "FALLOW" in stress_str or "UNCERTAIN" in stress_str)):
        msg = get_message("location_validation_fallow", lang=code)
        if is_demo:
            return f"[DEMO MODE — ILLUSTRATIVE LOCATION DATA]\n\n⚠️ Demonstration Location Validation Notice:\n\n{msg}"
        return msg
    elif val_status == "INSUFFICIENT_SATELLITE_DATA" or ("VALIDATION_FAILED" in stress_str and ("SATELLITE" in stress_str or "IMAGERY" in stress_str or "CLOUD" in stress_str)):
        msg = get_message("location_validation_satellite_unavailable", lang=code)
        if is_demo:
            return f"[DEMO MODE — ILLUSTRATIVE LOCATION DATA]\n\n⚠️ Demonstration Location Validation Notice:\n\n{msg}"
        return msg
    elif val_status == "CROP_MISMATCH" or ("VALIDATION_FAILED" in stress_str and "CROP" in stress_str):
        crop_val = advisory.get("crop_validation") or {}
        pred_crop = crop_val.get("predicted_crop") or advisory.get("predicted_crop") or "another crop"
        rec_reason = advisory.get("recommendation") or crop_val.get("reason") or "Crop discrepancy detected against satellite observations."
        msg = get_message(
            "crop_validation_mismatch",
            lang=code,
            farm_id=farm_id,
            declared_crop=crop_display,
            predicted_crop=pred_crop,
            reason=rec_reason,
        )
        if is_demo:
            return f"[DEMO MODE — ILLUSTRATIVE LOCATION DATA]\n\n{msg}"
        return msg

    # Date formatting
    date_val = advisory.get("observation_date") or advisory.get("created_at")
    advisory_date = _format_date(date_val)

    # Stress formatting
    raw_stress = advisory.get("observed_stress") or advisory.get("stress_level") or "Unknown"
    observed_stress_display = get_localized_stress(raw_stress, code)

    # Rain formatting
    rain_val = advisory.get("rain_forecast_mm")
    if rain_val is None:
        rain_val = advisory.get("rainfall_48h")

    if rain_val is not None:
        forecast_rain_display = f"{float(rain_val):.1f} mm"
        rain_float = float(rain_val)
    else:
        if code == "mr":
            forecast_rain_display = "माहिती उपलब्ध नाही (Unavailable)"
        elif code == "hi":
            forecast_rain_display = "जानकारी उपलब्ध नहीं (Unavailable)"
        else:
            forecast_rain_display = "Data unavailable"
        rain_float = None

    # Recommended action formatting
    raw_action = advisory.get("recommended_action")
    action_key = infer_recommended_action(
        recommended_action=raw_action,
        recommendation_text=advisory.get("recommendation"),
        observed_stress=raw_stress,
        rain_mm=rain_float,
    )
    recommended_action_display = get_localized_action(action_key, code)

    # Agronomic explanation text
    crop_stage = advisory.get("crop_stage")
    advisory_explanation = get_localized_advisory(
        lang=code,
        observed_stress=raw_stress,
        recommended_action=action_key,
        crop=crop_name,
        stage=crop_stage,
        rain_48h=rain_float,
    )

    res = get_message(
        "status_advisory",
        lang=code,
        farm_id=farm_id,
        name=farmer_name,
        crop=crop_display,
        advisory_date=advisory_date,
        observed_stress=observed_stress_display,
        recommended_action=recommended_action_display,
        forecast_rain=forecast_rain_display,
        advisory_explanation=advisory_explanation,
    )
    # Append transparent crop verification note if species classification is inconclusive
    crop_val = advisory.get("crop_validation") or {}
    if crop_val.get("outcome") == "INCONCLUSIVE":
        if code == "mr":
            crop_note = f"\n\nℹ️ *पीक पडताळणी नोंद:* उपग्रह डेटावरून सक्रिय शेतजमिनीची खात्री होते. सल्ला नोंदवलेल्या {crop_display} पिकासाठी तयार केला आहे."
        elif code == "hi":
            crop_note = f"\n\nℹ️ *फसल सत्यापन टिप्पणी:* उपग्रह डेटा सक्रिय कृषि भूमि की पुष्टि करता है। सलाह घोषित {crop_display} फसल के लिए तैयार की गई है।"
        else:
            crop_note = f"\n\nℹ️ *Crop Verification Note:* Satellite observations confirm active cropland. Advisory is calibrated for declared {crop_display}."
        res = f"{res}{crop_note}"

    # Append transparent Assessment Source and Academic Prototype Disclaimer
    method = str(advisory.get("assessment_method") or "").upper()
    ml_inf = advisory.get("ml_inference") or {}
    probs = ml_inf.get("probabilities") if isinstance(ml_inf, dict) else None

    if method == "ML_PRIMARY_PREDICTOR":
        p_str = ""
        if probs and isinstance(probs, dict):
            p_none = probs.get("no_stress", 0.0)
            p_mild = probs.get("mild_stress", 0.0)
            p_severe = probs.get("severe_stress", 0.0)
            if code == "mr":
                p_str = f"\n📊 *मॉडेल संभाव्यता:* निरोगी {p_none*100:.0f}%, हलका {p_mild*100:.0f}%, तीव्र {p_severe*100:.0f}%"
            elif code == "hi":
                p_str = f"\n📊 *मॉडल प्रायिकता:* स्वस्थ {p_none*100:.0f}%, हल्का {p_mild*100:.0f}%, गंभीर {p_severe*100:.0f}%"
            else:
                p_str = f"\n📊 *Model Probabilities:* Healthy {p_none*100:.0f}%, Mild {p_mild*100:.0f}%, Severe {p_severe*100:.0f}%"

        if code == "mr":
            ml_note = (
                f"\n\n🤖 *मूल्यांकन स्रोत:* AI/ML मॉडेल (५-घटक रँडम फॉरेस्ट){p_str}\n"
                f"⚠️ *प्रायोगिक प्रोटोटाइप:* हे मॉडेल पूर्व भारतातील गव्हाच्या संशोधन डेटावर आधारित आहे. "
                f"व्यावसायिक शेती निर्णयांसाठी प्रमाणित नाही."
            )
        elif code == "hi":
            ml_note = (
                f"\n\n🤖 *मूल्यांकन स्रोत:* AI/ML मॉडल (5-फीचर रैंडम फॉरेस्ट){p_str}\n"
                f"⚠️ *अकादमिक प्रोटोटाइप:* यह मॉडल पूर्वी भारत के गेहूं अनुसंधान डेटा पर आधारित है। "
                f"वास्तविक कृषि निर्णयों के लिए प्रमाणित नहीं है।"
            )
        else:
            ml_note = (
                f"\n\n🤖 *Assessment Source:* AI/ML Model (5-Feature Random Forest){p_str}\n"
                f"⚠️ *Academic Prototype:* Experimental model trained on Eastern India wheat research data. "
                f"Not validated for real-farmer decisions."
            )
        res = f"{res}{ml_note}"

    elif "RULE_FALLBACK" in method or (method and "FALLBACK" in method):
        if "UNSUPPORTED_CROP" in method:
            if code == "mr":
                fb_reason = f"घोषित पीक ({crop_display}) गहू ML मॉडेलद्वारे समर्थित नाही."
            elif code == "hi":
                fb_reason = f"घोषित फसल ({crop_display}) गेहूं ML मॉडल द्वारा समर्थित नहीं है।"
            else:
                fb_reason = f"Declared crop ({crop_name}) is not supported by the wheat ML model."
        elif "MISSING_INPUTS" in method:
            if code == "mr":
                fb_reason = "आवश्यक उपग्रह किंवा सेन्सर डेटा उपलब्ध नाही."
            elif code == "hi":
                fb_reason = "आवश्यक उपग्रह या सेंसर डेटा उपलब्ध नहीं है।"
            else:
                fb_reason = "Required satellite or sensor data is missing or incomplete."
        else:
            if code == "mr":
                fb_reason = "ML मॉडेल अनुपलब्ध असल्याने नियम-आधारित पद्धत वापरली."
            elif code == "hi":
                fb_reason = "ML मॉडल अनुपलब्ध होने के कारण नियम-आधारित विधि प्रयुक्त की गई।"
            else:
                fb_reason = "ML inference unavailable; assessed via rule engine."

        if code == "mr":
            fb_note = (
                f"\n\n⚙️ *मूल्यांकन स्रोत:* नियम-आधारित तज्ञ इंजिन (पर्यायी पद्धत)\n"
                f"ℹ️ *कारण:* {fb_reason}"
            )
        elif code == "hi":
            fb_note = (
                f"\n\n⚙️ *मूल्यांकन स्रोत:* नियम-आधारित विशेषज्ञ इंजन (वैकल्पिक विधि)\n"
                f"ℹ️ *कारण:* {fb_reason}"
            )
        else:
            fb_note = (
                f"\n\n⚙️ *Assessment Source:* Rule-Based Expert Engine (Fallback)\n"
                f"ℹ️ *Reason:* {fb_reason}"
            )
        res = f"{res}{fb_note}"

    if is_demo:
        return f"[DEMO MODE — ILLUSTRATIVE LOCATION DATA]\n\n{res}"
    return res


def format_no_advisory(
    farm: Dict[str, Any],
    lang: str = DEFAULT_LANGUAGE,
) -> str:
    """
    Renders a friendly explanation when a farm is registered but no advisory is ready yet.
    """
    code = normalize_language(lang)
    farm_id = farm.get("id", "N/A")
    farmer_name = farm.get("farmer_name", "Farmer")
    crop_name = farm.get("crop_name", "Crop")
    crop_display = get_localized_crop(crop_name, code)

    is_demo = bool(
        farm.get("is_demo")
        or (isinstance(farm.get("notes"), str) and "demo" in farm.get("notes", "").lower())
        or (isinstance(farm.get("boundary_source"), str) and "demo" in farm.get("boundary_source", "").lower())
        or os.getenv("DEMO_MODE", "").strip().lower() in ("true", "1", "yes")
    )

    if is_demo:
        return get_message(
            "status_no_advisory_demo",
            lang=code,
            farm_id=farm_id,
            name=farmer_name,
            crop=crop_display,
        )

    return get_message(
        "status_no_advisory",
        lang=code,
        farm_id=farm_id,
        name=farmer_name,
        crop=crop_display,
    )


def format_unregistered_status(lang: str = DEFAULT_LANGUAGE) -> str:
    """
    Renders guidance for unregistered senders attempting to run the status command.
    """
    code = normalize_language(lang)
    return get_message("status_not_registered", lang=code)


def format_voice_script(
    farm: Optional[Dict[str, Any]],
    advisory: Optional[Dict[str, Any]],
    language: Optional[str] = None,
) -> Optional[str]:
    """
    Converts a structured farm advisory into a short, natural, farmer-friendly spoken voice script.
    Supports English, Marathi, and Hindi.

    Rules:
    - If advisory is withheld or farm location is unsuitable, returns None (no irrigation recommendation).
    - If crop validation indicates a mismatch, returns None (no irrigation recommendation).
    - Respects rainfall guardrails without recommending unnecessary irrigation.
    - Uses conversational, simple tone without technical jargon (no NDVI, SMAP, etc.).
    - Suitable for listening on basic smartphone speaker.
    """
    if not advisory or not isinstance(advisory, dict):
        return None

    # Check if advisory was withheld or validation failed
    val_status = str(advisory.get("validation_status") or "").strip().upper()
    stress_str = str(advisory.get("stress_level") or "").strip().upper()
    crop_val = advisory.get("crop_validation") or {}
    if crop_val.get("outcome") == "MISMATCH" or crop_val.get("is_suitable_for_advisory") is False:
        return None

    unsuitable_statuses = {
        "LIKELY_URBAN",
        "BARREN_OR_UNCERTAIN",
        "INSUFFICIENT_SATELLITE_DATA",
        "INVALID_COORDINATES",
        "UNVALIDATED",
    }
    if val_status in unsuitable_statuses or "VALIDATION_FAILED" in stress_str or advisory.get("is_suitable_for_advisory") is False:
        return None

    farm = farm or {}
    code = normalize_language(language or farm.get("preferred_language") or DEFAULT_LANGUAGE)

    is_demo = bool(
        farm.get("is_demo")
        or advisory.get("is_demo")
        or (isinstance(farm.get("notes"), str) and "demo" in farm.get("notes", "").lower())
        or os.getenv("DEMO_MODE", "").strip().lower() in ("true", "1", "yes")
    )

    # 1. Farmer Name & Greeting
    farmer_name = farm.get("farmer_name")
    if farmer_name and str(farmer_name).strip() and str(farmer_name).strip().lower() not in {"farmer", "none"}:
        name_clean = str(farmer_name).strip()
        if code == "mr":
            greeting = f"नमस्कार {name_clean}जी"
        elif code == "hi":
            greeting = f"नमस्ते {name_clean}जी"
        else:
            greeting = f"Hello {name_clean}"
    else:
        if code == "mr":
            greeting = "नमस्कार शेतकरी मित्र"
        elif code == "hi":
            greeting = "नमस्ते किसान भाई"
        else:
            greeting = "Hello"

    # 2. Crop
    raw_crop = farm.get("crop_name")
    crop_display = get_localized_crop(raw_crop, code) if raw_crop else ("पिकासाठी" if code == "mr" else ("फसल के लिए" if code == "hi" else "crop"))

    method = str(advisory.get("assessment_method") or "").upper()
    is_ml_primary = (method == "ML_PRIMARY_PREDICTOR")
    is_rule_fallback = ("RULE_FALLBACK" in method)

    if code == "mr":
        if is_ml_primary:
            intro = f"{greeting}, खेतसेन्स AI द्वारे तयार केलेला तुमच्या {crop_display} पिकासाठी हा सिंचन सल्ला आहे."
        elif is_rule_fallback:
            intro = f"{greeting}, खेतसेन्स नियम-आधारित प्रणालीवरून तुमच्या {crop_display} पिकासाठी हा सिंचन सल्ला आहे."
        else:
            intro = f"{greeting}, खेतसेन्सवरून तुमच्या {crop_display} पिकासाठी हा सिंचन सल्ला आहे."
    elif code == "hi":
        if is_ml_primary:
            intro = f"{greeting}, खेतसेंस AI द्वारा तैयार किया गया आपकी {crop_display} फसल के लिए यह सिंचाई सलाह है।"
        elif is_rule_fallback:
            intro = f"{greeting}, खेतसेंस नियम-आधारित प्रणाली से आपकी {crop_display} फसल के लिए यह सिंचाई सलाह है।"
        else:
            intro = f"{greeting}, खेतसेंस से यह आपकी {crop_display} फसल के लिए सिंचाई सलाह है।"
    else:
        crop_phrase = f"your {crop_display} crop" if raw_crop else "your crop"
        if is_ml_primary:
            intro = f"{greeting}, this is your KhetSense AI-generated irrigation advisory for {crop_phrase}."
        elif is_rule_fallback:
            intro = f"{greeting}, this is your KhetSense rule-based irrigation advisory for {crop_phrase}."
        else:
            intro = f"{greeting}, this is your KhetSense irrigation advisory for {crop_phrase}."

    if is_demo:
        if code == "mr":
            demo_prefix = "डेमो मोड सूचना: ही प्रात्यक्षिक माहिती आहे. "
        elif code == "hi":
            demo_prefix = "डेमो मोड सूचना: यह केवल प्रदर्शन के लिए जानकारी है। "
        else:
            demo_prefix = "Demo mode notice: This is illustrative location data. "
        intro = demo_prefix + intro

    # 3. Detected Crop Condition / Stress
    raw_stress = str(advisory.get("observed_stress") or advisory.get("stress_level") or "").strip().lower()
    if "severe" in raw_stress:
        if code == "mr":
            stress_sentence = "सध्या तुमच्या पिकामध्ये तीव्र पाण्याचा ताण दिसून येत आहे."
        elif code == "hi":
            stress_sentence = "वर्तमान में आपकी फसल में गंभीर पानी का तनाव देखा गया है।"
        else:
            stress_sentence = "Your crop is experiencing severe water stress."
    elif "mild" in raw_stress:
        if code == "mr":
            stress_sentence = "सध्या तुमच्या पिकामध्ये हलका पाण्याचा ताण दिसून येत आहे."
        elif code == "hi":
            stress_sentence = "वर्तमान में आपकी फसल में हल्का पानी का तनाव देखा गया है।"
        else:
            stress_sentence = "Your crop is experiencing mild water stress."
    elif "no stress" in raw_stress or "healthy" in raw_stress:
        if code == "mr":
            stress_sentence = "तुमच्या शेतात पुरेशी ओलावा असून पीक निरोगी आहे."
        elif code == "hi":
            stress_sentence = "आपकी फसल में पर्याप्त नमी है और फसल स्वस्थ है।"
        else:
            stress_sentence = "Your crop has adequate moisture and is in good health."
    else:
        if code == "mr":
            stress_sentence = "शेतातील ओलाव्याचे निरीक्षण सुरू आहे."
        elif code == "hi":
            stress_sentence = "खेत की नमी की निगरानी की जा रही है।"
        else:
            stress_sentence = "Field moisture is being monitored."

    # 4. Expected Rainfall Info
    rain_val = advisory.get("rain_forecast_mm")
    if rain_val is None:
        rain_val = advisory.get("rainfall_48h")

    if rain_val is not None:
        try:
            rain_float = float(rain_val)
        except (ValueError, TypeError):
            rain_float = None
    else:
        rain_float = None

    if rain_float is not None:
        if rain_float >= 15.0:
            if code == "mr":
                rain_sentence = f"पुढील दोन दिवसांत सुमारे {rain_float:.1f} मिलिमीटर मुसळधार पावसाचा अंदाज आहे."
            elif code == "hi":
                rain_sentence = f"अगले 48 घंटों में लगभग {rain_float:.1f} मिलीमीटर भारी बारिश का अनुमान है।"
            else:
                rain_sentence = f"Heavy rainfall of about {rain_float:.1f} millimeters is forecast in the next 48 hours."
        elif rain_float >= 5.0:
            if code == "mr":
                rain_sentence = f"पुढील दोन दिवसांत सुमारे {rain_float:.1f} मिलिमीटर मध्यम पावसाचा अंदाज आहे."
            elif code == "hi":
                rain_sentence = f"अगले 48 घंटों में लगभग {rain_float:.1f} मिलीमीटर मध्यम बारिश का अनुमान है।"
            else:
                rain_sentence = f"Moderate rainfall of about {rain_float:.1f} millimeters is expected in the next 48 hours."
        elif rain_float > 0.0:
            if code == "mr":
                rain_sentence = f"पुढील दोन दिवसांत सुमारे {rain_float:.1f} मिलिमीटर हलक्या पावसाचा अंदाज आहे."
            elif code == "hi":
                rain_sentence = f"अगले दो दिनों में लगभग {rain_float:.1f} मिलीमीटर हल्की बारिश का अनुमान है।"
            else:
                rain_sentence = f"Light rain of about {rain_float:.1f} millimeters is expected."
        else:
            if code == "mr":
                rain_sentence = "पुढील दोन दिवसांत पावसाची शक्यता नाही."
            elif code == "hi":
                rain_sentence = "अगले 48 घंटों में बारिश की संभावना नहीं है।"
            else:
                rain_sentence = "No rainfall is expected in the next 48 hours."
    else:
        if code == "mr":
            rain_sentence = "सध्या पावसाचा अंदाज उपलब्ध नाही."
        elif code == "hi":
            rain_sentence = "वर्तमान में बारिश का पूर्वानुमान उपलब्ध नहीं है।"
        else:
            rain_sentence = "Rainfall forecast data is currently unavailable."

    # 5. Recommended Irrigation Action & Timing
    raw_action = advisory.get("recommended_action")
    action_key = infer_recommended_action(
        recommended_action=raw_action,
        recommendation_text=advisory.get("recommendation"),
        observed_stress=advisory.get("observed_stress") or advisory.get("stress_level"),
        rain_mm=rain_float,
    )

    if action_key == ACTION_IRRIGATE_NOW:
        if code == "mr":
            action_sentence = "पिकाचे नुकसान टाळण्यासाठी कृपया ताबडतोब पाणी द्या."
        elif code == "hi":
            action_sentence = "फसल के नुकसान से बचने के लिए कृपया तुरंत सिंचाई करें।"
        else:
            action_sentence = "Please irrigate your crop immediately to prevent yield loss."
    elif action_key == ACTION_IRRIGATE_LIGHTLY:
        if code == "mr":
            action_sentence = "मध्यम पाऊस अपेक्षित असल्याने, शेतात पाणी साचू नये म्हणून केवळ हलके पाणी द्या."
        elif code == "hi":
            action_sentence = "मध्यम बारिश की संभावना है, इसलिए खेत में पानी भरने से बचने के लिए केवल हल्की सिंचाई करें।"
        else:
            action_sentence = "Because moderate rain is expected, apply only light irrigation to avoid waterlogging."
    elif action_key == ACTION_SCHEDULE_IRRIGATION:
        if code == "mr":
            action_sentence = "कृपया येत्या २४ ते ४८ तासांत पाणी देण्याचे नियोजन करा."
        elif code == "hi":
            action_sentence = "कृपया अगले 24 से 48 घंटों में सिंचाई की योजना बनाएं।"
        else:
            action_sentence = "Please plan to irrigate your field within the next 24 to 48 hours."
    elif action_key == ACTION_DELAY_RECHECK:
        if code == "mr":
            action_sentence = "पावसाचा अंदाज असल्याने सध्या पाणी देणे पुढे ढकला आणि पावसानंतर शेतातील ओलावा तपासा."
        elif code == "hi":
            action_sentence = "बारिश का अनुमान होने के कारण अभी सिंचाई टालें और बारिश के बाद खेत की नमी जांचें।"
        else:
            action_sentence = "Please delay irrigation due to expected rain and recheck your field after the rainfall."
    elif action_key == ACTION_HOLD_RECHECK:
        if code == "mr":
            action_sentence = "मुसळधार पाऊस अपेक्षित असल्याने पाणी देणे थांबवा, जेणेकरून शेतात पाणी साचणार नाही. पावसानंतर पुन्हा तपासा."
        elif code == "hi":
            action_sentence = "भारी बारिश की संभावना है, इसलिए सिंचाई रोकें ताकि जलभराव न हो। बारिश के बाद स्थिति दोबारा जांचें।"
        else:
            action_sentence = "Heavy rain is expected. Please hold off all irrigation to prevent waterlogging and check again after the rain."
    elif action_key == ACTION_NO_ACTION:
        if code == "mr":
            action_sentence = "सध्या पाणी देण्याची आवश्यकता नाही."
        elif code == "hi":
            action_sentence = "इस समय सिंचाई की कोई आवश्यकता नहीं है।"
        else:
            action_sentence = "No irrigation is needed at this time."
    else:
        if code == "mr":
            action_sentence = "कृपया शेतातील ओलावा स्वतः तपासा किंवा काही दिवसांनी पुन्हा status पाठवा."
        elif code == "hi":
            action_sentence = "कृपया खेत की नमी स्वयं जांचें या कुछ दिनों बाद status लिखकर भेजें।"
        else:
            action_sentence = "Please check your field moisture directly or send status again in a few days."

    # 6. Closing
    if code == "mr":
        closing = "पुढील सल्ल्यासाठी खेतसेन्सशी जोडलेले राहा. धन्यवाद."
    elif code == "hi":
        closing = "अगली सलाह के लिए खेतसेंस से जुड़े रहें। धन्यवाद।"
    else:
        closing = "Stay tuned to KhetSense for your next advisory. Thank you."

    # Assemble into a clean, spoken paragraph
    script_parts = [intro, stress_sentence, rain_sentence, action_sentence, closing]
    return " ".join(p.strip() for p in script_parts if p and p.strip())


# ==============================================================================
# 5b. TEXT SANITIZATION & TRILINGUAL SCRIPT HELPERS
# ==============================================================================

def clean_text_for_speech(text: Optional[str], lang: str = DEFAULT_LANGUAGE) -> str:
    """
    Sanitizes WhatsApp chatbot text for natural, human-sounding neural TTS:
    - Strips emojis and decorative Unicode symbols.
    - Strips WhatsApp markdown (*bold*, _italic_, ~strikethrough~, ```code```).
    - Replaces raw map URLs with clean spoken descriptions in the target language.
    - Replaces bullet points (*, -) with natural pauses or list numbers.
    - Preserves numbers, crop names, farmer names, coordinates, and instructions.
    - Collapses redundant whitespace.
    """
    if not text or not str(text).strip():
        return ""

    code = normalize_language(lang)
    cleaned = str(text)

    # 1. Replace map URLs with natural phrasing in target language
    if code == "mr":
        map_phrase = "नकाशावरील जागेवर"
        link_phrase = "दिलेल्या लिंकवर"
    elif code == "hi":
        map_phrase = "नक्शे वाले स्थान पर"
        link_phrase = "दी गई लिंक पर"
    else:
        map_phrase = "on the map location"
        link_phrase = "at the link provided"

    cleaned = re.sub(
        r"https?://(?:(?:www\.)?google\.[a-z.]+/maps|maps\.google\.[a-z.]+|goo\.gl/maps|maps\.app\.goo\.gl)[^\s]*",
        map_phrase,
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"https?://[^\s]+", link_phrase, cleaned, flags=re.IGNORECASE)

    # 2. Strip code blocks and markdown fences
    cleaned = re.sub(r"```[^\n]*\n(.*?)```", r"\1", cleaned, flags=re.DOTALL)
    cleaned = cleaned.replace("```", "")

    # 3. Strip bold (*), italics (_), strikethrough (~)
    cleaned = re.sub(r"\*([^\*]+)\*", r"\1", cleaned)
    cleaned = re.sub(r"_([^_]+)_", r"\1", cleaned)
    cleaned = re.sub(r"~([^~]+)~", r"\1", cleaned)
    cleaned = cleaned.replace("*", "").replace("_", "").replace("~", "")

    # 4. Strip emojis and decorative Unicode symbols
    cleaned = re.sub(r"[\U00010000-\U0010ffff\u2600-\u27bf\u25a0-\u25ff\ufe00-\ufe0f]", "", cleaned)

    # 5. Clean bullet points at beginning of lines into clean speech
    cleaned = re.sub(r"^[ \t]*[\-\•][ \t]+", "", cleaned, flags=re.MULTILINE)

    # 6. Normalize separators and line breaks
    cleaned = re.sub(r"[-=]{3,}", " ", cleaned)
    lines = [l.strip() for l in cleaned.splitlines() if l.strip()]
    punctuated_lines = []
    for line in lines:
        if line and not line[-1] in {".", "!", "?", "।", ":", ","}:
            punctuated_lines.append(line + ".")
        else:
            punctuated_lines.append(line)

    result = " ".join(punctuated_lines)
    result = re.sub(r"\.{2,}", ".", result)
    result = re.sub(r"\s+", " ", result).strip()
    return result


def format_trilingual_welcome_script() -> List[Tuple[str, str]]:
    """
    Returns the initial greeting as ordered (text, language_code) segments.
    Each segment is synthesized using that language's native neural voice for
    natural pronunciation across English, Marathi, and Hindi.
    """
    return [
        (
            "Welcome to KhetSense AI. Please choose your preferred language. Reply 1 for English.",
            "en",
        ),
        (
            "खेतसेन्स मध्ये आपले स्वागत आहे. कृपया तुमची पसंतीची भाषा निवडा. मराठीसाठी 2 पाठवा.",
            "mr",
        ),
        (
            "खेतसेंस में आपका स्वागत है। कृपया अपनी पसंदीदा भाषा चुनें। हिंदी के लिए 3 भेजें।",
            "hi",
        ),
    ]


# ==============================================================================
# 6. LEGACY EXPORTS FOR BACKWARDS COMPATIBILITY
# ==============================================================================

WELCOME_PROMPT = MESSAGES["welcome_and_language"]["en"]
NAME_CONFIRM_PROMPT = MESSAGES["name_confirm"]["en"]
NAME_CONFIRM_INVALID_PROMPT = MESSAGES["name_confirm_invalid"]["en"]
CROP_PROMPT = MESSAGES["crop_prompt"]["en"]
CROP_INVALID_PROMPT = MESSAGES["crop_invalid"]["en"]
ACREAGE_PROMPT = MESSAGES["acreage_prompt"]["en"]
ACREAGE_INVALID_PROMPT = MESSAGES["acreage_invalid"]["en"]
LOCATION_PROMPT = MESSAGES["location_prompt"]["en"]
LOCATION_INVALID_PROMPT = MESSAGES["location_invalid"]["en"]
LOCATION_OUT_OF_BOUNDS_PROMPT = MESSAGES["location_out_of_bounds"]["en"]
REGISTRATION_SUCCESS = MESSAGES["registration_success"]["en"]
ALREADY_REGISTERED = MESSAGES["already_registered"]["en"]
ERROR_GENERIC = MESSAGES["error_generic"]["en"]
RESET_SUCCESS = MESSAGES["reset_success"]["en"]
STATUS_ADVISORY = MESSAGES["status_advisory"]["en"]
STATUS_NO_ADVISORY = MESSAGES["status_no_advisory"]["en"]
STATUS_NOT_REGISTERED = MESSAGES["status_not_registered"]["en"]
STATUS_PROCESSING = MESSAGES["status_processing"]["en"]
PIPELINE_FAILED_NOTICE = MESSAGES["pipeline_failed_notice"]["en"]
LOCATION_CHOICE_PROMPT = MESSAGES["location_choice_prompt"]["en"]
LOCATION_AT_FARM_PROMPT = MESSAGES["location_at_farm_prompt"]["en"]
LOCATION_AWAY_PROMPT = MESSAGES["location_away_prompt"]["en"]
LOCATION_CONFIRM_PROMPT = MESSAGES["location_confirm_prompt"]["en"]
LOCATION_REENTER_PROMPT = MESSAGES["location_reenter_prompt"]["en"]
LOCATION_AMBIGUOUS_PROMPT = MESSAGES["location_ambiguous_prompt"]["en"]
LOCATION_NOT_FOUND_PROMPT = MESSAGES["location_not_found_prompt"]["en"]
LOCATION_VALIDATION_URBAN = MESSAGES["location_validation_urban"]["en"]
LOCATION_VALIDATION_FALLOW = MESSAGES["location_validation_fallow"]["en"]
LOCATION_VALIDATION_SATELLITE_UNAVAILABLE = MESSAGES["location_validation_satellite_unavailable"]["en"]
LOCATION_VALIDATION_DEMO_FAILED = MESSAGES["location_validation_demo_failed"]["en"]
DEMO_REGISTRATION_SUCCESS = MESSAGES["demo_registration_success"]["en"]
STATUS_NO_ADVISORY_DEMO = MESSAGES["status_no_advisory_demo"]["en"]
CROP_VALIDATION_MISMATCH = MESSAGES["crop_validation_mismatch"]["en"]
CROP_VALIDATION_INCONCLUSIVE = MESSAGES["crop_validation_inconclusive"]["en"]
