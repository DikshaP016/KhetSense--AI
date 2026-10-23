#!/usr/bin/env python3
"""
KhetSense AI — Builder for Document 1: KhetSense_Project_Overview.docx
"""

from doc_helpers import (
    create_base_doc, add_heading_1, add_heading_2, add_heading_3,
    add_bullet, add_callout, apply_table_styles, save_doc,
    HEX_WARN_BG, HEX_GREEN_BG
)

def build_doc1():
    doc = create_base_doc(
        "KhetSense AI — Project Overview",
        "System Purpose, Agricultural Problem, Aim, Scope, and Implementation Status"
    )

    # 1. Project Title & Identity
    add_heading_1(doc, "1. Project Title & Overview")
    doc.add_paragraph(
        "Full Project Title: KhetSense AI — AI-Driven Crop Stress Detection and "
        "Multilingual Voice-Based Irrigation Advisory Using Satellite Remote Sensing."
    )
    doc.add_paragraph(
        "Domain: Precision Agriculture, Remote Sensing, Machine Learning, and Conversational User Interfaces."
    )
    doc.add_paragraph(
        "Academic Context: Master of Computer Applications (MCA) Final Year Research Project (2025–2027), "
        "conducted under the mentorship of Prof. Anamika Dhawan."
    )

    # 2. Executive Summary / Abstract
    add_heading_1(doc, "2. Executive Summary")
    doc.add_paragraph(
        "KhetSense AI is an end-to-end, zero-hardware precision irrigation advisory system developed to address the "
        "acute water-management challenges faced by smallholder farmers in developing agricultural regions. Over 86% of "
        "Indian farmers cultivate landholdings of less than two hectares and cannot afford expensive in-situ soil moisture "
        "probes ($200–$500 per unit). In addition, existing agro-portals provide broad district-level bulletins that lack "
        "parcel-level relevance, and mobile applications suffer from literacy and language barriers."
    )
    doc.add_paragraph(
        "To solve this, KhetSense AI eliminates all in-field hardware by extracting satellite surface reflectance from the European "
        "Space Agency (ESA) Sentinel-2 mission (10-meter resolution), spaceborne microwave soil moisture from NASA's Soil "
        "Moisture Active Passive (SMAP) satellite (9-km resolution), and localized 48-hour forward weather forecasts from "
        "OpenWeatherMap. These multi-source inputs are processed through an agronomic decision engine combining machine learning "
        "predictions (a 5-feature Random Forest model for supported wheat crops) with deterministic rule-based fallbacks and "
        "a two-tier rainfall safety guardrail (5 mm and 15 mm thresholds). Actionable advisories are delivered directly through "
        "Meta WhatsApp in English, Marathi, and Hindi using both structured visual cards and edge-synthesized neural voice notes."
    )

    # 3. Background and Motivation
    add_heading_1(doc, "3. Background and Motivation")
    doc.add_paragraph(
        "In semi-arid and drought-prone regions such as Maharashtra (Vidarbha and Marathwada) and the Indo-Gangetic Plains, "
        "water is the single most critical input determining agricultural yield and farmer livelihoods. Most marginal farmers "
        "rely on reactive, flood-based irrigation scheduled by fixed calendar days or visual observation of soil cracking and "
        "canopy wilting. By the time visual wilting is noticeable to the human eye, irreversible biochemical stress has already "
        "occurred, reducing grain yield by 15% to 40%."
    )
    doc.add_paragraph(
        "Conversely, irrigating shortly before an unpredicted rainfall event causes severe waterlogging, root hypoxia, fungal "
        "infection, electricity waste, and accelerated depletion of groundwater tables. A practical, parcel-specific, and "
        "timely advisory system is desperately needed—one that does not require farmers to install or maintain hardware, and "
        "one that communicates in their spoken mother tongue."
    )

    # 4. Problem Statement
    add_heading_1(doc, "4. Problem Statement")
    doc.add_paragraph(
        "Marginal and smallholder farmers are excluded from modern precision agriculture by a triple barrier:"
    )
    add_bullet(doc, "Commercial soil moisture sensors cost $200–$500 per acre and suffer from rodent damage, salt encrustation, and battery failure.", "1. The Capital and Maintenance Divide: ")
    add_bullet(doc, "Most smart farming apps require complex navigation, high-speed broadband, and English or formal Hindi reading literacy, excluding vernacular-speaking farmers.", "2. The Interface and Literacy Divide: ")
    add_bullet(doc, "Government agro-bulletins cover 5,000–10,000 square kilometers, failing to inform an individual farmer whether their specific field requires water today.", "3. The Spatial and Actionability Divide: ")

    # 5. Aim and Objectives
    add_heading_1(doc, "5. Project Aim and Measurable Objectives")
    doc.add_paragraph(
        "Aim: To design, build, test, and demonstrate an automated, zero-hardware crop water-stress monitoring and multilingual "
        "irrigation advisory system that leverages satellite remote sensing, machine learning, and conversational WhatsApp delivery."
    )
    doc.add_paragraph("Key Measurable Objectives:")
    add_bullet(doc, "Integrate cloud APIs (Google Earth Engine, NASA CMR, OpenWeatherMap) to retrieve Sentinel-2 reflectance, SMAP radiometry, and 48-hour rainfall.", "Objective 1 (Telemetry Ingestion): ")
    add_bullet(doc, "Extract and compute NDVI, NDWI (Gao 1996), NDRE (Barnes 2000), MSAVI (Qi 1994), and volumetric soil moisture percentage.", "Objective 2 (Feature Engineering): ")
    add_bullet(doc, "Build an expert system that fuses canopy greenness and soil moisture into a 3-class stress rating (No Stress, Mild Stress, Severe Stress).", "Objective 3 (Rule Decision Engine): ")
    add_bullet(doc, "Enforce an independent two-tier rainfall policy (5 mm deferral, 15 mm suspension) to prevent water waste and crop damage.", "Objective 4 (Rainfall Guardrails): ")
    add_bullet(doc, "Train and evaluate 5-feature and 9-feature ML models on the 7,648-sample CSISA Eastern India benchmark across 40 districts under a strict spatial holdout.", "Objective 5 (Machine Learning Benchmark): ")
    add_bullet(doc, "In Phase 8, promote the 5-feature Random Forest as the primary predictor for wheat while maintaining explicit rule-based fallbacks for unsupported crops and missing data.", "Objective 6 (Phase 8 Hybrid Architecture): ")
    add_bullet(doc, "Build a conversational WhatsApp onboarding state machine in English, Marathi, and Hindi with edge-synthesized Opus neural voice notes.", "Objective 7 (Vernacular Delivery): ")

    # 6. Intended Users and Use Cases
    add_heading_1(doc, "6. Intended Users and Practical Use Cases")
    doc.add_paragraph("Target User Profiles:")
    add_bullet(doc, "Primary audience. Can send a WhatsApp location pin and receive simple voice advice in Marathi or Hindi telling them whether to irrigate today or wait for rain.", "1. Vernacular Smallholder Farmers: ")
    add_bullet(doc, "Can register multiple farmers across a village, monitor crop stress trends, and explain satellite indices to farmer groups.", "2. Village Extension Workers (Krishi Mitras): ")
    add_bullet(doc, "Reviewers evaluating multi-sensor satellite fusion, spatial ML evaluation, and safety guardrail performance.", "3. Academic Reviewers & Students: ")
    
    doc.add_paragraph("Primary System Use Cases:")
    add_bullet(doc, "Farmer texts 'Hi', chooses language (English, Marathi, Hindi), shares farm location via GPS pin or Google Maps URL, enters crop and acreage, and confirms location.", "Use Case 1 (Conversational Onboarding): ")
    add_bullet(doc, "Farmer sends 'status' to receive an updated visual card and an audio voice note detailing crop stress and recommended irrigation actions.", "Use Case 2 (On-Demand Advisory Retrieval): ")
    add_bullet(doc, "When heavy rain is forecast (>= 15 mm), the system automatically changes the recommendation to 'Hold, Re-check After Rain', preventing waterlogging.", "Use Case 3 (Rainfall Safety Override): ")

    # 7. Project Scope
    add_heading_1(doc, "7. Project Scope and Boundaries")
    doc.add_paragraph("What is IN Scope:")
    add_bullet(doc, "Automated retrieval of Sentinel-2 Level-2A surface reflectance (10m) and NASA SMAP L3 enhanced radiometry (9km).")
    add_bullet(doc, "Computation of NDVI, NDWI, NDRE, MSAVI, and volumetric soil moisture percentage.")
    add_bullet(doc, "ESA WorldCover 10m agricultural land-cover validation.")
    add_bullet(doc, "Phase 8 primary 5-feature Random Forest model for supported Wheat crops.")
    add_bullet(doc, "Explicit rule-based fallback for unsupported crops (Cotton, Soybean) and missing sensor data.")
    add_bullet(doc, "Two-tier rainfall guardrail policy (5 mm and 15 mm thresholds).")
    add_bullet(doc, "Conversational WhatsApp state machine supporting English, Marathi, and Hindi.")
    add_bullet(doc, "Edge-synthesized vernacular Text-to-Speech (TTS) generating Opus voice notes.")
    add_bullet(doc, "Automated test suite (401 unit and integration tests passing).")
    
    doc.add_paragraph("What is OUT of Scope (Academic Prototype Boundaries):")
    add_bullet(doc, "Physical field sensor installation (zero in-situ hardware design).")
    add_bullet(doc, "Automated physical irrigation pump or valve electrical switching.")
    add_bullet(doc, "Multi-season longitudinal randomized control trials measuring crop yield or water savings on live farms.")
    add_bullet(doc, "Unsupervised drone aerial imagery or commercial satellite imagery subscription.")

    # 8. Key Features
    add_heading_1(doc, "8. Key Features of the Implemented System")
    add_bullet(doc, "Zero capital expenditure and zero physical maintenance burden for farmers.", "1. Zero-Hardware Telemetry: ")
    add_bullet(doc, "Uses 10m Sentinel-2 pixels to analyze specific farm boundaries rather than broad regional averages.", "2. Parcel-Level Optical Resolution: ")
    add_bullet(doc, "Screens coordinates using ESA WorldCover 10m to reject urban concrete or barren desert lands.", "3. Agricultural Land-Cover Screening: ")
    add_bullet(doc, "Evaluates crop moisture stress biophysically, but independently checks weather forecasts before advising water application.", "4. Decoupled Stress and Irrigation Action: ")
    add_bullet(doc, "Operates the 5-feature Random Forest as primary predictor for wheat while ensuring non-wheat crops are safely handled by rule-based fallbacks.", "5. Phase 8 Hybrid Decision Intelligence: ")
    add_bullet(doc, "High forecast rainfall unconditionally overrides severe stress recommendations, preventing water waste.", "6. Two-Tier Rainfall Safety Guardrail: ")
    add_bullet(doc, "Speaks directly to the farmer in natural Marathi, Hindi, or English via WhatsApp audio voice notes.", "7. Neural Voice Delivery in Vernacular: ")
    add_bullet(doc, "Advisory cards transparently disclose whether the recommendation came from AI/ML or expert rules, list model probabilities, and display an academic prototype notice.", "8. Transparent AI Provenance: ")

    # 9. Existing Approach vs. Proposed Approach
    add_heading_1(doc, "9. Comparison of Existing and Proposed Approaches")
    tbl = doc.add_table(rows=7, cols=3)
    tbl.rows[0].cells[0].text = "Evaluation Dimension"
    tbl.rows[0].cells[1].text = "Existing Approaches (IoT / Portals / Chatbots)"
    tbl.rows[0].cells[2].text = "KhetSense AI (Proposed System)"
    
    data = [
        ("Hardware Cost", "$200–$500 per probe or regional station only", "Zero in-situ hardware (Satellite virtual sensing)"),
        ("Spatial Scale", "Single point probe or 50–100 km district bulletin", "10-meter parcel-level optical canopy resolution"),
        ("Delivery Channel", "Complex mobile application or web dashboard", "Everyday WhatsApp chat and automatic audio voice notes"),
        ("Language & Audio", "English or formal Hindi text only", "Trilingual (English, Marathi, Hindi) with neural voice notes"),
        ("Rainfall Safety", "Rarely integrated; advice issued regardless of rain", "Deterministic two-tier guardrail halts advice if rain >= 15mm"),
        ("Execution Speed", "Minutes or manual batch processing", "1.57 microseconds (Rules) / 25.5 milliseconds (ML)")
    ]
    for row_idx, row_data in enumerate(data, start=1):
        for col_idx, text in enumerate(row_data):
            tbl.rows[row_idx].cells[col_idx].text = text
    apply_table_styles(tbl, [1.5, 2.5, 2.5])

    # 10. Expected Benefits vs. Current Scientific Limitations
    add_heading_1(doc, "10. Expected Benefits and Current Scientific Limitations")
    doc.add_paragraph("Expected Project Benefits (Demonstrated via Prototype):")
    add_bullet(doc, "No hardware purchase or battery replacement cost for smallholders.")
    add_bullet(doc, "Prevents wasteful irrigation when heavy rain is forecast.")
    add_bullet(doc, "Bridges the digital literacy divide by explaining crop status via spoken voice.")
    add_bullet(doc, "Provides verifiable software reliability with 401 passing automated tests.")

    add_callout(
        doc,
        "1. Geographic Limitation: The machine learning model was trained strictly on Eastern Indian wheat research data "
        "(Bihar and Eastern UP). It has NOT been validated for Central Maharashtra (Vertisol / Black Cotton Soils).\n"
        "2. Crop Limitation: The ML model is validated ONLY for Bread Wheat. Non-wheat crops (Cotton, Soybean) are routed "
        "to rule-based fallbacks.\n"
        "3. Survey Labels: Training labels were derived from post-harvest farmer recall surveys, not physical physiological sensors.\n"
        "4. No Yield Trial: KhetSense AI has NOT conducted longitudinal randomized control trials measuring crop yield increases "
        "or volumetric water savings on physical farms.",
        title="CRITICAL SCIENTIFIC BOUNDARIES & LIMITATIONS",
        border_hex="C62828",
        bg_hex="FFEBEE"
    )

    # 11. Current Implementation Status
    add_heading_1(doc, "11. Current Implementation Status")
    doc.add_paragraph(
        "KhetSense AI has reached Phase 8: Primary Machine Learning Predictor Integration for an Academic Prototype. "
        "The software codebase is complete, fully integrated end-to-end, and verified by 401 automated unit and integration tests "
        "across 14 test suites with zero failures and zero errors."
    )
    doc.add_paragraph(
        "The interactive demonstration suite (`demo_khetsense.py`) provides 5 comprehensive demonstration scenarios: "
        "trilingual WhatsApp registration, two-tier rainfall guardrails, crop calendar mismatch screening, missing sensor handling, "
        "and primary 5-feature ML prediction on supported wheat crops alongside explicit rule-based fallbacks."
    )

    save_doc(doc, "KhetSense_Project_Overview.docx")

if __name__ == "__main__":
    build_doc1()
