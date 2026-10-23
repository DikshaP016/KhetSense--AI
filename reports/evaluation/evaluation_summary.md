# KhetSense AI — Verified Model Evaluation Summary

**Document Type:** Empirical Model Evaluation & Comparative Performance Audit  
**Date:** October 21, 2026  
**Auditor:** Senior AI/ML Research Engineer & Testing Lead  
**Evaluation Scope:** Strict Spatial Holdout Benchmark (8 Unseen Districts, 1,513 Held-Out Records)  
**Associated Artifacts:**
- [`model_comparison.csv`](file:///c:/Users/NIDEEKSHA/Documents/DEEKSHA/MASTERS/Research%20Project/khetsense/reports/evaluation/model_comparison.csv)
- [`confusion_matrices.json`](file:///c:/Users/NIDEEKSHA/Documents/DEEKSHA/MASTERS/Research%20Project/khetsense/reports/evaluation/confusion_matrices.json)
- [`evaluation_charts.png`](file:///c:/Users/NIDEEKSHA/Documents/DEEKSHA/MASTERS/Research%20Project/khetsense/reports/evaluation/evaluation_charts.png)
- [`evaluation_manifest.json`](file:///c:/Users/NIDEEKSHA/Documents/DEEKSHA/MASTERS/Research%20Project/khetsense/reports/evaluation/evaluation_manifest.json)

---

## 1. Executive Summary & Core Scientific Findings

This evaluation report provides an independently verified, publication-grade assessment of the multi-sensor stress classification models in KhetSense AI. Models were trained on the **Cereal Systems Initiative for South Asia (CSISA) Eastern India Wheat Research Benchmark** (7,648 records) across 32 training districts and evaluated on a strict spatial holdout of **8 unseen test districts** (1,513 records).

### Key Empirical Findings:

1. **Deterministic Rule Baseline Outperforms 5-Feature ML**:
   On the unseen held-out districts, the **Deterministic Agronomic Rule Baseline** achieves:
   - **Severe Stress Recall:** **22.89%** ($19 / 83$) vs **12.05%** ($10 / 83$) for the tuned 5-feature Random Forest.
   - **Severe Stress Precision:** **11.05%** ($19 / 172$) vs **6.37%** ($10 / 157$) for the tuned 5-feature Random Forest.
   - **Severe Stress False Alarms:** **153** vs **1,274** for tuned HistGradientBoosting.
   - **Balanced Accuracy:** **0.3911** vs **0.3069** for tuned Random Forest.
   - **Inference Latency:** **1.57 microseconds** ($0.0016$ ms) vs **25.52 milliseconds** for Random Forest (16,000x faster).

2. **Why HistGradientBoosting's 72.29% Recall is Deceptive**:
   When tuning the decision threshold on HistGradientBoosting Out-Of-Fold probabilities, the optimizer selected an extreme threshold of $T = 0.02$. While this captures $60 / 83$ severe stress instances ($72.29\%$ recall), it classifies **1,334 out of 1,513 test samples as Severe Stress**. This generates **1,274 false alarms**, depressing precision to **4.50%** (below the random baseline prevalence of $5.49\%$) and collapsing Macro-F1 to **0.0865**. In practical farming, a system that generates 1,274 false emergency irrigation alerts destroys farmer trust and leads to massive water and electricity waste.

3. **Impact of Removing ERA5 Reanalysis Climate Features**:
   In the 9-feature model, reanalysis features (`era5_precip_season_mm`, `era5_vpd_mean_kpa`, `era5_temp_*`) represented **55.22%** of tree splits and achieved 19.35% Severe Precision ($T=0.33$). Restricting inputs strictly to live-native satellite observations (`s2_ndvi`, `s2_ndwi`, `s2_ndre`, `s2_msavi`, `smap_sm_pct`) dropped Severe Precision to 6.37%. This confirms that the retrospective survey labels correlate strongly with seasonal macro-climate anomalies rather than single-date satellite snapshots.

4. **Architectural & Operational Decision**:
   The **Deterministic Rule-Based Expert Decision Engine MUST remain the sole active decision authority** for farmer advisories. The candidate 5-feature ML model serves strictly in an isolated shadow evaluation capacity.

---

## 2. Comprehensive Model Performance Comparison Table

All metrics below are computed on the strict held-out spatial test set (8 districts, $N = 1,513$ records, 83 Severe Stress cases).

| Model Architecture | Feature Set | Decision Threshold | Macro-F1 | Balanced Acc | Severe Precision | Severe Recall | Severe F1 | Severe False Alarms | Severe PR-AUC | Latency (ms) |
|---|---|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Deterministic Rule Baseline** | 5-Feat Live Native | Physical Rules (NDVI<0.30, SM<15%) | **0.3053** | **0.3911** | **11.05%** | **22.89%** | **0.1490** | **153** | N/A | **0.0016** |
| **Random Forest 5-Feat (Argmax)** | 5-Feat Live Native | Argmax ($P \\ge 0.50$) | 0.3062 | 0.3075 | 8.33% | 4.82% | 0.0611 | 44 | 0.0659 | 25.52 |
| **Random Forest 5-Feat (Tuned)** | 5-Feat Live Native | Tuned Severe $T = 0.27$ | 0.2999 | 0.3069 | 6.37% | 12.05% | 0.0833 | 147 | 0.0659 | 25.52 |
| **HistGradientBoosting 5-Feat (Argmax)** | 5-Feat Live Native | Argmax ($P \\ge 0.50$) | 0.2970 | 0.2992 | 3.19% | 3.61% | 0.0339 | 91 | 0.0488 | 4.51 |
| **HistGradientBoosting 5-Feat (Tuned)** | 5-Feat Live Native | Tuned Severe $T = 0.02$ | 0.0865 | 0.2748 | 4.50% | 72.29% | 0.0847 | 1,274 | 0.0488 | 4.51 |
| **Logistic Regression 9-Feat (Balanced)** | 9-Feat Full (with ERA5) | Balanced Class Weights | 0.2771 | 0.4679 | 14.89% | 72.29% | 0.2469 | 343 | Not rep. | 0.50 |
| **Random Forest 9-Feat (Argmax)** | 9-Feat Full (with ERA5) | Argmax ($P \\ge 0.50$) | 0.3115 | 0.3136 | 11.76% | 4.82% | 0.0684 | 30 | Not rep. | 24.57 |
| **Random Forest 9-Feat (Tuned)** | 9-Feat Full (with ERA5) | Tuned Severe $T = 0.33$ | **0.3405** | **0.3397** | **19.35%** | **14.46%** | **0.1655** | 50 | 0.0188 | 24.57 |
| **HistGradientBoosting 9-Feat (Argmax)** | 9-Feat Full (with ERA5) | Argmax ($P \\ge 0.50$) | 0.3314 | 0.3323 | 7.94% | 6.02% | 0.0685 | 58 | Not rep. | 2.07 |
| **HistGradientBoosting 9-Feat (Tuned)** | 9-Feat Full (with ERA5) | Tuned Severe $T = 0.41$ | 0.3329 | 0.3337 | 8.62% | 6.02% | 0.0709 | 53 | Not rep. | 2.07 |

---

## 3. Confusion Matrix Breakdown (Class Ordering: No Stress, Mild Stress, Severe Stress)

### 3.1 Deterministic Rule Baseline
```
Actual \\ Pred    No Stress (0)    Mild Stress (1)    Severe Stress (2)    Total
No Stress (0)          54               582                 73              709
Mild Stress (1)        15               626                 80              721
Severe Stress (2)       0                64                 19               83
Total Predicted        69             1,272                172            1,513
```
- **True Positives (Severe):** 19
- **False Positives (Severe):** $73 + 80 = 153$
- **False Negatives (Severe):** $0 + 64 = 64$
- **Severe Stress Recall:** $19 / 83 = 22.89\\%$
- **Severe Stress Precision:** $19 / 172 = 11.05\\%$

### 3.2 Random Forest 5-Feature (Tuned $T=0.27$)
```
Actual \\ Pred    No Stress (0)    Mild Stress (1)    Severe Stress (2)    Total
No Stress (0)         236               414                 59              709
Mild Stress (1)       296               337                 88              721
Severe Stress (2)      23                50                 10               83
Total Predicted       555               801                157            1,513
```
- **True Positives (Severe):** 10
- **False Positives (Severe):** $59 + 88 = 147$
- **False Negatives (Severe):** $23 + 50 = 73$
- **Severe Stress Recall:** $10 / 83 = 12.05\\%$
- **Severe Stress Precision:** $10 / 157 = 6.37\\%$

### 3.3 HistGradientBoosting 5-Feature (Tuned $T=0.02$) — Pathological False Alarm Case
```
Actual \\ Pred    No Stress (0)    Mild Stress (1)    Severe Stress (2)    Total
No Stress (0)          14                63                632              709
Mild Stress (1)        20                59                642              721
Severe Stress (2)       9                14                 60               83
Total Predicted        43               136              1,334            1,513
```
- **True Positives (Severe):** 60
- **False Positives (Severe):** $632 + 642 = 1,274$
- **False Negatives (Severe):** $9 + 14 = 23$
- **Severe Stress Recall:** $60 / 83 = 72.29\\%$
- **Severe Stress Precision:** $60 / 1,334 = 4.50\\%$
- **Analysis:** Predicts Severe Stress for 88.2% of all farms in the test set.

---

## 4. Feature Importance Analysis (5-Feature Live Model)

Relative Gini importance from 150 decision trees in `random_forest_5feat.joblib`:

1. **`smap_sm_pct` (NASA SMAP 9-km Microwave Soil Moisture):** **45.37%**
2. **`s2_ndwi` (Sentinel-2 Water Index B8/B11):** **15.67%**
3. **`s2_ndre` (Sentinel-2 Red-Edge Chlorophyll B8/B5):** **13.50%**
4. **`s2_msavi` (Sentinel-2 Modified Soil-Adjusted VI):** **12.99%**
5. **`s2_ndvi` (Sentinel-2 Normalized Difference VI B8/B4):** **12.48%**

**Synthesis:**
- Optical canopy reflectance indices collectively represent **54.64%** of tree split weight.
- Microwave soil moisture represents **45.37%** as the single most influential continuous predictor.
- All 5 features are genuinely extracted live in KhetSense AI's operational pipeline.

---

## 5. Scientific Limitations & Dataset Grounding

1. **Geographic Scoping**: The dataset originates exclusively from Eastern India (Bihar, Eastern Uttar Pradesh, Odisha). Soil types (Alluvial Indo-Gangetic Plains) and agro-climatic conditions differ substantially from Central Maharashtra (Vertisol / Black Cotton Soil). The model is **not validated for Maharashtra** or for non-wheat crops (Cotton, Soybean, Sugarcane).
2. **Label Subjectivity**: Labels derive from post-harvest farmer recall (ODK survey question `I-q5502_droughtSeverity`) collected up to 165 days after harvest. Human memory heuristics introduce subjective noise compared to instrumented lysimeter ground truth.
3. **Cross-Model Comparability**: The 9-feature models and 5-feature models were evaluated on the same 1,513 held-out records across the same 8 districts. However, the 9-feature model included retrospective reanalysis features that are scientifically unavailable during live inference. Therefore, the 9-feature model's higher precision (19.35%) cannot be achieved in real-time operational deployment without reanalysis lag.
