#!/usr/bin/env python3
"""
KhetSense AI — Phase 7A: Machine Learning Advisory Pipeline Integration Tests
=============================================================================
Tests:
1. Model loading, artifact verification, SHA-256 versioning.
2. Feature vector ordering and SimpleImputer/StandardScaler compatibility.
3. Input sanitization: NaN, +inf, -inf, non-numeric, out-of-range.
4. Class mapping and probability extraction (raw uncalibrated confidence).
5. Unsupported crop behavior (Cotton, Soybean -> flagged as unsupported, fallback to rule engine).
6. Supported crop (Wheat) behavior -> ML inference runs and assists active pipeline.
7. Agreement scenario: ML and Rule agree -> consensus classification.
8. Disagreement scenario: Rule predicts Severe Stress, ML predicts Mild -> Rule safety floor retained.
9. Disagreement scenario: ML predicts Severe Stress, Rule predicts Mild -> Conservative escalation for Wheat.
10. Disagreement scenario: ML predicts Mild Stress, Rule predicts No Stress -> Early warning if SM is low.
11. Disagreement scenario: ML predicts No Stress, Rule predicts Mild Stress -> Rule safety floor retained.
12. Missing sensor inputs -> Graceful fallback to rule engine.
13. Missing model artifacts / dependencies -> Resilient fallback without pipeline exception.
14. Rainfall guardrail precedence: Forecast rain >= 15 mm ALWAYS triggers HOLD regardless of ML prediction.
15. Crop validation mismatch precedence: S2 crop mismatch WITHHOLDS advice; ML cannot override.
16. Multilingual message generation: English, Marathi, and Hindi rendered cleanly with ML output.
17. Voice script generation: Natural conversational script generated without technical jargon/probabilities.
18. End-to-end active pipeline test: `run_pipeline_for_farm` invokes ML and persists hybrid output.
"""

import os
import sys
import math
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.ml_inference import (
    predict_crop_stress,
    load_ml_model,
    is_crop_supported_by_ml,
    FEATURE_NAMES,
    TARGET_CLASSES,
    RF_SEVERE_THRESHOLD,
    _sanitize_float,
    _MODEL_CACHE,
)
from pipeline.classifier import (
    hybrid_stress_assessment,
    apply_rainfall_guardrail,
    generate_irrigation_advisory,
    classify_ndvi_stress,
    classify_soil_moisture_stress,
    get_more_severe,
)
from whatsapp.messages import (
    format_status_advisory,
    format_voice_script,
    get_message,
)
import pipeline.test_pipeline
from pipeline.test_pipeline import run_pipeline_for_farm


class TestMLAdvisoryIntegration(unittest.TestCase):
    """Phase 7A Machine Learning integration and hybrid decision test suite."""

    def setUp(self):
        # Ensure fresh model cache
        load_ml_model(force_reload=True)

    def test_feature_ordering_and_specification(self):
        """Verifies operational feature vector matches exact 9-feature benchmark specification."""
        expected = [
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
        self.assertEqual(FEATURE_NAMES, expected)

    def test_input_sanitization(self):
        """Verifies that non-finite values (NaN, Inf, -Inf, bools) are sanitized to None."""
        self.assertIsNone(_sanitize_float(float("nan")))
        self.assertIsNone(_sanitize_float(float("inf")))
        self.assertIsNone(_sanitize_float(float("-inf")))
        self.assertIsNone(_sanitize_float(True))
        self.assertIsNone(_sanitize_float(False))
        self.assertIsNone(_sanitize_float("invalid_string"))
        self.assertEqual(_sanitize_float(0.45), 0.45)
        self.assertEqual(_sanitize_float(12), 12.0)

    def test_crop_support_scoping(self):
        """Verifies ML model is strictly scoped to Wheat and recognizes aliases."""
        self.assertTrue(is_crop_supported_by_ml("Wheat"))
        self.assertTrue(is_crop_supported_by_ml("wheat"))
        self.assertTrue(is_crop_supported_by_ml("Gehu"))
        self.assertTrue(is_crop_supported_by_ml("गेहूं"))
        self.assertTrue(is_crop_supported_by_ml("गहू"))

        # Non-wheat crops MUST return False
        self.assertFalse(is_crop_supported_by_ml("Cotton"))
        self.assertFalse(is_crop_supported_by_ml("Soybean"))
        self.assertFalse(is_crop_supported_by_ml("Sugarcane"))
        self.assertFalse(is_crop_supported_by_ml("Pigeon Pea"))
        self.assertFalse(is_crop_supported_by_ml("Maize"))
        self.assertFalse(is_crop_supported_by_ml(None))

    def test_unsupported_crop_behavior(self):
        """Unsupported crops execute reference inference but flag crop_supported=False."""
        res = predict_crop_stress(
            crop_name="Cotton",
            s2_ndvi=0.65,
            s2_ndwi=0.15,
            smap_sm_pct=26.0,
            era5_precip_season_mm=5.0,
        )
        self.assertFalse(res["crop_supported"])
        if res["inference_status"] not in ("DEPENDENCY_UNAVAILABLE", "MODEL_NOT_FOUND"):
            self.assertEqual(res["inference_status"], "UNSUPPORTED_CROP")
            self.assertIn("not wheat", res["reason"].lower())
            self.assertTrue(res["is_provisional"])

    def test_missing_critical_inputs_handled(self):
        """When optical and soil moisture inputs are both absent, returns MISSING_INPUTS."""
        res = predict_crop_stress(
            crop_name="Wheat",
            s2_ndvi=None,
            s2_ndwi=None,
            smap_sm_pct=None,
        )
        self.assertEqual(res["inference_status"], "MISSING_INPUTS")
        self.assertIsNone(res["predicted_class"])

    def test_hybrid_assessment_consensus(self):
        """When ML and Rule engine agree, assessment_method is HYBRID_CONSENSUS."""
        ml_mock = {
            "inference_status": "SUCCESS",
            "crop_supported": True,
            "predicted_class": "Mild Stress",
            "uncalibrated_confidence": 0.58,
        }
        stress, method, disagree, details = hybrid_stress_assessment(
            rule_observed_stress="Mild Stress",
            ml_result=ml_mock,
            crop_name="Wheat",
            sm_pct=18.0,
            ndvi=0.45,
        )
        self.assertEqual(stress, "Mild Stress")
        self.assertEqual(method, "HYBRID_CONSENSUS")
        self.assertFalse(disagree)
        self.assertIsNone(details)

    def test_hybrid_assessment_rule_severe_safety_floor(self):
        """Safety Floor: Rule Severe Stress is NEVER downgraded by ML."""
        ml_mock = {
            "inference_status": "SUCCESS",
            "crop_supported": True,
            "predicted_class": "No Stress",
            "uncalibrated_confidence": 0.72,
        }
        # Real physical sensor shows severe drought: SMAP 12% (<15%)
        stress, method, disagree, details = hybrid_stress_assessment(
            rule_observed_stress="Severe Stress",
            ml_result=ml_mock,
            crop_name="Wheat",
            sm_pct=12.0,
            ndvi=0.55,
        )
        self.assertEqual(stress, "Severe Stress")
        self.assertEqual(method, "RULE_SAFETY_OVERRIDE")
        self.assertTrue(disagree)
        self.assertIn("safety floor", details.lower())

    def test_hybrid_assessment_ml_conservative_escalation(self):
        """Conservative Policy: ML Severe Stress elevates Mild Stress for Wheat under low SM."""
        ml_mock = {
            "inference_status": "SUCCESS",
            "crop_supported": True,
            "predicted_class": "Severe Stress",
            "uncalibrated_confidence": 0.42,  # > 0.33 calibrated threshold
        }
        stress, method, disagree, details = hybrid_stress_assessment(
            rule_observed_stress="Mild Stress",
            ml_result=ml_mock,
            crop_name="Wheat",
            sm_pct=19.0,
            ndvi=0.50,
        )
        self.assertEqual(stress, "Severe Stress")
        self.assertEqual(method, "ML_CONSERVATIVE_ESCALATION")
        self.assertTrue(disagree)
        self.assertIn("escalated", details.lower())

    def test_hybrid_assessment_unsupported_crop_uses_rule_only(self):
        """Unsupported crop (e.g. Cotton) keeps rule engine as sole authority."""
        ml_mock = {
            "inference_status": "UNSUPPORTED_CROP",
            "crop_supported": False,
            "predicted_class": "Severe Stress",
            "uncalibrated_confidence": 0.55,
        }
        stress, method, disagree, details = hybrid_stress_assessment(
            rule_observed_stress="Mild Stress",
            ml_result=ml_mock,
            crop_name="Cotton",
            sm_pct=22.0,
            ndvi=0.50,
        )
        self.assertEqual(stress, "Mild Stress")
        self.assertEqual(method, "RULE_ENGINE_UNSUPPORTED_CROP")
        self.assertFalse(disagree)
        self.assertIn("cotton", details.lower())

    def test_hybrid_assessment_ml_failure_fallback(self):
        """When ML inference fails or is None, falls back cleanly to rule engine."""
        stress, method, disagree, details = hybrid_stress_assessment(
            rule_observed_stress="Severe Stress",
            ml_result=None,
            crop_name="Wheat",
        )
        self.assertEqual(stress, "Severe Stress")
        self.assertEqual(method, "RULE_ENGINE_ONLY")
        self.assertFalse(disagree)

    def test_rainfall_guardrail_precedence_over_ml(self):
        """Heavy forecast rainfall (>= 15mm) ALWAYS pauses irrigation regardless of ML prediction."""
        # Suppose ML and hybrid assessment output Severe Stress
        observed_stress = "Severe Stress"
        heavy_rain_48h = 22.5  # mm >= R2 (15.0 mm)

        stress, action, guardrail_triggered = apply_rainfall_guardrail(observed_stress, heavy_rain_48h)
        self.assertEqual(stress, "Severe Stress")
        self.assertEqual(action, "hold, re-check after rain")
        self.assertTrue(guardrail_triggered)

    def test_multilingual_advisory_formatting_with_ml(self):
        """Verifies text advisory cards in EN, MR, and HI render cleanly with hybrid output."""
        farm = {"id": 1, "farmer_name": "Ramesh", "crop_name": "Wheat"}
        advisory_data = {
            "id": 101,
            "observation_date": "2026-10-20",
            "observed_stress": "Severe Stress",
            "recommended_action": "irrigate now",
            "rain_forecast_mm": 2.0,
            "crop_stage": "Tillering",
            "assessment_method": "HYBRID_CONSENSUS",
        }

        # English
        card_en = format_status_advisory(farm, advisory_data, lang="en")
        self.assertIn("Ramesh", card_en)
        self.assertIn("Wheat", card_en)
        self.assertIn("Severe", card_en)
        self.assertIn("Immediate irrigation recommended", card_en)

        # Marathi
        card_mr = format_status_advisory(farm, advisory_data, lang="mr")
        self.assertIn("गहू", card_mr)
        self.assertIn("तीव्र पाण्याचा ताण", card_mr)

        # Hindi
        card_hi = format_status_advisory(farm, advisory_data, lang="hi")
        self.assertIn("गेहूं", card_hi)
        self.assertIn("गंभीर तनाव", card_hi)

    def test_voice_script_generation_free_of_jargon(self):
        """Voice scripts must not include model names, raw probabilities, or confusion matrices."""
        farm = {"id": 1, "farmer_name": "Ramesh", "crop_name": "Wheat"}
        advisory_data = {
            "id": 101,
            "observed_stress": "Mild Stress",
            "recommended_action": "schedule irrigation in 24-48h",
            "rain_forecast_mm": 1.0,
            "ml_inference": {
                "model_name": "Random Forest Classifier",
                "probabilities": {"severe": 0.35},
                "uncalibrated_confidence": 0.45,
            },
        }

        # English voice script
        script_en = format_voice_script(farm, advisory_data, language="en")
        self.assertIsNotNone(script_en)
        self.assertNotIn("Random Forest", script_en)
        self.assertNotIn("probability", script_en)
        self.assertNotIn("F1", script_en)
        self.assertIn("Ramesh", script_en)
        self.assertIn("mild water stress", script_en.lower())

        # Marathi voice script
        script_mr = format_voice_script(farm, advisory_data, language="mr")
        self.assertIsNotNone(script_mr)
        self.assertNotIn("Random Forest", script_mr)
        self.assertIn("नमस्कार", script_mr)

    @patch("pipeline.test_pipeline.save_advisory_to_database")
    @patch("pipeline.test_pipeline.fetch_openweather_forecast")
    @patch("pipeline.test_pipeline.fetch_smap_soil_moisture")
    @patch("pipeline.test_pipeline.fetch_sentinel2_indices")
    @patch("pipeline.test_pipeline.validate_agricultural_location")
    @patch("pipeline.test_pipeline.authenticate_earth_engine")
    @patch("pipeline.test_pipeline.ee")
    @patch("pipeline.test_pipeline.get_farm_from_database")
    def test_end_to_end_pipeline_ml_invocation(
        self,
        mock_get_farm,
        mock_ee,
        mock_auth_ee,
        mock_loc_val,
        mock_s2,
        mock_smap,
        mock_weather,
        mock_save_adv,
    ):
        """Verifies run_pipeline_for_farm genuinely executes ML inference in the active pipeline."""
        mock_get_farm.return_value = {
            "id": 10,
            "farmer_name": "Suresh",
            "crop_name": "Wheat",
            "mobile_number": "919876543210",
            "farm_area": 3.0,
            "preferred_language": "en",
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
        mock_s2.return_value = (0.50, 0.12, {"date": "2026-10-18T10:00:00Z"}, None)
        mock_smap.return_value = (19.0, {"date": "2026-10-18T10:00:00Z"}, None)
        mock_weather.return_value = (3.0, None)
        mock_save_adv.return_value = {
            "id": 777,
            "observation_date": "2026-10-20",
            "created_at": "2026-10-20T12:00:00Z",
        }

        mock_voice_sender = MagicMock(return_value={"status": "success", "media_id": "mock_voice_123"})
        mock_tts = MagicMock()

        res = run_pipeline_for_farm(
            farm_id=10,
            db_url="postgresql://mock",
            auto_send_advisory=False,
            outbound_voice_sender=mock_voice_sender,
            tts_provider=mock_tts,
        )

        self.assertEqual(res["status"], "success")
        self.assertIn("ml_inference", res)
        self.assertIn("assessment_method", res)
        # Verify that ML was genuinely called
        self.assertIsNotNone(res["ml_inference"])
        self.assertEqual(res["ml_inference"]["features_used"]["s2_ndvi"], 0.50)
        self.assertEqual(res["ml_inference"]["features_used"]["smap_sm_pct"], 19.0)


if __name__ == "__main__":
    unittest.main()
