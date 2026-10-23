#!/usr/bin/env python3
"""
KhetSense AI — Phase 7E Unit Tests: Live Sentinel-2 Feature Expansion
---------------------------------------------------------------------
Verifies:
1. Mathematical precision and boundary conditions for:
   - NDVI (NIR - Red) / (NIR + Red)
   - NDWI (NIR - SWIR) / (NIR + SWIR) (Gao 1996)
   - NDRE (NIR - RedEdge) / (NIR + RedEdge) (Barnes et al. 2000)
   - MSAVI (Qi et al. 1994) with [0, 1] reflectance scaling
2. Scaling sensitivity: verifies raw DN (10,000x) scaled vs unscaled
3. Robustness against zero denominators, NaN, Inf, negative reflectances, and negative discriminants
4. Earth Engine fetch_sentinel2_indices() multi-band reduction:
   - 4-band multi-spectral stack (B4, B5, B8, B11)
   - Backwards-compatible 4-tuple return (mean_ndvi, mean_ndwi, metadata, error)
   - Extended 6-tuple return when return_all=True
   - Metadata population with 'ndre', 'msavi', and 'indices' dictionary
5. Seamless end-to-end integration into run_pipeline_for_farm and predict_crop_stress
"""

import math
import os
import sys
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ["WHATSAPP_ALLOWLIST_ENABLED"] = "false"

from pipeline.test_pipeline import (
    calculate_ndvi,
    calculate_ndwi,
    calculate_ndre,
    calculate_msavi,
    calculate_all_spectral_indices,
    fetch_sentinel2_indices,
    run_pipeline_for_farm,
)


class TestSpectralIndicesFormulas(unittest.TestCase):
    """Test 1: Mathematical formulas, bounds, and edge cases for optical indices."""

    def test_calculate_ndvi_standard_and_bounds(self):
        # Healthy dense crop
        self.assertAlmostEqual(calculate_ndvi(0.50, 0.05), 0.8182, places=4)
        # Sparse / emerging crop
        self.assertAlmostEqual(calculate_ndvi(0.25, 0.15), 0.2500, places=4)
        # Bare soil (equal reflectances)
        self.assertAlmostEqual(calculate_ndvi(0.20, 0.20), 0.0000, places=4)
        # Water body / negative NDVI
        self.assertAlmostEqual(calculate_ndvi(0.05, 0.15), -0.5000, places=4)

    def test_calculate_ndvi_invalid_and_zero_denominator(self):
        # Zero denominator (0 + 0)
        self.assertIsNone(calculate_ndvi(0.0, 0.0))
        # None inputs
        self.assertIsNone(calculate_ndvi(None, 0.10))
        self.assertIsNone(calculate_ndvi(0.50, None))
        # Non-finite values
        self.assertIsNone(calculate_ndvi(float("nan"), 0.10))
        self.assertIsNone(calculate_ndvi(0.50, float("inf")))
        self.assertIsNone(calculate_ndvi(0.50, float("-inf")))

    def test_calculate_ndwi_standard_and_stress(self):
        # Well-hydrated canopy (high NDWI)
        self.assertAlmostEqual(calculate_ndwi(0.50, 0.15), 0.5385, places=4)
        # Moderate / water-stressed canopy
        self.assertAlmostEqual(calculate_ndwi(0.35, 0.25), 0.1667, places=4)
        # Severe water stress (SWIR > NIR)
        self.assertAlmostEqual(calculate_ndwi(0.20, 0.30), -0.2000, places=4)

    def test_calculate_ndwi_invalid_inputs(self):
        self.assertIsNone(calculate_ndwi(0.0, 0.0))
        self.assertIsNone(calculate_ndwi(None, None))
        self.assertIsNone(calculate_ndwi(float("nan"), 0.20))

    def test_calculate_ndre_red_edge_sensitivity(self):
        # B8 (NIR) vs B5 (Red-Edge 1 at 705nm)
        self.assertAlmostEqual(calculate_ndre(0.50, 0.20), 0.4286, places=4)
        # Early vegetative stage
        self.assertAlmostEqual(calculate_ndre(0.30, 0.20), 0.2000, places=4)
        # Equal reflectances
        self.assertAlmostEqual(calculate_ndre(0.15, 0.15), 0.0000, places=4)

    def test_calculate_ndre_invalid_inputs(self):
        self.assertIsNone(calculate_ndre(0.0, 0.0))
        self.assertIsNone(calculate_ndre(None, 0.20))
        self.assertIsNone(calculate_ndre(0.40, float("nan")))

    def test_calculate_msavi_scaling_and_precision(self):
        # Dense vegetation in [0, 1] reflectance: NIR=0.50, Red=0.05
        # 2*NIR + 1 = 2.0; (2*NIR + 1)^2 = 4.0; 8*(NIR - Red) = 8*0.45 = 3.6
        # sqrt(4.0 - 3.6) = sqrt(0.4) ≈ 0.6324555
        # MSAVI = (2.0 - 0.6324555) / 2 = 1.3675445 / 2 ≈ 0.6838
        msavi_scaled = calculate_msavi(0.50, 0.05, scale_factor=1.0)
        self.assertAlmostEqual(msavi_scaled, 0.6838, places=4)

        # Raw Level-2A integer DN (10,000x): NIR=5000, Red=500 with scale_factor=10000.0
        # MUST yield the exact same physical result
        msavi_raw = calculate_msavi(5000, 500, scale_factor=10000.0)
        self.assertEqual(msavi_scaled, msavi_raw)

        # Bare soil: NIR=0.15, Red=0.15 (NIR - Red = 0)
        # sqrt((2*0.15 + 1)^2) = 1.3 -> (1.3 - 1.3) / 2 = 0.0
        self.assertAlmostEqual(calculate_msavi(0.15, 0.15), 0.0000, places=4)

    def test_calculate_msavi_discriminant_and_physical_guards(self):
        # Negative reflectances must be rejected
        self.assertIsNone(calculate_msavi(-0.10, 0.05))
        self.assertIsNone(calculate_msavi(0.50, -0.05))
        # None and NaN handling
        self.assertIsNone(calculate_msavi(None, 0.05))
        self.assertIsNone(calculate_msavi(0.50, float("nan")))

    def test_calculate_all_spectral_indices_comprehensive(self):
        # Test full 4-index dictionary calculation
        res = calculate_all_spectral_indices(
            b4_red=0.05,
            b5_red_edge=0.20,
            b8_nir=0.50,
            b11_swir=0.15,
            scale_factor=1.0,
        )
        self.assertEqual(res["ndvi"], 0.8182)
        self.assertEqual(res["ndwi"], 0.5385)
        self.assertEqual(res["ndre"], 0.4286)
        self.assertEqual(res["msavi"], 0.6838)


class TestFetchSentinel2IndicesEEIntegration(unittest.TestCase):
    """Test 2: GEE multi-band reduction, backwards compatibility, and metadata population."""

    def setUp(self):
        self.ref_date = datetime(2026, 10, 20, 12, 0, 0, tzinfo=timezone.utc)
        self.mock_geom = MagicMock()

    @patch("pipeline.test_pipeline.ee")
    def test_fetch_sentinel2_indices_default_return_format(self, mock_ee):
        """Default return format is 4-tuple with NDRE and MSAVI in metadata."""
        epoch_ms = int((self.ref_date - timedelta(days=2)).timestamp() * 1000)

        mock_img = MagicMock()
        mock_img.get.side_effect = lambda k: {
            "system:time_start": MagicMock(getInfo=lambda: epoch_ms),
            "CLOUDY_PIXEL_PERCENTAGE": MagicMock(getInfo=lambda: 5.0),
        }[k]
        mock_img.id.return_value.getInfo.return_value = "COPERNICUS/S2_SR_HARMONIZED/20261018T053641"

        # Mock multi-band reduceRegion result with all 4 indices
        mock_stats = {
            "NDVI": 0.65,
            "NDWI": 0.22,
            "NDRE": 0.38,
            "MSAVI": 0.54,
        }
        mock_img.normalizedDifference.return_value.rename.return_value.addBands.return_value.reduceRegion.return_value.getInfo.return_value = mock_stats

        mock_col = MagicMock()
        mock_col.filterBounds.return_value = mock_col
        mock_col.filterDate.return_value = mock_col
        mock_col.filter.return_value = mock_col
        mock_col.sort.return_value = mock_col
        mock_col.size.return_value.getInfo.return_value = 1
        mock_col.first.return_value = mock_img
        mock_ee.ImageCollection.return_value = mock_col

        # Default call (return_all=False)
        res = fetch_sentinel2_indices(
            self.mock_geom,
            max_age_days=14,
            reference_date=self.ref_date,
            return_all=False,
        )

        # Verifies strictly 4 elements returned (preserves all existing callers)
        self.assertEqual(len(res), 4)
        ndvi, ndwi, meta, err = res
        self.assertIsNone(err)
        self.assertEqual(ndvi, 0.65)
        self.assertEqual(ndwi, 0.22)

        # Verifies metadata contains live NDRE and MSAVI
        self.assertIsNotNone(meta)
        self.assertEqual(meta["ndre"], 0.38)
        self.assertEqual(meta["msavi"], 0.54)
        self.assertIn("indices", meta)
        self.assertEqual(meta["indices"]["ndvi"], 0.65)
        self.assertEqual(meta["indices"]["ndwi"], 0.22)
        self.assertEqual(meta["indices"]["ndre"], 0.38)
        self.assertEqual(meta["indices"]["msavi"], 0.54)

    @patch("pipeline.test_pipeline.ee")
    def test_fetch_sentinel2_indices_extended_return_format(self, mock_ee):
        """Extended return format returns 6-tuple when return_all=True."""
        epoch_ms = int((self.ref_date - timedelta(days=3)).timestamp() * 1000)

        mock_img = MagicMock()
        mock_img.get.side_effect = lambda k: {
            "system:time_start": MagicMock(getInfo=lambda: epoch_ms),
            "CLOUDY_PIXEL_PERCENTAGE": MagicMock(getInfo=lambda: 6.2),
        }[k]
        mock_img.id.return_value.getInfo.return_value = "COPERNICUS/S2_SR_HARMONIZED/20261017T053641"

        mock_stats = {
            "NDVI": 0.58,
            "NDWI": 0.18,
            "NDRE": 0.32,
            "MSAVI": 0.49,
        }
        mock_img.normalizedDifference.return_value.rename.return_value.addBands.return_value.reduceRegion.return_value.getInfo.return_value = mock_stats

        mock_col = MagicMock()
        mock_col.filterBounds.return_value = mock_col
        mock_col.filterDate.return_value = mock_col
        mock_col.filter.return_value = mock_col
        mock_col.sort.return_value = mock_col
        mock_col.size.return_value.getInfo.return_value = 1
        mock_col.first.return_value = mock_img
        mock_ee.ImageCollection.return_value = mock_col

        # Extended call
        res = fetch_sentinel2_indices(
            self.mock_geom,
            max_age_days=14,
            reference_date=self.ref_date,
            return_all=True,
        )

        # Verifies 6 elements returned
        self.assertEqual(len(res), 6)
        ndvi, ndwi, ndre, msavi, meta, err = res
        self.assertIsNone(err)
        self.assertEqual(ndvi, 0.58)
        self.assertEqual(ndwi, 0.18)
        self.assertEqual(ndre, 0.32)
        self.assertEqual(msavi, 0.49)
        self.assertEqual(meta["image_id"], "COPERNICUS/S2_SR_HARMONIZED/20261017T053641")


class TestPipelineLiveSentinel2ExpansionIntegration(unittest.TestCase):
    """Test 3: End-to-end integration into run_pipeline_for_farm and predict_crop_stress."""

    @patch("pipeline.test_pipeline.get_farm_from_database")
    @patch("pipeline.test_pipeline.ee")
    @patch("pipeline.test_pipeline.authenticate_earth_engine")
    @patch("pipeline.test_pipeline.validate_agricultural_location")
    @patch("pipeline.test_pipeline.fetch_sentinel2_indices")
    @patch("pipeline.test_pipeline.fetch_smap_soil_moisture")
    @patch("pipeline.test_pipeline.fetch_openweather_forecast")
    @patch("pipeline.test_pipeline.save_advisory_to_database")
    def test_pipeline_forwards_live_ndre_and_msavi(
        self,
        mock_save_adv,
        mock_weather,
        mock_smap,
        mock_s2,
        mock_loc_val,
        mock_auth,
        mock_ee,
        mock_get_farm,
    ):
        mock_get_farm.return_value = {
            "id": 305,
            "farmer_name": "Balasaheb",
            "crop_name": "Wheat",
            "mobile_number": "919876543210",
            "farm_area": 3.0,
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
        # Sentinel-2 returns live 4-index suite in metadata
        mock_s2.return_value = (
            0.62,
            0.19,
            {
                "date": "2026-10-19T10:00:00Z",
                "ndre": 0.41,
                "msavi": 0.58,
                "indices": {"ndvi": 0.62, "ndwi": 0.19, "ndre": 0.41, "msavi": 0.58},
            },
            None,
        )
        mock_smap.return_value = (24.0, {"date": "2026-10-19T10:00:00Z"}, None)
        mock_weather.return_value = (2.0, None)
        mock_save_adv.return_value = {
            "id": 999,
            "observation_date": "2026-10-20",
            "created_at": "2026-10-20T12:00:00Z",
        }

        mock_voice_sender = MagicMock(return_value={"status": "success", "media_id": "mock_123"})
        mock_tts = MagicMock()

        res = run_pipeline_for_farm(
            farm_id=305,
            db_url="postgresql://mock",
            auto_send_advisory=False,
            outbound_voice_sender=mock_voice_sender,
            tts_provider=mock_tts,
        )

        self.assertEqual(res["status"], "success")
        self.assertIn("ml_inference", res)
        ml_inf = res["ml_inference"]

        # Verifies live NDRE and MSAVI are genuinely forwarded to the feature vector
        self.assertEqual(ml_inf["features_used"]["s2_ndvi"], 0.62)
        self.assertEqual(ml_inf["features_used"]["s2_ndwi"], 0.19)
        self.assertEqual(ml_inf["features_used"]["s2_ndre"], 0.41)
        self.assertEqual(ml_inf["features_used"]["s2_msavi"], 0.58)

        # Verifies that seasonal precipitation absence STILL keeps inference safely gated
        self.assertIsNone(ml_inf["features_used"]["era5_precip_season_mm"])
        self.assertEqual(ml_inf["inference_status"], "FEATURE_INCOMPATIBILITY")
        self.assertEqual(res["assessment_method"], "RULE_ENGINE_FEATURE_INCOMPATIBILITY")


if __name__ == "__main__":
    unittest.main()
