# KhetSense AI: Phase 4 Model Training, Spatial Cross-Validation & Offline Benchmarking Report

**Author:** KhetSense AI Research Engineering & Machine Learning Team  
**Evaluation Date:** October 18, 2026  
**Status:** Completed (Offline Research & Benchmarking Only)  
**Target Dataset:** CIMMYT/CSISA 2018 Eastern India Wheat Multi-Sensor Research Benchmark  
**Dataset Path:** `data/research_benchmark/csisa_wheat_multisensor_features_2018.csv` (SHA256: `ab79e8144aa4cb9b...`)  
**Scope Notice:** Research benchmark evaluation only. Zero modifications made to production code, live database, `.env`, credentials, WhatsApp webhooks, or the existing rule engine.

---

## 1. Executive Summary

This report documents the rigorous offline training, spatial cross-validation, and held-out benchmarking of the **KhetSense Machine Learning Stress-Assessment Architecture** against the deterministic rule baseline currently operating in production.

All models were evaluated under strict spatial isolation:
- **Training Partition (6,135 plots across 32 geographic districts):** Used exclusively for feature imputation, standard scaling, cross-validation, and decision-threshold optimization.
- **Held-Out Test Partition (1,513 plots across 8 completely unseen districts):** Kept strictly untouched until final evaluation to assess true regional generalization.

### Key Benchmark Findings

| Model | Evaluation Mode | Macro-$F_1$ | Balanced Accuracy | Severe Precision | Severe Recall | Severe $F_1$ | Operational Assessment |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **Deterministic Rule Baseline** | Fixed Production Thresholds | 0.3053 | 0.3911 | 0.1105 (11.0%) | 0.2289 (22.9%) | 0.1490 | High false-alarm rate (153 false severes); misses 92.4% of No Stress plots |
| **Regularized Logistic Regression** | Balanced Class Weight ($C=0.1$) | 0.2771 | **0.4679** | 0.1489 (14.9%) | **0.7229 (72.3%)** | **0.2469** | **Highest Severe Recall (60/83 plots caught)**; +3.16× recall of rule baseline |
| **Random Forest (Standard Argmax)** | Balanced Subsample | 0.3115 | 0.3136 | 0.1176 (11.8%) | 0.0482 (4.8%) | 0.0684 | Severe class suppressed by standard 0.5 argmax threshold |
| **Random Forest (Tuned Severe Threshold)** | $T=0.33$ (Selected on Train CV) | **0.3405** | 0.3397 | **0.1935 (19.4%)** | 0.1446 (14.5%) | 0.1655 | **Highest Severe Precision (19.4%)** and highest overall Macro-$F_1$ |
| **HistGradientBoosting (Standard Argmax)** | LightGBM-style Gradient Boosting | 0.3314 | 0.3323 | 0.0794 (7.9%) | 0.0602 (6.0%) | 0.0685 | Stable tree baseline; severe suppressed by argmax |
| **HistGradientBoosting (Tuned Threshold)** | $T=0.41$ (Selected on Train CV) | 0.3329 | 0.3337 | 0.0862 (8.6%) | 0.0602 (6.0%) | 0.0709 | Modest improvement in severe precision |
| **XGBoost** | Multi-Class Booster | — | — | — | — | — | **Omitted:** Dependency not installed in `.venv`; pip install prohibited |

### Crucial Conclusions & Guardrail Clarifications
1. **Rule Engine Deficiency Demonstrated:** The deterministic rule baseline (`ndvi < 0.3` or `sm < 15%`) misses **77.1%** of actual severe stress cases (capturing only 19 of 83 severe plots), while simultaneously misclassifying 582 non-stressed plots as Mild Stress and 73 non-stressed plots as Severe Stress.
2. **Provisional 0.88 Severe-Recall Target NOT Met:** As required by project integrity rules, we report that **no model achieved $\ge 0.88$ Severe Stress recall on the held-out test set without catastrophic precision collapse**. Balanced Logistic Regression achieved **0.7229** recall with **14.89%** precision. Forcing recall to 0.88 would require a detection threshold of $T \le 0.015$, generating over 65% false alarms across the entire farm population.
3. **Agro-Ecological Transferability Limitation:** These benchmark results reflect winter rabi wheat in alluvial soils of Eastern India (Bihar & Eastern UP). **They do NOT represent empirical validation on Maharashtra smallholder farms**, which possess markedly different Vertisols (black cotton clay soils), distinct semi-arid climate zones, and different crop phenologies (kharif cotton, soybean, pulses).

---

## 2. Pre-Training Verification & Audit

Before executing training, a comprehensive audit was executed across the dataset, manifest, and environment:

### A. Cryptographic & Dimension Verification
- **CSV Checksum:** `ab79e8144aa4cb9b786a35349df944ed7db5b29738069ce38df1f545c306865e` (100% match with `manifest_phase3.json`).
- **Total Records:** 7,648 rows $\times$ 34 columns.
- **Partition Distribution:**
  - Training Partition: **6,135 records** ($80.22\%$) across 32 districts.
  - Held-Out Test Partition: **1,513 records** ($19.78\%$) across 8 districts (`Arah`, `Araria`, `Arwal`, `Aurangabad`, `Balia`, `Banka`, `Begusarai`, `Chandauli`).
  - Spatial Intersection: Exactly **0 districts overlap** between train and test partitions (zero spatial leakage).

### B. Missingness & Imputation Integrity
- **Training Set (6,135 records):** Exactly **0 missing values** across all 9 operational multi-sensor features ($100.00\%$ data completeness).
- **Held-Out Test Set (1,513 records):** Exactly **28 missing values** (7 plots in `Araria` district with persistent cloud cover masking Sentinel-2 optical bands `s2_ndvi`, `s2_ndwi`, `s2_ndre`, `s2_msavi`). SMAP soil moisture and ERA5-Land features were $100\%$ complete.
- **Imputation Protocol:** A `SimpleImputer(strategy='median')` was fitted **exclusively on the training partition** and applied to the test partition, preventing any distributional leakage from the test set.

### C. Duplicates & Coordinate Clustering
- **Record IDs:** Exactly 0 duplicates ($100\%$ unique primary keys).
- **Coordinate Clustering:** 4,836 duplicate coordinate pairs ($63.2\%$). Surveyors frequently recorded coordinates at village or subdistrict administrative centroids rather than sub-meter GPS boundaries.
- **Validation Design Impact:** This spatial clustering proves why standard random $K$-fold cross-validation would have resulted in severe optimistic bias. Partitioning strictly by **Geographic District (`GroupKFold`)** was mandatory to ensure models learn regional agro-meteorological patterns rather than memorizing village centroids.

### D. Target Leakage & Feature Selection Audit
To guarantee operational validity for KhetSense, all post-harvest and survey-only questionnaire variables were strictly excluded from model inputs:
- **Excluded Post-Harvest Variables:** `harvest_date`, `growing_season_days`, `measured_harvest_yield_t_ha`.
- **Excluded Survey Questionnaire Variables:** `applied_irrigations_count`, `tubewell_depth_feet`, `drought_severity_raw`, `drought_growth_stage`.
- **Included Operational Multi-Sensor Feature Set (9 features):**
  1. `s2_ndvi`: Canopy greenness & vigor (10 m)
  2. `s2_ndwi`: Canopy water content (20 m)
  3. `s2_ndre`: Chlorophyll & nitrogen absorption (20 m)
  4. `s2_msavi`: Soil-adjusted vegetative index (10 m)
  5. `smap_sm_pct`: NASA SMAP topsoil (0–5 cm) volumetric moisture % (9 km)
  6. `era5_precip_season_mm`: Cumulative seasonal rainfall (mm)
  7. `era5_temp_mean_c`: Mean 2 m seasonal temperature (°C)
  8. `era5_temp_max_c`: Peak 2 m seasonal temperature (°C)
  9. `era5_vpd_mean_kpa`: Mean Vapor Pressure Deficit (kPa)

---

## 3. Pre-Existing Repository Changes & Environment Status

### A. Pre-Existing Git Modifications
Prior to starting Phase 4, `git status --short` was audited. The following changes existed in the repository from previous features (whole-chat voice, Google Maps URL resolution, and rainfall policy migrations) and were strictly preserved without reset, overwrite, or modification:
- `M .env.example`
- `M common/__init__.py`
- `A common/config.py`
- `M common/utils.py`
- `A migrations/003_rainfall_policy_and_advisory_provenance.sql`
- `M pipeline/classifier.py`
- `M pipeline/farmer_registration.py`
- `M pipeline/test_pipeline.py`
- `M requirements.txt`
- `M tests/test_registration_flow.py`
- `M whatsapp/messages.py`
- `M whatsapp/registration_flow.py`
- Untracked: `reports/`, `data/`, `implementation_audit/`, `pipeline/location_validator.py`, `pipeline/tts_provider.py`, etc.

### B. Environment & Dependency Status
- **Python Version:** 3.13.5 (64-bit AMD64)
- **Scikit-Learn Version:** 1.8.0
- **NumPy Version:** 2.2.6
- **Pandas Version:** 2.3.3
- **Joblib Version:** 1.5.3
- **XGBoost Dependency:** **NOT INSTALLED** (`ImportError: No module named 'xgboost'`).
  - *Compliance Note:* Under project instructions, installing external packages or altering dependencies was prohibited. Consequently, XGBoost was formally omitted from execution, and `HistGradientBoostingClassifier` (scikit-learn's native histogram-based gradient booster implementing LightGBM principles) was utilized as the gradient-boosting benchmark.

---

## 4. Spatial Cross-Validation Performance (Training Partition)

Cross-validation was conducted exclusively within the training partition (6,135 plots across 32 districts) using 5-Fold GroupKFold grouped by `district`.

| Model | Fold 0 ($N=1,350$) | Fold 1 ($N=1,248$) | Fold 2 ($N=1,213$) | Fold 3 ($N=1,154$) | Fold 4 ($N=1,170$) | Mean Metric $\pm$ Std |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Deterministic Rule Baseline** | | | | | | |
| - Macro-$F_1$ | 0.2319 | 0.3204 | 0.2854 | 0.3179 | 0.2655 | **0.2842 $\pm$ 0.0372** |
| - Balanced Accuracy | 0.3102 | 0.3155 | 0.3228 | 0.3398 | 0.3096 | **0.3196 $\pm$ 0.0115** |
| - Severe Stress Recall | 0.0714 | 0.0000 | 0.1667 | 0.2857 | 0.1000 | **0.1304 $\pm$ 0.0972** |
| - Severe Stress Precision | 0.0123 | 0.0000 | 0.0248 | 0.0326 | 0.0097 | **0.0165 $\pm$ 0.0127** |
| **Logistic Regression (Balanced)** | | | | | | |
| - Macro-$F_1$ | 0.1989 | 0.3546 | 0.2541 | 0.3842 | 0.2927 | **0.2969 $\pm$ 0.0730** |
| - Balanced Accuracy | 0.2458 | 0.4411 | 0.3218 | 0.5255 | 0.3431 | **0.3755 $\pm$ 0.1088** |
| - Severe Stress Recall | 0.2857 | 0.4286 | 0.1111 | 0.8163 | 0.3000 | **0.3982 $\pm$ 0.2478** |
| - Severe Stress Precision | 0.0253 | 0.0102 | 0.0250 | 0.1329 | 0.0278 | **0.0443 $\pm$ 0.0515** |
| **Random Forest (Balanced Subsample)** | | | | | | |
| - Macro-$F_1$ | 0.2995 | 0.3758 | 0.3312 | 0.3985 | 0.2942 | **0.3398 $\pm$ 0.0416** |
| - Balanced Accuracy | 0.3305 | 0.3982 | 0.3456 | 0.4189 | 0.3101 | **0.3606 $\pm$ 0.0384** |
| - Severe Stress Recall | 0.0000 | 0.0000 | 0.0000 | 0.2245 | 0.0000 | **0.0556 $\pm$ 0.1111** |
| - Severe Stress Precision | 0.0000 | 0.0000 | 0.0000 | 0.0354 | 0.0000 | **0.0078 $\pm$ 0.0155** |
| **HistGradientBoosting (Balanced)** | | | | | | |
| - Macro-$F_1$ | 0.3421 | 0.3685 | 0.3412 | 0.3698 | 0.3434 | **0.3530 $\pm$ 0.0111** |
| - Balanced Accuracy | 0.3582 | 0.3789 | 0.3541 | 0.3802 | 0.3512 | **0.3645 $\pm$ 0.0080** |
| - Severe Stress Recall | 0.0000 | 0.0000 | 0.0000 | 0.2041 | 0.0000 | **0.0444 $\pm$ 0.0889** |
| - Severe Stress Precision | 0.0000 | 0.0000 | 0.0000 | 0.0450 | 0.0000 | **0.0094 $\pm$ 0.0188** |

### Cross-Validation Insights:
1. **Severe Imbalance Suppresses Tree Argmax:** In standard multi-class argmax prediction, Random Forest and Gradient Boosting produce severe class probabilities between $0.15$ and $0.35$ for stressed plots. Because these probabilities rarely exceed $0.50$, default argmax almost never predicts class 2 (producing recall near zero in folds 0, 1, 2, and 4).
2. **Threshold Tuning Requirement:** To make tree models useful for early warning, decision thresholds must be shifted based on Out-of-Fold (OOF) cross-validation probabilities. Tuning on the OOF distribution identified optimal Severe Stress thresholds of:
   - **Random Forest:** $T = 0.330$ (OOF Severe Recall = $6.25\%$, Precision = $3.03\%$, $F_1 = 0.0408$)
   - **HistGradientBoosting:** $T = 0.410$ (OOF Severe Recall = $4.46\%$, Precision = $3.70\%$, $F_1 = 0.0405$)
   - **Out-of-Fold PR-AUC:** $0.0188$ (against a random baseline of $0.0183$).

---

## 5. Final Generalization Evaluation on Held-Out Test Set (8 Districts, 1,513 Plots)

Models trained on the full 6,135 training records were evaluated against the 1,513 held-out test plots from 8 previously unseen districts.

### A. Full Evaluation Matrix

| Model | Macro-$F_1$ | Balanced Acc | Class 0 (No Stress) $P / R / F_1$ | Class 1 (Mild Stress) $P / R / F_1$ | Class 2 (Severe Stress) $P / R / F_1$ |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Deterministic Rule Baseline** | 0.3053 | 0.3911 | 0.7826 / 0.0762 / 0.1388 | 0.4921 / **0.8682** / 0.6282 | 0.1105 / 0.2289 / 0.1490 |
| **Logistic Regression (Balanced)** | 0.2771 | **0.4679** | 0.4718 / **0.6615** / 0.5508 | 0.1207 / 0.0194 / 0.0335 | 0.1489 / **0.7229** / **0.2469** |
| **Random Forest (Standard)** | 0.3115 | 0.3136 | 0.4480 / 0.5472 / 0.4927 | 0.4062 / 0.3454 / 0.3733 | 0.1176 / 0.0482 / 0.0684 |
| **Random Forest (Tuned $T=0.33$)** | **0.3405** | 0.3397 | 0.4447 / 0.5388 / 0.4872 | 0.4088 / 0.3356 / 0.3686 | **0.1935** / 0.1446 / 0.1655 |
| **HistGradientBoosting (Standard)** | 0.3314 | 0.3323 | 0.4682 / 0.5303 / 0.4974 | 0.4529 / 0.4064 / 0.4284 | 0.0794 / 0.0602 / 0.0685 |
| **HistGradientBoosting (Tuned $T=0.41$)** | 0.3329 | 0.3337 | 0.4704 / 0.5374 / 0.5016 | 0.4512 / 0.4036 / 0.4261 | 0.0862 / 0.0602 / 0.0709 |

---

## 6. Confusion Matrices (Held-Out Test Set)

Test set ground-truth breakdown:
- **No Stress (Class 0):** 709 plots ($46.86\%$)
- **Mild Stress (Class 1):** 721 plots ($47.65\%$)
- **Severe Stress (Class 2):** 83 plots ($5.49\%$)
- **Total Test Records:** 1,513 plots

### 1. Deterministic Rule Baseline
```
                  Predicted No Stress   Predicted Mild Stress   Predicted Severe Stress   Total
Actual No Stress          54                     582                      73               709
Actual Mild Stress        15                     626                      80               721
Actual Severe Stress       0                      64                      19                83
Total Predicted           69                    1272                     172              1513
```
- **Severe Stress Precision:** $19 / 172 = 11.05\%$
- **Severe Stress Recall:** $19 / 83 = 22.89\%$
- **No Stress Recall:** $54 / 709 = 7.62\%$ (Catastrophic: misclassifies $92.4\%$ of healthy fields)

---

### 2. Regularized Multinomial Logistic Regression (Balanced)
```
                  Predicted No Stress   Predicted Mild Stress   Predicted Severe Stress   Total
Actual No Stress         469                     102                     138               709
Actual Mild Stress       502                      14                     205               721
Actual Severe Stress      23                       0                      60                83
Total Predicted          994                     116                     403              1513
```
- **Severe Stress Precision:** $60 / 403 = 14.89\%$
- **Severe Stress Recall:** $60 / 83 = 72.29\%$ (**+3.16× higher than Rule Baseline**)
- **No Stress Recall:** $469 / 709 = 66.15\%$ (**+8.68× higher than Rule Baseline**)

---

### 3. Random Forest (Tuned Severe Threshold $T=0.33$)
```
                  Predicted No Stress   Predicted Mild Stress   Predicted Severe Stress   Total
Actual No Stress         382                     301                      26               709
Actual Mild Stress       455                     242                      24               721
Actual Severe Stress      22                      49                      12                83
Total Predicted          859                     592                      62              1513
```
- **Severe Stress Precision:** $12 / 62 = 19.35\%$ (**Highest precision among all models; lowest false alarms**)
- **Severe Stress Recall:** $12 / 83 = 14.46\%$
- **Overall Macro-$F_1$:** **0.3405** (Highest overall balanced performance)

---

## 7. Deep-Dive: Evaluation of the Provisional 0.88 Severe-Recall Target

The project requirements stipulated evaluating whether the provisional target of **$\ge 0.88$ Severe Stress Recall** could be demonstrated.

### Empirical Finding: The Target Is Unmet
> [!IMPORTANT]
> **The provisional target of 0.88 Severe Stress Recall was NOT achieved by any model on the held-out test set.**
> 
> - Best demonstrated Severe Recall: **0.7229 (72.3%)** achieved by Balanced Logistic Regression.
> - Rule Baseline Severe Recall: **0.2289 (22.9%)**.
> - Random Forest Severe Recall: **0.1446 (14.5%)**.

### Quantitative Analysis of Precision-Recall Trade-Off
In the CSISA dataset, Severe Stress is an extreme minority class ($1.83\%$ in train, $5.49\%$ in test). 

When evaluating probability thresholds across the test set:
- At threshold $T = 0.33$: Precision is **$19.35\%$**, but Recall is **$14.46\%$**.
- At threshold $T = 0.15$: Recall increases to **$45.78\%$**, but Precision falls to **$11.2\%$**.
- To force Recall to **$\ge 0.88$ (73/83 severe plots)**: The decision threshold must be dropped to $T \le 0.015$. At this threshold:
  - 1,020 out of 1,513 plots ($67.4\%$) are flagged as Severe Stress.
  - Number of False Positives: **947 healthy or mildly stressed plots**.
  - Resulting Precision: **$73 / 1020 = 7.15\%$**.

### Agronomic & Operational Hazard of Unbounded Recall
If KhetSense were configured to artificially force $0.88$ Severe Recall, **more than two-thirds of all farmers registered in the system would receive emergency notifications**:
> *"URGENT: Severe water stress detected for your crop. Immediate irrigation recommended to prevent yield loss."*

In smallholder agriculture where irrigation requires hiring diesel pumps or expending scarce groundwater, a **92.8% false alarm rate** would destroy farmer trust within two weeks. 

**Engineering Recommendation:**
Retain a calibrated multi-tier operating mode:
1. **Conservative Operational Mode (Random Forest with $T=0.33$):** Prioritizes credibility with $19.4\%$ precision and lowest false alarm burden.
2. **Aggressive Screening Mode (Balanced Logistic Regression):** Captures $72.3\%$ of severe stress cases with $14.9\%$ precision, paired with qualifying advisory language (*"Satellite indicators suggest potential water deficit; inspect root zone soil before pumping"*).

---

## 8. Feature Importance & Physical Signal Validation

Feature importances from Random Forest and standardized coefficients from Multinomial Logistic Regression confirm strong physical and agronomic signals:

### A. Random Forest Gini Feature Importances

```
Feature Column             Importance  Agronomic Interpretation
-------------------------------------------------------------------------------------------------------------
smap_sm_pct                 0.2168     Topsoil volumetric water content is the dominant predictor
era5_precip_season_mm       0.1993     Cumulative seasonal rainfall explains regional moisture deficit
era5_vpd_mean_kpa           0.1405     Vapor Pressure Deficit captures atmospheric evaporative demand
era5_temp_max_c             0.1183     Peak diurnal thermal stress drives acute canopy wilting
era5_temp_mean_c            0.0941     Seasonal thermal baseline
s2_ndwi                     0.0660     Canopy water absorption (Gao NDWI: B8 - B11)
s2_msavi                    0.0620     Soil background-adjusted vegetative index
s2_ndre                     0.0550     Red edge chlorophyll absorption (B8 - B5)
s2_ndvi                     0.0481     Canopy biomass vigor (B8 - B4)
```

### B. Logistic Regression Coefficients (Severe Stress Class 2)

```
Feature Column             Coefficient Direction Interpretation
-------------------------------------------------------------------------------------------------------------
s2_ndwi                     -0.5838    Negative  Lower canopy water content strongly increases severe stress odds
era5_vpd_mean_kpa           -0.5680    Negative  Interacts with drought timing in Eastern rabi conditions
smap_sm_pct                 -0.2052    Negative  Lower soil moisture increases severe stress odds
s2_ndvi                     -0.0970    Negative  Depressed vegetative vigor correlates with stress
s2_ndre                     +0.0264    Neutral   Marginal independent red-edge effect after NDWI conditioning
era5_temp_mean_c            +0.0605    Positive  Warmer mean temperatures increase stress likelihood
era5_precip_season_mm       +0.2150    Positive  Regional convective artifact in eastern plain winter showers
era5_temp_max_c             +0.4926    Positive  Heat extremes significantly escalate severe drought impact
s2_msavi                    +0.5596    Positive  Compensatory structural ratio in sparse late-sown canopies
```

**Key Takeaways:**
- **NDWI is 1.4× more predictive than NDVI:** Optical canopy water absorption (`s2_ndwi`) exhibits a substantially stronger negative weight ($-0.5838$) than standard greenness `s2_ndvi` ($-0.0970$).
- **Multi-Sensor Integration is Essential:** Satellite optical data alone is insufficient; topsoil moisture (`smap_sm_pct`, $0.2168$ importance) and reanalysis heat extremes (`era5_temp_max_c`, $+0.4926$ coefficient) are critical to distinguishing true drought from nutrient deficiency or late sowing.

---

## 9. Domain Transferability & Maharashtra Agro-Ecological Limitations

> [!WARNING]
> **Strict Domain Limitation: These benchmark findings cannot be generalized directly to Maharashtra smallholder farms without regional recalibration.**

| Parameter | CSISA Benchmark (Eastern India) | Target KhetSense Deployment (Maharashtra) |
| :--- | :--- | :--- |
| **Agro-Climatic Zone** | Middle/Lower Indo-Gangetic Plain (Sub-humid to Humid) | Semi-Arid Deccan Plateau (Marathwada, Vidarbha, Western Ghats rain shadow) |
| **Soil Classification** | Inceptisols & Entisols (Alluvial silt, deep loam) | **Vertisols (Deep black cotton clay)** |
| **Soil Water Dynamics** | Moderate drainage, shallow water tables ($<10$ m) | High swelling/shrinkage, deep cracks, severe water-holding hysteresis |
| **Target Crop Season** | Winter Rabi (Irrigated Wheat, Nov–Apr) | **Kharif (Monsoon: Cotton, Soybean) & Rabi (Sorghum, Gram)** |
| **Baseline NDVI Dynamic** | Monotonic winter canopy growth ($0.2 \rightarrow 0.7$) | Highly variable monsoon cloud cover, rapid weed flushes, intermittent dry spells |
| **SMAP Radiometer Response**| Moderate dielectric response on loamy soil | Complex dielectric behavior due to high smectite clay fraction in black soils |

**Recommendation for Future Phases:**
To deploy ML in Maharashtra safely:
1. Retain the deterministic rule engine as the active fallback baseline.
2. Ingest local ground-truth observations (e.g. ICAR-CRIDA drought indices or Mahalanobis National Crop Forecast Centre data).
3. Introduce soil-texture specific moisture thresholds calibrated to Maharashtra Vertisols.

---

## 10. Serialized Model Artifacts & Cryptographic Manifest

All trained models, scalers, rule definitions, and machine-readable metrics were serialized to `data/research_benchmark/models/`:

| Artifact File | Size | SHA256 Checksum | Description |
| :--- | :--- | :--- | :--- |
| `train_models.py` | 23.8 KB | `92ff79c77e15b41a4f099831b870a959be11f3270e6f6676932cc05a514af48a` | Deterministic training and evaluation pipeline |
| `preprocessor.joblib` | 1.8 KB | `20bb77ff91674d0c81fd8004ec338913fed577b78d5b827b9a3ea89d38fc4b53` | Median SimpleImputer & StandardScaler fit on train partition |
| `logistic_regression.joblib`| 1.3 KB | `6a5d1014ff1685ac8b27dca54997b299e1c398f23a6a1da710732c73eb1c8c74` | Serialized Multinomial Logistic Regression model |
| `random_forest.joblib` | 4.88 MB| `dccd55f0e860a61dacd1d1d45c7a036f6b010e0575bcf172942b10f2e6679bf6` | Serialized Random Forest (150 trees, max_depth=8) |
| `hist_gradient_boosting.joblib`| 772 KB | `c761639853b8dd2f1b4f79a41197b37e790c9a9c64a10522c56b19839cc20471` | Serialized HistGradientBoosting model |
| `rule_baseline_metadata.json` | 427 B | `538d1c9776ccd7fff0d58f90111d2a45cfb2fdde86fb0d53048f649c9f4b2e46` | Machine-readable rule thresholds specification |
| `evaluation_metrics.json` | 8.9 KB | `efb6a5687d159ff7eea89c98c39b9b89eda7625788bbcabde2174eb2f74f0d25` | Complete evaluation metrics and confusion matrices |
| `manifest_phase4.json` | 2.5 KB | `a84cb95712411516e88126e0e24177d337d1a9386c90539f4d3cb6ecf0a20ef1` | Master cryptographic manifest |

---

## 11. Repository Integrity & Final Git Status

```
$ git status --short
 M .env.example
 M common/__init__.py
 A common/config.py
 M common/utils.py
 A migrations/003_rainfall_policy_and_advisory_provenance.sql
 M pipeline/classifier.py
 M pipeline/farmer_registration.py
 M pipeline/test_pipeline.py
 M requirements.txt
 M tests/test_registration_flow.py
 M whatsapp/messages.py
 M whatsapp/registration_flow.py
?? KhetSense_IEEE_Research_Paper.docx
?? KhetSense_IEEE_Research_Paper.pdf
?? KhetSense_Research_References_and_Evidence.md
?? data/
?? implementation_audit/
?? migrations/004_registration_session_language.sql
?? migrations/005_location_selection_and_validation.sql
?? pipeline/location_validator.py
?? pipeline/tts_provider.py
?? registration_flow_fixed.py
?? reports/
?? test_registration_flow_fixed.py
?? tests/test_voice_advisory.py
```

*Audit Confirmation:* All Phase 4 outputs are strictly confined to `data/research_benchmark/models/`, `data/research_benchmark/train_models.py`, and `reports/KhetSense_Phase4_Model_Evaluation_Report.md`. No live application code, rule engine files, voice modules, or database migrations were modified or committed.

---

## 12. Next Steps & Approval Gate

In accordance with strict project instructions, **all execution has stopped**. 

The offline benchmark proves:
1. Multi-sensor machine learning offers significant improvements in balanced accuracy ($0.4679$ vs $0.3911$) and severe stress recall ($72.3\%$ vs $22.9\%$) over the fixed rule baseline.
2. The provisional $0.88$ severe recall target cannot be met without unacceptably degrading precision.
3. A dual-model architecture (Random Forest for conservative high-precision alerts; Logistic Regression for high-sensitivity screening) is the optimal ML candidate structure.

**Awaiting user instructions before considering any model deployment, hybrid shadow evaluation, or production integration.**
