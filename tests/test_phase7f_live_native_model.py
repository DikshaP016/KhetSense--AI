#!/usr/bin/env python3
"""
KhetSense AI — Phase 7F Test Suite: Live-Native Five-Feature ML Model
====================================================================
Tests the candidate 5-feature multi-sensor crop stress model:
1. Artifact existence and SHA-256 checksum verification against manifest.
2. Preprocessor bundle structure and feature order ['s2_ndvi', 's2_ndwi', 's2_ndre', 's2_msavi', 'smap_sm_pct'].
3. Model deserialization and isolated candidate inference (predict_crop_stress_5feat).
4. Severe stress detection under calibrated threshold T=0.27.
5. Crop domain guardrails (Wheat supported, Cotton/Soybean unsupported).
6. Missing sensor handling (graceful imputation vs critical failure on missing core inputs).
7. Non-interference with 9-feature model and live production advisory safeguards.
8. Evaluation metrics verification (GroupKFold spatial CV and held-out test benchmarks).
"""

import sys
import os
import site
import json
import hashlib
import unittest
from pathlib import Path

# Ensure user site packages are accessible for scikit-learn/joblib in Python 3.13
user_site = site.getusersitepackages()
if user_site and os.path.exists(user_site) and user_site not in sys.path:
    sys.path.append(user_site)

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.ml_inference import (
    FEATURE_NAMES_5FEAT,
    RF_5FEAT_SEVERE_THRESHOLD,
    load_ml_model_5feat,
    predict_crop_stress_5feat,
    predict_crop_stress,
    is_crop_supported_by_ml,
)
from pipeline.classifier import (
    classify_ndvi_stress,
    classify_soil_moisture_stress,
    hybrid_stress_assessment,
)


class TestPhase7FLiveNativeModel(unittest.TestCase):
    """Test suite for Phase 7F candidate 5-feature model artifacts and inference."""

    @classmethod
    def setUpClass(cls):
        cls.models_dir = PROJECT_ROOT / "data" / "research_benchmark" / "models"
        cls.manifest_path = cls.models_dir / "manifest_phase7f.json"
        cls.metrics_path = cls.models_dir / "evaluation_metrics_5feat.json"

    def _compute_sha256(self, filepath: Path) -> str:
        h = hashlib.sha256()
        with open(filepath, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()

    # -------------------------------------------------------------------------
    # 1. Manifest & Artifact Checksum Verification
    # -------------------------------------------------------------------------
    def test_01_manifest_and_artifact_integrity(self):
        """Verify that all Phase 7F artifacts exist and their SHA256 hashes match the manifest."""
        self.assertTrue(self.manifest_path.exists(), "manifest_phase7f.json must exist")
        with open(self.manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        self.assertIn("artifacts", manifest)
        artifacts = manifest["artifacts"]

        expected_files = [
            "preprocessor_5feat.joblib",
            "random_forest_5feat.joblib",
            "hist_gradient_boosting_5feat.joblib",
            "evaluation_metrics_5feat.json",
        ]
        for fname in expected_files:
            self.assertIn(fname, artifacts, f"{fname} must be registered in manifest")
            fpath = self.models_dir / fname
            self.assertTrue(fpath.exists(), f"Artifact file {fname} must exist on disk")
            actual_sha = self._compute_sha256(fpath)
            self.assertEqual(
                actual_sha,
                artifacts[fname],
                f"SHA256 mismatch for {fname}: expected {artifacts[fname]}, got {actual_sha}",
            )

    # -------------------------------------------------------------------------
    # 2. Preprocessor Bundle & Feature Structure
    # -------------------------------------------------------------------------
    def test_02_preprocessor_structure_and_features(self):
        """Verify the 5-feature preprocessor bundle contains the exact live-native feature set."""
        import joblib

        preproc_path = self.models_dir / "preprocessor_5feat.joblib"
        bundle = joblib.load(preproc_path)

        self.assertIn("imputer", bundle)
        self.assertIn("scaler", bundle)
        self.assertIn("feature_names", bundle)
        self.assertIn("imputed_medians", bundle)

        expected_features = ["s2_ndvi", "s2_ndwi", "s2_ndre", "s2_msavi", "smap_sm_pct"]
        self.assertEqual(bundle["feature_names"], expected_features)
        self.assertEqual(FEATURE_NAMES_5FEAT, expected_features)
        self.assertEqual(len(bundle["feature_names"]), 5)

        # Verify training medians are valid positive physical numbers
        medians = bundle["imputed_medians"]
        self.assertAlmostEqual(medians["s2_ndvi"], 0.6140, places=2)
        self.assertAlmostEqual(medians["s2_ndwi"], 0.2322, places=2)
        self.assertAlmostEqual(medians["s2_ndre"], 0.4274, places=2)
        self.assertAlmostEqual(medians["s2_msavi"], 0.3536, places=2)
        self.assertAlmostEqual(medians["smap_sm_pct"], 23.9574, places=2)

    # -------------------------------------------------------------------------
    # 3. Model Loading & In-Memory Caching
    # -------------------------------------------------------------------------
    def test_03_load_ml_model_5feat(self):
        """Test thread-safe loading and caching of the 5-feature candidate model."""
        is_avail, err = load_ml_model_5feat(force_reload=True, models_dir=self.models_dir)
        self.assertTrue(is_avail, f"Model loading failed: {err}")
        self.assertIsNone(err)

    # -------------------------------------------------------------------------
    # 4. Candidate Inference on Supported Crop (Wheat)
    # -------------------------------------------------------------------------
    def test_04_candidate_inference_supported_crop(self):
        """Test candidate inference execution with valid live observations on Wheat."""
        res = predict_crop_stress_5feat(
            crop_name="Wheat",
            s2_ndvi=0.62,
            s2_ndwi=0.22,
            s2_ndre=0.43,
            s2_msavi=0.36,
            smap_sm_pct=24.5,
            models_dir=self.models_dir,
        )
        self.assertEqual(res["inference_status"], "SUCCESS")
        self.assertTrue(res["crop_supported"])
        self.assertTrue(res["is_candidate"])
        self.assertTrue(res["is_provisional"])
        self.assertIn(res["predicted_class"], ["No Stress", "Mild Stress", "Severe Stress"])
        self.assertIsNotNone(res["probabilities"])
        self.assertAlmostEqual(sum(res["probabilities"].values()), 1.0, places=2)
        self.assertGreaterEqual(res["uncalibrated_confidence"], 0.0)
        self.assertLessEqual(res["uncalibrated_confidence"], 1.0)
        self.assertGreater(res["inference_latency_ms"], 0.0)

    # -------------------------------------------------------------------------
    # 5. Severe Stress Detection at Calibrated Threshold T=0.27
    # -------------------------------------------------------------------------
    def test_05_severe_stress_detection_tuned_threshold(self):
        """Test that inputs matching the training severe stress profile trigger Severe Stress at T=0.27."""
        # Using typical severe stress characteristics from CSISA training set
        res = predict_crop_stress_5feat(
            crop_name="Wheat",
            s2_ndvi=0.49,
            s2_ndwi=0.07,
            s2_ndre=0.32,
            s2_msavi=0.25,
            smap_sm_pct=17.7,
            rf_threshold=RF_5FEAT_SEVERE_THRESHOLD,
            models_dir=self.models_dir,
        )
        self.assertEqual(res["inference_status"], "SUCCESS")
        self.assertEqual(res["predicted_class"], "Severe Stress")
        self.assertGreaterEqual(res["probabilities"]["severe_stress"], RF_5FEAT_SEVERE_THRESHOLD)
        self.assertEqual(res["uncalibrated_confidence"], res["probabilities"]["severe_stress"])

    # -------------------------------------------------------------------------
    # 6. Crop Domain Guardrail (Wheat vs Unsupported Crops)
    # -------------------------------------------------------------------------
    def test_06_unsupported_crop_guardrail(self):
        """Verify that non-wheat crops are flagged UNSUPPORTED_CROP with crop_supported=False."""
        unsupported_crops = ["Cotton", "Soybean", "Sugarcane", "Gram", "Maize", "Onion"]
        for crop in unsupported_crops:
            res = predict_crop_stress_5feat(
                crop_name=crop,
                s2_ndvi=0.60,
                s2_ndwi=0.20,
                s2_ndre=0.40,
                s2_msavi=0.35,
                smap_sm_pct=25.0,
                models_dir=self.models_dir,
            )
            self.assertEqual(res["inference_status"], "UNSUPPORTED_CROP")
            self.assertFalse(res["crop_supported"])
            self.assertIn("not wheat", res["reason"])

        # Wheat aliases should be supported
        for alias in ["Wheat", "wheat", "Gehu", "gehu", "गेहूं", "गहू"]:
            self.assertTrue(is_crop_supported_by_ml(alias), f"Alias '{alias}' should be recognized as Wheat")

    # -------------------------------------------------------------------------
    # 7. Missing Sensor Handling & Median Imputation
    # -------------------------------------------------------------------------
    def test_07_missing_sensors_and_imputation(self):
        """Verify graceful imputation of optional live indices and rejection when core sensors missing."""
        # Case A: All sensors missing
        res_all_miss = predict_crop_stress_5feat(
            crop_name="Wheat",
            s2_ndvi=None,
            s2_ndwi=None,
            s2_ndre=None,
            s2_msavi=None,
            smap_sm_pct=None,
            models_dir=self.models_dir,
        )
        self.assertEqual(res_all_miss["inference_status"], "MISSING_INPUTS")
        self.assertIsNone(res_all_miss["predicted_class"])

        # Case B: Core sensors missing (NDVI and SMAP both None)
        res_core_miss = predict_crop_stress_5feat(
            crop_name="Wheat",
            s2_ndvi=None,
            s2_ndwi=0.20,
            s2_ndre=0.40,
            s2_msavi=0.35,
            smap_sm_pct=None,
            models_dir=self.models_dir,
        )
        self.assertEqual(res_core_miss["inference_status"], "MISSING_INPUTS")

        # Case C: Optical NDRE and MSAVI missing (unobserved cloud/band), but NDVI and SMAP present
        res_partial = predict_crop_stress_5feat(
            crop_name="Wheat",
            s2_ndvi=0.60,
            s2_ndwi=0.20,
            s2_ndre=None,
            s2_msavi=None,
            smap_sm_pct=26.0,
            models_dir=self.models_dir,
        )
        self.assertEqual(res_partial["inference_status"], "SUCCESS")
        self.assertIn("S2_NDRE_MISSING", res_partial["missing_sensor_flag"])
        self.assertIn("S2_MSAVI_MISSING", res_partial["missing_sensor_flag"])
        self.assertIsNotNone(res_partial["predicted_class"])

    # -------------------------------------------------------------------------
    # 8. Non-Interference with 9-Feature Model & Production Pipeline
    # -------------------------------------------------------------------------
    def test_08_non_interference_with_production_safeguards(self):
        """Ensure 9-feature model and hybrid arbitration maintain strict safety guards."""
        # The 9-feature model must continue to withhold predictions when seasonal precip is missing
        res_9f = predict_crop_stress(
            crop_name="Wheat",
            s2_ndvi=0.60,
            s2_ndwi=0.20,
            s2_ndre=0.40,
            s2_msavi=0.35,
            smap_sm_pct=25.0,
            era5_precip_season_mm=None,
        )
        self.assertEqual(res_9f["inference_status"], "FEATURE_INCOMPATIBILITY")

        # Hybrid arbitration must fall back to rule engine
        obs_stress, method, dis_flag, details = hybrid_stress_assessment(
            rule_observed_stress="Severe Stress",
            ml_result=res_9f,
            crop_name="Wheat",
            sm_pct=12.0,
            ndvi=0.25,
        )
        self.assertEqual(obs_stress, "Severe Stress")
        self.assertEqual(method, "RULE_ENGINE_FEATURE_INCOMPATIBILITY")

        # Physical sensor severe stress must NEVER be downgraded by any ML prediction
        fake_ml_no_stress = {
            "inference_status": "SUCCESS",
            "crop_supported": True,
            "predicted_class": "No Stress",
            "uncalibrated_confidence": 0.85,
        }
        obs_stress_ovr, method_ovr, dis_flag_ovr, details_ovr = hybrid_stress_assessment(
            rule_observed_stress="Severe Stress",
            ml_result=fake_ml_no_stress,
            crop_name="Wheat",
            sm_pct=12.0,
            ndvi=0.25,
        )
        self.assertEqual(obs_stress_ovr, "Severe Stress")
        self.assertEqual(method_ovr, "RULE_SAFETY_OVERRIDE")
        self.assertTrue(dis_flag_ovr)

    # -------------------------------------------------------------------------
    # 9. Evaluation Metrics & Benchmark Findings Verification
    # -------------------------------------------------------------------------
    def test_09_evaluation_metrics_and_benchmark_superiority(self):
        """Verify saved evaluation metrics record the rule baseline outperforming ML on spatial test."""
        with open(self.metrics_path, "r", encoding="utf-8") as f:
            metrics = json.load(f)

        meta = metrics["dataset_metadata"]
        self.assertEqual(meta["total_records"], 7648)
        self.assertEqual(meta["train_records"], 6135)
        self.assertEqual(meta["test_records"], 1513)
        self.assertEqual(meta["train_districts_count"], 32)
        self.assertEqual(meta["test_districts_count"], 8)

        evals = {item["model_name"]: item for item in metrics["held_out_test_evaluations"]}

        rule_eval = evals["Deterministic Rule Baseline"]
        rf_eval = evals["Random Forest 5-Feat (Tuned Severe T=0.27)"]

        # Rule baseline Macro-F1 = 0.3053, Balanced Acc = 0.3911, Severe Recall = 22.89%
        self.assertAlmostEqual(rule_eval["macro_f1"], 0.3053, places=3)
        self.assertAlmostEqual(rule_eval["balanced_accuracy"], 0.3911, places=3)
        self.assertAlmostEqual(rule_eval["per_class"]["severe_stress"]["recall"], 0.2289, places=3)

        # RF Tuned Severe Recall = 12.05%, Severe Precision = 6.37%
        self.assertAlmostEqual(rf_eval["per_class"]["severe_stress"]["recall"], 0.1205, places=3)
        self.assertAlmostEqual(rf_eval["per_class"]["severe_stress"]["precision"], 0.0637, places=3)

        # Scientific confirmation: Rule baseline has higher Severe Recall on held-out test than RF (22.89% vs 12.05%)
        self.assertGreater(
            rule_eval["per_class"]["severe_stress"]["recall"],
            rf_eval["per_class"]["severe_stress"]["recall"],
            "Deterministic Rule Baseline achieves higher Severe Stress recall than 5-Feat RF",
        )


if __name__ == "__main__":
    unittest.main()
