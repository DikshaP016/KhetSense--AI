#!/usr/bin/env python3
"""
KhetSense AI — WhatsApp Message Templates
Contains all user-facing strings and message templates in English.
"""

WELCOME_PROMPT = (
    "Welcome to KhetSense AI! 🌱\n"
    "Your satellite-powered precision farming assistant.\n\n"
    "Let's get your farm registered in just a few steps.\n\n"
    "What is your full name?"
)

NAME_CONFIRM_PROMPT = (
    "Is your name {name}?\n\n"
    "Reply YES to confirm, or send your name again."
)

NAME_CONFIRM_INVALID_PROMPT = (
    "Please reply YES if your name is {name}, or send your full name again."
)

CROP_PROMPT = (
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
)

CROP_INVALID_PROMPT = (
    "Sorry, we couldn't recognize that crop. 🌱\n\n"
    "Please choose one of our supported crops:\n"
    "Cotton, Soybean, Wheat, Rice, Pigeon Pea (Tur), Chickpea (Chana), "
    "Sugarcane, Maize, or Onion."
)

ACREAGE_PROMPT = (
    "Great! Crop set to {crop}.\n\n"
    "How large is your farm in acres? (e.g., 2.5 or 5)\n\n"
    "If you're not sure, reply 'skip' to use our standard default "
    "(2.5 acres / 1.0 hectare)."
)

ACREAGE_INVALID_PROMPT = (
    "Please enter a valid farm size in acres between 0.1 and 50.0 (e.g., 2.5), "
    "or reply 'skip' to use the default."
)

LOCATION_PROMPT = (
    "Got it: {acreage_str}.\n\n"
    "Finally, please share your farm location pin 📍:\n"
    "1. Tap the paperclip/attachment icon (+)\n"
    "2. Select 'Location'\n"
    "3. Send your current location or drop a pin on your farm field."
)

LOCATION_INVALID_PROMPT = (
    "Please send a WhatsApp Location pin 📍 for your farm field:\n"
    "Tap the attachment (+) icon, select 'Location', and send your farm's pin."
)

LOCATION_OUT_OF_BOUNDS_PROMPT = (
    "The coordinates provided appear to be outside India (Lat 6.0–38.0°N, Lon 68.0–98.0°E).\n\n"
    "KhetSense currently monitors farm plots within India. "
    "Please share a valid farm location pin located in India."
)

REGISTRATION_SUCCESS = (
    "🎉 Farm Registration Complete!\n\n"
    "Farm ID: #{farm_id}\n"
    "Farmer: {name}\n"
    "Crop: {crop}\n"
    "Estimated Area: {area:.2f} acres\n"
    "Boundary: Approximate square area around your pin (estimated)\n"
    "Pin Location: Lat {lat:.5f}, Lon {lon:.5f}\n\n"
    "Your farm details and estimated boundary have been recorded in KhetSense."
)

ALREADY_REGISTERED = (
    "You are already registered with KhetSense AI! 🌱\n\n"
    "Farm ID: #{farm_id}\n"
    "Farmer: {name}\n"
    "Crop: {crop}\n\n"
    "To view your farm details or run a status check, reply 'status'.\n"
    "If you need to re-register with a new farm location, reply 'restart'."
)

ERROR_GENERIC = (
    "We encountered a temporary issue processing your message. "
    "Please try again in a few moments, or reply 'restart' to start registration over."
)

RESET_SUCCESS = (
    "Registration has been reset. Let's start fresh! 🌱\n\n"
    "What is your full name?"
)
