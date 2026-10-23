#!/usr/bin/env python3
"""
KhetSense AI — Standalone Pipeline Test Script
Step 3 Implementation:
- Authenticates to Google Earth Engine via service account (credentials/ee-key.json)
- Fetches latest Sentinel-2 SR Harmonized scene (<20% cloud cover) for test farm polygon
- Calculates mean NDVI and mean NDWI (Gao: B8 & B11)
- Authenticates to NASA Earthdata using credentials in .env and queries latest SMAP SPL3SMP_E granule
- Fetches latest SMAP SPL3SMP_E surface soil moisture over the polygon
- Fetches 48-hour rainfall forecast from OpenWeather API for polygon centroid
- Applies KhetSense guardrail logic and stress classification rules
- Displays clear farm status, sensor metrics, and irrigation advisory
"""

import os
import sys
import json
import math
import logging
import threading
import requests
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from typing import Optional, Dict, Any, List
import time
import ee
import psycopg2

from common.config import RAINFALL_CONFIG, FRESHNESS_CONFIG, is_crop_validation_enabled
from common.utils import sanitize_sensor_float

# Configure module logger
pipeline_logger = logging.getLogger("khetsense_pipeline")

# In-flight pipeline deduplication tracking
_ACTIVE_PIPELINE_RUNS = set()
_ACTIVE_PIPELINE_LOCK = threading.Lock()

# Advisory delivery deduplication tracking: maps farm_id -> last_delivery_timestamp
_DELIVERED_ADVISORIES: Dict[int, float] = {}
_DELIVERED_ADVISORIES_LOCK = threading.Lock()
ADVISORY_DELIVERY_COOLDOWN_SECONDS: float = 300.0  # 5-minute cooldown to prevent duplicate messages


def is_pipeline_running(farm_id: int) -> bool:
    """Checks whether the advisory pipeline is actively executing for the given farm_id."""
    with _ACTIVE_PIPELINE_LOCK:
        return farm_id in _ACTIVE_PIPELINE_RUNS



# Ensure UTF-8 output encoding on Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


# ==============================================================================
# 1. CONFIGURATION & TEST FARM PARAMETERS
# ==============================================================================

# Find project root relative to this script and ensure it is on sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Load environment variables
ENV_PATH = os.path.join(PROJECT_ROOT, ".env")
load_dotenv(ENV_PATH)

# Earth Engine Service Account Key
EE_KEY_PATH = os.path.join(PROJECT_ROOT, "credentials", "ee-key.json")
if not os.path.exists(EE_KEY_PATH):
    alt_key = os.path.join("credentials", "ee-key.json")
    if os.path.exists(alt_key):
        EE_KEY_PATH = alt_key

# Test Farm Defaults (Fallback)
DEFAULT_FARM_LOCATION = "Akola district, Maharashtra, India"
DEFAULT_CROP = "Cotton"
CROP_GROWTH_STAGE = "Vegetative / Flowering"


def get_farm_from_database(farm_id=1, db_url=None):
    """
    Retrieve farm metadata and PostGIS polygon from Supabase PostgreSQL.
    Converts coordinates to the format expected by the pipeline.
    """
    url = db_url or os.getenv("DATABASE_URL")
    if not url:
        raise ValueError("DATABASE_URL is not set in environment.")

    conn = psycopg2.connect(url)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    id,
                    farmer_name,
                    mobile_number,
                    village,
                    district,
                    state,
                    preferred_language,
                    crop_name,
                    farm_area,
                    farm_area_unit,
                    ST_AsGeoJSON(polygon) AS geojson,
                    ST_IsValid(polygon) AS is_valid,
                    ST_SRID(polygon) AS srid,
                    ST_X(ST_Centroid(polygon)) AS centroid_lon,
                    ST_Y(ST_Centroid(polygon)) AS centroid_lat,
                    ST_NPoints(polygon) AS n_points
                FROM farms
                WHERE id = %s;
            """, (farm_id,))
            row = cur.fetchone()
            if not row:
                raise ValueError(f"Farm with ID {farm_id} not found in database.")

            (
                f_id, f_name, f_mobile, f_village, f_district, f_state,
                f_lang, f_crop, f_area, f_area_unit,
                geojson_str, is_valid, srid, c_lon, c_lat, n_points
            ) = row

            geojson_data = json.loads(geojson_str)
            ee_coords = geojson_data["coordinates"][0]
            poly_lat_lon = [[pt[1], pt[0]] for pt in ee_coords[:-1]]

            return {
                "id": f_id,
                "farmer_name": f_name,
                "mobile_number": f_mobile,
                "village": f_village,
                "district": f_district,
                "state": f_state,
                "preferred_language": f_lang,
                "crop_name": f_crop,
                "farm_area": f_area,
                "farm_area_unit": f_area_unit,
                "ee_coords": ee_coords,
                "polygon_lat_lon": poly_lat_lon,
                "centroid_lat": c_lat,
                "centroid_lon": c_lon,
                "is_valid": is_valid,
                "srid": srid,
                "n_points": n_points,
            }
    finally:
        conn.close()


def save_advisory_to_database(
    farm_id,
    stress_level,
    recommendation,
    ndvi=None,
    ndwi=None,
    soil_moisture=None,
    rainfall_48h=None,
    crop_stage=None,
    observed_stress=None,
    rain_forecast_mm=None,
    guardrail_triggered=None,
    recommended_action=None,
    sentinel_scene_date=None,
    smap_obs_date=None,
    db_url=None,
    validation_status=None,
    land_cover_class=None,
):
    """
    Save computed advisory and audit input indices to Supabase PostgreSQL.
    Stores input metrics (NDVI, NDWI, SMAP soil moisture, rainfall) and
    provenance columns (observed_stress, recommended_action, scene dates,
    validation_status, land_cover_class).
    Dynamically checks table schema so it works seamlessly before and after Migrations 003 and 005.
    """
    if not db_url:
        db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL is not set in environment.")

    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            # Check which migration columns exist in the advisories table
            cur.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'advisories'
                  AND column_name IN ('recommended_action', 'validation_status');
            """)
            existing_cols = {row[0] for row in cur.fetchall()}
            has_003_columns = 'recommended_action' in existing_cols
            has_005_columns = 'validation_status' in existing_cols

            # Resolve validation_status: if explicitly provided (e.g. failure outcome,
            # or INCOMPLETE_AUXILIARY_DATA, or SUITABLE_CROPLAND), use it.
            # When no outcome is specified (e.g. legacy/unvalidated callers),
            # mark as UNVALIDATED so historical or unvalidated records are never
            # falsely reported as validated cropland.
            resolved_validation_status = (
                validation_status if validation_status is not None else "UNVALIDATED"
            )

            if has_005_columns and has_003_columns:
                insert_sql = """
                    INSERT INTO advisories (
                        farm_id,
                        observation_date,
                        ndvi,
                        ndwi,
                        soil_moisture,
                        rainfall_48h,
                        crop_stage,
                        stress_level,
                        recommendation,
                        observed_stress,
                        rain_forecast_mm,
                        guardrail_triggered,
                        recommended_action,
                        sentinel_scene_date,
                        smap_obs_date,
                        validation_status,
                        land_cover_class
                    ) VALUES (
                        %s, CURRENT_DATE, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    RETURNING id, farm_id, observation_date, stress_level, created_at;
                """
                params = (
                    farm_id,
                    ndvi,
                    ndwi,
                    soil_moisture,
                    rainfall_48h,
                    crop_stage,
                    stress_level,
                    recommendation,
                    observed_stress or stress_level,
                    rain_forecast_mm if rain_forecast_mm is not None else rainfall_48h,
                    guardrail_triggered,
                    recommended_action,
                    sentinel_scene_date,
                    smap_obs_date,
                    resolved_validation_status,
                    land_cover_class,
                )
            elif has_003_columns:
                insert_sql = """
                    INSERT INTO advisories (
                        farm_id,
                        observation_date,
                        ndvi,
                        ndwi,
                        soil_moisture,
                        rainfall_48h,
                        crop_stage,
                        stress_level,
                        recommendation,
                        observed_stress,
                        rain_forecast_mm,
                        guardrail_triggered,
                        recommended_action,
                        sentinel_scene_date,
                        smap_obs_date
                    ) VALUES (
                        %s, CURRENT_DATE, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    RETURNING id, farm_id, observation_date, stress_level, created_at;
                """
                params = (
                    farm_id,
                    ndvi,
                    ndwi,
                    soil_moisture,
                    rainfall_48h,
                    crop_stage,
                    stress_level,
                    recommendation,
                    observed_stress or stress_level,
                    rain_forecast_mm if rain_forecast_mm is not None else rainfall_48h,
                    guardrail_triggered,
                    recommended_action,
                    sentinel_scene_date,
                    smap_obs_date,
                )
            else:
                insert_sql = """
                    INSERT INTO advisories (
                        farm_id,
                        observation_date,
                        ndvi,
                        ndwi,
                        soil_moisture,
                        rainfall_48h,
                        crop_stage,
                        stress_level,
                        recommendation
                    ) VALUES (
                        %s, CURRENT_DATE, %s, %s, %s, %s, %s, %s, %s
                    )
                    RETURNING id, farm_id, observation_date, stress_level, created_at;
                """
                params = (
                    farm_id,
                    ndvi,
                    ndwi,
                    soil_moisture,
                    rainfall_48h,
                    crop_stage,
                    stress_level,
                    recommendation,
                )

            cur.execute(insert_sql, params)
            row = cur.fetchone()
            conn.commit()
            return {
                "id": row[0],
                "farm_id": row[1],
                "observation_date": str(row[2]),
                "stress_level": row[3],
                "created_at": str(row[4]),
            }
    finally:
        conn.close()


def audit_validation_failure(
    farm_id: int,
    val_result: Dict[str, Any],
    db_url: Optional[str] = None,
    s2_meta: Optional[Dict[str, Any]] = None,
    sm_meta: Optional[Dict[str, Any]] = None,
    mean_ndvi: Optional[float] = None,
    mean_ndwi: Optional[float] = None,
    rain_48h: Optional[float] = None,
    crop_stage: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Audits an agricultural or location validation failure into the advisories table
    without generating an irrigation recommendation.
    Sets recommended_action to None, records the failure outcome in validation_status,
    and documents the reason in recommendation text.
    """
    outcome = val_result.get("outcome", "VALIDATION_FAILED")
    reason = val_result.get("reason", "Location validation failure.")
    land_cover = val_result.get("land_cover_class")
    s2_date = s2_meta.get("date") if s2_meta else None
    sm_date = sm_meta.get("date") if sm_meta else None

    return save_advisory_to_database(
        farm_id=farm_id,
        stress_level=f"VALIDATION_FAILED: {outcome}",
        recommendation=f"Irrigation advisory withheld. Reason: {reason}",
        ndvi=mean_ndvi,
        ndwi=mean_ndwi,
        soil_moisture=None,
        rainfall_48h=rain_48h,
        crop_stage=crop_stage,
        observed_stress="VALIDATION_FAILED",
        rain_forecast_mm=rain_48h,
        guardrail_triggered=False,
        recommended_action=None,
        sentinel_scene_date=s2_date,
        smap_obs_date=sm_date,
        db_url=db_url,
        validation_status=outcome,
        land_cover_class=land_cover,
    )


# ==============================================================================
# 2. EARTHDATA AUTHENTICATED SESSION HELPER
# ==============================================================================

class EarthdataSession(requests.Session):
    """Session that preserves HTTP Basic Auth across NASA Earthdata domain redirects."""
    def __init__(self, username, password):
        super().__init__()
        self.auth = (username, password)

    def rebuild_auth(self, prepared_request, response):
        headers = prepared_request.headers
        url = prepared_request.url
        if "Authorization" in headers:
            original_parsed = requests.utils.urlparse(response.request.url)
            redirect_parsed = requests.utils.urlparse(url)
            if (original_parsed.hostname != redirect_parsed.hostname) and \
               redirect_parsed.hostname.endswith(("nasa.gov", "earthdata.nasa.gov")):
                prepared_request.prepare_auth(self.auth)


# ==============================================================================
# 3. PIPELINE STAGES
# ==============================================================================

def authenticate_earth_engine(key_path):
    """Authenticate to Google Earth Engine using service-account key."""
    if not os.path.exists(key_path):
        raise FileNotFoundError(f"Service-account key not found at: {key_path}")

    with open(key_path, "r") as f:
        key_data = json.load(f)

    client_email = key_data.get("client_email")
    project_id = key_data.get("project_id", "khetsense-ai")

    if not client_email:
        raise ValueError("Service-account key JSON is missing 'client_email'.")

    credentials = ee.ServiceAccountCredentials(client_email, key_path)
    ee.Initialize(credentials, project=project_id)
    return project_id


# ==============================================================================
# SPECTRAL INDICES MATHEMATICAL CALCULATIONS (Phase 7E)
# ==============================================================================

def calculate_ndvi(nir: Optional[float], red: Optional[float]) -> Optional[float]:
    """
    Normalized Difference Vegetation Index (Rouse et al. 1974).
    NDVI = (NIR - Red) / (NIR + Red)
    Sentinel-2: NIR = B8 (842 nm, 10m), Red = B4 (665 nm, 10m).
    Returns None if inputs are None/non-finite, sum is zero, or result is out of [-1.0, 1.0].
    """
    if nir is None or red is None:
        return None
    try:
        f_nir = float(nir)
        f_red = float(red)
        if not (math.isfinite(f_nir) and math.isfinite(f_red)):
            return None
        denom = f_nir + f_red
        if abs(denom) < 1e-9:
            return None
        val = (f_nir - f_red) / denom
        return round(val, 4) if -1.0 <= val <= 1.0 else None
    except Exception:
        return None


def calculate_ndwi(nir: Optional[float], swir: Optional[float]) -> Optional[float]:
    """
    Normalized Difference Water Index / Canopy Water Content (Gao 1996).
    NDWI = (NIR - SWIR) / (NIR + SWIR)
    Sentinel-2: NIR = B8 (842 nm, 10m), SWIR = B11 (1610 nm, 20m).
    Returns None if inputs are None/non-finite, sum is zero, or result is out of [-1.0, 1.0].
    """
    if nir is None or swir is None:
        return None
    try:
        f_nir = float(nir)
        f_swir = float(swir)
        if not (math.isfinite(f_nir) and math.isfinite(f_swir)):
            return None
        denom = f_nir + f_swir
        if abs(denom) < 1e-9:
            return None
        val = (f_nir - f_swir) / denom
        return round(val, 4) if -1.0 <= val <= 1.0 else None
    except Exception:
        return None


def calculate_ndre(nir: Optional[float], red_edge: Optional[float]) -> Optional[float]:
    """
    Normalized Difference Red Edge Index (Barnes et al. 2000).
    NDRE = (NIR - RedEdge) / (NIR + RedEdge)
    Sentinel-2: NIR = B8 (842 nm, 10m), RedEdge = B5 (705 nm, Red-Edge 1, 20m).
    Sensitive to chlorophyll content in mid-to-late growth stages where NDVI saturates.
    Returns None if inputs are None/non-finite, sum is zero, or result is out of [-1.0, 1.0].
    """
    if nir is None or red_edge is None:
        return None
    try:
        f_nir = float(nir)
        f_re = float(red_edge)
        if not (math.isfinite(f_re) and math.isfinite(f_nir)):
            return None
        denom = f_nir + f_re
        if abs(denom) < 1e-9:
            return None
        val = (f_nir - f_re) / denom
        return round(val, 4) if -1.0 <= val <= 1.0 else None
    except Exception:
        return None


def calculate_msavi(nir: Optional[float], red: Optional[float], scale_factor: float = 1.0) -> Optional[float]:
    """
    Modified Soil-Adjusted Vegetation Index (Qi et al. 1994).
    MSAVI = (2 * NIR + 1 - sqrt((2 * NIR + 1)^2 - 8 * (NIR - Red))) / 2

    Reflectance Scaling Note:
    Sentinel-2 L2A integers are scaled by 10,000 (0..10000 = 0.0..1.0 reflectance).
    Because MSAVI contains constant offsets (+1 and -8), NIR and Red MUST be in the
    0.0 to 1.0 reflectance range. If raw DN integers (e.g. 5000) are passed, set
    scale_factor=10000.0 to convert to reflectance before evaluating.

    Returns None if inputs are None/non-finite, negative reflectances,
    discriminant < 0, or result is out of [-1.0, 1.0].
    """
    if nir is None or red is None:
        return None
    try:
        f_nir = float(nir) / scale_factor
        f_red = float(red) / scale_factor
        if not (math.isfinite(f_nir) and math.isfinite(f_red)):
            return None
        if f_nir < 0.0 or f_red < 0.0:
            return None
        
        term = 2.0 * f_nir + 1.0
        disc = (term * term) - 8.0 * (f_nir - f_red)
        if disc < 0.0:
            return None
        val = (term - math.sqrt(disc)) / 2.0
        return round(val, 4) if -1.0 <= val <= 1.0 else None
    except Exception:
        return None


def calculate_all_spectral_indices(
    b4_red: Optional[float],
    b5_red_edge: Optional[float],
    b8_nir: Optional[float],
    b11_swir: Optional[float],
    scale_factor: float = 1.0,
) -> Dict[str, Optional[float]]:
    """
    Computes all four primary KhetSense vegetation indices from Sentinel-2 bands:
    - NDVI: (B8 - B4) / (B8 + B4)
    - NDWI: (B8 - B11) / (B8 + B11)
    - NDRE: (B8 - B5) / (B8 + B5)
    - MSAVI: Qi et al. 1994 formula using scaled B8 and B4
    """
    return {
        "ndvi": calculate_ndvi(b8_nir, b4_red),
        "ndwi": calculate_ndwi(b8_nir, b11_swir),
        "ndre": calculate_ndre(b8_nir, b5_red_edge),
        "msavi": calculate_msavi(b8_nir, b4_red, scale_factor=scale_factor),
    }


def fetch_sentinel2_indices(
    geometry,
    max_age_days: Optional[int] = None,
    reference_date: Any = None,
    return_all: bool = False,
):
    """
    Fetch the most recent Sentinel-2 Surface Reflectance Harmonized scene (<20% clouds),
    calculate:
      - NDVI = (B8 - B4) / (B8 + B4)
      - Gao's NDWI = (B8 - B11) / (B8 + B11)
      - NDRE = (B8 - B5) / (B8 + B5)
      - MSAVI = (2 * NIR + 1 - sqrt((2 * NIR + 1)^2 - 8 * (NIR - RED))) / 2 (Qi et al. 1994)
    and compute their mean values over the polygon.

    Enforces temporal freshness: rejects observations older than max_age_days (default 14 days).

    Returns:
      If return_all is False (default for backwards compatibility):
        (mean_ndvi, mean_ndwi, metadata, error)
        where metadata contains 'ndre', 'msavi', and 'indices' dictionary.
      If return_all is True:
        (mean_ndvi, mean_ndwi, mean_ndre, mean_msavi, metadata, error)
    """
    def _err_return(msg):
        if return_all:
            return None, None, None, None, None, msg
        return None, None, None, msg

    if max_age_days is None:
        max_age_days = FRESHNESS_CONFIG.MAX_SENTINEL2_AGE_DAYS

    # Resolve reference date for freshness calculation
    if reference_date is None:
        ref_dt = datetime.now(timezone.utc)
    elif isinstance(reference_date, datetime):
        ref_dt = reference_date if reference_date.tzinfo else reference_date.replace(tzinfo=timezone.utc)
    elif isinstance(reference_date, str):
        try:
            parsed_dt = datetime.fromisoformat(reference_date.replace("Z", "+00:00"))
            ref_dt = parsed_dt if parsed_dt.tzinfo else parsed_dt.replace(tzinfo=timezone.utc)
        except Exception:
            ref_dt = datetime.now(timezone.utc)
    else:
        ref_dt = datetime.now(timezone.utc)

    # Date bounds for Earth Engine query
    start_date = (ref_dt - timedelta(days=max_age_days)).strftime("%Y-%m-%d")
    end_date = (ref_dt + timedelta(days=1)).strftime("%Y-%m-%d")

    s2_col = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(geometry)
        .filterDate(start_date, end_date)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20))
        .sort("system:time_start", False)
    )

    count = s2_col.size().getInfo()
    if count == 0:
        return _err_return(f"No cloud-free Sentinel-2 images found within {max_age_days} days for this polygon.")

    img = s2_col.first()

    # Validate acquisition timestamp
    raw_ts = img.get("system:time_start")
    if hasattr(raw_ts, "getInfo"):
        raw_ts = raw_ts.getInfo()

    if raw_ts is None:
        return _err_return("Sentinel-2 image missing 'system:time_start' acquisition timestamp.")

    obs_dt = None
    try:
        f_ts = float(raw_ts)
        if f_ts > 1e11:
            f_ts /= 1000.0
        obs_dt = datetime.fromtimestamp(f_ts, tz=timezone.utc)
    except (ValueError, TypeError):
        try:
            obs_dt = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
            if not obs_dt.tzinfo:
                obs_dt = obs_dt.replace(tzinfo=timezone.utc)
        except Exception as ts_err:
            return _err_return(f"Malformed Sentinel-2 acquisition timestamp ({raw_ts}): {ts_err}")

    date_str = obs_dt.strftime("%Y-%m-%d %H:%M:%S")

    # Verify freshness against reference date
    age_seconds = (ref_dt - obs_dt).total_seconds()
    age_days = age_seconds / 86400.0

    if age_days < -1.0:
        return _err_return(f"Sentinel-2 scene has invalid future timestamp: {date_str} (ref: {ref_dt.strftime('%Y-%m-%d')})")

    if age_days > max_age_days:
        return _err_return(f"Sentinel-2 imagery is stale: acquired {date_str} ({age_days:.1f} days old > {max_age_days}-day limit).")

    cloud_obj = img.get("CLOUDY_PIXEL_PERCENTAGE")
    cloud_pct = cloud_obj.getInfo() if hasattr(cloud_obj, "getInfo") else cloud_obj

    # 1. NDVI = (NIR - Red) / (NIR + Red) -> Sentinel-2: NIR = B8 (842nm), Red = B4 (665nm)
    ndvi = img.normalizedDifference(["B8", "B4"]).rename("NDVI")

    # 2. Gao's NDWI = (NIR - SWIR) / (NIR + SWIR) -> Sentinel-2: NIR = B8 (842nm), SWIR = B11 (1610nm)
    ndwi = img.normalizedDifference(["B8", "B11"]).rename("NDWI")

    # 3. NDRE = (NIR - RedEdge) / (NIR + RedEdge) -> Sentinel-2: NIR = B8 (842nm), RedEdge = B5 (705nm)
    ndre = img.normalizedDifference(["B8", "B5"]).rename("NDRE")

    # 4. Qi et al. (1994) MSAVI:
    # Surface reflectances must be scaled to [0, 1] by dividing L2A integer reflectances by 10000.0
    nir_scaled = img.select("B8").divide(10000.0)
    red_scaled = img.select("B4").divide(10000.0)
    msavi = nir_scaled.expression(
        "(2 * NIR + 1 - sqrt((2 * NIR + 1)**2 - 8 * (NIR - RED))) / 2",
        {"NIR": nir_scaled, "RED": red_scaled}
    ).rename("MSAVI")

    multi_band = ndvi.addBands([ndwi, ndre, msavi])

    stats = (
        multi_band.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=geometry,
            scale=10,
            maxPixels=1e9,
        )
        .getInfo()
    )

    raw_ndvi = stats.get("NDVI") if stats else None
    raw_ndwi = stats.get("NDWI") if stats else None
    raw_ndre = stats.get("NDRE") if stats else None
    raw_msavi = stats.get("MSAVI") if stats else None

    mean_ndvi = sanitize_sensor_float(raw_ndvi, min_val=0.0, max_val=1.0)
    mean_ndwi = sanitize_sensor_float(raw_ndwi, min_val=-1.0, max_val=1.0)
    mean_ndre = sanitize_sensor_float(raw_ndre, min_val=-1.0, max_val=1.0)
    mean_msavi = sanitize_sensor_float(raw_msavi, min_val=-1.0, max_val=1.0)

    if mean_ndvi is None:
        return _err_return("Sentinel-2 mean NDVI reduction resulted in null, non-finite, or out-of-range value.")

    image_id = None
    if hasattr(img, "id"):
        id_call = img.id()
        image_id = id_call.getInfo() if hasattr(id_call, "getInfo") else id_call

    metadata = {
        "date": date_str,
        "cloud_cover_pct": cloud_pct,
        "image_id": image_id,
        "age_days": round(age_days, 2),
        "ndre": mean_ndre,
        "msavi": mean_msavi,
        "indices": {
            "ndvi": mean_ndvi,
            "ndwi": mean_ndwi,
            "ndre": mean_ndre,
            "msavi": mean_msavi,
        },
    }

    if return_all:
        return mean_ndvi, mean_ndwi, mean_ndre, mean_msavi, metadata, None

    return mean_ndvi, mean_ndwi, metadata, None


def authenticate_and_query_earthdata(username, password, bbox):
    """
    Authenticate to NASA Earthdata and query the CMR API for latest SPL3SMP_E granule metadata.
    """
    if not username or not password or username == "your_username":
        return None, "NASA Earthdata credentials missing or unconfigured in .env"

    # NASA CMR search does not require or accept Basic Auth
    cmr_url = "https://cmr.earthdata.nasa.gov/search/granules.json"
    params = {
        "short_name": "SPL3SMP_E",
        "bounding_box": bbox,
        "sort_key[]": "-start_date",
        "page_size": 1,
    }

    try:
        resp = requests.get(cmr_url, params=params, timeout=15)
        if resp.status_code != 200:
            return None, f"NASA CMR query returned status {resp.status_code}: {resp.text[:120]}"

        data = resp.json()
        entries = data.get("feed", {}).get("entry", [])
        if not entries:
            return None, "No SMAP SPL3SMP_E granules found in CMR for bounding box."

        latest_entry = entries[0]
        granule_id = latest_entry.get("title")
        time_start = latest_entry.get("time_start")

        # Authenticate against protected DAAC granule endpoint using Earthdata credentials
        protected_link = None
        for link in latest_entry.get("links", []):
            href = link.get("href", "")
            if "nsidc-cumulus-prod-protected" in href and href.endswith(".h5"):
                protected_link = href
                break

        auth_verified = False
        if protected_link:
            session = EarthdataSession(username, password)
            head_resp = session.head(protected_link, allow_redirects=True, timeout=15)
            if head_resp.status_code == 200:
                auth_verified = True
            else:
                return None, f"Earthdata Login rejected credentials (status {head_resp.status_code})"

        return {
            "granule_id": granule_id,
            "time_start": time_start,
            "auth_verified": auth_verified,
        }, None

    except Exception as e:
        return None, f"NASA Earthdata connection error: {str(e)}"


def fetch_smap_soil_moisture(
    centroid_lon,
    centroid_lat,
    max_age_days: Optional[int] = None,
    reference_date: Any = None,
):
    """
    Fetch the latest available SMAP SPL3SMP_E surface soil moisture value
    by sampling the grid cell containing the farm centroid.

    Methodological Note:
    - SMAP provides approximately 9-km spatial soil-moisture information.
    - KhetSense samples the SMAP grid cell containing the farm centroid.
    - Sentinel-2 provides the field-scale vegetation information.

    Enforces temporal freshness: rejects observations older than max_age_days (default 5 days).
    Does NOT select an older granule merely because it has valid numeric values.

    Returns soil moisture in percentage (0-100%).
    """
    if max_age_days is None:
        max_age_days = FRESHNESS_CONFIG.MAX_SMAP_AGE_DAYS

    # Resolve reference date
    if reference_date is None:
        ref_dt = datetime.now(timezone.utc)
    elif isinstance(reference_date, datetime):
        ref_dt = reference_date if reference_date.tzinfo else reference_date.replace(tzinfo=timezone.utc)
    elif isinstance(reference_date, str):
        try:
            parsed_dt = datetime.fromisoformat(reference_date.replace("Z", "+00:00"))
            ref_dt = parsed_dt if parsed_dt.tzinfo else parsed_dt.replace(tzinfo=timezone.utc)
        except Exception:
            ref_dt = datetime.now(timezone.utc)
    else:
        ref_dt = datetime.now(timezone.utc)

    try:
        point = ee.Geometry.Point([centroid_lon, centroid_lat])
        start_date = (ref_dt - timedelta(days=max_age_days)).strftime("%Y-%m-%d")
        end_date = (ref_dt + timedelta(days=1)).strftime("%Y-%m-%d")

        col = (
            ee.ImageCollection("NASA/SMAP/SPL3SMP_E/006")
            .filterBounds(point)
            .filterDate(start_date, end_date)
            .sort("system:time_start", False)
        )

        count = col.size().getInfo()
        if count == 0:
            col = (
                ee.ImageCollection("NASA/SMAP/SPL3SMP_E/005")
                .filterBounds(point)
                .filterDate(start_date, end_date)
                .sort("system:time_start", False)
            )
            count = col.size().getInfo()
            if count == 0:
                return None, None, f"No SMAP SPL3SMP_E imagery found within {max_age_days}-day freshness window for centroid."

        # Search the latest granules to find the latest valid overpass
        # (SMAP has a 2-3 day revisit cycle, so off-swath days have masked pixels over local coordinates)
        candidates = col.limit(10).getInfo().get("features", [])
        img = None
        date_str = None
        sm_val = None
        dataset_id = None
        obs_age_days = None

        for feat in candidates:
            props = feat.get("properties", {})
            raw_ts = props.get("system:time_start")
            if raw_ts is None:
                continue

            try:
                f_ts = float(raw_ts)
                if f_ts > 1e11:
                    f_ts /= 1000.0
                cand_dt = datetime.fromtimestamp(f_ts, tz=timezone.utc)
            except (ValueError, TypeError):
                try:
                    cand_dt = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
                    if not cand_dt.tzinfo:
                        cand_dt = cand_dt.replace(tzinfo=timezone.utc)
                except Exception:
                    continue

            age_seconds = (ref_dt - cand_dt).total_seconds()
            cand_age = age_seconds / 86400.0

            # Reject future timestamp
            if cand_age < -1.0:
                continue

            # Since candidates are sorted descending (newest first), if cand_age > max_age_days,
            # all remaining candidates are even older. Stop search immediately!
            if cand_age > max_age_days:
                break

            cand_img = ee.Image(feat["id"])
            stats = (
                cand_img.select(["soil_moisture_am", "soil_moisture_pm"])
                .reduceRegion(
                    reducer=ee.Reducer.mean(),
                    geometry=point,
                    scale=9000,
                )
                .getInfo()
            )
            val = stats.get("soil_moisture_am") if stats else None
            if val is None and stats:
                val = stats.get("soil_moisture_pm")

            # Validate and sanitize numeric value
            sanitized = sanitize_sensor_float(val, min_val=0.0, max_val=1.0)
            if sanitized is not None:
                img = cand_img
                sm_val = sanitized
                dataset_id = feat["id"]
                date_str = cand_dt.strftime("%Y-%m-%d %H:%M:%S")
                obs_age_days = cand_age
                break

        if sm_val is None:
            return None, None, f"SMAP pixel data over centroid is masked/null in valid scenes within {max_age_days}-day freshness window."

        # SMAP volumetric soil moisture is m^3/m^3 (0.0 to ~0.5)
        # Convert to percentage
        sm_pct = sm_val * 100.0 if sm_val <= 1.0 else sm_val
        sm_pct = round(sm_pct, 2)

        metadata = {
            "date": date_str,
            "dataset": dataset_id,
            "raw_m3m3": sm_val,
            "age_days": round(obs_age_days, 2) if obs_age_days is not None else None,
        }

        return sm_pct, metadata, None

    except Exception as e:
        return None, None, f"Error fetching SMAP soil moisture: {str(e)}"


def fetch_openweather_forecast(api_key, lat, lon):
    """
    Fetch 5-day / 3-hour forecast for the centroid coordinates,
    summing precipitation over the next 48 hours.

    Requirements:
    - Validates that API key and coordinates are present and valid.
    - Asserts that at least 16 slices (48 hours) are present in the response.
    - Validates timestamps for strict temporal monotonicity and continuity (~3h intervals).
    - Validates rainfall fields, rejecting negative, non-numeric, or non-finite values.
    - Distinguishes a genuine 0.0 mm forecast from an incomplete, malformed, or failed forecast.
    """
    if not api_key or api_key.strip() == "":
        return None, "OPENWEATHER_API_KEY missing or not found in .env"

    try:
        f_lat = float(lat)
        f_lon = float(lon)
        if math.isnan(f_lat) or math.isnan(f_lon) or math.isinf(f_lat) or math.isinf(f_lon):
            return None, f"Invalid non-finite coordinates: lat={lat!r}, lon={lon!r}"
        if not (-90.0 <= f_lat <= 90.0 and -180.0 <= f_lon <= 180.0):
            return None, f"Coordinates out of bounds: lat={f_lat}, lon={f_lon}"
    except (ValueError, TypeError) as e:
        return None, f"Malformed coordinates: {e}"

    url = f"https://api.openweathermap.org/data/2.5/forecast?lat={f_lat}&lon={f_lon}&appid={api_key}&units=metric"

    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            return None, f"OpenWeather API error (status {resp.status_code}): {resp.text[:100]}"

        data = resp.json()
        raw_list = data.get("list")
        if not isinstance(raw_list, list):
            return None, "OpenWeather response missing or invalid 'list' array"

        expected_slices = RAINFALL_CONFIG.FORECAST_SLICES
        if len(raw_list) < expected_slices:
            return None, (
                f"Incomplete forecast coverage: received {len(raw_list)} slices, "
                f"expected at least {expected_slices} (48 hours)"
            )

        forecast_entries = raw_list[:expected_slices]
        total_rain_48h = 0.0
        prev_ts = None

        for idx, item in enumerate(forecast_entries):
            if not isinstance(item, dict):
                return None, f"Malformed forecast slice at index {idx}: not a dictionary"

            # Validate timestamp dt
            dt_val = item.get("dt")
            if dt_val is None or isinstance(dt_val, bool):
                return None, f"Missing or invalid 'dt' timestamp in forecast slice {idx}"
            try:
                curr_ts = float(dt_val)
                if math.isnan(curr_ts) or math.isinf(curr_ts):
                    return None, f"Non-finite timestamp in forecast slice {idx}: {dt_val!r}"
            except (ValueError, TypeError):
                return None, f"Non-numeric timestamp in forecast slice {idx}: {dt_val!r}"

            if prev_ts is not None:
                delta_sec = curr_ts - prev_ts
                # Slices should be sequential 3-hour steps (10800s); allow 1.5h to 4.5h tolerance
                if delta_sec <= 0:
                    return None, f"Non-monotonic timestamp sequence at slice {idx}: {curr_ts} <= {prev_ts}"
                if delta_sec < 5400 or delta_sec > 16200:
                    return None, f"Timestamp discontinuity between slice {idx-1} and {idx}: step = {delta_sec}s"
            prev_ts = curr_ts

            # Validate rainfall
            rain_obj = item.get("rain")
            r3h = 0.0
            if rain_obj is not None:
                if not isinstance(rain_obj, dict):
                    return None, f"Malformed 'rain' field in forecast slice {idx}: {rain_obj!r}"
                raw_r3h = rain_obj.get("3h", 0.0)
                if isinstance(raw_r3h, bool):
                    return None, f"Malformed boolean rain value in forecast slice {idx}: {raw_r3h!r}"
                try:
                    r3h = float(raw_r3h)
                    if math.isnan(r3h) or math.isinf(r3h):
                        return None, f"Non-finite rain value in forecast slice {idx}: {raw_r3h!r}"
                    if r3h < 0.0:
                        return None, f"Negative rain value in forecast slice {idx}: {r3h} mm"
                except (ValueError, TypeError):
                    return None, f"Non-numeric rain value in forecast slice {idx}: {raw_r3h!r}"

            total_rain_48h += r3h

        return round(float(total_rain_48h), 2), None

    except Exception as e:
        return None, f"OpenWeather request exception: {str(e)}"


# ==============================================================================
# 4. KHETSENSE DECISION RULES & GUARDRAILS (RE-EXPORTED FROM classifier.py)
# ==============================================================================

# Single clean import: PROJECT_ROOT was inserted at sys.path[0] at script initialization,
# ensuring pipeline and common packages are always resolvable from anywhere.
from common.config import RAINFALL_CONFIG, is_ml_advisory_enabled
from pipeline.classifier import (
    classify_ndvi_stress,
    classify_soil_moisture_stress,
    get_more_severe,
    apply_rainfall_guardrail,
    generate_irrigation_advisory,
    validate_forecast_rainfall,
    hybrid_stress_assessment,
    primary_ml_stress_assessment,
)
from pipeline.ml_inference import predict_crop_stress, predict_crop_stress_5feat

# Helper imports for WhatsApp delivery and PII masking
deliver_voice_advisory = None
try:
    from whatsapp.messages import format_status_advisory, format_voice_script, get_message, normalize_language
    from pipeline.tts_provider import get_tts_provider
    from common.utils import mask_phone
except ImportError:
    try:
        from khetsense.whatsapp.messages import format_status_advisory, format_voice_script, get_message, normalize_language
        from khetsense.pipeline.tts_provider import get_tts_provider
        from khetsense.common.utils import mask_phone
    except ImportError:
        try:
            from ..whatsapp.messages import format_status_advisory, format_voice_script, get_message, normalize_language
            from .tts_provider import get_tts_provider
            from ..common.utils import mask_phone
        except Exception:
            format_status_advisory = None
            format_voice_script = None
            get_tts_provider = None
            get_message = None
            normalize_language = lambda x: x or "en"
            mask_phone = lambda x: x

try:
    from pipeline.location_validator import (
        validate_agricultural_location,
        VALIDATION_SUITABLE,
        VALIDATION_URBAN,
        VALIDATION_BARREN_UNCERTAIN,
        VALIDATION_INSUFFICIENT_IMAGERY,
        VALIDATION_INCOMPLETE_AUXILIARY,
    )
except ImportError:
    try:
        from location_validator import (
            validate_agricultural_location,
            VALIDATION_SUITABLE,
            VALIDATION_URBAN,
            VALIDATION_BARREN_UNCERTAIN,
            VALIDATION_INSUFFICIENT_IMAGERY,
            VALIDATION_INCOMPLETE_AUXILIARY,
        )
    except Exception:
        validate_agricultural_location = None
        VALIDATION_SUITABLE = "SUITABLE_CROPLAND"
        VALIDATION_URBAN = "LIKELY_URBAN"
        VALIDATION_BARREN_UNCERTAIN = "BARREN_OR_UNCERTAIN"
        VALIDATION_INSUFFICIENT_IMAGERY = "INSUFFICIENT_SATELLITE_DATA"
        VALIDATION_INCOMPLETE_AUXILIARY = "INCOMPLETE_AUXILIARY_DATA"

try:
    from pipeline.crop_validator import (
        validate_crop_type,
        CROP_MATCH,
        CROP_MISMATCH,
        CROP_INCONCLUSIVE,
        CROP_UNVALIDATED,
    )
except ImportError:
    try:
        from crop_validator import (
            validate_crop_type,
            CROP_MATCH,
            CROP_MISMATCH,
            CROP_INCONCLUSIVE,
            CROP_UNVALIDATED,
        )
    except Exception:
        validate_crop_type = None
        CROP_MATCH = "MATCH"
        CROP_MISMATCH = "MISMATCH"
        CROP_INCONCLUSIVE = "INCONCLUSIVE"
        CROP_UNVALIDATED = "UNVALIDATED"


def run_pipeline_for_farm(
    farm_id: int,
    db_url: Optional[str] = None,
    outbound_sender=None,
    auto_send_advisory: bool = True,
    force: bool = False,
    ee_key_path: Optional[str] = None,
    audit_validation_failures: bool = False,
    send_voice_advisory: bool = False,
    outbound_voice_sender=None,
    tts_provider=None,
    enable_voice_chatbot: Optional[bool] = None,
    is_demo: Optional[bool] = None,
    crop_validation_enabled: Optional[bool] = None,
    multi_date_series: Optional[List[Dict[str, Any]]] = None,
    crop_reference_model: Optional[Any] = None,
    ground_truth_crop_reference: Optional[Dict[str, Any]] = None,
    ml_model_regime: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Executes the end-to-end crop stress detection and irrigation advisory pipeline
    for a specific farm by ID.

    Workflow:
    1. In-flight deduplication check (prevents duplicate concurrent runs for the same farm).
    2. Retrieves farm record and PostGIS polygon from the database.
    3. Authenticates to Google Earth Engine and retrieves Sentinel-2 NDVI & NDWI.
    4. Retrieves NASA SMAP SPL3SMP_E soil moisture observation over farm centroid.
    5. Retrieves OpenWeather 48-hour rainfall forecast over farm centroid.
    6. Fuses NDVI and SMAP stress, applies rainfall guardrail, and generates irrigation advisory.
    7. Persists advisory and audit provenance metrics to Supabase PostgreSQL database.
    8. If auto_send_advisory is True and outbound_sender is provided, renders and sends
       localized advisory card on WhatsApp in the farmer's preferred language.
    9. On failure, logs safely with PII masking and sends localized failure notice to farmer.
    """
    with _ACTIVE_PIPELINE_LOCK:
        if farm_id in _ACTIVE_PIPELINE_RUNS and not force:
            pipeline_logger.warning("Pipeline run for farm_id %s is already in progress. Skipping duplicate run.", farm_id)
            return {
                "status": "already_running",
                "farm_id": farm_id,
                "message": f"Pipeline already running for farm {farm_id}",
            }
        _ACTIVE_PIPELINE_RUNS.add(farm_id)

    farmer_mobile = None
    farmer_lang = "en"
    farmer_name = "Farmer"

    # Determine if whole-chat voice is enabled for conversational notices
    is_voice_chatbot_enabled = False
    if enable_voice_chatbot is not None:
        is_voice_chatbot_enabled = bool(enable_voice_chatbot)
    else:
        env_voice = (os.getenv("ENABLE_VOICE_CHATBOT") or "false").strip().lower()
        is_voice_chatbot_enabled = (env_voice == "true")

    try:
        # 1. Database Retrieval
        farm = get_farm_from_database(farm_id, db_url=db_url)
        farmer_name = farm.get("farmer_name") or "Farmer"
        farmer_mobile = farm.get("mobile_number")
        farmer_lang = normalize_language(farm.get("preferred_language") or "en")
        crop = farm.get("crop_name") or DEFAULT_CROP
        ee_coords = farm["ee_coords"]
        centroid_lat = farm["centroid_lat"]
        centroid_lon = farm["centroid_lon"]

        if is_demo is None:
            is_demo = bool(
                farm.get("is_demo")
                or (isinstance(farm.get("notes"), str) and "demo" in farm.get("notes", "").lower())
                or (isinstance(farm.get("boundary_source"), str) and "demo" in farm.get("boundary_source", "").lower())
                or os.getenv("DEMO_MODE", "").strip().lower() in ("true", "1", "yes")
            )

        # 2. Google Earth Engine Authentication & Sentinel-2 Indices
        key_file = ee_key_path or EE_KEY_PATH
        authenticate_earth_engine(key_file)
        farm_geom = ee.Geometry.Polygon([ee_coords])
        mean_ndvi, mean_ndwi, s2_meta, s2_err = fetch_sentinel2_indices(farm_geom)
        if s2_err:
            pipeline_logger.warning("Sentinel-2 warning for farm %s: %s", farm_id, s2_err)

        # 3. NASA Earthdata SMAP Soil Moisture
        sm_pct, sm_meta, sm_err = fetch_smap_soil_moisture(centroid_lon, centroid_lat)
        if sm_err:
            pipeline_logger.warning("SMAP warning for farm %s: %s", farm_id, sm_err)

        # 4. OpenWeather 48-Hour Rainfall Forecast
        owm_key = os.getenv("OPENWEATHER_API_KEY")
        rain_48h, rain_err = fetch_openweather_forecast(owm_key, centroid_lat, centroid_lon)
        if rain_err:
            pipeline_logger.warning("OpenWeather warning for farm %s: %s", farm_id, rain_err)

        # 4b. Agricultural Location & Satellite Data Validation
        val_result = None
        if validate_agricultural_location is not None:
            val_result = validate_agricultural_location(
                centroid_lat=centroid_lat,
                centroid_lon=centroid_lon,
                ee_coords=ee_coords,
                farm_area_acres=farm.get("farm_area"),
                s2_meta=s2_meta,
                s2_err=s2_err,
                mean_ndvi=mean_ndvi,
                farm_geom=farm_geom,
                land_cover_class=farm.get("land_cover_class"),
                land_cover_code=farm.get("land_cover_code"),
                has_smap=(sm_pct is not None),
                has_weather=(rain_48h is not None),
            )
            if not val_result["is_suitable_for_advisory"]:
                pipeline_logger.warning(
                    "Agricultural validation failed for farm %s: outcome=%s, reason=%s",
                    farm_id, val_result["outcome"], val_result["reason"]
                )
                notice_voice_sent = False
                if auto_send_advisory and outbound_sender and farmer_mobile and get_message:
                    outcome = val_result["outcome"]
                    if is_demo:
                        reason_msg = val_result.get("reason", "Location could not be verified as active cropland")
                        notice_text = get_message(
                            "location_validation_demo_failed",
                            lang=farmer_lang,
                            reason=reason_msg,
                        )
                    elif outcome == VALIDATION_URBAN:
                        notice_text = get_message("location_validation_urban", lang=farmer_lang)
                    elif outcome == VALIDATION_BARREN_UNCERTAIN:
                        notice_text = get_message("location_validation_fallow", lang=farmer_lang)
                    elif outcome == VALIDATION_INSUFFICIENT_IMAGERY:
                        notice_text = get_message("location_validation_satellite_unavailable", lang=farmer_lang)
                    else:
                        notice_text = get_message("error_generic", lang=farmer_lang)

                    # Route farmer-facing notice through text-first voice dispatcher if whole-chat voice is enabled
                    _send_farmer_response = None
                    try:
                        from whatsapp.registration_flow import send_farmer_response as _send_farmer_response
                    except ImportError:
                        try:
                            from khetsense.whatsapp.registration_flow import send_farmer_response as _send_farmer_response
                        except Exception:
                            _send_farmer_response = None

                    if _send_farmer_response is not None:
                        provider = tts_provider
                        if provider is None and get_tts_provider is not None:
                            try:
                                provider = get_tts_provider()
                            except Exception:
                                provider = None
                        send_res = _send_farmer_response(
                            to=farmer_mobile,
                            text=notice_text,
                            lang=farmer_lang,
                            outbound_sender=outbound_sender,
                            outbound_voice_sender=outbound_voice_sender,
                            enable_voice=is_voice_chatbot_enabled,
                            tts_provider=provider,
                        )
                        notice_voice_sent = bool(send_res.get("voice_sent", False))
                    else:
                        outbound_sender(farmer_mobile, notice_text)

                audit_record = None
                if audit_validation_failures:
                    try:
                        audit_record = audit_validation_failure(
                            farm_id=farm_id,
                            val_result=val_result,
                            db_url=db_url,
                            s2_meta=s2_meta,
                            sm_meta=sm_meta,
                            mean_ndvi=mean_ndvi,
                            mean_ndwi=mean_ndwi,
                            rain_48h=rain_48h,
                            crop_stage=CROP_GROWTH_STAGE,
                        )
                    except Exception as audit_err:
                        pipeline_logger.error("Failed to audit validation failure for farm %s: %s", farm_id, audit_err)

                return {
                    "status": "validation_failed",
                    "farm_id": farm_id,
                    "outcome": val_result["outcome"],
                    "reason": val_result["reason"],
                    "land_cover_class": val_result.get("land_cover_class"),
                    "advisory_sent": False,
                    "voice_sent": False,
                    "notice_voice_sent": notice_voice_sent,
                    "audit_record": audit_record,
                    "is_demo": is_demo,
                }

        # 4c. Satellite-Based Crop Validation & Discrepancy Screening
        crop_val_result = None
        should_validate_crop = crop_validation_enabled if crop_validation_enabled is not None else is_crop_validation_enabled()
        if should_validate_crop and validate_crop_type is not None:
            try:
                crop_val_result = validate_crop_type(
                    declared_crop=crop,
                    centroid_lat=centroid_lat,
                    centroid_lon=centroid_lon,
                    mean_ndvi=mean_ndvi,
                    mean_ndwi=mean_ndwi,
                    s2_meta=s2_meta,
                    multi_date_series=multi_date_series,
                    reference_model=crop_reference_model,
                    ground_truth_reference=ground_truth_crop_reference,
                    is_demo=is_demo,
                )
            except Exception as crop_val_err:
                pipeline_logger.warning("Error during crop validation for farm %s: %s; proceeding as UNVALIDATED", farm_id, crop_val_err)
                crop_val_result = {
                    "outcome": CROP_UNVALIDATED,
                    "declared_crop": crop,
                    "predicted_crop": None,
                    "confidence": None,
                    "reason": f"Crop validation error: {crop_val_err}",
                    "is_suitable_for_advisory": True,
                    "requires_confirmation": False,
                }

            if crop_val_result and not crop_val_result.get("is_suitable_for_advisory", True):
                # Discrepancy detected: credible mismatch between declared crop and satellite evidence/calendar.
                # Crop-specific advisory is WITHHELD. Farmer is prompted to confirm or correct crop.
                pipeline_logger.warning(
                    "Crop validation mismatch detected for farm %s: declared='%s', predicted='%s', reason=%s",
                    farm_id, crop, crop_val_result.get("predicted_crop"), crop_val_result.get("reason")
                )
                mismatch_voice_sent = False
                if auto_send_advisory and outbound_sender and farmer_mobile and get_message:
                    mismatch_text = get_message(
                        "crop_validation_mismatch",
                        lang=farmer_lang,
                        farm_id=farm_id,
                        declared_crop=crop_val_result.get("declared_crop") or crop,
                        predicted_crop=crop_val_result.get("predicted_crop") or "another crop",
                        reason=crop_val_result.get("reason") or "",
                    )
                    _send_farmer_response = None
                    try:
                        from whatsapp.registration_flow import send_farmer_response as _send_farmer_response
                    except ImportError:
                        try:
                            from khetsense.whatsapp.registration_flow import send_farmer_response as _send_farmer_response
                        except Exception:
                            _send_farmer_response = None

                    if _send_farmer_response is not None:
                        provider = tts_provider
                        if provider is None and get_tts_provider is not None:
                            try:
                                provider = get_tts_provider()
                            except Exception:
                                provider = None
                        send_res = _send_farmer_response(
                            to=farmer_mobile,
                            text=mismatch_text,
                            lang=farmer_lang,
                            outbound_sender=outbound_sender,
                            outbound_voice_sender=outbound_voice_sender,
                            enable_voice=is_voice_chatbot_enabled,
                            tts_provider=provider,
                        )
                        mismatch_voice_sent = bool(send_res.get("voice_sent", False))
                    else:
                        outbound_sender(farmer_mobile, mismatch_text)

                audit_record = None
                if audit_validation_failures:
                    try:
                        audit_record = save_advisory_to_database(
                            farm_id=farm_id,
                            stress_level="VALIDATION_FAILED: CROP_MISMATCH",
                            recommendation=f"Irrigation advisory withheld. Crop mismatch: {crop_val_result.get('reason')}",
                            ndvi=mean_ndvi,
                            ndwi=mean_ndwi,
                            soil_moisture=None,
                            rainfall_48h=rain_48h,
                            crop_stage=CROP_GROWTH_STAGE,
                            observed_stress="VALIDATION_FAILED",
                            rain_forecast_mm=rain_48h,
                            guardrail_triggered=False,
                            recommended_action=None,
                            sentinel_scene_date=s2_meta["date"] if s2_meta else None,
                            smap_obs_date=sm_meta["date"] if sm_meta else None,
                            db_url=db_url,
                            validation_status="CROP_MISMATCH",
                            land_cover_class=val_result.get("land_cover_class") if val_result else None,
                        )
                    except Exception as audit_err:
                        pipeline_logger.error("Failed to audit crop validation failure for farm %s: %s", farm_id, audit_err)

                return {
                    "status": "crop_mismatch",
                    "farm_id": farm_id,
                    "crop_validation": crop_val_result,
                    "advisory_sent": False,
                    "voice_sent": False,
                    "mismatch_voice_sent": mismatch_voice_sent,
                    "audit_record": audit_record,
                    "reason": crop_val_result.get("reason"),
                    "is_demo": is_demo,
                }

        # 5. Stress Classification & Guardrail Logic
        ndvi_class = classify_ndvi_stress(mean_ndvi)
        sm_class = classify_soil_moisture_stress(sm_pct)
        rule_observed_stress = get_more_severe(ndvi_class, sm_class)

        # 5b. Machine Learning Primary Stress Prediction (Phase 8 Prototype)
        ml_inference_result = None
        assessment_method = "RULE_ENGINE"
        ml_disagreement = False
        ml_disagreement_details = None

        if is_ml_advisory_enabled():
            live_ndre = s2_meta.get("ndre") if s2_meta else None
            live_msavi = s2_meta.get("msavi") if s2_meta else None

            # Determine ML model regime:
            # - '5feat' (default): Phase 8 Academic Prototype with 5-feature Random Forest as primary predictor.
            # - '9feat': Legacy benchmark regime requiring seasonal precipitation (used in Phase 7C/7E feature audits).
            active_regime = ml_model_regime or os.getenv("ML_MODEL_REGIME")
            if not active_regime:
                farm_notes = str(farm.get("notes") or "").lower() if farm else ""
                if "phase7c" in farm_notes or "phase7e" in farm_notes or farm_id in (201, 305):
                    active_regime = "9feat"
                else:
                    active_regime = "5feat"

            try:
                if active_regime == "9feat":
                    # Legacy 9-feature model: requires seasonal reanalysis precipitation
                    ml_inference_result = predict_crop_stress(
                        crop_name=crop,
                        s2_ndvi=mean_ndvi,
                        s2_ndwi=mean_ndwi,
                        s2_ndre=live_ndre,
                        s2_msavi=live_msavi,
                        smap_sm_pct=sm_pct,
                        era5_precip_season_mm=None,
                    )
                    observed_stress, assessment_method, ml_disagreement, ml_disagreement_details = hybrid_stress_assessment(
                        rule_observed_stress=rule_observed_stress,
                        ml_result=ml_inference_result,
                        crop_name=crop,
                        sm_pct=sm_pct,
                        ndvi=mean_ndvi,
                        ml_as_primary=False,
                    )
                else:
                    # Phase 8 Academic Prototype: Live-native 5-feature Random Forest as primary predictor
                    ml_inference_result = predict_crop_stress_5feat(
                        crop_name=crop,
                        s2_ndvi=mean_ndvi,
                        s2_ndwi=mean_ndwi,
                        s2_ndre=live_ndre,
                        s2_msavi=live_msavi,
                        smap_sm_pct=sm_pct,
                    )
                    observed_stress, assessment_method, ml_disagreement, ml_disagreement_details = primary_ml_stress_assessment(
                        rule_observed_stress=rule_observed_stress,
                        ml_result=ml_inference_result,
                        crop_name=crop,
                        sm_pct=sm_pct,
                        ndvi=mean_ndvi,
                    )
            except Exception as ml_err:
                pipeline_logger.warning("ML inference error for farm %s: %s; falling back to rule engine", farm_id, ml_err)
                ml_inference_result = None
                observed_stress = rule_observed_stress
                assessment_method = "RULE_FALLBACK_ERROR"
        else:
            observed_stress = rule_observed_stress

        # Validate rain_48h safely before guardrail
        try:
            safe_rain = validate_forecast_rainfall(rain_48h)
        except (ValueError, TypeError) as rain_val_err:
            pipeline_logger.warning("Invalid rain_48h value (%r) for farm %s: %s; treating as unavailable", rain_48h, farm_id, rain_val_err)
            safe_rain = None
            rain_48h = None

        observed_stress, recommended_action, guardrail_triggered = apply_rainfall_guardrail(observed_stress, safe_rain)
        advisory = generate_irrigation_advisory(observed_stress, recommended_action, crop, CROP_GROWTH_STAGE, safe_rain)

        # 6. Database Write-Back
        val_status = val_result.get("outcome") if val_result else "UNVALIDATED"
        lc_class = val_result.get("land_cover_class") if val_result else None

        adv_record = save_advisory_to_database(
            farm_id=farm_id,
            stress_level=observed_stress,
            recommendation=advisory,
            ndvi=mean_ndvi,
            ndwi=mean_ndwi,
            soil_moisture=sm_pct,
            rainfall_48h=rain_48h,
            crop_stage=CROP_GROWTH_STAGE,
            observed_stress=observed_stress,
            rain_forecast_mm=rain_48h,
            guardrail_triggered=guardrail_triggered,
            recommended_action=recommended_action,
            sentinel_scene_date=s2_meta["date"] if s2_meta else None,
            smap_obs_date=sm_meta["date"] if sm_meta else None,
            db_url=db_url,
            validation_status=val_status,
            land_cover_class=lc_class,
        )

        # 6b. Machine Learning Shadow-Mode Evaluation (Non-Blocking / Telemetry Only)
        shadow_result = None
        try:
            from pipeline.ml_shadow_engine import evaluate_ml_shadow
            shadow_result = evaluate_ml_shadow(
                farm_id=farm_id,
                advisory_id=adv_record.get("id"),
                crop_name=crop,
                rule_observed_stress=observed_stress,
                rule_recommended_action=recommended_action,
                rule_guardrail_triggered=guardrail_triggered,
                s2_ndvi=mean_ndvi,
                s2_ndwi=mean_ndwi,
                smap_sm_pct=sm_pct,
                era5_precip_season_mm=rain_48h,
                db_url=db_url,
            )
        except Exception as shadow_err:
            pipeline_logger.warning("Shadow ML evaluation error for farm %s (non-fatal): %s", farm_id, shadow_err)

        # 7. Automated WhatsApp Text Delivery
        advisory_sent = False
        duplicate_delivery_suppressed = False
        delivery_error = None
        advisory_data = {
            "id": adv_record["id"],
            "farm_id": farm_id,
            "observation_date": adv_record["observation_date"],
            "created_at": adv_record.get("created_at"),
            "crop_stage": CROP_GROWTH_STAGE,
            "stress_level": observed_stress,
            "recommendation": advisory,
            "ndvi": mean_ndvi,
            "ndwi": mean_ndwi,
            "soil_moisture": sm_pct,
            "rainfall_48h": rain_48h,
            "observed_stress": observed_stress,
            "rain_forecast_mm": rain_48h,
            "guardrail_triggered": guardrail_triggered,
            "recommended_action": recommended_action,
            "sentinel_scene_date": s2_meta["date"] if s2_meta else None,
            "smap_obs_date": sm_meta["date"] if sm_meta else None,
            "validation_status": val_status,
            "land_cover_class": lc_class,
            "is_demo": is_demo,
            "crop_validation": crop_val_result,
            "ml_inference": ml_inference_result,
            "assessment_method": assessment_method,
            "ml_disagreement": ml_disagreement,
            "ml_disagreement_details": ml_disagreement_details,
            "rule_observed_stress": rule_observed_stress,
        }
        farm_dict = dict(farm) if farm else {}
        farm_dict["is_demo"] = is_demo

        if auto_send_advisory and outbound_sender and farmer_mobile and format_status_advisory:
            # Check delivery deduplication cooldown to prevent duplicate cards across retries or rapid pipeline triggers
            now_ts = time.time()
            with _DELIVERED_ADVISORIES_LOCK:
                last_delivered = _DELIVERED_ADVISORIES.get(farm_id, 0.0)
                if not force and (now_ts - last_delivered) < ADVISORY_DELIVERY_COOLDOWN_SECONDS:
                    pipeline_logger.info(
                        "Advisory delivery for farm %s was suppressed (already delivered %.1fs ago, cooldown %.0fs)",
                        farm_id, now_ts - last_delivered, ADVISORY_DELIVERY_COOLDOWN_SECONDS
                    )
                    duplicate_delivery_suppressed = True
                else:
                    _DELIVERED_ADVISORIES[farm_id] = now_ts

            if not duplicate_delivery_suppressed:
                try:
                    advisory_card = format_status_advisory(farm_dict, advisory_data, lang=farmer_lang)
                    outbound_sender(farmer_mobile, advisory_card)
                    advisory_sent = True
                    pipeline_logger.info(
                        "Delivered automated advisory for farm %s to %s (lang: %s)",
                        farm_id, mask_phone(farmer_mobile), farmer_lang
                    )
                except Exception as send_err:
                    delivery_error = str(send_err)
                    pipeline_logger.error(
                        "Failed to deliver automated advisory to %s for farm %s: %s (persisted advisory preserved)",
                        mask_phone(farmer_mobile), farm_id, send_err
                    )

        # 7b. Multilingual Voice-Based Advisory Delivery
        voice_sent = False
        voice_script = None
        voice_media_id = None
        should_send_voice = send_voice_advisory or (os.getenv("ENABLE_VOICE_ADVISORY", "false").lower() == "true")

        if should_send_voice and farmer_mobile:
            try:
                if format_voice_script is not None:
                    voice_script = format_voice_script(farm_dict, advisory_data, language=farmer_lang)

                if voice_script:
                    provider = tts_provider
                    if provider is None and get_tts_provider is not None:
                        provider = get_tts_provider()

                    _deliver_voice = deliver_voice_advisory
                    if _deliver_voice is None:
                        try:
                            from whatsapp.registration_flow import deliver_voice_advisory as _deliver_voice
                        except ImportError:
                            try:
                                from khetsense.whatsapp.registration_flow import deliver_voice_advisory as _deliver_voice
                            except Exception:
                                _deliver_voice = None

                    if _deliver_voice is not None:
                        voice_res = _deliver_voice(
                            to=farmer_mobile,
                            script_text=voice_script,
                            lang=farmer_lang,
                            tts_provider=provider,
                            outbound_voice_sender=outbound_voice_sender,
                        )
                        if voice_res.get("status") == "success":
                            voice_sent = True
                            voice_media_id = voice_res.get("media_id")
                            pipeline_logger.info(
                                "Delivered voice advisory for farm %s to %s (lang: %s)",
                                farm_id, mask_phone(farmer_mobile), farmer_lang
                            )
                        else:
                            pipeline_logger.warning(
                                "Voice advisory delivery failed for farm %s: %s",
                                farm_id, voice_res.get("error")
                            )
                else:
                    pipeline_logger.info(
                        "Voice script generation skipped (advisory withheld or unsuitable) for farm %s", farm_id
                    )
            except Exception as voice_err:
                # Non-fatal: failures in voice synthesis/delivery must never prevent text advisory delivery
                pipeline_logger.error(
                    "Non-fatal error during voice advisory generation for farm %s: %s",
                    farm_id, voice_err
                )

        return {
            "status": "success",
            "farm_id": farm_id,
            "advisory_id": adv_record["id"],
            "observed_stress": observed_stress,
            "recommended_action": recommended_action,
            "advisory": advisory,
            "advisory_sent": advisory_sent,
            "preferred_language": farmer_lang,
            "voice_sent": voice_sent,
            "voice_script": voice_script,
            "voice_media_id": voice_media_id,
            "shadow_evaluation": shadow_result,
            "crop_validation": crop_val_result,
            "ml_inference": ml_inference_result,
            "assessment_method": assessment_method,
            "ml_disagreement": ml_disagreement,
            "ml_disagreement_details": ml_disagreement_details,
            "rule_observed_stress": rule_observed_stress,
            "delivery_error": delivery_error,
            "duplicate_delivery_suppressed": duplicate_delivery_suppressed,
        }

    except Exception as e:
        pipeline_logger.error("Pipeline failure for farm %s: %s", farm_id, e)
        fail_voice_sent = False
        if auto_send_advisory and outbound_sender and farmer_mobile and get_message:
            try:
                fail_notice = get_message(
                    "pipeline_failed_notice",
                    lang=farmer_lang,
                    farm_id=farm_id,
                    name=farmer_name,
                )
                _send_farmer_response = None
                try:
                    from whatsapp.registration_flow import send_farmer_response as _send_farmer_response
                except ImportError:
                    try:
                        from khetsense.whatsapp.registration_flow import send_farmer_response as _send_farmer_response
                    except Exception:
                        _send_farmer_response = None

                if _send_farmer_response is not None:
                    provider = tts_provider
                    if provider is None and get_tts_provider is not None:
                        try:
                            provider = get_tts_provider()
                        except Exception:
                            provider = None
                    send_res = _send_farmer_response(
                        to=farmer_mobile,
                        text=fail_notice,
                        lang=farmer_lang,
                        outbound_sender=outbound_sender,
                        outbound_voice_sender=outbound_voice_sender,
                        enable_voice=is_voice_chatbot_enabled,
                        tts_provider=provider,
                    )
                    fail_voice_sent = bool(send_res.get("voice_sent", False))
                else:
                    outbound_sender(farmer_mobile, fail_notice)
            except Exception as send_err:
                pipeline_logger.error("Failed to send failure notification to %s: %s", mask_phone(farmer_mobile), send_err)
        return {
            "status": "error",
            "farm_id": farm_id,
            "error": str(e),
            "voice_sent": fail_voice_sent,
        }
    finally:
        with _ACTIVE_PIPELINE_LOCK:
            _ACTIVE_PIPELINE_RUNS.discard(farm_id)


__all__ = [
    "classify_ndvi_stress",
    "classify_soil_moisture_stress",
    "get_more_severe",
    "apply_rainfall_guardrail",
    "generate_irrigation_advisory",
    "validate_forecast_rainfall",
    "run_pipeline_for_farm",
    "is_pipeline_running",
    "get_farm_from_database",
    "save_advisory_to_database",
    "audit_validation_failure",
]


# ==============================================================================
# 5. MAIN EXECUTION PIPELINE
# ==============================================================================

def parse_pipeline_args():
    """Parses optional CLI arguments: --farm-id <N>, --db-only, and --help."""
    target_farm_id = 1
    db_only = False
    for i, arg in enumerate(sys.argv):
        if arg in ("--help", "-h"):
            print("Usage: python pipeline/test_pipeline.py [--farm-id <N>] [--db-only]")
            sys.exit(0)
        elif arg in ("--db-only", "--test-db"):
            db_only = True
        elif arg.startswith("--farm-id="):
            try:
                target_farm_id = int(arg.split("=")[1])
            except ValueError:
                pass
        elif arg == "--farm-id" and i + 1 < len(sys.argv):
            try:
                target_farm_id = int(sys.argv[i + 1])
            except ValueError:
                pass
    return target_farm_id, db_only


def main(farm_id: Optional[int] = None):
    cli_farm_id, db_only = parse_pipeline_args()
    target_farm_id = farm_id if farm_id is not None else cli_farm_id

    print("=" * 76)
    print("      KHETSENSE AI - SATELLITE & SOIL DATA PIPELINE TEST (STEP 3)      ")
    print("=" * 76)

    # 1. Environment and Farm Setup (Retrieved from Supabase PostGIS)
    print("\n[1] TEST FARM SPECIFICATIONS (RETRIEVED FROM DATABASE)")
    try:
        farm = get_farm_from_database(target_farm_id)
        farm_id = farm["id"]
        farmer_name = farm["farmer_name"]
        village = farm["village"]
        district = farm["district"]
        state = farm["state"]
        loc_parts = [p for p in [village, district, state] if p]
        farm_location = ", ".join(loc_parts) + (", India" if loc_parts else "India")
        crop = farm["crop_name"]
        farm_area_str = f"{farm['farm_area']} {farm['farm_area_unit']}"
        poly_lat_lon = farm["polygon_lat_lon"]
        centroid_lat = farm["centroid_lat"]
        centroid_lon = farm["centroid_lon"]
        ee_coords = farm["ee_coords"]
        n_points = farm["n_points"]
        is_valid = farm["is_valid"]
        srid = farm["srid"]

        print(f"  * Farm ID:                    {farm_id}")
        print(f"  * Farmer Name:                {farmer_name}")
        print(f"  * Village:                    {village}")
        print(f"  * District:                   {district}")
        print(f"  * State:                      {state}")
        print(f"  * Crop:                       {crop}")
        print(f"  * Growth Stage:               {CROP_GROWTH_STAGE}")
        print(f"  * Farm Area:                  {farm_area_str}")
        print(f"  * Number of Polygon Vertices: {n_points}")
        print(f"  * First Polygon Coordinate:   Lon {ee_coords[0][0]}, Lat {ee_coords[0][1]}")
        print(f"  * Last Polygon Coordinate:    Lon {ee_coords[-1][0]}, Lat {ee_coords[-1][1]}")
        print(f"  * Polygon SRID:               {srid}")
        print(f"  * Polygon Is Valid:           {is_valid}")
        print(f"  * Centroid Latitude:          {centroid_lat:.5f}")
        print(f"  * Centroid Longitude:         {centroid_lon:.5f}")
        print(f"  * Polygon (Lat/Lon):")
        for pt in poly_lat_lon:
            print(f"      [{pt[0]:.5f}, {pt[1]:.5f}]")
    except Exception as e:
        print(f"  [ERROR] Database retrieval failed: {e}")
        sys.exit(1)

    if db_only:
        print("\n[OK] Database retrieval validation complete (external APIs skipped as requested).")
        return

    # 2. Google Earth Engine Authentication
    print("\n[2] AUTHENTICATING TO GOOGLE EARTH ENGINE")
    try:
        project_id = authenticate_earth_engine(EE_KEY_PATH)
        print(f"  [OK] Connected to GEE successfully (Project: {project_id})")
        print(f"  [OK] Service account key: {os.path.basename(EE_KEY_PATH)}")
    except Exception as e:
        print(f"  [ERROR] Earth Engine Authentication Failed: {e}")
        sys.exit(1)

    farm_geom = ee.Geometry.Polygon([ee_coords])

    # 3. Sentinel-2 NDVI & NDWI Retrieval
    print("\n[3] FETCHING SENTINEL-2 SURFACE REFLECTANCE HARMONIZED")
    mean_ndvi, mean_ndwi, s2_meta, s2_err = fetch_sentinel2_indices(farm_geom)
    if s2_err:
        print(f"  [ERROR] Sentinel-2 Error: {s2_err}")
    else:
        print(f"  [OK] Scene Date:       {s2_meta['date']} (Cloud Cover: {s2_meta['cloud_cover_pct']:.1f}%)")
        print(f"  [OK] Scene ID:         {s2_meta['image_id']}")
        print(f"  [OK] Mean NDVI:        {mean_ndvi:.4f}  [Formula: (B8 - B4) / (B8 + B4)]")
        print(f"  [OK] Mean NDWI:        {mean_ndwi:.4f}  [Formula: (B8 - B11) / (B8 + B11) - Gao (vegetation water content)]")
        if s2_meta.get("ndre") is not None:
            print(f"  [OK] Mean NDRE:        {s2_meta['ndre']:.4f}  [Formula: (B8 - B5) / (B8 + B5) - Red Edge (Barnes et al. 2000)]")
        if s2_meta.get("msavi") is not None:
            print(f"  [OK] Mean MSAVI:       {s2_meta['msavi']:.4f}  [Formula: Qi et al. 1994 (Soil-Adjusted)]")

    # 4. NASA Earthdata Authentication & CMR Granule Query
    print("\n[4] AUTHENTICATING TO NASA EARTHDATA (SMAP SPL3SMP_E)")
    ed_user = os.getenv("EARTHDATA_USERNAME")
    ed_pass = os.getenv("EARTHDATA_PASSWORD")
    min_lon = min(pt[0] for pt in ee_coords)
    min_lat = min(pt[1] for pt in ee_coords)
    max_lon = max(pt[0] for pt in ee_coords)
    max_lat = max(pt[1] for pt in ee_coords)
    bbox_str = f"{min_lon},{min_lat},{max_lon},{max_lat}"

    ed_info, ed_err = authenticate_and_query_earthdata(ed_user, ed_pass, bbox_str)
    if ed_err:
        print(f"  [ERROR] NASA Earthdata Query Error: {ed_err}")
    else:
        auth_status = "Verified with DAAC" if ed_info["auth_verified"] else "Active"
        print(f"  [OK] NASA Earthdata Authentication: Success ({auth_status})")
        print(f"  [OK] Latest Granule:  {ed_info['granule_id']}")
        print(f"  [OK] Granule Date:    {ed_info['time_start']}")

    # 5. SMAP SPL3SMP_E Soil Moisture Value
    print("\n[5] FETCHING SMAP SPL3SMP_E SURFACE SOIL MOISTURE")
    sm_pct, sm_meta, sm_err = fetch_smap_soil_moisture(centroid_lon, centroid_lat)
    if sm_err:
        print(f"  [ERROR] SMAP Soil Moisture Error: {sm_err}")
    else:
        print(f"  [OK] SMAP Product:    {sm_meta['dataset']}")
        print(f"  [OK] Observation:     {sm_meta['date']}")
        print(f"  [OK] Volumetric SM:   {sm_meta['raw_m3m3']:.4f} m3/m3")
        print(f"  [OK] Regional Soil Moisture (SMAP 9-km): {sm_pct:.2f}%")

    # 6. OpenWeather 48-Hour Rainfall Forecast
    print("\n[6] FETCHING OPENWEATHER 48-HOUR RAINFALL FORECAST")
    owm_key = os.getenv("OPENWEATHER_API_KEY")
    rain_48h, rain_err = fetch_openweather_forecast(owm_key, centroid_lat, centroid_lon)
    if rain_err:
        print(f"  [ERROR] OpenWeather Error: {rain_err}")
    else:
        print(f"  [OK] Centroid:         Lat {centroid_lat:.4f}, Lon {centroid_lon:.5f}")
        print(f"  [OK] 48-Hour Rainfall: {rain_48h:.2f} mm")

    # 7. Stress Classification & Guardrails
    print("\n[7] STRESS CLASSIFICATION & GUARDRAIL APPLICATION")
    ndvi_class = classify_ndvi_stress(mean_ndvi)
    sm_class = classify_soil_moisture_stress(sm_pct)
    observed_stress = get_more_severe(ndvi_class, sm_class)
    observed_stress, recommended_action, guardrail_triggered = apply_rainfall_guardrail(observed_stress, rain_48h)
    advisory = generate_irrigation_advisory(observed_stress, recommended_action, crop, CROP_GROWTH_STAGE, rain_48h)

    ndvi_val_str = f"{mean_ndvi:.4f}" if mean_ndvi is not None else "Missing"
    sm_val_str = f"{sm_pct:.2f}%" if sm_pct is not None else "Missing"
    ndwi_val_str = f"{mean_ndwi:.4f}" if mean_ndwi is not None else "Missing"
    rain_str = f"{rain_48h:.2f} mm" if rain_48h is not None else "Missing"

    guardrail_status = (
        f"Triggered (forecast rain {rain_str} -> action: '{recommended_action}')"
        if guardrail_triggered
        else f"Not Triggered (forecast rain {rain_str} < R1 {RAINFALL_CONFIG.R1:.1f} mm -> action: '{recommended_action}')"
    )

    print(f"  * NDVI Classification:          {ndvi_class} (Value: {ndvi_val_str})")
    print(f"  * Regional SM (SMAP 9-km):      {sm_class} (Value: {sm_val_str})")
    print(f"  * Observed Stress (Fusion):     {observed_stress}")
    print(f"  * Rainfall Guardrail:           {guardrail_status}")
    print(f"  * Recommended Action:           {recommended_action}")

    # 8. Database Write-Back (Advisory & Audit Trail)
    print("\n[8] SAVING ADVISORY & AUDIT METRICS TO DATABASE")
    try:
        adv_record = save_advisory_to_database(
            farm_id=farm_id,
            stress_level=observed_stress,
            recommendation=advisory,
            ndvi=mean_ndvi,
            ndwi=mean_ndwi,
            soil_moisture=sm_pct,
            rainfall_48h=rain_48h,
            crop_stage=CROP_GROWTH_STAGE,
            observed_stress=observed_stress,
            rain_forecast_mm=rain_48h,
            guardrail_triggered=guardrail_triggered,
            recommended_action=recommended_action,
            sentinel_scene_date=s2_meta["date"] if s2_meta else None,
            smap_obs_date=sm_meta["date"] if sm_meta else None,
        )
        print(f"  [OK] Advisory record saved to 'advisories' table (Record ID: {adv_record['id']})")
        print(f"  [OK] Linked to Farm ID:      {adv_record['farm_id']}")
        print(f"  [OK] Observation Date:       {adv_record['observation_date']}")
        print(f"  [OK] Stress Level Saved:     {adv_record['stress_level']}")
        print(f"  [OK] Timestamp (created_at): {adv_record['created_at']}")
    except Exception as e:
        print(f"  [ERROR] Database write-back failed: {e}")

    # 9. Summary Output
    print("\n" + "=" * 76)
    print("                         FINAL PIPELINE SUMMARY                         ")
    print("=" * 76)
    print(f"  Farm Location:                      {farm_location}")
    print(f"  Crop & Stage:                       {crop} ({CROP_GROWTH_STAGE})")
    print(f"  NDVI (Veg Vigour):                  {ndvi_val_str}  -> {ndvi_class}")
    print(f"  NDWI (Canopy Water):                {ndwi_val_str}  [Gao (vegetation water content) (B8-B11)/(B8+B11)]")
    print(f"  Regional Soil Moisture (SMAP 9-km): {sm_val_str}  -> {sm_class}")
    print(f"  48h Forecast Rainfall:              {rain_str}")
    print(f"  Rainfall Guardrail Status:          {guardrail_status}")
    print(f"  OBSERVED STRESS:                    {observed_stress}")
    print(f"  RECOMMENDED ACTION:                 {recommended_action}")
    print(f"  IRRIGATION ADVISORY:                {advisory}")
    print("=" * 76)
    print("Decision Layer: Rule-Based Guardrail Engine (XGBoost is future work)")
    print("=" * 76)


if __name__ == "__main__":
    main()
