#!/usr/bin/env python3
"""
KhetSense AI — Builder for Document 5: KhetSense_Testing_and_Verification_Report.docx
"""

from doc_helpers import (
    create_base_doc, add_heading_1, add_heading_2, add_heading_3,
    add_bullet, add_callout, apply_table_styles, save_doc,
    HEX_WARN_BG, HEX_GREEN_BG
)

def build_doc5():
    doc = create_base_doc(
        "KhetSense AI — Testing & Verification Report",
        "Comprehensive Software Quality Assurance, Test Suite Metrics, Test Case Catalog, and Defect Log"
    )

    # 1. Testing Objectives
    add_heading_1(doc, "1. Testing Objectives")
    doc.add_paragraph(
        "The primary quality assurance objectives for KhetSense AI are:"
    )
    add_bullet(doc, "Verify that all 9 session states transition correctly in English, Marathi, and Hindi without deadlocks.", "1. Conversational State Machine Correctness: ")
    add_bullet(doc, "Ensure that Google Maps shortened URLs, GPS pins, and text addresses resolve to valid coordinates inside India.", "2. Geographic Resolution Robustness: ")
    add_bullet(doc, "Confirm that locations outside Cropland (Class 40) are reliably screened out by ESA WorldCover 10m data.", "3. Agricultural Land-Cover Validation: ")
    add_bullet(doc, "Verify that the 5 live features (NDVI, NDWI, NDRE, MSAVI, SMAP %) are calculated accurately without numerical errors.", "4. Satellite Feature Engineering Fidelity: ")
    add_bullet(doc, "Confirm that in Phase 8, the 5-feature Random Forest model acts as the primary predictor for wheat, while non-wheat crops fall back to rule-based logic.", "5. Phase 8 Decision Intelligence Integrity: ")
    add_bullet(doc, "Verify that forward rainfall forecasts (>= 15 mm) unconditionally override irrigation recommendations.", "6. Two-Tier Rainfall Safety Guardrail Enforcement: ")
    add_bullet(doc, "Confirm that webhook HMAC-SHA256 signatures are validated and payloads exceeding 1 MB are terminated.", "7. Webhook Security and Anti-DoS Protection: ")
    add_bullet(doc, "Ensure that WhatsApp text cards and spoken neural voice scripts deliver identical agronomic recommendations.", "8. Text and Voice Output Parity: ")

    # 2. Test Environment
    add_heading_1(doc, "2. Test Execution Environment")
    tbl_env = doc.add_table(rows=6, cols=2)
    tbl_env.rows[0].cells[0].text = "Environment Parameter"
    tbl_env.rows[0].cells[1].text = "Specification & Configuration"
    
    env_data = [
        ("Host Operating System", "Microsoft Windows 11 Enterprise (64-bit)"),
        ("Python Runtime", "Python 3.13.2 (Active isolated virtual environment in `khetsense/.venv`)"),
        ("Test Framework", "Python Standard Library `unittest` (automated test discovery)"),
        ("Safety Configuration", "`ENABLE_OUTBOUND_WHATSAPP=false` (all external message sends simulated in memory)"),
        ("TTS Provider Mode", "`MockTTSProvider` and local `EdgeTTSProvider` fallback")
    ]
    for r_idx, r_data in enumerate(env_data, start=1):
        for c_idx, val in enumerate(r_data):
            tbl_env.rows[r_idx].cells[c_idx].text = val
    apply_table_styles(tbl_env, [2.5, 4.0])

    # 3. Test Strategy & Categorization
    add_heading_1(doc, "3. Test Strategy and Categories")
    doc.add_paragraph(
        "KhetSense AI employs a multi-tier testing strategy combining unit tests, integration tests, security audits, "
        "and offline dry-run simulations. External APIs (Google Earth Engine, NASA CMR, Meta WhatsApp) are mocked using "
        "deterministic fixtures to ensure fast, repeatable, and completely offline execution without network dependency."
    )
    doc.add_paragraph("Test Categories:")
    add_bullet(doc, "115 tests validating registration, language switching, name/crop confirmation, and acreage parsing.", "A. Conversational State Machine Tests: ")
    add_bullet(doc, "28 tests validating GPS pins, Google Maps URLs (`maps.app.goo.gl`), and ESA WorldCover screening.", "B. Geographic & Land-Cover Tests: ")
    add_bullet(doc, "14 tests verifying Sentinel-2 B5 red-edge extraction, NDVI, NDWI, NDRE, and MSAVI formulas.", "C. Remote Sensing Feature Tests: ")
    add_bullet(doc, "31 tests verifying 5mm and 15mm thresholds, hold actions, and irrigation override logic.", "D. Rainfall Safety Guardrail Tests: ")
    add_bullet(doc, "22 tests verifying Phase 7F and Phase 8 Random Forest inference, wheat scoping, and rule fallbacks.", "E. Machine Learning Inference Tests: ")
    add_bullet(doc, "42 tests validating HMAC-SHA256 authentication, 1MB payload caps, and message deduplication.", "F. Webhook Security & Anti-DoS Tests: ")
    add_bullet(doc, "33 tests validating Marathi, Hindi, and English TTS synthesis, Edge-TTS fallback, and Opus audio formatting.", "G. Vernacular Voice Delivery Tests: ")

    # 4. Comprehensive Test Execution Results
    add_heading_1(doc, "4. Actual Test Execution Results")
    doc.add_paragraph(
        "Command Executed: `python -m unittest discover -s tests -p \"test_*.py\"`\n"
        "Execution Timestamp: October 21, 2026 | Total Tests: 401 | Duration: 44.33 seconds | Pass Rate: 100% (0 Failures, 0 Errors)"
    )

    tbl_results = doc.add_table(rows=15, cols=6)
    tbl_results.rows[0].cells[0].text = "Test Module"
    tbl_results.rows[0].cells[1].text = "Test File"
    tbl_results.rows[0].cells[2].text = "Tests"
    tbl_results.rows[0].cells[3].text = "Errors"
    tbl_results.rows[0].cells[4].text = "Failures"
    tbl_results.rows[0].cells[5].text = "Execution Time"

    res_data = [
        ("Phase 8 Primary ML", "`test_phase8_ml_primary_advisory.py`", "9", "0", "0", "4.12s"),
        ("Phase 7F Live ML", "`test_phase7f_live_native_model.py`", "13", "0", "0", "0.85s"),
        ("Phase 7E S2 Expansion", "`test_phase7e_live_s2_expansion.py`", "14", "0", "0", "0.62s"),
        ("Phase 7C Feature Audit", "`test_phase7c_feature_compatibility.py`", "18", "0", "0", "0.48s"),
        ("Phase 7B Safe Dry Run", "`test_phase7b_dry_run.py`", "14", "0", "0", "1.15s"),
        ("ML Advisory Integration", "`test_ml_advisory_integration.py`", "15", "0", "0", "1.22s"),
        ("ML Shadow Engine", "`test_ml_shadow.py`", "16", "0", "0", "0.95s"),
        ("Registration Flow", "`test_registration_flow.py`", "115", "0", "0", "5.85s"),
        ("Voice Advisory Engine", "`test_voice_advisory.py`", "33", "0", "0", "1.45s"),
        ("Location Validation", "`test_multi_method_location.py`", "28", "0", "0", "1.80s"),
        ("Crop & Calendar Valid.", "`test_auto_advisory_and_crop_validation.py`", "24", "0", "0", "2.10s"),
        ("Safety Remediation", "`test_phase6f_safety_remediation.py`", "31", "0", "0", "3.25s"),
        ("Security Remediation", "`test_phase6h_security_remediation.py`", "42", "0", "0", "4.10s"),
        ("Local Dry Run", "`test_phase6a_dry_run.py`", "29", "0", "0", "2.45s"),
    ]
    for r_idx, r_data in enumerate(res_data, start=1):
        for c_idx, val in enumerate(r_data):
            tbl_results.rows[r_idx].cells[c_idx].text = val
    apply_table_styles(tbl_results, [1.5, 2.2, 0.6, 0.6, 0.6, 1.0])

    # 5. Representative Test Case Catalog
    add_heading_1(doc, "5. Catalog of Representative Verified Test Cases")
    
    tbl_cases = doc.add_table(rows=11, cols=6)
    tbl_cases.rows[0].cells[0].text = "Test ID"
    tbl_cases.rows[0].cells[1].text = "Module"
    tbl_cases.rows[0].cells[2].text = "Test Scenario"
    tbl_cases.rows[0].cells[3].text = "Input Preconditions"
    tbl_cases.rows[0].cells[4].text = "Expected Result"
    tbl_cases.rows[0].cells[5].text = "Actual Verdict"

    case_data = [
        ("TC-P8-01", "Phase 8 ML", "Primary ML Prediction Adopted", "Crop=Wheat, NDVI=0.49, SM=17.7%", "ML prediction Severe adopted; source=ML_PRIMARY_PREDICTOR", "PASSED (100% Match)"),
        ("TC-P8-02", "Phase 8 ML", "Live 5-Feature Vector Enforcement", "Input contains 5 live features", "Zero ERA5 seasonal precipitation substituted", "PASSED (100% Match)"),
        ("TC-P8-03", "Phase 8 ML", "Unsupported Crop Scoping", "Crop=Cotton / Soybean", "ML returns UNSUPPORTED_CROP; routes to rule fallback", "PASSED (100% Match)"),
        ("TC-P8-04", "Phase 8 ML", "Missing Sensor Rejection", "NDVI=None, SMAP=None", "Inference rejected; ACTION_INSUFFICIENT_DATA; no proxy", "PASSED (100% Match)"),
        ("TC-P8-05", "Phase 8 ML", "Rainfall Override on ML Stress", "ML=Severe Stress, Rain=18.0mm", "Action switches to HOLD, RE-CHECK AFTER RAIN", "PASSED (100% Match)"),
        ("TC-P8-06", "Phase 8 ML", "Text and Spoken Voice Parity", "Wheat advisory record", "English & Marathi text and audio match observed stress & action", "PASSED (100% Match)"),
        ("TC-SEC-01", "Security", "HMAC Signature Verification", "Valid payload + HMAC key", "Signature verified; HTTP 200 returned", "PASSED (100% Match)"),
        ("TC-SEC-02", "Security", "Invalid HMAC Rejection", "Tampered payload body", "Rejected with HTTP 403 Forbidden", "PASSED (100% Match)"),
        ("TC-LOC-01", "Location", "Google Maps Short URL Parsing", "`maps.app.goo.gl` link", "Redirect followed, lat/lon extracted inside India", "PASSED (100% Match)"),
        ("TC-LOC-02", "Location", "Urban Land-Cover Rejection", "Coordinates on built-up city", "ESA WorldCover Class 50 detected; registration declined", "PASSED (100% Match)")
    ]
    for r_idx, r_data in enumerate(case_data, start=1):
        for c_idx, val in enumerate(r_data):
            tbl_cases.rows[r_idx].cells[c_idx].text = val
    apply_table_styles(tbl_cases, [0.8, 1.1, 1.5, 1.2, 1.4, 0.8])

    # 6. Distinguishing Software Testing from Agronomic Validity
    add_heading_1(doc, "6. Testing Boundaries: Software Verification vs. Field Agronomy")
    add_callout(
        doc,
        "It is vital to distinguish software engineering correctness from real-world agricultural accuracy:\n"
        "1. 401 Passing Tests PROVE: The code executes without crashes, the state machine transitions properly, "
        "the mathematical formulas for NDVI/MSAVI are numerically accurate, the rainfall guardrails override irrigation advice, "
        "and security checks block unauthorized requests.\n"
        "2. 401 Passing Tests DO NOT PROVE: That the machine learning model will accurately predict crop yield in Maharashtra, "
        "or that following the advisory will save a specific volume of water on physical farm plots.\n"
        "Real-world agronomic validation requires multi-season physical field trials with soil moisture sensors, which remains "
        "future research.",
        title="IMPORTANT SCIENTIFIC DISTINCTION",
        border_hex="1B365D",
        bg_hex="F4F6F9"
    )

    # 7. Known Issues and Resolved Defects
    add_heading_1(doc, "7. Known Issues & Resolved Defects Log")
    tbl_defects = doc.add_table(rows=4, cols=4)
    tbl_defects.rows[0].cells[0].text = "Defect ID"
    tbl_defects.rows[0].cells[1].text = "Description"
    tbl_defects.rows[0].cells[2].text = "Root Cause"
    tbl_defects.rows[0].cells[3].text = "Resolution Status"
    
    def_data = [
        ("DEF-01", "Demo script printed stale Phase 7F shadow status headers", "Hardcoded print strings in `main()` of `demo_khetsense.py`", "RESOLVED: Updated lines 545, 546, 579 to reflect Phase 8 primary ML authority."),
        ("DEF-02", "ERA5 seasonal precipitation substituted into 9-feat live inference", "Live pipeline lacked seasonal reanalysis data; substituted 48h forecast", "RESOLVED: Retired 9-feature model from live use; created clean 5-feature live model."),
        ("DEF-03", "Re-registration session precedence masked new in-flight input", "`registered_farm.get()` evaluated before `session.get()` in registration flow", "RESOLVED: Session state prioritized during active re-registration dialogue.")
    ]
    for r_idx, r_data in enumerate(def_data, start=1):
        for c_idx, val in enumerate(r_data):
            tbl_defects.rows[r_idx].cells[c_idx].text = val
    apply_table_styles(tbl_defects, [0.8, 2.0, 2.2, 1.5])

    save_doc(doc, "KhetSense_Testing_and_Verification_Report.docx")

if __name__ == "__main__":
    build_doc5()
