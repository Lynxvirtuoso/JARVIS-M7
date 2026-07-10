# JARVIS M7 — Voice Calibration & Reliability Testing Checklist

Use this guide to tune and verify your microphone, VAD settings, and accent-friendly corrections for the JARVIS M7 Voice OS.

---

## 1. Wake Word Testing

1. Start the application: `python main.py`
2. Say `"Wake up Jarvis"` or `"Hey Jarvis"` in your natural voice and accent.
3. Observe the HUD:
   - The status indicator should transition from `PASSIVE LISTENING` to `WAKE DETECTED` and then `SPEAKING`.
   - JARVIS should respond with: `"Yes, Sir."`
4. If it fails to wake:
   - Go to Settings (via tray icon or by entering `settings` command).
   - Adjust the **Wake Sensitivity** slider down (lower values make VAD trigger easier).
   - Switch the microphone profile preset to your hardware type (e.g. `Laptop Microphone`).

---

## 2. Command Recognition Testing

1. Trigger a wake phrase or click the green **WAKE** button on the HUD.
2. Once the HUD shows `ACTIVE LISTENING`, speak a desktop control command:
   - `"Open Chrome"`
   - `"Open Notepad"`
   - `"Open VS Code"`
   - `"Take screenshot"`
   - `"Increase volume"`
   - `"Decrease volume"`
3. Verify that the HUD **Voice Command Diagnostics** panel updates with:
   - **Raw**: What Whisper transcribed.
   - **Normalized**: Stripped filler words ("please", "kindly", etc.).
   - **Personal Match**: User-calibrated pronunciation variant matches.
   - **Fuzzy Match**: Similarity correction lookup.
   - **Confidence**: Match confidence score.
   - **Decision**: Final action decision (`Executed`, `Asked confirmation`, `Rejected`, or `Sent to Gemini`).

---

## 3. How to use "Record Test Command" (Push-To-Talk Test)

1. Open the configuration panel.
2. Select the **AUDIO / VOICE** tab.
3. Click the **RECORD TEST COMMAND** button.
4. The button will display `LISTENING (5s)...`. Speak your command.
5. The button will display `PROCESSING...`, downsample the audio, run VAD normalization, compute fuzzy matches, and update the HUD's Diagnostics Panel directly in **Test Mode** (no actions will be executed).
6. Use this mode to check how Whisper transcribes your voice before saving settings!

---

## 4. How to tune Input Gain

1. If your raw transcription is consistently empty or misheard, your mic level may be too low.
2. In Settings $\rightarrow$ **AUDIO / VOICE**, adjust the **INPUT GAIN BOOST** slider (adds up to `20 dB` of real-time software amplification).
3. Click **SAVE CONFIG** to hot-reload.
4. Click **TEST MICROPHONE** -> Speak -> It will record 3 seconds and play it back so you can hear the amplified gain.

---

## 5. How to choose Whisper model

1. In Settings $\rightarrow$ **AUDIO / VOICE**, select the **WHISPER MODEL** dropdown.
2. Models available (ordered by resource intensity):
   - `tiny.en` (fastest, low accuracy)
   - `base.en` (balanced, standard system default)
   - `small.en` (high accuracy, recommended)
   - `medium.en` (best accuracy, requires decent CPU/RAM)
3. Click **SAVE CONFIG**. The background model is dynamically hot-reloaded without restarting the app.

---

## 6. How to disable Clap Wake

1. Clap wake is disabled by default to prevent accidental triggers from typing or ambient noise.
2. To verify, check that **Enable Double Clap Activation** is unticked in Settings.
3. To enable, tick the checkbox and click **SAVE CONFIG**.

---

## 7. How to enable Safe Mode

1. In Settings $\rightarrow$ **AUDIO / VOICE**, tick the **Enable Safe Mode (Confirm every command)** checkbox.
2. Save Config.
3. Speak any command (e.g. "Open Chrome").
4. JARVIS will always ask: `"Did you mean open Chrome, Sir?"`
5. Speak `"Yes"` or `"Yeah"` to execute, or `"No"` to cancel.

---

## 8. Guided Voice Calibration Wizard

1. If you have an Indian/Tamil-accented English, standard Whisper might transcribe commands differently (e.g. `"open chrome"` as `"open crumb"`).
2. Click **LAUNCH VOICE CALIBRATION WIZARD** in settings.
3. Read the 8 phrases aloud.
4. If a phrase is misheard, the wizard automatically records the misheard raw transcription and binds it as a personal pronunciation alias for that command.
5. Once complete, these personal mappings override generic fuzzy matching!
