import os
import re
import queue
import time
import threading
import wave
import numpy as np
import sounddevice as sd
from difflib import SequenceMatcher
from core.event_bus import bus
from core.logger import logger
from core.config import config

# ===========================================================================
# TEMPORARY DEBUGGING FEATURE: Session-wide audio recording
# ===========================================================================
DEBUG_SESSION_RECORDING = True
DEBUG_RECORDING_DIR = r"d:\JARVIS M7\debug_recordings"

class SessionAudioRecorder:
    def __init__(self):
        self.wav_file = None
        self.filename = None

    def start_session(self):
        if not DEBUG_SESSION_RECORDING:
            return
        try:
            os.makedirs(DEBUG_RECORDING_DIR, exist_ok=True)
            timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")
            self.filename = os.path.join(DEBUG_RECORDING_DIR, f"session_{timestamp}.wav")
            self.wav_file = wave.open(self.filename, "wb")
            self.wav_file.setnchannels(1)
            self.wav_file.setsampwidth(2) # 16-bit PCM
            self.wav_file.setframerate(16000)
            logger.info(f"[DEBUG] Started session recording: {self.filename}")
        except Exception as e:
            logger.error(f"[DEBUG] Failed to start session recording: {e}")

    def write_chunk(self, chunk):
        if not DEBUG_SESSION_RECORDING or self.wav_file is None:
            return
        try:
            # chunk is float32 numpy array. Convert to 16-bit PCM bytes
            audio_data = (chunk * 32767).astype(np.int16)
            self.wav_file.writeframes(audio_data.tobytes())
        except Exception as e:
            logger.error(f"[DEBUG] Failed to write session chunk: {e}")

    def stop_session(self):
        if not DEBUG_SESSION_RECORDING or self.wav_file is None:
            return
        try:
            self.wav_file.close()
            logger.info(f"[DEBUG] Stopped and saved session recording: {self.filename}")
        except Exception as e:
            logger.error(f"[DEBUG] Failed to stop session recording: {e}")
        finally:
            self.wav_file = None
            self.filename = None

try:
    from faster_whisper import WhisperModel
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False

# ---------------------------------------------------------------------------
# Wake phrase matching — canonical forms and accent/STT variant lists
# ---------------------------------------------------------------------------

# Canonical wake phrases JARVIS accepts as definitive matches
WAKE_PHRASES = [
    "jarvis",
    "hey jarvis",
    "wake up jarvis",
    "hello jarvis",
]

# All accent / STT mishear variants — treated as exact matches when found in text.
# Expanding for Indian-English common mishearings: jollis, javish, jarvish, jar wish
FUZZY_VARIANTS = [
    # Single-word Jarvis variants
    "javis", "jarves", "charvis", "jaavas", "jarvez", "jarvas",
    "javish", "jarvish", "jollis", "jarviz", "jarfish", "jarvi",
    "jar vis", "jar fis", "jar face", "jar miss", "jar vice",
    # wake-up + variant
    "wake up jervis", "wake up javis", "wake up javish",
    "wake up jarvish", "wake up jollis", "wake up jar wish",
    "wake up jarviz", "wake up jarves", "wake up jaarvis",
    "wake up service", "wake up jars", "wake up jealous",
    # hey + variant
    "hey jervis", "hey javis", "hey javish",
    "hey jarvish", "hey jollis", "hey jar wish",
    "hey jarviz", "hey charvis",
    # jar wish as two words
    "jar wish",
]

# Words that must NOT trigger wake even if they score high on fuzzy
REJECT_WORDS = {
    "hope", "yes", "jobless", "mewd", "okay", "no", "yeah",
    "welcome", "goodbye", "hello", "ciao", "mutual", "knowledge",
    "julius", "travis", "paris", "hollis",
}

# Fuzzy ratio threshold for full-phrase wake matching
WAKE_FUZZY_THRESHOLD = 0.80

# Fuzzy ratio threshold for single-word "is this a Jarvis-like word?" check
WAKE_WORD_FUZZY_THRESHOLD = 0.65


def is_wake_phrase(transcription: str) -> tuple[bool, str]:
    """
    Check if transcription matches a wake phrase using exact + fuzzy matching.

    Returns:
        (matched: bool, canonical: str)
        `canonical` is the matched WAKE_PHRASES entry (or variant label) for logging.
        If not matched, canonical is an empty string.

    Pass order (reject-words checked first, wins over ALL fuzzy passes):
        1. Exact canonical phrase substring
        2. Exact variant / mishear substring
        3. Full-phrase SequenceMatcher fuzzy (threshold WAKE_FUZZY_THRESHOLD)
        4. Per-word fuzzy against 'jarvis' (threshold WAKE_WORD_FUZZY_THRESHOLD)
           — reject words are skipped INSIDE this loop too.
    """
    text = transcription.lower().strip()
    # Remove common punctuation
    text = re.sub(r"[.,!?;:'\"]+", "", text).strip()

    if not text or len(text) < 3:
        return False, ""

    # Reject known false positives — checked BEFORE any fuzzy pass
    all_words = text.split()
    word_set = set(all_words)
    if word_set.issubset(REJECT_WORDS):
        logger.info(f"Wake phrase rejected: raw='{text}', reason='reject word'")
        return False, ""

    # ---- Pass 1: Exact canonical phrase substring check ----
    for phrase in WAKE_PHRASES:
        if phrase in text:
            logger.info(
                f"Wake phrase matched: raw='{text}', canonical='{phrase}', method='exact'"
            )
            return True, phrase

    # ---- Pass 2: Exact variant / mishear substring check ----
    for variant in FUZZY_VARIANTS:
        if variant in text:
            logger.info(
                f"Wake phrase matched: raw='{text}', canonical='wake up jarvis', method='variant'"
            )
            return True, "wake up jarvis"

    # ---- Pass 3: SequenceMatcher fuzzy on full text vs each wake phrase ----
    # Ensure length/word constraint to prevent false wake triggers
    has_wake_context = any(w in all_words for w in ["wake", "hey", "hello", "hi", "up"])
    
    for phrase in WAKE_PHRASES:
        ratio = SequenceMatcher(None, text, phrase).ratio()
        if ratio >= WAKE_FUZZY_THRESHOLD:
            if len(text) < 4:
                continue
            if len(all_words) > 2 and not has_wake_context:
                logger.info(f"Wake check dismissed: raw='{text}', reason='fuzzy wake without wake context'")
                return False, ""
            logger.info(
                f"Wake phrase matched: raw='{text}', canonical='{phrase}', "
                f"method='fuzzy', score={ratio:.2f}"
            )
            return True, phrase

    # ---- Pass 4: Per-word fuzzy against 'jarvis' ----
    for word in all_words:
        if len(word) < 4:
            continue
        if word in REJECT_WORDS:          # per-word reject guard
            continue
        ratio = SequenceMatcher(None, word, "jarvis").ratio()
        if ratio >= WAKE_WORD_FUZZY_THRESHOLD:
            if len(all_words) > 2 and not has_wake_context:
                logger.info(f"Wake check dismissed: raw='{text}', reason='fuzzy wake without wake context'")
                return False, ""
            logger.info(
                f"Wake phrase matched: raw='{text}', canonical='jarvis', "
                f"method='word_fuzzy', score={ratio:.2f} (word='{word}')"
            )
            return True, "jarvis"

    logger.info(f"Wake check dismissed: raw='{text}', reason='no match'")
    return False, ""


class AudioService(threading.Thread):
    """
    Core audio listener with strict state-gated processing.
    
    Audio frames are processed differently depending on current engine state:
    - PASSIVE_WAKE_LISTENING: wake phrase detection + optional clap detection
    - ACTIVE_COMMAND_LISTENING: command recording with VAD
    - All other states: frames are ignored (only mic level sent to GUI)
    
    Self-hearing prevention: frames are dropped while TTS is active or in cooldown.
    """
    _instance = None
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = AudioService()
        return cls._instance

    def __init__(self):
        super().__init__()
        self.daemon = True
        self.sample_rate = 16000
        self.chunk_size = 1024
        self.audio_queue = queue.Queue()
        self.session_recorder = SessionAudioRecorder()
        
        # State tracking (mirrors engine state via event bus)
        self.current_state = "INITIALIZING"
        self.current_stream = None
        self.stream_active = True
        self.active_sample_rate = 16000
        self.is_suspended = False
        self.suspend_event = threading.Event()
        
        # Ambient noise calibration
        self.ambient_rms = 0.01
        self.calibrated = False
        self.calibration_samples = []
        
        # Command recording
        self.command_buffer = []
        self.command_has_speech = False
        self.silence_counter = 0
        
        # Double clap detection
        self.clap_history = []   # list of (timestamp, rms) for spike analysis
        self.last_clap_wake_time = 0.0
        
        # Voice wake phrase parameters
        self.wake_voice_buffer = []
        self.is_transcribing_wake = False
        self.is_collecting_wake = False
        self.wake_silence_counter = 0
        
        # TTS Interruption parameters (entirely separate from wake/command)
        self.interrupt_voice_buffer = []
        self.interrupt_pre_roll_buffer = []
        self.is_collecting_interrupt = False
        self.interrupt_silence_counter = 0
        self.is_transcribing_interrupt = False
        
        self.pre_roll_buffer = []
        self.last_raw_rms = 0.0
        self.last_avg_rms = 0.0
        self.last_peak_val = 0.0
        self.last_duration = 0.0
        self.last_diagnostics_warning = None
        
        # Connect to event bus
        bus.state_changed.connect(self.on_state_changed)

    # -- Configuration helpers -----------------------------------------------
    @property
    def silence_threshold(self):
        """Dynamic silence threshold based on ambient noise calibration."""
        base = float(config.get("command_sensitivity", "0.015"))
        # At least 3.5x ambient noise, but not less than base
        return max(base, self.ambient_rms * 3.5)
    
    @property
    def wake_trigger_threshold(self):
        # At least 4.0x ambient noise, but not less than base sensitivity
        return max(self.ambient_rms * 4.0, float(config.get("wake_sensitivity", "0.03")))
    
    @property
    def wake_word_enabled(self):
        return config.get("wake_word_enabled", "true").lower() == "true"

    @property
    def clap_enabled(self):
        return config.get("clap_wake_enabled", "false").lower() == "true"
    
    @property
    def silence_timeout_chunks(self):
        """Number of consecutive silent chunks before ending command recording (~1s)."""
        ms = int(config.get("silence_timeout_ms", "1000"))
        chunk_duration_ms = (self.chunk_size / self.sample_rate) * 1000
        return max(8, int(ms / chunk_duration_ms))
    
    @property
    def min_command_chunks(self):
        """Minimum number of chunks for a valid command."""
        min_sec = float(config.get("minimum_command_duration_seconds", "0.8"))
        return max(4, int(min_sec * self.sample_rate / self.chunk_size))
    
    @property
    def max_command_chunks(self):
        """Maximum command recording duration."""
        max_sec = float(config.get("maximum_command_duration_seconds", "15"))
        return int(max_sec * self.sample_rate / self.chunk_size)


    # -- State sync ----------------------------------------------------------
    def on_state_changed(self, state):
        old = self.current_state
        self.current_state = state

        if state in ("SESSION_LISTENING", "ACTIVE_COMMAND_LISTENING"):
            # Reset command recording state for both session and legacy active mode
            self.command_buffer = []
            self.pre_roll_buffer = []
            self.command_has_speech = False
            self.silence_counter = 0
            # Cancel any in-progress wake collection
            self.is_collecting_wake = False
            self.wake_voice_buffer = []
            logger.info(f"Command listening active ({state}). Waiting for user command.")
            
            # Start continuous debug recording session if not already started
            if self.session_recorder.wav_file is None:
                self.session_recorder.start_session()

        elif state == "PASSIVE_WAKE_LISTENING":
            # Reset wake collection state
            self.is_collecting_wake = False
            self.wake_voice_buffer = []
            self.wake_silence_counter = 0

    # -- Audio callback & stream management ----------------------------------
    def audio_callback(self, indata, frames, time_info, status):
        if status:
            logger.debug(f"Audio stream status: {status}")
            
        # Apply input gain boost if set in dB
        gain_db = float(config.get("input_gain_boost_db", "0"))
        if gain_db != 0:
            gain_factor = 10 ** (gain_db / 20.0)
            indata = indata * gain_factor
            
        # Real-time resampling if native rate differs from 16000Hz
        if self.active_sample_rate != self.sample_rate:
            xp = np.linspace(0, 1, len(indata))
            x = np.linspace(0, 1, self.chunk_size)
            resampled = np.interp(x, xp, indata.flatten()).astype(np.float32).reshape(-1, 1)
            self.audio_queue.put(resampled)
        else:
            self.audio_queue.put(indata.copy())

    def select_best_microphone(self):
        """Intelligent Microphone Selection — see previous implementation."""
        devices = sd.query_devices()
        hostapis = sd.query_hostapis()
        
        input_devices = []
        for idx, dev in enumerate(devices):
            if dev.get("max_input_channels", 0) > 0:
                backend = hostapis[dev.get("hostapi")]["name"]
                input_devices.append({
                    "index": idx, "name": dev.get("name"),
                    "backend": backend, "max_input_channels": dev.get("max_input_channels")
                })
        if not input_devices:
            raise RuntimeError("No input audio recording devices found on this system.")
        
        # Priority 1: User-configured device by index first, then name/backend
        saved_index = config.get("selected_microphone_index")
        if saved_index is not None:
            try:
                idx = int(saved_index)
                for dev in input_devices:
                    if dev["index"] == idx:
                        return dev["index"], dev["name"], dev["backend"]
            except ValueError:
                pass

        saved_name = config.get("mic_device_name")
        saved_backend = config.get("mic_device_backend")
        if saved_name:
            for dev in input_devices:
                if dev["name"] == saved_name and dev["backend"] == saved_backend:
                    return dev["index"], dev["name"], dev["backend"]
            logger.warn(f"Configured mic '{saved_name}' ({saved_backend}) not found. Auto-selecting.")
        
        # Priority 2: Windows default (if not virtual)
        try:
            default_idx = sd.default.device[0]
            if 0 <= default_idx < len(devices):
                d = devices[default_idx]
                name = d.get("name")
                backend = hostapis[d.get("hostapi")]["name"]
                virtuals = ["wo mic", "audiorelay", "virtual mic", "stereo mix", "loopback", "steam", "nvidia",
                            "sound mapper", "microsoft sound mapper"]
                if not any(v in name.lower() for v in virtuals):
                    return default_idx, name, backend
        except Exception:
            pass
        
        # Priority 3: Score-based selection
        virtuals = ["wo mic", "audiorelay", "virtual mic", "stereo mix", "loopback", "steam", "nvidia",
                    "sound mapper", "microsoft sound mapper"]
        scored = []
        for dev in input_devices:
            nl = dev["name"].lower()
            score = -100 if any(v in nl for v in virtuals) else 0
            if "intel" in nl or "smart sound" in nl: score += 50
            if "microphone array" in nl: score += 30
            if "built-in" in nl or "internal" in nl: score += 20
            if "conexant" in nl or "realtek" in nl: score += 15
            if dev["backend"] == "Windows WASAPI": score += 10
            scored.append((score, dev))
        scored.sort(key=lambda x: x[0], reverse=True)
        best = scored[0][1]
        logger.info(f"Auto-selected mic: {best['name']} ({best['backend']}) [Score: {scored[0][0]}]")
        return best["index"], best["name"], best["backend"]

    def run(self):
        logger.info("Always-listening microphone thread initialized.")
        self.stream_active = True
        
        while self.stream_active:
            if self.is_suspended:
                self.suspend_event.wait(timeout=0.5)
                continue

            try:
                device_idx, device_name, backend_name = self.select_best_microphone()
                device_info = sd.query_devices(device_idx)
                
                self.active_sample_rate = self.sample_rate
                stream_rate = self.sample_rate
                default_rate = int(device_info.get("default_samplerate", 16000))
                
                try:
                    self.current_stream = sd.InputStream(
                        samplerate=self.sample_rate, channels=1,
                        callback=self.audio_callback, blocksize=self.chunk_size,
                        dtype='float32', device=device_idx
                    )
                except Exception:
                    logger.warn(f"Sample rate {self.sample_rate}Hz unsupported. Falling back to {default_rate}Hz.")
                    self.active_sample_rate = default_rate
                    stream_rate = default_rate
                    stream_blocksize = int(self.chunk_size * (default_rate / self.sample_rate))
                    self.current_stream = sd.InputStream(
                        samplerate=default_rate, channels=1,
                        callback=self.audio_callback, blocksize=stream_blocksize,
                        dtype='float32', device=device_idx
                    )
                
                logger.info(
                    f"\nSelected microphone:\n{device_name}\n\n"
                    f"Index: {device_idx}\n\nBackend: {backend_name}\n\n"
                    f"Sample Rate: {stream_rate} Hz\n"
                )
                bus.console_log.emit("INFO", f"Active Mic: {device_name}")
                bus.system_stats_updated.emit({"active_mic": device_name})
                
                with self.current_stream:
                    logger.info("Listening...")
                    # Ambient noise calibration (2 seconds) - skip if already calibrated to preserve noise floor
                    if not self.calibrated:
                        self._calibrate_ambient()
                    else:
                        logger.info("Resuming listening without recalibrating ambient noise floor.")
                    
                    while self.current_stream is not None:
                        try:
                            chunk = self.audio_queue.get(timeout=0.1)
                            self.process_audio_chunk(chunk)
                        except queue.Empty:
                            pass
            except Exception as e:
                logger.error(f"Audio stream error: {e}", exc_info=True)
                bus.console_log.emit("ERROR", f"Microphone error: {e}")
                time.sleep(3.0)

    def _calibrate_ambient(self):
        """Sample 2 seconds of ambient noise to establish a noise floor."""
        logger.info("Calibrating ambient noise level (2 seconds)...")
        samples = []
        deadline = time.time() + 2.0
        while time.time() < deadline:
            try:
                chunk = self.audio_queue.get(timeout=0.1)
                rms = np.sqrt(np.mean(chunk**2))
                samples.append(rms)
            except queue.Empty:
                pass
        if samples:
            self.ambient_rms = np.mean(samples)
            self.calibrated = True
            logger.info(f"Ambient noise calibration complete. Noise floor RMS: {self.ambient_rms:.6f}")
        else:
            self.ambient_rms = 0.01
            logger.warn("Ambient calibration failed (no samples). Using default noise floor.")

    def restart_stream(self):
        """Close current stream; the run() loop will re-open with updated config."""
        logger.info("Re-initializing microphone device stream...")
        
        if self.current_stream:
            try:
                stream = self.current_stream
                self.current_stream = None
                stream.stop()
                stream.close()
            except Exception as e:
                logger.error(f"Error stopping stream: {e}")
        while not self.audio_queue.empty():
            try: self.audio_queue.get_nowait()
            except queue.Empty: break

    def suspend_listening(self):
        """Temporarily suspend microphone stream for live monitor test."""
        if not self.is_suspended:
            logger.info("Suspending main always-listening microphone thread...")
            self.is_suspended = True
            self.suspend_event.clear()
            self.restart_stream()

    def resume_listening(self):
        """Resume normal microphone wake-word listening."""
        if self.is_suspended:
            logger.info("Resuming main always-listening microphone thread...")
            self.is_suspended = False
            self.suspend_event.set()

    def stop(self):
        """Cleanly stop the audio service thread and stream."""
        logger.info("Stopping microphone audio service thread...")
        self.stream_active = False
        self.restart_stream()
        if hasattr(self, "session_recorder"):
            self.session_recorder.stop_session()

    # -- Core audio processing -----------------------------------------------
    def process_audio_chunk(self, chunk):
        rms = np.sqrt(np.mean(chunk**2))
        
        # Always send mic level to GUI
        bus.system_stats_updated.emit({"mic_level": float(rms)})

        # [TEMPORARY DEBUG] Record session chunk continuously during active session
        if hasattr(self, "session_recorder") and self.session_recorder.wav_file is not None:
            self.session_recorder.write_chunk(chunk)
        
        # ---- Self-hearing prevention & TTS interrupt detection ----
        from services.speech_service import speech
        if speech.is_speaking:
            if not speech.tts_cooldown_active:
                self._process_tts_interrupt(chunk, rms)
            return  # Drop frame silently for normal logic
        elif speech.tts_cooldown_active:
            return  # Drop frame silently
        
        state = self.current_state

        # ===== States where mic frames are actively processed =====
        if state in ("SESSION_LISTENING", "ACTIVE_COMMAND_LISTENING", "COMMAND_RECORDING"):
            self._process_command_recording(chunk, rms)

        elif state == "PASSIVE_WAKE_LISTENING":
            self._process_passive_wake(chunk, rms)

        # ===== All other states: ignore audio processing =====
        # (SPEAKING_ACKNOWLEDGEMENT, TRANSCRIBING_COMMAND, EXECUTING_COMMAND,
        #  SPEAKING_RESPONSE, COOLDOWN, SLEEPING, SHUTTING_DOWN, WAITING_FOR_CONFIRMATION)
        else:
            pass  # Frame dropped; mic level still sent to GUI

    def _process_command_recording(self, chunk, rms):
        """Record user command with voice activity detection and sliding pre-roll buffer."""
        if not self.command_has_speech:
            # Maintain a sliding pre-roll buffer (~300-500ms is 5 to 8 chunks)
            self.pre_roll_buffer.append(chunk)
            if len(self.pre_roll_buffer) > 8:
                self.pre_roll_buffer.pop(0)

            if rms > self.silence_threshold:
                self.command_has_speech = True
                dev_info = ""
                if self.current_stream:
                    try:
                        import sounddevice as sd
                        info = sd.query_devices(self.current_stream.device)
                        dev_info = f" (Device Index: {self.current_stream.device}, Name: {info['name']})"
                    except Exception:
                        dev_info = f" (Device Index: {self.current_stream.device})"
                logger.info(f"Command voice detected. RMS: {rms:.4f}{dev_info}")
                # Notify engine — it will transition ACTIVE_COMMAND_LISTENING → COMMAND_RECORDING
                # and cancel the command-listening timeout.
                bus.command_recording_started.emit()
                # Prepend the pre-roll chunks to self.command_buffer
                self.command_buffer.extend(self.pre_roll_buffer)
                self.pre_roll_buffer = []
                self.command_buffer.append(chunk)
                self.silence_counter = 0
        else:
            self.command_buffer.append(chunk)
            if rms < self.silence_threshold:
                self.silence_counter += 1
            else:
                self.silence_counter = 0

        # Periodic diagnostic (debug mode only)
        if len(self.command_buffer) % 20 == 0:
            logger.debug(f"Command recording — Chunks: {len(self.command_buffer)}, "
                         f"RMS: {rms:.4f}, Speech detected: {self.command_has_speech}, "
                         f"Silence counter: {self.silence_counter}/{self.silence_timeout_chunks}")

        # End conditions
        should_stop = False
        reason = ""

        if self.command_has_speech and self.silence_counter >= self.silence_timeout_chunks:
            should_stop = True
            reason = "Command silence detected"
        elif len(self.command_buffer) >= self.max_command_chunks:
            should_stop = True
            reason = "Maximum command duration reached"

        if should_stop:
            duration = len(self.command_buffer) * (self.chunk_size / self.sample_rate)
            logger.info(f"{reason}. Command recording stopped. Duration: {duration:.2f}s")

            if not self.command_has_speech or len(self.command_buffer) < self.min_command_chunks:
                logger.warning(f"Command audio too short or no speech detected. Duration: {duration:.2f}s. Ignoring.")
                bus.command_transcription_failed.emit("audio too short or no speech detected")
                return

            # Notify engine that silence ended the recording window
            bus.command_recording_stopped.emit()
            # Notify engine that STT pipeline is starting
            bus.command_transcription_started.emit()
            buffer_copy = list(self.command_buffer)
            self.command_buffer = []
            self.command_has_speech = False
            threading.Thread(target=self._transcribe_command, args=(buffer_copy,), daemon=True).start()

    def _process_passive_wake(self, chunk, rms):
        """Handle wake phrase detection and optional clap detection."""
        
        # A. Double Clap Detection (only if enabled)
        if self.clap_enabled:
            self._check_clap(rms)
        
        # B. Voice Wake Phrase Detection
        if self.wake_word_enabled and rms > self.wake_trigger_threshold and not self.is_transcribing_wake:
            if not self.is_collecting_wake:
                self.is_collecting_wake = True
                self.wake_voice_buffer = []
                self.wake_silence_counter = 0
                logger.info(f"Voice activity detected in passive mode. RMS: {rms:.4f}")
            
        if self.wake_word_enabled and self.is_collecting_wake:
            self.wake_voice_buffer.append(chunk)
            
            if rms < self.wake_trigger_threshold:
                self.wake_silence_counter += 1
            else:
                self.wake_silence_counter = 0
            
            wake_silence_limit = 15  # ~1.0s of silence
            wake_max_chunks = 50     # ~3.2s max
            
            if self.wake_silence_counter >= wake_silence_limit or len(self.wake_voice_buffer) >= wake_max_chunks:
                self.is_collecting_wake = False
                if len(self.wake_voice_buffer) > 8:
                    dur = len(self.wake_voice_buffer) * (self.chunk_size / self.sample_rate)
                    logger.info(f"Wake buffer complete. Duration: {dur:.2f}s. Transcribing...")
                    buf = list(self.wake_voice_buffer)
                    self.wake_voice_buffer = []
                    threading.Thread(target=self._check_wake_phrase, args=(buf,), daemon=True).start()

    def _check_clap(self, rms):
        """
        Improved double-clap detection.
        Requires two sharp spikes (≥4× ambient RMS) within 200-700ms with silence between.
        """
        now = time.time()
        clap_min_rms = max(0.25, self.ambient_rms * 4.0)
        
        # Cooldown after last successful clap wake
        if now - self.last_clap_wake_time < 8.0:
            return
        
        if rms > clap_min_rms:
            self.clap_history.append((now, rms))
        
        # Keep only recent entries (last 2 seconds)
        self.clap_history = [(t, r) for t, r in self.clap_history if now - t < 2.0]
        
        if len(self.clap_history) >= 2:
            t1, r1 = self.clap_history[-2]
            t2, r2 = self.clap_history[-1]
            dt = t2 - t1
            
            if 0.15 < dt < 0.70:
                logger.info(f"Double clap detected! Δt={dt:.2f}s, peaks=({r1:.3f}, {r2:.3f}), ambient={self.ambient_rms:.4f}")
                self.clap_history = []
                self.last_clap_wake_time = now
                bus.wake_detected.emit("clap")
            elif dt >= 0.70:
                # Too slow — clear the oldest
                self.clap_history = self.clap_history[-1:]

    # -- Wake phrase check ---------------------------------------------------
    def _check_wake_phrase(self, buffer):
        """
        Transcribe a short audio buffer using the lightweight wake model (tiny.en).
        This is intentionally separate from the command model to keep wake latency low.
        """
        if self.is_transcribing_wake:
            return
        # Extra state guard
        if self.current_state != "PASSIVE_WAKE_LISTENING":
            logger.debug(f"Wake transcription skipped — state is {self.current_state}")
            return
        try:
            self.is_transcribing_wake = True
            audio_data = np.concatenate(buffer, axis=0).flatten()

            # Use the dedicated tiny.en wake model (fast, minimal latency)
            from services.stt.wake_model_manager import wake_model_manager
            model = wake_model_manager.get_model()

            segments, info = model.transcribe(
                audio_data,
                beam_size=1,          # Fastest possible — wake doesn't need accuracy
                language="en",
                temperature=0,
                condition_on_previous_text=False,
                vad_filter=True,
            )
            transcription = " ".join([s.text for s in segments]).lower().strip()
            logger.info(f"Wake check transcription: '{transcription}'")

            matched, canonical = is_wake_phrase(transcription)
            if matched:
                # Final state guard before emitting
                if self.current_state == "PASSIVE_WAKE_LISTENING":
                    logger.info(f"Wake phrase candidate detected: '{transcription}' (canonical: '{canonical}')")
                    bus.wake_detected.emit("voice")
                else:
                    logger.debug(f"Wake matched but state changed to {self.current_state}. Ignoring.")
            else:
                logger.info(f"Wake check dismissed: '{transcription}'")

        except Exception as e:
            logger.error(f"Wake phrase check error: {e}")
            # Fallback: try the command model if wake model fails to load
            try:
                from services.stt.local_model_manager import local_model_manager
                model = local_model_manager.get_model()
                audio_data = np.concatenate(buffer, axis=0).flatten()
                segments, _ = model.transcribe(
                    audio_data, beam_size=1, language="en",
                    temperature=0, condition_on_previous_text=False, vad_filter=True,
                )
                transcription = " ".join([s.text for s in segments]).lower().strip()
                matched_fb, canonical_fb = is_wake_phrase(transcription)
                if matched_fb and self.current_state == "PASSIVE_WAKE_LISTENING":
                    logger.info(f"Wake fallback matched: '{transcription}' (canonical: '{canonical_fb}')")
                    bus.wake_detected.emit("voice")
            except Exception as fallback_err:
                logger.error(f"Wake fallback also failed: {fallback_err}")
        finally:
            self.is_transcribing_wake = False

    # -- Command transcription -----------------------------------------------
    def _transcribe_command(self, buffer):
        """
        Run STT on the recorded command buffer.
        Emits semantic bus signals only — never touches bus.state_changed directly.
        All engine state transitions happen on the main Qt thread via those signals.
        """
        if not buffer:
            logger.warning("Command buffer empty.")
            bus.command_transcription_failed.emit("empty command buffer")
            return

        # bus.command_transcription_started was already emitted by _process_command_recording
        # before this thread was started, so the engine is already in TRANSCRIBING_COMMAND.

        audio_data = np.concatenate(buffer, axis=0).flatten()
        duration = len(buffer) * (self.chunk_size / self.sample_rate)

        # Calculate chunk-based RMS to find the voiced segment's peak level (sliding 500ms window)
        chunk_rms_values = [np.sqrt(np.mean(c**2)) for c in buffer]
        window_size = min(8, len(chunk_rms_values))
        if window_size > 0:
            sliding_rms = []
            for i in range(len(chunk_rms_values) - window_size + 1):
                window_mean_square = np.mean([r**2 for r in chunk_rms_values[i:i+window_size]])
                sliding_rms.append(np.sqrt(window_mean_square))
            raw_rms = max(sliding_rms) if sliding_rms else 0.0
        else:
            raw_rms = 0.0

        avg_rms = np.sqrt(np.mean(audio_data**2))
        peak_val = np.max(np.abs(audio_data))

        # Pre-STT audio quality gate check (discard if raw_rms is close to calibrated ambient floor)
        rms_margin = raw_rms - self.ambient_rms
        if rms_margin < 0.025:
            logger.warning(
                f"Audio quality gate triggered: raw_rms ({raw_rms:.6f}) - ambient_rms ({self.ambient_rms:.6f}) "
                f"= {rms_margin:.6f} which is below min_margin 0.025. Skipping STT."
            )
            bus.console_log.emit("WARN", "Command skipped: audio level too close to noise floor")
            bus.command_transcription_failed.emit("audio too close to noise floor")
            return

        logger.info(
            f"\nCommand recording started\n"
            f"Original sample rate: {self.active_sample_rate}\n"
            f"Resampled sample rate: 16000\n"
            f"Command audio duration: {duration:.1f}s\n"
            f"Audio RMS: {avg_rms:.4f}\n"
            f"Peak level: {peak_val:.4f}\n"
        )

        # Safe audio volume processing & peak scaling
        orig_peak = float(np.max(np.abs(audio_data)))
        orig_rms = float(np.sqrt(np.mean(audio_data**2)))
        is_clipped = bool(orig_peak >= 0.98)
        audio_quality = 1.0

        if orig_peak > 1.0:
            # Overloaded/clipped input -> do NOT amplify, scale down safely
            audio_data = audio_data / orig_peak * 0.95
            clip_severity = orig_peak - 1.0
            audio_quality = max(0.3, 1.0 - clip_severity * 1.5)
            logger.warning(f"Audio clipping detected (peak: {orig_peak:.4f}). Scaled down to 0.95. Quality factor: {audio_quality:.2f}")
        elif orig_peak > 0.0 and orig_peak < 0.9:
            gain = min(0.9 / orig_peak, 2.5)
            audio_data = audio_data * gain

        audio_data = np.clip(audio_data, -1.0, 1.0)
        proc_peak = float(np.max(np.abs(audio_data)))
        proc_rms = float(np.sqrt(np.mean(audio_data**2)))

        logger.info(
            f"\nCommand audio processed:\n"
            f"Original RMS: {orig_rms:.4f} | Original Peak: {orig_peak:.4f} | Clipped: {is_clipped}\n"
            f"Processed RMS: {proc_rms:.4f} | Processed Peak: {proc_peak:.4f} | Quality factor: {audio_quality:.2f}\n"
        )

        # Store diagnostics parameters
        self.last_raw_rms = raw_rms
        self.last_avg_rms = proc_rms
        self.last_peak_val = proc_peak
        self.last_duration = duration

        transcription = ""
        try:
            logger.info("Running command transcription via provider manager...")
            import io
            import soundfile as sf
            wav_io = io.BytesIO()
            sf.write(wav_io, audio_data, 16000, format='WAV', subtype='PCM_16')
            wav_bytes = wav_io.getvalue()

            from services.stt.prompt_builder import stt_prompt_builder
            initial_prompt = stt_prompt_builder.build_prompt(
                mode="active_command",
                relevant_apps=["Google Chrome", "Visual Studio Code", "Notepad", "Settings"]
            )
            stt_lang = config.get("stt_language", "en")

            import time
            stt_start_time = time.monotonic()
            from services.stt.provider_manager import stt_manager
            logger.info(f"STT API Call initial_prompt payload: '{initial_prompt}'")
            stt_result = stt_manager.transcribe(
                wav_bytes,
                audio_format="wav",
                language=stt_lang,
                initial_prompt=initial_prompt
            )
            stt_latency = time.monotonic() - stt_start_time
            bus.system_stats_updated.emit({"stt_latency": round(stt_latency, 2)})
            
            raw_text = stt_result.text
            from services.phonetic_correction_service import phonetic_correction_service
            transcription = phonetic_correction_service.correct_transcription(raw_text)
            if transcription != raw_text:
                logger.info(f"Phonetic correction applied: '{raw_text}' -> '{transcription}'")
            else:
                logger.info(f"Raw transcription: '{transcription}' (via {stt_result.provider}) in {stt_latency:.2f}s")

            # Two-pass STT re-transcription logic for contact/call commands
            try:
                from skills.call_skill import CallSkill
                if CallSkill.has_call_intent_static(transcription):
                    target = CallSkill.extract_call_target_static(transcription)
                    if target:
                        from services.contacts_service import contacts_service
                        res = contacts_service.resolve_contact(target)
                        if res["status"] != "resolved":
                            logger.info(
                                f"First-pass STT calling intent target '{target}' did not resolve confidently "
                                f"(status={res['status']}). Performing second-pass phonetic STT..."
                            )
                            # Fetch all contact names (preferring display overrides)
                            with db.get_connection() as conn:
                                cursor = conn.cursor()
                                cursor.execute("SELECT COALESCE(display_override, name) FROM contacts")
                                all_contact_names = [row[0] for row in cursor.fetchall() if row[0]]
                            
                            # Find top 15 phonetically-plausible candidates using difflib.SequenceMatcher
                            candidates = []
                            target_clean = target.lower().strip()
                            for c_name in all_contact_names:
                                c_clean = c_name.lower().strip()
                                max_ratio = SequenceMatcher(None, target_clean, c_clean).ratio()
                                # Split and check individual tokens
                                tokens = re.split(r"[\s\-_&]+", c_clean)
                                for token in tokens:
                                    if len(token) >= 3:
                                        r = SequenceMatcher(None, target_clean, token).ratio()
                                        if r > max_ratio:
                                            max_ratio = r
                                candidates.append((c_name, max_ratio))
                            candidates.sort(key=lambda x: x[1], reverse=True)
                            top_names = [c[0] for c in candidates[:15]]
                            
                            # Build targeted second-pass prompt
                            second_biasing_names = []
                            for name in top_names:
                                words = re.split(r"[\s\-_&]+", name)
                                for w in words:
                                    cleaned = re.sub(r"[^\w]", "", w).strip()
                                    if cleaned.isalpha() and len(cleaned) >= 3 and cleaned not in second_biasing_names:
                                        second_biasing_names.append(cleaned)
                                        
                            second_prompt = (
                                "Jarvis desktop assistant command. "
                                "Common: open Chrome, open Notepad, open VS Code, exit app, screenshot, play/stop music, lock computer. "
                                "Transcribe clearly, including 'Jarvis' (or Jervis, Javis) at the start."
                            )
                            if second_biasing_names:
                                second_prompt += " Vocabulary: " + ", ".join(second_biasing_names) + "."
                            
                            logger.info(f"Second-pass STT initial_prompt: {second_prompt}")
                            stt_result_second = stt_manager.transcribe(
                                wav_bytes,
                                audio_format="wav",
                                language=stt_lang,
                                initial_prompt=second_prompt
                            )
                            raw_second = stt_result_second.text
                            transcription_second = phonetic_correction_service.correct_transcription(raw_second)
                            if transcription_second != raw_second:
                                logger.info(f"Second-pass phonetic correction applied: '{raw_second}' -> '{transcription_second}'")
                            else:
                                logger.info(f"Second-pass transcription: '{transcription_second}' (via {stt_result_second.provider})")
                            transcription = transcription_second
            except Exception as two_pass_err:
                logger.error(f"Two-pass STT re-transcription failed: {two_pass_err}", exc_info=True)

            # Two-pass STT re-transcription logic for raga commands
            try:
                from core.engine import JarvisEngine
                from skills.raga_skill import RagaSkill
                engine = JarvisEngine._instance
                if RagaSkill.has_raga_intent_static(transcription, engine=engine):
                    target = RagaSkill.extract_raga_target_static(transcription)
                    if target:
                        from services.ragas_service import ragas_service
                        res = ragas_service.resolve_raga(target)
                        if res["status"] == "no_match":
                            logger.info(
                                f"First-pass STT raga query target '{target}' did not resolve. "
                                f"Performing second-pass phonetic STT for ragas..."
                            )
                            with db.get_connection() as conn:
                                cursor = conn.cursor()
                                cursor.execute("SELECT name FROM ragas")
                                all_raga_names = [row[0] for row in cursor.fetchall() if row[0]]
                            candidates = []
                            target_clean = target.lower().strip()
                            for r_name in all_raga_names:
                                import unicodedata
                                normalized = unicodedata.normalize('NFKD', r_name)
                                ascii_name = "".join([c for c in normalized if not unicodedata.combining(c)])
                                r_clean = ascii_name.lower().strip()
                                max_ratio = SequenceMatcher(None, target_clean, r_clean).ratio()
                                tokens = re.split(r"[\s\-_&]+", r_clean)
                                for token in tokens:
                                    if len(token) >= 3:
                                        r = SequenceMatcher(None, target_clean, token).ratio()
                                        if r > max_ratio:
                                            max_ratio = r
                                candidates.append((ascii_name, max_ratio))
                            candidates.sort(key=lambda x: x[1], reverse=True)
                            top_names = [c[0] for c in candidates[:15]]
                            
                            second_biasing_names = []
                            for name in top_names:
                                words = re.split(r"[\s\-_&]+", name)
                                for w in words:
                                    cleaned = re.sub(r"[^\w]", "", w).strip()
                                    if cleaned.isalpha() and len(cleaned) >= 3 and cleaned not in second_biasing_names:
                                        second_biasing_names.append(cleaned)
                                        
                            second_prompt = (
                                "Music Space raga database search. "
                                "Transcribe music and raga terms clearly: arohana, avarohana, melakarta, scale, tradition."
                            )
                            if second_biasing_names:
                                second_prompt += " Vocabulary: " + ", ".join(second_biasing_names) + "."
                            
                            logger.info(f"Second-pass Raga STT initial_prompt: {second_prompt}")
                            stt_result_second = stt_manager.transcribe(
                                wav_bytes,
                                audio_format="wav",
                                language=stt_lang,
                                initial_prompt=second_prompt
                            )
                            raw_second = stt_result_second.text
                            transcription_second = phonetic_correction_service.correct_transcription(raw_second)
                            if transcription_second != raw_second:
                                logger.info(f"Second-pass raga phonetic correction applied: '{raw_second}' -> '{transcription_second}'")
                            else:
                                logger.info(f"Second-pass raga transcription: '{transcription_second}' (via {stt_result_second.provider})")
                            transcription = transcription_second
            except Exception as raga_two_pass_err:
                logger.error(f"Raga two-pass STT re-transcription failed: {raga_two_pass_err}", exc_info=True)
        except Exception as e:
            logger.error(f"All STT providers failed. Error: {e}")
            bus.console_log.emit("ERROR", "All STT providers failed.")
            bus.command_transcription_failed.emit(f"STT error: {e}")
            return

        if transcription:
            # Signal the engine with the transcribed text — it will route and execute.
            bus.command_transcription_completed.emit(transcription)
        else:
            logger.warning("Empty transcription. Reason: whisper returned no segments.")
            bus.command_transcription_failed.emit("empty transcription")

    def _process_tts_interrupt(self, chunk, rms):
        if self.is_transcribing_interrupt:
            return

        if not self.is_collecting_interrupt:
            # Maintain a sliding pre-roll buffer (~300-500ms is 5 to 8 chunks)
            self.interrupt_pre_roll_buffer.append(chunk)
            if len(self.interrupt_pre_roll_buffer) > 8:
                self.interrupt_pre_roll_buffer.pop(0)

            if rms > self.wake_trigger_threshold:
                self.is_collecting_interrupt = True
                # Prepend the pre-roll chunks to self.interrupt_voice_buffer
                self.interrupt_voice_buffer = list(self.interrupt_pre_roll_buffer)
                self.interrupt_pre_roll_buffer = []
                self.interrupt_silence_counter = 0
                logger.info(f"Voice activity detected during TTS. RMS: {rms:.4f}")
        else:
            self.interrupt_voice_buffer.append(chunk)
            
            if rms < self.wake_trigger_threshold:
                self.interrupt_silence_counter += 1
            else:
                self.interrupt_silence_counter = 0
            
            # ~1.0s of silence to mark end of utterance (15 chunks)
            if self.interrupt_silence_counter >= 15:
                self.is_collecting_interrupt = False
                buffer_copy = list(self.interrupt_voice_buffer)
                self.interrupt_voice_buffer = []
                
                # Check minimum duration to prevent clicks/spikes from transcribing (approx 0.6s)
                if len(buffer_copy) >= 4:
                    self.is_transcribing_interrupt = True
                    utterance_end_time = time.time()
                    threading.Thread(
                        target=self._transcribe_interrupt, 
                        args=(buffer_copy, utterance_end_time), 
                        daemon=True
                    ).start()
                else:
                    logger.debug("Interrupt audio too short, ignoring.")

    def _transcribe_interrupt(self, buffer, utterance_end_time):
        try:
            import io
            import soundfile as sf
            import numpy as np
            from services.stt.wake_model_manager import wake_model_manager
            
            audio_data = np.concatenate(buffer).flatten()
            model = wake_model_manager.get_model()
            
            audio_data = audio_data.astype(np.float32)
            
            logger.info("Transcribing interrupt audio buffer...")
            segments, info = model.transcribe(
                audio_data,
                beam_size=1,
                language="en",
                temperature=0.0,
                condition_on_previous_text=False,
                vad_filter=True
            )
            transcription = " ".join([s.text for s in segments]).strip()
            logger.info(f"Interrupt listener transcription: {transcription!r}")
            
            from services.speech_service import speech
            from services.conversation.echo_rejector import echo_rejector
            from services.tts.streaming_tts_queue import streaming_tts_queue
            
            req_id = getattr(streaming_tts_queue, "active_request_id", None)
            curr_sentence = getattr(speech, "current_spoken_sentence", "")
            recent_sentences = getattr(speech, "recent_spoken_sentences", [])

            is_echo_talk = echo_rejector.is_echo(
                transcription,
                curr_sentence,
                recent_sentences,
                request_id=req_id
            )

            if is_echo_talk:
                logger.info(f"Self-hearing echo discarded for transcript: '{transcription[:30]}...'")
                return

            from services.tts.provider_manager import tts_manager
            tts_manager.stop_speaking()
            
            latency = time.time() - utterance_end_time
            logger.info(f"INTERRUPT LATENCY: {latency:.4f} seconds from end of utterance to playback halt.")
            
            bus.speech_interrupted.emit()
        except Exception as e:
            logger.error(f"Error in _transcribe_interrupt: {e}", exc_info=True)
        finally:
            self.is_transcribing_interrupt = False

audio_service = AudioService.get_instance()
