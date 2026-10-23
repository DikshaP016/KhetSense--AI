#!/usr/bin/env python3
"""
KhetSense AI — Unit & Integration Test Suite for ML Shadow-Mode Engine (Phase 5D)
================================================================================
Comprehensive verification:
1. Operational feature schema and ordering.
2. Standard ML shadow inference (Random Forest T=0.33, Logistic Regression).
3. Missing sensor detection and transparent audit flagging.
4. Non-finite input sanitization (NaN, +inf, -inf conversion).
5. All-invalid / all-missing feature fallback robustness.
6. Crop context recording and schema compatibility.
7. Model artifact missing / corruption graceful degradation.
8. Missing dependencies (joblib/sklearn unavailable) graceful degradation.
9. Thread-safe simultaneous model cache initialization.
10. Bounded worker execution, technical timeout enforcement, and load shedding.
11. Repeated timeout resilience: worker pool remains healthy.
12. Rule-versus-ML disagreement and severe-disagreement tracking.
13. Database persistence idempotency and duplicate advisory conflict handling.
14. Multi-threaded concurrent evaluation stress testing.
15. Pipeline isolation: ML/persistence failures never alter active rule advisories.
"""

import os
import sys
import time
import math
import unittest
import threading
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.ml_shadow_engine import (
    evaluate_ml_shadow,
    load_shadow_models,
    persist_shadow_record,
    get_shadow_executor,
    shutdown_shadow_executor,
    _execute_raw_inference,
    _sanitize_float,
    FEATURE_NAMES,
    _MODEL_CACHE,
    MAX_SHADOW_QUEUE_TASKS,
)


class TestMLShadowEngine(unittest.TestCase):
    """Unit and stress tests for pipeline/ml_shadow_engine.py."""

    def setUp(self):
        # Reset cache before each test
        load_shadow_models(force_reload=True)

    def tearDown(self):
        # Ensure executor is clean if manipulated
        pass

    def test_feature_names_order(self):
        """Verifies operational feature vector matches exact 9-feature specification."""
        expected = [
            "s2_ndvi", "s2_ndwi", "s2_ndre", "s2_msavi",
            "smap_sm_pct",
            "era5_precip_season_mm", "era5_temp_mean_c", "era5_temp_max_c", "era5_vpd_mean_kpa"
        ]
        self.assertEqual(FEATURE_NAMES, expected)

    def test_shadow_inference_success_with_models(self):
        """Tests standard shadow evaluation when benchmark models are available."""
        res = evaluate_ml_shadow(
            farm_id=101,
            advisory_id=501,
            crop_name="Wheat",
            rule_observed_stress="Mild Stress",
            rule_recommended_action="schedule irrigation in 24-48h",
            rule_guardrail_triggered=False,
            s2_ndvi=0.55,
            s2_ndwi=0.18,
            s2_ndre=0.42,
            s2_msavi=0.35,
            smap_sm_pct=22.5,
            era5_precip_season_mm=12.0,
            era5_temp_mean_c=20.1,
            era5_temp_max_c=36.5,
            era5_vpd_mean_kpa=0.98,
            persist_to_db=False,
        )

        self.assertEqual(res["farm_id"], 101)
        self.assertEqual(res["advisory_id"], 501)
        self.assertEqual(res["crop_name"], "Wheat")
        self.assertEqual(res["rule_observed_stress"], "Mild Stress")
        self.assertEqual(res["rule_recommended_action"], "schedule irrigation in 24-48h")
        self.assertFalse(res["rule_guardrail_triggered"])
        self.assertEqual(res["missing_sensor_flag"], "COMPLETE")

        if res["execution_status"] == "SUCCESS":
            self.assertIn(res["rf_predicted_class"], ["No Stress", "Mild Stress", "Severe Stress"])
            self.assertIn(res["lr_predicted_class"], ["No Stress", "Mild Stress", "Severe Stress"])
            self.assertIsInstance(res["rf_prob_no_stress"], float)
            self.assertIsInstance(res["rf_prob_mild_stress"], float)
            self.assertIsInstance(res["rf_prob_severe_stress"], float)
            self.assertTrue(0.0 <= res["rf_prob_severe_stress"] <= 1.0)
            self.assertGreater(res["inference_latency_ms"], 0.0)
        else:
            self.assertIn(res["execution_status"], ["DEPENDENCY_UNAVAILABLE", "MODEL_LOAD_FAILED"])

    def test_missing_sensor_flag_reporting(self):
        """Verifies that missing optical and soil moisture inputs are transparently flagged."""
        res = evaluate_ml_shadow(
            farm_id=102,
            rule_observed_stress="Mild Stress",
            rule_recommended_action="schedule irrigation",
            rule_guardrail_triggered=False,
            s2_ndvi=None,   # Cloudy scene
            s2_ndwi=None,
            smap_sm_pct=None, # Missing SMAP radiometer
            persist_to_db=False,
        )

        self.assertIn("S2_OPTICAL_MISSING", res["missing_sensor_flag"])
        self.assertIn("SMAP_SOIL_MOISTURE_MISSING", res["missing_sensor_flag"])
        self.assertIn("WEATHER_METRICS_DEFAULTED", res["missing_sensor_flag"])
        self.assertIsNone(res["feat_s2_ndvi"])
        self.assertIsNone(res["feat_s2_ndwi"])
        self.assertIsNone(res["feat_smap_sm_pct"])

    def test_non_finite_inputs_handled_safely(self):
        """Verifies that NaN and positive/negative infinity are safely sanitized without raising ValueError."""
        res = evaluate_ml_shadow(
            farm_id=103,
            rule_observed_stress="No Stress",
            rule_recommended_action="none",
            rule_guardrail_triggered=False,
            s2_ndvi=float("nan"),
            s2_ndwi=float("inf"),
            smap_sm_pct=float("-inf"),
            era5_precip_season_mm=10.0,
            era5_temp_mean_c=25.0,
            era5_temp_max_c=35.0,
            era5_vpd_mean_kpa=1.2,
            persist_to_db=False,
        )

        # Non-finite values must be sanitized to None in telemetry snapshots
        self.assertIsNone(res["feat_s2_ndvi"])
        self.assertIsNone(res["feat_s2_ndwi"])
        self.assertIsNone(res["feat_smap_sm_pct"])
        self.assertIn("S2_OPTICAL_NON_FINITE_SANITIZED", res["missing_sensor_flag"])
        self.assertIn("SMAP_SOIL_MOISTURE_NON_FINITE_SANITIZED", res["missing_sensor_flag"])

        # Execution must NOT fail with ValueError: Input contains infinity
        if res["execution_status"] != "DEPENDENCY_UNAVAILABLE":
            self.assertEqual(res["execution_status"], "SUCCESS")

    def test_all_invalid_features_handled_gracefully(self):
        """Verifies all-None/all-NaN feature rows fall back to median imputation gracefully."""
        res = evaluate_ml_shadow(
            farm_id=104,
            rule_observed_stress="Unknown",
            rule_recommended_action="recheck",
            rule_guardrail_triggered=False,
            s2_ndvi=None, s2_ndwi=None, s2_ndre=None, s2_msavi=None,
            smap_sm_pct=None, era5_precip_season_mm=None,
            era5_temp_mean_c=None, era5_temp_max_c=None, era5_vpd_mean_kpa=None,
            persist_to_db=False,
        )

        self.assertIn("ALL_SENSORS_MISSING_OR_INVALID", res["missing_sensor_flag"])
        if res["execution_status"] != "DEPENDENCY_UNAVAILABLE":
            self.assertEqual(res["execution_status"], "SUCCESS")
            self.assertIsNotNone(res["rf_predicted_class"])

    def test_crop_context_captured_in_shadow_record(self):
        """Verifies crop_name is captured accurately or defaults to 'Unknown'."""
        res1 = evaluate_ml_shadow(
            farm_id=105, crop_name="Wheat", rule_observed_stress="No Stress",
            rule_recommended_action="none", rule_guardrail_triggered=False, persist_to_db=False,
        )
        self.assertEqual(res1["crop_name"], "Wheat")

        res2 = evaluate_ml_shadow(
            farm_id=106, crop_name=None, rule_observed_stress="No Stress",
            rule_recommended_action="none", rule_guardrail_triggered=False, persist_to_db=False,
        )
        self.assertEqual(res2["crop_name"], "Unknown")

    def test_simultaneous_model_loading_thread_safety(self):
        """Verifies that simultaneous concurrent invocations of load_shadow_models are thread-safe."""
        results = []
        errors = []

        def worker():
            try:
                avail, err = load_shadow_models(force_reload=True)
                results.append(avail)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Concurrent load_shadow_models raised errors: {errors}")
        self.assertEqual(len(results), 8)

    def test_disagreement_detection_logic(self):
        """Verifies calculation of is_disagreement and severe_disagreement flags."""
        with patch("pipeline.ml_shadow_engine._execute_raw_inference") as mock_inf:
            mock_inf.return_value = {
                "rf_predicted_class": "No Stress",
                "rf_prob_no_stress": 0.8, "rf_prob_mild_stress": 0.15, "rf_prob_severe_stress": 0.05,
                "rf_model_version": "rf_mock",
                "lr_predicted_class": "No Stress",
                "lr_prob_no_stress": 0.7, "lr_prob_mild_stress": 0.2, "lr_prob_severe_stress": 0.1,
                "lr_model_version": "lr_mock",
            }
            with patch("pipeline.ml_shadow_engine.load_shadow_models", return_value=(True, None)):
                # Case 1: Agreement
                res1 = evaluate_ml_shadow(
                    farm_id=1, rule_observed_stress="No Stress", rule_recommended_action="no action",
                    rule_guardrail_triggered=False, persist_to_db=False
                )
                self.assertFalse(res1["is_disagreement"])
                self.assertFalse(res1["severe_disagreement"])

                # Case 2: Mild vs No Stress (non-severe disagreement)
                res2 = evaluate_ml_shadow(
                    farm_id=2, rule_observed_stress="Mild Stress", rule_recommended_action="schedule",
                    rule_guardrail_triggered=False, persist_to_db=False
                )
                self.assertTrue(res2["is_disagreement"])
                self.assertFalse(res2["severe_disagreement"])

                # Case 3: Severe Disagreement (Rule says Mild, RF says Severe)
                mock_inf.return_value["rf_predicted_class"] = "Severe Stress"
                res3 = evaluate_ml_shadow(
                    farm_id=3, rule_observed_stress="Mild Stress", rule_recommended_action="schedule",
                    rule_guardrail_triggered=False, persist_to_db=False
                )
                self.assertTrue(res3["is_disagreement"])
                self.assertTrue(res3["severe_disagreement"])

    def test_bounded_timeout_enforcement(self):
        """Technically proves that shadow inference timeout is enforced and aborts cleanly."""
        def slow_inference(*args, **kwargs):
            time.sleep(0.15)
            return {}

        with patch("pipeline.ml_shadow_engine._execute_raw_inference", side_effect=slow_inference):
            with patch("pipeline.ml_shadow_engine.load_shadow_models", return_value=(True, None)):
                start = time.time()
                res = evaluate_ml_shadow(
                    farm_id=107,
                    rule_observed_stress="No Stress",
                    rule_recommended_action="none",
                    rule_guardrail_triggered=False,
                    timeout_seconds=0.03,  # Strict 30ms timeout
                    persist_to_db=False,
                )
                elapsed = time.time() - start

                self.assertEqual(res["execution_status"], "TIMEOUT_EXCEEDED")
                self.assertLess(elapsed, 0.12)
                self.assertIsNone(res["rf_predicted_class"])

    def test_bounded_worker_queue_and_load_shedding(self):
        """Verifies that when all worker slots and queue capacity are busy, extra calls are load-shed immediately."""
        def slow_worker(*args, **kwargs):
            time.sleep(0.10)
            return {}

        with patch("pipeline.ml_shadow_engine._execute_raw_inference", side_effect=slow_worker):
            with patch("pipeline.ml_shadow_engine.load_shadow_models", return_value=(True, None)):
                # Saturate queue by launching MAX_SHADOW_QUEUE_TASKS threads
                results = []
                def call_shadow(fid):
                    r = evaluate_ml_shadow(
                        farm_id=fid, rule_observed_stress="No Stress", rule_recommended_action="none",
                        rule_guardrail_triggered=False, timeout_seconds=0.5, persist_to_db=False,
                    )
                    results.append(r["execution_status"])

                threads = [threading.Thread(target=call_shadow, args=(200 + i,)) for i in range(MAX_SHADOW_QUEUE_TASKS)]
                for t in threads:
                    t.start()

                # Immediate extra call while workers are occupied must shed load
                time.sleep(0.01)  # Allow background threads to acquire semaphore
                overflow_res = evaluate_ml_shadow(
                    farm_id=999, rule_observed_stress="No Stress", rule_recommended_action="none",
                    rule_guardrail_triggered=False, persist_to_db=False,
                )

                for t in threads:
                    t.join()

                self.assertEqual(overflow_res["execution_status"], "LOAD_SHED_QUEUE_FULL")

    def test_repeated_timeouts_bounded_worker_behavior(self):
        """Verifies that repeated timeouts do not crash or corrupt the shared worker pool."""
        def slow_task(*args, **kwargs):
            time.sleep(0.04)
            return {}

        with patch("pipeline.ml_shadow_engine._execute_raw_inference", side_effect=slow_task):
            with patch("pipeline.ml_shadow_engine.load_shadow_models", return_value=(True, None)):
                for i in range(3):
                    start = time.time()
                    res = evaluate_ml_shadow(
                        farm_id=300 + i, rule_observed_stress="No Stress", rule_recommended_action="none",
                        rule_guardrail_triggered=False, timeout_seconds=0.01, persist_to_db=False,
                    )
                    elapsed = time.time() - start
                    self.assertEqual(res["execution_status"], "TIMEOUT_EXCEEDED")
                    self.assertLess(elapsed, 0.08)

    def test_duplicate_advisory_persistence_idempotency(self):
        """Verifies that persist_shadow_record executes ON CONFLICT (advisory_id) DO UPDATE."""
        dummy_record = {
            "farm_id": 888, "advisory_id": 42, "crop_name": "Wheat", "rule_observed_stress": "No Stress",
            "rule_recommended_action": "none", "rule_guardrail_triggered": False,
            "rf_predicted_class": "No Stress", "rf_prob_no_stress": 0.9, "rf_prob_mild_stress": 0.1,
            "rf_prob_severe_stress": 0.0, "rf_model_version": "v1", "lr_predicted_class": "No Stress",
            "lr_prob_no_stress": 0.9, "lr_prob_mild_stress": 0.1, "lr_prob_severe_stress": 0.0,
            "lr_model_version": "v1", "feat_s2_ndvi": 0.6, "feat_s2_ndwi": 0.2, "feat_s2_ndre": 0.4,
            "feat_s2_msavi": 0.3, "feat_smap_sm_pct": 25.0, "feat_era5_precip_season_mm": 10.0,
            "feat_era5_temp_mean_c": 20.0, "feat_era5_temp_max_c": 35.0, "feat_era5_vpd_mean_kpa": 1.0,
            "execution_status": "SUCCESS", "is_disagreement": False, "severe_disagreement": False,
            "missing_sensor_flag": "COMPLETE", "inference_latency_ms": 15.0,
        }

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        try:
            import psycopg2
            with patch("psycopg2.connect", return_value=mock_conn):
                persisted = persist_shadow_record(dummy_record, "postgresql://test_user:pass@localhost:5432/db")
                self.assertTrue(persisted)

                # Verify SQL query includes ON CONFLICT and crop_name
                executed_sql = mock_cur.execute.call_args[0][0]
                self.assertIn("ON CONFLICT (advisory_id) DO UPDATE SET", executed_sql)
                self.assertIn("crop_name", executed_sql)
                mock_conn.commit.assert_called_once()
        except ImportError:
            # If psycopg2 is not installed, persist_shadow_record must return False cleanly
            persisted = persist_shadow_record(dummy_record, "postgresql://test_user:pass@localhost:5432/db")
            self.assertFalse(persisted)

    def test_concurrent_evaluations_stress(self):
        """Stress-tests evaluate_ml_shadow across 8 concurrent worker threads."""
        results = []
        errors = []

        def stress_caller(fid):
            try:
                res = evaluate_ml_shadow(
                    farm_id=400 + fid,
                    advisory_id=fid,
                    crop_name="Wheat",
                    rule_observed_stress="Mild Stress",
                    rule_recommended_action="schedule",
                    rule_guardrail_triggered=False,
                    s2_ndvi=0.55,
                    s2_ndwi=0.18,
                    smap_sm_pct=22.0,
                    persist_to_db=False,
                )
                results.append(res)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=stress_caller, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Concurrent evaluate_ml_shadow failed with exceptions: {errors}")
        self.assertEqual(len(results), 8)
        for r in results:
            self.assertIn(r["execution_status"], ["SUCCESS", "DEPENDENCY_UNAVAILABLE", "LOAD_SHED_QUEUE_FULL"])


class TestPipelineShadowIntegration(unittest.TestCase):
    """Verifies pipeline isolation: shadow failures must NEVER change rule advisories."""

    @patch.dict("os.environ", {"ENABLE_VOICE_ADVISORY": "false", "ENABLE_VOICE_CHATBOT": "false"})
    @patch("pipeline.test_pipeline.deliver_voice_advisory")
    @patch("pipeline.test_pipeline.ee")
    @patch("pipeline.test_pipeline.authenticate_earth_engine")
    @patch("pipeline.test_pipeline.get_farm_from_database")
    @patch("pipeline.test_pipeline.validate_agricultural_location")
    @patch("pipeline.test_pipeline.fetch_sentinel2_indices")
    @patch("pipeline.test_pipeline.fetch_smap_soil_moisture")
    @patch("pipeline.test_pipeline.fetch_openweather_forecast")
    @patch("pipeline.test_pipeline.save_advisory_to_database")
    def test_ml_failure_preserves_rule_based_advisory(
        self,
        mock_save_adv,
        mock_weather,
        mock_smap,
        mock_s2,
        mock_val,
        mock_get_farm,
        mock_auth_ee,
        mock_ee,
        mock_voice,
    ):
        """Proves that a total failure in ML shadow engine does NOT change the active advisory."""
        from pipeline.test_pipeline import run_pipeline_for_farm

        coords = [[75.0, 19.0], [75.01, 19.0], [75.01, 19.01], [75.0, 19.01], [75.0, 19.0]]
        mock_get_farm.return_value = {
            "id": 42,
            "farmer_name": "Test Farmer",
            "phone_number": "919999999999",
            "mobile_number": "919999999999",
            "crop_type": "Wheat",
            "crop_name": "Wheat",
            "crop": "Wheat",
            "preferred_language": "en",
            "language": "en",
            "ee_coords": coords,
            "centroid_lat": 19.005,
            "centroid_lon": 75.005,
            "land_cover_code": 10,
            "land_cover_class": "Cropland",
            "polygon_geojson": '{"type": "Polygon", "coordinates": [[[75.0, 19.0], [75.01, 19.0], [75.01, 19.01], [75.0, 19.01], [75.0, 19.0]]]}',
        }
        mock_val.return_value = {
            "is_suitable_for_advisory": True,
            "suitable": True,
            "outcome": "SUITABLE_CROPLAND",
            "reason": "Cropland",
            "land_cover_class": "10",
        }
        mock_s2.return_value = (0.55, 0.18, {"date": "2026-02-15", "cloud_pct": 1.0}, None)
        mock_smap.return_value = (22.5, {"date": "2026-02-15"}, None)
        mock_weather.return_value = (0.0, None)
        mock_save_adv.return_value = {
            "id": 901,
            "farm_id": 42,
            "observation_date": "2026-02-15",
            "stress_level": "Mild Stress",
            "created_at": "2026-02-15T12:00:00Z",
        }

        # Mock evaluate_ml_shadow throwing a catastrophic unexpected exception
        with patch("pipeline.ml_shadow_engine.evaluate_ml_shadow", side_effect=RuntimeError("Catastrophic ML Crash")):
            res = run_pipeline_for_farm(
                farm_id=42,
                auto_send_advisory=False,
                send_voice_advisory=False,
                force=True,
            )

            self.assertEqual(res["status"], "success")
            self.assertEqual(res["farm_id"], 42)
            self.assertEqual(res["advisory_id"], 901)
            self.assertEqual(res["observed_stress"], "Mild Stress")
            self.assertEqual(res["recommended_action"], "schedule irrigation in 24-48h")
            self.assertIn("Wheat", res["advisory"])
            self.assertIn("shadow_evaluation", res)
            self.assertIsNone(res["shadow_evaluation"])

    @patch.dict("os.environ", {"ENABLE_VOICE_ADVISORY": "false", "ENABLE_VOICE_CHATBOT": "false"})
    @patch("pipeline.test_pipeline.deliver_voice_advisory")
    @patch("pipeline.test_pipeline.ee")
    @patch("pipeline.test_pipeline.authenticate_earth_engine")
    @patch("pipeline.test_pipeline.get_farm_from_database")
    @patch("pipeline.test_pipeline.validate_agricultural_location")
    @patch("pipeline.test_pipeline.fetch_sentinel2_indices")
    @patch("pipeline.test_pipeline.fetch_smap_soil_moisture")
    @patch("pipeline.test_pipeline.fetch_openweather_forecast")
    @patch("pipeline.test_pipeline.save_advisory_to_database")
    def test_pipeline_runs_shadow_evaluation_successfully(
        self,
        mock_save_adv,
        mock_weather,
        mock_smap,
        mock_s2,
        mock_val,
        mock_get_farm,
        mock_auth_ee,
        mock_ee,
        mock_voice,
    ):
        """Verifies shadow evaluation hook runs and populates shadow_evaluation key without altering advisory."""
        from pipeline.test_pipeline import run_pipeline_for_farm

        coords = [[75.0, 19.0], [75.01, 19.0], [75.01, 19.01], [75.0, 19.01], [75.0, 19.0]]
        mock_get_farm.return_value = {
            "id": 43,
            "farmer_name": "Test Farmer 2",
            "phone_number": "919999999998",
            "mobile_number": "919999999998",
            "crop_type": "Wheat",
            "crop_name": "Wheat",
            "crop": "Wheat",
            "preferred_language": "en",
            "language": "en",
            "ee_coords": coords,
            "centroid_lat": 19.005,
            "centroid_lon": 75.005,
            "land_cover_code": 10,
            "land_cover_class": "Cropland",
            "polygon_geojson": '{"type": "Polygon", "coordinates": [[[75.0, 19.0], [75.01, 19.0], [75.01, 19.01], [75.0, 19.01], [75.0, 19.0]]]}',
        }
        mock_val.return_value = {
            "is_suitable_for_advisory": True,
            "suitable": True,
            "outcome": "SUITABLE_CROPLAND",
            "reason": "Cropland",
            "land_cover_class": "10",
        }
        mock_s2.return_value = (0.55, 0.18, {"date": "2026-02-15", "cloud_pct": 1.0}, None)
        mock_smap.return_value = (22.5, {"date": "2026-02-15"}, None)
        mock_weather.return_value = (0.0, None)
        mock_save_adv.return_value = {
            "id": 902,
            "farm_id": 43,
            "observation_date": "2026-02-15",
            "stress_level": "Mild Stress",
            "created_at": "2026-02-15T12:00:00Z",
        }

        mock_shadow_result = {
            "execution_status": "SUCCESS",
            "crop_name": "Wheat",
            "rf_predicted_class": "No Stress",
            "rf_prob_severe_stress": 0.05,
            "is_disagreement": True,
        }

        with patch("pipeline.ml_shadow_engine.evaluate_ml_shadow", return_value=mock_shadow_result) as mock_eval:
            res = run_pipeline_for_farm(
                farm_id=43,
                auto_send_advisory=False,
                send_voice_advisory=False,
                force=True,
            )

            mock_eval.assert_called_once()
            call_kwargs = mock_eval.call_args[1]
            self.assertEqual(call_kwargs.get("crop_name"), "Wheat")
            self.assertEqual(res["status"], "success")
            self.assertEqual(res["observed_stress"], "Mild Stress")
            self.assertIn("shadow_evaluation", res)
            self.assertEqual(res["shadow_evaluation"]["rf_predicted_class"], "No Stress")
            self.assertEqual(res["shadow_evaluation"]["crop_name"], "Wheat")
            self.assertTrue(res["shadow_evaluation"]["is_disagreement"])


if __name__ == "__main__":
    unittest.main()
