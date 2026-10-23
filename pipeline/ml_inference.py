#!/usr/bin/env python3
"""
KhetSense AI — Machine Learning Inference Engine (Phase 7A)
============================================================
Author: KhetSense AI Research Engineering & Machine Learning Team
Status: Provisional ML-Assisted Component (Advisory Hybrid Architecture)

PURPOSE:
Provides dedicated, thread-safe, cached inference using the trained Random Forest
multi-sensor stress classification model (calibrated severe threshold T=0.33).

RESEARCH INTEGRITY & SCIENTIFIC CITATION:
1. Training Origin:
   Trained on the CSISA 2018 Eastern India Wheat Multi-Sensor Research Benchmark
   (7,648 records, 32 train districts, 8 held-out test districts).
2. Geographic & Crop Bounds:
   Validated strictly on Wheat in Eastern India. The model is NOT validated for
   Maharashtra or for non-wheat crops (Cotton, Soybean, Sugarcane, Pigeon Pea,
   Chickpea, Maize, Onion).
3. Provisional Status:
   Serves as an assistive decision component in a hybrid architecture. The
   deterministic rule engine and rainfall guardrails retain authority as the
   operational safety floor.
4. Input Transparency:
   Missing live sensors (e.g. S2 NDRE, MSAVI) are imputed using pre-fitted training
   medians via SimpleImputer. Missing inputs are never silently fabricated as
   genuine observations.
5. Probability Calibration:
   Model outputs are raw probabilities. They are NOT interpreted as calibrated
   Bayesian confidence.
"""

import os
import sys
import time
import math
import logging
import hashlib
import threading
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path

logger = logging.getLogger("khetsense_ml_inference")

# Default paths and constants
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DEFAULT_MODELS_DIR = PROJECT_ROOT / "data" / "research_benchmark" / "models"

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

# Supported crops for this model (Wheat only, including aliases in English, Marathi, and Hindi)
SUPPORTED_ML_CROPS: Dict[str, str] = {
    "wheat": "Wheat",
    "gehu": "Wheat",
    "gahu": "Wheat",
    "गेहूं": "Wheat",
    "गहू": "Wheat",
}

# Process-wide singleton model cache and synchronization lock
_MODEL_CACHE: Dict[str, Any] = {
    "loaded": False,
    "available": False,
    "load_error": None,
    "preprocessor": None,
    "rf_model": None,
    "rf_version": "unknown",
}
_MODEL_LOCK = threading.Lock()

# Phase 7F: Live-Native Five-Feature Model Constants and Cache
FEATURE_NAMES_5FEAT: List[str] = [
    "s2_ndvi",
    "s2_ndwi",
    "s2_ndre",
    "s2_msavi",
    "smap_sm_pct",
]
RF_5FEAT_SEVERE_THRESHOLD: float = 0.27

_MODEL_CACHE_5FEAT: Dict[str, Any] = {
    "loaded": False,
    "available": False,
    "load_error": None,
    "preprocessor": None,
    "rf_model": None,
    "rf_version": "unknown",
}
_MODEL_LOCK_5FEAT = threading.Lock()


def _sanitize_float(val: Any) -> Optional[float]:
    """
    Validates and sanitizes numeric input.
    Converts NaN, +inf, -inf, booleans, and non-numeric types to None.
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


def load_ml_model(
    force_reload: bool = False,
    models_dir: Optional[Path] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Loads serialized Random Forest model and preprocessor into process-wide memory.
    Thread-safe lazy initialization with double-checked locking.

    Returns:
        (is_available: bool, error_message: Optional[str])
    """
    global _MODEL_CACHE

    if _MODEL_CACHE["loaded"] and not force_reload:
        return _MODEL_CACHE["available"], _MODEL_CACHE["load_error"]

    with _MODEL_LOCK:
        if _MODEL_CACHE["loaded"] and not force_reload:
            return _MODEL_CACHE["available"], _MODEL_CACHE["load_error"]

        target_dir = models_dir or DEFAULT_MODELS_DIR

        # 1. Verify ML library availability
        try:
            try:
                import site
                user_site = site.getusersitepackages()
                if user_site and os.path.exists(user_site) and user_site not in sys.path:
                    sys.path.append(user_site)
            except Exception:
                pass
            import joblib
            import numpy as np
            import sklearn
        except ImportError as imp_err:
            err_msg = f"ML dependencies (joblib/numpy/sklearn) unavailable: {imp_err}"
            logger.info("ML inference component dormant: %s", err_msg)
            _MODEL_CACHE = {
                "loaded": True,
                "available": False,
                "load_error": err_msg,
                "preprocessor": None,
                "rf_model": None,
                "rf_version": "unavailable",
            }
            return False, err_msg

        # 2. Check model artifact existence
        preproc_path = target_dir / "preprocessor.joblib"
        rf_path = target_dir / "random_forest.joblib"

        if not (preproc_path.exists() and rf_path.exists()):
            err_msg = f"Model artifact files missing in {target_dir}"
            logger.warning("ML inference component: %s", err_msg)
            _MODEL_CACHE = {
                "loaded": True,
                "available": False,
                "load_error": err_msg,
                "preprocessor": None,
                "rf_model": None,
                "rf_version": "missing",
            }
            return False, err_msg

        # 3. Load artifacts with error capture
        try:
            preprocessor_dict = joblib.load(preproc_path)
            rf_model = joblib.load(rf_path)
            rf_hash = _compute_sha256(rf_path)[:16]

            _MODEL_CACHE = {
                "loaded": True,
                "available": True,
                "load_error": None,
                "preprocessor": preprocessor_dict,
                "rf_model": rf_model,
                "rf_version": f"rf_v1_{rf_hash}",
            }
            logger.info("ML inference model successfully loaded (RF: %s)", rf_hash)
            return True, None

        except Exception as e:
            err_msg = f"Failed to deserialize model artifacts: {e}"
            logger.error("ML inference deserialization error: %s", err_msg)
            _MODEL_CACHE = {
                "loaded": True,
                "available": False,
                "load_error": err_msg,
                "preprocessor": None,
                "rf_model": None,
                "rf_version": "corrupt",
            }
            return False, err_msg


def is_crop_supported_by_ml(crop_name: Optional[str]) -> bool:
    """Checks whether the declared crop matches the trained model's domain (Wheat)."""
    if not crop_name or not isinstance(crop_name, str):
        return False
    norm = crop_name.strip().lower()
    return norm in SUPPORTED_ML_CROPS


def predict_crop_stress(
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
    rf_threshold: float = RF_SEVERE_THRESHOLD,
    models_dir: Optional[Path] = None,
    require_seasonal_precipitation: bool = True,
) -> Dict[str, Any]:
    """
    Executes ML inference using the trained Random Forest model.

    Features:
    - Input sanitization (NaN/Inf to None).
    - Scientific feature compatibility audit (Phase 7C): prevents substituting forward forecasts
      into seasonal cumulative rainfall slots.
    - Crop domain eligibility check (Wheat supported; other crops flagged as unsupported).
    - Median imputation of unobserved features using pre-fitted SimpleImputer (when explicitly permitted).
    - Application of calibrated decision threshold T=0.33 for the Severe Stress class.
    - Safe error handling: never raises unhandled exceptions.

    Returns:
        Structured dictionary containing:
        - predicted_class: Optional[str] ('No Stress', 'Mild Stress', 'Severe Stress', or None)
        - probabilities: Optional[Dict[str, float]]
        - uncalibrated_confidence: Optional[float] (raw model probability; not calibrated)
        - model_name: str
        - model_version: str
        - inference_status: str ('SUCCESS', 'FEATURE_INCOMPATIBILITY', 'UNSUPPORTED_CROP', 'MISSING_INPUTS', 'DEPENDENCY_UNAVAILABLE', 'MODEL_NOT_FOUND', 'INFERENCE_ERROR')
        - crop_supported: bool
        - is_provisional: bool (always True for this model)
        - reason: Optional[str]
        - features_used: Dict[str, Optional[float]]
        - missing_sensor_flag: str
        - inference_latency_ms: float
    """
    start_ts = time.time()

    # 1. Sanitize all numerical inputs
    clean_ndvi = _sanitize_float(s2_ndvi)
    clean_ndwi = _sanitize_float(s2_ndwi)
    clean_ndre = _sanitize_float(s2_ndre)
    clean_msavi = _sanitize_float(s2_msavi)
    clean_smap = _sanitize_float(smap_sm_pct)
    clean_precip = _sanitize_float(era5_precip_season_mm)
    clean_temp_mean = _sanitize_float(era5_temp_mean_c)
    clean_temp_max = _sanitize_float(era5_temp_max_c)
    clean_vpd = _sanitize_float(era5_vpd_mean_kpa)

    features_dict = {
        "s2_ndvi": clean_ndvi,
        "s2_ndwi": clean_ndwi,
        "s2_ndre": clean_ndre,
        "s2_msavi": clean_msavi,
        "smap_sm_pct": clean_smap,
        "era5_precip_season_mm": clean_precip,
        "era5_temp_mean_c": clean_temp_mean,
        "era5_temp_max_c": clean_temp_max,
        "era5_vpd_mean_kpa": clean_vpd,
    }

    # Audit missing and non-finite sensors
    missing_flags = []
    if clean_ndvi is None or clean_ndwi is None:
        missing_flags.append("S2_OPTICAL_MISSING")
    if clean_smap is None:
        missing_flags.append("SMAP_SOIL_MOISTURE_MISSING")
    if clean_temp_mean is None or clean_vpd is None:
        missing_flags.append("WEATHER_METRICS_DEFAULTED")
    if clean_precip is None:
        missing_flags.append("SEASONAL_PRECIP_MISSING")

    clean_raw_vector = [
        clean_ndvi,
        clean_ndwi,
        clean_ndre,
        clean_msavi,
        clean_smap,
        clean_precip,
        clean_temp_mean,
        clean_temp_max,
        clean_vpd,
    ]

    all_missing = all(v is None for v in clean_raw_vector)
    if all_missing:
        missing_flags.append("ALL_SENSORS_MISSING")

    missing_sensor_flag = ";".join(missing_flags) if missing_flags else "COMPLETE"

    # Base response structure
    result: Dict[str, Any] = {
        "predicted_class": None,
        "probabilities": None,
        "uncalibrated_confidence": None,
        "model_name": "Random Forest Classifier (Tuned Severe T=0.33)",
        "model_version": "none",
        "inference_status": "PENDING",
        "crop_supported": is_crop_supported_by_ml(crop_name),
        "is_provisional": True,
        "reason": None,
        "features_used": features_dict,
        "missing_sensor_flag": missing_sensor_flag,
        "inference_latency_ms": 0.0,
    }

    # 2. Check if all critical observation inputs are missing
    if all_missing or (clean_ndvi is None and clean_smap is None):
        result["inference_status"] = "MISSING_INPUTS"
        result["reason"] = "Both optical Sentinel-2 and microwave SMAP inputs are missing or non-finite."
        result["inference_latency_ms"] = round((time.time() - start_ts) * 1000, 2)
        return result

    # 2b. Scientific Feature Compatibility Audit (Phase 7C):
    # The trained model strictly requires 120-day seasonal cumulative precipitation (era5_precip_season_mm).
    # In live operational production, substituting a 48-hour forward forecast (rain_48h) or blind median
    # into a seasonal climate slot is scientifically invalid. ML inference is disabled for affected inputs.
    if require_seasonal_precipitation and clean_precip is None:
        result["inference_status"] = "FEATURE_INCOMPATIBILITY"
        result["crop_supported"] = False
        result["reason"] = (
            "Feature incompatibility: The trained model requires 120-day seasonal cumulative precipitation "
            "(era5_precip_season_mm) from reanalysis. Live operational inputs provide only a 48-hour forward "
            "forecast (rain_48h), which cannot be scientifically substituted. Additionally, optical red-edge "
            "(NDRE) and soil-adjusted (MSAVI) indices are unobserved in the single-scene live pipeline. "
            "ML inference is disabled for active production advice to prevent invalid recommendations."
        )
        result["inference_latency_ms"] = round((time.time() - start_ts) * 1000, 2)
        return result

    # 3. Check model artifact loading
    is_avail, load_err = load_ml_model(models_dir=models_dir)
    if not is_avail:
        if "dependencies" in str(load_err):
            result["inference_status"] = "DEPENDENCY_UNAVAILABLE"
        elif "missing" in str(load_err):
            result["inference_status"] = "MODEL_NOT_FOUND"
        else:
            result["inference_status"] = "MODEL_LOAD_FAILED"
        result["reason"] = str(load_err)
        result["inference_latency_ms"] = round((time.time() - start_ts) * 1000, 2)
        return result

    # 4. Check crop compatibility
    crop_is_supported = is_crop_supported_by_ml(crop_name)
    result["crop_supported"] = crop_is_supported
    result["model_version"] = _MODEL_CACHE["rf_version"]

    # 5. Run inference
    try:
        import numpy as np

        preprocessor = _MODEL_CACHE["preprocessor"]
        rf_model = _MODEL_CACHE["rf_model"]
        imputer = preprocessor["imputer"]

        # Replace None with np.nan for median imputation
        sanitized_for_imputer = [np.nan if v is None else float(v) for v in clean_raw_vector]
        X_raw = np.array([sanitized_for_imputer], dtype=float)

        # Impute missing values via training median
        X_imp = imputer.transform(X_raw)

        # Predict probabilities
        rf_probs = rf_model.predict_proba(X_imp)[0]
        p_none, p_mild, p_severe = float(rf_probs[0]), float(rf_probs[1]), float(rf_probs[2])

        probs_dict = {
            "no_stress": round(p_none, 4),
            "mild_stress": round(p_mild, 4),
            "severe_stress": round(p_severe, 4),
        }
        result["probabilities"] = probs_dict

        # Apply calibrated threshold decision
        if p_severe >= rf_threshold:
            pred_class = "Severe Stress"
            confidence = p_severe
        elif p_none >= p_mild:
            pred_class = "No Stress"
            confidence = p_none
        else:
            pred_class = "Mild Stress"
            confidence = p_mild

        result["predicted_class"] = pred_class
        result["uncalibrated_confidence"] = round(confidence, 4)

        if not crop_is_supported:
            result["inference_status"] = "UNSUPPORTED_CROP"
            result["reason"] = (
                f"Declared crop '{crop_name}' is not wheat. Model was trained exclusively on CSISA Eastern India "
                f"wheat data and is not validated for '{crop_name}'. Output is provided for reference only."
            )
        else:
            result["inference_status"] = "SUCCESS"
            result["reason"] = "Inference completed successfully on supported crop (Wheat)."

    except Exception as inf_err:
        result["inference_status"] = "INFERENCE_ERROR"
        result["reason"] = f"Inference execution failed: {str(inf_err)}"
        logger.error("ML inference error: %s", inf_err)

    result["inference_latency_ms"] = round((time.time() - start_ts) * 1000, 2)
    return result


def load_ml_model_5feat(
    force_reload: bool = False,
    models_dir: Optional[Path] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Loads serialized 5-feature candidate Random Forest model and preprocessor into process-wide memory.
    Thread-safe lazy initialization with double-checked locking.

    Returns:
        (is_available: bool, error_message: Optional[str])
    """
    global _MODEL_CACHE_5FEAT

    if _MODEL_CACHE_5FEAT["loaded"] and not force_reload:
        return _MODEL_CACHE_5FEAT["available"], _MODEL_CACHE_5FEAT["load_error"]

    with _MODEL_LOCK_5FEAT:
        if _MODEL_CACHE_5FEAT["loaded"] and not force_reload:
            return _MODEL_CACHE_5FEAT["available"], _MODEL_CACHE_5FEAT["load_error"]

        target_dir = models_dir or DEFAULT_MODELS_DIR

        # 1. Verify ML library availability
        try:
            try:
                import site
                user_site = site.getusersitepackages()
                if user_site and os.path.exists(user_site) and user_site not in sys.path:
                    sys.path.append(user_site)
            except Exception:
                pass
            import joblib
            import numpy as np
            import sklearn
        except ImportError as imp_err:
            err_msg = f"ML dependencies (joblib/numpy/sklearn) unavailable: {imp_err}"
            logger.info("ML 5-feat candidate component dormant: %s", err_msg)
            _MODEL_CACHE_5FEAT = {
                "loaded": True,
                "available": False,
                "load_error": err_msg,
                "preprocessor": None,
                "rf_model": None,
                "rf_version": "unavailable",
            }
            return False, err_msg

        # 2. Check model artifact existence
        preproc_path = target_dir / "preprocessor_5feat.joblib"
        rf_path = target_dir / "random_forest_5feat.joblib"

        if not (preproc_path.exists() and rf_path.exists()):
            err_msg = f"Candidate 5-feat model artifact files missing in {target_dir}"
            logger.warning("ML 5-feat candidate component: %s", err_msg)
            _MODEL_CACHE_5FEAT = {
                "loaded": True,
                "available": False,
                "load_error": err_msg,
                "preprocessor": None,
                "rf_model": None,
                "rf_version": "missing",
            }
            return False, err_msg

        # 3. Load artifacts with error capture
        try:
            preprocessor_dict = joblib.load(preproc_path)
            rf_model = joblib.load(rf_path)
            rf_hash = _compute_sha256(rf_path)[:16]

            _MODEL_CACHE_5FEAT = {
                "loaded": True,
                "available": True,
                "load_error": None,
                "preprocessor": preprocessor_dict,
                "rf_model": rf_model,
                "rf_version": f"rf_5feat_v1_{rf_hash}",
            }
            logger.info("ML 5-feat candidate model successfully loaded (RF: %s)", rf_hash)
            return True, None

        except Exception as e:
            err_msg = f"Failed to deserialize 5-feat model artifacts: {e}"
            logger.error("ML 5-feat deserialization error: %s", err_msg)
            _MODEL_CACHE_5FEAT = {
                "loaded": True,
                "available": False,
                "load_error": err_msg,
                "preprocessor": None,
                "rf_model": None,
                "rf_version": "corrupt",
            }
            return False, err_msg


def predict_crop_stress_5feat(
    crop_name: Optional[str] = None,
    s2_ndvi: Optional[float] = None,
    s2_ndwi: Optional[float] = None,
    s2_ndre: Optional[float] = None,
    s2_msavi: Optional[float] = None,
    smap_sm_pct: Optional[float] = None,
    rf_threshold: float = RF_5FEAT_SEVERE_THRESHOLD,
    models_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Executes ML inference using the candidate Live-Native Five-Feature Random Forest model.

    Features (5 live-observable):
    - s2_ndvi
    - s2_ndwi
    - s2_ndre
    - s2_msavi
    - smap_sm_pct

    Decision Threshold:
    - Tuned Severe Stress decision threshold T=0.27 (optimized via out-of-fold spatial CV).

    Crop Domain:
    - Trained exclusively on CSISA Eastern India Wheat. Unsupported crops are flagged.

    Safety & Operational Status:
    - Research candidate model for offline benchmarking and shadow evaluation.
    - Does NOT dictate live farmer advisory recommendations.

    Returns:
        Structured dictionary identical in schema to predict_crop_stress.
    """
    start_ts = time.time()

    # 1. Sanitize all numerical inputs
    clean_ndvi = _sanitize_float(s2_ndvi)
    clean_ndwi = _sanitize_float(s2_ndwi)
    clean_ndre = _sanitize_float(s2_ndre)
    clean_msavi = _sanitize_float(s2_msavi)
    clean_smap = _sanitize_float(smap_sm_pct)

    features_dict = {
        "s2_ndvi": clean_ndvi,
        "s2_ndwi": clean_ndwi,
        "s2_ndre": clean_ndre,
        "s2_msavi": clean_msavi,
        "smap_sm_pct": clean_smap,
    }

    # Audit missing and non-finite sensors
    missing_flags = []
    missing_input_names = []
    if clean_ndvi is None:
        missing_input_names.append("s2_ndvi")
    if clean_ndwi is None:
        missing_input_names.append("s2_ndwi")
    if clean_ndre is None:
        missing_input_names.append("s2_ndre")
    if clean_msavi is None:
        missing_input_names.append("s2_msavi")
    if clean_smap is None:
        missing_input_names.append("smap_sm_pct")

    if clean_ndvi is None or clean_ndwi is None:
        missing_flags.append("S2_PRIMARY_OPTICAL_MISSING")
    if clean_ndre is None:
        missing_flags.append("S2_NDRE_MISSING")
    if clean_msavi is None:
        missing_flags.append("S2_MSAVI_MISSING")
    if clean_smap is None:
        missing_flags.append("SMAP_SOIL_MOISTURE_MISSING")

    clean_raw_vector = [clean_ndvi, clean_ndwi, clean_ndre, clean_msavi, clean_smap]
    all_missing = all(v is None for v in clean_raw_vector)
    if all_missing:
        missing_flags.append("ALL_SENSORS_MISSING")

    missing_sensor_flag = ";".join(missing_flags) if missing_flags else "COMPLETE"

    # Base response structure
    result: Dict[str, Any] = {
        "predicted_class": None,
        "probabilities": None,
        "uncalibrated_confidence": None,
        "uncalibrated_probability": None,
        "model_name": "Candidate Live-Native 5-Feature Random Forest (Tuned Severe T=0.27)",
        "model_version": "none",
        "inference_status": "PENDING",
        "crop_supported": is_crop_supported_by_ml(crop_name),
        "is_provisional": True,
        "is_candidate": True,
        "is_primary": True,
        "reason": None,
        "features_used": features_dict,
        "missing_sensor_flag": missing_sensor_flag,
        "missing_inputs": missing_input_names,
        "inference_latency_ms": 0.0,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "disclaimer": (
            "Academic Prototype — Experimental model trained on CSISA Eastern India wheat research data. "
            "Not validated for commercial farming decisions or non-wheat crops."
        ),
    }

    # 2. Check if all critical observation inputs are missing
    if all_missing or (clean_ndvi is None and clean_smap is None):
        result["inference_status"] = "MISSING_INPUTS"
        result["reason"] = (
            f"Required sensor inputs missing: optical Sentinel-2 (NDVI) and microwave SMAP inputs are missing or non-finite. "
            f"Missing fields: {missing_input_names or ['s2_ndvi', 'smap_sm_pct']}."
        )
        result["inference_latency_ms"] = round((time.time() - start_ts) * 1000, 2)
        return result

    # 3. Check model artifact loading
    is_avail, load_err = load_ml_model_5feat(models_dir=models_dir)
    if not is_avail:
        if "dependencies" in str(load_err):
            result["inference_status"] = "DEPENDENCY_UNAVAILABLE"
        elif "missing" in str(load_err):
            result["inference_status"] = "MODEL_NOT_FOUND"
        else:
            result["inference_status"] = "MODEL_LOAD_FAILED"
        result["reason"] = str(load_err)
        result["inference_latency_ms"] = round((time.time() - start_ts) * 1000, 2)
        return result

    # 4. Check crop compatibility
    crop_is_supported = is_crop_supported_by_ml(crop_name)
    result["crop_supported"] = crop_is_supported
    result["model_version"] = _MODEL_CACHE_5FEAT["rf_version"]

    # 5. Run inference
    try:
        import numpy as np

        preprocessor = _MODEL_CACHE_5FEAT["preprocessor"]
        rf_model = _MODEL_CACHE_5FEAT["rf_model"]
        imputer = preprocessor["imputer"]

        # Replace None with np.nan for median imputation
        sanitized_for_imputer = [np.nan if v is None else float(v) for v in clean_raw_vector]
        X_raw = np.array([sanitized_for_imputer], dtype=float)

        # Impute missing values via training median
        X_imp = imputer.transform(X_raw)

        # Predict probabilities
        rf_probs = rf_model.predict_proba(X_imp)[0]
        p_none, p_mild, p_severe = float(rf_probs[0]), float(rf_probs[1]), float(rf_probs[2])

        probs_dict = {
            "no_stress": round(p_none, 4),
            "mild_stress": round(p_mild, 4),
            "severe_stress": round(p_severe, 4),
        }
        result["probabilities"] = probs_dict

        # Apply calibrated threshold decision (T=0.27)
        if p_severe >= rf_threshold:
            pred_class = "Severe Stress"
            confidence = p_severe
        elif p_none >= p_mild:
            pred_class = "No Stress"
            confidence = p_none
        else:
            pred_class = "Mild Stress"
            confidence = p_mild

        result["predicted_class"] = pred_class
        result["uncalibrated_confidence"] = round(confidence, 4)
        result["uncalibrated_probability"] = round(confidence, 4)

        if not crop_is_supported:
            result["inference_status"] = "UNSUPPORTED_CROP"
            result["reason"] = (
                f"Declared crop '{crop_name}' is not wheat. Model was trained exclusively on CSISA Eastern India "
                f"wheat data and is not validated for '{crop_name}'. Candidate output is provided for evaluation only."
            )
        else:
            result["inference_status"] = "SUCCESS"
            result["reason"] = "Candidate 5-feature inference completed successfully on supported crop (Wheat)."

    except Exception as inf_err:
        result["inference_status"] = "INFERENCE_ERROR"
        result["reason"] = f"Candidate 5-feature inference execution failed: {str(inf_err)}"
        logger.error("ML 5-feat inference error: %s", inf_err)

    result["inference_latency_ms"] = round((time.time() - start_ts) * 1000, 2)
    return result
