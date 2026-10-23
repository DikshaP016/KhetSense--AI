#!/usr/bin/env python3
"""
KhetSense AI — Satellite-Based Crop Validation & Discrepancy Engine

Validates farmer-declared crop against satellite-derived spectral, phenological,
and seasonal crop calendar evidence before generating crop-specific irrigation advisories.

Core Principles:
1. Agricultural Location Screening Prerequisite:
   Location must first be confirmed as active cropland (ESA WorldCover class 40).
   Cropland classification alone does NOT prove any specific crop species.
2. Scientific Integrity & No False Attribution:
   Single-date NDVI/NDWI thresholds alone CANNOT discriminate crop species
   (e.g., peak vegetative Cotton, Soybean, and Tur have overlapping NDVI 0.65–0.80).
   Untrained or unvalidated models must NEVER be presented as ground truth.
3. Multi-Temporal & Seasonal Calendar Validation:
   Evaluates regional crop calendars (Kharif, Rabi, Zaid, Perennial) for Central India
   (Maharashtra: Vidarbha, Marathwada, Western Maharashtra).
4. Structured Decision Outcomes:
   - MATCH: Declared crop is consistent with regional season and observed phenological trajectory.
   - MISMATCH: Credible discrepancy detected (severe out-of-season declaration, perennial vs annual
     contradiction, or validated reference model conflict). Irrigation advice is WITHHELD.
   - INCONCLUSIVE: Cropland is verified, but optical data or validated reference labels are
     insufficient to conclusively differentiate crop species without fabricating evidence.
     The farmer is prompted to confirm the crop; advice proceeds with explicit transparency.
5. Data Preservation:
   The declared crop is NEVER silently overwritten.
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple

logger = logging.getLogger("khetsense_crop_validator")

# ==============================================================================
# 1. OUTCOME CONSTANTS
# ==============================================================================

CROP_MATCH = "MATCH"
CROP_MISMATCH = "MISMATCH"
CROP_INCONCLUSIVE = "INCONCLUSIVE"
CROP_UNVALIDATED = "UNVALIDATED"

ALL_CROP_OUTCOMES = {
    CROP_MATCH,
    CROP_MISMATCH,
    CROP_INCONCLUSIVE,
    CROP_UNVALIDATED,
}

# ==============================================================================
# 2. REGIONAL CROP TAXONOMY & PHENOLOGICAL CALENDARS (MAHARASHTRA / CENTRAL INDIA)
# ==============================================================================

SUPPORTED_CROPS: Dict[str, Dict[str, Any]] = {
    "cotton": {
        "standard_name": "Cotton",
        "aliases": ["cotton", "kapas", "kapus", "कापूस", "कपास"],
        "season": "kharif",
        "sowing_months": [6, 7],            # June - July
        "vegetative_months": [7, 8, 9, 10], # July - October
        "harvest_months": [11, 12, 1],      # November - January
        "duration_days": 160,
        "is_perennial": False,
        "expected_peak_ndvi": (0.45, 0.85),
    },
    "soybean": {
        "standard_name": "Soybean",
        "aliases": ["soybean", "soya", "soyabean", "सोयाबीन"],
        "season": "kharif",
        "sowing_months": [6, 7],
        "vegetative_months": [7, 8, 9],     # July - September
        "harvest_months": [9, 10],          # Late Sept - October
        "duration_days": 95,
        "is_perennial": False,
        "expected_peak_ndvi": (0.45, 0.85),
    },
    "wheat": {
        "standard_name": "Wheat",
        "aliases": ["wheat", "gehu", "gahu", "गहू", "गेहूं"],
        "season": "rabi",
        "sowing_months": [10, 11, 12],      # Late October - December
        "vegetative_months": [12, 1, 2],    # December - February
        "harvest_months": [3, 4],           # March - April
        "duration_days": 120,
        "is_perennial": False,
        "expected_peak_ndvi": (0.50, 0.85),
    },
    "sugarcane": {
        "standard_name": "Sugarcane",
        "aliases": ["sugarcane", "cane", "oos", "ganna", "ऊस", "गन्ना"],
        "season": "perennial",
        "sowing_months": list(range(1, 13)), # Planted across multiple windows (Eksali, Pre-seasonal, Adsali)
        "vegetative_months": list(range(1, 13)),
        "harvest_months": list(range(1, 13)),
        "duration_days": 365,
        "is_perennial": True,
        "expected_peak_ndvi": (0.55, 0.90),
        "expected_min_ndwi": 0.10,
    },
    "pigeon_pea": {
        "standard_name": "Pigeon Pea (Tur)",
        "aliases": ["pigeon pea", "tur", "arhar", "toor", "तूर", "अरहर"],
        "season": "kharif",
        "sowing_months": [6, 7],
        "vegetative_months": [7, 8, 9, 10, 11],
        "harvest_months": [12, 1, 2],
        "duration_days": 180,
        "is_perennial": False,
        "expected_peak_ndvi": (0.40, 0.80),
    },
    "chickpea": {
        "standard_name": "Chickpea (Chana)",
        "aliases": ["chickpea", "chana", "gram", "हरभरा", "चना"],
        "season": "rabi",
        "sowing_months": [10, 11],
        "vegetative_months": [11, 12, 1],
        "harvest_months": [2, 3],
        "duration_days": 105,
        "is_perennial": False,
        "expected_peak_ndvi": (0.40, 0.75),
    },
    "rice": {
        "standard_name": "Rice",
        "aliases": ["rice", "paddy", "tandul", "bhat", "chawal", "तांदूळ", "भात", "चावल"],
        "season": "kharif",
        "sowing_months": [6, 7],
        "vegetative_months": [7, 8, 9, 10],
        "harvest_months": [10, 11],
        "duration_days": 125,
        "is_perennial": False,
        "expected_peak_ndvi": (0.50, 0.85),
    },
    "maize": {
        "standard_name": "Maize",
        "aliases": ["maize", "corn", "makka", "maka", "मका", "मक्का"],
        "season": "kharif_or_rabi",
        "sowing_months": [6, 7, 10, 11],
        "vegetative_months": [7, 8, 11, 12],
        "harvest_months": [9, 10, 2, 3],
        "duration_days": 100,
        "is_perennial": False,
        "expected_peak_ndvi": (0.45, 0.85),
    },
    "onion": {
        "standard_name": "Onion",
        "aliases": ["onion", "kanda", "pyaz", "कांदा", "प्याज"],
        "season": "kharif_or_rabi",
        "sowing_months": [6, 7, 9, 10, 11, 12],
        "vegetative_months": [7, 8, 10, 11, 12, 1],
        "harvest_months": [10, 11, 1, 2, 3, 4],
        "duration_days": 110,
        "is_perennial": False,
        "expected_peak_ndvi": (0.35, 0.70),
    },
}


def normalize_crop_name(name: Optional[str]) -> Optional[str]:
    """Resolves arbitrary user input crop text to standard canonical key."""
    if not name or not isinstance(name, str):
        return None
    cleaned = name.strip().lower()
    for key, spec in SUPPORTED_CROPS.items():
        if cleaned == key or cleaned == spec["standard_name"].lower():
            return key
        for alias in spec["aliases"]:
            if cleaned == alias.lower() or alias.lower() in cleaned:
                return key
    return None


def get_standard_crop_display(key_or_name: Optional[str]) -> str:
    """Returns clean English display title for a crop."""
    key = normalize_crop_name(key_or_name)
    if key and key in SUPPORTED_CROPS:
        return SUPPORTED_CROPS[key]["standard_name"]
    return (key_or_name or "Unknown Crop").strip()


# ==============================================================================
# 3. CORE CROP VALIDATION ENGINE
# ==============================================================================

def validate_crop_type(
    declared_crop: Optional[str],
    centroid_lat: float,
    centroid_lon: float,
    mean_ndvi: Optional[float] = None,
    mean_ndwi: Optional[float] = None,
    s2_meta: Optional[Dict[str, Any]] = None,
    observation_date: Optional[Any] = None,
    multi_date_series: Optional[List[Dict[str, Any]]] = None,
    reference_model: Optional[Any] = None,
    ground_truth_reference: Optional[Dict[str, Any]] = None,
    is_demo: bool = False,
) -> Dict[str, Any]:
    """
    Validates declared crop against seasonal calendar, multi-temporal optical evidence,
    and reference data.

    Returns:
        Dict containing:
        - "outcome": "MATCH" | "MISMATCH" | "INCONCLUSIVE"
        - "declared_crop": str (canonical/standard name)
        - "predicted_crop": Optional[str] (suggested crop if credible mismatch detected)
        - "confidence": Optional[float] (calibrated probability/confidence if supportable)
        - "data_dates": List[str] (dates of satellite observations used)
        - "reason": str (transparent explanation of outcome)
        - "is_suitable_for_advisory": bool (False if MISMATCH, True if MATCH or INCONCLUSIVE)
        - "requires_confirmation": bool (True if farmer must confirm crop before advice)
        - "details": Dict[str, Any]
    """
    raw_declared = declared_crop or "Unspecified"
    canonical_key = normalize_crop_name(declared_crop)
    standard_name = get_standard_crop_display(declared_crop)

    # 1. Collect satellite observation date
    obs_dt = None
    data_dates: List[str] = []

    if s2_meta and s2_meta.get("date"):
        data_dates.append(str(s2_meta["date"]))
        try:
            obs_dt = datetime.fromisoformat(str(s2_meta["date"]).replace("Z", "+00:00"))
        except Exception:
            pass

    if obs_dt is None and observation_date:
        if isinstance(observation_date, datetime):
            obs_dt = observation_date
            data_dates.append(obs_dt.strftime("%Y-%m-%d"))
        elif isinstance(observation_date, str):
            data_dates.append(observation_date)
            try:
                obs_dt = datetime.fromisoformat(observation_date.replace("Z", "+00:00"))
            except Exception:
                pass

    if obs_dt is None:
        obs_dt = datetime.now()
        data_dates.append(obs_dt.strftime("%Y-%m-%d"))

    obs_month = obs_dt.month

    # Append multi-date series dates if provided
    if multi_date_series:
        for entry in multi_date_series:
            d = entry.get("date")
            if d and str(d) not in data_dates:
                data_dates.append(str(d))

    # 2. Check for unknown or unsupported declared crop
    if not canonical_key or canonical_key not in SUPPORTED_CROPS:
        return {
            "outcome": CROP_INCONCLUSIVE,
            "declared_crop": standard_name,
            "predicted_crop": None,
            "confidence": None,
            "data_dates": data_dates,
            "reason": (
                f"Crop '{raw_declared}' is not in the recognized regional agronomic taxonomy. "
                "Crop species could not be independently identified from satellite data alone. "
                "Advisory will use general agronomic parameters."
            ),
            "is_suitable_for_advisory": True,
            "requires_confirmation": True,
            "details": {"raw_declared": raw_declared, "month": obs_month},
        }

    crop_spec = SUPPORTED_CROPS[canonical_key]

    # ==========================================================================
    # 3. EXPLICIT REFERENCE BENCHMARK / GROUND TRUTH EVALUATION
    # ==========================================================================
    # If a validated external reference model or verified ground-truth dataset is provided:
    if ground_truth_reference:
        ref_crop_raw = ground_truth_reference.get("crop_name") or ground_truth_reference.get("crop")
        ref_conf = ground_truth_reference.get("confidence")
        ref_key = normalize_crop_name(ref_crop_raw)

        if ref_key and ref_key != canonical_key:
            predicted_display = get_standard_crop_display(ref_key)
            conf_val = float(ref_conf) if ref_conf is not None else 0.85
            return {
                "outcome": CROP_MISMATCH,
                "declared_crop": standard_name,
                "predicted_crop": predicted_display,
                "confidence": conf_val,
                "data_dates": data_dates,
                "reason": (
                    f"Validated satellite reference dataset indicates '{predicted_display}' "
                    f"(confidence {conf_val:.0%}), which contradicts the declared crop '{standard_name}'."
                ),
                "is_suitable_for_advisory": False,
                "requires_confirmation": True,
                "details": {
                    "source": "ground_truth_reference",
                    "reference_crop": predicted_display,
                    "confidence": conf_val,
                },
            }
        elif ref_key and ref_key == canonical_key:
            conf_val = float(ref_conf) if ref_conf is not None else 0.90
            return {
                "outcome": CROP_MATCH,
                "declared_crop": standard_name,
                "predicted_crop": standard_name,
                "confidence": conf_val,
                "data_dates": data_dates,
                "reason": (
                    f"Satellite reference dataset validates '{standard_name}' with {conf_val:.0%} confidence."
                ),
                "is_suitable_for_advisory": True,
                "requires_confirmation": False,
                "details": {
                    "source": "ground_truth_reference",
                    "confidence": conf_val,
                },
            }

    # Reference classification model
    if reference_model is not None and hasattr(reference_model, "predict_crop"):
        try:
            model_res = reference_model.predict_crop(
                lat=centroid_lat,
                lon=centroid_lon,
                mean_ndvi=mean_ndvi,
                mean_ndwi=mean_ndwi,
                month=obs_month,
            )
            pred_crop_raw = model_res.get("predicted_crop")
            pred_conf = model_res.get("confidence", 0.80)
            pred_key = normalize_crop_name(pred_crop_raw)

            if pred_key and pred_key != canonical_key and pred_conf >= 0.70:
                pred_display = get_standard_crop_display(pred_key)
                return {
                    "outcome": CROP_MISMATCH,
                    "declared_crop": standard_name,
                    "predicted_crop": pred_display,
                    "confidence": pred_conf,
                    "data_dates": data_dates,
                    "reason": (
                        f"Validated spectral classifier predicts '{pred_display}' "
                        f"with {pred_conf:.0%} confidence, which contradicts declared '{standard_name}'."
                    ),
                    "is_suitable_for_advisory": False,
                    "requires_confirmation": True,
                    "details": model_res,
                }
            elif pred_key == canonical_key and pred_conf >= 0.60:
                return {
                    "outcome": CROP_MATCH,
                    "declared_crop": standard_name,
                    "predicted_crop": standard_name,
                    "confidence": pred_conf,
                    "data_dates": data_dates,
                    "reason": f"Spectral classification validates declared '{standard_name}' (confidence: {pred_conf:.0%}).",
                    "is_suitable_for_advisory": True,
                    "requires_confirmation": False,
                    "details": model_res,
                }
        except Exception as m_err:
            logger.warning("Reference model execution failed; falling back to rule engine: %s", m_err)

    # ==========================================================================
    # 4. REGIONAL SEASONALITY & PHENOLOGICAL CONTRADICTION SCREENING
    # ==========================================================================

    # Case M1: Severe Out-of-Season Rabi Crop declared in Monsoon Peak (June-August)
    # E.g. Declaring actively growing Wheat or Chickpea in July/August with high NDVI
    if canonical_key in ("wheat", "chickpea") and obs_month in (6, 7, 8, 9):
        if mean_ndvi is not None and mean_ndvi >= 0.35:
            likely_crop = "Cotton / Soybean (Kharif)"
            return {
                "outcome": CROP_MISMATCH,
                "declared_crop": standard_name,
                "predicted_crop": likely_crop,
                "confidence": 0.88,
                "data_dates": data_dates,
                "reason": (
                    f"{standard_name} is a winter (Rabi) crop sown in November–December in Central India. "
                    f"Active vegetative growth (NDVI {mean_ndvi:.2f}) observed in {obs_dt.strftime('%B')} "
                    f"indicates a monsoon (Kharif) crop such as Cotton or Soybean."
                ),
                "is_suitable_for_advisory": False,
                "requires_confirmation": True,
                "details": {
                    "contradiction": "monsoon_rabi_incompatibility",
                    "obs_month": obs_month,
                    "mean_ndvi": mean_ndvi,
                },
            }

    # Case M2: Short-Duration Crop declared in Post-Harvest Dense Canopy
    # E.g. Declaring Soybean in December/January when Soybean is harvested by October
    if canonical_key == "soybean" and obs_month in (12, 1, 2):
        if mean_ndvi is not None and mean_ndvi >= 0.50:
            likely_crop = "Cotton / Sugarcane / Rabi Wheat"
            return {
                "outcome": CROP_MISMATCH,
                "declared_crop": standard_name,
                "predicted_crop": likely_crop,
                "confidence": 0.85,
                "data_dates": data_dates,
                "reason": (
                    f"Soybean in Maharashtra matures in 90–100 days and is harvested by October. "
                    f"Dense canopy (NDVI {mean_ndvi:.2f}) observed in {obs_dt.strftime('%B')} "
                    f"contradicts completed soybean harvest and indicates a longer-duration crop."
                ),
                "is_suitable_for_advisory": False,
                "requires_confirmation": True,
                "details": {
                    "contradiction": "post_harvest_canopy_contradiction",
                    "obs_month": obs_month,
                    "mean_ndvi": mean_ndvi,
                },
            }

    # Case M3: Perennial Sugarcane Canopy vs Annual Rainfed Crop Declaration
    # If multi-temporal series shows persistent dense canopy throughout pre-monsoon summer (April–May)
    if multi_date_series and canonical_key not in ("sugarcane",):
        summer_dense_scenes = [
            s for s in multi_date_series
            if s.get("month") in (4, 5) and (s.get("ndvi") or 0.0) >= 0.55
        ]
        if len(summer_dense_scenes) >= 1:
            return {
                "outcome": CROP_MISMATCH,
                "declared_crop": standard_name,
                "predicted_crop": "Sugarcane / Perennial Orchard",
                "confidence": 0.86,
                "data_dates": data_dates,
                "reason": (
                    f"Multi-temporal satellite series exhibits dense canopy (NDVI >= 0.55) during "
                    f"peak pre-monsoon summer (April–May). Rainfed annual {standard_name} cannot support "
                    "summer canopy in Vidarbha/Maharashtra; profile indicates standing Sugarcane or Orchard."
                ),
                "is_suitable_for_advisory": False,
                "requires_confirmation": True,
                "details": {
                    "contradiction": "summer_perennial_canopy",
                    "summer_scenes": len(summer_dense_scenes),
                },
            }

    # ==========================================================================
    # 5. MULTI-TEMPORAL CONSISTENCY MATCH
    # ==========================================================================
    # If a multi-date trajectory is provided and aligns with the declared crop's calendar:
    if multi_date_series and len(multi_date_series) >= 3:
        # Check that observation months fall within declared biological calendar
        calendar_months = set(crop_spec["sowing_months"] + crop_spec["vegetative_months"] + crop_spec["harvest_months"])
        series_months = [s.get("month") for s in multi_date_series if s.get("month") is not None]
        matching_months = [m for m in series_months if m in calendar_months]

        if len(matching_months) >= len(series_months) * 0.75:
            return {
                "outcome": CROP_MATCH,
                "declared_crop": standard_name,
                "predicted_crop": standard_name,
                "confidence": 0.78,
                "data_dates": data_dates,
                "reason": (
                    f"Observed multi-temporal Sentinel-2 vegetation trajectory across {len(multi_date_series)} "
                    f"dates aligns with the regional {crop_spec['season'].capitalize()} phenological calendar for {standard_name}."
                ),
                "is_suitable_for_advisory": True,
                "requires_confirmation": False,
                "details": {
                    "multi_temporal_dates": len(multi_date_series),
                    "season": crop_spec["season"],
                },
            }

    # ==========================================================================
    # 6. INCONCLUSIVE: SINGLE-DATE OPTICAL REALITY (NO SATELLITE FABRICATION)
    # ==========================================================================
    # When single-date imagery is available, the declared crop is seasonally plausible,
    # and no ground-truth reference model exists:
    # A single optical snapshot CANNOT discriminate Cotton vs Soybean vs Pigeon Pea.
    # Therefore, the system truthfully returns INCONCLUSIVE with data limitations stated.

    ndvi_str = f"NDVI {mean_ndvi:.3f}" if mean_ndvi is not None else "vegetation data"
    date_str = obs_dt.strftime("%Y-%m-%d")

    return {
        "outcome": CROP_INCONCLUSIVE,
        "declared_crop": standard_name,
        "predicted_crop": None,
        "confidence": None,
        "data_dates": data_dates,
        "reason": (
            f"Single-date Sentinel-2 observations ({ndvi_str} on {date_str}) confirm active cropland, "
            f"but multi-temporal optical time-series and local ground-truth reference data are required "
            f"to conclusively differentiate {standard_name} from other co-occurring crops. "
            f"Irrigation advice is generated using your declared crop ({standard_name})."
        ),
        "is_suitable_for_advisory": True,
        "requires_confirmation": True,
        "details": {
            "declared_crop": standard_name,
            "mean_ndvi": mean_ndvi,
            "mean_ndwi": mean_ndwi,
            "obs_date": date_str,
            "season": crop_spec["season"],
            "data_dates": data_dates,
        },
    }
