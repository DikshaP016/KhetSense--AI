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
import socket
import unittest
from unittest.mock import MagicMock, patch
try:
    import requests
except ImportError:
    requests = None
try:
    import psycopg2
except ImportError:
    psycopg2 = None

# Add parent and khetsense directories to sys.path
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
KHETSENSE_DIR = os.path.abspath(os.path.join(TEST_DIR, ".."))
PROJECT_ROOT = os.path.abspath(os.path.join(KHETSENSE_DIR, ".."))
for p in [KHETSENSE_DIR, PROJECT_ROOT]:
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ["WHATSAPP_ALLOWLIST_ENABLED"] = "false"

from pipeline.geo_utils import point_to_square_polygon
from common.utils import (
    normalize_phone,
    mask_phone,
    is_valid_farmer_name,
    clean_farmer_name,
    is_affirmative_response,
    is_negative_response,
    parse_location_from_text,
    validate_lat_lon_bounds,
    resolve_google_maps_shortlink,
    extract_direct_coordinates,
)
from whatsapp.registration_flow import (
    normalize_crop,
    parse_acreage,
    validate_india_bounds,
    handle_incoming,
    claim_message,
    unclaim_message,
    get_latest_advisory,
    is_status_command,
    STATUS_COMMANDS,
    trigger_pipeline_for_farm,
    is_pipeline_running,
    extract_incoming_coordinates,
)
from pipeline.classifier import (
    classify_ndvi_stress,
    classify_soil_moisture_stress,
    get_more_severe,
    apply_rainfall_guardrail,
    generate_irrigation_advisory,
    validate_forecast_rainfall,
)
from common.config import (
    RAINFALL_CONFIG,
    ACTION_IRRIGATE_NOW,
    ACTION_IRRIGATE_LIGHTLY,
    ACTION_SCHEDULE_IRRIGATION,
    ACTION_DELAY_RECHECK,
    ACTION_HOLD_RECHECK,
    ACTION_NO_ACTION,
    ACTION_INSUFFICIENT_DATA,
)
import pipeline.test_pipeline as test_pipeline_module
from pipeline.location_validator import (
    validate_agricultural_location,
    VALIDATION_SUITABLE,
    VALIDATION_URBAN,
    VALIDATION_BARREN_UNCERTAIN,
    VALIDATION_INSUFFICIENT_IMAGERY,
    VALIDATION_INCOMPLETE_AUXILIARY,
    VALIDATION_INVALID_COORDINATES,
)
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
    STATUS_ADVISORY,
    STATUS_NO_ADVISORY,
    STATUS_NOT_REGISTERED,
    get_message,
    get_localized_crop,
    get_localized_advisory,
    format_status_advisory,
    format_no_advisory,
    format_unregistered_status,
    parse_language_choice,
    normalize_language,
    MESSAGES,
    ADVISORY_TEMPLATES,
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

    def _mock_save_session(self, phone, state, name=None, crop=None, acreage_acres=None, preferred_language=None, pending_lat=None, pending_lon=None, db_url=None, **kwargs):
        sess = self.sessions.get(phone, {"phone": phone})
        sess["state"] = state
        if name is not None:
            sess["name"] = name
        if crop is not None:
            sess["crop"] = crop
        if acreage_acres is not None:
            sess["acreage_acres"] = acreage_acres
        if preferred_language is not None:
            sess["preferred_language"] = preferred_language
        p_lat = pending_lat if pending_lat is not None else kwargs.get("pending_lat")
        if p_lat is not None:
            sess["pending_lat"] = p_lat
        p_lon = pending_lon if pending_lon is not None else kwargs.get("pending_lon")
        if p_lon is not None:
            sess["pending_lon"] = p_lon
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

        # Step 1: Initial greeting ("Hi") -> Starts session, sends welcome_and_language
        msg1 = {"id": "wamid.1", "from": phone, "type": "text", "text": {"body": "Hi"}}
        res1 = handle_incoming(msg1, outbound_sender=self.mock_sender)
        self.assertEqual(res1["status"], "session_started")
        self.assertEqual(res1["next_state"], "AWAITING_LANGUAGE")
        self.mock_sender.assert_called_with(phone, WELCOME_PROMPT)

        # Step 1b: Farmer chooses English ("1") -> saves language, sends language confirmation & name prompt
        msg1b = {"id": "wamid.1b", "from": phone, "type": "text", "text": {"body": "1"}}
        res1b = handle_incoming(msg1b, outbound_sender=self.mock_sender)
        self.assertEqual(res1b["status"], "language_selected")
        self.assertEqual(res1b["next_state"], "AWAITING_NAME")
        self.assertEqual(res1b["language"], "en")
        self.mock_sender.assert_called_with(phone, get_message("language_confirmed", lang="en"))

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

        # Step 5: Farmer sends acreage ("2.0 acres") -> saves acreage, sends location_choice_prompt
        msg4 = {"id": "wamid.5", "from": phone, "type": "text", "text": {"body": "2.0 acres"}}
        res4 = handle_incoming(msg4, outbound_sender=self.mock_sender)
        self.assertEqual(res4["status"], "acreage_saved")
        self.assertEqual(res4["next_state"], "AWAITING_LOCATION_CHOICE")
        self.mock_sender.assert_called_with(phone, get_message("location_choice_prompt", lang="en", acreage_str="2.00 acres"))

        # Step 5b: Farmer selects choice 1 (At farm) -> sends location_at_farm_prompt
        msg4b = {"id": "wamid.5b", "from": phone, "type": "text", "text": {"body": "1"}}
        res4b = handle_incoming(msg4b, outbound_sender=self.mock_sender)
        self.assertEqual(res4b["status"], "location_method_selected")
        self.assertEqual(res4b["next_state"], "AWAITING_LOCATION")
        self.mock_sender.assert_called_with(phone, get_message("location_at_farm_prompt", lang="en"))

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

        # Step 8: Farmer sends valid farm location in India (Akola) -> requests confirmation
        msg5_good = {
            "id": "wamid.8",
            "from": phone,
            "type": "location",
            "location": {"latitude": 20.50260, "longitude": 77.14195},
        }
        res5_good = handle_incoming(msg5_good, outbound_sender=self.mock_sender)
        self.assertEqual(res5_good["status"], "location_confirmation_requested")
        self.assertEqual(res5_good["next_state"], "AWAITING_LOCATION_CONFIRMATION")
        self.mock_sender.assert_called_with(phone, get_message("location_confirm_prompt", lang="en", lat=20.50260, lon=77.14195))

        # Step 9: Farmer confirms with YES -> completes registration and triggers pipeline
        mock_reg_pin.return_value = {
            "success": True,
            "farm_id": 42,
            "farmer_name": "Ramesh Patil",
            "crop_name": "Cotton",
            "farm_area": 2.0,
            "boundary_source": "estimated_from_pin",
        }
        mock_pipe_runner = MagicMock()
        msg5_confirm = {"id": "wamid.9", "from": phone, "type": "text", "text": {"body": "YES"}}
        res5_confirm = handle_incoming(msg5_confirm, outbound_sender=self.mock_sender, pipeline_runner=mock_pipe_runner)
        self.assertEqual(res5_confirm["status"], "registration_complete")
        self.assertEqual(res5_confirm["farm_id"], 42)
        self.assertTrue(res5_confirm.get("pipeline_triggered"))
        mock_pipe_runner.assert_called_once_with(
            farm_id=42,
            db_url=None,
            outbound_sender=self.mock_sender,
        )
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
        self.assertEqual(res1["next_state"], "AWAITING_LANGUAGE")

        # Step 1b: Farmer selects Marathi ("2")
        msg1b = {"id": "wamid.mr.1b", "from": phone, "type": "text", "text": {"body": "2"}}
        res1b = handle_incoming(msg1b, outbound_sender=self.mock_sender)
        self.assertEqual(res1b["status"], "language_selected")
        self.assertEqual(res1b["next_state"], "AWAITING_NAME")
        self.assertEqual(res1b["language"], "mr")
        self.mock_sender.assert_called_with(phone, get_message("language_confirmed", lang="mr"))

        # Step 2: Farmer provides Devanagari name ("रमेश पाटील")
        msg2 = {"id": "wamid.mr.2", "from": phone, "type": "text", "text": {"body": "रमेश पाटील"}}
        res2 = handle_incoming(msg2, outbound_sender=self.mock_sender)
        self.assertEqual(res2["status"], "name_candidate_received")
        self.assertEqual(res2["next_state"], "AWAITING_NAME_CONFIRMATION")
        self.assertEqual(res2["candidate_name"], "रमेश पाटील")
        self.mock_sender.assert_called_with(phone, get_message("name_confirm", lang="mr", name="रमेश पाटील"))

        # Step 3: Farmer confirms with Marathi 'हो' (Yes)
        msg3 = {"id": "wamid.mr.3", "from": phone, "type": "text", "text": {"body": "हो"}}
        res3 = handle_incoming(msg3, outbound_sender=self.mock_sender)
        self.assertEqual(res3["status"], "name_confirmed")
        self.assertEqual(res3["next_state"], "AWAITING_CROP")
        self.assertEqual(res3["name"], "रमेश पाटील")
        self.mock_sender.assert_called_with(phone, get_message("crop_prompt", lang="mr", name="रमेश पाटील"))

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
        res1 = handle_incoming({"id": "wamid.c.1", "from": phone, "type": "text", "text": {"body": "Start"}}, outbound_sender=self.mock_sender)
        self.assertEqual(res1["next_state"], "AWAITING_LANGUAGE")

        # Step 1b: Language selection (English)
        res1b = handle_incoming({"id": "wamid.c.1b", "from": phone, "type": "text", "text": {"body": "1"}}, outbound_sender=self.mock_sender)
        self.assertEqual(res1b["next_state"], "AWAITING_NAME")

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

    def test_boundaries_severe_stress_at_r1_and_r2(self):
        """
        Severe Stress boundary tests at R1 (5.0 mm) and R2 (15.0 mm):
        - Observed stress (Severe Stress) is NEVER modified by rainfall forecast.
        - recommended_action transitions:
            < R1 (0.0, 4.9 mm)         -> 'irrigate now' (guardrail not triggered)
            R1..R2 (5.0, 5.1, 14.9 mm) -> 'irrigate lightly, rain may not suffice' (guardrail triggered)
            >= R2 (15.0, 15.1 mm)      -> 'hold, re-check after rain' (guardrail triggered)
            Missing rain (None)        -> 'irrigate now' (guardrail not triggered)
        """
        # < R1: rain = 0.0 mm
        obs, act, trig = apply_rainfall_guardrail("Severe Stress", 0.0)
        self.assertEqual(obs, "Severe Stress")
        self.assertEqual(act, ACTION_IRRIGATE_NOW)
        self.assertFalse(trig)

        # < R1: rain = 4.9 mm
        obs, act, trig = apply_rainfall_guardrail("Severe Stress", 4.9)
        self.assertEqual(obs, "Severe Stress")
        self.assertEqual(act, ACTION_IRRIGATE_NOW)
        self.assertFalse(trig)

        # At R1: rain = 5.0 mm (boundary)
        obs, act, trig = apply_rainfall_guardrail("Severe Stress", 5.0)
        self.assertEqual(obs, "Severe Stress")
        self.assertEqual(act, ACTION_IRRIGATE_LIGHTLY)
        self.assertTrue(trig)

        # Just above R1: rain = 5.1 mm
        obs, act, trig = apply_rainfall_guardrail("Severe Stress", 5.1)
        self.assertEqual(obs, "Severe Stress")
        self.assertEqual(act, ACTION_IRRIGATE_LIGHTLY)
        self.assertTrue(trig)

        # Just below R2: rain = 14.9 mm
        obs, act, trig = apply_rainfall_guardrail("Severe Stress", 14.9)
        self.assertEqual(obs, "Severe Stress")
        self.assertEqual(act, ACTION_IRRIGATE_LIGHTLY)
        self.assertTrue(trig)

        # At R2: rain = 15.0 mm (boundary)
        obs, act, trig = apply_rainfall_guardrail("Severe Stress", 15.0)
        self.assertEqual(obs, "Severe Stress")
        self.assertEqual(act, ACTION_HOLD_RECHECK)
        self.assertTrue(trig)

        # Just above R2: rain = 15.1 mm
        obs, act, trig = apply_rainfall_guardrail("Severe Stress", 15.1)
        self.assertEqual(obs, "Severe Stress")
        self.assertEqual(act, ACTION_HOLD_RECHECK)
        self.assertTrue(trig)

        # Missing rain forecast: None
        obs, act, trig = apply_rainfall_guardrail("Severe Stress", None)
        self.assertEqual(obs, "Severe Stress")
        self.assertEqual(act, ACTION_IRRIGATE_NOW)
        self.assertFalse(trig)

    def test_boundaries_mild_stress_at_r1_and_r2(self):
        """
        Mild Stress boundary tests at R1 (5.0 mm) and R2 (15.0 mm):
        - Observed stress (Mild Stress) is NEVER modified by rainfall forecast.
        - recommended_action transitions:
            < R1 (0.0, 4.9 mm)         -> 'schedule irrigation in 24-48h' (guardrail not triggered)
            R1..R2 (5.0, 5.1, 14.9 mm) -> 'delay, re-check after rain' (guardrail triggered)
            >= R2 (15.0, 15.1 mm)      -> 'hold, re-check after rain' (guardrail triggered)
            Missing rain (None)        -> 'schedule irrigation in 24-48h' (guardrail not triggered)
        """
        # < R1: rain = 0.0 mm
        obs, act, trig = apply_rainfall_guardrail("Mild Stress", 0.0)
        self.assertEqual(obs, "Mild Stress")
        self.assertEqual(act, ACTION_SCHEDULE_IRRIGATION)
        self.assertFalse(trig)

        # < R1: rain = 4.9 mm
        obs, act, trig = apply_rainfall_guardrail("Mild Stress", 4.9)
        self.assertEqual(obs, "Mild Stress")
        self.assertEqual(act, ACTION_SCHEDULE_IRRIGATION)
        self.assertFalse(trig)

        # At R1: rain = 5.0 mm (boundary)
        obs, act, trig = apply_rainfall_guardrail("Mild Stress", 5.0)
        self.assertEqual(obs, "Mild Stress")
        self.assertEqual(act, ACTION_DELAY_RECHECK)
        self.assertTrue(trig)

        # Just above R1: rain = 5.1 mm
        obs, act, trig = apply_rainfall_guardrail("Mild Stress", 5.1)
        self.assertEqual(obs, "Mild Stress")
        self.assertEqual(act, ACTION_DELAY_RECHECK)
        self.assertTrue(trig)

        # Just below R2: rain = 14.9 mm
        obs, act, trig = apply_rainfall_guardrail("Mild Stress", 14.9)
        self.assertEqual(obs, "Mild Stress")
        self.assertEqual(act, ACTION_DELAY_RECHECK)
        self.assertTrue(trig)

        # At R2: rain = 15.0 mm (boundary)
        obs, act, trig = apply_rainfall_guardrail("Mild Stress", 15.0)
        self.assertEqual(obs, "Mild Stress")
        self.assertEqual(act, ACTION_HOLD_RECHECK)
        self.assertTrue(trig)

        # Just above R2: rain = 15.1 mm
        obs, act, trig = apply_rainfall_guardrail("Mild Stress", 15.1)
        self.assertEqual(obs, "Mild Stress")
        self.assertEqual(act, ACTION_HOLD_RECHECK)
        self.assertTrue(trig)

        # Missing rain forecast: None
        obs, act, trig = apply_rainfall_guardrail("Mild Stress", None)
        self.assertEqual(obs, "Mild Stress")
        self.assertEqual(act, ACTION_SCHEDULE_IRRIGATION)
        self.assertFalse(trig)

    def test_boundaries_no_stress_at_r1_and_r2(self):
        """
        No Stress boundary tests at R1 (5.0 mm) and R2 (15.0 mm):
        - Observed stress (No Stress) stays 'No Stress' across all bands.
        - recommended_action is always 'no action'.
        - guardrail_triggered is always False.
        """
        for rain in [0.0, 4.9, 5.0, 5.1, 14.9, 15.0, 15.1, 30.0, None]:
            obs, act, trig = apply_rainfall_guardrail("No Stress", rain)
            self.assertEqual(obs, "No Stress", f"Failed for rain={rain}")
            self.assertEqual(act, ACTION_NO_ACTION, f"Failed for rain={rain}")
            self.assertFalse(trig, f"Failed for rain={rain}")

    def test_end_to_end_synthetic_classification(self):
        # Scenario 1: Severe drought scenario (NDVI=0.22, SM=11.5%, Rain=0mm)
        c_ndvi = classify_ndvi_stress(0.22)  # Severe
        c_sm = classify_soil_moisture_stress(11.5)  # Severe
        prelim = get_more_severe(c_ndvi, c_sm)  # Severe
        obs, act, trig = apply_rainfall_guardrail(prelim, 0.0)
        self.assertEqual(obs, "Severe Stress")
        self.assertEqual(act, ACTION_IRRIGATE_NOW)
        self.assertFalse(trig)
        adv = generate_irrigation_advisory(obs, act, "Cotton", "Vegetative / Flowering", 0.0)
        self.assertIn("URGENT", adv)
        self.assertIn("Immediate irrigation recommended", adv)

        # Scenario 2: Severe stress with imminent heavy rainfall >= R2 (NDVI=0.22, SM=11.5%, Rain=18mm)
        obs2, act2, trig2 = apply_rainfall_guardrail(prelim, 18.0)
        self.assertEqual(obs2, "Severe Stress")  # Invariant!
        self.assertEqual(act2, ACTION_HOLD_RECHECK)
        self.assertTrue(trig2)
        adv2 = generate_irrigation_advisory(obs2, act2, "Cotton", "Vegetative / Flowering", 18.0)
        self.assertIn("MONITOR", adv2)
        self.assertIn("Hold irrigation and re-check after rain", adv2)

        # Scenario 3: Mild stress with moderate rainfall R1..R2 (NDVI=0.45, SM=21.0%, Rain=12mm)
        c_ndvi3 = classify_ndvi_stress(0.45)  # Mild
        c_sm3 = classify_soil_moisture_stress(21.0)  # Mild
        prelim3 = get_more_severe(c_ndvi3, c_sm3)  # Mild
        obs3, act3, trig3 = apply_rainfall_guardrail(prelim3, 12.0)
        self.assertEqual(obs3, "Mild Stress")  # Invariant!
        self.assertEqual(act3, ACTION_DELAY_RECHECK)
        self.assertTrue(trig3)
        adv3 = generate_irrigation_advisory(obs3, act3, "Cotton", "Vegetative / Flowering", 12.0)
        self.assertIn("MONITOR", adv3)
        self.assertIn("Delay irrigation and re-check after 12.0 mm forecast rain", adv3)

        # Scenario 4: Optimal healthy canopy (NDVI=0.75, SM=28.0%, Rain=0mm)
        c_ndvi4 = classify_ndvi_stress(0.75)  # No Stress
        c_sm4 = classify_soil_moisture_stress(28.0)  # No Stress
        prelim4 = get_more_severe(c_ndvi4, c_sm4)  # No Stress
        obs4, act4, trig4 = apply_rainfall_guardrail(prelim4, 0.0)
        self.assertEqual(obs4, "No Stress")
        self.assertEqual(act4, ACTION_NO_ACTION)
        self.assertFalse(trig4)
        adv4 = generate_irrigation_advisory(obs4, act4, "Cotton", "Vegetative / Flowering", 0.0)
        self.assertIn("OPTIMAL", adv4)

    def test_farm_2_real_satellite_classification(self):
        """
        Validates real-world Farm 2 readings:
        NDVI = 0.7248 (> 0.6 -> No Stress)
        Soil Moisture = 21.00% (15-25% -> Mild Stress)
        Worst-case preliminary = Mild Stress
        Rainfall 48h = 0.00 mm (< R1 5.0 mm -> Not Triggered)
        Expected observed stress = Mild Stress
        Expected recommended action = 'schedule irrigation in 24-48h'
        """
        ndvi_val = 0.7248
        sm_pct = 21.0
        rain_mm = 0.0

        c_ndvi = classify_ndvi_stress(ndvi_val)
        self.assertEqual(c_ndvi, "No Stress")

        c_sm = classify_soil_moisture_stress(sm_pct)
        self.assertEqual(c_sm, "Mild Stress")

        prelim = get_more_severe(c_ndvi, c_sm)
        self.assertEqual(prelim, "Mild Stress")

        obs_stress, rec_action, guardrail_triggered = apply_rainfall_guardrail(prelim, rain_mm)
        self.assertEqual(obs_stress, "Mild Stress")
        self.assertEqual(rec_action, ACTION_SCHEDULE_IRRIGATION)
        self.assertFalse(guardrail_triggered)

        adv = generate_irrigation_advisory(obs_stress, rec_action, "Cotton", "Vegetative / Flowering", rain_mm)
        self.assertIn("ATTENTION", adv)
        self.assertIn("Mild water stress detected", adv)
        self.assertIn("Schedule regular irrigation in the next 24-48 hours", adv)

    def test_severe_stress_rainfall_transition_at_r1_and_r2(self):
        """
        Validates the transition of recommended actions across R1 (5.0 mm) and R2 (15.0 mm)
        under the new rainfall policy:
        - Observed stress is NEVER modified by rainfall forecast (it remains Severe Stress in all bands).
        - No stress-level flip occurs (replacing the legacy cliff at 5.0 mm).
        - Recommended action transitions:
            4.9 mm (< R1)              -> ACTION_IRRIGATE_NOW
            5.0 mm & 5.1 mm (R1..R2)   -> ACTION_IRRIGATE_LIGHTLY
            15.0 mm (>= R2)            -> ACTION_HOLD_RECHECK
        """
        prelim = "Severe Stress"

        # 1. Below R1 (4.9 mm): Irrigate now
        obs_4_9, act_4_9, trig_4_9 = apply_rainfall_guardrail(prelim, 4.9)
        self.assertEqual(obs_4_9, "Severe Stress")
        self.assertEqual(act_4_9, ACTION_IRRIGATE_NOW)
        self.assertFalse(trig_4_9)
        adv_4_9 = generate_irrigation_advisory(obs_4_9, act_4_9, "Cotton", "Vegetative / Flowering", 4.9)
        self.assertTrue(adv_4_9.startswith("URGENT: Severe water stress"))
        self.assertIn("Immediate irrigation recommended", adv_4_9)

        # 2. At R1 (5.0 mm): Irrigate lightly
        obs_5_0, act_5_0, trig_5_0 = apply_rainfall_guardrail(prelim, 5.0)
        self.assertEqual(obs_5_0, "Severe Stress")  # Invariant: stress does NOT flip
        self.assertEqual(act_5_0, ACTION_IRRIGATE_LIGHTLY)
        self.assertTrue(trig_5_0)
        adv_5_0 = generate_irrigation_advisory(obs_5_0, act_5_0, "Cotton", "Vegetative / Flowering", 5.0)
        self.assertTrue(adv_5_0.startswith("ATTENTION: Severe water stress"))
        self.assertIn("Light irrigation recommended", adv_5_0)

        # 3. Just above R1 (5.1 mm): Irrigate lightly
        obs_5_1, act_5_1, trig_5_1 = apply_rainfall_guardrail(prelim, 5.1)
        self.assertEqual(obs_5_1, "Severe Stress")  # Invariant
        self.assertEqual(act_5_1, ACTION_IRRIGATE_LIGHTLY)
        self.assertTrue(trig_5_1)
        adv_5_1 = generate_irrigation_advisory(obs_5_1, act_5_1, "Cotton", "Vegetative / Flowering", 5.1)
        self.assertTrue(adv_5_1.startswith("ATTENTION: Severe water stress"))

        # 4. At R2 (15.0 mm): Hold and re-check
        obs_15_0, act_15_0, trig_15_0 = apply_rainfall_guardrail(prelim, 15.0)
        self.assertEqual(obs_15_0, "Severe Stress")  # Invariant
        self.assertEqual(act_15_0, ACTION_HOLD_RECHECK)
        self.assertTrue(trig_15_0)
        adv_15_0 = generate_irrigation_advisory(obs_15_0, act_15_0, "Cotton", "Vegetative / Flowering", 15.0)
        self.assertTrue(adv_15_0.startswith("MONITOR: Severe water stress"))
        self.assertIn("Hold irrigation and re-check after rain", adv_15_0)

    def test_classifier_reexport_integrity(self):
        """Verifies that test_pipeline correctly re-exports functions from classifier.py without modification."""
        self.assertIs(test_pipeline_module.classify_ndvi_stress, classify_ndvi_stress)
        self.assertIs(test_pipeline_module.classify_soil_moisture_stress, classify_soil_moisture_stress)
        self.assertIs(test_pipeline_module.get_more_severe, get_more_severe)
        self.assertIs(test_pipeline_module.apply_rainfall_guardrail, apply_rainfall_guardrail)
        self.assertIs(test_pipeline_module.generate_irrigation_advisory, generate_irrigation_advisory)
        self.assertIs(test_pipeline_module.validate_forecast_rainfall, validate_forecast_rainfall)

    def test_validate_forecast_rainfall_valid_inputs(self):
        """Verifies that valid non-negative finite numeric values and None pass validation."""
        self.assertIsNone(validate_forecast_rainfall(None))
        self.assertEqual(validate_forecast_rainfall(0.0), 0.0)
        self.assertEqual(validate_forecast_rainfall(0), 0.0)
        self.assertEqual(validate_forecast_rainfall(4.9), 4.9)
        self.assertEqual(validate_forecast_rainfall(5.0), 5.0)
        self.assertEqual(validate_forecast_rainfall(15.0), 15.0)
        self.assertEqual(validate_forecast_rainfall("12.5"), 12.5)

    def test_validate_forecast_rainfall_invalid_inputs(self):
        """Verifies that negative, NaN, Inf, non-numeric and boolean values raise ValueError or TypeError."""
        # Negative numbers
        with self.assertRaises(ValueError) as ctx:
            validate_forecast_rainfall(-0.01)
        self.assertIn("cannot be negative", str(ctx.exception))

        with self.assertRaises(ValueError):
            validate_forecast_rainfall(-5.0)

        # NaN and Infs
        with self.assertRaises(ValueError) as ctx:
            validate_forecast_rainfall(float("nan"))
        self.assertIn("NaN", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            validate_forecast_rainfall(float("inf"))
        self.assertIn("Infinity", str(ctx.exception))

        with self.assertRaises(ValueError):
            validate_forecast_rainfall(float("-inf"))

        # Non-numeric strings and containers
        with self.assertRaises(ValueError):
            validate_forecast_rainfall("not_a_number")

        with self.assertRaises(ValueError):
            validate_forecast_rainfall([])

        # Boolean values (subclass of int) must be rejected
        with self.assertRaises(TypeError) as ctx:
            validate_forecast_rainfall(True)
        self.assertIn("boolean", str(ctx.exception))

        with self.assertRaises(TypeError):
            validate_forecast_rainfall(False)

    def test_apply_rainfall_guardrail_input_validation(self):
        """Verifies that apply_rainfall_guardrail rejects invalid rainfall values instead of treating them as 0 mm."""
        # Negative rainfall must raise ValueError, not silently trigger dry baseline
        with self.assertRaises(ValueError):
            apply_rainfall_guardrail("Severe Stress", -1.0)

        with self.assertRaises(ValueError):
            apply_rainfall_guardrail("Mild Stress", -0.5)

        with self.assertRaises(ValueError):
            apply_rainfall_guardrail("No Stress", -10.0)

        # NaN and Inf must raise ValueError
        with self.assertRaises(ValueError):
            apply_rainfall_guardrail("Severe Stress", float("nan"))

        with self.assertRaises(ValueError):
            apply_rainfall_guardrail("Severe Stress", float("inf"))

        # Booleans must raise TypeError
        with self.assertRaises(TypeError):
            apply_rainfall_guardrail("Severe Stress", True)

    def test_observed_stress_invariance_exhaustive(self):
        """
        Exhaustively verifies that observed stress (NDVI + SMAP) is NEVER altered by rainfall
        across all categories and all rainfall amounts.
        """
        stress_levels = ["Severe Stress", "Mild Stress", "No Stress", "Unknown"]
        rainfall_values = [None, 0.0, 1.0, 4.9, 5.0, 5.1, 14.9, 15.0, 15.1, 50.0]

        for s in stress_levels:
            for r in rainfall_values:
                obs, act, trig = apply_rainfall_guardrail(s, r)
                self.assertEqual(obs, s, f"Observed stress mutated for stress={s!r}, rain={r}")
                if s == "No Stress":
                    self.assertEqual(act, ACTION_NO_ACTION)
                    self.assertFalse(trig)
                elif s == "Unknown":
                    self.assertEqual(act, ACTION_INSUFFICIENT_DATA)
                    self.assertFalse(trig)

    def test_generate_irrigation_advisory_backward_compatibility(self):
        """
        Verifies that generate_irrigation_advisory supports new 5-arg, legacy 4-arg,
        positional, keyword, and mixed calling conventions without runtime errors.
        """
        # 1. New 5-arg positional: (observed_stress, recommended_action, crop, stage, rain_48h)
        adv1 = generate_irrigation_advisory(
            "Severe Stress", ACTION_IRRIGATE_NOW, "Cotton", "Flowering", 0.0
        )
        self.assertIn("URGENT: Severe water stress detected for Cotton at Flowering stage", adv1)
        self.assertIn("(no forecast rain)", adv1)

        # 2. New 5-arg keyword call
        adv2 = generate_irrigation_advisory(
            observed_stress="Severe Stress",
            recommended_action=ACTION_IRRIGATE_NOW,
            crop="Cotton",
            stage="Flowering",
            rain_48h=0.0,
        )
        self.assertEqual(adv1, adv2)

        # 3. Legacy 4-arg positional: (final_stress, crop, stage, rain_48h)
        adv3 = generate_irrigation_advisory(
            "Severe Stress", "Cotton", "Flowering", 0.0
        )
        self.assertEqual(adv1, adv3)

        # 4. Legacy 4-arg keyword call (using final_stress)
        adv4 = generate_irrigation_advisory(
            final_stress="Severe Stress",
            crop="Cotton",
            stage="Flowering",
            rain_48h=0.0,
        )
        self.assertEqual(adv1, adv4)

        # 5. Mixed positional + keyword call
        adv5 = generate_irrigation_advisory(
            "Severe Stress",
            crop="Cotton",
            stage="Flowering",
            rain_48h=0.0,
        )
        self.assertEqual(adv1, adv5)

        # 6. Legacy 3-arg positional: (final_stress, crop, stage) -> rain defaults to None
        adv6 = generate_irrigation_advisory("Severe Stress", "Cotton", "Flowering")
        self.assertIn("URGENT: Severe water stress detected for Cotton at Flowering stage", adv6)
        self.assertIn("(forecast rain data unavailable)", adv6)

        # 7. Invalid rainfall in advisory call must raise ValueError
        with self.assertRaises(ValueError):
            generate_irrigation_advisory("Severe Stress", "Cotton", "Flowering", -2.0)

        with self.assertRaises(ValueError):
            generate_irrigation_advisory(
                observed_stress="Severe Stress",
                recommended_action=ACTION_IRRIGATE_NOW,
                crop="Cotton",
                stage="Flowering",
                rain_48h=-5.0,
            )

    def test_advisory_text_growth_stage_consistency(self):
        """
        Verifies that growth stage is consistently formatted across all 6 action templates
        when provided, and degrades cleanly to 'for {crop}' when stage is None/omitted.
        """
        stage_name = "Boll Development"
        crop_name = "Cotton"

        # Action: IRRIGATE_NOW
        adv = generate_irrigation_advisory("Severe Stress", ACTION_IRRIGATE_NOW, crop_name, stage_name, 0.0)
        self.assertIn(f"for {crop_name} at {stage_name} stage.", adv)

        # Action: IRRIGATE_LIGHTLY
        adv = generate_irrigation_advisory("Severe Stress", ACTION_IRRIGATE_LIGHTLY, crop_name, stage_name, 8.0)
        self.assertIn(f"for {crop_name} at {stage_name} stage.", adv)

        # Action: HOLD_RECHECK (Severe)
        adv = generate_irrigation_advisory("Severe Stress", ACTION_HOLD_RECHECK, crop_name, stage_name, 20.0)
        self.assertIn(f"for {crop_name} at {stage_name} stage,", adv)

        # Action: SCHEDULE_IRRIGATION
        adv = generate_irrigation_advisory("Mild Stress", ACTION_SCHEDULE_IRRIGATION, crop_name, stage_name, 0.0)
        self.assertIn(f"for {crop_name} at {stage_name} stage.", adv)

        # Action: DELAY_RECHECK
        adv = generate_irrigation_advisory("Mild Stress", ACTION_DELAY_RECHECK, crop_name, stage_name, 8.0)
        self.assertIn(f"for {crop_name} at {stage_name} stage.", adv)

        # Action: NO_ACTION
        adv = generate_irrigation_advisory("No Stress", ACTION_NO_ACTION, crop_name, stage_name, 0.0)
        self.assertIn(f"for {crop_name} at {stage_name} stage.", adv)

        # Omitted / None stage: must cleanly degrade without 'None' text
        adv_no_stage = generate_irrigation_advisory("Severe Stress", ACTION_IRRIGATE_NOW, crop_name, None, 0.0)
        self.assertIn(f"for {crop_name}.", adv_no_stage)
        self.assertNotIn("None", adv_no_stage)

    def test_advisory_missing_vs_zero_rain_distinction(self):
        """
        Verifies that advisory text clearly distinguishes unavailable forecast data
        from a confirmed 0.0 mm forecast.
        """
        # Severe Stress: Missing vs 0 mm
        adv_none = generate_irrigation_advisory("Severe Stress", "Cotton", "Vegetative", None)
        self.assertIn("(forecast rain data unavailable)", adv_none)
        self.assertNotIn("no forecast rain", adv_none)

        adv_zero = generate_irrigation_advisory("Severe Stress", "Cotton", "Vegetative", 0.0)
        self.assertIn("(no forecast rain)", adv_zero)
        self.assertNotIn("data unavailable", adv_zero)

        # Mild Stress: Missing vs 0 mm
        adv_mild_none = generate_irrigation_advisory("Mild Stress", "Cotton", "Vegetative", None)
        self.assertIn("(forecast rain data unavailable)", adv_mild_none)

        adv_mild_zero = generate_irrigation_advisory("Mild Stress", "Cotton", "Vegetative", 0.0)
        self.assertIn("(no forecast rain)", adv_mild_zero)

        # No Stress: Missing (no mention) vs 0 mm
        adv_no_none = generate_irrigation_advisory("No Stress", "Cotton", "Vegetative", None)
        self.assertNotIn("forecast rain", adv_no_none)

        adv_no_zero = generate_irrigation_advisory("No Stress", "Cotton", "Vegetative", 0.0)
        self.assertIn("(0.0 mm forecast rain)", adv_no_zero)


class TestMultilingualAndLanguageSelection(unittest.TestCase):
    """Tests for Stage 1: Multilingual support, language selection, and advisory localization."""

    def setUp(self):
        self.mock_sender = MagicMock(return_value=True)
        self.sessions = {}
        self.processed = set()
        self.farms = {}

    def _mock_get_session(self, phone, db_url=None):
        return self.sessions.get(phone)

    def _mock_save_session(self, phone, state, name=None, crop=None, acreage_acres=None, preferred_language=None, pending_lat=None, pending_lon=None, db_url=None, **kwargs):
        sess = self.sessions.get(phone, {"phone": phone})
        sess["state"] = state
        if name is not None:
            sess["name"] = name
        if crop is not None:
            sess["crop"] = crop
        if acreage_acres is not None:
            sess["acreage_acres"] = acreage_acres
        if preferred_language is not None:
            sess["preferred_language"] = preferred_language
        p_lat = pending_lat if pending_lat is not None else kwargs.get("pending_lat")
        if p_lat is not None:
            sess["pending_lat"] = p_lat
        p_lon = pending_lon if pending_lon is not None else kwargs.get("pending_lon")
        if p_lon is not None:
            sess["pending_lon"] = p_lon
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

    def _mock_update_farmer_language(self, phone, lang, db_url=None):
        if phone in self.farms:
            self.farms[phone]["preferred_language"] = lang
            return True
        return False

    def test_parse_language_choice_numeric_and_text(self):
        # English
        self.assertEqual(parse_language_choice("1"), "en")
        self.assertEqual(parse_language_choice("1."), "en")
        self.assertEqual(parse_language_choice("English"), "en")
        self.assertEqual(parse_language_choice("english"), "en")
        self.assertEqual(parse_language_choice("EN"), "en")
        self.assertEqual(parse_language_choice("इंग्रजी"), "en")

        # Marathi
        self.assertEqual(parse_language_choice("2"), "mr")
        self.assertEqual(parse_language_choice("2)"), "mr")
        self.assertEqual(parse_language_choice("Marathi"), "mr")
        self.assertEqual(parse_language_choice("marathi"), "mr")
        self.assertEqual(parse_language_choice("मराठी"), "mr")
        self.assertEqual(parse_language_choice("mr"), "mr")

        # Hindi
        self.assertEqual(parse_language_choice("3"), "hi")
        self.assertEqual(parse_language_choice("3."), "hi")
        self.assertEqual(parse_language_choice("Hindi"), "hi")
        self.assertEqual(parse_language_choice("hindi"), "hi")
        self.assertEqual(parse_language_choice("हिंदी"), "hi")
        self.assertEqual(parse_language_choice("हिन्दी"), "hi")
        self.assertEqual(parse_language_choice("hi"), "hi")

        # Invalid
        self.assertIsNone(parse_language_choice("french"))
        self.assertIsNone(parse_language_choice("4"))
        self.assertIsNone(parse_language_choice(""))
        self.assertIsNone(parse_language_choice(None))

    def test_normalize_language(self):
        self.assertEqual(normalize_language("en"), "en")
        self.assertEqual(normalize_language("mr"), "mr")
        self.assertEqual(normalize_language("hi"), "hi")
        self.assertEqual(normalize_language("EN"), "en")
        self.assertEqual(normalize_language("MR"), "mr")
        self.assertEqual(normalize_language(None), "en")
        self.assertEqual(normalize_language("es"), "en")

    @patch("whatsapp.registration_flow.get_registered_farm")
    @patch("whatsapp.registration_flow.get_session")
    @patch("whatsapp.registration_flow.save_session")
    @patch("whatsapp.registration_flow.clear_session")
    @patch("whatsapp.registration_flow.claim_message")
    @patch("whatsapp.registration_flow.unclaim_message")
    def test_invalid_language_selection_retries(
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

        phone = "919876543222"

        # Initial message starts session in AWAITING_LANGUAGE
        res1 = handle_incoming({"id": "wamid.l1", "from": phone, "type": "text", "text": {"body": "Hi"}}, outbound_sender=self.mock_sender)
        self.assertEqual(res1["status"], "session_started")
        self.assertEqual(res1["next_state"], "AWAITING_LANGUAGE")

        # Farmer sends invalid language "spanish"
        res2 = handle_incoming({"id": "wamid.l2", "from": phone, "type": "text", "text": {"body": "spanish"}}, outbound_sender=self.mock_sender)
        self.assertEqual(res2["status"], "invalid_language")
        self.assertEqual(res2["state"], "AWAITING_LANGUAGE")
        self.mock_sender.assert_called_with(phone, get_message("language_invalid", lang="en"))

        # Farmer sends valid option "2" (Marathi)
        res3 = handle_incoming({"id": "wamid.l3", "from": phone, "type": "text", "text": {"body": "2"}}, outbound_sender=self.mock_sender)
        self.assertEqual(res3["status"], "language_selected")
        self.assertEqual(res3["next_state"], "AWAITING_NAME")
        self.assertEqual(res3["language"], "mr")
        self.mock_sender.assert_called_with(phone, get_message("language_confirmed", lang="mr"))

    @patch("whatsapp.registration_flow.get_registered_farm")
    @patch("whatsapp.registration_flow.get_session")
    @patch("whatsapp.registration_flow.save_session")
    @patch("whatsapp.registration_flow.clear_session")
    @patch("whatsapp.registration_flow.claim_message")
    @patch("whatsapp.registration_flow.unclaim_message")
    @patch("whatsapp.registration_flow.register_farmer_from_pin")
    def test_full_marathi_registration_flow(
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

        phone = "919876543233"

        # Step 1: Greeting
        res1 = handle_incoming({"id": "wamid.m1", "from": phone, "type": "text", "text": {"body": "नमस्कार"}}, outbound_sender=self.mock_sender)
        self.assertEqual(res1["status"], "session_started")
        self.assertEqual(res1["next_state"], "AWAITING_LANGUAGE")

        # Step 2: Select Marathi
        res2 = handle_incoming({"id": "wamid.m2", "from": phone, "type": "text", "text": {"body": "मराठी"}}, outbound_sender=self.mock_sender)
        self.assertEqual(res2["status"], "language_selected")
        self.assertEqual(res2["language"], "mr")
        self.mock_sender.assert_called_with(phone, get_message("language_confirmed", lang="mr"))

        # Step 3: Name
        res3 = handle_incoming({"id": "wamid.m3", "from": phone, "type": "text", "text": {"body": "तुकाराम पाटील"}}, outbound_sender=self.mock_sender)
        self.assertEqual(res3["status"], "name_candidate_received")
        self.assertEqual(res3["candidate_name"], "तुकाराम पाटील")
        self.mock_sender.assert_called_with(phone, get_message("name_confirm", lang="mr", name="तुकाराम पाटील"))

        # Step 4: Affirmation ("हो")
        res4 = handle_incoming({"id": "wamid.m4", "from": phone, "type": "text", "text": {"body": "हो"}}, outbound_sender=self.mock_sender)
        self.assertEqual(res4["status"], "name_confirmed")
        self.assertEqual(res4["next_state"], "AWAITING_CROP")
        self.mock_sender.assert_called_with(phone, get_message("crop_prompt", lang="mr", name="तुकाराम पाटील"))

        # Step 5: Crop in Marathi ("कापूस")
        res5 = handle_incoming({"id": "wamid.m5", "from": phone, "type": "text", "text": {"body": "कापूस"}}, outbound_sender=self.mock_sender)
        self.assertEqual(res5["status"], "crop_saved")
        self.assertEqual(res5["crop"], "Cotton")
        self.mock_sender.assert_called_with(phone, get_message("acreage_prompt", lang="mr", crop=get_localized_crop("Cotton", "mr")))

        # Step 6: Acreage ("3.5 एकर")
        res6 = handle_incoming({"id": "wamid.m6", "from": phone, "type": "text", "text": {"body": "3.5 एकर"}}, outbound_sender=self.mock_sender)
        self.assertEqual(res6["status"], "acreage_saved")
        self.assertEqual(res6["acreage_acres"], 3.5)
        self.assertEqual(res6["next_state"], "AWAITING_LOCATION_CHOICE")
        self.mock_sender.assert_called_with(phone, get_message("location_choice_prompt", lang="mr", acreage_str="3.50 एकर"))

        # Step 6b: Select choice 1 (At farm)
        res6b = handle_incoming({"id": "wamid.m6b", "from": phone, "type": "text", "text": {"body": "1"}}, outbound_sender=self.mock_sender)
        self.assertEqual(res6b["status"], "location_method_selected")
        self.assertEqual(res6b["next_state"], "AWAITING_LOCATION")
        self.mock_sender.assert_called_with(phone, get_message("location_at_farm_prompt", lang="mr"))

        # Step 7: Location Pin
        loc_msg = {
            "id": "wamid.m7",
            "from": phone,
            "type": "location",
            "location": {"latitude": 20.5026, "longitude": 77.1419},
        }
        res7 = handle_incoming(loc_msg, outbound_sender=self.mock_sender)
        self.assertEqual(res7["status"], "location_confirmation_requested")
        self.assertEqual(res7["next_state"], "AWAITING_LOCATION_CONFIRMATION")
        self.mock_sender.assert_called_with(phone, get_message("location_confirm_prompt", lang="mr", lat=20.5026, lon=77.1419))

        # Step 8: Confirm with Marathi affirmative ("हो")
        mock_reg_pin.return_value = {
            "success": True,
            "farm_id": 55,
            "farmer_name": "तुकाराम पाटील",
            "crop_name": "Cotton",
            "farm_area": 3.5,
            "boundary_source": "estimated_from_pin",
        }
        confirm_msg = {"id": "wamid.m8", "from": phone, "type": "text", "text": {"body": "हो"}}
        res8 = handle_incoming(confirm_msg, outbound_sender=self.mock_sender)
        self.assertEqual(res8["status"], "registration_complete")
        self.assertEqual(res8["preferred_language"], "mr")
        mock_reg_pin.assert_called_once()
        self.assertEqual(mock_reg_pin.call_args[1]["preferred_language"], "mr")

    @patch("whatsapp.registration_flow.get_registered_farm")
    @patch("whatsapp.registration_flow.get_session")
    @patch("whatsapp.registration_flow.save_session")
    @patch("whatsapp.registration_flow.clear_session")
    @patch("whatsapp.registration_flow.claim_message")
    @patch("whatsapp.registration_flow.unclaim_message")
    @patch("whatsapp.registration_flow.register_farmer_from_pin")
    def test_full_hindi_registration_flow(
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

        phone = "919876543244"

        # Step 1: Greeting
        res1 = handle_incoming({"id": "wamid.h1", "from": phone, "type": "text", "text": {"body": "नमस्ते"}}, outbound_sender=self.mock_sender)
        self.assertEqual(res1["next_state"], "AWAITING_LANGUAGE")

        # Step 2: Select Hindi ("3")
        res2 = handle_incoming({"id": "wamid.h2", "from": phone, "type": "text", "text": {"body": "3"}}, outbound_sender=self.mock_sender)
        self.assertEqual(res2["status"], "language_selected")
        self.assertEqual(res2["language"], "hi")
        self.mock_sender.assert_called_with(phone, get_message("language_confirmed", lang="hi"))

        # Step 3: Name
        res3 = handle_incoming({"id": "wamid.h3", "from": phone, "type": "text", "text": {"body": "राजेश शर्मा"}}, outbound_sender=self.mock_sender)
        self.assertEqual(res3["status"], "name_candidate_received")
        self.assertEqual(res3["candidate_name"], "राजेश शर्मा")
        self.mock_sender.assert_called_with(phone, get_message("name_confirm", lang="hi", name="राजेश शर्मा"))

        # Step 4: Affirmation ("हाँ")
        res4 = handle_incoming({"id": "wamid.h4", "from": phone, "type": "text", "text": {"body": "हाँ"}}, outbound_sender=self.mock_sender)
        self.assertEqual(res4["status"], "name_confirmed")
        self.assertEqual(res4["next_state"], "AWAITING_CROP")

        # Step 5: Crop in Hindi ("गेहूं")
        res5 = handle_incoming({"id": "wamid.h5", "from": phone, "type": "text", "text": {"body": "गेहूं"}}, outbound_sender=self.mock_sender)
        self.assertEqual(res5["status"], "crop_saved")
        self.assertEqual(res5["crop"], "Wheat")

        # Step 6: Acreage skip ("skip")
        res6 = handle_incoming({"id": "wamid.h6", "from": phone, "type": "text", "text": {"body": "skip"}}, outbound_sender=self.mock_sender)
        self.assertEqual(res6["status"], "acreage_saved")
        self.assertIsNone(res6["acreage_acres"])
        self.assertEqual(res6["next_state"], "AWAITING_LOCATION_CHOICE")
        self.mock_sender.assert_called_with(phone, get_message("location_choice_prompt", lang="hi", acreage_str="मानक आकार (2.5 एकड़ / 1.0 हेक्टेयर)"))

        # Step 6b: Select choice 2 (Away from farm)
        res6b = handle_incoming({"id": "wamid.h6b", "from": phone, "type": "text", "text": {"body": "2"}}, outbound_sender=self.mock_sender)
        self.assertEqual(res6b["status"], "location_method_selected")
        self.assertEqual(res6b["next_state"], "AWAITING_LOCATION")
        self.mock_sender.assert_called_with(phone, get_message("location_away_prompt", lang="hi"))

        # Step 7: Location
        loc_msg = {
            "id": "wamid.h7",
            "from": phone,
            "type": "location",
            "location": {"latitude": 21.0, "longitude": 78.0},
        }
        mock_pipe_runner = MagicMock()
        res7 = handle_incoming(loc_msg, outbound_sender=self.mock_sender, pipeline_runner=mock_pipe_runner)
        self.assertEqual(res7["status"], "location_confirmation_requested")
        self.assertEqual(res7["next_state"], "AWAITING_LOCATION_CONFIRMATION")
        self.mock_sender.assert_called_with(phone, get_message("location_confirm_prompt", lang="hi", lat=21.0, lon=78.0))

        # Step 8: Confirm with Hindi affirmative ("हाँ")
        mock_reg_pin.return_value = {
            "success": True,
            "farm_id": 77,
            "farmer_name": "राजेश शर्मा",
            "crop_name": "Wheat",
            "farm_area": 2.47,
            "boundary_source": "estimated_from_pin",
        }
        confirm_msg = {"id": "wamid.h8", "from": phone, "type": "text", "text": {"body": "हाँ"}}
        res8 = handle_incoming(confirm_msg, outbound_sender=self.mock_sender, pipeline_runner=mock_pipe_runner)
        self.assertEqual(res8["status"], "registration_complete")
        self.assertEqual(res8["preferred_language"], "hi")
        mock_reg_pin.assert_called_once()
        self.assertEqual(mock_reg_pin.call_args[1]["preferred_language"], "hi")

        self.assertEqual(res8["preferred_language"], "hi")
        self.assertTrue(res8.get("pipeline_triggered"))
        mock_pipe_runner.assert_called_once_with(
            farm_id=77,
            db_url=None,
            outbound_sender=self.mock_sender,
        )
        self.assertEqual(mock_reg_pin.call_args[1]["preferred_language"], "hi")

    @patch("whatsapp.registration_flow.get_registered_farm")
    @patch("whatsapp.registration_flow.get_session")
    @patch("whatsapp.registration_flow.save_session")
    @patch("whatsapp.registration_flow.clear_session")
    @patch("whatsapp.registration_flow.claim_message")
    @patch("whatsapp.registration_flow.unclaim_message")
    @patch("whatsapp.registration_flow.update_farmer_language")
    def test_registered_farmer_language_change_command(
        self,
        mock_update_lang,
        mock_unclaim_msg,
        mock_claim_msg,
        mock_clear_sess,
        mock_save_sess,
        mock_get_sess,
        mock_get_farm,
    ):
        phone = "919999888877"
        self.farms[phone] = {
            "id": 10,
            "farmer_name": "Vinod Deshmukh",
            "crop_name": "Soybean",
            "preferred_language": "en",
        }
        mock_get_farm.side_effect = self._mock_get_farm
        mock_get_sess.side_effect = self._mock_get_session
        mock_save_sess.side_effect = self._mock_save_session
        mock_clear_sess.side_effect = self._mock_clear_session
        mock_claim_msg.side_effect = self._mock_claim_message
        mock_unclaim_msg.side_effect = self._mock_unclaim_message
        mock_update_lang.side_effect = self._mock_update_farmer_language

        # Farmer sends 'language'
        msg1 = {"id": "wamid.lc.1", "from": phone, "type": "text", "text": {"body": "language"}}
        res1 = handle_incoming(msg1, outbound_sender=self.mock_sender)
        self.assertEqual(res1["status"], "language_change_requested")
        self.assertEqual(res1["next_state"], "CHANGING_LANGUAGE")
        self.mock_sender.assert_called_with(phone, get_message("language_change_prompt", lang="en"))

        # Farmer selects '2' (Marathi)
        msg2 = {"id": "wamid.lc.2", "from": phone, "type": "text", "text": {"body": "2"}}
        res2 = handle_incoming(msg2, outbound_sender=self.mock_sender)
        self.assertEqual(res2["status"], "language_updated")
        self.assertEqual(res2["language"], "mr")
        self.mock_sender.assert_called_with(phone, get_message("language_updated", lang="mr"))
        mock_update_lang.assert_called_with(phone, "mr", None)

    @patch("whatsapp.registration_flow.get_registered_farm")
    @patch("whatsapp.registration_flow.get_session")
    @patch("whatsapp.registration_flow.save_session")
    @patch("whatsapp.registration_flow.clear_session")
    @patch("whatsapp.registration_flow.claim_message")
    @patch("whatsapp.registration_flow.unclaim_message")
    def test_registered_farmer_without_preference_defaults_to_english(
        self,
        mock_unclaim_msg,
        mock_claim_msg,
        mock_clear_sess,
        mock_save_sess,
        mock_get_sess,
        mock_get_farm,
    ):
        phone = "919999888800"
        self.farms[phone] = {
            "id": 11,
            "farmer_name": "Legacy Farmer",
            "crop_name": "Cotton",
            "preferred_language": None,
        }
        mock_get_farm.side_effect = self._mock_get_farm
        mock_get_sess.side_effect = self._mock_get_session
        mock_save_sess.side_effect = self._mock_save_session
        mock_clear_sess.side_effect = self._mock_clear_session
        mock_claim_msg.side_effect = self._mock_claim_message
        mock_unclaim_msg.side_effect = self._mock_unclaim_message

        msg = {"id": "wamid.leg.1", "from": phone, "type": "text", "text": {"body": "Hello"}}
        res = handle_incoming(msg, outbound_sender=self.mock_sender)
        self.assertEqual(res["status"], "already_registered")
        self.mock_sender.assert_called_with(
            phone,
            get_message("already_registered", lang="en", farm_id=11, name="Legacy Farmer", crop="Cotton")
        )

    def test_all_localized_templates_exist_and_non_empty(self):
        required_keys = [
            "welcome_and_language",
            "language_confirmed",
            "language_invalid",
            "language_change_prompt",
            "language_updated",
            "name_prompt",
            "name_confirm",
            "name_confirm_invalid",
            "crop_prompt",
            "crop_invalid",
            "acreage_prompt",
            "acreage_invalid",
            "location_prompt",
            "location_invalid",
            "location_out_of_bounds",
            "registration_success",
            "already_registered",
            "error_generic",
            "reset_success",
            "restart_confirm",
            "restart_confirm_invalid",
            "restart_cancelled",
            "re_registration_start",
            "farm_updated_success",
            "status_advisory",
            "status_no_advisory",
            "status_not_registered",
        ]
        for key in required_keys:
            self.assertIn(key, MESSAGES, f"Missing message key: {key}")
            for lang in ["en", "mr", "hi"]:
                self.assertIn(lang, MESSAGES[key], f"Missing lang {lang} for key {key}")
                val = MESSAGES[key][lang]
                self.assertTrue(len(val) > 0, f"Empty template for {key} in {lang}")

    def test_localized_advisories_all_actions_and_languages(self):
        actions = [
            ACTION_IRRIGATE_NOW,
            ACTION_IRRIGATE_LIGHTLY,
            ACTION_SCHEDULE_IRRIGATION,
            ACTION_DELAY_RECHECK,
            ACTION_HOLD_RECHECK,
            ACTION_NO_ACTION,
            ACTION_INSUFFICIENT_DATA,
        ]
        for action in actions:
            for lang in ["en", "mr", "hi"]:
                adv = get_localized_advisory(
                    lang=lang,
                    observed_stress="Severe Stress",
                    recommended_action=action,
                    crop="Cotton",
                    stage="Flowering",
                    rain_48h=6.0,
                )
                self.assertTrue(len(adv) > 10, f"Advisory too short for {action} in {lang}")

        adv_en = get_localized_advisory("en", "Severe Stress", ACTION_IRRIGATE_NOW, "Cotton", "Flowering", 0.0)
        self.assertIn("URGENT: Severe water stress detected for Cotton at Flowering stage", adv_en)
        self.assertIn("Immediate irrigation recommended", adv_en)

        adv_mr = get_localized_advisory("mr", "Mild Stress", ACTION_SCHEDULE_IRRIGATION, "Cotton", "Flowering", 0.0)
        self.assertIn("कापूस", adv_mr)
        self.assertIn("हलका पाण्याचा ताण", adv_mr)
        self.assertIn("नियमित पाणी देण्याचे नियोजन करा", adv_mr)

        adv_hi = get_localized_advisory("hi", "Severe Stress", ACTION_IRRIGATE_NOW, "Wheat", "Tillering", 2.0)
        self.assertIn("गेहूं", adv_hi)
        self.assertIn("गंभीर तनाव", adv_hi)
        self.assertIn("तुरंत सिंचाई करने की सलाह", adv_hi)


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


class TestRestartAndReRegistrationFlow(unittest.TestCase):
    """
    Regression unit tests for the 'restart' command in WhatsApp registration flow.
    Verifies:
    1. Restarting as an existing farmer (both cancel and confirm)
    2. Continuing as a new farmer without getting trapped
    3. Language persistence across restart flow
    4. Prevention of duplicate farm records and preservation of Farm ID
    5. Re-prompts on invalid confirmation input
    """

    def setUp(self):
        self.mock_sender = MagicMock(return_value=True)
        self.sessions = {}
        self.processed = set()
        self.farms = {}
        with test_pipeline_module._ACTIVE_PIPELINE_LOCK:
            test_pipeline_module._ACTIVE_PIPELINE_RUNS.clear()

    def _mock_get_session(self, phone, db_url=None):
        return self.sessions.get(phone)

    def _mock_save_session(self, phone, state, name=None, crop=None, acreage_acres=None, preferred_language=None, pending_lat=None, pending_lon=None, db_url=None, **kwargs):
        sess = self.sessions.get(phone, {"phone": phone})
        sess["state"] = state
        if name is not None:
            sess["name"] = name
        if crop is not None:
            sess["crop"] = crop
        if acreage_acres is not None:
            sess["acreage_acres"] = acreage_acres
        if preferred_language is not None:
            sess["preferred_language"] = preferred_language
        p_lat = pending_lat if pending_lat is not None else kwargs.get("pending_lat")
        if p_lat is not None:
            sess["pending_lat"] = p_lat
        p_lon = pending_lon if pending_lon is not None else kwargs.get("pending_lon")
        if p_lon is not None:
            sess["pending_lon"] = p_lon
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

    def _mock_update_farmer_language(self, phone, lang, db_url=None):
        if phone in self.farms:
            self.farms[phone]["preferred_language"] = lang
            return True
        return False

    @patch("whatsapp.registration_flow.get_registered_farm")
    @patch("whatsapp.registration_flow.get_session")
    @patch("whatsapp.registration_flow.save_session")
    @patch("whatsapp.registration_flow.clear_session")
    @patch("whatsapp.registration_flow.claim_message")
    @patch("whatsapp.registration_flow.unclaim_message")
    def test_existing_farmer_restart_cancelled_preserves_details(
        self,
        mock_unclaim,
        mock_claim,
        mock_clear_sess,
        mock_save_sess,
        mock_get_sess,
        mock_get_farm,
    ):
        mock_get_farm.side_effect = self._mock_get_farm
        mock_get_sess.side_effect = self._mock_get_session
        mock_save_sess.side_effect = self._mock_save_session
        mock_clear_sess.side_effect = self._mock_clear_session
        mock_claim.side_effect = self._mock_claim_message
        mock_unclaim.side_effect = self._mock_unclaim_message

        phone = "919876543210"
        self.farms[phone] = {
            "id": 3,
            "farmer_name": "Ramesh Patil",
            "crop_name": "Cotton",
            "farm_area": 2.5,
            "farm_area_unit": "acres",
            "preferred_language": "en",
        }

        # Step 1: Farmer sends 'restart'
        msg1 = {"id": "wamid.rst.1", "from": phone, "type": "text", "text": {"body": "restart"}}
        res1 = handle_incoming(msg1, outbound_sender=self.mock_sender)
        self.assertEqual(res1["status"], "restart_confirmation_requested")
        self.assertEqual(res1["next_state"], "AWAITING_RESTART_CONFIRMATION")
        self.assertEqual(res1["farm_id"], 3)
        self.mock_sender.assert_called_with(
            phone,
            get_message("restart_confirm", lang="en", farm_id=3, name="Ramesh Patil", crop="Cotton"),
        )

        # Step 2: Farmer replies 'NO' (cancels restart)
        msg2 = {"id": "wamid.rst.2", "from": phone, "type": "text", "text": {"body": "NO"}}
        res2 = handle_incoming(msg2, outbound_sender=self.mock_sender)
        self.assertEqual(res2["status"], "restart_cancelled")
        self.assertEqual(res2["farm_id"], 3)
        self.mock_sender.assert_called_with(
            phone,
            get_message("restart_cancelled", lang="en", farm_id=3, name="Ramesh Patil", crop="Cotton"),
        )
        self.assertNotIn(phone, self.sessions)
        self.assertEqual(self.farms[phone]["id"], 3)
        self.assertEqual(self.farms[phone]["farmer_name"], "Ramesh Patil")

        # Step 3: Subsequent message returns already_registered cleanly
        msg3 = {"id": "wamid.rst.3", "from": phone, "type": "text", "text": {"body": "Hello"}}
        res3 = handle_incoming(msg3, outbound_sender=self.mock_sender)
        self.assertEqual(res3["status"], "already_registered")
        self.assertEqual(res3["farm_id"], 3)

    @patch("whatsapp.registration_flow.get_registered_farm")
    @patch("whatsapp.registration_flow.get_session")
    @patch("whatsapp.registration_flow.save_session")
    @patch("whatsapp.registration_flow.clear_session")
    @patch("whatsapp.registration_flow.claim_message")
    @patch("whatsapp.registration_flow.unclaim_message")
    def test_existing_farmer_restart_invalid_response_reprompts(
        self,
        mock_unclaim,
        mock_claim,
        mock_clear_sess,
        mock_save_sess,
        mock_get_sess,
        mock_get_farm,
    ):
        mock_get_farm.side_effect = self._mock_get_farm
        mock_get_sess.side_effect = self._mock_get_session
        mock_save_sess.side_effect = self._mock_save_session
        mock_clear_sess.side_effect = self._mock_clear_session
        mock_claim.side_effect = self._mock_claim_message
        mock_unclaim.side_effect = self._mock_unclaim_message

        phone = "919876543210"
        self.farms[phone] = {
            "id": 3,
            "farmer_name": "Ramesh Patil",
            "crop_name": "Cotton",
            "preferred_language": "en",
        }

        # Step 1: Farmer sends 'restart'
        msg1 = {"id": "wamid.inv.1", "from": phone, "type": "text", "text": {"body": "restart"}}
        handle_incoming(msg1, outbound_sender=self.mock_sender)

        # Step 2: Farmer sends ambiguous message 'maybe'
        msg2 = {"id": "wamid.inv.2", "from": phone, "type": "text", "text": {"body": "maybe"}}
        res2 = handle_incoming(msg2, outbound_sender=self.mock_sender)
        self.assertEqual(res2["status"], "invalid_restart_confirmation")
        self.assertEqual(res2["state"], "AWAITING_RESTART_CONFIRMATION")
        self.mock_sender.assert_called_with(phone, get_message("restart_confirm_invalid", lang="en"))

    @patch("whatsapp.registration_flow.register_farmer_from_pin")
    @patch("whatsapp.registration_flow.get_registered_farm")
    @patch("whatsapp.registration_flow.get_session")
    @patch("whatsapp.registration_flow.save_session")
    @patch("whatsapp.registration_flow.clear_session")
    @patch("whatsapp.registration_flow.claim_message")
    @patch("whatsapp.registration_flow.unclaim_message")
    def test_existing_farmer_restart_confirm_and_update_farm(
        self,
        mock_unclaim,
        mock_claim,
        mock_clear_sess,
        mock_save_sess,
        mock_get_sess,
        mock_get_farm,
        mock_reg_pin,
    ):
        mock_get_farm.side_effect = self._mock_get_farm
        mock_get_sess.side_effect = self._mock_get_session
        mock_save_sess.side_effect = self._mock_save_session
        mock_clear_sess.side_effect = self._mock_clear_session
        mock_claim.side_effect = self._mock_claim_message
        mock_unclaim.side_effect = self._mock_unclaim_message

        phone = "919876543210"
        self.farms[phone] = {
            "id": 3,
            "farmer_name": "Ramesh Patil",
            "crop_name": "Cotton",
            "farm_area": 2.5,
            "farm_area_unit": "acres",
            "preferred_language": "en",
        }

        # Step 1: Farmer sends 'restart'
        msg1 = {"id": "wamid.up.1", "from": phone, "type": "text", "text": {"body": "restart"}}
        res1 = handle_incoming(msg1, outbound_sender=self.mock_sender)
        self.assertEqual(res1["status"], "restart_confirmation_requested")

        # Step 2: Farmer confirms with 'YES'
        msg2 = {"id": "wamid.up.2", "from": phone, "type": "text", "text": {"body": "YES"}}
        res2 = handle_incoming(msg2, outbound_sender=self.mock_sender)
        self.assertEqual(res2["status"], "re_registration_confirmed")
        self.assertEqual(res2["next_state"], "AWAITING_LANGUAGE")
        self.mock_sender.assert_called_with(
            phone,
            get_message("reset_success", lang="en"),
        )

        # Step 2b: Farmer selects preferred language ('1' - English)
        msg2b = {"id": "wamid.up.2b", "from": phone, "type": "text", "text": {"body": "1"}}
        res2b = handle_incoming(msg2b, outbound_sender=self.mock_sender)
        self.assertEqual(res2b["status"], "language_selected")
        self.assertEqual(res2b["next_state"], "AWAITING_NAME")
        self.assertEqual(res2b["language"], "en")
        self.assertEqual(res2b["farm_id"], 3)
        self.mock_sender.assert_called_with(
            phone,
            get_message("re_registration_start", lang="en", farm_id=3),
        )

        # Step 3: Farmer enters new name 'Rameshwar Patil'
        msg3 = {"id": "wamid.up.3", "from": phone, "type": "text", "text": {"body": "Rameshwar Patil"}}
        res3 = handle_incoming(msg3, outbound_sender=self.mock_sender)
        self.assertEqual(res3["status"], "name_candidate_received")
        self.assertEqual(res3["candidate_name"], "Rameshwar Patil")

        # Step 4: Farmer confirms name 'YES'
        msg4 = {"id": "wamid.up.4", "from": phone, "type": "text", "text": {"body": "YES"}}
        res4 = handle_incoming(msg4, outbound_sender=self.mock_sender)
        self.assertEqual(res4["status"], "name_confirmed")
        self.assertEqual(res4["next_state"], "AWAITING_CROP")

        # Step 5: Farmer specifies new crop 'Soybean'
        msg5 = {"id": "wamid.up.5", "from": phone, "type": "text", "text": {"body": "Soybean"}}
        res5 = handle_incoming(msg5, outbound_sender=self.mock_sender)
        self.assertEqual(res5["status"], "crop_saved")
        self.assertEqual(res5["crop"], "Soybean")

        # Step 6: Farmer specifies new acreage '4.5'
        msg6 = {"id": "wamid.up.6", "from": phone, "type": "text", "text": {"body": "4.5"}}
        res6 = handle_incoming(msg6, outbound_sender=self.mock_sender)
        self.assertEqual(res6["status"], "acreage_saved")
        self.assertEqual(res6["acreage_acres"], 4.5)

        # Step 7: Farmer drops updated location pin -> requests confirmation
        msg7 = {
            "id": "wamid.up.7",
            "from": phone,
            "type": "location",
            "location": {"latitude": 20.50260, "longitude": 77.14195},
        }
        res7 = handle_incoming(msg7, outbound_sender=self.mock_sender)
        self.assertEqual(res7["status"], "location_confirmation_requested")
        self.assertEqual(res7["next_state"], "AWAITING_LOCATION_CONFIRMATION")
        self.mock_sender.assert_called_with(
            phone,
            get_message("location_confirm_prompt", lang="en", lat=20.50260, lon=77.14195),
        )

        # Step 8: Farmer confirms updated location with YES -> completes update and triggers pipeline
        mock_reg_pin.return_value = {
            "success": True,
            "farm_id": 3,
            "farmer_name": "Rameshwar Patil",
            "mobile_number": phone,
            "crop_name": "Soybean",
            "farm_area": 4.5,
            "farm_area_unit": "acres",
            "centroid_lat": 20.50260,
            "centroid_lon": 77.14195,
        }
        mock_pipe_runner = MagicMock()
        msg8 = {"id": "wamid.up.8", "from": phone, "type": "text", "text": {"body": "YES"}}
        res8 = handle_incoming(msg8, outbound_sender=self.mock_sender, pipeline_runner=mock_pipe_runner)
        self.assertEqual(res8["status"], "farm_updated")
        self.assertEqual(res8["farm_id"], 3)
        self.assertEqual(res8["farmer_name"], "Rameshwar Patil")
        self.assertEqual(res8["crop_name"], "Soybean")
        self.assertEqual(res8["area_acres"], 4.5)
        self.assertTrue(res8.get("pipeline_triggered"))
        mock_pipe_runner.assert_called_once_with(
            farm_id=3,
            db_url=None,
            outbound_sender=self.mock_sender,
        )

        # Verifies register_farmer_from_pin was called with updated details
        mock_reg_pin.assert_called_once()
        call_kwargs = mock_reg_pin.call_args[1]
        self.assertEqual(call_kwargs["farmer_name"], "Rameshwar Patil")
        self.assertEqual(call_kwargs["crop_name"], "Soybean")
        self.assertEqual(call_kwargs["farm_area_acres"], 4.5)
        self.assertEqual(call_kwargs["preferred_language"], "en")

        # Verifies farm_updated_success message was sent to user
        self.mock_sender.assert_called_with(
            phone,
            get_message(
                "farm_updated_success",
                lang="en",
                farm_id=3,
                name="Rameshwar Patil",
                crop="Soybean",
                area=4.5,
                boundary_source="Approximate square area around your pin (estimated)",
                lat=20.50260,
                lon=77.14195,
            ),
        )

    @patch("whatsapp.registration_flow.get_registered_farm")
    @patch("whatsapp.registration_flow.get_session")
    @patch("whatsapp.registration_flow.save_session")
    @patch("whatsapp.registration_flow.clear_session")
    @patch("whatsapp.registration_flow.claim_message")
    @patch("whatsapp.registration_flow.unclaim_message")
    def test_new_farmer_restart_and_continue(
        self,
        mock_unclaim,
        mock_claim,
        mock_clear_sess,
        mock_save_sess,
        mock_get_sess,
        mock_get_farm,
    ):
        mock_get_farm.side_effect = self._mock_get_farm
        mock_get_sess.side_effect = self._mock_get_session
        mock_save_sess.side_effect = self._mock_save_session
        mock_clear_sess.side_effect = self._mock_clear_session
        mock_claim.side_effect = self._mock_claim_message
        mock_unclaim.side_effect = self._mock_unclaim_message

        phone = "919876543999"  # Not registered

        # Step 1: Greeting
        msg1 = {"id": "wamid.new.1", "from": phone, "type": "text", "text": {"body": "Hi"}}
        res1 = handle_incoming(msg1, outbound_sender=self.mock_sender)
        self.assertEqual(res1["status"], "session_started")

        # Step 2: Choose Marathi ('2')
        msg2 = {"id": "wamid.new.2", "from": phone, "type": "text", "text": {"body": "2"}}
        res2 = handle_incoming(msg2, outbound_sender=self.mock_sender)
        self.assertEqual(res2["status"], "language_selected")
        self.assertEqual(res2["language"], "mr")

        # Step 3: New farmer sends 'restart' mid-registration
        msg3 = {"id": "wamid.new.3", "from": phone, "type": "text", "text": {"body": "restart"}}
        res3 = handle_incoming(msg3, outbound_sender=self.mock_sender)
        self.assertEqual(res3["status"], "session_reset")
        self.assertEqual(res3["next_state"], "AWAITING_LANGUAGE")
        self.mock_sender.assert_called_with(phone, get_message("reset_success", lang="mr"))

        # Step 4: Farmer selects '1' (English) after restart
        msg4 = {"id": "wamid.new.4", "from": phone, "type": "text", "text": {"body": "1"}}
        res4 = handle_incoming(msg4, outbound_sender=self.mock_sender)
        self.assertEqual(res4["status"], "language_selected")
        self.assertEqual(res4["language"], "en")
        self.mock_sender.assert_called_with(phone, get_message("language_confirmed", lang="en"))

    @patch("whatsapp.registration_flow.update_farmer_language")
    @patch("whatsapp.registration_flow.get_registered_farm")
    @patch("whatsapp.registration_flow.get_session")
    @patch("whatsapp.registration_flow.save_session")
    @patch("whatsapp.registration_flow.clear_session")
    @patch("whatsapp.registration_flow.claim_message")
    @patch("whatsapp.registration_flow.unclaim_message")
    def test_language_change_followed_by_restart_flow(
        self,
        mock_unclaim,
        mock_claim,
        mock_clear_sess,
        mock_save_sess,
        mock_get_sess,
        mock_get_farm,
        mock_update_lang,
    ):
        mock_get_farm.side_effect = self._mock_get_farm
        mock_get_sess.side_effect = self._mock_get_session
        mock_save_sess.side_effect = self._mock_save_session
        mock_clear_sess.side_effect = self._mock_clear_session
        mock_claim.side_effect = self._mock_claim_message
        mock_unclaim.side_effect = self._mock_unclaim_message
        mock_update_lang.side_effect = self._mock_update_farmer_language

        phone = "919876543210"
        self.farms[phone] = {
            "id": 3,
            "farmer_name": "Ramesh Patil",
            "crop_name": "Cotton",
            "farm_area": 2.5,
            "farm_area_unit": "acres",
            "preferred_language": "mr",  # Initially Marathi
        }

        # Step 1: Farmer sends 'language'
        msg1 = {"id": "wamid.sc.1", "from": phone, "type": "text", "text": {"body": "language"}}
        res1 = handle_incoming(msg1, outbound_sender=self.mock_sender)
        self.assertEqual(res1["status"], "language_change_requested")
        self.mock_sender.assert_called_with(phone, get_message("language_change_prompt", lang="mr"))

        # Step 2: Farmer selects '1' (English)
        msg2 = {"id": "wamid.sc.2", "from": phone, "type": "text", "text": {"body": "1"}}
        res2 = handle_incoming(msg2, outbound_sender=self.mock_sender)
        self.assertEqual(res2["status"], "language_updated")
        self.assertEqual(res2["language"], "en")
        self.assertEqual(self.farms[phone]["preferred_language"], "en")

        # Step 3: Farmer sends 'restart'
        msg3 = {"id": "wamid.sc.3", "from": phone, "type": "text", "text": {"body": "restart"}}
        res3 = handle_incoming(msg3, outbound_sender=self.mock_sender)
        self.assertEqual(res3["status"], "restart_confirmation_requested")
        self.assertEqual(res3["next_state"], "AWAITING_RESTART_CONFIRMATION")
        # Critical verification: restart_confirm is in ENGLISH (the updated language)
        self.mock_sender.assert_called_with(
            phone,
            get_message("restart_confirm", lang="en", farm_id=3, name="Ramesh Patil", crop="Cotton"),
        )

        # Step 4: Farmer confirms re-registration with 'YES'
        msg4 = {"id": "wamid.sc.4", "from": phone, "type": "text", "text": {"body": "YES"}}
        res4 = handle_incoming(msg4, outbound_sender=self.mock_sender)
        self.assertEqual(res4["status"], "re_registration_confirmed")
        self.assertEqual(res4["next_state"], "AWAITING_LANGUAGE")
        # Critical verification: reset_success is in ENGLISH
        self.mock_sender.assert_called_with(
            phone,
            get_message("reset_success", lang="en"),
        )

        # Step 4b: Farmer selects preferred language ('1' - English)
        msg4b = {"id": "wamid.sc.4b", "from": phone, "type": "text", "text": {"body": "1"}}
        res4b = handle_incoming(msg4b, outbound_sender=self.mock_sender)
        self.assertEqual(res4b["status"], "language_selected")
        self.assertEqual(res4b["next_state"], "AWAITING_NAME")
        self.assertEqual(res4b["language"], "en")
        self.mock_sender.assert_called_with(
            phone,
            get_message("re_registration_start", lang="en", farm_id=3),
        )

        # Step 5: Farmer sends name
        msg5 = {"id": "wamid.sc.5", "from": phone, "type": "text", "text": {"body": "Dnyaneshwar Shinde"}}
        res5 = handle_incoming(msg5, outbound_sender=self.mock_sender)
        self.assertEqual(res5["status"], "name_candidate_received")
        # Critical verification: name_confirm is in ENGLISH
        self.mock_sender.assert_called_with(
            phone,
            get_message("name_confirm", lang="en", name="Dnyaneshwar Shinde"),
        )

    def test_duplicate_farm_record_prevention_sql(self):
        """Verifies that farmer_registration.py contains ON CONFLICT (mobile_number) DO UPDATE SET."""
        import inspect
        from pipeline import farmer_registration
        src = inspect.getsource(farmer_registration.register_farmer_from_pin)
        self.assertIn("ON CONFLICT (mobile_number) DO UPDATE SET", src)
        self.assertIn("RETURNING", src)
        self.assertIn("id,", src)

    @patch("whatsapp.registration_flow.get_registered_farm")
    @patch("whatsapp.registration_flow.get_session")
    @patch("whatsapp.registration_flow.save_session")
    @patch("whatsapp.registration_flow.claim_message", return_value=True)
    def test_returning_farmer_location_prompt_prefers_in_flight_name_and_crop(
        self, mock_claim, mock_save_session, mock_get_session, mock_get_farm
    ):
        """Re-registration prompts should use newly entered session values, not stale DB values."""
        phone = "919876543210"
        session = {
            "phone": phone,
            "state": "AWAITING_ACREAGE",
            "name": "New Farmer",
            "crop": "Pigeon Pea",
            "preferred_language": "en",
        }
        registered_farm = {
            "id": 7,
            "farmer_name": "Old Farmer",
            "crop_name": "Maize",
            "pin_lat": 20.50260,
            "pin_lon": 77.14195,
            "preferred_language": "en",
        }
        mock_get_session.return_value = session
        mock_get_farm.return_value = registered_farm
        sender = MagicMock()

        result = handle_incoming(
            {"from": phone, "type": "text", "text": {"body": "3 acres"}},
            outbound_sender=sender,
        )

        self.assertEqual(result["status"], "acreage_saved")
        self.assertEqual(result["next_state"], "AWAITING_LOCATION_CHOICE")
        sender.assert_called_with(
            phone,
            get_message(
                "location_choice_returning_prompt",
                lang="en",
                farm_id=7,
                name="New Farmer",
                crop="Pigeon Pea",
                lat=20.50260,
                lon=77.14195,
            ),
        )

    @patch("whatsapp.registration_flow.get_registered_farm")
    @patch("whatsapp.registration_flow.get_session")
    @patch("whatsapp.registration_flow.claim_message", return_value=True)
    def test_invalid_returning_farmer_location_choice_uses_in_flight_name_and_crop(
        self, mock_claim, mock_get_session, mock_get_farm
    ):
        """An invalid location choice must not re-display stale farmer/crop details."""
        phone = "919876543210"
        session = {
            "phone": phone,
            "state": "AWAITING_LOCATION_CHOICE",
            "name": "New Farmer",
            "crop": "Pigeon Pea",
            "acreage_acres": 3.0,
            "preferred_language": "en",
        }
        registered_farm = {
            "id": 7,
            "farmer_name": "Old Farmer",
            "crop_name": "Maize",
            "pin_lat": 20.50260,
            "pin_lon": 77.14195,
            "preferred_language": "en",
        }
        mock_get_session.return_value = session
        mock_get_farm.return_value = registered_farm
        sender = MagicMock()

        result = handle_incoming(
            {"from": phone, "type": "text", "text": {"body": "9"}},
            outbound_sender=sender,
        )

        self.assertEqual(result["status"], "invalid_location_choice")
        sender.assert_called_with(
            phone,
            get_message(
                "location_choice_returning_prompt",
                lang="en",
                farm_id=7,
                name="New Farmer",
                crop="Pigeon Pea",
                lat=20.50260,
                lon=77.14195,
            ),
        )


class TestStatusCommand(unittest.TestCase):
    """
    Comprehensive unit tests for the multilingual farmer 'status' command (Step 3).
    Verifies:
    1. Registered farmer with advisory receives localized status card (en, mr, hi).
    2. Registered farmer with 0 advisories receives localized pending message.
    3. Unregistered sender receives localized registration guidance (no DB query, no farm created).
    4. Strict farm scoping (Farm ID 1 cannot see Farm ID 2's data).
    5. Missing / legacy advisory fields format gracefully without errors.
    6. Database exception handling: unclaims message for Meta retry, logs securely, returns error.
    7. Deduplication for status commands.
    8. Farm records, sessions, and language preferences remain uncorrupted.
    9. Status command synonyms and regional transliterations.
    10. SQL query contract scoping strictly by farm_id.
    """

    def setUp(self):
        self.mock_sender = MagicMock(return_value=True)
        self.sessions = {}
        self.processed = set()
        self.farms = {}
        self.advisories = {}
        with test_pipeline_module._ACTIVE_PIPELINE_LOCK:
            test_pipeline_module._ACTIVE_PIPELINE_RUNS.clear()

    def _mock_get_session(self, phone, db_url=None):
        return self.sessions.get(phone)

    def _mock_save_session(self, phone, state, name=None, crop=None, acreage_acres=None, preferred_language=None, pending_lat=None, pending_lon=None, db_url=None, **kwargs):
        sess = self.sessions.get(phone, {"phone": phone})
        sess["state"] = state
        if name is not None:
            sess["name"] = name
        if crop is not None:
            sess["crop"] = crop
        if acreage_acres is not None:
            sess["acreage_acres"] = acreage_acres
        if preferred_language is not None:
            sess["preferred_language"] = preferred_language
        p_lat = pending_lat if pending_lat is not None else kwargs.get("pending_lat")
        if p_lat is not None:
            sess["pending_lat"] = p_lat
        p_lon = pending_lon if pending_lon is not None else kwargs.get("pending_lon")
        if p_lon is not None:
            sess["pending_lon"] = p_lon
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

    def _mock_get_latest_advisory(self, farm_id, db_url=None):
        return self.advisories.get(farm_id)

    @patch("whatsapp.registration_flow.get_latest_advisory")
    @patch("whatsapp.registration_flow.get_registered_farm")
    @patch("whatsapp.registration_flow.get_session")
    @patch("whatsapp.registration_flow.save_session")
    @patch("whatsapp.registration_flow.clear_session")
    @patch("whatsapp.registration_flow.claim_message")
    @patch("whatsapp.registration_flow.unclaim_message")
    def test_registered_farmer_status_english_with_advisory(
        self,
        mock_unclaim,
        mock_claim,
        mock_clear,
        mock_save,
        mock_sess,
        mock_farm,
        mock_adv,
    ):
        mock_farm.side_effect = self._mock_get_farm
        mock_sess.side_effect = self._mock_get_session
        mock_claim.side_effect = self._mock_claim_message
        mock_unclaim.side_effect = self._mock_unclaim_message
        mock_adv.side_effect = self._mock_get_latest_advisory

        phone = "919876543210"
        self.farms[phone] = {
            "id": 1,
            "farmer_name": "Diksha",
            "crop_name": "Soybean",
            "farm_area": 2.47,
            "farm_area_unit": "acres",
            "preferred_language": "en",
        }
        self.advisories[1] = {
            "id": 101,
            "farm_id": 1,
            "observation_date": "2026-10-02",
            "created_at": "2026-10-02 14:00:00",
            "crop_stage": "Pod Development",
            "stress_level": "Mild Stress",
            "recommendation": "Schedule regular irrigation in the next 24-48 hours",
            "ndvi": 0.45,
            "soil_moisture": 22.0,
            "rainfall_48h": 0.0,
            "observed_stress": "Mild Stress",
            "rain_forecast_mm": 0.0,
            "guardrail_triggered": False,
            "recommended_action": ACTION_SCHEDULE_IRRIGATION,
        }

        msg = {"id": "wamid.st.1", "from": phone, "type": "text", "text": {"body": "status"}}
        res = handle_incoming(msg, outbound_sender=self.mock_sender)

        self.assertEqual(res["status"], "advisory_sent")
        self.assertEqual(res["farm_id"], 1)
        self.assertEqual(res["advisory_id"], 101)
        self.assertEqual(res["language"], "en")

        sent_body = self.mock_sender.call_args[0][1]
        self.assertIn("KhetSense Farm Status & Advisory", sent_body)
        self.assertIn("Farm ID: #1", sent_body)
        self.assertIn("Farmer: Diksha", sent_body)
        self.assertIn("Crop: Soybean", sent_body)
        self.assertIn("Mild Stress", sent_body)
        self.assertIn("Schedule Irrigation (24-48h)", sent_body)
        self.assertIn("0.0 mm", sent_body)
        self.assertIn("02-10-2026", sent_body)

    @patch("whatsapp.registration_flow.get_latest_advisory")
    @patch("whatsapp.registration_flow.get_registered_farm")
    @patch("whatsapp.registration_flow.get_session")
    @patch("whatsapp.registration_flow.save_session")
    @patch("whatsapp.registration_flow.clear_session")
    @patch("whatsapp.registration_flow.claim_message")
    @patch("whatsapp.registration_flow.unclaim_message")
    def test_registered_farmer_status_marathi_with_advisory(
        self,
        mock_unclaim,
        mock_claim,
        mock_clear,
        mock_save,
        mock_sess,
        mock_farm,
        mock_adv,
    ):
        mock_farm.side_effect = self._mock_get_farm
        mock_sess.side_effect = self._mock_get_session
        mock_claim.side_effect = self._mock_claim_message
        mock_unclaim.side_effect = self._mock_unclaim_message
        mock_adv.side_effect = self._mock_get_latest_advisory

        phone = "919876543211"
        self.farms[phone] = {
            "id": 2,
            "farmer_name": "रमेश पाटील",
            "crop_name": "Cotton",
            "farm_area": 5.0,
            "farm_area_unit": "acres",
            "preferred_language": "mr",
        }
        self.advisories[2] = {
            "id": 102,
            "farm_id": 2,
            "observation_date": "2026-10-02",
            "created_at": "2026-10-02 14:00:00",
            "crop_stage": "Flowering",
            "stress_level": "Severe Stress",
            "recommendation": "Immediate irrigation recommended",
            "ndvi": 0.25,
            "soil_moisture": 12.0,
            "rainfall_48h": 0.0,
            "observed_stress": "Severe Stress",
            "rain_forecast_mm": 0.0,
            "guardrail_triggered": False,
            "recommended_action": ACTION_IRRIGATE_NOW,
        }

        # Farmer tests with Devanagari command 'स्थिती'
        msg = {"id": "wamid.st.2", "from": phone, "type": "text", "text": {"body": "स्थिती"}}
        res = handle_incoming(msg, outbound_sender=self.mock_sender)

        self.assertEqual(res["status"], "advisory_sent")
        self.assertEqual(res["farm_id"], 2)
        self.assertEqual(res["language"], "mr")

        sent_body = self.mock_sender.call_args[0][1]
        self.assertIn("खेतसेन्स शेती अहवाल आणि सल्ला", sent_body)
        self.assertIn("शेत आयडी: #2", sent_body)
        self.assertIn("शेतकरी: रमेश पाटील", sent_body)
        self.assertIn("कापूस", sent_body)
        self.assertIn("तीव्र ताण", sent_body)
        self.assertIn("तात्काळ पाणी द्या", sent_body)
        self.assertIn("0.0 mm", sent_body)

    @patch("whatsapp.registration_flow.get_latest_advisory")
    @patch("whatsapp.registration_flow.get_registered_farm")
    @patch("whatsapp.registration_flow.get_session")
    @patch("whatsapp.registration_flow.save_session")
    @patch("whatsapp.registration_flow.clear_session")
    @patch("whatsapp.registration_flow.claim_message")
    @patch("whatsapp.registration_flow.unclaim_message")
    def test_registered_farmer_status_hindi_with_advisory(
        self,
        mock_unclaim,
        mock_claim,
        mock_clear,
        mock_save,
        mock_sess,
        mock_farm,
        mock_adv,
    ):
        mock_farm.side_effect = self._mock_get_farm
        mock_sess.side_effect = self._mock_get_session
        mock_claim.side_effect = self._mock_claim_message
        mock_unclaim.side_effect = self._mock_unclaim_message
        mock_adv.side_effect = self._mock_get_latest_advisory

        phone = "919876543212"
        self.farms[phone] = {
            "id": 4,
            "farmer_name": "सुरेश कुमार",
            "crop_name": "Wheat",
            "farm_area": 3.0,
            "farm_area_unit": "acres",
            "preferred_language": "hi",
        }
        self.advisories[4] = {
            "id": 104,
            "farm_id": 4,
            "observation_date": "2026-10-02",
            "created_at": "2026-10-02 14:00:00",
            "crop_stage": "Tillering",
            "stress_level": "Severe Stress",
            "recommendation": "Light irrigation recommended",
            "ndvi": 0.28,
            "soil_moisture": 13.5,
            "rainfall_48h": 8.0,
            "observed_stress": "Severe Stress",
            "rain_forecast_mm": 8.0,
            "guardrail_triggered": True,
            "recommended_action": ACTION_IRRIGATE_LIGHTLY,
        }

        # Farmer tests with Devanagari Hindi command 'स्थिति'
        msg = {"id": "wamid.st.3", "from": phone, "type": "text", "text": {"body": "स्थिति"}}
        res = handle_incoming(msg, outbound_sender=self.mock_sender)

        self.assertEqual(res["status"], "advisory_sent")
        self.assertEqual(res["farm_id"], 4)
        self.assertEqual(res["language"], "hi")

        sent_body = self.mock_sender.call_args[0][1]
        self.assertIn("खेतसेंस खेत स्थिति एवं सलाह", sent_body)
        self.assertIn("फार्म आईडी: #4", sent_body)
        self.assertIn("किसान: सुरेश कुमार", sent_body)
        self.assertIn("गेहूं", sent_body)
        self.assertIn("गंभीर तनाव", sent_body)
        self.assertIn("हल्की सिंचाई करें", sent_body)
        self.assertIn("8.0 mm", sent_body)

    @patch("whatsapp.registration_flow.get_latest_advisory")
    @patch("whatsapp.registration_flow.get_registered_farm")
    @patch("whatsapp.registration_flow.get_session")
    @patch("whatsapp.registration_flow.save_session")
    @patch("whatsapp.registration_flow.clear_session")
    @patch("whatsapp.registration_flow.claim_message")
    @patch("whatsapp.registration_flow.unclaim_message")
    def test_registered_farmer_zero_advisories_pending_message(
        self,
        mock_unclaim,
        mock_claim,
        mock_clear,
        mock_save,
        mock_sess,
        mock_farm,
        mock_adv,
    ):
        mock_farm.side_effect = self._mock_get_farm
        mock_sess.side_effect = self._mock_get_session
        mock_claim.side_effect = self._mock_claim_message
        mock_unclaim.side_effect = self._mock_unclaim_message
        mock_adv.side_effect = self._mock_get_latest_advisory

        # Farm ID 3 (Diksha, Soybean) with zero advisories (identical to live DB state!)
        phone = "919876543213"
        self.farms[phone] = {
            "id": 3,
            "farmer_name": "Diksha",
            "crop_name": "Soybean",
            "farm_area": 2.47,
            "farm_area_unit": "acres",
            "preferred_language": "en",
        }
        self.advisories[3] = None

        msg = {"id": "wamid.st.4", "from": phone, "type": "text", "text": {"body": "status"}}
        res = handle_incoming(msg, outbound_sender=self.mock_sender)

        self.assertEqual(res["status"], "no_advisory_found")
        self.assertEqual(res["farm_id"], 3)
        self.assertEqual(res["language"], "en")

        sent_body = self.mock_sender.call_args[0][1]
        self.assertIn("Farm ID: #3", sent_body)
        self.assertIn("Registered & Monitoring Active", sent_body)
        self.assertIn("first irrigation advisory will be available shortly", sent_body)

    @patch("whatsapp.registration_flow.get_latest_advisory")
    @patch("whatsapp.registration_flow.get_registered_farm")
    @patch("whatsapp.registration_flow.get_session")
    @patch("whatsapp.registration_flow.save_session")
    @patch("whatsapp.registration_flow.clear_session")
    @patch("whatsapp.registration_flow.claim_message")
    @patch("whatsapp.registration_flow.unclaim_message")
    def test_unregistered_sender_receives_registration_guidance(
        self,
        mock_unclaim,
        mock_claim,
        mock_clear,
        mock_save,
        mock_sess,
        mock_farm,
        mock_adv,
    ):
        mock_farm.side_effect = self._mock_get_farm
        mock_sess.side_effect = self._mock_get_session
        mock_claim.side_effect = self._mock_claim_message
        mock_unclaim.side_effect = self._mock_unclaim_message
        mock_adv.side_effect = self._mock_get_latest_advisory

        phone = "919999000111"

        msg = {"id": "wamid.st.5", "from": phone, "type": "text", "text": {"body": "status"}}
        res = handle_incoming(msg, outbound_sender=self.mock_sender)

        self.assertEqual(res["status"], "not_registered")
        self.assertEqual(res["language"], "en")

        # Crucial security checks:
        mock_adv.assert_not_called()
        self.assertNotIn(phone, self.farms)

        sent_body = self.mock_sender.call_args[0][1]
        self.assertIn("You do not have a registered farm yet", sent_body)
        self.assertIn("register your farm first", sent_body)

    @patch("whatsapp.registration_flow.get_latest_advisory")
    @patch("whatsapp.registration_flow.get_registered_farm")
    @patch("whatsapp.registration_flow.get_session")
    @patch("whatsapp.registration_flow.save_session")
    @patch("whatsapp.registration_flow.clear_session")
    @patch("whatsapp.registration_flow.claim_message")
    @patch("whatsapp.registration_flow.unclaim_message")
    def test_status_query_strictly_scoped_to_sender_farm(
        self,
        mock_unclaim,
        mock_claim,
        mock_clear,
        mock_save,
        mock_sess,
        mock_farm,
        mock_adv,
    ):
        mock_farm.side_effect = self._mock_get_farm
        mock_sess.side_effect = self._mock_get_session
        mock_claim.side_effect = self._mock_claim_message
        mock_unclaim.side_effect = self._mock_unclaim_message
        mock_adv.side_effect = self._mock_get_latest_advisory

        phone1 = "919876543201"
        phone2 = "919876543202"

        self.farms[phone1] = {"id": 1, "farmer_name": "Farmer One", "crop_name": "Cotton", "preferred_language": "en"}
        self.farms[phone2] = {"id": 2, "farmer_name": "Farmer Two", "crop_name": "Wheat", "preferred_language": "en"}

        self.advisories[1] = {
            "id": 101,
            "farm_id": 1,
            "observation_date": "2026-10-01",
            "observed_stress": "Severe Stress",
            "recommended_action": ACTION_IRRIGATE_NOW,
            "rain_forecast_mm": 0.0,
        }
        self.advisories[2] = {
            "id": 202,
            "farm_id": 2,
            "observation_date": "2026-10-02",
            "observed_stress": "No Stress",
            "recommended_action": ACTION_NO_ACTION,
            "rain_forecast_mm": 20.0,
        }

        # Farmer 1 requests status
        msg1 = {"id": "wamid.sc.p1", "from": phone1, "type": "text", "text": {"body": "status"}}
        res1 = handle_incoming(msg1, outbound_sender=self.mock_sender)
        self.assertEqual(res1["farm_id"], 1)
        self.assertEqual(res1["advisory_id"], 101)
        mock_adv.assert_called_with(1, db_url=None)

        # Farmer 2 requests status
        msg2 = {"id": "wamid.sc.p2", "from": phone2, "type": "text", "text": {"body": "status"}}
        res2 = handle_incoming(msg2, outbound_sender=self.mock_sender)
        self.assertEqual(res2["farm_id"], 2)
        self.assertEqual(res2["advisory_id"], 202)
        mock_adv.assert_called_with(2, db_url=None)

    def test_missing_and_legacy_advisory_fields_formatting(self):
        farm = {"id": 99, "farmer_name": "Test Farmer", "crop_name": "Cotton"}
        legacy_advisory = {
            "id": 5,
            "farm_id": 99,
            "observation_date": None,
            "created_at": None,
            "crop_stage": None,
            "stress_level": "Mild Stress",
            "recommendation": "Schedule regular irrigation in the next 24-48 hours",
            "ndvi": 0.50,
            "soil_moisture": 20.0,
            "rainfall_48h": 0.0,
            "observed_stress": None,
            "rain_forecast_mm": None,
            "guardrail_triggered": None,
            "recommended_action": None,
        }
        card_en = format_status_advisory(farm, legacy_advisory, lang="en")
        self.assertIn("Farm ID: #99", card_en)
        self.assertIn("Mild Stress", card_en)
        self.assertIn("Schedule Irrigation (24-48h)", card_en)
        self.assertIn("0.0 mm", card_en)

        card_mr = format_status_advisory(farm, legacy_advisory, lang="mr")
        self.assertIn("शेत आयडी: #99", card_mr)
        self.assertIn("कापूस", card_mr)
        self.assertIn("हलका ताण", card_mr)

    @patch("whatsapp.registration_flow.get_latest_advisory")
    @patch("whatsapp.registration_flow.get_registered_farm")
    @patch("whatsapp.registration_flow.get_session")
    @patch("whatsapp.registration_flow.save_session")
    @patch("whatsapp.registration_flow.clear_session")
    @patch("whatsapp.registration_flow.claim_message")
    @patch("whatsapp.registration_flow.unclaim_message")
    def test_database_exception_in_status_unclaims_message_and_sends_error(
        self,
        mock_unclaim,
        mock_claim,
        mock_clear,
        mock_save,
        mock_sess,
        mock_farm,
        mock_adv,
    ):
        mock_farm.side_effect = self._mock_get_farm
        mock_sess.side_effect = self._mock_get_session
        mock_claim.side_effect = self._mock_claim_message
        mock_unclaim.side_effect = self._mock_unclaim_message
        mock_adv.side_effect = RuntimeError("DB connection pool exhausted")

        phone = "919876543210"
        self.farms[phone] = {"id": 1, "farmer_name": "Diksha", "crop_name": "Soybean", "preferred_language": "en"}

        msg = {"id": "wamid.err.1", "from": phone, "type": "text", "text": {"body": "status"}}
        res = handle_incoming(msg, outbound_sender=self.mock_sender)

        self.assertEqual(res["status"], "error")
        # Assert message was unclaimed so Meta delivery retry works
        self.assertNotIn("wamid.err.1", self.processed)
        # Assert generic error sent
        self.mock_sender.assert_called_with(phone, get_message("error_generic", lang="en"))

    @patch("whatsapp.registration_flow.get_latest_advisory")
    @patch("whatsapp.registration_flow.get_registered_farm")
    @patch("whatsapp.registration_flow.get_session")
    @patch("whatsapp.registration_flow.save_session")
    @patch("whatsapp.registration_flow.clear_session")
    @patch("whatsapp.registration_flow.claim_message")
    @patch("whatsapp.registration_flow.unclaim_message")
    def test_duplicate_status_message_deduplication(
        self,
        mock_unclaim,
        mock_claim,
        mock_clear,
        mock_save,
        mock_sess,
        mock_farm,
        mock_adv,
    ):
        mock_farm.side_effect = self._mock_get_farm
        mock_sess.side_effect = self._mock_get_session
        mock_claim.side_effect = self._mock_claim_message
        mock_unclaim.side_effect = self._mock_unclaim_message
        mock_adv.side_effect = self._mock_get_latest_advisory

        phone = "919876543210"
        self.farms[phone] = {"id": 1, "farmer_name": "Diksha", "crop_name": "Soybean", "preferred_language": "en"}
        self.advisories[1] = {"id": 101, "farm_id": 1, "observed_stress": "No Stress", "recommended_action": ACTION_NO_ACTION}

        msg = {"id": "wamid.dup.status", "from": phone, "type": "text", "text": {"body": "status"}}

        # Call 1: Processed
        res1 = handle_incoming(msg, outbound_sender=self.mock_sender)
        self.assertEqual(res1["status"], "advisory_sent")
        self.assertEqual(self.mock_sender.call_count, 1)

        # Call 2: Duplicate ignored
        res2 = handle_incoming(msg, outbound_sender=self.mock_sender)
        self.assertEqual(res2["status"], "duplicate")
        self.assertEqual(res2["message_id"], "wamid.dup.status")
        self.assertEqual(self.mock_sender.call_count, 1)

    @patch("whatsapp.registration_flow.get_latest_advisory")
    @patch("whatsapp.registration_flow.get_registered_farm")
    @patch("whatsapp.registration_flow.get_session")
    @patch("whatsapp.registration_flow.save_session")
    @patch("whatsapp.registration_flow.clear_session")
    @patch("whatsapp.registration_flow.claim_message")
    @patch("whatsapp.registration_flow.unclaim_message")
    def test_status_command_does_not_modify_farm_or_session(
        self,
        mock_unclaim,
        mock_claim,
        mock_clear,
        mock_save,
        mock_sess,
        mock_farm,
        mock_adv,
    ):
        mock_farm.side_effect = self._mock_get_farm
        mock_sess.side_effect = self._mock_get_session
        mock_claim.side_effect = self._mock_claim_message
        mock_unclaim.side_effect = self._mock_unclaim_message
        mock_adv.side_effect = self._mock_get_latest_advisory

        phone = "919876543210"
        initial_farm = {
            "id": 7,
            "farmer_name": "Ganesh",
            "crop_name": "Onion",
            "farm_area": 1.5,
            "farm_area_unit": "acres",
            "preferred_language": "mr",
        }
        self.farms[phone] = dict(initial_farm)
        self.advisories[7] = {
            "id": 701,
            "farm_id": 7,
            "observed_stress": "No Stress",
            "recommended_action": ACTION_NO_ACTION,
        }

        msg = {"id": "wamid.imm.1", "from": phone, "type": "text", "text": {"body": "status"}}
        res = handle_incoming(msg, outbound_sender=self.mock_sender)
        self.assertEqual(res["status"], "advisory_sent")

        # Verify farm state is completely unmodified
        self.assertEqual(self.farms[phone], initial_farm)
        # Verify save_session was NOT called to corrupt session
        mock_save.assert_not_called()
        mock_clear.assert_not_called()

    def test_status_command_synonyms_and_transliterations(self):
        valid_synonyms = [
            "status",
            "STATUS",
            "Status",
            "status!",
            " स्थिती ",
            "स्थिति",
            "report",
            "REPORT",
            "advisory",
            "check",
            "check status",
            "farm status",
            "my status",
            "crop status",
            "शेती स्थिती",
            "खेत स्थिति",
        ]
        for syn in valid_synonyms:
            self.assertTrue(is_status_command(syn), f"Failed to match valid status command: {syn}")

        invalid_commands = [
            "restart",
            "language",
            "hello",
            "hi",
            "1",
            "Cotton",
            "random text",
        ]
        for inv in invalid_commands:
            self.assertFalse(is_status_command(inv), f"Incorrectly matched invalid status command: {inv}")

    def test_get_latest_advisory_sql_query_contract(self):
        """Verifies that get_latest_advisory uses parameterized farm_id and orders DESC LIMIT 1."""
        import inspect
        src = inspect.getsource(get_latest_advisory)
        self.assertIn("WHERE farm_id = %s", src)
        self.assertIn("ORDER BY created_at DESC, id DESC", src)
        self.assertIn("LIMIT 1", src)



class TestAutomatedPipelineAndStatusEnhancements(unittest.TestCase):
    """
    Unit tests for automated pipeline triggering and status command enhancements:
    1. In-flight status processing check in en, mr, hi when pipeline is active.
    2. End-to-end run_pipeline_for_farm with mocked satellite/weather inputs and localized advisory delivery.
    3. Failure handling in run_pipeline_for_farm sending localized failure notices.
    4. Concurrency deduplication in run_pipeline_for_farm.
    5. trigger_pipeline_for_farm async (thread) and sync execution modes.
    6. Command isolation in AWAITING_NAME for 'status' and 'language'.
    7. Command isolation in AWAITING_CROP for 'status' and 'language'.
    8. Exact template formatting for welcome_and_language across en, mr, hi.
    9. Exact template formatting for satellite monitoring notices in registration_success and farm_updated_success.
    """

    def setUp(self):
        self.mock_sender = MagicMock(return_value=True)
        self.sessions = {}
        self.processed = set()
        self.farms = {}
        self.advisories = {}
        with test_pipeline_module._ACTIVE_PIPELINE_LOCK:
            test_pipeline_module._ACTIVE_PIPELINE_RUNS.clear()

    def tearDown(self):
        with test_pipeline_module._ACTIVE_PIPELINE_LOCK:
            test_pipeline_module._ACTIVE_PIPELINE_RUNS.clear()

    def _mock_get_session(self, phone, db_url=None):
        return self.sessions.get(phone)

    def _mock_save_session(self, phone, state, name=None, crop=None, acreage_acres=None, preferred_language=None, pending_lat=None, pending_lon=None, db_url=None, **kwargs):
        sess = self.sessions.get(phone, {"phone": phone})
        sess["state"] = state
        if name is not None:
            sess["name"] = name
        if crop is not None:
            sess["crop"] = crop
        if acreage_acres is not None:
            sess["acreage_acres"] = acreage_acres
        if preferred_language is not None:
            sess["preferred_language"] = preferred_language
        p_lat = pending_lat if pending_lat is not None else kwargs.get("pending_lat")
        if p_lat is not None:
            sess["pending_lat"] = p_lat
        p_lon = pending_lon if pending_lon is not None else kwargs.get("pending_lon")
        if p_lon is not None:
            sess["pending_lon"] = p_lon
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
    def test_status_processing_message_multilingual(
        self, mock_unclaim, mock_claim, mock_clear, mock_save, mock_get_sess, mock_get_farm
    ):
        mock_get_farm.side_effect = self._mock_get_farm
        mock_get_sess.side_effect = self._mock_get_session
        mock_claim.side_effect = self._mock_claim_message
        mock_unclaim.side_effect = self._mock_unclaim_message

        cases = [
            ("en", "KhetSense Advisory Processing", "Farm ID: #101", "919876543201"),
            ("mr", "खेतसेन्स सल्ला प्रक्रिया सुरू आहे", "शेत आयडी: #101", "919876543202"),
            ("hi", "खेतसेंस सलाह प्रक्रिया जारी है", "फार्म आईडी: #101", "919876543203"),
        ]

        for lang, expected_phrase, expected_id, phone in cases:
            self.farms[phone] = {
                "id": 101,
                "farmer_name": "Test Farmer",
                "crop_name": "Cotton",
                "preferred_language": lang,
            }
            with test_pipeline_module._ACTIVE_PIPELINE_LOCK:
                test_pipeline_module._ACTIVE_PIPELINE_RUNS.add(101)

            try:
                msg = {"id": f"wamid.proc.{lang}", "from": phone, "type": "text", "text": {"body": "status"}}
                res = handle_incoming(msg, outbound_sender=self.mock_sender)
                self.assertEqual(res["status"], "advisory_processing")
                self.assertEqual(res["farm_id"], 101)
                self.assertEqual(res["language"], lang)

                sent_msg = self.mock_sender.call_args[0][1]
                self.assertIn(expected_phrase, sent_msg)
                self.assertIn(expected_id, sent_msg)
            finally:
                with test_pipeline_module._ACTIVE_PIPELINE_LOCK:
                    test_pipeline_module._ACTIVE_PIPELINE_RUNS.discard(101)

    @patch.dict(os.environ, {"ENABLE_VOICE_ADVISORY": "false"})
    @patch("pipeline.test_pipeline.deliver_voice_advisory")
    @patch("pipeline.test_pipeline.get_tts_provider")
    @patch("pipeline.test_pipeline.save_advisory_to_database")
    @patch("pipeline.test_pipeline.fetch_openweather_forecast")
    @patch("pipeline.test_pipeline.fetch_smap_soil_moisture")
    @patch("pipeline.test_pipeline.fetch_sentinel2_indices")
    @patch("pipeline.test_pipeline.ee")
    @patch("pipeline.test_pipeline.authenticate_earth_engine")
    @patch("pipeline.test_pipeline.get_farm_from_database")
    def test_run_pipeline_for_farm_success_and_whatsapp_delivery(
        self,
        mock_get_farm_db,
        mock_auth_ee,
        mock_ee,
        mock_fetch_s2,
        mock_fetch_smap,
        mock_fetch_owm,
        mock_save_adv,
        mock_get_tts,
        mock_deliver_voice,
    ):
        mock_get_farm_db.return_value = {
            "id": 5,
            "farmer_name": "Suresh Deshmukh",
            "mobile_number": "919876543255",
            "preferred_language": "mr",
            "crop_name": "Cotton",
            "ee_coords": [[77.1, 20.5], [77.2, 20.5], [77.2, 20.6], [77.1, 20.6], [77.1, 20.5]],
            "centroid_lat": 20.55,
            "centroid_lon": 77.15,
            "land_cover_code": 40,
            "land_cover_class": "Cropland",
        }
        mock_fetch_s2.return_value = (0.25, 0.10, {"date": "2026-03-29", "cloud_pct": 2.0}, None)
        mock_fetch_smap.return_value = (0.12, {"date": "2026-03-29"}, None)
        mock_fetch_owm.return_value = (1.5, None)
        mock_save_adv.return_value = {
            "id": 88,
            "farm_id": 5,
            "observation_date": "2026-03-29",
            "stress_level": "Severe Stress",
            "created_at": "2026-03-29 11:00:00",
        }

        res = test_pipeline_module.run_pipeline_for_farm(
            farm_id=5,
            outbound_sender=self.mock_sender,
            auto_send_advisory=True,
        )

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["farm_id"], 5)
        self.assertEqual(res["advisory_id"], 88)
        self.assertTrue(res["advisory_sent"])
        self.assertFalse(res["voice_sent"])
        self.assertEqual(res["preferred_language"], "mr")
        self.mock_sender.assert_called_once()
        mock_get_tts.assert_not_called()
        mock_deliver_voice.assert_not_called()
        sent_phone, sent_text = self.mock_sender.call_args[0]
        self.assertEqual(sent_phone, "919876543255")
        self.assertIn("शेत आयडी: #5", sent_text)
        self.assertIn("कापूस", sent_text)

    @patch("pipeline.test_pipeline.fetch_sentinel2_indices")
    @patch("pipeline.test_pipeline.ee")
    @patch("pipeline.test_pipeline.authenticate_earth_engine")
    @patch("pipeline.test_pipeline.get_farm_from_database")
    def test_run_pipeline_for_farm_failure_sends_localized_notice(
        self,
        mock_get_farm_db,
        mock_auth_ee,
        mock_ee,
        mock_fetch_s2,
    ):
        mock_get_farm_db.return_value = {
            "id": 7,
            "farmer_name": "Amit Kumar",
            "mobile_number": "919876543277",
            "preferred_language": "hi",
            "crop_name": "Wheat",
            "ee_coords": [[78.1, 21.5], [78.2, 21.5], [78.2, 21.6], [78.1, 21.6], [78.1, 21.5]],
            "centroid_lat": 21.55,
            "centroid_lon": 78.15,
        }
        mock_fetch_s2.side_effect = RuntimeError("GEE connection timed out")

        res = test_pipeline_module.run_pipeline_for_farm(
            farm_id=7,
            outbound_sender=self.mock_sender,
            auto_send_advisory=True,
        )

        self.assertEqual(res["status"], "error")
        self.assertEqual(res["farm_id"], 7)
        self.assertIn("GEE connection timed out", res["error"])

        self.mock_sender.assert_called_once()
        sent_phone, sent_text = self.mock_sender.call_args[0]
        self.assertEqual(sent_phone, "919876543277")
        self.assertIn("फार्म आईडी: #7", sent_text)
        self.assertIn("अस्थायी देरी हो रही है", sent_text)

    def test_run_pipeline_for_farm_concurrency_deduplication(self):
        with test_pipeline_module._ACTIVE_PIPELINE_LOCK:
            test_pipeline_module._ACTIVE_PIPELINE_RUNS.add(99)

        try:
            res = test_pipeline_module.run_pipeline_for_farm(farm_id=99)
            self.assertEqual(res["status"], "already_running")
            self.assertEqual(res["farm_id"], 99)
        finally:
            with test_pipeline_module._ACTIVE_PIPELINE_LOCK:
                test_pipeline_module._ACTIVE_PIPELINE_RUNS.discard(99)

    @patch("whatsapp.registration_flow.run_pipeline_for_farm")
    def test_trigger_pipeline_for_farm_async_and_sync_modes(self, mock_run_pipeline):
        mock_run_pipeline.return_value = {"status": "success", "farm_id": 12}

        # Async mode (default)
        t = trigger_pipeline_for_farm(farm_id=12, async_mode=True)
        import threading
        self.assertIsInstance(t, threading.Thread)
        t.join(timeout=1.0)

        # Sync mode
        res_sync = trigger_pipeline_for_farm(farm_id=12, async_mode=False)
        self.assertEqual(res_sync["status"], "success")

    @patch("whatsapp.registration_flow.get_registered_farm")
    @patch("whatsapp.registration_flow.get_session")
    @patch("whatsapp.registration_flow.save_session")
    @patch("whatsapp.registration_flow.clear_session")
    @patch("whatsapp.registration_flow.claim_message")
    @patch("whatsapp.registration_flow.unclaim_message")
    def test_command_isolation_awaiting_name(
        self, mock_unclaim, mock_claim, mock_clear, mock_save, mock_get_sess, mock_get_farm
    ):
        phone = "919876543111"
        self.sessions[phone] = {"phone": phone, "state": "AWAITING_NAME", "preferred_language": "en"}
        mock_get_farm.side_effect = self._mock_get_farm
        mock_get_sess.side_effect = self._mock_get_session
        mock_claim.side_effect = self._mock_claim_message
        mock_unclaim.side_effect = self._mock_unclaim_message
        mock_save.side_effect = self._mock_save_session

        # Sending 'status' while awaiting name
        msg_status = {"id": "wamid.iso.1", "from": phone, "type": "text", "text": {"body": "status"}}
        res_st = handle_incoming(msg_status, outbound_sender=self.mock_sender)
        self.assertEqual(res_st["status"], "not_registered")
        self.assertNotEqual(self.sessions[phone].get("state"), "AWAITING_NAME_CONFIRMATION")
        self.assertNotEqual(self.sessions[phone].get("name"), "status")

        # Sending 'language' while awaiting name
        msg_lang = {"id": "wamid.iso.2", "from": phone, "type": "text", "text": {"body": "language"}}
        res_lang = handle_incoming(msg_lang, outbound_sender=self.mock_sender)
        self.assertEqual(res_lang["status"], "language_change_requested")
        self.assertEqual(res_lang["next_state"], "CHANGING_LANGUAGE")
        self.assertNotEqual(self.sessions[phone].get("name"), "language")

    @patch("whatsapp.registration_flow.get_registered_farm")
    @patch("whatsapp.registration_flow.get_session")
    @patch("whatsapp.registration_flow.save_session")
    @patch("whatsapp.registration_flow.clear_session")
    @patch("whatsapp.registration_flow.claim_message")
    @patch("whatsapp.registration_flow.unclaim_message")
    def test_command_isolation_awaiting_crop(
        self, mock_unclaim, mock_claim, mock_clear, mock_save, mock_get_sess, mock_get_farm
    ):
        phone = "919876543222"
        self.sessions[phone] = {"phone": phone, "state": "AWAITING_CROP", "name": "Kishor", "preferred_language": "en"}
        mock_get_farm.side_effect = self._mock_get_farm
        mock_get_sess.side_effect = self._mock_get_session
        mock_claim.side_effect = self._mock_claim_message
        mock_unclaim.side_effect = self._mock_unclaim_message
        mock_save.side_effect = self._mock_save_session

        # Sending 'status' while awaiting crop -> intercepted as status check without modifying session/crop
        msg_status = {"id": "wamid.iso.3", "from": phone, "type": "text", "text": {"body": "status"}}
        res_st = handle_incoming(msg_status, outbound_sender=self.mock_sender)
        self.assertEqual(res_st["status"], "not_registered")
        self.assertNotEqual(self.sessions[phone].get("crop"), "status")
        self.assertEqual(self.sessions[phone]["state"], "AWAITING_CROP")

        # Sending 'language' while awaiting crop -> transitions to CHANGING_LANGUAGE without modifying crop
        msg_lang = {"id": "wamid.iso.4", "from": phone, "type": "text", "text": {"body": "language"}}
        res_lang = handle_incoming(msg_lang, outbound_sender=self.mock_sender)
        self.assertEqual(res_lang["status"], "language_change_requested")
        self.assertEqual(res_lang["next_state"], "CHANGING_LANGUAGE")
        self.assertNotEqual(self.sessions[phone].get("crop"), "language")

    def test_welcome_and_language_exact_specification(self):
        msg_en = get_message("welcome_and_language", lang="en")
        self.assertIn("Welcome to KhetSense AI! 🌱", msg_en)
        self.assertIn("1. English", msg_en)
        self.assertIn("2. मराठी (Marathi)", msg_en)
        self.assertIn("3. हिन्दी (Hindi)", msg_en)
        self.assertIn("Please reply with 1, 2 or 3.", msg_en)

        msg_mr = get_message("welcome_and_language", lang="mr")
        self.assertIn("खेतसेन्स (KhetSense AI) मध्ये आपले स्वागत आहे! 🌱", msg_mr)
        self.assertIn("1. English", msg_mr)
        self.assertIn("2. मराठी (Marathi)", msg_mr)
        self.assertIn("3. हिन्दी (Hindi)", msg_mr)
        self.assertIn("कृपया 1, 2 किंवा 3 उत्तर पाठवा.", msg_mr)

        msg_hi = get_message("welcome_and_language", lang="hi")
        self.assertIn("खेतसेंस (KhetSense AI) में आपका स्वागत है! 🌱", msg_hi)
        self.assertIn("1. English", msg_hi)
        self.assertIn("2. मराठी (Marathi)", msg_hi)
        self.assertIn("3. हिन्दी (Hindi)", msg_hi)
        self.assertIn("कृपया 1, 2 या 3 लिखकर भेजें।", msg_hi)

    def test_satellite_monitoring_notifications_in_success_templates(self):
        reg_en = get_message("registration_success", lang="en", farm_id=1, name="A", crop="Cotton", area=2.5, boundary_source="b", lat=20.0, lon=77.0)
        self.assertIn("Satellite monitoring is starting now; your first irrigation advisory will be sent shortly.", reg_en)

        reg_mr = get_message("registration_success", lang="mr", farm_id=1, name="A", crop="कापूस", area=2.5, boundary_source="b", lat=20.0, lon=77.0)
        self.assertIn("उपग्रह निरीक्षण सुरू होत आहे; तुमचा पहिला सिंचन सल्ला लवकरच पाठवला जाईल.", reg_mr)

        up_hi = get_message("farm_updated_success", lang="hi", farm_id=1, name="A", crop="कपास", area=2.5, boundary_source="b", lat=20.0, lon=77.0)
        self.assertIn("उपग्रह निगरानी अपडेट हो रही है; आपकी नवीनतम सिंचाई सलाह जल्द ही भेज दी जाएगी।", up_hi)



class TestFarmLocationSelectionAndValidation(unittest.TestCase):
    """
    Comprehensive tests for:
    1. Farm Location Selection Flow (at-farm, away, direct pin, rejection/re-prompt, returning farmer reuse).
    2. Agricultural Location Validation Engine (Cases A, B, C, D, E, invalid coordinates).
    3. Pipeline integration (withholding advisory on unsuitable location, localized notices).
    4. Multilingual validation notices (English, Marathi, Hindi).
    """

    def setUp(self):
        self.mock_sender = MagicMock(return_value=True)
        self.sessions = {}
        self.processed = set()
        self.farms = {}
        with test_pipeline_module._ACTIVE_PIPELINE_LOCK:
            test_pipeline_module._ACTIVE_PIPELINE_RUNS.clear()

    def tearDown(self):
        with test_pipeline_module._ACTIVE_PIPELINE_LOCK:
            test_pipeline_module._ACTIVE_PIPELINE_RUNS.clear()

    def _mock_get_session(self, phone, db_url=None):
        return self.sessions.get(phone)

    def _mock_save_session(self, phone, state, name=None, crop=None, acreage_acres=None, preferred_language=None, pending_lat=None, pending_lon=None, db_url=None, **kwargs):
        sess = self.sessions.get(phone, {"phone": phone})
        sess["state"] = state
        if name is not None:
            sess["name"] = name
        if crop is not None:
            sess["crop"] = crop
        if acreage_acres is not None:
            sess["acreage_acres"] = acreage_acres
        if preferred_language is not None:
            sess["preferred_language"] = preferred_language
        p_lat = pending_lat if pending_lat is not None else kwargs.get("pending_lat")
        if p_lat is not None:
            sess["pending_lat"] = p_lat
        p_lon = pending_lon if pending_lon is not None else kwargs.get("pending_lon")
        if p_lon is not None:
            sess["pending_lon"] = p_lon
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

    # --------------------------------------------------------------------------
    # 1. Location Selection State Transitions
    # --------------------------------------------------------------------------

    @patch("whatsapp.registration_flow.get_registered_farm")
    @patch("whatsapp.registration_flow.get_session")
    @patch("whatsapp.registration_flow.save_session")
    @patch("whatsapp.registration_flow.clear_session")
    @patch("whatsapp.registration_flow.claim_message")
    @patch("whatsapp.registration_flow.unclaim_message")
    def test_location_choice_at_farm(
        self, mock_unclaim, mock_claim, mock_clear, mock_save, mock_get_sess, mock_get_farm
    ):
        phone = "919876543101"
        self.sessions[phone] = {
            "phone": phone,
            "state": "AWAITING_LOCATION_CHOICE",
            "name": "Devidas",
            "crop": "Cotton",
            "acreage_acres": 3.0,
            "preferred_language": "en",
        }
        mock_get_farm.side_effect = self._mock_get_farm
        mock_get_sess.side_effect = self._mock_get_session
        mock_claim.side_effect = self._mock_claim_message
        mock_unclaim.side_effect = self._mock_unclaim_message
        mock_save.side_effect = self._mock_save_session

        # Farmer chooses Option 1 ("At farm")
        msg = {"id": "wamid.loc.1", "from": phone, "type": "text", "text": {"body": "1"}}
        res = handle_incoming(msg, outbound_sender=self.mock_sender)
        self.assertEqual(res["status"], "location_method_selected")
        self.assertEqual(res["method"], "at_farm")
        self.assertEqual(res["next_state"], "AWAITING_LOCATION")
        self.assertEqual(self.sessions[phone]["state"], "AWAITING_LOCATION")
        self.mock_sender.assert_called_with(phone, get_message("location_at_farm_prompt", lang="en"))

    @patch("whatsapp.registration_flow.get_registered_farm")
    @patch("whatsapp.registration_flow.get_session")
    @patch("whatsapp.registration_flow.save_session")
    @patch("whatsapp.registration_flow.clear_session")
    @patch("whatsapp.registration_flow.claim_message")
    @patch("whatsapp.registration_flow.unclaim_message")
    def test_location_choice_away(
        self, mock_unclaim, mock_claim, mock_clear, mock_save, mock_get_sess, mock_get_farm
    ):
        phone = "919876543102"
        self.sessions[phone] = {
            "phone": phone,
            "state": "AWAITING_LOCATION_CHOICE",
            "name": "Devidas",
            "crop": "Cotton",
            "acreage_acres": 3.0,
            "preferred_language": "mr",
        }
        mock_get_farm.side_effect = self._mock_get_farm
        mock_get_sess.side_effect = self._mock_get_session
        mock_claim.side_effect = self._mock_claim_message
        mock_unclaim.side_effect = self._mock_unclaim_message
        mock_save.side_effect = self._mock_save_session

        # Farmer chooses Option 2 ("Away from farm" in Marathi)
        msg = {"id": "wamid.loc.2", "from": phone, "type": "text", "text": {"body": "2"}}
        res = handle_incoming(msg, outbound_sender=self.mock_sender)
        self.assertEqual(res["status"], "location_method_selected")
        self.assertEqual(res["method"], "away")
        self.assertEqual(res["next_state"], "AWAITING_LOCATION")
        self.assertEqual(self.sessions[phone]["state"], "AWAITING_LOCATION")
        self.mock_sender.assert_called_with(phone, get_message("location_away_prompt", lang="mr"))

    @patch("whatsapp.registration_flow.get_registered_farm")
    @patch("whatsapp.registration_flow.get_session")
    @patch("whatsapp.registration_flow.save_session")
    @patch("whatsapp.registration_flow.clear_session")
    @patch("whatsapp.registration_flow.claim_message")
    @patch("whatsapp.registration_flow.unclaim_message")
    def test_location_choice_direct_pin(
        self, mock_unclaim, mock_claim, mock_clear, mock_save, mock_get_sess, mock_get_farm
    ):
        phone = "919876543103"
        self.sessions[phone] = {
            "phone": phone,
            "state": "AWAITING_LOCATION_CHOICE",
            "name": "Raju",
            "crop": "Soybean",
            "acreage_acres": 2.5,
            "preferred_language": "hi",
        }
        mock_get_farm.side_effect = self._mock_get_farm
        mock_get_sess.side_effect = self._mock_get_session
        mock_claim.side_effect = self._mock_claim_message
        mock_unclaim.side_effect = self._mock_unclaim_message
        mock_save.side_effect = self._mock_save_session

        # Farmer sends a location pin directly instead of 1 or 2
        msg = {
            "id": "wamid.loc.3",
            "from": phone,
            "type": "location",
            "location": {"latitude": 20.7000, "longitude": 77.0000},
        }
        res = handle_incoming(msg, outbound_sender=self.mock_sender)
        self.assertEqual(res["status"], "location_confirmation_requested")
        self.assertEqual(res["next_state"], "AWAITING_LOCATION_CONFIRMATION")
        self.assertEqual(res["lat"], 20.7000)
        self.assertEqual(res["lon"], 77.0000)
        self.assertEqual(self.sessions[phone]["pending_lat"], 20.7000)
        self.assertEqual(self.sessions[phone]["pending_lon"], 77.0000)
        self.mock_sender.assert_called_with(
            phone,
            get_message("location_confirm_prompt", lang="hi", lat=20.7000, lon=77.0000),
        )

    @patch("whatsapp.registration_flow.get_registered_farm")
    @patch("whatsapp.registration_flow.get_session")
    @patch("whatsapp.registration_flow.save_session")
    @patch("whatsapp.registration_flow.clear_session")
    @patch("whatsapp.registration_flow.claim_message")
    @patch("whatsapp.registration_flow.unclaim_message")
    def test_location_confirmation_rejection_reprompts(
        self, mock_unclaim, mock_claim, mock_clear, mock_save, mock_get_sess, mock_get_farm
    ):
        phone = "919876543104"
        self.sessions[phone] = {
            "phone": phone,
            "state": "AWAITING_LOCATION_CONFIRMATION",
            "name": "Kiran",
            "crop": "Wheat",
            "acreage_acres": 2.0,
            "preferred_language": "mr",
            "pending_lat": 20.5026,
            "pending_lon": 77.1419,
        }
        mock_get_farm.side_effect = self._mock_get_farm
        mock_get_sess.side_effect = self._mock_get_session
        mock_claim.side_effect = self._mock_claim_message
        mock_unclaim.side_effect = self._mock_unclaim_message
        mock_save.side_effect = self._mock_save_session

        # Farmer says NO ("नाही" in Marathi)
        msg = {"id": "wamid.loc.4", "from": phone, "type": "text", "text": {"body": "नाही"}}
        res = handle_incoming(msg, outbound_sender=self.mock_sender)
        self.assertEqual(res["status"], "location_rejected")
        self.assertEqual(res["next_state"], "AWAITING_LOCATION")
        self.assertEqual(self.sessions[phone]["state"], "AWAITING_LOCATION")
        self.mock_sender.assert_called_with(phone, get_message("location_reenter_prompt", lang="mr"))

    @patch("whatsapp.registration_flow.get_registered_farm")
    @patch("whatsapp.registration_flow.get_session")
    @patch("whatsapp.registration_flow.save_session")
    @patch("whatsapp.registration_flow.clear_session")
    @patch("whatsapp.registration_flow.claim_message")
    @patch("whatsapp.registration_flow.unclaim_message")
    def test_location_confirmation_candidate_updated_by_new_pin(
        self, mock_unclaim, mock_claim, mock_clear, mock_save, mock_get_sess, mock_get_farm
    ):
        phone = "919876543105"
        self.sessions[phone] = {
            "phone": phone,
            "state": "AWAITING_LOCATION_CONFIRMATION",
            "name": "Sunil",
            "crop": "Cotton",
            "acreage_acres": 2.5,
            "preferred_language": "en",
            "pending_lat": 20.5000,
            "pending_lon": 77.1400,
        }
        mock_get_farm.side_effect = self._mock_get_farm
        mock_get_sess.side_effect = self._mock_get_session
        mock_claim.side_effect = self._mock_claim_message
        mock_unclaim.side_effect = self._mock_unclaim_message
        mock_save.side_effect = self._mock_save_session

        # Farmer drops a new, corrected pin while awaiting confirmation
        msg = {
            "id": "wamid.loc.5",
            "from": phone,
            "type": "location",
            "location": {"latitude": 20.5500, "longitude": 77.2000},
        }
        res = handle_incoming(msg, outbound_sender=self.mock_sender)
        self.assertEqual(res["status"], "location_candidate_updated")
        self.assertEqual(res["next_state"], "AWAITING_LOCATION_CONFIRMATION")
        self.assertEqual(res["lat"], 20.5500)
        self.assertEqual(res["lon"], 77.2000)
        self.assertEqual(self.sessions[phone]["pending_lat"], 20.5500)
        self.assertEqual(self.sessions[phone]["pending_lon"], 77.2000)
        self.mock_sender.assert_called_with(
            phone,
            get_message("location_confirm_prompt", lang="en", lat=20.5500, lon=77.2000),
        )

    @patch("whatsapp.registration_flow.get_registered_farm")
    @patch("whatsapp.registration_flow.get_session")
    @patch("whatsapp.registration_flow.save_session")
    @patch("whatsapp.registration_flow.clear_session")
    @patch("whatsapp.registration_flow.claim_message")
    @patch("whatsapp.registration_flow.unclaim_message")
    def test_returning_farmer_reuse_saved_location(
        self, mock_unclaim, mock_claim, mock_clear, mock_save, mock_get_sess, mock_get_farm
    ):
        phone = "919876543106"
        # Registered farm exists with previously saved coordinates
        self.farms[phone] = {
            "id": 15,
            "farmer_name": "Vijay Shinde",
            "crop_name": "Cotton",
            "farm_area": 4.0,
            "preferred_language": "en",
            "pin_lat": 20.50260,
            "pin_lon": 77.14195,
        }
        self.sessions[phone] = {
            "phone": phone,
            "state": "AWAITING_LOCATION_CHOICE",
            "name": "Vijay Shinde",
            "crop": "Cotton",
            "acreage_acres": 4.0,
            "preferred_language": "en",
        }
        mock_get_farm.side_effect = self._mock_get_farm
        mock_get_sess.side_effect = self._mock_get_session
        mock_claim.side_effect = self._mock_claim_message
        mock_unclaim.side_effect = self._mock_unclaim_message
        mock_save.side_effect = self._mock_save_session

        # Returning farmer chooses Option 1 ("Keep current saved location")
        msg = {"id": "wamid.loc.6", "from": phone, "type": "text", "text": {"body": "1"}}
        res = handle_incoming(msg, outbound_sender=self.mock_sender)
        self.assertEqual(res["status"], "location_confirmation_requested")
        self.assertTrue(res.get("reused_saved_location"))
        self.assertEqual(res["lat"], 20.50260)
        self.assertEqual(res["lon"], 77.14195)
        self.assertEqual(self.sessions[phone]["pending_lat"], 20.50260)
        self.assertEqual(self.sessions[phone]["pending_lon"], 77.14195)
        self.mock_sender.assert_called_with(
            phone,
            get_message("location_confirm_prompt", lang="en", lat=20.50260, lon=77.14195),
        )

    # --------------------------------------------------------------------------
    # 2. Agricultural Location Validator Core Logic (Cases A–E)
    # --------------------------------------------------------------------------

    def test_validator_case_a_suitable_cropland(self):
        res = validate_agricultural_location(
            centroid_lat=20.5026,
            centroid_lon=77.1419,
            land_cover_code=40,
            land_cover_class="Cropland",
            cloud_cover_pct=4.5,
            has_smap=True,
            has_weather=True,
            farm_area_acres=2.5,
        )
        self.assertEqual(res["outcome"], VALIDATION_SUITABLE)
        self.assertTrue(res["is_suitable_for_advisory"])
        self.assertEqual(res["land_cover_class"], "Cropland")
        self.assertTrue(res["resolution_adequate"])

    def test_validator_case_b_likely_urban(self):
        res = validate_agricultural_location(
            centroid_lat=19.0760,
            centroid_lon=72.8777,
            land_cover_code=50,
            land_cover_class="Built-up",
            cloud_cover_pct=5.0,
            has_smap=True,
            has_weather=True,
        )
        self.assertEqual(res["outcome"], VALIDATION_URBAN)
        self.assertFalse(res["is_suitable_for_advisory"])
        self.assertEqual(res["land_cover_class"], "Built-up")
        self.assertIn("urban", res["reason"].lower())

    def test_validator_case_c_barren_or_uncertain_class(self):
        res = validate_agricultural_location(
            centroid_lat=26.9124,
            centroid_lon=75.7873,
            land_cover_code=60,
            land_cover_class="Bare / sparse vegetation",
            cloud_cover_pct=2.0,
            has_smap=True,
            has_weather=True,
        )
        self.assertEqual(res["outcome"], VALIDATION_BARREN_UNCERTAIN)
        self.assertFalse(res["is_suitable_for_advisory"])
        self.assertIn("bare", res["reason"].lower())

    def test_validator_case_c_barren_by_low_ndvi(self):
        res = validate_agricultural_location(
            centroid_lat=20.5026,
            centroid_lon=77.1419,
            mean_ndvi=0.07,
            cloud_cover_pct=2.0,
            has_smap=True,
            has_weather=True,
        )
        self.assertEqual(res["outcome"], VALIDATION_BARREN_UNCERTAIN)
        self.assertFalse(res["is_suitable_for_advisory"])
        self.assertIn("NDVI < 0.10", res["land_cover_class"])

    def test_validator_case_d_cloudy_satellite_data(self):
        res = validate_agricultural_location(
            centroid_lat=20.5026,
            centroid_lon=77.1419,
            land_cover_code=40,
            cloud_cover_pct=32.0,
            has_smap=True,
            has_weather=True,
        )
        self.assertEqual(res["outcome"], VALIDATION_INSUFFICIENT_IMAGERY)
        self.assertFalse(res["is_suitable_for_advisory"])
        self.assertIn("cloud coverage", res["reason"].lower())

    def test_validator_case_d_missing_sentinel_scene(self):
        res = validate_agricultural_location(
            centroid_lat=20.5026,
            centroid_lon=77.1419,
            s2_err="No valid Sentinel-2 scenes found in 14-day window",
            has_smap=True,
            has_weather=True,
        )
        self.assertEqual(res["outcome"], VALIDATION_INSUFFICIENT_IMAGERY)
        self.assertFalse(res["is_suitable_for_advisory"])
        self.assertIn("no cloud-free", res["reason"].lower())

    def test_validator_case_e_incomplete_auxiliary(self):
        res = validate_agricultural_location(
            centroid_lat=20.5026,
            centroid_lon=77.1419,
            land_cover_code=40,
            land_cover_class="Cropland",
            cloud_cover_pct=5.0,
            has_smap=False,
            has_weather=True,
        )
        self.assertEqual(res["outcome"], VALIDATION_INCOMPLETE_AUXILIARY)
        self.assertTrue(res["is_suitable_for_advisory"])  # proceeds with safe fallback
        self.assertIn("SMAP Soil Moisture", res["reason"])

    def test_validator_invalid_coordinates_out_of_india(self):
        res = validate_agricultural_location(
            centroid_lat=51.5074,
            centroid_lon=-0.1278,  # London
        )
        self.assertEqual(res["outcome"], VALIDATION_INVALID_COORDINATES)
        self.assertFalse(res["is_suitable_for_advisory"])
        self.assertIn("outside India", res["reason"])

    # --------------------------------------------------------------------------
    # 3. Pipeline Integration & Advisory Withholding
    # --------------------------------------------------------------------------

    @patch("pipeline.test_pipeline.save_advisory_to_database")
    @patch("pipeline.test_pipeline.fetch_openweather_forecast")
    @patch("pipeline.test_pipeline.fetch_smap_soil_moisture")
    @patch("pipeline.test_pipeline.fetch_sentinel2_indices")
    @patch("pipeline.test_pipeline.ee")
    @patch("pipeline.test_pipeline.authenticate_earth_engine")
    @patch("pipeline.test_pipeline.get_farm_from_database")
    def test_pipeline_run_withholds_advisory_on_urban_validation_failure(
        self,
        mock_get_farm_db,
        mock_auth_ee,
        mock_ee,
        mock_fetch_s2,
        mock_fetch_smap,
        mock_fetch_owm,
        mock_save_adv,
    ):
        mock_get_farm_db.return_value = {
            "id": 99,
            "farmer_name": "City Resident",
            "mobile_number": "919876543999",
            "preferred_language": "en",
            "crop_name": "Cotton",
            "ee_coords": [[72.8, 19.0], [72.9, 19.0], [72.9, 19.1], [72.8, 19.1], [72.8, 19.0]],
            "centroid_lat": 19.05,
            "centroid_lon": 72.85,
            "farm_area": 1.0,
        }
        mock_fetch_s2.return_value = (0.12, 0.05, {"date": "2026-03-29", "cloud_cover_pct": 5.0}, None)
        mock_fetch_smap.return_value = (0.10, {"date": "2026-03-29"}, None)
        mock_fetch_owm.return_value = (0.0, None)

        with patch("pipeline.test_pipeline.validate_agricultural_location") as mock_val:
            mock_val.return_value = {
                "outcome": VALIDATION_URBAN,
                "is_suitable_for_advisory": False,
                "land_cover_class": "Built-up",
                "land_cover_code": 50,
                "reason": "Urban area detected.",
            }

            res = test_pipeline_module.run_pipeline_for_farm(
                farm_id=99,
                outbound_sender=self.mock_sender,
                auto_send_advisory=True,
            )

            self.assertEqual(res["status"], "validation_failed")
            self.assertEqual(res["outcome"], VALIDATION_URBAN)
            self.assertFalse(res["advisory_sent"])
            mock_save_adv.assert_not_called()
            self.mock_sender.assert_called_once()
            sent_phone, sent_text = self.mock_sender.call_args[0]
            self.assertEqual(sent_phone, "919876543999")
            self.assertIn("urban or built-up area", sent_text)

    @patch("pipeline.test_pipeline.save_advisory_to_database")
    @patch("pipeline.test_pipeline.fetch_openweather_forecast")
    @patch("pipeline.test_pipeline.fetch_smap_soil_moisture")
    @patch("pipeline.test_pipeline.fetch_sentinel2_indices")
    @patch("pipeline.test_pipeline.ee")
    @patch("pipeline.test_pipeline.authenticate_earth_engine")
    @patch("pipeline.test_pipeline.get_farm_from_database")
    def test_pipeline_run_withholds_advisory_on_fallow_validation_failure(
        self,
        mock_get_farm_db,
        mock_auth_ee,
        mock_ee,
        mock_fetch_s2,
        mock_fetch_smap,
        mock_fetch_owm,
        mock_save_adv,
    ):
        mock_get_farm_db.return_value = {
            "id": 100,
            "farmer_name": "संजय शिंदे",
            "mobile_number": "919876543100",
            "preferred_language": "mr",
            "crop_name": "Cotton",
            "ee_coords": [[77.1, 20.5], [77.2, 20.5], [77.2, 20.6], [77.1, 20.6], [77.1, 20.5]],
            "centroid_lat": 20.55,
            "centroid_lon": 77.15,
            "farm_area": 2.0,
        }
        mock_fetch_s2.return_value = (0.05, 0.01, {"date": "2026-03-29", "cloud_cover_pct": 3.0}, None)
        mock_fetch_smap.return_value = (0.08, {"date": "2026-03-29"}, None)
        mock_fetch_owm.return_value = (0.0, None)

        with patch("pipeline.test_pipeline.validate_agricultural_location") as mock_val:
            mock_val.return_value = {
                "outcome": VALIDATION_BARREN_UNCERTAIN,
                "is_suitable_for_advisory": False,
                "land_cover_class": "Bare / sparse vegetation",
                "reason": "Barren/fallow land detected.",
            }

            res = test_pipeline_module.run_pipeline_for_farm(
                farm_id=100,
                outbound_sender=self.mock_sender,
                auto_send_advisory=True,
            )

            self.assertEqual(res["status"], "validation_failed")
            self.assertEqual(res["outcome"], VALIDATION_BARREN_UNCERTAIN)
            self.assertFalse(res["advisory_sent"])
            mock_save_adv.assert_not_called()
            self.mock_sender.assert_called_once()
            sent_phone, sent_text = self.mock_sender.call_args[0]
            self.assertEqual(sent_phone, "919876543100")
            self.assertIn("पडिक", sent_text)

    # --------------------------------------------------------------------------
    # 4. Multilingual Validation Notice Templates
    # --------------------------------------------------------------------------

    def test_multilingual_validation_templates_content(self):
        # Urban notices
        self.assertIn("urban or built-up area", get_message("location_validation_urban", lang="en"))
        self.assertIn("शहरी किंवा इमारतींचे क्षेत्र", get_message("location_validation_urban", lang="mr"))
        self.assertIn("शहरी या निर्माण क्षेत्र", get_message("location_validation_urban", lang="hi"))

        # Fallow notices
        self.assertIn("newly sown, fallow, harvested", get_message("location_validation_fallow", lang="en"))
        self.assertIn("पडिक", get_message("location_validation_fallow", lang="mr"))
        self.assertIn("परती, खाली", get_message("location_validation_fallow", lang="hi"))

        # Satellite unavailable notices: asks farmer to check later / send status and avoids false promises of automatic recheck
        sat_en = get_message("location_validation_satellite_unavailable", lang="en")
        sat_mr = get_message("location_validation_satellite_unavailable", lang="mr")
        sat_hi = get_message("location_validation_satellite_unavailable", lang="hi")

        self.assertIn("unavailable or obstructed by heavy clouds", sat_en)
        self.assertIn("check again later or send 'status'", sat_en)
        self.assertNotIn("automatically recheck", sat_en)

        self.assertIn("ढगांमुळे (>२०%)", sat_mr)
        self.assertIn("'status' पाठवा", sat_mr)
        self.assertNotIn("आम्ही पुन्हा तपासू", sat_mr)

        self.assertIn("घने बादलों (>20%)", sat_hi)
        self.assertIn("'status' लिखकर भेजें", sat_hi)
        self.assertNotIn("हम पुनः जांच करेंगे", sat_hi)

        # Location choice prompts
        self.assertIn("How would you like to share your farm location?", get_message("location_choice_prompt", lang="en", acreage_str="2.50 acres"))
        self.assertIn("तुमच्या शेताचे स्थान (लोकेशन) कसे निवडायचे आहे?", get_message("location_choice_prompt", lang="mr", acreage_str="2.50 एकर"))
        self.assertIn("आप अपने खेत का स्थान (लोकेशन) कैसे चुनना चाहते हैं?", get_message("location_choice_prompt", lang="hi", acreage_str="2.50 एकड़"))

        # Returning farmer choice prompts
        self.assertIn("We have your previously saved farm location", get_message("location_choice_returning_prompt", lang="en", farm_id=1, name="A", crop="Cotton", lat=20.0, lon=77.0))
        self.assertIn("आमच्याकडे तुमचे आधीचे सेव्ह केलेले शेताचे स्थान आहे", get_message("location_choice_returning_prompt", lang="mr", farm_id=1, name="A", crop="कापूस", lat=20.0, lon=77.0))
        self.assertIn("हमारे पास आपके खेत का पहले से सहेजा गया स्थान है", get_message("location_choice_returning_prompt", lang="hi", farm_id=1, name="A", crop="कपास", lat=20.0, lon=77.0))

    # --------------------------------------------------------------------------
    # 5. Cloud Metadata Handling & Resolution (Issue 3)
    # --------------------------------------------------------------------------

    def test_validator_cloud_pct_legacy_and_modern_keys(self):
        # 1. Direct explicit argument takes precedence
        res = validate_agricultural_location(
            centroid_lat=20.5026,
            centroid_lon=77.1419,
            cloud_cover_pct=15.0,
            s2_meta={"cloud_cover_pct": 5.0, "cloud_pct": 3.0},
        )
        self.assertEqual(res["cloud_cover_pct"], 15.0)

        # 2. Modern key in s2_meta ('cloud_cover_pct')
        res = validate_agricultural_location(
            centroid_lat=20.5026,
            centroid_lon=77.1419,
            s2_meta={"cloud_cover_pct": 12.0},
        )
        self.assertEqual(res["cloud_cover_pct"], 12.0)

        # 3. Legacy key in s2_meta ('cloud_pct')
        res = validate_agricultural_location(
            centroid_lat=20.5026,
            centroid_lon=77.1419,
            s2_meta={"cloud_pct": 25.0},
        )
        self.assertEqual(res["cloud_cover_pct"], 25.0)
        self.assertEqual(res["outcome"], VALIDATION_INSUFFICIENT_IMAGERY)
        self.assertFalse(res["is_suitable_for_advisory"])

        # 4. Fallback to legacy key when modern key is None
        res = validate_agricultural_location(
            centroid_lat=20.5026,
            centroid_lon=77.1419,
            s2_meta={"cloud_cover_pct": None, "cloud_pct": 8.5},
        )
        self.assertEqual(res["cloud_cover_pct"], 8.5)

        # 5. Missing cloud metadata in s2_meta (None / empty)
        res = validate_agricultural_location(
            centroid_lat=20.5026,
            centroid_lon=77.1419,
            s2_meta={"date": "2026-03-29"},
        )
        self.assertIsNone(res["cloud_cover_pct"])

        # 6. Non-numeric or invalid string handled safely without raising exception
        res = validate_agricultural_location(
            centroid_lat=20.5026,
            centroid_lon=77.1419,
            s2_meta={"cloud_pct": "not-a-number"},
        )
        self.assertIsNone(res["cloud_cover_pct"])

    # --------------------------------------------------------------------------
    # 6. Database Persistence & Migration 005 Contract (Issue 1)
    # --------------------------------------------------------------------------

    @patch("pipeline.test_pipeline.psycopg2.connect")
    def test_save_advisory_persists_validation_status_and_land_cover_migration_005(self, mock_connect):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        # Simulate presence of Migration 003 and 005 columns
        mock_cur.fetchall.return_value = [("recommended_action",), ("validation_status",)]
        mock_cur.fetchone.return_value = (501, 10, "2026-03-29", "Mild Stress", "2026-03-29 12:00:00")

        res = test_pipeline_module.save_advisory_to_database(
            farm_id=10,
            stress_level="Mild Stress",
            recommendation="Irrigate within 48h",
            observed_stress="Mild Stress",
            recommended_action=ACTION_SCHEDULE_IRRIGATION,
            validation_status=VALIDATION_INCOMPLETE_AUXILIARY,
            land_cover_class="Cropland",
            db_url="postgresql://mock",
        )

        self.assertEqual(res["id"], 501)
        self.assertEqual(mock_cur.execute.call_count, 2)
        insert_call = mock_cur.execute.call_args_list[1]
        insert_sql, params = insert_call[0]

        # Verify SQL contains Migration 005 columns
        self.assertIn("validation_status", insert_sql)
        self.assertIn("land_cover_class", insert_sql)
        # Verify passed parameters preserve actual validation status and do not default to SUITABLE_CROPLAND
        self.assertIn(VALIDATION_INCOMPLETE_AUXILIARY, params)
        self.assertIn("Cropland", params)
        self.assertNotIn("SUITABLE_CROPLAND", params)

    @patch("pipeline.test_pipeline.psycopg2.connect")
    def test_save_advisory_defaults_to_unvalidated_when_not_specified(self, mock_connect):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        mock_cur.fetchall.return_value = [("recommended_action",), ("validation_status",)]
        mock_cur.fetchone.return_value = (502, 10, "2026-03-29", "No Stress", "2026-03-29 12:00:00")

        test_pipeline_module.save_advisory_to_database(
            farm_id=10,
            stress_level="No Stress",
            recommendation="Adequate soil moisture",
            db_url="postgresql://mock",
        )

        insert_call = mock_cur.execute.call_args_list[1]
        _, params = insert_call[0]
        self.assertIn("UNVALIDATED", params)
        self.assertNotIn("SUITABLE_CROPLAND", params)

    @patch("pipeline.test_pipeline.psycopg2.connect")
    def test_save_advisory_backward_compatible_before_migration_005(self, mock_connect):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        # Only Migration 003 columns present (no validation_status)
        mock_cur.fetchall.return_value = [("recommended_action",)]
        mock_cur.fetchone.return_value = (503, 10, "2026-03-29", "No Stress", "2026-03-29 12:00:00")

        test_pipeline_module.save_advisory_to_database(
            farm_id=10,
            stress_level="No Stress",
            recommendation="Adequate soil moisture",
            validation_status=VALIDATION_INCOMPLETE_AUXILIARY,
            land_cover_class="Cropland",
            db_url="postgresql://mock",
        )

        insert_call = mock_cur.execute.call_args_list[1]
        insert_sql, params = insert_call[0]
        self.assertNotIn("validation_status", insert_sql)
        self.assertNotIn("land_cover_class", insert_sql)

    # --------------------------------------------------------------------------
    # 7. Incomplete Auxiliary Data & Auditing (Issues 1 & 4)
    # --------------------------------------------------------------------------

    @patch.dict(os.environ, {"ENABLE_VOICE_ADVISORY": "false"})
    @patch("pipeline.test_pipeline.deliver_voice_advisory")
    @patch("pipeline.test_pipeline.get_tts_provider")
    @patch("pipeline.test_pipeline.save_advisory_to_database")
    @patch("pipeline.test_pipeline.fetch_openweather_forecast")
    @patch("pipeline.test_pipeline.fetch_smap_soil_moisture")
    @patch("pipeline.test_pipeline.fetch_sentinel2_indices")
    @patch("pipeline.test_pipeline.ee")
    @patch("pipeline.test_pipeline.authenticate_earth_engine")
    @patch("pipeline.test_pipeline.get_farm_from_database")
    def test_pipeline_run_case_e_persists_incomplete_auxiliary_status(
        self,
        mock_get_farm_db,
        mock_auth_ee,
        mock_ee,
        mock_fetch_s2,
        mock_fetch_smap,
        mock_fetch_owm,
        mock_save_adv,
        mock_get_tts,
        mock_deliver_voice,
    ):
        mock_get_farm_db.return_value = {
            "id": 105,
            "farmer_name": "Ramesh",
            "mobile_number": "919876543105",
            "preferred_language": "en",
            "crop_name": "Cotton",
            "ee_coords": [[77.1, 20.5], [77.2, 20.5], [77.2, 20.6], [77.1, 20.6], [77.1, 20.5]],
            "centroid_lat": 20.55,
            "centroid_lon": 77.15,
            "farm_area": 2.0,
            "land_cover_code": 40,
            "land_cover_class": "Cropland",
        }
        # SMAP missing -> triggers Case E (INCOMPLETE_AUXILIARY_DATA)
        mock_fetch_s2.return_value = (0.45, 0.20, {"date": "2026-03-29", "cloud_cover_pct": 4.0}, None)
        mock_fetch_smap.return_value = (None, None, "SMAP 404 Not Found")
        mock_fetch_owm.return_value = (0.0, None)
        mock_save_adv.return_value = {
            "id": 901,
            "farm_id": 105,
            "observation_date": "2026-03-29",
            "stress_level": "No Stress",
            "created_at": "2026-03-29 12:00:00",
        }

        res = test_pipeline_module.run_pipeline_for_farm(
            farm_id=105,
            outbound_sender=self.mock_sender,
            auto_send_advisory=True,
        )

        self.assertEqual(res["status"], "success")
        self.assertFalse(res["voice_sent"])
        mock_get_tts.assert_not_called()
        mock_deliver_voice.assert_not_called()
        mock_save_adv.assert_called_once()
        save_kwargs = mock_save_adv.call_args[1]
        self.assertEqual(save_kwargs["validation_status"], VALIDATION_INCOMPLETE_AUXILIARY)

    @patch("pipeline.test_pipeline.save_advisory_to_database")
    def test_audit_validation_failure_helper_withholds_irrigation(self, mock_save_adv):
        mock_save_adv.return_value = {"id": 888, "stress_level": "VALIDATION_FAILED: LIKELY_URBAN"}
        val_result = {
            "outcome": VALIDATION_URBAN,
            "reason": "Built-up land cover detected (code 50).",
            "land_cover_class": "Built-up",
        }

        record = test_pipeline_module.audit_validation_failure(
            farm_id=200,
            val_result=val_result,
            s2_meta={"date": "2026-03-29"},
            mean_ndvi=0.12,
        )

        mock_save_adv.assert_called_once()
        call_kwargs = mock_save_adv.call_args[1]
        self.assertEqual(call_kwargs["farm_id"], 200)
        self.assertEqual(call_kwargs["validation_status"], VALIDATION_URBAN)
        self.assertEqual(call_kwargs["land_cover_class"], "Built-up")
        self.assertIsNone(call_kwargs["recommended_action"])  # Crucial: no irrigation action
        self.assertFalse(call_kwargs["guardrail_triggered"])
        self.assertIn("Irrigation advisory withheld", call_kwargs["recommendation"])
        self.assertIn("VALIDATION_FAILED", call_kwargs["stress_level"])

    @patch("pipeline.test_pipeline.save_advisory_to_database")
    @patch("pipeline.test_pipeline.fetch_openweather_forecast")
    @patch("pipeline.test_pipeline.fetch_smap_soil_moisture")
    @patch("pipeline.test_pipeline.fetch_sentinel2_indices")
    @patch("pipeline.test_pipeline.ee")
    @patch("pipeline.test_pipeline.authenticate_earth_engine")
    @patch("pipeline.test_pipeline.get_farm_from_database")
    def test_pipeline_run_audits_failure_when_audit_failures_enabled(
        self,
        mock_get_farm_db,
        mock_auth_ee,
        mock_ee,
        mock_fetch_s2,
        mock_fetch_smap,
        mock_fetch_owm,
        mock_save_adv,
    ):
        mock_get_farm_db.return_value = {
            "id": 201,
            "farmer_name": "Urban Resident",
            "mobile_number": "919876543201",
            "preferred_language": "en",
            "crop_name": "Cotton",
            "ee_coords": [[72.8, 19.0], [72.9, 19.0], [72.9, 19.1], [72.8, 19.1], [72.8, 19.0]],
            "centroid_lat": 19.05,
            "centroid_lon": 72.85,
            "farm_area": 1.0,
        }
        mock_fetch_s2.return_value = (0.12, 0.05, {"date": "2026-03-29", "cloud_cover_pct": 5.0}, None)
        mock_fetch_smap.return_value = (0.10, {"date": "2026-03-29"}, None)
        mock_fetch_owm.return_value = (0.0, None)
        mock_save_adv.return_value = {"id": 999, "stress_level": "VALIDATION_FAILED: LIKELY_URBAN"}

        with patch("pipeline.test_pipeline.validate_agricultural_location") as mock_val:
            mock_val.return_value = {
                "outcome": VALIDATION_URBAN,
                "is_suitable_for_advisory": False,
                "land_cover_class": "Built-up",
                "land_cover_code": 50,
                "reason": "Urban area detected.",
            }

            res = test_pipeline_module.run_pipeline_for_farm(
                farm_id=201,
                outbound_sender=self.mock_sender,
                auto_send_advisory=True,
                audit_validation_failures=True,
            )

            self.assertEqual(res["status"], "validation_failed")
            self.assertFalse(res["advisory_sent"])
            self.assertIsNotNone(res.get("audit_record"))
            mock_save_adv.assert_called_once()
            save_kwargs = mock_save_adv.call_args[1]
            self.assertEqual(save_kwargs["validation_status"], VALIDATION_URBAN)
            self.assertIsNone(save_kwargs["recommended_action"])


class TestEdgeCasesAndDatabaseSafeguards(unittest.TestCase):
    """
    Dedicated tests for edge cases and database safeguards identified in code review:
    1. GEE fallback & missing land-cover: High NDVI without external land-cover confirmation is NOT assumed cropland.
    2. Urban green spaces: High NDVI in urban/built-up land is correctly classified as LIKELY_URBAN and withheld.
    3. Non-cropland: Forest/tree cover and water bodies are withheld as non-cropland.
    4. Migration 005 schema compatibility in get_latest_advisory (extracts validation_status and land_cover_class).
    5. Database fallback in get_latest_advisory: Missing columns safely default to UNVALIDATED.
    6. Historical / unvalidated advisory records in save_advisory_to_database default to UNVALIDATED.
    7. format_status_advisory renders localized location warnings for audited validation failure records.
    """

    def test_validator_missing_land_cover_withholds_advisory_despite_high_ndvi(self):
        """When external land-cover is unavailable, high NDVI must NOT automatically qualify as cropland."""
        res = validate_agricultural_location(
            centroid_lat=20.5026,
            centroid_lon=77.1419,
            mean_ndvi=0.55,
            cloud_cover_pct=2.0,
            has_smap=True,
            has_weather=True,
            farm_area_acres=2.5,
        )
        self.assertEqual(res["outcome"], VALIDATION_BARREN_UNCERTAIN)
        self.assertFalse(res["is_suitable_for_advisory"])
        self.assertEqual(res["land_cover_class"], "Uncertain / Land Cover Unavailable")
        self.assertIn("reliable land-cover classification is unavailable", res["reason"].lower())

    def test_validator_urban_green_space_with_high_ndvi_identified_as_urban(self):
        """Urban green spaces (parks, golf courses) with high NDVI are strictly identified as LIKELY_URBAN."""
        res = validate_agricultural_location(
            centroid_lat=19.0760,
            centroid_lon=72.8777,
            mean_ndvi=0.68,
            land_cover_code=50,
            land_cover_class="Built-up",
            cloud_cover_pct=3.0,
            has_smap=True,
            has_weather=True,
        )
        self.assertEqual(res["outcome"], VALIDATION_URBAN)
        self.assertFalse(res["is_suitable_for_advisory"])
        self.assertEqual(res["land_cover_class"], "Built-up")
        self.assertIn("urban", res["reason"].lower())

    def test_validator_non_cropland_tree_cover_or_water_withholds_advisory(self):
        """Non-cropland land covers (forest, water) are withheld as agricultural cropland cannot be verified."""
        # Forest / Tree cover (code 10)
        res_tree = validate_agricultural_location(
            centroid_lat=20.5026,
            centroid_lon=77.1419,
            mean_ndvi=0.72,
            land_cover_code=10,
            land_cover_class="Tree cover",
            cloud_cover_pct=2.0,
        )
        self.assertEqual(res_tree["outcome"], VALIDATION_BARREN_UNCERTAIN)
        self.assertFalse(res_tree["is_suitable_for_advisory"])
        self.assertIn("Tree cover", res_tree["land_cover_class"])

        # Permanent water body (code 80)
        res_water = validate_agricultural_location(
            centroid_lat=20.5026,
            centroid_lon=77.1419,
            mean_ndvi=0.04,
            land_cover_code=80,
            land_cover_class="Permanent water bodies",
            cloud_cover_pct=1.0,
        )
        self.assertEqual(res_water["outcome"], VALIDATION_BARREN_UNCERTAIN)
        self.assertFalse(res_water["is_suitable_for_advisory"])

    @patch("whatsapp.registration_flow.get_db_connection")
    def test_get_latest_advisory_extracts_migration_005_columns(self, mock_get_conn):
        """When Migration 005 is applied, get_latest_advisory extracts validation_status and land_cover_class."""
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        mock_cur.fetchone.return_value = (
            55, 12, "2026-03-30", "2026-03-30 10:00:00", "Vegetative",
            "Severe Stress", "Irrigate immediately", 0.22, 0.11, 0.0,
            "Severe Stress", 0.0, False,
            "irrigate now", "2026-03-30", "2026-03-30",
            "SUITABLE_CROPLAND", "Cropland"
        )

        res = get_latest_advisory(farm_id=12, db_url="postgresql://mock")
        self.assertIsNotNone(res)
        self.assertEqual(res["validation_status"], "SUITABLE_CROPLAND")
        self.assertEqual(res["land_cover_class"], "Cropland")
        self.assertEqual(res["recommended_action"], "irrigate now")

    @patch("whatsapp.registration_flow.get_db_connection")
    def test_get_latest_advisory_handles_missing_migration_005_columns_fallback(self, mock_get_conn):
        """When Migration 005 columns do not exist, get_latest_advisory safely defaults validation_status to UNVALIDATED."""
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        # First query raises psycopg2.Error (missing validation_status column)
        # Second query (fallback) succeeds with Migration 003 columns
        mock_cur.execute.side_effect = [
            psycopg2.Error("column validation_status does not exist"),
            None,
        ]
        mock_cur.fetchone.return_value = (
            56, 14, "2026-03-30", "2026-03-30 10:00:00", "Flowering",
            "Mild Stress", "Schedule irrigation", 0.35, 0.18, 2.0,
            "Mild Stress", 2.0, False,
            "schedule irrigation in 24-48h", "2026-03-30", "2026-03-30"
        )

        res = get_latest_advisory(farm_id=14, db_url="postgresql://mock")
        self.assertIsNotNone(res)
        self.assertEqual(res["validation_status"], "UNVALIDATED")
        self.assertIsNone(res["land_cover_class"])
        self.assertEqual(mock_conn.rollback.call_count, 1)

    def test_format_status_advisory_renders_warning_on_audited_validation_failure(self):
        """Advisories audited with validation failures render localized location notices instead of normal crop cards."""
        farm = {"id": 10, "farmer_name": "Ramesh", "crop_name": "Cotton"}

        # 1. Urban failure in English, Marathi, and Hindi
        adv_urban = {
            "validation_status": "LIKELY_URBAN",
            "observed_stress": "VALIDATION_FAILED: LIKELY_URBAN",
            "recommendation": "Irrigation advisory withheld.",
        }
        res_en = format_status_advisory(farm, adv_urban, lang="en")
        self.assertIn("urban or built-up area", res_en)
        res_mr = format_status_advisory(farm, adv_urban, lang="mr")
        self.assertIn("शहरी किंवा इमारतींचे क्षेत्र", res_mr)
        res_hi = format_status_advisory(farm, adv_urban, lang="hi")
        self.assertIn("शहरी या निर्माण क्षेत्र", res_hi)

        # 2. Barren / fallow failure
        adv_fallow = {
            "validation_status": "BARREN_OR_UNCERTAIN",
            "observed_stress": "VALIDATION_FAILED: BARREN_OR_UNCERTAIN",
        }
        self.assertIn("uncultivated field", format_status_advisory(farm, adv_fallow, lang="en"))

        # 3. Satellite unavailable failure
        adv_cloudy = {
            "validation_status": "INSUFFICIENT_SATELLITE_DATA",
            "observed_stress": "VALIDATION_FAILED: INSUFFICIENT_SATELLITE_DATA",
        }
        self.assertIn("heavy clouds", format_status_advisory(farm, adv_cloudy, lang="en"))

    @patch("pipeline.test_pipeline.psycopg2.connect")
    def test_save_advisory_preserves_unvalidated_for_historical_records(self, mock_connect):
        """When validation_status is omitted, save_advisory_to_database persists UNVALIDATED to prevent false validation flags."""
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        mock_cur.fetchall.return_value = [("recommended_action",), ("validation_status",)]
        mock_cur.fetchone.return_value = (601, 20, "2026-03-30", "Severe Stress", "2026-03-30 10:00:00")

        test_pipeline_module.save_advisory_to_database(
            farm_id=20,
            stress_level="Severe Stress",
            recommendation="Immediate irrigation",
            validation_status=None,  # Unspecified / historical
            db_url="postgresql://mock",
        )

        insert_call = mock_cur.execute.call_args_list[1]
        _, params = insert_call[0]
        self.assertIn("UNVALIDATED", params)
        self.assertNotIn("SUITABLE_CROPLAND", params)



# ==============================================================================
# GOOGLE MAPS LOCATION PARSING & SECURE SHORTLINK REGRESSION SUITE
# ==============================================================================

class TestGoogleMapsLocationParsing(unittest.TestCase):
    """Unit tests for centralized coordinate extraction from URLs, labels, and text."""

    def test_direct_url_formats(self):
        """Validates coordinate extraction across all supported direct Google Maps URL formats."""
        url_cases = [
            ("https://www.google.com/maps?q=19.34634,74.31100", (19.34634, 74.31100)),
            ("https://maps.google.com/?q=19.34634,74.31100", (19.34634, 74.31100)),
            ("https://www.google.com/maps?q=19.34634%2C74.31100", (19.34634, 74.31100)),
            ("https://maps.google.com/?ll=19.34634,74.31100", (19.34634, 74.31100)),
            ("https://maps.google.com/?query=19.34634,74.31100", (19.34634, 74.31100)),
            ("https://www.google.com/maps/@19.34634,74.31100,15z", (19.34634, 74.31100)),
            ("https://www.google.com/maps/place/19.34634,74.31100", (19.34634, 74.31100)),
            ("https://www.google.com/maps/place/19.34634,74.31100/@19.34634,74.31100,17z", (19.34634, 74.31100)),
            ("https://www.google.com/maps/search/19.34634,74.31100", (19.34634, 74.31100)),
        ]
        for url, expected in url_cases:
            coords = parse_location_from_text(url, resolve_shortlinks=False)
            self.assertIsNotNone(coords, f"Failed to parse coordinates from: {url}")
            self.assertAlmostEqual(coords[0], expected[0], places=4)
            self.assertAlmostEqual(coords[1], expected[1], places=4)

    def test_raw_coordinate_text(self):
        """Validates coordinate extraction from raw and labeled coordinate strings."""
        coord_cases = [
            ("19.34634, 74.31100", (19.34634, 74.31100)),
            ("19.34634,74.31100", (19.34634, 74.31100)),
            ("19.34634 74.31100", (19.34634, 74.31100)),
            ("Lat: 19.34634, Lon: 74.31100", (19.34634, 74.31100)),
            ("Latitude: 19.34634, Longitude: 74.31100", (19.34634, 74.31100)),
            ("19.34634 N, 74.31100 E", (19.34634, 74.31100)),
            ("19.34634° N, 74.31100° E", (19.34634, 74.31100)),
        ]
        for text, expected in coord_cases:
            coords = parse_location_from_text(text, resolve_shortlinks=False)
            self.assertIsNotNone(coords, f"Failed to parse coordinates from: {text}")
            self.assertAlmostEqual(coords[0], expected[0], places=4)
            self.assertAlmostEqual(coords[1], expected[1], places=4)

    def test_embedded_coordinates_in_conversational_text(self):
        """Validates coordinate extraction when embedded within conversational sentences."""
        embedded_cases = [
            ("My farm is at https://www.google.com/maps?q=19.34634,74.31100 check it", (19.34634, 74.31100)),
            ("Farm coordinates: 19.34634, 74.31100 please note", (19.34634, 74.31100)),
            ("माझे शेत https://www.google.com/maps/@19.34634,74.31100,16z येथे आहे", (19.34634, 74.31100)),
        ]
        for text, expected in embedded_cases:
            coords = parse_location_from_text(text, resolve_shortlinks=False)
            self.assertIsNotNone(coords, f"Failed to extract embedded coordinates from: {text}")
            self.assertAlmostEqual(coords[0], expected[0], places=4)
            self.assertAlmostEqual(coords[1], expected[1], places=4)

    def test_conversational_text_produces_no_false_positives(self):
        """Ordinary text, acreage descriptions, and non-coordinate numbers must NOT produce coordinates."""
        non_coord_cases = [
            "I have 2.5 acres and 5 cows",
            "1",
            "2",
            "Option 1 or 2",
            "My phone number is 9876543210",
            "शेतात 3 एकर कापूस आहे आणि 2 म्हशी आहेत",
            "2.5",
            "10.5",
            "yes",
            "no",
            "namaste",
        ]
        for text in non_coord_cases:
            coords = parse_location_from_text(text, resolve_shortlinks=False)
            self.assertIsNone(coords, f"Expected None for non-coordinate text: {text!r}, got: {coords}")

    def test_missing_and_malformed_coordinates(self):
        """Malformed or coordinate-free Google Maps URLs return None."""
        invalid_cases = [
            "https://www.google.com/maps",
            "https://www.google.com/maps?q=invalid,coords",
            "https://www.google.com/maps/place/Mumbai",
            "",
            None,
        ]
        for url in invalid_cases:
            coords = parse_location_from_text(url, resolve_shortlinks=False)
            self.assertIsNone(coords, f"Expected None for invalid coordinate text: {url!r}")

    def test_mathematical_bounds_validation(self):
        """Extractors strictly enforce -90 <= lat <= 90 and -180 <= lon <= 180."""
        out_of_bounds_math = [
            "https://www.google.com/maps?q=95.12345,74.31100",   # Lat > 90
            "https://www.google.com/maps?q=-95.12345,74.31100",  # Lat < -90
            "https://www.google.com/maps?q=19.34634,195.31100",  # Lon > 180
            "https://www.google.com/maps?q=19.34634,-195.31100", # Lon < -180
            "91.0, 74.0",
            "19.0, 181.0",
        ]
        for text in out_of_bounds_math:
            coords = parse_location_from_text(text, resolve_shortlinks=False)
            self.assertIsNone(coords, f"Expected None for mathematically invalid coordinates: {text!r}")


class TestSecureShortlinkResolution(unittest.TestCase):
    """Unit tests for Anti-SSRF, DNS pinning, and secure Google Maps shortlink resolution."""

    @patch("common.utils.socket.getaddrinfo")
    @patch("common.utils.requests.Session")
    def test_valid_shortlink_redirect_single_hop(self, mock_session_cls, mock_getaddrinfo):
        """Resolves a valid maps.app.goo.gl shortlink via HTTP 302 Location header."""
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("142.250.190.46", 443))
        ]
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_resp = MagicMock()
        mock_resp.status_code = 302
        mock_resp.headers = {"Location": "https://www.google.com/maps/@19.34634,74.31100,17z"}
        mock_session.head.return_value = mock_resp

        coords = resolve_google_maps_shortlink("https://maps.app.goo.gl/AbCdEfGh")
        self.assertIsNotNone(coords)
        self.assertAlmostEqual(coords[0], 19.34634, places=4)
        self.assertAlmostEqual(coords[1], 74.31100, places=4)
        mock_session.head.assert_called_once()
        mock_resp.close.assert_called_once()

    @patch("common.utils.socket.getaddrinfo")
    @patch("common.utils.requests.Session")
    def test_valid_shortlink_redirect_multihop(self, mock_session_cls, mock_getaddrinfo):
        """Resolves a shortlink requiring multiple redirect hops within approved hosts."""
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("142.250.190.46", 443))
        ]
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        resp1 = MagicMock()
        resp1.status_code = 302
        resp1.headers = {"Location": "https://goo.gl/maps/intermediary"}

        resp2 = MagicMock()
        resp2.status_code = 302
        resp2.headers = {"Location": "https://maps.google.com/?q=19.34634,74.31100"}

        mock_session.head.side_effect = [resp1, resp2]

        coords = resolve_google_maps_shortlink("https://maps.app.goo.gl/hop1")
        self.assertIsNotNone(coords)
        self.assertAlmostEqual(coords[0], 19.34634, places=4)
        self.assertAlmostEqual(coords[1], 74.31100, places=4)

    @patch("common.utils.socket.getaddrinfo")
    @patch("common.utils.requests.Session")
    def test_shortlink_redirect_loop_blocked(self, mock_session_cls, mock_getaddrinfo):
        """Detects and terminates redirect loops without hanging."""
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("142.250.190.46", 443))
        ]
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        loop_resp = MagicMock()
        loop_resp.status_code = 302
        loop_resp.headers = {"Location": "https://maps.app.goo.gl/loop"}
        mock_session.head.return_value = loop_resp

        coords = resolve_google_maps_shortlink("https://maps.app.goo.gl/loop")
        self.assertIsNone(coords)

    @patch("common.utils.socket.getaddrinfo")
    @patch("common.utils.requests.Session")
    def test_shortlink_exceeds_max_hops_blocked(self, mock_session_cls, mock_getaddrinfo):
        """Blocks shortlinks that exceed the 3-hop redirect budget."""
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("142.250.190.46", 443))
        ]
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        def make_resp(dest):
            r = MagicMock()
            r.status_code = 302
            r.headers = {"Location": dest}
            return r

        mock_session.head.side_effect = [
            make_resp("https://maps.app.goo.gl/hop2"),
            make_resp("https://maps.app.goo.gl/hop3"),
            make_resp("https://maps.app.goo.gl/hop4"),
            make_resp("https://maps.app.goo.gl/hop5"),
        ]

        coords = resolve_google_maps_shortlink("https://maps.app.goo.gl/hop1", max_redirects=3)
        self.assertIsNone(coords)

    def test_shortlink_unapproved_initial_hosts_rejected_without_network_call(self):
        """Disallowed initial domains (e.g. bit.ly, tinyurl, malicious.com) are rejected immediately."""
        unapproved_urls = [
            "https://bit.ly/farm_location",
            "https://tinyurl.com/farm123",
            "https://evil.com/maps.app.goo.gl/test",
            "http://maps.app.goo.gl/unencrypted",
            "ftp://maps.app.goo.gl/ftp",
            "https://goo.gl/other_path_not_maps",
        ]
        for u in unapproved_urls:
            with patch("common.utils.requests.Session") as mock_session:
                coords = resolve_google_maps_shortlink(u)
                self.assertIsNone(coords)
                mock_session.assert_not_called()

    @patch("common.utils.socket.getaddrinfo")
    @patch("common.utils.requests.Session")
    def test_shortlink_redirect_to_disallowed_host_blocked(self, mock_session_cls, mock_getaddrinfo):
        """Redirects to non-whitelisted destinations are rejected immediately."""
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("142.250.190.46", 443))
        ]
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        bad_redirect_resp = MagicMock()
        bad_redirect_resp.status_code = 302
        bad_redirect_resp.headers = {"Location": "https://malicious-site.com/steal_credentials"}
        mock_session.head.return_value = bad_redirect_resp

        coords = resolve_google_maps_shortlink("https://maps.app.goo.gl/evil")
        self.assertIsNone(coords)

    @patch("common.utils.socket.getaddrinfo")
    @patch("common.utils.requests.Session")
    def test_shortlink_redirect_to_non_https_blocked(self, mock_session_cls, mock_getaddrinfo):
        """Redirects to non-HTTPS destinations (e.g. http://) are blocked."""
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("142.250.190.46", 443))
        ]
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        http_resp = MagicMock()
        http_resp.status_code = 302
        http_resp.headers = {"Location": "http://maps.google.com/?q=19.34634,74.31100"}
        mock_session.head.return_value = http_resp

        coords = resolve_google_maps_shortlink("https://maps.app.goo.gl/insecure")
        self.assertIsNone(coords)

    @patch("common.utils.socket.getaddrinfo")
    def test_shortlink_private_and_loopback_ips_blocked(self, mock_getaddrinfo):
        """Blocks SSRF attacks attempting loopback, private RFC1918, link-local, and cloud metadata."""
        prohibited_ips = [
            "127.0.0.1",       # Loopback
            "10.0.0.1",        # Private RFC1918
            "172.16.0.1",      # Private RFC1918
            "192.168.1.1",     # Private RFC1918
            "169.254.169.254", # AWS/GCP/Azure Instance Metadata
            "::1",             # IPv6 Loopback
            "fe80::1",         # IPv6 Link-Local
            "fc00::1",         # IPv6 Unique Local
        ]
        for bad_ip in prohibited_ips:
            mock_getaddrinfo.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", (bad_ip, 443))
            ]
            with patch("common.utils.requests.Session") as mock_session:
                coords = resolve_google_maps_shortlink("https://maps.app.goo.gl/ssrf_target")
                self.assertIsNone(coords, f"Expected None for prohibited IP: {bad_ip}")
                mock_session.assert_not_called()

    @patch("common.utils.socket.getaddrinfo")
    def test_shortlink_mixed_dns_fails_closed(self, mock_getaddrinfo):
        """If DNS returns a mixture of public and private addresses, fails closed immediately."""
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("142.250.190.46", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),  # Malicious poison
        ]
        with patch("common.utils.requests.Session") as mock_session:
            coords = resolve_google_maps_shortlink("https://maps.app.goo.gl/dns_poison")
            self.assertIsNone(coords)
            mock_session.assert_not_called()

    @patch("common.utils.socket.getaddrinfo")
    def test_shortlink_ipv4_mapped_ipv6_blocked(self, mock_getaddrinfo):
        """Blocks IPv4-mapped IPv6 loopback and metadata addresses (::ffff:127.0.0.1)."""
        mock_getaddrinfo.return_value = [
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::ffff:127.0.0.1", 443))
        ]
        with patch("common.utils.requests.Session") as mock_session:
            coords = resolve_google_maps_shortlink("https://maps.app.goo.gl/ipv4_mapped")
            self.assertIsNone(coords)
            mock_session.assert_not_called()

    @patch("common.utils.socket.getaddrinfo")
    @patch("common.utils.requests.Session")
    def test_shortlink_network_timeout_and_errors_handled_gracefully(self, mock_session_cls, mock_getaddrinfo):
        """Handles socket and HTTP timeouts without raising unhandled exceptions."""
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("142.250.190.46", 443))
        ]
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.head.side_effect = requests.Timeout("Connection timed out after 3.0s")

        coords = resolve_google_maps_shortlink("https://maps.app.goo.gl/timeout_link")
        self.assertIsNone(coords)

    @patch("common.utils.socket.getaddrinfo")
    @patch("common.utils.requests.Session")
    def test_redirect_to_disallowed_destination_with_coordinates_blocked(
        self, mock_session_cls, mock_getaddrinfo
    ):
        """Redirects to unapproved hosts containing coordinate-looking text are rejected without trusting coordinates."""
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("142.250.190.46", 443))
        ]
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        resp = MagicMock()
        resp.status_code = 302
        resp.headers = {"Location": "https://malicious-site.com/maps?q=19.34634,74.31100"}
        mock_session.head.return_value = resp

        coords = resolve_google_maps_shortlink("https://maps.app.goo.gl/malicious_coords")
        self.assertIsNone(coords, "Expected None for redirect to disallowed domain even if coordinates present")

    @patch("common.utils.socket.getaddrinfo")
    @patch("common.utils.requests.Session")
    def test_redirect_to_private_ip_destination_with_coordinates_blocked(
        self, mock_session_cls, mock_getaddrinfo
    ):
        """Redirects pointing to private/loopback/cloud metadata IP literals containing coordinates are blocked."""
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("142.250.190.46", 443))
        ]
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        private_dests = [
            "https://127.0.0.1/maps?q=19.34634,74.31100",
            "https://10.0.0.1/maps?q=19.34634,74.31100",
            "https://169.254.169.254/maps?q=19.34634,74.31100",
        ]
        for dest in private_dests:
            resp = MagicMock()
            resp.status_code = 302
            resp.headers = {"Location": dest}
            mock_session.head.return_value = resp

            coords = resolve_google_maps_shortlink("https://maps.app.goo.gl/private_ip")
            self.assertIsNone(coords, f"Expected None for redirect to private IP: {dest}")

    @patch("common.utils.socket.getaddrinfo")
    @patch("common.utils.requests.Session")
    def test_redirect_to_approved_host_resolving_to_private_ip_blocked(
        self, mock_session_cls, mock_getaddrinfo
    ):
        """Redirects to approved hostnames that resolve to private/loopback IPs are blocked before coordinate extraction."""
        # Initial shortlink host resolves safely, but redirect destination resolves to loopback
        def getaddrinfo_side_effect(host, port, *args, **kwargs):
            if host == "maps.app.goo.gl":
                return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("142.250.190.46", 443))]
            elif host == "maps.google.com":
                return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]
            return []

        mock_getaddrinfo.side_effect = getaddrinfo_side_effect
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        resp = MagicMock()
        resp.status_code = 302
        resp.headers = {"Location": "https://maps.google.com/?q=19.34634,74.31100"}
        mock_session.head.return_value = resp

        coords = resolve_google_maps_shortlink("https://maps.app.goo.gl/dns_poisoned_redirect")
        self.assertIsNone(coords, "Expected None when redirect destination resolves to loopback IP")

    @patch("common.utils.socket.getaddrinfo")
    @patch("common.utils.requests.Session")
    def test_redirect_with_credentials_and_coordinates_blocked(
        self, mock_session_cls, mock_getaddrinfo
    ):
        """Redirects with embedded userinfo credentials containing coordinates are blocked."""
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("142.250.190.46", 443))
        ]
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        resp = MagicMock()
        resp.status_code = 302
        resp.headers = {"Location": "https://admin:secret@maps.google.com/?q=19.34634,74.31100"}
        mock_session.head.return_value = resp

        coords = resolve_google_maps_shortlink("https://maps.app.goo.gl/creds_target")
        self.assertIsNone(coords, "Expected None for redirect with embedded credentials")

    @patch("common.utils.socket.getaddrinfo")
    @patch("common.utils.requests.Session")
    def test_redirect_with_non_standard_port_and_coordinates_blocked(
        self, mock_session_cls, mock_getaddrinfo
    ):
        """Redirects with non-standard ports containing coordinates are blocked."""
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("142.250.190.46", 443))
        ]
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        resp = MagicMock()
        resp.status_code = 302
        resp.headers = {"Location": "https://maps.google.com:8443/?q=19.34634,74.31100"}
        mock_session.head.return_value = resp

        coords = resolve_google_maps_shortlink("https://maps.app.goo.gl/port_target")
        self.assertIsNone(coords, "Expected None for redirect with non-443 port")

    @patch("common.utils.socket.getaddrinfo")
    @patch("common.utils.requests.Session")
    def test_socket_getaddrinfo_never_mutated_globally(
        self, mock_session_cls, mock_getaddrinfo
    ):
        """Verifies that socket.getaddrinfo is never globally monkeypatched during or after shortlink resolution."""
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("142.250.190.46", 443))
        ]
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        resp = MagicMock()
        resp.status_code = 302
        resp.headers = {"Location": "https://www.google.com/maps/@19.34634,74.31100,17z"}

        original_getaddrinfo = socket.getaddrinfo

        # Verify during request execution that socket.getaddrinfo remains unmutated
        def head_side_effect(*args, **kwargs):
            self.assertIs(
                socket.getaddrinfo,
                original_getaddrinfo,
                "socket.getaddrinfo was modified during request execution!",
            )
            return resp

        mock_session.head.side_effect = head_side_effect

        coords = resolve_google_maps_shortlink("https://maps.app.goo.gl/safe_link")
        self.assertIsNotNone(coords)
        self.assertAlmostEqual(coords[0], 19.34634, places=4)
        self.assertAlmostEqual(coords[1], 74.31100, places=4)

        # Verify after request execution
        self.assertIs(
            socket.getaddrinfo,
            original_getaddrinfo,
            "socket.getaddrinfo was modified after request execution!",
        )


class TestRegistrationFlowGoogleMapsIntegration(unittest.TestCase):
    """End-to-end integration tests for Google Maps links and coordinates in the registration state machine."""

    def setUp(self):
        self.db_url = "postgresql://mock_khetsense_db"
        self.mock_sender = MagicMock(return_value=True)

    @patch("whatsapp.registration_flow.get_registered_farm")
    @patch("whatsapp.registration_flow.save_session")
    @patch("whatsapp.registration_flow.get_session")
    def test_awaiting_location_with_direct_google_maps_url(
        self, mock_get_session, mock_save_session, mock_get_farm
    ):
        """In AWAITING_LOCATION, sending a direct Google Maps URL transitions to AWAITING_LOCATION_CONFIRMATION."""
        mock_get_farm.return_value = None
        mock_get_session.return_value = {
            "state": "AWAITING_LOCATION",
            "preferred_language": "en",
            "name": "Ramesh",
            "crop": "Cotton",
            "acreage_acres": 3.0,
        }

        msg = {
            "from": "919876543210",
            "id": "msg_maps_1",
            "type": "text",
            "text": {"body": "https://www.google.com/maps?q=19.34634,74.31100"},
        }

        res = handle_incoming(msg, outbound_sender=self.mock_sender, db_url=self.db_url)

        self.assertEqual(res["status"], "location_confirmation_requested")
        self.assertEqual(res["next_state"], "AWAITING_LOCATION_CONFIRMATION")
        self.assertAlmostEqual(res["lat"], 19.34634, places=4)
        self.assertAlmostEqual(res["lon"], 74.31100, places=4)

        # Verifies save_session saved pending coordinates
        mock_save_session.assert_called_with(
            "919876543210",
            "AWAITING_LOCATION_CONFIRMATION",
            preferred_language="en",
            pending_lat=19.34634,
            pending_lon=74.311,
            db_url=self.db_url,
        )

        # Verifies localized confirmation prompt was dispatched
        self.mock_sender.assert_called_once()
        sent_body = self.mock_sender.call_args[0][1]
        self.assertIn("19.34634", sent_body)
        self.assertIn("74.31100", sent_body)
        self.assertIn("Reply YES to confirm and proceed", sent_body)

    @patch("whatsapp.registration_flow.get_registered_farm")
    @patch("whatsapp.registration_flow.save_session")
    @patch("whatsapp.registration_flow.get_session")
    def test_awaiting_location_with_raw_coordinates_text(
        self, mock_get_session, mock_save_session, mock_get_farm
    ):
        """In AWAITING_LOCATION, sending raw coordinate text transitions to AWAITING_LOCATION_CONFIRMATION."""
        mock_get_farm.return_value = None
        mock_get_session.return_value = {
            "state": "AWAITING_LOCATION",
            "preferred_language": "mr",
            "name": "सुरेश",
            "crop": "Soybean",
            "acreage_acres": 2.5,
        }

        msg = {
            "from": "919876543210",
            "id": "msg_raw_coords_1",
            "type": "text",
            "text": {"body": "19.34634, 74.31100"},
        }

        res = handle_incoming(msg, outbound_sender=self.mock_sender, db_url=self.db_url)

        self.assertEqual(res["status"], "location_confirmation_requested")
        self.assertEqual(res["next_state"], "AWAITING_LOCATION_CONFIRMATION")
        self.assertAlmostEqual(res["lat"], 19.34634, places=4)
        self.assertAlmostEqual(res["lon"], 74.31100, places=4)

        # Verifies Marathi prompt
        sent_body = self.mock_sender.call_args[0][1]
        self.assertIn("अक्षांश", sent_body)
        self.assertIn("हो", sent_body)

    @patch("common.utils.resolve_google_maps_shortlink")
    @patch("whatsapp.registration_flow.get_registered_farm")
    @patch("whatsapp.registration_flow.save_session")
    @patch("whatsapp.registration_flow.get_session")
    def test_awaiting_location_with_shortlink(
        self, mock_get_session, mock_save_session, mock_get_farm, mock_resolve
    ):
        """In AWAITING_LOCATION, sending a Google Maps short link safely transitions to confirmation."""
        mock_resolve.return_value = (19.34634, 74.31100)
        mock_get_farm.return_value = None
        mock_get_session.return_value = {
            "state": "AWAITING_LOCATION",
            "preferred_language": "hi",
            "name": "विकास",
            "crop": "Cotton",
            "acreage_acres": 4.0,
        }

        msg = {
            "from": "919876543210",
            "id": "msg_shortlink_1",
            "type": "text",
            "text": {"body": "https://maps.app.goo.gl/AbCdEfGh"},
        }

        res = handle_incoming(msg, outbound_sender=self.mock_sender, db_url=self.db_url)

        self.assertEqual(res["status"], "location_confirmation_requested")
        self.assertAlmostEqual(res["lat"], 19.34634, places=4)
        self.assertAlmostEqual(res["lon"], 74.31100, places=4)

    @patch("whatsapp.registration_flow.get_registered_farm")
    @patch("whatsapp.registration_flow.get_session")
    def test_awaiting_location_out_of_bounds_url_triggers_localized_error(
        self, mock_get_session, mock_get_farm
    ):
        """Coordinates outside India receive location_out_of_bounds and remain in AWAITING_LOCATION."""
        mock_get_farm.return_value = None
        mock_get_session.return_value = {
            "state": "AWAITING_LOCATION",
            "preferred_language": "en",
        }

        msg = {
            "from": "919876543210",
            "id": "msg_out_of_bounds_1",
            "type": "text",
            "text": {"body": "https://www.google.com/maps?q=40.7128,-74.0060"},  # New York coordinates
        }

        res = handle_incoming(msg, outbound_sender=self.mock_sender, db_url=self.db_url)

        self.assertEqual(res["status"], "location_out_of_bounds")
        self.assertEqual(res["state"], "AWAITING_LOCATION")
        sent_body = self.mock_sender.call_args[0][1]
        self.assertIn("outside India", sent_body)

    @patch("whatsapp.registration_flow.get_registered_farm")
    @patch("whatsapp.registration_flow.get_session")
    def test_awaiting_location_invalid_text_triggers_location_invalid(
        self, mock_get_session, mock_get_farm
    ):
        """Conversational non-coordinate text in AWAITING_LOCATION triggers location_invalid."""
        mock_get_farm.return_value = None
        mock_get_session.return_value = {
            "state": "AWAITING_LOCATION",
            "preferred_language": "en",
        }

        msg = {
            "from": "919876543210",
            "id": "msg_invalid_text_1",
            "type": "text",
            "text": {"body": "I have 2.5 acres and 5 cows"},
        }

        res = handle_incoming(msg, outbound_sender=self.mock_sender, db_url=self.db_url)

        self.assertEqual(res["status"], "location_required")
        self.assertEqual(res["state"], "AWAITING_LOCATION")
        sent_body = self.mock_sender.call_args[0][1]
        self.assertIn("WhatsApp Location pin", sent_body)

    @patch("whatsapp.registration_flow.get_registered_farm")
    @patch("whatsapp.registration_flow.save_session")
    @patch("whatsapp.registration_flow.get_session")
    def test_awaiting_location_native_pin_preserved(
        self, mock_get_session, mock_save_session, mock_get_farm
    ):
        """Native WhatsApp location pins continue to be parsed and transition cleanly."""
        mock_get_farm.return_value = None
        mock_get_session.return_value = {
            "state": "AWAITING_LOCATION",
            "preferred_language": "en",
        }

        msg = {
            "from": "919876543210",
            "id": "msg_native_pin_1",
            "type": "location",
            "location": {"latitude": 19.34634, "longitude": 74.31100},
        }

        res = handle_incoming(msg, outbound_sender=self.mock_sender, db_url=self.db_url)

        self.assertEqual(res["status"], "location_confirmation_requested")
        self.assertEqual(res["next_state"], "AWAITING_LOCATION_CONFIRMATION")
        self.assertAlmostEqual(res["lat"], 19.34634, places=4)
        self.assertAlmostEqual(res["lon"], 74.31100, places=4)

    @patch("whatsapp.registration_flow.get_registered_farm")
    @patch("whatsapp.registration_flow.save_session")
    @patch("whatsapp.registration_flow.get_session")
    def test_awaiting_location_choice_with_google_maps_url(
        self, mock_get_session, mock_save_session, mock_get_farm
    ):
        """In AWAITING_LOCATION_CHOICE, pasting a Google Maps URL transitions directly to confirmation."""
        mock_get_farm.return_value = None
        mock_get_session.return_value = {
            "state": "AWAITING_LOCATION_CHOICE",
            "preferred_language": "en",
            "acreage_acres": 2.5,
        }

        msg = {
            "from": "919876543210",
            "id": "msg_choice_url_1",
            "type": "text",
            "text": {"body": "https://www.google.com/maps?q=19.34634,74.31100"},
        }

        res = handle_incoming(msg, outbound_sender=self.mock_sender, db_url=self.db_url)

        self.assertEqual(res["status"], "location_confirmation_requested")
        self.assertEqual(res["next_state"], "AWAITING_LOCATION_CONFIRMATION")
        self.assertAlmostEqual(res["lat"], 19.34634, places=4)
        self.assertAlmostEqual(res["lon"], 74.31100, places=4)

    @patch("whatsapp.registration_flow.get_registered_farm")
    @patch("whatsapp.registration_flow.save_session")
    @patch("whatsapp.registration_flow.get_session")
    def test_awaiting_location_confirmation_replacement_with_new_url(
        self, mock_get_session, mock_save_session, mock_get_farm
    ):
        """In AWAITING_LOCATION_CONFIRMATION, sending a new Google Maps URL updates the candidate coordinates."""
        mock_get_farm.return_value = None
        mock_get_session.return_value = {
            "state": "AWAITING_LOCATION_CONFIRMATION",
            "preferred_language": "en",
            "pending_lat": 19.00000,
            "pending_lon": 74.00000,
        }

        msg = {
            "from": "919876543210",
            "id": "msg_replacement_url_1",
            "type": "text",
            "text": {"body": "https://www.google.com/maps?q=19.55555,74.66666"},
        }

        res = handle_incoming(msg, outbound_sender=self.mock_sender, db_url=self.db_url)

        self.assertEqual(res["status"], "location_candidate_updated")
        self.assertEqual(res["next_state"], "AWAITING_LOCATION_CONFIRMATION")
        self.assertAlmostEqual(res["lat"], 19.55555, places=4)
        self.assertAlmostEqual(res["lon"], 74.66666, places=4)

        # Verifies updated candidate saved to session
        mock_save_session.assert_called_with(
            "919876543210",
            "AWAITING_LOCATION_CONFIRMATION",
            preferred_language="en",
            pending_lat=19.55555,
            pending_lon=74.66666,
            db_url=self.db_url,
        )

    @patch("whatsapp.registration_flow.get_registered_farm")
    @patch("whatsapp.registration_flow.get_session")
    def test_awaiting_location_confirmation_arbitrary_url_not_treated_as_yes(
        self, mock_get_session, mock_get_farm
    ):
        """In AWAITING_LOCATION_CONFIRMATION, non-coordinate URLs or arbitrary text do NOT confirm registration."""
        mock_get_farm.return_value = None
        mock_get_session.return_value = {
            "state": "AWAITING_LOCATION_CONFIRMATION",
            "preferred_language": "en",
            "pending_lat": 19.34634,
            "pending_lon": 74.31100,
        }

        msg = {
            "from": "919876543210",
            "id": "msg_arbitrary_url_1",
            "type": "text",
            "text": {"body": "https://example.com/arbitrary/page"},
        }

        res = handle_incoming(msg, outbound_sender=self.mock_sender, db_url=self.db_url)

        self.assertEqual(res["status"], "location_confirmation_required")
        self.assertEqual(res["state"], "AWAITING_LOCATION_CONFIRMATION")
        sent_body = self.mock_sender.call_args[0][1]
        self.assertIn("Reply YES to confirm and proceed", sent_body)

    @patch("whatsapp.registration_flow.trigger_pipeline_for_farm")
    @patch("whatsapp.registration_flow.register_farmer_from_pin")
    @patch("whatsapp.registration_flow.save_session")
    @patch("whatsapp.registration_flow.get_registered_farm")
    @patch("whatsapp.registration_flow.get_session")
    def test_awaiting_location_confirmation_affirmative_completes_registration(
        self, mock_get_session, mock_get_farm, mock_save_session, mock_reg_pin, mock_pipeline
    ):
        """Replying YES after URL location extraction registers farm and triggers pipeline."""
        mock_get_farm.return_value = None
        mock_get_session.return_value = {
            "state": "AWAITING_LOCATION_CONFIRMATION",
            "preferred_language": "en",
            "name": "Anil",
            "crop": "Cotton",
            "acreage_acres": 3.0,
            "pending_lat": 19.34634,
            "pending_lon": 74.31100,
        }
        mock_reg_pin.return_value = {"farm_id": 42, "farm_area": 3.0}

        msg = {
            "from": "919876543210",
            "id": "msg_confirm_yes_1",
            "type": "text",
            "text": {"body": "YES"},
        }

        res = handle_incoming(msg, outbound_sender=self.mock_sender, db_url=self.db_url)

        self.assertEqual(res["status"], "registration_complete")
        self.assertEqual(res["farm_id"], 42)
        mock_reg_pin.assert_called_once()
        self.assertAlmostEqual(mock_reg_pin.call_args[1]["lat"], 19.34634, places=4)
        self.assertAlmostEqual(mock_reg_pin.call_args[1]["lon"], 74.31100, places=4)


if __name__ == "__main__":
    unittest.main()

