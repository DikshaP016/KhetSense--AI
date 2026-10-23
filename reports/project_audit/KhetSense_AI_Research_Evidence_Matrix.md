# KhetSense AI — Research Paper Evidence Matrix

**Document Reference:** `KS-AUDIT-2026-EVIDENCE-MATRIX`  
**Project Title:** KhetSense AI: AI-Driven Crop Stress Detection and Multilingual Voice-Based Irrigation Advisory Using Satellite Remote Sensing  
**Author/Auditor:** Senior AI/ML Researcher & Testing Lead  
**Date:** October 21, 2026  
**Repository Working Baseline:** Commit `e466026` + Phase 8 ML-Primary Architecture (401 Automated Unit/Integration Tests Passing)  
**Destination:** `reports/project_audit/KhetSense_AI_Research_Evidence_Matrix.md`  

---

## 1. Evidence Matrix Overview & Protocol

This matrix provides a rigorous, publication-grade audit trail connecting every factual claim proposed for an academic research paper or university thesis to underlying repository evidence. Every claim is assigned a formal verification category:

- **Verified from source code:** The algorithmic logic, equation, or control flow exists and is directly traceable in active production Python source code.
- **Verified from evaluation artifact:** The numerical value, confusion matrix, or metric is verifiable from persistent, reproducible evaluation JSON, CSV, or model checkpoint files.
- **Verified by executed test:** The capability has been executed and passed within the 401-test automated test suite in the local environment.
- **Reported but not independently verified:** The metric or statement was documented in an upstream project report or external documentation but lacks automated verification scripts.
- **Simulated or mocked:** The component operates against synthetic, in-memory, or mocked interfaces (e.g., mock WhatsApp Cloud API or mock TTS audio synthesis) rather than live production endpoints.
- **Unsupported / do not claim:** The assertion is unsupported by the current codebase, scientifically invalid, or disproven by empirical evidence.

---

## 2. Comprehensive Research Evidence Mapping

| Proposed Research-Paper Claim | Supporting Evidence | Source File / Artifact | Verification Method | Evidence Strength | Limitation or Scientific Qualification |
|---|---|---|---|---|---|
| **Zero-Hardware Ingestion Architecture** | Cloud API querying of ESA Sentinel-2 L2A optical reflectance and NASA SMAP microwave radiometry eliminates requirement for in-situ soil probes. | `pipeline/test_pipeline.py` (lines 410–560), `common/config.py` | Source code inspection & unit test execution | **Verified from source code** | Dependent on external cloud availability (Google Earth Engine, NASA CMR API); cloud cover $>20\%$ degrades optical observations. |
| **Sentinel-2 Surface Reflectance Scaling** | Digital Numbers (DN) scaled by $0.0001$ to normalize surface reflectance into $[0.0, 1.0]$ interval prior to non-linear index computation. | `pipeline/test_pipeline.py` (lines 425–445) | Source code inspection & mathematical audit | **Verified from source code** | Crucial for MSAVI square root stability; unscaled DN causes mathematical domain error in `sqrt`. |
| **Four Satellite Index Extraction** | Computes NDVI (B8, B4), NDWI (B8, B11 - Gao 1996), NDRE (B8, B5 - Barnes 2000), and MSAVI (B8, B4 - Qi 1994). | `pipeline/test_pipeline.py` (lines 430–458) | Automated test execution (`test_phase7e_live_s2_expansion.py`) | **Verified by executed test** | NDWI uses Band 11 (1610 nm SWIR liquid water), NOT Band 3 (McFeeters water body index). |
| **NASA SMAP 9km Microwave Soil Moisture** | Retrieves volumetric surface soil moisture ($0–5\text{ cm}$) from enhanced Level-3 radiometry product (`SPL3SMP_E`). | `pipeline/test_pipeline.py` (lines 460–560) | Unit tests with mocked HTTP responses | **Verified by executed test** | Spatial resolution ($9\text{ km} \times 9\text{ km}$) represents regional average moisture, not parcel-scale variability. |
| **Deterministic Rule-Based Stress Baseline** | Evaluates NDVI ($<0.30$ Severe, $0.30–0.60$ Mild, $>0.60$ No Stress) and SMAP ($<15\%$ Severe, $15–25\%$ Mild, $>25\%$ No Stress) using conservative worst-case ranking. | `pipeline/classifier.py` (lines 40–118) | Unit test execution (`test_phase8_ml_primary_advisory.py`) | **Verified by executed test** | Thresholds are heuristic expert agronomic rules; not empirically derived through soil-water sensor calibration. |
| **Rule Baseline Benchmark Performance** | Achieves 22.89% recall ($19/83$), 11.05% precision ($19/172$), and 0.3911 balanced accuracy on 1,513 spatial holdout records. | `reports/evaluation/model_comparison.csv`, `reports/evaluation/confusion_matrices.json` | Re-evaluated artifact inspection | **Verified from evaluation artifact** | Outperforms tuned 5-feature Random Forest on Severe Stress recall ($22.89\%$ vs $12.05\%$) on held-out districts. |
| **Rule Engine Inference Latency** | Baseline rule classification executes in 1.57 microseconds ($0.0016\text{ ms}$). | `reports/evaluation/model_comparison.csv` (line 2) | Benchmark script timing run | **Verified from evaluation artifact** | Approximately 16,000 times faster than Random Forest inference ($25.52\text{ ms}$). |
| **Two-Tier Rainfall Guardrail** | Short-term 48-hour forecast halts or defers irrigation advice: $R_1 = 5.0\text{ mm}$ (Hold & Monitor), $R_2 = 15.0\text{ mm}$ (Hold, Re-check After Rain). | `pipeline/classifier.py` (lines 120–180), `pipeline/test_pipeline.py` (lines 562–600) | Unit tests (`tests/test_phase6f_safety_remediation.py`) | **Verified by executed test** | Overrides Severe Stress irrigation advice; relies on OpenWeatherMap 3-hour forecast accuracy. |
| **Strict Spatial Holdout Dataset Split** | CSISA Eastern India Wheat Benchmark (7,648 records) split into 32 training districts (6,135 plots) and 8 test districts (1,513 plots) with zero district overlap. | `data/research_benchmark/train_live_native_models.py` (lines 145–165), `evaluation_manifest.json` | Script assertions & CSV partition check | **Verified from source code** | Prevents spatial autocorrelation leakage between training and testing plots. |
| **Live-Native 5-Feature ML Candidate** | Random Forest model trained strictly on 5 live-observable features (`s2_ndvi`, `s2_ndwi`, `s2_ndre`, `s2_msavi`, `smap_sm_pct`). | `data/research_benchmark/models/random_forest_5feat.joblib` | Model artifact inspection & unit tests | **Verified from evaluation artifact** | Eliminates ERA5 reanalysis lag; drops feature count from 9 to 5 to match live pipeline capabilities. |
| **Random Forest 5-Feature Evaluation** | Tuned severe threshold ($T = 0.27$) yields 12.05% recall ($10/83$), 6.37% precision ($10/157$), Macro-F1 0.2999, and Balanced Accuracy 0.3069. | `reports/evaluation/model_comparison.csv` (line 4) | Cross-checked against confusion matrix JSON | **Verified from evaluation artifact** | Severe precision is lower than rule baseline ($6.37\%$ vs $11.05\%$); generates 147 false alarms. |
| **HistGradientBoosting Severe Base-Rate Trap** | Optimizing threshold on OOF probabilities yields $T = 0.02$, achieving 72.29% recall but generating 1,274 false alarms on 1,513 samples (Precision: 4.50%). | `reports/evaluation/model_comparison.csv` (line 6), `reports/evaluation/confusion_matrices.json` | Independent mathematical audit | **Verified from evaluation artifact** | Pathological threshold failure: predicts Severe Stress for $88.2\%$ of all test samples; unsuitable for live use. |
| **Feature Importance Distribution** | NASA SMAP represents 45.37% of tree split weight; optical canopy indices represent 54.64% (`s2_ndwi` 15.67%, `s2_ndre` 13.50%, `s2_msavi` 12.99%, `s2_ndvi` 12.48%). | `data/research_benchmark/train_live_native_models.py` (lines 394–402), `reports/evaluation/evaluation_summary.md` | Model attribute inspection | **Verified from evaluation artifact** | Highlights microwave soil moisture as the single dominant continuous biophysical indicator. |
| **Phase 8 Primary ML Integration** | 5-feature Random Forest acts as active primary crop-stress predictor for supported Wheat crops, determining `observed_stress`. | `pipeline/test_pipeline.py` (lines 1450–1485), `pipeline/classifier.py` (lines 670–750) | Executed test suite (`test_phase8_ml_primary_advisory.py`) | **Verified by executed test** | Activated for academic prototype demonstration; preserves rule-based baseline for comparative logging. |
| **Unsupported Crop Fallback Guardrail** | Non-wheat crops (Cotton, Soybean) bypass ML inference (`UNSUPPORTED_CROP`) and route to rule-based fallback (`RULE_FALLBACK_UNSUPPORTED_CROP`). | `pipeline/ml_inference.py` (lines 720–740), `pipeline/classifier.py` (lines 690–710) | Automated test execution (`test_03_unsupported_crop_fallback`) | **Verified by executed test** | Prevents scientific misapplication of wheat-trained model to C4 crops or summer taproot crops. |
| **Missing Sensor Zero-Fabrication Policy** | If optical NDVI or microwave SMAP inputs are missing/non-finite, model rejects inference (`MISSING_INPUTS`) without fabricating numbers. | `pipeline/ml_inference.py` (lines 740–765), `pipeline/test_pipeline.py` | Automated test execution (`test_04_missing_sensor_rejection`) | **Verified by executed test** | System issues `ACTION_INSUFFICIENT_DATA`; never imputes synthetic values in live production path. |
| **Text and Spoken Voice Output Parity** | Multilingual WhatsApp cards and synthesized audio scripts share identical observed stress, recommended action, and rainfall metrics. | `whatsapp/messages.py` (lines 265–450) | Automated test execution (`test_06_text_voice_parity`) | **Verified by executed test** | Guaranteed identical agronomic advice across both visual text and auditory modalities. |
| **Agricultural Land-Cover Validation** | ESA WorldCover 10m global land cover screens GPS coordinates, confirming Class 40 (Cropland) and rejecting Class 50 (Built-up) or Class 60 (Barren). | `pipeline/location_validator.py` (lines 80–345) | Unit test execution (`test_multi_method_location.py`) | **Verified by executed test** | Prevents false crop stress alerts on concrete surfaces or urban infrastructure. |
| **Trilingual WhatsApp Onboarding** | Conversational state machine supports English, Marathi, and Hindi; parses GPS pins, Google Maps URLs, crop names, and acreage. | `whatsapp/registration_flow.py`, `whatsapp/messages.py` | Unit tests (`test_registration_flow.py`) & manual mobile verification | **Verified by executed test** | Full state transition coverage (115 tests in `test_registration_flow.py`). |
| **Edge-Synthesized Vernacular Voice Notes** | Generates native Marathi (`mr-IN-AarohiNeural`), Hindi (`hi-IN-SwaraNeural`), and English (`en-IN-NeerjaNeural`) Opus voice notes (`audio/ogg`). | `pipeline/tts_provider.py` (lines 1–485) | Unit tests (`test_voice_advisory.py`) | **Verified by executed test** | Uses `MockTTSProvider` by default in CI/CD; `EdgeTTSProvider` tested locally; eliminates technical jargon. |
| **Webhook Security & Replay Prevention** | HMAC-SHA256 signature verification on WhatsApp webhooks; 1MB payload size enforcement; processed message ID deduplication table. | `webhook_server.py`, `common/utils.py` | Automated test execution (`test_phase6h_security_remediation.py`) | **Verified by executed test** | Prevents spoofing, denial-of-service via unbounded streaming, and duplicate message triggers. |
| **Automated Software Test Suite** | 401 unit and integration tests passing in 44.33 seconds across 14 test modules with 0 failures and 0 errors. | `tests/` directory (14 test files) | Live test execution via `unittest discover` | **Verified by executed test** | Verifies software engineering correctness, state machine logic, and security guardrails. |
| **Validation on Maharashtra Smallholders** | Model validated on physical farms in Central Maharashtra (Marathwada/Vidarbha). | None | Repository audit | **Unsupported / do not claim** | Model trained strictly on Eastern India wheat (Bihar/Eastern UP); Maharashtra validation has NOT occurred. |
| **Calibrated Predictive Confidence** | Model output probabilities represent calibrated Bayesian certainty of true crop water stress. | None (Brier score or Platt scaling not implemented) | Codebase audit | **Unsupported / do not claim** | Probabilities are uncalibrated Random Forest tree vote fractions; not true posterior probabilities. |
| **Physiological Ground Truth Labels** | Survey labels reflect in-situ leaf water potential or stomatal conductance measurements. | CSISA dataset documentation | Dataset metadata inspection | **Unsupported / do not claim** | Target labels are retrospective farmer interview responses ("did your crop suffer moisture stress?"). |
| **Proven Yield Improvement or Water Savings** | KhetSense AI deployment increases wheat yield by 20% or saves 30% irrigation water in field trials. | None | Project audit | **Unsupported / do not claim** | No longitudinal randomized control field trials have been conducted; system is an academic prototype. |
| **Live Outbound WhatsApp Messaging** | System sends automated live WhatsApp messages to registered farmer phone numbers in production. | `common/config.py` (`ENABLE_OUTBOUND_WHATSAPP=false`) | Configuration audit | **Simulated or mocked** | Outbound WhatsApp messaging is strictly disabled by default; simulated in-memory for safety. |

---

## 3. Disallowed Claims for Academic Submissions

The following statements **MUST NOT** be made in any research paper or university defense presentation:

1. **"The machine learning model is ready for commercial deployment across India."**  
   *Correction:* The ML model is an experimental academic prototype trained on a single crop (wheat) in Eastern India. It has not been validated for other agro-climatic zones or soil types.
2. **"Our ML model outperforms traditional agronomic rules."**  
   *Correction:* On unseen held-out districts, the deterministic agronomic rule baseline achieves higher Severe Stress recall ($22.89\%$ vs $12.05\%$) and precision ($11.05\%$ vs $6.37\%$) than the live-native 5-feature Random Forest.
3. **"HistGradientBoosting achieves 72.29% severe stress accuracy."**  
   *Correction:* Chasing 72.29% recall via threshold tuning collapses precision to 4.50% and generates 1,274 false alarms on 1,513 test plots ($88.2\%$ false alert rate).
4. **"The model has been validated for Cotton, Soybean, and Pulses."**  
   *Correction:* The ML model is restricted exclusively to Wheat. Non-wheat crops are routed to deterministic rule-based fallbacks.
5. **"KhetSense AI provides parcel-level soil moisture measurements."**  
   *Correction:* While Sentinel-2 vegetation indices are parcel-scale ($10\text{ m}$), NASA SMAP radiometry provides regional-scale ($9\text{ km}$) surface soil moisture.
6. **"The target labels represent physical ground-truth soil moisture sensors."**  
   *Correction:* Labels represent retrospective post-harvest farmer recall surveys collected by the CSISA project in 2018.

---

## 4. Minimum Experimental Roadmap Prior to Journal Publication

Before submitting KhetSense AI to a peer-reviewed IEEE Transactions or Elsevier journal, the following empirical studies must be completed:

1. **Independent Agro-Climatic Validation:** Collect paired Sentinel-2, SMAP, and in-situ tensiometer/TDR soil moisture readings across at least 30 physical farm plots in Maharashtra over a full Rabi wheat season.
2. **Probability Calibration:** Implement Isotonic Regression or Platt Scaling on Out-Of-Fold probabilities and evaluate Expected Calibration Error (ECE) and Brier Score.
3. **Multi-Temporal Sequence Modeling:** Transition from single-date satellite snapshots to multi-temporal time-series architectures (e.g., Temporal Convolutional Networks or LSTMs) to capture dynamic crop drydown rates.
4. **Controlled Irrigation Water Savings Trial:** Conduct a micro-plot agronomic trial comparing KhetSense-guided irrigation vs. conventional flood irrigation to measure actual volumetric water conservation and grain yield impact.
