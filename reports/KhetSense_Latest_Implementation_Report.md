# KhetSense AI — Latest Implementation Status Report

**Document Version:** 2.0.0  
**Audit Date:** October 14, 2026  
**Auditor Profile:** Senior Software Auditor, Python Backend Systems Engineer, QA Specialist  
**Project:** KhetSense AI — Integrated Satellite-Based Crop-Water-Stress Assessment & Multilingual Voice-Enabled Irrigation Advisory System  
**Repository Path:** `C:\Users\NIDEEKSHA\Documents\DEEKSHA\MASTERS\Research Project\khetsense\`  
**Target Platform:** Python 3.13.5 (CPython, Windows x64), FastAPI 0.141.1, PostgreSQL 15+ / PostGIS 3.3+, Google Earth Engine, Meta WhatsApp Cloud API v21.0  

---

## 1. Project Overview

### 1.1 Purpose and Problem Statement
Smallholder agriculture in semi-arid and monsoon-dependent regions of India (specifically Maharashtra and the Deccan Plateau) faces escalating water stress, erratic precipitation patterns, and acute groundwater depletion. Farmers often lack access to timely, hyper-local, and scientifically rigorous irrigation guidance. Existing advisory platforms suffer from three systemic barriers:
1. **Coarse Spatial Resolution:** Generalized regional agro-advisories fail to account for field-specific soil moisture, crop canopy vigor, and localized rainfall dynamics.
2. **Linguistic and Literacy Barriers:** Complex text-heavy dashboards or English/standard-Hindi-only interfaces alienate rural farmers who speak regional dialects or Marathi and rely primarily on voice communications.
3. **Complex User Experience:** Requiring farmers to install specialized mobile applications with complex navigation results in severe friction and abandonment.

**KhetSense AI** solves these challenges by combining satellite remote sensing (Sentinel-2 10-meter optical imagery and NASA SMAP 9-kilometer microwave radiometer surface soil moisture) with 48-hour localized weather forecasts, routing personalized irrigation advisories directly to farmers through WhatsApp using conversational text and synchronized multilingual neural voice notes in English, Marathi, and Hindi.

### 1.2 Actual Current System Architecture
The current implementation adheres to a decoupled, event-driven, text-first micro-architecture:

```
+-----------------------------------------------------------------------------------+
|                                 FARMER CHATBOT                                    |
|              WhatsApp Mobile Client (English / Marathi / Hindi)                   |
+-----------------------------------------------------------------------------------+
                                       |
                   Inbound Webhook     |  Outbound Text & Voice Notes
                   (JSON payload)      |  (Meta Graph API v21.0)
                                       v
+-----------------------------------------------------------------------------------+
|                        FASTAPI INGESTION & WEBHOOK SERVER                         |
|   - webhook_server.py: Verification (GET /webhook), Ingestion (POST /webhook)     |
|   - FastAPI BackgroundTasks: Offloads processing to maintain <2s webhook SLA      |
+-----------------------------------------------------------------------------------+
                                       |
                                       v
+-----------------------------------------------------------------------------------+
|                      STATE MACHINE & REGISTRATION ENGINE                          |
|   - whatsapp/registration_flow.py: 8-State Registration State Machine             |
|   - common/utils.py: Phone Normalization, Name & Coordinate Parsing               |
|   - common/utils.py: Anti-SSRF Shortlink Resolver (_PinnedHTTPAdapter)            |
|   - Supabase PostGIS: registration_sessions (State persistence & deduplication)   |
+-----------------------------------------------------------------------------------+
                                       |
                         Upon Successful Registration /
                         Advisory STATUS Command Request
                                       v
+-----------------------------------------------------------------------------------+
|                     DATA RETRIEVAL & SCREENING PIPELINE                           |
|   - pipeline/location_validator.py: Agricultural Suitability Screening            |
|     (ESA WorldCover 10m Land Cover, S2 Cloud Screening, India Coordinate Bounds)  |
|   - pipeline/test_pipeline.py: Sentinel-2 SR Harmonized (NDVI B8/B4, NDWI B8/B11)|
|   - pipeline/test_pipeline.py: NASA SMAP SPL3SMP_E 9km Surface Soil Moisture      |
|   - pipeline/test_pipeline.py: OpenWeather 5-day / 3-hour Forecast (48h horizon)  |
+-----------------------------------------------------------------------------------+
                                       |
                                       v
+-----------------------------------------------------------------------------------+
|                       DECISION ENGINE & GUARDRAIL RULES                           |
|   - pipeline/classifier.py: Deterministic Rule-Based Crop Stress Classifier       |
|     (NDVI Classes: >0.6, 0.3-0.6, <0.3; SMAP Classes: >25%, 15-25%, <15%)         |
|     Worst-Case Severity Heuristic + 48-Hour Rainfall Guardrail (R1=5mm, R2=15mm)  |
|   - Output: Recommended Action (e.g., IRRIGATE_NOW, HOLD_RECHECK, NO_ACTION)      |
+-----------------------------------------------------------------------------------+
                                       |
                                       v
+-----------------------------------------------------------------------------------+
|                     OMNICHANNEL DISPATCH & VOICE SYNTHESIS                        |
|   - whatsapp/registration_flow.py: send_farmer_response()                         |
|   - Text-First Delivery: Sends localized WhatsApp formatted text card first       |
|   - Voice Synthesis (Feature Flag ENABLE_VOICE_CHATBOT):                          |
|     * EdgeTTSProvider (Microsoft Azure Neural: en-IN, mr-IN, hi-IN)               |
|     * Trilingual MP3 Sequential Concatenation for Initial Welcome Onboarding     |
|     * Speech Sanitization (clean_text_for_speech: markdown & emoji removal)       |
|   - WhatsApp Media Upload (POST /v21.0/{phone_number_id}/media)                   |
|   - Audio Dispatch (POST /v21.0/{phone_number_id}/messages type="audio")          |
|   - Safe Failure Isolation: Audio errors do NOT retract or duplicate text         |
+-----------------------------------------------------------------------------------+
```

### 1.3 Main User Interactions and Expected Outputs
1. **Initial Farmer Onboarding:**
   - **Farmer Input:** Any greeting or message (e.g., "Hi", "Namaste", "नमस्कार").
   - **System Output:** Localized text prompt presenting 3 language options (`1: English`, `2: Marathi`, `3: Hindi`), paired with a sequential trilingual neural voice note speaking the welcome guidance in English, Marathi, and Hindi.
2. **Conversational Registration Flow:**
   - **Farmer Input:** Sequential turns providing Name, Crop Name (e.g., "Cotton", "कापूस"), Land Acreage (e.g., "5.5 acres"), and Farm Location.
   - **Supported Location Inputs:**
     - Native WhatsApp GPS location pin.
     - Direct Google Maps URL (`https://www.google.com/maps?q=19.34634,74.31100` or `/@19.34634,74.31100,15z`).
     - Google Maps Shortlink (`https://maps.app.goo.gl/AbCdEf123` or `https://goo.gl/maps/xYz987`).
     - Explicit raw coordinates text (`19.34634, 74.31100` or `Lat: 19.34634, Lon: 74.31100`).
   - **System Output:** Contextual localized confirmation prompts and affirmative validation.
3. **Automated Pipeline Execution & Advisory Dispatch:**
   - **Trigger:** Immediate upon farm registration confirmation, or upon farmer texting "STATUS" (`स्थिती`, `स्थिति`).
   - **System Processing:** Fetches satellite canopy vigor, soil moisture, and weather forecast, checks land suitability, and evaluates stress.
   - **System Output:** Structured WhatsApp message card detailing farm indices, observed stress level, 48-hour forecast rainfall, and actionable irrigation instructions, followed by an accompanying spoken audio note in the farmer's registered language.
4. **Safety & Suitability Notices:**
   - If the submitted location resolves to non-agricultural built-up land (`LIKELY_URBAN`) or barren land (`BARREN_OR_UNCERTAIN`), the irrigation advisory is withheld, and a warning notification is sent via text and voice prompting the farmer to send a pin located within their crop field.

### 1.4 Intended Users and System Boundaries
- **Intended Users:** Smallholder and medium-scale farmers in India (primary focus: Maharashtra), agricultural extension workers, and agronomists.
- **Geographic Scope:** Bounded to the Republic of India: Latitude 6.0°N to 38.0°N, Longitude 68.0°E to 98.0°E.
- **System Boundaries:**
  - KhetSense AI is an advisory decision-support tool, not an automated closed-loop valve controller or SCADA actuator.
  - The stress assessment is strictly rule-based and derived from public remote sensing products; it does not replace localized in-situ agronomic soil chemical testing.

---

## 2. Repository and Technology Stack

### 2.1 Repository Folder Structure
```
khetsense/
├── .env.example                               # Template for required environment variables
├── requirements.txt                           # Pinned Python package dependencies
├── webhook_server.py                          # FastAPI server for Meta WhatsApp Cloud API webhooks
├── common/
│   ├── __init__.py                            # Package initialization and exports
│   ├── config.py                              # Central decision thresholds, rainfall policy, and actions
│   └── utils.py                               # Anti-SSRF shortlink resolver, phone normalization, coordinate parser
├── pipeline/
│   ├── __init__.py
│   ├── classifier.py                          # Rule-based stress classification & rainfall guardrails
│   ├── farmer_registration.py                 # PostGIS spatial registration & polygon generation
│   ├── geo_utils.py                           # Geometry manipulation & coordinate bounds checking
│   ├── location_validator.py                  # Agricultural land cover screening (ESA WorldCover 10m)
│   ├── test_pipeline.py                       # Core satellite, SMAP, and weather data orchestration
│   └── tts_provider.py                        # Text-to-Speech provider abstraction (EdgeTTS, GoogleCloud, Mock)
├── whatsapp/
│   ├── __init__.py
│   ├── messages.py                            # Multilingual message catalogs, speech cleaner, templates
│   └── registration_flow.py                   # Central state machine, dispatcher, retry engine, Meta API client
├── migrations/
│   ├── 001_initial_schema.sql                 # Baseline farms and advisories tables with PostGIS extensions
│   ├── 002_registration_sessions.sql         # Conversational session tracking and deduplication
│   ├── 003_rainfall_policy_and_advisory_provenance.sql # Provenance audit columns & recommended actions
│   ├── 004_registration_session_language.sql # Session-level preferred language persistence
│   └── 005_location_selection_and_validation.sql # Multi-option location and validation audit tracking
├── credentials/                               # (Git-ignored) GEE service account keys (ee-key.json)
├── reports/                                   # Audit and QA documentation reports
└── tests/
    ├── __init__.py
    ├── test_registration_flow.py              # 150 unit & integration tests for registration and location
    └── test_voice_advisory.py                 # 55 unit & integration tests for TTS and omnichannel dispatch
```

### 2.2 Active Technologies, Frameworks, and Libraries
- **Language Runtime:** Python 3.13.5 (CPython 64-bit).
- **Web & Asynchronous Framework:** FastAPI `0.141.1`, Starlette `1.7.0`, Uvicorn `0.54.0`, AnyIO `4.15.1`.
- **Database & Spatial Engine:** PostgreSQL 15+ with PostGIS 3.3+, accessed via `psycopg2-binary 2.9.13`.
- **Remote Sensing & Earth Observation:** Google Earth Engine Python API `earthengine-api 1.7.42`, Google Auth `2.57.1`.
- **Weather Services:** OpenWeather 5-day / 3-hour Forecast API via `requests 2.34.2`.
- **Voice Synthesis & Processing:** `edge-tts 7.3.1` (Microsoft Azure Neural TTS WebSocket client), `aiohttp 3.14.5`.
- **HTTP Client & Security:** `requests 2.34.2`, `urllib3 2.7.0` (with custom pool adapter for IP pinning).
- **Configuration & Validation:** `pydantic 2.13.5`, `python-dotenv 1.2.3`.

### 2.3 Entry Points, Backend Modules, and Configuration Files
- **Server Entry Point:** `webhook_server.py` (`uvicorn webhook_server:app --host 0.0.0.0 --port 8000`).
- **Pipeline Standalone Runner:** `pipeline/test_pipeline.py` (CLI execution: `python pipeline/test_pipeline.py [farm_id]`).
- **Configuration File:** `common/config.py` (Defines `RainfallPolicyConfig`, R1/R2 thresholds, action constants).

---

## 3. Module-by-Module Implementation Audit

### 3.1 Webhook Server (`webhook_server.py`)
- **Responsibility:** Ingests and acknowledges Meta WhatsApp Cloud API webhooks.
- **Key Functions / Endpoints:**
  - `GET /`: Health check endpoint returning `{ status: "ok", service: "khetsense-webhook" }`.
  - `GET /webhook`: Meta Webhook Verification Challenge. Validates `hub.mode == "subscribe"` and `hub.verify_token == WHATSAPP_VERIFY_TOKEN`, returning `hub.challenge`.
  - `POST /webhook`: Main webhook receiver. Extracts inbound messages and enqueues processing via `fastapi.BackgroundTasks` before returning HTTP 200 `{ status: "received" }` within milliseconds.
- **Error Handling:** Malformed payloads or missing signatures return HTTP 200 to prevent Meta retry storming, while errors are logged with stack traces.

### 3.2 Common Utilities & Security (`common/utils.py`)
- **Responsibility:** Independent, zero-dependency shared helper functions.
- **Key Functions & Classes:**
  - `normalize_phone(phone)`: Strips formatting and prefixes `91` to 10-digit Indian numbers.
  - `mask_phone(phone)`: Sanitizes phone numbers for logging (e.g., `919876543210` -> `...+3210`).
  - `is_valid_farmer_name(text)`: Validates names against lengths (2-80 chars), 1-4 word tokens, Devanagari Unicode marks, and greeting blocklists.
  - `extract_direct_coordinates(text)`: Regex extraction of coordinates from query parameters (`?q=`, `ll=`), viewports (`/@lat,lon`), labeled strings (`Lat:... Lon:...`), and directional formats (`19.34 N, 74.31 E`).
  - `validate_destination_safety(url_or_location, allowed_hosts)`: Strict Anti-SSRF validator. Enforces HTTPS, approved host whitelisting, port 443, no user credentials, DNS resolution, and rejects private, loopback, link-local, multicast, and cloud metadata IPs.
  - `_PinnedHTTPAdapter`: Custom `requests.adapters.HTTPAdapter` and `urllib3.connectionpool.HTTPSConnectionPool` implementation that pins connections directly to the verified public IP while preserving TLS SNI and certificate verification without modifying global socket behavior.
  - `resolve_google_maps_shortlink(url, max_redirects=3, timeout=3.0)`: Follows shortlink redirects hop-by-hop with pre-extraction destination safety validation.
  - `parse_location_from_text(text, resolve_shortlinks=True)`: High-level location parser executing regex extraction followed by secure shortlink resolution.

### 3.3 Central Decision Configuration (`common/config.py`)
- **Responsibility:** Single source of truth for decision engine constants and thresholds.
- **Key Constants:**
  - `RainfallPolicyConfig`: Frozen dataclass containing `R1 = 5.0 mm`, `R2 = 15.0 mm`, `FORECAST_HOURS = 48`, `FORECAST_SLICES = 16`.
  - Standard action strings: `ACTION_IRRIGATE_NOW`, `ACTION_IRRIGATE_LIGHTLY`, `ACTION_SCHEDULE_IRRIGATION`, `ACTION_DELAY_RECHECK`, `ACTION_HOLD_RECHECK`, `ACTION_NO_ACTION`, `ACTION_INSUFFICIENT_DATA`.

### 3.4 Crop Stress Classifier (`pipeline/classifier.py`)
- **Responsibility:** Deterministic expert system for stress classification and advisory generation.
- **Key Functions:**
  - `classify_ndvi_stress(ndvi)`: Classifies Sentinel-2 NDVI into `No Stress` (>0.6), `Mild Stress` (0.3–0.6), or `Severe Stress` (<0.3).
  - `classify_soil_moisture_stress(sm_pct)`: Classifies SMAP surface soil moisture into `No Stress` (>25%), `Mild Stress` (15–25%), or `Severe Stress` (<15%).
  - `get_more_severe(cat1, cat2)`: Heuristic ranking: `Severe Stress (3) > Mild Stress (2) > No Stress (1) > Unknown (0)`.
  - `validate_forecast_rainfall(forecast_rain_mm)`: Rejects boolean, negative, NaN, and Infinite inputs.
  - `apply_rainfall_guardrail(observed_stress, forecast_rain_mm)`: Evaluates observed stress against 48h rainfall to determine action.
  - `generate_irrigation_advisory(...)`: Generates clear, plain-language advisory text in English.

### 3.5 Location Validator (`pipeline/location_validator.py`)
- **Responsibility:** Prevents running advisories on unsuitable, non-cropland locations.
- **Key Functions:**
  - `validate_coordinates_in_bounds(lat, lon)`: Validates coordinates against India bounds (6.0°N–38.0°N, 68.0°E–98.0°E).
  - `fetch_esa_worldcover_gee(farm_geom)`: Queries ESA WorldCover 10m to determine majority land-cover class (Cropland class 40, Built-up class 50, Bare/sparse class 60).
  - `validate_agricultural_location(...)`: Returns comprehensive assessment dictionary (`is_suitable_for_advisory`, `outcome`, `reason`, `land_cover_class`).

### 3.6 Farm Registration & PostGIS Storage (`pipeline/farmer_registration.py`)
- **Responsibility:** Persists farmer details and constructs PostGIS spatial boundaries.
- **Key Functions:**
  - `point_to_square_polygon(lat, lon, area_acres)`: Converts a point coordinate into a square polygon buffered by acreage (or default 100m buffer) with WGS84 SRID 4326.
  - `register_farmer_from_pin(...)`: Upserts farmer record into `farms` table with `boundary_source='pin_buffered'` and `area_source='farmer_reported'`.

### 3.7 Data Pipeline Orchestrator (`pipeline/test_pipeline.py`)
- **Responsibility:** Coordinates end-to-end data fetching, validation, advisory generation, and persistence.
- **Key Functions:**
  - `authenticate_earth_engine(key_path)`: Authenticates GEE using service account credentials.
  - `fetch_sentinel2_indices(geometry)`: Computes mean NDVI (`[B8-B4]/[B8+B4]`) and mean NDWI (`[B8-B11]/[B8+B11]`) on `COPERNICUS/S2_SR_HARMONIZED` (<20% cloud cover).
  - `fetch_smap_soil_moisture(centroid_lon, centroid_lat)`: Samples `NASA/SMAP/SPL3SMP_E/006` (or fallback `005`) for `soil_moisture_am`/`pm` at 9km scale.
  - `fetch_openweather_forecast(api_key, lat, lon)`: Sums 48h precipitation across 16 3-hour slices.
  - `save_advisory_to_database(...)`: Inserts advisory record into `advisories` table with complete input indices and provenance metadata.
  - `run_pipeline_for_farm(farm_id, ...)`: Thread-safe, deduplicated execution wrapper. Evaluates location suitability, executes data fetches, calculates stress, persists results, and invokes the WhatsApp text-first voice dispatcher.

### 3.8 Text-to-Speech Engine (`pipeline/tts_provider.py`)
- **Responsibility:** Provides unified audio synthesis abstraction across providers.
- **Classes & Functions:**
  - `BaseTTSProvider`: Abstract base declaring `synthesize()`, `is_available()`, and `synthesize_multilingual()`.
  - `MockTTSProvider`: Offline mock generating valid 32kbps MP3 sync frames for automated testing.
  - `GoogleCloudTTSProvider`: REST client for Google Cloud Text-to-Speech (`en-IN-Wavenet-D`, `mr-IN-Wavenet-A`, `hi-IN-Wavenet-A`).
  - `EdgeTTSProvider`: Microsoft Azure Neural TTS client via `edge-tts` (`en-IN-NeerjaNeural`, `mr-IN-AarohiNeural`, `hi-IN-SwaraNeural`).
  - `get_tts_provider(name)`: Factory returning configured provider (defaults safely to `MockTTSProvider` if external services are unavailable).

### 3.9 Multilingual Message Engine (`whatsapp/messages.py`)
- **Responsibility:** Catalogs localized prompts and formats speech scripts.
- **Key Functions:**
  - `normalize_language(lang)` / `parse_language_choice(text)`: Parses `1`/`2`/`3` and textual language names into `en`, `mr`, or `hi`.
  - `clean_text_for_speech(text, lang)`: Strips emojis, markdown, and converts map URLs to localized spoken text.
  - `format_trilingual_welcome_script()`: Returns ordered tuples `[("...", "en"), ("...", "mr"), ("...", "hi")]` for multi-voice welcome audio generation.
  - `format_voice_script(...)`: Generates spoken audio script for advisories in English, Marathi, or Hindi.

### 3.10 WhatsApp State Machine & Central Dispatcher (`whatsapp/registration_flow.py`)
- **Responsibility:** Core conversational state engine, message deduplication, and outbound communication.
- **State Flow:**
  - `AWAITING_LANGUAGE` -> `AWAITING_NAME` -> `AWAITING_NAME_CONFIRMATION` -> `AWAITING_CROP` -> `AWAITING_ACREAGE` -> `AWAITING_LOCATION_CHOICE` -> `AWAITING_LOCATION` -> `AWAITING_LOCATION_CONFIRMATION` -> `REGISTERED`.
- **Key Functions:**
  - `handle_incoming_message(message_data, ...)`: State router with atomic message claim and deduplication.
  - `send_farmer_response(...)`: Centralized Omnichannel Dispatcher. Delivers text first via Meta Cloud API; if text succeeds and `ENABLE_VOICE_CHATBOT=true`, synthesizes audio and dispatches voice note.
  - `retry_audio_delivery(...)`: Retries audio delivery without re-sending duplicate text.
  - `upload_whatsapp_media(...)`: Uploads generated MP3 to Meta Graph API v21.0 `/media` endpoint.
  - `send_whatsapp_audio(...)`: Sends audio message via Meta Graph API v21.0 `/messages`.

---

## 4. Satellite, Soil-Moisture, and Weather Pipeline

### 4.1 Sentinel-2 Optical Remote Sensing
- **GEE Image Collection:** `COPERNICUS/S2_SR_HARMONIZED` (Level-2A Surface Reflectance).
- **Cloud Filtering:** Filtered for `CLOUDY_PIXEL_PERCENTAGE < 20.0`.
- **Spectral Indices Computed:**
  - **NDVI (Normalized Difference Vegetation Index):**
    $$\text{NDVI} = \frac{\text{B8} - \text{B4}}{\text{B8} + \text{B4}}$$
    Where Band 8 is Near-Infrared (NIR, center 842 nm) and Band 4 is Red (center 665 nm). Evaluates crop canopy greenness and photosynthetic vigor.
  - **NDWI (Normalized Difference Water Index - Gao 1996):**
    $$\text{NDWI} = \frac{\text{B8} - \text{B11}}{\text{B8} + \text{B11}}$$
    Where Band 8 is NIR and Band 11 is Short-Wave Infrared (SWIR, center 1610 nm). Sensitive to liquid water absorption in crop canopy vegetation.
- **Spatial Reducer:** `ee.Reducer.mean()` calculated over the farm polygon boundary at 10-meter native spatial resolution (`scale=10`, `maxPixels=1e9`).

### 4.2 NASA SMAP Soil Moisture
- **Product:** SMAP L3 Enhanced Radiometer Surface Soil Moisture (`NASA/SMAP/SPL3SMP_E/006`, with graceful fallback to `005`).
- **Depth Layer:** Surface soil layer (top 0 to 5 cm depth).
- **Target Variables:** `soil_moisture_am` (primary, descending orbit ~6:00 AM local time), falling back to `soil_moisture_pm` (ascending orbit ~6:00 PM local time).
- **Unit Conversion:** Raw SMAP volumetric soil moisture in $\text{m}^3/\text{m}^3$ ($0.0 \text{ to } \approx 0.5$) is converted to volumetric percentage ($0\% \text{ to } 50\%+$) by multiplying by $100.0$.
- **Spatial Resolution & Sampling:** Approximately 9-kilometer spatial resolution grid cell sampled at the farm polygon centroid (`ee.Geometry.Point([lon, lat])`).
- **Temporal Fallback:** The 10 most recent scenes are inspected sequentially to locate the latest non-masked overpass over the coordinates.

### 4.3 Weather Forecast Integration
- **API Provider:** OpenWeather 5-day / 3-hour Forecast API (`api.openweathermap.org/data/2.5/forecast`).
- **Forecast Horizon:** Exactly 48 hours (16 consecutive 3-hour slices, derived as `48 // 3 = 16`).
- **Precipitation Sum:** Sum of `item["rain"]["3h"]` across the 16 slices.
- **Validation:** Enforced via `validate_forecast_rainfall()`. Rejects non-numeric, negative, NaN, Infinite, or boolean types.

### 4.4 Data Screening, Failure Paths, and Fallbacks
- **Cloudy / Missing Satellite Data:** If no Sentinel-2 scene with $<20\%$ cloud cover is available, the location validator flags `INSUFFICIENT_SATELLITE_DATA`. The farmer is notified that recent scenes are cloud-covered and an advisory will be generated upon the next clear pass.
- **Missing SMAP Soil Moisture:** If SMAP pixels are masked or the satellite has not covered the swath, the pipeline falls back gracefully to `INCOMPLETE_AUXILIARY_DATA`. The advisory relies on Sentinel-2 canopy vigor and rainfall, noting incomplete auxiliary data in the audit log.
- **Missing Weather Data:** If OpenWeather is unavailable, the pipeline falls back to the conservative dry baseline (`rain = None`, equivalent to $<R_1$), prioritizing irrigation to protect crops.

---

## 5. Crop-Water-Stress Assessment

### 5.1 Classifier Nature: Deterministic Rule-Based Engine
> [!IMPORTANT]
> The KhetSense AI crop-water-stress classifier is **strictly a deterministic, rule-based expert decision engine**. It is **NOT** a machine learning, deep learning, or statistical regression model. There are no neural network weights, trained coefficients, training datasets, or ML model artifacts in this repository. Claims of machine learning accuracy, precision, recall, F1-score, or validated yield savings have no empirical basis in the code and must never be fabricated.

### 5.2 Decision Rules and Thresholds
The classification operates in three sequential phases:

#### Phase 1: Individual Sensor Categorization
1. **NDVI Canopy Stress (`classify_ndvi_stress`):**
   - $\text{NDVI} > 0.6$: **No Stress** (Healthy, dense vegetative canopy)
   - $0.3 \le \text{NDVI} \le 0.6$: **Mild Stress** (Moderate vegetative cover or early moisture deficit)
   - $\text{NDVI} < 0.3$: **Severe Stress** (Severe canopy senescence, sparse vegetation, or acute stress)
2. **SMAP Surface Soil Moisture Stress (`classify_soil_moisture_stress`):**
   - $\text{Soil Moisture} > 25.0\%$: **No Stress** (Adequate root-zone soil water content)
   - $15.0\% \le \text{Soil Moisture} \le 25.0\%$: **Mild Stress** (Depleted surface moisture)
   - $\text{Soil Moisture} < 15.0\%$: **Severe Stress** (Critically dry soil below wilting point)

#### Phase 2: Observed Stress Severity Synthesis (`get_more_severe`)
The system applies a **worst-case heuristic** across both remote sensing products to ensure crop safety:
$$\text{Observed Stress} = \max(\text{Severity}(\text{NDVI}), \text{Severity}(\text{SMAP}))$$
Where severity ranks: $\text{Severe Stress (3)} > \text{Mild Stress (2)} > \text{No Stress (1)} > \text{Unknown (0)}$.
*Invariance Rule:* Observed stress reflects physical sensor measurements and is **NEVER** modified by rainfall forecasts.

#### Phase 3: 48-Hour Rainfall Policy Guardrail (`apply_rainfall_guardrail`)
The 48-hour rainfall forecast is evaluated against two policy thresholds defined in `common/config.py`:
- $R_1 = 5.0\text{ mm}$: Ineffective rainfall cutoff (Dastane 1978, FAO Paper 25). Rain below 5 mm is lost to canopy interception and evaporation.
- $R_2 = 15.0\text{ mm}$: Substantial rainfall boundary (IMD moderate rain classification). Rain above 15 mm provides significant root infiltration.

| Observed Stress | 48h Forecast Rain | Recommended Action | Guardrail Triggered | Advisory Intent |
| :--- | :--- | :--- | :--- | :--- |
| **Severe Stress** | $< 5.0\text{ mm}$ (or None) | `irrigate now` | False | Immediate urgent irrigation to prevent yield loss |
| **Severe Stress** | $5.0\text{ mm} \le \text{Rain} < 15.0\text{ mm}$ | `irrigate lightly, rain may not suffice` | True | Supplementary light irrigation |
| **Severe Stress** | $\ge 15.0\text{ mm}$ | `hold, re-check after rain` | True | Hold irrigation to prevent waterlogging and runoff |
| **Mild Stress** | $< 5.0\text{ mm}$ (or None) | `schedule irrigation in 24-48h` | False | Regular scheduled irrigation |
| **Mild Stress** | $5.0\text{ mm} \le \text{Rain} < 15.0\text{ mm}$ | `delay, re-check after rain` | True | Delay irrigation and monitor soil moisture |
| **Mild Stress** | $\ge 15.0\text{ mm}$ | `hold, re-check after rain` | True | Hold irrigation; rain is expected to recharge soil |
| **No Stress** | Any amount | `no action` | False | Optimal soil and canopy conditions; no irrigation needed |

---

## 6. WhatsApp and Multilingual Voice Implementation

### 6.1 Conversational State Flow & Language Selection
- **Languages:** English (`en`), Marathi (`mr`), Hindi (`hi`).
- **Session Tracking:** Managed in PostgreSQL `registration_sessions` table with columns `(mobile_number, current_state, selected_language, in_flight_details, last_updated)`.
- **First Contact:** Unregistered phone numbers enter `AWAITING_LANGUAGE`. The bot dispatches the trilingual text prompt and voice note.
- **Language Switch:** Registered farmers can send `"language"` or `"भाषा"` at any time to switch their preferred language without re-entering farm details.

### 6.2 Text-First Delivery Architecture
All farmer-facing communications use `send_farmer_response()` in `whatsapp/registration_flow.py`:
1. **Primary Text Dispatch:** Outbound text is delivered first via Meta Graph API `POST /v21.0/{phone_number_id}/messages`.
2. **Text Delivery Verification:** If text fails, voice generation is aborted immediately, returning `text_delivery_failed`.
3. **Voice Follow-up:** If text succeeds and `ENABLE_VOICE_CHATBOT=true`, the voice pipeline is triggered.
4. **Failure Isolation:** If voice synthesis or media upload fails, the text message is **never retracted or duplicated**. The failure is logged, and a `retry_payload` containing all message parameters is preserved.

### 6.3 Voice Synthesis & Multilingual Concatenation
- **TTS Provider:** `EdgeTTSProvider` utilizes Microsoft Azure Neural voices:
  - English: `en-IN-NeerjaNeural`
  - Marathi: `mr-IN-AarohiNeural`
  - Hindi: `hi-IN-SwaraNeural`
- **Speech Text Cleaning (`clean_text_for_speech`):**
  - Emojis and decorative Unicode characters are stripped.
  - Markdown asterisks, underscores, and backticks are removed.
  - URLs are replaced with natural phrases (e.g., `"on the map location"`, `"नकाशावरील जागेवर"`, `"नक्शे वाले स्थान पर"`).
  - Punctuation and line breaks are normalized to introduce natural pauses.
- **Trilingual Onboarding Audio (`synthesize_multilingual`):**
  - The initial welcome message cannot be spoken clearly by a single language voice.
  - The script is partitioned into 3 segments: English (`en-IN-NeerjaNeural`), Marathi (`mr-IN-AarohiNeural`), and Hindi (`hi-IN-SwaraNeural`).
  - Each segment is synthesized independently, and the resulting MPEG-1 Layer III audio byte streams are concatenated into a single MP3 file. Because all three segments use the identical sample rate (24 kHz) and bit depth, standard MP3 frame concatenation is technically valid and decodes seamlessly.

### 6.4 Audio Upload and Dispatch to Meta WhatsApp API
1. **Media Upload:** MP3 bytes/file are posted to `POST https://graph.facebook.com/v21.0/{phone_number_id}/media` with `messaging_product="whatsapp"` and `type="audio/mpeg"`. Meta returns a `media_id`.
2. **Message Dispatch:** Audio message payload `{ "messaging_product": "whatsapp", "to": to, "type": "audio", "audio": { "id": media_id } }` is posted to `POST https://graph.facebook.com/v21.0/{phone_number_id}/messages`.
3. **Transient Retry:** Bounded single retry (`max_retries=1`) on network timeout.

### 6.5 Investigation & Resolution of Edge TTS HTTP 403 Handshake Failure
- **Observed Issue:** In recent tests, calls to `edge-tts` failed with:
  `WSServerHandshakeError: 403, message='Invalid response status'` from `wss://speech.platform.bing.com/consumer/speech/synthesize/readaloud/edge/v1`.
- **Root Cause Analysis:** Microsoft updated the Edge Read-Aloud service authentication protocol. Older versions of `edge-tts` transmitted `Sec-MS-GEC` version 1 (`1-143.0.3650.75`), which Microsoft deprecated and blocked with HTTP 403. The updated protocol requires `Sec-MS-GEC` Version 2 (`2-143.0.3650.75`) featuring dual CS64 and SHA256 client token digests.
- **Verification of Fix:** The dependency was upgraded and pinned to `edge-tts==7.3.1` in `requirements.txt` and `.venv`.
- **Empirical Validation:** Isolated live synthesis tests confirmed that `edge-tts==7.3.1` successfully synthesized all voices:
  - Hindi (`hi-IN-SwaraNeural`): 12,096 bytes generated.
  - Marathi (`mr-IN-AarohiNeural`): 11,520 bytes generated.
  - English (`en-IN-NeerjaNeural`): 11,520 bytes generated.
  - Trilingual concatenated onboarding audio: 40,896 bytes generated.
  The WebSocket 403 error is confirmed resolved in the installed virtual environment.

---

## 7. Location Handling and Security

### 7.1 Location Submission Modalities
The system supports 4 flexible location submission methods:
1. **WhatsApp GPS Pin:** Native WhatsApp location message containing `latitude` and `longitude` fields.
2. **Direct Google Maps URL:** URLs containing query coordinates (`?q=19.34,74.31`, `?ll=19.34,74.31`, `/place/19.34,74.31`) or viewport coordinates (`/@19.34,74.31,15z`).
3. **Google Maps Shortlink:** Shortened links (`https://maps.app.goo.gl/...` or `https://goo.gl/maps/...`).
4. **Raw Coordinate Strings:** Plain text coordinate pairs (e.g., `19.34634, 74.31100`, `Lat: 19.34634, Lon: 74.31100`, or `19.34634 N, 74.31100 E`).

### 7.2 Strict Anti-SSRF Protections for Shortlinks
To prevent Server-Side Request Forgery (SSRF), internal network scanning, and DNS rebinding attacks when resolving shortlinks, `common/utils.py` enforces a defense-in-depth security model:
1. **Scheme Validation:** Strict `https://` only; plain `http://`, `file://`, `ftp://`, or `gopher://` are rejected.
2. **Hostname Whitelisting:**
   - Initial Shortlink Hosts: Strictly `maps.app.goo.gl` or `goo.gl` (with `/maps` path prefix).
   - Redirect Target Hosts: Restricted to Google Maps domains (`maps.google.com`, `www.google.com`, `maps.app.goo.gl`, `goo.gl`).
3. **Port & Credential Validation:** Only standard HTTPS port 443 is permitted. URLs with embedded credentials (`user:pass@host`) are immediately rejected.
4. **Public IP & DNS Enforcement:**
   - Every target hostname is resolved via `socket.getaddrinfo`.
   - All returned IP addresses are validated using Python's `ipaddress` module.
   - The connection is aborted if any IP resolves to loopback (`127.0.0.0/8`, `::1`), private RFC1918 (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), link-local / cloud metadata (`169.254.169.254`, `fe80::/10`), multicast, or IPv4-mapped IPv6 (`::ffff:...`).
5. **Pre-Extraction Destination Validation:** Coordinates in HTTP `Location` redirect headers are **never extracted or trusted** until the redirect destination URL has fully passed all destination safety checks.
6. **Concurrency-Safe Connection Pinning:**
   - The implementation **avoids process-wide monkeypatching** of `socket.getaddrinfo`.
   - Instead, a custom `_PinnedHTTPAdapter` and `_PinnedHTTPSConnectionPool` inject the verified public IP into `urllib3.connection.HTTPSConnection._dns_host` while preserving `server_hostname` for TLS SNI and valid certificate verification.
7. **Hop Limits & Loop Detection:** Bounded to a maximum of 3 redirect hops, maintaining a `visited` set to detect and abort redirect loops.

---

## 8. Database Schema & Data Models

The persistence layer is implemented in PostgreSQL with PostGIS extensions:
1. `farms`: Primary agricultural registry storing farmer profiles, crop type, acreage, boundary polygons, centroid coordinates, and registration provenance:
   - `polygon`: `geometry(Polygon, 4326)`
   - `boundary_source`: `'pin_buffered'` or `'polygon_drawn'`
   - `area_source`: `'farmer_reported'` or `'derived'`
2. `registration_sessions`: Active conversational state tracking:
   - `mobile_number`: Unique E.164 phone number
   - `current_state`: Active state machine state
   - `preferred_language`: Selected language (`en`, `mr`, `hi`)
   - `in_flight_details`: JSONB structure storing partial inputs (name, crop, acreage, candidate location)
3. `advisories`: Historical log of all generated irrigation advisories:
   - Sensor inputs: `ndvi`, `ndwi`, `soil_moisture`, `rainfall_48h`
   - Decision audit: `observed_stress`, `recommended_action`, `guardrail_triggered`
   - Satellite metadata: `sentinel_scene_date`, `smap_obs_date`
   - Agricultural validation: `validation_status`, `land_cover_class`
4. `advisory_validation_audit`: Dedicated audit trail for suitability screening outcomes (e.g., `LIKELY_URBAN`, `BARREN_OR_UNCERTAIN`).

---

## 9. Configuration and Operational Readiness

### 9.1 Required Environment Variables
The application requires the following environment variables (defined in `.env.example`):
- `DATABASE_URL`: PostgreSQL connection URI with PostGIS.
- `WHATSAPP_TOKEN`: Meta WhatsApp Cloud API System User access token.
- `WHATSAPP_PHONE_NUMBER_ID`: Meta Graph API Phone Number ID.
- `WHATSAPP_VERIFY_TOKEN`: Secret string for Meta Webhook verification handshake.
- `OPENWEATHER_API_KEY`: OpenWeather API authentication key.
- `ENABLE_VOICE_CHATBOT`: Boolean feature flag (`true` or `false`).
- `TTS_PROVIDER`: Text-to-Speech engine selection (`edge`, `google`, or `mock`).
- `GOOGLE_APPLICATION_CREDENTIALS`: Path to Google Cloud service account JSON (for GEE and optional Google Cloud TTS).

### 9.2 Operational Dependencies & Tunnel Requirements
- **Inbound Tunneling:** Because Meta requires public HTTPS endpoints for webhook callbacks, local execution requires a reverse proxy / tunnel (e.g., `ngrok`, `cloudflared`, or a public VPS).
- **External Services:** Active Internet connectivity to `graph.facebook.com`, `earthengine.googleapis.com`, `cmr.earthdata.nasa.gov`, `api.openweathermap.org`, and Microsoft Azure Speech WebSockets.

---

## 10. Known Issues, Limitations & Technical Debt

| # | Issue Description | Source Evidence | Severity | Status | Impact & Recommended Next Step |
| :- | :--- | :--- | :--- | :--- | :--- |
| **1** | **SMAP Spatial Resolution vs. Farm Area** | `pipeline/test_pipeline.py:521-526` | Medium | Inherent Limitation | SMAP 9-km radiometer resolution samples regional soil moisture, not field-scale moisture. Recommend investigating 1-km downscaled or Sentinel-1 SAR soil moisture products in future phases. |
| **2** | **Test Assertion Drift with Voice Flag** | `tests/test_registration_flow.py:3141, 4077` | Medium | Confirmed | 2 tests assert `mock_get_tts.assert_not_called()` assuming `ENABLE_VOICE_CHATBOT=false`. When the flag is `true`, these tests fail. Recommend parametrizing tests with `@patch.dict(os.environ, {"ENABLE_VOICE_CHATBOT": "false"})`. |
| **3** | **Obsolete Test Assertion for Location Notice Voice** | `tests/test_voice_advisory.py:912` | Low | Confirmed | Older test `test_run_pipeline_for_farm_unsuitable_location_withholds_voice` asserts voice sender not called, but newer requirement routes validation warning notices through voice. Recommend updating test assertion to match the new requirement. |
| **4** | **Unauthenticated NASA CMR vs. Protected DAAC HDF5** | `pipeline/test_pipeline.py:468-506` | Low | Confirmed | CMR metadata search is unauthenticated, while downloading raw `.h5` files requires Earthdata credentials. Currently, SMAP data is accessed via Google Earth Engine (`NASA/SMAP/SPL3SMP_E/006`), making direct DAAC downloads redundant. |
| **5** | **Lack of Dynamic Crop Coefficients ($K_c$)** | `pipeline/classifier.py:25-56` | Medium | Technical Debt | Decision rules apply identical NDVI and soil moisture thresholds across all crops. Future releases should incorporate FAO-56 crop growth stages and crop coefficient ($K_c$) tables. |

---

## 11. Implementation Status Matrix

| Component / Feature | Status | Source Evidence | Operational Limitations | Recommended Next Step |
| :--- | :--- | :--- | :--- | :--- |
| **FastAPI Webhook Server** | **Implemented** | `webhook_server.py:1-120` | Requires public HTTPS tunnel for Meta webhooks | Deploy behind production ASGI reverse proxy |
| **Multilingual Chatbot (EN/MR/HI)** | **Implemented** | `whatsapp/messages.py`, `whatsapp/registration_flow.py` | Marathi and Hindi localized prompts active | Ongoing field linguistic validation with farmers |
| **Location Pin Parsing** | **Implemented** | `whatsapp/registration_flow.py:320-350` | Requires farmer to share GPS location | Maintain conversational re-prompt on invalid pins |
| **Google Maps URL & Shortlink Parser**| **Implemented** | `common/utils.py:250-335, 581-612` | Dependent on Google Maps URL schema stability | Maintain test coverage across URL formats |
| **Anti-SSRF & DNS Pinning** | **Implemented** | `common/utils.py:337-470` | Connection pinning requires `requests` and `urllib3` | Maintain strict host whitelist |
| **Agricultural Suitability Validator**| **Implemented** | `pipeline/location_validator.py:133-320` | ESA WorldCover is static (2021) | Incorporate near-real-time Dynamic World queries |
| **Sentinel-2 NDVI / NDWI Engine** | **Implemented** | `pipeline/test_pipeline.py:410-458` | Blocked by persistent cloud cover (>20%) | Implement temporal interpolation for cloudy scenes |
| **NASA SMAP Soil Moisture Engine** | **Implemented** | `pipeline/test_pipeline.py:517-594` | Coarse 9-km spatial resolution | Explore Sentinel-1 SAR surface moisture |
| **OpenWeather 48h Rain Forecast** | **Implemented** | `pipeline/test_pipeline.py:596-625` | 3-hour forecast model accuracy limits | Integrate IMD gridded numerical weather forecasts |
| **Rule-Based Decision Classifier** | **Implemented** | `pipeline/classifier.py:25-175` | Deterministic expert rules, not trained ML | Calibrate thresholds against field soil probes |
| **Edge TTS Multilingual Voice** | **Implemented** | `pipeline/tts_provider.py:465-569` | Requires external Microsoft WebSocket service | Maintain Google Cloud TTS fallback |
| **Trilingual Welcome Audio** | **Implemented** | `whatsapp/registration_flow.py:685-688` | MP3 frame concatenation relies on identical format | Verified functional across EN/MR/HI voices |
| **Text-First Voice Dispatcher** | **Implemented** | `whatsapp/registration_flow.py:673-798` | Controlled by `ENABLE_VOICE_CHATBOT` | Ready for live controlled test |
| **Audio-Only Retry Engine** | **Implemented** | `whatsapp/registration_flow.py:800-820` | In-memory retry payload; no DB persistence | Add persistent queue in future release |

---

## 12. Overall Assessment and Production Readiness

KhetSense AI possesses a robust, well-architected software foundation. The conversational state machine, Anti-SSRF location parser, remote sensing data retrieval pipeline, and text-first multilingual voice dispatcher are fully implemented and verified in source code. 

**Readiness Verdict:**
- **Controlled Live Testing:** **READY**. The system is fully prepared for a controlled live WhatsApp test with the registered Meta test recipient.
- **Production Scaled Deployment:** **CONDITIONALLY READY**. Requires:
  1. Resolving the 3 test assertion discrepancies under `ENABLE_VOICE_CHATBOT=true`.
  2. Deploying a persistent database queue for failed audio retries.
  3. Calibrating crop-specific stress thresholds ($K_c$) with regional agronomic institutions.
