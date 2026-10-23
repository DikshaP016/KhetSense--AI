#!/usr/bin/env python3
"""
KhetSense AI — Phase 6H: WhatsApp Security & Safe Test-Mode Remediation Test Suite
==================================================================================
Tests and verifies all five security remediations specified in Phase 6H:
1. Meta Webhook Signature Verification (X-Hub-Signature-256 HMAC-SHA256, constant-time compare, fail-closed).
2. Outbound WhatsApp Message Kill Switch (ENABLE_OUTBOUND_WHATSAPP=false by default).
3. Decoupled Farmer Registration vs Advisory Dispatch (AUTO_DISPATCH_ADVISORY_ON_REGISTRATION=false by default).
4. Sender Allowlisting (WHATSAPP_ALLOWLIST_ENABLED, normalized matching, deny-by-default).
5. In-Memory & Atomic Duplicate Event Handling (claim_message, offline resilience).
"""

import os
import sys
import json
import hmac
import hashlib
import asyncio
import logging
import unittest
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

from fastapi import BackgroundTasks, HTTPException
from webhook_server import app, receive_whatsapp_event
from common.config import (
    verify_meta_signature,
    is_outbound_whatsapp_enabled,
    is_auto_advisory_on_registration_enabled,
    is_whatsapp_allowlist_enabled,
    get_allowed_sender_numbers,
    is_sender_allowed,
)
from common.utils import mask_phone, normalize_phone
from whatsapp.registration_flow import (
    handle_incoming,
    claim_message,
    unclaim_message,
    is_message_processed,
    send_text,
    send_whatsapp_message,
    upload_whatsapp_media,
    send_whatsapp_audio,
    trigger_pipeline_for_farm,
    _IN_MEMORY_PROCESSED_MESSAGES,
)


class MockFastAPIRequest:
    """Simulates an incoming HTTP Request for FastAPI endpoint testing."""
    def __init__(self, json_data=None, headers=None, raw_body=None, app_secret=None, chunk_size=None):
        self._data = json_data
        self._raw_body = raw_body if raw_body is not None else (json.dumps(json_data).encode("utf-8") if json_data is not None else b"")
        self.headers = dict(headers or {})
        self.chunk_size = chunk_size

        if "X-Hub-Signature-256" not in self.headers and app_secret:
            sig = hmac.new(app_secret.encode("utf-8"), self._raw_body, hashlib.sha256).hexdigest()
            self.headers["X-Hub-Signature-256"] = f"sha256={sig}"

    async def json(self):
        return self._data

    async def body(self):
        return self._raw_body

    async def stream(self):
        if self.chunk_size:
            for i in range(0, len(self._raw_body), self.chunk_size):
                yield self._raw_body[i:i + self.chunk_size]
        else:
            yield self._raw_body



# ==============================================================================
# 1. META WEBHOOK SIGNATURE VERIFICATION TESTS
# ==============================================================================
class TestMetaWebhookSignatureVerification(unittest.TestCase):
    """Audits X-Hub-Signature-256 HMAC-SHA256 verification and fail-closed security."""

    def setUp(self):
        self.secret = "test_meta_app_secret_phase6h_98765"
        self.body_bytes = b'{"object":"whatsapp_business_account","entry":[]}'
        self.valid_hex = hmac.new(self.secret.encode("utf-8"), self.body_bytes, hashlib.sha256).hexdigest()
        self.valid_header = f"sha256={self.valid_hex}"

    def test_01_valid_signature_accepted(self):
        """Valid HMAC-SHA256 signature against raw body passes verification."""
        valid, reason = verify_meta_signature(self.body_bytes, self.valid_header, app_secret=self.secret)
        self.assertTrue(valid)
        self.assertEqual(reason, "Signature verified")

    def test_02_tampered_body_rejected(self):
        """Tampered payload fails verification with HMAC mismatch."""
        tampered_body = b'{"object":"whatsapp_business_account","entry":[{"tampered":true}]}'
        valid, reason = verify_meta_signature(tampered_body, self.valid_header, app_secret=self.secret)
        self.assertFalse(valid)
        self.assertIn("mismatch", reason.lower())

    def test_03_missing_signature_header_rejected(self):
        """Missing X-Hub-Signature-256 header fails closed."""
        valid, reason = verify_meta_signature(self.body_bytes, None, app_secret=self.secret)
        self.assertFalse(valid)
        self.assertIn("Missing", reason)

        valid2, reason2 = verify_meta_signature(self.body_bytes, "", app_secret=self.secret)
        self.assertFalse(valid2)
        self.assertIn("Missing", reason2)

    def test_04_malformed_signature_header_rejected(self):
        """Header without 'sha256=' prefix or empty digest fails closed."""
        # Missing prefix
        valid, reason = verify_meta_signature(self.body_bytes, self.valid_hex, app_secret=self.secret)
        self.assertFalse(valid)
        self.assertIn("Malformed", reason)

        # Empty hex digest
        valid2, reason2 = verify_meta_signature(self.body_bytes, "sha256=", app_secret=self.secret)
        self.assertFalse(valid2)
        self.assertIn("Empty", reason2)

    def test_05_missing_secret_fails_closed(self):
        """If META_APP_SECRET is unconfigured or empty, verification fails closed."""
        with patch.dict(os.environ, {"META_APP_SECRET": ""}):
            valid, reason = verify_meta_signature(self.body_bytes, self.valid_header, app_secret=None)
            self.assertFalse(valid)
            self.assertIn("failing closed", reason)

    def test_06_webhook_server_post_endpoint_enforces_signature(self):
        """FastAPI POST /webhook raises HTTP 403 on invalid signature and 200 on valid signature."""
        bg = BackgroundTasks()
        payload = {"object": "whatsapp_business_account", "entry": []}

        # 1. Invalid signature -> HTTP 403
        bad_req = MockFastAPIRequest(payload, headers={"X-Hub-Signature-256": "sha256=invalidhex000"})
        with patch.dict(os.environ, {"META_APP_SECRET": self.secret}):
            with self.assertRaises(HTTPException) as cm:
                asyncio.run(receive_whatsapp_event(bad_req, bg))
            self.assertEqual(cm.exception.status_code, 403)

        # 2. Valid signature -> HTTP 200
        good_req = MockFastAPIRequest(payload, app_secret=self.secret)
        with patch.dict(os.environ, {"META_APP_SECRET": self.secret}):
            resp = asyncio.run(receive_whatsapp_event(good_req, bg))
            self.assertEqual(resp.status_code, 200)

    def test_07_secret_not_exposed_in_error_or_logs(self):
        """Ensures the secret string is never leaked into return reasons or error logs."""
        valid, reason = verify_meta_signature(self.body_bytes, "sha256=wrong", app_secret=self.secret)
        self.assertNotIn(self.secret, reason)


# ==============================================================================
# 2. OUTBOUND MESSAGING KILL-SWITCH TESTS
# ==============================================================================
class TestOutboundMessagingKillSwitch(unittest.TestCase):
    """Verifies that outbound messaging defaults to disabled and suppresses all network requests."""

    def test_01_disabled_by_default(self):
        """ENABLE_OUTBOUND_WHATSAPP defaults to False when unset or empty."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ENABLE_OUTBOUND_WHATSAPP", None)
            self.assertFalse(is_outbound_whatsapp_enabled())

    def test_02_enabled_only_when_explicitly_true(self):
        """ENABLE_OUTBOUND_WHATSAPP is True only when set to case-insensitive 'true'."""
        with patch.dict(os.environ, {"ENABLE_OUTBOUND_WHATSAPP": "true"}):
            self.assertTrue(is_outbound_whatsapp_enabled())
        with patch.dict(os.environ, {"ENABLE_OUTBOUND_WHATSAPP": "TRUE"}):
            self.assertTrue(is_outbound_whatsapp_enabled())
        with patch.dict(os.environ, {"ENABLE_OUTBOUND_WHATSAPP": "false"}):
            self.assertFalse(is_outbound_whatsapp_enabled())
        with patch.dict(os.environ, {"ENABLE_OUTBOUND_WHATSAPP": "0"}):
            self.assertFalse(is_outbound_whatsapp_enabled())

    def test_03_send_whatsapp_message_suppressed_when_disabled(self):
        """send_whatsapp_message returns False and never invokes requests.post when disabled."""
        with patch.dict(os.environ, {"ENABLE_OUTBOUND_WHATSAPP": "false", "WHATSAPP_TOKEN": "valid_token"}):
            with patch("requests.post") as mock_post:
                res = send_whatsapp_message("919876543210", "Test notification")
                self.assertFalse(res)
                mock_post.assert_not_called()

    def test_04_upload_whatsapp_media_suppressed_when_disabled(self):
        """upload_whatsapp_media returns mock ID and never invokes requests.post when disabled."""
        with patch.dict(os.environ, {"ENABLE_OUTBOUND_WHATSAPP": "false", "WHATSAPP_TOKEN": "valid_token"}):
            with patch("requests.post") as mock_post:
                media_id = upload_whatsapp_media(b"fake_mp3_audio_bytes")
                self.assertEqual(media_id, "mock_media_id_audio_12345")
                mock_post.assert_not_called()

    def test_05_send_whatsapp_audio_suppressed_when_disabled(self):
        """send_whatsapp_audio returns True (simulated success) without requests.post when disabled."""
        with patch.dict(os.environ, {"ENABLE_OUTBOUND_WHATSAPP": "false", "WHATSAPP_TOKEN": "valid_token"}):
            with patch("requests.post") as mock_post:
                res = send_whatsapp_audio("919876543210", "mock_media_id_123")
                self.assertTrue(res)
                mock_post.assert_not_called()


# ==============================================================================
# 3. DECOUPLED REGISTRATION VS ADVISORY TESTS
# ==============================================================================
class TestDecoupledRegistrationAndAdvisory(unittest.TestCase):
    """Verifies that completing farmer registration does not automatically dispatch advisories."""

    def setUp(self):
        _IN_MEMORY_PROCESSED_MESSAGES.clear()

    def test_01_auto_advisory_on_registration_disabled_by_default(self):
        """AUTO_DISPATCH_ADVISORY_ON_REGISTRATION defaults to False."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AUTO_DISPATCH_ADVISORY_ON_REGISTRATION", None)
            self.assertFalse(is_auto_advisory_on_registration_enabled())

    @patch("whatsapp.registration_flow.get_registered_farm")
    @patch("whatsapp.registration_flow.get_session")
    @patch("whatsapp.registration_flow.save_session")
    @patch("whatsapp.registration_flow.register_farmer_from_pin")
    def test_02_registration_completes_with_advisory_decoupled(
        self, mock_reg_pin, mock_save_session, mock_get_session, mock_get_reg_farm
    ):
        """Location confirmation completes registration with advisory_dispatched=False by default."""
        mock_get_reg_farm.return_value = None
        mock_get_session.return_value = {
            "state": "AWAITING_LOCATION_CONFIRMATION",
            "name": "Ramesh Patil",
            "crop": "Cotton",
            "acreage_acres": 2.5,
            "preferred_language": "en",
            "pending_lat": 20.5026,
            "pending_lon": 77.1419,
        }
        mock_reg_pin.return_value = {
            "success": True,
            "farm_id": 101,
            "farmer_name": "Ramesh Patil",
            "crop_name": "Cotton",
            "farm_area": 2.5,
            "boundary_source": "estimated_from_pin",
        }

        mock_outbound = MagicMock(return_value=True)
        mock_pipeline_runner = MagicMock()

        msg = {"id": "wamid.phase6h.reg.001", "from": "919876543210", "type": "text", "text": {"body": "yes"}}

        with patch.dict(os.environ, {"AUTO_DISPATCH_ADVISORY_ON_REGISTRATION": "false"}):
            res = handle_incoming(
                msg,
                outbound_sender=mock_outbound,
                pipeline_runner=mock_pipeline_runner,
            )

        self.assertEqual(res["status"], "registration_complete")
        self.assertEqual(res["farm_id"], 101)
        self.assertFalse(res.get("advisory_dispatched"))

        # Verify confirmation message was sent to farmer
        mock_outbound.assert_called_once()
        sent_body = mock_outbound.call_args[0][1]
        self.assertIn("Ramesh Patil", sent_body)
        self.assertIn("101", sent_body)

    @patch("whatsapp.registration_flow.get_registered_farm")
    @patch("whatsapp.registration_flow.get_session")
    @patch("whatsapp.registration_flow.get_latest_advisory")
    def test_03_farmer_pull_advisory_via_status_command_succeeds(
        self, mock_get_latest_adv, mock_get_session, mock_get_reg_farm
    ):
        """A registered farmer texting 'status' explicitly retrieves their latest advisory."""
        mock_get_session.return_value = {"state": "REGISTERED", "preferred_language": "en"}
        mock_get_reg_farm.return_value = {
            "id": 101,
            "farmer_name": "Ramesh Patil",
            "crop_name": "Cotton",
            "preferred_language": "en",
        }
        mock_get_latest_adv.return_value = {
            "id": 5001,
            "farm_id": 101,
            "stress_level": "Mild Stress",
            "recommendation": "Irrigate lightly, rain may not suffice",
            "ndvi": 0.45,
            "soil_moisture": 32.0,
            "rainfall_48h": 2.0,
            "observed_stress": "Mild Stress",
            "rain_forecast_mm": 2.0,
            "guardrail_triggered": False,
        }

        mock_outbound = MagicMock(return_value=True)
        msg = {"id": "wamid.phase6h.status.001", "from": "919876543210", "type": "text", "text": {"body": "status"}}

        res = handle_incoming(msg, outbound_sender=mock_outbound)
        self.assertEqual(res["status"], "advisory_sent")
        self.assertEqual(res["advisory_id"], 5001)
        mock_outbound.assert_called_once()
        self.assertIn("Mild Stress", mock_outbound.call_args[0][1])


# ==============================================================================
# 4. SENDER ALLOWLISTING TESTS
# ==============================================================================
class TestSenderAllowlisting(unittest.TestCase):
    """Verifies recipient phone number allowlist enforcement and normalization."""

    def test_01_allowlist_disabled_by_default(self):
        """WHATSAPP_ALLOWLIST_ENABLED defaults to False."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("WHATSAPP_ALLOWLIST_ENABLED", None)
            self.assertFalse(is_whatsapp_allowlist_enabled())

    def test_02_all_senders_permitted_when_allowlist_disabled(self):
        """When allowlist is disabled, any valid phone number is permitted."""
        with patch.dict(os.environ, {"WHATSAPP_ALLOWLIST_ENABLED": "false"}):
            self.assertTrue(is_sender_allowed("919876543210"))
            self.assertTrue(is_sender_allowed("9876543210"))
            self.assertTrue(is_sender_allowed("+91 98765 43210"))

    def test_03_allowlist_normalization_handles_various_formats(self):
        """Allows 10-digit Indian numbers, leading zeros, and Country Code prefixes."""
        with patch.dict(os.environ, {
            "WHATSAPP_ALLOWLIST_ENABLED": "true",
            "WHATSAPP_ALLOWED_NUMBERS": "9876543210, 09123456789, 919999999999",
        }):
            allowed = get_allowed_sender_numbers()
            self.assertIn("919876543210", allowed)
            self.assertIn("919123456789", allowed)
            self.assertIn("919999999999", allowed)

            # Test phone matches
            self.assertTrue(is_sender_allowed("9876543210"))
            self.assertTrue(is_sender_allowed("919876543210"))
            self.assertTrue(is_sender_allowed("+91-9876543210"))
            self.assertTrue(is_sender_allowed("09123456789"))
            self.assertTrue(is_sender_allowed("9123456789"))

    def test_04_unauthorized_number_rejected_when_allowlist_enabled(self):
        """When allowlist is enabled, non-allowlisted senders are denied."""
        with patch.dict(os.environ, {
            "WHATSAPP_ALLOWLIST_ENABLED": "true",
            "WHATSAPP_ALLOWED_NUMBERS": "919876543210",
        }):
            self.assertTrue(is_sender_allowed("919876543210"))
            self.assertFalse(is_sender_allowed("919000000000"))
            self.assertFalse(is_sender_allowed("919111111111"))

    def test_05_handle_incoming_rejects_non_allowlisted_sender(self):
        """handle_incoming discards messages from non-allowlisted senders."""
        with patch.dict(os.environ, {
            "WHATSAPP_ALLOWLIST_ENABLED": "true",
            "WHATSAPP_ALLOWED_NUMBERS": "919876543210",
        }):
            msg = {"id": "wamid.unauth.001", "from": "919000000000", "type": "text", "text": {"body": "hello"}}
            res = handle_incoming(msg)
            self.assertEqual(res["status"], "rejected")
            self.assertEqual(res["reason"], "sender_not_allowlisted")

    def test_06_unparseable_or_empty_phone_rejected(self):
        """Empty, None, or non-numeric phone values are rejected."""
        self.assertFalse(is_sender_allowed(None))
        self.assertFalse(is_sender_allowed(""))
        self.assertFalse(is_sender_allowed("   "))
        self.assertFalse(is_sender_allowed("not_a_phone"))


# ==============================================================================
# 5. DUPLICATE WEBHOOK EVENT HANDLING TESTS
# ==============================================================================
class TestDuplicateWebhookEvents(unittest.TestCase):
    """Verifies atomic claiming, in-memory fallback, and duplicate suppression."""

    def setUp(self):
        _IN_MEMORY_PROCESSED_MESSAGES.clear()

    def test_01_atomic_claim_and_duplicate_rejection(self):
        """First claim succeeds; second claim with the same message_id is rejected."""
        msg_id = "wamid.dedup.test.001"
        # First claim -> True
        self.assertTrue(claim_message(msg_id, db_url=None))
        self.assertTrue(is_message_processed(msg_id, db_url=None))

        # Duplicate claim -> False
        self.assertFalse(claim_message(msg_id, db_url=None))

    def test_02_handle_incoming_suppresses_duplicate_messages(self):
        """handle_incoming returns duplicate status for re-delivered message_ids."""
        msg = {
            "id": "wamid.dedup.test.002",
            "from": "919876543210",
            "type": "text",
            "text": {"body": "hello"},
        }
        mock_sender = MagicMock(return_value=True)

        # First delivery
        with patch("whatsapp.registration_flow.save_session"):
            res1 = handle_incoming(msg, outbound_sender=mock_sender, db_url=None)
            self.assertIn(res1["status"], ["session_started", "language_selected", "invalid_language"])

        # Second delivery with same ID
        res2 = handle_incoming(msg, outbound_sender=mock_sender, db_url=None)
        self.assertEqual(res2["status"], "duplicate")
        self.assertEqual(res2["message_id"], "wamid.dedup.test.002")

    def test_03_unclaim_message_restores_claimability(self):
        """unclaim_message removes ID from tracking so it can be re-processed if handling failed."""
        msg_id = "wamid.dedup.test.003"
        self.assertTrue(claim_message(msg_id, db_url=None))
        unclaim_message(msg_id, db_url=None)
        self.assertFalse(is_message_processed(msg_id, db_url=None))
        self.assertTrue(claim_message(msg_id, db_url=None))


# ==============================================================================
# 6. REQUEST BODY SIZE PROTECTION & STREAM LIMIT TESTS (Phase 6N)
# ==============================================================================
class TestWebhookBodySizeProtection(unittest.TestCase):
    """Audits request-body size limits (HTTP 413) and background task isolation."""

    def setUp(self):
        self.secret = "test_meta_app_secret_phase6n_12345"
        self.bg = BackgroundTasks()

    def test_01_valid_payload_within_limit_accepted(self):
        """Payload within size limit is accepted and verified successfully."""
        payload = {"object": "whatsapp_business_account", "entry": []}
        req = MockFastAPIRequest(payload, app_secret=self.secret)
        with patch.dict(os.environ, {"META_APP_SECRET": self.secret, "MAX_WEBHOOK_BODY_BYTES": "1048576"}):
            res = asyncio.run(receive_whatsapp_event(req, self.bg))
            self.assertEqual(res.status_code, 200)

    def test_02_oversized_payload_via_content_length_rejected_413(self):
        """Oversized payload with Content-Length header is rejected with HTTP 413 before parsing."""
        raw_oversized = b"X" * 2048
        bg = BackgroundTasks()
        req = MockFastAPIRequest(
            raw_body=raw_oversized,
            headers={"Content-Length": "2048", "X-Hub-Signature-256": "sha256=dummy"},
        )
        with patch.dict(os.environ, {"META_APP_SECRET": self.secret, "MAX_WEBHOOK_BODY_BYTES": "1024"}):
            with self.assertRaises(HTTPException) as cm:
                asyncio.run(receive_whatsapp_event(req, bg))
            self.assertEqual(cm.exception.status_code, 413)
            self.assertIn("exceeds maximum permitted size", cm.exception.detail)
            # Verify NO background tasks were scheduled
            self.assertEqual(len(bg.tasks), 0)

    def test_03_oversized_payload_without_content_length_rejected_during_streaming(self):
        """Oversized payload without Content-Length is aborted and rejected with HTTP 413 while streaming."""
        raw_oversized = b"Y" * 3000
        bg = BackgroundTasks()
        # Omit Content-Length from headers, stream in 500-byte chunks
        req = MockFastAPIRequest(
            raw_body=raw_oversized,
            headers={"X-Hub-Signature-256": "sha256=dummy"},
            chunk_size=500,
        )
        self.assertNotIn("content-length", req.headers)
        with patch.dict(os.environ, {"META_APP_SECRET": self.secret, "MAX_WEBHOOK_BODY_BYTES": "1024"}):
            with self.assertRaises(HTTPException) as cm:
                asyncio.run(receive_whatsapp_event(req, bg))
            self.assertEqual(cm.exception.status_code, 413)
            self.assertIn("exceeds maximum permitted size", cm.exception.detail)
            # Verify NO background tasks were scheduled
            self.assertEqual(len(bg.tasks), 0)

    def test_04_starlette_native_request_oversized_stream_rejected_413(self):
        """Native Starlette Request with chunked ASGI receive channel aborts streaming on limit exceed."""
        from starlette.requests import Request
        chunks_delivered = []

        async def mock_receive():
            chunks_delivered.append(1)
            # Deliver 400-byte chunks with more_body=True
            return {"type": "http.request", "body": b"Z" * 400, "more_body": len(chunks_delivered) < 5}

        scope = {
            "type": "http",
            "method": "POST",
            "path": "/webhook",
            "headers": [(b"x-hub-signature-256", b"sha256=dummy")],
        }
        req = Request(scope, mock_receive)
        bg = BackgroundTasks()

        with patch.dict(os.environ, {"META_APP_SECRET": self.secret, "MAX_WEBHOOK_BODY_BYTES": "1000"}):
            with self.assertRaises(HTTPException) as cm:
                asyncio.run(receive_whatsapp_event(req, bg))
            self.assertEqual(cm.exception.status_code, 413)
            # Check that streaming was aborted early: delivered 3 chunks (1200 bytes) instead of all 5 chunks (2000 bytes)
            self.assertLess(len(chunks_delivered), 5)
            self.assertEqual(len(bg.tasks), 0)

    def test_05_invalid_signature_rejection_does_not_schedule_tasks(self):
        """Invalid signature on valid-sized payload raises 403 and never schedules background tasks."""
        payload = {"object": "whatsapp_business_account", "entry": []}
        bg = BackgroundTasks()
        req = MockFastAPIRequest(payload, headers={"X-Hub-Signature-256": "sha256=badhex"})
        with patch.dict(os.environ, {"META_APP_SECRET": self.secret, "MAX_WEBHOOK_BODY_BYTES": "524288"}):
            with self.assertRaises(HTTPException) as cm:
                asyncio.run(receive_whatsapp_event(req, bg))
            self.assertEqual(cm.exception.status_code, 403)
            self.assertIn("Invalid webhook signature", cm.exception.detail)
            # Verify NO background tasks were scheduled
            self.assertEqual(len(bg.tasks), 0)

    def test_06_hmac_signature_verified_against_exact_raw_body(self):
        """Signature verification works correctly on raw body stream for valid payloads."""
        payload = {"object": "whatsapp_business_account", "entry": [{"id": "123"}]}
        req = MockFastAPIRequest(payload, app_secret=self.secret, chunk_size=20)
        bg = BackgroundTasks()
        with patch.dict(os.environ, {"META_APP_SECRET": self.secret}):
            res = asyncio.run(receive_whatsapp_event(req, bg))
            self.assertEqual(res.status_code, 200)


if __name__ == "__main__":
    unittest.main()

