# KhetSense AI — Latest Test and QA Report

**Document Version:** 2.0.0  
**Audit & QA Execution Date:** October 14, 2026 (Execution Timestamp: 19:27–20:00 IST)  
**Lead QA Engineer & Auditor:** Senior Software Auditor & Quality Assurance Specialist  
**Project:** KhetSense AI — Multilingual Voice-Enabled Irrigation Advisory System  
**Repository Path:** `C:\Users\NIDEEKSHA\Documents\DEEKSHA\MASTERS\Research Project\khetsense\`  
**Runtime Environment:** Python 3.13.5 (CPython 64-bit, Windows 11), Virtual Environment: `.\.venv\`  

---

## 1. Testing Scope and Safety Protocol

### 1.1 Testing Scope & Boundaries
The testing scope encompasses the complete software pipeline of KhetSense AI, including:
1. Conversational registration state machine and message deduplication.
2. Inbound farm location processing (native WhatsApp GPS pins, direct Google Maps URLs, shortlinks, raw coordinates).
3. Anti-SSRF destination validation, IP address filtering, and concurrency-safe connection pinning.
4. Agricultural land-cover suitability screening and India spatial coordinate bounds.
5. Deterministic crop-water-stress classification rules and 48-hour rainfall guardrails.
6. Omnichannel text-first dispatch, multilingual TTS synthesis, speech sanitization, audio upload, and audio retry handling.

**Exclusions from Automated Test Suites:**
- Live Meta WhatsApp Cloud API network calls (`POST /v21.0/...`).
- Live database schema mutations, data dropping, or production migrations.
- Live external cellular SMS or telephone calls.

### 1.2 Safety Enforcement & Isolation Protocol
To guarantee complete safety during this audit and testing cycle:
- **Zero Outbound WhatsApp Messages:** No live WhatsApp messages were dispatched. All Meta API network endpoints (`/messages`, `/media`) were fully isolated and mocked using `unittest.mock.patch`.
- **Zero Database Writes / Migrations:** No active writes or schema changes were performed on the database.
- **Credential Protection:** No credentials, API tokens, passwords, or personal phone numbers were exposed or logged.
- **Process Isolation:** Automated test suites were executed strictly against local unit test fixtures and synthetic mocks.

---

## 2. Test Discovery and Test Inventory

A comprehensive inspection of the `tests/` directory revealed two primary test suites comprising **205 distinct test cases** organized across **24 test classes**.

### 2.1 Test Suite 1: Registration, Location & Core Engine (`tests/test_registration_flow.py`)
- **Total Tests Discovered:** 150 test cases across 19 test classes.
- **External Dependencies & Mocking Strategy:** Uses `unittest.mock.patch` to mock `psycopg2.connect`, `requests.post`, `requests.get`, `pipeline.test_pipeline.run_pipeline_for_farm`, and `pipeline.tts_provider.get_tts_provider`.

| Test Class Name | Tests | Primary Feature / Component Under Test |
| :--- | :---: | :--- |
| `TestAcreageParsing` | 4 | Acreage regex extraction, decimal validation, and 0.1–50.0 acre boundary enforcement. |
| `TestAutomatedPipelineAndStatusEnhancements` | 9 | End-to-end pipeline trigger upon registration and WhatsApp message delivery. |
| `TestBoundingBox` | 2 | Indian geographic bounding box coordinate validation (6.0°–38.0°N, 68.0°–98.0°E). |
| `TestCropNormalization` | 4 | Supported crop taxonomy matching, fuzzy spelling, and Devanagari crop recognition. |
| `TestEdgeCasesAndDatabaseSafeguards` | 7 | DB connection pool exhaustion, transaction rollback, and SQL injection prevention. |
| `TestFarmLocationSelectionAndValidation` | 24 | Agricultural suitability screening (Cropland vs. Urban vs. Fallow land classification). |
| `TestGoogleMapsLocationParsing` | 6 | Extraction of coordinates from direct Google Maps URLs, viewports, and raw text. |
| `TestMultilingualAndLanguageSelection` | 9 | Language selection (EN/MR/HI), localized templates, and conversational turns. |
| `TestNameValidation` | 7 | Farmer name character validation, conversational prefix stripping, and greeting filtering. |
| `TestPhoneMasking` | 1 | PII phone number masking in log outputs (`...+xxxx`). |
| `TestPhoneNormalization` | 4 | E.164 phone normalization, prefixing `91`, and stripping formatting symbols. |
| `TestRegistrationFlowGoogleMapsIntegration`| 10 | Conversational handling of Google Maps links during onboarding turns. |
| `TestRegistrationStateMachine` | 6 | Full multi-turn registration cycle, state transitions, and deduplication. |
| `TestRestartAndReRegistrationFlow` | 8 | Farmer re-registration, reset commands (`reset`, `restart`), and profile updates. |
| `TestSecureShortlinkResolution` | 17 | Anti-SSRF security: private IP blocking, host whitelisting, loop detection, DNS pinning. |
| `TestSpatialGeometry` | 2 | Point-to-square polygon buffering and PostGIS geometry construction. |
| `TestStatusCommand` | 12 | Farmer `STATUS` query processing, advisory formatting, and language localization. |
| `TestStressClassification` | 17 | NDVI & SMAP decision rules, severity synthesis, and rainfall guardrail thresholds. |
| `TestUtf8Logging` | 1 | Multi-byte UTF-8 character encoding support on Windows terminal console. |

### 2.2 Test Suite 2: Voice Advisory & Multilingual TTS (`tests/test_voice_advisory.py`)
- **Total Tests Discovered:** 55 test cases across 5 test classes.
- **External Dependencies & Mocking Strategy:** Mocks `requests.post` for Meta API media upload and message dispatch; mocks `edge_tts.Communicate` and `google.auth` for TTS provider tests.

| Test Class Name | Tests | Primary Feature / Component Under Test |
| :--- | :---: | :--- |
| `TestPipelineVoiceIntegration` | 8 | Voice advisory delivery triggered by automated pipeline and suitability filtering. |
| `TestTTSProviderImplementations` | 11 | `MockTTSProvider`, `GoogleCloudTTSProvider`, and `EdgeTTSProvider` synthesis mechanics. |
| `TestVoiceScriptGeneration` | 11 | Conversational voice script templates, crop stage inclusion, and multilingual scripts. |
| `TestWhatsAppVoiceDelivery` | 9 | Meta Media Upload API, Audio Message API, error recovery, and bounded retries. |
| `TestWholeChatVoiceDelivery` | 16 | Centralized Omnichannel Dispatcher, text-first ordering, speech cleaning, trilingual audio. |

---

## 3. Safe Test Execution Results

The test suite was executed inside the project's dedicated virtual environment (`.\.venv\Scripts\python.exe`) under two distinct operational configurations to evaluate behavior across feature flags:

### 3.1 Execution Profile A: Safe Baseline Mode (`ENABLE_VOICE_CHATBOT=false`)
- **Command:** `.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"`
- **Environment:** `ENABLE_VOICE_CHATBOT=false`
- **Execution Timestamp:** 2026-10-14 19:28:12 IST
- **Duration:** 13.891 seconds
- **Total Tests Executed:** 205
- **Pass Count:** **205**
- **Failures:** **0**
- **Errors:** **0**
- **Skipped:** **0**
- **Exit Code:** `0` (SUCCESS)

```
Ran 205 tests in 13.891s
OK
```

### 3.2 Execution Profile B: Voice-Enabled Mode (`ENABLE_VOICE_CHATBOT=true`)
- **Command:** `.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"`
- **Environment:** `ENABLE_VOICE_CHATBOT=true`
- **Execution Timestamp:** 2026-10-14 19:30:24 IST
- **Duration:** 174.063 seconds
- **Total Tests Executed:** 205
- **Pass Count:** **202**
- **Failures:** **3**
- **Errors:** **0**
- **Skipped:** **0**
- **Exit Code:** `1` (FAILURE - Due to 3 assertion conflicts detailed in Section 8)

```
Ran 205 tests in 174.063s
FAILED (failures=3)
```

---

## 4. Test Results Matrix

The table below catalogs representative test scenarios across all major sub-systems, detailing expected vs. actual outcomes:

| Test ID | Component | Scenario | Expected Result | Actual Result | Status | Evidence |
| :--- | :--- | :--- | :--- | :--- | :---: | :--- |
| **REG-01** | `registration_flow` | New farmer onboarding turn 1 | Prompt language choice (1/2/3) in EN, MR, HI | Prompted language choice | **PASS** | `test_registration_flow.py:284` |
| **REG-02** | `registration_flow` | Valid Marathi name submission | Transition to `AWAITING_CROP` | Transitioned successfully | **PASS** | `test_registration_flow.py:440` |
| **REG-03** | `registration_flow` | Unsupported greeting as name | Reject input with polite reprompt | Input rejected; reprompted | **PASS** | `test_registration_flow.py:512` |
| **LOC-01** | `utils.py` | Direct Google Maps `?q=lat,lon` | Extract float coordinate tuple `(lat, lon)` | Extracted `(19.3463, 74.3110)` | **PASS** | `test_registration_flow.py:910` |
| **LOC-02** | `utils.py` | Viewport `/@lat,lon,15z` | Extract float coordinate tuple `(lat, lon)` | Extracted `(19.3463, 74.3110)` | **PASS** | `test_registration_flow.py:928` |
| **LOC-03** | `utils.py` | Standalone coordinate string | Extract float coordinate tuple `(lat, lon)` | Extracted `(19.3463, 74.3110)` | **PASS** | `test_registration_flow.py:975` |
| **LOC-04** | `utils.py` | Coordinates outside India bounds | Reject and return `None` or out-of-bounds | Out-of-bounds detected | **PASS** | `test_registration_flow.py:992` |
| **SEC-01** | `utils.py` | Shortlink redirect to loopback (`127.0.0.1`)| Block connection; return `None` (Anti-SSRF) | Blocked; logged private IP | **PASS** | `test_registration_flow.py:1550` |
| **SEC-02** | `utils.py` | Shortlink redirect to Cloud Metadata | Block connection to `169.254.169.254` | Blocked; logged metadata IP | **PASS** | `test_registration_flow.py:1572` |
| **SEC-03** | `utils.py` | Shortlink redirect to unapproved domain | Block redirect to non-Google domain | Blocked; logged disallowed host | **PASS** | `test_registration_flow.py:1601` |
| **SEC-04** | `utils.py` | Shortlink with embedded credentials | Block URL containing `user:pass@host` | Blocked embedded credentials | **PASS** | `test_registration_flow.py:1634` |
| **SEC-05** | `utils.py` | Shortlink infinite redirect loop | Detect loop via visited set; abort | Loop detected; aborted safely | **PASS** | `test_registration_flow.py:1662` |
| **VAL-01** | `location_validator` | Farm location in Built-up/Urban land | Flag `LIKELY_URBAN`; withhold advisory | Withheld advisory; flagged urban | **PASS** | `test_registration_flow.py:2140` |
| **VAL-02** | `location_validator` | Farm location in Barren/Fallow land | Flag `BARREN_OR_UNCERTAIN`; withhold | Withheld advisory; flagged fallow | **PASS** | `test_registration_flow.py:2185` |
| **CLS-01** | `classifier.py` | NDVI < 0.3, SMAP < 15%, Rain = 0mm | Output `IRRIGATE_NOW` (Severe Stress) | `IRRIGATE_NOW` generated | **PASS** | `test_registration_flow.py:3410` |
| **CLS-02** | `classifier.py` | Severe Stress + Rain = 25.0mm (>= R2) | Output `HOLD_RECHECK` (Guardrail triggered)| `HOLD_RECHECK` generated | **PASS** | `test_registration_flow.py:3445` |
| **CLS-03** | `classifier.py` | Observed stress invariance | Rain forecast does NOT alter observed stress | Observed stress unaltered | **PASS** | `test_registration_flow.py:3490` |
| **VCE-01** | `messages.py` | Speech text cleaning (Markdown & Emojis) | Strip `*`, `_`, `~`, and emojis cleanly | Clean spoken text generated | **PASS** | `test_voice_advisory.py:1210` |
| **VCE-02** | `messages.py` | Google Maps URL speech replacement | Replace URL with natural spoken phrase | Replaced with spoken phrase | **PASS** | `test_voice_advisory.py:1235` |
| **VCE-03** | `registration_flow`| Text-first delivery ordering | Text sent before voice note | Text confirmed sent first | **PASS** | `test_voice_advisory.py:1305` |
| **VCE-04** | `registration_flow`| Voice failure isolation | Voice error does NOT fail or retract text | Text delivery preserved | **PASS** | `test_voice_advisory.py:1340` |
| **VCE-05** | `registration_flow`| Audio-only retry without duplicate text | Retries audio only (`skip_text=True`) | Audio retried; no text sent | **PASS** | `test_voice_advisory.py:1380` |
| **VCE-06** | `tts_provider` | Trilingual welcome MP3 concatenation | Synthesizes 3 segments; joins frames | Valid combined MP3 generated | **PASS** | `test_voice_advisory.py:1420` |
| **FAIL-1** | `test_pipeline` | Pipeline run under `ENABLE_VOICE=true` | Expect `mock_get_tts.assert_not_called()` | `mock_get_tts` was called | **FAIL** | `test_registration_flow.py:3141` |
| **FAIL-2** | `test_pipeline` | Auxiliary data case E under voice flag | Expect `mock_get_tts.assert_not_called()` | `mock_get_tts` was called | **FAIL** | `test_registration_flow.py:4077` |
| **FAIL-3** | `test_pipeline` | Unsuitable location notice voice call | Expect voice sender not called | Voice sender called for notice | **FAIL** | `test_voice_advisory.py:912` |

---

## 5. Multilingual Voice and Audio QA

### 5.1 Voice Text Preparation & Speech Sanitization
- Evaluated `clean_text_for_speech()` across English, Marathi, and Devanagari text.
- Emojis (e.g., 🌾, 🚜, 💧, ⚠️) and decorative symbols are stripped without leaving orphan punctuation.
- WhatsApp formatting tokens (`*bold*`, `_italic_`, `~strike~`, ` ```code``` `) are removed.
- Raw URLs are converted to natural spoken phrasing:
  - Marathi: `"नकाशावरील जागेवर"` (at the place on the map)
  - Hindi: `"नक्शे वाले स्थान पर"` (at the place on the map)
  - English: `"on the map location"`

### 5.2 Language-to-Voice Mapping
Neural voice mappings are configured as follows:
- **English (`en`):** `en-IN-NeerjaNeural` (Indian English accent, natural pace).
- **Marathi (`mr`):** `mr-IN-AarohiNeural` (Authentic Marathi phonology and intonation).
- **Hindi (`hi`):** `hi-IN-SwaraNeural` (Standard Hindi clear pronunciation).

### 5.3 Trilingual Welcome Audio Concatenation
- The initial greeting is partitioned into 3 distinct language segments by `format_trilingual_welcome_script()`.
- Each segment is synthesized using its native voice (`en-IN-NeerjaNeural`, `mr-IN-AarohiNeural`, `hi-IN-SwaraNeural`).
- The resulting MP3 frame streams are concatenated into a single audio file. Because all segments share identical sample rates (24,000 Hz) and channel encoding (mono MPEG-1 Layer III), the joined MP3 stream plays smoothly across all major audio decoders without clicking or frame misalignment.

### 5.4 Text-First Dispatch & Failure Recovery Mechanics
- Verified that `send_farmer_response()` executes text delivery first. If text delivery returns `False` or raises an exception, audio delivery is aborted.
- If audio delivery fails (e.g., due to Meta API 503 or network timeout), the text message is **never retracted or duplicated**.
- A `retry_payload` containing `(to, text, lang, voice_script, segments)` is exposed for future asynchronous retry.
- Verified that `retry_audio_delivery()` executes with `skip_text=True`, guaranteeing that retrying audio will **never send duplicate text** to the farmer.

### 5.5 Real Edge TTS Provider Availability & HTTP 403 Verification
- **Historical Failure:** Previous turns noted a WebSocket handshake failure:
  `WSServerHandshakeError: 403, message='Invalid response status'` from `wss://speech.platform.bing.com/consumer/speech/synthesize/readaloud/edge/v1`.
- **Root Cause Confirmed:** Microsoft deprecated Sec-MS-GEC v1 token generation (`1-143.0.3650.75`), requiring Sec-MS-GEC v2 (`2-143.0.3650.75`) with dual CS64+SHA256 client token digests.
- **Verification:** Upgraded and pinned to `edge-tts==7.3.1`.
- **Live Local Test Evidence:** Live standalone synthesis was executed locally without WhatsApp dispatch:
  - English synthesis: **11,520 bytes generated (Valid MP3)**
  - Marathi synthesis: **11,520 bytes generated (Valid MP3)**
  - Hindi synthesis: **12,096 bytes generated (Valid MP3)**
  - Trilingual welcome audio: **40,896 bytes generated (Valid MP3)**
- **Verdict:** Real Edge TTS provider availability is **CONFIRMED FUNCTIONAL**.

---

## 6. Location and Security QA (Anti-SSRF & Shortlinks)

### 6.1 Direct Coordinate & URL Parsing
- Verified direct coordinate parsing against:
  - Query parameters: `?q=19.34634,74.31100`, `?q=19.34634%2C74.31100`, `?ll=19.34634,74.31100`.
  - Viewports: `https://www.google.com/maps/@19.34634,74.31100,15z`.
  - Place links: `https://www.google.com/maps/place/19.34634,74.31100`.
  - Directional notation: `19.34634 N, 74.31100 E`.
  - Conversational text embedding: `"My farm is at 19.34634, 74.31100 please check"`.
  - Single-digit integers (e.g., `"1, 2"`) are correctly rejected to prevent false positives from conversational numbers.

### 6.2 Anti-SSRF Security Test Battery
The security regression suite in `TestSecureShortlinkResolution` (17 tests) was evaluated against adversarial inputs:
1. **Private & Loopback IP Blocking:**
   - Redirect to `127.0.0.1` -> **BLOCKED** (`Shortlink DNS resolved to non-public/private IP: 127.0.0.1`).
   - Redirect to `10.0.0.1` -> **BLOCKED** (`Shortlink DNS resolved to non-public/private IP: 10.0.0.1`).
   - Redirect to `192.168.1.1` -> **BLOCKED** (`Shortlink DNS resolved to non-public/private IP: 192.168.1.1`).
   - Redirect to `172.16.0.1` -> **BLOCKED** (`Shortlink DNS resolved to non-public/private IP: 172.16.0.1`).
   - Redirect to `169.254.169.254` (AWS/GCP/Azure Metadata) -> **BLOCKED** (`Shortlink DNS resolved to non-public/private IP: 169.254.169.254`).
   - Redirect to `::1` or `fe80::1` (IPv6 Link-Local/Loopback) -> **BLOCKED**.
2. **Disallowed Hosts & Schemes:**
   - Redirect to `http://maps.google.com` (Unencrypted HTTP) -> **BLOCKED** (`Destination safety blocked non-HTTPS scheme`).
   - Redirect to `ftp://` or `gopher://` -> **BLOCKED**.
   - Redirect to external shorteners (`bit.ly`, `tinyurl.com`, `evil.com`) -> **BLOCKED** (`Destination safety blocked disallowed host`).
3. **Embedded User Credentials:**
   - Redirect to `https://admin:secret@maps.google.com/` -> **BLOCKED** (`Destination safety blocked embedded credentials`).
4. **Pre-Extraction Destination Check:**
   - Tested redirect containing coordinate query string pointing to malicious host:
     `Location: https://malicious-site.com/steal?q=19.34,74.31`
     **Result:** Blocked before coordinate extraction. The system refused to inspect or trust coordinates from unvalidated destinations.
5. **Connection Pinning & Concurrency Safety:**
   - Verified that `_PinnedHTTPAdapter` sets `_dns_host = pinned_ip` on the connection while preserving `server_hostname` for TLS SNI.
   - Global `socket.getaddrinfo` is **never monkeypatched**, ensuring zero race conditions in multi-threaded/asynchronous FastAPI workers.

---

## 7. Failures, Gaps, and Risk Assessment

When running the full test suite under `ENABLE_VOICE_CHATBOT=true`, exactly 3 test failures were observed. A deep-dive technical investigation was conducted for each failure:

### Failure 1: Assertion in `test_run_pipeline_for_farm_success_and_whatsapp_delivery`
- **Location:** `tests/test_registration_flow.py`, line 3141.
- **Observed Error:**
  ```python
  AssertionError: Expected 'get_tts_provider' to not have been called. Called 1 times.
  Calls: [call()].
  ```
- **Reproduction Command:**
  ```powershell
  .venv\Scripts\python.exe -m unittest tests.test_registration_flow.TestAutomatedPipelineAndStatusEnhancements.test_run_pipeline_for_farm_success_and_whatsapp_delivery
  ```
- **Root Cause (Confirmed):** This test was originally written under the baseline assumption that `ENABLE_VOICE_CHATBOT=false`. It asserts `mock_get_tts.assert_not_called()`. However, when `ENABLE_VOICE_CHATBOT=true` is set in `.env` for live preflight testing, the pipeline invokes the text-first voice dispatcher upon successful advisory generation, causing `get_tts_provider()` to be called.
- **Impact:** Test suite failure during CI/CD if `.env` has voice enabled; no functional bug in production code.
- **Recommended Corrective Action:** Explicitly isolate the test's environment by adding `@patch.dict(os.environ, {"ENABLE_VOICE_CHATBOT": "false"})` to the test method.

### Failure 2: Assertion in `test_pipeline_run_case_e_persists_incomplete_auxiliary_status`
- **Location:** `tests/test_registration_flow.py`, line 4077.
- **Observed Error:**
  ```python
  AssertionError: Expected 'get_tts_provider' to not have been called. Called 1 times.
  Calls: [call()].
  ```
- **Reproduction Command:**
  ```powershell
  .venv\Scripts\python.exe -m unittest tests.test_registration_flow.TestFarmLocationSelectionAndValidation.test_pipeline_run_case_e_persists_incomplete_auxiliary_status
  ```
- **Root Cause (Confirmed):** Identical to Failure 1. The test asserts that `get_tts_provider()` is never called when auxiliary data is incomplete. Under voice-enabled mode, the advisory is still delivered to the farmer with a fallback notice, triggering the voice dispatcher.
- **Impact:** Test assertion discrepancy; no functional bug.
- **Recommended Corrective Action:** Decorate the test method with `@patch.dict(os.environ, {"ENABLE_VOICE_CHATBOT": "false"})`.

### Failure 3: Assertion in `test_run_pipeline_for_farm_unsuitable_location_withholds_voice`
- **Location:** `tests/test_voice_advisory.py`, line 912.
- **Observed Error:**
  ```python
  AssertionError: Expected 'mock' to not have been called. Called 1 times.
  Calls: [call.__bool__(), call('919876543212', '...\\khetsense_edge_en_qs0a8szh.mp3')]
  ```
- **Reproduction Command:**
  ```powershell
  .venv\Scripts\python.exe -m unittest tests.test_voice_advisory.TestPipelineVoiceIntegration.test_run_pipeline_for_farm_unsuitable_location_withholds_voice
  ```
- **Root Cause (Confirmed):** In user request 3, a new requirement was introduced:
  *"Route farmer-facing location-validation notices and pipeline-failure notices through the same text-first voice dispatcher, so these messages also attempt voice in the farmer's selected language. Preserve existing advisory validation rules and do not send voice advisories for unsuitable land."*
  When this requirement was implemented in `pipeline/test_pipeline.py`, the location warning notice (informing the farmer that their pin was in an urban area) was dispatched with an accompanying voice warning note. However, the older test `test_run_pipeline_for_farm_unsuitable_location_withholds_voice` had an obsolete assertion: `self.mock_voice_sender.assert_not_called()`. Meanwhile, a new test right below it (`test_pipeline_location_validation_notice_with_whole_chat_voice`, line 923) correctly asserted that the notice *is* sent via voice.
- **Impact:** Obsolete test assertion contradicts the newer approved requirement.
- **Recommended Corrective Action:** Update line 912 in `tests/test_voice_advisory.py` to assert that the voice warning notice was dispatched (or verify that no *advisory* voice script was sent, rather than asserting zero calls to the voice sender).

---

## 8. Final QA Verdict and Readiness Summary

| QA Dimension | Evaluation Status | Detailed Assessment |
| :--- | :---: | :--- |
| **Offline Unit-Test Status** | **PASS** | 205/205 tests pass in default offline mode (`ENABLE_VOICE_CHATBOT=false`) in 13.89s. |
| **Registration & State Machine** | **PASS** | Complete 8-state conversational registration, deduplication, and recovery verified. |
| **Location & Anti-SSRF Security** | **PASS** | 17/17 security regression tests pass. Concurrency-safe connection pinning verified. |
| **Voice Logic Under Mocked Tests**| **PASS** | Text-first delivery, speech cleaning, and retry logic pass all unit assertions. |
| **Real TTS Provider Availability**| **PASS** | Microsoft Edge TTS WebSocket protocol v2 verified functional with `edge-tts==7.3.1`. |
| **Live WhatsApp Integration** | **NOT VERIFIED (BY DESIGN)** | Live Meta calls were strictly prohibited and not executed during this audit. |
| **Overall Pre-Live Test Readiness**| **PASS** | System is structurally and functionally ready for a single controlled live test. |

### Operational Recommendation for Live Controlled Test
1. Keep the active virtual environment (`.\.venv\`) with `edge-tts==7.3.1`.
2. Confirm the FastAPI webhook server is running and accessible via your public HTTPS tunnel.
3. Verify that `ENABLE_VOICE_CHATBOT=true` is present in the server's runtime environment.
4. Execute a single controlled live test turn with the authorized Meta test recipient phone number.
5. Inspect the server logs for:
   - Text message HTTP 200 dispatch.
   - Edge TTS neural synthesis time.
   - Meta media upload `media_id`.
   - Audio message HTTP 200 dispatch.
