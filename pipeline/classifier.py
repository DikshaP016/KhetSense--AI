#!/usr/bin/env python3
"""
KhetSense AI — Decision Engine & Stress Classification Rules
Contains core logic for:
1. NDVI vegetation vigor stress classification.
2. Soil moisture (SMAP 9-km) stress classification.
3. Severity comparison (worst-case heuristic: observed stress).
4. 48-hour rainfall guardrail application (policy thresholds R1 & R2).
5. Plain-language irrigation advisory text generation.
"""

from typing import Optional, Tuple, Any
from common.config import (
    RAINFALL_CONFIG,
    FRESHNESS_CONFIG,
    ACTION_IRRIGATE_NOW,
    ACTION_IRRIGATE_LIGHTLY,
    ACTION_SCHEDULE_IRRIGATION,
    ACTION_DELAY_RECHECK,
    ACTION_HOLD_RECHECK,
    ACTION_NO_ACTION,
    ACTION_INSUFFICIENT_DATA,
)
from common.utils import sanitize_sensor_float


def classify_ndvi_stress(ndvi: Any) -> str:
    """
    NDVI Stress Thresholds:
      > 0.60        -> No Stress
      0.30 - 0.60   -> Mild Stress
      0.00 - < 0.30 -> Severe Stress
      None, NaN, Inf, non-numeric, or out-of-range (< 0.0 or > 1.0) -> Unknown
    """
    val = sanitize_sensor_float(ndvi, min_val=0.0, max_val=1.0)
    if val is None:
        return "Unknown"
    if val > 0.6:
        return "No Stress"
    elif val >= 0.3:
        return "Mild Stress"
    else:
        return "Severe Stress"


def classify_soil_moisture_stress(sm_pct: Any) -> str:
    """
    Soil Moisture Stress Thresholds (% volumetric):
      > 25.0%        -> No Stress
      15.0% - 25.0%  -> Mild Stress
      0.0% - < 15.0% -> Severe Stress
      None, NaN, Inf, non-numeric, or out-of-range (< 0.0 or > 100.0) -> Unknown
    """
    val = sanitize_sensor_float(sm_pct, min_val=0.0, max_val=100.0)
    if val is None:
        return "Unknown"
    if val > 25.0:
        return "No Stress"
    elif val >= 15.0:
        return "Mild Stress"
    else:
        return "Severe Stress"


def get_more_severe(cat1: Any, cat2: Any) -> str:
    """
    Return the more severe of two stress classifications.
    Ranking: Severe Stress (3) > Mild Stress (2) > No Stress (1) > Unknown (0).
    Safely handles None, unrecognized strings, and malformed inputs.
    """
    severity_rank = {
        "Severe Stress": 3,
        "Mild Stress": 2,
        "No Stress": 1,
        "Unknown": 0,
    }
    r1 = severity_rank.get(cat1, 0)
    r2 = severity_rank.get(cat2, 0)

    if r1 >= r2:
        return cat1 if r1 > 0 else "Unknown"
    return cat2 if r2 > 0 else "Unknown"


def validate_forecast_rainfall(forecast_rain_mm: Any) -> Optional[float]:
    """
    Validates 48-hour forecast rainfall value.

    Returns:
      - None if forecast data is missing/unavailable (None).
      - float value if valid non-negative finite numeric.

    Raises:
      - TypeError if input is boolean (e.g. True/False) or unconvertible type.
      - ValueError if input is non-numeric, negative (< 0.0), NaN, or Infinite.
    """
    if forecast_rain_mm is None:
        return None

    # In Python, bool is a subclass of int. Reject boolean flags as rainfall values.
    if isinstance(forecast_rain_mm, bool):
        raise TypeError(f"Invalid forecast rainfall type: boolean ({forecast_rain_mm!r}) is not permitted.")

    try:
        val = float(forecast_rain_mm)
    except (ValueError, TypeError) as e:
        raise ValueError(f"Invalid non-numeric forecast rainfall value: {forecast_rain_mm!r}") from e

    import math
    if math.isnan(val):
        raise ValueError("Invalid forecast rainfall value: NaN (Not a Number).")

    if math.isinf(val):
        raise ValueError("Invalid forecast rainfall value: Infinity.")

    if val < 0.0:
        raise ValueError(f"Invalid negative forecast rainfall value: {val:.2f} mm (rainfall cannot be negative).")

    return val


def apply_rainfall_guardrail(
    observed_stress: str,
    forecast_rain_mm: Optional[float]
) -> Tuple[str, str, bool]:
    """
    Applies rainfall policy guardrails based on observed stress (NDVI + SMAP)
    and 48-hour forecast rainfall.

    Policy Rules:
    - Observed stress (NDVI + SMAP) is NEVER modified by rainfall forecast.
    - recommended_action depends on (observed_stress, rain_48h):
        Severe Stress:
          < R1    -> "irrigate now" (guardrail not triggered)
          R1..R2  -> "irrigate lightly, rain may not suffice" (guardrail triggered)
          >= R2   -> "hold, re-check after rain" (guardrail triggered)
        Mild Stress:
          < R1    -> "schedule irrigation in 24-48h" (guardrail not triggered)
          R1..R2  -> "delay, re-check after rain" (guardrail triggered)
          >= R2   -> "hold, re-check after rain" (guardrail triggered)
        No Stress / None:
          All bands -> "no action" (guardrail not triggered)

    Thresholds:
      R1 = RAINFALL_CONFIG.R1 (5.0 mm)
      R2 = RAINFALL_CONFIG.R2 (15.0 mm)

    Returns:
      (observed_stress, recommended_action, guardrail_triggered)
    """
    valid_rain = validate_forecast_rainfall(forecast_rain_mm)
    r1 = RAINFALL_CONFIG.R1
    r2 = RAINFALL_CONFIG.R2

    if observed_stress == "No Stress":
        return observed_stress, ACTION_NO_ACTION, False

    if observed_stress not in ("Severe Stress", "Mild Stress"):
        return observed_stress, ACTION_INSUFFICIENT_DATA, False

    # Missing rain data: fall back to dry baseline (< R1)
    if valid_rain is None:
        action = ACTION_IRRIGATE_NOW if observed_stress == "Severe Stress" else ACTION_SCHEDULE_IRRIGATION
        return observed_stress, action, False

    if observed_stress == "Severe Stress":
        if valid_rain < r1:
            return observed_stress, ACTION_IRRIGATE_NOW, False
        elif valid_rain < r2:
            return observed_stress, ACTION_IRRIGATE_LIGHTLY, True
        else:
            return observed_stress, ACTION_HOLD_RECHECK, True

    else:  # Mild Stress
        if valid_rain < r1:
            return observed_stress, ACTION_SCHEDULE_IRRIGATION, False
        elif valid_rain < r2:
            return observed_stress, ACTION_DELAY_RECHECK, True
        else:
            return observed_stress, ACTION_HOLD_RECHECK, True


def generate_irrigation_advisory(
    *args,
    observed_stress: Optional[str] = None,
    final_stress: Optional[str] = None,
    recommended_action: Optional[str] = None,
    crop: Optional[str] = None,
    stage: Optional[str] = None,
    rain_48h: Optional[float] = None,
    **kwargs,
) -> str:
    """
    Generate clear plain-language irrigation advisory text based on observed stress
    and recommended action.

    Supports:
      - 5-arg positional: (observed_stress, recommended_action, crop, stage, rain_48h)
      - Legacy 4-arg positional: (observed_stress, crop, stage, rain_48h)
      - Keyword argument calls (using observed_stress or final_stress, recommended_action,
        crop, stage, rain_48h, etc.)
    Consistently incorporates growth stage where present, uses 'Mild' / 'Severe',
    and mentions 'forecast' rain.
    """
    known_actions = {
        ACTION_IRRIGATE_NOW,
        ACTION_IRRIGATE_LIGHTLY,
        ACTION_SCHEDULE_IRRIGATION,
        ACTION_DELAY_RECHECK,
        ACTION_HOLD_RECHECK,
        ACTION_NO_ACTION,
        ACTION_INSUFFICIENT_DATA,
    }

    # Resolve from keyword arguments first
    stress_val = observed_stress or final_stress
    action_val = recommended_action
    crop_val = crop
    stage_val = stage
    rain_val = rain_48h

    # Parse positional arguments if supplied
    if len(args) == 5:
        # (observed_stress, recommended_action, crop, stage, rain_48h)
        stress_val = args[0]
        action_val = args[1]
        crop_val = args[2]
        stage_val = str(args[3]) if args[3] is not None else None
        rain_val = args[4]
    elif len(args) == 4:
        stress_val = args[0]
        if args[1] in known_actions:
            # (observed_stress, recommended_action, crop, stage)
            action_val = args[1]
            crop_val = args[2]
            stage_val = str(args[3]) if args[3] is not None else None
        else:
            # Legacy: (final_stress, crop, stage, rain_48h)
            crop_val = args[1]
            stage_val = str(args[2]) if args[2] is not None else None
            rain_val = args[3]
    elif len(args) == 3:
        stress_val = args[0]
        crop_val = args[1]
        stage_val = str(args[2]) if args[2] is not None else None
    elif len(args) == 2:
        stress_val = args[0]
        if args[1] in known_actions:
            action_val = args[1]
        else:
            crop_val = args[1]
    elif len(args) == 1:
        stress_val = args[0]

    # Handle alias kwargs
    if "crop_name" in kwargs and crop_val is None:
        crop_val = kwargs["crop_name"]
    if "crop_stage" in kwargs and stage_val is None:
        stage_val = str(kwargs["crop_stage"]) if kwargs["crop_stage"] is not None else None
    if "forecast_rain_mm" in kwargs and rain_val is None:
        rain_val = kwargs["forecast_rain_mm"]
    if "rain_mm" in kwargs and rain_val is None:
        rain_val = kwargs["rain_mm"]

    # Validate rainfall
    valid_rain = validate_forecast_rainfall(rain_val)

    # Derive recommended_action if not explicitly provided or unrecognized
    if action_val is None or action_val not in known_actions:
        _, action_val, _ = apply_rainfall_guardrail(stress_val or "Unknown", valid_rain)

    crop_name = crop_val or "the crop"
    # Consistent growth-stage suffix: " at {stage} stage" if stage provided and not empty/None
    if stage_val and str(stage_val).strip() and str(stage_val).strip().lower() != "none":
        stage_suffix = f" at {stage_val} stage"
    else:
        stage_suffix = ""

    rain_str = f"{valid_rain:.1f} mm" if valid_rain is not None else "minimal"

    if action_val == ACTION_IRRIGATE_NOW:
        rain_info = f"minimal forecast rain: {rain_str}" if (valid_rain is not None and valid_rain > 0) else "no forecast rain"
        if valid_rain is None:
            rain_info = "forecast rain data unavailable"
        return (
            f"URGENT: Severe water stress detected for {crop_name}{stage_suffix}. "
            f"Immediate irrigation recommended to prevent yield loss ({rain_info})."
        )

    elif action_val == ACTION_IRRIGATE_LIGHTLY:
        return (
            f"ATTENTION: Severe water stress detected for {crop_name}{stage_suffix}. "
            f"Light irrigation recommended as {rain_str} forecast rain may not suffice."
        )

    elif action_val == ACTION_HOLD_RECHECK:
        stress_word = "Severe" if stress_val == "Severe Stress" else "Mild"
        return (
            f"MONITOR: {stress_word} water stress detected for {crop_name}{stage_suffix}, "
            f"but {rain_str} forecast rain expected. Hold irrigation and re-check after rain."
        )

    elif action_val == ACTION_SCHEDULE_IRRIGATION:
        rain_info = f"minimal forecast rain: {rain_str}" if (valid_rain is not None and valid_rain > 0) else "no forecast rain"
        if valid_rain is None:
            rain_info = "forecast rain data unavailable"
        return (
            f"ATTENTION: Mild water stress detected for {crop_name}{stage_suffix}. "
            f"Schedule regular irrigation in the next 24-48 hours ({rain_info})."
        )

    elif action_val == ACTION_DELAY_RECHECK:
        return (
            f"MONITOR: Mild water stress detected for {crop_name}{stage_suffix}. "
            f"Delay irrigation and re-check after {rain_str} forecast rain."
        )

    elif action_val == ACTION_NO_ACTION:
        rain_mention = f" ({rain_str} forecast rain)" if valid_rain is not None else ""
        return (
            f"OPTIMAL: Adequate soil moisture and healthy canopy for {crop_name}{stage_suffix}. "
            f"No action required{rain_mention}."
        )

    else:
        return "INSUFFICIENT DATA: Advisory could not be finalized due to missing sensor inputs."


def primary_ml_stress_assessment(
    rule_observed_stress: str,
    ml_result: Optional[dict] = None,
    crop_name: Optional[str] = None,
    sm_pct: Optional[float] = None,
    ndvi: Optional[float] = None,
) -> Tuple[str, str, bool, Optional[str]]:
    """
    Evaluates crop stress using the Machine Learning model as the PRIMARY predictor
    for the academic prototype.

    Core Principles:
    1. Primary Authority: When ML inference succeeds on a supported crop (Wheat), the
       ML prediction directly dictates the active stress classification.
    2. Crop Scope Transparency: The ML model is trained exclusively on CSISA Eastern India wheat.
       For unsupported crops (Cotton, Soybean, etc.), ML prediction is withheld and the system
       falls back to the rule engine with explicit labeling (RULE_FALLBACK_UNSUPPORTED_CROP).
    3. Missing Data Transparency: If required sensor inputs are missing, stale, or invalid,
       ML inference fails with MISSING_INPUTS. No data is fabricated. Fallback to rule engine
       is explicitly labeled (RULE_FALLBACK_MISSING_INPUTS).
    4. Comparative Baseline: The deterministic rule baseline is computed and recorded alongside
       the ML prediction for comparative transparency.

    Returns:
        (final_observed_stress: str, assessment_method: str, disagreement_flag: bool, disagreement_details: Optional[str])
    """
    valid_classes = {"No Stress", "Mild Stress", "Severe Stress"}

    if not ml_result or not isinstance(ml_result, dict):
        fallback_details = "ML inference result unavailable; evaluated using rule-based fallback."
        return rule_observed_stress, "RULE_FALLBACK_UNAVAILABLE", False, fallback_details

    inf_status = ml_result.get("inference_status")
    crop_supported = bool(ml_result.get("crop_supported", False))
    ml_pred = ml_result.get("predicted_class")

    # Handle Unsupported Crops: Explicit fallback to rule engine
    if inf_status == "UNSUPPORTED_CROP" or not crop_supported:
        reason = (
            f"Declared crop '{crop_name}' is not wheat. The ML model is trained exclusively on Eastern India wheat "
            f"and is not validated for '{crop_name}'. Stress assessed using rule-based fallback."
        )
        return rule_observed_stress, "RULE_FALLBACK_UNSUPPORTED_CROP", False, reason

    # Handle Missing Inputs: No data fabrication, explicit fallback
    if inf_status == "MISSING_INPUTS":
        missing_inputs = ml_result.get("missing_inputs") or ["Sentinel-2 NDVI", "SMAP Soil Moisture"]
        reason = (
            f"Required sensor inputs missing ({', '.join(missing_inputs)}). "
            f"ML inference withheld; assessed using rule-based fallback."
        )
        return rule_observed_stress, "RULE_FALLBACK_MISSING_INPUTS", False, reason

    # Handle Feature Incompatibility: Explicit fallback
    if inf_status == "FEATURE_INCOMPATIBILITY":
        reason = ml_result.get(
            "reason",
            "Feature incompatibility detected. Assessed using rule-based fallback."
        )
        return rule_observed_stress, "RULE_FALLBACK_FEATURE_INCOMPATIBILITY", False, reason

    # Handle Model Load/Dependency Failure
    if inf_status != "SUCCESS" or ml_pred not in valid_classes:
        reason = f"ML inference failed ({inf_status}): {ml_result.get('reason')}. Assessed using rule-based fallback."
        return rule_observed_stress, f"RULE_FALLBACK_{inf_status or 'ERROR'}", False, reason

    # ML INFERENCE SUCCEEDED ON SUPPORTED CROP (WHEAT) — ML IS PRIMARY PREDICTOR
    disagreement = (ml_pred != rule_observed_stress)
    probs = ml_result.get("probabilities") or {}
    prob_str = f"P(Severe)={probs.get('severe_stress', 0):.2f}, P(Mild)={probs.get('mild_stress', 0):.2f}, P(None)={probs.get('no_stress', 0):.2f}"

    if disagreement:
        details = (
            f"Primary ML Model (5-Feature Random Forest) predicted '{ml_pred}' ({prob_str}). "
            f"Deterministic rule baseline comparison was '{rule_observed_stress}'."
        )
    else:
        details = (
            f"Primary ML Model (5-Feature Random Forest) and rule-based baseline agreed on '{ml_pred}' ({prob_str})."
        )

    return ml_pred, "ML_PRIMARY_PREDICTOR", disagreement, details


def hybrid_stress_assessment(
    rule_observed_stress: str,
    ml_result: Optional[dict] = None,
    crop_name: Optional[str] = None,
    sm_pct: Optional[float] = None,
    ndvi: Optional[float] = None,
    ml_as_primary: bool = False,
) -> Tuple[str, str, bool, Optional[str]]:
    """
    Arbitrates between rule-based stress classification and ML model predictions.
    When ml_as_primary=True, delegates to primary_ml_stress_assessment.
    When ml_as_primary=False (default for legacy safety floor), runs safety floor arbitration.

    Guiding Principles:
    1. Safety Floor: Physical observations indicating Severe Stress in the rule engine
       (NDVI < 0.30 or SMAP < 15%) must NEVER be downgraded by an ML model.
    2. Crop Domain Scoping: The ML model is trained exclusively on CSISA Eastern India wheat.
       For unsupported crops (Cotton, Soybean, etc.), the rule engine remains the sole authority.
    3. Conservative Escalation: If the crop is Wheat and ML predicts Severe Stress
       under low soil moisture (< 25%), stress is conservatively elevated to prevent drought loss.
    4. Resilient Fallback: If ML inference fails or is unavailable, returns rule_observed_stress.

    Returns:
        (final_observed_stress: str, assessment_method: str, disagreement_flag: bool, disagreement_details: Optional[str])
    """
    if ml_as_primary:
        return primary_ml_stress_assessment(
            rule_observed_stress=rule_observed_stress,
            ml_result=ml_result,
            crop_name=crop_name,
            sm_pct=sm_pct,
            ndvi=ndvi,
        )
    valid_classes = {"No Stress", "Mild Stress", "Severe Stress"}
    if rule_observed_stress not in valid_classes:
        return rule_observed_stress, "RULE_ENGINE_FALLBACK", False, None

    if not ml_result or not isinstance(ml_result, dict):
        return rule_observed_stress, "RULE_ENGINE_ONLY", False, None

    inf_status = ml_result.get("inference_status")
    crop_supported = bool(ml_result.get("crop_supported", False))
    ml_pred = ml_result.get("predicted_class")

    # If ML inference did not succeed or crop is unsupported, rule engine has sole authority
    if inf_status != "SUCCESS" or not crop_supported or ml_pred not in valid_classes:
        if inf_status == "UNSUPPORTED_CROP":
            reason = f"Declared crop '{crop_name}' is not wheat. ML output is unvalidated and withheld from active advice."
            return rule_observed_stress, "RULE_ENGINE_UNSUPPORTED_CROP", False, reason
        elif inf_status == "FEATURE_INCOMPATIBILITY":
            reason = ml_result.get(
                "reason",
                "Feature incompatibility: Live inputs lack authentic seasonal precipitation. ML inference withheld."
            )
            return rule_observed_stress, "RULE_ENGINE_FEATURE_INCOMPATIBILITY", False, reason
        return rule_observed_stress, f"RULE_ENGINE_{inf_status or 'UNAVAILABLE'}", False, ml_result.get("reason")

    # Both rule engine and ML produced valid classifications for supported crop (Wheat)
    if ml_pred == rule_observed_stress:
        return rule_observed_stress, "HYBRID_CONSENSUS", False, None

    # Disagreement Case 1: Rule engine detects Severe Stress, ML detects Mild or No Stress
    # Safety Rule: NEVER downgrade physical sensor Severe Stress based on ML
    if rule_observed_stress == "Severe Stress":
        details = (
            f"Physical sensor threshold detected Severe Stress (NDVI={ndvi}, SMAP={sm_pct}%). "
            f"Retained as safety floor over ML prediction of '{ml_pred}'."
        )
        return "Severe Stress", "RULE_SAFETY_OVERRIDE", True, details

    # Disagreement Case 2: ML detects Severe Stress, Rule engine detects Mild Stress
    # Conservative Policy: If soil moisture is low-to-moderate (< 25%), conservatively elevate
    if ml_pred == "Severe Stress" and rule_observed_stress == "Mild Stress":
        conf = ml_result.get("uncalibrated_confidence", 0.0)
        details = (
            f"ML model flagged Severe Stress (P_severe={conf:.2f} >= 0.33 threshold) for Wheat. "
            f"Conservatively escalated from Mild Stress to prevent yield depression."
        )
        return "Severe Stress", "ML_CONSERVATIVE_ESCALATION", True, details

    # Disagreement Case 3: ML detects Severe Stress, Rule engine detects No Stress
    # If soil moisture is low (< 22%), escalate to Mild Stress as early warning; otherwise retain No Stress
    if ml_pred == "Severe Stress" and rule_observed_stress == "No Stress":
        if sm_pct is not None and sm_pct < 22.0:
            details = "ML flagged Severe Stress while rules indicated No Stress; soil moisture is borderline (<22%). Escalated to Mild Stress."
            return "Mild Stress", "ML_EARLY_WARNING", True, details
        details = "ML flagged Severe Stress but canopy and soil sensors confirm healthy status (>25% SM, >0.6 NDVI). Retained No Stress floor."
        return "No Stress", "RULE_SAFETY_FLOOR", True, details

    # Disagreement Case 4: ML detects Mild Stress, Rule engine detects No Stress
    # If SM is borderline (< 25%), provide Mild Stress early warning
    if ml_pred == "Mild Stress" and rule_observed_stress == "No Stress":
        if sm_pct is not None and sm_pct < 25.0:
            details = "ML flagged Mild Stress for Wheat with declining soil moisture (<25%). Escalated to Mild Stress."
            return "Mild Stress", "ML_EARLY_WARNING", True, details
        details = "ML flagged Mild Stress but sensors indicate adequate moisture. Retained No Stress."
        return "No Stress", "RULE_SAFETY_FLOOR", True, details

    # Disagreement Case 5: ML detects No Stress, Rule engine detects Mild Stress
    # Retain Mild Stress as conservative safety floor
    if ml_pred == "No Stress" and rule_observed_stress == "Mild Stress":
        details = "Rule engine detected Mild Stress from sensor thresholds; retained over ML No Stress prediction."
        return "Mild Stress", "RULE_SAFETY_FLOOR", True, details

    # Default fallback
    return rule_observed_stress, "RULE_ENGINE_FALLBACK", False, None

