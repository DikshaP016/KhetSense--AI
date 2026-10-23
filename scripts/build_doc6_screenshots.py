#!/usr/bin/env python3
"""
KhetSense AI — Builder for Document 6: KhetSense_Project_Screenshots_and_Figure_Plan.docx
"""

from doc_helpers import (
    create_base_doc, add_heading_1, add_heading_2, add_heading_3,
    add_bullet, add_callout, apply_table_styles, save_doc,
    HEX_WARN_BG, HEX_GREEN_BG
)

def build_doc6():
    doc = create_base_doc(
        "KhetSense AI — Screenshots & Figure Plan",
        "Visual Evidence Catalog, Recommended Presentation Visuals, Capture Protocols, and Slide Mapping"
    )

    # 1. Screenshot Inventory & Existing Visual Assets
    add_heading_1(doc, "1. Existing Visual Assets & Screenshot Inventory")
    doc.add_paragraph(
        "This document details all visual figures, terminal captures, charts, and workflow diagrams "
        "designed for the Research Project PPT presentation. Evaluators and professors look for authentic "
        "evidence of software execution, architecture design, and test validation."
    )
    doc.add_paragraph("Currently Available Visual Assets in Repository:")
    add_bullet(doc, "Located at `khetsense/reports/evaluation/evaluation_charts.png` (742 KB). High-resolution 4-panel chart showing PR-curves, threshold tuning curves, confusion matrices, and feature importances.", "1. Model Evaluation Multi-Panel Chart: ")
    add_bullet(doc, "Located in project root (`133_136_Prof_Anamika_Dhawan.jpeg`). Official project documentation photo.", "2. Project Review Photo: ")
    add_bullet(doc, "Rendered via `python demo_khetsense.py --scenario all` showing clean banners, WhatsApp advisory cards, and spoken scripts.", "3. Interactive CLI Demo Output: ")

    # 2. Recommended Screenshots to Capture for Project PPT
    add_heading_1(doc, "2. Recommended Screenshots to Capture for Research Project PPT")
    doc.add_paragraph(
        "To present a compelling, evidence-backed demonstration in your Research Project PPT, capture the "
        "following 10 genuine screenshots from your local environment:"
    )

    tbl_shots = doc.add_table(rows=11, cols=4)
    tbl_shots.rows[0].cells[0].text = "Shot ID"
    tbl_shots.rows[0].cells[1].text = "Visual Subject"
    tbl_shots.rows[0].cells[2].text = "How to Generate / Capture"
    tbl_shots.rows[0].cells[3].text = "Slide Placement in Project PPT"

    shots_data = [
        ("SHOT-01", "Demo Startup & Active Phase 8 Banner", "Run `python demo_khetsense.py --scenario ml` in PowerShell", "Slide 3 (Project Status & Decision Authority)"),
        ("SHOT-02", "Conversational Registration (Marathi)", "Run `python demo_khetsense.py --scenario registration --lang mr`", "Slide 8 (Conversational Onboarding Engine)"),
        ("SHOT-03", "Generated English WhatsApp Advisory Card", "Terminal capture of Scenario 5 output in `demo_khetsense.py`", "Slide 10 (Advisory Card Generation)"),
        ("SHOT-04", "Generated Marathi WhatsApp Advisory Card", "Terminal capture of Marathi status card in Scenario 5", "Slide 10 (Vernacular Delivery & Inclusivity)"),
        ("SHOT-05", "Spoken Voice Script (English & Marathi)", "Terminal capture of spoken voice scripts in Scenario 5", "Slide 11 (Neural Voice Synthesis Engine)"),
        ("SHOT-06", "Two-Tier Rainfall Guardrail Override", "Run `python demo_khetsense.py --scenario rainfall`", "Slide 12 (Agronomic Safety & Rainfall Guardrails)"),
        ("SHOT-07", "Unsupported Crop Fallback (Cotton)", "Terminal capture of Scenario 5 showing rule fallback", "Slide 13 (Crop Scoping & Fail-Safe Fallbacks)"),
        ("SHOT-08", "Full 401-Test Suite Discovery Run", "Run `python -m unittest discover -s tests -p \"test_*.py\"`", "Slide 15 (Quality Assurance & Test Evidence)"),
        ("SHOT-09", "Phase 8 Primary ML Test Execution", "Run `python -m unittest tests/test_phase8_ml_primary_advisory.py`", "Slide 16 (Phase 8 ML Verification Results)"),
        ("SHOT-10", "Evaluation Charts & PR-Curves", "Insert `reports/evaluation/evaluation_charts.png` directly", "Slide 17 (Model Evaluation & Benchmarking)")
    ]
    for r_idx, r_data in enumerate(shots_data, start=1):
        for c_idx, val in enumerate(r_data):
            tbl_shots.rows[r_idx].cells[c_idx].text = val
    apply_table_styles(tbl_shots, [0.8, 1.8, 2.3, 1.6])

    # 3. Recommended Architecture & Workflow Diagrams
    add_heading_1(doc, "3. Recommended Diagrams for PPT Slides")
    
    add_heading_2(doc, "A. Overall System Architecture Diagram (Slide 4)")
    doc.add_paragraph(
        "Purpose: Explains the five functional layers from WhatsApp mobile client to FastAPI webhook, "
        "satellite cloud ingestion, core decision engine, and multilingual voice synthesis."
    )
    doc.add_paragraph("Caption: Fig. 1. End-to-end layered architecture of KhetSense AI illustrating decoupled multi-sensor ingestion and vernacular WhatsApp delivery.")

    add_heading_2(doc, "B. End-to-End Operational Workflow Diagram (Slide 9)")
    doc.add_paragraph(
        "Purpose: Details the step-by-step decision flow when a farmer sends 'status': sensor freshness check, "
        "wheat ML inference vs. cotton rule fallback, rainfall guardrail override, and text/voice dispatch."
    )
    doc.add_paragraph("Caption: Fig. 2. Operational decision workflow showing primary ML evaluation for wheat, rule-based fallback, and rainfall safety overrides.")

    add_heading_2(doc, "C. Technology Stack Architecture Visual (Slide 6)")
    doc.add_paragraph(
        "Purpose: Groups technologies into 4 visual pillars: Backend (Python, FastAPI, Supabase), Remote Sensing (GEE, NASA SMAP, OpenWeather), "
        "Machine Learning (Scikit-Learn, Joblib), and Delivery (WhatsApp Cloud API, Edge-TTS)."
    )
    doc.add_paragraph("Caption: Fig. 3. Software technology stack and external API ecosystem powering KhetSense AI.")

    # 4. Step-by-Step Screenshot Capture Guide
    add_heading_1(doc, "4. Step-by-Step Manual Capture Protocol")
    doc.add_paragraph(
        "To capture clean, presentation-ready terminal screenshots on Windows 11:"
    )
    add_bullet(doc, "Use Windows Terminal with a clean dark background (Consolas or Cascadia Code font, size 11 or 12).", "1. Terminal Formatting: ")
    add_bullet(doc, "Maximize or expand the window width to at least 100 columns so table borders and card outlines do not wrap awkwardly.", "2. Window Width: ")
    add_bullet(doc, "Press `Win + Shift + S` to use the Windows Snipping Tool. Drag a rectangle around the terminal output.", "3. Capture Tool: ")
    add_bullet(doc, "Save captures as high-quality PNG images (e.g., `screenshot_01_demo_banner.png`) inside your PPT assets folder.", "4. Image Format: ")

    # 5. Missing Visual Evidence & What to State in PPT
    add_heading_1(doc, "5. Missing Visual Evidence & How to Address It in PPT")
    doc.add_paragraph(
        "Certain visuals cannot be collected live without physical field deployments. Address them transparently in your presentation:"
    )
    add_bullet(doc, "Outbound WhatsApp messaging is disabled by default for safety (`ENABLE_OUTBOUND_WHATSAPP=false`). Use the clean terminal-generated cards from `demo_khetsense.py` and state that it is an offline simulation.", "1. Real WhatsApp Mobile Phone Screenshot: ")
    add_bullet(doc, "KhetSense AI is a zero-hardware satellite solution. Explain that no in-field hardware photos exist because the core innovation is eliminating hardware probes completely.", "2. Physical In-Field Soil Probe Photos: ")
    add_bullet(doc, "Explain that the model is trained on Eastern India wheat research data and that physical field trials on Maharashtra farms represent future work.", "3. Farmer Testimonial Photos: ")

    save_doc(doc, "KhetSense_Project_Screenshots_and_Figure_Plan.docx")

if __name__ == "__main__":
    build_doc6()
