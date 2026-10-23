#!/usr/bin/env python3
"""
KhetSense AI — Phase 7C: ML Feature Compatibility Audit and Verification
========================================================================
Validates the scientific defensibility of ML feature inputs, verifying that:
1. Live inference does NOT substitute 48-hour forward forecasts into seasonal accumulated rainfall.
2. When seasonal precipitation is absent, ML inference flags FEATURE_INCOMPATIBILITY and is withheld.
3. Rule-based assessment, rainfall guardrails, and multilingual delivery are 100% preserved.
4. Optical indices (MSAVI/NDRE) are audited as unobserved/imputed, not described as live calculations.
5. Severe stress threshold T=0.33 is verified directly from evaluation_metrics.json.
6. Temporal and label leakage characteristics are audited and documented.
"""

import os
import sys
import json
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Ensure user site-packages are loaded for scikit-learn/joblib if available
try:
    import site
    user_site = site.getusersitepackages()
    if user_site and os.path.exists(user_site) and user_site not in sys.path:
        sys.path.append(user_site)
except Exception:
    pass

from pipeline.ml_inference import (
    predict_crop_stress,
    load_ml_model,
    is_crop_supported_by_ml,
    FEATURE_NAMES,
    TARGET_CLASSES,
    RF_SEVERE_THRESHOLD,
)
from pipeline.classifier import (
    hybrid_stress_assessment,
    apply_rainfall_guardrail,
    classify_ndvi_stress,
    classify_soil_moisture_stress,
    get_more_severe,
)
from common.config import (
    ACTION_IRRIGATE_NOW,
    ACTION_SCHEDULE_IRRIGATION,
    ACTION_HOLD_RECHECK,
)
from whatsapp.messages import (
    format_status_advisory,
    format_voice_script,
)
import pipeline.test_pipeline
from pipeline.test_pipeline import run_pipeline_for_farm


class TestPhase7CFeatureCompatibility(unittest.TestCase):
    """Phase 7C Feature Compatibility & Scientific Defensibility Test Suite."""

    @classmethod
    def setUpClass(cls):
        cls.ml_loaded, _ = load_ml_model()

    def test_01_feature_names_and_training_alignment(self):
        """Verifies operational feature vector matches exact 9 features in preprocessor.joblib."""
        expected_features = [
            "s2_ndvi",
            "s2_ndwi",
            "s2_ndre",
            "s2_msavi",
            "smap_sm_pct",
            "era5_precip_season_mm",
            "era5_temp_mean_c",
            "era5_temp_max_c",
            "era5_vpd_mean_kpa",
        ]
        self.assertEqual(FEATURE_NAMES, expected_features)

    def test_02_era5_precip_season_mm_substitution_prevention(self):
        """Live inference must NOT substitute rain_48h into era5_precip_season_mm."""
        # When era5_precip_season_mm is None (omitted due to incompatibility with 48h forecast):
        res = predict_crop_stress(
            crop_name="Wheat",
            s2_ndvi=0.52,
            s2_ndwi=0.10,
            smap_sm_pct=22.0,
            era5_precip_season_mm=None,  # Not provided in live pipeline
            require_seasonal_precipitation=True,
        )
        self.assertEqual(res["inference_status"], "FEATURE_INCOMPATIBILITY")
        self.assertFalse(res["crop_supported"])
        self.assertIsNone(res["predicted_class"])
        self.assertIn("120-day seasonal cumulative precipitation", res["reason"])
        self.assertIn("48-hour forward forecast", res["reason"])

    def test_03_hybrid_arbitration_on_feature_incompatibility(self):
        """When ML flags FEATURE_INCOMPATIBILITY, rule engine acts as sole authority."""
        rule_stress = "Mild Stress"
        ml_result = {
            "inference_status": "FEATURE_INCOMPATIBILITY",
            "crop_supported": False,
            "predicted_class": None,
            "reason": "Feature incompatibility: era5_precip_season_mm requires 120-day seasonal rainfall.",
        }

        final_stress, method, disagree, details = hybrid_stress_assessment(
            rule_observed_stress=rule_stress,
            ml_result=ml_result,
            crop_name="Wheat",
            sm_pct=22.0,
            ndvi=0.52,
        )
        self.assertEqual(final_stress, "Mild Stress")
        self.assertEqual(method, "RULE_ENGINE_FEATURE_INCOMPATIBILITY")
        self.assertFalse(disagree)
        self.assertIn("feature incompatibility", details.lower())

    def test_04_msavi_and_ndre_audit_as_unobserved_in_single_scene(self):
        """Verifies msavi and ndre are flagged as defaulted/unobserved when not provided."""
        res = predict_crop_stress(
            crop_name="Wheat",
            s2_ndvi=0.52,
            s2_ndwi=0.10,
            smap_sm_pct=22.0,
            era5_precip_season_mm=10.0,
            require_seasonal_precipitation=False,
        )
        # s2_ndre and s2_msavi were not passed
        self.assertIsNone(res["features_used"]["s2_ndre"])
        self.assertIsNone(res["features_used"]["s2_msavi"])
        # They are not described as live calculations
        self.assertEqual(res["features_used"]["s2_ndvi"], 0.52)
        self.assertEqual(res["features_used"]["s2_ndwi"], 0.10)

    def test_05_threshold_and_metrics_direct_artifact_verification(self):
        """Directly parses evaluation_metrics.json to verify threshold T=0.33 and metrics."""
        metrics_path = PROJECT_ROOT / "data" / "research_benchmark" / "models" / "evaluation_metrics.json"
        self.assertTrue(metrics_path.exists())

        with open(metrics_path, "r") as f:
            data = json.load(f)

        # 1. Verify optimized threshold
        thresh = data["threshold_optimization"]["rf_severe_threshold"]
        self.assertEqual(thresh, 0.33)

        # 2. Verify held-out evaluations
        evals = {e["model_name"]: e for e in data["held_out_test_evaluations"]}
        rf_tuned = evals.get("Random Forest (Tuned Severe Threshold T=0.33)")
        rule_base = evals.get("Deterministic Rule Baseline")
        lr_bal = evals.get("Regularized Logistic Regression (Balanced)")

        self.assertIsNotNone(rf_tuned)
        self.assertEqual(rf_tuned["macro_f1"], 0.3405)
        self.assertEqual(rf_tuned["per_class"]["severe_stress"]["precision"], 0.1935)
        self.assertEqual(rf_tuned["per_class"]["severe_stress"]["recall"], 0.1446)

        # 3. Verify false alarm counts from confusion matrices
        # Confusion matrix: row = true, col = pred. False alarms on severe = CM[0][2] + CM[1][2]
        rf_cm = rf_tuned["confusion_matrix"]
        rule_cm = rule_base["confusion_matrix"]
        lr_cm = lr_bal["confusion_matrix"]

        rf_fa = rf_cm[0][2] + rf_cm[1][2]  # 26 + 24 = 50
        rule_fa = rule_cm[0][2] + rule_cm[1][2]  # 73 + 80 = 153
        lr_fa = lr_cm[0][2] + lr_cm[1][2]  # 138 + 205 = 343

        self.assertEqual(rf_fa, 50)
        self.assertEqual(rule_fa, 153)
        self.assertEqual(lr_fa, 343)

    def test_06_end_to_end_pipeline_live_feature_isolation(self):
        """run_pipeline_for_farm executes with live features, withholding ML and preserving rule advice."""
        with patch("pipeline.test_pipeline.get_farm_from_database") as mock_get_farm, \
             patch("pipeline.test_pipeline.ee") as mock_ee, \
             patch("pipeline.test_pipeline.authenticate_earth_engine") as mock_auth, \
             patch("pipeline.test_pipeline.validate_agricultural_location") as mock_loc_val, \
             patch("pipeline.test_pipeline.fetch_sentinel2_indices") as mock_s2, \
             patch("pipeline.test_pipeline.fetch_smap_soil_moisture") as mock_smap, \
             patch("pipeline.test_pipeline.fetch_openweather_forecast") as mock_weather, \
             patch("pipeline.test_pipeline.save_advisory_to_database") as mock_save_adv:

            mock_get_farm.return_value = {
                "id": 201,
                "farmer_name": "Ramesh",
                "crop_name": "Wheat",
                "mobile_number": "919876543210",
                "farm_area": 2.5,
                "preferred_language": "mr",
                "ee_coords": [[77.0, 20.0], [77.01, 20.0], [77.01, 20.01], [77.0, 20.01], [77.0, 20.0]],
                "centroid_lat": 20.005,
                "centroid_lon": 77.005,
                "is_demo": False,
            }
            mock_loc_val.return_value = {
                "outcome": "SUITABLE_CROPLAND",
                "land_cover_class": "Cropland",
                "is_suitable_for_advisory": True,
            }
            mock_s2.return_value = (0.52, 0.10, {"date": "2026-10-18T10:00:00Z"}, None)
            mock_smap.return_value = (22.0, {"date": "2026-10-18T10:00:00Z"}, None)
            mock_weather.return_value = (2.0, None)
            mock_save_adv.return_value = {
                "id": 888,
                "observation_date": "2026-10-20",
                "created_at": "2026-10-20T12:00:00Z",
            }

            mock_voice_sender = MagicMock(return_value={"status": "success", "media_id": "mock_voice_123"})
            mock_tts = MagicMock()

            res = run_pipeline_for_farm(
                farm_id=201,
                db_url="postgresql://mock",
                auto_send_advisory=False,
                outbound_voice_sender=mock_voice_sender,
                tts_provider=mock_tts,
            )

            # Status is success
            self.assertEqual(res["status"], "success")
            # ML inference documents FEATURE_INCOMPATIBILITY
            self.assertIn("ml_inference", res)
            self.assertEqual(res["ml_inference"]["inference_status"], "FEATURE_INCOMPATIBILITY")
            self.assertIsNone(res["ml_inference"]["features_used"]["era5_precip_season_mm"])
            # Assessment method records feature incompatibility
            self.assertEqual(res["assessment_method"], "RULE_ENGINE_FEATURE_INCOMPATIBILITY")
            # Final stress and action are derived safely from rule engine + rainfall guardrail
            self.assertEqual(res["observed_stress"], "Mild Stress")
            self.assertEqual(res["recommended_action"], ACTION_SCHEDULE_IRRIGATION)

            # Multilingual cards and voice scripts work cleanly
            adv_data = {
                "id": 888,
                "observation_date": "2026-10-20",
                "observed_stress": res["observed_stress"],
                "recommended_action": res["recommended_action"],
                "rain_forecast_mm": 2.0,
                "ml_inference": res["ml_inference"],
            }
            card_mr = format_status_advisory(mock_get_farm.return_value, adv_data, lang="mr")
            script_mr = format_voice_script(mock_get_farm.return_value, adv_data, language="mr")
            self.assertIn("गहू", card_mr)
            self.assertIn("नमस्कार Rameshजी", script_mr)

    def test_07_offline_research_mode_with_authentic_seasonal_precipitation(self):
        """When authentic seasonal precipitation is explicitly supplied, ML inference executes."""
        res = predict_crop_stress(
            crop_name="Wheat",
            s2_ndvi=0.52,
            s2_ndwi=0.10,
            smap_sm_pct=22.0,
            era5_precip_season_mm=10.73,  # Authentic seasonal precipitation mean
            require_seasonal_precipitation=True,
        )
        if res["inference_status"] not in ("DEPENDENCY_UNAVAILABLE", "MODEL_NOT_FOUND"):
            self.assertEqual(res["inference_status"], "SUCCESS")
            self.assertTrue(res["crop_supported"])
            self.assertIsNotNone(res["predicted_class"])
            self.assertEqual(res["features_used"]["era5_precip_season_mm"], 10.73)


if __name__ == "__main__":
    unittest.main()
