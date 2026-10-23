#!/usr/bin/env python3
"""
KhetSense AI — Phase 8: Primary Machine Learning Advisory Verification Test Suite
================================================================================
Verifies that the Live-Native Five-Feature Random Forest model acts as the PRIMARY
crop-stress predictor for the academic prototype:
1. Active advisory path executes 5-feature ML model and adopts its prediction.
2. Compatible input handling (5 live features only; zero seasonal precipitation substitution).
3. Crop domain scoping (Wheat supported; Cotton/Soybean explicitly flagged with rule-based fallback).
4. Missing sensor handling (rejection without data fabrication; explicit missing fields list).
5. Independent rainfall guardrail application (48h forecast applied to ML-predicted stress).
6. Parity and consistency between WhatsApp multilingual text cards and spoken voice scripts.
7. Transparent provenance: text card states AI/ML assessment source and includes prototype disclaimer.
8. Transparent fallback: rule-based fallback is explicitly labeled when used.
9. Probability disclosure: model probabilities disclosed without misrepresenting as calibrated confidence.
10. End-to-end active pipeline test: `run_pipeline_for_farm` invokes ML as primary authority.
"""

import os
import sys
import math
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Ensure user site packages are accessible for scikit-learn/joblib in Python 3.13
try:
    import site
    user_site = site.getusersitepackages()
    if user_site and os.path.exists(user_site) and user_site not in sys.path:
        sys.path.append(user_site)
except Exception:
    pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.ml_inference import (
    predict_crop_stress_5feat,
    load_ml_model_5feat,
    is_crop_supported_by_ml,
    FEATURE_NAMES_5FEAT,
    RF_5FEAT_SEVERE_THRESHOLD,
)
from pipeline.classifier import (
    primary_ml_stress_assessment,
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
from pipeline.test_pipeline import run_pipeline_for_farm


class TestPhase8MLPrimaryAdvisory(unittest.TestCase):
    """Test suite for Phase 8 primary ML crop-stress advisory integration."""

    @classmethod
    def setUpClass(cls):
        cls.models_dir = PROJECT_ROOT / "data" / "research_benchmark" / "models"
        is_avail, err = load_ml_model_5feat(force_reload=True, models_dir=cls.models_dir)
        if not is_avail:
            raise RuntimeError(f"5-Feature ML Model failed to load: {err}")

    # -------------------------------------------------------------------------
    # 1. Primary Authority: ML Prediction Adopted on Supported Crop (Wheat)
    # -------------------------------------------------------------------------
    def test_01_primary_ml_prediction_adopted(self):
        """Verify that ML model's prediction directly dictates active stress when crop is supported."""
        # Simulated sensor values where ML predicts Severe Stress
        ml_res = predict_crop_stress_5feat(
            crop_name="Wheat",
            s2_ndvi=0.49,
            s2_ndwi=0.07,
            s2_ndre=0.32,
            s2_msavi=0.25,
            smap_sm_pct=17.7,
            models_dir=self.models_dir,
        )
        self.assertEqual(ml_res["inference_status"], "SUCCESS")
        self.assertTrue(ml_res["crop_supported"])
        self.assertEqual(ml_res["predicted_class"], "Severe Stress")
        self.assertTrue(ml_res.get("is_primary"))

        # Rule baseline for comparison indicates Mild Stress (0.49 NDVI -> Mild, 17.7% SM -> Mild)
        rule_stress = "Mild Stress"

        final_stress, method, dis_flag, details = primary_ml_stress_assessment(
            rule_observed_stress=rule_stress,
            ml_result=ml_res,
            crop_name="Wheat",
            sm_pct=17.7,
            ndvi=0.49,
        )

        # ML prediction MUST be the primary authority!
        self.assertEqual(final_stress, "Severe Stress")
        self.assertEqual(method, "ML_PRIMARY_PREDICTOR")
        self.assertTrue(dis_flag)
        self.assertIn("Primary ML Model", details)
        self.assertIn("rule baseline comparison was 'Mild Stress'", details)

    # -------------------------------------------------------------------------
    # 2. Compatible Live Inputs Only (No Seasonal Precipitation Substitution)
    # -------------------------------------------------------------------------
    def test_02_compatible_live_inputs_only(self):
        """Verify that 5-feature inference uses strictly live optical and radiometry inputs."""
        self.assertEqual(FEATURE_NAMES_5FEAT, ["s2_ndvi", "s2_ndwi", "s2_ndre", "s2_msavi", "smap_sm_pct"])
        self.assertNotIn("era5_precip_season_mm", FEATURE_NAMES_5FEAT)

        ml_res = predict_crop_stress_5feat(
            crop_name="Wheat",
            s2_ndvi=0.62,
            s2_ndwi=0.22,
            s2_ndre=0.43,
            s2_msavi=0.36,
            smap_sm_pct=25.0,
            models_dir=self.models_dir,
        )
        self.assertEqual(set(ml_res["features_used"].keys()), set(FEATURE_NAMES_5FEAT))
        self.assertEqual(ml_res["features_used"]["s2_ndvi"], 0.62)
        self.assertEqual(ml_res["features_used"]["smap_sm_pct"], 25.0)

    # -------------------------------------------------------------------------
    # 3. Explicit Crop Scoping: Unsupported Crop Triggers Rule-Based Fallback
    # -------------------------------------------------------------------------
    def test_03_unsupported_crop_explicit_fallback(self):
        """Verify non-wheat crops (Cotton, Soybean) explicitly trigger rule-based fallback."""
        for crop in ["Cotton", "Soybean", "Sugarcane", "Chilli"]:
            ml_res = predict_crop_stress_5feat(
                crop_name=crop,
                s2_ndvi=0.55,
                s2_ndwi=0.15,
                s2_ndre=0.38,
                s2_msavi=0.30,
                smap_sm_pct=20.0,
                models_dir=self.models_dir,
            )
            self.assertEqual(ml_res["inference_status"], "UNSUPPORTED_CROP")
            self.assertFalse(ml_res["crop_supported"])

            final_stress, method, dis_flag, details = primary_ml_stress_assessment(
                rule_observed_stress="Mild Stress",
                ml_result=ml_res,
                crop_name=crop,
                sm_pct=20.0,
                ndvi=0.55,
            )
            self.assertEqual(final_stress, "Mild Stress")
            self.assertEqual(method, "RULE_FALLBACK_UNSUPPORTED_CROP")
            self.assertFalse(dis_flag)
            self.assertIn("not wheat", details)

    # -------------------------------------------------------------------------
    # 4. Missing Sensor Rejection: No Data Fabrication
    # -------------------------------------------------------------------------
    def test_04_missing_sensor_rejection_no_fabrication(self):
        """Verify that missing core sensors cause clean rejection with missing field list."""
        ml_res = predict_crop_stress_5feat(
            crop_name="Wheat",
            s2_ndvi=None,
            s2_ndwi=None,
            s2_ndre=None,
            s2_msavi=None,
            smap_sm_pct=None,
            models_dir=self.models_dir,
        )
        self.assertEqual(ml_res["inference_status"], "MISSING_INPUTS")
        self.assertIsNone(ml_res["predicted_class"])
        self.assertIn("s2_ndvi", ml_res["missing_inputs"])
        self.assertIn("smap_sm_pct", ml_res["missing_inputs"])

        final_stress, method, dis_flag, details = primary_ml_stress_assessment(
            rule_observed_stress="Unknown",
            ml_result=ml_res,
            crop_name="Wheat",
            sm_pct=None,
            ndvi=None,
        )
        self.assertEqual(final_stress, "Unknown")
        self.assertEqual(method, "RULE_FALLBACK_MISSING_INPUTS")
        self.assertIn("Required sensor inputs missing", details)

    # -------------------------------------------------------------------------
    # 5. Rainfall Guardrail Precedence Over ML-Predicted Stress
    # -------------------------------------------------------------------------
    def test_05_rainfall_guardrail_precedence(self):
        """Verify that rainfall forecast policy applies independently to ML-predicted stress."""
        # Case A: ML predicts Severe Stress, but heavy rain (18mm >= 15mm R2) is forecast
        ml_stress = "Severe Stress"
        stress_a, action_a, guardrail_a = apply_rainfall_guardrail(ml_stress, 18.0)
        self.assertEqual(stress_a, "Severe Stress")
        self.assertEqual(action_a, "hold, re-check after rain")
        self.assertTrue(guardrail_a)

        # Case B: ML predicts Severe Stress, moderate rain (8mm in R1..R2) is forecast
        stress_b, action_b, guardrail_b = apply_rainfall_guardrail(ml_stress, 8.0)
        self.assertEqual(action_b, "irrigate lightly, rain may not suffice")
        self.assertTrue(guardrail_b)

        # Case C: ML predicts Severe Stress, dry forecast (1mm < 5mm R1)
        stress_c, action_c, guardrail_c = apply_rainfall_guardrail(ml_stress, 1.0)
        self.assertEqual(action_c, "irrigate now")
        self.assertFalse(guardrail_c)

    # -------------------------------------------------------------------------
    # 6. Text and Voice Output Parity & Provenance Transparency
    # -------------------------------------------------------------------------
    def test_06_text_and_voice_parity_and_provenance(self):
        """Verify WhatsApp cards and voice scripts carry consistent stress, crop, and AI provenance."""
        ml_res = predict_crop_stress_5feat(
            crop_name="Wheat",
            s2_ndvi=0.49,
            s2_ndwi=0.07,
            s2_ndre=0.32,
            s2_msavi=0.25,
            smap_sm_pct=17.7,
            models_dir=self.models_dir,
        )
        farm = {"id": 88, "farmer_name": "Ramesh", "crop_name": "Wheat", "is_demo": True}
        adv = {
            "id": 999,
            "observation_date": "2026-10-21",
            "observed_stress": "Severe Stress",
            "recommended_action": "irrigate now",
            "rain_forecast_mm": 2.0,
            "crop_stage": "Flowering",
            "ml_inference": ml_res,
            "assessment_method": "ML_PRIMARY_PREDICTOR",
        }

        # English Text and Voice
        card_en = format_status_advisory(farm, adv, lang="en")
        script_en = format_voice_script(farm, adv, language="en")
        self.assertIn("Wheat", card_en)
        self.assertIn("Severe", card_en)
        self.assertIn("AI/ML Model (5-Feature Random Forest)", card_en)
        self.assertIn("Academic Prototype", card_en)
        self.assertIn("Model Probabilities", card_en)
        self.assertIn("KhetSense AI-generated irrigation advisory", script_en)
        self.assertIn("severe water stress", script_en)

        # Marathi Text and Voice
        card_mr = format_status_advisory(farm, adv, lang="mr")
        script_mr = format_voice_script(farm, adv, language="mr")
        self.assertIn("गहू", card_mr)
        self.assertIn("AI/ML मॉडेल", card_mr)
        self.assertIn("प्रायोगिक प्रोटोटाइप", card_mr)
        self.assertIn("खेतसेन्स AI द्वारे", script_mr)

        # Hindi Text and Voice
        card_hi = format_status_advisory(farm, adv, lang="hi")
        script_hi = format_voice_script(farm, adv, language="hi")
        self.assertIn("गेहूं", card_hi)
        self.assertIn("AI/ML मॉडल", card_hi)
        self.assertIn("अकादमिक प्रोटोटाइप", card_hi)
        self.assertIn("खेतसेंस AI द्वारा", script_hi)

    # -------------------------------------------------------------------------
    # 7. Explicit Rule-Based Fallback Transparency in Output
    # -------------------------------------------------------------------------
    def test_07_rule_fallback_explicit_in_output(self):
        """Verify that when fallback is used, text and voice state rule-based assessment."""
        farm_cotton = {"id": 89, "farmer_name": "Anil", "crop_name": "Cotton", "is_demo": True}
        adv_cotton = {
            "id": 1000,
            "observation_date": "2026-10-21",
            "observed_stress": "Mild Stress",
            "recommended_action": "schedule irrigation in 24-48h",
            "rain_forecast_mm": 0.0,
            "crop_stage": "Vegetative",
            "assessment_method": "RULE_FALLBACK_UNSUPPORTED_CROP",
        }
        card_en = format_status_advisory(farm_cotton, adv_cotton, lang="en")
        script_en = format_voice_script(farm_cotton, adv_cotton, language="en")
        self.assertIn("Rule-Based Expert Engine (Fallback)", card_en)
        self.assertIn("not supported by the wheat ML model", card_en)
        self.assertIn("KhetSense rule-based irrigation advisory", script_en)

    # -------------------------------------------------------------------------
    # 8. Uncalibrated Probability Disclosure (Not Claimed as Confidence)
    # -------------------------------------------------------------------------
    def test_08_probability_disclosure_semantics(self):
        """Verify that probabilities are labeled uncalibrated and not claimed as Bayesian confidence."""
        ml_res = predict_crop_stress_5feat(
            crop_name="Wheat",
            s2_ndvi=0.55,
            s2_ndwi=0.15,
            s2_ndre=0.38,
            s2_msavi=0.30,
            smap_sm_pct=22.0,
            models_dir=self.models_dir,
        )
        self.assertIn("uncalibrated_probability", ml_res)
        self.assertIn("disclaimer", ml_res)
        self.assertIn("Academic Prototype", ml_res["disclaimer"])
        self.assertIn("timestamp", ml_res)

    # -------------------------------------------------------------------------
    # 9. End-to-End Pipeline Execution with Primary ML Predictor
    # -------------------------------------------------------------------------
    @patch("pipeline.test_pipeline.save_advisory_to_database")
    @patch("pipeline.test_pipeline.fetch_openweather_forecast")
    @patch("pipeline.test_pipeline.fetch_smap_soil_moisture")
    @patch("pipeline.test_pipeline.fetch_sentinel2_indices")
    @patch("pipeline.test_pipeline.validate_agricultural_location")
    @patch("pipeline.test_pipeline.authenticate_earth_engine")
    @patch("pipeline.test_pipeline.ee")
    @patch("pipeline.test_pipeline.get_farm_from_database")
    def test_09_active_pipeline_end_to_end_ml_primary(
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
        """Verify run_pipeline_for_farm executes 5-feature ML as primary predictor for Wheat."""
        mock_get_farm.return_value = {
            "id": 55,
            "farmer_name": "Devendra",
            "crop_name": "Wheat",
            "mobile_number": "919988776655",
            "farm_area": 2.5,
            "preferred_language": "en",
            "ee_coords": [[77.0, 20.0], [77.01, 20.0], [77.01, 20.01], [77.0, 20.01], [77.0, 20.0]],
            "centroid_lat": 20.005,
            "centroid_lon": 77.005,
            "is_demo": True,
        }
        mock_loc_val.return_value = {
            "outcome": "SUITABLE_CROPLAND",
            "land_cover_class": "Cropland",
            "is_suitable_for_advisory": True,
        }
        # Provide 5 live features (ndvi, ndwi, ndre, msavi, smap) matching Severe Stress
        mock_s2.return_value = (
            0.49,
            0.07,
            {"date": "2026-10-21T10:00:00Z", "ndre": 0.32, "msavi": 0.25},
            None,
        )
        mock_smap.return_value = (17.7, {"date": "2026-10-21T10:00:00Z"}, None)
        mock_weather.return_value = (2.0, None)
        mock_save_adv.return_value = {
            "id": 888,
            "observation_date": "2026-10-21",
            "created_at": "2026-10-21T12:00:00Z",
        }

        mock_voice_sender = MagicMock(return_value={"status": "success", "media_id": "mock_voice_888"})
        res = run_pipeline_for_farm(
            farm_id=55,
            db_url="postgresql://mock",
            auto_send_advisory=False,
            outbound_voice_sender=mock_voice_sender,
            send_voice_advisory=False,
        )

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["assessment_method"], "ML_PRIMARY_PREDICTOR")
        self.assertEqual(res["observed_stress"], "Severe Stress")
        self.assertEqual(res["recommended_action"], "irrigate now")
        self.assertIsNotNone(res["ml_inference"])
        self.assertEqual(res["ml_inference"]["predicted_class"], "Severe Stress")
        self.assertEqual(res["ml_inference"]["features_used"]["s2_ndvi"], 0.49)
        self.assertEqual(res["ml_inference"]["features_used"]["s2_ndre"], 0.32)
        self.assertEqual(res["ml_inference"]["features_used"]["s2_msavi"], 0.25)
        self.assertEqual(res["ml_inference"]["features_used"]["smap_sm_pct"], 17.7)


if __name__ == "__main__":
    unittest.main()
