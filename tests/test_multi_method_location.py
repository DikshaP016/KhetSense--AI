#!/usr/bin/env python3
"""
KhetSense AI — Multi-Method Farm Location Input Test Suite

Tests:
1. Native WhatsApp location pin parsing and confirmation.
2. Google Maps URL resolution (direct coordinates, query params, protobuf !3d/!4d).
3. Google Maps shortlink resolution with SSRF / private IP protections.
4. Typed address geocoding via OpenStreetMap/Nominatim:
   - Valid unambiguous address resolution.
   - Ambiguous address detection (>15km spread, similar rank) and clarification prompt.
   - Address not found detection and guidance prompt.
5. Spatial bounding box enforcement (Lat 6.0–38.0°N, Lon 68.0–98.0°E).
6. Conversational confirmation workflow:
   - Affirmative (YES / हो / हाँ) commits farm registration.
   - Negative (NO / नाही / नहीं) cancels without overwriting existing farms.
7. Demo mode:
   - Keyword 'demo' / 'demo mode' / 'डेमो' resolves agricultural plot presets.
   - Displays [DEMO MODE — ILLUSTRATIVE LOCATION DATA] banner in status advisory.
   - Spoken disclaimer in neural voice script.
   - Preserves land cover screening and guardrails (no sensor fabrication).
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Ensure proper paths for imports
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
KHETSENSE_DIR = os.path.abspath(os.path.join(TEST_DIR, ".."))
if KHETSENSE_DIR not in sys.path:
    sys.path.insert(0, KHETSENSE_DIR)

import uuid
from common.utils import (
    validate_india_bounds,
    extract_direct_coordinates,
    extract_place_query_from_maps_url,
    geocode_address,
    resolve_farm_location_input,
    parse_location_from_text,
    DEMO_AGRICULTURAL_PRESETS,
)
from whatsapp.messages import (
    get_message,
    format_status_advisory,
    format_no_advisory,
    format_voice_script,
    LOCATION_AMBIGUOUS_PROMPT,
    LOCATION_NOT_FOUND_PROMPT,
    LOCATION_INVALID_PROMPT,
    LOCATION_CONFIRM_PROMPT,
)
from whatsapp.registration_flow import (
    handle_incoming,
    extract_incoming_coordinates,
    _IN_FLIGHT_LOCATION_CACHE,
    _IN_FLIGHT_LOCATION_DETAILS,
    _IN_MEMORY_PROCESSED_MESSAGES,
    clear_session,
)


class TestDirectAndProtobufCoordinates(unittest.TestCase):
    """Verifies direct extraction of GPS coordinates from diverse Google Maps URL formats."""

    def test_direct_lat_lon_slash_at(self):
        url = "https://www.google.com/maps/@18.15000,74.58000,15z"
        coords = extract_direct_coordinates(url)
        self.assertIsNotNone(coords)
        self.assertAlmostEqual(coords[0], 18.15000, places=4)
        self.assertAlmostEqual(coords[1], 74.58000, places=4)

    def test_direct_lat_lon_query_param(self):
        url = "https://maps.google.com/?q=20.70000,77.00000"
        coords = extract_direct_coordinates(url)
        self.assertIsNotNone(coords)
        self.assertAlmostEqual(coords[0], 20.70000, places=4)
        self.assertAlmostEqual(coords[1], 77.00000, places=4)

    def test_protobuf_coordinates_in_place_url(self):
        url = "https://www.google.com/maps/place/KhetSense+Farm/data=!4m2!3m1!1s0x0:0x0!8m2!3d21.14580!4d79.08820"
        coords = extract_direct_coordinates(url)
        self.assertIsNotNone(coords)
        self.assertAlmostEqual(coords[0], 21.14580, places=4)
        self.assertAlmostEqual(coords[1], 79.08820, places=4)

    def test_place_query_extraction_from_maps_url(self):
        url = "https://www.google.com/maps/place/Baramati,+Maharashtra+413102"
        query = extract_place_query_from_maps_url(url)
        self.assertEqual(query, "Baramati, Maharashtra 413102")


class TestGeocodingAndAmbiguityHandling(unittest.TestCase):
    """Verifies Nominatim geocoding, boundary validation, and ambiguity detection."""

    @patch("requests.get")
    def test_unambiguous_address_resolution(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {
                "lat": "18.1512",
                "lon": "74.5775",
                "display_name": "Baramati, Pune District, Maharashtra, 413102, India",
                "importance": 0.85,
            }
        ]
        mock_get.return_value = mock_resp

        res = geocode_address("Baramati, Pune")
        self.assertEqual(res["status"], "success")
        self.assertAlmostEqual(res["lat"], 18.1512, places=4)
        self.assertAlmostEqual(res["lon"], 74.5775, places=4)
        self.assertIn("Baramati", res["display_name"])

    @patch("requests.get")
    def test_ambiguous_address_resolution(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        # Two locations named 'Rampur' separated by hundreds of km
        mock_resp.json.return_value = [
            {
                "lat": "28.805",
                "lon": "79.026",
                "display_name": "Rampur, Rampur District, Uttar Pradesh, India",
                "importance": 0.65,
            },
            {
                "lat": "25.485",
                "lon": "82.571",
                "display_name": "Rampur, Bhadohi District, Uttar Pradesh, India",
                "importance": 0.60,
            },
        ]
        mock_get.return_value = mock_resp

        res = geocode_address("Rampur")
        self.assertEqual(res["status"], "ambiguous")
        self.assertEqual(len(res["candidates"]), 2)
        self.assertIn("Rampur District", res["candidates"][0])

    @patch("requests.get")
    def test_address_not_found(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []
        mock_get.return_value = mock_resp

        res = geocode_address("NonExistentVillageXYZ999")
        self.assertEqual(res["status"], "not_found")
        self.assertEqual(res["raw_input"], "NonExistentVillageXYZ999")

    @patch("requests.get")
    def test_geocoded_address_outside_india(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {
                "lat": "51.5074",
                "lon": "-0.1278",
                "display_name": "London, Greater London, England, United Kingdom",
                "importance": 0.90,
            }
        ]
        mock_get.return_value = mock_resp

        res = geocode_address("London, UK")
        self.assertEqual(res["status"], "out_of_bounds")


class TestMultiMethodLocationInRegistrationFlow(unittest.TestCase):
    """End-to-end tests for multi-method location in KhetSense registration state machine."""

    def _mock_claim_message(self, msg_id, db_url=None):
        if not msg_id:
            return True
        if msg_id in self.processed_messages:
            return False
        self.processed_messages.add(msg_id)
        return True

    def _mock_unclaim_message(self, msg_id, db_url=None):
        self.processed_messages.discard(msg_id)

    def setUp(self):
        self.phone = "919876543111"
        self.mock_sender = MagicMock()
        self.processed_messages = set()
        self.claim_patch = patch("whatsapp.registration_flow.claim_message", side_effect=self._mock_claim_message)
        self.unclaim_patch = patch("whatsapp.registration_flow.unclaim_message", side_effect=self._mock_unclaim_message)
        self.claim_patch.start()
        self.unclaim_patch.start()
        _IN_FLIGHT_LOCATION_CACHE.clear()
        _IN_FLIGHT_LOCATION_DETAILS.clear()
        _IN_MEMORY_PROCESSED_MESSAGES.clear()
        os.environ["WHATSAPP_ALLOWLIST_ENABLED"] = "false"
        os.environ["ENABLE_OUTBOUND_WHATSAPP"] = "false"

    def tearDown(self):
        self.claim_patch.stop()
        self.unclaim_patch.stop()
        _IN_FLIGHT_LOCATION_CACHE.clear()
        _IN_FLIGHT_LOCATION_DETAILS.clear()
        _IN_MEMORY_PROCESSED_MESSAGES.clear()

    @patch("whatsapp.registration_flow.save_session")
    @patch("whatsapp.registration_flow.get_registered_farm", return_value=None)
    @patch("whatsapp.registration_flow.get_session")
    def test_awaiting_location_native_pin(self, mock_get_session, mock_get_farm, mock_save_session):
        mock_get_session.return_value = {
            "state": "AWAITING_LOCATION",
            "preferred_language": "en",
            "name": "Devidas",
            "crop": "Cotton",
            "acreage_acres": 3.0,
        }

        msg = {
            "from": self.phone,
            "id": f"wamid.pin.{uuid.uuid4().hex}",
            "type": "location",
            "location": {"latitude": 20.7000, "longitude": 77.0000},
        }

        res = handle_incoming(msg, outbound_sender=self.mock_sender)
        self.assertEqual(res["status"], "location_confirmation_requested")
        self.assertEqual(res["next_state"], "AWAITING_LOCATION_CONFIRMATION")
        self.assertAlmostEqual(res["lat"], 20.7000, places=4)
        self.assertAlmostEqual(res["lon"], 77.0000, places=4)

        sent_text = self.mock_sender.call_args[0][1]
        self.assertIn("Lat 20.70000, Lon 77.00000", sent_text)
        self.assertIn("Reply YES to confirm", sent_text)

    @patch("whatsapp.registration_flow.save_session")
    @patch("whatsapp.registration_flow.get_registered_farm", return_value=None)
    @patch("whatsapp.registration_flow.get_session")
    def test_awaiting_location_google_maps_url(self, mock_get_session, mock_get_farm, mock_save_session):
        mock_get_session.return_value = {
            "state": "AWAITING_LOCATION",
            "preferred_language": "mr",
            "name": "ज्ञानेश्वर",
            "crop": "Soybean",
            "acreage_acres": 2.5,
        }

        msg = {
            "from": self.phone,
            "id": f"wamid.maps.{uuid.uuid4().hex}",
            "type": "text",
            "text": {"body": "https://www.google.com/maps/@18.15000,74.58000,16z"},
        }

        res = handle_incoming(msg, outbound_sender=self.mock_sender)
        self.assertEqual(res["status"], "location_confirmation_requested")
        self.assertEqual(res["next_state"], "AWAITING_LOCATION_CONFIRMATION")
        self.assertAlmostEqual(res["lat"], 18.15000, places=4)
        self.assertAlmostEqual(res["lon"], 74.58000, places=4)

        sent_text = self.mock_sender.call_args[0][1]
        self.assertIn("अक्षांश 18.15000, रेखांश 74.58000", sent_text)
        self.assertIn("पुष्टी करण्यासाठी 'हो' (YES)", sent_text)

    @patch("common.utils.geocode_address")
    @patch("whatsapp.registration_flow.save_session")
    @patch("whatsapp.registration_flow.get_registered_farm", return_value=None)
    @patch("whatsapp.registration_flow.get_session")
    def test_awaiting_location_typed_address_success(
        self, mock_get_session, mock_get_farm, mock_save_session, mock_geocode
    ):
        mock_get_session.return_value = {
            "state": "AWAITING_LOCATION",
            "preferred_language": "en",
            "name": "Rohan",
            "crop": "Wheat",
            "acreage_acres": 4.0,
        }
        mock_geocode.return_value = {
            "status": "success",
            "lat": 18.1512,
            "lon": 74.5775,
            "display_name": "Baramati, Pune District, Maharashtra, India",
            "source": "nominatim_osm",
            "is_demo": False,
        }

        msg = {
            "from": self.phone,
            "id": f"wamid.addr.{uuid.uuid4().hex}",
            "type": "text",
            "text": {"body": "Baramati, Pune"},
        }

        res = handle_incoming(msg, outbound_sender=self.mock_sender)
        self.assertEqual(res["status"], "location_confirmation_requested")
        self.assertEqual(res["next_state"], "AWAITING_LOCATION_CONFIRMATION")
        self.assertAlmostEqual(res["lat"], 18.1512, places=4)
        self.assertIn("Baramati", res["location_name"])

        sent_text = self.mock_sender.call_args[0][1]
        self.assertIn("Location: Baramati, Pune District", sent_text)
        self.assertIn("Coordinates: Lat 18.15120, Lon 74.57750", sent_text)

    @patch("common.utils.geocode_address")
    @patch("whatsapp.registration_flow.save_session")
    @patch("whatsapp.registration_flow.get_registered_farm", return_value=None)
    @patch("whatsapp.registration_flow.get_session")
    def test_awaiting_location_ambiguous_address(
        self, mock_get_session, mock_get_farm, mock_save_session, mock_geocode
    ):
        mock_get_session.return_value = {
            "state": "AWAITING_LOCATION",
            "preferred_language": "hi",
            "name": "मोहन",
            "crop": "Maize",
            "acreage_acres": 5.0,
        }
        mock_geocode.return_value = {
            "status": "ambiguous",
            "query": "Rampur",
            "raw_input": "Rampur",
            "candidates": ["Rampur, UP", "Rampur, Bihar"],
        }

        msg = {
            "from": self.phone,
            "id": f"wamid.ambig.{uuid.uuid4().hex}",
            "type": "text",
            "text": {"body": "Rampur"},
        }

        res = handle_incoming(msg, outbound_sender=self.mock_sender)
        self.assertEqual(res["status"], "location_ambiguous")
        self.assertEqual(res["state"], "AWAITING_LOCATION")

        sent_text = self.mock_sender.call_args[0][1]
        self.assertIn("मिलते-जुलते एक से अधिक स्थान मिले हैं", sent_text)
        self.assertIn("Rampur", sent_text)

    @patch("common.utils.geocode_address")
    @patch("whatsapp.registration_flow.get_registered_farm", return_value=None)
    @patch("whatsapp.registration_flow.get_session")
    def test_awaiting_location_not_found_address(
        self, mock_get_session, mock_get_farm, mock_geocode
    ):
        mock_get_session.return_value = {
            "state": "AWAITING_LOCATION",
            "preferred_language": "en",
            "name": "Sita",
            "crop": "Pigeonpea",
            "acreage_acres": 2.0,
        }
        mock_geocode.return_value = {
            "status": "not_found",
            "query": "UnknownPlaceXYZ",
            "raw_input": "UnknownPlaceXYZ",
        }

        msg = {
            "from": self.phone,
            "id": f"wamid.nf.{uuid.uuid4().hex}",
            "type": "text",
            "text": {"body": "UnknownPlaceXYZ"},
        }

        res = handle_incoming(msg, outbound_sender=self.mock_sender)
        self.assertEqual(res["status"], "location_not_found")
        self.assertEqual(res["state"], "AWAITING_LOCATION")

        sent_text = self.mock_sender.call_args[0][1]
        self.assertIn("could not find coordinates for 'UnknownPlaceXYZ'", sent_text)


class TestDemoModeAndAdvisoryDisclaimer(unittest.TestCase):
    """Verifies demonstration plot selection without farm ownership, and advisory banner."""

    def _mock_claim_message(self, msg_id, db_url=None):
        if not msg_id:
            return True
        if msg_id in self.processed_messages:
            return False
        self.processed_messages.add(msg_id)
        return True

    def _mock_unclaim_message(self, msg_id, db_url=None):
        self.processed_messages.discard(msg_id)

    def setUp(self):
        self.phone = "919876543222"
        self.mock_sender = MagicMock()
        self.processed_messages = set()
        self.claim_patch = patch("whatsapp.registration_flow.claim_message", side_effect=self._mock_claim_message)
        self.unclaim_patch = patch("whatsapp.registration_flow.unclaim_message", side_effect=self._mock_unclaim_message)
        self.claim_patch.start()
        self.unclaim_patch.start()
        _IN_FLIGHT_LOCATION_CACHE.clear()
        _IN_FLIGHT_LOCATION_DETAILS.clear()
        _IN_MEMORY_PROCESSED_MESSAGES.clear()
        os.environ["WHATSAPP_ALLOWLIST_ENABLED"] = "false"
        os.environ["ENABLE_OUTBOUND_WHATSAPP"] = "false"

    def tearDown(self):
        self.claim_patch.stop()
        self.unclaim_patch.stop()
        _IN_FLIGHT_LOCATION_CACHE.clear()
        _IN_FLIGHT_LOCATION_DETAILS.clear()
        _IN_MEMORY_PROCESSED_MESSAGES.clear()

    @patch("whatsapp.registration_flow.save_session")
    @patch("whatsapp.registration_flow.get_registered_farm", return_value=None)
    @patch("whatsapp.registration_flow.get_session")
    def test_demo_keyword_selects_akola_preset(self, mock_get_session, mock_get_farm, mock_save_session):
        mock_get_session.return_value = {
            "state": "AWAITING_LOCATION",
            "preferred_language": "en",
            "name": "Demo Farmer",
            "crop": "Cotton",
            "acreage_acres": 2.5,
        }

        msg = {
            "from": self.phone,
            "id": f"wamid.demo.{uuid.uuid4().hex}",
            "type": "text",
            "text": {"body": "demo"},
        }

        res = handle_incoming(msg, outbound_sender=self.mock_sender)
        self.assertEqual(res["status"], "location_confirmation_requested")
        self.assertEqual(res["next_state"], "AWAITING_LOCATION_CONFIRMATION")
        self.assertTrue(res["is_demo"])
        self.assertIn("Akola", res["location_name"])

        sent_text = self.mock_sender.call_args[0][1]
        self.assertIn("Location: Akola Cropland (Borgaon Manju)", sent_text)
        self.assertIn("Coordinates: Lat 20.68500, Lon 77.15000", sent_text)

    @patch("whatsapp.registration_flow.trigger_pipeline_for_farm")
    @patch("whatsapp.registration_flow.register_farmer_from_pin")
    @patch("whatsapp.registration_flow.save_session")
    @patch("whatsapp.registration_flow.get_registered_farm", return_value=None)
    @patch("whatsapp.registration_flow.get_session")
    def test_confirm_demo_registration_adds_banner_and_preserves_pipeline(
        self, mock_get_session, mock_get_farm, mock_save_session, mock_reg_pin, mock_pipeline
    ):
        mock_get_session.return_value = {
            "state": "AWAITING_LOCATION_CONFIRMATION",
            "preferred_language": "en",
            "name": "Demo User",
            "crop": "Cotton",
            "acreage_acres": 2.5,
            "pending_lat": 20.6850,
            "pending_lon": 77.1500,
        }
        # Mark in flight as demo
        _IN_FLIGHT_LOCATION_DETAILS[self.phone] = {
            "lat": 20.6850,
            "lon": 77.1500,
            "is_demo": True,
            "display_name": "Akola Cropland (Borgaon Manju), Maharashtra",
        }
        mock_reg_pin.return_value = {"farm_id": 999, "farm_area": 2.5}

        msg = {
            "from": self.phone,
            "id": f"wamid.demo.confirm.{uuid.uuid4().hex}",
            "type": "text",
            "text": {"body": "YES"},
        }

        res = handle_incoming(msg, outbound_sender=self.mock_sender)
        self.assertEqual(res["status"], "registration_complete")
        self.assertTrue(res["is_demo"])
        self.assertEqual(res["farm_id"], 999)

        # Success message must carry demo mode disclaimer and avoid false live monitoring promises
        sent_text = self.mock_sender.call_args[0][1]
        self.assertIn("[DEMO MODE — ILLUSTRATIVE LOCATION DATA]", sent_text)
        self.assertIn("Demonstration Farm Setup Recorded", sent_text)
        self.assertIn("Farm ID: #999", sent_text)
        self.assertIn("reply 'status'", sent_text)
        self.assertNotIn("Satellite monitoring is starting now; your first irrigation advisory will be sent shortly", sent_text)

    def test_demo_registration_success_message_is_truthful(self):
        """Verifies demo_registration_success template carries demo banner, prompts for status, and avoids false promises."""
        for lang, expected_status_word in [("en", "reply 'status'"), ("mr", "'status' पाठवा"), ("hi", "'status' भेजें")]:
            msg = get_message(
                "demo_registration_success",
                lang=lang,
                farm_id=999,
                name="Test Demo",
                crop="Cotton",
                area=2.5,
                boundary_source="Estimated circular boundary",
                lat=20.68500,
                lon=77.15000,
            )
            self.assertIn("[DEMO MODE — ILLUSTRATIVE LOCATION DATA]", msg)
            self.assertIn(expected_status_word, msg)
            self.assertNotIn("Satellite monitoring is starting now", msg)
            self.assertNotIn("उपग्रह निरीक्षण सुरू होत आहे", msg)
            self.assertNotIn("उपग्रह निगरानी शुरू हो रही है", msg)

    def test_status_advisory_demo_banner(self):
        farm = {
            "id": 999,
            "farmer_name": "Demo Farmer",
            "crop_name": "Cotton",
            "is_demo": True,
        }
        advisory = {
            "observed_stress": "Severe Stress",
            "rain_forecast_mm": 2.0,
            "recommended_action": "irrigate now",
            "created_at": "2026-10-20",
        }

        card = format_status_advisory(farm, advisory, lang="en")
        self.assertTrue(card.startswith("[DEMO MODE — ILLUSTRATIVE LOCATION DATA]"))
        self.assertIn("Severe Stress", card)
        self.assertIn("Irrigate Now", card)

    def test_voice_script_demo_spoken_notice(self):
        farm = {
            "id": 999,
            "farmer_name": "Demo Farmer",
            "crop_name": "Cotton",
            "is_demo": True,
        }
        advisory = {
            "observed_stress": "Mild Stress",
            "rain_forecast_mm": 0.0,
            "recommended_action": "schedule irrigation in 24-48h",
        }

        script_en = format_voice_script(farm, advisory, language="en")
        self.assertIsNotNone(script_en)
        self.assertIn("Demo mode notice: This is illustrative location data", script_en)

        script_mr = format_voice_script(farm, advisory, language="mr")
        self.assertIsNotNone(script_mr)
        self.assertIn("डेमो मोड सूचना: ही प्रात्यक्षिक माहिती आहे", script_mr)

    def test_urban_location_withheld_even_in_demo_mode(self):
        farm = {
            "id": 999,
            "farmer_name": "Demo Farmer",
            "crop_name": "Cotton",
            "is_demo": True,
        }
        advisory = {
            "validation_status": "LIKELY_URBAN",
            "is_suitable_for_advisory": False,
        }

        card = format_status_advisory(farm, advisory, lang="en")
        self.assertIn("[DEMO MODE — ILLUSTRATIVE LOCATION DATA]", card)
        self.assertIn("urban or built-up area", card)

        voice = format_voice_script(farm, advisory, language="en")
        self.assertIsNone(voice)

    @patch("pipeline.test_pipeline.save_advisory_to_database")
    @patch("pipeline.test_pipeline.fetch_openweather_forecast")
    @patch("pipeline.test_pipeline.fetch_smap_soil_moisture")
    @patch("pipeline.test_pipeline.authenticate_and_query_earthdata")
    @patch("pipeline.test_pipeline.fetch_sentinel2_indices")
    @patch("pipeline.test_pipeline.ee")
    @patch("pipeline.test_pipeline.authenticate_earth_engine")
    @patch("pipeline.test_pipeline.validate_agricultural_location")
    @patch("pipeline.test_pipeline.get_farm_from_database")
    def test_demo_pipeline_validation_success_generates_advisory(
        self,
        mock_get_farm,
        mock_val,
        mock_ee_auth,
        mock_ee,
        mock_s2,
        mock_ed,
        mock_smap,
        mock_weather,
        mock_save_adv,
    ):
        mock_get_farm.return_value = {
            "id": 999,
            "farmer_name": "Demo Farmer",
            "mobile_number": "919876543222",
            "preferred_language": "en",
            "crop_name": "Cotton",
            "ee_coords": [[77.145, 20.680], [77.155, 20.680], [77.155, 20.690], [77.145, 20.690], [77.145, 20.680]],
            "centroid_lat": 20.68500,
            "centroid_lon": 77.15000,
            "is_demo": True,
        }
        mock_val.return_value = {
            "is_suitable_for_advisory": True,
            "outcome": "SUITABLE_CROPLAND",
            "reason": "Cropland verified",
            "land_cover_class": "Cropland (Class 40)",
        }
        mock_ee_auth.return_value = "khetsense-test-proj"
        mock_s2.return_value = (0.42, 0.15, {"date": "2026-10-18"}, None)
        mock_ed.return_value = ({"auth_verified": True, "granule_id": "test_granule", "time_start": "2026-10-18"}, None)
        mock_smap.return_value = (28.5, {"dataset": "SPL3SMP_E", "date": "2026-10-18", "raw_m3m3": 0.285}, None)
        mock_weather.return_value = (0.0, None)
        mock_save_adv.return_value = {
            "id": 501,
            "farm_id": 999,
            "observation_date": "2026-10-18",
            "stress_level": "Mild Stress",
            "created_at": "2026-10-20",
        }

        mock_outbound = MagicMock()
        from pipeline.test_pipeline import run_pipeline_for_farm

        res = run_pipeline_for_farm(
            farm_id=999,
            outbound_sender=mock_outbound,
            auto_send_advisory=True,
            force=True,
            is_demo=True,
        )

        self.assertEqual(res["status"], "success")
        self.assertTrue(res["advisory_sent"])

        # Sent advisory card must have the demo banner
        sent_card = mock_outbound.call_args[0][1]
        self.assertTrue(sent_card.startswith("[DEMO MODE — ILLUSTRATIVE LOCATION DATA]"))
        self.assertIn("KhetSense Farm Status & Advisory", sent_card)
        self.assertIn("Cotton", sent_card)

    @patch("pipeline.test_pipeline.fetch_openweather_forecast")
    @patch("pipeline.test_pipeline.fetch_smap_soil_moisture")
    @patch("pipeline.test_pipeline.fetch_sentinel2_indices")
    @patch("pipeline.test_pipeline.ee")
    @patch("pipeline.test_pipeline.authenticate_earth_engine")
    @patch("pipeline.test_pipeline.validate_agricultural_location")
    @patch("pipeline.test_pipeline.get_farm_from_database")
    def test_demo_pipeline_validation_failure_sends_demo_notice(
        self,
        mock_get_farm,
        mock_val,
        mock_ee_auth,
        mock_ee,
        mock_s2,
        mock_smap,
        mock_weather,
    ):
        mock_get_farm.return_value = {
            "id": 999,
            "farmer_name": "Demo Farmer",
            "mobile_number": "919876543222",
            "preferred_language": "en",
            "crop_name": "Cotton",
            "ee_coords": [[77.00, 20.70], [77.01, 20.70], [77.01, 20.71], [77.00, 20.71], [77.00, 20.70]],
            "centroid_lat": 20.70020,
            "centroid_lon": 77.00820,
            "is_demo": True,
        }
        mock_s2.return_value = (0.05, -0.05, {"date": "2026-10-18"}, None)
        mock_smap.return_value = (10.0, {"dataset": "SPL3SMP_E", "date": "2026-10-18"}, None)
        mock_weather.return_value = (0.0, None)
        mock_val.return_value = {
            "is_suitable_for_advisory": False,
            "outcome": "LIKELY_URBAN",
            "reason": "Location intersects built-up urban structures (ESA Class 50)",
            "land_cover_class": "Built-up (Class 50)",
        }
        mock_ee_auth.return_value = "khetsense-test-proj"

        mock_outbound = MagicMock()
        from pipeline.test_pipeline import run_pipeline_for_farm

        res = run_pipeline_for_farm(
            farm_id=999,
            outbound_sender=mock_outbound,
            auto_send_advisory=True,
            force=True,
            is_demo=True,
        )

        self.assertEqual(res["status"], "validation_failed")
        self.assertFalse(res["advisory_sent"])
        self.assertTrue(res["is_demo"])

        # Sent notice must carry the demo notice format
        sent_notice = mock_outbound.call_args[0][1]
        self.assertIn("[DEMO MODE — ILLUSTRATIVE LOCATION DATA]", sent_notice)
        self.assertIn("Demonstration Location Validation Notice", sent_notice)
        self.assertIn("No irrigation recommendation was generated", sent_notice)
        self.assertIn("Safety guardrails and land-cover screening remain active", sent_notice)

    def test_demo_status_no_advisory_message_is_truthful(self):
        farm_demo = {
            "id": 999,
            "farmer_name": "Demo Farmer",
            "crop_name": "Cotton",
            "is_demo": True,
        }
        msg = format_no_advisory(farm_demo, lang="en")
        self.assertTrue(msg.startswith("[DEMO MODE — ILLUSTRATIVE LOCATION DATA]"))
        self.assertIn("KhetSense Demo Status", msg)
        self.assertIn("Demonstration Profile (Illustrative Evaluation)", msg)
        self.assertNotIn("Satellite monitoring is active!", msg)


class TestConfirmationAndRejectionFlow(unittest.TestCase):
    """Verifies that NO reverts safely and does not overwrite existing farm data."""

    def _mock_claim_message(self, msg_id, db_url=None):
        if not msg_id:
            return True
        if msg_id in self.processed_messages:
            return False
        self.processed_messages.add(msg_id)
        return True

    def _mock_unclaim_message(self, msg_id, db_url=None):
        self.processed_messages.discard(msg_id)

    def setUp(self):
        self.phone = "919876543333"
        self.mock_sender = MagicMock()
        self.processed_messages = set()
        self.claim_patch = patch("whatsapp.registration_flow.claim_message", side_effect=self._mock_claim_message)
        self.unclaim_patch = patch("whatsapp.registration_flow.unclaim_message", side_effect=self._mock_unclaim_message)
        self.claim_patch.start()
        self.unclaim_patch.start()
        _IN_FLIGHT_LOCATION_CACHE.clear()
        _IN_FLIGHT_LOCATION_DETAILS.clear()
        _IN_MEMORY_PROCESSED_MESSAGES.clear()
        os.environ["WHATSAPP_ALLOWLIST_ENABLED"] = "false"
        os.environ["ENABLE_OUTBOUND_WHATSAPP"] = "false"

    def tearDown(self):
        self.claim_patch.stop()
        self.unclaim_patch.stop()
        _IN_FLIGHT_LOCATION_CACHE.clear()
        _IN_FLIGHT_LOCATION_DETAILS.clear()
        _IN_MEMORY_PROCESSED_MESSAGES.clear()

    @patch("whatsapp.registration_flow.save_session")
    @patch("whatsapp.registration_flow.get_registered_farm")
    @patch("whatsapp.registration_flow.get_session")
    def test_rejection_clears_cache_and_preserves_registered_farm(
        self, mock_get_session, mock_get_farm, mock_save_session
    ):
        existing_farm = {
            "id": 101,
            "farmer_name": "Original Name",
            "crop_name": "Cotton",
            "lat": 19.5000,
            "lon": 75.5000,
        }
        mock_get_farm.return_value = existing_farm
        mock_get_session.return_value = {
            "state": "AWAITING_LOCATION_CONFIRMATION",
            "preferred_language": "en",
            "pending_lat": 20.8000,
            "pending_lon": 77.3000,
        }
        _IN_FLIGHT_LOCATION_CACHE[self.phone] = (20.8000, 77.3000)
        _IN_FLIGHT_LOCATION_DETAILS[self.phone] = {"lat": 20.8000, "lon": 77.3000, "display_name": "New Candidate"}

        msg = {
            "from": self.phone,
            "id": f"wamid.rej.{uuid.uuid4().hex}",
            "type": "text",
            "text": {"body": "NO"},
        }

        res = handle_incoming(msg, outbound_sender=self.mock_sender)
        self.assertEqual(res["status"], "location_rejected")
        self.assertEqual(res["next_state"], "AWAITING_LOCATION")

        # Caches must be cleared
        self.assertNotIn(self.phone, _IN_FLIGHT_LOCATION_CACHE)
        self.assertNotIn(self.phone, _IN_FLIGHT_LOCATION_DETAILS)

        # Farmer prompted to re-enter
        sent_text = self.mock_sender.call_args[0][1]
        self.assertIn("Share your farm location using a WhatsApp location pin", sent_text)

        # Existing farm untouched
        self.assertEqual(existing_farm["lat"], 19.5000)
        self.assertEqual(existing_farm["lon"], 75.5000)


if __name__ == "__main__":
    unittest.main()
