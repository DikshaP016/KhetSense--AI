# KhetSense AI — Research Paper Figures and Tables Specification Plan

**Document Reference:** `KS-AUDIT-2026-FIGURES-TABLES-PLAN`  
**Project Title:** KhetSense AI: AI-Driven Crop Stress Detection and Multilingual Voice-Based Irrigation Advisory Using Satellite Remote Sensing  
**Intended Publication Format:** IEEE Two-Column Journal / Transactions Format  
**Author:** Diksha Poojary (Roll No. 136) | Master of Computer Applications (MCA)  
**Date:** October 21, 2026  
**Destination:** `reports/project_audit/KhetSense_AI_Paper_Figures_Tables_Plan.md`  

---

## 1. Overview & Publication Standards

This document establishes the detailed specifications, source artifacts, mathematical inputs, and caption texts for all **Figures (8)** and **Tables (8)** proposed for the academic research paper. Every visual asset is linked directly to existing, reproducible project artifacts or validated Python test suites. 

All figures are designed to comply with IEEE publication requirements:
- Minimum resolution: **300 DPI** for raster graphics (`.png`); vector graphics (`.pdf` / `.svg`) preferred for flowcharts and architectures.
- Color palette: Colorblind-safe palettes (Viridis, Cividis, ColorBrewer Set2) with distinct grayscale contrast.
- Typography: Arial or Helvetica sans-serif fonts, 8 pt to 10 pt matching IEEE caption specifications.

---

## 2. Scientific Figure Specification Plan

### Figure 1: End-to-End System Architecture of KhetSense AI
- **Type:** Architectural Block Diagram / Flowchart.
- **Source Data / Files:** `pipeline/test_pipeline.py`, `webhook_server.py`, `whatsapp/registration_flow.py`, `pipeline/location_validator.py`.
- **Purpose:** Illustrates the four functional layers of KhetSense AI: Farmer Messaging Layer (WhatsApp Cloud API), Geospatial Ingestion Layer (GEE, NASA CMR, OpenWeather), Core Intelligence Layer (Agronomic Rules, 5-Feature ML, Rainfall Guardrails), and Multilingual Delivery Layer (Text Cards, Neural Voice Notes).
- **Proposed Caption:** *"Fig. 1. End-to-end system architecture of KhetSense AI illustrating decoupled ingestion of Sentinel-2 surface reflectance, NASA SMAP radiometry, and weather forecasts, leading to dual-path agronomic inference and multilingual WhatsApp delivery."*
- **Production Status:** **Ready to generate.** Flowchart defined in Mermaid syntax in Comprehensive Technical Report (Chapter 6).

### Figure 2: Geospatial Dataset Partitioning and Spatial Block Holdout
- **Type:** Geographic Choropleth Map / Spatial Split Schematic.
- **Source Data / Files:** `data/research_benchmark/csisa_wheat_multisensor_features_2018.csv`, `data/research_benchmark/train_live_native_models.py`.
- **Purpose:** Visualizes the geographic distribution of 7,648 survey plots across Eastern India (Bihar, Eastern UP, Odisha), highlighting the 32 training districts ($N = 6,135$) and the 8 completely isolated held-out test districts ($N = 1,513$) to demonstrate zero spatial leakage.
- **Proposed Caption:** *"Fig. 2. Spatial block holdout partition across Eastern India showing the 32 training districts (blue) and 8 held-out evaluation districts (orange), guaranteeing zero spatial autocorrelation leakage between model training and testing."*
- **Production Status:** **Data verified.** Can be rendered using geopandas with India district boundary shapefiles and `district` column in CSV.

### Figure 3: Live-Native 5-Feature Preprocessing & ML Inference Pipeline
- **Type:** Technical Pipeline Flowchart.
- **Source Data / Files:** `pipeline/ml_inference.py`, `data/research_benchmark/models/preprocessor_5feat.joblib`.
- **Purpose:** Details the exact feature flow: extraction of optical bands (B4, B5, B8, B11) and SMAP moisture, normalization to $[0, 1]$, median imputation using pre-fitted training statistics, standard scaling, and probability extraction from `random_forest_5feat.joblib`.
- **Proposed Caption:** *"Fig. 3. Feature transformation pipeline for live-native inference: raw multi-sensor telemetry undergoes boundary reduction, validity checking, pre-fitted training median imputation, and severe-threshold classification ($T = 0.27$)."*
- **Production Status:** **Ready to generate.** Fully specified in source code and unit tests.

### Figure 4: Severe Stress Precision-Recall (PR) Curves & Decision Thresholds
- **Type:** 2D Line Chart (Precision vs. Recall).
- **Source Data / Files:** `data/research_benchmark/train_live_native_models.py` (lines 316–325 & 378–383), `reports/evaluation/evaluation_charts.png`.
- **Purpose:** Compares the Precision-Recall curves for the minority Severe Stress class ($5.49\%$ prevalence) across Random Forest and HistGradientBoosting under standard and tuned threshold operating points. Highlights the extreme drop in precision when threshold $T$ approaches zero.
- **Proposed Caption:** *"Fig. 4. Precision-Recall curves for the minority Severe Stress class ($5.49\%$ prevalence). Tuning $T$ on HistGradientBoosting to $0.02$ causes an operational base-rate collapse, whereas Random Forest at $T = 0.27$ maintains a balanced operational trade-off."*
- **Production Status:** **Verified from artifact.** Matplotlib rendering exists in `reports/evaluation/evaluation_charts.png`.

### Figure 5: Multi-Model Confusion Matrix Heatmaps
- **Type:** $3 \times 3$ Confusion Matrix Heatmaps with normalized row percentages and raw counts.
- **Source Data / Files:** `reports/evaluation/confusion_matrices.json`.
- **Sub-Figures:**
  - *(a) Deterministic Agronomic Rule Baseline* ($N = 1,513$).
  - *(b) Candidate 5-Feature Random Forest (Tuned $T = 0.27$)*.
  - *(c) HistGradientBoosting (Tuned $T = 0.02$ — Severe False Alarm Case)*.
- **Purpose:** Visually confirms that the Deterministic Rule Baseline captures more true severe stress instances ($TP = 19$) than the tuned Random Forest ($TP = 10$) with comparable false alarms ($153$ vs $147$), and displays the catastrophic column collapse of HistGradientBoosting ($1,274$ false alarms).
- **Proposed Caption:** *"Fig. 5. Normalized confusion matrices on 1,513 held-out test plots across unseen districts: (a) Deterministic Rule Baseline, (b) 5-Feature Random Forest (Tuned $T=0.27$), and (c) HistGradientBoosting (Tuned $T=0.02$). Class labels: 0: No Stress, 1: Mild Stress, 2: Severe Stress."*
- **Production Status:** **Verified from artifact.** Complete matrices documented in `reports/evaluation/confusion_matrices.json`.

### Figure 6: Gini Feature Importance in Live-Native Random Forest
- **Type:** Horizontal Bar Chart with error bars / percentage annotations.
- **Source Data / Files:** `data/research_benchmark/models/random_forest_5feat.joblib`, `reports/evaluation/evaluation_summary.md` (lines 108–119).
- **Purpose:** Illustrates the relative importance of each feature in the 150-tree Random Forest: NASA SMAP microwave moisture ($45.37\%$), NDWI ($15.67\%$), NDRE ($13.50\%$), MSAVI ($12.99\%$), and NDVI ($12.48\%$).
- **Proposed Caption:** *"Fig. 6. Mean decrease in Gini impurity across 150 estimators in the 5-feature Random Forest. Microwave soil moisture accounts for $45.37\%$ of decision importance, while optical canopy reflectance indices collectively represent $54.63\%$."*
- **Production Status:** **Verified from artifact.** Exact numerical percentages verified from model checkpoint.

### Figure 7: Two-Tier Rainfall Guardrail Decision State Machine
- **Type:** UML State Machine / Logic Decision Tree.
- **Source Data / Files:** `pipeline/classifier.py` (lines 120–180), `pipeline/test_pipeline.py` (lines 562–600).
- **Purpose:** Diagrams how the biophysical stress classification (No Stress, Mild Stress, Severe Stress) is combined with the 48-hour forward rainfall forecast ($R_1 = 5.0\text{ mm}$, $R_2 = 15.0\text{ mm}$) to produce the final recommended action (`IRRIGATE_NOW`, `MONITOR`, `HOLD_RAIN_SOON`, `HOLD_RECHECK`).
- **Proposed Caption:** *"Fig. 7. Two-tier rainfall guardrail logic decoupling observed biophysical crop stress from actionable irrigation advice based on short-term numerical precipitation forecasts ($R_1 = 5.0\text{ mm}$, $R_2 = 15.0\text{ mm}$).*
- **Production Status:** **Ready to generate.** Fully specified in source code.

### Figure 8: Conversational WhatsApp User Interface & Vernacular Voice Generation
- **Type:** Screen Capture Mockup & Speech Spectrogram/Waveform.
- **Source Data / Files:** `demo_khetsense.py` (Scenario 5 output), `pipeline/tts_provider.py`.
- **Purpose:** Shows the side-by-side presentation of the formatted WhatsApp advisory card in Marathi and English, along with the spoken voice script and audio waveform representation (`audio/ogg; codecs=opus`).
- **Proposed Caption:** *"Fig. 8. Multilingual advisory delivery over WhatsApp: (left) English advisory card, (center) native Marathi advisory card with AI provenance disclosure and prototype disclaimer, and (right) synthesized neural voice note script and audio waveform."*
- **Production Status:** **Verified by executed test.** Terminal output generated in demo runs; audio files generated by `pipeline/tts_provider.py`.

---

## 3. Scientific Table Specification Plan

### Table I: Comparison of Precision Agriculture Advisory Paradigms
- **Source Data:** Literature review audit (`KhetSense_Research_References_and_Evidence.md`).
- **Purpose:** Compares In-Situ IoT Networks, Regional Portals, General LLM Chatbots, and KhetSense AI across 10 functional criteria (Hardware Cost, Spatial Scale, Delivery Channel, Audio Support, Latency, Failure Risk).
- **Proposed Caption:** *"TABLE I: Comparative Assessment of Precision Agricultural Advisory Paradigms"*
- **Production Status:** **Complete.** Included in Chapter 4 of Comprehensive Technical Report.

### Table II: Multi-Sensor Remote Sensing Specifications and Band Characteristics
- **Source Data:** Mission technical specifications (ESA Sentinel-2, NASA SMAP, OpenWeather).
- **Purpose:** Documents spatial resolution, revisit cadence, spectral band centers, radiometric accuracy, and physical parameters for all four satellite bands and radiometry products.
- **Proposed Caption:** *"TABLE II: Remote Sensing Sensor Specifications, Spectral Characteristics, and Extraction Parameters"*
- **Production Status:** **Complete.** Included in Chapter 8 of Comprehensive Technical Report.

### Table III: Dataset Summary and Class Distributions
- **Source Data:** `data/research_benchmark/csisa_wheat_multisensor_features_2018.csv`, `evaluation_manifest.json`.
- **Purpose:** Documents total plots, district counts, and sample counts for No Stress, Mild Stress, and Severe Stress across Full Benchmark, Training Partition, and Held-Out Test Partition.
- **Proposed Caption:** *"TABLE III: Dataset Stratification and Class Distribution Across Spatial Partitions"*
- **Production Status:** **Complete.** Verified in Model Evaluation Audit (Section 2.2).

### Table IV: Overall Multi-Model Classification Performance Benchmark
- **Source Data:** `reports/evaluation/model_comparison.csv`.
- **Purpose:** The primary experimental results table presenting Macro-F1, Balanced Accuracy, Class-wise Precision, Recall, and F1 for No Stress, Mild Stress, and Severe Stress across all 10 evaluated model configurations on the 1,513 held-out test plots.
- **Proposed Caption:** *"TABLE IV: Multi-Class Stress Classification Performance on Held-Out Spatial Test Set (8 Districts, $N = 1,513$)"*
- **Production Status:** **Complete.** Verified from evaluation CSV artifact.

### Table V: Confusion Matrix and Error Distribution on Held-Out Districts
- **Source Data:** `reports/evaluation/confusion_matrices.json`.
- **Purpose:** Details True Positives ($TP$), False Positives ($FP$), False Negatives ($FN$), and True Negatives ($TN$) for the critical Severe Stress class across the Rule Baseline, 5-Feature Random Forest, and 5-Feature HistGradientBoosting.
- **Proposed Caption:** *"TABLE V: Severe Stress Error Distribution, False Alarm Counts, and Specificity Across Key Models"*
- **Production Status:** **Complete.** Documented in Model Evaluation Audit (Section 4).

### Table VI: Computational Complexity and Inference Latency Benchmark
- **Source Data:** `reports/evaluation/model_comparison.csv`.
- **Purpose:** Summarizes execution time in milliseconds and relative speedup factor over 1,000 iterations for Deterministic Rules ($0.0016\text{ ms}$), Logistic Regression ($0.50\text{ ms}$), HistGradientBoosting ($4.51\text{ ms}$), and Random Forest ($25.52\text{ ms}$).
- **Proposed Caption:** *"TABLE VI: Model Inference Latency and Execution Speed Benchmark on Local Workstation"*
- **Production Status:** **Complete.** Documented in Model Evaluation Audit (Section 7).

### Table VII: Comprehensive Automated Software Verification Results
- **Source Data:** Test suite execution logs (`python -m unittest discover -s tests`).
- **Purpose:** Documents test module names, test counts (401 total), execution time (44.33 s), components tested, mocked interfaces, and 100% pass rates across all 14 test suites.
- **Proposed Caption:** *"TABLE VII: Software Quality Assurance and Test Suite Verification Summary"*
- **Production Status:** **Complete.** Executed and verified live in the current environment.

### Table VIII: Research Paper Evidence, Verification Status, and Scientific Boundaries
- **Source Data:** `reports/project_audit/KhetSense_AI_Research_Evidence_Matrix.md`.
- **Purpose:** Explicitly catalogs verified claims vs. unsupported/disallowed claims, ensuring that academic reviewers have a transparent view of the project's real capabilities and limitations.
- **Proposed Caption:** *"TABLE VIII: Scientific Claim Verification Matrix, Supporting Artifacts, and Publication Boundaries"*
- **Production Status:** **Complete.** Included in Deliverable B.
