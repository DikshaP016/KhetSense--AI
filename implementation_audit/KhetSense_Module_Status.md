# KhetSense AI — Module Implementation & Verification Status

**Project:** KhetSense AI — Satellite-Based Crop Stress Detection and Multilingual Voice-Enabled Irrigation Advisory System  
**Document Type:** Technical Audit & Verification Matrix  
**Date of Audit:** October 3, 2026  
**Auditor:** Senior Software Engineer & Technical Auditor (MCA Research Project)  
**Git Baseline:** Branch `master` (`e466026 Stage 2 baseline`)  
**Offline Test Suite:** 148 passing unit tests (0 failures, 0 errors, 0 skipped)

---

## 1. Classification Definitions

In strict accordance with project audit standards, the following classifications are applied:

- **Implemented:** Present in the active source code.
- **Mock-tested:** Verified using deterministic mocks, synthetic payloads, or isolated test fixtures.
- **Integration-tested:** Tested with live, authentic external endpoints or actual service interfaces.
- **Live-tested:** Successfully verified in an active runtime deployment with real end-user interaction (e.g., actual WhatsApp mobile devices).
- **Partially implemented:** Core components exist, but secondary functions, edge cases, or dependencies are unfinished.
- **Pending:** Architecture or interface specified, but code execution or verification has not taken place.
- **Blocked:** Execution impeded by missing external credentials, unapplied database migrations, or active bugs.

---

## 2. Comprehensive Module Status Matrix

| Module / Subsystem | Primary Source File(s) | Primary Functions / Classes | Implementation Status | Test & Execution Evidence | Audit Notes & Key Constraints |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **WhatsApp Webhook Ingestion** | `webhook_server.py` | `verify_webhook()`, `handle_webhook()`, `lifespan()` | **Live-tested** | `tests/test_registration_flow.py` (Payload parsing); real ngrok & Meta webhook dispatches | Verifies Meta HMAC SHA-256 signature; returns HTTP 200 within 3s; routes incoming messages asynchronously. |
| **Message Deduplication** | `whatsapp/registration_flow.py` | `claim_message()`, `unclaim_message()`, `is_message_processed()` | **Mock-tested** | `test_registration_flow.py` (atomic conflict simulation); SQL table `processed_messages` | Uses atomic SQL `INSERT ... ON CONFLICT DO NOTHING`. Gracefully falls back to in-memory set if DB is offline. |
| **Language Selection** | `whatsapp/registration_flow.py`, `whatsapp/messages.py` | `parse_language_choice()`, `normalize_language()`, `update_farmer_language()` | **Live-tested** | `test_registration_flow.py` (English, Marathi, Hindi choices); mobile test session | Supports English (`1`/`en`), Marathi (`2`/`mr`), Hindi (`3`/`hi`). Set as Step 1 of onboarding. |
| **Farmer Name Validation** | `common/utils.py`, `whatsapp/registration_flow.py` | `is_valid_farmer_name()`, `clean_farmer_name()` | **Live-tested** | `test_registration_flow.py` (15 name patterns); mobile tests (`diks`, `pobin`) | Rejects single characters, numbers, and system keywords (`status`, `language`). Requires explicit confirmation. |
| **Crop Normalization & Transliteration** | `whatsapp/registration_flow.py`, `whatsapp/messages.py` | `normalize_crop()`, `get_localized_crop()`, `SUPPORTED_CROPS` | **Live-tested** | `test_registration_flow.py` (30+ crop aliases); mobile tests (`Maize`, `tur`) | Normalizes Devanagari script, regional vernacular (e.g., `kapas`, `soya`, `tur`, `arhar`), and English. |
| **Acreage Parsing & Validation** | `whatsapp/registration_flow.py` | `parse_acreage()` | **Live-tested** | `test_registration_flow.py` (Numeric, decimals, units); mobile test (`4`) | Restricts farm area between 0.1 and 50.0 acres. Defaults to 2.5 acres (1.0 ha) if skipped. |
| **Farmer Re-Registration / Restart** | `whatsapp/registration_flow.py` | `handle_incoming()` (lines 1165–1265) | **Live-tested (Bug Identified)** | Mobile test (Farm ID #3 re-registration); `test_registration_flow.py` | **CRITICAL AUDIT FINDING:** Pending name (`pobin`) and crop (`tur`) temporarily masked by old farm record (`diks`, `Maize`) at location step. |
| **Farm Location Selection Flow** | `whatsapp/registration_flow.py` | `handle_incoming()` (states `AWAITING_LOCATION_CHOICE`, `AWAITING_LOCATION`) | **Live-tested (Prompt)** | `test_registration_flow.py` (Options 1, 2, 3); mobile test prompt | Returning farmers can: (1) reuse saved location, (2) share current GPS pin, or (3) select map pin. |
| **Geographic Boundary Verification** | `pipeline/location_validator.py`, `whatsapp/registration_flow.py` | `validate_india_bounds()`, `validate_coordinates_in_bounds()` | **Mock-tested** | `test_registration_flow.py` (Bounding box coordinates) | Enforces Indian bounding box: Latitude 6.0°N – 38.0°N, Longitude 68.0°E – 98.0°E. |
| **Agricultural Location Validation** | `pipeline/location_validator.py` | `validate_agricultural_location()`, `fetch_esa_worldcover_gee()` | **Mock-tested** | `test_registration_flow.py` (Cases A through E); 11 test cases | Evaluates ESA WorldCover 10m classes. Rejects Built-up (50), Barren (60). Withholds advisory if land cover is uncertain. |
| **Boundary & Geometry Estimation** | `pipeline/geo_utils.py`, `pipeline/farmer_registration.py` | `estimate_square_polygon_from_pin()`, `register_farmer_from_pin()` | **Mock-tested** | `test_registration_flow.py` (WKT generation, PostGIS projection) | Converts GPS point into approximate square polygon in PostGIS (EPSG:4326/3857) based on stated acreage. |
| **Sentinel-2 Satellite Indices** | `pipeline/test_pipeline.py` | `fetch_sentinel2_indices()`, `authenticate_earth_engine()` | **Mock-tested (Credentials Present)** | `test_pipeline.py` unit mocks; `credentials/ee-key.json` exists | Queries `COPERNICUS/S2_SR_HARMONIZED`. Calculates NDVI `(B8-B4)/(B8+B4)` and NDWI `(B8-B11)/(B8+B11)`. Cloud filter < 20%. |
| **NASA SMAP Soil Moisture** | `pipeline/test_pipeline.py` | `fetch_smap_soil_moisture()`, `authenticate_and_query_earthdata()` | **Mock-tested** | `test_registration_flow.py` (Mocked responses & HTTP 404 fallbacks) | Queries NASA Earthdata CMR API for `SPL3SMP_E` granules. Extracts surface volumetric soil moisture ($cm^3/cm^3$). |
| **Weather & Rainfall Forecast** | `pipeline/test_pipeline.py` | `fetch_openweather_forecast()` | **Mock-tested** | `test_registration_flow.py` (0mm, 8mm, 25mm rain mocks) | Queries OpenWeatherMap 5-day / 3-hour API. Aggregates cumulative 48-hour precipitation ($mm$). |
| **Crop Stress Classification** | `pipeline/classifier.py` | `classify_ndvi_stress()`, `classify_soil_moisture_stress()`, `get_more_severe()` | **Mock-tested** | `test_registration_flow.py` (Matrix of NDVI vs SMAP states) | **Rule-Based Decision Logic**, NOT ML. Evaluates NDVI thresholds (<0.35, <0.50, >=0.50) and SMAP thresholds (<0.18, <0.28, >=0.28). |
| **Rainfall Guardrail Engine** | `pipeline/classifier.py` | `apply_rainfall_guardrail()`, `infer_recommended_action()` | **Mock-tested** | `test_registration_flow.py` (Dry, moderate, heavy rainfall tests) | If rain $\ge 15mm$, overrides `IRRIGATE_NOW` to `HOLD_RECHECK` or `DELAY_RECHECK` to prevent waterlogging and wasteful pumping. |
| **Multilingual Text Advisory** | `whatsapp/messages.py`, `pipeline/test_pipeline.py` | `format_status_advisory()`, `generate_irrigation_advisory()` | **Mock-tested** | `test_registration_flow.py` (English, Marathi, Hindi text output) | Generates structured WhatsApp advisory cards with localized crop names, stress level, rain forecast, and recommended action. |
| **Voice Advisory Script Generation** | `whatsapp/messages.py` | `format_voice_script()`, `LOCALIZED_CROPS_VOICE` | **Mock-tested** | `tests/test_voice_advisory.py` (11 script generation tests) | Conversational voice scripts in EN, MR, HI. Strictly avoids technical jargon (NDVI, SMAP, PostGIS). Localizes units ($mm$, acres). |
| **Text-to-Speech (TTS) Engine** | `pipeline/tts_provider.py` | `MockTTSProvider`, `GoogleCloudTTSProvider`, `EdgeTTSProvider`, `get_tts_provider()` | **Mock-tested** | `tests/test_voice_advisory.py` (10 provider tests); WAV/MP3 generation | Default is offline `MockTTSProvider`. Live Google Cloud TTS and Edge TTS are disabled unless explicitly configured in `.env`. |
| **WhatsApp Media Upload** | `whatsapp/registration_flow.py` | `upload_whatsapp_media()` | **Mock-tested** | `tests/test_voice_advisory.py` (Multipart upload mock, HTTP 500 error mock) | Uploads audio payload to Meta Graph API v21.0 `/media` endpoint. Returns `media_id`. |
| **WhatsApp Audio Message Delivery** | `whatsapp/registration_flow.py` | `send_whatsapp_audio()`, `deliver_voice_advisory()` | **Mock-tested** | `tests/test_voice_advisory.py` (Audio dispatch mocks, simulated network failures) | Dispatches voice message (`type: "audio"`) via Meta Graph API v21.0. Failure never blocks primary text advisory. |
| **Supabase / PostgreSQL Schema** | `migrations/001` through `005` | SQL DDL scripts | **Partially Implemented (Offline DB)** | Schema definitions match code models; fallback clauses in Python code | Tables: `farms`, `registration_sessions`, `advisories`, `processed_messages`. Migrations 004 & 005 pending live execution. |

---

## 3. Detailed Component Breakdown & Evidence

### 3.1 WhatsApp Conversational Engine
- **Files:** `whatsapp/registration_flow.py`, `whatsapp/messages.py`, `webhook_server.py`
- **Supported Languages:** English (`en`), Marathi (`mr`), Hindi (`hi`).
- **State Machine States:**
  1. `AWAITING_LANGUAGE`
  2. `AWAITING_NAME`
  3. `AWAITING_NAME_CONFIRMATION`
  4. `AWAITING_CROP`
  5. `AWAITING_ACREAGE`
  6. `AWAITING_LOCATION_CHOICE`
  7. `AWAITING_LOCATION`
  8. `AWAITING_LOCATION_CONFIRMATION`
  9. `REGISTERED`
- **Commands:** `restart`, `reset`, `language` / `भाषा`, `status` / `स्थिती`.
- **Live Evidence:** Real WhatsApp interaction successfully traversed language selection, name entry, name confirmation, crop entry, and acreage entry. Disclosed precedence inversion bug upon transitioning to location choice.

### 3.2 Location Validation Engine
- **Files:** `pipeline/location_validator.py`, `pipeline/geo_utils.py`
- **Taxonomy:** ESA WorldCover 10m (Cropland=40, Built-up=50, Bare/sparse=60, Water=80, Tree cover=10).
- **Outcomes:**
  - `SUITABLE_CROPLAND`: Proceed with irrigation advisory.
  - `LIKELY_URBAN`: Advisory withheld; farmer prompted to send actual field location.
  - `BARREN_OR_UNCERTAIN`: Advisory withheld; field uncultivated or NDVI insufficient.
  - `INSUFFICIENT_SATELLITE_DATA`: Advisory withheld; scene cloudy (>20%) or unavailable.
  - `INCOMPLETE_AUXILIARY_DATA`: Auxiliary weather/soil moisture incomplete; uses conservative fallback.
  - `INVALID_COORDINATES`: Outside India bounding box.
- **Safety Safeguard:** No advisory is ever generated if `is_suitable_for_advisory` is `False`.

### 3.3 Crop Stress & Environmental Pipeline
- **Files:** `pipeline/classifier.py`, `pipeline/test_pipeline.py`, `pipeline/ml_inference.py`
- **Satellite Data (Sentinel-2 L2A Harmonized - 10m/20m):**
  - **Live Genuinely Observed Indices (Phase 7E):**
    1. `NDVI`: $(B8 - B4) / (B8 + B4)$ (Canopy vigor/biomass, 10m).
    2. `NDWI`: $(B8 - B11) / (B8 + B11)$ (Canopy moisture/water content, Gao 1996, 20m).
    3. `NDRE`: $(B8 - B5) / (B8 + B5)$ (Chlorophyll/red-edge activity, Barnes et al. 2000, 20m).
    4. `MSAVI`: $[2 \cdot NIR + 1 - \sqrt{(2 \cdot NIR + 1)^2 - 8(NIR - RED)}] / 2$ (Soil-adjusted vegetation index, Qi et al. 1994, computed with $[0, 1]$ reflectance scaling).
- **Soil Moisture:** NASA SMAP L3 Radiometer (`SPL3SMP_E`, 9km gridded surface soil moisture sampled at farm centroid).
- **Weather:** OpenWeatherMap 5-day / 3-hour forecast (48-hour forward accumulation $R_{48h}$).
- **Feature Status Distinction:**
  - *Genuinely Observed Live:* `s2_ndvi`, `s2_ndwi`, `s2_ndre`, `s2_msavi`, `smap_sm_pct`.
  - *Imputed / Unavailable Live:* `era5_precip_season_mm` (121-day backward seasonal reanalysis sum), `era5_temp_mean_c`, `era5_temp_max_c`, `era5_vpd_mean_kpa`. (Live inference safely triggers `FEATURE_INCOMPATIBILITY` when seasonal reanalysis precipitation is unobserved, preventing invalid ML outputs).
- **Active Advisory Nature:** **Expert Rule-Based Engine** with 100% safety floor using dual-index thresholding and rainfall matrix.
- **Rainfall Guardrail Rules:**
  - Rain < 5mm: Normal irrigation recommendation (`IRRIGATE_NOW` / `SCHEDULE_IRRIGATION`).
  - Rain 5–15mm: Moderate rain; reduce to `IRRIGATE_LIGHTLY`.
  - Rain > 15mm: Heavy rain expected; delay irrigation (`DELAY_RECHECK` or `HOLD_RECHECK`).


### 3.4 Multilingual Voice Advisory Engine
- **Files:** `pipeline/tts_provider.py`, `whatsapp/messages.py`, `whatsapp/registration_flow.py`
- **Supported Providers:**
  1. `MockTTSProvider`: Synthetic deterministic audio (default).
  2. `GoogleCloudTTSProvider`: Google Cloud Neural/Wavenet voices (`en-IN-Wavenet-D`, `mr-IN-Wavenet-A`, `hi-IN-Wavenet-A`).
  3. `EdgeTTSProvider`: Microsoft Azure Neural voices (`en-IN-NeerjaNeural`, `mr-IN-AarohiNeural`, `hi-IN-SwaraNeural`).
- **Delivery Mechanism:** Multipart upload to Meta Graph API v21.0 `/media` -> send message with `media_id`.
- **Fault Tolerance:** Non-fatal try-except wrapper ensures voice synthesis failure never impairs text advisory delivery.
- **Verification Level:** Implemented and comprehensively Mock-tested (33 unit tests). Live mobile voice reception is **Pending**.

---

## 4. Audit Summary & Readiness Verdict

1. **Codebase Health:** Clean syntax, strong separation of concerns, comprehensive offline test coverage (148/148 passed).
2. **Safety Guardrails:** Robust. Unvalidated locations, non-cropland, and heavy rainfall strictly prevent hazardous irrigation advice.
3. **Identified Defect:** WhatsApp re-registration session precedence order in `whatsapp/registration_flow.py` (lines 1622–1623 & 1781–1782) must be adjusted before live field deployment.
4. **Research Paper Grounding:** The system architecture must be documented as a **satellite-derived rule-based expert decision system**, avoiding unsupported claims of trained neural network models.
