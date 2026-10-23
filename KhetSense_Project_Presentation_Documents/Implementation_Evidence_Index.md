# KhetSense AI — Implementation Evidence Index

**Project Title:** KhetSense AI: AI-Driven Crop Stress Detection and Multilingual Voice-Based Irrigation Advisory Using Satellite Remote Sensing  
**Author:** Diksha Poojary (Roll No. 136) | Master of Computer Applications (MCA)  
**Mentor:** Prof. Anamika Dhawan  
**Academic Year:** 2025–2027  
**Location:** `KhetSense_Project_Presentation_Documents/`  
**Purpose:** Formal catalog of all inspected source files, test files, configuration examples, API routes, database schemas, serialized models, and evaluation artifacts used to construct the Research Project presentation package.

---

## 1. Verified Source Code Files Inspected

| Module Category | Source File Path | Key Functions / Classes Inspected | Verification Status |
|---|---|---|---|
| **Pipeline & Satellite Telemetry** | `pipeline/test_pipeline.py` | `fetch_sentinel2_indices()`, `fetch_smap_soil_moisture()`, `fetch_weather_forecast()`, `run_pipeline_for_farm()`, `trigger_pipeline_for_farm()` | **Verified from source code** |
| **Agronomic Classifier & Guardrails** | `pipeline/classifier.py` | `classify_ndvi_stress()`, `classify_soil_moisture_stress()`, `get_more_severe()`, `apply_rainfall_guardrail()`, `primary_ml_stress_assessment()`, `generate_irrigation_advisory()` | **Verified from source code** |
| **Machine Learning Inference** | `pipeline/ml_inference.py` | `load_ml_model_5feat()`, `predict_crop_stress_5feat()`, `is_crop_supported_by_ml()`, `FEATURE_NAMES_5FEAT`, `RF_5FEAT_SEVERE_THRESHOLD` | **Verified from source code** |
| **Geographic Utilities** | `pipeline/geo_utils.py` | `resolve_google_maps_short_url()`, `extract_lat_lon_from_url()`, `is_point_in_india()`, `geocode_address()` | **Verified from source code** |
| **Agricultural Land-Cover Validation** | `pipeline/location_validator.py` | `validate_agricultural_location()`, `inspect_worldcover_distribution()`, `AgriculturalValidationOutcome` | **Verified from source code** |
| **Crop Calendar Validation** | `pipeline/crop_validator.py` | `validate_crop_phenology()`, `get_crop_calendar()`, `detect_crop_mismatch()` | **Verified from source code** |
| **Text-to-Speech Engine** | `pipeline/tts_provider.py` | `EdgeTTSProvider`, `GoogleCloudTTSProvider`, `MockTTSProvider`, `synthesize_voice_advisory()`, `get_tts_provider()` | **Verified from source code** |
| **Conversational Onboarding State Machine** | `whatsapp/registration_flow.py` | `handle_incoming()`, `process_registration_step()`, `get_latest_advisory()`, `format_status_advisory()` | **Verified from source code** |
| **Multilingual Advisory Templates** | `whatsapp/messages.py` | `format_status_advisory()`, `format_voice_script()`, `get_message()`, trilingual dictionary mappings (`en`, `mr`, `hi`) | **Verified from source code** |
| **Webhook Server Entry Point** | `webhook_server.py` | FastAPI `app`, Starlette middleware, Flask fallback, HMAC-SHA256 verification, 1MB stream cap | **Verified from source code** |
| **Configuration & Safety Flags** | `common/config.py` & `.env.example` | `ENABLE_OUTBOUND_WHATSAPP`, `DEFAULT_LANGUAGE`, `RAIN_GUARD_TIER1_MM`, `RAIN_GUARD_TIER2_MM` | **Verified from source code** |
| **General Utilities & DB Queries** | `common/utils.py` | `sanitize_sensor_float()`, `verify_webhook_signature()`, database query helper functions | **Verified from source code** |
| **Demonstration CLI Suite** | `demo_khetsense.py` | `main()`, `run_scenario_registration()`, `run_scenario_rainfall()`, `run_scenario_crop_mismatch()`, `run_scenario_missing_sensors()`, `run_scenario_ml_evaluation()` | **Verified from source code & executed** |

---

## 2. Verified Test Suites Executed

Executed live via: `python -m unittest discover -s tests -p "test_*.py"`  
**Result:** 401 tests passed in 44.33 seconds (100% green build, 0 errors, 0 failures).

| Test Module File | Test Count | Pass Rate | Key Capabilities Tested |
|---|:---:|:---:|---|
| `tests/test_phase8_ml_primary_advisory.py` | 9 | 100% | Phase 8 primary ML prediction adoption, wheat scoping, cotton rule fallback, missing data rejection, text/voice parity. |
| `tests/test_phase7f_live_native_model.py` | 13 | 100% | 5-feature model loading, median imputation, severe thresholding ($T=0.27$). |
| `tests/test_phase7e_live_s2_expansion.py` | 14 | 100% | Sentinel-2 B5 red-edge extraction, NDRE, MSAVI formulas, $[0, 1]$ reflectance scaling. |
| `tests/test_phase7c_feature_compatibility.py` | 18 | 100% | Feature compatibility, unit verification, checking for absence of ERA5 live substitution. |
| `tests/test_phase7b_dry_run.py` | 14 | 100% | Safe offline ML advisory dry run, multilingual generation without DB writes. |
| `tests/test_ml_advisory_integration.py` | 15 | 100% | End-to-end ML advisory generation and threshold evaluation. |
| `tests/test_ml_shadow.py` | 16 | 100% | Non-blocking shadow evaluation logging to `ml_shadow_advisories`. |
| `tests/test_registration_flow.py` | 115 | 100% | Conversational state machine, trilingual onboarding, acreage parsing, phone normalization. |
| `tests/test_voice_advisory.py` | 33 | 100% | Vernacular TTS synthesis, Edge-TTS fallback, Opus audio formatting, delivery error handling. |
| `tests/test_multi_method_location.py` | 28 | 100% | GPS pins, Google Maps URL resolution, ESA WorldCover 10m screening, India bounding box. |
| `tests/test_auto_advisory_and_crop_validation.py` | 24 | 100% | Phenological calendar validation, crop mismatch detection, automated scheduled advisory flow. |
| `tests/test_phase6f_safety_remediation.py` | 31 | 100% | Two-tier rainfall guardrails ($5\text{ mm}$ / $15\text{ mm}$), boundary screening, cooldown periods. |
| `tests/test_phase6h_security_remediation.py` | 42 | 100% | HMAC-SHA256 signature verification, 1MB payload limits, message deduplication. |
| `tests/test_phase6a_dry_run.py` | 29 | 100% | Local dry run, database write isolation, pipeline execution fidelity. |

---

## 3. Verified Datasets & Serialized Model Artifacts

| Artifact Name | File Path | Checksum (SHA-256) | Record Count / File Size | Verification Status |
|---|---|---|:---:|---|
| **CSISA Wheat Benchmark Dataset** | `data/research_benchmark/csisa_wheat_multisensor_features_2018.csv` | `ab79e8144aa4cb9b786a35349df944ed7db5b29738069ce38df1f545c306865e` | 7,648 rows $\times$ 34 cols | **Verified on disk** |
| **5-Feature Preprocessor Bundle** | `data/research_benchmark/models/preprocessor_5feat.joblib` | `616128656d1c422cc6292189cb0e045e5e15dc29dff24ab96bf4237740483467` | 2.1 KB | **Verified on disk** |
| **5-Feature Random Forest Checkpoint** | `data/research_benchmark/models/random_forest_5feat.joblib` | `a8b10f1fa5c2b89e6f80b4bfc88273ad40af28d589260c3fa263229cb505e503` | 13.8 MB | **Verified on disk** |
| **5-Feature HistGradientBoosting** | `data/research_benchmark/models/hist_gradient_boosting_5feat.joblib` | `3ae7ef4309544f4ab279be5ac1692dd710d2784a90dbdd0f2cc9e0e4bdd00f14` | 895 KB | **Verified on disk** |
| **Evaluation Manifest** | `reports/evaluation/evaluation_manifest.json` | JSON format | 2.6 KB | **Verified on disk** |
| **Model Comparison Table** | `reports/evaluation/model_comparison.csv` | CSV table (10 models) | 4.1 KB | **Verified on disk** |
| **Confusion Matrices** | `reports/evaluation/confusion_matrices.json` | JSON format (raw counts & %) | 13.6 KB | **Verified on disk** |
| **Evaluation Charts PNG** | `reports/evaluation/evaluation_charts.png` | 4-panel Matplotlib graphic | 742 KB | **Verified on disk** |

---

## 4. Verified Database Schema Migrations

Located in `khetsense/migrations/`:
- `001_initial_schema.sql`: Core tables for `farmers`, `farms`, `advisories`, `farm_polygons` with PostGIS geometry.
- `002_user_roles.sql`: Role-based access control and admin security.
- `003_rainfall_policy_and_advisory_provenance.sql`: Advisory provenance columns, assessment source, and rainfall guardrail fields.
- `004_registration_session_language.sql`: Persistent session state machine and multi-language preference tracking.
- `005_location_selection_and_validation.sql`: Location confirmation and ESA WorldCover validation metadata.
- `006_ml_shadow_evaluation.sql`: `ml_shadow_advisories` table for non-blocking shadow telemetry and prediction divergence tracking.

---

## 5. Items Clearly Marked as Unverified or Simulated

To maintain absolute academic integrity, the following items are formally identified as **simulated, offline, or unverified**:
1. **Live Outbound WhatsApp Delivery:** Simulated in memory (`ENABLE_OUTBOUND_WHATSAPP=false`) to protect against unauthorized messaging. Real mobile delivery was tested during Phase 6 staging but is suppressed in testing and demo scripts.
2. **Longitudinal Field Trials:** The project has **not conducted physical field trials** measuring crop yield increases or water savings on live farms.
3. **Maharashtra Ground-Truth Calibration:** The ML model was trained strictly on Eastern Indian wheat research data (Bihar/Eastern UP) and has **not been validated for Maharashtra Vertisol soils**.
4. **Physical In-Field Hardware:** KhetSense AI is a **zero-hardware satellite solution**; no in-situ soil moisture probe photos or physical circuit boards exist.
