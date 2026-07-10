import os
import base64
import requests
from core.config import config
from core.logger import logger
from services.stt.base import STTProvider, STTResult


def _load_api_key() -> str:
    from dotenv import load_dotenv
    load_dotenv()
    return (os.getenv("GEMINI_API_KEY") or config.get("gemini_api_key", "")).strip()


def is_mostly_latin_or_ascii(text: str) -> bool:
    """
    Returns True if at least 85% of characters in `text` are ASCII.
    Used to reject non-Latin script responses (Tamil, Malayalam, Hindi, etc.)
    """
    if not text:
        return False
    latin_chars = sum(1 for ch in text if ch.isascii())
    return (latin_chars / max(len(text), 1)) >= 0.85


# System prompt ensuring accurate, English-only, no-repeat transcription
GEMINI_STT_SYSTEM_PROMPT = """\
You are transcribing a short English Windows assistant command for an assistant named JARVIS.

Rules:
- Return only English text using Latin letters.
- Do NOT translate into Malayalam, Tamil, Hindi, or any other script.
- Do NOT add explanations.
- Do NOT add punctuation unless needed.
- Do NOT repeat phrases.
- If audio is unclear, return an empty string.

Common assistant words: Jarvis, open, close, launch, start, run, notepad, chrome, microsoft edge, \
edge, calculator, file explorer, sleep, full shutdown, exit app.

Important:
- If the user says Jarvis sleep, return exactly: Jarvis sleep
- If the user says Jarvis open notepad, return exactly: Jarvis open notepad
- Do not invent "Jarvis" if it was not spoken.
- Do not return any non-Latin characters.
"""


class GeminiSTTProvider(STTProvider):
    provider_id = "gemini_stt"

    def transcribe(
        self,
        audio_bytes: bytes,
        *,
        audio_format: str = "wav",
        language: str | None = "en",
        initial_prompt: str | None = None,
    ) -> STTResult:
        from services.gemini_quota_manager import gemini_quota_manager, ProviderUnavailable, extract_retry_delay_seconds

        stt_model = config.gemini_stt_model
        if not gemini_quota_manager.is_available(stt_model, "stt"):
            remaining = gemini_quota_manager.get_remaining_seconds(stt_model, "stt")
            raise ProviderUnavailable(f"Gemini STT cooling down for {remaining}s")

        api_key = _load_api_key()
        if not api_key:
            raise ValueError("Gemini API key missing for STT")

        model = stt_model
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

        # Determine correct MIME type
        mime_map = {
            "wav": "audio/wav",
            "mp3": "audio/mp3",
            "m4a": "audio/mp4",
            "webm": "audio/webm",
            "ogg": "audio/ogg",
            "flac": "audio/flac",
        }
        mime_type = mime_map.get(audio_format.lower(), f"audio/{audio_format}")

        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "inlineData": {
                                "mimeType": mime_type,
                                "data": audio_b64,
                            }
                        },
                        {"text": GEMINI_STT_SYSTEM_PROMPT},
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.0,
                "candidateCount": 1,
            },
        }

        headers = {"Content-Type": "application/json"}

        logger.info(f"Requesting Gemini STT transcription (model={model})...")
        response = requests.post(url, headers=headers, json=payload, timeout=20)

        if response.status_code != 200:
            error_text = response.text
            if response.status_code == 429 or "RESOURCE_EXHAUSTED" in error_text:
                retry_seconds = extract_retry_delay_seconds(error_text)
                logger.warning(f"Gemini STT quota exceeded. Cooling down for {retry_seconds}s.")
                gemini_quota_manager.set_cooldown(stt_model, retry_seconds, "stt")
                raise ProviderUnavailable(f"Gemini STT quota exceeded. Cooling down for {retry_seconds}s")
            raise RuntimeError(f"Gemini STT API error {response.status_code}: {error_text}")

        res_data = response.json()
        try:
            parts = res_data["candidates"][0]["content"].get("parts", [])
        except Exception:
            parts = []

        text = ""
        if parts:
            try:
                text = parts[0].get("text", "").strip()
            except Exception:
                pass

        if not text:
            logger.info("Gemini STT returned no transcription text.")
            return STTResult(
                text="",
                language=language,
                provider=self.provider_id,
                metadata=res_data,
            )

        # Guard: reject non-Latin / non-ASCII transcriptions (Tamil, Malayalam, etc.)
        if text and not is_mostly_latin_or_ascii(text):
            logger.warning(
                f"Gemini STT returned non-Latin transcription: {text!r}. "
                "Raising to trigger local fallback."
            )
            raise RuntimeError(
                f"Gemini STT non-Latin output rejected: {text!r}. Fallback to local_faster_whisper."
            )

        logger.info(f"Gemini STT transcription: {text!r}")
        return STTResult(
            text=text,
            language=language,
            provider=self.provider_id,
            metadata=res_data,
        )


    def health(self) -> tuple[bool, str]:
        api_key = _load_api_key()
        if not api_key:
            return False, "Unavailable: API key missing"
        return True, "Ready"

    def supported_formats(self) -> list[str]:
        return ["wav", "mp3", "m4a", "webm", "ogg", "flac"]
