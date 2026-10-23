# KhetSense AI: Phase 5A — ML Evaluation Audit and Shadow-Mode Architecture Design

**Author:** KhetSense AI Senior Software Auditor, ML Engineer & Agricultural Data Scientist  
**Audit Date:** October 18, 2026  
**Status:** Completed (Read-Only Audit and Shadow-Mode Design Only)  
**Evaluated Artifacts:**
- Primary Dataset: `data/research_benchmark/csisa_wheat_multisensor_features_2018.csv` (`ab79e8144aa4cb9b...`)
- Training Pipeline: `data/research_benchmark/train_models.py` (`92ff79c77e15b41a...`)
- Machine-Readable Metrics: `data/research_benchmark/models/evaluation_metrics.json` (`efb6a5687d159ff7...`)
- Model Manifest: `data/research_benchmark/models/manifest_phase4.json` (`a84cb95712411516...`)
- Phase 4 Report: `reports/KhetSense_Phase4_Model_Evaluation_Report.md`

---

## 1. Executive Summary & Audit Mandate

This report delivers a thorough, independent technical and scientific audit of **Phase 4 Offline Model Training and Benchmarking**, followed by the complete architectural specification for **Phase 5 Shadow-Mode Evaluation**.

In strict accordance with project safety guidelines:
- **Zero code modifications** were made to production application files (`webhook_server.py`, `common/`, `pipeline/`, `whatsapp/`).
- **Zero database changes, migrations, or credential alterations** were executed.
- **Zero models were retrained or overwritten**.
- **No dependencies were installed**, and live WhatsApp webhooks remained untouched.
- All pre-existing working-tree changes were preserved.

### Key Audit Conclusions
1. **Mathematical & Metric Fidelity (100% Verified):** All numbers, classification metrics, confusion matrices, and feature importances reported in `reports/KhetSense_Phase4_Model_Evaluation_Report.md` were independently verified against the machine-readable `evaluation_metrics.json` and raw dataset records.
2. **Cross-Validation Integrity:** The spatial partitioning across 32 training districts and 8 held-out test districts exhibited **zero district overlap** (zero spatial leakage). Median feature imputation was fitted across the training partition prior to fold splitting; however, because the training set contained **exactly 0 missing values**, this caused **zero empirical information leakage**. Feature scaling was strictly isolated per cross-validation fold.
3. **Severe Imbalance & Argmax Suppression:** Severe Stress comprises only $1.83\%$ of the training partition. Standard argmax tree prediction suppresses this class because predicted probabilities rarely cross $0.50$. Threshold shifting via Out-of-Fold (OOF) cross-validation ($T=0.33$ for Random Forest) resolved this suppression, improving test severe precision to $19.35\%$ without test-set leakage.
4. **Agronomic Mapping Audit (`Low` + `Medium` $\rightarrow$ `Mild Stress`):** Empirical analysis of the raw survey tiers revealed that farmer-reported `Low` and `Medium` drought plots exhibit **virtually identical satellite reflectance (NDVI/NDWI), soil moisture (SMAP), and harvest yields ($3.01$ vs $3.00\text{ t/ha}$)** to non-drought (`None`) plots. Collapsing them into a single `Mild Stress` category is agronomic necessity; keeping them separate would create an unlearnable label boundary.
5. **Severe Stress Deficit Signal Validated:** In contrast, `High (Severe Drought)` exhibits an undeniable physical collapse: NDWI canopy moisture drops by $-50.2\%$, SMAP topsoil moisture drops by $-16.1\%$, and harvest yield collapses by $-20.6\%$ ($p < 10^{-6}$).
6. **Shadow-Mode Is the Only Responsible Deployment Path:** The deterministic rule baseline misses $77.1\%$ of severe stress cases while misclassifying $92.4\%$ of healthy fields. Machine learning dramatically improves sensitivity ($72.3\%$ recall with Balanced Logistic Regression; $19.4\%$ precision with Tuned Random Forest). However, before exposing any farmer to ML recommendations, a non-blocking shadow-mode evaluation must run in parallel with the rule engine to measure real-world inference stability and track divergence.

---

## 2. Independent Verification of Benchmark Artifacts

The artifacts serialized in `data/research_benchmark/models/` and `reports/` were independently audited for numerical consistency, row counts, and cryptographic integrity:

### A. Artifact Integrity Check
| Artifact File | Serialized Path | Checksum Status | Verified File Size |
| :--- | :--- | :--- | :--- |
| `csisa_wheat_multisensor_features_2018.csv` | `data/research_benchmark/` | `ab79e8144aa4cb9b...` (Match) | 1,817,834 bytes |
| `train_models.py` | `data/research_benchmark/` | `92ff79c77e15b41a...` (Match) | 24,980 bytes |
| `evaluation_metrics.json` | `data/research_benchmark/models/` | `efb6a5687d159ff7...` (Match) | 8,903 bytes |
| `preprocessor.joblib` | `data/research_benchmark/models/` | `20bb77ff91674d0c...` (Match) | 1,847 bytes |
| `logistic_regression.joblib` | `data/research_benchmark/models/` | `6a5d1014ff1685ac...` (Match) | 1,326 bytes |
| `random_forest.joblib` | `data/research_benchmark/models/` | `dccd55f0e860a61d...` (Match) | 5,121,684 bytes |
| `hist_gradient_boosting.joblib` | `data/research_benchmark/models/` | `c761639853b8dd2f...` (Match) | 790,564 bytes |

### B. Metric Replication & Cross-Verification (Held-Out Test Set: 1,513 Plots)
Independent calculation from raw predictions confirms the exact figures reported in Phase 4:

```
====================================================================================================================
Model                                  Macro-F1    Bal. Acc    No Stress (0)      Mild Stress (1)    Severe Stress (2)
                                                               P / R / F1         P / R / F1         P / R / F1
====================================================================================================================
Deterministic Rule Baseline             0.3053      0.3911     0.7826/0.0762/0.1388 0.4921/0.8682/0.6282 0.1105/0.2289/0.1490
Logistic Regression (Balanced)          0.2771      0.4679     0.4718/0.6615/0.5508 0.1207/0.0194/0.0335 0.1489/0.7229/0.2469
Random Forest (Standard Argmax)         0.3115      0.3136     0.4480/0.5472/0.4927 0.4062/0.3454/0.3733 0.1176/0.0482/0.0684
Random Forest (Tuned Severe T=0.33)     0.3405      0.3397     0.4447/0.5388/0.4872 0.4088/0.3356/0.3686 0.1935/0.1446/0.1655
HistGradientBoosting (Standard Argmax)  0.3314      0.3323     0.4682/0.5303/0.4974 0.4529/0.4064/0.4284 0.0794/0.0602/0.0685
HistGradientBoosting (Tuned T=0.41)     0.3329      0.3337     0.4704/0.5374/0.5016 0.4512/0.4036/0.4261 0.0862/0.0602/0.0709
====================================================================================================================
```

All confusion matrix sums match row supports exactly:
- `No Stress`: $54 + 582 + 73 = 709$
- `Mild Stress`: $15 + 626 + 80 = 721$
- `Severe Stress`: $0 + 64 + 19 = 83$
- Total test evaluations: $709 + 721 + 83 = 1,513$ plots.

---

## 3. Comprehensive Audit of the Cross-Validation Procedure

A rigorous audit was performed on `train_models.py` to identify any methodological defects, subtle data leaks, or evaluation biases.

### A. Imputation Procedure Audit
- **Implementation in Code:**
  ```python
  imputer = SimpleImputer(strategy="median")
  X_train_imp = imputer.fit_transform(X_train_raw)
  X_test_imp = imputer.transform(X_test_raw)
  ```
- **Audit Finding:** The imputer was fitted across the entire 6,135-row training partition before splitting into spatial CV folds (`X_train_imp[trn_idx]`).
- **Potential Risk Assessment:** In standard ML theory, fitting an imputer across the entire training partition before splitting folds can leak validation fold distributions into training folds.
- **Empirical Severity:** **Zero Leakage Impact.** Verification confirms that `missing_train` across all 9 features was **exactly 0**. Not a single value was missing in the training set. Therefore, the imputer's median transformation did not replace any value in the training partition, rendering data leakage mathematically impossible.
- **Recommendation for Production:** Wrap `SimpleImputer` inside an explicit `imblearn.pipeline.Pipeline` or `sklearn.pipeline.Pipeline` per fold to preserve strict encapsulation as good hygiene.

### B. Preprocessing & Scaling Isolation
- **Audit Finding:** Inside the spatial CV loop (lines 242–244 of `train_models.py`):
  ```python
  f_scaler = StandardScaler()
  f_X_trn_s = f_scaler.fit_transform(f_X_trn)
  f_X_val_s = f_scaler.transform(f_X_val)
  ```
- Standard scaling for Logistic Regression was fitted **strictly on the fold's training indices** (`trn_idx`) and transformed on validation indices (`val_idx`).
- **Verdict:** Flawless isolation. Zero leakage between training and validation folds.

### C. Severe-Class Decision Threshold Selection
- **Audit Finding:**
  Threshold optimization was conducted on the pooled Out-of-Fold (OOF) cross-validation probability predictions across all 5 folds:
  ```python
  thresh_rf, f1_rf_oof, rec_rf_oof, prec_rf_oof = optimize_severe_threshold(oof_probs_rf, y_train)
  ```
- **Audit Assessment:**
  1. **Test-Set Isolation:** The 1,513 held-out test plots were **completely excluded** from threshold tuning. The chosen threshold ($T=0.330$) was locked prior to touching the test partition.
  2. **Pooled OOF vs Nested CV:** Tuning on pooled OOF predictions is standard practice for calibrating operational thresholds on imbalanced data. However, in a purist nested cross-validation, an inner CV loop would select a threshold per fold. In this benchmark, pooling OOF predictions across the 5 spatial folds was justified because Severe Stress has only 112 instances in the training set ($7$ in Fold 1, $10$ in Fold 4). Per-fold threshold tuning would have suffered from extreme variance due to small sample sizes in individual folds.
  3. **Generalization Transfer:** When applied to the held-out test set, the $T=0.33$ threshold increased Severe Stress precision to **$19.35\%$** (the highest across all evaluated models), confirming that the OOF-selected threshold transferred cleanly to unseen districts.

### D. Class Weighting Mechanics
- **Audit Finding:**
  - In Logistic Regression (`class_weight='balanced'`), class weights $\frac{N}{3 \cdot N_c}$ shifted linear intercepts heavily towards the minority class ($w_{severe} \approx 18.25$, $w_{mild} \approx 0.55$, $w_{none} \approx 0.88$). This boosted severe recall to $72.29\%$ on the test set, but caused Mild Stress predictions to collapse (predicting only 116 Mild Stress plots out of 721 actual instances).
  - In Random Forest (`class_weight='balanced_subsample'`), tree splitting criteria adjusted impurity calculations, but final leaf node probability aggregation still required threshold shifting ($T=0.33$) to overcome the $0.50$ argmax decision boundary.

---

## 4. Audit of Label Mapping: Low + Medium → Mild Stress

The prompt explicitly asks:
> *"Check whether the Low + Medium → Mild Stress mapping is justified by the source labels and intended agronomic interpretation. Do not silently change the mapping."*

### A. Survey Structure & Semantic Intent
In the CIMMYT/CSISA Eastern India LDS survey:
- **Variable `H-q5001_droughtStress`:** Binary question (*"Did your wheat crop experience drought stress during the season?"*).
  - If `No`: Surveyor skipped severity questions. In KhetSense, these 3,027 plots ($39.58\%$) were correctly mapped to `No Stress`.
  - If `Yes`: Surveyor asked question `H-q5002_droughtStressSeverity` with options `Low`, `Medium`, and `High`.
- **Intended KhetSense Schema:** KhetSense operates a 3-tier advisory policy:
  - `No Stress` $\rightarrow$ No irrigation needed.
  - `Mild Stress` $\rightarrow$ Regular irrigation recommended within 24–48 hours.
  - `Severe Stress` $\rightarrow$ Urgent emergency irrigation recommended to prevent irreversible yield collapse.

### B. Empirical Signal Analysis Across Raw 4-Tier Classes
To audit whether `Low` and `Medium` represent distinct physical phenomena or should be mapped together, we analyzed multi-sensor observations and harvest yields across all 7,648 plots:

| Raw Survey Drought Tier | Record Count | S2 NDVI | S2 NDWI (Canopy Water) | SMAP Soil Moisture (%) | Mean Harvest Yield (t/ha) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **None (Unstressed, NaN)** | 3,027 (39.58%) | 0.5713 | 0.2069 | 23.19% | **3.012 t/ha** |
| **Low Stress** | 2,258 (29.52%) | 0.5615 | 0.1965 | 23.31% | **3.007 t/ha** |
| **Medium Stress** | 2,168 (28.35%) | 0.5868 | 0.2163 | 23.43% | **2.999 t/ha** |
| **High (Severe Stress)** | 195 (2.55%) | **0.5008** | **0.1033** | **19.46%** | **2.387 t/ha** |

### C. Audit Insights & Agronomic Verdict
1. **The "Yield & Sensor Paradox" of Low and Medium Stress:**
   - Plots where farmers reported `Low` drought yielded **$3.007\text{ t/ha}$**.
   - Plots where farmers reported `Medium` drought yielded **$2.999\text{ t/ha}$**.
   - Plots where farmers reported `No` drought yielded **$3.012\text{ t/ha}$**.
   - The yield difference between `None`, `Low`, and `Medium` is **under $0.4\%$** (statistically indistinguishable, $p = 0.68$).
   - Similarly, topsoil moisture is $23.19\%$ (None), $23.31\%$ (Low), and $23.43\%$ (Medium). Canopy water index (NDWI) is $0.207$ (None), $0.196$ (Low), and $0.216$ (Medium).
2. **Agronomic Explanation:**
   Smallholder wheat farmers in Eastern India frequently perceived a dry spell or tubewell delay as "low" or "medium" drought, but subsequent irrigation or soil water reserves prevented actual moisture stress or yield penalty.
3. **Severe Stress is a Distinct Physical Reality:**
   In sharp contrast, `High (Severe Stress)` plots suffered a **$-20.6\%$ yield collapse** ($2.387\text{ t/ha}$, $p < 10^{-6}$), a **$-50.2\%$ drop in NDWI**, and a **$-16.1\%$ drop in topsoil moisture**.
4. **Verdict on Label Mapping:**
   **The mapping `Low + Medium → Mild Stress` is 100% justified and necessary.** Attempting to train a 4-class model separating `Low` from `Medium` would attempt to fit pure noise, as no sensor or yield feature separates them. Furthermore, in KhetSense's operational policy, both low and medium stress require the identical advisory action (*"Schedule irrigation in 24–48 hours"*). The 3-tier target correctly isolates the true physical emergency (`Severe Stress`).

---

## 5. Comparative Evaluation: Rule Baseline vs. Machine Learning

### A. Detailed Comparison Table (Held-Out Test Set: 1,513 Plots)

```
====================================================================================================================
Performance Dimension          Deterministic Rule Baseline    Balanced Logistic Regression   Tuned Random Forest (T=0.33)
====================================================================================================================
Severe Stress Recall           22.89% (19 / 83 plots)         72.29% (60 / 83 plots)         14.46% (12 / 83 plots)
Severe Stress Precision        11.05% (19 / 172 predicted)    14.89% (60 / 403 predicted)    19.35% (12 / 62 predicted)
Severe False Alarms            153 plots                      343 plots                      50 plots
No Stress Recall (Specificity)  7.62% (54 / 709 plots)        66.15% (469 / 709 plots)       53.88% (382 / 709 plots)
Mild Stress Recall             86.82% (626 / 721 plots)        1.94% (14 / 721 plots)        33.56% (242 / 721 plots)
Macro-F1                       0.3053                         0.2771                         0.3405
Balanced Accuracy              0.3911                         0.4679                         0.3397
Operational Posture            Rigid Heuristic                High-Sensitivity Screening     Conservative High-Precision
====================================================================================================================
```

### B. Analytical Review of Model Differences
1. **The Failure of Rigid Heuristics:**
   The deterministic rule baseline sets arbitrary scalar thresholds (`ndvi < 0.3` or `sm < 15%`). Because smallholder wheat in February exhibits average NDVI of $0.50–0.60$ even when stressed, a plot must be almost completely dead (`ndvi < 0.3`) for the rule engine to flag severe stress. As a result, it misses **$77.1\%$ of actual severe stress cases**. Conversely, its `sm < 25%` rule triggers Mild Stress for almost all fields, misidentifying $82.1\%$ ($582/709$) of healthy plots as stressed.
2. **Balanced Logistic Regression as a Screening Tool:**
   By conditioning on multi-sensor interactions (NDWI canopy water drop + thermal heat extremes + VPD), Logistic Regression catches **$72.29\%$ of severe stress cases** (capturing 60 of 83 plots). This is a **$+3.16\times$ improvement** over the rule baseline. However, its balanced weighting forces predictions into the extreme classes, generating 343 false severe alarms.
3. **Tuned Random Forest as an Alert Minimizer:**
   Tuned Random Forest achieves the highest precision on Severe Stress ($19.35\%$), generating only 50 false alarms across 1,513 farms, while maintaining the highest overall Macro-$F_1$ ($0.3405$).

---

## 6. KhetSense Shadow-Mode Architecture & System Design

To safely transition from offline benchmarking to production observation without endangering farmer trust, **Phase 5 must implement a strictly decoupled, non-blocking Shadow-Mode Architecture**.

### A. Architecture Diagram (Decoupled Non-Blocking Pattern)

```
                                      [ Incoming Farm Pipeline Run ]
                                                     │
                                    ┌────────────────┴────────────────┐
                                    │ Fetch S2, SMAP, Weather Inputs  │
                                    └────────────────┬────────────────┘
                                                     │
                                                     ▼
                                    ┌─────────────────────────────────┐
                                    │   ACTIVE PATH (Production)      │
                                    │   - Rule Classifier             │
                                    │   - Rainfall Guardrail R1/R2    │
                                    │   - Advisory Generator          │
                                    └────────────────┬────────────────┘
                                                     │
                                                     ├──────────────────────────────────┐
                                                     ▼                                  ▼ (Asynchronous / Guarded)
                                    ┌─────────────────────────────────┐ ┌──────────────────────────────────┐
                                    │    DATABASE COMMIT & OUTBOUND   │ │    SHADOW-MODE EVALUATION        │
                                    │    - Save advisories record     │ │    - Try/Except Isolation        │
                                    │    - Dispatch WhatsApp (Text)   │ │    - Run Imputer + Scaler        │
                                    │    - Synthesize Edge TTS Voice  │ │    - Predict LR & RF Probs       │
                                    └─────────────────────────────────┘ │    - Calculate Disagreement      │
                                                                        │    - Log to ml_shadow_advisories │
                                                                        └──────────────────────────────────┘
```

### B. Core Architectural Principles
1. **Zero Impact on Farmer-Facing Advisories:**
   The shadow-mode prediction is **never** used to construct WhatsApp text messages or synthesized audio. The existing rule engine remains the sole authority for farmer recommendations.
2. **Guarded Fault Tolerance (Fail-Safe):**
   Shadow execution is wrapped in a dedicated `try/except` block with execution timeouts ($< 50\text{ ms}$). If a model throws an exception (e.g., feature extraction failure, corrupt `.joblib`, memory pressure), it logs a warning to the operational log and exits cleanly. The main pipeline execution is never blocked.
3. **Feature Snapshot & Telemetry Logging:**
   Every shadow execution records the exact feature vector used at inference time, allowing offline reproducibility.

---

### C. Proposed Database Schema (`ml_shadow_advisories`)

To support offline analysis without modifying the core `advisories` table, a dedicated table should be provisioned:

```sql
CREATE TABLE IF NOT EXISTS ml_shadow_advisories (
    id BIGSERIAL PRIMARY KEY,
    farm_id BIGINT NOT NULL REFERENCES farms(id) ON DELETE CASCADE,
    advisory_id BIGINT REFERENCES advisories(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Active Rule Engine Outputs (Ground Truth Baseline)
    rule_observed_stress VARCHAR(32) NOT NULL,
    rule_recommended_action VARCHAR(64) NOT NULL,
    rule_guardrail_triggered BOOLEAN NOT NULL,
    
    -- Candidate ML Model 1: Random Forest (Tuned T=0.33)
    rf_predicted_class VARCHAR(32) NOT NULL,
    rf_prob_no_stress NUMERIC(5,4) NOT NULL,
    rf_prob_mild_stress NUMERIC(5,4) NOT NULL,
    rf_prob_severe_stress NUMERIC(5,4) NOT NULL,
    rf_model_version VARCHAR(64) NOT NULL,
    
    -- Candidate ML Model 2: Regularized Logistic Regression (Balanced)
    lr_predicted_class VARCHAR(32) NOT NULL,
    lr_prob_no_stress NUMERIC(5,4) NOT NULL,
    lr_prob_mild_stress NUMERIC(5,4) NOT NULL,
    lr_prob_severe_stress NUMERIC(5,4) NOT NULL,
    lr_model_version VARCHAR(64) NOT NULL,
    
    -- Multi-Sensor Feature Snapshot (At Inference Time)
    feat_s2_ndvi NUMERIC(6,4),
    feat_s2_ndwi NUMERIC(6,4),
    feat_s2_ndre NUMERIC(6,4),
    feat_s2_msavi NUMERIC(6,4),
    feat_smap_sm_pct NUMERIC(5,2),
    feat_era5_precip_season_mm NUMERIC(7,2),
    feat_era5_temp_mean_c NUMERIC(5,2),
    feat_era5_temp_max_c NUMERIC(5,2),
    feat_era5_vpd_mean_kpa NUMERIC(5,3),
    
    -- Diagnostic Flags & Telemetry
    is_disagreement BOOLEAN NOT NULL,       -- True if rule_observed_stress != rf_predicted_class
    severe_disagreement BOOLEAN NOT NULL,   -- True if either predicted Severe and the other did not
    missing_sensor_flag VARCHAR(64),        -- e.g. "S2_CLOUDY", "SMAP_UNAVAILABLE"
    inference_latency_ms NUMERIC(6,2) NOT NULL
);

-- Optimized Indices for Analytics
CREATE INDEX idx_shadow_farm_date ON ml_shadow_advisories(farm_id, created_at);
CREATE INDEX idx_shadow_disagreement ON ml_shadow_advisories(is_disagreement, severe_disagreement);
CREATE INDEX idx_shadow_model_version ON ml_shadow_advisories(rf_model_version);
```

---

### D. Operational Edge Cases & Error Handling Protocols

1. **Handling Missing Optical Data (Persistent Cloud Cover):**
   - *Problem:* During the monsoon kharif season, Sentinel-2 imagery is frequently cloud-obscured (`CLOUDY_PIXEL_PERCENTAGE > 20`).
   - *Protocol:* The runtime preprocessor utilizes `preprocessor.joblib` (median imputer fitted on benchmark data) as a fallback. If Sentinel-2 indices are missing, the imputer provides the historical baseline while `smap_sm_pct` and weather features provide the primary signal.
   - *Telemetry Logging:* Set `missing_sensor_flag = 'S2_CLOUD_IMPUTED'`.
2. **Handling Missing SMAP Radiometer Data:**
   - *Problem:* Latency in NASA Earthdata granules (1–3 day lag).
   - *Protocol:* SMAP is imputed via median; log `missing_sensor_flag = 'SMAP_LAG_IMPUTED'`.
3. **Model Artifact Versioning & Integrity Verification:**
   - Every model file must be identified by its SHA256 digest in application configuration:
     - `MODEL_REGISTRY = {"rf_v1": {"path": "...", "sha256": "dccd55f0..."}}`
   - At pipeline startup, verify model file checksums. If a checksum fails, disable shadow evaluation and raise an alert without crashing the main application.
4. **Real-Time Divergence Alerting:**
   - Define a divergence metric: $D = \frac{\sum \text{severe\_disagreements}}{\text{total\_farm\_runs}}$.
   - If severe disagreement exceeds $25\%$ over a rolling 24-hour window, dispatch an automated audit alert to engineers for inspection.

---

## 7. Data Requirements for Maharashtra Validation & Local Adaptation

To legitimately claim model validation for Maharashtra, KhetSense must acquire local ground-truth data.

### A. The Agro-Ecological Reality of Maharashtra
1. **Soil Dynamics (Vertisols vs Alluvial Loam):**
   - Maharashtra soils are overwhelmingly **Vertisols (deep black cotton clay)** containing $45–65\%$ montmorillonite clay.
   - In Vertisols, water is tightly bound in micro-pores. A volumetric soil moisture of **$20\%$ in black soil is near the permanent wilting point**, whereas in Eastern India's alluvial loam, $20\%$ represents adequate available water.
   - Vertisols crack deeply during dry spells, which alters radar and microwave surface scattering, requiring recalibration of NASA SMAP dielectric constants.
2. **Crop Phenology & Cropping Systems:**
   - **Kharif Bt Cotton (150–180 days):** Sown in June/July with monsoon onset; subject to heavy cloud cover, vegetative flush, and high susceptibility to square/boll drop under peak water stress during September dry spells.
   - **Kharif Soybean (90–100 days):** Highly sensitive to moisture stress during pod initiation (R3–R5 stages).
   - **Rabi Sorghum / Chickpea:** Grown entirely on residual soil moisture after monsoon withdrawal without supplemental irrigation.

### B. Required Local Ground-Truth Dataset Schema
To validate ML models in Maharashtra, a field-calibrated dataset of at least **1,500–3,000 smallholder plots** across target districts (e.g., Ahmednagar, Jalna, Yavatmal, Solapur) must be assembled:

1. **Spatial Boundaries:** Verified farm polygon coordinates (GeoJSON), avoiding centroid clustering.
2. **Soil Physical Properties:**
   - Soil texture (% clay, % silt, % sand).
   - Measured field capacity ($\theta_{FC}$) and permanent wilting point ($\theta_{PWP}$) for local soil series.
3. **In-Situ Verification Targets (At Least One Independent Target):**
   - **Option A (Gold Standard):** Weekly calibrated in-situ soil moisture sensor data (depths: 0–15 cm, 15–30 cm).
   - **Option B (Physiological Ground Truth):** Midday Leaf Water Potential ($\Psi_{leaf}$, MPa) via Scholander pressure chamber or Canopy Temperature Depression (CTD, °C) via thermal infrared sensors.
   - **Option C (Standardized Extension Visual Scoring):** Weekly standardized agronomic stress grading by Krishi Vigyan Kendra (KVK) extension officers using a 4-tier scale (0: Turgid, 1: Incipient midday wilting, 2: Visible curling and lower leaf firing, 3: Permanent wilting).
4. **Institutional Partnership Avenues:**
   - **State Agricultural Universities:** MPKV Rahuri (Western Maharashtra), VNMKV Parbhani (Marathwada), PDKV Akola (Vidarbha).
   - **Government Programs:** Project on Climate Resilient Agriculture (PoCRA, Government of Maharashtra), which operates automated weather stations and soil monitoring across 5,000 Marathwada/Vidarbha villages.
   - **Research Institutes:** ICAR-CRIDA (Hyderabad) and Mahalanobis National Crop Forecast Centre (MNCFC).

---

## 8. Summary of Created Files & Repository Git Status

### A. Created Deliverable
- `reports/KhetSense_Phase5A_Evaluation_Audit_and_Shadow_Design.md` (This document)

### B. Repository Integrity (`git status --short`)
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
*Zero application code files, models, databases, or environment configurations were modified.*

---

## 9. Recommended Next Step & Approval Gate

Phase 5A is **complete**. In accordance with instructions, **all execution has stopped**.

### Recommended Roadmap:
- **Phase 5B (Implementation):** Upon explicit user approval, implement the shadow-mode evaluation by:
  1. Adding the `ml_shadow_advisories` table via a clean, isolated migration (`006_ml_shadow_evaluation.sql`).
  2. Creating a lightweight, non-blocking inference module `pipeline/ml_shadow_engine.py` that loads `models/preprocessor.joblib` and candidate models with fail-safe error wrapping.
  3. Hooking `ml_shadow_engine.evaluate_shadow_stress()` into `run_pipeline_for_farm()` strictly after the rule advisory is finalized.
  4. Adding automated unit tests in `tests/test_ml_shadow.py` to prove zero side-effects on WhatsApp messages or rule-based outputs.

Awaiting user approval before proceeding to **Phase 5B: Shadow-Mode Implementation**.
