#!/usr/bin/env python3
"""
KhetSense AI — Agricultural Location Validation Engine

Validates whether a farmer-selected location pin / polygon is suitable for
crop stress detection and irrigation advisory generation before executing the pipeline.

Validation Checks:
1. Spatial coordinate validity (Indian bounding box: Lat 6.0–38.0°N, Lon 68.0–98.0°E).
2. Satellite data availability & quality (Sentinel-2 scene exists, cloud coverage < 20.0%).
3. Land-cover classification (ESA WorldCover 10m / Dynamic World):
   - Cropland (class 40): Suitable for agricultural advisory.
   - Built-up / Urban (class 50): Unsuitable; low vegetation must NOT be misclassified as crop stress.
   - Bare / Sparse / Fallow (class 60): Barren or unverified; irrigation advice withheld for safety.
   - Water / Wetland / Forest: Notified and reviewed.
4. Spatial resolution suitability (Sentinel-2 10m pixel size vs. farm acreage).
5. Auxiliary data completeness (SMAP soil moisture, OpenWeather rainfall forecast).

Validation Outcomes:
- Case A: SUITABLE_CROPLAND (Proceed with full pipeline)
- Case B: LIKELY_URBAN (Withhold advisory, request farm field pin)
- Case C: BARREN_OR_UNCERTAIN (Withhold advisory, request verification of crop / fallow field)
- Case D: INSUFFICIENT_SATELLITE_DATA (Inform farmer, retry when clear satellite pass is available)
- Case E: INCOMPLETE_AUXILIARY_DATA (Suitable farm, handle missing SMAP/weather via safe fallback)
- INVALID_COORDINATES (Out of bounds or invalid GPS pin)
"""

import logging
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger("khetsense_location_validator")

# ==============================================================================
# 1. VALIDATION OUTCOME CONSTANTS
# ==============================================================================

VALIDATION_SUITABLE = "SUITABLE_CROPLAND"
VALIDATION_URBAN = "LIKELY_URBAN"
VALIDATION_BARREN_UNCERTAIN = "BARREN_OR_UNCERTAIN"
VALIDATION_INSUFFICIENT_IMAGERY = "INSUFFICIENT_SATELLITE_DATA"
VALIDATION_INCOMPLETE_AUXILIARY = "INCOMPLETE_AUXILIARY_DATA"
VALIDATION_INVALID_COORDINATES = "INVALID_COORDINATES"

ALL_VALIDATION_OUTCOMES = {
    VALIDATION_SUITABLE,
    VALIDATION_URBAN,
    VALIDATION_BARREN_UNCERTAIN,
    VALIDATION_INSUFFICIENT_IMAGERY,
    VALIDATION_INCOMPLETE_AUXILIARY,
    VALIDATION_INVALID_COORDINATES,
}

# ==============================================================================
# 2. ESA WORLDCOVER 10m LAND COVER TAXONOMY
# ==============================================================================

ESA_WORLDCOVER_CLASSES: Dict[int, str] = {
    10: "Tree cover",
    20: "Shrubland",
    30: "Grassland",
    40: "Cropland",
    50: "Built-up",
    60: "Bare / sparse vegetation",
    70: "Snow and ice",
    80: "Permanent water bodies",
    90: "Herbaceous wetland",
    95: "Mangroves",
    100: "Moss and lichen",
}

# Thresholds
MAX_CLOUD_COVER_PCT = 20.0
MIN_FARM_ACRES_FOR_10M_PIXEL = 0.05  # ~200 m² (~2 Sentinel-2 10m pixels)


# ==============================================================================
# 3. SPATIAL BOUNDING BOX CHECK
# ==============================================================================

def validate_coordinates_in_bounds(lat: float, lon: float) -> bool:
    """Checks whether coordinates fall within India's geographical bounding box."""
    if lat is None or lon is None:
        return False
    return (6.0 <= float(lat) <= 38.0) and (68.0 <= float(lon) <= 98.0)


# ==============================================================================
# 4. EARTH ENGINE ESA WORLDCOVER QUERY (OPTIONAL / GRACEFUL FALLBACK)
# ==============================================================================

def fetch_esa_worldcover_gee(farm_geom) -> Tuple[Optional[int], Optional[str], Optional[str]]:
    """
    Fetches the majority ESA WorldCover 10m land cover class over the farm geometry in Google Earth Engine.
    Returns:
        (class_code, class_name, error_message)
    """
    try:
        import ee
        # Attempt ESA WorldCover v200 (2021) or v100 (2020)
        try:
            wc = ee.ImageCollection("ESA/WorldCover/v200").first()
            if wc is None:
                wc = ee.ImageCollection("ESA/WorldCover/v100").first()
        except Exception:
            wc = ee.Image("ESA/WorldCover/v100/2020")

        if wc is None:
            return None, None, "ESA WorldCover image collection unavailable in GEE"

        map_band = wc.select("Map")
        mode_val = map_band.reduceRegion(
            reducer=ee.Reducer.mode(),
            geometry=farm_geom,
            scale=10,
            maxPixels=1e6,
        ).get("Map")

        code = mode_val.getInfo() if mode_val else None
        if code is not None:
            code_int = int(code)
            name = ESA_WORLDCOVER_CLASSES.get(code_int, f"Unknown ({code_int})")
            return code_int, name, None
        return None, None, "No land cover pixel mode returned"
    except Exception as e:
        logger.debug("GEE ESA WorldCover query not executed: %s", e)
        return None, None, str(e)


# ==============================================================================
# 5. CORE AGRICULTURAL LOCATION VALIDATOR
# ==============================================================================

def validate_agricultural_location(
    centroid_lat: float,
    centroid_lon: float,
    ee_coords: Optional[list] = None,
    farm_area_acres: Optional[float] = None,
    s2_meta: Optional[Dict[str, Any]] = None,
    s2_err: Optional[str] = None,
    mean_ndvi: Optional[float] = None,
    land_cover_class: Optional[str] = None,
    land_cover_code: Optional[int] = None,
    cloud_cover_pct: Optional[float] = None,
    has_smap: bool = True,
    has_weather: bool = True,
    farm_geom: Any = None,
) -> Dict[str, Any]:
    """
    Validates farm location suitability for agricultural monitoring and irrigation advisories.

    Returns:
        dict with keys:
            - outcome: One of VALIDATION_* constants
            - is_suitable_for_advisory: bool (True for Case A & Case E, False for Cases B, C, D)
            - land_cover_class: str
            - land_cover_code: Optional[int]
            - cloud_cover_pct: Optional[float]
            - resolution_adequate: bool
            - reason: str
            - details: dict
    """
    # 1. Geographic Coordinate Check
    if not validate_coordinates_in_bounds(centroid_lat, centroid_lon):
        return {
            "outcome": VALIDATION_INVALID_COORDINATES,
            "is_suitable_for_advisory": False,
            "land_cover_class": None,
            "land_cover_code": None,
            "cloud_cover_pct": None,
            "resolution_adequate": False,
            "reason": f"Coordinates ({centroid_lat}, {centroid_lon}) fall outside India bounding box (Lat: 6.0–38.0°N, Lon: 68.0–98.0°E).",
            "details": {"lat": centroid_lat, "lon": centroid_lon},
        }

    # 2. Resolution & Area Check
    area_acres = float(farm_area_acres) if farm_area_acres is not None else 2.47
    resolution_adequate = area_acres >= MIN_FARM_ACRES_FOR_10M_PIXEL
    res_warning = None
    if not resolution_adequate:
        res_warning = f"Farm area ({area_acres:.2f} acres) is smaller than minimum recommended for 10m Sentinel-2 pixel (~{MIN_FARM_ACRES_FOR_10M_PIXEL} acres)."

    # 3. Satellite Data Availability & Cloud Quality (Case D)
    cloud_pct = None
    if cloud_cover_pct is not None:
        try:
            cloud_pct = float(cloud_cover_pct)
        except (ValueError, TypeError):
            cloud_pct = None

    if cloud_pct is None and s2_meta:
        raw_cloud = s2_meta.get("cloud_cover_pct")
        if raw_cloud is None:
            raw_cloud = s2_meta.get("cloud_pct")
        if raw_cloud is not None:
            try:
                cloud_pct = float(raw_cloud)
            except (ValueError, TypeError):
                cloud_pct = None

    if s2_err and any(k in s2_err.lower() for k in ["no valid", "not found", "missing", "stale", "cloud-free"]):
        return {
            "outcome": VALIDATION_INSUFFICIENT_IMAGERY,
            "is_suitable_for_advisory": False,
            "land_cover_class": None,
            "land_cover_code": None,
            "cloud_cover_pct": cloud_pct,
            "resolution_adequate": resolution_adequate,
            "reason": f"No cloud-free Sentinel-2 satellite imagery found for this location within the observation window: {s2_err}",
            "details": {"s2_err": s2_err, "cloud_cover_pct": cloud_pct},
        }

    if cloud_pct is not None and cloud_pct > MAX_CLOUD_COVER_PCT:
        return {
            "outcome": VALIDATION_INSUFFICIENT_IMAGERY,
            "is_suitable_for_advisory": False,
            "land_cover_class": None,
            "land_cover_code": None,
            "cloud_cover_pct": cloud_pct,
            "resolution_adequate": resolution_adequate,
            "reason": f"Satellite scene cloud coverage ({cloud_pct:.1f}%) exceeds maximum permissible quality threshold ({MAX_CLOUD_COVER_PCT:.1f}%).",
            "details": {"cloud_cover_pct": cloud_pct, "max_allowed": MAX_CLOUD_COVER_PCT},
        }

    # 4. Land-Cover Classification (Cases B, C, A)
    resolved_code = land_cover_code
    resolved_class = land_cover_class

    # If not explicitly provided, attempt GEE query if farm_geom is provided
    if resolved_class is None and farm_geom is not None:
        c_code, c_name, g_err = fetch_esa_worldcover_gee(farm_geom)
        if c_code is not None:
            resolved_code = c_code
            resolved_class = c_name

    # Check for Built-up / Urban (Case B)
    if resolved_code == 50 or (resolved_class and any(u in resolved_class.lower() for u in ["built", "urban", "city", "settlement"])):
        return {
            "outcome": VALIDATION_URBAN,
            "is_suitable_for_advisory": False,
            "land_cover_class": resolved_class or "Built-up",
            "land_cover_code": resolved_code or 50,
            "cloud_cover_pct": cloud_pct,
            "resolution_adequate": resolution_adequate,
            "reason": "Location classified as built-up or urban land cover. Low vegetation in urban areas must not be treated as crop stress.",
            "details": {"land_cover_class": resolved_class, "land_cover_code": resolved_code},
        }

    # Check for Bare / Fallow / Sparse / Non-vegetated (Case C)
    if resolved_code == 60 or (resolved_class and any(b in resolved_class.lower() for b in ["bare", "sparse", "barren", "fallow"])):
        return {
            "outcome": VALIDATION_BARREN_UNCERTAIN,
            "is_suitable_for_advisory": False,
            "land_cover_class": resolved_class or "Bare / sparse vegetation",
            "land_cover_code": resolved_code or 60,
            "cloud_cover_pct": cloud_pct,
            "resolution_adequate": resolution_adequate,
            "reason": "Location classified as bare, fallow, or sparse vegetation. Crop presence cannot be verified from satellite data alone.",
            "details": {"land_cover_class": resolved_class, "land_cover_code": resolved_code, "mean_ndvi": mean_ndvi},
        }

    # If external land-cover was not provided/resolved, do NOT automatically classify as cropland based only on NDVI
    if resolved_class is None and resolved_code is None:
        if mean_ndvi is not None and mean_ndvi < 0.10:
            return {
                "outcome": VALIDATION_BARREN_UNCERTAIN,
                "is_suitable_for_advisory": False,
                "land_cover_class": "Uncertain / Very Low Vegetation (NDVI < 0.10)",
                "land_cover_code": None,
                "cloud_cover_pct": cloud_pct,
                "resolution_adequate": resolution_adequate,
                "reason": "Location exhibits negligible vegetation signal (NDVI < 0.10). Field may be fallow, harvested, or uncultivated.",
                "details": {"mean_ndvi": mean_ndvi},
            }
        return {
            "outcome": VALIDATION_BARREN_UNCERTAIN,
            "is_suitable_for_advisory": False,
            "land_cover_class": "Uncertain / Land Cover Unavailable",
            "land_cover_code": None,
            "cloud_cover_pct": cloud_pct,
            "resolution_adequate": resolution_adequate,
            "reason": (
                "Reliable land-cover classification is unavailable for this location. "
                "Cropland cannot be verified based on NDVI alone, so irrigation advisory is withheld for safety."
            ),
            "details": {"mean_ndvi": mean_ndvi, "land_cover_available": False},
        }

    # If external land-cover was resolved, verify that it is actually Cropland
    is_cropland = (resolved_code == 40) or (
        resolved_class is not None and "crop" in resolved_class.lower()
    )
    if not is_cropland:
        return {
            "outcome": VALIDATION_BARREN_UNCERTAIN,
            "is_suitable_for_advisory": False,
            "land_cover_class": resolved_class or f"Non-cropland ({resolved_code})",
            "land_cover_code": resolved_code,
            "cloud_cover_pct": cloud_pct,
            "resolution_adequate": resolution_adequate,
            "reason": f"Location classified as {resolved_class or 'non-cropland'}. Agricultural irrigation advisory requires verified cropland.",
            "details": {"land_cover_class": resolved_class, "land_cover_code": resolved_code, "mean_ndvi": mean_ndvi},
        }

    final_land_cover = resolved_class or "Cropland"
    final_code = resolved_code if resolved_code is not None else 40

    # 5. Auxiliary Data Check (Case E vs Case A)
    if not has_smap or not has_weather:
        missing_sources = []
        if not has_smap:
            missing_sources.append("SMAP Soil Moisture")
        if not has_weather:
            missing_sources.append("OpenWeather Forecast")
        return {
            "outcome": VALIDATION_INCOMPLETE_AUXILIARY,
            "is_suitable_for_advisory": True,  # Pipeline can proceed using safe fallback rules
            "land_cover_class": final_land_cover,
            "land_cover_code": final_code,
            "cloud_cover_pct": cloud_pct,
            "resolution_adequate": resolution_adequate,
            "reason": f"Valid agricultural location, but auxiliary data is incomplete: {', '.join(missing_sources)}. Advisory will use safe fallback rules.",
            "details": {
                "has_smap": has_smap,
                "has_weather": has_weather,
                "missing": missing_sources,
                "res_warning": res_warning,
            },
        }

    # Case A: Suitable Agricultural Location with Sufficient Data
    return {
        "outcome": VALIDATION_SUITABLE,
        "is_suitable_for_advisory": True,
        "land_cover_class": final_land_cover,
        "land_cover_code": final_code,
        "cloud_cover_pct": cloud_pct,
        "resolution_adequate": resolution_adequate,
        "reason": "Location confirmed as suitable agricultural land with adequate satellite quality and complete auxiliary data.",
        "details": {
            "cloud_cover_pct": cloud_pct,
            "farm_area_acres": area_acres,
            "res_warning": res_warning,
        },
    }
