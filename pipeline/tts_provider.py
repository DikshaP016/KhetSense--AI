#!/usr/bin/env python3
"""
KhetSense AI — Text-to-Speech (TTS) Provider Abstraction & Implementations
Supports multilingual audio generation for English, Marathi, and Hindi.

Providers implemented:
1. BaseTTSProvider: Abstract base class for all TTS providers.
2. MockTTSProvider: Deterministic, offline, zero-dependency provider for testing and safe local dev.
3. GoogleCloudTTSProvider: Production-grade cloud provider using Google Cloud Text-to-Speech REST API
   (supporting en-IN, mr-IN, hi-IN neural/wavenet voices and MP3/OGG_OPUS formats).
4. EdgeTTSProvider: High-quality Microsoft Azure neural voice provider via edge-tts (if installed).
"""

import os
import sys
import json
import base64
import logging
import tempfile
import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Tuple, List

try:
    import requests
except ImportError:
    requests = None

# Configure logger
logger = logging.getLogger("khetsense_tts")

# Audio formats supported by WhatsApp Cloud API
MIME_MP3 = "audio/mpeg"
MIME_OGG = "audio/ogg"
MIME_AAC = "audio/aac"
MIME_MP4 = "audio/mp4"

SUPPORTED_AUDIO_FORMATS = {
    "mp3": MIME_MP3,
    "ogg": MIME_OGG,
    "aac": MIME_AAC,
    "mp4": MIME_MP4,
}


@dataclass
class TTSResult:
    """Encapsulates the outcome of a text-to-speech synthesis operation."""
    audio_bytes: bytes
    mime_type: str
    file_path: Optional[str] = None
    language: str = "en"
    provider_name: str = "mock"
    duration_seconds: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def cleanup(self) -> bool:
        """Safely removes the generated audio file from disk if it exists."""
        if self.file_path and os.path.exists(self.file_path):
            try:
                os.remove(self.file_path)
                return True
            except OSError as e:
                logger.warning("Failed to remove temporary audio file %s: %s", self.file_path, e)
                return False
        return False


class BaseTTSProvider(ABC):
    """Abstract base class for all Text-to-Speech providers."""

    @abstractmethod
    def synthesize(
        self,
        text: str,
        language: str = "en",
        output_path: Optional[str] = None,
        audio_format: str = "mp3",
    ) -> TTSResult:
        """
        Synthesizes text into spoken audio.

        Args:
            text: Spoken script content.
            language: Normalized language code ('en', 'mr', 'hi').
            output_path: Optional specific file path to save audio.
            audio_format: Desired audio format ('mp3', 'ogg', etc.).

        Returns:
            TTSResult containing audio bytes, mime_type, and file path.

        Raises:
            ValueError: If text is empty or language is unsupported.
            RuntimeError: If synthesis fails.
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Returns True if the provider is fully configured and ready for synthesis."""
        pass

    def get_cache_key(self, text: str, language: str, audio_format: str = "mp3") -> str:
        """Generates a deterministic hash for deduplication/caching."""
        raw = f"{self.__class__.__name__}:{language.lower().strip()}:{audio_format.lower().strip()}:{text.strip()}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def synthesize_multilingual(
        self,
        segments: List[Tuple[str, str]],
        output_path: Optional[str] = None,
        audio_format: str = "mp3",
    ) -> TTSResult:
        """
        Synthesizes multiple language segments sequentially into a single cohesive audio result.
        Synthesizes each segment using its native neural voice and joins the raw audio frames.
        """
        if not segments:
            raise ValueError("Segments list cannot be empty.")
        combined_bytes = bytearray()
        last_mime = MIME_MP3
        temp_files_to_clean = []
        for text, lang in segments:
            res = self.synthesize(text=text, language=lang, audio_format=audio_format)
            combined_bytes.extend(res.audio_bytes)
            last_mime = res.mime_type
            if res.file_path and os.path.exists(res.file_path):
                temp_files_to_clean.append(res.file_path)

        payload = bytes(combined_bytes)
        ext = audio_format.lower()
        if output_path:
            file_path = output_path
            os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
            with open(file_path, "wb") as f:
                f.write(payload)
        else:
            fd, file_path = tempfile.mkstemp(prefix="khetsense_multilingual_", suffix=f".{ext}")
            with os.fdopen(fd, "wb") as f:
                f.write(payload)

        # Clean intermediate individual segment files
        for p in temp_files_to_clean:
            if p != file_path and os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass

        return TTSResult(
            audio_bytes=payload,
            mime_type=last_mime,
            file_path=file_path,
            language="multilingual",
            provider_name=self.__class__.__name__,
            metadata={"segments_count": len(segments)},
        )


class MockTTSProvider(BaseTTSProvider):
    """
    Deterministic Mock TTS Provider.
    Produces valid synthetic audio payload for testing without calling external APIs.
    Supports failure simulation and call tracking for comprehensive test assertion.
    """

    # Valid synthetic MP3 frame header (MPEG-1 Layer III 32kbps mono sync frame)
    MOCK_MP3_PAYLOAD = (
        b"\xff\xfb\x90\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
        b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
        b"KHETSENSE_MOCK_AUDIO_FRAME_V1"
    )

    def __init__(
        self,
        simulate_error: Optional[str] = None,
        custom_audio_bytes: Optional[bytes] = None,
        temp_dir: Optional[str] = None,
    ):
        self.simulate_error = simulate_error
        self.custom_audio_bytes = custom_audio_bytes
        self.temp_dir = temp_dir or tempfile.gettempdir()
        self.synthesized_calls: List[Dict[str, Any]] = []
        self._cache: Dict[str, TTSResult] = {}

    def is_available(self) -> bool:
        return True

    def synthesize(
        self,
        text: str,
        language: str = "en",
        output_path: Optional[str] = None,
        audio_format: str = "mp3",
    ) -> TTSResult:
        if not text or not text.strip():
            raise ValueError("Text to synthesize cannot be empty.")

        norm_lang = (language or "en").strip().lower()
        if norm_lang not in {"en", "mr", "hi"}:
            norm_lang = "en"

        # Record call for test verification
        self.synthesized_calls.append({
            "text": text,
            "language": norm_lang,
            "audio_format": audio_format,
            "output_path": output_path,
        })

        if self.simulate_error:
            raise RuntimeError(f"Mock TTS synthesis failure: {self.simulate_error}")

        cache_key = self.get_cache_key(text, norm_lang, audio_format)
        if cache_key in self._cache and output_path is None:
            return self._cache[cache_key]

        payload = self.custom_audio_bytes or self.MOCK_MP3_PAYLOAD
        mime_type = SUPPORTED_AUDIO_FORMATS.get(audio_format.lower(), MIME_MP3)

        # Write to file
        ext = "mp3" if audio_format.lower() == "mp3" else ("ogg" if audio_format.lower() == "ogg" else "audio")
        if output_path:
            file_path = output_path
            os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
            with open(file_path, "wb") as f:
                f.write(payload)
        else:
            fd, file_path = tempfile.mkstemp(prefix=f"khetsense_voice_{norm_lang}_", suffix=f".{ext}", dir=self.temp_dir)
            with os.fdopen(fd, "wb") as f:
                f.write(payload)

        # Approximate duration: ~15 words per minute -> rough estimate
        word_count = len(text.split())
        approx_seconds = round(max(2.0, word_count / 2.5), 1)

        result = TTSResult(
            audio_bytes=payload,
            mime_type=mime_type,
            file_path=file_path,
            language=norm_lang,
            provider_name="mock",
            duration_seconds=approx_seconds,
            metadata={"cache_key": cache_key, "word_count": word_count},
        )
        self._cache[cache_key] = result
        return result

    def synthesize_multilingual(
        self,
        segments: List[Tuple[str, str]],
        output_path: Optional[str] = None,
        audio_format: str = "mp3",
    ) -> TTSResult:
        if not segments:
            raise ValueError("Segments list cannot be empty.")

        self.synthesized_calls.append({
            "segments": segments,
            "multilingual": True,
            "audio_format": audio_format,
            "output_path": output_path,
        })

        if self.simulate_error:
            raise RuntimeError(f"Mock TTS synthesis failure: {self.simulate_error}")

        payload = b"".join(self.custom_audio_bytes or self.MOCK_MP3_PAYLOAD for _ in segments)
        mime_type = SUPPORTED_AUDIO_FORMATS.get(audio_format.lower(), MIME_MP3)
        ext = "mp3" if audio_format.lower() == "mp3" else "audio"

        if output_path:
            file_path = output_path
            os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
            with open(file_path, "wb") as f:
                f.write(payload)
        else:
            fd, file_path = tempfile.mkstemp(prefix="khetsense_mock_multi_", suffix=f".{ext}", dir=self.temp_dir)
            with os.fdopen(fd, "wb") as f:
                f.write(payload)

        return TTSResult(
            audio_bytes=payload,
            mime_type=mime_type,
            file_path=file_path,
            language="multilingual",
            provider_name="mock",
            duration_seconds=float(len(segments) * 2.0),
            metadata={"segments_count": len(segments)},
        )


class GoogleCloudTTSProvider(BaseTTSProvider):
    """
    Google Cloud Text-to-Speech REST API Provider.
    Supports high-quality Neural2, Wavenet, and Standard voices for Indian languages:
    - English (India): en-IN (en-IN-Wavenet-D, en-IN-Neural2-A)
    - Marathi (India): mr-IN (mr-IN-Wavenet-A, mr-IN-Standard-A)
    - Hindi (India): hi-IN (hi-IN-Wavenet-A, hi-IN-Neural2-A)
    """

    API_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"

    # Default voice mappings by language
    VOICE_CONFIG = {
        "en": {
            "language_code": "en-IN",
            "name": "en-IN-Wavenet-D",
            "ssml_gender": "FEMALE",
        },
        "mr": {
            "language_code": "mr-IN",
            "name": "mr-IN-Wavenet-A",
            "ssml_gender": "FEMALE",
        },
        "hi": {
            "language_code": "hi-IN",
            "name": "hi-IN-Wavenet-A",
            "ssml_gender": "FEMALE",
        },
    }

    def __init__(
        self,
        api_key: Optional[str] = None,
        credentials_path: Optional[str] = None,
        temp_dir: Optional[str] = None,
    ):
        self.api_key = api_key or os.getenv("GOOGLE_TTS_API_KEY")
        self.credentials_path = credentials_path or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        self.temp_dir = temp_dir or tempfile.gettempdir()
        self._cache: Dict[str, TTSResult] = {}

    def is_available(self) -> bool:
        if self.api_key:
            return True
        if self.credentials_path and os.path.exists(self.credentials_path):
            return True
        # Check standard default EE key path as potential service account
        default_ee_key = os.path.join(os.path.dirname(__file__), "..", "credentials", "ee-key.json")
        if os.path.exists(default_ee_key):
            return True
        return False

    def _get_auth_headers_or_url(self) -> Tuple[Dict[str, str], str]:
        """Resolves authentication via API key or OAuth2 Bearer token."""
        if self.api_key:
            return {"Content-Type": "application/json; charset=utf-8"}, f"{self.API_URL}?key={self.api_key}"

        # Attempt to obtain Google bearer token using google-auth if installed
        try:
            import google.auth
            from google.auth.transport.requests import Request as GoogleAuthRequest

            creds = None
            if self.credentials_path and os.path.exists(self.credentials_path):
                from google.oauth2 import service_account
                creds = service_account.Credentials.from_service_account_file(
                    self.credentials_path,
                    scopes=["https://www.googleapis.com/auth/cloud-platform"],
                )
            else:
                default_ee_key = os.path.join(os.path.dirname(__file__), "..", "credentials", "ee-key.json")
                if os.path.exists(default_ee_key):
                    from google.oauth2 import service_account
                    creds = service_account.Credentials.from_service_account_file(
                        default_ee_key,
                        scopes=["https://www.googleapis.com/auth/cloud-platform"],
                    )
                else:
                    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])

            if creds:
                if not creds.valid:
                    creds.refresh(GoogleAuthRequest())
                return {
                    "Authorization": f"Bearer {creds.token}",
                    "Content-Type": "application/json; charset=utf-8",
                }, self.API_URL
        except Exception as e:
            logger.warning("Failed to obtain Google Cloud OAuth token for TTS: %s", e)

        raise RuntimeError("No valid Google Cloud TTS credentials found (set GOOGLE_TTS_API_KEY or GOOGLE_APPLICATION_CREDENTIALS).")

    def synthesize(
        self,
        text: str,
        language: str = "en",
        output_path: Optional[str] = None,
        audio_format: str = "mp3",
    ) -> TTSResult:
        if not text or not text.strip():
            raise ValueError("Text to synthesize cannot be empty.")

        norm_lang = (language or "en").strip().lower()
        if norm_lang not in self.VOICE_CONFIG:
            norm_lang = "en"

        cache_key = self.get_cache_key(text, norm_lang, audio_format)
        if cache_key in self._cache and output_path is None:
            return self._cache[cache_key]

        headers, endpoint_url = self._get_auth_headers_or_url()

        voice_def = self.VOICE_CONFIG[norm_lang]
        encoding = "MP3" if audio_format.lower() == "mp3" else ("OGG_OPUS" if audio_format.lower() == "ogg" else "MP3")
        mime_type = MIME_MP3 if encoding == "MP3" else MIME_OGG

        payload = {
            "input": {"text": text},
            "voice": {
                "languageCode": voice_def["language_code"],
                "name": voice_def["name"],
                "ssmlGender": voice_def["ssml_gender"],
            },
            "audioConfig": {
                "audioEncoding": encoding,
                "speakingRate": 0.95,  # Slightly slower for agricultural clarity
                "pitch": 0.0,
            },
        }

        if requests is None:
            raise RuntimeError("The 'requests' package is required for GoogleCloudTTSProvider.")

        try:
            resp = requests.post(endpoint_url, headers=headers, json=payload, timeout=15)
            if resp.status_code != 200:
                raise RuntimeError(f"Google Cloud TTS API error {resp.status_code}: {resp.text}")

            resp_data = resp.json()
            audio_base64 = resp_data.get("audioContent")
            if not audio_base64:
                raise RuntimeError("Google Cloud TTS API response missing audioContent field.")

            audio_bytes = base64.b64decode(audio_base64)
        except Exception as req_err:
            logger.error("Exception during Google Cloud TTS request: %s", req_err)
            raise

        ext = "mp3" if encoding == "MP3" else "ogg"
        if output_path:
            file_path = output_path
            os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
            with open(file_path, "wb") as f:
                f.write(audio_bytes)
        else:
            fd, file_path = tempfile.mkstemp(prefix=f"khetsense_gcloud_{norm_lang}_", suffix=f".{ext}", dir=self.temp_dir)
            with os.fdopen(fd, "wb") as f:
                f.write(audio_bytes)

        result = TTSResult(
            audio_bytes=audio_bytes,
            mime_type=mime_type,
            file_path=file_path,
            language=norm_lang,
            provider_name="google_cloud",
            metadata={"voice": voice_def["name"], "cache_key": cache_key},
        )
        self._cache[cache_key] = result
        return result


class EdgeTTSProvider(BaseTTSProvider):
    """
    Microsoft Edge Neural TTS Provider.
    Utilizes free, natural-sounding Azure neural voices without requiring an API key.
    - English: en-IN-NeerjaNeural
    - Marathi: mr-IN-AarohiNeural
    - Hindi: hi-IN-SwaraNeural
    Requires `edge-tts` package if used in runtime.
    """

    VOICE_CONFIG = {
        "en": "en-IN-NeerjaNeural",
        "mr": "mr-IN-AarohiNeural",
        "hi": "hi-IN-SwaraNeural",
    }

    def __init__(self, temp_dir: Optional[str] = None):
        self.temp_dir = temp_dir or tempfile.gettempdir()
        self._cache: Dict[str, TTSResult] = {}

    def is_available(self) -> bool:
        try:
            import edge_tts
            return True
        except ImportError:
            return False

    def synthesize(
        self,
        text: str,
        language: str = "en",
        output_path: Optional[str] = None,
        audio_format: str = "mp3",
    ) -> TTSResult:
        if not text or not text.strip():
            raise ValueError("Text to synthesize cannot be empty.")

        try:
            import asyncio
            import edge_tts
        except ImportError:
            raise RuntimeError("The 'edge-tts' package is not installed. Install with: pip install edge-tts")

        norm_lang = (language or "en").strip().lower()
        if norm_lang not in self.VOICE_CONFIG:
            norm_lang = "en"
        voice = self.VOICE_CONFIG[norm_lang]

        cache_key = self.get_cache_key(text, norm_lang, audio_format)
        if cache_key in self._cache and output_path is None:
            cached = self._cache[cache_key]
            if cached.file_path and os.path.exists(cached.file_path):
                return cached

        ext = "mp3"
        created_temp = False
        if output_path:
            file_path = output_path
            os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        else:
            fd, file_path = tempfile.mkstemp(prefix=f"khetsense_edge_{norm_lang}_", suffix=f".{ext}", dir=self.temp_dir)
            os.close(fd)
            created_temp = True

        async def _run_edge():
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(file_path)

        try:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    pool.submit(asyncio.run, _run_edge()).result()
            else:
                asyncio.run(_run_edge())

            with open(file_path, "rb") as f:
                audio_bytes = f.read()

            if not audio_bytes:
                raise RuntimeError("Edge TTS synthesis produced an empty audio file.")
        except Exception:
            if created_temp and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except OSError:
                    pass
            raise

        result = TTSResult(
            audio_bytes=audio_bytes,
            mime_type=MIME_MP3,
            file_path=file_path,
            language=norm_lang,
            provider_name="edge_tts",
            metadata={"voice": voice, "cache_key": cache_key},
        )
        self._cache[cache_key] = result
        return result


def get_tts_provider(provider_name: Optional[str] = None) -> BaseTTSProvider:
    """
    Factory function to instantiate the configured TTS provider.

    Resolution order:
    1. Explicit provider_name argument ('mock', 'google', 'edge').
    2. TTS_PROVIDER environment variable.
    3. If 'google' is requested but credentials are unavailable, falls back safely to 'mock'.
    4. Default: MockTTSProvider (safe, offline-ready).
    """
    selected = (provider_name or os.getenv("TTS_PROVIDER", "mock")).strip().lower()

    if selected in ("google", "google_cloud", "gcloud"):
        provider = GoogleCloudTTSProvider()
        if provider.is_available():
            return provider
        logger.warning("GoogleCloudTTSProvider requested but credentials are not available. Falling back to MockTTSProvider.")
        return MockTTSProvider()

    elif selected in ("edge", "edge_tts"):
        provider = EdgeTTSProvider()
        if provider.is_available():
            return provider
        logger.warning("EdgeTTSProvider requested but edge-tts is not installed. Falling back to MockTTSProvider.")
        return MockTTSProvider()

    return MockTTSProvider()


__all__ = [
    "BaseTTSProvider",
    "TTSResult",
    "MockTTSProvider",
    "GoogleCloudTTSProvider",
    "EdgeTTSProvider",
    "get_tts_provider",
    "SUPPORTED_AUDIO_FORMATS",
    "MIME_MP3",
    "MIME_OGG",
]
