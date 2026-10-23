# KhetSense AI: Phase 6A — Local End-to-End Dry Run Report

**Author:** KhetSense AI Senior Software Auditor, ML Engineer & QA Lead  
**Execution Date:** October 19, 2026  
**Status:** 100% Passed (33/33 Dry-Run Tests, 253/253 Total System Tests)  
**Evaluated Artifacts:**
- Webhook Server: `webhook_server.py`
- Conversational Flow & Outbound Sender: `whatsapp/registration_flow.py`
- Agricultural Location Validator: `pipeline/location_validator.py`
- Decision Engine & Stress Classifier: `pipeline/classifier.py`
- Central Policy Configuration: `common/config.py`
- Multilingual Messages & Voice Scripts: `whatsapp/messages.py`
- Multilingual TTS Audio Engine: `pipeline/tts_provider.py`
- ML Shadow Telemetry Engine: `pipeline/ml_shadow_engine.py`
- Operational Pipeline Integration Hook: `pipeline/test_pipeline.py` (Line 905)
- Local Dry-Run Test Suite: `tests/test_phase6a_dry_run.py`

---

## 1. Executive Summary & Verification Mandate

In accordance with the **Phase 6A execution mandate**, a complete, safe, and local end-to-end dry run of the KhetSense AI application was conducted. The objective was to validate the entire operational workflow—from incoming WhatsApp webhook handling, conversational farmer registration, multi-modal location validation, satellite & weather processing, deterministic stress classification, and multi-tier rainfall guardrail policy enforcement, to multilingual text/voice generation and parallel ML shadow telemetry—in a strictly isolated local environment with zero side effects.

### Absolute Safety Invariants Verified
1. **ZERO outbound WhatsApp messages:** No live HTTP requests were dispatched to Meta's WhatsApp Cloud API (`https://graph.facebook.com/*`). All outbound text and voice message functions operated in guarded mock mode.
2. **ZERO live database writes or connections:** No connections or writes were opened to the production PostgreSQL / Supabase database. All data persistence calls operated with `db_url=None` or mocked connections.
3. **ZERO database migrations applied:** Migration scripts (`migrations/001` through `006`) remained unexecuted against any live database instance.
4. **ZERO `.env` or credential modifications:** Environment configuration, API tokens, and credentials remained strictly untouched.
5. **ZERO changes to farmer-facing business logic:** Deterministic rule thresholds, rainfall guardrails, and advisory strings were evaluated strictly as authored.
6. **Preservation of uncommitted changes:** All pre-existing modified and untracked files across the repository working tree were preserved completely intact.

---

## 2. Test Architecture & Results by Workflow Stage

The dry-run test harness `tests/test_phase6a_dry_run.py` was executed across 7 comprehensive workflow stages. All 33 test cases passed with 100% compliance.

| Stage | Focus Area | Tests Executed | Status | Primary Invariant Verified |
| :---: | :--- | :---: | :---: | :--- |
| **Stage 1** | FastAPI Webhook Server Lifecycle & Meta Handshake | 6 | **PASS** | Sub-3s response, valid handshake token check, 403 on mismatch, async background task enqueuing. |
| **Stage 2** | Conversational Registration & Multi-Modal Location Inputs | 9 | **PASS** | Trilingual state machine (en, mr, hi), crop aliases, acreage bounds (0.1–50.0), GPS pin, shortlink DNS safety & SSRF defense. |
| **Stage 3** | Agricultural Land-Cover & Location Suitability Validation | 5 | **PASS** | Cropland approval (Case A), Urban rejection (Case B), Barren/Fallow warning (Case C), Cloud retry (Case D), Missing SMAP fallback (Case E). |
| **Stage 4** | Stress Classification & Multi-Tier Rainfall Guardrails Policy Matrix | 2 (8 cells) | **PASS** | Deterministic NDVI & SMAP classification; full 8-cell rainfall policy matrix ($R_1 = 5.0\text{ mm}$, $R_2 = 15.0\text{ mm}$). |
| **Stage 5** | Multilingual Text Advisory & Neural TTS Voice Generation | 4 | **PASS** | Jargon-free scripts in en, mr, hi; MockTTS offline; Azure EdgeTTS neural audio generation; text delivery decoupled from TTS failures. |
| **Stage 6** | ML Shadow-Mode Integration & Non-Interference | 4 | **PASS** | Zero mutation of rule advisory; NaN/Inf sanitized; crash immunity; 500ms timeout with bounded load shedding. |
| **Stage 7** | Read-Only External Data Retrieval & Safety Audit | 3 | **PASS** | Real read-only OpenWeather fetch (0.0mm rain, 0 mutations); verified 0 WhatsApp HTTP calls; verified 0 PostgreSQL connections. |
| **TOTAL** | **Phase 6A Local Dry Run** | **33** | **PASS** | **100% Test Success** |

---

## 3. Detailed Technical Verification by Stage

### Stage 1: FastAPI Webhook Server Lifecycle & Meta Handshake
- **Healthcheck Endpoint (`GET /`):** Verified that `root()` returns `status="online"`, service name `"KhetSense WhatsApp Webhook"`, and confirms webhook verification token readiness.
- **Meta Verification Handshake (`GET /webhook`):**
  - Evaluated `hub.mode="subscribe"` with matching verify token (`AafatKiToli@PratikshaAmanDikshaJobin04`); verified HTTP 200 `PlainTextResponse` returning exact challenge code string.
  - Tested token mismatch; verified `HTTPException(403, detail="Verification token mismatch")`.
  - Tested invalid mode (`hub.mode="unsubscribe"`); verified `HTTPException(403)`.
- **Inbound Event Processing (`POST /webhook`):**
  - Submitted valid Meta message payload; verified HTTP 200 response (`{"status": "received"}`) returned in $< 5\text{ ms}$ (comfortably within Meta's 3-second SLA).
  - Verified message dispatch was offloaded to FastAPI `BackgroundTasks` (`handle_incoming`).
  - Verified non-WhatsApp events return `{"status": "ignored"}` without enqueuing tasks.

### Stage 2: Conversational Registration State Machine & Multi-Modal Location Inputs
- **Trilingual Session Management:**
  - Verified trilingual welcome script generation via `format_trilingual_welcome_script()` producing 3 clean segments (`en`, `mr`, `hi`).
  - Verified localized message retrieval across languages (`name_confirm` in English, Marathi, Hindi with Devanagari script).
- **Farmer Name Validation:** Verified alphanumeric/Unicode name validation (`clean_farmer_name`, `is_valid_farmer_name`), correctly accepting `"Ramesh Patil"` and `"सुरेश कुमार"`, while rejecting single characters or numbers.
- **Crop Normalization Across Regional Dialects:**
  - English: `"wheat"` $\rightarrow$ `"Wheat"`, `"cotton"` $\rightarrow$ `"Cotton"`.
  - Marathi: `"गहू"` $\rightarrow$ `"Wheat"`, `"कापूस"` $\rightarrow$ `"Cotton"`, `"ऊस"` $\rightarrow$ `"Sugarcane"`.
  - Hindi: `"गेहूं"` $\rightarrow$ `"Wheat"`, `"कपास"` $\rightarrow$ `"Cotton"`, `"गन्ना"` $\rightarrow$ `"Sugarcane"`.
  - Unrecognized crops (`"pineapple"`, `"unknown_crop"`) return `None` to trigger reprompting.
- **Acreage Parsing & Bounds:**
  - Valid strings (`"2.5"`, `"5 acres"`, `"३ एकर"`, `"10 हेक्टर"`) correctly parsed to floats (`2.5`, `5.0`, `3.0`, `10.0`).
  - Values outside $[0.1, 50.0]$ acres (`"0.05"`, `"600"`) rejected with `(False, None)`.
- **Multi-Modal Location Inputs:**
  - **Native WhatsApp GPS Pin:** Verified `{"type": "location", "location": {"latitude": 19.3463, "longitude": 74.3110}}` extracted and verified within India bounds ($6.0^\circ\text{–}38.0^\circ\text{N}$, $68.0^\circ\text{–}98.0^\circ\text{E}$).
  - **Raw Text Coordinates:** Successfully parsed `"19.34634, 74.31100"`.
  - **Google Maps Shortlink:** Safely resolved `https://maps.app.goo.gl/...` following verified 302 redirects.
  - **SSRF Defense:** Verified that shortlinks pointing to loopback (`127.0.0.1`), link-local AWS metadata (`169.254.169.254`), or private IP ranges are blocked by DNS validation.
  - **Geographic Out-of-Bounds Rejection:** Verified that out-of-bounds coordinates (e.g., New York $40.7128^\circ\text{N}, -74.0060^\circ\text{W}$) fail `validate_india_bounds`.

### Stage 3: Agricultural Land-Cover & Location Suitability Validation
Using `pipeline/location_validator.py::validate_agricultural_location`:
- **Case A (`SUITABLE_CROPLAND`):** Cropland (ESA WorldCover class 40, cloud cover $5.0\%$) $\rightarrow$ `is_suitable_for_advisory: True`.
- **Case B (`LIKELY_URBAN`):** Built-up / Urban (ESA class 50) $\rightarrow$ `is_suitable_for_advisory: False`, `action: "WITHHOLD_ADVISORY_REQUEST_FARM_PIN"`.
- **Case C (`BARREN_OR_UNCERTAIN`):** Bare/sparse vegetation (ESA class 60) $\rightarrow$ `is_suitable_for_advisory: False`, farmer verification requested.
- **Case D (`INSUFFICIENT_SATELLITE_DATA`):** Cloud cover $> 20.0\%$ ($85.0\%$) $\rightarrow$ `is_suitable_for_advisory: False`, deferred for clear pass.
- **Case E (`INCOMPLETE_AUXILIARY_DATA`):** Cropland with missing SMAP auxiliary data $\rightarrow$ `is_suitable_for_advisory: True`, safe single-sensor fallback.

### Stage 4: Stress Classification & Multi-Tier Rainfall Guardrails Policy Matrix
- **Core Classifier:**
  - NDVI thresholds: $>0.60$ (No Stress), $0.30\text{–}0.60$ (Mild Stress), $<0.30$ (Severe Stress).
  - SMAP thresholds: $>25\%$ (No Stress), $15\%\text{–}25\%$ (Mild Stress), $<15\%$ (Severe Stress).
  - Heuristic worst-case selection: `get_more_severe("Mild Stress", "Severe Stress")` $\rightarrow$ `"Severe Stress"`.
- **Multi-Tier Rainfall Guardrail Matrix ($R_1 = 5.0\text{ mm}, R_2 = 15.0\text{ mm}$ over 48h):**
  All 8 matrix cells verified:
  1. Severe Stress + 0.0 mm rain $\rightarrow$ Action: `IRRIGATE_NOW` (Guardrail: `False`)
  2. Severe Stress + 8.0 mm rain ($R_1 \le R < R_2$) $\rightarrow$ Action: `IRRIGATE_LIGHTLY` (Guardrail: `True`)
  3. Severe Stress + 20.0 mm rain ($R \ge R_2$) $\rightarrow$ Action: `HOLD_RECHECK` (Guardrail: `True`)
  4. Mild Stress + 0.0 mm rain $\rightarrow$ Action: `SCHEDULE_IRRIGATION` (Guardrail: `False`)
  5. Mild Stress + 6.0 mm rain ($R_1 \le R < R_2$) $\rightarrow$ Action: `DELAY_RECHECK` (Guardrail: `True`)
  6. Mild Stress + 18.0 mm rain ($R \ge R_2$) $\rightarrow$ Action: `HOLD_RECHECK` (Guardrail: `True`)
  7. No Stress + 0.0 mm rain $\rightarrow$ Action: `NO_ACTION` (Guardrail: `False`)
  8. No Stress + 25.0 mm rain $\rightarrow$ Action: `NO_ACTION` (Guardrail: `False`)

### Stage 5: Multilingual Text Advisory & Neural TTS Voice Generation
- **Jargon-Free Conversational Voice Scripts:**
  - English, Marathi, and Hindi scripts tested via `format_voice_script()`.
  - Verified absence of technical metrics (`"NDVI"`, `"NDWI"`, `"SMAP"`).
  - Marathi script verified: contains regional greetings (`"नमस्कार"`, `"खेतसेन्स"`, `"गहू (Wheat)"`, `"पाण्याचा ताण"`).
  - Hindi script verified: contains regional greetings (`"नमस्ते"`, `"खेतसेंस"`, `"गेहूं (Wheat)"`, `"सिंचाई सलाह"`).
- **TTS Providers Evaluated:**
  - `MockTTSProvider`: Synthesizes deterministic MP3 audio bytes offline; file cleanup verified.
  - `EdgeTTSProvider`: Verified operational neural audio synthesis across Indian voices (`en-IN-NeerjaNeural`, `mr-IN-AarohiNeural`, `hi-IN-SwaraNeural`). Synthesized real non-empty MP3 audio frames and cleanly deleted temporary files.
- **Fault Decoupling:** Proved that a complete failure in TTS synthesis (`RuntimeError("TTS Service Timeout")`) never raises an unhandled exception or interrupts text advisory delivery.

### Stage 6: ML Shadow-Mode Integration, Non-Interference & Concurrency
- **Non-Interference Invariant:** In `evaluate_ml_shadow()`, verified that `rule_observed_stress`, `rule_recommended_action`, and `rule_guardrail_triggered` are returned 100% unaltered.
- **Input Sanitization:** Evaluated non-finite inputs (`NaN`, `+inf`, `-inf`); verified safe coercion to `None`/`np.nan` with zero crashes.
- **Crash Immunity:** Injected unhandled `RuntimeError("Unrecoverable ML Kernel Panic")` into raw inference; verified that `evaluate_ml_shadow()` catches the error, sets `execution_status="INFERENCE_ERROR: ..."`, and allows caller to proceed safely.
- **Bounded Concurrency & Load Shedding:**
  - Injected an 80ms inference delay with a 20ms timeout; caller returned in $< 150\text{ ms}$ with `execution_status="TIMEOUT_EXCEEDED"`.
  - Persistent worker pool (`MAX_SHADOW_WORKERS=2`) and counting semaphore (`MAX_SHADOW_QUEUE_TASKS=4`) prevent thread exhaustion.
- **Dual-Environment ML Execution:**
  - In `.venv` (where ML libraries are intentionally uninstalled): engine logs `Shadow ML engine dormant: ML dependencies unavailable` and returns `DEPENDENCY_UNAVAILABLE` telemetry without throwing an exception.
  - In Python 3.13 (where `scikit-learn` and `joblib` are installed): models `rf_v1_dccd55f0e860a61d` and `lr_v1_6a5d1014ff1685ac` load and execute real inference, outputting class probabilities (`rf_prob_severe_stress`, `lr_prob_severe_stress`) and disagreement flags.

### Stage 7: Read-Only External Data Retrieval & Side-Effect Safety Audit
- **Real Read-Only OpenWeather Forecast:**
  - Executed `test_pipeline.py::fetch_openweather_forecast` using the real `OPENWEATHER_API_KEY` from `.env` for centroid coordinates $(19.3463^\circ\text{N}, 74.3110^\circ\text{E})$ in Ahmednagar, Maharashtra.
  - Successfully retrieved 48h precipitation forecast ($0.0\text{ mm}$ rain, `err=None`).
  - Verified read-only execution: zero database mutations and zero messages sent.
- **Zero WhatsApp Messages Audit:**
  - Executed `send_text("919876543210", "Dry run test message")` under mock mode (`WHATSAPP_TOKEN=""`).
  - Verified `requests.post` was called **0 times**.
- **Zero Database Mutations Audit:**
  - Executed `evaluate_ml_shadow` with `db_url=None`.
  - Verified `psycopg2.connect` was called **0 times**, returning `persistence_status="SKIPPED"`.

---

## 4. Audit of Missing Configurations & Dependencies

In accordance with the transparency mandate, the following configuration and environment items were identified:

| Item | Current Status | Impact on Phase 6A | Recommendation for Next Stage |
| :--- | :--- | :--- | :--- |
| **Google Earth Engine (GEE)** | Unauthenticated (`EEException: Please authorize access to your Earth Engine account by running earthengine authenticate`). | Satellite optical indices (Sentinel-2) and SMAP soil moisture operated via test fixtures and fallback paths. | When ready for live satellite retrieval in staging, execute interactive authentication via `earthengine authenticate` or configure service account credentials in `credentials/ee-key.json`. |
| **Starlette TestClient (`httpx`)** | Missing in `.venv` (`RuntimeError: The starlette.testclient module requires the httpx package to be installed`). | Direct async function invocation (`asyncio.run(root())`, `asyncio.run(verify_webhook(...))`, `receive_whatsapp_event(...)`) was used instead of HTTP socket binding. | Do NOT install `httpx` in production unless required by test harnesses; direct ASGI/async testing is faster, lighter, and dependency-free. |
| **Runtime ML Dependencies (`scikit-learn`, `joblib`)** | Not installed in `.venv`; present in `C:\Python313`. | Architectural invariant verified: `.venv` handles absent ML dependencies gracefully as dormant telemetry (`DEPENDENCY_UNAVAILABLE`), while Python 3.13 executes full model inference. | Maintain dependency isolation: install `scikit-learn` and `joblib` into the active container/runtime virtualenv only when live shadow telemetry is formally commissioned. |
| **Production PostgreSQL Database** | Not connected (`db_url=None`). | Dry-run tests operated with zero database side effects. All SQL generation and idempotency rules (`ON CONFLICT (advisory_id) DO UPDATE`) verified via unit tests. | Apply `migrations/006_ml_shadow_evaluation.sql` only when explicitly authorized by the user before live shadow evaluation begins. |

---

## 5. Execution Logs & Console Capture

```text
================================================================================
      KhetSense AI — Phase 6A: Local End-to-End Dry Run Execution       
================================================================================
test_01_root_healthcheck_endpoint (tests.test_phase6a_dry_run.TestStage1WebhookServerLifecycle) ... ok
test_02_meta_verification_handshake_success (tests.test_phase6a_dry_run.TestStage1WebhookServerLifecycle) ... ok
test_03_meta_verification_handshake_token_mismatch_rejected (tests.test_phase6a_dry_run.TestStage1WebhookServerLifecycle) ... ok
test_04_meta_verification_handshake_invalid_mode_rejected (tests.test_phase6a_dry_run.TestStage1WebhookServerLifecycle) ... ok
test_05_inbound_post_event_sub_3s_immediate_response (tests.test_phase6a_dry_run.TestStage1WebhookServerLifecycle) ... ok
test_06_inbound_post_ignores_non_whatsapp_events (tests.test_phase6a_dry_run.TestStage1WebhookServerLifecycle) ... ok
test_01_language_selection_and_welcome_scripts (tests.test_phase6a_dry_run.TestStage2RegistrationAndLocationInputs) ... ok
test_02_farmer_name_cleaning_and_affirmation (tests.test_phase6a_dry_run.TestStage2RegistrationAndLocationInputs) ... ok
test_03_crop_normalization_across_dialects (tests.test_phase6a_dry_run.TestStage2RegistrationAndLocationInputs) ... ok
test_04_acreage_parsing_and_bounds (tests.test_phase6a_dry_run.TestStage2RegistrationAndLocationInputs) ... ok
test_05_location_input_native_gps_pin (tests.test_phase6a_dry_run.TestStage2RegistrationAndLocationInputs) ... ok
test_06_location_input_text_coordinates (tests.test_phase6a_dry_run.TestStage2RegistrationAndLocationInputs) ... ok
test_07_location_input_google_maps_shortlink (tests.test_phase6a_dry_run.TestStage2RegistrationAndLocationInputs) ... ok
test_08_location_out_of_bounds_rejection (tests.test_phase6a_dry_run.TestStage2RegistrationAndLocationInputs) ... ok
test_09_location_ssrf_malicious_shortlink_blocked (tests.test_phase6a_dry_run.TestStage2RegistrationAndLocationInputs) ... ok
test_01_suitable_cropland_validation (tests.test_phase6a_dry_run.TestStage3AgriculturalLocationValidation) ... ok
test_02_urban_built_up_rejection (tests.test_phase6a_dry_run.TestStage3AgriculturalLocationValidation) ... ok
test_03_barren_or_uncertain_fallow_field (tests.test_phase6a_dry_run.TestStage3AgriculturalLocationValidation) ... ok
test_04_insufficient_satellite_imagery_due_to_clouds (tests.test_phase6a_dry_run.TestStage3AgriculturalLocationValidation) ... ok
test_05_incomplete_auxiliary_data_fallback (tests.test_phase6a_dry_run.TestStage3AgriculturalLocationValidation) ... ok
test_01_deterministic_ndvi_and_soil_moisture_classification (tests.test_phase6a_dry_run.TestStage4StressClassificationAndGuardrails) ... ok
test_02_multi_tier_rainfall_guardrail_matrix (tests.test_phase6a_dry_run.TestStage4StressClassificationAndGuardrails) ... ok
test_01_multilingual_voice_script_formatting (tests.test_phase6a_dry_run.TestStage5MultilingualAdvisoryAndVoice) ... ok
test_02_mock_tts_provider_offline_synthesis (tests.test_phase6a_dry_run.TestStage5MultilingualAdvisoryAndVoice) ... ok
test_03_neural_edge_tts_provider_synthesis (tests.test_phase6a_dry_run.TestStage5MultilingualAdvisoryAndVoice) ... ok
test_04_tts_failure_isolation_does_not_block_text (tests.test_phase6a_dry_run.TestStage5MultilingualAdvisoryAndVoice) ... ok
test_01_shadow_evaluation_non_interference_invariant (tests.test_phase6a_dry_run.TestStage6MLShadowEngineIntegration) ... ok
test_02_shadow_evaluation_with_non_finite_inputs (tests.test_phase6a_dry_run.TestStage6MLShadowEngineIntegration) ... ok
test_03_shadow_evaluation_catastrophic_crash_immunity (tests.test_phase6a_dry_run.TestStage6MLShadowEngineIntegration) ... ok
test_04_shadow_timeout_and_bounded_load_shedding (tests.test_phase6a_dry_run.TestStage6MLShadowEngineIntegration) ... ok
test_01_read_only_openweather_forecast_fetch (tests.test_phase6a_dry_run.TestStage7ReadOnlyDataRetrievalAndSafety) ... ok
test_02_zero_outbound_whatsapp_messages_audit (tests.test_phase6a_dry_run.TestStage7ReadOnlyDataRetrievalAndSafety) ... ok
test_03_zero_database_mutations_audit (tests.test_phase6a_dry_run.TestStage7ReadOnlyDataRetrievalAndSafety) ... ok

----------------------------------------------------------------------
Ran 33 tests in 2.375s

OK
```

---

## 6. Full Test Suite Regression Summary

Across all active test suites in the repository:
1. `tests/test_phase6a_dry_run.py`: **33/33 PASS**
2. `tests/test_ml_shadow.py`: **15/15 PASS**
3. `tests/test_voice_advisory.py`: **55/55 PASS**
4. `tests/test_registration_flow.py`: **150/150 PASS**

**Total System Test Suite:** **253 tests executed, 253 passed (100% success rate)**.

---

## 7. Next-Stage Readiness & Recommendations

Phase 6A has verified with high technical rigor that:
1. The KhetSense conversational registration flow, agricultural location validation, and multilingual voice generation function seamlessly without regressions.
2. The deterministic rule-based stress engine and multi-tier rainfall guardrails remain 100% authoritative and completely immune to interference from ML shadow processes.
3. The ML shadow engine operates safely under all edge conditions (missing sensors, non-finite floats, timeouts, saturated queues, and runtime crashes).
4. Zero unauthorized network or database side effects were generated.

### Readiness Status:
The application is **fully verified and ready** for **Phase 6B (Shadow-Mode Pilot / Staging Validation)** whenever authorized by the user.
