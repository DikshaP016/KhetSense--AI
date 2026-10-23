#!/usr/bin/env python3
"""
KhetSense AI — Unit Tests for Multilingual Voice-Based Irrigation Advisory
Covers:
1. Voice script formatting across English, Marathi, and Hindi (Devanagari script, regional crops).
2. Agronomic safety & rainfall guardrail alignment (no unnecessary irrigation, no technical jargon).
3. Missing fields, fallback behavior, and withholding on unsuitable farm locations.
4. TTS provider implementations: MockTTSProvider, GoogleCloudTTSProvider, EdgeTTSProvider, and factory.
5. WhatsApp media upload and audio delivery functions (mock mode, API success, and error handling).
6. Non-blocking error handling in end-to-end voice advisory delivery.
7. Pipeline integration: ensuring text advisory is never blocked by voice generation or upload failures.
"""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ["WHATSAPP_ALLOWLIST_ENABLED"] = "false"

from whatsapp.messages import (
    format_voice_script,
    infer_recommended_action,
    ACTION_IRRIGATE_NOW,
    ACTION_IRRIGATE_LIGHTLY,
    ACTION_SCHEDULE_IRRIGATION,
    ACTION_DELAY_RECHECK,
    ACTION_HOLD_RECHECK,
    ACTION_NO_ACTION,
    clean_text_for_speech,
    format_trilingual_welcome_script,
    get_message,
)
from pipeline.tts_provider import (
    BaseTTSProvider,
    TTSResult,
    MockTTSProvider,
    GoogleCloudTTSProvider,
    EdgeTTSProvider,
    get_tts_provider,
    MIME_MP3,
    MIME_OGG,
)
from whatsapp.registration_flow import (
    upload_whatsapp_media,
    send_whatsapp_audio,
    deliver_voice_advisory,
    deliver_voice_message,
    send_farmer_response,
    retry_audio_delivery,
    handle_incoming,
)
import pipeline.test_pipeline as test_pipeline_module


class TestVoiceScriptGeneration(unittest.TestCase):
    """Tests conversational voice script generation across languages, stress states, and guardrails."""

    def test_english_voice_script_severe_stress_no_rain(self):
        """Validates English voice script for severe stress and no rain (IRRIGATE_NOW)."""
        farm = {
            "id": 1,
            "farmer_name": "Ramesh",
            "crop_name": "Cotton",
            "preferred_language": "en",
        }
        advisory = {
            "observed_stress": "Severe Stress",
            "rainfall_48h": 0.0,
            "recommended_action": ACTION_IRRIGATE_NOW,
            "validation_status": "SUITABLE_CROPLAND",
        }
        script = format_voice_script(farm, advisory, language="en")
        self.assertIsNotNone(script)
        self.assertIn("Hello Ramesh", script)
        self.assertIn("your Cotton crop", script)
        self.assertIn("severe water stress", script)
        self.assertIn("No rainfall is expected", script)
        self.assertIn("irrigate your crop immediately", script)
        self.assertIn("Stay tuned to KhetSense", script)

        # Technical jargon checks
        for jargon in ["NDVI", "SMAP", "PostGIS", "satellite reflectance", "centroid"]:
            self.assertNotIn(jargon.lower(), script.lower())

    def test_english_voice_script_severe_stress_moderate_rain(self):
        """Severe stress with moderate rain triggers light irrigation recommendation."""
        farm = {"farmer_name": "Anil", "crop_name": "Soybean"}
        advisory = {
            "observed_stress": "Severe Stress",
            "rainfall_48h": 8.5,
            "recommended_action": ACTION_IRRIGATE_LIGHTLY,
            "validation_status": "SUITABLE_CROPLAND",
        }
        script = format_voice_script(farm, advisory, language="en")
        self.assertIn("Moderate rainfall of about 8.5 millimeters is expected", script)
        self.assertIn("apply only light irrigation to avoid waterlogging", script)

    def test_english_voice_script_severe_stress_heavy_rain(self):
        """Severe stress with heavy rain triggers delay recommendation (guardrail)."""
        farm = {"farmer_name": "Deepak", "crop_name": "Wheat"}
        advisory = {
            "observed_stress": "Severe Stress",
            "rainfall_48h": 22.0,
            "recommended_action": ACTION_DELAY_RECHECK,
            "validation_status": "SUITABLE_CROPLAND",
        }
        script = format_voice_script(farm, advisory, language="en")
        self.assertIn("Heavy rainfall of about 22.0 millimeters is forecast", script)
        self.assertIn("delay irrigation due to expected rain", script)

    def test_english_voice_script_mild_stress_actions(self):
        """Validates mild stress script transitions across rainfall regimes."""
        farm = {"farmer_name": "Vikram", "crop_name": "Cotton"}

        # 1. Low rain -> schedule in 24-48h
        adv_low = {
            "observed_stress": "Mild Stress",
            "rainfall_48h": 2.0,
            "recommended_action": ACTION_SCHEDULE_IRRIGATION,
            "validation_status": "SUITABLE_CROPLAND",
        }
        script_low = format_voice_script(farm, adv_low, language="en")
        self.assertIn("mild water stress", script_low)
        self.assertIn("plan to irrigate your field within the next 24 to 48 hours", script_low)

        # 2. Moderate rain -> delay
        adv_mod = {
            "observed_stress": "Mild Stress",
            "rainfall_48h": 10.0,
            "recommended_action": ACTION_DELAY_RECHECK,
            "validation_status": "SUITABLE_CROPLAND",
        }
        script_mod = format_voice_script(farm, adv_mod, language="en")
        self.assertIn("delay irrigation due to expected rain", script_mod)

        # 3. Heavy rain -> hold
        adv_heavy = {
            "observed_stress": "Mild Stress",
            "rainfall_48h": 30.0,
            "recommended_action": ACTION_HOLD_RECHECK,
            "validation_status": "SUITABLE_CROPLAND",
        }
        script_heavy = format_voice_script(farm, adv_heavy, language="en")
        self.assertIn("hold off all irrigation to prevent waterlogging", script_heavy)

    def test_english_voice_script_no_stress(self):
        """Validates healthy / no stress advisory voice script."""
        farm = {"farmer_name": "Pooja", "crop_name": "Rice"}
        advisory = {
            "observed_stress": "No Stress",
            "rainfall_48h": 0.0,
            "recommended_action": ACTION_NO_ACTION,
            "validation_status": "SUITABLE_CROPLAND",
        }
        script = format_voice_script(farm, advisory, language="en")
        self.assertIn("adequate moisture and is in good health", script)
        self.assertIn("No irrigation is needed at this time", script)

    def test_marathi_voice_script_phrasing_and_crops(self):
        """Validates natural Marathi Devanagari script, crop localization, and phrasing."""
        farm = {
            "farmer_name": "सुरेश",
            "crop_name": "Cotton",  # Should map to कापूस
            "preferred_language": "mr",
        }
        advisory = {
            "observed_stress": "Severe Stress",
            "rainfall_48h": 0.0,
            "recommended_action": ACTION_IRRIGATE_NOW,
            "validation_status": "SUITABLE_CROPLAND",
        }
        script = format_voice_script(farm, advisory, language="mr")
        self.assertIsNotNone(script)
        self.assertIn("नमस्कार सुरेशजी", script)
        self.assertIn("कापूस", script)
        self.assertIn("तीव्र पाण्याचा ताण", script)
        self.assertIn("पावसाची शक्यता नाही", script)
        self.assertIn("ताबडतोब पाणी द्या", script)
        self.assertIn("खेतसेन्सशी जोडलेले राहा", script)

    def test_marathi_voice_script_rainfall_guardrail(self):
        """Validates Marathi script with moderate rain and light irrigation advice."""
        farm = {"farmer_name": "ज्ञानेश्वर", "crop_name": "Soybean"}
        advisory = {
            "observed_stress": "Severe Stress",
            "rainfall_48h": 7.5,
            "recommended_action": ACTION_IRRIGATE_LIGHTLY,
            "validation_status": "SUITABLE_CROPLAND",
        }
        script = format_voice_script(farm, advisory, language="mr")
        self.assertIn("सोयाबीन", script)
        self.assertIn("7.5 मिलिमीटर", script)
        self.assertIn("केवळ हलके पाणी द्या", script)

    def test_hindi_voice_script_phrasing_and_crops(self):
        """Validates natural Hindi Devanagari script, crop localization, and phrasing."""
        farm = {
            "farmer_name": "राजेश",
            "crop_name": "Wheat",  # Should map to गेहूं
            "preferred_language": "hi",
        }
        advisory = {
            "observed_stress": "Mild Stress",
            "rainfall_48h": 12.0,
            "recommended_action": ACTION_DELAY_RECHECK,
            "validation_status": "SUITABLE_CROPLAND",
        }
        script = format_voice_script(farm, advisory, language="hi")
        self.assertIsNotNone(script)
        self.assertIn("नमस्ते राजेशजी", script)
        self.assertIn("गेहूं", script)
        self.assertIn("हल्का पानी का तनाव", script)
        self.assertIn("12.0 मिलीमीटर", script)
        self.assertIn("सिंचाई टालें", script)
        self.assertIn("खेतसेंस से जुड़े रहें", script)

    def test_missing_and_edge_case_inputs(self):
        """Validates safe handling of missing names, crops, rainfall, and stress values."""
        # 1. Missing farmer name -> fallback greeting
        farm_no_name = {"crop_name": "Cotton"}
        adv = {
            "observed_stress": "Mild Stress",
            "rainfall_48h": 0.0,
            "recommended_action": ACTION_SCHEDULE_IRRIGATION,
            "validation_status": "SUITABLE_CROPLAND",
        }
        script_en = format_voice_script(farm_no_name, adv, language="en")
        self.assertTrue(script_en.startswith("Hello, this is your KhetSense"))
        self.assertNotIn("Hello None", script_en)
        self.assertNotIn("Hello Farmer", script_en)

        script_mr = format_voice_script(farm_no_name, adv, language="mr")
        self.assertIn("नमस्कार शेतकरी मित्र", script_mr)

        script_hi = format_voice_script(farm_no_name, adv, language="hi")
        self.assertIn("नमस्ते किसान भाई", script_hi)

        # 2. Missing crop name
        farm_no_crop = {"farmer_name": "Ramesh"}
        script_no_crop = format_voice_script(farm_no_crop, adv, language="en")
        self.assertIn("advisory for your crop.", script_no_crop)

        # 3. Missing rainfall
        adv_no_rain = {
            "observed_stress": "Mild Stress",
            "rainfall_48h": None,
            "recommended_action": ACTION_SCHEDULE_IRRIGATION,
            "validation_status": "SUITABLE_CROPLAND",
        }
        script_no_rain = format_voice_script(farm_no_name, adv_no_rain, language="en")
        self.assertIn("Rainfall forecast data is currently unavailable.", script_no_rain)

        # 4. Unknown stress level
        adv_unknown_stress = {
            "observed_stress": "Uncertain",
            "rainfall_48h": 0.0,
            "recommended_action": None,
            "validation_status": "SUITABLE_CROPLAND",
        }
        script_unknown = format_voice_script(farm_no_name, adv_unknown_stress, language="en")
        self.assertIn("Field moisture is being monitored.", script_unknown)

    def test_unsupported_language_fallback(self):
        """Unsupported language codes fallback cleanly to English."""
        farm = {"farmer_name": "Carlos", "crop_name": "Cotton"}
        adv = {
            "observed_stress": "Severe Stress",
            "rainfall_48h": 0.0,
            "recommended_action": ACTION_IRRIGATE_NOW,
            "validation_status": "SUITABLE_CROPLAND",
        }
        script = format_voice_script(farm, adv, language="es")
        self.assertIn("Hello Carlos", script)
        self.assertIn("severe water stress", script)

    def test_unsuitable_and_withheld_locations_return_none(self):
        """Unsuitable locations and withheld advisories must NEVER produce an irrigation voice script."""
        farm = {"farmer_name": "Test User", "crop_name": "Cotton"}

        # 1. Urban location
        adv_urban = {
            "validation_status": "LIKELY_URBAN",
            "observed_stress": "Severe Stress",
            "rainfall_48h": 0.0,
            "recommended_action": ACTION_IRRIGATE_NOW,
        }
        self.assertIsNone(format_voice_script(farm, adv_urban, language="en"))

        # 2. Barren / uncertain location
        adv_barren = {
            "validation_status": "BARREN_OR_UNCERTAIN",
            "observed_stress": "Severe Stress",
            "rainfall_48h": 0.0,
        }
        self.assertIsNone(format_voice_script(farm, adv_barren, language="mr"))

        # 3. Insufficient satellite imagery
        adv_cloudy = {
            "validation_status": "INSUFFICIENT_SATELLITE_DATA",
            "observed_stress": "Severe Stress",
        }
        self.assertIsNone(format_voice_script(farm, adv_cloudy, language="hi"))

        # 4. Validation failed in stress_level
        adv_fail_stress = {
            "stress_level": "VALIDATION_FAILED: LIKELY_URBAN",
            "rainfall_48h": 0.0,
        }
        self.assertIsNone(format_voice_script(farm, adv_fail_stress, language="en"))

        # 5. is_suitable_for_advisory = False
        adv_not_suitable = {
            "is_suitable_for_advisory": False,
            "observed_stress": "Severe Stress",
        }
        self.assertIsNone(format_voice_script(farm, adv_not_suitable, language="en"))

        # 6. None or empty advisory
        self.assertIsNone(format_voice_script(farm, None, language="en"))
        self.assertIsNone(format_voice_script(farm, {}, language="en"))

        # 7. Unvalidated historical advisory
        adv_unvalidated = {
            "validation_status": "UNVALIDATED",
            "observed_stress": "Severe Stress",
            "recommended_action": ACTION_IRRIGATE_NOW,
        }
        self.assertIsNone(format_voice_script(farm, adv_unvalidated, language="en"))
        self.assertIsNone(format_voice_script(farm, adv_unvalidated, language="mr"))
        self.assertIsNone(format_voice_script(farm, adv_unvalidated, language="hi"))


class TestTTSProviderImplementations(unittest.TestCase):
    """Tests the pluggable TTS provider abstractions and concrete classes."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="khetsense_tts_test_")

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            for fname in os.listdir(self.temp_dir):
                fpath = os.path.join(self.temp_dir, fname)
                try:
                    os.remove(fpath)
                except OSError:
                    pass
            try:
                os.rmdir(self.temp_dir)
            except OSError:
                pass

    def test_mock_tts_provider_basic_synthesis(self):
        """Verifies MockTTSProvider produces valid synthetic audio without external network calls."""
        provider = MockTTSProvider(temp_dir=self.temp_dir)
        self.assertTrue(provider.is_available())

        res = provider.synthesize(
            text="Hello Ramesh, this is your irrigation advisory.",
            language="en",
            audio_format="mp3",
        )
        self.assertIsInstance(res, TTSResult)
        self.assertEqual(res.mime_type, MIME_MP3)
        self.assertEqual(res.language, "en")
        self.assertEqual(res.provider_name, "mock")
        self.assertGreater(len(res.audio_bytes), 0)
        self.assertIn(b"KHETSENSE_MOCK_AUDIO", res.audio_bytes)
        self.assertTrue(os.path.exists(res.file_path))
        self.assertGreater(res.duration_seconds, 0)

        # Verify call tracking
        self.assertEqual(len(provider.synthesized_calls), 1)
        self.assertEqual(provider.synthesized_calls[0]["language"], "en")

        # Verify cleanup
        cleaned = res.cleanup()
        self.assertTrue(cleaned)
        self.assertFalse(os.path.exists(res.file_path))

    def test_mock_tts_provider_cache_deduplication(self):
        """Repeated synthesis with identical parameters retrieves cached result."""
        provider = MockTTSProvider(temp_dir=self.temp_dir)
        res1 = provider.synthesize("Test audio caching", language="mr")
        res2 = provider.synthesize("Test audio caching", language="mr")

        self.assertEqual(res1.file_path, res2.file_path)
        self.assertEqual(res1.audio_bytes, res2.audio_bytes)

    def test_mock_tts_provider_empty_text_validation(self):
        """Provider must reject empty or whitespace-only text."""
        provider = MockTTSProvider(temp_dir=self.temp_dir)
        with self.assertRaises(ValueError):
            provider.synthesize("")
        with self.assertRaises(ValueError):
            provider.synthesize("   \n\t  ")

    def test_mock_tts_provider_simulated_error(self):
        """Provider simulates external TTS API failure when configured."""
        provider = MockTTSProvider(simulate_error="API quota exceeded", temp_dir=self.temp_dir)
        with self.assertRaises(RuntimeError) as ctx:
            provider.synthesize("Some script", language="hi")
        self.assertIn("API quota exceeded", str(ctx.exception))

    def test_mock_tts_provider_custom_output_path(self):
        """Provider writes audio to explicit output path if specified."""
        provider = MockTTSProvider(temp_dir=self.temp_dir)
        custom_out = os.path.join(self.temp_dir, "custom_speech.mp3")
        res = provider.synthesize("Save here", output_path=custom_out)
        self.assertEqual(res.file_path, custom_out)
        self.assertTrue(os.path.exists(custom_out))

    @patch("pipeline.tts_provider.requests.post")
    def test_google_cloud_tts_provider_successful_synthesis(self, mock_post):
        """Validates Google Cloud TTS REST API request structure, voice mappings, and base64 decoding."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        # base64 encoded "GOOGLE_CLOUD_AUDIO_BYTES"
        import base64
        mock_response.json.return_value = {
            "audioContent": base64.b64encode(b"GOOGLE_CLOUD_AUDIO_BYTES").decode("utf-8")
        }
        mock_post.return_value = mock_response

        provider = GoogleCloudTTSProvider(api_key="test_fake_api_key", temp_dir=self.temp_dir)
        self.assertTrue(provider.is_available())

        # Synthesize Marathi
        res = provider.synthesize("नमस्कार शेतकरी मित्र", language="mr", audio_format="mp3")
        self.assertEqual(res.provider_name, "google_cloud")
        self.assertEqual(res.audio_bytes, b"GOOGLE_CLOUD_AUDIO_BYTES")
        self.assertEqual(res.language, "mr")
        self.assertTrue(os.path.exists(res.file_path))

        # Verify API request payload
        mock_post.assert_called_once()
        endpoint_called, kwargs = mock_post.call_args
        self.assertIn("key=test_fake_api_key", endpoint_called[0])
        req_payload = kwargs["json"]
        self.assertEqual(req_payload["input"]["text"], "नमस्कार शेतकरी मित्र")
        self.assertEqual(req_payload["voice"]["languageCode"], "mr-IN")
        self.assertEqual(req_payload["voice"]["name"], "mr-IN-Wavenet-A")
        self.assertEqual(req_payload["audioConfig"]["audioEncoding"], "MP3")

    @patch("pipeline.tts_provider.requests.post")
    def test_google_cloud_tts_provider_api_error_handling(self, mock_post):
        """Google Cloud TTS API errors raise RuntimeError."""
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = '{"error": {"message": "Invalid API Key"}}'
        mock_post.return_value = mock_response

        provider = GoogleCloudTTSProvider(api_key="bad_key", temp_dir=self.temp_dir)
        with self.assertRaises(RuntimeError) as ctx:
            provider.synthesize("Hello", language="en")
        self.assertIn("Google Cloud TTS API error 403", str(ctx.exception))

    def test_edge_tts_provider_availability(self):
        """EdgeTTSProvider reports availability based on package presence."""
        provider = EdgeTTSProvider(temp_dir=self.temp_dir)
        self.assertIsInstance(provider.is_available(), bool)

        # Simulate package missing -> False
        with patch.dict(sys.modules, {"edge_tts": None}):
            self.assertFalse(provider.is_available())

        # Simulate package present -> True
        mock_edge_mod = MagicMock()
        with patch.dict(sys.modules, {"edge_tts": mock_edge_mod}):
            self.assertTrue(provider.is_available())

    def test_edge_tts_provider_language_mapping_and_synthesis(self):
        """Verifies EdgeTTSProvider language-to-voice mappings (en, mr, hi, fallback) and TTSResult fields (mocked)."""
        self.assertEqual(EdgeTTSProvider.VOICE_CONFIG["en"], "en-IN-NeerjaNeural")
        self.assertEqual(EdgeTTSProvider.VOICE_CONFIG["mr"], "mr-IN-AarohiNeural")
        self.assertEqual(EdgeTTSProvider.VOICE_CONFIG["hi"], "hi-IN-SwaraNeural")

        fake_mp3 = b"\xff\xfb\x90\x00FAKE_EDGE_TTS_MP3_STREAM"
        mock_edge_mod = MagicMock()

        def make_communicate(text, voice):
            comm = MagicMock()
            async def _fake_save(path):
                with open(path, "wb") as f:
                    f.write(fake_mp3)
            comm.save = _fake_save
            return comm

        mock_edge_mod.Communicate.side_effect = make_communicate

        cases = [
            ("en", "en", "en-IN-NeerjaNeural", "Hello Ramesh, irrigate your crop."),
            ("mr", "mr", "mr-IN-AarohiNeural", "नमस्कार रमेशजी, तुमच्या पिकाला पाणी द्या."),
            ("hi", "hi", "hi-IN-SwaraNeural", "नमस्ते रमेशजी, अपनी फसल की सिंचाई करें।"),
            ("fr", "en", "en-IN-NeerjaNeural", "Unsupported language falls back to English."),
        ]

        with patch.dict(sys.modules, {"edge_tts": mock_edge_mod}):
            for input_lang, expected_lang, expected_voice, sample_text in cases:
                provider = EdgeTTSProvider(temp_dir=self.temp_dir)
                mock_edge_mod.Communicate.reset_mock()

                res = provider.synthesize(sample_text, language=input_lang)

                mock_edge_mod.Communicate.assert_called_once_with(sample_text, expected_voice)
                self.assertIsInstance(res, TTSResult)
                self.assertEqual(res.audio_bytes, fake_mp3)
                self.assertEqual(res.mime_type, MIME_MP3)
                self.assertEqual(res.language, expected_lang)
                self.assertEqual(res.provider_name, "edge_tts")
                self.assertEqual(res.metadata.get("voice"), expected_voice)
                self.assertIsNotNone(res.file_path)
                self.assertTrue(os.path.exists(res.file_path))
                self.assertTrue(res.cleanup())

    def test_edge_tts_provider_error_handling(self):
        """Verifies EdgeTTSProvider error handling for empty text, missing dependency, and synthesis failures."""
        provider = EdgeTTSProvider(temp_dir=self.temp_dir)

        # 1. Empty / whitespace text raises ValueError
        with self.assertRaises(ValueError):
            provider.synthesize("", language="en")
        with self.assertRaises(ValueError):
            provider.synthesize("   ", language="mr")

        # 2. Missing edge-tts package raises RuntimeError
        with patch.dict(sys.modules, {"edge_tts": None}):
            with self.assertRaises(RuntimeError) as ctx:
                provider.synthesize("Hello", language="en")
            self.assertIn("edge-tts", str(ctx.exception))

        # 3. Network / synthesis exception propagates and cleans up temporary file
        mock_edge_mod = MagicMock()
        def make_failing_communicate(text, voice):
            comm = MagicMock()
            async def _fail_save(path):
                raise RuntimeError("Simulated WebSocket connection error")
            comm.save = _fail_save
            return comm

        mock_edge_mod.Communicate.side_effect = make_failing_communicate
        with patch.dict(sys.modules, {"edge_tts": mock_edge_mod}):
            with self.assertRaises(RuntimeError) as ctx:
                provider.synthesize("Hello farmer", language="en")
            self.assertIn("Simulated WebSocket connection error", str(ctx.exception))

        # 4. Empty audio output raises RuntimeError
        def make_empty_communicate(text, voice):
            comm = MagicMock()
            async def _empty_save(path):
                with open(path, "wb") as f:
                    f.write(b"")
            comm.save = _empty_save
            return comm

        mock_edge_mod.Communicate.side_effect = make_empty_communicate
        with patch.dict(sys.modules, {"edge_tts": mock_edge_mod}):
            with self.assertRaises(RuntimeError) as ctx:
                provider.synthesize("Hello farmer", language="en")
            self.assertIn("empty audio file", str(ctx.exception))

    def test_get_tts_provider_factory(self):
        """Factory returns correct provider based on configuration and availability."""
        # 1. Default (when TTS_PROVIDER is unset/empty) -> MockTTSProvider
        with patch.dict(os.environ, {"TTS_PROVIDER": ""}):
            p_default = get_tts_provider()
            self.assertIsInstance(p_default, MockTTSProvider)

        # 2. Explicit 'mock'
        p_mock = get_tts_provider("mock")
        self.assertIsInstance(p_mock, MockTTSProvider)

        # 3. Google without available credentials -> graceful fallback to MockTTSProvider
        with patch.object(GoogleCloudTTSProvider, "is_available", return_value=False):
            p_gcloud_fallback = get_tts_provider("google")
            self.assertIsInstance(p_gcloud_fallback, MockTTSProvider)

        # 4. Google with available credentials -> returns GoogleCloudTTSProvider
        with patch.object(GoogleCloudTTSProvider, "is_available", return_value=True):
            p_gcloud_ready = get_tts_provider("google")
            self.assertIsInstance(p_gcloud_ready, GoogleCloudTTSProvider)

        # 5. Edge without package available -> graceful fallback to MockTTSProvider
        with patch.object(EdgeTTSProvider, "is_available", return_value=False):
            p_edge_fallback = get_tts_provider("edge")
            self.assertIsInstance(p_edge_fallback, MockTTSProvider)

        # 6. Edge with package available -> returns EdgeTTSProvider
        with patch.object(EdgeTTSProvider, "is_available", return_value=True):
            p_edge_ready = get_tts_provider("edge")
            self.assertIsInstance(p_edge_ready, EdgeTTSProvider)
            p_edge_env = None
            with patch.dict(os.environ, {"TTS_PROVIDER": "edge"}):
                p_edge_env = get_tts_provider()
            self.assertIsInstance(p_edge_env, EdgeTTSProvider)


class TestWhatsAppVoiceDelivery(unittest.TestCase):
    """Tests media upload, audio messaging, and delivery orchestration."""

    def test_upload_whatsapp_media_mock_mode(self):
        """When credentials are not set, upload_whatsapp_media returns mock ID safely."""
        with patch.dict(os.environ, {"WHATSAPP_TOKEN": "", "META_ACCESS_TOKEN": "", "WHATSAPP_PHONE_NUMBER_ID": ""}):
            media_id = upload_whatsapp_media(b"fake_mp3_data", mime_type="audio/mpeg")
            self.assertEqual(media_id, "mock_media_id_audio_12345")

    @patch("whatsapp.registration_flow.requests.post")
    def test_upload_whatsapp_media_api_success(self, mock_post):
        """Validates successful multipart media upload to Meta Graph API v21.0."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": "meta_audio_media_777"}
        mock_post.return_value = mock_resp

        media_id = upload_whatsapp_media(
            file_bytes_or_path=b"audio_bytes_123",
            mime_type="audio/mpeg",
            filename="advisory.mp3",
            phone_number_id="100998877",
            token="EAABtesttoken",
        )
        self.assertEqual(media_id, "meta_audio_media_777")
        mock_post.assert_called_once()
        url = mock_post.call_args[0][0]
        self.assertIn("/100998877/media", url)

    @patch("whatsapp.registration_flow.requests.post")
    def test_upload_whatsapp_media_api_failure(self, mock_post):
        """Validates graceful failure handling when media upload fails."""
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_post.return_value = mock_resp

        media_id = upload_whatsapp_media(
            file_bytes_or_path=b"audio_bytes_123",
            phone_number_id="100998877",
            token="EAABtesttoken",
        )
        self.assertIsNone(media_id)

    def test_send_whatsapp_audio_mock_mode(self):
        """When credentials are not set, send_whatsapp_audio returns True in mock mode."""
        with patch.dict(os.environ, {"WHATSAPP_TOKEN": "", "META_ACCESS_TOKEN": "", "WHATSAPP_PHONE_NUMBER_ID": ""}):
            sent = send_whatsapp_audio(to="919876543210", media_id="mock_media_123")
            self.assertTrue(sent)

    @patch("whatsapp.registration_flow.requests.post")
    def test_send_whatsapp_audio_api_success(self, mock_post):
        """Validates successful audio dispatch to recipient via WhatsApp Cloud API."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"messages": [{"id": "wamid.audio123"}]}
        mock_post.return_value = mock_resp

        sent = send_whatsapp_audio(
            to="919876543210",
            media_id="meta_audio_media_777",
            phone_number_id="100998877",
            token="EAABtesttoken",
        )
        self.assertTrue(sent)
        mock_post.assert_called_once()
        payload = mock_post.call_args[1]["json"]
        self.assertEqual(payload["type"], "audio")
        self.assertEqual(payload["audio"]["id"], "meta_audio_media_777")
        self.assertEqual(payload["to"], "919876543210")

    def test_send_whatsapp_audio_missing_media_and_url(self):
        """Fails gracefully if neither media_id nor audio_url is provided."""
        sent = send_whatsapp_audio(to="919876543210")
        self.assertFalse(sent)

    def test_deliver_voice_advisory_end_to_end_custom_sender(self):
        """Tests complete delivery orchestration using a mock custom outbound voice sender."""
        provider = MockTTSProvider()
        mock_voice_sender = MagicMock(return_value=True)

        res = deliver_voice_advisory(
            to="919876543210",
            script_text="Hello Ramesh, this is your advisory.",
            lang="en",
            tts_provider=provider,
            outbound_voice_sender=mock_voice_sender,
        )
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["to"], "919876543210")
        self.assertEqual(res["language"], "en")
        mock_voice_sender.assert_called_once()
        called_to, called_audio = mock_voice_sender.call_args[0]
        self.assertEqual(called_to, "919876543210")
        self.assertTrue(os.path.exists(called_audio))

    def test_deliver_voice_advisory_synthesis_error_graceful(self):
        """If TTS synthesis fails, deliver_voice_advisory returns failed status without raising."""
        failing_provider = MockTTSProvider(simulate_error="TTS quota exceeded")
        res = deliver_voice_advisory(
            to="919876543210",
            script_text="Hello Ramesh, this is your advisory.",
            lang="en",
            tts_provider=failing_provider,
        )
        self.assertEqual(res["status"], "failed")
        self.assertIn("synthesis_failed", res["error"])

    def test_deliver_voice_advisory_empty_script_skipped(self):
        """Empty script is skipped safely."""
        res = deliver_voice_advisory(to="919876543210", script_text="", lang="en")
        self.assertEqual(res["status"], "skipped")
        self.assertEqual(res["reason"], "empty_script")


class TestPipelineVoiceIntegration(unittest.TestCase):
    """Tests the integration of voice advisories within run_pipeline_for_farm."""

    def setUp(self):
        self.mock_text_sender = MagicMock(return_value=True)
        self.mock_voice_sender = MagicMock(return_value=True)

    @patch("pipeline.test_pipeline.validate_agricultural_location")
    @patch("pipeline.test_pipeline.save_advisory_to_database")
    @patch("pipeline.test_pipeline.fetch_openweather_forecast")
    @patch("pipeline.test_pipeline.fetch_smap_soil_moisture")
    @patch("pipeline.test_pipeline.fetch_sentinel2_indices")
    @patch("pipeline.test_pipeline.ee")
    @patch("pipeline.test_pipeline.authenticate_earth_engine")
    @patch("pipeline.test_pipeline.get_farm_from_database")
    def test_run_pipeline_for_farm_with_voice_advisory_success(
        self,
        mock_get_farm_db,
        mock_auth_ee,
        mock_ee,
        mock_fetch_s2,
        mock_fetch_smap,
        mock_fetch_owm,
        mock_save_adv,
        mock_validate_loc,
    ):
        """Verifies both text and voice advisories are delivered when send_voice_advisory=True."""
        mock_get_farm_db.return_value = {
            "id": 10,
            "farmer_name": "सुरेश",
            "mobile_number": "919876543210",
            "preferred_language": "mr",
            "crop_name": "Cotton",
            "ee_coords": [[77.1, 20.5], [77.2, 20.5], [77.2, 20.6], [77.1, 20.6], [77.1, 20.5]],
            "centroid_lat": 20.55,
            "centroid_lon": 77.15,
        }
        mock_fetch_s2.return_value = (0.22, 0.08, {"date": "2026-03-30", "cloud_pct": 2.0}, None)
        mock_fetch_smap.return_value = (0.11, {"date": "2026-03-30"}, None)
        mock_fetch_owm.return_value = (0.0, None)
        mock_validate_loc.return_value = {
            "is_suitable_for_advisory": True,
            "outcome": "SUITABLE_CROPLAND",
            "land_cover_class": "Cropland",
            "reason": "Active crop vegetation confirmed.",
        }
        mock_save_adv.return_value = {
            "id": 99,
            "farm_id": 10,
            "observation_date": "2026-03-30",
            "stress_level": "Severe Stress",
            "created_at": "2026-03-30 10:00:00",
        }

        mock_tts = MockTTSProvider()

        res = test_pipeline_module.run_pipeline_for_farm(
            farm_id=10,
            outbound_sender=self.mock_text_sender,
            auto_send_advisory=True,
            send_voice_advisory=True,
            outbound_voice_sender=self.mock_voice_sender,
            tts_provider=mock_tts,
        )

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["farm_id"], 10)
        self.assertTrue(res["advisory_sent"])
        self.assertTrue(res["voice_sent"])
        self.assertIsNotNone(res["voice_script"])
        self.assertIn("नमस्कार सुरेशजी", res["voice_script"])
        self.assertIn("कापूस", res["voice_script"])

        # Check that both text sender and voice sender were invoked
        self.mock_text_sender.assert_called_once()
        self.mock_voice_sender.assert_called_once()
        sent_voice_to, sent_voice_path = self.mock_voice_sender.call_args[0]
        self.assertEqual(sent_voice_to, "919876543210")
        self.assertTrue(os.path.exists(sent_voice_path))

    @patch("pipeline.test_pipeline.validate_agricultural_location")
    @patch("pipeline.test_pipeline.save_advisory_to_database")
    @patch("pipeline.test_pipeline.fetch_openweather_forecast")
    @patch("pipeline.test_pipeline.fetch_smap_soil_moisture")
    @patch("pipeline.test_pipeline.fetch_sentinel2_indices")
    @patch("pipeline.test_pipeline.ee")
    @patch("pipeline.test_pipeline.authenticate_earth_engine")
    @patch("pipeline.test_pipeline.get_farm_from_database")
    def test_run_pipeline_for_farm_voice_failure_does_not_block_text(
        self,
        mock_get_farm_db,
        mock_auth_ee,
        mock_ee,
        mock_fetch_s2,
        mock_fetch_smap,
        mock_fetch_owm,
        mock_save_adv,
        mock_validate_loc,
    ):
        """Voice synthesis or delivery failure must NEVER block or fail the primary text advisory."""
        mock_get_farm_db.return_value = {
            "id": 11,
            "farmer_name": "Ramesh",
            "mobile_number": "919876543211",
            "preferred_language": "en",
            "crop_name": "Wheat",
            "ee_coords": [[77.1, 20.5], [77.2, 20.5], [77.2, 20.6], [77.1, 20.6], [77.1, 20.5]],
            "centroid_lat": 20.55,
            "centroid_lon": 77.15,
        }
        mock_fetch_s2.return_value = (0.25, 0.10, {"date": "2026-03-30", "cloud_pct": 1.0}, None)
        mock_fetch_smap.return_value = (0.12, {"date": "2026-03-30"}, None)
        mock_fetch_owm.return_value = (0.0, None)
        mock_validate_loc.return_value = {
            "is_suitable_for_advisory": True,
            "outcome": "SUITABLE_CROPLAND",
            "land_cover_class": "Cropland",
            "reason": "Active crop vegetation confirmed.",
        }
        mock_save_adv.return_value = {
            "id": 100,
            "farm_id": 11,
            "observation_date": "2026-03-30",
            "stress_level": "Severe Stress",
            "created_at": "2026-03-30 10:00:00",
        }

        failing_tts = MockTTSProvider(simulate_error="Network down")

        res = test_pipeline_module.run_pipeline_for_farm(
            farm_id=11,
            outbound_sender=self.mock_text_sender,
            auto_send_advisory=True,
            send_voice_advisory=True,
            tts_provider=failing_tts,
        )

        # Main pipeline succeeds, text advisory is delivered
        self.assertEqual(res["status"], "success")
        self.assertTrue(res["advisory_sent"])
        self.mock_text_sender.assert_called_once()

        # Voice failed gracefully
        self.assertFalse(res["voice_sent"])

    @patch("pipeline.test_pipeline.validate_agricultural_location")
    @patch("pipeline.test_pipeline.save_advisory_to_database")
    @patch("pipeline.test_pipeline.fetch_openweather_forecast")
    @patch("pipeline.test_pipeline.fetch_smap_soil_moisture")
    @patch("pipeline.test_pipeline.fetch_sentinel2_indices")
    @patch("pipeline.test_pipeline.ee")
    @patch("pipeline.test_pipeline.authenticate_earth_engine")
    @patch("pipeline.test_pipeline.get_farm_from_database")
    def test_run_pipeline_for_farm_unsuitable_location_withholds_voice(
        self,
        mock_get_farm_db,
        mock_auth_ee,
        mock_ee,
        mock_fetch_s2,
        mock_fetch_smap,
        mock_fetch_owm,
        mock_save_adv,
        mock_validate_loc,
    ):
        """When farm location is unsuitable (e.g. LIKELY_URBAN), voice advisory is withheld."""
        mock_get_farm_db.return_value = {
            "id": 12,
            "farmer_name": "Urban User",
            "mobile_number": "919876543212",
            "preferred_language": "en",
            "crop_name": "Cotton",
            "ee_coords": [[77.1, 20.5], [77.2, 20.5], [77.2, 20.6], [77.1, 20.6], [77.1, 20.5]],
            "centroid_lat": 20.55,
            "centroid_lon": 77.15,
        }
        mock_fetch_s2.return_value = (0.05, -0.05, {"date": "2026-03-30", "cloud_pct": 1.0}, None)
        mock_fetch_smap.return_value = (0.10, {"date": "2026-03-30"}, None)
        mock_fetch_owm.return_value = (0.0, None)
        mock_validate_loc.return_value = {
            "is_suitable_for_advisory": False,
            "outcome": "LIKELY_URBAN",
            "land_cover_class": "Urban / Built-up",
            "reason": "Centroid overlaps urban land cover.",
        }

        res = test_pipeline_module.run_pipeline_for_farm(
            farm_id=12,
            outbound_sender=self.mock_text_sender,
            auto_send_advisory=True,
            send_voice_advisory=True,
            enable_voice_chatbot=False,
            outbound_voice_sender=self.mock_voice_sender,
        )

        self.assertEqual(res["status"], "validation_failed")
        self.assertFalse(res["advisory_sent"])
        self.mock_voice_sender.assert_not_called()
        self.mock_text_sender.assert_called_once()  # Delivered urban location warning text

    @patch("pipeline.test_pipeline.validate_agricultural_location")
    @patch("pipeline.test_pipeline.save_advisory_to_database")
    @patch("pipeline.test_pipeline.fetch_openweather_forecast")
    @patch("pipeline.test_pipeline.fetch_smap_soil_moisture")
    @patch("pipeline.test_pipeline.fetch_sentinel2_indices")
    @patch("pipeline.test_pipeline.ee")
    @patch("pipeline.test_pipeline.authenticate_earth_engine")
    @patch("pipeline.test_pipeline.get_farm_from_database")
    def test_pipeline_location_validation_notice_with_whole_chat_voice(
        self,
        mock_get_farm_db,
        mock_auth_ee,
        mock_ee,
        mock_fetch_s2,
        mock_fetch_smap,
        mock_fetch_owm,
        mock_save_adv,
        mock_validate_loc,
    ):
        """When whole-chat voice is enabled, unsuitable location notice delivers text and voice in farmer's language."""
        mock_get_farm_db.return_value = {
            "id": 15,
            "farmer_name": "सचिन",
            "mobile_number": "919876543215",
            "preferred_language": "mr",
            "crop_name": "Soybean",
            "ee_coords": [[77.1, 20.5], [77.2, 20.5], [77.2, 20.6], [77.1, 20.6], [77.1, 20.5]],
            "centroid_lat": 20.55,
            "centroid_lon": 77.15,
        }
        mock_fetch_s2.return_value = (0.05, -0.05, {"date": "2026-03-30", "cloud_pct": 1.0}, None)
        mock_fetch_smap.return_value = (0.10, {"date": "2026-03-30"}, None)
        mock_fetch_owm.return_value = (0.0, None)
        mock_validate_loc.return_value = {
            "is_suitable_for_advisory": False,
            "outcome": "LIKELY_URBAN",
            "land_cover_class": "Urban / Built-up",
            "reason": "Centroid overlaps urban land cover.",
        }

        mock_tts = MockTTSProvider()

        res = test_pipeline_module.run_pipeline_for_farm(
            farm_id=15,
            outbound_sender=self.mock_text_sender,
            auto_send_advisory=True,
            send_voice_advisory=False,
            enable_voice_chatbot=True,
            outbound_voice_sender=self.mock_voice_sender,
            tts_provider=mock_tts,
        )

        self.assertEqual(res["status"], "validation_failed")
        self.assertFalse(res["advisory_sent"])
        self.assertFalse(res["voice_sent"])  # Advisory voice is withheld!
        self.assertTrue(res["notice_voice_sent"])  # Location warning voice note delivered
        self.mock_text_sender.assert_called_once()
        sent_text = self.mock_text_sender.call_args[0][1]
        self.assertIn("शहरी किंवा इमारतींचे क्षेत्र", sent_text)  # Marathi urban notice
        self.mock_voice_sender.assert_called_once()
        sent_phone, sent_audio = self.mock_voice_sender.call_args[0]
        self.assertEqual(sent_phone, "919876543215")
        self.assertTrue(os.path.exists(sent_audio))

    @patch("pipeline.test_pipeline.validate_agricultural_location")
    @patch("pipeline.test_pipeline.save_advisory_to_database")
    @patch("pipeline.test_pipeline.fetch_openweather_forecast")
    @patch("pipeline.test_pipeline.fetch_smap_soil_moisture")
    @patch("pipeline.test_pipeline.fetch_sentinel2_indices")
    @patch("pipeline.test_pipeline.ee")
    @patch("pipeline.test_pipeline.authenticate_earth_engine")
    @patch("pipeline.test_pipeline.get_farm_from_database")
    def test_pipeline_location_validation_notice_voice_failure_does_not_block_text(
        self,
        mock_get_farm_db,
        mock_auth_ee,
        mock_ee,
        mock_fetch_s2,
        mock_fetch_smap,
        mock_fetch_owm,
        mock_save_adv,
        mock_validate_loc,
    ):
        """Audio delivery failure on location validation notice must not block or fail text delivery."""
        mock_get_farm_db.return_value = {
            "id": 16,
            "farmer_name": "अनिल",
            "mobile_number": "919876543216",
            "preferred_language": "hi",
            "crop_name": "Wheat",
            "ee_coords": [[77.1, 20.5], [77.2, 20.5], [77.2, 20.6], [77.1, 20.6], [77.1, 20.5]],
            "centroid_lat": 20.55,
            "centroid_lon": 77.15,
        }
        mock_fetch_s2.return_value = (0.05, -0.05, {"date": "2026-03-30", "cloud_pct": 1.0}, None)
        mock_fetch_smap.return_value = (0.10, {"date": "2026-03-30"}, None)
        mock_fetch_owm.return_value = (0.0, None)
        mock_validate_loc.return_value = {
            "is_suitable_for_advisory": False,
            "outcome": "BARREN_OR_UNCERTAIN",
            "land_cover_class": "Barren land",
            "reason": "NDVI below threshold.",
        }

        def mock_failing_voice(to, audio):
            raise RuntimeError("WhatsApp API timeout")

        res = test_pipeline_module.run_pipeline_for_farm(
            farm_id=16,
            outbound_sender=self.mock_text_sender,
            auto_send_advisory=True,
            enable_voice_chatbot=True,
            outbound_voice_sender=mock_failing_voice,
            tts_provider=MockTTSProvider(),
        )

        self.assertEqual(res["status"], "validation_failed")
        self.assertFalse(res["advisory_sent"])
        self.assertFalse(res["voice_sent"])
        self.assertFalse(res["notice_voice_sent"])
        self.mock_text_sender.assert_called_once()
        sent_text = self.mock_text_sender.call_args[0][1]
        self.assertIn("सक्रिय फसल की पुष्टि नहीं हो सकी", sent_text)  # Hindi barren notice

    @patch("pipeline.test_pipeline.get_farm_from_database")
    def test_pipeline_failure_notice_with_whole_chat_voice(
        self,
        mock_get_farm_db,
    ):
        """When an exception occurs during pipeline execution, failure notice delivers text and voice in farmer's language."""
        mock_get_farm_db.return_value = {
            "id": 17,
            "farmer_name": "राजेश",
            "mobile_number": "919876543217",
            "preferred_language": "hi",
            "crop_name": "Cotton",
            "ee_coords": [[77.1, 20.5], [77.2, 20.5], [77.2, 20.6], [77.1, 20.6], [77.1, 20.5]],
            "centroid_lat": 20.55,
            "centroid_lon": 77.15,
        }

        with patch("pipeline.test_pipeline.authenticate_earth_engine", side_effect=RuntimeError("GEE quota exceeded")):
            res = test_pipeline_module.run_pipeline_for_farm(
                farm_id=17,
                outbound_sender=self.mock_text_sender,
                enable_voice_chatbot=True,
                outbound_voice_sender=self.mock_voice_sender,
                tts_provider=MockTTSProvider(),
            )

        self.assertEqual(res["status"], "error")
        self.assertIn("GEE quota exceeded", res["error"])
        self.assertTrue(res["voice_sent"])
        self.mock_text_sender.assert_called_once()
        sent_text = self.mock_text_sender.call_args[0][1]
        self.assertIn("किसान: राजेश", sent_text)
        self.assertIn("अस्थायी देरी", sent_text)  # Hindi failure notice
        self.mock_voice_sender.assert_called_once()
        sent_phone, _ = self.mock_voice_sender.call_args[0]
        self.assertEqual(sent_phone, "919876543217")

    @patch("pipeline.test_pipeline.get_farm_from_database")
    def test_pipeline_failure_notice_voice_failure_does_not_block_text(
        self,
        mock_get_farm_db,
    ):
        """Audio failure during pipeline failure notification must not block failure notice text delivery."""
        mock_get_farm_db.return_value = {
            "id": 18,
            "farmer_name": "विकास",
            "mobile_number": "919876543218",
            "preferred_language": "mr",
            "crop_name": "Cotton",
            "ee_coords": [[77.1, 20.5], [77.2, 20.5], [77.2, 20.6], [77.1, 20.6], [77.1, 20.5]],
            "centroid_lat": 20.55,
            "centroid_lon": 77.15,
        }

        def mock_failing_voice(to, audio):
            raise RuntimeError("Media service unavailable")

        with patch("pipeline.test_pipeline.authenticate_earth_engine", side_effect=RuntimeError("Service down")):
            res = test_pipeline_module.run_pipeline_for_farm(
                farm_id=18,
                outbound_sender=self.mock_text_sender,
                enable_voice_chatbot=True,
                outbound_voice_sender=mock_failing_voice,
                tts_provider=MockTTSProvider(),
            )

        self.assertEqual(res["status"], "error")
        self.assertFalse(res["voice_sent"])
        self.mock_text_sender.assert_called_once()
        sent_text = self.mock_text_sender.call_args[0][1]
        self.assertIn("शेतकरी: विकास", sent_text)
        self.assertIn("तात्पुरता विलंब", sent_text)  # Marathi failure notice

    def test_duplicate_pipeline_run_locking(self):
        """Verifies _ACTIVE_PIPELINE_RUNS deduplication prevents concurrent duplicate runs."""
        with test_pipeline_module._ACTIVE_PIPELINE_LOCK:
            test_pipeline_module._ACTIVE_PIPELINE_RUNS.add(999)

        try:
            res = test_pipeline_module.run_pipeline_for_farm(farm_id=999, force=False)
            self.assertEqual(res["status"], "already_running")
            self.assertEqual(res["farm_id"], 999)
        finally:
            with test_pipeline_module._ACTIVE_PIPELINE_LOCK:
                test_pipeline_module._ACTIVE_PIPELINE_RUNS.discard(999)


class TestWholeChatVoiceDelivery(unittest.TestCase):
    """
    Unit tests for KhetSense AI Whole-Chat TEXT + VOICE feature:
    - Text sanitization (emojis, markdown, Google Maps link replacement, numbers/names preservation)
    - Trilingual welcome audio script formatting and neural voice synthesis (EN, MR, HI)
    - Omnichannel dispatcher (text-first primacy, non-blocking voice note delivery)
    - Partial-failure recovery & audio-only retry (no duplicate text)
    - Multilingual conversational turns in registration and status checks
    """

    def setUp(self):
        self.mock_text_sender = MagicMock(return_value=True)
        self.mock_voice_sender = MagicMock(return_value=True)
        self.mock_tts = MockTTSProvider()

        # In-memory session and registration state for conversational turns
        self.sessions = {}
        self.processed_messages = set()
        self.farms = {}

    def _mock_get_session(self, phone, db_url=None):
        return self.sessions.get(phone)

    def _mock_save_session(self, phone, state, name=None, crop=None, acreage_acres=None,
                           preferred_language=None, pending_lat=None, pending_lon=None, db_url=None, **kwargs):
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
        if pending_lat is not None:
            sess["pending_lat"] = pending_lat
        if pending_lon is not None:
            sess["pending_lon"] = pending_lon
        self.sessions[phone] = sess

    def _mock_clear_session(self, phone, db_url=None):
        self.sessions.pop(phone, None)

    def _mock_claim_message(self, msg_id, db_url=None):
        if not msg_id:
            return True
        if msg_id in self.processed_messages:
            return False
        self.processed_messages.add(msg_id)
        return True

    def _mock_unclaim_message(self, msg_id, db_url=None):
        self.processed_messages.discard(msg_id)

    def _mock_get_farm(self, phone, db_url=None):
        return self.farms.get(phone)

    # --------------------------------------------------------------------------
    # 1. Text Sanitization & Cleaning for Speech
    # --------------------------------------------------------------------------

    def test_clean_text_for_speech_emojis_and_markdown(self):
        """Verifies emojis, asterisks, underscores, and tildes are cleanly stripped from spoken text."""
        raw_text = "Welcome to *KhetSense AI*! 🌱🌾\n_Please_ select your language:\n1. ~English~\n2. मराठी"
        cleaned = clean_text_for_speech(raw_text, lang="en")
        self.assertNotIn("🌱", cleaned)
        self.assertNotIn("🌾", cleaned)
        self.assertNotIn("*", cleaned)
        self.assertNotIn("_", cleaned)
        self.assertNotIn("~", cleaned)
        self.assertIn("Welcome to KhetSense AI", cleaned)
        self.assertIn("Please select your language", cleaned)
        self.assertIn("English", cleaned)
        self.assertIn("मराठी", cleaned)

    def test_clean_text_for_speech_google_maps_url_replacement(self):
        """Verifies raw Google Maps URLs are replaced with natural localized spoken phrases."""
        # English
        en_raw = "Your farm location: https://maps.google.com/?q=20.5026,77.1419. Please confirm."
        en_clean = clean_text_for_speech(en_raw, lang="en")
        self.assertNotIn("https://", en_clean)
        self.assertIn("on the map location", en_clean)

        # Marathi
        mr_raw = "तुमच्या शेताचे स्थान: https://www.google.com/maps/place/20.5026,77.1419. कृपया खात्री करा."
        mr_clean = clean_text_for_speech(mr_raw, lang="mr")
        self.assertNotIn("https://", mr_clean)
        self.assertIn("नकाशावरील जागेवर", mr_clean)

        # Hindi
        hi_raw = "आपके खेत का स्थान: https://maps.google.com/?q=20.5026,77.1419. कृपया पुष्टि करें।"
        hi_clean = clean_text_for_speech(hi_raw, lang="hi")
        self.assertNotIn("https://", hi_clean)
        self.assertIn("नक्शे वाले स्थान पर", hi_clean)

    def test_clean_text_for_speech_preserves_numbers_and_names(self):
        """Verifies numbers, farmer names, crop names, and farm IDs are preserved."""
        text = "Farm ID #42 with 2.5 acres registered for Ramesh Patil (Cotton crop)."
        cleaned = clean_text_for_speech(text, lang="en")
        self.assertIn("42", cleaned)
        self.assertIn("2.5", cleaned)
        self.assertIn("Ramesh Patil", cleaned)
        self.assertIn("Cotton", cleaned)

    # --------------------------------------------------------------------------
    # 2. Trilingual Welcome Script Formatting
    # --------------------------------------------------------------------------

    def test_format_trilingual_welcome_script(self):
        """Verifies trilingual welcome script produces valid ordered segments for EN, MR, and HI."""
        segments = format_trilingual_welcome_script()
        self.assertEqual(len(segments), 3)
        languages = [lang for _, lang in segments]
        self.assertEqual(languages, ["en", "mr", "hi"])

        for script, lang in segments:
            self.assertTrue(len(script.strip()) > 10)
            self.assertNotIn("🌱", script)
            self.assertNotIn("*", script)

    # --------------------------------------------------------------------------
    # 3. Multilingual Speech Synthesis
    # --------------------------------------------------------------------------

    def test_synthesize_multilingual_mock_provider(self):
        """Verifies MockTTSProvider synthesizes multilingual segments successfully."""
        segments = format_trilingual_welcome_script()
        res = self.mock_tts.synthesize_multilingual(segments=segments, audio_format="mp3")
        self.assertIsInstance(res, TTSResult)
        self.assertEqual(res.mime_type, MIME_MP3)
        self.assertTrue(len(res.audio_bytes) > 0)
        self.assertEqual(res.language, "multilingual")
        self.assertTrue(res.cleanup())

    def test_synthesize_multilingual_edge_tts_provider_sequential(self):
        """Verifies EdgeTTSProvider synthesizes each language segment with its native voice."""
        segments = [
            ("Welcome to KhetSense", "en"),
            ("खेतसेन्स मध्ये आपले स्वागत आहे", "mr"),
            ("खेतसेंस में आपका स्वागत है", "hi"),
        ]
        provider = EdgeTTSProvider()

        mock_edge = MagicMock()
        recorded_voices = []

        def make_comm(text, voice):
            recorded_voices.append(voice)
            comm = MagicMock()
            async def _fake_save(p):
                # Write a simulated valid MPEG frame
                with open(p, "wb") as f:
                    f.write(b"\xff\xf3d\xc4" + b"\x00" * 284)
            comm.save = _fake_save
            return comm

        mock_edge.Communicate.side_effect = make_comm

        with patch.dict(sys.modules, {"edge_tts": mock_edge}):
            res = provider.synthesize_multilingual(segments=segments, audio_format="mp3")
            self.assertIsInstance(res, TTSResult)
            self.assertEqual(res.mime_type, MIME_MP3)
            self.assertEqual(recorded_voices, [
                "en-IN-NeerjaNeural",
                "mr-IN-AarohiNeural",
                "hi-IN-SwaraNeural",
            ])
            self.assertTrue(res.cleanup())

    # --------------------------------------------------------------------------
    # 4. Omnichannel Dispatcher (send_farmer_response)
    # --------------------------------------------------------------------------

    def test_send_farmer_response_text_first_ordering(self):
        """Verifies that text message is sent first before audio message."""
        call_sequence = []

        def mock_text(to, body):
            call_sequence.append(("text", to, body))
            return True

        def mock_voice(to, audio):
            call_sequence.append(("voice", to, audio))
            return True

        res = send_farmer_response(
            to="919876543210",
            text="Hello Farmer Ramesh",
            lang="en",
            outbound_sender=mock_text,
            outbound_voice_sender=mock_voice,
            enable_voice=True,
            tts_provider=self.mock_tts,
        )

        self.assertEqual(res["status"], "success")
        self.assertTrue(res["text_sent"])
        self.assertTrue(res["voice_sent"])
        self.assertFalse(res["can_retry_audio"])
        self.assertEqual(len(call_sequence), 2)
        self.assertEqual(call_sequence[0][0], "text")
        self.assertEqual(call_sequence[1][0], "voice")

    def test_send_farmer_response_voice_failure_does_not_block_text(self):
        """Verifies that voice synthesis or upload errors NEVER fail or retract text delivery."""
        def mock_failing_voice(to, audio):
            raise RuntimeError("WhatsApp Cloud API timeout")

        res = send_farmer_response(
            to="919876543210",
            text="Your farm is registered",
            lang="en",
            outbound_sender=self.mock_text_sender,
            outbound_voice_sender=mock_failing_voice,
            enable_voice=True,
            tts_provider=self.mock_tts,
        )

        self.assertEqual(res["status"], "success")
        self.assertTrue(res["text_sent"])
        self.assertFalse(res["voice_sent"])
        self.assertTrue(res["can_retry_audio"])
        self.mock_text_sender.assert_called_once_with("919876543210", "Your farm is registered")

    def test_send_farmer_response_text_failure_prevents_voice(self):
        """When text delivery fails, voice delivery is aborted immediately."""
        mock_failing_text = MagicMock(return_value=False)

        res = send_farmer_response(
            to="919876543210",
            text="Test message",
            lang="en",
            outbound_sender=mock_failing_text,
            outbound_voice_sender=self.mock_voice_sender,
            enable_voice=True,
            tts_provider=self.mock_tts,
        )

        self.assertEqual(res["status"], "failed")
        self.assertFalse(res["text_sent"])
        self.assertFalse(res["voice_sent"])
        self.mock_voice_sender.assert_not_called()

    def test_retry_audio_delivery_no_duplicate_text(self):
        """Verifies retry_audio_delivery delivers audio without re-sending duplicate text."""
        res = retry_audio_delivery(
            to="919876543210",
            text="Your advisory update",
            lang="en",
            outbound_voice_sender=self.mock_voice_sender,
            tts_provider=self.mock_tts,
        )

        self.assertEqual(res["status"], "success")
        self.assertTrue(res["text_sent"])
        self.assertTrue(res["voice_sent"])
        self.mock_text_sender.assert_not_called()  # Confirmed: no duplicate text sent!
        self.mock_voice_sender.assert_called_once()

    def test_send_farmer_response_voice_disabled_by_default(self):
        """Verifies that voice is skipped when enable_voice is False or unset."""
        with patch.dict(os.environ, {"ENABLE_VOICE_CHATBOT": "false"}):
            res = send_farmer_response(
                to="919876543210",
                text="Plain text update",
                lang="en",
                outbound_sender=self.mock_text_sender,
                outbound_voice_sender=self.mock_voice_sender,
                enable_voice=None,
            )
            self.assertEqual(res["status"], "success")
            self.assertTrue(res["text_sent"])
            self.assertFalse(res["voice_sent"])
            self.assertEqual(res.get("reason"), "voice_disabled")
            self.mock_voice_sender.assert_not_called()

    # --------------------------------------------------------------------------
    # 5. Full WhatsApp Conversational Turns (handle_incoming)
    # --------------------------------------------------------------------------

    @patch("whatsapp.registration_flow.get_registered_farm")
    @patch("whatsapp.registration_flow.get_session")
    @patch("whatsapp.registration_flow.save_session")
    @patch("whatsapp.registration_flow.clear_session")
    @patch("whatsapp.registration_flow.claim_message")
    @patch("whatsapp.registration_flow.unclaim_message")
    def test_handle_incoming_first_contact_sends_text_and_trilingual_audio(
        self,
        mock_unclaim_msg,
        mock_claim_msg,
        mock_clear_sess,
        mock_save_sess,
        mock_get_sess,
        mock_get_farm,
    ):
        """First contact sends welcome text and trilingual voice note."""
        mock_get_farm.side_effect = self._mock_get_farm
        mock_get_sess.side_effect = self._mock_get_session
        mock_save_sess.side_effect = self._mock_save_session
        mock_clear_sess.side_effect = self._mock_clear_session
        mock_claim_msg.side_effect = self._mock_claim_message
        mock_unclaim_msg.side_effect = self._mock_unclaim_message

        phone = "919876543210"
        msg = {"id": "wamid.v1", "from": phone, "type": "text", "text": {"body": "Hi"}}

        res = handle_incoming(
            msg,
            outbound_sender=self.mock_text_sender,
            outbound_voice_sender=self.mock_voice_sender,
            enable_voice=True,
            tts_provider=self.mock_tts,
        )

        self.assertEqual(res["status"], "session_started")
        self.assertEqual(res["next_state"], "AWAITING_LANGUAGE")
        self.mock_text_sender.assert_called_once_with(phone, get_message("welcome_and_language", lang="en"))
        self.mock_voice_sender.assert_called_once()

    @patch("whatsapp.registration_flow.get_registered_farm")
    @patch("whatsapp.registration_flow.get_session")
    @patch("whatsapp.registration_flow.save_session")
    @patch("whatsapp.registration_flow.clear_session")
    @patch("whatsapp.registration_flow.claim_message")
    @patch("whatsapp.registration_flow.unclaim_message")
    def test_handle_incoming_marathi_registration_conversational_turns(
        self,
        mock_unclaim_msg,
        mock_claim_msg,
        mock_clear_sess,
        mock_save_sess,
        mock_get_sess,
        mock_get_farm,
    ):
        """Conversational turns in Marathi send Marathi text and Marathi voice notes."""
        mock_get_farm.side_effect = self._mock_get_farm
        mock_get_sess.side_effect = self._mock_get_session
        mock_save_sess.side_effect = self._mock_save_session
        mock_clear_sess.side_effect = self._mock_clear_session
        mock_claim_msg.side_effect = self._mock_claim_message
        mock_unclaim_msg.side_effect = self._mock_unclaim_message

        phone = "919876543210"

        # Turn 1: Select Marathi (Option 2)
        self.sessions[phone] = {"phone": phone, "state": "AWAITING_LANGUAGE", "preferred_language": "en"}
        msg_lang = {"id": "wamid.mr.1", "from": phone, "type": "text", "text": {"body": "2"}}

        res1 = handle_incoming(
            msg_lang,
            outbound_sender=self.mock_text_sender,
            outbound_voice_sender=self.mock_voice_sender,
            enable_voice=True,
            tts_provider=self.mock_tts,
        )

        self.assertEqual(res1["status"], "language_selected")
        self.assertEqual(res1["language"], "mr")
        self.assertEqual(res1["next_state"], "AWAITING_NAME")
        self.mock_text_sender.assert_called_with(phone, get_message("language_confirmed", lang="mr"))
        self.assertEqual(self.mock_voice_sender.call_count, 1)

        # Turn 2: Provide Farmer Name -> Prompts for Confirmation in Marathi
        msg_name = {"id": "wamid.mr.2", "from": phone, "type": "text", "text": {"body": "तुकाराम शिंदे"}}
        res2 = handle_incoming(
            msg_name,
            outbound_sender=self.mock_text_sender,
            outbound_voice_sender=self.mock_voice_sender,
            enable_voice=True,
            tts_provider=self.mock_tts,
        )

        self.assertEqual(res2["status"], "name_candidate_received")
        self.assertEqual(res2["next_state"], "AWAITING_NAME_CONFIRMATION")
        self.mock_text_sender.assert_called_with(phone, get_message("name_confirm", lang="mr", name="तुकाराम शिंदे"))
        self.assertEqual(self.mock_voice_sender.call_count, 2)

        # Turn 3: Farmer confirms name -> Prompts for Crop in Marathi
        msg_confirm = {"id": "wamid.mr.3", "from": phone, "type": "text", "text": {"body": "होय"}}
        res3 = handle_incoming(
            msg_confirm,
            outbound_sender=self.mock_text_sender,
            outbound_voice_sender=self.mock_voice_sender,
            enable_voice=True,
            tts_provider=self.mock_tts,
        )

        self.assertEqual(res3["status"], "name_confirmed")
        self.assertEqual(res3["next_state"], "AWAITING_CROP")
        self.mock_text_sender.assert_called_with(phone, get_message("crop_prompt", lang="mr", name="तुकाराम शिंदे"))
        self.assertEqual(self.mock_voice_sender.call_count, 3)

    @patch("whatsapp.registration_flow.get_registered_farm")
    @patch("whatsapp.registration_flow.get_session")
    @patch("whatsapp.registration_flow.save_session")
    @patch("whatsapp.registration_flow.clear_session")
    @patch("whatsapp.registration_flow.claim_message")
    @patch("whatsapp.registration_flow.unclaim_message")
    def test_handle_incoming_hindi_registration_conversational_turns(
        self,
        mock_unclaim_msg,
        mock_claim_msg,
        mock_clear_sess,
        mock_save_sess,
        mock_get_sess,
        mock_get_farm,
    ):
        """Conversational turns in Hindi send Hindi text and Hindi voice notes."""
        mock_get_farm.side_effect = self._mock_get_farm
        mock_get_sess.side_effect = self._mock_get_session
        mock_save_sess.side_effect = self._mock_save_session
        mock_clear_sess.side_effect = self._mock_clear_session
        mock_claim_msg.side_effect = self._mock_claim_message
        mock_unclaim_msg.side_effect = self._mock_unclaim_message

        phone = "919876543211"

        # Turn 1: Select Hindi (Option 3)
        self.sessions[phone] = {"phone": phone, "state": "AWAITING_LANGUAGE", "preferred_language": "en"}
        msg_lang = {"id": "wamid.hi.1", "from": phone, "type": "text", "text": {"body": "3"}}

        res1 = handle_incoming(
            msg_lang,
            outbound_sender=self.mock_text_sender,
            outbound_voice_sender=self.mock_voice_sender,
            enable_voice=True,
            tts_provider=self.mock_tts,
        )

        self.assertEqual(res1["status"], "language_selected")
        self.assertEqual(res1["language"], "hi")
        self.assertEqual(res1["next_state"], "AWAITING_NAME")
        self.mock_text_sender.assert_called_with(phone, get_message("language_confirmed", lang="hi"))
        self.assertEqual(self.mock_voice_sender.call_count, 1)

        # Turn 2: Provide Farmer Name -> Prompts for Confirmation in Hindi
        msg_name = {"id": "wamid.hi.2", "from": phone, "type": "text", "text": {"body": "रमेश पाटिल"}}
        res2 = handle_incoming(
            msg_name,
            outbound_sender=self.mock_text_sender,
            outbound_voice_sender=self.mock_voice_sender,
            enable_voice=True,
            tts_provider=self.mock_tts,
        )

        self.assertEqual(res2["status"], "name_candidate_received")
        self.assertEqual(res2["next_state"], "AWAITING_NAME_CONFIRMATION")
        self.mock_text_sender.assert_called_with(phone, get_message("name_confirm", lang="hi", name="रमेश पाटिल"))
        self.assertEqual(self.mock_voice_sender.call_count, 2)

        # Turn 3: Farmer confirms name -> Prompts for Crop in Hindi
        msg_confirm = {"id": "wamid.hi.3", "from": phone, "type": "text", "text": {"body": "हाँ"}}
        res3 = handle_incoming(
            msg_confirm,
            outbound_sender=self.mock_text_sender,
            outbound_voice_sender=self.mock_voice_sender,
            enable_voice=True,
            tts_provider=self.mock_tts,
        )

        self.assertEqual(res3["status"], "name_confirmed")
        self.assertEqual(res3["next_state"], "AWAITING_CROP")
        self.mock_text_sender.assert_called_with(phone, get_message("crop_prompt", lang="hi", name="रमेश पाटिल"))
        self.assertEqual(self.mock_voice_sender.call_count, 3)

    @patch("whatsapp.registration_flow.get_registered_farm")
    @patch("whatsapp.registration_flow.get_session")
    @patch("whatsapp.registration_flow.save_session")
    @patch("whatsapp.registration_flow.clear_session")
    @patch("whatsapp.registration_flow.claim_message")
    @patch("whatsapp.registration_flow.unclaim_message")
    @patch("whatsapp.registration_flow.get_latest_advisory")
    def test_handle_incoming_status_command_delivers_text_and_voice_advisory(
        self,
        mock_get_advisory,
        mock_unclaim_msg,
        mock_claim_msg,
        mock_clear_sess,
        mock_save_sess,
        mock_get_sess,
        mock_get_farm,
    ):
        """When registered farmer requests STATUS, delivers advisory card text AND voice advisory script."""
        mock_get_sess.return_value = None
        mock_claim_msg.return_value = True
        mock_unclaim_msg.return_value = None

        phone = "919876543299"
        mock_get_farm.return_value = {
            "id": 99,
            "farmer_name": "Suresh",
            "mobile_number": phone,
            "preferred_language": "mr",
            "crop_name": "Cotton",
        }
        mock_get_advisory.return_value = {
            "id": 501,
            "farm_id": 99,
            "crop_stage": "Mid-Season",
            "stress_level": "MODERATE",
            "observed_stress": "MODERATE",
            "recommendation": "Irrigate lightly",
            "recommended_action": "irrigate lightly, rain may not suffice",
            "ndvi": 0.45,
            "soil_moisture": 0.18,
            "rainfall_48h": 6.5,
            "rain_forecast_mm": 6.5,
            "sentinel_scene_date": "2026-03-30",
            "smap_obs_date": "2026-03-30",
            "validation_status": "VALIDATED_AGRICULTURE",
        }

        msg = {"id": "wamid.status.1", "from": phone, "type": "text", "text": {"body": "STATUS"}}

        res = handle_incoming(
            msg,
            outbound_sender=self.mock_text_sender,
            outbound_voice_sender=self.mock_voice_sender,
            enable_voice=True,
            tts_provider=self.mock_tts,
        )

        self.assertEqual(res["status"], "advisory_sent")
        self.assertEqual(res["farm_id"], 99)
        self.assertEqual(res["language"], "mr")
        self.mock_text_sender.assert_called_once()
        self.mock_voice_sender.assert_called_once()

    def test_send_farmer_response_retry_payload_exposed_on_voice_failure(self):
        """Verifies retry_payload contains all metadata necessary for audio retry without re-sending text."""
        def mock_fail_voice(to, audio):
            raise RuntimeError("WhatsApp API 503")

        res = send_farmer_response(
            to="919876543210",
            text="Your farm is registered",
            lang="en",
            outbound_sender=self.mock_text_sender,
            outbound_voice_sender=mock_fail_voice,
            enable_voice=True,
            tts_provider=self.mock_tts,
        )

        self.assertEqual(res["status"], "success")
        self.assertTrue(res["text_sent"])
        self.assertFalse(res["voice_sent"])
        self.assertTrue(res["can_retry_audio"])
        self.assertIsNotNone(res["retry_payload"])
        self.assertEqual(res["retry_payload"]["to"], "919876543210")
        self.assertEqual(res["retry_payload"]["text"], "Your farm is registered")
        self.assertEqual(res["retry_payload"]["lang"], "en")
        self.assertIn("farm is registered", res["retry_payload"]["voice_script"])

        # Now test that retry_audio_delivery consumes this without duplicate text
        self.mock_text_sender.reset_mock()
        retry_res = retry_audio_delivery(
            to=res["retry_payload"]["to"],
            text=res["retry_payload"]["text"],
            lang=res["retry_payload"]["lang"],
            voice_script=res["retry_payload"]["voice_script"],
            outbound_voice_sender=self.mock_voice_sender,
            tts_provider=self.mock_tts,
        )
        self.mock_text_sender.assert_not_called()  # No duplicate text!
        self.mock_voice_sender.assert_called_once()  # Audio delivered!
        self.assertTrue(retry_res["voice_sent"])


if __name__ == "__main__":
    unittest.main()

