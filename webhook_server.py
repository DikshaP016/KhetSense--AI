#!/usr/bin/env python3
"""
KhetSense AI — WhatsApp Cloud API Webhook Receiver (Stage 1)
Handles:
1. Meta Webhook Verification Handshake (GET /webhook)
2. Parsing & Logging Incoming WhatsApp Messages (POST /webhook)
   - Text messages
   - Location pins (latitude & longitude)
   - Interactive button replies / quick replies
"""

import os
import sys
import json
import logging
from typing import Dict, Any, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response, Query, HTTPException, status, BackgroundTasks
from fastapi.responses import PlainTextResponse, JSONResponse
import uvicorn

try:
    from whatsapp.registration_flow import handle_incoming, mask_phone
except ImportError:
    from khetsense.whatsapp.registration_flow import handle_incoming, mask_phone

try:
    from common.config import verify_meta_signature, is_sender_allowed, get_max_webhook_body_bytes
except ImportError:
    from khetsense.common.config import verify_meta_signature, is_sender_allowed, get_max_webhook_body_bytes

# Configure UTF-8 encoding on Windows console for both stdout and stderr
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Load environment variables
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(SCRIPT_DIR, ".env")
load_dotenv(ENV_PATH)

# Verify token configured by user
VERIFY_TOKEN = os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN", "khetsense_verify_token_2026")

# Configure UTF-8 safe logging
log_handlers = [logging.StreamHandler(sys.stdout)]
webhook_log_file = os.getenv("WEBHOOK_LOG_FILE")
if webhook_log_file:
    log_handlers.append(logging.FileHandler(webhook_log_file, encoding="utf-8"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=log_handlers,
    force=True,
)
logger = logging.getLogger("khetsense_webhook")

app = FastAPI(
    title="KhetSense WhatsApp Webhook Receiver",
    description="Stage 1 Connectivity Endpoint for Meta WhatsApp Cloud API",
    version="1.0.0",
)


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "online",
        "service": "KhetSense WhatsApp Webhook",
        "stage": "Stage 1 — Connectivity & Event Logging",
        "verify_token_configured": bool(VERIFY_TOKEN and VERIFY_TOKEN != "your_custom_webhook_verify_token_here"),
    }


# ==============================================================================
# 1. META GET VERIFICATION HANDSHAKE
# ==============================================================================
@app.get("/webhook")
async def verify_webhook(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
):
    """
    Handles Meta's GET verification request when configuring the webhook in
    the Meta App Dashboard (WhatsApp > Configuration).
    
    Meta sends:
      hub.mode=subscribe
      hub.verify_token=<your_configured_verify_token>
      hub.challenge=<random_string_or_integer>
      
    Your endpoint must respond with HTTP 200 and the plain text hub.challenge.
    """
    logger.info("Received Meta Webhook Verification Handshake Request")
    logger.info("  hub.mode: %s", hub_mode)
    logger.info("  hub.verify_token: %s", hub_verify_token)

    expected_token = os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN", VERIFY_TOKEN)

    # Validate mode and token
    if hub_mode == "subscribe" and hub_verify_token == expected_token:
        logger.info("Verification SUCCESS! Returning hub.challenge to Meta.")
        # Meta requires plain text response with challenge value
        return PlainTextResponse(content=hub_challenge, status_code=200)

    logger.warning("Verification FAILED! Token mismatch or invalid mode.")
    logger.warning("  Expected: %s", expected_token)
    logger.warning("  Received: %s", hub_verify_token)
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Verification token mismatch")


async def read_request_body_with_limit(request: Request, max_bytes: int) -> bytes:
    """
    Safely reads and buffers the incoming request body up to max_bytes.
    Enforces a strict upper bound to prevent unbounded in-memory buffering.
    Rejects oversized payloads with HTTP 413 (Payload Too Large).
    """
    # 1. Fast rejection if Content-Length header is present and exceeds max_bytes
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            cl = int(content_length.strip())
            if cl > max_bytes:
                logger.warning(
                    "Rejected webhook request: Content-Length %s exceeds limit of %s bytes",
                    cl, max_bytes,
                )
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail=f"Request body exceeds maximum permitted size of {max_bytes} bytes",
                )
        except ValueError:
            pass

    # 2. Check if request body was already cached/buffered (e.g. pre-buffered test mocks or Starlette cache)
    if hasattr(request, "_body") and request._body is not None:
        if len(request._body) > max_bytes:
            logger.warning(
                "Rejected webhook request: Cached body size %s exceeds limit of %s bytes",
                len(request._body), max_bytes,
            )
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"Request body exceeds maximum permitted size of {max_bytes} bytes",
            )
        return request._body

    # 3. Stream chunks if request provides an async stream() method (ASGI streaming)
    if hasattr(request, "stream") and callable(request.stream):
        chunks = []
        total_size = 0
        try:
            async for chunk in request.stream():
                total_size += len(chunk)
                if total_size > max_bytes:
                    logger.warning(
                        "Rejected webhook request: Streamed body exceeded limit of %s bytes (aborted at %s bytes)",
                        max_bytes, total_size,
                    )
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail=f"Request body exceeds maximum permitted size of {max_bytes} bytes",
                    )
                chunks.append(chunk)
            raw_body = b"".join(chunks)
            request._body = raw_body
            return raw_body
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error reading request stream: %s", e)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to read request stream")

    # 4. Fallback for mock objects that define await request.body()
    if hasattr(request, "body") and callable(request.body):
        raw_body = await request.body()
        if len(raw_body) > max_bytes:
            logger.warning(
                "Rejected webhook request: Body size %s exceeds limit of %s bytes",
                len(raw_body), max_bytes,
            )
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"Request body exceeds maximum permitted size of {max_bytes} bytes",
            )
        return raw_body

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid request object")


# ==============================================================================
# 2. INCOMING WHATSAPP MESSAGE EVENT HANDLER (POST /webhook)
# ==============================================================================
@app.post("/webhook")
async def receive_whatsapp_event(request: Request, background_tasks: BackgroundTasks):
    """
    Receives incoming WhatsApp Cloud API events from Meta:
    - Enforces maximum request-body size limit (HTTP 413) before unbounded buffering
    - Validates Meta Webhook Signature (X-Hub-Signature-256 HMAC-SHA256)
    - Parses sender phone number (from)
    - Parses sender profile name
    - Identifies message type ('text', 'location', 'interactive', etc.)
    - Logs formatted message payload to console
    - Offloads message handling to FastAPI BackgroundTask (sub-3s SLA)
    - Returns HTTP 200 OK immediately to satisfy Meta's 3-second delivery SLA
    """
    # 1. Enforce Maximum Request Body Size Limit before buffering unlimited bytes
    max_bytes = get_max_webhook_body_bytes()
    raw_body = await read_request_body_with_limit(request, max_bytes=max_bytes)

    # 2. Verify Meta Webhook Signature (X-Hub-Signature-256)
    sig_header = request.headers.get("X-Hub-Signature-256")
    is_valid, reason = verify_meta_signature(raw_body, sig_header)
    if not is_valid:
        logger.warning("Rejected webhook request: %s", reason)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Invalid webhook signature: {reason}",
        )

    try:
        body = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except Exception as e:
        logger.error("Failed to parse request JSON: %s", e)
        return JSONResponse(content={"status": "invalid_json"}, status_code=400)

    # Confirm event is from WhatsApp Business Account
    obj = body.get("object")
    if obj != "whatsapp_business_account":
        logger.warning("Ignored non-whatsapp event: %s", obj)
        return JSONResponse(content={"status": "ignored"}, status_code=200)

    # Iterate through entries and changes in the Meta payload
    entries = body.get("entry", [])
    for entry in entries:
        changes = entry.get("changes", [])
        for change in changes:
            field = change.get("field")
            if field != "messages":
                continue

            value = change.get("value", {})
            metadata = value.get("metadata", {})
            business_phone_id = metadata.get("phone_number_id")

            # Extract user profile information if available
            contacts = value.get("contacts", [])
            contact_name = "Farmer"
            if contacts:
                contact_name = contacts[0].get("profile", {}).get("name", "Farmer")

            # Handle Message Delivery Status Updates (sent, delivered, read)
            statuses = value.get("statuses", [])
            for s in statuses:
                recipient_id = s.get("recipient_id")
                msg_status = s.get("status")
                logger.info("[STATUS UPDATE] To: %s | Status: %s", mask_phone(recipient_id), msg_status.upper())

            # Handle Inbound User Messages
            messages = value.get("messages", [])
            for msg in messages:
                sender_mobile = msg.get("from")
                msg_id = msg.get("id")
                msg_type = msg.get("type")
                timestamp = msg.get("timestamp")

                print("\n" + "=" * 70)
                print("             INCOMING WHATSAPP MESSAGE RECEIVED             ")
                print("=" * 70)
                print(f"  Sender Phone:     {mask_phone(sender_mobile)}")
                print(f"  Farmer Name:      {contact_name}")
                print(f"  Message Type:     {msg_type.upper()}")
                print(f"  Message ID:       {msg_id}")
                print(f"  Timestamp:        {timestamp}")

                # Parse by message type
                if msg_type == "text":
                    text_body = msg.get("text", {}).get("body", "").strip()
                    print(f"  Text Content:     \"{text_body}\"")

                elif msg_type == "location":
                    loc = msg.get("location", {})
                    lat = loc.get("latitude")
                    lon = loc.get("longitude")
                    name = loc.get("name") or "None"
                    addr = loc.get("address") or "None"
                    print(f"  GPS Coordinates:  Lat: {lat}, Lon: {lon}")
                    print(f"  Location Name:    {name}")
                    print(f"  Address:          {addr}")
                    print("  [NOTE] Location pin ready for Stage 2 point-to-polygon conversion.")

                elif msg_type == "interactive":
                    inter = msg.get("interactive", {})
                    inter_type = inter.get("type")
                    if inter_type == "button_reply":
                        btn_id = inter.get("button_reply", {}).get("id")
                        btn_title = inter.get("button_reply", {}).get("title")
                        print(f"  Button Clicked:   [{btn_title}] (ID: {btn_id})")
                    elif inter_type == "list_reply":
                        list_id = inter.get("list_reply", {}).get("id")
                        list_title = inter.get("list_reply", {}).get("title")
                        print(f"  List Selected:    [{list_title}] (ID: {list_id})")
                    else:
                        print(f"  Interactive Data: {inter}")

                elif msg_type == "button":
                    btn_text = msg.get("button", {}).get("text")
                    print(f"  Quick Button:     \"{btn_text}\"")

                else:
                    print(f"  Other Payload:    {msg.get(msg_type)}")

                print("=" * 70 + "\n")

                # Allowlist check (Phase 6H)
                if not is_sender_allowed(sender_mobile):
                    logger.warning(
                        "[ALLOWLIST] Sender %s is not in the authorized allowlist. Discarding message %s.",
                        mask_phone(sender_mobile),
                        msg_id,
                    )
                    continue

                # Dispatch conversation state machine in background (sub-3s Meta SLA)
                background_tasks.add_task(handle_incoming, msg, contact_name)

    # Meta requires HTTP 200 OK fast (<3s) to prevent retries
    return JSONResponse(content={"status": "received"}, status_code=200)


# ==============================================================================
# ENTRY POINT
# ==============================================================================
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    print("=" * 70)
    print("      Starting KhetSense WhatsApp Cloud API Webhook Receiver        ")
    print(f"      Listening on: http://127.0.0.1:{port}                         ")
    print(f"      Webhook Verification Route: GET  http://127.0.0.1:{port}/webhook")
    print(f"      Incoming Messages Route:    POST http://127.0.0.1:{port}/webhook")
    print("=" * 70)
    uvicorn.run("webhook_server:app", host="127.0.0.1", port=port, reload=True)
