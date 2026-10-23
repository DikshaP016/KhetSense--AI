#!/usr/bin/env python3
"""
KhetSense AI — Machine Learning Shadow-Mode Evaluation Engine
=============================================================
Author: KhetSense AI Research Engineering & Machine Learning Team
Status: Production-Grade Shadow Evaluation (Non-Blocking / Advisory Neutral)

PURPOSE:
Executes candidate offline ML models (Random Forest with calibrated severe threshold T=0.33,
and Regularized Multinomial Logistic Regression) in parallel with the active production rule
classifier.

MANDATORY SAFETY & NON-BLOCKING GUARANTEES:
1. Zero Farmer Impact: Output is logged strictly to `ml_shadow_advisories` table for telemetry.
   The active rule engine remains the sole authority for farmer WhatsApp advisories.
2. Bounded Execution Time: Model inference is bounded by a technical timeout enforced via
   a persistent, reusable ThreadPoolExecutor with counting semaphore load shedding
   (default 500 ms; configurable down to 30 ms).
3. Thread Termination & Worker Lifecycle Guarantees:
   Python's threading library and ThreadPoolExecutor cannot forcibly terminate an active OS thread
   executing in bytecode without cooperative interruption. Therefore:
   - Callers (the active pipeline) are guaranteed immediate non-blocking return upon timeout expiry.
   - The background worker thread pool is strictly capped via counting semaphore (`MAX_SHADOW_QUEUE_TASKS`)
     to prevent unbounded accumulation of background tasks or memory exhaustion.
   - Any task exceeding timeout releases its worker slot upon completion, while excess incoming tasks
     are shed immediately (`LOAD_SHED_QUEUE_FULL`) rather than queued indefinitely.
4. Dependency & Artifact Resilience: If scikit-learn/joblib are not installed, or model artifacts
   are absent/corrupted, the engine records 'DEPENDENCY_UNAVAILABLE' and exits cleanly without
   raising unhandled exceptions or disrupting production pipelines.
5. Input Sanitization & Transparency: Missing or non-finite raw sensor inputs (NaN, +inf, -inf)
   are sanitized to safe missing values before imputer ingestion and flagged explicitly in
   `missing_sensor_flag`. Imputed values are passed to models for mathematical continuity
   but are NEVER represented as genuine field observations in telemetry records.
6. Parameterized SQL & Idempotency: All database writes use parameterized queries with
   `ON CONFLICT (advisory_id) DO UPDATE` to guarantee exactly one shadow record per advisory assessment.
"""

import os
import sys
import time
import math
import logging
import hashlib
import threading
from typing import Dict, Any, Optional, Tuple, List
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

logger = logging.getLogger("khetsense_ml_shadow")

# Default execution timeout in seconds
DEFAULT_SHADOW_TIMEOUT_SECONDS = float(os.getenv("ML_SHADOW_TIMEOUT_SECONDS", "0.5"))

# Concurrency limits for reusable worker pool
MAX_SHADOW_WORKERS = int(os.getenv("ML_SHADOW_MAX_WORKERS", "2"))
MAX_SHADOW_QUEUE_TASKS = int(os.getenv("ML_SHADOW_MAX_QUEUE", "4"))

# Module-level singletons and synchronization primitives
_SHADOW_EXECUTOR: Optional[ThreadPoolExecutor] = None
_EXECUTOR_INIT_LOCK = threading.Lock()
_SHADOW_SEMAPHORE = threading.Semaphore(MAX_SHADOW_QUEUE_TASKS)
_MODEL_INIT_LOCK = threading.Lock()

# Project roots and model directory resolution
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
MODELS_DIR = PROJECT_ROOT / "data" / "research_benchmark" / "models"

# Exact operational feature order verified from preprocessor.joblib
FEATURE_NAMES: List[str] = [
    "s2_ndvi",
    "s2_ndwi",
    "s2_ndre",
    "s2_msavi",
    "smap_sm_pct",
    "era5_precip_season_mm",
    "era5_temp_mean_c",
    "era5_temp_max_c",
    "era5_vpd_mean_kpa",
]

TARGET_CLASSES: Dict[int, str] = {
    0: "No Stress",
    1: "Mild Stress",
    2: "Severe Stress",
}

# Calibrated decision threshold for Severe Stress on Random Forest
RF_SEVERE_THRESHOLD: float = 0.33

# Global model cache to avoid repeated disk reads during frequent farm assessments
_MODEL_CACHE: Dict[str, Any] = {
    "loaded": False,
    "available": False,
    "load_error": None,
    "preprocessor": None,
    "rf_model": None,
    "lr_model": None,
    "rf_version": "unknown",
    "lr_version": "unknown",
}


def get_shadow_executor() -> ThreadPoolExecutor:
    """
    Returns the persistent, process-wide, bounded ThreadPoolExecutor instance.
    Lazily initialized with a thread-safe lock.
    """
    global _SHADOW_EXECUTOR
    if _SHADOW_EXECUTOR is not None:
        return _SHADOW_EXECUTOR
    with _EXECUTOR_INIT_LOCK:
        if _SHADOW_EXECUTOR is None:
            _SHADOW_EXECUTOR = ThreadPoolExecutor(
                max_workers=MAX_SHADOW_WORKERS,
                thread_name_prefix="khetsense-ml-shadow",
            )
        return _SHADOW_EXECUTOR


def shutdown_shadow_executor(wait: bool = True) -> None:
    """
    Shuts down the shared executor (used for test teardowns or process termination).
    """
    global _SHADOW_EXECUTOR
    with _EXECUTOR_INIT_LOCK:
        if _SHADOW_EXECUTOR is not None:
            _SHADOW_EXECUTOR.shutdown(wait=wait)
            _SHADOW_EXECUTOR = None


def _sanitize_float(val: Any) -> Optional[float]:
    """
    Validates and sanitizes numeric input.
    Converts NaN, +inf, -inf, booleans, and non-numeric types to None (safe missing value).
    """
    if val is None or isinstance(val, bool):
        return None
    try:
        f = float(val)
        if not math.isfinite(f):
            return None
        return f
    except (ValueError, TypeError):
        return None


def _compute_sha256(filepath: Path) -> str:
    """Computes SHA256 hex digest of a file safely."""
    h = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return "checksum_failed"


def load_shadow_models(force_reload: bool = False, models_dir: Optional[Path] = None) -> Tuple[bool, Optional[str]]:
    """
    Loads serialized ML models into memory with dependency verification.
    Protected by mutex lock for thread-safe concurrent initialization.
    Returns (success_boolean, error_message_or_None).
    """
    global _MODEL_CACHE

    if _MODEL_CACHE["loaded"] and not force_reload:
        return _MODEL_CACHE["available"], _MODEL_CACHE["load_error"]

    with _MODEL_INIT_LOCK:
        if _MODEL_CACHE["loaded"] and not force_reload:
            return _MODEL_CACHE["available"], _MODEL_CACHE["load_error"]

        target_dir = models_dir or MODELS_DIR

        # 1. Verify ML library availability
        try:
            import joblib
            import numpy as np
        except ImportError as imp_err:
            err_msg = f"ML dependencies (joblib/numpy) unavailable: {imp_err}"
            logger.info("Shadow ML engine dormant: %s", err_msg)
            _MODEL_CACHE = {
                "loaded": True,
                "available": False,
                "load_error": err_msg,
                "preprocessor": None,
                "rf_model": None,
                "lr_model": None,
                "rf_version": "unavailable",
                "lr_version": "unavailable",
            }
            return False, err_msg

        # 2. Check model artifact existence
        preproc_path = target_dir / "preprocessor.joblib"
        rf_path = target_dir / "random_forest.joblib"
        lr_path = target_dir / "logistic_regression.joblib"

        if not (preproc_path.exists() and rf_path.exists() and lr_path.exists()):
            err_msg = f"Model artifact files missing in {target_dir}"
            logger.warning("Shadow ML engine: %s", err_msg)
            _MODEL_CACHE = {
                "loaded": True,
                "available": False,
                "load_error": err_msg,
                "preprocessor": None,
                "rf_model": None,
                "lr_model": None,
                "rf_version": "missing",
                "lr_version": "missing",
            }
            return False, err_msg

        # 3. Load artifacts with error capture
        try:
            preprocessor_dict = joblib.load(preproc_path)
            rf_model = joblib.load(rf_path)
            lr_model = joblib.load(lr_path)

            rf_hash = _compute_sha256(rf_path)[:16]
            lr_hash = _compute_sha256(lr_path)[:16]

            _MODEL_CACHE = {
                "loaded": True,
                "available": True,
                "load_error": None,
                "preprocessor": preprocessor_dict,
                "rf_model": rf_model,
                "lr_model": lr_model,
                "rf_version": f"rf_v1_{rf_hash}",
                "lr_version": f"lr_v1_{lr_hash}",
            }
            logger.info("Shadow ML engine models successfully loaded (RF: %s, LR: %s)", rf_hash, lr_hash)
            return True, None

        except Exception as e:
            err_msg = f"Failed to deserialize model artifacts: {e}"
            logger.error("Shadow ML engine loading error: %s", err_msg)
            _MODEL_CACHE = {
                "loaded": True,
                "available": False,
                "load_error": err_msg,
                "preprocessor": None,
                "rf_model": None,
                "lr_model": None,
                "rf_version": "corrupt",
                "lr_version": "corrupt",
            }
            return False, err_msg


def _execute_raw_inference(
    raw_features: List[Optional[float]],
    rf_threshold: float,
) -> Dict[str, Any]:
    """
    Executes actual array transformations and model inferences synchronously.
    Converts any non-finite numbers (NaN, +inf, -inf) to np.nan for median imputation.
    """
    import numpy as np

    preprocessor = _MODEL_CACHE["preprocessor"]
    rf_model = _MODEL_CACHE["rf_model"]
    lr_model = _MODEL_CACHE["lr_model"]

    imputer = preprocessor["imputer"]
    scaler = preprocessor["scaler"]

    # Defensive sanitization: replace None, inf, -inf with np.nan for safe SimpleImputer transformation
    sanitized_features = []
    for val in raw_features:
        if val is None:
            sanitized_features.append(np.nan)
        else:
            try:
                f = float(val)
                sanitized_features.append(f if np.isfinite(f) else np.nan)
            except (ValueError, TypeError):
                sanitized_features.append(np.nan)

    # Construct input matrix
    X_raw = np.array([sanitized_features], dtype=float)

    # Impute missing/non-finite values via pre-fitted training median
    X_imp = imputer.transform(X_raw)

    # Scale for Logistic Regression
    X_scaled = scaler.transform(X_imp)

    # 1. Random Forest Inference & Threshold Calibrated Decision
    rf_probs = rf_model.predict_proba(X_imp)[0]
    p_none, p_mild, p_severe = float(rf_probs[0]), float(rf_probs[1]), float(rf_probs[2])

    if p_severe >= rf_threshold:
        rf_class = "Severe Stress"
    elif p_none >= p_mild:
        rf_class = "No Stress"
    else:
        rf_class = "Mild Stress"

    # 2. Logistic Regression Inference
    lr_probs = lr_model.predict_proba(X_scaled)[0]
    lr_p_none, lr_p_mild, lr_p_severe = float(lr_probs[0]), float(lr_probs[1]), float(lr_probs[2])
    lr_pred_code = int(np.argmax(lr_probs))
    lr_class = TARGET_CLASSES.get(lr_pred_code, "Unknown")

    return {
        "rf_predicted_class": rf_class,
        "rf_prob_no_stress": round(p_none, 4),
        "rf_prob_mild_stress": round(p_mild, 4),
        "rf_prob_severe_stress": round(p_severe, 4),
        "rf_model_version": _MODEL_CACHE["rf_version"],
        "lr_predicted_class": lr_class,
        "lr_prob_no_stress": round(lr_p_none, 4),
        "lr_prob_mild_stress": round(lr_p_mild, 4),
        "lr_prob_severe_stress": round(lr_p_severe, 4),
        "lr_model_version": _MODEL_CACHE["lr_version"],
    }


def evaluate_ml_shadow(
    farm_id: int,
    rule_observed_stress: str,
    rule_recommended_action: str,
    rule_guardrail_triggered: bool,
    advisory_id: Optional[int] = None,
    crop_name: Optional[str] = None,
    s2_ndvi: Optional[float] = None,
    s2_ndwi: Optional[float] = None,
    s2_ndre: Optional[float] = None,
    s2_msavi: Optional[float] = None,
    smap_sm_pct: Optional[float] = None,
    era5_precip_season_mm: Optional[float] = None,
    era5_temp_mean_c: Optional[float] = None,
    era5_temp_max_c: Optional[float] = None,
    era5_vpd_mean_kpa: Optional[float] = None,
    db_url: Optional[str] = None,
    timeout_seconds: float = DEFAULT_SHADOW_TIMEOUT_SECONDS,
    rf_threshold: float = RF_SEVERE_THRESHOLD,
    persist_to_db: bool = False,
    models_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Main entry point for shadow-mode evaluation.

    Executes:
    1. Input sanitization (NaN/Inf conversion) and missing sensor auditing.
    2. Model loading verification.
    3. Bounded-queue semaphore check and execution via shared thread pool.
    4. Disagreement metric calculation against the rule baseline.
    5. Non-blocking idempotent database persistence to `ml_shadow_advisories`.

    GUARANTEE: Returns a dictionary of shadow metrics. Never raises an unhandled exception.
    """
    start_ts = time.time()

    # 1. Sanitize all numerical inputs
    clean_s2_ndvi = _sanitize_float(s2_ndvi)
    clean_s2_ndwi = _sanitize_float(s2_ndwi)
    clean_s2_ndre = _sanitize_float(s2_ndre)
    clean_s2_msavi = _sanitize_float(s2_msavi)
    clean_smap_sm_pct = _sanitize_float(smap_sm_pct)
    clean_era5_precip = _sanitize_float(era5_precip_season_mm)
    clean_era5_temp_mean = _sanitize_float(era5_temp_mean_c)
    clean_era5_temp_max = _sanitize_float(era5_temp_max_c)
    clean_era5_vpd_mean = _sanitize_float(era5_vpd_mean_kpa)

    # Base telemetry payload
    result: Dict[str, Any] = {
        "farm_id": farm_id,
        "advisory_id": advisory_id,
        "crop_name": crop_name or "Unknown",
        "rule_observed_stress": rule_observed_stress,
        "rule_recommended_action": rule_recommended_action,
        "rule_guardrail_triggered": bool(rule_guardrail_triggered),
        "rf_predicted_class": None,
        "rf_prob_no_stress": None,
        "rf_prob_mild_stress": None,
        "rf_prob_severe_stress": None,
        "rf_model_version": "none",
        "lr_predicted_class": None,
        "lr_prob_no_stress": None,
        "lr_prob_mild_stress": None,
        "lr_prob_severe_stress": None,
        "lr_model_version": "none",
        "feat_s2_ndvi": clean_s2_ndvi,
        "feat_s2_ndwi": clean_s2_ndwi,
        "feat_s2_ndre": clean_s2_ndre,
        "feat_s2_msavi": clean_s2_msavi,
        "feat_smap_sm_pct": clean_smap_sm_pct,
        "feat_era5_precip_season_mm": clean_era5_precip,
        "feat_era5_temp_mean_c": clean_era5_temp_mean,
        "feat_era5_temp_max_c": clean_era5_temp_max,
        "feat_era5_vpd_mean_kpa": clean_era5_vpd_mean,
        "execution_status": "PENDING",
        "is_disagreement": False,
        "severe_disagreement": False,
        "missing_sensor_flag": "NONE",
        "inference_latency_ms": 0.0,
        "persistence_status": "SKIPPED",
    }

    # Audit missing and non-finite input sensors
    missing_flags = []
    if clean_s2_ndvi is None or clean_s2_ndwi is None:
        if s2_ndvi is not None or s2_ndwi is not None:
            missing_flags.append("S2_OPTICAL_NON_FINITE_SANITIZED")
        else:
            missing_flags.append("S2_OPTICAL_MISSING")
    if clean_smap_sm_pct is None:
        if smap_sm_pct is not None:
            missing_flags.append("SMAP_SOIL_MOISTURE_NON_FINITE_SANITIZED")
        else:
            missing_flags.append("SMAP_SOIL_MOISTURE_MISSING")
    if clean_era5_temp_mean is None or clean_era5_vpd_mean is None:
        missing_flags.append("WEATHER_METRICS_DEFAULTED")

    clean_raw_vector = [
        clean_s2_ndvi,
        clean_s2_ndwi,
        clean_s2_ndre,
        clean_s2_msavi,
        clean_smap_sm_pct,
        clean_era5_precip,
        clean_era5_temp_mean,
        clean_era5_temp_max,
        clean_era5_vpd_mean,
    ]

    if all(v is None for v in clean_raw_vector):
        missing_flags.append("ALL_SENSORS_MISSING_OR_INVALID")

    if missing_flags:
        result["missing_sensor_flag"] = ";".join(missing_flags)
    else:
        result["missing_sensor_flag"] = "COMPLETE"

    # 2. Check model loading and availability
    is_avail, err = load_shadow_models(models_dir=models_dir)
    if not is_avail:
        result["execution_status"] = "DEPENDENCY_UNAVAILABLE" if "dependencies" in str(err) else "MODEL_LOAD_FAILED"
        result["inference_latency_ms"] = round((time.time() - start_ts) * 1000, 2)
        logger.debug("Shadow evaluation skipped for farm %s: %s", farm_id, result["execution_status"])
        return result

    # 3. Bounded-queue semaphore check: shed load immediately if worker queue is saturated
    acquired = _SHADOW_SEMAPHORE.acquire(blocking=False)
    if not acquired:
        result["execution_status"] = "LOAD_SHED_QUEUE_FULL"
        result["inference_latency_ms"] = round((time.time() - start_ts) * 1000, 2)
        logger.warning(
            "Shadow ML queue full (max=%d in-flight); shedding shadow evaluation for farm %s",
            MAX_SHADOW_QUEUE_TASKS,
            farm_id,
        )
        return result

    def _worker_task(features, thresh):
        try:
            return _execute_raw_inference(features, thresh)
        finally:
            _SHADOW_SEMAPHORE.release()

    executor = get_shadow_executor()
    try:
        future = executor.submit(_worker_task, clean_raw_vector, rf_threshold)
    except Exception as submit_err:
        _SHADOW_SEMAPHORE.release()
        result["execution_status"] = f"SUBMIT_ERROR: {str(submit_err)[:60]}"
        result["inference_latency_ms"] = round((time.time() - start_ts) * 1000, 2)
        logger.error("Failed to submit shadow inference task for farm %s: %s", farm_id, submit_err)
        return result

    try:
        inf_res = future.result(timeout=timeout_seconds)

        # Merge prediction results
        result.update(inf_res)
        result["execution_status"] = "SUCCESS"

        # Calculate disagreement flags against rule-based authority
        rf_class = result["rf_predicted_class"]
        result["is_disagreement"] = bool(rule_observed_stress != rf_class)
        result["severe_disagreement"] = bool(
            (rule_observed_stress == "Severe Stress") != (rf_class == "Severe Stress")
        )

    except FutureTimeoutError:
        result["execution_status"] = "TIMEOUT_EXCEEDED"
        logger.warning(
            "Shadow ML inference exceeded timeout (%.3fs) for farm %s. Bounded execution aborted cleanly.",
            timeout_seconds,
            farm_id,
        )
    except Exception as inf_err:
        result["execution_status"] = f"INFERENCE_ERROR: {str(inf_err)[:60]}"
        logger.error("Error during shadow ML inference for farm %s: %s", farm_id, inf_err)

    result["inference_latency_ms"] = round((time.time() - start_ts) * 1000, 2)

    # 4. Non-blocking Idempotent Database Persistence (Guarded)
    if persist_to_db and db_url:
        try:
            persisted = persist_shadow_record(result, db_url)
            result["persistence_status"] = "PERSISTED" if persisted else "PERSISTENCE_FAILED"
        except Exception as db_err:
            result["persistence_status"] = f"PERSISTENCE_FAILED: {str(db_err)[:60]}"
            logger.warning("Shadow advisory DB persistence failed for farm %s: %s", farm_id, db_err)

    return result


def persist_shadow_record(record: Dict[str, Any], db_url: str) -> bool:
    """
    Persists shadow telemetry record to `ml_shadow_advisories` using parameterized SQL.
    Includes ON CONFLICT (advisory_id) to ensure strict idempotency and duplicate prevention.
    Fails safely if table is not yet provisioned or connection drops.
    """
    try:
        import psycopg2
    except ImportError:
        logger.debug("psycopg2 unavailable; skipping shadow DB persistence.")
        return False

    insert_sql = """
        INSERT INTO ml_shadow_advisories (
            farm_id, advisory_id, crop_name,
            rule_observed_stress, rule_recommended_action, rule_guardrail_triggered,
            rf_predicted_class, rf_prob_no_stress, rf_prob_mild_stress, rf_prob_severe_stress, rf_model_version,
            lr_predicted_class, lr_prob_no_stress, lr_prob_mild_stress, lr_prob_severe_stress, lr_model_version,
            feat_s2_ndvi, feat_s2_ndwi, feat_s2_ndre, feat_s2_msavi, feat_smap_sm_pct,
            feat_era5_precip_season_mm, feat_era5_temp_mean_c, feat_era5_temp_max_c, feat_era5_vpd_mean_kpa,
            execution_status, is_disagreement, severe_disagreement, missing_sensor_flag, inference_latency_ms
        ) VALUES (
            %(farm_id)s, %(advisory_id)s, %(crop_name)s,
            %(rule_observed_stress)s, %(rule_recommended_action)s, %(rule_guardrail_triggered)s,
            %(rf_predicted_class)s, %(rf_prob_no_stress)s, %(rf_prob_mild_stress)s, %(rf_prob_severe_stress)s, %(rf_model_version)s,
            %(lr_predicted_class)s, %(lr_prob_no_stress)s, %(lr_prob_mild_stress)s, %(lr_prob_severe_stress)s, %(lr_model_version)s,
            %(feat_s2_ndvi)s, %(feat_s2_ndwi)s, %(feat_s2_ndre)s, %(feat_s2_msavi)s, %(feat_smap_sm_pct)s,
            %(feat_era5_precip_season_mm)s, %(feat_era5_temp_mean_c)s, %(feat_era5_temp_max_c)s, %(feat_era5_vpd_mean_kpa)s,
            %(execution_status)s, %(is_disagreement)s, %(severe_disagreement)s, %(missing_sensor_flag)s, %(inference_latency_ms)s
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
            feat_s2_ndwi = EXCLUDED.feat_s2_ndwi,
            feat_s2_ndre = EXCLUDED.feat_s2_ndre,
            feat_s2_msavi = EXCLUDED.feat_s2_msavi,
            feat_smap_sm_pct = EXCLUDED.feat_smap_sm_pct,
            feat_era5_precip_season_mm = EXCLUDED.feat_era5_precip_season_mm,
            feat_era5_temp_mean_c = EXCLUDED.feat_era5_temp_mean_c,
            feat_era5_temp_max_c = EXCLUDED.feat_era5_temp_max_c,
            feat_era5_vpd_mean_kpa = EXCLUDED.feat_era5_vpd_mean_kpa,
            execution_status = EXCLUDED.execution_status,
            is_disagreement = EXCLUDED.is_disagreement,
            severe_disagreement = EXCLUDED.severe_disagreement,
            missing_sensor_flag = EXCLUDED.missing_sensor_flag,
            inference_latency_ms = EXCLUDED.inference_latency_ms;
    """

    conn = None
    try:
        conn = psycopg2.connect(db_url)
        with conn.cursor() as cur:
            cur.execute(insert_sql, record)
        conn.commit()
        return True
    except Exception as pg_err:
        logger.debug("Database error writing to ml_shadow_advisories (table may not exist yet): %s", pg_err)
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        return False
    finally:
        if conn:
            conn.close()
