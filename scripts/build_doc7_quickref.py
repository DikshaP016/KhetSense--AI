#!/usr/bin/env python3
"""
KhetSense AI — Builder for Document 7: KhetSense_Project_Quick_Reference.docx
"""

from doc_helpers import (
    create_base_doc, add_heading_1, add_heading_2, add_heading_3,
    add_bullet, add_callout, apply_table_styles, save_doc,
    HEX_WARN_BG, HEX_GREEN_BG
)

def build_doc7():
    doc = create_base_doc(
        "KhetSense AI — Project Quick Reference & Viva Guide",
        "Concise Master Summary, Architectural Key Facts, Viva Q&A Guide, and Evaluator Talking Points"
    )

    # 1. One-Paragraph Project Summary
    add_heading_1(doc, "1. Project Summary in One Paragraph")
    doc.add_paragraph(
        "KhetSense AI is an automated, zero-hardware, cloud-native precision irrigation advisory platform designed to help "
        "resource-poor smallholder farmers optimize water management. By extracting 10-meter optical surface reflectance from "
        "ESA Sentinel-2 satellites, 9-km passive microwave soil moisture from NASA's SMAP mission, and localized 48-hour forward "
        "precipitation forecasts from OpenWeatherMap, the system remotely monitors crop water stress without requiring costly "
        "in-field physical sensors. In Phase 8, a live-native 5-feature Random Forest model serves as the primary stress predictor "
        "for supported wheat crops, backed by deterministic rule-based fallbacks for unsupported crops (Cotton/Soybean) and a "
        "two-tier rainfall safety guardrail (5 mm and 15 mm). Actionable advisories are delivered directly through Meta WhatsApp "
        "in English, Marathi, and Hindi via visual status cards and edge-synthesized neural voice notes, verified by 401 automated tests."
    )

    # 2. Problem Statement in 3 Bullets
    add_heading_1(doc, "2. Problem Statement (The Triple Divide)")
    add_bullet(doc, "In-situ soil probes cost $200–$500 per acre, which smallholders cannot afford, and buried sensors frequently break during tractor tillage.", "1. Hardware & Capital Cost Barrier: ")
    add_bullet(doc, "Conventional agricultural apps require English literacy and complex smartphone navigation, excluding vernacular-speaking farmers.", "2. Interface & Literacy Barrier: ")
    add_bullet(doc, "Government agro-bulletins cover thousands of square kilometers, failing to inform an individual farmer about their specific field.", "3. Spatial Coarseness Barrier: ")

    # 3. Main Objectives in 5 Bullets
    add_heading_1(doc, "3. Core Objectives")
    add_bullet(doc, "Eliminate in-field hardware by extracting Sentinel-2 optical bands and NASA SMAP microwave soil moisture from cloud APIs.", "1. Zero-Hardware Telemetry: ")
    add_bullet(doc, "Compute NDVI, NDWI (Gao 1996), NDRE (Barnes 2000), and MSAVI (Qi 1994) with proper surface reflectance scaling.", "2. Multi-Spectral Feature Engineering: ")
    add_bullet(doc, "Operate a 5-feature Random Forest model as primary predictor for wheat, with deterministic rule fallback for other crops.", "3. Phase 8 Hybrid Decision Intelligence: ")
    add_bullet(doc, "Halt or defer irrigation recommendations when significant rainfall (>= 15 mm) is forecast within 48 hours.", "4. Rainfall Safety Guardrails: ")
    add_bullet(doc, "Provide trilingual WhatsApp onboarding (English, Marathi, Hindi) and synthesize natural vernacular voice notes.", "5. Inclusive Conversational Delivery: ")

    # 4. Technology Stack at a Glance
    add_heading_1(doc, "4. Technology Stack Summary")
    add_bullet(doc, "Python 3.13.2, FastAPI / Starlette, Flask, Supabase, PostgreSQL 15, PostGIS.", "Backend & API: ")
    add_bullet(doc, "Google Earth Engine API (Sentinel-2 L2A), NASA Earthdata CMR (SMAP L3 9km), OpenWeatherMap API, Shapely.", "Geospatial & Remote Sensing: ")
    add_bullet(doc, "Scikit-Learn 1.6.1, Joblib, NumPy, Pandas, Random Forest (150 trees, max depth 8).", "Machine Learning: ")
    add_bullet(doc, "Meta WhatsApp Cloud API (Graph API v18.0), Edge-TTS (`mr-IN-AarohiNeural`, `hi-IN-SwaraNeural`), Opus OGG audio.", "Delivery & Speech: ")
    add_bullet(doc, "Python `unittest` (401 tests across 14 test suites, 100% green build).", "Testing & Verification: ")

    # 5. Core Operational Workflow in 6 Steps
    add_heading_1(doc, "5. Core System Workflow")
    doc.add_paragraph(
        "1. Farmer sends WhatsApp message -> Webhook server verifies HMAC-SHA256 signature and checks deduplication.\n"
        "2. Conversational state machine onboard farmer, captures language (en/mr/hi), crop, acreage, and farm location.\n"
        "3. ESA WorldCover 10m verifies the location is Cropland (Class 40), rejecting urban or barren land.\n"
        "4. Pipeline retrieves Sentinel-2 bands, NASA SMAP soil moisture, and 48-hour forward rain forecast.\n"
        "5. Decision engine executes 5-feature Random Forest for Wheat (or rule-based fallback for Cotton/Soybean).\n"
        "6. Two-tier rainfall guardrail checks precipitation; system outputs formatted WhatsApp card and spoken voice note."
    )

    # 6. Key Scientific Findings & Benchmark Facts
    add_heading_1(doc, "6. Key Experimental Findings (CSISA Benchmark Evaluation)")
    add_bullet(doc, "32 districts (6,135 plots) for training; 8 districts (1,513 plots) held-out. Zero district overlap guarantees no spatial leakage.", "Spatial Holdout Protocol: ")
    add_bullet(doc, "On unseen districts, the Deterministic Rule Baseline achieves higher Severe Recall (22.89% vs 12.05%) and Precision (11.05% vs 6.37%) than the tuned 5-feature Random Forest.", "Rule Baseline Superiority: ")
    add_bullet(doc, "Threshold tuning on HistGradientBoosting (T=0.02) achieved 72.29% recall but generated 1,274 false alarms on 1,513 test plots (88.2% false alarm rate), proving the danger of unconstrained recall optimization.", "Base-Rate Trap Discovery: ")
    add_bullet(doc, "NASA SMAP soil moisture represents 45.37% of Random Forest tree split weight; optical indices represent 54.63% (NDWI 15.67%, NDRE 13.50%, MSAVI 12.99%, NDVI 12.48%).", "Feature Importance Breakdown: ")
    add_bullet(doc, "Deterministic rules execute in 1.57 microseconds (0.0016 ms) — 16,000 times faster than Random Forest (25.52 ms).", "Inference Latency: ")

    # 7. Quality Assurance Evidence
    add_heading_1(doc, "7. Quality Assurance Summary")
    doc.add_paragraph(
        "• Total Automated Tests: 401 tests across 14 test modules.\n"
        "• Pass Rate: 100% (401 passed, 0 failures, 0 errors, 0 skipped).\n"
        "• Execution Duration: 44.33 seconds in isolated Python virtual environment.\n"
        "• Safety: Outbound WhatsApp messaging strictly disabled in test/demo (`ENABLE_OUTBOUND_WHATSAPP=false`)."
    )

    # 8. Critical Limitations & Scientific Boundaries
    add_heading_1(doc, "8. Critical Limitations & Disclosures")
    add_callout(
        doc,
        "1. Training Domain: Model trained on Eastern India wheat research data (Bihar/Eastern UP); NOT validated for Maharashtra.\n"
        "2. Crop Boundary: ML model is validated ONLY for Wheat. Non-wheat crops use rule-based fallback.\n"
        "3. Survey Labels: Target labels represent retrospective post-harvest farmer recall, not direct physiological sensors.\n"
        "4. No Yield Field Trial: Has not conducted multi-season randomized control trials measuring crop yield gains on live farms.",
        title="LIMITATIONS TO STATE CLEARLY TO MENTOR",
        border_hex="C62828",
        bg_hex="FFEBEE"
    )

    # 9. Top 10 Viva Questions and Recommended Answers
    add_heading_1(doc, "9. Top 10 Viva Questions and Model Answers")

    viva_qas = [
        ("Q1: Why is KhetSense AI called a 'zero-hardware' solution?",
         "Because it eliminates the need for physical in-situ soil moisture probes or on-farm weather stations. All telemetry is obtained remotely via cloud APIs querying Sentinel-2 optical satellites, NASA SMAP microwave radiometry, and numerical weather forecasts."),
        ("Q2: Why do you compute both NDVI and NDWI?",
         "NDVI measures chlorophyll absorption and green canopy biomass using Red (B4) and NIR (B8). NDWI (Gao 1996) measures liquid water thickness inside leaves using NIR (B8) and SWIR (B11). Together, they capture both vegetative vigor and internal canopy moisture."),
        ("Q3: Why is MSAVI needed in addition to NDVI?",
         "During early crop emergence, bare soil dominates the pixel reflectance, causing NDVI to appear falsely depressed. MSAVI incorporates a mathematical soil-adjustment factor that isolates the emerging crop from background soil brightness."),
        ("Q4: What is the Phase 8 Primary ML architecture?",
         "In Phase 8, the 5-feature live-native Random Forest model acts as the primary crop-stress predictor for supported Wheat crops. Non-wheat crops (Cotton, Soybean) and missing sensor cases automatically fall back to the deterministic agronomic rule engine."),
        ("Q5: Why did the Deterministic Rule Baseline outperform the 5-feature ML model?",
         "Because the rule baseline uses physical agronomic thresholds (NDVI < 0.30 and SMAP < 15%) that directly capture biophysical wilting. The ML model struggled with noisy, subjective survey labels in the training dataset, achieving lower precision and recall on unseen districts."),
        ("Q6: What is the 'Severe Base-Rate Trap' in HistGradientBoosting?",
         "Because severe stress occurs in only 5.49% of the dataset, tuning the decision threshold down to T=0.02 captured 72.29% of severe cases but classified 88.2% of all test farms as Severe Stress, generating 1,274 false alarms. This proves why unconstrained recall tuning destroys practical advisory trust."),
        ("Q7: How do your rainfall guardrails work?",
         "We evaluate a 48-hour forward precipitation forecast. If rain is between 5 mm and 15 mm, we defer non-urgent irrigation. If rain is 15 mm or more (heavy rain), we halt irrigation advice unconditionally to prevent waterlogging, regardless of whether the crop is stressed."),
        ("Q8: Why is the ML model restricted to Wheat?",
         "Because the underlying training benchmark (CSISA 2018) contains survey records exclusively from wheat farms in Eastern India. Applying a wheat model to Cotton or Soybean would be scientifically invalid due to differences in rooting depth, canopy structure, and water requirements."),
        ("Q9: How do you support non-literate farmers?",
         "We generate edge-synthesized neural voice notes in Marathi (`mr-IN-AarohiNeural`), Hindi (`hi-IN-SwaraNeural`), and English. The audio is sent directly to the farmer's WhatsApp as an Opus voice note, allowing them to listen to the advice without reading text."),
        ("Q10: What does your 401-test suite prove?",
         "It proves complete software engineering correctness: that the state machine, URL parser, index formulas, guardrails, security checks, and ML pipelines execute reliably without crashes or logic errors. It does not prove agronomic yield improvements, which requires physical field trials.")
    ]

    for q, a in viva_qas:
        add_heading_2(doc, q)
        doc.add_paragraph(a)

    save_doc(doc, "KhetSense_Project_Quick_Reference.docx")

if __name__ == "__main__":
    build_doc7()
