#!/usr/bin/env python3
"""
KhetSense AI — Unit Tests for WhatsApp Registration Flow & Spatial Geometry
Tests:
1. Geodesic & Spatial calculations (point_to_square_polygon, WGS84 ellipsoidal scaling, provenance).
2. Crop normalization & regional transliterations.
3. Acreage parsing and boundary limits.
4. Indian spatial bounding box verification.
5. PII phone masking.
6. WhatsApp state machine transitions and retry deduplication.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Add parent and khetsense directories to sys.path
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
KHETSENSE_DIR = os.path.abspath(os.path.join(TEST_DIR, ".."))
PROJECT_ROOT = os.path.abspath(os.path.join(KHETSENSE_DIR, ".."))
for p in [KHETSENSE_DIR, PROJECT_ROOT]:
    if p not in sys.path:
        sys.path.insert(0, p)

from pipeline.geo_utils import point_to_square_polygon
from common.utils import (
    normalize_phone,
    mask_phone,
    is_valid_farmer_name,
    clean_farmer_name,
    is_affirmative_response,
)
from whatsapp.registration_flow import (
    normalize_crop,
    parse_acreage,
    validate_india_bounds,
    handle_incoming,
    claim_message,
    unclaim_message,
)
from pipeline.classifier import (
    classify_ndvi_stress,
    classify_soil_moisture_stress,
    get_more_severe,
    apply_rainfall_guardrail,
    generate_irrigation_advisory,
)
import pipeline.test_pipeline as test_pipeline_module
from whatsapp.messages import (
    WELCOME_PROMPT,
    NAME_CONFIRM_PROMPT,
    NAME_CONFIRM_INVALID_PROMPT,
    CROP_PROMPT,
    CROP_INVALID_PROMPT,
    ACREAGE_PROMPT,
    ACREAGE_INVALID_PROMPT,
    LOCATION_PROMPT,
    LOCATION_INVALID_PROMPT,
    LOCATION_OUT_OF_BOUNDS_PROMPT,
    REGISTRATION_SUCCESS,
    ALREADY_REGISTERED,
    RESET_SUCCESS,
)


class TestSpatialGeometry(unittest.TestCase):
    """Tests for geo_utils.point_to_square_polygon."""

    def test_default_100m_buffer(self):
        # Akola, Maharashtra test coordinates
        lat, lon = 20.50260, 77.14195
        res = point_to_square_polygon(lat=lat, lon=lon, side_meters=100.0)

        # 100m x 100m = 10,000 m^2 ≈ 2.47 acres
        self.assertEqual(res["side_meters"], 100.0)
        self.assertEqual(res["area_sq_m"], 10000.0)
        self.assertAlmostEqual(res["area_acres"], 2.47, places=2)

        # Polygon closed ring check
        coords = res["coordinates"]
        self.assertEqual(len(coords), 5)
        self.assertEqual(coords[0], coords[-1])  # closed ring

        # WKT check
        self.assertTrue(res["wkt"].startswith("POLYGON(("))
        self.assertEqual(res["pin_wkt"], f"POINT({lon} {lat})")

    def test_custom_acreage_buffer(self):
        # 2.0 acres test
        lat, lon = 20.50260, 77.14195
        res = point_to_square_polygon(lat=lat, lon=lon, farm_area_acres=2.0)

        # 2.0 acres = 8093.71 m^2 -> side ≈ 89.965 m
        self.assertAlmostEqual(res["side_meters"], 89.97, places=1)
        self.assertEqual(res["area_acres"], 2.0)
        self.assertAlmostEqual(res["area_sq_m"], 8093.71, delta=1.0)
        self.assertEqual(res["pin_wkt"], f"POINT({lon} {lat})")


class TestCropNormalization(unittest.TestCase):
    """Tests for crop name normalization and regional transliterations."""

    def test_exact_matches(self):
        self.assertEqual(normalize_crop("cotton"), "Cotton")
        self.assertEqual(normalize_crop("Soybean"), "Soybean")
        self.assertEqual(normalize_crop("WHEAT"), "Wheat")
        self.assertEqual(normalize_crop("rice"), "Rice")
        self.assertEqual(normalize_crop("sugarcane"), "Sugarcane")
        self.assertEqual(normalize_crop("maize"), "Maize")
        self.assertEqual(normalize_crop("onion"), "Onion")

    def test_regional_transliterations(self):
        # Cotton transliterations
        self.assertEqual(normalize_crop("kapas"), "Cotton")
        self.assertEqual(normalize_crop("kapaas"), "Cotton")

        # Wheat transliterations
        self.assertEqual(normalize_crop("gehu"), "Wheat")
        self.assertEqual(normalize_crop("gehun"), "Wheat")
        self.assertEqual(normalize_crop("gahu"), "Wheat")

        # Rice transliterations
        self.assertEqual(normalize_crop("paddy"), "Rice")
        self.assertEqual(normalize_crop("dhan"), "Rice")
        self.assertEqual(normalize_crop("chawal"), "Rice")

        # Pigeon Pea transliterations
        self.assertEqual(normalize_crop("tur"), "Pigeon Pea")
        self.assertEqual(normalize_crop("toor"), "Pigeon Pea")
        self.assertEqual(normalize_crop("arhar"), "Pigeon Pea")

        # Chickpea transliterations
        self.assertEqual(normalize_crop("chana"), "Chickpea")
        self.assertEqual(normalize_crop("gram"), "Chickpea")
        self.assertEqual(normalize_crop("bengal gram"), "Chickpea")

        # Sugarcane transliterations
        self.assertEqual(normalize_crop("ganna"), "Sugarcane")

        # Maize transliterations
        self.assertEqual(normalize_crop("corn"), "Maize")
        self.assertEqual(normalize_crop("makka"), "Maize")

        # Onion transliterations
        self.assertEqual(normalize_crop("pyaz"), "Onion")
        self.assertEqual(normalize_crop("kanda"), "Onion")

    def test_phrase_and_punctuation(self):
        self.assertEqual(normalize_crop("  I grow Cotton!  "), "Cotton")
        self.assertEqual(normalize_crop("my crop is soyabean"), "Soybean")
        self.assertEqual(normalize_crop("pigeon pea."), "Pigeon Pea")

    def test_unsupported_crop(self):
        self.assertIsNone(normalize_crop("dragonfruit"))
        self.assertIsNone(normalize_crop("random_weed_xyz"))
        self.assertIsNone(normalize_crop(""))
        self.assertIsNone(normalize_crop(None))


class TestAcreageParsing(unittest.TestCase):
    """Tests for acreage parsing and boundary limits."""

    def test_valid_numbers(self):
        self.assertEqual(parse_acreage("2"), (True, 2.0))
        self.assertEqual(parse_acreage("2.5"), (True, 2.5))
        self.assertEqual(parse_acreage("2.5 acres"), (True, 2.5))
        self.assertEqual(parse_acreage("10.0 acre"), (True, 10.0))
        self.assertEqual(parse_acreage("0.5"), (True, 0.5))

    def test_skip_and_default(self):
        self.assertEqual(parse_acreage("skip"), (True, None))
        self.assertEqual(parse_acreage("default"), (True, None))
        self.assertEqual(parse_acreage("don't know"), (True, None))
        self.assertEqual(parse_acreage("no"), (True, None))

    def test_out_of_bounds(self):
        # Min limit is 0.1, Max limit is 50.0
        self.assertEqual(parse_acreage("0.05"), (False, None))
        self.assertEqual(parse_acreage("55"), (False, None))
        self.assertEqual(parse_acreage("100 acres"), (False, None))
        self.assertEqual(parse_acreage("-2"), (False, None))

    def test_invalid_text(self):
        self.assertEqual(parse_acreage("very large field"), (False, None))
        self.assertEqual(parse_acreage(""), (False, None))
        self.assertEqual(parse_acreage(None), (False, None))


class TestBoundingBox(unittest.TestCase):
    """Tests for Indian geographic boundary validation."""

    def test_inside_india(self):
        # Akola, Maharashtra
        self.assertTrue(validate_india_bounds(20.5026, 77.1419))
        # New Delhi
        self.assertTrue(validate_india_bounds(28.6139, 77.2090))
        # Bengaluru, Karnataka
        self.assertTrue(validate_india_bounds(12.9716, 77.5946))
        # Guwahati, Assam
        self.assertTrue(validate_india_bounds(26.1445, 91.7362))

    def test_outside_india(self):
        # New York, USA
        self.assertFalse(validate_india_bounds(40.7128, -74.0060))
        # London, UK
        self.assertFalse(validate_india_bounds(51.5074, -0.1278))
        # Equator/Prime Meridian
        self.assertFalse(validate_india_bounds(0.0, 0.0))
        # North Pole
        self.assertFalse(validate_india_bounds(90.0, 0.0))


class TestPhoneMasking(unittest.TestCase):
    """Tests for PII phone number masking."""

    def test_masking(self):
        self.assertEqual(mask_phone("919876543210"), "...+3210")
        self.assertEqual(mask_phone("1234"), "...+1234")
        self.assertEqual(mask_phone("12"), "...+xxxx")
        self.assertEqual(mask_phone(None), "...+xxxx")


class TestPhoneNormalization(unittest.TestCase):
    """Tests for normalize_phone helper."""

    def test_standard_indian_10_digits(self):
        self.assertEqual(normalize_phone("9876543210"), "919876543210")
        self.assertEqual(normalize_phone("8765432109"), "918765432109")
        self.assertEqual(normalize_phone("7654321098"), "917654321098")
        self.assertEqual(normalize_phone("6543210987"), "916543210987")

    def test_already_international_format(self):
        self.assertEqual(normalize_phone("919876543210"), "919876543210")
        self.assertEqual(normalize_phone("+919876543210"), "919876543210")

    def test_formatted_with_symbols(self):
        self.assertEqual(normalize_phone("+91 (987) 654-3210"), "919876543210")
        self.assertEqual(normalize_phone("09876543210"), "919876543210")

    def test_empty_and_none(self):
        self.assertEqual(normalize_phone(""), "")
        self.assertEqual(normalize_phone(None), "")


class TestNameValidation(unittest.TestCase):
    """Tests for is_valid_farmer_name helper."""

    def test_valid_names(self):
        self.assertTrue(is_valid_farmer_name("Ramesh Patil"))
        self.assertTrue(is_valid_farmer_name("Sanjay Deshmukh"))
        self.assertTrue(is_valid_farmer_name("Amit"))
        self.assertTrue(is_valid_farmer_name("My name is Sunita"))

    def test_devanagari_names(self):
        # Native Devanagari / Marathi / Hindi farmer names
        self.assertTrue(is_valid_farmer_name("रमेश पाटील"))
        self.assertTrue(is_valid_farmer_name("संजय देशमुख"))
        self.assertTrue(is_valid_farmer_name("दिलीप मोरे"))
        self.assertTrue(is_valid_farmer_name("सुनीता गायकवाड"))
        self.assertTrue(is_valid_farmer_name("माझे नाव रमेश पाटील आहे"))

    def test_structural_formatting(self):
        # 1 to 4 words with allowed punctuation (spaces, ., -, ')
        self.assertTrue(is_valid_farmer_name("A. P. J. Kalam"))
        self.assertTrue(is_valid_farmer_name("O'Connor"))
        self.assertTrue(is_valid_farmer_name("Mary-Jane Watson"))
        self.assertTrue(is_valid_farmer_name("D. B. Patil"))

    def test_word_count_limits(self):
        # 1 to 4 words allowed
        self.assertTrue(is_valid_farmer_name("Ramesh"))
        self.assertTrue(is_valid_farmer_name("Ramesh Kumar Patil"))
        self.assertTrue(is_valid_farmer_name("Shri Ramesh Kumar Patil"))
        # 5 words rejected
        self.assertFalse(is_valid_farmer_name("Ram Lal Shyam Mohan Kumar"))

    def test_greetings_rejected(self):
        self.assertFalse(is_valid_farmer_name("Hi"))
        self.assertFalse(is_valid_farmer_name("Hello"))
        self.assertFalse(is_valid_farmer_name("Namaste"))
        self.assertFalse(is_valid_farmer_name("Good morning"))
        self.assertFalse(is_valid_farmer_name("Ok"))
        self.assertFalse(is_valid_farmer_name("राम राम"))

    def test_conversational_intents_rejected(self):
        self.assertFalse(is_valid_farmer_name("Hi, I want to register my farm"))
        self.assertFalse(is_valid_farmer_name("I want to register"))
        self.assertFalse(is_valid_farmer_name("Please register"))

    def test_invalid_lengths_and_digits(self):
        self.assertFalse(is_valid_farmer_name("A"))
        self.assertFalse(is_valid_farmer_name("12345"))
        self.assertFalse(is_valid_farmer_name("Farmer#123"))
        self.assertFalse(is_valid_farmer_name("..."))
        self.assertFalse(is_valid_farmer_name(""))
        self.assertFalse(is_valid_farmer_name(None))


class TestRegistrationStateMachine(unittest.TestCase):
    """Tests for WhatsApp registration flow state transitions and deduplication."""

    def setUp(self):
        self.mock_sender = MagicMock(return_value=True)
        self.sessions = {}
        self.processed = set()
        self.farms = {}

    def _mock_get_session(self, phone, db_url=None):
        return self.sessions.get(phone)

    def _mock_save_session(self, phone, state, name=None, crop=None, acreage_acres=None, db_url=None):
        sess = self.sessions.get(phone, {"phone": phone})
        sess["state"] = state
        if name is not None:
            sess["name"] = name
        if crop is not None:
            sess["crop"] = crop
        if acreage_acres is not None:
            sess["acreage_acres"] = acreage_acres
        self.sessions[phone] = sess

    def _mock_clear_session(self, phone, db_url=None):
        self.sessions.pop(phone, None)

    def _mock_claim_message(self, msg_id, db_url=None):
        if not msg_id:
            return True
        if msg_id in self.processed:
            return False
        self.processed.add(msg_id)
        return True

    def _mock_unclaim_message(self, msg_id, db_url=None):
        self.processed.discard(msg_id)

    def _mock_get_farm(self, phone, db_url=None):
        return self.farms.get(phone)

    @patch("whatsapp.registration_flow.get_registered_farm")
    @patch("whatsapp.registration_flow.get_session")
    @patch("whatsapp.registration_flow.save_session")
    @patch("whatsapp.registration_flow.clear_session")
    @patch("whatsapp.registration_flow.claim_message")
    @patch("whatsapp.registration_flow.unclaim_message")
    @patch("whatsapp.registration_flow.register_farmer_from_pin")
    def test_full_successful_registration_cycle(
        self,
        mock_reg_pin,
        mock_unclaim_msg,
        mock_claim_msg,
        mock_clear_sess,
        mock_save_sess,
        mock_get_sess,
        mock_get_farm,
    ):
        mock_get_farm.side_effect = self._mock_get_farm
        mock_get_sess.side_effect = self._mock_get_session
        mock_save_sess.side_effect = self._mock_save_session
        mock_clear_sess.side_effect = self._mock_clear_session
        mock_claim_msg.side_effect = self._mock_claim_message
        mock_unclaim_msg.side_effect = self._mock_unclaim_message

        phone = "919876543210"

        # Step 1: Initial greeting ("Hi") -> Starts session, sends WELCOME_PROMPT
        msg1 = {"id": "wamid.1", "from": phone, "type": "text", "text": {"body": "Hi"}}
        res1 = handle_incoming(msg1, outbound_sender=self.mock_sender)
        self.assertEqual(res1["status"], "session_started")
        self.assertEqual(res1["next_state"], "AWAITING_NAME")
        self.mock_sender.assert_called_with(phone, WELCOME_PROMPT)

        # Step 2: Farmer sends name ("Ramesh Patil") -> saves candidate, sends NAME_CONFIRM_PROMPT
        msg2 = {"id": "wamid.2", "from": phone, "type": "text", "text": {"body": "Ramesh Patil"}}
        res2 = handle_incoming(msg2, outbound_sender=self.mock_sender)
        self.assertEqual(res2["status"], "name_candidate_received")
        self.assertEqual(res2["next_state"], "AWAITING_NAME_CONFIRMATION")
        self.mock_sender.assert_called_with(phone, NAME_CONFIRM_PROMPT.format(name="Ramesh Patil"))

        # Step 2b: Farmer confirms name ("YES") -> saves confirmed name, sends CROP_PROMPT
        msg2b = {"id": "wamid.2b", "from": phone, "type": "text", "text": {"body": "YES"}}
        res2b = handle_incoming(msg2b, outbound_sender=self.mock_sender)
        self.assertEqual(res2b["status"], "name_confirmed")
        self.assertEqual(res2b["next_state"], "AWAITING_CROP")
        self.mock_sender.assert_called_with(phone, CROP_PROMPT.format(name="Ramesh Patil"))

        # Step 3: Farmer sends invalid crop ("dragonfruit") -> sends CROP_INVALID_PROMPT
        msg3_bad = {"id": "wamid.3", "from": phone, "type": "text", "text": {"body": "dragonfruit"}}
        res3_bad = handle_incoming(msg3_bad, outbound_sender=self.mock_sender)
        self.assertEqual(res3_bad["status"], "crop_unrecognized")
        self.mock_sender.assert_called_with(phone, CROP_INVALID_PROMPT)

        # Step 4: Farmer sends valid crop transliteration ("kapas") -> normalized to Cotton, sends ACREAGE_PROMPT
        msg3_good = {"id": "wamid.4", "from": phone, "type": "text", "text": {"body": "kapas"}}
        res3_good = handle_incoming(msg3_good, outbound_sender=self.mock_sender)
        self.assertEqual(res3_good["status"], "crop_saved")
        self.assertEqual(res3_good["crop"], "Cotton")
        self.assertEqual(res3_good["next_state"], "AWAITING_ACREAGE")
        self.mock_sender.assert_called_with(phone, ACREAGE_PROMPT.format(crop="Cotton"))

        # Step 5: Farmer sends acreage ("2.0 acres") -> saves acreage, sends LOCATION_PROMPT
        msg4 = {"id": "wamid.5", "from": phone, "type": "text", "text": {"body": "2.0 acres"}}
        res4 = handle_incoming(msg4, outbound_sender=self.mock_sender)
        self.assertEqual(res4["status"], "acreage_saved")
        self.assertEqual(res4["next_state"], "AWAITING_LOCATION")
        self.mock_sender.assert_called_with(phone, LOCATION_PROMPT.format(acreage_str="2.00 acres"))

        # Step 6: Farmer sends text instead of location -> sends LOCATION_INVALID_PROMPT
        msg5_bad = {"id": "wamid.6", "from": phone, "type": "text", "text": {"body": "I am at the farm"}}
        res5_bad = handle_incoming(msg5_bad, outbound_sender=self.mock_sender)
        self.assertEqual(res5_bad["status"], "location_required")
        self.mock_sender.assert_called_with(phone, LOCATION_INVALID_PROMPT)

        # Step 7: Farmer sends location outside India (New York) -> sends LOCATION_OUT_OF_BOUNDS_PROMPT
        msg5_ny = {
            "id": "wamid.7",
            "from": phone,
            "type": "location",
            "location": {"latitude": 40.7128, "longitude": -74.0060},
        }
        res5_ny = handle_incoming(msg5_ny, outbound_sender=self.mock_sender)
        self.assertEqual(res5_ny["status"], "location_out_of_bounds")
        self.mock_sender.assert_called_with(phone, LOCATION_OUT_OF_BOUNDS_PROMPT)

        # Step 8: Farmer sends valid farm location in India (Akola) -> triggers registration, sends REGISTRATION_SUCCESS
        mock_reg_pin.return_value = {
            "success": True,
            "farm_id": 42,
            "farmer_name": "Ramesh Patil",
            "crop_name": "Cotton",
            "farm_area": 2.0,
            "boundary_source": "estimated_from_pin",
        }
        msg5_good = {
            "id": "wamid.8",
            "from": phone,
            "type": "location",
            "location": {"latitude": 20.50260, "longitude": 77.14195},
        }
        res5_good = handle_incoming(msg5_good, outbound_sender=self.mock_sender)
        self.assertEqual(res5_good["status"], "registration_complete")
        self.assertEqual(res5_good["farm_id"], 42)
        mock_reg_pin.assert_called_once()

    @patch("whatsapp.registration_flow.get_registered_farm")
    @patch("whatsapp.registration_flow.get_session")
    @patch("whatsapp.registration_flow.save_session")
    @patch("whatsapp.registration_flow.clear_session")
    @patch("whatsapp.registration_flow.claim_message")
    @patch("whatsapp.registration_flow.unclaim_message")
    def test_message_deduplication(
        self,
        mock_unclaim_msg,
        mock_claim_msg,
        mock_clear_sess,
        mock_save_sess,
        mock_get_sess,
        mock_get_farm,
    ):
        mock_get_farm.side_effect = self._mock_get_farm
        mock_get_sess.side_effect = self._mock_get_session
        mock_save_sess.side_effect = self._mock_save_session
        mock_clear_sess.side_effect = self._mock_clear_session
        mock_claim_msg.side_effect = self._mock_claim_message
        mock_unclaim_msg.side_effect = self._mock_unclaim_message

        phone = "919876543210"
        msg = {"id": "duplicate.wamid.100", "from": phone, "type": "text", "text": {"body": "Hi"}}

        # First delivery
        res1 = handle_incoming(msg, outbound_sender=self.mock_sender)
        self.assertEqual(res1["status"], "session_started")

        # Second delivery (retry by Meta)
        res2 = handle_incoming(msg, outbound_sender=self.mock_sender)
        self.assertEqual(res2["status"], "duplicate")

    @patch("whatsapp.registration_flow.get_registered_farm")
    @patch("whatsapp.registration_flow.get_session")
    @patch("whatsapp.registration_flow.save_session")
    @patch("whatsapp.registration_flow.clear_session")
    @patch("whatsapp.registration_flow.claim_message")
    @patch("whatsapp.registration_flow.unclaim_message")
    def test_handler_fails_once_retry_succeeds(
        self,
        mock_unclaim_msg,
        mock_claim_msg,
        mock_clear_sess,
        mock_save_sess,
        mock_get_sess,
        mock_get_farm,
    ):
        """
        Verifies atomic claim & unclaim logic:
        When a handler encounters an unhandled exception during processing,
        it unclaims the message so Meta's subsequent retry delivery succeeds.
        """
        mock_get_farm.side_effect = self._mock_get_farm
        mock_get_sess.side_effect = self._mock_get_session
        mock_clear_sess.side_effect = self._mock_clear_session
        mock_claim_msg.side_effect = self._mock_claim_message
        mock_unclaim_msg.side_effect = self._mock_unclaim_message

        phone = "919876543210"
        msg = {"id": "wamid.retry.1", "from": phone, "type": "text", "text": {"body": "Hi"}}

        # Attempt 1: Handler encounters a database error during save_session
        with patch("whatsapp.registration_flow.save_session", side_effect=RuntimeError("DB dropped")):
            with self.assertRaises(RuntimeError):
                handle_incoming(msg, outbound_sender=self.mock_sender)

        # Verify that wamid.retry.1 was unclaimed after failure
        self.assertNotIn("wamid.retry.1", self.processed)

        # Attempt 2: Meta retries delivery with the exact same message_id, now succeeding
        mock_save_sess.side_effect = self._mock_save_session
        res = handle_incoming(msg, outbound_sender=self.mock_sender)
        self.assertEqual(res["status"], "session_started")
        self.assertIn("wamid.retry.1", self.processed)

    @patch("whatsapp.registration_flow.get_registered_farm")
    @patch("whatsapp.registration_flow.get_session")
    @patch("whatsapp.registration_flow.save_session")
    @patch("whatsapp.registration_flow.clear_session")
    @patch("whatsapp.registration_flow.claim_message")
    @patch("whatsapp.registration_flow.unclaim_message")
    def test_already_registered_user(
        self,
        mock_unclaim_msg,
        mock_claim_msg,
        mock_clear_sess,
        mock_save_sess,
        mock_get_sess,
        mock_get_farm,
    ):
        phone = "919999999999"
        self.farms[phone] = {
            "id": 1,
            "farmer_name": "Test Farmer",
            "crop_name": "Cotton",
        }
        mock_get_farm.side_effect = self._mock_get_farm
        mock_get_sess.side_effect = self._mock_get_session
        mock_save_sess.side_effect = self._mock_save_session
        mock_clear_sess.side_effect = self._mock_clear_session
        mock_claim_msg.side_effect = self._mock_claim_message
        mock_unclaim_msg.side_effect = self._mock_unclaim_message

        msg = {"id": "wamid.200", "from": phone, "type": "text", "text": {"body": "Hello"}}
        res = handle_incoming(msg, outbound_sender=self.mock_sender)
        self.assertEqual(res["status"], "already_registered")
        self.assertEqual(res["farm_id"], 1)

    @patch("whatsapp.registration_flow.get_registered_farm")
    @patch("whatsapp.registration_flow.get_session")
    @patch("whatsapp.registration_flow.save_session")
    @patch("whatsapp.registration_flow.clear_session")
    @patch("whatsapp.registration_flow.claim_message")
    @patch("whatsapp.registration_flow.unclaim_message")
    def test_devanagari_name_and_regional_affirmation_in_flow(
        self,
        mock_unclaim_msg,
        mock_claim_msg,
        mock_clear_sess,
        mock_save_sess,
        mock_get_sess,
        mock_get_farm,
    ):
        """Tests that Devanagari names pass validation and are confirmed via regional affirmation (e.g. Marathi 'हो')."""
        mock_get_farm.side_effect = self._mock_get_farm
        mock_get_sess.side_effect = self._mock_get_session
        mock_save_sess.side_effect = self._mock_save_session
        mock_clear_sess.side_effect = self._mock_clear_session
        mock_claim_msg.side_effect = self._mock_claim_message
        mock_unclaim_msg.side_effect = self._mock_unclaim_message

        phone = "919876543210"

        # Step 1: Greeting
        msg1 = {"id": "wamid.mr.1", "from": phone, "type": "text", "text": {"body": "नमस्कार"}}
        res1 = handle_incoming(msg1, outbound_sender=self.mock_sender)
        self.assertEqual(res1["status"], "session_started")
        self.assertEqual(res1["next_state"], "AWAITING_NAME")

        # Step 2: Farmer provides Devanagari name ("रमेश पाटील")
        msg2 = {"id": "wamid.mr.2", "from": phone, "type": "text", "text": {"body": "रमेश पाटील"}}
        res2 = handle_incoming(msg2, outbound_sender=self.mock_sender)
        self.assertEqual(res2["status"], "name_candidate_received")
        self.assertEqual(res2["next_state"], "AWAITING_NAME_CONFIRMATION")
        self.assertEqual(res2["candidate_name"], "रमेश पाटील")
        self.mock_sender.assert_called_with(phone, NAME_CONFIRM_PROMPT.format(name="रमेश पाटील"))

        # Step 3: Farmer confirms with Marathi 'हो' (Yes)
        msg3 = {"id": "wamid.mr.3", "from": phone, "type": "text", "text": {"body": "हो"}}
        res3 = handle_incoming(msg3, outbound_sender=self.mock_sender)
        self.assertEqual(res3["status"], "name_confirmed")
        self.assertEqual(res3["next_state"], "AWAITING_CROP")
        self.assertEqual(res3["name"], "रमेश पाटील")
        self.mock_sender.assert_called_with(phone, CROP_PROMPT.format(name="रमेश पाटील"))

    @patch("whatsapp.registration_flow.get_registered_farm")
    @patch("whatsapp.registration_flow.get_session")
    @patch("whatsapp.registration_flow.save_session")
    @patch("whatsapp.registration_flow.clear_session")
    @patch("whatsapp.registration_flow.claim_message")
    @patch("whatsapp.registration_flow.unclaim_message")
    def test_name_correction_in_confirmation_flow(
        self,
        mock_unclaim_msg,
        mock_claim_msg,
        mock_clear_sess,
        mock_save_sess,
        mock_get_sess,
        mock_get_farm,
    ):
        """Tests that a farmer can send a corrected name instead of YES."""
        mock_get_farm.side_effect = self._mock_get_farm
        mock_get_sess.side_effect = self._mock_get_session
        mock_save_sess.side_effect = self._mock_save_session
        mock_clear_sess.side_effect = self._mock_clear_session
        mock_claim_msg.side_effect = self._mock_claim_message
        mock_unclaim_msg.side_effect = self._mock_unclaim_message

        phone = "919876543210"

        # Step 1: Start
        handle_incoming({"id": "wamid.c.1", "from": phone, "type": "text", "text": {"body": "Start"}}, outbound_sender=self.mock_sender)

        # Step 2: First name provided
        res2 = handle_incoming({"id": "wamid.c.2", "from": phone, "type": "text", "text": {"body": "Ramesh"}}, outbound_sender=self.mock_sender)
        self.assertEqual(res2["next_state"], "AWAITING_NAME_CONFIRMATION")
        self.assertEqual(res2["candidate_name"], "Ramesh")

        # Step 3: Farmer provides corrected full name instead of YES
        res3 = handle_incoming({"id": "wamid.c.3", "from": phone, "type": "text", "text": {"body": "Ramesh Patil"}}, outbound_sender=self.mock_sender)
        self.assertEqual(res3["status"], "name_candidate_updated")
        self.assertEqual(res3["next_state"], "AWAITING_NAME_CONFIRMATION")
        self.assertEqual(res3["candidate_name"], "Ramesh Patil")
        self.mock_sender.assert_called_with(phone, NAME_CONFIRM_PROMPT.format(name="Ramesh Patil"))

        # Step 4: Farmer confirms corrected name
        res4 = handle_incoming({"id": "wamid.c.4", "from": phone, "type": "text", "text": {"body": "YES"}}, outbound_sender=self.mock_sender)
        self.assertEqual(res4["status"], "name_confirmed")
        self.assertEqual(res4["next_state"], "AWAITING_CROP")
        self.assertEqual(res4["name"], "Ramesh Patil")


class TestStressClassification(unittest.TestCase):
    """
    Synthetic-input unit tests for KhetSense stress classification & guardrails:
    - classify_ndvi_stress (No Stress > 0.6, Mild Stress 0.3-0.6, Severe Stress < 0.3)
    - classify_soil_moisture_stress (No Stress > 25%, Mild Stress 15-25%, Severe Stress < 15%)
    - get_more_severe
    - apply_rainfall_guardrail at 5.0 mm threshold
    - generate_irrigation_advisory
    """

    def test_ndvi_stress_branches(self):
        # > 0.6 -> No Stress
        self.assertEqual(classify_ndvi_stress(0.75), "No Stress")
        self.assertEqual(classify_ndvi_stress(0.61), "No Stress")
        # 0.3 to 0.6 -> Mild Stress
        self.assertEqual(classify_ndvi_stress(0.60), "Mild Stress")
        self.assertEqual(classify_ndvi_stress(0.45), "Mild Stress")
        self.assertEqual(classify_ndvi_stress(0.30), "Mild Stress")
        # < 0.3 -> Severe Stress
        self.assertEqual(classify_ndvi_stress(0.29), "Severe Stress")
        self.assertEqual(classify_ndvi_stress(0.10), "Severe Stress")
        # Missing
        self.assertEqual(classify_ndvi_stress(None), "Unknown")

    def test_soil_moisture_stress_branches(self):
        # > 25% -> No Stress
        self.assertEqual(classify_soil_moisture_stress(30.0), "No Stress")
        self.assertEqual(classify_soil_moisture_stress(25.1), "No Stress")
        # 15% to 25% -> Mild Stress
        self.assertEqual(classify_soil_moisture_stress(25.0), "Mild Stress")
        self.assertEqual(classify_soil_moisture_stress(20.0), "Mild Stress")
        self.assertEqual(classify_soil_moisture_stress(15.0), "Mild Stress")
        # < 15% -> Severe Stress
        self.assertEqual(classify_soil_moisture_stress(14.9), "Severe Stress")
        self.assertEqual(classify_soil_moisture_stress(8.0), "Severe Stress")
        # Missing
        self.assertEqual(classify_soil_moisture_stress(None), "Unknown")

    def test_more_severe_combination(self):
        self.assertEqual(get_more_severe("No Stress", "No Stress"), "No Stress")
        self.assertEqual(get_more_severe("No Stress", "Mild Stress"), "Mild Stress")
        self.assertEqual(get_more_severe("Mild Stress", "No Stress"), "Mild Stress")
        self.assertEqual(get_more_severe("Mild Stress", "Severe Stress"), "Severe Stress")
        self.assertEqual(get_more_severe("Severe Stress", "Mild Stress"), "Severe Stress")
        self.assertEqual(get_more_severe("Severe Stress", "Severe Stress"), "Severe Stress")

    def test_rainfall_guardrail_at_5mm_threshold(self):
        # Case A: Rain <= 5.0 mm -> Guardrail NOT triggered, stress stays unchanged
        final, status = apply_rainfall_guardrail("Severe Stress", 0.0)
        self.assertEqual(final, "Severe Stress")
        self.assertIn("Not Triggered", status)

        final, status = apply_rainfall_guardrail("Mild Stress", 3.2)
        self.assertEqual(final, "Mild Stress")
        self.assertIn("Not Triggered", status)

        # Boundary: Exactly 5.0 mm (threshold is strictly > 5.0 mm)
        final, status = apply_rainfall_guardrail("Severe Stress", 5.0)
        self.assertEqual(final, "Severe Stress")
        self.assertIn("Not Triggered", status)

        final, status = apply_rainfall_guardrail("Mild Stress", 5.0)
        self.assertEqual(final, "Mild Stress")
        self.assertIn("Not Triggered", status)

        # Case B: Rain > 5.0 mm -> Guardrail TRIGGERED
        # Severe Stress downgraded to Mild Stress
        final, status = apply_rainfall_guardrail("Severe Stress", 5.1)
        self.assertEqual(final, "Mild Stress")
        self.assertIn("Triggered", status)

        final, status = apply_rainfall_guardrail("Severe Stress", 15.0)
        self.assertEqual(final, "Mild Stress")
        self.assertIn("Triggered", status)

        # Mild Stress downgraded to No Stress
        final, status = apply_rainfall_guardrail("Mild Stress", 8.5)
        self.assertEqual(final, "No Stress")
        self.assertIn("Triggered", status)

        # No Stress stays No Stress
        final, status = apply_rainfall_guardrail("No Stress", 20.0)
        self.assertEqual(final, "No Stress")
        self.assertIn("Triggered", status)

        # Case C: Rain data missing / None -> Skipped
        final, status = apply_rainfall_guardrail("Severe Stress", None)
        self.assertEqual(final, "Severe Stress")
        self.assertIn("Skipped", status)

    def test_end_to_end_synthetic_classification(self):
        # Scenario 1: Severe drought scenario (NDVI=0.22, SM=11.5%, Rain=0mm)
        c_ndvi = classify_ndvi_stress(0.22)  # Severe
        c_sm = classify_soil_moisture_stress(11.5)  # Severe
        prelim = get_more_severe(c_ndvi, c_sm)  # Severe
        final, guardrail = apply_rainfall_guardrail(prelim, 0.0)  # Severe (no rain)
        self.assertEqual(final, "Severe Stress")
        adv = generate_irrigation_advisory(final, "Cotton", "Vegetative / Flowering", 0.0)
        self.assertIn("URGENT", adv)

        # Scenario 2: Severe stress with imminent rainfall (NDVI=0.22, SM=11.5%, Rain=18mm)
        final2, guardrail2 = apply_rainfall_guardrail(prelim, 18.0)  # Downgraded to Mild
        self.assertEqual(final2, "Mild Stress")
        self.assertIn("Triggered", guardrail2)
        adv2 = generate_irrigation_advisory(final2, "Cotton", "Vegetative / Flowering", 18.0)
        self.assertIn("ATTENTION", adv2)
        self.assertIn("monitoring incoming 18.0 mm rain", adv2)

        # Scenario 3: Mild stress downgraded by rain (NDVI=0.45, SM=21.0%, Rain=12mm)
        c_ndvi3 = classify_ndvi_stress(0.45)  # Mild
        c_sm3 = classify_soil_moisture_stress(21.0)  # Mild
        prelim3 = get_more_severe(c_ndvi3, c_sm3)  # Mild
        final3, guardrail3 = apply_rainfall_guardrail(prelim3, 12.0)  # Downgraded to No Stress
        self.assertEqual(final3, "No Stress")
        self.assertIn("Triggered", guardrail3)
        adv3 = generate_irrigation_advisory(final3, "Cotton", "Vegetative / Flowering", 12.0)
        self.assertIn("OPTIMAL", adv3)

        # Scenario 4: Optimal healthy canopy (NDVI=0.75, SM=28.0%, Rain=0mm)
        c_ndvi4 = classify_ndvi_stress(0.75)  # No Stress
        c_sm4 = classify_soil_moisture_stress(28.0)  # No Stress
        prelim4 = get_more_severe(c_ndvi4, c_sm4)  # No Stress
        final4, _ = apply_rainfall_guardrail(prelim4, 0.0)
        self.assertEqual(final4, "No Stress")
        adv4 = generate_irrigation_advisory(final4, "Cotton", "Vegetative / Flowering", 0.0)
        self.assertIn("OPTIMAL", adv4)

    def test_classifier_reexport_integrity(self):
        """Verifies that test_pipeline correctly re-exports functions from classifier.py without modification."""
        self.assertIs(test_pipeline_module.classify_ndvi_stress, classify_ndvi_stress)
        self.assertIs(test_pipeline_module.classify_soil_moisture_stress, classify_soil_moisture_stress)
        self.assertIs(test_pipeline_module.get_more_severe, get_more_severe)
        self.assertIs(test_pipeline_module.apply_rainfall_guardrail, apply_rainfall_guardrail)
        self.assertIs(test_pipeline_module.generate_irrigation_advisory, generate_irrigation_advisory)


class TestUtf8Logging(unittest.TestCase):
    """Tests for UTF-8 safe logging of Marathi / regional text without encoding errors."""

    def test_marathi_log_output(self):
        import io
        import logging

        stream = io.StringIO()
        test_logger = logging.getLogger("khetsense_marathi_test")
        test_logger.setLevel(logging.INFO)
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging.Formatter("%(message)s"))
        test_logger.addHandler(handler)

        marathi_msg = "शेतकरी नोंदणी यशस्वी: रमेश पाटील, अकोला (कपाशी पीक)"
        try:
            test_logger.info(marathi_msg)
            handler.flush()
            output = stream.getvalue()
            self.assertIn("शेतकरी नोंदणी यशस्वी", output)
            self.assertIn("रमेश पाटील", output)
        finally:
            test_logger.removeHandler(handler)


if __name__ == "__main__":
    unittest.main()
