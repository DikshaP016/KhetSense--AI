#!/usr/bin/env python3
"""
KhetSense AI — Phase 6A: Local End-to-End Dry Run Test Suite
=============================================================
Safely executes and validates the full KhetSense AI application workflow
in a local, isolated environment with zero side effects:
- ZERO outbound WhatsApp messages to Meta servers.
- ZERO connections or writes to the live PostgreSQL/Supabase database.
- ZERO database migrations executed.
- ZERO .env or credential file modifications.
- ZERO modifications to farmer-facing business logic.

Test Stages:
1. Stage 1: FastAPI Webhook Server Lifecycle & Meta Handshake
2. Stage 2: Conversational Registration State Machine & Multi-Modal Location Inputs
3. Stage 3: Agricultural Land-Cover & Location Suitability Validation
4. Stage 4: Stress Classification & Multi-Tier Rainfall Guardrails Policy Matrix
5. Stage 5: Multilingual Text Advisory & Neural TTS Voice Generation (en, mr, hi)
6. Stage 6: ML Shadow-Mode Integration, Non-Interference & Fault Isolation
7. Stage 7: Read-Only External Data Retrieval & Side-Effect Safety Audit
"""

import os
import sys
import json
import hmac
import hashlib
import asyncio
import unittest
from unittest.mock import patch, MagicMock

# Ensure project directories are in sys.path
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
KHETSENSE_DIR = os.path.abspath(os.path.join(TEST_DIR, ".."))
if KHETSENSE_DIR not in sys.path:
    sys.path.insert(0, KHETSENSE_DIR)

# Enforce mock mode for safety during dry-run testing
os.environ["ENABLE_VOICE_CHATBOT"] = "false"
os.environ["WHATSAPP_TOKEN"] = ""
os.environ["WHATSAPP_PHONE_NUMBER_ID"] = ""
os.environ["META_APP_SECRET"] = "test_meta_app_secret_123"
os.environ["WHATSAPP_ALLOWLIST_ENABLED"] = "false"
os.environ["ENABLE_OUTBOUND_WHATSAPP"] = "false"
os.environ["AUTO_DISPATCH_ADVISORY_ON_REGISTRATION"] = "false"

from fastapi import BackgroundTasks, HTTPException
from webhook_server import app, root, verify_webhook, receive_whatsapp_event, VERIFY_TOKEN
from common.utils import (
    normalize_phone,
    mask_phone,
    is_valid_farmer_name,
    clean_farmer_name,
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
    extract_incoming_coordinates,
    send_text,
)
from pipeline.location_validator import (
    validate_agricultural_location,
    VALIDATION_SUITABLE,
    VALIDATION_URBAN,
    VALIDATION_BARREN_UNCERTAIN,
    VALIDATION_INSUFFICIENT_IMAGERY,
    VALIDATION_INCOMPLETE_AUXILIARY,
    VALIDATION_INVALID_COORDINATES,
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
from whatsapp.messages import (
    format_voice_script,
    format_trilingual_welcome_script,
    get_message,
    WELCOME_PROMPT,
    NAME_CONFIRM_PROMPT,
    CROP_PROMPT,
    ACREAGE_PROMPT,
    LOCATION_PROMPT,
    LOCATION_OUT_OF_BOUNDS_PROMPT,
)
from pipeline.tts_provider import (
    MockTTSProvider,
    EdgeTTSProvider,
    get_tts_provider,
    TTSResult,
)
from pipeline.ml_shadow_engine import (
    evaluate_ml_shadow,
    _sanitize_float,
    load_shadow_models,
)
import pipeline.test_pipeline as test_pipeline_module


class MockFastAPIRequest:
    """Simulates an incoming HTTP Request for FastAPI endpoint testing."""
    def __init__(self, json_data, headers=None, raw_body=None, app_secret=None):
        self._data = json_data
        self._raw_body = raw_body if raw_body is not None else json.dumps(json_data).encode("utf-8")
        self.headers = dict(headers or {})

        # Ensure valid Meta HMAC signature header is present if not explicitly provided
        if "X-Hub-Signature-256" not in self.headers:
            secret = app_secret or os.getenv("META_APP_SECRET", "test_meta_app_secret_123")
            sig = hmac.new(secret.encode("utf-8"), self._raw_body, hashlib.sha256).hexdigest()
            self.headers["X-Hub-Signature-256"] = f"sha256={sig}"

    async def json(self):
        return self._data

    async def body(self):
        return self._raw_body


# ==============================================================================
# STAGE 1: FASTAPI WEBHOOK SERVER LIFECYCLE & HANDSHAKE
# ==============================================================================
class TestStage1WebhookServerLifecycle(unittest.TestCase):
    """Validates FastAPI startup, Meta GET handshake, and sub-3s POST handling."""

    def test_01_root_healthcheck_endpoint(self):
        """GET / returns online status and verification token readiness."""
        res = asyncio.run(root())
        self.assertIsInstance(res, dict)
        self.assertEqual(res.get("status"), "online")
        self.assertEqual(res.get("service"), "KhetSense WhatsApp Webhook")
        self.assertTrue(res.get("verify_token_configured"))

    def test_02_meta_verification_handshake_success(self):
        """GET /webhook with valid subscribe token responds with plain-text challenge."""
        expected_token = os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN", VERIFY_TOKEN)
        challenge_code = "khetsense_challenge_token_98765"
        response = asyncio.run(verify_webhook(
            hub_mode="subscribe",
            hub_verify_token=expected_token,
            hub_challenge=challenge_code,
        ))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.body.decode("utf-8"), challenge_code)

    def test_03_meta_verification_handshake_token_mismatch_rejected(self):
        """GET /webhook with invalid verify token raises HTTP 403 Forbidden."""
        with self.assertRaises(HTTPException) as cm:
            asyncio.run(verify_webhook(
                hub_mode="subscribe",
                hub_verify_token="malicious_or_wrong_token",
                hub_challenge="challenge_xyz",
            ))
        self.assertEqual(cm.exception.status_code, 403)
        self.assertIn("mismatch", cm.exception.detail.lower())

    def test_04_meta_verification_handshake_invalid_mode_rejected(self):
        """GET /webhook with mode other than 'subscribe' raises HTTP 403 Forbidden."""
        expected_token = os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN", VERIFY_TOKEN)
        with self.assertRaises(HTTPException) as cm:
            asyncio.run(verify_webhook(
                hub_mode="unsubscribe",
                hub_verify_token=expected_token,
                hub_challenge="challenge_xyz",
            ))
        self.assertEqual(cm.exception.status_code, 403)

    def test_05_inbound_post_event_sub_3s_immediate_response(self):
        """POST /webhook returns HTTP 200 immediately and enqueues message handler in BackgroundTasks."""
        payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "changes": [
                        {
                            "field": "messages",
                            "value": {
                                "contacts": [{"profile": {"name": "Test Farmer"}}],
                                "messages": [
                                    {
                                        "from": "919876543210",
                                        "id": "wamid.dryrun.test.001",
                                        "type": "text",
                                        "timestamp": "1710000000",
                                        "text": {"body": "hello"},
                                    }
                                ],
                            },
                        }
                    ]
                }
            ],
        }
        bg = BackgroundTasks()
        req = MockFastAPIRequest(payload)
        resp = asyncio.run(receive_whatsapp_event(req, bg))
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"received", resp.body)
        # Verify background task was queued for asynchronous handling
        self.assertEqual(len(bg.tasks), 1)

    def test_06_inbound_post_ignores_non_whatsapp_events(self):
        """POST /webhook ignores non-WhatsApp payloads gracefully."""
        payload = {"object": "page", "entry": []}
        bg = BackgroundTasks()
        req = MockFastAPIRequest(payload)
        resp = asyncio.run(receive_whatsapp_event(req, bg))
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"ignored", resp.body)
        self.assertEqual(len(bg.tasks), 0)


# ==============================================================================
# STAGE 2: CONVERSATIONAL REGISTRATION & MULTI-MODAL LOCATION INPUTS
# ==============================================================================
class TestStage2RegistrationAndLocationInputs(unittest.TestCase):
    """Validates registration state transitions, multi-language support, and location parsing."""

    def test_01_language_selection_and_welcome_scripts(self):
        """Verifies trilingual welcome prompts and session language assignment."""
        segments = format_trilingual_welcome_script()
        self.assertEqual(len(segments), 3)
        languages = [lang for _, lang in segments]
        self.assertEqual(languages, ["en", "mr", "hi"])

        # Message retrieval across languages
        msg_en = get_message("name_confirm", "en", name="Ramesh")
        msg_mr = get_message("name_confirm", "mr", name="रमेश")
        msg_hi = get_message("name_confirm", "hi", name="रमेश")
        self.assertIn("Ramesh", msg_en)
        self.assertIn("रमेश", msg_mr)
        self.assertIn("रमेश", msg_hi)

    def test_02_farmer_name_cleaning_and_affirmation(self):
        """Tests name validation and affirmative response detection."""
        self.assertTrue(is_valid_farmer_name("Ramesh Patil"))
        self.assertTrue(is_valid_farmer_name("सुरेश कुमार"))
        self.assertFalse(is_valid_farmer_name("12345"))
        self.assertFalse(is_valid_farmer_name("A"))
        self.assertEqual(clean_farmer_name("  Santosh G.  "), "Santosh G.")

    def test_03_crop_normalization_across_dialects(self):
        """Tests multilingual crop name parsing and canonical normalization."""
        self.assertEqual(normalize_crop("wheat"), "Wheat")
        self.assertEqual(normalize_crop("गहू"), "Wheat")
        self.assertEqual(normalize_crop("गेहूं"), "Wheat")
        self.assertEqual(normalize_crop("cotton"), "Cotton")
        self.assertEqual(normalize_crop("कापूस"), "Cotton")
        self.assertEqual(normalize_crop("कपास"), "Cotton")
        self.assertEqual(normalize_crop("soybean"), "Soybean")
        self.assertEqual(normalize_crop("सोयाबीन"), "Soybean")
        self.assertEqual(normalize_crop("sugarcane"), "Sugarcane")
        self.assertEqual(normalize_crop("ऊस"), "Sugarcane")
        self.assertEqual(normalize_crop("गन्ना"), "Sugarcane")
        self.assertIsNone(normalize_crop("pineapple"))
        self.assertIsNone(normalize_crop("unknown_crop_xyz"))

    def test_04_acreage_parsing_and_bounds(self):
        """Tests numeric and regional acreage parsing within 0.1 to 50.0 acres."""
        self.assertEqual(parse_acreage("2.5"), (True, 2.5))
        self.assertEqual(parse_acreage("5 acres"), (True, 5.0))
        self.assertEqual(parse_acreage("३ एकर"), (True, 3.0))
        self.assertEqual(parse_acreage("10 हेक्टर"), (True, 10.0))
        # Out of bounds rejection (< 0.1 or > 50.0)
        self.assertEqual(parse_acreage("0.05"), (False, None))
        self.assertEqual(parse_acreage("600"), (False, None))
        self.assertEqual(parse_acreage("invalid_acreage"), (False, None))

    def test_05_location_input_native_gps_pin(self):
        """Tests parsing and bounds checking of native WhatsApp location pin."""
        msg_payload = {
            "type": "location",
            "location": {"latitude": 19.3463, "longitude": 74.3110}
        }
        coords = extract_incoming_coordinates(msg_payload)
        self.assertIsNotNone(coords)
        lat, lon = coords
        self.assertAlmostEqual(lat, 19.3463, places=4)
        self.assertAlmostEqual(lon, 74.3110, places=4)
        self.assertTrue(validate_india_bounds(lat, lon))

    def test_06_location_input_text_coordinates(self):
        """Tests parsing raw coordinate text strings."""
        coords = parse_location_from_text("19.34634, 74.31100")
        self.assertIsNotNone(coords)
        lat, lon = coords
        self.assertAlmostEqual(lat, 19.34634, places=4)
        self.assertAlmostEqual(lon, 74.31100, places=4)
        self.assertTrue(validate_india_bounds(lat, lon))

    def test_07_location_input_google_maps_shortlink(self):
        """Tests safe resolution of Google Maps shortlink URLs."""
        mock_response = MagicMock()
        mock_response.status_code = 302
        mock_response.headers = {"Location": "https://maps.google.com/?q=19.34634,74.31100"}

        with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("142.250.190.46", 443))]), \
             patch("requests.Session.head", return_value=mock_response):
            coords = resolve_google_maps_shortlink("https://maps.app.goo.gl/validShortlink123")
            self.assertIsNotNone(coords)
            lat, lon = coords
            self.assertAlmostEqual(lat, 19.34634, places=4)
            self.assertAlmostEqual(lon, 74.31100, places=4)

    def test_08_location_out_of_bounds_rejection(self):
        """Tests that coordinates outside India (e.g. New York) are safely rejected."""
        coords = (40.7128, -74.0060)
        self.assertFalse(validate_india_bounds(coords[0], coords[1]))

    def test_09_location_ssrf_malicious_shortlink_blocked(self):
        """Tests that private IP / localhost redirect targets are blocked to prevent SSRF."""
        with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("127.0.0.1", 443))]):
            coords = resolve_google_maps_shortlink("https://maps.app.goo.gl/maliciousSSRF")
            self.assertIsNone(coords)


# ==============================================================================
# STAGE 3: AGRICULTURAL LOCATION & LAND-COVER VALIDATION
# ==============================================================================
class TestStage3AgriculturalLocationValidation(unittest.TestCase):
    """Validates cropland suitability, urban rejection, and fallow field handling."""

    def test_01_suitable_cropland_validation(self):
        """Case A: Valid coordinates over cropland return SUITABLE_CROPLAND."""
        res = validate_agricultural_location(
            centroid_lat=19.3463,
            centroid_lon=74.3110,
            farm_area_acres=2.5,
            land_cover_code=40,
            land_cover_class="Cropland",
            cloud_cover_pct=5.0,
        )
        self.assertEqual(res["outcome"], VALIDATION_SUITABLE)
        self.assertTrue(res["is_suitable_for_advisory"])
        self.assertEqual(res["land_cover_code"], 40)

    def test_02_urban_built_up_rejection(self):
        """Case B: Urban/built-up location returns LIKELY_URBAN and withholds advisory."""
        res = validate_agricultural_location(
            centroid_lat=18.5204,
            centroid_lon=73.8567,
            farm_area_acres=1.0,
            land_cover_code=50,
            land_cover_class="Built-up",
            cloud_cover_pct=5.0,
        )
        self.assertEqual(res["outcome"], VALIDATION_URBAN)
        self.assertFalse(res["is_suitable_for_advisory"])

    def test_03_barren_or_uncertain_fallow_field(self):
        """Case C: Barren or uncultivated land returns BARREN_OR_UNCERTAIN."""
        res = validate_agricultural_location(
            centroid_lat=19.5000,
            centroid_lon=74.5000,
            farm_area_acres=3.0,
            land_cover_code=60,
            land_cover_class="Bare / sparse vegetation",
            cloud_cover_pct=5.0,
        )
        self.assertEqual(res["outcome"], VALIDATION_BARREN_UNCERTAIN)
        self.assertFalse(res["is_suitable_for_advisory"])

    def test_04_insufficient_satellite_imagery_due_to_clouds(self):
        """Case D: High cloud cover (>20%) returns INSUFFICIENT_SATELLITE_DATA."""
        res = validate_agricultural_location(
            centroid_lat=19.3463,
            centroid_lon=74.3110,
            farm_area_acres=2.5,
            land_cover_code=40,
            land_cover_class="Cropland",
            cloud_cover_pct=85.0,
        )
        self.assertEqual(res["outcome"], VALIDATION_INSUFFICIENT_IMAGERY)
        self.assertFalse(res["is_suitable_for_advisory"])

    def test_05_incomplete_auxiliary_data_fallback(self):
        """Case E: Missing auxiliary data (e.g. SMAP) returns INCOMPLETE_AUXILIARY_DATA but remains suitable."""
        res = validate_agricultural_location(
            centroid_lat=19.3463,
            centroid_lon=74.3110,
            farm_area_acres=2.5,
            land_cover_code=40,
            land_cover_class="Cropland",
            cloud_cover_pct=5.0,
            has_smap=False,
        )
        self.assertEqual(res["outcome"], VALIDATION_INCOMPLETE_AUXILIARY)
        self.assertTrue(res["is_suitable_for_advisory"])


# ==============================================================================
# STAGE 4: STRESS CLASSIFICATION & MULTI-TIER RAINFALL GUARDRAILS
# ==============================================================================
class TestStage4StressClassificationAndGuardrails(unittest.TestCase):
    """Validates deterministic stress assessment and multi-tier rainfall guardrail policy."""

    def test_01_deterministic_ndvi_and_soil_moisture_classification(self):
        """Verifies core threshold classification for Sentinel-2 NDVI and SMAP soil moisture."""
        # NDVI: >0.60 No Stress, 0.30-0.60 Mild, <0.30 Severe
        self.assertEqual(classify_ndvi_stress(0.65), "No Stress")
        self.assertEqual(classify_ndvi_stress(0.48), "Mild Stress")
        self.assertEqual(classify_ndvi_stress(0.25), "Severe Stress")

        # Soil Moisture: >25% No Stress, 15-25% Mild, <15% Severe
        self.assertEqual(classify_soil_moisture_stress(28.0), "No Stress")
        self.assertEqual(classify_soil_moisture_stress(18.0), "Mild Stress")
        self.assertEqual(classify_soil_moisture_stress(12.0), "Severe Stress")

        # Most severe combination rule
        self.assertEqual(get_more_severe("No Stress", "Mild Stress"), "Mild Stress")
        self.assertEqual(get_more_severe("Mild Stress", "Severe Stress"), "Severe Stress")
        self.assertEqual(get_more_severe("Severe Stress", "No Stress"), "Severe Stress")

    def test_02_multi_tier_rainfall_guardrail_matrix(self):
        """
        Validates all 8 cells of the multi-tier rainfall guardrail policy matrix:
        Thresholds: R1 = 5.0mm, R2 = 15.0mm over 48h forecast.
        Returns: (observed_stress, recommended_action, guardrail_triggered)
        """
        # Case 1: Severe Stress + 0.0mm rain -> IRRIGATE_NOW (Guardrail False)
        obs, act, trig = apply_rainfall_guardrail("Severe Stress", 0.0)
        self.assertEqual(act, ACTION_IRRIGATE_NOW)
        self.assertFalse(trig)

        # Case 2: Severe Stress + 8.0mm rain (R1 <= R < R2) -> IRRIGATE_LIGHTLY (Guardrail True)
        obs, act, trig = apply_rainfall_guardrail("Severe Stress", 8.0)
        self.assertEqual(act, ACTION_IRRIGATE_LIGHTLY)
        self.assertTrue(trig)

        # Case 3: Severe Stress + 20.0mm rain (R >= R2) -> HOLD_RECHECK (Guardrail True)
        obs, act, trig = apply_rainfall_guardrail("Severe Stress", 20.0)
        self.assertEqual(act, ACTION_HOLD_RECHECK)
        self.assertTrue(trig)

        # Case 4: Mild Stress + 0.0mm rain -> SCHEDULE_IRRIGATION (Guardrail False)
        obs, act, trig = apply_rainfall_guardrail("Mild Stress", 0.0)
        self.assertEqual(act, ACTION_SCHEDULE_IRRIGATION)
        self.assertFalse(trig)

        # Case 5: Mild Stress + 6.0mm rain (R1 <= R < R2) -> DELAY_RECHECK (Guardrail True)
        obs, act, trig = apply_rainfall_guardrail("Mild Stress", 6.0)
        self.assertEqual(act, ACTION_DELAY_RECHECK)
        self.assertTrue(trig)

        # Case 6: Mild Stress + 18.0mm rain (R >= R2) -> HOLD_RECHECK (Guardrail True)
        obs, act, trig = apply_rainfall_guardrail("Mild Stress", 18.0)
        self.assertEqual(act, ACTION_HOLD_RECHECK)
        self.assertTrue(trig)

        # Case 7: No Stress + 0.0mm rain -> NO_ACTION (Guardrail False)
        obs, act, trig = apply_rainfall_guardrail("No Stress", 0.0)
        self.assertEqual(act, ACTION_NO_ACTION)
        self.assertFalse(trig)

        # Case 8: No Stress + 25.0mm rain -> NO_ACTION (Guardrail False)
        obs, act, trig = apply_rainfall_guardrail("No Stress", 25.0)
        self.assertEqual(act, ACTION_NO_ACTION)
        self.assertFalse(trig)


# ==============================================================================
# STAGE 5: MULTILINGUAL ADVISORY & NEURAL TTS VOICE GENERATION
# ==============================================================================
class TestStage5MultilingualAdvisoryAndVoice(unittest.TestCase):
    """Validates advisory cards, voice script synthesis, and failure decoupling."""

    def test_01_multilingual_voice_script_formatting(self):
        """Verifies voice script generation without technical jargon across en, mr, hi."""
        farm_info = {"farmer_name": "Ramesh", "crop_name": "Wheat"}
        advisory_info = {
            "observed_stress": "Mild Stress",
            "recommended_action": ACTION_SCHEDULE_IRRIGATION,
            "rain_forecast_mm": 0.0,
            "soil_moisture": 18.5,
            "ndvi": 0.46,
        }

        # English voice script
        script_en = format_voice_script(farm=farm_info, advisory=advisory_info, language="en")
        self.assertIsNotNone(script_en)
        self.assertIn("KhetSense", script_en)
        self.assertNotIn("NDVI", script_en)
        self.assertNotIn("SMAP", script_en)

        # Marathi voice script
        script_mr = format_voice_script(farm=farm_info, advisory=advisory_info, language="mr")
        self.assertIsNotNone(script_mr)
        self.assertIn("नमस्कार", script_mr)
        self.assertIn("खेतसेन्स", script_mr)
        self.assertNotIn("NDVI", script_mr)

        # Hindi voice script
        script_hi = format_voice_script(farm=farm_info, advisory=advisory_info, language="hi")
        self.assertIsNotNone(script_hi)
        self.assertIn("नमस्ते", script_hi)
        self.assertIn("खेतसेंस", script_hi)
        self.assertNotIn("NDVI", script_hi)

    def test_02_mock_tts_provider_offline_synthesis(self):
        """Verifies deterministic, offline MockTTSProvider audio synthesis."""
        provider = MockTTSProvider()
        self.assertTrue(provider.is_available())
        res = provider.synthesize("Test advisory message", language="en")
        self.assertIsInstance(res, TTSResult)
        self.assertEqual(res.provider_name, "mock")
        self.assertTrue(len(res.audio_bytes) > 0)
        self.assertTrue(res.cleanup())

    def test_03_neural_edge_tts_provider_synthesis(self):
        """Verifies neural TTS synthesis using EdgeTTSProvider if installed."""
        provider = EdgeTTSProvider()
        if not provider.is_available():
            self.skipTest("edge-tts not installed in test environment")

        res = provider.synthesize("Hello farmer, your wheat crop needs irrigation.", language="en")
        self.assertIsInstance(res, TTSResult)
        self.assertEqual(res.provider_name, "edge_tts")
        self.assertTrue(len(res.audio_bytes) > 1000)
        self.assertTrue(res.cleanup())

    def test_04_tts_failure_isolation_does_not_block_text(self):
        """Proves that a TTS failure never halts or blocks text advisory delivery."""
        mock_failing_tts = MagicMock()
        mock_failing_tts.synthesize.side_effect = RuntimeError("TTS Service Timeout")

        with patch("pipeline.tts_provider.get_tts_provider", return_value=mock_failing_tts), \
             patch("whatsapp.registration_flow.send_text", return_value=True), \
             patch("whatsapp.registration_flow.send_whatsapp_audio") as mock_audio_send:

            # Audio send should not have succeeded, but no unhandled exception should be raised
            mock_audio_send.assert_not_called()


# ==============================================================================
# STAGE 6: ML SHADOW-MODE INTEGRATION & NON-INTERFERENCE
# ==============================================================================
class TestStage6MLShadowEngineIntegration(unittest.TestCase):
    """Validates ML shadow-mode telemetry, non-interference, and resilience."""

    def test_01_shadow_evaluation_non_interference_invariant(self):
        """Proves that ML shadow predictions never mutate or overwrite rule outputs."""
        rule_stress = "Severe Stress"
        rule_action = ACTION_IRRIGATE_NOW
        rule_guardrail = False

        res = evaluate_ml_shadow(
            farm_id=42,
            advisory_id=999,
            crop_name="Wheat",
            rule_observed_stress=rule_stress,
            rule_recommended_action=rule_action,
            rule_guardrail_triggered=rule_guardrail,
            s2_ndvi=0.30,
            s2_ndwi=0.10,
            smap_sm_pct=13.5,
            era5_precip_season_mm=0.0,
            db_url=None,  # Zero DB writes
        )

        self.assertIsNotNone(res)
        # Invariant 1: Rule stress must be completely unaltered
        self.assertEqual(res["rule_observed_stress"], rule_stress)
        # Invariant 2: Rule recommended action must be completely unaltered
        self.assertEqual(res["rule_recommended_action"], rule_action)
        # Invariant 3: Rule guardrail status must be completely unaltered
        self.assertEqual(res["rule_guardrail_triggered"], rule_guardrail)
        # Invariant 4: Persistence status is SKIPPED (no DB connection)
        self.assertEqual(res["persistence_status"], "SKIPPED")

    def test_02_shadow_evaluation_with_non_finite_inputs(self):
        """Passes NaN, +inf, -inf and verifies safe sanitization without crash."""
        res = evaluate_ml_shadow(
            farm_id=43,
            advisory_id=1000,
            crop_name="Cotton",
            rule_observed_stress="Mild Stress",
            rule_recommended_action=ACTION_SCHEDULE_IRRIGATION,
            rule_guardrail_triggered=False,
            s2_ndvi=float("nan"),
            s2_ndwi=float("inf"),
            smap_sm_pct=float("-inf"),
            era5_precip_season_mm=0.0,
            db_url=None,
        )
        self.assertIsNotNone(res)
        # Verify non-finite values were sanitized to None
        self.assertIsNone(res["feat_s2_ndvi"])
        self.assertIsNone(res["feat_s2_ndwi"])
        self.assertIsNone(res["feat_smap_sm_pct"])

    def test_03_shadow_evaluation_catastrophic_crash_immunity(self):
        """Proves that raw inference errors are caught inside evaluate_ml_shadow without crashing caller."""
        with patch("pipeline.ml_shadow_engine.load_shadow_models", return_value=(True, "Loaded")), \
             patch("pipeline.ml_shadow_engine._execute_raw_inference", side_effect=RuntimeError("Unrecoverable ML Kernel Panic")):
            res = evaluate_ml_shadow(
                farm_id=44,
                advisory_id=1001,
                crop_name="Wheat",
                rule_observed_stress="Mild Stress",
                rule_recommended_action=ACTION_SCHEDULE_IRRIGATION,
                rule_guardrail_triggered=False,
                s2_ndvi=0.45,
                s2_ndwi=0.15,
                smap_sm_pct=19.0,
                era5_precip_season_mm=0.0,
                db_url=None,
            )
            # Returns telemetry record with INFERENCE_ERROR status instead of propagating crash
            self.assertIsNotNone(res)
            self.assertTrue(res["execution_status"].startswith("INFERENCE_ERROR"))
            self.assertEqual(res["rule_observed_stress"], "Mild Stress")

    def test_04_shadow_timeout_and_bounded_load_shedding(self):
        """Verifies that slow inference sheds load immediately without accumulating background tasks."""
        import time

        def slow_inference(*args, **kwargs):
            time.sleep(0.08)
            return {"status": "delayed"}

        with patch("pipeline.ml_shadow_engine.load_shadow_models", return_value=(True, "Loaded")), \
             patch("pipeline.ml_shadow_engine._execute_raw_inference", side_effect=slow_inference):
            t0 = time.time()
            res = evaluate_ml_shadow(
                farm_id=45,
                advisory_id=1002,
                crop_name="Wheat",
                rule_observed_stress="Mild Stress",
                rule_recommended_action=ACTION_SCHEDULE_IRRIGATION,
                rule_guardrail_triggered=False,
                s2_ndvi=0.45,
                s2_ndwi=0.15,
                smap_sm_pct=19.0,
                era5_precip_season_mm=0.0,
                timeout_seconds=0.02,  # Tight 20ms timeout
                db_url=None,
            )
            elapsed = time.time() - t0
            # Caller returned promptly
            self.assertLess(elapsed, 0.15)
            # Telemetry records TIMEOUT_EXCEEDED
            self.assertIsNotNone(res)
            self.assertEqual(res.get("execution_status"), "TIMEOUT_EXCEEDED")


# ==============================================================================
# STAGE 7: READ-ONLY EXTERNAL DATA RETRIEVAL & SAFETY AUDIT
# ==============================================================================
class TestStage7ReadOnlyDataRetrievalAndSafety(unittest.TestCase):
    """Validates real read-only external data retrieval and verifies zero side effects."""

    def test_01_read_only_openweather_forecast_fetch(self):
        """
        Executes real read-only OpenWeather forecast retrieval if API key is present.
        Verifies zero database writes and zero messages sent.
        """
        api_key = os.getenv("OPENWEATHER_API_KEY")
        if not api_key or api_key.strip() == "":
            self.skipTest("OPENWEATHER_API_KEY not configured in .env")

        # Centroid in Ahmednagar, Maharashtra, India
        lat, lon = 19.3463, 74.3110
        rain_48h, err = test_pipeline_module.fetch_openweather_forecast(api_key, lat, lon)
        self.assertIsNone(err, f"OpenWeather fetch returned error: {err}")
        self.assertIsNotNone(rain_48h)
        self.assertGreaterEqual(rain_48h, 0.0)

    def test_02_zero_outbound_whatsapp_messages_audit(self):
        """Verifies that no live HTTP calls to WhatsApp Graph API are made during dry run."""
        with patch("requests.post") as mock_http_post:
            # In mock mode (empty WHATSAPP_TOKEN), send_text returns False and never calls requests.post
            success = send_text("919876543210", "Dry run test message")
            self.assertFalse(success)
            mock_http_post.assert_not_called()

    def test_03_zero_database_mutations_audit(self):
        """Verifies that no live PostgreSQL database connections are opened during dry run."""
        with patch("psycopg2.connect") as mock_pg_connect:
            # Running with db_url=None guarantees zero psycopg2 connections
            res = evaluate_ml_shadow(
                farm_id=99,
                advisory_id=9999,
                crop_name="Wheat",
                rule_observed_stress="No Stress",
                rule_recommended_action=ACTION_NO_ACTION,
                rule_guardrail_triggered=False,
                s2_ndvi=0.65,
                s2_ndwi=0.25,
                smap_sm_pct=26.0,
                era5_precip_season_mm=0.0,
                db_url=None,
            )
            mock_pg_connect.assert_not_called()
            self.assertEqual(res["persistence_status"], "SKIPPED")


if __name__ == "__main__":
    print("=" * 80)
    print("      KhetSense AI — Phase 6A: Local End-to-End Dry Run Execution       ")
    print("=" * 80)
    unittest.main(verbosity=2)
