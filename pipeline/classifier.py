#!/usr/bin/env python3
"""
KhetSense AI — Decision Engine & Stress Classification Rules
Contains core logic for:
1. NDVI vegetation vigor stress classification.
2. Soil moisture (SMAP 9-km) stress classification.
3. Severity comparison (worst-case heuristic).
4. 48-hour rainfall guardrail application.
5. Plain-language irrigation advisory text generation.
"""

from typing import Optional, Tuple


def classify_ndvi_stress(ndvi: Optional[float]) -> str:
    """
    NDVI Stress Thresholds:
      > 0.6     -> No Stress
      0.3 - 0.6 -> Mild Stress
      < 0.3     -> Severe Stress
    """
    if ndvi is None:
        return "Unknown"
    if ndvi > 0.6:
        return "No Stress"
    elif ndvi >= 0.3:
        return "Mild Stress"
    else:
        return "Severe Stress"


def classify_soil_moisture_stress(sm_pct: Optional[float]) -> str:
    """
    Soil Moisture Stress Thresholds (% volumetric):
      > 25%     -> No Stress
      15% - 25% -> Mild Stress
      < 15%     -> Severe Stress
    """
    if sm_pct is None:
        return "Unknown"
    if sm_pct > 25.0:
        return "No Stress"
    elif sm_pct >= 15.0:
        return "Mild Stress"
    else:
        return "Severe Stress"


def get_more_severe(cat1: str, cat2: str) -> str:
    """
    Return the more severe of two stress classifications.
    Ranking: Severe Stress (3) > Mild Stress (2) > No Stress (1) > Unknown (0).
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


def apply_rainfall_guardrail(
    preliminary_stress: str,
    forecast_rain_mm: Optional[float]
) -> Tuple[str, str]:
    """
    Rainfall Guardrail Logic:
    If total forecast rainfall > 5 mm within 48 hours:
      - Severe Stress -> Mild Stress
      - Mild Stress   -> No Stress
      - No Stress     -> No Stress
    """
    if forecast_rain_mm is None:
        return preliminary_stress, "Guardrail Skipped (Rainfall forecast data unavailable)"

    if forecast_rain_mm > 5.0:
        if preliminary_stress == "Severe Stress":
            final = "Mild Stress"
        elif preliminary_stress == "Mild Stress":
            final = "No Stress"
        else:
            final = "No Stress"
        status = (
            f"Triggered (> 5.0 mm forecast: {forecast_rain_mm:.2f} mm predicted. "
            f"Downgraded {preliminary_stress} -> {final})"
        )
        return final, status
    else:
        status = f"Not Triggered ({forecast_rain_mm:.2f} mm <= 5.0 mm threshold)"
        return preliminary_stress, status


def generate_irrigation_advisory(
    final_stress: str,
    crop: str,
    stage: str,
    rain_48h: Optional[float]
) -> str:
    """
    Generate clear plain-language irrigation advisory based on classification.
    """
    if final_stress == "Severe Stress":
        return (
            f"URGENT: High water stress detected for {crop} at {stage} stage. "
            "Immediate irrigation recommended to prevent yield loss."
        )
    elif final_stress == "Mild Stress":
        if rain_48h is not None and rain_48h > 2.0:
            return (
                f"ATTENTION: Moderate water stress detected for {crop}. "
                f"Light irrigation recommended, monitoring incoming {rain_48h:.1f} mm rain."
            )
        else:
            return (
                f"ATTENTION: Moderate water stress detected for {crop} at {stage} stage. "
                "Schedule regular irrigation in the next 24-48 hours."
            )
    elif final_stress == "No Stress":
        return (
            f"OPTIMAL: Adequate soil moisture and healthy canopy for {crop}. "
            "No immediate irrigation required."
        )
    else:
        return "INSUFFICIENT DATA: Advisory could not be finalized due to missing sensor inputs."
