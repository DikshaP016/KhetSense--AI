# KhetSense AI — Test Suite & Execution Evidence

**Project:** KhetSense AI — Satellite-Based Crop Stress Detection and Multilingual Voice-Enabled Irrigation Advisory System  
**Test Suite Status:** PASSING (148/148 Tests Passed)  
**Execution Environment:** Windows Python 3.13 venv (`khetsense/.venv`)  
**Audit Timestamp:** October 3, 2026, 22:24:42 IST  
**Isolation Level:** 100% Offline, Deterministic, Zero Network Calls, Zero Live Database Writes

---

## 1. Test Suite Summary Metrics

| Metric | Value | Reference / Notes |
| :--- | :--- | :--- |
| **Execution Command** | `.\.venv\Scripts\python.exe -m unittest discover -s tests -v` | Discovers all test modules in `tests/` directory |
| **Total Tests Discovered** | **148** | Complete regression and feature suite |
| **Tests Passed** | **148** (100.0%) | Verified green build |
| **Tests Failed** | **0** | No assertion failures |
| **Tests Errored** | **0** | No unhandled exceptions |
| **Tests Skipped** | **0** | Full suite actively executed |
| **Execution Duration** | **5.524s** | Verbose execution logging |
| **Network Calls Made** | **0** | Fully mocked (GEE, SMAP, OpenWeather, WhatsApp, TTS) |
| **Database Writes Made** | **0** | Fully mocked psycopg2 connection pools |

---

## 2. Test Breakdown by Test File & Module

### 2.1 `tests/test_registration_flow.py` (115 Tests)
Covers the core WhatsApp registration flow, state machine, location selection, agricultural validation, data normalization, and background pipeline execution.

| Test Class / Component | Tests | Focus Area & Verified Behaviors |
| :--- | :---: | :--- |
| `TestUtils` | 16 | Phone normalization (`+91` prefix, 10-digit formats), masking (`...+1234`), name validation, clean formatting. |
| `TestCropNormalization` | 14 | English aliases, Marathi Devanagari (`कापूस`, `सोयाबीन`, `तूर`, `गहू`), Hindi Devanagari (`कपास`, `अरहर`, `धान`), transliteration. |
| `TestAcreageParsing` | 12 | Numeric strings (`"4"`, `"2.5"`), units (`"5 acres"`, `"3 एकर"`), boundaries ($0.1$ to $50.0$), default handling. |
| `TestBoundingBoxValidation` | 8 | Valid Indian coordinates (Maharashtra, Punjab, Tamil Nadu); invalid international coordinates (USA, Europe, Ocean). |
| `TestDeduplicationAndState` | 15 | Meta webhook retry deduplication via `claim_message()`, unclaim on error, atomic conflict handling. |
| `TestMultilingualRegistration` | 20 | Complete conversational onboarding in English, Marathi, Hindi; state transitions from `AWAITING_LANGUAGE` to `REGISTERED`. |
| `TestLocationSelection` | 15 | Returning farmer prompt (`location_choice_returning_prompt`), Option 1 (reusing saved pin), Option 2 (at farm pin), Option 3 (away map pin). |
| `TestLocationValidationEngine` | 15 | Case A (`SUITABLE_CROPLAND`), Case B (`LIKELY_URBAN`), Case C (`BARREN_OR_UNCERTAIN`), Case D (`INSUFFICIENT_SATELLITE_DATA`), Case E (`INCOMPLETE_AUXILIARY_DATA`), cloudy scenes (>20%). |

### 2.2 `tests/test_voice_advisory.py` (33 Tests)
Covers multilingual voice advisory generation, TTS provider abstractions, WhatsApp audio media upload, audio message delivery, and pipeline resilience.

| Test Class / Component | Tests | Focus Area & Verified Behaviors |
| :--- | :---: | :--- |
| `TestVoiceScriptGeneration` | 11 | English, Marathi, Hindi conversational voice script synthesis; phrasing for `IRRIGATE_NOW`, `IRRIGATE_LIGHTLY`, `DELAY_RECHECK`; strict exclusion of technical jargon (NDVI, SMAP, PostGIS). |
| `TestTTSProviderImplementations` | 10 | `MockTTSProvider` synthetic audio generation and cache deduplication; `GoogleCloudTTSProvider` REST API payload structure and base64 audio decoding; `EdgeTTSProvider` availability and fallback to mock; factory resolution order. |
| `TestWhatsAppVoiceDelivery` | 6 | Multipart media upload to Meta Graph API v21.0 `/media`; audio dispatch via `/messages`; graceful mock mode when credentials unconfigured; HTTP 500 error handling. |
| `TestPipelineVoiceIntegration` | 6 | End-to-end pipeline execution with voice enabled (`send_voice_advisory=True`); non-blocking fault tolerance (TTS or upload failure never fails text advisory); voice withholding on unsuitable or unvalidated farm locations. |

---

## 3. Real Mobile Testing Evidence & Bug Investigation

### 3.1 Documented WhatsApp Live Interaction Log
During real mobile testing on WhatsApp with a live farmer session:
- **Actor:** Existing registered farmer with **Farm ID #3**.
- **Historical Record in Database:** Name: `diks`, Crop: `Maize`, Preferred Language: `mr` (Marathi).
- **Session Sequence:**
  1. Farmer sent `restart` to re-register the farm.
  2. Bot sent `restart_confirm`: *"Are you sure you want to re-register Farm ID #3 (diks - मका)? Reply YES to confirm or NO to cancel."*
  3. Farmer replied `YES`.
  4. Bot confirmed reset and transitioned to language selection, then prompted for full name.
  5. Farmer typed new name: `pobin`.
  6. Bot asked for name confirmation: *"Is your name **pobin**? Reply YES to confirm."*
  7. Farmer replied `YES`.
  8. Bot prompted for crop: *"Welcome pobin! Which crop do you grow?"*
  9. Farmer typed new crop: `tur` (Pigeon Pea).
  10. Bot prompted for farm area: *"What is your farm area for Pigeon Pea in acres?"*
  11. Farmer typed new acreage: `4`.
  12. **Defect Occurrence:** Bot immediately sent `location_choice_returning_prompt`:
      > *"Welcome back, diks! For your farm #3 (Maize):  
      > We have your previously saved farm location (Lat 19.8762, Lon 75.3421).  
      > 1. Keep current saved farm location  
      > 2. I am currently at my farm (share current pin)  
      > 3. I am not at my farm (select or drop a pin on the map)"*

### 3.2 Code Trace & Root Cause Analysis

- **File:** `whatsapp/registration_flow.py`
- **Location 1 (Triggered in Step 12):** Lines 1618–1626
  ```python
  # whatsapp/registration_flow.py lines 1621-1624
  get_message(
      "location_choice_returning_prompt",
      lang=session_lang,
      farm_id=registered_farm["id"],
      name=registered_farm.get("farmer_name") or session.get("name") or "Farmer",
      crop=get_localized_crop(registered_farm.get("crop_name") or session.get("crop"), session_lang),
      lat=float(prev_lat),
      lon=float(prev_lon),
  )
  ```
- **Location 2 (Triggered on invalid choice re-prompt):** Lines 1780–1783
  ```python
  # whatsapp/registration_flow.py lines 1781-1782
  name=registered_farm.get("farmer_name") or session.get("name") or "Farmer",
  crop=get_localized_crop(registered_farm.get("crop_name") or session.get("crop"), session_lang),
  ```

#### Detailed Technical Explanation
In Python, the boolean expression `A or B` returns `A` if `A` is truthy, and only evaluates `B` if `A` is falsy (`None`, empty string, etc.).
- `registered_farm` represents the existing database record from the `farms` table for the sender's mobile number. For Farm ID #3, `registered_farm["farmer_name"]` is `"diks"` and `registered_farm["crop_name"]` is `"Maize"`.
- Both `"diks"` and `"Maize"` are non-empty strings and therefore strictly truthy.
- In contrast, `session` contains the in-flight registration session stored in `registration_sessions`, where the farmer just entered `session["name"] = "pobin"` and `session["crop"] = "Pigeon Pea"`.
- Because the code placed `registered_farm.get(...)` before `session.get(...)`, the existing database values completely overrode and masked the newly entered session values.
- As a consequence, the bot displayed the old name `diks` and old crop `Maize` instead of the newly updated values `pobin` and `Pigeon Pea`.

#### Recommended Remedial Code (Audit Recommendation Only)
In `whatsapp/registration_flow.py`, reverse the evaluation precedence so that in-flight session data always overrides stale database values:
```python
# Recommended fix for lines 1622-1623 and 1781-1782:
name = (session.get("name") if session and session.get("name") else registered_farm.get("farmer_name")) or "Farmer"
raw_crop = (session.get("crop") if session and session.get("crop") else registered_farm.get("crop_name")) or "Cotton"
crop = get_localized_crop(raw_crop, session_lang)
```
*(Note: As mandated by audit constraints, no source code has been modified).*

---

## 4. Test Gaps & Verification Limits

1. **Live Google Cloud TTS API:** Not exercised against live Google Cloud billing endpoints during offline testing. Relies on mock REST client tests.
2. **Live Edge TTS Provider:** The `edge-tts` Python library is not installed in the production venv, causing the system to automatically fall back to `MockTTSProvider`.
3. **Live WhatsApp Audio Reception:** Voice notes have not yet been delivered to or auditioned on a physical mobile device.
4. **Live Database Migrations:** Migrations 004 and 005 are verified via local SQL scripts and test suite schema fallbacks, but have not been executed on the production Supabase PostgreSQL instance.
