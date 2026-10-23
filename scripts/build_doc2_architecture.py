#!/usr/bin/env python3
"""
KhetSense AI — Builder for Document 2: KhetSense_System_Architecture_and_Workflow.docx
"""

from doc_helpers import (
    create_base_doc, add_heading_1, add_heading_2, add_heading_3,
    add_bullet, add_callout, apply_table_styles, save_doc,
    HEX_WARN_BG, HEX_GREEN_BG
)

def build_doc2():
    doc = create_base_doc(
        "KhetSense AI — System Architecture & Workflow",
        "Technical Architecture, Subsystem Design, Component Data Flow, and Operational Workflows"
    )

    # 1. High-Level System Architecture
    add_heading_1(doc, "1. High-Level System Architecture")
    doc.add_paragraph(
        "KhetSense AI is architected as an asynchronous, event-driven, decoupled micro-pipeline. "
        "The system coordinates incoming mobile user requests, geospatial land screening, remote-sensing "
        "data extraction, hybrid machine-learning and rule-based decisioning, rainfall safety filtering, "
        "and multilingual text and voice delivery."
    )
    doc.add_paragraph(
        "The architecture is organized into five distinct, decoupled functional layers:"
    )
    add_bullet(doc, "Mobile WhatsApp client communicating with the Meta WhatsApp Cloud API gateway over secure webhooks.", "Layer 1: Farmer Messaging Layer — ")
    add_bullet(doc, "FastAPI / Starlette asynchronous server providing HMAC-SHA256 signature verification, request payload size limits (1 MB), and message deduplication.", "Layer 2: Webhook & Security Layer — ")
    add_bullet(doc, "Multi-source cloud extractors querying Google Earth Engine (Sentinel-2), NASA CMR API (SMAP 9km radiometry), and OpenWeatherMap (48-hour forward precipitation).", "Layer 3: Geospatial Ingestion Layer — ")
    add_bullet(doc, "Phase 8 primary 5-feature Random Forest model for Wheat, coupled with deterministic agronomic expert rules for unsupported crops and missing data, plus independent rainfall guardrails.", "Layer 4: Core Decision & Safeguard Engine — ")
    add_bullet(doc, "Trilingual template engine generating WhatsApp cards in English, Marathi, and Hindi, coupled with an Edge-TTS Opus audio synthesizer.", "Layer 5: Multilingual Delivery Layer — ")

    doc.add_paragraph("\n[SYSTEM ARCHITECTURE BLOCK DIAGRAM]")
    arch_ascii = (
        "+-----------------------------------------------------------------------------------+\n"
        "|                         LAYER 1: FARMER MESSAGING LAYER                           |\n"
        "|  Farmer Mobile Phone  <==== (WhatsApp Chat & Audio) ====> Meta WhatsApp Cloud API |\n"
        "+-----------------------------------------+-----------------------------------------+\n"
        "                                          |\n"
        "                               HTTPS Webhook POST\n"
        "                                          v\n"
        "+-----------------------------------------+-----------------------------------------+\n"
        "|                       LAYER 2: WEBHOOK & SECURITY LAYER                           |\n"
        "|  - Webhook Server (FastAPI / Starlette)      - HMAC-SHA256 Signature Auth         |\n"
        "|  - 1 MB Payload Stream Enforcement          - Deduplication (processed_messages)  |\n"
        "+-----------------------------------------+-----------------------------------------+\n"
        "                                          |\n"
        "                                          v\n"
        "+-----------------------------------------+-----------------------------------------+\n"
        "|                     LAYER 3: GEOSPATIAL INGESTION LAYER                           |\n"
        "|  - Location Resolver (GPS Pin / Short URL)   - ESA WorldCover 10m Land Screening  |\n"
        "|  - Google Earth Engine (Sentinel-2 L2A)      - NASA CMR Earthdata (SMAP L3 9km)   |\n"
        "|  - OpenWeatherMap 48-Hour Precipitation Forecast                                  |\n"
        "+-----------------------------------------+-----------------------------------------+\n"
        "                                          |\n"
        "                                          v\n"
        "+-----------------------------------------+-----------------------------------------+\n"
        "|                   LAYER 4: CORE DECISION & SAFEGUARD ENGINE                       |\n"
        "|  - Phase 8 Primary 5-Feature Random Forest (Tuned Severe Threshold T = 0.27)      |\n"
        "|  - Deterministic Agronomic Rule Baseline & Unsupported Crop Fallback (Cotton/Soy) |\n"
        "|  - Two-Tier Rainfall Safety Guardrail Policy (Tier 1: 5.0 mm, Tier 2: 15.0 mm)   |\n"
        "|  - Zero-Fabrication Missing Sensor Data Handler (ACTION_INSUFFICIENT_DATA)        |\n"
        "+-----------------------------------------+-----------------------------------------+\n"
        "                                          |\n"
        "                                          v\n"
        "+-----------------------------------------+-----------------------------------------+\n"
        "|                     LAYER 5: MULTILINGUAL DELIVERY LAYER                          |\n"
        "|  - Trilingual Structured WhatsApp Cards (English, Marathi, Hindi)                 |\n"
        "|  - Vernacular Neural Text-to-Speech (mr-IN-AarohiNeural, hi-IN-SwaraNeural)       |\n"
        "|  - Opus Audio Note Formatter (audio/ogg; codecs=opus)                             |\n"
        "|  - Outbound Safety Guardrail Switch (ENABLE_OUTBOUND_WHATSAPP)                    |\n"
        "+-----------------------------------------------------------------------------------+"
    )
    doc.add_paragraph(arch_ascii)

    # 2. Component Descriptions
    add_heading_1(doc, "2. Detailed Component Descriptions")
    
    add_heading_2(doc, "A. Webhook Ingestion & Security Module (`webhook_server.py`)")
    doc.add_paragraph(
        "Acts as the single entry point for all incoming HTTP traffic from Meta's WhatsApp Cloud API. "
        "It validates the `X-Hub-Signature-256` header against the application secret, enforces a 1 MB stream "
        "limit to prevent Denial-of-Service (DoS) buffer exhaustion, and deduplicates message IDs against the database."
    )

    add_heading_2(doc, "B. Registration & Session State Machine (`whatsapp/registration_flow.py`)")
    doc.add_paragraph(
        "Manages multi-turn onboarding for new farmers. Tracks session state across: AWAITING_LANGUAGE, "
        "AWAITING_NAME, AWAITING_NAME_CONFIRMATION, AWAITING_LOCATION, AWAITING_LOCATION_CHOICE, "
        "AWAITING_LOCATION_CONFIRMATION, AWAITING_CROP, AWAITING_ACRES, and REGISTERED. "
        "Guarantees that a farmer's language preference and farm location are confirmed before pipeline execution."
    )

    add_heading_2(doc, "C. Location Resolution & Geocoding (`pipeline/geo_utils.py`)")
    doc.add_paragraph(
        "Accepts multi-modal geographic inputs: native WhatsApp GPS location pins, Google Maps short URLs "
        "(e.g., `maps.app.goo.gl`), full Google Maps URLs, or typed village names. Resolves redirected URLs "
        "securely and extracts precise decimal latitude and longitude coordinates within India's borders."
    )

    add_heading_2(doc, "D. Agricultural Land-Cover Validator (`pipeline/location_validator.py`)")
    doc.add_paragraph(
        "Queries the ESA WorldCover 10m global land-cover dataset centered on the farm coordinates. "
        "Screens the location to ensure it falls within Class 40 (Cropland). If the centroid falls on Class 50 (Built-up/Urban) "
        "or Class 60 (Barren), registration is halted to prevent false stress advisories on concrete surfaces."
    )

    add_heading_2(doc, "E. Remote Sensing Ingestion Engine (`pipeline/test_pipeline.py`)")
    doc.add_paragraph(
        "Coordinates external API calls: fetches ESA Sentinel-2 Bottom-Of-Atmosphere reflectance bands (B4, B5, B8, B11) "
        "from Google Earth Engine with QA60 cloud masking (<20% cloud cover); queries the NASA CMR API for SMAP Enhanced L3 "
        "radiometry (volumetric soil moisture 0-5 cm); and queries OpenWeatherMap for forward precipitation."
    )

    add_heading_2(doc, "F. Primary ML Inference Engine (`pipeline/ml_inference.py`)")
    doc.add_paragraph(
        "Loads the live-native 5-feature Random Forest model (`random_forest_5feat.joblib`) and preprocessor bundle. "
        "Imputes missing features using training-set medians, extracts class probabilities, applies the calibrated "
        "severe-stress threshold (T = 0.27), and returns the primary stress prediction."
    )

    add_heading_2(doc, "G. Agronomic Classifier & Guardrail Engine (`pipeline/classifier.py`)")
    doc.add_paragraph(
        "Houses the deterministic agronomic expert rules (NDVI and SMAP thresholds), the unsupported crop fallback router, "
        "and the two-tier rainfall guardrail policy. Serves as the ultimate authority for converting stress classifications "
        "into safe, actionable irrigation advice."
    )

    add_heading_2(doc, "H. Vernacular TTS Synthesis Provider (`pipeline/tts_provider.py`)")
    doc.add_paragraph(
        "Synthesizes natural spoken voice advisories using Edge-TTS or Google Cloud TTS in Marathi, Hindi, and English. "
        "Converts raw audio streams into WhatsApp-compliant Opus OGG voice notes (`audio/ogg; codecs=opus`)."
    )

    # 3. Data-Flow Explanation
    add_heading_1(doc, "3. End-to-End Data Flow Explanation")
    doc.add_paragraph("The life cycle of an advisory request follows a rigorous 7-stage data flow:")
    add_bullet(doc, "Farmer sends 'status' to the KhetSense WhatsApp number. Meta forwards an encrypted webhook payload.", "Stage 1 (Ingestion): ")
    add_bullet(doc, "Webhook server verifies signature, drops duplicate message IDs, and retrieves the registered farm profile.", "Stage 2 (Verification): ")
    add_bullet(doc, "Pipeline queries GEE for Sentinel-2 bands, NASA CMR for SMAP soil moisture, and OpenWeatherMap for rain.", "Stage 3 (Telemetry Extraction): ")
    add_bullet(doc, "Pipeline computes NDVI, NDWI, NDRE, MSAVI, and SMAP % after validating sensor freshness.", "Stage 4 (Feature Computation): ")
    add_bullet(doc, "If crop is Wheat, ML predicts stress state. If crop is Cotton/Soybean, rule fallback is executed.", "Stage 5 (Stress Assessment): ")
    add_bullet(doc, "Observed stress is evaluated against 48h forward rainfall forecast (5mm / 15mm thresholds).", "Stage 6 (Rainfall Guardrail): ")
    add_bullet(doc, "Formatted WhatsApp text card and spoken voice note are generated in farmer's chosen language.", "Stage 7 (Delivery Formatting): ")

    # 4. Operational Workflow
    add_heading_1(doc, "4. Operational Workflow & Decision Flowchart")
    doc.add_paragraph(
        "The operational decision logic implemented in Phase 8 strictly separates biophysical stress prediction "
        "from the final irrigation action recommendation, as shown in the decision flow diagram below:"
    )

    wf_ascii = (
        "                    [ incoming farmer 'status' command ]\n"
        "                                    |\n"
        "                                    v\n"
        "                     { Are core sensor inputs valid? }\n"
        "                               /         \\\n"
        "                      [No]    /           \\    [Yes]\n"
        "                             v             v\n"
        "                 ( ACTION_INSUFFICIENT_DATA )   { Is declared crop Wheat? }\n"
        "                 ( No numbers fabricated   )          /         \\\n"
        "                                             [No]   /           \\   [Yes]\n"
        "                                                   v             v\n"
        "                                      ( RULE-BASED FALLBACK )   ( 5-FEATURE ML PREDICTION )\n"
        "                                      ( Explicit Cotton/Soy )   ( Tuned Threshold T=0.27  )\n"
        "                                                   \\             /\n"
        "                                                    v           v\n"
        "                                            [ Candidate Observed Stress ]\n"
        "                                            ( No / Mild / Severe Stress )\n"
        "                                                          |\n"
        "                                                          v\n"
        "                                       { Check 48-Hour Forward Rain Forecast }\n"
        "                                          /               |               \\\n"
        "                                         /                |                \\\n"
        "                     [ Rain >= 15.0 mm ]/     [ 5.0 <= Rain < 15.0 mm ]     \\[ Rain < 5.0 mm ]\n"
        "                                       /                  |                  \\\n"
        "                                      v                   v                   v\n"
        "                           ( HOLD, RE-CHECK )    ( HOLD & MONITOR )    ( IRRIGATE / MONITOR )\n"
        "                           ( Halts irrigation)   ( Defer if mild  )    ( Normal advisory    )\n"
        "                                       \\                  |                  /\n"
        "                                        \\                 |                 /\n"
        "                                         v                v                v\n"
        "                                    [ Format Trilingual WhatsApp Text Card ]\n"
        "                                    [ Synthesize Vernacular Opus Voice Note ]"
    )
    doc.add_paragraph(wf_ascii)

    # 5. External Services and Integrations
    add_heading_1(doc, "5. External Services and API Integrations")
    tbl_ext = doc.add_table(rows=7, cols=4)
    tbl_ext.rows[0].cells[0].text = "External Service"
    tbl_ext.rows[0].cells[1].text = "Integration Method"
    tbl_ext.rows[0].cells[2].text = "Data Exchanged"
    tbl_ext.rows[0].cells[3].text = "Fallback / Safe Handling"
    
    ext_data = [
        ("Meta WhatsApp Cloud API", "HTTPS Webhook & Graph API v18.0", "Inbound messages, outbound text & Opus audio", "Outbound kill-switch (`ENABLE_OUTBOUND_WHATSAPP=false`) in test/demo"),
        ("Google Earth Engine (GEE)", "Official `earthengine-api` Python SDK", "Sentinel-2 L2A surface reflectance (B4, B5, B8, B11)", "Cloud filtering QA60; missing sensor fallback if scene cloudy (>20%)"),
        ("NASA Earthdata (CMR API)", "REST API over HTTPS", "SMAP Enhanced L3 radiometry (SPL3SMP_E soil moisture)", "Fallback to optical-only rule assessment if SMAP 9km grid unavailable"),
        ("OpenWeatherMap API", "REST API (5-day / 3-hour forecast)", "48-hour forward precipitation, temp, humidity", "If unavailable, issues advisory with explicit 'weather unverified' warning"),
        ("Edge-TTS (Microsoft Neural)", "Async WebSocket stream (`edge-tts`)", "Advisory text script -> OGG Opus audio stream", "Falls back to MockTTSProvider in offline CI/CD or Google Cloud TTS"),
        ("Supabase (PostgreSQL/PostGIS)", "REST / Python `supabase-py` SDK", "Farmers, farms, polygons, advisories, dedup", "Full SQLite / In-Memory simulation for dry runs without database writes")
    ]
    for r_idx, r_data in enumerate(ext_data, start=1):
        for c_idx, val in enumerate(r_data):
            tbl_ext.rows[r_idx].cells[c_idx].text = val
    apply_table_styles(tbl_ext, [1.5, 1.5, 2.0, 1.5])

    # 6. Error Handling & Failure Scenarios
    add_heading_1(doc, "6. Error Handling and Resilience Architecture")
    add_bullet(doc, "If HMAC signature does not match, request is immediately rejected with HTTP 403 Forbidden.", "1. Unauthorized Webhook Call: ")
    add_bullet(doc, "If request payload exceeds 1 MB, connection is terminated with HTTP 413 to prevent RAM exhaustion.", "2. Oversized Payload (DoS Protection): ")
    add_bullet(doc, "Duplicate WhatsApp message IDs are recorded in `processed_messages` and ignored to avoid double-triggers.", "3. Network Replay / Duplicate Ingestion: ")
    add_bullet(doc, "If GPS coordinates fall outside India's bounding box (lat 6-38°N, lon 68-98°E), farmer is prompted to re-enter.", "4. Invalid Geographic Coordinates: ")
    add_bullet(doc, "If ESA WorldCover classifies location as Urban (Class 50) or Barren (Class 60), registration is declined.", "5. Non-Agricultural Land Overlap: ")
    add_bullet(doc, "If cloudy scene (>20%) or sensor telemetry outage occurs, advisory outputs 'INSUFFICIENT DATA'; zero values are fabricated.", "6. Missing / Cloudy Satellite Telemetry: ")
    add_bullet(doc, "If TTS synthesis encounters network timeout, advisory text card is delivered with a clear voice failure note.", "7. Voice Synthesis Failure: ")

    # 7. Deployment Architecture
    add_heading_1(doc, "7. Deployment and Execution Architecture")
    doc.add_paragraph(
        "KhetSense AI is designed for containerized cloud or on-premise execution: "
        "The application can run as a Docker container on Google Cloud Run, AWS App Runner, or a local server. "
        "All secrets, API tokens, and operational flags are injected strictly through environment variables. "
        "In offline demonstration and test environments, `ENABLE_OUTBOUND_WHATSAPP=false` prevents accidental "
        "external message transmission while maintaining 100% pipeline fidelity in memory."
    )

    save_doc(doc, "KhetSense_System_Architecture_and_Workflow.docx")

if __name__ == "__main__":
    build_doc2()
