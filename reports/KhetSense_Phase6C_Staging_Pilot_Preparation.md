# KhetSense AI: Phase 6C — Controlled Staging Pilot Preparation Report

**Author:** KhetSense AI Senior Software Auditor, ML Engineer & Agricultural Data Scientist  
**Date:** October 19, 2026  
**Status:** Preparation Complete — Staging Validation Protocol Established  
**Prior Audits Reviewed:**
- Phase 5C Safety Audit: [KhetSense_Phase5C_PreDeployment_Safety_Audit.md](file:///c:/Users/NIDEEKSHA/Documents/DEEKSHA/MASTERS/Research%20Project/khetsense/reports/KhetSense_Phase5C_PreDeployment_Safety_Audit.md)
- Phase 5D Remediation Report: [KhetSense_Phase5D_Remediation_and_Regression_Report.md](file:///c:/Users/NIDEEKSHA/Documents/DEEKSHA/MASTERS/Research%20Project/khetsense/reports/KhetSense_Phase5D_Remediation_and_Regression_Report.md)
- Phase 6A Dry-Run Report: [KhetSense_Phase6A_Local_Dry_Run_Report.md](file:///c:/Users/NIDEEKSHA/Documents/DEEKSHA/MASTERS/Research%20Project/khetsense/reports/KhetSense_Phase6A_Local_Dry_Run_Report.md)
- Phase 6B Staging Readiness Report: [KhetSense_Phase6B_Staging_Readiness_Report.md](file:///c:/Users/NIDEEKSHA/Documents/DEEKSHA/MASTERS/Research%20Project/khetsense/reports/KhetSense_Phase6B_Staging_Readiness_Report.md)

---

## 1. Executive Summary & Purpose

Following the successful execution of the local end-to-end dry run (Phase 6A) and the live read-only satellite/weather validation (Phase 6B), **Phase 6C: Controlled Staging Pilot Preparation** establishes the formal architectural, operational, and agronomic protocol required before executing a real-farm staging pilot.

This phase is strictly limited to:
1. Environment and dependency audit.
2. Database migration inspection and compatibility review.
3. Staging architecture design with strict non-interference and safe default controls.
4. Real-farm validation protocol establishing the essential distinction between software execution and agronomic ground truth.
5. Formulation of a rigorous GO/NO-GO staging checklist.

### Absolute Constraints Maintained During Phase 6C
- **ZERO packages installed.**
- **ZERO modifications to `.env`, credentials, source code, models, or database schemas.**
- **ZERO database connections or migration executions.**
- **ZERO WhatsApp messages sent or outbound messaging endpoints called.**
- **ZERO deployment or live shadow telemetry activation.**
- **Full preservation of all pre-existing uncommitted changes across the working tree.**

---

## 2. Environment & Dependency Audit (Task 1)

### 2.1 Python Runtime vs. ML Benchmark Environment
The host system maintains two separate Python 3.13.5 environments by deliberate architectural isolation:

```
+-----------------------------------------------------------------------------------+
| Host System (Windows 11 x64, Python 3.13.5)                                       |
+-------------------------------------------------+---------------------------------+
| Runtime Environment: .venv                      | Benchmark Environment: C:\Python313 |
| (Operational Application Service)               | (Offline ML Research & Tuning)  |
+-------------------------------------------------+---------------------------------+
| - FastAPI 0.141.1, Starlette 1.7.0, uvicorn     | - scikit-learn 1.8.0            |
| - earthengine-api 1.7.42                        | - joblib 1.5.3                  |
| - psycopg2-binary 2.9.13                        | - pandas 2.3.3                  |
| - edge-tts 7.3.1 (Azure Neural Voices)          | - numpy 2.2.6                   |
| - requests 2.34.2, python-dotenv 1.2.3          | - scipy 1.16.3                  |
| - pydantic 2.13.5                               | - matplotlib, seaborn, torch    |
| (NO scikit-learn / joblib / pandas / numpy)     | (NO fastapi, earthengine, psycopg2) |
+-------------------------------------------------+---------------------------------+
```

### 2.2 Dependency Requirements for Staging Execution
To run KhetSense in staging with operational ML shadow telemetry:

1. **Active Core Pipeline (Operational):**
   - `fastapi`, `starlette`, `uvicorn` (Webhook server & Meta callback handling)
   - `earthengine-api` (Copernicus Sentinel-2 & NASA SMAP data access via Google Cloud Service Account)
   - `psycopg2-binary` (PostgreSQL / Supabase PostGIS connection pool)
   - `requests` (OpenWeather forecast HTTP client)
   - `edge-tts` (Trilingual voice advisory synthesis)
   - `python-dotenv`, `pydantic` (Configuration & payload validation)
   *Status in `.venv`:* **Fully Installed & Verified (Phase 6A & 6B)**

2. **Candidate ML Shadow Engine (`pipeline/ml_shadow_engine.py`):**
   - `joblib >= 1.3.0` (Loading serialized `rf_water_stress_pipeline.joblib` and `lr_water_stress_pipeline.joblib`)
   - `scikit-learn >= 1.4.0` (Pipeline execution, `SimpleImputer`, `StandardScaler`, `RandomForestClassifier`, `LogisticRegression`)
   - `numpy >= 1.24.0` (Vector operations, non-finite float handling)
   *Status in `.venv`:* **Dormant by design.** When absent, the shadow engine logs `Shadow ML engine dormant: ML dependencies unavailable` and outputs `DEPENDENCY_UNAVAILABLE` telemetry without throwing an exception or blocking the pipeline.
   *Status in `C:\Python313`:* **Installed and Verified.** Real model inference loads and executes in $< 20\text{ ms}$.

3. **Staging Recommendation:**
   When authorized to deploy staging, `scikit-learn`, `joblib`, and `numpy` should be installed directly into the application's isolated runtime virtual environment (`.venv`), consolidating the dual-environment setup into a single, cohesive staging runtime.

### 2.3 Environment Variable Control Matrix (Zero Secret Exposure)
The application's behavioral modes are controlled by environment variables loaded from `.env`. The table below documents their operational control semantics without exposing secret values:

| Variable Name | Sensitive | Current Staging Configuration | Safety Control Function |
| :--- | :---: | :---: | :--- |
| `WHATSAPP_TOKEN` | YES | `[Configured]` | If unset or empty, outbound messaging automatically switches to **MOCK MODE** (logs simulated send, zero HTTP calls). |
| `WHATSAPP_PHONE_NUMBER_ID` | YES | `[Configured]` | Required for Meta Graph API v21.0 outbound dispatch; mocked when unset. |
| `WHATSAPP_WEBHOOK_VERIFY_TOKEN` | YES | `[Configured]` | Verified during Meta's `GET /webhook` handshake. Unmatched tokens return HTTP 403 Forbidden. |
| `DATABASE_URL` | YES | `[Configured]` | PostgreSQL connection string. In tests and safe staging, setting `db_url=None` enforces zero live database access. |
| `OPENWEATHER_API_KEY` | YES | `[Configured]` | OpenWeather 5-day / 3-hour precipitation forecast API key. |
| `ENABLE_VOICE_ADVISORY` | NO | `false` | Controls whether automated voice advisory MP3s are uploaded and sent upon advisory calculation. |
| `ENABLE_VOICE_CHATBOT` | NO | `false` | Controls whether voice audio notes accompany conversational chatbot responses. |
| `TTS_PROVIDER` | NO | `edge_tts` | Selects audio provider: `mock`, `edge_tts`, or `google_cloud`. |
| `ML_SHADOW_TIMEOUT_SECONDS` | NO | `0.5` | Bounded execution timeout for ML inference (enforces caller return in $\le 500\text{ ms}$). |
| `ML_SHADOW_MAX_WORKERS` | NO | `2` | Persistent thread pool size for background ML inference. |
| `ML_SHADOW_MAX_QUEUE` | NO | `4` | Semaphore bound on pending shadow tasks; sheds load immediately when full. |

---

## 3. Database Migration Review & Schema Compatibility (Task 2)

### 3.1 Migration 006 Schema Inspection
Migration `migrations/006_ml_shadow_evaluation.sql` provisions the dedicated shadow telemetry table:

```sql
CREATE TABLE IF NOT EXISTS ml_shadow_advisories (
    id BIGSERIAL PRIMARY KEY,
    farm_id BIGINT NOT NULL REFERENCES farms(id) ON DELETE CASCADE,
    advisory_id BIGINT REFERENCES advisories(id) ON DELETE SET NULL,
    crop_name VARCHAR(64) NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Active Rule Engine Outputs (Production Authority)
    rule_observed_stress VARCHAR(32) NOT NULL,
    rule_recommended_action VARCHAR(64) NOT NULL,
    rule_guardrail_triggered BOOLEAN NOT NULL DEFAULT FALSE,
    
    -- Candidate ML Model 1: Random Forest Classifier (Calibrated Threshold T=0.33)
    rf_predicted_class VARCHAR(32),
    rf_prob_no_stress DOUBLE PRECISION,
    rf_prob_mild_stress DOUBLE PRECISION,
    rf_prob_severe_stress DOUBLE PRECISION,
    rf_model_version VARCHAR(64),
    
    -- Candidate ML Model 2: Regularized Logistic Regression (Balanced Multi-Class)
    lr_predicted_class VARCHAR(32),
    lr_prob_no_stress DOUBLE PRECISION,
    lr_prob_mild_stress DOUBLE PRECISION,
    lr_prob_severe_stress DOUBLE PRECISION,
    lr_model_version VARCHAR(64),
    
    -- Multi-Sensor Feature Snapshot
    feat_s2_ndvi DOUBLE PRECISION NULL,
    feat_s2_ndwi DOUBLE PRECISION NULL,
    feat_s2_ndre DOUBLE PRECISION NULL,
    feat_s2_msavi DOUBLE PRECISION NULL,
    feat_smap_sm_pct DOUBLE PRECISION NULL,
    feat_era5_precip_season_mm DOUBLE PRECISION NULL,
    feat_era5_temp_mean_c DOUBLE PRECISION NULL,
    feat_era5_temp_max_c DOUBLE PRECISION NULL,
    feat_era5_vpd_mean_kpa DOUBLE PRECISION NULL,
    
    -- Diagnostics & Telemetry
    execution_status VARCHAR(64) NOT NULL DEFAULT 'SUCCESS',
    is_disagreement BOOLEAN NOT NULL DEFAULT FALSE,
    severe_disagreement BOOLEAN NOT NULL DEFAULT FALSE,
    missing_sensor_flag VARCHAR(128) NULL,
    inference_latency_ms DOUBLE PRECISION NULL,

    -- Strict Idempotency Constraint
    CONSTRAINT uq_ml_shadow_advisory_id UNIQUE (advisory_id)
);
```

### 3.2 Compatibility & Idempotency Analysis
1. **Zero Table Alterations to Production Tables:** `advisories`, `farms`, and `farmer_sessions` are completely untouched. The migration only creates a new, standalone table (`ml_shadow_advisories`).
2. **Referential Integrity:**
   - `farm_id REFERENCES farms(id) ON DELETE CASCADE`: Safe cleanup if a test farm is deleted.
   - `advisory_id REFERENCES advisories(id) ON DELETE SET NULL`: Prevents shadow records from blocking advisory deletions.
3. **Idempotency Guarantee:**
   - The unique constraint `uq_ml_shadow_advisory_id UNIQUE (advisory_id)` guarantees that exactly one shadow evaluation record exists per advisory run.
   - In `pipeline/ml_shadow_engine.py::persist_shadow_record`, queries use:
     ```sql
     INSERT INTO ml_shadow_advisories (...) VALUES (...)
     ON CONFLICT (advisory_id) DO UPDATE SET
         crop_name = EXCLUDED.crop_name,
         rule_observed_stress = EXCLUDED.rule_observed_stress,
         ...
     ```
   - Retried deliveries, status queries, or duplicate webhooks update telemetry rather than generating duplicate rows.
4. **Indexes:** Five targeted indexes (`idx_ml_shadow_farm_created`, `idx_ml_shadow_advisory_id`, `idx_ml_shadow_crop`, `idx_ml_shadow_disagreement`, `idx_ml_shadow_rf_version`) support rapid offline querying of disagreement rates, latency, and sensor availability.

### 3.3 Prerequisites Before Migration Application
Before applying Migration 006 in staging:
- Ensure migrations `001_whatsapp_registration.sql` and `003_rainfall_policy_and_advisory_provenance.sql` are active on the target database (establishing `farms` and `advisories` tables).
- Verify database user has `CREATE TABLE`, `CREATE INDEX`, and `COMMENT` privileges on the `public` schema.
- **Safety Restriction:** Migration 006 must **NOT** be executed until formal deployment authorization is granted.

---

## 4. Proposed Staging Architecture (Task 3)

### 4.1 Architectural Invariant: Observational Shadow Decoupling
In the staging pilot, ML models run exclusively in **observational shadow mode**. The diagram below details the execution path:

```
                      Farmer Location & Crop Input
                                    |
                                    v
                 +--------------------------------------+
                 | Location & Land Cover Validator      |
                 | (Cropland vs Urban vs Barren/Fallow) |
                 +--------------------------------------+
                                    | (Suitable Farm)
                                    v
                 +--------------------------------------+
                 | Data Retrieval: Sentinel-2 & SMAP    |
                 | & OpenWeather 48h Forecast           |
                 +--------------------------------------+
                                    |
                                    v
                 +--------------------------------------+
                 | Deterministic Stress Classifier      |
                 | (NDVI + SMAP Fusion: Worst-Case)     |
                 +--------------------------------------+
                                    |
                                    v
                 +--------------------------------------+
                 | Multi-Tier Rainfall Guardrails       |
                 | (R1 = 5.0mm, R2 = 15.0mm)            |
                 +--------------------------------------+
                                    |
                                    v
                 +--------------------------------------+
                 | Active Production Advisory Created   |
                 | (Saved to DB advisories table)       |
                 +--------------------------------------+
                               /         \
          (Farmer Communication Path)    (Observational Shadow Path)
                    /                               \
                   v                                 v
   +-------------------------------+   +------------------------------------+
   | Multilingual Advisory Card    |   | ml_shadow_engine.py                |
   | & Neural TTS Voice Generation |   | - Background ThreadPool (workers=2)|
   | (English, Marathi, Hindi)     |   | - 500ms Hard Timeout               |
   +-------------------------------+   | - SimpleImputer + StandardScaler   |
                   |                   | - Random Forest (T=0.33) & LogReg  |
                   v                   +------------------------------------+
   +-------------------------------+                     |
   | Guarded Outbound WhatsApp     |                     v
   | (Mock Mode by Default)        |   +------------------------------------+
   +-------------------------------+   | Disagreement & Latency Telemetry   |
                                       | Saved to ml_shadow_advisories      |
                                       +------------------------------------+
```

### 4.2 Core Safety & Decoupling Guarantees
1. **Rule Authority:** Farmer-facing advisories are formulated strictly by `classify_ndvi_stress`, `classify_soil_moisture_stress`, and `apply_rainfall_guardrail`. The candidate ML predictions are never surfaced in farmer-facing text cards, voice notes, or status responses.
2. **Crash & Timeout Immunity:** ML shadow inference runs inside a guarded `try...except` block in `pipeline/test_pipeline.py` (Line 905). Unhandled exceptions or timeouts in ML code cannot halt, delay, or alter the farmer's advisory.
3. **Staging Data Isolation:**
   - Dedicated staging farm records are assigned designated ID ranges ($> 10000$) or flagged with phone prefixes (`+919999900000` through `+919999900099`).
   - Staging records never mix with historical production analytics.
4. **Default Outbound WhatsApp Suppression:**
   - In staging, `WHATSAPP_TOKEN` remains unset or set to dummy credentials by default, routing all outbound messaging to the validated console mock (`[WHATSAPP MOCK]`).
   - Live WhatsApp delivery is enabled only for explicit whitelist farmer phone numbers with prior consent.
5. **Observability Tracking:**
   Every shadow record logs:
   - Exact model versions (`rf_v1_dccd55f0e860a61d`, `lr_v1_6a5d1014ff1685ac`)
   - Normalized crop name (`Wheat`, `Cotton`, `Soybean`, etc.)
   - Full sensor vector snapshot at inference time
   - Disagreement flags (`is_disagreement`, `severe_disagreement`)
   - Sensor missingness flags (`missing_sensor_flag`)
   - Wall-clock inference latency (`inference_latency_ms`)

---

## 5. Real-Farm Validation Protocol & Agronomic Ground-Truth Framework (Task 4)

### 5.1 The Tripartite Evaluation Framework
An agricultural AI system cannot be declared accurate based on software execution alone. The validation protocol explicitly establishes three independent levels of verification:

```
+-----------------------------------------------------------------------------------+
| LEVEL 1: DATA & SENSOR FEASIBILITY                                                |
| - Copernicus Sentinel-2 Level-2A GEE query returns valid reflectance bands.       |
| - NASA SMAP 9-km L3 radiometer returns non-null volumetric moisture.              |
| - OpenWeather API returns 48-hour precipitation forecast without HTTP errors.     |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
| LEVEL 2: SOFTWARE EXECUTION & POLICY VERIFICATION                                 |
| - System extracts coordinates, scales 2.5-acre polygon, and executes classifiers. |
| - Worst-case fusion and multi-tier rainfall guardrails trigger correctly.         |
| - Multilingual text and voice scripts format properly without technical jargon.   |
| - ML shadow engine evaluates within 500ms timeout; idempotency constraint holds.  |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
| LEVEL 3: AGRONOMIC GROUND-TRUTH VALIDITY (FIELD REALITY)                           |
| - Does the 10m Sentinel-2 pixel reflect actual crop canopy transpiration status,  |
|   or is it confounded by soil background, row spacing, or weed patches?          |
| - Does the coarse 9-km SMAP cell correlate with root-zone moisture (0-30 cm)     |
|   on this specific 2-acre field with its local soil texture and topography?       |
| - Is the irrigation timing agronomically sound for this specific crop growth      |
|   stage (e.g. Wheat CRI vs. Flowering) in this specific agro-climatic zone?      |
+-----------------------------------------------------------------------------------+
```

> [!CAUTION]
> **Domain Transfer Warning:**  
> The existing candidate ML models (Random Forest and Logistic Regression) were trained on the **CSISA Eastern Indo-Gangetic Plains (Bihar, Eastern UP, Odisha) Rabi Wheat Dataset (2018–2022)**.  
> 
> Applying these models to **Maharashtra farms (Western/Central Deccan Plateau)** or to non-wheat crops (Cotton, Sugarcane, Soybean) represents an **unvalidated geographical and agronomic domain shift**:
> - Differences in soil taxonomy (Alluvial soils in Bihar vs. Deep Vertisols / Black Cotton Soils in Maharashtra).
> - Differences in evaporative demand (Vapor Pressure Deficit and temperature profiles).
> - Differences in irrigation access (tube well inundation vs. canal/drip systems).
>
> Therefore, in the staging pilot, ML predictions must be evaluated purely as **observational research telemetry**, not as validated crop stress classifications.

---

### 5.2 Real-Farm Site Selection & Verification Protocol

#### Step 1: Farm Location Selection
- **Target Agro-Climatic Zone:** Ahmednagar / Pune / Nashik agricultural belt, Maharashtra.
- **Minimum Plot Size:** $\ge 1.0\text{ acre}$ ($4,047\text{ m}^2$, corresponding to $\ge 40$ contiguous Sentinel-2 10m pixels) to avoid edge-pixel contamination.
- **Topography:** Flat to gently undulating ($< 3\%$ slope) to avoid radar terrain shadows or severe optical shading.
- **Land Cover Verification:** Centroid must verify as ESA WorldCover Class 40 (Cropland) via `validate_agricultural_location`. Urban, forest, wetland, or barren centroids are excluded.

#### Step 2: Crop & Phenology Ground-Truthing
Before satellite observation matching, record on-farm metadata:
- **Crop Variety & Sowing Date:** Exact planting date to establish Days After Sowing (DAS).
- **Phenological Growth Stage:**
  - For Wheat: Crown Root Initiation (CRI, 21–25 DAS), Tillering, Jointing, Flowering, Milk, or Dough stage.
  - For Cotton: Vegetative, Square formation, Flowering, Boll development.
- **Irrigation History:** Date, duration, and method (flood, furrow, drip) of the most recent irrigation event.
- **Soil Classification:** Black cotton vertisol, sandy loam, or medium red soil.

#### Step 3: Satellite & Weather Observation Alignment
- **Sentinel-2 Overpass Matching:**
  - Query Copernicus Sentinel-2 MSI overpass schedule over the farm polygon.
  - Require scene cloud cover $< 20.0\%$ over the specific tile and $< 5.0\%$ over the farm polygon.
  - Reject scenes contaminated by thin cirrus or haze.
- **SMAP Observation Matching:**
  - Check SMAP ascending (6 PM) and descending (6 AM) overpasses within $\pm 48\text{ hours}$ of the optical scene.
  - Record whether the overpass was off-swath or valid.
- **Weather Station Cross-Check:**
  - Record OpenWeather 48h forecast.
  - If feasible, cross-reference with India Meteorological Department (IMD) district-level agro-meteorological bulletins.

#### Step 4: Physical Soil & Crop Moisture Verification
To evaluate Level 3 agronomic ground truth, field observations must be collected within $\pm 12\text{ hours}$ of the satellite overpass:
1. **Soil Moisture Feel-and-Appearance or TDR Probe:**
   - Sample at $0\text{–}15\text{ cm}$ (topsoil) and $15\text{–}30\text{ cm}$ (effective root zone).
   - Classify into soil moisture status: *Saturated*, *Field Capacity / Adequate*, *Depleted / Moderate Stress*, or *Severe Deficit / Wilting Point*.
2. **Visual Crop Stress Indicators:**
   - Afternoon leaf rolling / wilting.
   - Canopy color dulling (loss of bright green luster).
   - Stunted vegetative elongation relative to irrigated control plots.

#### Step 5: Comparative Disagreement Analysis
For every staging assessment, log the comparative matrix:

$$\Delta_{\text{Rule-ML}} = \text{rule\_observed\_stress} \oplus \text{rf\_predicted\_class}$$

$$\Delta_{\text{Rule-Field}} = \text{rule\_observed\_stress} \oplus \text{ground\_truth\_field\_status}$$

$$\Delta_{\text{ML-Field}} = \text{rf\_predicted\_class} \oplus \text{ground\_truth\_field\_status}$$

Analyze whether:
- The rule engine correctly identified field-verified stress.
- The rainfall guardrail appropriately prevented unnecessary irrigation before rain events.
- The ML model agreed with or contradicted field observations.

---

## 6. Security and Safety Controls Checklist

| Control ID | Category | Implementation Mechanism | Staging Verification Standard |
| :--- | :--- | :--- | :--- |
| **SEC-01** | WhatsApp Protection | Unset `WHATSAPP_TOKEN` / mock mode fallback in `whatsapp/registration_flow.py`. | Verified: 0 live HTTP POST requests to `graph.facebook.com`. |
| **SEC-02** | Database Isolation | Enforce `db_url=None` or dedicated staging database URL. | Verified: Production `farms` and `advisories` tables have 0 staging inserts. |
| **SEC-03** | Concurrency Bounding | Persistent `ThreadPoolExecutor(max_workers=2)` + semaphore queue bound (`4`). | Verified: Concurrency test sheds excess load in $< 0.05\text{ ms}$; no thread leaks. |
| **SEC-04** | Inference Timeout | Strict $0.50\text{s}$ timeout with `FutureTimeoutError` fallback. | Verified: Active advisory continues unimpeded if ML inference delays. |
| **SEC-05** | Credential Secrecy | Service-account key in `credentials/ee-key.json` restricted by OS file permissions. | Verified: Zero secrets printed to console or logs; API keys masked in outputs. |
| **SEC-06** | PII Protection | Phone numbers masked to last 4 digits (`mask_phone`) across all application logs. | Verified: Logs print `...+3210` instead of raw phone numbers. |
| **SEC-07** | Non-Finite Floats | `_sanitize_float` coerces `NaN`, `+inf`, `-inf` to `None`/`np.nan`. | Verified: Zero `ValueError` or crashes during model preprocessing. |
| **SEC-08** | SSRF Defense | Google Maps shortlink resolver checks initial host, redirect host, and public IP resolution. | Verified: Resolves to private/loopback IPs are blocked prior to HTTP fetch. |

---

## 7. Staging Pilot GO / NO-GO Decision Checklist

| Checkpoint | Requirement | Current Status | Verdict |
| :--- | :--- | :---: | :---: |
| **1. Unit Test Suite** | 100% pass rate across core registration and voice tests. | 253/253 tests pass (`test_registration_flow`, `test_voice_advisory`, `test_ml_shadow`, `test_phase6a_dry_run`). | **GO** |
| **2. GEE Authentication** | Valid service-account authentication without interactive prompt. | Authenticated via `credentials/ee-key.json` to project `khetsense-ai`. | **GO** |
| **3. Live Sentinel-2** | Live retrieval over Indian agricultural coordinates. | Verified: 2026-10-15 scene retrieved, NDVI $0.2725$, cloud $0.78\%$. | **GO** |
| **4. Live SMAP & Weather** | Live soil moisture and 48h forecast retrieval. | Verified: SMAP $20.38\%$, OpenWeather $0.0\text{ mm}$ rain. | **GO** |
| **5. Migration 006** | Idempotent schema definition with unique constraint on `advisory_id`. | Validated: `migrations/006_ml_shadow_evaluation.sql` ready for application. | **GO** |
| **6. Observational Decoupling** | Farmer-facing advisories 100% rule-driven; ML shadow non-blocking. | Validated: Rule engine and guardrails remain sole authority. | **GO** |
| **7. ML Environment Alignment**| `scikit-learn` and `joblib` available in active runtime. | Current `.venv` lacks ML packages; ML packages reside in `C:\Python313`. | **PENDING APPROVAL** |
| **8. Real-Farm Pilot Site** | Verified farm coordinate, crop sowing date, and farmer consent. | Awaiting user designation of specific pilot farm. | **PENDING INPUT** |

### Overall Readiness Verdict: **CONDITIONAL GO**
The core application, live data pipelines, decision engine, and safety controls are **100% validated and ready for staging**. Formal deployment into staging is conditioned strictly upon the manual approvals listed below.

---

## 8. Exact Manual Actions Requiring User Approval

Before any live staging or deployment actions take place, the following explicit user approvals are required:

1. **Approval Action 1: Consolidate ML Dependencies in `.venv`**
   - *Command:* `.\.venv\Scripts\pip.exe install scikit-learn==1.8.0 joblib==1.5.3 numpy==2.2.6 pandas==2.3.3`
   - *Purpose:* Allows the active FastAPI runtime `.venv` to execute candidate Random Forest and Logistic Regression shadow inference without relying on cross-environment paths.
2. **Approval Action 2: Apply Migration 006 to Staging Database**
   - *Script:* `migrations/006_ml_shadow_evaluation.sql`
   - *Purpose:* Provisions the `ml_shadow_advisories` table with the idempotency constraint `uq_ml_shadow_advisory_id`.
3. **Approval Action 3: Designate Pilot Farm Location & Crop**
   - *Input:* Verified latitude, longitude, crop type, sowing date, and farmer consent.
4. **Approval Action 4: Whitelist Pilot Farmer Phone Number**
   - *Input:* Farmer mobile number authorized to receive pilot WhatsApp advisories (if outbound messaging is to be tested live).

---

## 9. Conclusion & Working Tree Status

Phase 6C has successfully established a comprehensive, safety-first staging preparation report. All software and architectural prerequisites are thoroughly audited, while the critical distinction between software execution and agronomic ground truth has been documented.

No packages were installed, no credentials or environment files were modified, no migrations were executed, no database connections were established, and all working tree modifications remain completely preserved.
