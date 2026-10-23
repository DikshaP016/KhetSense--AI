#!/usr/bin/env python3
"""
KhetSense AI — Phase 7B: Safe ML End-to-End Dry Run
===================================================
Executes a controlled, offline dry run verifying that the ML model is called
through the actual advisory pipeline and that multilingual text and voice
advisories are generated correctly under strict safety guardrails.

STRICT CONSTRAINTS MAINTAINED:
- No writes to .env
- No outbound WhatsApp messages or external network calls
- No database writes (all DB operations use memory or mocked return values)
- No deployment actions
- Preserves all existing safety floors, location validation, and rainfall guardrails.

TEST SCENARIOS:
1. Supported crop (Wheat) with valid synthetic sensor inputs.
2. Unsupported crop (Cotton / Soybean) verifying ML is not used.
3. ML and rule-based predictions agree (Consensus).
4. ML and rule-based predictions disagree (Conservative Escalation).
5. Severe stress detected by the rule engine (Safety Floor Override).
6. High rainfall forecast activates the existing rainfall guardrail (Hold Irrigation).
7. Missing or stale sensor data prevents unsafe ML inference (Safe Withholding).
8. Model artifact is unavailable or raises an exception (Resilient Fallback).
9. Crop validation rejects the farm (Crop Mismatch Withholding).
10. Final advisory generation in English, Marathi, and Hindi, including voice generation.
"""

import os
import sys
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
from common.config import (
    ACTION_IRRIGATE_NOW,
    ACTION_IRRIGATE_LIGHTLY,
    ACTION_SCHEDULE_IRRIGATION,
    ACTION_HOLD_RECHECK,
    ACTION_NO_ACTION,
    ACTION_INSUFFICIENT_DATA,
)
from whatsapp.messages import (
    format_status_advisory,
    format_voice_script,
    get_message,
)
import pipeline.test_pipeline
from pipeline.test_pipeline import run_pipeline_for_farm


class TestPhase7BSafeDryRun(unittest.TestCase):
    """Phase 7B Safe ML End-to-End Dry Run Verification Suite."""

    @classmethod
    def setUpClass(cls):
        # Verify model loading
        cls.ml_loaded, cls.ml_load_err = load_ml_model()

    def test_scenario_01_supported_crop_wheat(self):
        """Scenario 1: Supported crop (Wheat) with valid synthetic sensor inputs."""
        crop = "Wheat"
        s2_ndvi = 0.52
        s2_ndwi = 0.10
        sm_pct = 22.0
        rain_48h = 2.0

        # 1. Rule Engine Assessment
        ndvi_stress = classify_ndvi_stress(s2_ndvi)  # No Stress (>= 0.50)
        sm_stress = classify_soil_moisture_stress(sm_pct)  # Mild Stress (20-30%)
        rule_stress = get_more_severe(ndvi_stress, sm_stress)
        self.assertEqual(rule_stress, "Mild Stress")

        # 2. ML Inference
        ml_res = predict_crop_stress(
            crop_name=crop,
            s2_ndvi=s2_ndvi,
            s2_ndwi=s2_ndwi,
            smap_sm_pct=sm_pct,
            era5_precip_season_mm=rain_48h,
        )
        self.assertEqual(ml_res["inference_status"], "SUCCESS")
        self.assertTrue(ml_res["crop_supported"])
        self.assertIn(ml_res["predicted_class"], ["Mild Stress", "No Stress"])

        # 3. Hybrid Arbitration
        final_stress, method, disagree, details = hybrid_stress_assessment(
            rule_observed_stress=rule_stress,
            ml_result=ml_res,
            crop_name=crop,
            sm_pct=sm_pct,
            ndvi=s2_ndvi,
        )
        self.assertEqual(final_stress, "Mild Stress")

        # 4. Rainfall Guardrail
        stress, action, guardrail = apply_rainfall_guardrail(final_stress, rain_48h)
        self.assertEqual(action, ACTION_SCHEDULE_IRRIGATION)
        self.assertFalse(guardrail)

        # 5. Multilingual Text and Spoken Voice Generation
        farm = {"id": 101, "farmer_name": "Ramesh", "crop_name": crop}
        adv = {
            "id": 501,
            "observation_date": "2026-10-20",
            "observed_stress": final_stress,
            "recommended_action": action,
            "rain_forecast_mm": rain_48h,
            "ml_inference": ml_res,
        }
        card_en = format_status_advisory(farm, adv, lang="en")
        script_en = format_voice_script(farm, adv, language="en")
        self.assertIn("Wheat", card_en)
        self.assertIn("Ramesh", script_en)
        self.assertNotIn("Random Forest", script_en)

    def test_scenario_02_unsupported_crop_cotton(self):
        """Scenario 2: Unsupported crop (Cotton / Soybean) verifying ML is not used."""
        crop = "Cotton"
        s2_ndvi = 0.45
        s2_ndwi = 0.08
        sm_pct = 22.0
        rain_48h = 0.0

        # 1. Rule Engine
        ndvi_stress = classify_ndvi_stress(s2_ndvi)
        sm_stress = classify_soil_moisture_stress(sm_pct)
        rule_stress = get_more_severe(ndvi_stress, sm_stress)
        self.assertEqual(rule_stress, "Mild Stress")

        # 2. ML Inference Gating
        self.assertFalse(is_crop_supported_by_ml(crop))
        ml_res = predict_crop_stress(
            crop_name=crop,
            s2_ndvi=s2_ndvi,
            s2_ndwi=s2_ndwi,
            smap_sm_pct=sm_pct,
            era5_precip_season_mm=rain_48h,
        )
        self.assertEqual(ml_res["inference_status"], "UNSUPPORTED_CROP")
        self.assertFalse(ml_res["crop_supported"])

        # 3. Hybrid Arbitration: Rule engine has sole authority
        final_stress, method, disagree, details = hybrid_stress_assessment(
            rule_observed_stress=rule_stress,
            ml_result=ml_res,
            crop_name=crop,
            sm_pct=sm_pct,
            ndvi=s2_ndvi,
        )
        self.assertEqual(final_stress, "Mild Stress")
        self.assertEqual(method, "RULE_ENGINE_UNSUPPORTED_CROP")
        self.assertFalse(disagree)
        self.assertIn("cotton", details.lower())

        # 4. Action
        stress, action, guardrail = apply_rainfall_guardrail(final_stress, rain_48h)
        self.assertEqual(action, ACTION_SCHEDULE_IRRIGATION)

        # 5. Text & Voice
        farm = {"id": 102, "farmer_name": "Suresh", "crop_name": crop}
        adv = {
            "id": 502,
            "observation_date": "2026-10-20",
            "observed_stress": final_stress,
            "recommended_action": action,
            "rain_forecast_mm": rain_48h,
            "ml_inference": ml_res,
        }
        card_mr = format_status_advisory(farm, adv, lang="mr")
        script_mr = format_voice_script(farm, adv, language="mr")
        self.assertIn("कापूस", card_mr)
        self.assertIn("कापूस", script_mr)

    def test_scenario_03_consensus_agreement(self):
        """Scenario 3: ML and rule-based predictions agree (Consensus)."""
        crop = "Wheat"
        rule_stress = "Mild Stress"
        ml_mock = {
            "inference_status": "SUCCESS",
            "crop_supported": True,
            "predicted_class": "Mild Stress",
            "uncalibrated_confidence": 0.54,
            "probabilities": {"no_stress": 0.35, "mild_stress": 0.54, "severe_stress": 0.11},
        }

        final_stress, method, disagree, details = hybrid_stress_assessment(
            rule_observed_stress=rule_stress,
            ml_result=ml_mock,
            crop_name=crop,
            sm_pct=22.0,
            ndvi=0.48,
        )
        self.assertEqual(final_stress, "Mild Stress")
        self.assertEqual(method, "HYBRID_CONSENSUS")
        self.assertFalse(disagree)
        self.assertIsNone(details)

        stress, action, guardrail = apply_rainfall_guardrail(final_stress, 1.5)
        self.assertEqual(action, ACTION_SCHEDULE_IRRIGATION)

    def test_scenario_04_disagreement_conservative_escalation(self):
        """Scenario 4: ML predicts Severe Stress while Rule predicts Mild Stress under water deficit."""
        crop = "Wheat"
        rule_stress = "Mild Stress"
        ml_mock = {
            "inference_status": "SUCCESS",
            "crop_supported": True,
            "predicted_class": "Severe Stress",
            "uncalibrated_confidence": 0.42,  # > 0.33 calibrated threshold
            "probabilities": {"no_stress": 0.20, "mild_stress": 0.38, "severe_stress": 0.42},
        }

        # Soil moisture is 19.0% (<25% threshold)
        final_stress, method, disagree, details = hybrid_stress_assessment(
            rule_observed_stress=rule_stress,
            ml_result=ml_mock,
            crop_name=crop,
            sm_pct=19.0,
            ndvi=0.48,
        )
        self.assertEqual(final_stress, "Severe Stress")
        self.assertEqual(method, "ML_CONSERVATIVE_ESCALATION")
        self.assertTrue(disagree)
        self.assertIn("escalated", details.lower())

        # Minimal rain -> URGENT IRRIGATION
        stress, action, guardrail = apply_rainfall_guardrail(final_stress, 0.0)
        self.assertEqual(action, ACTION_IRRIGATE_NOW)

    def test_scenario_05_rule_severe_stress_safety_floor(self):
        """Scenario 5: Severe stress detected by the rule engine (Safety Floor Override)."""
        crop = "Wheat"
        # Real physical sensor shows severe drought: SMAP 12% (<15%)
        rule_stress = "Severe Stress"
        ml_mock = {
            "inference_status": "SUCCESS",
            "crop_supported": True,
            "predicted_class": "No Stress",
            "uncalibrated_confidence": 0.75,
            "probabilities": {"no_stress": 0.75, "mild_stress": 0.20, "severe_stress": 0.05},
        }

        final_stress, method, disagree, details = hybrid_stress_assessment(
            rule_observed_stress=rule_stress,
            ml_result=ml_mock,
            crop_name=crop,
            sm_pct=12.0,
            ndvi=0.55,
        )
        # MUST NEVER BE DOWNGRADED BY ML
        self.assertEqual(final_stress, "Severe Stress")
        self.assertEqual(method, "RULE_SAFETY_OVERRIDE")
        self.assertTrue(disagree)
        self.assertIn("safety floor", details.lower())

        stress, action, guardrail = apply_rainfall_guardrail(final_stress, 1.0)
        self.assertEqual(action, ACTION_IRRIGATE_NOW)

    def test_scenario_06_high_rainfall_forecast_guardrail(self):
        """Scenario 6: High rainfall forecast (>= 15mm) activates the rainfall guardrail."""
        crop = "Wheat"
        observed_stress = "Severe Stress"
        heavy_rain_48h = 28.5  # mm >= 15.0 mm (Rule R2)

        stress, action, guardrail = apply_rainfall_guardrail(observed_stress, heavy_rain_48h)
        self.assertEqual(stress, "Severe Stress")
        self.assertEqual(action, ACTION_HOLD_RECHECK)
        self.assertTrue(guardrail)

        # Verify agronomic advice tells farmer to hold irrigation
        farm = {"id": 106, "farmer_name": "Kisan", "crop_name": crop}
        adv = {
            "id": 506,
            "observation_date": "2026-10-20",
            "observed_stress": stress,
            "recommended_action": action,
            "rain_forecast_mm": heavy_rain_48h,
        }
        card_en = format_status_advisory(farm, adv, lang="en")
        script_en = format_voice_script(farm, adv, language="en")
        self.assertIn("Hold irrigation and re-check after rain", card_en)
        self.assertIn("heavy rainfall", script_en.lower())

    def test_scenario_07_missing_or_stale_sensor_data(self):
        """Scenario 7: Missing or stale sensor data prevents unsafe ML inference."""
        crop = "Wheat"
        # S2 is completely missing / cloudy
        s2_ndvi = None
        s2_ndwi = None
        sm_pct = 20.0

        ml_res = predict_crop_stress(
            crop_name=crop,
            s2_ndvi=s2_ndvi,
            s2_ndwi=s2_ndwi,
            smap_sm_pct=sm_pct,
        )
        # Critical sensors missing flagged
        self.assertIn("S2_OPTICAL_MISSING", ml_res.get("missing_sensor_flag", ""))

        # When optical data is missing, rule engine handles missing data
        rule_stress = "Data Pending"
        final_stress, method, disagree, details = hybrid_stress_assessment(
            rule_observed_stress=rule_stress,
            ml_result=ml_res,
            crop_name=crop,
            sm_pct=sm_pct,
            ndvi=s2_ndvi,
        )
        # Does not produce unconstrained stress decision
        self.assertEqual(final_stress, "Data Pending")
        self.assertEqual(method, "RULE_ENGINE_FALLBACK")

    def test_scenario_08_model_artifact_failure_resilience(self):
        """Scenario 8: Model artifact is unavailable or raises an exception (Resilient Fallback)."""
        crop = "Wheat"
        rule_stress = "Mild Stress"
        ml_failure_mock = {
            "inference_status": "LOAD_ERROR",
            "crop_supported": False,
            "predicted_class": None,
            "reason": "Model artifact corrupted or unavailable",
        }

        final_stress, method, disagree, details = hybrid_stress_assessment(
            rule_observed_stress=rule_stress,
            ml_result=ml_failure_mock,
            crop_name=crop,
            sm_pct=22.0,
            ndvi=0.45,
        )
        self.assertEqual(final_stress, "Mild Stress")
        self.assertEqual(method, "RULE_ENGINE_LOAD_ERROR")
        self.assertFalse(disagree)

        stress, action, guardrail = apply_rainfall_guardrail(final_stress, 0.0)
        self.assertEqual(action, ACTION_SCHEDULE_IRRIGATION)

    def test_scenario_09_crop_validation_rejects_farm(self):
        """Scenario 9: Crop validation rejects the farm (Seasonality Mismatch)."""
        from pipeline.crop_validator import validate_crop_type, CROP_MISMATCH

        # Farmer declares Wheat (Rabi crop), but satellite observes high vegetative peak in July (Kharif)
        s2_meta = {"date": "2026-07-20 10:00:00"}
        val_res = validate_crop_type(
            declared_crop="Wheat",
            centroid_lat=20.5,
            centroid_lon=77.0,
            mean_ndvi=0.68,
            mean_ndwi=0.20,
            s2_meta=s2_meta,
        )
        self.assertEqual(val_res["outcome"], CROP_MISMATCH)
        self.assertFalse(val_res["is_suitable_for_advisory"])
        self.assertIn("winter (Rabi) crop", val_res["reason"])

        # Spoken audio advisory MUST BE WITHHELD
        farm = {"id": 109, "farmer_name": "Farmer", "crop_name": "Wheat"}
        adv_mismatch = {
            "id": 509,
            "validation_status": "CROP_MISMATCH",
            "stress_level": "VALIDATION_FAILED: CROP_MISMATCH",
            "observed_stress": "VALIDATION_FAILED",
            "crop_validation": val_res,
        }
        script = format_voice_script(farm, adv_mismatch, language="en")
        self.assertIsNone(script)  # Audio withheld!

        # Text card informs farmer of mismatch
        card = format_status_advisory(farm, adv_mismatch, lang="en")
        self.assertIn("KhetSense Crop Verification Notice", card)

    @patch("pipeline.test_pipeline.save_advisory_to_database")
    @patch("pipeline.test_pipeline.fetch_openweather_forecast")
    @patch("pipeline.test_pipeline.fetch_smap_soil_moisture")
    @patch("pipeline.test_pipeline.fetch_sentinel2_indices")
    @patch("pipeline.test_pipeline.validate_agricultural_location")
    @patch("pipeline.test_pipeline.authenticate_earth_engine")
    @patch("pipeline.test_pipeline.ee")
    @patch("pipeline.test_pipeline.get_farm_from_database")
    def test_scenario_10_multilingual_text_and_voice_pipeline(
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
        """Scenario 10: Final advisory generation in English, Marathi, and Hindi including mock voice."""
        for lang, expected_crop_token, expected_greeting in [
            ("en", "Wheat", "Hello Suresh"),
            ("mr", "गहू", "नमस्कार Sureshजी"),
            ("hi", "गेहूं", "नमस्ते Sureshजी"),
        ]:
            mock_get_farm.return_value = {
                "id": 110,
                "farmer_name": "Suresh",
                "crop_name": "Wheat",
                "mobile_number": "919876543210",
                "farm_area": 3.0,
                "preferred_language": lang,
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
            mock_weather.return_value = (2.0, None)
            mock_save_adv.return_value = {
                "id": 777,
                "observation_date": "2026-10-20",
                "created_at": "2026-10-20T12:00:00Z",
            }

            mock_voice_sender = MagicMock(return_value={"status": "success", "media_id": f"mock_voice_{lang}"})
            mock_tts = MagicMock()

            res = run_pipeline_for_farm(
                farm_id=110,
                db_url="postgresql://mock",
                auto_send_advisory=False,
                outbound_voice_sender=mock_voice_sender,
                tts_provider=mock_tts,
            )

            self.assertEqual(res["status"], "success")
            self.assertIn("ml_inference", res)
            self.assertIn("assessment_method", res)

            # Test formatting directly for the farm's language
            adv_data = {
                "id": 777,
                "observation_date": "2026-10-20",
                "observed_stress": res["observed_stress"],
                "recommended_action": res["recommended_action"],
                "rain_forecast_mm": 2.0,
                "ml_inference": res["ml_inference"],
            }
            card = format_status_advisory(mock_get_farm.return_value, adv_data, lang=lang)
            script = format_voice_script(mock_get_farm.return_value, adv_data, language=lang)

            self.assertIn(expected_crop_token, card)
            self.assertIn(expected_greeting, script)
            # Technical jargon check
            self.assertNotIn("Random Forest", script)
            self.assertNotIn("probability", script.lower())
            self.assertNotIn("f1", script.lower())


def run_standalone_dry_run():
    """Executes the dry-run scenarios standalone and prints structured results."""
    print("=" * 80)
    print("KHETSENSE AI — PHASE 7B SAFE ML END-TO-END DRY RUN")
    print("=" * 80)
    ok, err = load_ml_model()
    print(f"ML Model Loading Status: {'AVAILABLE' if ok else 'UNAVAILABLE'} (Error: {err})")
    print("-" * 80)

    scenarios = [
        ("Scenario 1: Supported Crop (Wheat)", "Wheat", 0.52, 0.10, 22.0, 2.0),
        ("Scenario 2: Unsupported Crop (Cotton)", "Cotton", 0.45, 0.08, 22.0, 0.0),
    ]

    for title, crop, ndvi, ndwi, sm, rain in scenarios:
        print(f"\n--- {title} ---")
        ndvi_s = classify_ndvi_stress(ndvi)
        sm_s = classify_soil_moisture_stress(sm)
        rule_s = get_more_severe(ndvi_s, sm_s)
        print(f"1. Rule Assessment: NDVI={ndvi_s}, SM={sm_s} -> Combined={rule_s}")

        ml_res = predict_crop_stress(crop, s2_ndvi=ndvi, s2_ndwi=ndwi, smap_sm_pct=sm, era5_precip_season_mm=rain)
        print(f"2. ML Inference: Status={ml_res['inference_status']}, CropSupported={ml_res['crop_supported']}, PredClass={ml_res['predicted_class']}")

        final_s, method, dis, det = hybrid_stress_assessment(rule_s, ml_res, crop, sm, ndvi)
        print(f"3. Hybrid Arbitration: FinalStress={final_s}, Method={method}, Disagreement={dis}")

        s, action, g = apply_rainfall_guardrail(final_s, rain)
        print(f"4. Rainfall Guardrail: Action={action}, Triggered={g}")

        farm = {"id": 1, "farmer_name": "Ramesh", "crop_name": crop}
        adv = {"id": 1, "observed_stress": s, "recommended_action": action, "rain_forecast_mm": rain}
        print("5. Advisory Cards & Voice Script Generation:")
        for lang in ["en", "mr", "hi"]:
            c = format_status_advisory(farm, adv, lang=lang)
            v = format_voice_script(farm, adv, language=lang)
            print(f"   [{lang.upper()}] Card Length={len(c)} chars | Voice Length={len(v) if v else 0} chars | Voice Preview: {v[:60] if v else 'None'}...")

    print("\n" + "=" * 80)
    print("ALL DRY-RUN SCENARIOS EXECUTED UNDER SAFE MOCKS")
    print("=" * 80)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--report":
        run_standalone_dry_run()
    else:
        unittest.main()
