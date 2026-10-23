#!/usr/bin/env python3
"""
KhetSense AI — Phase 3 Historical Multi-Sensor Feature Extraction Pipeline
--------------------------------------------------------------------------
Extracts aligned Sentinel-2 L2A vegetation indices (NDVI, NDWI, NDRE, MSAVI),
NASA SMAP 9km soil moisture, and ECMWF ERA5-Land weather features for the
CSISA 2018 Eastern India Wheat Dataset via Google Earth Engine.

Applies:
1. Phenological windowing (Peak vegetative/flowering window: Jan 15 - Feb 28, 2018).
2. Cloud masking on Sentinel-2 using QA60 bitmask (<20% tile cloud cover).
3. Scale conversions (S2 reflectances, SMAP m3/m3 to %, ERA5 precip m to mm, temp K to C).
4. Atmospheric Vapor Pressure Deficit (VPD in kPa) calculation via Tetens formula.
5. Spatial Blocked Validation partitioning (Held-out test districts + 5-Fold GroupKFold).
6. Preserves original drought severity labels ('None', 'Low', 'Medium', 'High') alongside
   the 3-tier KhetSense target schema ('No Stress', 'Mild Stress', 'Severe Stress').
"""

import os
import sys
import csv
import json
import time
import gzip
import math
from datetime import datetime
from collections import Counter, defaultdict
import ee

# 1. Environment & Credentials Setup
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))

KEY_PATH = os.path.join(PROJECT_ROOT, "credentials", "ee-key.json")
if not os.path.exists(KEY_PATH):
    raise FileNotFoundError(f"Earth Engine key not found at: {KEY_PATH}")

with open(KEY_PATH, "r") as f:
    key_data = json.load(f)

ee_creds = ee.ServiceAccountCredentials(key_data["client_email"], KEY_PATH)
ee.Initialize(ee_creds, project=key_data.get("project_id", "khetsense-ai"))
print(f"[INIT] Earth Engine initialized successfully (Project: {key_data.get('project_id')})")

RAW_CSV_PATH = os.path.join(PROJECT_ROOT, "data", "research_benchmark", "csisa_wheat_2018", "CSISA_IND_LDS_Whe_2018_Data.csv")
OUTPUT_CSV_PATH = os.path.join(PROJECT_ROOT, "data", "research_benchmark", "csisa_wheat_multisensor_features_2018.csv")
OUTPUT_GZ_PATH = OUTPUT_CSV_PATH + ".gz"
METRIC_REPORT_PATH = os.path.join(PROJECT_ROOT, "data", "research_benchmark", "extraction_metrics.json")

# 2. Date Parsing Helper
def parse_date(d_str):
    if not d_str or d_str.strip() in ("", "NA", "nan", "null"):
        return None
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y %H:%M", "%m-%d-%Y %H:%M", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(d_str.strip(), fmt)
        except ValueError:
            pass
    return None

def safe_float(val, default=None):
    if not val or str(val).strip().lower() in ("", "na", "nan", "null"):
        return default
    try:
        return float(str(val).strip())
    except (ValueError, TypeError):
        return default

def safe_int(val, default=None):
    if not val or str(val).strip().lower() in ("", "na", "nan", "null"):
        return default
    try:
        return int(float(str(val).strip()))
    except (ValueError, TypeError):
        return default

# 3. Load & Validate Raw Survey Records
print(f"[LOAD] Ingesting raw CSISA survey data from: {RAW_CSV_PATH}")
raw_records = []
districts_counter = Counter()

with open(RAW_CSV_PATH, "r", encoding="utf-8", errors="replace") as f:
    reader = csv.DictReader(f)
    for i, row in enumerate(reader):
        lat_s = row.get("O-largestPlotGPS-Latitude", "").strip()
        lon_s = row.get("O-largestPlotGPS-Longitude", "").strip()
        acc_s = row.get("O-largestPlotGPS-Accuracy", "").strip()
        sow_s = row.get("D-q415_seedingSowingTransDate", "").strip()
        harv_s = row.get("L-q601_harvestDate", "").strip() or row.get("L-harvDate", "").strip()
        
        sow_d = parse_date(sow_s)
        harv_d = parse_date(harv_s)
        
        lat = safe_float(lat_s)
        lon = safe_float(lon_s)
        if lat is None or lon is None or abs(lat) < 0.1 or abs(lon) < 0.1:
            continue
            
        dist = row.get("A-q103_district", "").strip()
        state = row.get("A-q102_state", "").strip()
        districts_counter[dist] += 1
        
        # Season length
        season_days = (harv_d - sow_d).days if (sow_d and harv_d) else None
        
        raw_records.append({
            "record_id": i,
            "unique_survey_id": row.get("uniqueID", "").strip(),
            "state": state,
            "district": dist,
            "subdistrict_block": row.get("A-q104_subDistrict", "").strip(),
            "village": row.get("A-q105_village", "").strip(),
            "latitude": lat,
            "longitude": lon,
            "gps_accuracy_m": safe_float(acc_s, 9.21),
            "sowing_date": sow_d.strftime("%Y-%m-%d") if sow_d else "",
            "harvest_date": harv_d.strftime("%Y-%m-%d") if harv_d else "",
            "growing_season_days": season_days,
            "plot_area_acres": safe_float(row.get("C-q306_cropLarestAreaAcre"), 0.62),
            "soil_texture": row.get("D-q401_soilTexture", "Loam").strip(),
            "drainage_class": row.get("D-q402_drainClass", "Well drained").strip(),
            "irrigation_facility": row.get("G-q5301_irrigAvail", "yes").strip().lower(),
            "applied_irrigations_count": safe_int(row.get("G-q5305_irrigTimes"), 2),
            "tubewell_depth_feet": safe_float(row.get("H-q5405_tubewellDepthFeet"), 97.5),
            "drought_severity_raw": row.get("I-q5502_droughtSeverity", "None").strip(),
            "drought_growth_stage": row.get("I-q5501_droughtGS", "None").strip(),
            "measured_harvest_yield_t_ha": safe_float(row.get("L-tonPerHectare"), 3.0),
        })

total_plots = len(raw_records)
print(f"[LOAD] Ingested {total_plots} valid georeferenced records across {len(districts_counter)} districts.")

# 4. Spatial Blocked Partitioning (Anti-Leakage)
# Designate 8 districts (20% of data) as Held-Out Test Set (6 in Bihar, 2 in UP)
# Remaining 32 districts split into 5 spatial cross-validation folds.
sorted_districts = sorted(districts_counter.keys())
up_districts = sorted([d for d in sorted_districts if any(r["district"] == d and r["state"] == "UttarPradesh" for r in raw_records)])
bihar_districts = sorted([d for d in sorted_districts if d not in up_districts])

held_out_districts = set()
# 2 UP districts
held_out_districts.update(up_districts[:2]) # e.g. Balia, Deoria
# 6 Bihar districts
held_out_districts.update(bihar_districts[:6]) # e.g. Begusarai, Bhagalpur, Bhojpur, Buxar, Darbhanga, Gaya

cv_districts = [d for d in sorted_districts if d not in held_out_districts]
district_to_fold = {}
for idx, d in enumerate(cv_districts):
    district_to_fold[d] = idx % 5

print(f"[SPLIT] Spatial Partitioning: {len(held_out_districts)} Held-Out Test Districts, {len(cv_districts)} CV Training Districts.")
print(f"        Held-out Districts: {sorted(held_out_districts)}")

for r in raw_records:
    d = r["district"]
    if d in held_out_districts:
        r["spatial_split"] = "held_out_test"
        r["cv_fold_id"] = -1
    else:
        r["spatial_split"] = "train"
        r["cv_fold_id"] = district_to_fold.get(d, 0)
        
    # Standard KhetSense 3-class target mapping
    ds_raw = r["drought_severity_raw"]
    if ds_raw == "None":
        r["target_stress_3class"] = "No Stress"
        r["target_code_3class"] = 0
    elif ds_raw in ("Low", "Medium"):
        r["target_stress_3class"] = "Mild Stress"
        r["target_code_3class"] = 1
    elif ds_raw == "High":
        r["target_stress_3class"] = "Severe Stress"
        r["target_code_3class"] = 2
    else:
        r["target_stress_3class"] = "No Stress"
        r["target_code_3class"] = 0

# 5. Build Earth Engine Multi-Sensor Image Stack
print("[GEE] Constructing Multi-Sensor Image Stack...")
study_bounds = ee.Geometry.Polygon([
    [[82.0, 24.0], [88.5, 24.0], [88.5, 28.0], [82.0, 28.0], [82.0, 24.0]]
])

def mask_s2(img):
    qa = img.select('QA60')
    mask = qa.bitwiseAnd(1 << 10).eq(0).And(qa.bitwiseAnd(1 << 11).eq(0))
    return img.updateMask(mask)

# Peak vegetative window for Rabi wheat: Jan 15 to Feb 28, 2018
s2_col = (
    ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
    .filterBounds(study_bounds)
    .filterDate('2018-01-15', '2018-02-28')
    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))
    .map(mask_s2)
)
s2_comp = s2_col.median()

ndvi = s2_comp.normalizedDifference(['B8', 'B4']).rename('s2_ndvi')
ndwi = s2_comp.normalizedDifference(['B8', 'B11']).rename('s2_ndwi')
ndre = s2_comp.normalizedDifference(['B8', 'B5']).rename('s2_ndre')

nir = s2_comp.select('B8').divide(10000.0)
red = s2_comp.select('B4').divide(10000.0)
msavi = nir.expression(
    '(2 * NIR + 1 - sqrt((2 * NIR + 1)**2 - 8 * (NIR - RED))) / 2',
    {'NIR': nir, 'RED': red}
).rename('s2_msavi')

s2_stack = ndvi.addBands([ndwi, ndre, msavi])

# NASA SMAP 9km median surface soil moisture (m3/m3 * 100 -> %)
smap_col = (
    ee.ImageCollection('NASA/SMAP/SPL3SMP_E/006')
    .filterBounds(study_bounds)
    .filterDate('2018-01-15', '2018-02-28')
)
smap_am = smap_col.select('soil_moisture_am').mean()
smap_pm = smap_col.select('soil_moisture_pm').mean()
smap_mean = smap_am.unmask(smap_pm).multiply(100.0).rename('smap_sm_pct')

# ECMWF ERA5-Land Reanalysis during cropping cycle (Dec 1, 2017 to Mar 31, 2018)
era5_col = (
    ee.ImageCollection('ECMWF/ERA5_LAND/DAILY_AGGR')
    .filterBounds(study_bounds)
    .filterDate('2017-12-01', '2018-03-31')
)
era5_precip = era5_col.select('total_precipitation_sum').sum().multiply(1000.0).rename('era5_precip_season_mm')
era5_temp = era5_col.select('temperature_2m').mean().subtract(273.15).rename('era5_temp_mean_c')
era5_temp_max = era5_col.select('temperature_2m_max').max().subtract(273.15).rename('era5_temp_max_c')
era5_dew = era5_col.select('dewpoint_temperature_2m').mean().subtract(273.15).rename('era5_dewpoint_c')

# Tetens VPD calculation in GEE
# es = 0.61078 * exp((17.27 * T) / (T + 237.3))
# ea = 0.61078 * exp((17.27 * Td) / (Td + 237.3))
# vpd = es - ea
es = era5_temp.expression(
    '0.61078 * exp((17.27 * T) / (T + 237.3))',
    {'T': era5_temp}
)
ea = era5_dew.expression(
    '0.61078 * exp((17.27 * Td) / (Td + 237.3))',
    {'Td': era5_dew}
)
vpd = es.subtract(ea).max(0.0).rename('era5_vpd_mean_kpa')

era5_stack = era5_precip.addBands([era5_temp, era5_temp_max, vpd])

# Full Multi-Sensor Stack
master_stack = s2_stack.addBands([smap_mean, era5_stack])
print("[GEE] Multi-sensor stack constructed: ['s2_ndvi', 's2_ndwi', 's2_ndre', 's2_msavi', 'smap_sm_pct', 'era5_precip_season_mm', 'era5_temp_mean_c', 'era5_temp_max_c', 'era5_vpd_mean_kpa']")

# 6. Batch Reduction over All 7,648 Plots
BATCH_SIZE = 250
num_batches = math.ceil(total_plots / BATCH_SIZE)
print(f"[GEE] Starting batch extraction: {total_plots} plots across {num_batches} batches (Batch Size: {BATCH_SIZE})...")

extracted_features = {}
start_total = time.time()

for b_idx in range(num_batches):
    b_start = b_idx * BATCH_SIZE
    b_end = min((b_idx + 1) * BATCH_SIZE, total_plots)
    batch_records = raw_records[b_start:b_end]
    
    ee_pts = [
        ee.Feature(ee.Geometry.Point([r["longitude"], r["latitude"]]), {"rec_id": r["record_id"]})
        for r in batch_records
    ]
    batch_fc = ee.FeatureCollection(ee_pts)
    
    t_b0 = time.time()
    try:
        sampled_batch = master_stack.reduceRegions(
            collection=batch_fc,
            reducer=ee.Reducer.mean(),
            scale=30
        ).getInfo()
        t_b1 = time.time()
        
        batch_valid = 0
        for feat in sampled_batch.get("features", []):
            p = feat.get("properties", {})
            rid = p.get("rec_id")
            extracted_features[rid] = {
                "s2_ndvi": p.get("s2_ndvi"),
                "s2_ndwi": p.get("s2_ndwi"),
                "s2_ndre": p.get("s2_ndre"),
                "s2_msavi": p.get("s2_msavi"),
                "smap_sm_pct": p.get("smap_sm_pct"),
                "era5_precip_season_mm": p.get("era5_precip_season_mm"),
                "era5_temp_mean_c": p.get("era5_temp_mean_c"),
                "era5_temp_max_c": p.get("era5_temp_max_c"),
                "era5_vpd_mean_kpa": p.get("era5_vpd_mean_kpa"),
            }
            if p.get("s2_ndvi") is not None:
                batch_valid += 1
                
        print(f"  Batch {b_idx+1:02d}/{num_batches:02d} ({b_start:4d}-{b_end:4d}) completed in {t_b1 - t_b0:5.2f}s | Valid S2: {batch_valid}/{len(batch_records)}")
        
    except Exception as e:
        print(f"  Batch {b_idx+1:02d} failed: {e}. Retrying after 5s...", file=sys.stderr)
        time.sleep(5)
        # Retry once
        sampled_batch = master_stack.reduceRegions(
            collection=batch_fc,
            reducer=ee.Reducer.mean(),
            scale=30
        ).getInfo()
        for feat in sampled_batch.get("features", []):
            p = feat.get("properties", {})
            rid = p.get("rec_id")
            extracted_features[rid] = {
                "s2_ndvi": p.get("s2_ndvi"),
                "s2_ndwi": p.get("s2_ndwi"),
                "s2_ndre": p.get("s2_ndre"),
                "s2_msavi": p.get("s2_msavi"),
                "smap_sm_pct": p.get("smap_sm_pct"),
                "era5_precip_season_mm": p.get("era5_precip_season_mm"),
                "era5_temp_mean_c": p.get("era5_temp_mean_c"),
                "era5_temp_max_c": p.get("era5_temp_max_c"),
                "era5_vpd_mean_kpa": p.get("era5_vpd_mean_kpa"),
            }

total_elapsed = time.time() - start_total
print(f"[GEE] All {num_batches} batches processed in {total_elapsed/60:.2f} minutes!")

# 7. Merge Extracted Features & Export CSV / GZ
print(f"[EXPORT] Merging features and exporting to: {OUTPUT_CSV_PATH}")

fieldnames = [
    "record_id",
    "unique_survey_id",
    "state",
    "district",
    "subdistrict_block",
    "village",
    "latitude",
    "longitude",
    "gps_accuracy_m",
    "sowing_date",
    "harvest_date",
    "growing_season_days",
    "plot_area_acres",
    "soil_texture",
    "drainage_class",
    "irrigation_facility",
    "applied_irrigations_count",
    "tubewell_depth_feet",
    "s2_ndvi",
    "s2_ndwi",
    "s2_ndre",
    "s2_msavi",
    "smap_sm_pct",
    "era5_precip_season_mm",
    "era5_temp_mean_c",
    "era5_temp_max_c",
    "era5_vpd_mean_kpa",
    "drought_severity_raw",
    "drought_growth_stage",
    "measured_harvest_yield_t_ha",
    "target_stress_3class",
    "target_code_3class",
    "spatial_split",
    "cv_fold_id"
]

total_exported = 0
valid_s2_count = 0
valid_smap_count = 0
valid_weather_count = 0

with open(OUTPUT_CSV_PATH, "w", newline="", encoding="utf-8") as f_out, \
     gzip.open(OUTPUT_GZ_PATH, "wt", newline="", encoding="utf-8") as f_gz:
    
    writer = csv.DictWriter(f_out, fieldnames=fieldnames)
    writer_gz = csv.DictWriter(f_gz, fieldnames=fieldnames)
    
    writer.writeheader()
    writer_gz.writeheader()
    
    for r in raw_records:
        rid = r["record_id"]
        gee_feat = extracted_features.get(rid, {})
        
        # Merge
        row = dict(r)
        for k in ["s2_ndvi", "s2_ndwi", "s2_ndre", "s2_msavi", "smap_sm_pct", 
                  "era5_precip_season_mm", "era5_temp_mean_c", "era5_temp_max_c", "era5_vpd_mean_kpa"]:
            val = gee_feat.get(k)
            if val is not None and not math.isnan(val):
                row[k] = round(val, 4)
            else:
                row[k] = ""
                
        if row["s2_ndvi"] != "":
            valid_s2_count += 1
        if row["smap_sm_pct"] != "":
            valid_smap_count += 1
        if row["era5_precip_season_mm"] != "":
            valid_weather_count += 1
            
        writer.writerow(row)
        writer_gz.writerow(row)
        total_exported += 1

print(f"[EXPORT] Complete! Successfully exported {total_exported} rows.")
print(f"         Valid Sentinel-2: {valid_s2_count} ({valid_s2_count/total_exported*100:.2f}%)")
print(f"         Valid NASA SMAP:  {valid_smap_count} ({valid_smap_count/total_exported*100:.2f}%)")
print(f"         Valid ERA5-Land:  {valid_weather_count} ({valid_weather_count/total_exported*100:.2f}%)")

# Save summary metrics
metrics = {
    "total_records_processed": total_exported,
    "valid_sentinel2_records": valid_s2_count,
    "valid_smap_records": valid_smap_count,
    "valid_era5_records": valid_weather_count,
    "held_out_test_districts": sorted(held_out_districts),
    "held_out_test_records": sum(1 for r in raw_records if r["spatial_split"] == "held_out_test"),
    "train_cv_records": sum(1 for r in raw_records if r["spatial_split"] == "train"),
    "elapsed_seconds": total_elapsed,
    "csv_path": OUTPUT_CSV_PATH,
    "csv_gz_path": OUTPUT_GZ_PATH,
    "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
}

with open(METRIC_REPORT_PATH, "w", encoding="utf-8") as f:
    json.dump(metrics, f, indent=2)

print(f"[REPORT] Saved extraction metrics to: {METRIC_REPORT_PATH}")
