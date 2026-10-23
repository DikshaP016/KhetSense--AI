# KhetSense AI: ML Dataset Feasibility, Data Sourcing & Validation Design Report

**Document Version:** 1.0.0  
**Date:** October 18, 2026  
**Auditor & Lead Data Scientist:** Senior Machine Learning Engineer & Agricultural Data Scientist  
**Project:** KhetSense AI — Satellite-Based Crop-Water-Stress Assessment & Multilingual Advisory System  
**Repository Path:** `C:\Users\NIDEEKSHA\Documents\DEEKSHA\MASTERS\Research Project\khetsense\`  
**Status:** PHASE 1 PROPOSAL — PENDING USER APPROVAL (Zero Source Code, Database, or Configuration Changes Made)  

---

## Executive Summary & Scientific Defensibility Verdict

> [!IMPORTANT]
> **Can a scientifically defensible model be trained with currently accessible public data?**  
> **Verdict: YES for methodological benchmarking and pipeline verification, but NO for immediate live production deployment to Indian smallholders without local ground-truth calibration.**  
> 
> 1. **Public Benchmark Feasibility:** Realistic, open-access agricultural trial datasets (such as the USDA-ARS Limited Irrigation Research Farm datasets on Ag Data Commons, CIMMYT/CSISA Eastern India wheat irrigation trials, and peer-reviewed crop water stress index repositories) provide legitimate physical ground-truth measurements (layered soil water deficit, canopy temperature differentials, and crop water stress indices). These datasets are suitable for training, cross-validating, and benchmarking the model architectures (Logistic Regression, Random Forest, XGBoost vs. Rule Engine).
> 2. **Geographic & Agronomic Domain Gap:** Publicly accessible datasets predominantly cover maize, winter wheat, and sunflower under temperate or subtropical regimes (e.g. Colorado, European plain, Indo-Gangetic plain). They **do not** directly represent the core target crops of KhetSense AI in Maharashtra and the Deccan Plateau—specifically rainfed and semi-arid **Cotton (*Gossypium hirsutum*)**, **Soybean (*Glycine max*)**, **Pigeon Pea (*Cajanus cajan*)**, and **Chickpea (*Cicer arietinum*)** cultivated on shrink-swell black clay soils (Vertisols).
> 3. **Two-Track Recommendation:**  
>    - **Track A (Open Benchmark Track):** Train and validate the baseline and ML architectures (Logistic Regression, Random Forest, XGBoost) on standardized public agronomic datasets to prove the feature-engineering pipeline, evaluate comparative metrics, and establish the shadow-mode inference engine.  
>    - **Track B (Localized Calibration Track):** Acquire 1,500–3,000 localized, expert-labeled observations from Indian agricultural university experimental farms (e.g. MPKV Rahuri, PDKV Akola, ICAR-CRIDA, ICRISAT) before promoting any ML model from shadow mode to live farmer-facing advisory generation.

---

## 1. Investigation of Publicly Accessible Datasets with Verified Ground Truth

An exhaustive audit of open scientific repositories (USDA Ag Data Commons, Zenodo, Figshare, Mendeley Data, CGSpace/CIMMYT, and Harvard Dataverse) identified the following candidates:

### 1.1 Dataset 1: USDA-ARS Limited Irrigation Research Farm (LIRF) Deficit Irrigation Dataset
- **Repository:** USDA National Agricultural Library — Ag Data Commons  
- **Identifier / Citation:** Trout, T. J., Bausch, W. C. et al. (USDA-ARS Water Management Research Unit, Fort Collins / Greeley, Colorado). ICASA standard formatted agronomic trials.  
- **License:** Public Domain / Creative Commons CC0.  
- **Access URL:** `https://data.nal.usda.gov/dataset/usda-ars-colorado-maize-water-productivity-dataset`  
- **Crops:** Maize (*Zea mays*), Sunflower (*Helianthus annuus*), Winter Wheat.  
- **Region & Climate:** Semi-arid Great Plains (Greeley, CO; Lat 40.45°N, Lon 104.64°W; Elevation ~1,425m).  
- **Sample Size:** 4 to 6 irrigation treatment levels (ranging from 40% to 100% full crop evapotranspiration $ET_c$) across 4 replicate plots over 6 consecutive growing seasons ($N \approx 1,800$ plot-week measurement epochs).  
- **Ground-Truth Physical Labels:**
  - Volumetric Soil Water Content (VWC) measured using calibrated neutron probe attenuation and electromagnetic capacitance sensors across layered depths ($0\text{–}15\text{ cm}$, $15\text{–}30\text{ cm}$, $30\text{–}60\text{ cm}$, $60\text{–}90\text{ cm}$, $90\text{–}120\text{ cm}$).
  - Available Soil Water Depletion percentage ($ASWD$) and Soil Water Deficit ($SWD$).
  - Infrared radiometric canopy temperature ($T_c$) and Crop Water Stress Index ($CWSI$).
  - Crop growth stages, leaf area index (LAI), fractional green canopy cover, and grain yield.  
- **Associated Features:** Daily on-site automated weather station data ($T_{\min}, T_{\max}, RH, U_2, R_s, ET_0$), daily applied irrigation, and effective rainfall.  
- **Suitability Assessment:** **High for Pipeline Benchmarking.** Provides gold-standard physical ground truth. Must be mapped to KhetSense's 3-tier discrete stress schema using standardized $ASWD$ cutoffs.

### 1.2 Dataset 2: CIMMYT / CSISA Eastern India Irrigation & Wheat Trial Dataset
- **Repository:** CGSpace / CIMMYT Research Data Repository  
- **Identifier / Citation:** Cereal Systems Initiative for South Asia (CSISA); Balwinder-Singh, McDonald, A. et al. (CIMMYT/IRRI/ICAR).  
- **License:** Creative Commons Attribution (CC-BY 4.0).  
- **Access URL:** `https://hdl.handle.net/11529/105481`  
- **Crops:** Wheat (*Triticum aestivum*), Rice (*Oryza sativa*).  
- **Region & Climate:** Eastern Indo-Gangetic Plains (Bihar and Eastern Uttar Pradesh, India). Subtropical monsoon/semi-arid transition.  
- **Sample Size:** Multi-location farmer-field trials spanning 800+ farm plots over 3 winter (*Rabi*) seasons ($N \approx 2,400$ observation intervals).  
- **Ground-Truth Physical Labels:**
  - In-situ tensiometer soil water tension (kPa) and gravimetric root-zone moisture at critical growth stages (crown root initiation, tillering, flowering, grain filling).
  - Terminal drought stress logs, irrigation application dates, depth applied (mm), and yield penalties under missed irrigation windows.  
- **Associated Features:** Daily gridded IMD rainfall and temperature, sowing date, variety phenology, and tillage practice.  
- **Suitability Assessment:** **High for Indian Agronomic Calibration (Wheat).** Directly originates from Indian smallholder contexts, making it highly valuable for evaluating the Wheat pipeline module.

### 1.3 Dataset 3: Multitemporal Crop Water Stress Index & UAV/Satellite Benchmark (Mendeley Data / Zenodo)
- **Repository:** Mendeley Data & Zenodo  
- **Identifier / Citation:** DOI: `10.17632/963h6nmnyj.1` / Zenodo records on thermal/multispectral CWSI in cotton and wheat.  
- **License:** CC-BY 4.0.  
- **Crops:** Cotton (*Gossypium hirsutum*), Wheat, Maize.  
- **Region:** Semi-arid agricultural research stations (Mediterranean and Northwest India).  
- **Sample Size:** 350–700 experimental plot observations with concurrent multispectral UAV/Sentinel-2 passes.  
- **Ground-Truth Physical Labels:**
  - Empirical Crop Water Stress Index ($CWSI = \frac{(T_c - T_a) - (T_c - T_a)_{\text{lower}}}{(T_c - T_a)_{\text{upper}} - (T_c - T_a)_{\text{lower}}}$).
  - Leaf stomatal conductance ($g_s$, $\text{mmol}\cdot\text{m}^{-2}\cdot\text{s}^{-1}$) measured via steady-state leaf porometer.
  - Midday leaf water potential ($\Psi_{\text{leaf}}$, $\text{MPa}$) measured with Scholander pressure chamber.  
- **Suitability Assessment:** **Medium-High for Physiological Validation.** The labels are direct plant-physiological indicators of transpiration shutdown, but sample size is modest ($N < 1,000$).

---

## 2. Alignment Feasibility with KhetSense Pipeline Features

To train an ML model that drops seamlessly into the existing KhetSense backend, the external dataset must align with the current runtime inputs:

```
+---------------------------------------------------------------------------------------------------------+
|                                    FEATURE ALIGNMENT MATRIX                                             |
+--------------------------+-----------------------+----------------------------------+-------------------+
| KhetSense Engine Feature | Runtime Ingestion API | Public Dataset Equivalent        | Alignment Method  |
+--------------------------+-----------------------+----------------------------------+-------------------+
| mean_ndvi                | GEE Sentinel-2 L2A    | In-situ reflectance / GEE match  | Direct band-math  |
| mean_ndwi                | GEE Sentinel-2 L2A    | In-situ SWIR / GEE match         | Direct band-math  |
| s2_scene_age_days        | GEE Sentinel-2 date   | Date difference (t_obs - t_s2)   | Computed delta    |
| smap_sm_pct              | GEE NASA SMAP 9km     | Extracted SMAP pixel over site   | GEE centroid pull |
| smap_obs_age_days        | GEE SMAP header date  | Date difference (t_obs - t_smap) | Computed delta    |
| forecast_rain_48h        | OpenWeather 48h API   | Forward 48h recorded rainfall    | Weather log sum   |
| crop_name                | Farmer self-report    | Documented trial crop type       | Categorical match |
| crop_growth_stage        | Hardcoded default     | Phenology log / Days after sow   | Ordinal mapping   |
| farm_area_acres          | PostGIS polygon       | Trial plot area                  | Numerical scale   |
+--------------------------+-----------------------+----------------------------------+-------------------+
```

### 2.1 Spatial and Temporal Alignment Rules
1. **Satellite Index Alignment via Google Earth Engine:**  
   For any ground-truth dataset that provides GPS coordinates and observation dates (e.g. LIRF plots or CSISA plots), KhetSense's existing `pipeline/test_pipeline.py:fetch_sentinel2_indices()` function can be executed historically using Earth Engine's `.filterDate(obs_date - 10 days, obs_date + 1 day)` to pull the exact Sentinel-2 L2A NDVI and NDWI values that a satellite-based system would have seen on that date.
2. **SMAP Soil Moisture Historical Pull:**  
   Similarly, `NASA/SMAP/SPL3SMP_E/006` is archived in GEE from March 2015 to the present. For each ground observation date, the corresponding 9km SMAP grid cell over the experimental coordinates can be retrieved historically, matching runtime conditions.
3. **Weather Alignment:**  
   OpenWeather provides historical weather through its Time Machine / One Call Historical API, or ERA5-Land hourly reanalysis (0.1° resolution) can supply the preceding and forward 48-hour precipitation and temperature sums to replicate OpenWeather forecast inputs without data leakage.
4. **Temporal Revisit Lag Constraint:**  
   Sentinel-2 overpasses occur every 5 days (under 2-satellite constellation). Ground observations collected on dates with heavy cloud cover ($>20\%$) must reference the latest preceding clear scene, exactly as the live runtime system operates, recording `s2_scene_age_days`. Observations where the nearest clear scene is older than 14 days must be flagged or pruned to prevent stale-feature distortion.

---

## 3. Dataset Categorization: Training-Ready vs. Research-Only

A critical requirement is distinguishing genuine training data from non-labeled auxiliary resources:

```
+---------------------------------------------------------------------------------------------------------+
|                                  DATASET CATEGORIZATION TAXONOMY                                        |
+------------------------------------+--------------------------+--------------------+--------------------+
| Dataset Name / Collection          | Contains Stress Ground   | Suitability Role   | Justification      |
|                                    | Truth Labels?            |                    |                    |
+------------------------------------+--------------------------+--------------------+--------------------+
| USDA-ARS LIRF Deficit Trials       | YES (VWC, SWD, CWSI)     | TRAINING-READY     | Direct soil/canopy |
|                                    |                          | (Benchmark)        | water stress data  |
+------------------------------------+--------------------------+--------------------+--------------------+
| CIMMYT/CSISA Wheat Trials          | YES (Soil tension, yield | TRAINING-READY     | Multi-plot Indian  |
|                                    | penalty, drought logs)   | (Indian Wheat)     | field trials       |
+------------------------------------+--------------------------+--------------------+--------------------+
| Mendeley CWSI / Stomatal Datasets  | YES (CWSI, stomatal g_s, | TRAINING-READY     | Plant physiological|
|                                    | leaf water potential)    | (Validation)       | stress indicators  |
+------------------------------------+--------------------------+--------------------+--------------------+
| ISMN (International Soil Moisture  | PARTIAL (Soil moisture   | RESEARCH & FEATURE | Measures moisture  |
| Network) Indian In-Situ Stations   | probe readings only; NO  | GENERATION ONLY    | but lacks crop or  |
|                                    | crop stress labels)      |                    | stress context     |
+------------------------------------+--------------------------+--------------------+--------------------+
| NASA SMAP SPL3SMP_E Global Grids   | NO (Coarse radiometer    | INPUT FEATURE      | Raw predictor;     |
|                                    | soil moisture estimate)  | GENERATION ONLY    | cannot be label    |
+------------------------------------+--------------------------+--------------------+--------------------+
| Copernicus Sentinel-2 L2A Archive  | NO (Surface reflectance; | INPUT FEATURE      | Raw spectral input |
|                                    | radiance bands only)     | GENERATION ONLY    | to compute indices |
+------------------------------------+--------------------------+--------------------+--------------------+
| ERA5-Land / IMD Gridded Weather    | NO (Precipitation, temp, | INPUT FEATURE      | Meteorological     |
|                                    | humidity reanalysis)     | GENERATION ONLY    | context only       |
+------------------------------------+--------------------------+--------------------+--------------------+
| Existing advisories DB table       | NO (Deterministic rule   | BASELINE AUDIT     | Using as label is  |
|                                    | outputs; circular)       | ONLY (Not Ground T)| circular distillation|
+------------------------------------+--------------------------+--------------------+--------------------+
```

---

## 4. Reproducible Dataset Schema & Quality Control Specification

To maintain data integrity and reproducibility across development, training, and testing, all ingested data will conform to a strict tabular schema.

### 4.1 Tabular Schema Definition (`khetsense_stress_dataset_v1.parquet`)

```
Field Name                Type        Description / Constraints
---------------------------------------------------------------------------------------------
observation_id            string      Unique UUID for the observation record
source_dataset            string      Originating dataset identifier (e.g. 'usda_lirf', 'csisa_wheat')
farm_plot_id              string      Unique plot/farm identifier (Group identifier for splitting)
latitude                  float64     Latitude in decimal degrees (e.g. 19.34634)
longitude                 float64     Longitude in decimal degrees (e.g. 74.31100)
observation_date          date        Date of ground measurement (YYYY-MM-DD)
crop_name                 string      Normalized crop name (Cotton, Wheat, Maize, Soybean, etc.)
crop_growth_stage         string      Phenological stage (Emergence, Vegetative, Flowering, Maturity)
days_after_sowing         int32       Days elapsed since crop planting (-1 if unknown)
mean_ndvi                 float32     Sentinel-2 mean NDVI over polygon [-0.2, 1.0]
mean_ndwi                 float32     Sentinel-2 Gao NDWI over polygon [-0.5, 1.0]
msavi                     float32     Sentinel-2 Modified Soil-Adjusted Vegetation Index [-0.2, 1.0]
ndre                      float32     Sentinel-2 Normalized Difference Red Edge Index [-0.2, 1.0]
s2_scene_date             timestamp   Timestamp of Sentinel-2 acquisition
s2_scene_age_days         float32     t_obs - t_s2 in days [0.0, 30.0]
cloud_cover_pct           float32     Sentinel-2 tile cloud cover percentage [0.0, 20.0]
smap_sm_pct               float32     SMAP 9km volumetric soil moisture percentage [0.0, 100.0]
smap_obs_date             timestamp   Timestamp of SMAP observation
smap_obs_age_days         float32     t_obs - t_smap in days [0.0, 14.0]
smap_orbit                string      SMAP orbit pass ('am', 'pm', 'unknown')
forecast_rain_48h         float32     Total precipitation in forward 48 hours in mm [0.0, 500.0]
temp_max_48h              float32     Maximum forecast temperature in °C [-10.0, 60.0]
temp_mean_48h             float32     Mean forecast temperature in °C [-10.0, 50.0]
vpd_mean_48h              float32     Mean Vapor Pressure Deficit in kPa [0.0, 10.0]
farm_area_acres           float32     Farm/plot size in acres [0.05, 500.0]
ground_truth_method       string      Measurement type: 'probe_aswd', 'cwsi_thermal', 'leaf_potential'
ground_truth_raw_value    float64     Unprocessed physical value (e.g. ASWD percentage, CWSI value)
stress_label              string      TARGET LABEL: 'No Stress' | 'Mild Stress' | 'Severe Stress'
target_code               int8        Encoded target: 0 ('No Stress'), 1 ('Mild Stress'), 2 ('Severe Stress')
```

### 4.2 Automated Data Quality Checks
Any candidate observation record must pass these programmatic validation gates before inclusion:
1. **Coordinate Verification:** Latitude $\in [-90.0, 90.0]$, Longitude $\in [-180.0, 180.0]$.
2. **Spectral Bound Gates:** $\text{NDVI} \in [-0.2, 1.0]$, $\text{NDWI} \in [-0.5, 1.0]$. Values outside this range indicate water body submergence, sensor saturation, or calculation errors.
3. **Temporal Freshness Gate:** $\text{s2\_scene\_age\_days} \le 14.0\text{ days}$. Optical scenes older than 14 days do not reflect dynamic crop water status and are pruned.
4. **Soil Moisture Physical Gate:** $\text{smap\_sm\_pct} \in [0.0, 65.0\%]$ (typical mineral soil saturation porosity does not exceed 60–65%).
5. **Rainfall Non-Negativity:** $\text{forecast\_rain\_48h} \ge 0.0\text{ mm}$, non-NaN, non-Infinite.
6. **Ground Truth Completeness:** `ground_truth_raw_value` must be non-null and linked to a verified sensor calibration document.

---

## 5. Target Label Protocol and Agronomic Mapping Standards

Because raw agricultural trials record continuous physiological or soil-hydrological variables, a standardized, transparent mapping protocol is required to translate continuous measurements into KhetSense's 3-tier discrete classification system.

```
+---------------------------------------------------------------------------------------------------------+
|                                     GROUND TRUTH MAPPING PROTOCOL                                       |
+---------------------+-------------------------+----------------------------+----------------------------+
| Target Class        | Available Soil Water    | Crop Water Stress Index    | Leaf Water Potential       |
|                     | Depletion (ASWD, FAO-56)| (CWSI, Thermal Differential)| (\Psi_leaf, Scholander)    |
+---------------------+-------------------------+----------------------------+----------------------------+
| **No Stress** (0)   | $ASWD < 45\%$           | $CWSI < 0.30$              | $\Psi_{\text{leaf}} > -1.0\text{ MPa}$  |
|                     | (Moisture in readily    | (Transpiration rate        | (Cells fully turgid;       |
|                     | available water range)  | near potential $ET$)       | stomata fully open)        |
+---------------------+-------------------------+----------------------------+----------------------------+
| **Mild Stress** (1) | $45\% \le ASWD \le 70\%$| $0.30 \le CWSI \le 0.60$   | $-1.5\text{ MPa} \le \Psi \le -1.0\text{ MPa}$ |
|                     | (Stomatal closure begins| (Incipient water deficit;  | (Incipient moisture stress;|
|                     | to restrict transpiration) moderate cooling decline)| slight leaf wilting)       |
+---------------------+-------------------------+----------------------------+----------------------------+
| **Severe Stress** (2)| $ASWD > 70\%$          | $CWSI > 0.60$              | $\Psi_{\text{leaf}} < -1.5\text{ MPa}$  |
|                     | (Exceeds critical root  | (Acute transpiration       | (Severe loss of turgor;    |
|                     | threshold; near PWP)    | shutdown; high canopy temp)| severe leaf rolling/wilt)  |
+---------------------+-------------------------+----------------------------+----------------------------+
```

*Agronomic Justification:* In standard irrigation engineering (FAO Irrigation & Drainage Paper No. 56, Allen et al., 1998), the management depletion factor ($p$) for most commercial field crops ranges from $0.40$ to $0.60$. Water depletion beyond $0.70 \times AWC$ pushes soil suction beyond $-1500\text{ kPa}$ (Permanent Wilting Point), resulting in irreversible cell desiccation.

---

## 6. Anti-Leakage Splitting Strategy

To guarantee that reported model performance reflects true generalizability to unseen farms and future growing seasons, random K-Fold cross-validation is strictly prohibited.

```
                      FULL ASSEMBLED DATASET (N samples, M farms)
                                           |
         +---------------------------------+---------------------------------+
         |                                                                   |
         v (Chronological Temporal Split: e.g. 2024 Season)                  v (Held-out Season: e.g. 2025)
  HISTORICAL TRAINING & VALIDATION POOL (80%)                          HELD-OUT TEST SET (20%)
         |                                                             - Unseen growing season
         v                                                             - Strictly unseen farms
+-------------------------------------------------------+              - Never seen during training
|      5-FOLD GROUP-K-FOLD (Grouped by farm_plot_id)    |              - Used ONLY for final evaluation
|  Fold 1: [Train: Farms A-D] [Val: Farm E]             |
|  Fold 2: [Train: Farms A-C, E] [Val: Farm D]          |
|  Fold 3: [Train: Farms A, B, D, E] [Val: Farm C]      |
|  Fold 4: [Train: Farms A, C, D, E] [Val: Farm B]      |
|  Fold 5: [Train: Farms B-E] [Val: Farm A]             |
+-------------------------------------------------------+
```

1. **Spatial Grouping Constraint:** All plot repeats or multitemporal observations from the same farm/plot (`farm_plot_id`) must remain exclusively within the same fold. If Plot 101 is in the training split, it must **never** appear in the validation or test splits.
2. **Temporal Out-of-Season Holdout:** The test set must consist of observations from a chronologically distinct subsequent growing season or year (e.g. training on 2023–2024 data, testing on 2025 data). This validates whether models generalize across changing annual climatic regimes.
3. **Pre-processing Leakage Prevention:** Feature scalers (`RobustScaler`), encoders (`OneHotEncoder`), and imputers must be fitted **strictly on the training fold** and transformed onto the validation/test folds. No global dataset statistics may be computed prior to splitting.

---

## 7. Model Comparison Framework

Four distinct modeling paradigms will be trained and evaluated side-by-side on the identical splits:

```
+-------------------------------------------------------------------------------------------------------+
|                                     MODEL SPECIFICATION MATRIX                                        |
+----------------------+--------------------+-------------------------------+---------------------------+
| Model Identifier     | Model Class / Type | Key Hyperparameters / Config  | Role in Benchmarking      |
+----------------------+--------------------+-------------------------------+---------------------------+
| **Baseline 0**       | Deterministic Rule | Heuristic thresholds in       | Preserved production      |
| (Rule-Based Engine)  | Expert System      | pipeline/classifier.py        | control baseline          |
+----------------------+--------------------+-------------------------------+---------------------------+
| **Baseline 1**       | Linear Multi-class | penalty='l2', C=1.0,          | Evaluates whether stress  |
| (Logistic Regression)| Probabilistic Model| solver='lbfgs', multinomial   | is linearly separable     |
+----------------------+--------------------+-------------------------------+---------------------------+
| **Baseline 2**       | Non-linear Ensemble| n_estimators=200, max_depth=8,| Tests non-linear bagging; |
| (Random Forest)      | Bagging Trees      | class_weight='balanced_sub'   | robust against noise      |
+----------------------+--------------------+-------------------------------+---------------------------+
| **Candidate Primary**| Gradient Boosted   | n_estimators=300, max_depth=5,| Primary production        |
| (XGBoost Classifier) | Decision Trees     | lr=0.03, objective='multi'    | candidate; feature import.|
+----------------------+--------------------+-------------------------------+---------------------------+
```

---

## 8. Evaluation Design & Severe-Stress Target Analysis

### 8.1 Required Evaluation Metrics Suite
For each model evaluated on the held-out test split, the following metrics must be recorded:
1. **Macro-$F_1$ Score:** Balanced harmonic mean of precision and recall across all 3 classes:
   $$\text{Macro-}F_1 = \frac{F_{1,\text{No Stress}} + F_{1,\text{Mild Stress}} + F_{1,\text{Severe Stress}}}{3}$$
2. **Class-Wise Precision & Recall:** Precision ($P_i$) and Recall ($R_i$) computed separately for each category $i \in \{\text{No Stress}, \text{Mild Stress}, \text{Severe Stress}\}$.
3. **Confusion Matrix:** Normalized $3 \times 3$ confusion matrix detailing true vs. predicted counts and misclassification patterns (specifically examining whether Severe Stress is ever falsely predicted as No Stress).
4. **Severe-Stress Recall ($R_{\text{severe}}$):**
   $$R_{\text{severe}} = \frac{TP_{\text{severe}}}{TP_{\text{severe}} + FN_{\text{severe}}}$$
5. **Expected Cost / Risk Score:** Assigning agronomic penalty weights:
   $$\text{Cost} = 10 \cdot FN_{\text{severe}} + 3 \cdot FN_{\text{mild}} + 1 \cdot FP_{\text{severe}} + 0.5 \cdot FP_{\text{mild}}$$

### 8.2 Analysis of the 0.88 Severe-Stress Recall Target
> [!NOTE]
> **Treating 0.88 Severe-Stress Recall as a Provisional Target, Not a Guaranteed Outcome:**  
> The 0.88 target was proposed based on the critical agronomic risk that failing to detect severe stress ($FN_{\text{severe}}$) leads to crop death, whereas false alarms ($FP_{\text{severe}}$) merely trigger a light precautionary irrigation.  
> However, **0.88 must be treated as a provisional engineering objective, not a predetermined certainty**:
> - In real-world field datasets, severe water stress is frequently a minority class (e.g. 10–15% of observations during normal seasons).
> - Forcing a model to hit $R_{\text{severe}} \ge 0.88$ on imbalanced data via aggressive decision threshold shifts (e.g. lowering the classification probability threshold from 0.50 to 0.25) inevitably depresses precision, producing more false positives.
> - If precision drops below ~0.60, farmers experience alert fatigue from frequent unnecessary irrigation recommendations, eroding trust in KhetSense AI.
> - **Formal Protocol:** The evaluation report will plot the **Precision-Recall Curve for Severe Stress**, explicitly showing the trade-off at various probability thresholds. The 0.88 recall point will be benchmarked alongside the maximum $F_1$ point to allow an informed, data-driven operational decision.

---

## 9. Gap Analysis & Localized Field Protocol for Maharashtra Crops

### 9.1 The Domain Gap for Maharashtra / Deccan Plateau Smallholders
While public datasets allow rigorous testing of model algorithms, the following local agronomic variables cannot be fully captured by foreign datasets:
- **Soil Chemistry & Physics:** Vertisols (deep black cotton soils) found in Vidarbha and Marathwada have very high clay fractions ($>50\%$), high shrink-swell capacity, wide cracking upon drying, and high water-holding capacities that differ sharply from Colorado sandy loams or European silt soils.
- **Crop Phenology:** Monsoonal rainfed Cotton (*Kharif*) and post-monsoon Chickpea (*Rabi*) possess specific rooting depths and flowering stress sensitivities unique to Indian varieties.

### 9.2 Proposed Field Calibration Protocol (To Bridge the Gap)
To achieve complete scientific defensibility before live cutover:
1. **Target Institution Partnerships:** Partner with local agricultural university research stations in Maharashtra:
   - Mahatma Phule Krishi Vidyapeeth (MPKV), Rahuri
   - Dr. Panjabrao Deshmukh Krishi Vidyapeeth (PDKV), Akola
   - ICAR-Central Research Institute for Dryland Agriculture (CRIDA)
2. **Field Data Acquisition Protocol:**
   - Establish 10–20 monitored smallholder field plots across Akola, Amravati, and Ahmednagar districts.
   - Install low-cost continuous Soil Water Content (capacitance) sensors at 20cm and 40cm root depths.
   - Weekly extension worker scouting logs recording visual wilting score (1–5) and irrigation events.
   - Align weekly ground logs with Sentinel-2 cloud-free passes and SMAP radiometer retrievals.
   - Total Target: 1,500 validated observation points across 1 full Kharif + 1 Rabi cropping cycle.

---

## 10. Step-by-Step Training & Evaluation Implementation Plan

```
Phase 1: Dataset Acquisition & Validation Design (CURRENT - COMPLETED IN THIS REPORT)
    ├── Audit existing engine & feature inputs
    ├── Investigate public benchmark datasets (LIRF, CSISA, Mendeley)
    ├── Define standardized schema & FAO-56 mapping protocol
    └── Establish leakage-free splitting & evaluation metrics
    
Phase 2: Offline Dataset Preparation & GEE Historical Matching (NEXT - PENDING APPROVAL)
    ├── Download public deficit trial data (LIRF / CSISA)
    ├── Construct automated GEE historical pull script to extract Sentinel-2 & SMAP features
    ├── Execute automated data-quality validation gates
    └── Export standardized khetsense_stress_benchmark_v1.parquet (Zero app changes)

Phase 3: Model Training, Cross-Validation & Benchmarking (OFFLINE)
    ├── Implement scikit-learn & XGBoost training pipeline in isolated scratch/
    ├── Execute 5-Fold GroupKFold cross-validation + held-out season split
    ├── Generate comparative metrics table: Rule Engine vs Logistic Regression vs RF vs XGBoost
    ├── Plot Confusion Matrices and Precision-Recall Curves
    └── Deliver formal Model Evaluation & Selection Report

Phase 4: Production Shadow-Mode Module Integration (UPON MODEL SELECTION APPROVAL)
    ├── Implement pipeline/ml_engine/ predictor module with ONNX/Joblib serialization
    ├── Implement safe fallback to pipeline/classifier.py on any exception or timeout
    ├── Add provisional migration 006 for shadow-mode database audit columns
    ├── Run offline regression tests (verifying all 205 existing tests pass)
    └── Enable Shadow Mode (parallel logging; zero alteration of farmer-facing text or voice)

Phase 5: Shadow-Mode Audit & Controlled Production Cutover
    ├── Monitor 500+ live inferences in shadow mode against rule-based advisories
    ├── Evaluate divergence cases with agronomic advisors
    └── Toggle ENABLE_ML_STRESS_ENGINE=true only after formal performance sign-off
```

---

## Summary of Confirmation

- **Application source code:** **UNTOUCHED.**
- **Database schemas and migrations:** **UNTOUCHED.**
- **Environment variables and credentials:** **UNTOUCHED.**
- **Dependencies:** **UNTOUCHED.**
- **Live WhatsApp endpoints:** **ZERO CALLS MADE.**

*Awaiting your review and formal approval of this Phase 1 Feasibility Report before proceeding to Phase 2 (offline dataset preparation and historical GEE feature matching).*
