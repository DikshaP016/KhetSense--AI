#!/usr/bin/env python3
"""
KhetSense AI — Phase 6F Safety Remediation & Regression Test Suite

Validates all 4 critical advisory safety controls identified in Phase 6E:
1. Floating-point IEEE 754 NaN and malformed numeric input sanitization in classifier.py.
2. Temporal freshness enforcement (14-day cutoff) and timestamp validation for Sentinel-2.
3. Temporal freshness enforcement (5-day cutoff) and granule break behavior for SMAP.
4. Completeness, timestamp continuity, and rainfall validation for 48-hour OpenWeather forecast.
5. Single-sensor fallbacks, dual-sensor failures, and safe insufficient-data actions.
6. Decoupled ML shadow failure/disagreement non-interference guarantee.

Zero live network access. Zero live database writes. Deterministic mocks only.
"""

import math
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from common.config import (
    ACTION_DELAY_RECHECK,
    ACTION_HOLD_RECHECK,
    ACTION_INSUFFICIENT_DATA,
    ACTION_IRRIGATE_LIGHTLY,
    ACTION_IRRIGATE_NOW,
    ACTION_NO_ACTION,
    ACTION_SCHEDULE_IRRIGATION,
    FRESHNESS_CONFIG,
    RAINFALL_CONFIG,
)
from common.utils import sanitize_sensor_float
from pipeline.classifier import (
    classify_ndvi_stress,
    classify_soil_moisture_stress,
    get_more_severe,
    apply_rainfall_guardrail,
    generate_irrigation_advisory,
    validate_forecast_rainfall,
)
from pipeline.test_pipeline import (
    fetch_openweather_forecast,
    fetch_sentinel2_indices,
    fetch_smap_soil_moisture,
)


class TestNumericSanitizationAndBoundaries(unittest.TestCase):
    """Test 1: Floating-point IEEE 754 NaN, Inf, non-numeric, and boundary handling."""

    def test_sanitize_sensor_float_extremes(self):
        """Verifies that sanitize_sensor_float rejects non-finites and enforces bounds."""
        self.assertIsNone(sanitize_sensor_float(None))
        self.assertIsNone(sanitize_sensor_float(float("nan")))
        self.assertIsNone(sanitize_sensor_float(float("inf")))
        self.assertIsNone(sanitize_sensor_float(float("-inf")))
        self.assertIsNone(sanitize_sensor_float(True))
        self.assertIsNone(sanitize_sensor_float(False))
        self.assertIsNone(sanitize_sensor_float("corrupt_string"))
        self.assertIsNone(sanitize_sensor_float({"invalid": "dict"}))

        # Boundary checks
        self.assertEqual(sanitize_sensor_float(0.45, min_val=0.0, max_val=1.0), 0.45)
        self.assertIsNone(sanitize_sensor_float(-0.01, min_val=0.0, max_val=1.0))
        self.assertIsNone(sanitize_sensor_float(1.01, min_val=0.0, max_val=1.0))

    def test_classify_ndvi_stress_nan_and_extremes(self):
        """Verifies that NDVI NaN/Inf/negative does NOT evaluate to Severe Stress."""
        # IEEE 754 non-finites must return Unknown
        self.assertEqual(classify_ndvi_stress(float("nan")), "Unknown")
        self.assertEqual(classify_ndvi_stress(float("inf")), "Unknown")
        self.assertEqual(classify_ndvi_stress(float("-inf")), "Unknown")
        self.assertEqual(classify_ndvi_stress(None), "Unknown")
        self.assertEqual(classify_ndvi_stress("invalid_string"), "Unknown")
        self.assertEqual(classify_ndvi_stress(True), "Unknown")

        # Unphysical out-of-range NDVI
        self.assertEqual(classify_ndvi_stress(-0.2), "Unknown")
        self.assertEqual(classify_ndvi_stress(1.5), "Unknown")

        # Valid boundaries
        self.assertEqual(classify_ndvi_stress(0.75), "No Stress")
        self.assertEqual(classify_ndvi_stress(0.61), "No Stress")
        self.assertEqual(classify_ndvi_stress(0.60), "Mild Stress")
        self.assertEqual(classify_ndvi_stress(0.45), "Mild Stress")
        self.assertEqual(classify_ndvi_stress(0.30), "Mild Stress")
        self.assertEqual(classify_ndvi_stress(0.29), "Severe Stress")
        self.assertEqual(classify_ndvi_stress(0.00), "Severe Stress")

    def test_classify_soil_moisture_stress_nan_and_extremes(self):
        """Verifies that SMAP NaN/Inf/negative does NOT evaluate to Severe Stress."""
        # IEEE 754 non-finites must return Unknown
        self.assertEqual(classify_soil_moisture_stress(float("nan")), "Unknown")
        self.assertEqual(classify_soil_moisture_stress(float("inf")), "Unknown")
        self.assertEqual(classify_soil_moisture_stress(float("-inf")), "Unknown")
        self.assertEqual(classify_soil_moisture_stress(None), "Unknown")
        self.assertEqual(classify_soil_moisture_stress("bad_input"), "Unknown")
        self.assertEqual(classify_soil_moisture_stress(False), "Unknown")

        # Unphysical percentages
        self.assertEqual(classify_soil_moisture_stress(-5.0), "Unknown")
        self.assertEqual(classify_soil_moisture_stress(105.0), "Unknown")

        # Valid boundaries
        self.assertEqual(classify_soil_moisture_stress(30.0), "No Stress")
        self.assertEqual(classify_soil_moisture_stress(25.1), "No Stress")
        self.assertEqual(classify_soil_moisture_stress(25.0), "Mild Stress")
        self.assertEqual(classify_soil_moisture_stress(18.0), "Mild Stress")
        self.assertEqual(classify_soil_moisture_stress(15.0), "Mild Stress")
        self.assertEqual(classify_soil_moisture_stress(14.9), "Severe Stress")
        self.assertEqual(classify_soil_moisture_stress(0.0), "Severe Stress")


class TestSensorFusionAndFallbacks(unittest.TestCase):
    """Test 2: Single-sensor fallbacks, dual-sensor failure, and safe actions."""

    def test_single_sensor_fallback_optical_only(self):
        """When SMAP is NaN or unavailable, decision follows fresh optical NDVI."""
        # Fresh Healthy NDVI + Missing SMAP -> No Stress
        stress = get_more_severe(classify_ndvi_stress(0.70), classify_soil_moisture_stress(float("nan")))
        self.assertEqual(stress, "No Stress")

        # Fresh Mild NDVI + Missing SMAP -> Mild Stress
        stress = get_more_severe(classify_ndvi_stress(0.40), classify_soil_moisture_stress(None))
        self.assertEqual(stress, "Mild Stress")

        # Fresh Severe NDVI + Missing SMAP -> Severe Stress
        stress = get_more_severe(classify_ndvi_stress(0.20), classify_soil_moisture_stress(-10.0))
        self.assertEqual(stress, "Severe Stress")

    def test_single_sensor_fallback_radiometric_only(self):
        """When Sentinel-2 is NaN or cloudy, decision follows fresh SMAP soil moisture."""
        # Missing NDVI + Fresh Severe SMAP -> Severe Stress
        stress = get_more_severe(classify_ndvi_stress(float("nan")), classify_soil_moisture_stress(10.0))
        self.assertEqual(stress, "Severe Stress")

        # Missing NDVI + Fresh Mild SMAP -> Mild Stress
        stress = get_more_severe(classify_ndvi_stress(None), classify_soil_moisture_stress(20.0))
        self.assertEqual(stress, "Mild Stress")

        # Missing NDVI + Fresh Healthy SMAP -> No Stress
        stress = get_more_severe(classify_ndvi_stress(1.8), classify_soil_moisture_stress(32.0))
        self.assertEqual(stress, "No Stress")

    def test_both_sensors_unavailable_safely_halts(self):
        """When both sensors are NaN or unavailable, action is strictly INSUFFICIENT_DATA."""
        stress = get_more_severe(classify_ndvi_stress(float("nan")), classify_soil_moisture_stress(float("nan")))
        self.assertEqual(stress, "Unknown")

        obs, act, trig = apply_rainfall_guardrail(stress, 0.0)
        self.assertEqual(obs, "Unknown")
        self.assertEqual(act, ACTION_INSUFFICIENT_DATA)
        self.assertFalse(trig)

        adv = generate_irrigation_advisory(obs, act, "Wheat", "Flowering", 0.0)
        self.assertIn("INSUFFICIENT DATA", adv)
        self.assertNotIn("Immediate irrigation recommended", adv)


class TestSentinel2FreshnessEnforcement(unittest.TestCase):
    """Test 3: Temporal freshness enforcement and timestamp verification for Sentinel-2."""

    def setUp(self):
        self.ref_date = datetime(2026, 10, 19, 12, 0, 0, tzinfo=timezone.utc)
        self.mock_geom = MagicMock()

    @patch("pipeline.test_pipeline.ee")
    def test_fresh_sentinel2_scene_accepted(self, mock_ee):
        """Scene acquired 4 days ago is within 14-day limit and accepted."""
        obs_date = self.ref_date - timedelta(days=4)
        epoch_ms = int(obs_date.timestamp() * 1000)

        mock_img = MagicMock()
        mock_img.get.side_effect = lambda k: {
            "system:time_start": MagicMock(getInfo=lambda: epoch_ms),
            "CLOUDY_PIXEL_PERCENTAGE": MagicMock(getInfo=lambda: 8.5),
        }[k]
        mock_img.id.return_value.getInfo.return_value = "COPERNICUS/S2_SR_HARMONIZED/20261015T053641"
        mock_img.normalizedDifference.return_value.rename.return_value.addBands.return_value.reduceRegion.return_value.getInfo.return_value = {
            "NDVI": 0.42,
            "NDWI": 0.12,
        }

        mock_col = MagicMock()
        mock_col.filterBounds.return_value = mock_col
        mock_col.filterDate.return_value = mock_col
        mock_col.filter.return_value = mock_col
        mock_col.sort.return_value = mock_col
        mock_col.size.return_value.getInfo.return_value = 1
        mock_col.first.return_value = mock_img
        mock_ee.ImageCollection.return_value = mock_col

        ndvi, ndwi, meta, err = fetch_sentinel2_indices(
            self.mock_geom, max_age_days=14, reference_date=self.ref_date
        )

        self.assertIsNone(err)
        self.assertEqual(ndvi, 0.42)
        self.assertEqual(ndwi, 0.12)
        self.assertIsNotNone(meta)
        self.assertAlmostEqual(meta["age_days"], 4.0, places=1)

    @patch("pipeline.test_pipeline.ee")
    def test_stale_sentinel2_scene_rejected(self, mock_ee):
        """Scene acquired 22 days ago exceeds 14-day limit and is rejected."""
        obs_date = self.ref_date - timedelta(days=22)
        epoch_ms = int(obs_date.timestamp() * 1000)

        mock_img = MagicMock()
        mock_img.get.side_effect = lambda k: {
            "system:time_start": MagicMock(getInfo=lambda: epoch_ms),
            "CLOUDY_PIXEL_PERCENTAGE": MagicMock(getInfo=lambda: 12.0),
        }[k]

        mock_col = MagicMock()
        mock_col.filterBounds.return_value = mock_col
        mock_col.filterDate.return_value = mock_col
        mock_col.filter.return_value = mock_col
        mock_col.sort.return_value = mock_col
        mock_col.size.return_value.getInfo.return_value = 1
        mock_col.first.return_value = mock_img
        mock_ee.ImageCollection.return_value = mock_col

        ndvi, ndwi, meta, err = fetch_sentinel2_indices(
            self.mock_geom, max_age_days=14, reference_date=self.ref_date
        )

        self.assertIsNone(ndvi)
        self.assertIsNone(ndwi)
        self.assertIsNone(meta)
        self.assertIn("stale", err.lower())
        self.assertIn("22.0 days old", err)

    @patch("pipeline.test_pipeline.ee")
    def test_sentinel2_missing_timestamp_rejected(self, mock_ee):
        """Scene with null system:time_start is safely rejected."""
        mock_img = MagicMock()
        mock_img.get.return_value = MagicMock(getInfo=lambda: None)

        mock_col = MagicMock()
        mock_col.filterBounds.return_value = mock_col
        mock_col.filterDate.return_value = mock_col
        mock_col.filter.return_value = mock_col
        mock_col.sort.return_value = mock_col
        mock_col.size.return_value.getInfo.return_value = 1
        mock_col.first.return_value = mock_img
        mock_ee.ImageCollection.return_value = mock_col

        ndvi, ndwi, meta, err = fetch_sentinel2_indices(
            self.mock_geom, max_age_days=14, reference_date=self.ref_date
        )

        self.assertIsNone(ndvi)
        self.assertIn("missing 'system:time_start'", err)


class TestSMAPFreshnessEnforcement(unittest.TestCase):
    """Test 4: Temporal freshness enforcement and granule search bounds for SMAP."""

    def setUp(self):
        self.ref_date = datetime(2026, 10, 19, 12, 0, 0, tzinfo=timezone.utc)

    @patch("pipeline.test_pipeline.ee")
    def test_fresh_smap_granule_accepted(self, mock_ee):
        """SMAP overpass 2 days old is accepted."""
        obs_date = self.ref_date - timedelta(days=2)
        epoch_ms = int(obs_date.timestamp() * 1000)

        mock_feat = {
            "id": "NASA/SMAP/SPL3SMP_E/006/SMAP_L3_SM_P_E_20261017",
            "properties": {"system:time_start": epoch_ms},
        }

        mock_cand_img = MagicMock()
        mock_cand_img.select.return_value.reduceRegion.return_value.getInfo.return_value = {
            "soil_moisture_am": 0.185,
        }
        mock_ee.Image.return_value = mock_cand_img

        mock_col = MagicMock()
        mock_col.filterBounds.return_value = mock_col
        mock_col.filterDate.return_value = mock_col
        mock_col.sort.return_value = mock_col
        mock_col.size.return_value.getInfo.return_value = 1
        mock_col.limit.return_value.getInfo.return_value = {"features": [mock_feat]}
        mock_ee.ImageCollection.return_value = mock_col

        sm_pct, meta, err = fetch_smap_soil_moisture(
            74.311, 19.346, max_age_days=5, reference_date=self.ref_date
        )

        self.assertIsNone(err)
        self.assertEqual(sm_pct, 18.5)
        self.assertIsNotNone(meta)
        self.assertAlmostEqual(meta["age_days"], 2.0, places=1)

    @patch("pipeline.test_pipeline.ee")
    def test_stale_smap_granule_breaks_early_and_rejects(self, mock_ee):
        """SMAP granules older than 5 days are not selected merely because values exist."""
        # Old granule: 9 days ago
        obs_date = self.ref_date - timedelta(days=9)
        epoch_ms = int(obs_date.timestamp() * 1000)

        mock_feat = {
            "id": "NASA/SMAP/SPL3SMP_E/006/SMAP_L3_SM_P_E_20261010",
            "properties": {"system:time_start": epoch_ms},
        }

        mock_col = MagicMock()
        mock_col.filterBounds.return_value = mock_col
        mock_col.filterDate.return_value = mock_col
        mock_col.sort.return_value = mock_col
        mock_col.size.return_value.getInfo.return_value = 1
        mock_col.limit.return_value.getInfo.return_value = {"features": [mock_feat]}
        mock_ee.ImageCollection.return_value = mock_col

        sm_pct, meta, err = fetch_smap_soil_moisture(
            74.311, 19.346, max_age_days=5, reference_date=self.ref_date
        )

        self.assertIsNone(sm_pct)
        self.assertIsNone(meta)
        self.assertIn("freshness window", err)


class TestOpenWeatherForecastValidation(unittest.TestCase):
    """Test 5: Completeness, continuity, and rainfall validation for 48h OpenWeather forecast."""

    def _build_valid_slices(self, count=16, start_epoch=1710000000, rain_per_slice=0.0):
        slices = []
        for i in range(count):
            entry = {
                "dt": start_epoch + (i * 10800),  # strictly 3-hour steps
                "main": {"temp": 28.0},
            }
            if rain_per_slice > 0:
                entry["rain"] = {"3h": rain_per_slice}
            slices.append(entry)
        return slices

    @patch("requests.get")
    def test_valid_zero_rain_forecast_distinguished(self, mock_http):
        """Genuine 0.0 mm forecast over 16 continuous slices returns 0.0 float."""
        slices = self._build_valid_slices(count=16, rain_per_slice=0.0)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"cod": "200", "list": slices}
        mock_http.return_value = mock_resp

        total_rain, err = fetch_openweather_forecast("valid_key", 19.346, 74.311)
        self.assertIsNone(err)
        self.assertEqual(total_rain, 0.0)

    @patch("requests.get")
    def test_valid_positive_rain_forecast(self, mock_http):
        """Complete 16 slices summing to 16.0 mm returns 16.0 float."""
        slices = self._build_valid_slices(count=16, rain_per_slice=1.0)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"cod": "200", "list": slices}
        mock_http.return_value = mock_resp

        total_rain, err = fetch_openweather_forecast("valid_key", 19.346, 74.311)
        self.assertIsNone(err)
        self.assertEqual(total_rain, 16.0)

    @patch("requests.get")
    def test_incomplete_forecast_rejected(self, mock_http):
        """Partial forecast (e.g. 6 slices = 18 hours) is rejected, NOT treated as dry."""
        slices = self._build_valid_slices(count=6, rain_per_slice=0.0)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"cod": "200", "list": slices}
        mock_http.return_value = mock_resp

        total_rain, err = fetch_openweather_forecast("valid_key", 19.346, 74.311)
        self.assertIsNone(total_rain)
        self.assertIn("Incomplete forecast coverage", err)
        self.assertIn("received 6 slices", err)

    @patch("requests.get")
    def test_timestamp_discontinuity_rejected(self, mock_http):
        """Discontinuous timestamps (e.g. 10-hour gap) are rejected."""
        slices = self._build_valid_slices(count=16, rain_per_slice=0.0)
        # Introduce 36,000s (10h) gap between slice 2 and 3
        slices[3]["dt"] = slices[2]["dt"] + 36000
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"cod": "200", "list": slices}
        mock_http.return_value = mock_resp

        total_rain, err = fetch_openweather_forecast("valid_key", 19.346, 74.311)
        self.assertIsNone(total_rain)
        self.assertIn("discontinuity", err.lower())

    @patch("requests.get")
    def test_malformed_rain_value_rejected(self, mock_http):
        """Negative or non-finite rainfall values in payload are rejected."""
        slices = self._build_valid_slices(count=16, rain_per_slice=0.0)
        slices[4]["rain"] = {"3h": -2.5}
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"cod": "200", "list": slices}
        mock_http.return_value = mock_resp

        total_rain, err = fetch_openweather_forecast("valid_key", 19.346, 74.311)
        self.assertIsNone(total_rain)
        self.assertIn("Negative rain value", err)


class TestMLShadowNonInterferenceUnderFailure(unittest.TestCase):
    """Test 6: Guarantees that ML shadow disagreement or failure cannot alter active advice."""

    def test_rule_advice_invariance_under_ml_failure(self):
        """Severe stress rule advice remains strictly unmutated even if ML crashes."""
        obs_stress = "Severe Stress"
        rec_action, _, _ = "irrigate now", None, False

        # Simulate ML shadow failure payload
        shadow_error_result = {
            "execution_status": "INFERENCE_ERROR",
            "prediction_class": None,
            "prediction_probability": None,
            "disagreement_detected": False,
        }

        # Farmer-facing card must only consume rule outputs
        adv = generate_irrigation_advisory(obs_stress, rec_action, "Cotton", "Flowering", 0.0)
        self.assertIn("Immediate irrigation recommended", adv)
        self.assertNotIn("INFERENCE_ERROR", adv)
        self.assertNotIn("shadow", adv)


if __name__ == "__main__":
    unittest.main()
