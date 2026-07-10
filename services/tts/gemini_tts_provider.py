import io
import os
import base64
import wave
import tempfile
import requests
from pathlib import Path
from core.config import config
from core.logger import logger
from services.tts.base import TTSProvider, TTSResult

# Per-session fail cache: if Gemini TTS fails due to a bad request, don't retry during same run.
_gemini_tts_failed_this_session = False

GEMINI_TTS_MODEL_FALLBACKS = [
    "gemini-2.5-flash-preview-tts",
    "gemini-2.5-pro-preview-tts",
]


def _write_wave(filename: str, pcm_bytes: bytes, channels: int = 1, rate: int = 24000, sample_width: int = 2) -> None:
    """Write raw PCM bytes to a WAV file."""
    with wave.open(filename, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        wf.writeframes(pcm_bytes)


def _load_api_key() -> str:
    from dotenv import load_dotenv
    load_dotenv()
    return (os.getenv("GEMINI_API_KEY") or config.get("gemini_api_key", "")).strip()


class GeminiTTSProvider(TTSProvider):
    provider_id = "gemini_tts"

    def speak(self, text: str) -> None:
        global _gemini_tts_failed_this_session
        if _gemini_tts_failed_this_session:
            raise RuntimeError("Gemini TTS is disabled for this session due to a previous permanent failure.")

        result = self.synthesize(text)

        # Play the audio from the returned bytes
        import soundfile as sf
        import sounddevice as sd
        try:
            data, fs = sf.read(io.BytesIO(result.audio))
            sd.play(data, fs)
            sd.wait()
        except Exception as e:
            # Soundfile may not parse PCM WAV — try playing temp file via simpleaudio/playsound
            logger.warning(f"Gemini TTS soundfile play failed ({e}), trying direct WAV play...")
            tmp = Path(tempfile.gettempdir()) / "jarvis_gemini_tts_out.wav"
            tmp.write_bytes(result.audio)
            self._play_wav_file(str(tmp))

    def _play_wav_file(self, path: str) -> None:
        import subprocess
        subprocess.run(
            ["powershell", "-c", f"(New-Object Media.SoundPlayer '{path}').PlaySync()"],
            check=False,
            timeout=30
        )

    def synthesize(
        self,
        text: str,
        *,
        voice_id: str = "",
        speed: float = 1.0,
    ) -> TTSResult:
        global _gemini_tts_failed_this_session
        from services.gemini_quota_manager import gemini_quota_manager, ProviderUnavailable, extract_retry_delay_seconds

        tts_model = config.gemini_tts_model
        if not gemini_quota_manager.is_available(tts_model, "tts"):
            remaining = gemini_quota_manager.get_remaining_seconds(tts_model, "tts")
            raise ProviderUnavailable(f"Gemini TTS cooling down for {remaining}s")

        api_key = _load_api_key()
        if not api_key:
            raise ValueError("Gemini API key missing")

        voice_name = voice_id or config.get("gemini_tts_voice", "Kore")
        # Sanitize voice name — must be one of the prebuilt options
        valid_voices = {"Puck", "Charon", "Kore", "Fenrir", "Aoede", "default"}
        if voice_name.lower() == "default" or voice_name not in valid_voices:
            voice_name = "Kore"

        # Try model fallback list
        models_to_try = GEMINI_TTS_MODEL_FALLBACKS.copy()
        configured_model = config.get("gemini_tts_model", "")
        if configured_model and configured_model not in models_to_try:
            models_to_try.insert(0, configured_model)

        last_error = None
        for model in models_to_try:
            try:
                audio_bytes = self._call_gemini_tts_api(api_key, model, text, voice_name)
                logger.info("Gemini TTS audio generated successfully.")
                return TTSResult(
                    audio=audio_bytes,
                    format="wav",
                    sample_rate=24000,
                    provider=self.provider_id,
                    voice_id=voice_name,
                )
            except ProviderUnavailable:
                raise
            except Exception as e:
                err_str = str(e)
                logger.warning(f"Gemini TTS model {model!r} failed: {e}")
                last_error = e

                # Check for rate limit / quota exhaustion
                if "HTTP 429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    retry_seconds = extract_retry_delay_seconds(err_str)
                    logger.warning(f"Gemini TTS quota exceeded. Cooling down for {retry_seconds}s.")
                    gemini_quota_manager.set_cooldown(tts_model, retry_seconds, "tts")
                    raise ProviderUnavailable(f"Gemini TTS quota exceeded. Cooling down for {retry_seconds}s")

                # Permanent failure — don't retry the same bad request type
                if "INVALID_ARGUMENT" in err_str or "allowed mimetypes" in err_str or "response_mime_type" in err_str:
                    logger.error("Gemini TTS permanent API shape error. Disabling for this session.")
                    _gemini_tts_failed_this_session = True
                    raise RuntimeError(f"Gemini TTS permanent failure: {e}") from e

        raise RuntimeError(f"All Gemini TTS models failed. Last: {last_error}") from last_error


    def _call_gemini_tts_api(self, api_key: str, model: str, text: str, voice_name: str) -> bytes:
        """
        Call the Gemini TTS REST endpoint using the correct payload shape.
        Returns raw WAV bytes.
        """
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": f"Say in a calm, confident, futuristic assistant voice: {text}"}
                    ]
                }
            ],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {
                            "voiceName": voice_name
                        }
                    }
                }
            }
        }

        headers = {"Content-Type": "application/json"}

        logger.info(f"Sending request to Gemini TTS API (model={model}, voice={voice_name})...")
        response = requests.post(url, headers=headers, json=payload, timeout=25)

        if response.status_code != 200:
            raise RuntimeError(f"Gemini TTS API HTTP {response.status_code}: {response.text}")

        res_data = response.json()

        # Extract the audio bytes from inlineData
        try:
            parts = res_data["candidates"][0]["content"]["parts"]
            audio_b64 = None
            for p in parts:
                if "inlineData" in p and "data" in p["inlineData"]:
                    audio_b64 = p["inlineData"]["data"]
                    break

            if not audio_b64:
                raise RuntimeError(f"No inlineData audio in Gemini TTS response: {res_data}")

            raw_pcm = base64.b64decode(audio_b64)

            # Wrap raw PCM as WAV so soundfile can read it
            tmp_wav = Path(tempfile.gettempdir()) / "jarvis_gemini_tts.wav"
            _write_wave(str(tmp_wav), raw_pcm, channels=1, rate=24000, sample_width=2)
            return tmp_wav.read_bytes()

        except (KeyError, IndexError) as e:
            raise RuntimeError(f"Failed to parse Gemini TTS response: {e}. Response: {res_data}")

    def available_voices(self) -> list[str]:
        return ["Kore", "Puck", "Charon", "Fenrir", "Aoede"]

    def health(self) -> tuple[bool, str]:
        global _gemini_tts_failed_this_session
        if _gemini_tts_failed_this_session:
            return False, "Disabled this session (API shape error)"
        api_key = _load_api_key()
        if not api_key:
            return False, "Unavailable: API key missing"
        return True, "Ready"
