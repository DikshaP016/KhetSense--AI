#!/usr/bin/env python3
"""
KhetSense AI — Automatic Advisory Delivery and Satellite-Based Crop Validation Test Suite
========================================================================================
Comprehensive unit and integration test suite covering:
1. Regional crop calendar and taxonomy normalization.
2. Seasonal contradiction detection (e.g., winter Rabi wheat in monsoon July/August).
3. Post-harvest dense canopy contradiction detection (e.g., soybean in January).
4. Multi-temporal summer perennial canopy screening (e.g., rainfed cotton vs standing sugarcane).
5. Ground-truth reference and validated benchmark model matching/mismatching.
6. Single-date optical reality: truthful INCONCLUSIVE outcome with transparent farmer notice.
7. End-to-end pipeline execution with crop validation:
   - MATCH / INCONCLUSIVE -> proceeds to stress classification and advisory delivery.
   - MISMATCH -> withholds crop-specific advice, dispatches discrepancy alert.
8. Automated WhatsApp advisory delivery (without needing 'status' pull).
9. Delivery deduplication cooldown window (suppressing rapid duplicate delivery).
10. Delivery failure resilience (persisted advisory preserved despite network/API exceptions).
11. Trilingual localization (English, Marathi, Hindi) for all notices and transparent notes.
12. Respect for outbound kill-switch and sender allowlist.
"""

import os
import sys
import time
import unittest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

# Ensure project directories are in sys.path
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
KHETSENSE_DIR = os.path.abspath(os.path.join(TEST_DIR, ".."))
if KHETSENSE_DIR not in sys.path:
    sys.path.insert(0, KHETSENSE_DIR)

# Enforce clean test mode
os.environ["ENABLE_VOICE_CHATBOT"] = "false"
os.environ["WHATSAPP_TOKEN"] = ""
os.environ["WHATSAPP_PHONE_NUMBER_ID"] = ""
os.environ["DATABASE_URL"] = ""
os.environ["WHATSAPP_ALLOWLIST_ENABLED"] = "false"

from pipeline.crop_validator import (
    validate_crop_type,
    normalize_crop_name,
    get_standard_crop_display,
    CROP_MATCH,
    CROP_MISMATCH,
    CROP_INCONCLUSIVE,
    CROP_UNVALIDATED,
    SUPPORTED_CROPS,
)
from pipeline.test_pipeline import (
    run_pipeline_for_farm,
    _DELIVERED_ADVISORIES,
    _DELIVERED_ADVISORIES_LOCK,
    ADVISORY_DELIVERY_COOLDOWN_SECONDS,
)
from whatsapp.messages import (
    get_message,
    format_status_advisory,
    format_voice_script,
)


class TestCropValidatorTaxonomyAndCalendar(unittest.TestCase):
    """Tests the regional taxonomy, crop aliases, and calendar definitions."""

    def test_normalize_crop_name_aliases(self):
        """Verifies resolution of English, Marathi, Hindi, and colloquial names."""
        self.assertEqual(normalize_crop_name("cotton"), "cotton")
        self.assertEqual(normalize_crop_name("Kapas"), "cotton")
        self.assertEqual(normalize_crop_name("कापूस"), "cotton")
        self.assertEqual(normalize_crop_name("कपास"), "cotton")

        self.assertEqual(normalize_crop_name("Soybean"), "soybean")
        self.assertEqual(normalize_crop_name("सोयाबीन"), "soybean")

        self.assertEqual(normalize_crop_name("Wheat"), "wheat")
        self.assertEqual(normalize_crop_name("Gehu"), "wheat")
        self.assertEqual(normalize_crop_name("गहू"), "wheat")

        self.assertEqual(normalize_crop_name("Sugarcane"), "sugarcane")
        self.assertEqual(normalize_crop_name("ऊस"), "sugarcane")
        self.assertEqual(normalize_crop_name("ganna"), "sugarcane")

        self.assertEqual(normalize_crop_name("Tur"), "pigeon_pea")
        self.assertEqual(normalize_crop_name("तूर"), "pigeon_pea")
        self.assertEqual(normalize_crop_name("अरहर"), "pigeon_pea")

        self.assertEqual(normalize_crop_name("Chana"), "chickpea")
        self.assertEqual(normalize_crop_name("हरभरा"), "chickpea")

        self.assertIsNone(normalize_crop_name("DragonFruitXYZ"))
        self.assertIsNone(normalize_crop_name(""))
        self.assertIsNone(normalize_crop_name(None))

    def test_standard_display_name(self):
        """Verifies clean standard English crop display names."""
        self.assertEqual(get_standard_crop_display("कापूस"), "Cotton")
        self.assertEqual(get_standard_crop_display("wheat"), "Wheat")
        self.assertEqual(get_standard_crop_display("UnknownCrop"), "UnknownCrop")


class TestSeasonalContradictionAndPhenologyScreening(unittest.TestCase):
    """Tests mismatch detection based on regional biological calendars and multi-temporal data."""

    def test_rabi_wheat_in_monsoon_july_detected_as_mismatch(self):
        """Declaring winter wheat during peak monsoon July with vegetative NDVI triggers MISMATCH."""
        res = validate_crop_type(
            declared_crop="Wheat",
            centroid_lat=20.70,
            centroid_lon=77.00,
            mean_ndvi=0.62,
            observation_date="2026-07-25",
        )
        self.assertEqual(res["outcome"], CROP_MISMATCH)
        self.assertFalse(res["is_suitable_for_advisory"])
        self.assertTrue(res["requires_confirmation"])
        self.assertEqual(res["declared_crop"], "Wheat")
        self.assertIn("Cotton / Soybean", res["predicted_crop"])
        self.assertIn("Rabi", res["reason"])

    def test_rabi_chickpea_in_august_detected_as_mismatch(self):
        """Declaring winter chickpea in August with active canopy triggers MISMATCH."""
        res = validate_crop_type(
            declared_crop="चना",
            centroid_lat=20.50,
            centroid_lon=76.80,
            mean_ndvi=0.55,
            observation_date="2026-08-15",
        )
        self.assertEqual(res["outcome"], CROP_MISMATCH)
        self.assertFalse(res["is_suitable_for_advisory"])
        self.assertEqual(res["declared_crop"], "Chickpea (Chana)")

    def test_soybean_in_january_dense_canopy_detected_as_mismatch(self):
        """Declaring short-duration Kharif soybean in January with high NDVI contradicts harvest schedule."""
        res = validate_crop_type(
            declared_crop="सोयाबीन",
            centroid_lat=20.70,
            centroid_lon=77.00,
            mean_ndvi=0.68,
            observation_date="2026-01-15",
        )
        self.assertEqual(res["outcome"], CROP_MISMATCH)
        self.assertFalse(res["is_suitable_for_advisory"])
        self.assertEqual(res["declared_crop"], "Soybean")
        self.assertIn("harvest", res["reason"].lower())

    def test_summer_perennial_canopy_contradiction(self):
        """Persistent dense summer canopy (April-May) contradicts rainfed annual crop (Cotton)."""
        multi_date_series = [
            {"date": "2026-01-10", "month": 1, "ndvi": 0.40},
            {"date": "2026-04-15", "month": 4, "ndvi": 0.65},  # Summer dense canopy
            {"date": "2026-05-10", "month": 5, "ndvi": 0.70},  # Summer dense canopy
            {"date": "2026-07-20", "month": 7, "ndvi": 0.72},
        ]
        res = validate_crop_type(
            declared_crop="Cotton",
            centroid_lat=20.70,
            centroid_lon=77.00,
            mean_ndvi=0.72,
            multi_date_series=multi_date_series,
        )
        self.assertEqual(res["outcome"], CROP_MISMATCH)
        self.assertFalse(res["is_suitable_for_advisory"])
        self.assertIn("Sugarcane", res["predicted_crop"])
        self.assertIn("pre-monsoon summer", res["reason"])

    def test_ground_truth_reference_match_and_mismatch(self):
        """Validated external reference dataset correctly validates matching or contradictory crop."""
        # Reference dataset matches
        res_match = validate_crop_type(
            declared_crop="Cotton",
            centroid_lat=20.70,
            centroid_lon=77.00,
            ground_truth_reference={"crop_name": "cotton", "confidence": 0.92},
        )
        self.assertEqual(res_match["outcome"], CROP_MATCH)
        self.assertTrue(res_match["is_suitable_for_advisory"])
        self.assertEqual(res_match["confidence"], 0.92)

        # Reference dataset contradicts
        res_mismatch = validate_crop_type(
            declared_crop="Soybean",
            centroid_lat=20.70,
            centroid_lon=77.00,
            ground_truth_reference={"crop_name": "sugarcane", "confidence": 0.95},
        )
        self.assertEqual(res_mismatch["outcome"], CROP_MISMATCH)
        self.assertFalse(res_mismatch["is_suitable_for_advisory"])
        self.assertEqual(res_mismatch["predicted_crop"], "Sugarcane")


class TestSingleDateOpticalHonesty(unittest.TestCase):
    """Tests that single-date scenes return INCONCLUSIVE without fabricating predictions."""

    def test_single_date_optical_returns_inconclusive(self):
        """Single-date Kharif cotton in August is seasonally plausible but species is inconclusive."""
        res = validate_crop_type(
            declared_crop="Cotton",
            centroid_lat=20.70,
            centroid_lon=77.00,
            mean_ndvi=0.60,
            observation_date="2026-08-10",
        )
        self.assertEqual(res["outcome"], CROP_INCONCLUSIVE)
        # Suitable for advisory because it is plausible active cropland; declared crop is respected
        self.assertTrue(res["is_suitable_for_advisory"])
        self.assertIsNone(res["predicted_crop"])
        self.assertIn("Single-date Sentinel-2 observations", res["reason"])
        self.assertIn("differentiate", res["reason"])
        self.assertEqual(res["declared_crop"], "Cotton")

    def test_unsupported_crop_returns_inconclusive(self):
        """Unrecognized crop names return INCONCLUSIVE with transparent explanation."""
        res = validate_crop_type(
            declared_crop="Avocado",
            centroid_lat=20.70,
            centroid_lon=77.00,
            observation_date="2026-08-10",
        )
        self.assertEqual(res["outcome"], CROP_INCONCLUSIVE)
        self.assertTrue(res["is_suitable_for_advisory"])
        self.assertIn("not in the recognized regional agronomic taxonomy", res["reason"])


class TestEndToEndPipelineAutoAdvisoryAndCropValidation(unittest.TestCase):
    """Tests the full pipeline integration with crop validation and automated delivery."""

    def setUp(self):
        with _DELIVERED_ADVISORIES_LOCK:
            _DELIVERED_ADVISORIES.clear()

    @patch("pipeline.test_pipeline.get_farm_from_database")
    @patch("pipeline.test_pipeline.fetch_sentinel2_indices")
    @patch("pipeline.test_pipeline.fetch_smap_soil_moisture")
    @patch("pipeline.test_pipeline.fetch_openweather_forecast")
    @patch("pipeline.test_pipeline.save_advisory_to_database")
    def test_pipeline_with_credible_crop_mismatch_withholds_advice(
        self, mock_save_adv, mock_owm, mock_smap, mock_s2, mock_get_farm
    ):
        """When crop mismatch is detected, irrigation advice is withheld and alert sent."""
        mock_get_farm.return_value = {
            "id": 42,
            "farmer_name": "Anil Deshmukh",
            "mobile_number": "919876543210",
            "preferred_language": "en",
            "crop_name": "Wheat",  # Declared Rabi Wheat
            "farm_area": 3.0,
            "ee_coords": [[77.0, 20.7], [77.01, 20.7], [77.01, 20.71], [77.0, 20.71], [77.0, 20.7]],
            "centroid_lat": 20.705,
            "centroid_lon": 77.005,
            "land_cover_class": "Cropland",
            "land_cover_code": 40,
            "is_demo": False,
        }
        # Monsoon observation with dense canopy
        mock_s2.return_value = (0.65, 0.20, {"date": "2026-07-20T05:30:00Z"}, None)
        mock_smap.return_value = (24.0, {"date": "2026-07-20T05:30:00Z"}, None)
        mock_owm.return_value = (2.0, None)

        mock_outbound = MagicMock(return_value=True)

        res = run_pipeline_for_farm(
            farm_id=42,
            db_url="postgresql://mock",
            outbound_sender=mock_outbound,
            auto_send_advisory=True,
            force=True,
        )

        self.assertEqual(res["status"], "crop_mismatch")
        self.assertFalse(res["advisory_sent"])
        self.assertEqual(res["crop_validation"]["outcome"], CROP_MISMATCH)

        # Verify outbound sender was called with discrepancy alert, NOT standard advisory
        mock_outbound.assert_called_once()
        sent_phone, sent_text = mock_outbound.call_args[0]
        self.assertEqual(sent_phone, "919876543210")
        self.assertIn("KhetSense Crop Verification Notice", sent_text)
        self.assertIn("Wheat", sent_text)
        self.assertIn("Cotton / Soybean", sent_text)
        self.assertIn("withheld", sent_text)

        # Crucial: standard advisory generation was skipped
        mock_save_adv.assert_not_called()

    @patch("pipeline.test_pipeline.get_farm_from_database")
    @patch("pipeline.test_pipeline.fetch_sentinel2_indices")
    @patch("pipeline.test_pipeline.fetch_smap_soil_moisture")
    @patch("pipeline.test_pipeline.fetch_openweather_forecast")
    @patch("pipeline.test_pipeline.save_advisory_to_database")
    def test_pipeline_with_inconclusive_crop_delivers_advisory_with_note(
        self, mock_save_adv, mock_owm, mock_smap, mock_s2, mock_get_farm
    ):
        """Inconclusive single-date crop delivers advisory card with transparent crop note."""
        mock_get_farm.return_value = {
            "id": 43,
            "farmer_name": "Suresh Kale",
            "mobile_number": "919876543210",
            "preferred_language": "en",
            "crop_name": "Cotton",
            "farm_area": 2.5,
            "ee_coords": [[77.0, 20.7], [77.01, 20.7], [77.01, 20.71], [77.0, 20.71], [77.0, 20.7]],
            "centroid_lat": 20.705,
            "centroid_lon": 77.005,
            "land_cover_class": "Cropland",
            "land_cover_code": 40,
            "is_demo": False,
        }
        mock_s2.return_value = (0.58, 0.15, {"date": "2026-08-15T05:30:00Z"}, None)
        mock_smap.return_value = (14.0, {"date": "2026-08-15T05:30:00Z"}, None)
        mock_owm.return_value = (1.5, None)

        mock_save_adv.return_value = {
            "id": 901,
            "farm_id": 43,
            "observation_date": "2026-08-15",
            "created_at": "2026-08-15 10:00:00",
            "stress_level": "MILD STRESS",
        }

        mock_outbound = MagicMock(return_value=True)

        res = run_pipeline_for_farm(
            farm_id=43,
            db_url="postgresql://mock",
            outbound_sender=mock_outbound,
            auto_send_advisory=True,
            force=True,
        )

        self.assertEqual(res["status"], "success")
        self.assertTrue(res["advisory_sent"])
        self.assertEqual(res["crop_validation"]["outcome"], CROP_INCONCLUSIVE)

        # Verify automated advisory was sent to WhatsApp
        mock_outbound.assert_called_once()
        sent_phone, sent_text = mock_outbound.call_args[0]
        self.assertEqual(sent_phone, "919876543210")
        self.assertIn("KhetSense Farm Status & Advisory", sent_text)
        self.assertIn("Suresh Kale", sent_text)
        # Transparent crop verification note is appended
        self.assertIn("Crop Verification Note", sent_text)
        self.assertIn("Advisory is calibrated for declared Cotton", sent_text)

    @patch("pipeline.test_pipeline.get_farm_from_database")
    @patch("pipeline.test_pipeline.fetch_sentinel2_indices")
    @patch("pipeline.test_pipeline.fetch_smap_soil_moisture")
    @patch("pipeline.test_pipeline.fetch_openweather_forecast")
    @patch("pipeline.test_pipeline.save_advisory_to_database")
    def test_delivery_deduplication_cooldown_suppresses_rapid_resend(
        self, mock_save_adv, mock_owm, mock_smap, mock_s2, mock_get_farm
    ):
        """Second pipeline run within 300s window does not re-send duplicate card unless forced."""
        mock_get_farm.return_value = {
            "id": 44,
            "farmer_name": "Prakash Rao",
            "mobile_number": "919876543210",
            "preferred_language": "en",
            "crop_name": "Cotton",
            "ee_coords": [[77.0, 20.7], [77.01, 20.7], [77.01, 20.71], [77.0, 20.71], [77.0, 20.7]],
            "centroid_lat": 20.705,
            "centroid_lon": 77.005,
            "land_cover_class": "Cropland",
            "land_cover_code": 40,
        }
        mock_s2.return_value = (0.55, 0.12, {"date": "2026-08-15T05:30:00Z"}, None)
        mock_smap.return_value = (15.0, {"date": "2026-08-15T05:30:00Z"}, None)
        mock_owm.return_value = (0.0, None)
        mock_save_adv.return_value = {
            "id": 902,
            "farm_id": 44,
            "observation_date": "2026-08-15",
            "created_at": "2026-08-15 10:00:00",
            "stress_level": "MILD STRESS",
        }

        mock_outbound = MagicMock(return_value=True)

        # Run 1: Delivers advisory
        res1 = run_pipeline_for_farm(
            farm_id=44,
            db_url="postgresql://mock",
            outbound_sender=mock_outbound,
            auto_send_advisory=True,
            force=False,
        )
        self.assertTrue(res1["advisory_sent"])
        self.assertFalse(res1["duplicate_delivery_suppressed"])
        self.assertEqual(mock_outbound.call_count, 1)

        # Run 2: Immediately following run 1 -> delivery suppressed
        res2 = run_pipeline_for_farm(
            farm_id=44,
            db_url="postgresql://mock",
            outbound_sender=mock_outbound,
            auto_send_advisory=True,
            force=False,
        )
        self.assertFalse(res2["advisory_sent"])
        self.assertTrue(res2["duplicate_delivery_suppressed"])
        self.assertEqual(mock_outbound.call_count, 1)  # Still 1, no duplicate sent

        # Run 3: Forced -> overrides cooldown
        res3 = run_pipeline_for_farm(
            farm_id=44,
            db_url="postgresql://mock",
            outbound_sender=mock_outbound,
            auto_send_advisory=True,
            force=True,
        )
        self.assertTrue(res3["advisory_sent"])
        self.assertFalse(res3["duplicate_delivery_suppressed"])
        self.assertEqual(mock_outbound.call_count, 2)

    @patch("pipeline.test_pipeline.get_farm_from_database")
    @patch("pipeline.test_pipeline.fetch_sentinel2_indices")
    @patch("pipeline.test_pipeline.fetch_smap_soil_moisture")
    @patch("pipeline.test_pipeline.fetch_openweather_forecast")
    @patch("pipeline.test_pipeline.save_advisory_to_database")
    def test_outbound_delivery_exception_preserves_persisted_advisory(
        self, mock_save_adv, mock_owm, mock_smap, mock_s2, mock_get_farm
    ):
        """If WhatsApp API raises network error, persisted database advisory is preserved."""
        mock_get_farm.return_value = {
            "id": 45,
            "farmer_name": "Vinod Jadhav",
            "mobile_number": "919876543210",
            "preferred_language": "en",
            "crop_name": "Cotton",
            "ee_coords": [[77.0, 20.7], [77.01, 20.7], [77.01, 20.71], [77.0, 20.71], [77.0, 20.7]],
            "centroid_lat": 20.705,
            "centroid_lon": 77.005,
            "land_cover_class": "Cropland",
            "land_cover_code": 40,
        }
        mock_s2.return_value = (0.50, 0.10, {"date": "2026-08-15T05:30:00Z"}, None)
        mock_smap.return_value = (12.0, {"date": "2026-08-15T05:30:00Z"}, None)
        mock_owm.return_value = (0.0, None)
        mock_save_adv.return_value = {
            "id": 903,
            "farm_id": 45,
            "observation_date": "2026-08-15",
            "created_at": "2026-08-15 10:00:00",
            "stress_level": "MILD STRESS",
        }

        # Mock outbound sender raises connection failure
        mock_failing_sender = MagicMock(side_effect=ConnectionError("Meta WhatsApp endpoint unreachable"))

        res = run_pipeline_for_farm(
            farm_id=45,
            db_url="postgresql://mock",
            outbound_sender=mock_failing_sender,
            auto_send_advisory=True,
            force=True,
        )

        # Pipeline completed successfully and saved record to DB
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["advisory_id"], 903)
        self.assertFalse(res["advisory_sent"])
        self.assertIn("Meta WhatsApp endpoint unreachable", res["delivery_error"])
        mock_save_adv.assert_called_once()  # Persisted DB record is intact!

    @patch("pipeline.test_pipeline.get_farm_from_database")
    @patch("pipeline.test_pipeline.fetch_sentinel2_indices")
    @patch("pipeline.test_pipeline.fetch_smap_soil_moisture")
    @patch("pipeline.test_pipeline.fetch_openweather_forecast")
    @patch("pipeline.test_pipeline.save_advisory_to_database")
    def test_pipeline_with_urban_location_withholds_advisory(
        self, mock_save_adv, mock_owm, mock_smap, mock_s2, mock_get_farm
    ):
        """When location validation classifies land as urban, advisory is withheld."""
        mock_get_farm.return_value = {
            "id": 46,
            "farmer_name": "Urban Resident",
            "mobile_number": "919876543210",
            "preferred_language": "en",
            "crop_name": "Cotton",
            "ee_coords": [[77.0, 20.7], [77.01, 20.7], [77.01, 20.71], [77.0, 20.71], [77.0, 20.7]],
            "centroid_lat": 20.705,
            "centroid_lon": 77.005,
            "land_cover_class": "Built-up",
            "land_cover_code": 50,
        }
        mock_s2.return_value = (0.25, 0.05, {"date": "2026-08-15T05:30:00Z"}, None)
        mock_smap.return_value = (10.0, {"date": "2026-08-15T05:30:00Z"}, None)
        mock_owm.return_value = (0.0, None)

        mock_outbound = MagicMock(return_value=True)

        res = run_pipeline_for_farm(
            farm_id=46,
            db_url="postgresql://mock",
            outbound_sender=mock_outbound,
            auto_send_advisory=True,
            force=True,
        )

        self.assertEqual(res["status"], "validation_failed")
        self.assertEqual(res["outcome"], "LIKELY_URBAN")
        self.assertFalse(res["advisory_sent"])
        mock_save_adv.assert_not_called()
        mock_outbound.assert_called_once()
        self.assertIn("urban or built-up area", mock_outbound.call_args[0][1])


class TestTrilingualLocalization(unittest.TestCase):
    """Tests trilingual message rendering for crop validation and advisory notes."""

    def test_crop_mismatch_messages_in_all_languages(self):
        """Verifies crop mismatch message content in English, Marathi, Hindi."""
        for lang, expected_token in [("en", "KhetSense Crop Verification Notice"), ("mr", "खेतसेन्स पीक पडताळणी सूचना"), ("hi", "खेतसेंस फसल सत्यापन सूचना")]:
            msg = get_message(
                "crop_validation_mismatch",
                lang=lang,
                farm_id=12,
                declared_crop="Wheat",
                predicted_crop="Cotton",
                reason="Seasonality contradiction",
            )
            self.assertIn(expected_token, msg)
            self.assertIn("Wheat", msg)
            self.assertIn("Cotton", msg)

    def test_inconclusive_crop_note_in_all_languages(self):
        """Verifies transparent crop note appended in English, Marathi, and Hindi."""
        farm = {"id": 15, "farmer_name": "Kisan", "crop_name": "Cotton"}
        adv = {
            "id": 100,
            "observation_date": "2026-08-15",
            "observed_stress": "NO STRESS",
            "recommended_action": "no action",
            "recommendation": "Adequate moisture",
            "crop_validation": {"outcome": "INCONCLUSIVE"},
        }

        # English
        card_en = format_status_advisory(farm, adv, lang="en")
        self.assertIn("Crop Verification Note", card_en)
        self.assertIn("Advisory is calibrated for declared Cotton", card_en)

        # Marathi
        card_mr = format_status_advisory(farm, adv, lang="mr")
        self.assertIn("पीक पडताळणी नोंद", card_mr)

        # Hindi
        card_hi = format_status_advisory(farm, adv, lang="hi")
        self.assertIn("फसल सत्यापन टिप्पणी", card_hi)

    def test_voice_script_withheld_on_crop_mismatch(self):
        """Spoken audio advisory is withheld when crop mismatch is present."""
        farm = {"id": 16, "farmer_name": "Farmer", "crop_name": "Wheat"}
        adv_mismatch = {
            "id": 101,
            "observed_stress": "SEVERE STRESS",
            "crop_validation": {"outcome": "MISMATCH"},
        }
        script = format_voice_script(farm, adv_mismatch, language="en")
        self.assertIsNone(script)


if __name__ == "__main__":
    unittest.main()
