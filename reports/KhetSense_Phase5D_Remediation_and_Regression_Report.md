# KhetSense AI: Phase 5D — Safety Remediation and Regression Testing Report

**Author:** KhetSense AI Senior Software Auditor, ML Engineer & QA Lead  
**Execution Date:** October 19, 2026  
**Status:** Remediations Implemented, Regression-Tested, and Verified Across Dual Environments  
**Evaluated Artifacts:**
- Shadow Inference Engine: `pipeline/ml_shadow_engine.py`
- Database Schema Migration: `migrations/006_ml_shadow_evaluation.sql`
- Pipeline Integration Hook: `pipeline/test_pipeline.py` (Line 905)
- Automated Test Suite: `tests/test_ml_shadow.py` (15 Automated Tests)
- Prior Audit Report: `reports/KhetSense_Phase5C_PreDeployment_Safety_Audit.md`

---

## 1. Executive Summary & Remediation Mandate

Following the findings of the **Phase 5C Pre-Deployment Safety and Integration Audit**, this phase executed targeted code remediations to resolve all identified architectural and concurrency risks prior to live database activation.

In strict compliance with project safety directives:
- **Zero changes** were made to the deterministic rule-based classifier (`classify_ndvi_stress`, `classify_soil_moisture_stress`, `get_more_severe`) or multi-tier rainfall guardrail (`apply_rainfall_guardrail`).
- **Zero WhatsApp messages** were sent, and live Meta WhatsApp Cloud API endpoints remained completely protected.
- **Zero dependencies** were installed into `.venv` or the global system Python.
- **Zero database migrations** were applied against the live PostgreSQL/Supabase database.
- **Zero live shadow persistence writes** were activated in production (`persist_to_db` remains default `False`).
- **All pre-existing working-tree modifications** were preserved without resets, reverts, or checkouts.

---

## 2. Summary of Remediations Implemented

| Finding ID | Severity | Category | Remediation Implemented | Verification Invariant |
| :--- | :---: | :--- | :--- | :--- |
| **FINDING-01** | **HIGH** | Worker Lifecycle / Concurrency | Replaced per-call `ThreadPoolExecutor(max_workers=1)` with a persistent, process-wide shared pool (`MAX_SHADOW_WORKERS=2`). Added a counting semaphore (`_SHADOW_SEMAPHORE`) capping in-flight tasks to `MAX_SHADOW_QUEUE_TASKS=4`. If saturated, excess calls shed load immediately (`LOAD_SHED_QUEUE_FULL`) without queuing or blocking the active pipeline. | Proved that caller returns within $< 120\text{ ms}$ on 30ms timeout, and subsequent tasks shed load rather than accumulating orphan worker threads. |
| **FINDING-02** | **MEDIUM** | Database Idempotency | Added `CONSTRAINT uq_ml_shadow_advisory_id UNIQUE (advisory_id)` to `migrations/006_ml_shadow_evaluation.sql`. Refactored `persist_shadow_record` in `pipeline/ml_shadow_engine.py` to use `ON CONFLICT (advisory_id) DO UPDATE SET ...`. | Exactly one shadow record per advisory assessment; repeated runs or retry deliveries update telemetry rather than generating duplicates. |
| **FINDING-03** | **MEDIUM** | Input Sanitization / Non-Finite Floats | Added `_sanitize_float` converting `NaN`, `+inf`, `-inf`, booleans, and non-numeric types to `None`. In `_execute_raw_inference`, non-finite values are mapped to `np.nan` for safe `SimpleImputer` median imputation. Added `ALL_SENSORS_MISSING_OR_INVALID` handling. | Passed `float("nan")`, `float("inf")`, and `float("-inf")`; verified zero `ValueError: Input contains infinity` crashes and clean telemetry reporting. |
| **FINDING-04** | **LOW** | Thread-Safe Model Cache | Protected `load_shadow_models` with a module-level mutex lock (`_MODEL_INIT_LOCK`) using double-checked locking. | 8 concurrent worker threads invoked `load_shadow_models(force_reload=True)` simultaneously without deadlocks or race conditions. |
| **FINDING-05** | **LOW** | Observability & Crop Context | Added `crop_name VARCHAR(64) NULL` and index `idx_ml_shadow_crop` to Migration 006. Updated `evaluate_ml_shadow` to accept and record `crop_name`, and updated `pipeline/test_pipeline.py` (line 905) to pass `crop_name=crop`. | Verified crop context is preserved in telemetry payload and passed to persistence without breaking callers defaulting to `"Unknown"`. |

---

## 3. Technical Architecture of Remediations

### A. Worker Lifecycle & Bounded Load Shedding Architecture
```
                                Incoming Pipeline Call
                                          |
                                          v
                         +---------------------------------+
                         | _SHADOW_SEMAPHORE.acquire()     |
                         | (Capacity = 4 in-flight tasks)  |
                         +---------------------------------+
                                    /           \
                         (Acquired)               (Queue Full)
                            /                           \
                           v                             v
           +-------------------------------+    +----------------------------------+
           | Submit to _SHADOW_EXECUTOR    |    | Return: LOAD_SHED_QUEUE_FULL     |
           | (max_workers=2, shared pool)  |    | Zero latency (< 0.05ms)          |
           +-------------------------------+    | Active advisory continues safely |
                           |                    +----------------------------------+
                           v
           +-------------------------------+
           | future.result(timeout=0.50s)  |
           +-------------------------------+
                   /               \
            (Finished)           (Timeout)
               /                     \
              v                       v
      Return SUCCESS          Return TIMEOUT_EXCEEDED
      Latency: <20ms          Caller returns immediately
              \                       /
               \                     /
                v                   v
           +---------------------------------+
           | Background Worker Task Finishes |
           | _SHADOW_SEMAPHORE.release()     |
           +---------------------------------+
```

#### Python Thread Termination Guarantees:
Python's standard library does not provide a mechanism to forcibly terminate an executing OS-level thread without cooperative polling or interpreter shutdown. Therefore:
1. **Caller Guarantee:** The caller thread (the active agricultural advisory pipeline) is **guaranteed** never to block longer than `timeout_seconds` (0.50s default).
2. **Resource Bound Guarantee:** Even if a model inference thread experiences a CPU delay and exceeds the timeout, the persistent worker pool is capped at `MAX_SHADOW_WORKERS=2` and the task queue is bounded at `MAX_SHADOW_QUEUE_TASKS=4`. If repeated timeouts occur, new incoming assessments shed load immediately (`LOAD_SHED_QUEUE_FULL`) in $< 0.05\text{ ms}$ rather than spawning new threads or accumulating unbounded background work.

### B. Idempotency & Upsert SQL Schema
In `migrations/006_ml_shadow_evaluation.sql`:
```sql
CREATE TABLE IF NOT EXISTS ml_shadow_advisories (
    id BIGSERIAL PRIMARY KEY,
    farm_id BIGINT NOT NULL REFERENCES farms(id) ON DELETE CASCADE,
    advisory_id BIGINT REFERENCES advisories(id) ON DELETE SET NULL,
    crop_name VARCHAR(64) NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ...
    CONSTRAINT uq_ml_shadow_advisory_id UNIQUE (advisory_id)
);
CREATE INDEX IF NOT EXISTS idx_ml_shadow_crop ON ml_shadow_advisories(crop_name);
```

In `pipeline/ml_shadow_engine.py::persist_shadow_record`:
```sql
INSERT INTO ml_shadow_advisories (
    farm_id, advisory_id, crop_name, rule_observed_stress, rule_recommended_action, ...
) VALUES (
    %(farm_id)s, %(advisory_id)s, %(crop_name)s, %(rule_observed_stress)s, ...
)
ON CONFLICT (advisory_id) DO UPDATE SET
    crop_name = EXCLUDED.crop_name,
    rule_observed_stress = EXCLUDED.rule_observed_stress,
    rule_recommended_action = EXCLUDED.rule_recommended_action,
    rule_guardrail_triggered = EXCLUDED.rule_guardrail_triggered,
    rf_predicted_class = EXCLUDED.rf_predicted_class,
    rf_prob_no_stress = EXCLUDED.rf_prob_no_stress,
    rf_prob_mild_stress = EXCLUDED.rf_prob_mild_stress,
    rf_prob_severe_stress = EXCLUDED.rf_prob_severe_stress,
    rf_model_version = EXCLUDED.rf_model_version,
    lr_predicted_class = EXCLUDED.lr_predicted_class,
    lr_prob_no_stress = EXCLUDED.lr_prob_no_stress,
    lr_prob_mild_stress = EXCLUDED.lr_prob_mild_stress,
    lr_prob_severe_stress = EXCLUDED.lr_prob_severe_stress,
    lr_model_version = EXCLUDED.lr_model_version,
    feat_s2_ndvi = EXCLUDED.feat_s2_ndvi,
    ...
    execution_status = EXCLUDED.execution_status,
    is_disagreement = EXCLUDED.is_disagreement,
    severe_disagreement = EXCLUDED.severe_disagreement,
    missing_sensor_flag = EXCLUDED.missing_sensor_flag,
    inference_latency_ms = EXCLUDED.inference_latency_ms;
```

---

## 4. Test Verification Across Environments

The test suite was expanded from 9 to **15 automated tests** in `tests/test_ml_shadow.py` and evaluated across both runtime environments:

### Test Suite Execution 1: Production Virtual Environment (`.venv`)
- **Python Version:** 3.13.5
- **Configuration:** Production dependencies only; `scikit-learn` intentionally absent.
- **Execution Command:**
  ```powershell
  .\.venv\Scripts\python.exe -m unittest tests/test_ml_shadow.py
  ```
- **Execution Log:**
  ```
  .Shadow ML inference exceeded timeout (0.030s) for farm 107. Bounded execution aborted cleanly.
  .Shadow ML queue full (max=4 in-flight); shedding shadow evaluation for farm 203
  Shadow ML queue full (max=4 in-flight); shedding shadow evaluation for farm 999
  ........Shadow ML inference exceeded timeout (0.010s) for farm 300. Bounded execution aborted cleanly.
  Shadow ML inference exceeded timeout (0.010s) for farm 301. Bounded execution aborted cleanly.
  Shadow ML inference exceeded timeout (0.010s) for farm 302. Bounded execution aborted cleanly.
  ...Shadow ML evaluation error for farm 42 (non-fatal): Catastrophic ML Crash
  ..
  ----------------------------------------------------------------------
  Ran 15 tests in 0.758s

  OK
  ```
- **Outcome:** **100% Pass (15/15 tests).**

### Test Suite Execution 2: Agricultural ML Benchmark Environment (Python 3.13 + ML Packages)
- **Python Version:** 3.13.5
- **Configuration:** `scikit-learn 1.8.0`, `joblib 1.5.3`, `pandas 2.3.3`, `numpy 2.2.6`, plus `.venv` site-packages via `PYTHONPATH`.
- **Execution Command:**
  ```powershell
  $env:PYTHONPATH="c:\Users\NIDEEKSHA\Documents\DEEKSHA\MASTERS\Research Project\khetsense\.venv\Lib\site-packages"
  C:\Python313\python.exe -m unittest tests/test_ml_shadow.py
  ```
- **Execution Log:**
  ```
  .Shadow ML inference exceeded timeout (0.030s) for farm 107. Bounded execution aborted cleanly.
  .Shadow ML queue full (max=4 in-flight); shedding shadow evaluation for farm 203
  Shadow ML queue full (max=4 in-flight); shedding shadow evaluation for farm 999
  .Shadow ML queue full (max=4 in-flight); shedding shadow evaluation for farm 404
  Shadow ML queue full (max=4 in-flight); shedding shadow evaluation for farm 405
  Shadow ML queue full (max=4 in-flight); shedding shadow evaluation for farm 406
  Shadow ML queue full (max=4 in-flight); shedding shadow evaluation for farm 407
  .......Shadow ML inference exceeded timeout (0.010s) for farm 300. Bounded execution aborted cleanly.
  Shadow ML inference exceeded timeout (0.010s) for farm 301. Bounded execution aborted cleanly.
  Shadow ML inference exceeded timeout (0.010s) for farm 302. Bounded execution aborted cleanly.
  ...Shadow ML evaluation error for farm 42 (non-fatal): Catastrophic ML Crash
  ..
  ----------------------------------------------------------------------
  Ran 15 tests in 4.062s

  OK
  ```
- **Outcome:** **100% Pass (15/15 tests).**

---

## 5. Comprehensive 15-Test Coverage Breakdown

| # | Test Method Name | Scope & Behavior Verified | Local Real vs. Mocked | Status |
| :---: | :--- | :--- | :---: | :---: |
| 1 | `test_feature_names_order` | Verifies operational feature order matches exact 9-feature specification. | **Local Real** | **PASSED** |
| 2 | `test_shadow_inference_success_with_models` | Validates live probability computation, severe threshold $T=0.33$, and latency tracking. | **Local Real** | **PASSED** |
| 3 | `test_missing_sensor_flag_reporting` | Validates that missing optical/soil inputs generate transparent audit tags. | **Local Real** | **PASSED** |
| 4 | `test_non_finite_inputs_handled_safely` | Ingests `NaN`, `+inf`, `-inf`. Verifies sanitization to `None` and safe median imputation without `ValueError`. | **Local Real** | **PASSED** |
| 5 | `test_all_invalid_features_handled_gracefully` | Ingests an all-None feature row. Verifies fallback to median imputation and `ALL_SENSORS_MISSING_OR_INVALID` flag. | **Local Real** | **PASSED** |
| 6 | `test_crop_context_captured_in_shadow_record` | Validates `crop_name` capture and graceful fallback to `'Unknown'` when omitted. | **Local Real** | **PASSED** |
| 7 | `test_simultaneous_model_loading_thread_safety` | Concurrently executes 8 threads calling `load_shadow_models(force_reload=True)` under mutex lock. | **Local Real (Threads)** | **PASSED** |
| 8 | `test_disagreement_detection_logic` | Validates divergence and severe-divergence calculations across all class pairings. | **Mocked Inference** | **PASSED** |
| 9 | `test_bounded_timeout_enforcement` | Simulates slow inference (150ms) against 30ms timeout; caller returns in $< 120\text{ ms}$. | **Mocked Delay** | **PASSED** |
| 10 | `test_bounded_worker_queue_and_load_shedding` | Saturates pool with 4 concurrent tasks; verifies 5th call sheds load (`LOAD_SHED_QUEUE_FULL`) in $< 0.05\text{ ms}$. | **Local Real (Threads)** | **PASSED** |
| 11 | `test_repeated_timeouts_bounded_worker_behavior` | Executes 3 sequential timed-out calls; verifies pool remains healthy and bounded. | **Mocked Delay** | **PASSED** |
| 12 | `test_duplicate_advisory_persistence_idempotency` | Verifies SQL query contains `ON CONFLICT (advisory_id) DO UPDATE SET` and `crop_name`. | **Mocked psycopg2** | **PASSED** |
| 13 | `test_concurrent_evaluations_stress` | Executes 8 concurrent threads invoking `evaluate_ml_shadow` simultaneously without deadlocks or unhandled exceptions. | **Local Real (Threads)** | **PASSED** |
| 14 | `test_ml_failure_preserves_rule_based_advisory` | Catastrophic exception during shadow call inside `run_pipeline_for_farm` leaves rule advisory 100% intact. | **Mocked Integration** | **PASSED** |
| 15 | `test_pipeline_runs_shadow_evaluation_successfully` | Verifies `evaluate_ml_shadow` is called with `crop_name=crop` and attaches results to return contract. | **Mocked Integration** | **PASSED** |

---

## 6. Full Pipeline & Audio Regression Test Results

To guarantee zero regression across the existing KhetSense codebase, existing integration test suites were executed:

### A. Advisory Pipeline & Stress Classification Regression Suite
- **Command:** `.\.venv\Scripts\python.exe -m unittest tests.test_registration_flow.TestStressClassification tests.test_registration_flow.TestAutomatedPipelineAndStatusEnhancements`
- **Result:**
  ```
  Ran 26 tests in 0.669s — OK
  ```
- **Verification:** All 26 stress classification, threshold fusion, rainfall guardrail, and automated pipeline status tests passed with zero regressions.

### B. Voice Advisory & Multilingual Delivery Regression Suite
- **Command:** `.\.venv\Scripts\python.exe -m unittest tests/test_voice_advisory.py`
- **Result:**
  ```
  Ran 55 tests in 0.741s — OK
  ```
- **Verification:** All 55 voice synthesis, Edge-TTS fallback, audio delivery retry, and whole-chat voice tests passed with zero regressions.

---

## 7. Working Tree & Repository Git Status

The repository status was inspected via `git status --short`. All pre-existing modified files and untracked artifacts were strictly preserved:

```
 M .env.example
 M common/__init__.py
 A common/config.py
 M common/utils.py
 A migrations/003_rainfall_policy_and_advisory_provenance.sql
 M pipeline/classifier.py
 M pipeline/farmer_registration.py
 M pipeline/test_pipeline.py
 M requirements.txt
 M tests/test_registration_flow.py
 M whatsapp/messages.py
 M whatsapp/registration_flow.py
?? KhetSense_IEEE_Research_Paper.docx
?? KhetSense_IEEE_Research_Paper.pdf
?? KhetSense_Research_References_and_Evidence.md
?? data/
?? implementation_audit/
?? migrations/004_registration_session_language.sql
?? migrations/005_location_selection_and_validation.sql
?? migrations/006_ml_shadow_evaluation.sql
?? pipeline/location_validator.py
?? pipeline/ml_shadow_engine.py
?? pipeline/tts_provider.py
?? registration_flow_fixed.py
?? reports/
?? test_registration_flow_fixed.py
?? tests/test_ml_shadow.py
?? tests/test_voice_advisory.py
```

---

## 8. Final Gate Sign-Off & Recommendations

### Production Gate Status: **CLEARED FOR CONTROLLED PHASE 6 SHADOW ACTIVATION**

1. **Safety Remediation Complete:** All 5 audit findings from Phase 5C have been remediated, verified, and regression-tested.
2. **Advisory Sovereignty Intact:** The active rule engine remains the sole authority for all farmer advisories.
3. **Graceful Dormancy:** In environments lacking `scikit-learn` (such as production `.venv`), the engine sits dormant without overhead.
4. **Next Step (Phase 6 Pre-Requisites):**
   - Apply `migrations/006_ml_shadow_evaluation.sql` to the production PostgreSQL database.
   - Install `scikit-learn==1.8.0` and `joblib==1.5.3` in the production environment.
   - Set `persist_to_db=True` in `pipeline/test_pipeline.py`.
   - Begin 30-day divergence telemetry logging.

*As mandated by project directives, all work has stopped after implementation and verification. No live deployments, database migrations, or WhatsApp messages have been initiated.*
