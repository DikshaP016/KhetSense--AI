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
import requests
from dotenv import load_dotenv
from typing import Optional, Dict, Any
import ee
import psycopg2

# Ensure UTF-8 output encoding on Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


# ==============================================================================
# 1. CONFIGURATION & TEST FARM PARAMETERS
# ==============================================================================

# Find project root relative to this script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))

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


def get_farm_from_database(farm_id=1):
    """
    Retrieve farm metadata and PostGIS polygon from Supabase PostgreSQL.
    Converts coordinates to the format expected by the pipeline.
    """
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL is not set in environment.")

    conn = psycopg2.connect(db_url)
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
    db_url=None,
):
    """
    Save computed advisory and audit input indices to Supabase PostgreSQL.
    Stores input metrics (NDVI, NDWI, SMAP soil moisture, rainfall) for complete audit trail.
    """
    if not db_url:
        db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL is not set in environment.")

    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
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
            cur.execute(
                insert_sql,
                (
                    farm_id,
                    ndvi,
                    ndwi,
                    soil_moisture,
                    rainfall_48h,
                    crop_stage,
                    stress_level,
                    recommendation,
                ),
            )
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


def fetch_sentinel2_indices(geometry):
    """
    Fetch the most recent Sentinel-2 Surface Reflectance Harmonized scene (<20% clouds),
    calculate NDVI = (B8 - B4) / (B8 + B4) and Gao's NDWI = (B8 - B11) / (B8 + B11),
    and compute their mean values over the polygon.
    """
    s2_col = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(geometry)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20))
        .sort("system:time_start", False)
    )

    count = s2_col.size().getInfo()
    if count == 0:
        return None, None, None, "No cloud-free Sentinel-2 images found for this polygon."

    img = s2_col.first()
    date_str = ee.Date(img.get("system:time_start")).format("YYYY-MM-dd HH:mm:ss").getInfo()
    cloud_pct = img.get("CLOUDY_PIXEL_PERCENTAGE").getInfo()

    # NDVI = (NIR - Red) / (NIR + Red) -> Sentinel-2: NIR = B8, Red = B4
    ndvi = img.normalizedDifference(["B8", "B4"]).rename("NDVI")

    # Gao's NDWI = (NIR - SWIR) / (NIR + SWIR) -> Sentinel-2: NIR = B8, SWIR = B11
    ndwi = img.normalizedDifference(["B8", "B11"]).rename("NDWI")

    stats = (
        ndvi.addBands(ndwi)
        .reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=geometry,
            scale=10,
            maxPixels=1e9,
        )
        .getInfo()
    )

    mean_ndvi = stats.get("NDVI")
    mean_ndwi = stats.get("NDWI")

    metadata = {
        "date": date_str,
        "cloud_cover_pct": cloud_pct,
        "image_id": img.id().getInfo(),
    }

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


def fetch_smap_soil_moisture(centroid_lon, centroid_lat):
    """
    Fetch the latest available SMAP SPL3SMP_E surface soil moisture value
    by sampling the grid cell containing the farm centroid.

    Methodological Note:
    - SMAP provides approximately 9-km spatial soil-moisture information.
    - KhetSense samples the SMAP grid cell containing the farm centroid.
    - Sentinel-2 provides the field-scale vegetation information.

    Returns soil moisture in percentage (0-100%).
    """
    try:
        point = ee.Geometry.Point([centroid_lon, centroid_lat])
        col = (
            ee.ImageCollection("NASA/SMAP/SPL3SMP_E/006")
            .filterBounds(point)
            .sort("system:time_start", False)
        )

        count = col.size().getInfo()
        if count == 0:
            col = (
                ee.ImageCollection("NASA/SMAP/SPL3SMP_E/005")
                .filterBounds(point)
                .sort("system:time_start", False)
            )
            count = col.size().getInfo()
            if count == 0:
                return None, None, "No SMAP SPL3SMP_E imagery found for centroid."

        # Search the latest granules to find the latest valid overpass
        # (SMAP has a 2-3 day revisit cycle, so off-swath days have masked pixels over local coordinates)
        candidates = col.limit(10).getInfo().get("features", [])
        img = None
        date_str = None
        sm_val = None
        dataset_id = None

        for feat in candidates:
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
            val = stats.get("soil_moisture_am")
            if val is None:
                val = stats.get("soil_moisture_pm")
            if val is not None:
                img = cand_img
                sm_val = val
                dataset_id = feat["id"]
                date_str = ee.Date(feat["properties"]["system:time_start"]).format("YYYY-MM-dd HH:mm:ss").getInfo()
                break

        if sm_val is None:
            return None, None, "SMAP pixel data over centroid is masked/null in recent scenes."

        # SMAP volumetric soil moisture is m^3/m^3 (0.0 to ~0.5)
        # Convert to percentage
        sm_pct = sm_val * 100.0 if sm_val <= 1.0 else sm_val

        metadata = {
            "date": date_str,
            "dataset": dataset_id,
            "raw_m3m3": sm_val,
        }

        return sm_pct, metadata, None

    except Exception as e:
        return None, None, f"Error fetching SMAP soil moisture: {str(e)}"


def fetch_openweather_forecast(api_key, lat, lon):
    """
    Fetch 5-day / 3-hour forecast for the centroid coordinates,
    summing precipitation over the next 48 hours.
    """
    if not api_key or api_key.strip() == "":
        return None, "OPENWEATHER_API_KEY missing or not found in .env"

    url = f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&appid={api_key}&units=metric"

    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            return None, f"OpenWeather API error (status {resp.status_code}): {resp.text[:100]}"

        data = resp.json()
        # Next 48 hours = up to 16 three-hour intervals
        forecast_entries = data.get("list", [])[:16]
        total_rain_48h = 0.0

        for item in forecast_entries:
            rain_obj = item.get("rain", {})
            r3h = rain_obj.get("3h", 0.0) if isinstance(rain_obj, dict) else 0.0
            total_rain_48h += float(r3h)

        return total_rain_48h, None

    except Exception as e:
        return None, f"OpenWeather request exception: {str(e)}"


# ==============================================================================
# 4. KHETSENSE DECISION RULES & GUARDRAILS (RE-EXPORTED FROM classifier.py)
# ==============================================================================

try:
    from .classifier import (
        classify_ndvi_stress,
        classify_soil_moisture_stress,
        get_more_severe,
        apply_rainfall_guardrail,
        generate_irrigation_advisory,
    )
except ImportError:
    try:
        from pipeline.classifier import (
            classify_ndvi_stress,
            classify_soil_moisture_stress,
            get_more_severe,
            apply_rainfall_guardrail,
            generate_irrigation_advisory,
        )
    except ImportError:
        from classifier import (
            classify_ndvi_stress,
            classify_soil_moisture_stress,
            get_more_severe,
            apply_rainfall_guardrail,
            generate_irrigation_advisory,
        )


# ==============================================================================
# 5. MAIN EXECUTION PIPELINE
# ==============================================================================

def parse_pipeline_args():
    """Parses optional CLI arguments: --farm-id <N> and --db-only."""
    target_farm_id = 1
    db_only = False
    for i, arg in enumerate(sys.argv):
        if arg in ("--db-only", "--test-db"):
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
    preliminary_class = get_more_severe(ndvi_class, sm_class)
    final_class, guardrail_status = apply_rainfall_guardrail(preliminary_class, rain_48h)
    advisory = generate_irrigation_advisory(final_class, crop, CROP_GROWTH_STAGE, rain_48h)

    ndvi_val_str = f"{mean_ndvi:.4f}" if mean_ndvi is not None else "Missing"
    sm_val_str = f"{sm_pct:.2f}%" if sm_pct is not None else "Missing"
    ndwi_val_str = f"{mean_ndwi:.4f}" if mean_ndwi is not None else "Missing"

    print(f"  * NDVI Classification:          {ndvi_class} (Value: {ndvi_val_str})")
    print(f"  * Regional SM (SMAP 9-km):      {sm_class} (Value: {sm_val_str})")
    print(f"  * Preliminary (More Severe):    {preliminary_class}")
    print(f"  * Rainfall Guardrail:           {guardrail_status}")
    print(f"  * Final Stress Classification:  {final_class}")

    # 8. Database Write-Back (Advisory & Audit Trail)
    print("\n[8] SAVING ADVISORY & AUDIT METRICS TO DATABASE")
    try:
        adv_record = save_advisory_to_database(
            farm_id=farm_id,
            stress_level=final_class,
            recommendation=advisory,
            ndvi=mean_ndvi,
            ndwi=mean_ndwi,
            soil_moisture=sm_pct,
            rainfall_48h=rain_48h,
            crop_stage=CROP_GROWTH_STAGE,
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
    rain_str = f"{rain_48h:.2f} mm" if rain_48h is not None else "Missing"
    print(f"  48h Forecast Rainfall:              {rain_str}")
    print(f"  Rainfall Guardrail Status:          {guardrail_status}")
    print(f"  FINAL STRESS CLASSIFICATION:        {final_class}")
    print(f"  IRRIGATION ADVISORY:                {advisory}")
    print("=" * 76)
    print("Decision Layer: Rule-Based Guardrail Engine (XGBoost is future work)")
    print("=" * 76)


if __name__ == "__main__":
    main()
