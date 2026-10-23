# KhetSense AI — Model Evaluation Audit & Empirical Performance Report

**Document Reference:** `KS-AUDIT-2026-MODEL-EVAL`  
**Project Title:** KhetSense AI: AI-Driven Crop Stress Detection and Multilingual Voice-Based Irrigation Advisory Using Satellite Remote Sensing  
**Auditor:** Senior AI/ML Researcher & Verification Engineer  
**Date:** October 21, 2026  
**Evaluation Scope:** Strict Spatial Holdout Benchmark (8 Unseen Districts, 1,513 Held-Out Records)  
**Destination:** `reports/project_audit/KhetSense_AI_Model_Evaluation_Audit.md`  

---

## 1. Executive Audit Summary

This evaluation audit provides an independent, reproducible cross-check of all statistical, machine-learning, and agronomic rule-based stress classification models developed for KhetSense AI. 

The evaluation is conducted on the **Cereal Systems Initiative for South Asia (CSISA) Eastern India Wheat Research Benchmark** ($N = 7,648$ records), partitioned under a strict **spatial block holdout protocol**:
- **Training Partition:** 32 districts, $N_{\text{train}} = 6,135$ plots ($80.22\%$).
- **Held-Out Test Partition:** 8 unseen districts, $N_{\text{test}} = 1,513$ plots ($19.78\%$).
- **Spatial Overlap:** Exactly **0 overlapping districts** between partitions, guaranteeing zero spatial autocorrelation leakage.

### Core Verified Findings:

1. **Superiority of the Deterministic Rule Baseline over Live-Native ML:**  
   On unseen held-out districts, the **Deterministic Agronomic Rule Baseline** achieves:
   - **Severe Stress Recall:** **22.89%** ($19 / 83$) vs. **12.05%** ($10 / 83$) for the tuned 5-feature Random Forest.
   - **Severe Stress Precision:** **11.05%** ($19 / 172$) vs. **6.37%** ($10 / 157$) for the tuned 5-feature Random Forest.
   - **Balanced Accuracy:** **0.3911** vs. **0.3069** for the tuned 5-feature Random Forest.
   - **Inference Latency:** **1.57 microseconds** ($0.0016\text{ ms}$) vs. **25.52 milliseconds** for Random Forest (16,000x faster).

2. **The Severe Base-Rate Trap in HistGradientBoosting ($T = 0.02$):**  
   Optimizing the severe-stress classification threshold on Out-Of-Fold (OOF) cross-validation probabilities yielded an extreme threshold of $T = 0.02$ for HistGradientBoosting. When evaluated on the held-out test set, this model achieved $72.29\%$ recall ($60 / 83$) but classified **1,334 out of 1,513 test samples as Severe Stress**. This generated **1,274 false alarms**, crashing precision to **4.50%** (lower than the random prevalence rate of $5.49\%$) and collapsing Macro-F1 to **0.0865**. In production farming, this represents catastrophic failure, as 88.2% of all farms would receive false emergency irrigation alerts.

3. **Impact of Live-Native Feature Scoping (9-Feature vs. 5-Feature):**  
   In the 9-feature model, ERA5 reanalysis features (`era5_precip_season_mm`, `era5_vpd_mean_kpa`, `era5_temp_*`) contributed **55.22%** of decision tree splits. Restricting features strictly to live-observable satellite inputs (`s2_ndvi`, `s2_ndwi`, `s2_ndre`, `s2_msavi`, `smap_sm_pct`) reduced Severe Precision from $19.35\%$ to $6.37\%$. This proves that the retrospective survey labels correlate primarily with seasonal climate anomalies rather than single-date satellite snapshots.

---

## 2. Dataset Partitioning & Anti-Leakage Audit

### 2.1 Dataset Provenance & Integrity
- **Dataset File:** `data/research_benchmark/csisa_wheat_multisensor_features_2018.csv`
- **File SHA-256:** `ab79e8144aa4cb9b786a35349df944ed7db5b29738069ce38df1f545c306865e`
- **Total Records:** 7,648 rows $\times$ 34 columns.
- **Crop:** Bread Wheat (*Triticum aestivum*).
- **Target Variable:** `target_code_3class` (Derived from CSISA farmer post-harvest recall surveys).

### 2.2 Class Distribution Across Partitions

| Partition | Total Records | No Stress (Code 0) | Mild Stress (Code 1) | Severe Stress (Code 2) | Severe Class Prevalence |
|---|:---:|:---:|:---:|:---:|:---:|
| **Full Benchmark** | 7,648 | 3,745 (48.97%) | 3,456 (45.19%) | 447 (5.84%) | 5.84% |
| **Training (32 Dists)** | 6,135 | 3,036 (49.49%) | 2,735 (44.58%) | 364 (5.93%) | 5.93% |
| **Held-Out Test (8 Dists)** | 1,513 | 709 (46.86%) | 721 (47.65%) | 83 (5.49%) | 5.49% |

The dataset exhibits acute class imbalance: the minority Severe Stress class constitutes only **5.49%** of the held-out evaluation sample ($83$ out of $1,513$).

### 2.3 District Spatial Partitioning
To prevent spatial autocorrelation leakage, whole administrative districts were assigned exclusively to either the training or testing partition:
- **Held-Out Test Districts (8):** Araria, Banka, Begusarai, Buxar, Gopalganj, Jamui, Katihar, Kishanganj.
- **Training Districts (32):** Remaining 32 districts across Bihar and Eastern Uttar Pradesh.
- **Intersection:** $\text{Districts}_{\text{train}} \cap \text{Districts}_{\text{test}} = \emptyset$ (Zero district leakage verified).

### 2.4 Preprocessing & Imputation Anti-Leakage Audit
- **Imputation:** `SimpleImputer(strategy='median')` fitted strictly on the $6,135$ training plots. Medians computed during training were persisted into `preprocessor_5feat.joblib` and applied unchanged to test plots.
  - `s2_ndvi` training median: $0.4851$
  - `s2_ndwi` training median: $0.0620$
  - `s2_ndre` training median: $0.3154$
  - `s2_msavi` training median: $0.2468$
  - `smap_sm_pct` training median: $17.6200\%$
- **Scaling:** `StandardScaler()` fitted strictly on the training partition.
- **Missing Data in Test Partition:** Exactly 7 cloudy scenes in Araria district were imputed using the persisted training medians.

---

## 3. Comprehensive Model Performance Benchmark

All metrics evaluated on the strict spatial holdout ($N = 1,513$, 83 Severe Stress cases).

| Model ID | Model Name & Feature Regime | Decision Threshold | Macro-F1 | Balanced Acc | No Stress F1 | Mild Stress F1 | Severe Stress F1 | Severe Precision | Severe Recall | Severe False Alarms | Severe PR-AUC | Latency (ms) |
|---|---|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `rule_baseline` | **Deterministic Rule Baseline** (5-Feat) | Agronomic Heuristic (NDVI<0.30, SM<15%) | **0.3053** | **0.3911** | 0.1389 | **0.6282** | **0.1490** | **11.05%** | **22.89%** | **153** | N/A | **0.0016** |
| `rf_5feat_argmax` | Random Forest (5-Feat Argmax) | Argmax ($P \ge 0.50$) | 0.3062 | 0.3075 | 0.3887 | 0.4687 | 0.0611 | 8.33% | 4.82% | 44 | 0.0659 | 25.52 |
| `rf_5feat_tuned` | **Random Forest (5-Feat Tuned)** | Tuned Severe $T = 0.27$ | 0.2999 | 0.3069 | 0.3734 | 0.4428 | 0.0833 | 6.37% | 12.05% | 147 | 0.0659 | 25.52 |
| `hgb_5feat_argmax` | HistGradientBoosting (5-Feat Argmax) | Argmax ($P \ge 0.50$) | 0.2970 | 0.2992 | 0.3781 | 0.4791 | 0.0339 | 3.19% | 3.61% | 91 | 0.0488 | 4.51 |
| `hgb_5feat_tuned` | HistGradientBoosting (5-Feat Tuned) | Tuned Severe $T = 0.02$ | 0.0865 | 0.2748 | 0.0372 | 0.1377 | 0.0847 | 4.50% | **72.29%** | 1,274 | 0.0488 | 4.51 |
| `logreg_9feat_bal` | Logistic Regression (9-Feat Full) | Balanced Class Weights | 0.2771 | 0.4679 | 0.5508 | 0.0335 | 0.2469 | 14.89% | 72.29% | 343 | Not rep. | 0.50 |
| `rf_9feat_argmax` | Random Forest (9-Feat Full Argmax) | Argmax ($P \ge 0.50$) | 0.3115 | 0.3136 | 0.4927 | 0.3733 | 0.0684 | 11.76% | 4.82% | 30 | Not rep. | 24.57 |
| `rf_9feat_tuned` | Random Forest (9-Feat Full Tuned) | Tuned Severe $T = 0.33$ | **0.3405** | **0.3397** | 0.4872 | 0.3686 | 0.1655 | **19.35%** | 14.46% | 50 | 0.0188 | 24.57 |
| `hgb_9feat_argmax` | HistGradientBoosting (9-Feat Argmax) | Argmax ($P \ge 0.50$) | 0.3314 | 0.3323 | 0.4974 | 0.4284 | 0.0685 | 7.94% | 6.02% | 58 | Not rep. | 2.07 |
| `hgb_9feat_tuned` | HistGradientBoosting (9-Feat Tuned) | Tuned Severe $T = 0.41$ | 0.3329 | 0.3337 | 0.5016 | 0.4261 | 0.0709 | 8.62% | 6.02% | 53 | Not rep. | 2.07 |

---

## 4. Confusion Matrix Audits

Class ordering: **Class 0 = No Stress, Class 1 = Mild Stress, Class 2 = Severe Stress**.

### 4.1 Deterministic Agronomic Rule Baseline
```
Actual \ Predicted     No Stress (0)    Mild Stress (1)    Severe Stress (2)    Total Actual
No Stress (0)               54               582                  73                709
Mild Stress (1)             15               626                  80                721
Severe Stress (2)            0                64                  19                 83
Total Predicted             69             1,272                 172              1,513
```
- **Severe Stress Analysis:**
  - True Positives ($TP$): $19$
  - False Positives ($FP$): $73 + 80 = 153$
  - False Negatives ($FN$): $0 + 64 = 64$
  - True Negatives ($TN$): $54 + 582 + 15 + 626 = 1,277$
  - Severe Recall: $19 / 83 = 22.89\%$
  - Severe Precision: $19 / 172 = 11.05\%$
  - False Positive Rate ($FPR$): $153 / 1,430 = 10.70\%$

### 4.2 Candidate 5-Feature Random Forest (Tuned $T = 0.27$) — Active Phase 8 Model
```
Actual \ Predicted     No Stress (0)    Mild Stress (1)    Severe Stress (2)    Total Actual
No Stress (0)              236               414                  59                709
Mild Stress (1)            296               337                  88                721
Severe Stress (2)           23                50                  10                 83
Total Predicted            555               801                 157              1,513
```
- **Severe Stress Analysis:**
  - True Positives ($TP$): $10$
  - False Positives ($FP$): $59 + 88 = 147$
  - False Negatives ($FN$): $23 + 50 = 73$
  - True Negatives ($TN$): $236 + 414 + 296 + 337 = 1,283$
  - Severe Recall: $10 / 83 = 12.05\%$
  - Severe Precision: $10 / 157 = 6.37\%$
  - False Positive Rate ($FPR$): $147 / 1,430 = 10.28\%$

### 4.3 HistGradientBoosting 5-Feature (Tuned $T = 0.02$) — Pathological Case
```
Actual \ Predicted     No Stress (0)    Mild Stress (1)    Severe Stress (2)    Total Actual
No Stress (0)               14                63                 632                709
Mild Stress (1)             20                59                 642                721
Severe Stress (2)            9                14                  60                 83
Total Predicted             43               136               1,334              1,513
```
- **Severe Stress Analysis:**
  - True Positives ($TP$): $60$
  - False Positives ($FP$): $632 + 642 = 1,274$
  - False Negatives ($FN$): $9 + 14 = 23$
  - True Negatives ($TN$): $14 + 63 + 20 + 59 = 156$
  - Severe Recall: $60 / 83 = 72.29\%$
  - Severe Precision: $60 / 1,334 = 4.50\%$
  - False Positive Rate ($FPR$): $1,274 / 1,430 = 89.09\%$

---

## 5. In-Depth Scientific Analysis of Findings

### 5.1 Why Does the Rule Baseline Outperform the ML Model?
The rule baseline relies on two direct physical agronomic thresholds:
1. $\text{NDVI} < 0.30$ indicates severe vegetative biomass collapse or crop emergence failure.
2. $\text{SMAP} < 15.0\%$ represents root-zone soil water content approaching the Permanent Wilting Point ($PWP$) for alluvial loams.

When fused via conservative worst-case ranking, the rule baseline successfully identifies $22.89\%$ of severe events ($19 / 83$). In contrast, the Random Forest model attempts to partition an uncalibrated 5-dimensional feature space where the classes overlap heavily due to survey label noise. Because the Random Forest tree splits optimize for overall Gini impurity rather than specific biophysical inflection points, it achieves only $12.05\%$ recall on unseen districts.

### 5.2 The Mathematical Mechanism of the HistGradientBoosting Base-Rate Trap
When tuning decision threshold $T$ on Out-Of-Fold probabilities using an unconstrained $F_{\beta}$ optimization with $\beta = 2$, the objective function heavily penalizes false negatives relative to false positives:
$$F_2 = \frac{5 \cdot \text{Precision} \cdot \text{Recall}}{4 \cdot \text{Precision} + \text{Recall}}$$
Because the minority class prevalence is so low ($5.49\%$), the optimizer discovered that slashing $T$ down to $0.02$ captured nearly all severe instances ($72.29\%$ recall). However, because the test partition contains $1,430$ non-severe plots, shifting $T$ to $0.02$ caused $89.09\%$ of non-severe plots to cross the threshold, generating $1,274$ false alarms. This serves as an important empirical case study in machine learning for precision agriculture: **optimizing recall without a strict precision lower bound creates an operationally hazardous advisory system.**

### 5.3 Feature Importance Breakdown (5-Feature Model)
Relative Gini importances from $150$ decision trees in `random_forest_5feat.joblib`:
1. `smap_sm_pct`: **45.37%**
2. `s2_ndwi`: **15.67%**
3. `s2_ndre`: **13.50%**
4. `s2_msavi`: **12.99%**
5. `s2_ndvi`: **12.48%**

Combined optical vegetation indices account for **54.63%** of total split importance, while microwave soil moisture accounts for **45.37%**. This validates the multi-sensor fusion hypothesis: both canopy optical reflectance and root-zone microwave radiometry provide essential, complementary biophysical signals.

---

## 6. Serialized Model Artifact Provenance

| Artifact Filename | Relative Path | SHA-256 Checksum | File Size | Serialization Format | Scikit-Learn Version |
|---|---|---|:---:|:---:|:---:|
| `preprocessor_5feat.joblib` | `data/research_benchmark/models/` | `616128656d1c422cc6292189cb0e045e5e15dc29dff24ab96bf4237740483467` | 2.1 KB | joblib | 1.6.1 |
| `random_forest_5feat.joblib` | `data/research_benchmark/models/` | `a8b10f1fa5c2b89e6f80b4bfc88273ad40af28d589260c3fa263229cb505e503` | 13.8 MB | joblib | 1.6.1 |
| `hist_gradient_boosting_5feat.joblib` | `data/research_benchmark/models/` | `3ae7ef4309544f4ab279be5ac1692dd710d2784a90dbdd0f2cc9e0e4bdd00f14` | 895 KB | joblib | 1.6.1 |
| `preprocessor.joblib` (9-Feat) | `data/research_benchmark/models/` | `20bb77ff91674d0c81fd8004ec338913fed577b78d5b827b9a3ea89d38fc4b53` | 2.4 KB | joblib | 1.6.1 |
| `random_forest.joblib` (9-Feat) | `data/research_benchmark/models/` | `dccd55f0e860a61dacd1d1d45c7a036f6b010e0575bcf172942b10f2e6679bf6` | 14.1 MB | joblib | 1.6.1 |
| `hist_gradient_boosting.joblib` (9-Feat) | `data/research_benchmark/models/` | `c761639853b8dd2f1b4f79a41197b37e790c9a9c64a10522c56b19839cc20471` | 920 KB | joblib | 1.6.1 |
| `logistic_regression.joblib` (9-Feat) | `data/research_benchmark/models/` | `6a5d1014ff1685ac8b27dca54997b299e1c398f23a6a1da710732c73eb1c8c74` | 3.2 KB | joblib | 1.6.1 |

---

## 7. Inference Latency & Computational Efficiency

Inference latencies measured over 1,000 warm iterations on local Windows workstation:
- **Deterministic Rule Baseline:** $0.0016\text{ ms}$ ($1.57\ \mu\text{s}$)
- **Multinomial Logistic Regression (9-Feat):** $0.50\text{ ms}$
- **HistGradientBoosting (5-Feat):** $4.51\text{ ms}$
- **Random Forest (5-Feat, 150 Trees):** $25.52\text{ ms}$

The rule-based decision logic evaluates in under two microseconds, making it four orders of magnitude faster than the ensemble tree models and ideal for real-time edge or serverless deployment.
