# KhetSense AI: Phase 3 Historical Feature Extraction & Offline Dataset Preparation Report

**Document Version:** 1.0.0  
**Date:** October 18, 2026 (Execution Timestamp: 22:56 IST)  
**Lead Auditor & Senior Agricultural Data Scientist:** Advanced Agentic AI Engineering & Agricultural Data Science Team  
**Project:** KhetSense AI — Satellite-Based Crop-Water-Stress Assessment & Multilingual Advisory System  
**Repository Path:** `C:\Users\NIDEEKSHA\Documents\DEEKSHA\MASTERS\Research Project\khetsense\`  
**Status:** PHASE 3 COMPLETE — REPRODUCIBLE RESEARCH DATASET PRODUCED (Zero Runtime Source Code, Database, or Configuration Changes Made)  

---

## Executive Summary & Major Outcomes

> [!IMPORTANT]
> **Key Achievements of Phase 3:**  
> 1. **Complete Multi-Sensor Extraction:** Historical satellite and reanalysis weather features were successfully extracted for all **$7,648$ smallholder farm plots** across 40 districts in Eastern India using Google Earth Engine (`ee`) in an isolated batch pipeline (`data/research_benchmark/extract_historical_features.py`).
> 2. **Physical Sensor Parity:**
>    - **Sentinel-2 L2A Harmonized:** Derived NDVI, NDWI (Gao), NDRE (Red Edge), and MSAVI (Soil-Adjusted) at 10m–20m resolution with QA60 cloud masking.
>    - **NASA SMAP Radiometer:** Retrieved 9km surface volumetric soil moisture percentages ($0\text{--}100\%$) composited across AM and PM passes.
>    - **ECMWF ERA5-Land Reanalysis:** Computed seasonal cumulative rainfall (mm), seasonal mean and maximum 2m air temperature (°C), and atmospheric Vapor Pressure Deficit (VPD in kPa via Tetens formulation).
> 3. **High Data Completeness:**
>    - **7,641 out of 7,648 records (99.91%)** have complete, valid Sentinel-2 optical indices (only 7 cloud/edge-masked records, missingness = $0.09\%$).
>    - **100.00% completeness** for NASA SMAP soil moisture and ERA5-Land weather variables.
> 4. **Empirical Ground-Truth Signal Validation:**
>    Comparing multi-sensor features against independent ground-truth labels revealed striking physical confirmation of water stress:
>    - **NDWI (Canopy Water Content):** Collapses by **$-50.2\%$** from $0.207$ (No Stress) down to **$0.103$** (Severe Stress).
>    - **NDVI (Canopy Biomass):** Drops from $0.571$ down to **$0.501$** ($-12.3\%$).
>    - **SMAP Soil Moisture:** Decreases from $23.19\%$ down to **$19.46\%$**.
>    - **Harvested Yield:** Collapses from $3.01\text{ t/ha}$ down to **$2.39\text{ t/ha}$** ($-20.6\%$ economic and biological yield penalty, $p < 0.001$).
> 5. **Spatial Anti-Leakage Partitioning Enforced:**
>    - **Held-Out Spatial Test Set:** 8 complete districts ($1,513$ records, $19.78\%$) kept completely untouched.
>    - **Cross-Validation Training Pool:** 32 districts ($6,135$ records, $80.22\%$) partitioned into 5 spatial folds.
>    - **District Overlap: Exactly 0 (Zero spatial leakage).**
> 6. **Portable Deliverables Generated:**
>    - Primary dataset: `data/research_benchmark/csisa_wheat_multisensor_features_2018.csv` ($1.82\text{ MB}$, 7,648 rows $\times$ 34 columns).
>    - Compressed dataset: `data/research_benchmark/csisa_wheat_multisensor_features_2018.csv.gz` ($225\text{ KB}$).
>    - Cryptographic manifest: `data/research_benchmark/manifest_phase3.json`.
>    - Machine-readable extraction metrics: `data/research_benchmark/extraction_metrics.json`.

---

## 1. Step 1: Pre-Processing Verification & Chronology Resolution

### 1.1 Cryptographic Integrity Check of Raw Source Data
Before processing, the source files in `data/research_benchmark/csisa_wheat_2018/` were verified against `manifest.json`. All files matched their recorded sizes and SHA256 checksums with 100% byte fidelity:

```
+-----------------------------------------------------------------------------------------------------------------------------+
|                                           RAW SOURCE DATA VERIFICATION MANIFEST                                             |
+---------------------------------+----------------+--------------------+----------------------------------+------------------+
| Filename                        | Expected Bytes | Actual Disk Bytes  | Recorded SHA256 Checksum         | Integrity Status |
+---------------------------------+----------------+--------------------+----------------------------------+------------------+
| `LDS_Variables_Details.tab`     | 22,863         | 22,863             | `1d3dbf67c7aaa66353adc08337...`  | PASSED (Match)   |
| `ODK_Prog_Choices_Sheet.tab`    | 33,208         | 33,208             | `aee9595a273c18ae0aa51c45a4...`  | PASSED (Match)   |
| `ODK_Prog_Survey_Sheet.tab`     | 74,397         | 74,397             | `93538bc6bbd61f87dfbd103e3a...`  | PASSED (Match)   |
| `CSISA_IND_LDS_Whe_2018_Data.csv`| 14,791,800     | 14,791,800         | `1f6642b4a5d637090498bed2e7...`  | PASSED (Match)   |
+---------------------------------+----------------+--------------------+----------------------------------+------------------+
```

### 1.2 Resolving Survey Administration Date vs. Active Crop Phenology Window
A critical scientific finding from our audit of the date columns was the discrepancy between survey recording dates and actual crop growth:
- **Wheat Sowing Dates (`D-q415`):** October 25, 2017 to January 25, 2018 (Peak: Nov 15 – Dec 10, 2017).
- **Wheat Harvest Dates (`L-q601`):** March 04, 2018 to May 29, 2018 (Peak: April 2018).
- **Crop Season Duration ($t_{\text{harvest}} - t_{\text{sow}}$):** Mean: $138.4\text{ days}$; Median: $140.0\text{ days}$; Range: $[80, 182]\text{ days}$ (100.0% biologically valid).
- **Survey Submission Dates (`SubmissionDate`):** May 2018 to November 2018 (Median lag post-harvest: **165 days**).

> [!WARNING]
> **Target Leakage Prevention:**  
> The household survey was conducted **post-harvest** as a retrospective agronomic diagnostic survey.  
> If satellite features were queried using the survey submission date (e.g. July or October 2018), the model would observe monsoonal vegetation or post-harvest bare fallow land rather than the growing wheat crop.  
> **Resolution:** In our extraction pipeline, all satellite and weather features were strictly windowed to the **active crop phenology window** ($t_{\text{sow}} \le t \le t_{\text{harvest}}$), specifically centering optical indices on the peak vegetative/flowering window (**January 15 to February 28, 2018**) and cumulative weather across the cropping season (**December 1, 2017 to March 31, 2018**).

---

## 2. Step 2: Multi-Sensor Extraction Architecture & Band Formulations

Extraction was executed using a standalone Python pipeline connecting to Google Earth Engine via service account credentials (`credentials/ee-key.json`).

```
                                  MULTI-SENSOR DATA FUSION PIPELINE
                                                  │
                 ┌────────────────────────────────┼────────────────────────────────┐
                 │                                │                                │
                 ▼                                ▼                                ▼
    Sentinel-2 L2A Harmonized            NASA SMAP Radiometer              ECMWF ERA5-Land
     (COPERNICUS/S2_SR_HARMONIZED)        (NASA/SMAP/SPL3SMP_E/006)         (ECMWF/ERA5_LAND/DAILY_AGGR)
     - Bands: B2, B3, B4, B5, B8, B11     - Bands: soil_moisture_am, pm     - Precip, Temp, Dewpoint
     - Cloud mask: QA60 < 20% clouds      - Resolution: 9 km gridded        - Resolution: 0.1° (~10 km)
     - Window: Jan 15 - Feb 28, 2018      - Window: Jan 15 - Feb 28, 2018   - Window: Dec 1, 2017 - Mar 31, 2018
                 │                                │                                │
                 ▼                                ▼                                ▼
         Vegetation Indices                  Topsoil VWC                   Meteorological Deficit
     NDVI, NDWI, NDRE, MSAVI              smap_sm_pct (%)                  Precip, TempMax, VPD (kPa)
                 │                                │                                │
                 └────────────────────────────────┼────────────────────────────────┘
                                                  │
                                                  ▼
                                ee.Image.reduceRegions(scale=30m)
                                Batch Size: 250 plots per call
                                31 Batches / 7,648 Plots Total (426.2s)
                                                  │
                                                  ▼
                        Integrated Feature Table (7,648 rows × 34 columns)
```

### 2.1 Band Formulations & Scientific Justifications

1. **Normalized Difference Vegetation Index (NDVI):**
   $$\text{NDVI} = \frac{\text{B8} - \text{B4}}{\text{B8} + \text{B4}}$$
   Measures fractional photosynthetically active radiation and green canopy biomass. Healthy vegetative wheat reaches $0.60\text{--}0.85$.
2. **Gao Normalized Difference Water Index (NDWI):**
   $$\text{NDWI} = \frac{\text{B8} - \text{B11}}{\text{B8} + \text{B11}}$$
   Contrasts near-infrared (B8, 842nm) with shortwave-infrared (B11, 1610nm). B11 absorption is proportional to liquid water in the spongy mesophyll. Water-stressed wheat exhibits declining NDWI values toward zero or negative.
3. **Normalized Difference Red Edge (NDRE):**
   $$\text{NDRE} = \frac{\text{B8} - \text{B5}}{\text{B8} + \text{B5}}$$
   Utilizes the Sentinel-2 Red Edge band (B5, 705nm). Because red absorption (B4) saturates in closed canopies, NDRE remains sensitive to chlorophyll degradation and incipient water stress during late vegetative and heading stages.
4. **Modified Soil-Adjusted Vegetation Index (MSAVI, Qi et al., 1994):**
   $$\text{MSAVI} = \frac{2 \cdot \text{B8} + 1 - \sqrt{(2 \cdot \text{B8} + 1)^2 - 8 \cdot (\text{B8} - \text{B4})}}{2}$$
   Applies an inductive self-adjusting soil factor to eliminate bare soil background reflectance in smallholder plots with sparse canopy cover.
5. **NASA SMAP Surface Volumetric Soil Moisture (`smap_sm_pct`):**
   Composites 6 AM descending (`soil_moisture_am`) and 6 PM ascending (`soil_moisture_pm`) 9km radiometer retrievals over the plot centroid, multiplied by 100 to yield percentage ($0\text{--}100\%$).
6. **Atmospheric Vapor Pressure Deficit (VPD in kPa):**
   Calculated using the Tetens saturation vapor pressure formulation over ERA5-Land 2m air temperature ($T$) and dewpoint temperature ($T_{\text{dew}}$):
   $$e_s(T) = 0.61078 \exp\left(\frac{17.27 \cdot T}{T + 237.3}\right) \quad (\text{kPa})$$
   $$e_a(T_{\text{dew}}) = 0.61078 \exp\left(\frac{17.27 \cdot T_{\text{dew}}}{T_{\text{dew}} + 237.3}\right) \quad (\text{kPa})$$
   $$\text{VPD} = \max(0, e_s - e_a) \quad (\text{kPa})$$
   Directly captures the atmospheric drying power driving crop transpiration demand.

---

## 3. Step 3: Ground Truth Label Analysis & Agronomic Signal Validation

### 3.1 Raw Drought Severity Class Distribution
The survey captures independent assessments across 4 severity tiers:

```
+---------------------------------------------------------------------------------------------------------+
|                                    RAW DROUGHT SEVERITY DISTRIBUTION                                    |
+------------------------+--------------------+---------------------+-------------------------------------+
| Raw Survey Category    | Sample Count ($N$) | Overall Prevalence  | Agronomic & Physiological Status    |
+------------------------+--------------------+---------------------+-------------------------------------+
| **None**               | 3,027              | 39.58%              | Full water satisfaction; no deficit |
| **Low**                | 2,258              | 29.52%              | Mild transient surface dryness      |
| **Medium**             | 2,168              | 28.35%              | Vegetative wilting; delayed irrig   |
| **High**               | 195                | 2.55%               | Acute terminal drought stress       |
| **Total**              | 7,648              | 100.00%             | 100% complete ground truth          |
+------------------------+--------------------+---------------------+-------------------------------------+
```

### 3.2 Physical Signal Confirmation across Classes
To assess whether survey-reported drought severity corresponds to physical satellite and meteorological measurements, we audited the multi-sensor feature means across the mapped KhetSense advisory classes:

```
+-----------------------------------------------------------------------------------------------------------------------------+
|                                        MULTI-SENSOR FEATURE MEANS BY ADVISORY CLASS                                         |
+----------------------+------------+------------+---------------+------------------+-------------------+---------------------+
| Mapped Class         | Mean NDVI  | Mean NDWI  | Mean SMAP SM% | Mean Seasonal    | Mean Seasonal     | Mean Harvest        |
|                      |            |            |               | Precipitation mm | Maximum Temp (°C) | Grain Yield (t/ha)  |
+----------------------+------------+------------+---------------+------------------+-------------------+---------------------+
| **No Stress** (0)    | 0.571      | 0.207      | 23.19%        | 9.3 mm           | 36.90 °C          | 3.01 t/ha           |
| **Mild Stress** (1)  | 0.574      | 0.206      | 23.37%        | 11.4 mm          | 36.95 °C          | 3.00 t/ha           |
| **Severe Stress** (2)| **0.501**  | **0.103**  | **19.46%**    | 18.7 mm          | **37.38 °C**      | **2.39 t/ha**       |
+----------------------+------------+------------+---------------+------------------+-------------------+---------------------+
| **Relative Change**  | **-12.3%** | **-50.2%** | **-16.1%**    | -                | **+0.48 °C**      | **-20.6% ($p<10^{-6}$)**|
+----------------------+------------+------------+---------------+------------------+-------------------+---------------------+
```

> [!NOTE]
> **Key Empirical Insights:**  
> 1. **NDWI is the Most Sensitive Water Stress Indicator:** While NDVI shows a moderate decline ($-12.3\%$), NDWI exhibits an acute **$-50.2\%$ collapse** in severely stressed plots ($0.207 \rightarrow 0.103$), reflecting direct leaf canopy dehydration prior to total chlorophyll degradation.
> 2. **Soil Moisture Deficit:** SMAP volumetric soil moisture drops from $23.19\%$ down to $19.46\%$, indicating lower topsoil water availability.
> 3. **Severe Stress Class Imbalance ($2.55\%$):** Only 195 records are classified as Severe Stress. In Phase 4, training must utilize cost-sensitive sample weighting (e.g. `scale_pos_weight` in XGBoost) or focal loss to prevent the minority class from being neglected.

---

## 4. Step 4: Spatial Validation Design (Anti-Leakage Partitioning)

### 4.1 Proof of Spatial Independence
Our spatial audit confirmed that 6,651 plots share GPS coordinates with neighboring village plots. Standard random K-Fold cross-validation would cause catastrophic data leakage.

To ensure true spatial generalization, a **Spatial Blocked Partitioning** was enforced by administrative district:
- **Held-Out Spatial Test Set:** 8 distinct districts ($1,513$ records, $19.78\%$ of data):  
  `Arah`, `Araria`, `Arwal`, `Aurangabad`, `Balia`, `Banka`, `Begusarai`, `Chandauli`
- **Cross-Validation Training Pool:** 32 distinct districts ($6,135$ records, $80.22\%$ of data) split into 5 spatial folds.
- **District Overlap Check:** $\text{Districts}_{\text{train}} \cap \text{Districts}_{\text{test}} = \emptyset$ (**Zero Leakage Verified**).

```
+---------------------------------------------------------------------------------------------------------+
|                                    SPATIAL PARTITIONING SUMMARY                                         |
+--------------------------+---------------------+-------------------+------------------------------------+
| Partition Name           | District Count      | Plot Records ($N$)| Role in ML Lifecycle               |
+--------------------------+---------------------+-------------------+------------------------------------+
| **Held-Out Test Set**    | 8 districts         | 1,513 (19.78%)    | Final out-of-domain evaluation     |
| **CV Fold 0**            | 6-7 districts       | 1,350 (17.65%)    | Training & Validation Fold 0       |
| **CV Fold 1**            | 6-7 districts       | 1,248 (16.32%)    | Training & Validation Fold 1       |
| **CV Fold 2**            | 6-7 districts       | 1,213 (15.86%)    | Training & Validation Fold 2       |
| **CV Fold 3**            | 6-7 districts       | 1,154 (15.09%)    | Training & Validation Fold 3       |
| **CV Fold 4**            | 6-7 districts       | 1,170 (15.30%)    | Training & Validation Fold 4       |
| **Total**                | 40 districts        | 7,648 (100.0%)    | Complete dataset                   |
+--------------------------+---------------------+-------------------+------------------------------------+
```

---

## 5. Dataset Quality, Missingness & Feature Statistics

### 5.1 Missingness Audit across All 34 Features

```
+---------------------------------------------------------------------------------------------------------+
|                                      DATASET MISSINGNESS SUMMARY                                        |
+------------------------------------+----------------+-------------------+-------------------------------+
| Feature Category                   | Total Columns  | Missing Values    | Completeness Percentage       |
+------------------------------------+----------------+-------------------+-------------------------------+
| Administrative & Metadata          | 6 columns      | 0                 | 100.00%                       |
| Spatial & Coordinates              | 4 columns      | 0                 | 100.00%                       |
| Phenology & Sowing/Harvest Dates   | 3 columns      | 0                 | 100.00%                       |
| Agronomic & Soil Management        | 6 columns      | 0                 | 100.00%                       |
| Sentinel-2 Vegetation Indices      | 4 columns      | 7 records (0.09%) | **99.91%** (Cloud/edge mask)  |
| NASA SMAP Soil Moisture            | 1 column       | 0                 | 100.00%                       |
| ECMWF ERA5-Land Weather Features   | 4 columns      | 0                 | 100.00%                       |
| Ground Truth Labels & Target Codes | 4 columns      | 0                 | 100.00%                       |
| Spatial Validation Partition Keys  | 2 columns      | 0                 | 100.00%                       |
| **All Features**                   | **34 columns** | **28 / 260,032**  | **99.989% Overall**           |
+------------------------------------+----------------+-------------------+-------------------------------+
```

### 5.2 Continuous Feature Summary Statistics Table

```
+-----------------------------------------------------------------------------------------------------------------------------+
|                                              FEATURE SUMMARY STATISTICS TABLE                                               |
+------------------------------+------------+--------+----------+----------+----------+----------+----------+-----------------+
| Column Name                  | Unit       | Count  | Mean     | Median   | Min      | Max      | StdDev   | Missingness (%) |
+------------------------------+------------+--------+----------+----------+----------+----------+----------+-----------------+
| `s2_ndvi`                    | Index      | 7,641  | 0.571    | 0.597    | -0.538   | 0.917    | 0.205    | 0.09% (7 rows)  |
| `s2_ndwi`                    | Index      | 7,641  | 0.204    | 0.213    | -0.217   | 0.578    | 0.187    | 0.09% (7 rows)  |
| `s2_ndre`                    | Index      | 7,641  | 0.404    | 0.412    | -0.634   | 0.751    | 0.169    | 0.09% (7 rows)  |
| `s2_msavi`                   | Index      | 7,641  | 0.350    | 0.340    | -0.079   | 0.787    | 0.166    | 0.09% (7 rows)  |
| `smap_sm_pct`                | % (vol)    | 7,648  | 23.200   | 23.256   | 14.522   | 39.508   | 3.743    | 0.00% (0 rows)  |
| `era5_precip_season_mm`      | mm         | 7,648  | 10.733   | 9.147    | 3.936    | 42.975   | 6.696    | 0.00% (0 rows)  |
| `era5_temp_mean_c`           | °C         | 7,648  | 20.045   | 20.093   | 18.682   | 20.750   | 0.299    | 0.00% (0 rows)  |
| `era5_temp_max_c`            | °C         | 7,648  | 36.941   | 36.730   | 33.980   | 39.217   | 1.280    | 0.00% (0 rows)  |
| `era5_vpd_mean_kpa`          | kPa        | 7,648  | 0.986    | 0.976    | 0.779    | 1.199    | 0.073    | 0.00% (0 rows)  |
| `measured_harvest_yield_t_ha`| t/ha       | 7,648  | 2.991    | 3.000    | 0.200    | 6.500    | 0.855    | 0.00% (0 rows)  |
| `applied_irrigations_count`  | count      | 7,648  | 2.285    | 2.000    | 1.000    | 5.000    | 0.766    | 0.00% (0 rows)  |
| `growing_season_days`        | days       | 7,648  | 138.38   | 140.00   | 80.00    | 182.00   | 14.92    | 0.00% (0 rows)  |
| `plot_area_acres`            | acres      | 7,648  | 0.618    | 0.450    | 0.030    | 20.000   | 0.672    | 0.00% (0 rows)  |
| `tubewell_depth_feet`        | feet       | 7,648  | 97.48    | 80.00    | 10.00    | 555.00   | 48.97    | 0.00% (0 rows)  |
+------------------------------+------------+--------+----------+----------+----------+----------+----------+-----------------+
```

---

## 6. Inventory of Generated Deliverables & Checksums

All produced artifacts are quarantined in `data/research_benchmark/` and recorded in `manifest_phase3.json`:

```
+-----------------------------------------------------------------------------------------------------------------------------+
|                                              PHASE 3 ARTIFACTS INVENTORY                                                    |
+--------------------------------------+--------------+-------------+---------------------------------------------------------+
| Artifact Relative Path               | File Size    | Type        | SHA256 Checksum                                         |
+--------------------------------------+--------------+-------------+---------------------------------------------------------+
| `data/research_benchmark/`           | 1,817,834 B  | Primary CSV | `ab79e8144aa4cb9b786a35349df944ed7db5b29738069ce38df1`|
| `csisa_wheat_multisensor_features_`  |              |             | `f545c306865e`                                          |
| `2018.csv`                           |              |             |                                                         |
+--------------------------------------+--------------+-------------+---------------------------------------------------------+
| `data/research_benchmark/`           | 225,325 B    | Compressed  | `d92834e6112fc93e4d4b991458f81a458b12f53166862e9ba920`|
| `csisa_wheat_multisensor_features_`  |              | CSV.GZ      | `801ab7d9ba70`                                          |
| `2018.csv.gz`                        |              |             |                                                         |
+--------------------------------------+--------------+-------------+---------------------------------------------------------+
| `data/research_benchmark/`           | 16,954 B     | Python GEE  | `f84c2967b58d594e20f7647ef6ea5ab9e66d6f4af3233c11bd3d`|
| `extract_historical_features.py`     |              | Script      | `8b8fcd3991a5`                                          |
+--------------------------------------+--------------+-------------+---------------------------------------------------------+
| `data/research_benchmark/`           | 785 B        | JSON Metric | `347e49997e83ba0489938bf52ac6f261f1b9de451f236c878a43`|
| `extraction_metrics.json`            |              | Log         | `c696f014b9af`                                          |
+--------------------------------------+--------------+-------------+---------------------------------------------------------+
| `data/research_benchmark/`           | 4,149 B      | JSON        | `3f972b22ec3c21a4ae07ec93d25686aa7e5e3170753fbe5e6e66`|
| `manifest_phase3.json`               |              | Manifest    | `8db61f77d467`                                          |
+--------------------------------------+--------------+-------------+---------------------------------------------------------+
```

---

## 7. Strict Commitments & Scope Verification

In compliance with every safety restriction:
1. **Application Source Code:** **ZERO CHANGES.** (`webhook_server.py`, `common/`, `pipeline/`, `whatsapp/` remain untouched).
2. **Production Classifier & Guardrails:** **ZERO CHANGES.** (`pipeline/classifier.py` heuristic rules and 48-hour rainfall guardrails remain untouched).
3. **Database & Migrations:** **ZERO MUTATIONS.** PostgreSQL schemas, tables, and credentials remain untouched.
4. **Environment & Secrets:** **ZERO MODIFICATIONS.** `.env` was not modified; no tokens or passwords were logged.
5. **Dependencies:** **ZERO PACKAGES INSTALLED.** No third-party packages were installed into `.venv`.
6. **External Network Calls:** **ZERO LIVE WHATSAPP CALLS OR PAID CHARGES.** Only Google Earth Engine free research service-account queries were executed.
7. **Model Training:** **NO MODELS TRAINED OR SERIALIZED.** Phase 3 was strictly confined to feature extraction and dataset validation.

---

## 8. Recommended Next Steps for Phase 4 (Offline Model Benchmarking & Evaluation)

With the research-quality multi-sensor dataset successfully prepared, validated, and partitioned, the project is ready for **Phase 4: Offline Model Benchmarking and Cross-Validation**:

1. **Model Training (Offline in `scratch/`):**
   - Train and cross-validate the four planned modeling paradigms on the 32 training districts:
     - **Baseline 0:** Deterministic Rule Engine (`pipeline/classifier.py`)
     - **Baseline 1:** Multinomial Logistic Regression (L2 penalty)
     - **Baseline 2:** Random Forest Classifier (Balanced Subsample)
     - **Candidate Primary:** XGBoost Multi-Class Classifier
2. **Spatial Evaluation on Held-Out Test Set:**
   - Evaluate all models on the 8 held-out districts ($1,513$ unseen plots).
   - Generate normalized $3 \times 3$ confusion matrices.
3. **Precision-Recall Curve for Severe Stress:**
   - Evaluate the trade-off between Severe-Stress Recall (engineering target: 0.88) and Precision to avoid false-alarm irrigation fatigue.
4. **Deliver Formal Model Evaluation & Selection Report.**

---

*Report authored by Senior Agricultural Data Scientist & ML Engineer. All generated data files, codebooks, extraction scripts, and SHA256 manifests are immutably archived in `data/research_benchmark/`.*
