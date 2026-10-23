#!/usr/bin/env python3
"""
KhetSense AI — Builder for Document 4: KhetSense_Implementation_and_Demo_Guide.docx
"""

from doc_helpers import (
    create_base_doc, add_heading_1, add_heading_2, add_heading_3,
    add_bullet, add_callout, apply_table_styles, save_doc,
    HEX_WARN_BG, HEX_GREEN_BG
)

def build_doc4():
    doc = create_base_doc(
        "KhetSense AI — Implementation & Demo Guide",
        "Step-by-Step Evaluator Demonstration Manual, Setup Protocols, Test Scenarios, and Verification Checklist"
    )

    # 1. Prerequisites and Safe Setup Instructions
    add_heading_1(doc, "1. Prerequisites & Safe Setup Instructions")
    doc.add_paragraph(
        "This guide provides exact, verified instructions for running an offline, safe, end-to-end demonstration "
        "of KhetSense AI for university mentors, project evaluators, and peer students. "
        "The demonstration runs in a controlled local simulation mode: it executes the actual Python pipeline logic, "
        "runs live model inference, and formats real multilingual cards and voice notes without modifying databases "
        "or sending live WhatsApp messages."
    )
    doc.add_paragraph("System Requirements:")
    add_bullet(doc, "Windows 10/11, macOS, or Linux.", "Operating System: ")
    add_bullet(doc, "Python 3.11, 3.12, or 3.13 (Python 3.13.2 verified in project environment).", "Python Version: ")
    add_bullet(doc, "Installed in `khetsense/.venv` (all dependencies pre-configured).", "Virtual Environment: ")
    add_bullet(doc, "`ENABLE_OUTBOUND_WHATSAPP=false` (strictly enforced by default; prevents accidental network calls).", "Safety Control Flag: ")

    doc.add_paragraph("Command to Activate Virtual Environment (PowerShell):")
    doc.add_paragraph(
        "cd \"c:\\Users\\NIDEEKSHA\\Documents\\DEEKSHA\\MASTERS\\Research Project\\khetsense\"\n"
        ".\\.venv\\Scripts\\Activate.ps1"
    )

    # 2. How to Start the Application
    add_heading_1(doc, "2. Starting the Application")
    doc.add_paragraph(
        "KhetSense AI can be executed in two demonstration modes:"
    )
    add_heading_2(doc, "Mode A: Interactive Multi-Scenario CLI Demonstration (`demo_khetsense.py`)")
    doc.add_paragraph(
        "This is the recommended demonstration tool for evaluators. It executes all five core operational scenarios "
        "sequentially, printing formatted WhatsApp cards, spoken voice scripts, and provenance metadata directly to the console."
    )
    doc.add_paragraph("Command: `python demo_khetsense.py --scenario all`")
    doc.add_paragraph("To run only the Phase 8 Primary ML scenario: `python demo_khetsense.py --scenario ml`")

    add_heading_2(doc, "Mode B: Live Local Webhook Server (`webhook_server.py`)")
    doc.add_paragraph(
        "Starts the FastAPI / Starlette webhook server listening on `http://127.0.0.1:8000`. "
        "Can receive simulated HTTP POST webhooks or connect to a live Meta WhatsApp test account via an ngrok tunnel."
    )
    doc.add_paragraph("Command: `python webhook_server.py`")

    # 3. Main User Journey
    add_heading_1(doc, "3. Main User Journey (Conversational Flow)")
    doc.add_paragraph("The typical farmer interaction follows a clear 6-step journey:")
    add_bullet(doc, "Farmer sends 'Hi' or 'Namaste' to the KhetSense WhatsApp number.", "Step 1: Initiation — ")
    add_bullet(doc, "System responds in Marathi, Hindi, and English. Farmer replies '1' for English, '2' for Marathi, or '3' for Hindi.", "Step 2: Language Selection — ")
    add_bullet(doc, "System asks for farmer's name, declared crop (e.g., Wheat), and acreage.", "Step 3: Profile Details — ")
    add_bullet(doc, "Farmer sends a WhatsApp GPS location pin or a Google Maps link.", "Step 4: Location Sharing — ")
    add_bullet(doc, "System resolves coordinates, checks ESA WorldCover cropland classification, and asks the farmer to confirm.", "Step 5: Location Confirmation — ")
    add_bullet(doc, "Farmer sends 'status'. The pipeline computes multi-sensor stress, applies rainfall guardrails, and returns a visual WhatsApp card and an audio voice note.", "Step 6: Advisory Delivery — ")

    # 4. Step-by-Step Demo Sequence (5 Scenarios)
    add_heading_1(doc, "4. Step-by-Step Demonstration Scenarios")
    
    add_heading_2(doc, "Scenario 1: Trilingual Registration and Onboarding")
    doc.add_paragraph(
        "Purpose: Demonstrates the multi-turn conversational state machine in English, Marathi, and Hindi, "
        "including crop alias resolution (e.g., 'Gahu' -> Wheat) and acreage parsing."
    )
    doc.add_paragraph("Command: `python demo_khetsense.py --scenario registration --lang mr`")
    doc.add_paragraph("Expected Output: The console displays the simulated conversation showing prompt and response pairs in Marathi.")

    add_heading_2(doc, "Scenario 2: Two-Tier Rainfall Safety Guardrail")
    doc.add_paragraph(
        "Purpose: Demonstrates how short-term weather forecasts override severe stress irrigation advice to prevent waterlogging."
    )
    doc.add_paragraph("Command: `python demo_khetsense.py --scenario rainfall`")
    doc.add_paragraph("Test Conditions:")
    add_bullet(doc, "Sensor stress is Severe, but 48h rainfall forecast is 22.0 mm (>= 15.0 mm threshold).")
    add_bullet(doc, "Expected Result: Recommended action switches to 'HOLD, RE-CHECK AFTER RAIN'. Advisory card warns farmer not to irrigate.")

    add_heading_2(doc, "Scenario 3: Crop Mismatch & Phenological Calendar Screening")
    doc.add_paragraph(
        "Purpose: Validates that declared crops match expected phenological seasons in Central India."
    )
    doc.add_paragraph("Command: `python demo_khetsense.py --scenario crop_mismatch`")
    doc.add_paragraph("Test Conditions:")
    add_bullet(doc, "Farmer registers Wheat (a winter Rabi crop) in July with high active vegetation (NDVI 0.65).")
    add_bullet(doc, "Expected Result: System flags a phenological mismatch, noting that active July growth indicates Kharif crops (Cotton/Soybean).")

    add_heading_2(doc, "Scenario 4: Missing & Cloudy Sensor Data Handling")
    doc.add_paragraph(
        "Purpose: Demonstrates honest reporting without data fabrication when satellites are cloudy or sensors fail."
    )
    doc.add_paragraph("Command: `python demo_khetsense.py --scenario missing_sensors`")
    doc.add_paragraph("Test Conditions:")
    add_bullet(doc, "Both Sentinel-2 optical bands and SMAP soil moisture are unavailable.")
    add_bullet(doc, "Expected Result: System outputs status 'MISSING_INPUTS' and issues an 'INSUFFICIENT DATA' advisory. No numbers are fabricated.")

    add_heading_2(doc, "Scenario 5: Phase 8 Primary 5-Feature ML Advisory & Rule Fallback")
    doc.add_paragraph(
        "Purpose: Verifies that the 5-feature Random Forest model acts as the primary predictor for wheat, "
        "while non-wheat crops (Cotton) route to rule-based fallback."
    )
    doc.add_paragraph("Command: `python demo_khetsense.py --scenario ml`")
    doc.add_paragraph("Test Conditions & Expected Results:")
    add_bullet(doc, "Wheat farm with NDVI 0.49, NDWI 0.07, NDRE 0.32, MSAVI 0.25, SMAP 17.7%. ML predicts Severe Stress (T=0.27). Adopted stress is 'Severe Stress' via 'ML_PRIMARY_PREDICTOR'. WhatsApp card and Marathi voice script both advise 'Irrigate Now'.")
    add_bullet(doc, "Cotton farm with same sensor values. ML returns 'UNSUPPORTED_CROP'. Pipeline routes to 'RULE_FALLBACK_UNSUPPORTED_CROP'. Adopted stress is 'Mild Stress'. Card clearly notes rule fallback.")

    # 5. Example WhatsApp Card and Voice Outputs
    add_heading_1(doc, "5. Real Example Advisory Outputs")
    
    add_heading_2(doc, "A. Generated English WhatsApp Advisory Card")
    card_en = (
        "[DEMO MODE — ILLUSTRATIVE LOCATION DATA]\n\n"
        "📊 *KhetSense Farm Status & Advisory* 🌱\n\n"
        "• Farm ID: #101\n"
        "• Farmer: Ramesh Kumar\n"
        "• Crop: Wheat\n"
        "• Status Date: 22-10-2026\n\n"
        "🌾 *Observed Stress:* Severe Stress\n"
        "💧 *Recommended Action:* Irrigate Now\n"
        "🌧️ *48-Hour Forecast Rain:* 2.0 mm\n\n"
        "📋 *Agronomic Advice:*\n"
        "URGENT: Severe water stress detected for Wheat at Flowering stage. Immediate irrigation "
        "recommended to prevent yield loss (minimal forecast rain: 2.0 mm).\n\n"
        "• Reply 'status' anytime for an updated advisory.\n"
        "• Reply 'language' to change your language.\n\n"
        "🤖 *Assessment Source:* AI/ML Model (5-Feature Random Forest)\n"
        "📊 *Model Probabilities:* Healthy 17%, Mild 29%, Severe 54%\n"
        "⚠️ *Academic Prototype:* Experimental model trained on Eastern India wheat research data. "
        "Not validated for real-farmer decisions."
    )
    doc.add_paragraph(card_en)

    add_heading_2(doc, "B. Generated Spoken Voice Scripts")
    doc.add_paragraph(
        "English Spoken Script:\n"
        "\"Demo mode notice: This is illustrative location data. Hello Ramesh Kumar, this is your KhetSense AI-generated "
        "irrigation advisory for your Wheat crop. Your crop is experiencing severe water stress. Light rain of about 2.0 millimeters "
        "is expected. Please irrigate your crop immediately to prevent yield loss. Stay tuned to KhetSense for your next advisory. Thank you.\""
    )
    doc.add_paragraph(
        "Marathi Spoken Script:\n"
        "\"डेमो मोड सूचना: ही प्रात्यक्षिक माहिती आहे. नमस्कार Ramesh Kumarजी, खेतसेन्स AI द्वारे तयार केलेला तुमच्या गहू (Wheat) "
        "पिकासाठी हा सिंचन सल्ला आहे. सध्या तुमच्या पिकामध्ये तीव्र पाण्याचा ताण दिसून येत आहे. पुढील दोन दिवसांत सुमारे 2.0 मिलिमीटर "
        "हलक्या पावसाचा अंदाज आहे. पिकाचे नुकसान टाळण्यासाठी कृपया ताबडतोब पाणी द्या. पुढील सल्ल्यासाठी खेतसेन्सशी जोडलेले राहा. धन्यवाद.\""
    )

    # 6. Common Errors and Troubleshooting
    add_heading_1(doc, "6. Common Errors and Evaluator Troubleshooting")
    tbl_err = doc.add_table(rows=5, cols=3)
    tbl_err.rows[0].cells[0].text = "Observed Issue"
    tbl_err.rows[0].cells[1].text = "Root Cause"
    tbl_err.rows[0].cells[2].text = "Resolution Steps"
    
    err_data = [
        ("Python command not found", "Virtual environment not activated in current shell", "Run `.\\.venv\\Scripts\\Activate.ps1` before executing python commands."),
        ("Missing model artifact (.joblib)", "Model files missing in `data/research_benchmark/models/`", "Run `python data/research_benchmark/train_live_native_models.py` to regenerate models."),
        ("Port 8000 already in use", "Another instance of `webhook_server.py` is running", "Terminate the existing python process or run on port 8001 via `uvicorn webhook_server:app --port 8001`."),
        ("Edge-TTS voice connection error", "No active internet connection for neural TTS synthesis", "System automatically falls back to `MockTTSProvider` ensuring demo runs uninterrupted.")
    ]
    for r_idx, r_data in enumerate(err_data, start=1):
        for c_idx, val in enumerate(r_data):
            tbl_err.rows[r_idx].cells[c_idx].text = val
    apply_table_styles(tbl_err, [1.8, 2.2, 2.5])

    # 7. Screenshot Collection Checklist
    add_heading_1(doc, "7. Checklist for Collecting Genuine Screenshots for PPT")
    doc.add_paragraph("Follow this checklist when taking screenshots for your Research Project PPT:")
    add_bullet(doc, "Run `python demo_khetsense.py --scenario ml` and capture the top banner showing Phase 8 Primary ML status.", "[ ] Screenshot 1: Demo Startup & Active Decision Authority Banner")
    add_bullet(doc, "Capture Scenario 1 showing the Marathi language selection and confirmation dialogue in the terminal.", "[ ] Screenshot 2: Trilingual WhatsApp Registration Dialogue (Marathi)")
    add_bullet(doc, "Capture the side-by-side English and Marathi WhatsApp advisory cards generated in Scenario 5.", "[ ] Screenshot 3: Generated Multilingual WhatsApp Advisory Cards")
    add_bullet(doc, "Capture Scenario 2 where an 18mm rain forecast overrides severe stress to 'HOLD, RE-CHECK AFTER RAIN'.", "[ ] Screenshot 4: Two-Tier Rainfall Safety Guardrail Override")
    add_bullet(doc, "Capture Scenario 5 output showing Cotton routing to 'RULE_FALLBACK_UNSUPPORTED_CROP'.", "[ ] Screenshot 5: Unsupported Crop Fallback Guardrail")
    add_bullet(doc, "Run `python -m unittest discover -s tests -p \"test_*.py\"` and capture the final 'Ran 401 tests in 44.3s - OK' summary.", "[ ] Screenshot 6: Full 401-Test Suite Verification Summary")

    save_doc(doc, "KhetSense_Implementation_and_Demo_Guide.docx")

if __name__ == "__main__":
    build_doc4()
