"""
capture_hud_screenshots.py
Boots JARVIS, transitions through states, injects real transcript/response
signals so the VOICE INPUT and CORE OUTPUT panels are populated, then
captures screenshots of the full two-column HUD.
"""
import sys
import os
import time

project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(project_dir)
sys.path.append(project_dir)

from PyQt6.QtCore import QTimer
from core.logger import logger
from main import JarvisApp


def capture(app):
    os.makedirs("screenshots", exist_ok=True)
    hud = app.hud

    def grab(fname):
        app.app.processEvents()
        time.sleep(0.5)
        app.app.processEvents()
        hud.grab().save(f"screenshots/{fname}")
        logger.info(f"  → saved screenshots/{fname}")

    # ── 1. IDLE ────────────────────────────────────────────────
    logger.info("Capturing IDLE state...")
    hud.on_state_changed("PASSIVE_WAKE_LISTENING")
    grab("hud_idle.png")

    # ── 2. LISTENING ───────────────────────────────────────────
    logger.info("Capturing LISTENING state...")
    hud.on_state_changed("SESSION_LISTENING")
    grab("hud_listening.png")

    # ── 3. PROCESSING ──────────────────────────────────────────
    logger.info("Capturing PROCESSING state (transcript injected)...")
    hud.on_state_changed("TRANSCRIBING_COMMAND")
    # Inject a completed transcription so VOICE INPUT shows a USER: line
    hud.on_transcription_completed("what's the capital of France")
    grab("hud_processing.png")

    # ── 4. SPEAKING + Core Output populated ────────────────────
    logger.info("Capturing SPEAKING state (core output streaming)...")
    hud.on_state_changed("SPEAKING_RESPONSE")
    # Stream two sentence chunks into CORE OUTPUT
    hud.on_stream_token_received("The capital of France is Paris,")
    app.app.processEvents()
    time.sleep(0.2)
    hud.on_stream_token_received(
        "a city known for its role as a global center of art and culture."
    )
    grab("hud_speaking.png")

    # ── 5. AFTER SPEECH: transcript shows JARVIS: line ────────
    logger.info("Capturing post-speech state (full transcript)...")
    hud.on_state_changed("COOLDOWN")
    # Simulate speech_ended so the JARVIS: line is appended and Core Output
    # starts its 5-second dismiss countdown
    hud.on_speech_ended()
    # Also inject a second exchange to prove multi-line transcript
    hud.on_transcription_completed("open notepad")
    hud.on_stream_token_received("Opening Notepad now, Sir.")
    hud.on_speech_ended()
    hud.on_state_changed("PASSIVE_WAKE_LISTENING")
    grab("hud_populated.png")

    logger.info("All screenshots captured successfully.")
    try:
        from services.audio_service import audio_service
        audio_service.stop()
    except Exception:
        pass
    app.app.quit()


def main():
    app = JarvisApp()
    # Wait 3s for full boot (TTS cache, mic calibration, etc.) then capture
    QTimer.singleShot(3000, lambda: capture(app))
    sys.exit(app.app.exec())


if __name__ == "__main__":
    main()
