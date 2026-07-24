import re
import time
import json
import os
import subprocess
from PyQt6.QtCore import QObject, QTimer, pyqtSlot, QThread, pyqtSignal
from difflib import SequenceMatcher
from core.event_bus import bus
from core.logger import logger
from core.config import config
from core.database import db
from services.speech_service import speech
from skills.manager import skill_manager
from core.trust_gate import TrustGate, ToolCall
from core.brain import brain
from services.acknowledgement_service import acknowledgement_service

def collapse_repeated_command(text: str) -> tuple[str, int]:
    original = text or ""
    cleaned = re.sub(r"[.!-]-", ".", original)
    cleaned = re.sub(r"\s-", " ", cleaned).strip()

    if not cleaned:
        return cleaned, 1

    def _similar(a: str, b: str, threshold: float = 0.82) -> bool:
        return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio() >= threshold

    # Split punctuation repeated phrases first.
    segments = [
        s.strip(" ,.;")
        for s in re.split(r"[,.;]-", cleaned)
        if s.strip(" ,.;")
    ]

    if len(segments) >= 2:
        first = segments[0]
        if all(_similar(first, s) for s in segments[1:]):
            logger.info(f'Repeated STT command collapsed: "{original}" -> "{first}" (count={len(segments)})')
            return first, len(segments)

    # Split repeated Jarvis-prefixed commands.
    # Only collapse when there is NO command body after the second occurrence
    # (i.e. the user genuinely said "Jarvis Jarvis" with nothing meaningful after it).
    JARVIS_PREFIX_PATTERN = r"(jarvis|jervis|javis|javish|jollis|jarvish|jar wish|jarves|jarvas|charvis|service|jar miss|jar vice|jarviz|jar fis|jar face|jarfish|jar vis|jarvi)"
    pattern = re.compile(rf"\b{JARVIS_PREFIX_PATTERN}\b", re.IGNORECASE)
    wake_matches = list(pattern.finditer(cleaned))

    if len(wake_matches) >= 2:
        second_end = wake_matches[1].end()
        after_second = cleaned[second_end:].strip(" ,.;")
        if not after_second:
            # Nothing after the second wake word â€” true double-Jarvis mishear, collapse to first segment
            first_start = wake_matches[0].start()
            second_start = wake_matches[1].start()
            first_command = cleaned[first_start:second_start].strip(" ,.;")
            if first_command:
                logger.info(f'Repeated STT command collapsed: "{original}" -> "{first_command}" (count={len(wake_matches)})')
                return first_command, len(wake_matches)
        else:
            # Command content follows the second wake word â€” strip only the leading "Jarvis Jarvis"
            # and return the command body after the second occurrence.
            logger.info(f'Repeated wake-word with command body: "{original}" -> "{after_second}" (keeping command)')
            return after_second, 1

    return cleaned, 1

def parse_file_creation(command: str):
    """
    Parses a command string for file-creation intents.
    Returns a dict with {"filename": str, "location": str} or None.
    """
    cmd = command.lower().strip()

    # Check if the command has call intent (prevents misrouting calling to file creation)
    from skills.call_skill import CallSkill
    if CallSkill.has_call_intent_static(command):
        return None

    # Unified regex pattern supporting action verbs, optional file indicators, and locations
    pattern = r"\b(-:create|make|write|generate)\b\s-(-:a\s-)-(-:new\s-)-(-:text\s-)-(-:file\s-)-(-:called\s-)-(.--)(-:\s-(-:in|on|at)\s-(desktop|documents|downloads|workspace|current directory|current folder))-$"

    match = re.search(pattern, cmd)
    if match:
        filename = match.group(1).strip()
        location = match.group(2).strip() if (len(match.groups()) > 1 and match.group(2)) else "workspace"

        # Default to .txt if no extension is present
        if "." not in filename:
            filename += ".txt"

        return {"filename": filename, "location": location}

    return None

def validate_filename(filename: str) -> bool:
    # Reject path separators or relative paths
    if "/" in filename or "\\" in filename or ".." in filename:
        return False
    # Reject Windows illegal characters
    illegal_chars = ['<', '>', ':', '"', '|', '-', '*']
    if any(c in filename for c in illegal_chars):
        return False
    return True

def map_directory(location: str) -> str:
    loc = location.lower().strip()
    user_home = os.path.expanduser("~")

    if loc == "desktop":
        return os.path.join(user_home, "Desktop")
    elif loc == "documents":
        return os.path.join(user_home, "Documents")
    elif loc == "downloads":
        return os.path.join(user_home, "Downloads")
    else:
        # Fetch configurable workspace directory
        return config.get("workspace_dir", os.getcwd())

EXIT_PHRASES = [
    "Shutting down fully, {salutation}. Have a good day.",
    "Powering down, {salutation}. Until next time.",
    "Systems going offline, {salutation}. Take care."
]

SLEEP_PHRASES = [
    "Going passive, {salutation}.",
    "Standing by, {salutation}.",
    "Entering passive mode, {salutation}. I'll be listening."
]

def get_weather_summary() -> str:
    import urllib.request
    lat = config.get("weather_latitude")
    lon = config.get("weather_longitude")
    city = config.get("weather_city")

    if not lat or not lon:
        try:
            req = urllib.request.Request("http://ip-api.com/json", headers={"User-Agent": "JARVIS/7.0"})
            with urllib.request.urlopen(req, timeout=3.0) as response:
                loc_data = json.loads(response.read().decode('utf-8'))
                lat = loc_data.get("lat")
                lon = loc_data.get("lon")
                if not city:
                    city = loc_data.get("city")
        except Exception as e:
            logger.warning(f"Could not retrieve IP-based location: {e}")

    if not lat or not lon:
        lat, lon = 13.0827, 80.2707
        if not city:
            city = "Chennai"

    url = f"https://api.open-meteo.com/v1/forecast-latitude={lat}&longitude={lon}&current_weather=true"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "JARVIS/7.0"})
        with urllib.request.urlopen(req, timeout=3.0) as response:
            data = json.loads(response.read().decode('utf-8'))
            curr = data.get("current_weather", {})
            temp = curr.get("temperature")
            wcode = curr.get("weathercode", 0)

            wmo_codes = {
                0: "clear skies",
                1: "mainly clear skies", 2: "partly cloudy skies", 3: "overcast skies",
                45: "foggy weather", 48: "depositing rime fog",
                51: "light drizzle", 53: "moderate drizzle", 55: "dense drizzle",
                61: "slight rain", 63: "moderate rain", 65: "heavy rain",
                80: "slight rain showers", 81: "moderate rain showers", 82: "violent rain showers",
                95: "thunderstorms"
            }
            condition = wmo_codes.get(wcode, "clear skies")
            temp_int = int(round(temp)) if temp is not None else 22
            return f"the weather in {city} is {temp_int} degrees with {condition}"
    except Exception as e:
        logger.warning(f"Could not retrieve weather details: {e}")
        return None

def get_system_status_summary() -> str:
    try:
        import psutil

        # 1. Battery Check
        try:
            battery = psutil.sensors_battery()
            if battery is not None:
                percent = battery.percent
                power_plugged = battery.power_plugged
                if percent < 20 and not power_plugged:
                    return f"your battery is at {percent} percent, you may want to plug in"
        except Exception as e:
            logger.warning(f"Error checking battery: {e}")

        # 2. CPU Check
        try:
            cpu_pct = psutil.cpu_percent(interval=0.5)
            if cpu_pct > 85:
                return f"your CPU usage is currently high, at {int(cpu_pct)} percent"
        except Exception as e:
            logger.warning(f"Error checking CPU: {e}")

        # 3. Disk Check
        try:
            import platform
            path = "C:\\" if platform.system() == "Windows" else "/"
            disk = psutil.disk_usage(path)
            if disk.percent > 90:
                return f"your main drive is nearly full, at {int(disk.percent)} percent used"
        except Exception as e:
            logger.warning(f"Error checking disk: {e}")

    except Exception as e:
        logger.warning(f"Error retrieving system status: {e}")

    return None

# ---------------------------------------------------------------------------
# Session prefix variants â€” any transcription starting with one of these
# (after lowercasing) is accepted as a valid in-session command.
#
# Covers common Indian-English STT mishearings of "Jarvis":
#   javish / jarvish / jollis / jar wish / jarviz / jar fis / jar face
# ---------------------------------------------------------------------------
SESSION_COMMAND_PREFIXES = [
    "jarvis",
    "jervis",
    "javis",
    "charvis",
    "service",
    "jar miss",
    "jar vice",
    "jarves",
    "jarvas",
    # Extended accent / STT error variants
    "javish",
    "jollis",
    "jar wish",
    "jarvish",
    "jarviz",
    "jar fis",
    "jar face",
    "jarfish",
    "jar vis",
    "jarvi",
]

# Fuzzy ratio threshold for prefix matching (0.0â€“1.0).
# Applied to the FIRST word(s) of a transcription when no exact match is found.
SESSION_PREFIX_FUZZY_THRESHOLD = 0.75

# ---------------------------------------------------------------------------
# Known desktop assistant commands and accent/mishear variants
# ---------------------------------------------------------------------------
KNOWN_COMMANDS = {
    "open chrome": [
        "open chrome", "launch chrome", "start chrome", "chrome open", "open google",
        "browser open", "open crumb", "open grown", "open chrome browser",
    ],
    "open notepad": [
        "open notepad", "start notepad", "create note", "note pad open", "open no pad",
        "open note pad", "launch notepad", "open note bad", "open node pad",
    ],
    "open vs code": [
        "open vs code", "open visual studio code", "start coding", "open code editor",
        "open visual studio court", "open vs court",
    ],
    "take screenshot": [
        "take screenshot", "take screen shot", "capture screen", "capture screenshot",
    ],
    "increase volume": [
        "increase volume", "volume up", "raise volume", "sound up", "increase value",
    ],
    "decrease volume": [
        "decrease volume", "volume down", "lower volume", "sound down", "decrease value",
    ],
    "mute volume": [
        "mute volume", "mute sound", "turn off sound",
    ],
    "open music space": [
        "open music space", "go to music space", "music space", "open music",
    ],
    "exit music space": [
        "exit music space", "close music space", "exit music", "close music",
    ],
}

# Keywords indicating the user was attempting a system command
COMMAND_KEYWORDS = [
    "open", "launch", "start", "screenshot", "volume", "sound", "shutdown",
    "exit", "close", "restart", "sleep", "lock", "calculator", "notepad",
    "terminal", "prompt", "chrome", "code", "delete", "format", "overwrite",
]


def get_personal_corrections():
    """Load user voice calibration correction mappings from configuration."""
    try:
        val = config.get("personal_corrections")
        if val:
            return json.loads(val)
    except Exception as e:
        logger.error(f"Error loading personal corrections: {e}")
    return {
        "open chrome": [],
        "open notepad": [],
        "open vs code": [],
        "take screenshot": [],
        "increase volume": [],
        "decrease volume": [],
        "mute volume": [],
        "open music space": [],
        "exit music space": [],
    }


def is_destructive(cmd: str) -> bool:
    """Detect if a command contains destructive or critical actions."""
    c = cmd.lower()
    destructive_keywords = [
        "delete", "format", "overwrite", "remove", "terminal", "shell",
        "lock", "unlock", "security", "destroy",
        # PC-lifecycle phrasings
        "shutdown pc", "shutdown computer", "shut down pc", "shut down computer",
        "restart pc", "restart computer", "reboot pc", "reboot computer",
        "power off", "turn off computer", "turn off pc",
    ]
    return any(re.search(rf"\b{re.escape(kw)}\b", c) for kw in destructive_keywords)



# ---------------------------------------------------------------------------
# CommandWorker â€” background execution thread
# ---------------------------------------------------------------------------
class CommandWorker(QThread):
    """
    Background worker thread to execute commands.
    Ensures heavy operations (AI calls, shell execution) never freeze the PyQt6 UI.

    Thread-safety: ONLY emits signals. Never calls engine.transition_to() directly.
    The engine receives signals and performs all state transitions on the main Qt thread.
    """
    started_executing = pyqtSignal()
    response_ready    = pyqtSignal(str)
    failed            = pyqtSignal(str)

    def __init__(self, command, engine, fallback_only=False, request_id: str | None = None):
        super().__init__()
        self.command = command
        self.engine = engine
        self.fallback_only = fallback_only
        self.request_id = request_id
        from core.telemetry import pipeline_timer
        self.telemetry_context = pipeline_timer.get_thread_context()

    def run(self):
        from core.telemetry import pipeline_timer
        if self.telemetry_context is not None:
            pipeline_timer.set_thread_context(self.telemetry_context)
        try:
            import time as _time
            nlu_start = _time.monotonic()
            self.started_executing.emit()
            response = self.engine.route_and_execute(self.command, fallback_only=self.fallback_only)

            import inspect
            if inspect.isgenerator(response):
                import re
                from core.database import db
                from core.telemetry import pipeline_timer

                self.engine.streamed_fallback_active = True

                from services.tts.sentence_buffer import SentenceBuffer
                from services.tts.streaming_tts_queue import streaming_tts_queue
                from services.speech_service import speech as _speech_svc

                # Preserve original command request_id through the entire stream lifecycle
                stream_req_id = self.request_id
                if stream_req_id:
                    _speech_svc.begin_request(stream_req_id)
                else:
                    streaming_tts_queue.start_new_request(request_id=stream_req_id)
                sentence_buffer = SentenceBuffer(
                    minimum_chars=int(config.get("tts_sentence_min_chars", 24)),
                    maximum_chars=int(config.get("tts_sentence_max_chars", 220)),
                    first_sentence_minimum_chars=int(config.get("tts_first_sentence_min_chars", 18))
                )

                stream_buffer = ""
                full_response = ""
                first_token_received = False
                first_sentence_spoken = False
                import time as _time
                _llm_start = _time.monotonic()

                try:
                    from services.tts.provider_manager import tts_manager
                    for token in response:
                        if tts_manager.interrupt_flag.is_set() or not streaming_tts_queue.is_request_active(stream_req_id):
                            logger.info("CommandWorker streaming loop aborted due to TTS interrupt or request cancellation.")
                            break
                        if not first_token_received:
                            first_token_received = True
                            nlu_latency = round(_time.monotonic() - _llm_start, 2)
                            bus.system_stats_updated.emit({"nlu_latency": nlu_latency})
                            pipeline_timer.log_event("first LLM token received")

                        stream_buffer += token
                        full_response += token

                        sentences = sentence_buffer.add_chunk(token)
                        for s in sentences:
                            if tts_manager.interrupt_flag.is_set() or not streaming_tts_queue.is_request_active(stream_req_id):
                                break
                            if not first_sentence_spoken:
                                first_sentence_spoken = True
                                pipeline_timer.log_event("first complete sentence synthesized/queued")
                            # Enqueue streamed sentence without re-initializing request
                            speech.enqueue_sentence(s, request_id=stream_req_id)
                            bus.stream_token_received.emit(s)
                except Exception as e:
                    logger.error(f"Error during streaming LLM response: {e}")
                    if stream_req_id:
                        _speech_svc.cancel_request(stream_req_id)
                    import uuid as _uuid
                    err_req_id = f"sys-error-{_uuid.uuid4().hex[:8]}"
                    speech.speak("Sorry Sir, the connection to my brain was interrupted.", request_id=err_req_id, standalone=True)
                    self.engine.streamed_fallback_active = False
                    self.failed.emit(str(e))
                    return

                if tts_manager.interrupt_flag.is_set() or not streaming_tts_queue.is_request_active(stream_req_id):
                    self.engine.streamed_fallback_active = False
                    logger.info("CommandWorker finished execution early due to interrupt.")
                    if stream_req_id:
                        _speech_svc.cancel_request(stream_req_id)
                    return

                # Flush leftover sentence text
                leftover_sentences = sentence_buffer.flush()
                for leftover in leftover_sentences:
                    if tts_manager.interrupt_flag.is_set() or not streaming_tts_queue.is_request_active(stream_req_id):
                        break
                    speech.enqueue_sentence(leftover, request_id=stream_req_id)
                    bus.stream_token_received.emit(leftover)

                pipeline_timer.log_event("action executed OR LLM response received")

                # Signal producer finished so speech_ended can be emitted once audio drains
                if stream_req_id:
                    _speech_svc.mark_producer_finished(stream_req_id)

                # Save history to SQLite
                db.add_history("user", self.command)
                db.add_history("model", full_response)

                bus.command_completed.emit(True, full_response)
                self.response_ready.emit(full_response)
            else:
                nlu_latency = round(_time.monotonic() - nlu_start, 2)
                bus.system_stats_updated.emit({"nlu_latency": nlu_latency})
                bus.command_completed.emit(True, response)
                self.response_ready.emit(response)
        except Exception as e:
            logger.error(f"Error executing command worker: {e}", exc_info=True)
            bus.command_completed.emit(False, str(e))
            self.failed.emit(str(e))

    @staticmethod
    def normalize_command(raw: str) -> str:
        """
        Clean up raw transcription into a usable command.
        NOTE: The Jarvis prefix must already be stripped before calling this.
        Strips polite filler words only (no longer strips 'jarvis' here).
        """
        text = raw.lower().strip()
        # Remove common punctuation except dots inside file extensions
        text = re.sub(r"[,!-;:'\"]-", "", text)
        text = re.sub(r"\.(-=\s|$)", "", text)
        # Collapse whitespace
        text = re.sub(r"\s-", " ", text).strip()

        # Strip polite filler (prefix already removed upstream)
        remove_phrases = [
            "can you", "could you", "would you",
            "please", "kindly", "hey", "hello", "sir",
        ]
        for phrase in remove_phrases:
            text = re.sub(rf"\b{re.escape(phrase)}\b", "", text).strip()

        text = re.sub(r"\s-", " ", text).strip()
        return text


# ---------------------------------------------------------------------------
# JarvisEngine â€” main state machine
# ---------------------------------------------------------------------------
class JarvisEngine(QObject):
    """
    JARVIS AI Operating System orchestrator.

    State machine:
      INITIALIZING
      PASSIVE_WAKE_LISTENING      - background wake detection only
      WAKE_DETECTED               - wake phrase recognised
      SPEAKING_ACKNOWLEDGEMENT    - saying 'Yes, Sir.'
      SESSION_LISTENING           - prefix-gated multi-command session loop  [NEW]
      COMMAND_RECORDING           - voice detected in session; recording
      TRANSCRIBING_COMMAND        - STT pipeline running
      WAITING_FOR_CONFIRMATION    - low-confidence command needs user yes/no
      EXECUTING_COMMAND           - CommandWorker running
      SPEAKING_RESPONSE           - TTS speaking the result
      SLEEPING                    - brief transition before returning to passive [NEW]
      COOLDOWN                    - post-sleep short pause
      SHUTTING_DOWN               - full app exit in progress

    ALL calls to transition_to() happen on the main Qt thread.
    """

    _instance = None

    def __init__(self):
        super().__init__()
        JarvisEngine._instance = self
        self.state = "INITIALIZING"
        self.wake_locked = False
        self.pending_command = None
        self.pending_command_type = None
        self.misheard_command = None
        self.worker = None

        # Session state tracking
        self.in_session = False
        self.consecutive_invalid = 0
        self.current_space = None
        self.pending_raga_candidates = None
        self.pending_command_aspect = None

        # Follow-up window state
        self.awaiting_followup = False
        self.followup_timer = QTimer(self)
        self.followup_timer.setSingleShot(True)
        self.followup_timer.timeout.connect(self._on_followup_timeout)

        # Routine creation state
        self.creation_routine_name = None
        self.creation_routine_steps = []

        # Command-listening timeout (used for WAITING_FOR_CONFIRMATION)
        self.wake_timer = QTimer(self)
        self.wake_timer.setSingleShot(True)
        self.wake_timer.timeout.connect(self.on_wake_timeout)

        # Session idle timeout
        self.session_timer = QTimer(self)
        self.session_timer.setSingleShot(True)
        self.session_timer.timeout.connect(self._on_session_timeout)

        # --- Core bus signals ---
        bus.wake_detected.connect(self.on_wake_detected)
        bus.speech_ended.connect(self.on_speech_ended)

        # --- Audio lifecycle signals (audio_service -> engine) ---
        bus.command_recording_started.connect(self.on_command_recording_started)
        bus.command_recording_stopped.connect(self.on_command_recording_stopped)
        bus.command_transcription_started.connect(self.on_command_transcription_started)
        bus.command_transcription_completed.connect(self.on_command_transcription_completed)
        bus.command_transcription_failed.connect(self.on_command_transcription_failed)
        bus.command_received.connect(self.on_typed_command_received)
        bus.speech_interrupted.connect(self.on_speech_interrupted)

        # Telegram Bot integration
        self.last_command_source = None
        self.last_telegram_chat_id = None
        self.pending_telegram_confirm = None
        self.last_telegram_was_voice = False

        from services.telegram_bot import TelegramBotService
        self.telegram_bot = TelegramBotService(self)
        self.telegram_bot.message_received.connect(self.on_telegram_message_received)
        self.telegram_bot.callback_received.connect(self.on_telegram_message_received)
        bus.stream_token_received.connect(self.on_stream_token_received)
        self.telegram_bot.start()

    @pyqtSlot()
    def on_speech_interrupted(self):
        logger.info("Engine received speech_interrupted signal. Resetting confirmation states and returning to session/passive.")
        self.pending_command = None
        self.pending_command_type = None
        self.misheard_command = None

        if self.in_session:
            self.transition_to("SESSION_LISTENING")
            self._reset_session_timer()
        else:
            self._return_to_passive()

    @pyqtSlot(str)
    def on_typed_command_received(self, text):
        """
        Slot for handling typed text commands from HUD.
        Ensures prefix is added if in session mode and missing prefix.
        """
        cmd = (text or "").strip()
        if not cmd:
            return

        # If in session and does not start with one of the prefixes, prepend "jarvis "
        if self.in_session:
            has_prefix, _ = self.strip_session_prefix(cmd)
            if not has_prefix:
                cmd = "jarvis " + cmd
                logger.info(f"Typed command normalized: {cmd}")

        # Initialize pipeline timer for telemetry logging
        from core.telemetry import pipeline_timer
        pipeline_timer.start_pipeline(cmd)

        # Process the command directly
        self._process_received_command(cmd, source="typed")

    @pyqtSlot(str, object)
    def on_telegram_message_received(self, text, chat_id):
        logger.info(f"Telegram message received in engine: '{text}' (chat_id: {chat_id})")
        self.last_command_source = "telegram"
        self.last_telegram_chat_id = chat_id

        # Trigger typing indicator
        self.telegram_bot.send_typing_indicator(chat_id)

        cmd = text.strip()
        has_prefix, stripped = self.strip_session_prefix(cmd)
        if has_prefix:
            cmd = stripped

        # 1. Blocking confirmation state check
        if self.pending_telegram_confirm:
            resolved = self.resolve_telegram_confirmation(cmd, chat_id)
            if resolved:
                return
            else:
                if cmd.lower().startswith(("/help", "/status")):
                    pass
                else:
                    self.telegram_bot.send_message(chat_id, "A confirmation is pending. Please answer the Confirm/Cancel prompt first.")
                    return

        # 2. Handle slash commands
        if cmd.startswith("/"):
            self.handle_telegram_slash_command(cmd, chat_id)
            return

        # 3. Process command normally
        self._process_received_command(cmd, source="telegram")

    def resolve_telegram_confirmation(self, response_text, chat_id) -> bool:
        if not self.pending_telegram_confirm:
            return False

        import time
        elapsed = time.time() - self.pending_telegram_confirm["timestamp"]
        if elapsed >= 60 or self.pending_telegram_confirm["chat_id"] != chat_id:
            self.pending_telegram_confirm = None
            return False

        normalized = response_text.lower().strip()
        yes_indicators = ["yes", "yeah", "correct", "confirm", "do it", "proceed", "okay", "ok", "confirm_yes"]
        no_indicators = ["no", "nope", "cancel", "wrong", "incorrect", "dont", "confirm_no", "/cancel"]

        def _is_match(indicator: str, response: str) -> bool:
            import re
            return bool(re.search(rf"\b{re.escape(indicator)}\b", response))

        # Clear inline buttons from original message if we have message_id
        msg_id = self.pending_telegram_confirm.get("message_id")
        if msg_id:
            self.telegram_bot.remove_inline_keyboard(chat_id, msg_id)

        if any(_is_match(ans, normalized) or ans == normalized for ans in yes_indicators):
            cmd_to_run = self.pending_telegram_confirm["command"]
            cmd_type = self.pending_telegram_confirm.get("type")
            self.pending_telegram_confirm = None

            if cmd_type == "near_miss_call_resolution":
                # Redirect to the second-step dial confirmation keyboard
                self.pending_command = cmd_to_run
                self.pending_command_type = "place_call"
                self.last_command_source = "telegram"
                self.last_telegram_chat_id = chat_id
                self.transition_to("WAITING_FOR_CONFIRMATION")
                return True

            self.send_telegram_reply(chat_id, f"Executing: {cmd_to_run}")
            self._process_received_command(cmd_to_run, source="telegram")
            return True
        elif any(_is_match(ans, normalized) or ans == normalized for ans in no_indicators):
            self.pending_telegram_confirm = None
            self.send_telegram_reply(chat_id, "Command cancelled.")
            return True

        return False

    def send_telegram_reply(self, chat_id, text):
        mode = config.get("telegram_voice_replies", "auto").lower()
        should_send_voice = False
        if mode == "always":
            should_send_voice = True
        elif mode == "never":
            should_send_voice = False
        else:  # "auto"
            should_send_voice = getattr(self, "last_telegram_was_voice", False)

        if should_send_voice:
            try:
                from services.tts.provider_manager import tts_manager
                tts_res = tts_manager.synthesize(text)
                if tts_res and tts_res.audio:
                    import io
                    import soundfile as sf
                    data, samplerate = sf.read(io.BytesIO(tts_res.audio))
                    out_io = io.BytesIO()
                    sf.write(out_io, data, samplerate, format='OGG', subtype='OPUS')
                    ogg_bytes = out_io.getvalue()
                    self.telegram_bot.send_voice(chat_id, ogg_bytes, caption=text)
                    return
            except Exception as e:
                logger.error(f"Failed to generate/send Telegram voice reply: {e}", exc_info=True)

        self.telegram_bot.send_message(chat_id, text)

    def handle_telegram_slash_command(self, cmd, chat_id):
        normalized = cmd.lower().strip()
        if normalized == "/help":
            help_text = (
                "<b>Hello Sir! I am JARVIS M7.</b>\n\n"
                "<b>Available Controls</b>:\n"
                "- Send any plain command to control me (e.g., <code>what time is it</code>, <code>open notepad</code>)\n"
                "- <code>/status</code> â€” View system state and active AI providers\n"
                "- <code>/cancel</code> â€” Cancel any pending confirmation"
            )
            self.telegram_bot.send_message(chat_id, help_text)
        elif normalized == "/status":
            stt = config.get("stt_provider", "default")
            brain_p = config.get("brain_provider", "default")
            tts = config.get("tts_provider", "default")
            state = getattr(self, "state", "UNKNOWN")
            session = "Active" if getattr(self, "in_session", False) else "Inactive"

            status_text = (
                "<b>--- JARVIS SYSTEM STATUS ---</b>\n"
                f"<b>State:</b> <code>{state}</code>\n"
                f"<b>Session:</b> <code>{session}</code>\n"
                f"<b>STT Provider:</b> <code>{stt}</code>\n"
                f"<b>Brain Provider:</b> <code>{brain_p}</code>\n"
                f"<b>TTS Provider:</b> <code>{tts}</code>"
            )
            self.telegram_bot.send_message(chat_id, status_text)
        elif normalized == "/cancel":
            if self.pending_telegram_confirm:
                self.resolve_telegram_confirmation("/cancel", chat_id)
            else:
                self.telegram_bot.send_message(chat_id, "No pending confirmation to cancel, Sir.")

    @pyqtSlot(str)
    def on_stream_token_received(self, sentence):
        if getattr(self, "last_command_source", "") == "telegram":
            chat_id = getattr(self, "last_telegram_chat_id", None)
            msg_id = getattr(self, "last_telegram_message_id", None)
            if chat_id and msg_id:
                curr = getattr(self, "streamed_telegram_text", "")
                if not curr:
                    self.streamed_telegram_text = sentence
                else:
                    self.streamed_telegram_text += " " + sentence
                self.telegram_bot.edit_message(chat_id, msg_id, self.streamed_telegram_text)

    # -----------------------------------------------------------------------
    # State machine
    # -----------------------------------------------------------------------
    def transition_to(self, new_state):
        if new_state == "WAITING_FOR_CONFIRMATION" and getattr(self, "last_command_source", "") == "telegram":
            import time
            confirm_cmd = self.pending_command
            confirm_type = self.pending_command_type

            self.pending_telegram_confirm = {
                "command": confirm_cmd,
                "timestamp": time.time(),
                "chat_id": self.last_telegram_chat_id,
                "message_id": None,
                "type": confirm_type
            }
            self.pending_command = None
            self.pending_command_type = None

            if confirm_type == "place_call" and confirm_cmd.startswith("place_call_confirmed:"):
                parts = confirm_cmd.split(":")
                number = parts[1]
                name = parts[2] if len(parts) > 2 else "Unknown"
                msg_text = f"Do you want me to call {name} at {number}, Sir-"
            elif confirm_type == "near_miss_call_resolution" and confirm_cmd.startswith("place_call_confirmed:"):
                parts = confirm_cmd.split(":")
                name = parts[2] if len(parts) > 2 else "Unknown"
                msg_text = f"Did you mean to call {name}, Sir-"
            else:
                msg_text = f"Did you mean: {confirm_cmd}-"

            msg_id = self.telegram_bot.send_confirmation_keyboard(
                self.last_telegram_chat_id,
                msg_text
            )
            self.pending_telegram_confirm["message_id"] = msg_id

            if self.in_session:
                QTimer.singleShot(0, lambda: self.transition_to("SESSION_LISTENING"))
            else:
                QTimer.singleShot(0, lambda: self._return_to_passive())
            return

        if new_state == "EXECUTING_COMMAND" and getattr(self, "last_command_source", "") == "telegram":
            chat_id = getattr(self, "last_telegram_chat_id", None)
            if chat_id:
                msg_id = self.telegram_bot.send_message_and_get_id(chat_id, "Thinking...")
                self.last_telegram_message_id = msg_id
                self.streamed_telegram_text = ""

        if self.state != new_state:
            old_state = self.state
            self.state = new_state
            logger.info(f"State: {old_state} -> {new_state}")

            # Cancel wake/command timeout when clearly busy
            timer_cancel_states = {
                "COMMAND_RECORDING",
                "TRANSCRIBING_COMMAND",
                "EXECUTING_COMMAND",
                "SPEAKING_RESPONSE",
                "WAITING_FOR_CONFIRMATION",
                "SHUTTING_DOWN",
            }
            if new_state in timer_cancel_states and self.wake_timer.isActive():
                self.wake_timer.stop()

            # Invalidate follow-up window if moving to non-session / busy states
            invalidate_followup_states = {
                "WAITING_FOR_CONFIRMATION",
                "SHUTTING_DOWN",
                "SLEEPING",
                "COOLDOWN",
                "PASSIVE_WAKE_LISTENING",
            }
            if new_state in invalidate_followup_states:
                if hasattr(self, "followup_timer") and self.followup_timer.isActive():
                    logger.info(f"Stopping follow-up window due to transition to {new_state}")
                    self.followup_timer.stop()
                self.awaiting_followup = False

                # Clear routine creation state on invalidation
                if self.creation_routine_name:
                    logger.info("Cancelling routine creation due to state transition.")
                    self.creation_routine_name = None
                    self.creation_routine_steps = []

            bus.state_changed.emit(new_state)

    def start(self, startup_mode: bool = False):
        logger.info("JARVIS engine orchestrator active.")
        self.transition_to("PASSIVE_WAKE_LISTENING")
        if startup_mode:
            logger.info("Launched in startup mode: skipping spoken startup greeting.")
            return
        salutation = config.salutation

        from datetime import datetime
        now = datetime.now()
        hour = now.hour
        if hour < 12:
            greeting = "Good morning"
        elif hour < 17:
            greeting = "Good afternoon"
        else:
            greeting = "Good evening"

        time_str = now.strftime("%I:%M %p")
        if time_str.startswith("0"):
            time_str = time_str[1:]

        weather_str = get_weather_summary()
        if weather_str:
            full_greeting = f"{greeting}, {salutation}. Systems online. It's currently {time_str}, and {weather_str}."
        else:
            full_greeting = f"{greeting}, {salutation}. Systems online. It's currently {time_str}."

        sys_status = get_system_status_summary()
        if sys_status:
            full_greeting += f" Also, {sys_status}."

        speech.speak(full_greeting)

    # -----------------------------------------------------------------------
    # Wake detection
    # -----------------------------------------------------------------------
    @pyqtSlot(str)
    def on_wake_detected(self, source):
        if self.state != "PASSIVE_WAKE_LISTENING":
            logger.info(f"Wake rejected: state={self.state}")
            return
        if self.wake_locked:
            logger.info("Wake rejected: wake_locked=True")
            return

        self.wake_locked = True
        logger.info(f"Wake accepted: source={source}")

        # Tell HUD to show itself (in case it was hidden while in passive)
        bus.show_hud_requested.emit()

        self.transition_to("WAKE_DETECTED")
        self.transition_to("SPEAKING_ACKNOWLEDGEMENT")

        salutation = config.salutation
        speech.speak(f"Yes, {salutation}.")
        # Session is activated inside on_speech_ended() after acknowledgement TTS finishes.

    # -----------------------------------------------------------------------
    # Speech lifecycle
    # -----------------------------------------------------------------------
    @pyqtSlot()
    def on_speech_ended(self):
        if self.state == "SPEAKING_ACKNOWLEDGEMENT":
            logger.info("Acknowledgement done. Entering session after TTS cooldown.")
            QTimer.singleShot(600, self._activate_session_listening)

        elif self.state == "WAITING_FOR_CONFIRMATION":
            logger.info("Confirmation prompt done. Re-activating session mic.")
            self.transition_to("SESSION_LISTENING")

        elif self.state == "SHUTTING_DOWN":
            logger.info("Shutdown speech done. Emitting full_exit_requested.")
            bus.full_exit_requested.emit()

        elif self.state == "SLEEPING":
            logger.info("Sleep speech done. Completing sleep transition.")
            self._do_sleep_transition()

    # -----------------------------------------------------------------------
    # Session activation
    # -----------------------------------------------------------------------
    def _activate_session_listening(self):
        """Enter SESSION_LISTENING and start the session idle timer."""
        if self.state != "SPEAKING_ACKNOWLEDGEMENT":
            # Guard: state may have changed during the 600ms singleShot delay
            return
        self.in_session = True
        self.consecutive_invalid = 0
        self.transition_to("SESSION_LISTENING")
        self._reset_session_timer()
        logger.info("Session started. Awaiting Jarvis-prefixed commands.")

    def _start_followup_timer(self):
        """Start the follow-up window timer."""
        seconds = int(config.get("followup_window_seconds", 7))
        logger.info(f"Starting follow-up window: {seconds} seconds.")
        self.followup_timer.stop()
        self.followup_timer.start(seconds * 1000)

    def _on_followup_timeout(self):
        """Follow-up timer expired."""
        if self.awaiting_followup:
            logger.info("Follow-up window expired. Prefix-free follow-ups disabled.")
            self.awaiting_followup = False

    def _reset_session_timer(self):
        """Restart the session idle countdown."""
        timeout_sec = int(config.get("session_timeout_seconds", "180"))
        self.session_timer.stop()
        self.session_timer.start(timeout_sec * 1000)

    def _on_session_timeout(self):
        """Session idle timer fired â€” user was silent for session_timeout_seconds."""
        logger.info("Session timeout. Returning to passive wake listening.")
        speak_timeout = config.get("session_timeout_speech", "false").lower() == "true"
        if speak_timeout:
            speech.speak("Session expired. Going passive, Sir.")
        self._end_session_to_passive()

    def _end_session_to_passive(self):
        """End session and return to passive without hiding the HUD."""
        self.session_timer.stop()
        self.wake_timer.stop()
        self.in_session = False
        self.consecutive_invalid = 0
        self.pending_command = None
        self.pending_command_type = None
        self.misheard_command = None
        self.transition_to("COOLDOWN")
        QTimer.singleShot(800, self._finish_cooldown)

    # -----------------------------------------------------------------------
    # Audio lifecycle signal handlers (all on the main Qt thread)
    # -----------------------------------------------------------------------
    @pyqtSlot()
    def on_command_recording_started(self):
        """Audio service detected voice in SESSION_LISTENING / ACTIVE_COMMAND_LISTENING."""
        if self.state in ("SESSION_LISTENING", "ACTIVE_COMMAND_LISTENING"):
            self.transition_to("COMMAND_RECORDING")

    @pyqtSlot()
    def on_command_recording_stopped(self):
        """Silence ended the recording window."""
        logger.debug("Command recording stopped.")

    @pyqtSlot()
    def on_command_transcription_started(self):
        """STT pipeline starting â€” stamp wall-clock time for latency measurement."""
        import time
        self._stt_start_time = time.monotonic()
        if self.state in ("SESSION_LISTENING", "ACTIVE_COMMAND_LISTENING", "COMMAND_RECORDING"):
            self.transition_to("TRANSCRIBING_COMMAND")

    @pyqtSlot(object)
    def on_command_transcription_completed(self, payload):
        """STT succeeded â€” emit measured STT latency to HUD telemetry panel."""
        if self.state == "TRANSCRIBING_COMMAND":
            try:
                from services.conversation.models import ConversationRequest
                if isinstance(payload, ConversationRequest):
                    req = payload
                    raw_text = req.cleaned_transcript or req.raw_transcript
                else:
                    raw_text = str(payload)
                    import uuid
                    import time
                    req = ConversationRequest(
                        request_id=uuid.uuid4().hex,
                        session_id="default_session",
                        raw_transcript=raw_text,
                        cleaned_transcript=raw_text,
                        created_at=time.time(),
                        stt_confidence=0.90,
                        stt_provider="voice"
                    )

                from core.telemetry import pipeline_timer
                pipeline_timer.start_pipeline(raw_text, request_id=req.request_id)
                self._process_received_command(req, source="voice")
            except Exception as e:
                logger.exception(f"Command processing crashed: {e}")
                self.transition_to("SPEAKING_RESPONSE")
                speech.speak("Sorry Sir, I had an internal command error.")
                self._schedule_return_to_session_after_speech()

    @pyqtSlot(str)
    def on_command_transcription_failed(self, reason):
        """STT failed or returned empty."""
        logger.warning(f"Transcription failed: {reason}")

        if self.in_session:
            # In session: silent failure â€” do NOT speak error; just return to listening
            logger.info("Session: transcription failed silently, returning to SESSION_LISTENING.")
            self.consecutive_invalid -= 1
            max_invalid = int(config.get("max_consecutive_invalid_session_inputs", "8"))
            if self.consecutive_invalid >= max_invalid:
                logger.warning(f"Max invalid inputs ({max_invalid}) reached. Ending session.")
                self._end_session_to_passive()
            else:
                self.transition_to("SESSION_LISTENING")
                self._reset_session_timer()
        else:
            # Outside session: speak the error, then return to passive
            self.transition_to("SPEAKING_RESPONSE")
            speech.speak("Sorry Sir, I could not transcribe the command.")
            self._schedule_return_to_passive_after_speech()

    # -----------------------------------------------------------------------
    # Command timeout
    # -----------------------------------------------------------------------
    def on_wake_timeout(self):
        """wake_timer fired (no command received)."""
        logger.info("Command listening timeout. No command received.")
        if self.in_session:
            self.transition_to("SESSION_LISTENING")
            self._reset_session_timer()
        else:
            self._return_to_passive()

    # -----------------------------------------------------------------------
    # Session prefix gate
    # -----------------------------------------------------------------------
    @staticmethod
    def strip_session_prefix(text: str):
        """
        Check if text starts with a known session prefix (exact then fuzzy).

        Strategy:
          1. Exact / startswith match against SESSION_COMMAND_PREFIXES.
          2. Fuzzy ratio match of the leading token(s) against each prefix
             (threshold = SESSION_PREFIX_FUZZY_THRESHOLD, default 0.75).
             Only fuzzy-matches the word count covered by each prefix.

        Special rule for the 'service' prefix:
          Because 'service' is also a common English word, it is only accepted
          when the payload after it begins with a recognised command action verb.
          'service is bad today' is silently rejected as non-prefixed speech.

        Returns (has_prefix: bool, text_without_prefix: str).
        """
        # Action verbs that must appear at the start of a payload for 'service' to qualify
        SERVICE_ACTION_VERBS = {
            "open", "close", "start", "launch", "stop", "hide", "show",
            "increase", "decrease", "mute", "unmute", "take", "play",
            "pause", "exit", "shutdown", "sleep", "standby", "lock",
            "search", "tell", "what", "which", "how", "when", "who",
        }

        t = text.lower().strip()
        # ---- Pass 1: Exact match ----
        for prefix in SESSION_COMMAND_PREFIXES:
            if t == prefix:
                logger.info(
                    f"Session prefix matched: raw='{prefix}', canonical='jarvis', method='exact'"
                )
                return True, ""

            if t.startswith(prefix + " "):
                remainder = text.strip()[len(prefix):].strip()
                # Special guard: 'service' prefix requires a command action verb
                if prefix == "service" and remainder:
                    rem_words = remainder.lower().split()
                    first_rem_word = re.sub(r"[.,!-;:'\"]-", "", rem_words[0]) if rem_words else ""
                    if first_rem_word not in SERVICE_ACTION_VERBS:
                        logger.info(
                            f"Session input ignored: 'service' prefix present but payload "
                            f"'{remainder}' does not start with a command verb"
                        )
                        return False, text

                logger.info(
                    f"Session prefix matched: raw='{prefix}', canonical='jarvis', method='exact'"
                )
                return True, remainder

        # ---- Pass 2: Fuzzy match of leading token(s) ----
        words_original = text.strip().split()
        words_clean = [re.sub(r"[.,!-;:'\"]-", "", w).lower() for w in words_original]

        for prefix in SESSION_COMMAND_PREFIXES:
            prefix_words = prefix.split()
            n = len(prefix_words)
            if len(words_clean) < n:
                continue

            candidate_clean = " ".join(words_clean[:n])
            ratio = SequenceMatcher(None, candidate_clean, prefix).ratio()
            if ratio >= SESSION_PREFIX_FUZZY_THRESHOLD:
                remainder = " ".join(words_original[n:]).strip()

                if prefix == "service" and remainder:
                    rem_words = remainder.lower().split()
                    first_rem_word = re.sub(r"[.,!-;:'\"]-", "", rem_words[0]) if rem_words else ""
                    if first_rem_word not in SERVICE_ACTION_VERBS:
                        logger.info(
                            f"Session input ignored: 'service' fuzzy prefix, payload "
                            f"'{remainder}' does not start with a command verb"
                        )
                        continue

                logger.info(
                    f"Session prefix matched: raw='{' '.join(words_original[:n])}', canonical='jarvis', "
                    f"method='fuzzy', score={ratio:.2f}"
                )
                return True, remainder

        return False, text

    # -----------------------------------------------------------------------
    # Core command routing
    # -----------------------------------------------------------------------
    def _process_received_command(self, raw_command, source="voice"):
        # Clear the NLU cache at the start of each command lifecycle
        from services.intent.provider_manager import intent_manager
        intent_manager.clear_cache()

        from services.conversation.models import ConversationRequest
        if isinstance(raw_command, ConversationRequest):
            req = raw_command
            request_id = req.request_id
            raw_text = req.cleaned_transcript or req.raw_transcript
            audio_quality = req.audio_quality
            stt_confidence = req.stt_confidence
        else:
            raw_text = str(raw_command)
            import uuid
            import time
            request_id = uuid.uuid4().hex
            audio_quality = 1.0
            stt_confidence = 0.90
            req = ConversationRequest(
                request_id=request_id,
                session_id="default_session",
                raw_transcript=raw_text,
                cleaned_transcript=raw_text,
                created_at=time.time(),
                audio_quality=audio_quality,
                stt_confidence=stt_confidence,
                stt_provider=source
            )

        self.last_command_source = source
        self.active_request_id = request_id
        self.wake_timer.stop()
        salutation = config.salutation

        # Ambiguous-action choice resolution (two-step disambiguation)
        if getattr(self, "pending_action_choice", None) is not None:
            session_id = getattr(req, "session_id", "default_session")
            if self._try_resolve_ambiguous_choice(raw_text, source, session_id, request_id):
                return

        if getattr(self, "pending_confirmation_obj", None) or self.pending_command:
            normalized_ans = raw_text.lower().strip()
            logger.info(f"Confirmation response [Req ID: {request_id[:8]}]: '{raw_text}'")

            # Check expiration
            conf_obj = getattr(self, "pending_confirmation_obj", None)
            if conf_obj and time.time() > conf_obj.expires_at:
                logger.info(f"Pending confirmation expired for req {conf_obj.request_id[:8]}")
                self.pending_confirmation_obj = None
                self.pending_command = None
                self.pending_command_type = None
                self.transition_to("SPEAKING_RESPONSE")
                speech.speak(f"Confirmation expired, {salutation}.", request_id=request_id)
                self._schedule_return_to_session_after_speech()
                return

            yes_indicators = ["yes", "yeah", "correct", "confirm", "do it", "proceed", "okay", "ok"]
            no_indicators = ["no", "nope", "cancel", "wrong", "incorrect", "dont", "never mind", "don't", "stop"]

            def _is_match(indicator: str, response: str) -> bool:
                return bool(re.search(rf"\b{re.escape(indicator)}\b", response))

            if any(_is_match(ans, normalized_ans) for ans in yes_indicators):
                # Check for ambiguous choice â€” a plain "yes" must NOT resolve an AMBIGUOUS_SHUTDOWN
                from services.conversation.models import SensitiveActionType, PendingActionChoice
                ambig_obj = getattr(self, "pending_action_choice", None)
                if ambig_obj is not None:
                    # User said "Yes" without clarifying which action â€” re-prompt
                    logger.info("Ambiguous action choice received generic 'Yes'. Re-prompting user.")
                    self.transition_to("SPEAKING_RESPONSE")
                    speech.speak(f'Please say \'close JARVIS\' or \'shut down the computer,\' {salutation}.', request_id=request_id)
                    self._schedule_return_to_session_after_speech()
                    return

                action_type = conf_obj.action_type if conf_obj else None

                # Source and session validation
                if conf_obj:
                    current_session = getattr(req, "session_id", "default_session")
                    current_source = source
                    if conf_obj.session_id != current_session:
                        logger.warning(f"Confirmation rejected: session mismatch ({conf_obj.session_id} vs {current_session})")
                        self.pending_confirmation_obj = None
                        self.transition_to("SPEAKING_RESPONSE")
                        speech.speak("That confirmation does not match the pending request.", request_id=request_id)
                        self._schedule_return_to_session_after_speech()
                        return
                    if conf_obj.source != current_source:
                        logger.warning(f"Confirmation rejected: source mismatch ({conf_obj.source} vs {current_source})")
                        self.pending_confirmation_obj = None
                        self.transition_to("SPEAKING_RESPONSE")
                        speech.speak("That confirmation does not match the pending request.", request_id=request_id)
                        self._schedule_return_to_session_after_speech()
                        return

                # Atomically copy and clear before executing (duplicate-Yes protection)
                cmd_to_run = self.pending_command
                self.pending_confirmation_obj = None
                self.pending_command = None
                self.pending_command_type = None
                self.misheard_command = None

                logger.info(f"Action confirmed [Type: {action_type}, Payload: {cmd_to_run}]")
                self.execute_confirmed_sensitive_action(action_type, cmd_to_run, request_id=request_id)
                return
            elif any(_is_match(ans, normalized_ans) for ans in no_indicators):
                logger.info("Command rejected/cancelled by user.")
                self.pending_confirmation_obj = None
                self.pending_command = None
                self.pending_command_type = None
                self.misheard_command = None
                self.transition_to("SPEAKING_RESPONSE")
                speech.speak(f"Command cancelled, {salutation}.", request_id=request_id)
                self._schedule_return_to_session_after_speech()
                return
            else:
                logger.info("Unclear confirmation reply.")
                self.pending_confirmation_obj = None
                self.pending_command = None
                self.pending_command_type = None
                self.misheard_command = None
                self.transition_to("SPEAKING_RESPONSE")
                speech.speak(f"Request cancelled, {salutation}.", request_id=request_id)
                self._schedule_return_to_session_after_speech()
                return

        # TranscriptResolver handling
        session_active = self.state in {
            "SESSION_LISTENING",
            "ACTIVE_COMMAND_LISTENING",
            "WAITING_FOR_FOLLOWUP",
            "WAITING_FOR_CONFIRMATION",
        } or getattr(self, "in_session", False)
        from services.conversation.transcript_resolver import transcript_resolver
        resolved_tr = transcript_resolver.resolve(
            raw_text,
            stt_confidence=stt_confidence,
            audio_quality=audio_quality,
            session_active=session_active,
        )
        logger.info(
            f"TranscriptResolver | Req ID: {request_id[:8]} | Raw: '{raw_text}' | "
            f"Resolved: '{resolved_tr.resolved_text}' | Conf: {resolved_tr.confidence:.2f} | "
            f"Wake: {resolved_tr.wake_word_detected} ({resolved_tr.wake_word_position}) | "
            f"Clarify: {resolved_tr.needs_clarification} | Sensitive: {resolved_tr.is_sensitive_action}"
        )

        from services.conversation.models import PendingConfirmation, SensitiveActionType
        if resolved_tr.needs_clarification:
            if resolved_tr.is_sensitive_action or "shut down" in resolved_tr.resolved_text.lower():
                self.pending_command = resolved_tr.resolved_text
                self.pending_command_type = "sensitive_action"
                self.pending_confirmation_obj = PendingConfirmation(
                    request_id=request_id,
                    session_id=getattr(req, "session_id", "default_session"),
                    action_type=resolved_tr.sensitive_action_type or SensitiveActionType.AMBIGUOUS_SHUTDOWN,
                    action_payload={"command": resolved_tr.resolved_text},
                    source=source,
                    created_at=time.time(),
                    expires_at=time.time() - 30.0
                )
                self.transition_to("WAITING_FOR_CONFIRMATION")
                speech.speak(resolved_tr.clarification_question or f"Did you ask me to {resolved_tr.resolved_text}-", request_id=request_id)
                return
            else:
                self.transition_to("SPEAKING_RESPONSE")
                speech.speak(resolved_tr.clarification_question or "Sorry Sir, I could not understand.", request_id=request_id)
                self._schedule_return_to_session_after_speech()
                return

        if resolved_tr.is_sensitive_action:
            act_type = resolved_tr.sensitive_action_type or SensitiveActionType.AMBIGUOUS_SHUTDOWN
            session_id = getattr(req, "session_id", "default_session")

            if act_type == SensitiveActionType.AMBIGUOUS_SHUTDOWN:
                # Two-step flow: first ask user to disambiguate, then confirm specific action
                from services.conversation.models import PendingActionChoice
                self.pending_action_choice = PendingActionChoice(
                    request_id=request_id,
                    session_id=session_id,
                    source=source,
                    options=[SensitiveActionType.EXIT_APPLICATION, SensitiveActionType.SHUTDOWN_COMPUTER],
                    created_at=time.time(),
                    expires_at=time.time() - 30.0
                )
                self.pending_command = resolved_tr.resolved_text
                self.pending_command_type = "sensitive_action"
                self.pending_confirmation_obj = None
                self.transition_to("WAITING_FOR_CONFIRMATION")
                speech.speak("Did you mean close JARVIS, or shut down the computer-", request_id=request_id)
                return

            self.pending_command = resolved_tr.resolved_text
            self.pending_command_type = "sensitive_action"
            self.pending_action_choice = None
            self.pending_confirmation_obj = PendingConfirmation(
                request_id=request_id,
                session_id=session_id,
                action_type=act_type,
                action_payload={"command": resolved_tr.resolved_text},
                source=source,
                created_at=time.time(),
                expires_at=time.time() - 30.0
            )
            self.transition_to("WAITING_FOR_CONFIRMATION")
            if act_type == SensitiveActionType.EXIT_APPLICATION:
                prompt = f"Do you want me to close JARVIS, {salutation}-"
            elif act_type == SensitiveActionType.SHUTDOWN_COMPUTER:
                prompt = f"Do you want me to shut down your PC, {salutation}-"
            elif act_type == SensitiveActionType.RESTART_COMPUTER:
                prompt = f"Do you want me to restart your PC, {salutation}-"
            elif act_type == SensitiveActionType.LOG_OUT_WINDOWS:
                prompt = f"Do you want me to log out of your PC, {salutation}-"
            elif act_type == SensitiveActionType.LOCK_COMPUTER:
                prompt = f"Do you want me to lock your PC, {salutation}-"
            else:
                prompt = f"Do you want me to {resolved_tr.resolved_text}, {salutation}-"
            speech.speak(prompt, request_id=request_id)
            return

        raw_command_str = raw_text
        raw_command_str, rep_count = collapse_repeated_command(raw_command_str)
        is_low_confidence = (rep_count >= 3)

        # Step collection interception (Prefix-free)
        if self.creation_routine_name:
            normalized_cmd = raw_command_str.lower().strip()
            normalized_cmd = re.sub(r"[.,!-;:'\"]-", "", normalized_cmd).strip()

            if normalized_cmd == "done":
                logger.info(f"Routine creation finished. Saving routine '{self.creation_routine_name}' with {len(self.creation_routine_steps)} steps.")
                db.save_routine(self.creation_routine_name, self.creation_routine_steps)

                msg = f"Got it. Routine called {self.creation_routine_name} has been successfully created with {len(self.creation_routine_steps)} steps, {salutation}."
                self.creation_routine_name = None
                self.creation_routine_steps = []

                self.transition_to("SPEAKING_RESPONSE")
                speech.speak(msg)
                self._schedule_return_to_session_after_speech()
            else:
                self.creation_routine_steps.append(raw_command_str)
                logger.info(f"Added step to routine '{self.creation_routine_name}': {raw_command_str}")

                self.transition_to("SPEAKING_RESPONSE")
                speech.speak("Got it. Anything else, or say 'done' to finish.")
                self._schedule_return_to_session_after_speech()
            return

        if self.in_session:
            if source in ("telegram", "typed"):
                has_prefix = True
                stripped = raw_command_str
            elif resolved_tr.wake_word_detected:
                has_prefix = True
                stripped = resolved_tr.resolved_text
            else:
                has_prefix, stripped = self.strip_session_prefix(raw_command_str)

            if not has_prefix and self.awaiting_followup:
                logger.info(f"Prefix-free follow-up accepted: '{raw_command}'")
                has_prefix = True
                stripped = raw_command
                self.awaiting_followup = False
                self.followup_timer.stop()
            elif has_prefix and self.awaiting_followup:
                logger.info("Command with prefix received during follow-up window. Resetting follow-up state.")
                self.awaiting_followup = False
                self.followup_timer.stop()

            if not has_prefix:
                logger.info(f"Session ignored: '{raw_command}' (no prefix)")
                bus.console_log.emit("INFO", "Session input ignored: missing Jarvis prefix")
                self.consecutive_invalid -= 1
                max_invalid = int(config.get("max_consecutive_invalid_session_inputs", "8"))
                if self.consecutive_invalid >= max_invalid:
                    logger.warning(f"Max invalid inputs ({max_invalid}) reached.")
                    self._end_session_to_passive()
                else:
                    self.transition_to("SESSION_LISTENING")
                    self._reset_session_timer()
                return

            self.consecutive_invalid = 0
            raw_command_for_routing = stripped
            if not raw_command_for_routing:
                logger.info("Bare prefix, no command body.")
                self.transition_to("SESSION_LISTENING")
                self._reset_session_timer()
                return

            stripped_lower = raw_command_for_routing.lower().strip()
            stripped_clean = re.sub(r"[.,!-;:'\"]-", "", stripped_lower).strip()
            from core.lifecycle_triggers import SLEEP_TRIGGERS, APP_EXIT_TRIGGERS
            if stripped_clean in SLEEP_TRIGGERS or stripped_clean in APP_EXIT_TRIGGERS:
                if is_low_confidence:
                    logger.info(f"Lifecycle command '{stripped_clean}' flagged as low confidence due to repetitions ({rep_count}). Demoting to confirmation.")
                    self.pending_command = stripped_clean
                    self.pending_command_type = "lifecycle_sleep" if stripped_clean in SLEEP_TRIGGERS else "lifecycle_exit"
                    self.misheard_command = raw_command
                    self.transition_to("WAITING_FOR_CONFIRMATION")
                    speech.speak(f"Did you mean, {stripped_clean}, {salutation}-")
                    return

                if stripped_clean in SLEEP_TRIGGERS:
                    self.sleep_jarvis()
                else:
                    self.full_exit_jarvis()
                return
        else:
            raw_command_for_routing = raw_command

        command = CommandWorker.normalize_command(raw_command_for_routing)
        if not command:
            if self.in_session:
                self.transition_to("SESSION_LISTENING")
                self._reset_session_timer()
            else:
                self._return_to_passive()
            return

        cmd_stripped = command.lower().strip()

        # Check for autostart toggles
        if cmd_stripped in ("enable autostart", "enable auto start", "disable autostart", "disable auto start"):
            is_enable = "enable" in cmd_stripped
            action = "enable_autostart" if is_enable else "disable_autostart"
            tool_call = ToolCall(
                tool_name="autostart",
                action=action,
                target="registry",
                source=source,
                confidence=1.0 if not is_low_confidence else 0.5,
                audio_quality=audio_quality,
                reversible=True,
                destructive=False
            )
            decision = TrustGate.evaluate(tool_call)
            if decision == "EXECUTE":
                self.transition_to("EXECUTING_COMMAND")
                self._launch_worker("enable autostart" if is_enable else "disable autostart")
                return
            elif decision == "CONFIRM":
                self.pending_command = "enable autostart" if is_enable else "disable autostart"
                self.pending_command_type = "autostart_toggle"
                self.misheard_command = command
                self.transition_to("WAITING_FOR_CONFIRMATION")
                speech.speak(f"Did you mean to {'enable' if is_enable else 'disable'} autostart, {salutation}-")
                return

        # Check for create routine trigger
        if cmd_stripped.startswith("create a routine called "):
            routine_name = command[len("create a routine called "):].strip()
            if routine_name:
                self.creation_routine_name = routine_name
                self.creation_routine_steps = []
                logger.info(f"Starting creation of routine: '{routine_name}'")
                self.transition_to("SPEAKING_RESPONSE")
                speech.speak("What should I do first, Sir-")
                self._schedule_return_to_session_after_speech()
                return

        # Memory: "remember that [fact]" or "remember [fact]"
        if cmd_stripped.startswith("remember that ") or cmd_stripped.startswith("remember "):
            fact = ""
            if cmd_stripped.startswith("remember that "):
                fact = command[len("remember that "):].strip()
            else:
                fact = command[len("remember "):].strip()

            if fact:
                facts = db.get_memory("user_facts", default=[])
                if fact not in facts:
                    facts.append(fact)
                    db.set_memory("user_facts", facts)
                logger.info(f"Saved fact to memory: '{fact}'")
                self.transition_to("SPEAKING_RESPONSE")
                speech.speak(f"Got it, {salutation}. I'll remember that.")
                self._schedule_return_to_session_after_speech()
                return

        # Memory: "what do you remember about me" or "what do you know about me"
        if cmd_stripped in ("what do you remember about me", "what do you know about me", "what do you know", "what do you remember"):
            facts = db.get_memory("user_facts", default=[])
            if not facts:
                msg = f"I don't have anything saved in my memory yet, {salutation}."
            else:
                facts_list = "; ".join(facts)
                msg = f"Here is what I remember about you, {salutation}: {facts_list}."
            self.transition_to("SPEAKING_RESPONSE")
            speech.speak(msg)
            self._schedule_return_to_session_after_speech()
            return

        # Memory: "forget everything"
        if cmd_stripped == "forget everything":
            db.set_memory("user_facts", [])
            logger.info("Cleared all facts from memory.")
            self.transition_to("SPEAKING_RESPONSE")
            speech.speak(f"I have cleared everything from my memory, {salutation}.")
            self._schedule_return_to_session_after_speech()
            return

        # Memory: "forget that [fact]"
        if cmd_stripped.startswith("forget that "):
            target_fact = command[len("forget that "):].strip().lower()
            facts = db.get_memory("user_facts", default=[])

            best_match = None
            best_score = 0.0

            for fact in facts:
                score = SequenceMatcher(None, target_fact, fact.lower()).ratio()
                if score > best_score:
                    best_score = score
                    best_match = fact

            if best_match and best_score >= 0.6:
                facts.remove(best_match)
                db.set_memory("user_facts", facts)
                logger.info(f"Removed fact from memory: '{best_match}' (similarity={best_score:.2f})")
                msg = f"Understood, {salutation}. That's been forgotten."
            else:
                msg = f"I couldn't find any memory matching '{target_fact}', {salutation}."

            self.transition_to("SPEAKING_RESPONSE")
            speech.speak(msg)
            self._schedule_return_to_session_after_speech()
            return

        from core.lifecycle_triggers import SLEEP_TRIGGERS, APP_EXIT_TRIGGERS

        # Exact app exit or sleep matching with low confidence check
        if cmd_stripped in APP_EXIT_TRIGGERS or cmd_stripped in SLEEP_TRIGGERS:
            if is_low_confidence:
                logger.info(f"Lifecycle command '{cmd_stripped}' flagged as low confidence due to repetitions ({rep_count}). Demoting to confirmation.")
                self.pending_command = cmd_stripped
                self.pending_command_type = "lifecycle_exit" if cmd_stripped in APP_EXIT_TRIGGERS else "lifecycle_sleep"
                self.misheard_command = command
                self.transition_to("WAITING_FOR_CONFIRMATION")
                speech.speak(f"Did you mean, {cmd_stripped}, {salutation}-")
                return

            if cmd_stripped in APP_EXIT_TRIGGERS:
                logger.info(f"App exit trigger: '{cmd_stripped}' -> full app exit")
                self.full_exit_jarvis()
            else:
                self.sleep_jarvis()
            return

        # PART E â€” Incomplete deterministic app commands check
        INCOMPLETE_APP_COMMANDS = {"open", "close", "launch", "start", "run", "stop", "kill", "exit"}
        if cmd_stripped in INCOMPLETE_APP_COMMANDS:
            self._speak_and_return_to_session("Which app should I close, Sir-")
            return

        # PART G â€” Protected Lifecycle Phrases Fuzzy Protection
        PROTECTED_LIFECYCLE_PHRASES = [
            "sleep",
            "standby",
            "go passive",
            "shutdown",
            "shut down",
            "full shutdown",
            "exit app",
            "close jarvis",
            "hide hud"
        ]

        is_lifecycle_phrase = False
        for phrase in PROTECTED_LIFECYCLE_PHRASES:
            if SequenceMatcher(None, cmd_stripped, phrase).ratio() >= 0.7:
                is_lifecycle_phrase = True
                break

        if is_lifecycle_phrase:
            logger.info(f"Protected lifecycle phrase detected/fuzzy-matched: '{cmd_stripped}'")
            self._speak_and_return_to_session("Did you mean to sleep or exit the application, Sir-")
            return

        personal_corrections = get_personal_corrections()
        personal_match = None
        for key, variants in personal_corrections.items():
            if command in variants or raw_command_for_routing.lower().strip() in variants:
                personal_match = key
                break

        direct_action = None
        direct_app_text = None
        for act in ["open", "launch", "start", "run", "close", "quit", "exit", "stop", "kill"]:
            if command.startswith(act + " "):
                direct_action = "open" if act in ["open", "launch", "start", "run"] else "close"
                direct_app_text = command[len(act):].strip()
                break

        if direct_action and direct_app_text:
            from services.app_resolver import app_resolver
            logger.info(f"Direct app command detected: action={direct_action}, app_text=\"{direct_app_text}\"")
            match = app_resolver.resolve_app(direct_app_text)
            if match and match.confidence >= 0.75:
                from core.telemetry import pipeline_timer
                pipeline_timer.log_event("intent parsed")
                logger.info(f"App resolved: {match.display_name}, confidence={match.confidence}, source={match.match_reason}")
                target_cmd = f"{direct_action} {match.display_name}"

                tool_call = ToolCall(
                    tool_name="app_resolver",
                    action=direct_action,
                    target=match.display_name,
                    source=source,
                    confidence=match.confidence,
                    audio_quality=audio_quality,
                    reversible=not is_destructive(target_cmd),
                    destructive=is_destructive(target_cmd)
                )
                pipeline_timer.log_event("ToolCall built")
                decision = TrustGate.evaluate(tool_call)
                pipeline_timer.log_event(f"TrustGate decision made: {decision}")
                if decision == "EXECUTE":
                    self.transition_to("EXECUTING_COMMAND")
                    self._launch_worker(target_cmd)
                    return
                elif decision == "CONFIRM":
                    self.pending_command = target_cmd
                    self.pending_command_type = "app_launch"
                    self.misheard_command = command
                    self.transition_to("WAITING_FOR_CONFIRMATION")
                    speech.speak(f"Did you mean, {target_cmd}, {salutation}-")
                    return
            else:
                logger.info(f"Direct app resolving failed or confidence low, falling back to intent/fuzzy pipeline.")

        # Local Deterministic Tier (new, zero-LLM-call)
        det_cmd = cmd_stripped
        for prefix in SESSION_COMMAND_PREFIXES:
            if det_cmd.startswith(prefix + " "):
                det_cmd = det_cmd[len(prefix):].strip()
                break
        det_cmd = det_cmd.strip(" -.")

        if det_cmd in ("settings", "open settings", "open configuration", "configuration", "open settings panel"):
            logger.info("Local Deterministic Trigger: Open settings requested")
            QTimer.singleShot(0, lambda: bus.command_status.emit("settings_request"))
            self._speak_and_return_to_session(f"Opening Configuration Panel, {salutation}.")
            return

        if det_cmd in ("what time is it", "whats the time", "what is the time", "tell me the time", "time"):
            import datetime
            now = datetime.datetime.now()
            time_str = now.strftime("%I:%M %p")
            msg = f"It is currently {time_str}, {salutation}."
            self._speak_and_return_to_session(msg)
            return

        if det_cmd in ("whats the date", "what is the date", "what day is it", "whats today", "what is today", "date"):
            import datetime
            now = datetime.datetime.now()
            date_str = now.strftime("%A, %B %d, %Y")
            msg = f"Today is {date_str}, {salutation}."
            self._speak_and_return_to_session(msg)
            return

        if det_cmd in ("system status", "check system status", "how is my pc", "how is my computer", "how is the system", "pc status", "computer status"):
            status = get_system_status_summary()
            if not status:
                status = f"All systems are functioning within normal parameters, {salutation}."
            else:
                status = f"System status update: {status}, {salutation}."
            self._speak_and_return_to_session(status)
            return

        # Question-like pattern heuristic to bypass fuzzy app-matching
        wh_pattern = r"^(who|what|when|where|why|how)s-\b"
        aux_pattern = r"^(is|are|was|were|did|does|do|can|could|will|would|have|has|had|should|must|may|might)\b"
        info_pattern = r"^(search|find|tell\s-me|explain|google)\b"

        is_question = (
            bool(re.search(wh_pattern, cmd_stripped)) or
            bool(re.search(aux_pattern, cmd_stripped)) or
            bool(re.search(info_pattern, cmd_stripped))
        )
        action_verbs = ["open", "close", "launch", "start", "stop", "kill", "exit", "sleep"]
        has_action = any(re.search(rf"\b{re.escape(verb)}\b", cmd_stripped) for verb in action_verbs)

        calendar_keywords = ["calendar", "meeting", "appointment", "event", "free", "busy", "schedule"]
        is_calendar = any(kw in cmd_stripped for kw in calendar_keywords) or any(
            x in cmd_stripped for x in ["lunch with", "dinner with", "coffee with", "brunch with", "breakfast with", "call with", "zoom with"]
        )

        if is_question and not has_action and not is_calendar:
            from core.telemetry import pipeline_timer
            pipeline_timer.log_event("intent parsed (question heuristic)")
            logger.info(f"Question heuristic matched: '{cmd_stripped}'. Routing directly to fallback/brain.")
            self.transition_to("EXECUTING_COMMAND")

            # Generate context-aware acknowledgment using services.acknowledgement_service
            from services.acknowledgement_service import acknowledgement_service
            from core.brain import needs_web_search

            use_web = needs_web_search(cmd_stripped)
            acknowledgment = acknowledgement_service.generate(
                cmd_stripped,
                brain_route="simple_chat",
                use_web=use_web
            )

            if acknowledgment:
                speech.speak(acknowledgment)

            self._launch_worker(command, fallback_only=True)
            return

        # File Creation Intent Matcher (intercepts before fuzzy app matcher)
        file_creation_match = parse_file_creation(command)
        if file_creation_match:
            filename = file_creation_match["filename"]
            location = file_creation_match["location"]

            if not validate_filename(filename):
                logger.warning(f"Unsafe filename rejected: '{filename}'")
                self.transition_to("SPEAKING_RESPONSE")
                speech.speak(f"That filename looks unsafe or contains illegal characters, Sir. Please try again with a safe filename.")
                self._schedule_return_to_session_after_speech()
                return

            target_dir = map_directory(location)
            filepath = os.path.join(target_dir, filename)

            # Check if file exists to handle overwrite confirmation
            if os.path.exists(filepath):
                logger.info(f"File already exists: '{filepath}'. Demoting to overwrite confirmation.")
                self.pending_command = f"create_file_confirmed:{filepath}"
                self.pending_command_type = "file_creation"
                self.misheard_command = command
                self.transition_to("WAITING_FOR_CONFIRMATION")
                speech.speak(f"The file {filename} already exists, Sir. Would you like to overwrite it-")
                return
            else:
                # Direct execute for genuinely new files
                tool_call = ToolCall(
                    tool_name="file_operations",
                    action="create",
                    target=filepath,
                    source=source,
                    confidence=1.0,
                    audio_quality=audio_quality,
                    reversible=True,
                    destructive=False
                )

                decision = TrustGate.evaluate(tool_call)
                if decision == "EXECUTE":
                    self.transition_to("EXECUTING_COMMAND")
                    self._launch_worker(f"create_file_confirmed:{filepath}")
                    return
                elif decision == "CONFIRM":
                    self.pending_command = f"create_file_confirmed:{filepath}"
                    self.pending_command_type = "file_creation"
                    self.misheard_command = command
                    self.transition_to("WAITING_FOR_CONFIRMATION")
                    speech.speak(f"Would you like me to create the file {filename} on your {location}, Sir-")
                    return
                else:
                    self.transition_to("PASSIVE_WAKE_LISTENING")
                    return

        corrected_cmd, confidence = self.correct_command(command)
        logger.info(f"Fuzzy Matcher evaluation: command='{command}', corrected_cmd='{corrected_cmd}', confidence={confidence}")
        if confidence < 0.7:
            corrected_cmd = None
            confidence = 0.0

        if personal_match:
            corrected_cmd = personal_match
            confidence = 1.0

        from core.telemetry import pipeline_timer
        pipeline_timer.log_event("intent parsed")

        c_action = "execute"
        c_target = corrected_cmd or command
        if corrected_cmd:
            for act in ["open", "launch", "start", "run", "close", "quit", "exit", "stop", "kill"]:
                if corrected_cmd.lower().startswith(act + " "):
                    c_action = "open" if act in ["open", "launch", "start", "run"] else "close"
                    c_target = corrected_cmd[len(act):].strip()
                    break

        if corrected_cmd:
            logger.info(f"Fuzzy match passed threshold. Evaluating TrustGate: corrected_cmd='{corrected_cmd}'")
            tool_call = ToolCall(
                tool_name="fuzzy_matcher",
                action=c_action,
                target=c_target,
                source=source,
                confidence=confidence,
                audio_quality=audio_quality,
                reversible=not is_destructive(corrected_cmd or command),
                destructive=is_destructive(corrected_cmd or command)
            )
            pipeline_timer.log_event("ToolCall built")
            decision = TrustGate.evaluate(tool_call)
            pipeline_timer.log_event(f"TrustGate decision made: {decision}")
            if decision == "EXECUTE":
                self.transition_to("EXECUTING_COMMAND")
                self._launch_worker(corrected_cmd)
                return
            elif decision == "CONFIRM":
                self.pending_command = corrected_cmd
                self.pending_command_type = "app_launch"
                self.misheard_command = command
                self.transition_to("WAITING_FOR_CONFIRMATION")
                speech.speak(f"Did you mean, {corrected_cmd}, {salutation}-")
                return

        try:
            from services.intent.provider_manager import intent_manager
            api_intent = intent_manager.parse_intent(command)
            if api_intent and api_intent.action in ["open_app", "close_app"] and api_intent.confidence >= 0.75:
                from services.app_resolver import app_resolver
                match = app_resolver.resolve_app(api_intent.target)
                if match and match.confidence >= 0.75:
                    logger.info(f"Gemini intent resolved: {api_intent.action} {match.display_name}")
                    act_verb = "open" if api_intent.action == "open_app" else "close"
                    target_cmd = f"{act_verb} {match.display_name}"

                    tool_call = ToolCall(
                        tool_name="intent_manager",
                        action=act_verb,
                        target=match.display_name,
                        source=source,
                        confidence=api_intent.confidence,
                        audio_quality=audio_quality,
                        reversible=not is_destructive(target_cmd),
                        destructive=is_destructive(target_cmd)
                    )
                    decision = TrustGate.evaluate(tool_call)
                    if decision == "EXECUTE":
                        self.transition_to("EXECUTING_COMMAND")
                        self._launch_worker(target_cmd)
                        return
                    elif decision == "CONFIRM":
                        self.pending_command = target_cmd
                        self.pending_command_type = "app_launch"
                        self.misheard_command = command
                        self.transition_to("WAITING_FOR_CONFIRMATION")
                        speech.speak(f"Did you mean, {target_cmd}, {salutation}-")
                        return
            elif api_intent and api_intent.action == "place_call" and api_intent.confidence >= 0.75:
                logger.info(f"Call intent resolved: {api_intent.action} {api_intent.target}")
                from services.contacts_service import contacts_service
                res = contacts_service.resolve_contact(api_intent.target)
                if res["status"] == "no_match":
                     self._speak_and_return_to_session(f"I couldn't find any contact matching '{api_intent.target}', {salutation}.")
                     return
                elif res["status"] == "near_miss":
                    contact = res["contact"]
                    name = contact["name"]
                    number = contact["phone"]

                    target_cmd = f"place_call_confirmed:{number}:{name}"
                    self.pending_command = target_cmd
                    self.pending_command_type = "near_miss_call_resolution"
                    self.misheard_command = command
                    self.transition_to("WAITING_FOR_CONFIRMATION")

                    confirm_phrase = f"Did you mean to call {name}, {salutation}-"
                    speech.speak(confirm_phrase)
                    return
                elif res["status"] == "ambiguous":
                    self.pending_call_candidates = res["candidates"]
                    self.pending_command = "WAITING_FOR_INDEX"
                    self.pending_command_type = "ambiguous_call_resolution"
                    self.transition_to("WAITING_FOR_CONFIRMATION")

                    candidates_list = [f"{i-1}. {c['name']}" for i, c in enumerate(res["candidates"])]
                    candidates_str = " ".join(candidates_list)
                    speech.speak(f"I found these contacts matching '{api_intent.target}', {salutation}: {candidates_str}. Which one should I call-")
                    return

                contact = res["contact"]
                name = contact["name"]
                number = contact["phone"]

                target_cmd = f"place_call_confirmed:{number}:{name}"

                tool_call = ToolCall(
                    tool_name="call_skill",
                    action="place_call",
                    target=f"{name} ({number})",
                    source=source,
                    confidence=api_intent.confidence,
                    audio_quality=audio_quality,
                    reversible=False,
                    destructive=True
                )

                decision = TrustGate.evaluate(tool_call)
                if decision == "EXECUTE":
                    self.transition_to("EXECUTING_COMMAND")
                    self._launch_worker(target_cmd)
                    return
                elif decision == "CONFIRM":
                    self.pending_command = target_cmd
                    self.pending_command_type = "place_call"
                    self.misheard_command = command
                    self.transition_to("WAITING_FOR_CONFIRMATION")

                    confirm_phrase = f"Do you want me to call {name} at {number}, {salutation}-"
                    speech.speak(confirm_phrase)
                    return
            elif api_intent and api_intent.action in ["create_event", "update_event", "delete_event", "list_events", "get_next_event", "check_availability"] and api_intent.confidence >= 0.75:
                logger.info(f"Calendar intent resolved: {api_intent.action} {api_intent.target}")
                is_dest = api_intent.action in ("delete_event", "update_event") or (api_intent.action == "create_event")

                tool_call = ToolCall(
                    tool_name="intent_manager",
                    action=api_intent.action,
                    target=api_intent.target,
                    source=source,
                    confidence=api_intent.confidence,
                    audio_quality=audio_quality,
                    reversible=not is_dest,
                    destructive=is_dest
                )
                decision = TrustGate.evaluate(tool_call)
                if decision == "EXECUTE":
                    self.transition_to("EXECUTING_COMMAND")
                    self._launch_worker(command, fallback_only=False)
                    return
                elif decision == "CONFIRM":
                    self.pending_command = command
                    self.pending_command_type = "calendar_confirm"
                    self.misheard_command = command
                    self.transition_to("WAITING_FOR_CONFIRMATION")

                    confirm_phrase = f"Do you want to run that calendar action, {salutation}-"
                    if api_intent.action == "create_event":
                        try:
                            params = json.loads(api_intent.target)
                            from services.calendar_service import format_datetime_human
                            readable_time = format_datetime_human(params.get("start_time"))
                            confirm_phrase = f"Do you want me to schedule '{params.get('summary', 'event')}' for {readable_time}, {salutation}-"
                        except Exception:
                            pass
                    elif api_intent.action == "delete_event":
                        try:
                            params = json.loads(api_intent.target)
                            confirm_phrase = f"Are you sure you want to delete the meeting '{params.get('event_ref')}', {salutation}-"
                        except Exception:
                            pass
                    elif api_intent.action == "update_event":
                        try:
                            params = json.loads(api_intent.target)
                            confirm_phrase = f"Do you want to update the meeting '{params.get('event_ref')}', {salutation}-"
                        except Exception:
                            pass

                    speech.speak(confirm_phrase)
                    return
        except Exception as e:
            logger.warn(f"Cloud intent NLU failed: {e}")

        # Filter out short, garbled commands (<= 3 words, not a question, not a greeting) to prevent LLM/web-search fallback cascade
        cmd_words = command.strip().lower().split()
        if len(cmd_words) <= 3 and not is_question:
            greetings = {"hello", "hi", "hey", "jarvis", "jervis", "javis"}
            if not any(w in greetings for w in cmd_words):
                logger.info(f"Garbled command check triggered: command='{command}' is short, not a question, and not a greeting. Bypassing Brain/LLM fallback.")
                self.transition_to("SPEAKING_RESPONSE")
                speech.speak(f"I didn't quite catch that, {salutation}. Could you repeat it-")
                self._schedule_return_to_session_after_speech()
                return

        # Fallback execution (Conversational Q&A / Brain) - Bypass TrustGate action checking
        from core.telemetry import pipeline_timer
        pipeline_timer.log_event("intent parsed (fallback path)")
        logger.info(f"Routing fallback command to engine pipeline (checking skills first): {command!r}")
        self.transition_to("EXECUTING_COMMAND")
        self._launch_worker(command, fallback_only=False)



    # Worker management (thread-safe via signals)
    # -----------------------------------------------------------------------
    def _launch_worker(self, command, fallback_only=False, request_id: str | None = None):
        """Create and start a CommandWorker. Connect its signals to main-thread slots."""
        # Pass the request_id directly â€” do not read from self.active_request_id which may be mutated
        self.worker = CommandWorker(command, self, fallback_only=fallback_only, request_id=request_id)
        self.worker.started_executing.connect(self._on_worker_started)
        self.worker.response_ready.connect(self._on_worker_response)
        self.worker.failed.connect(self._on_worker_failed)
        self.worker.start()

    @pyqtSlot()
    def _on_worker_started(self):
        if self.state != "EXECUTING_COMMAND":
            self.transition_to("EXECUTING_COMMAND")

    @pyqtSlot(str)
    def _on_worker_response(self, response):
        self.transition_to("SPEAKING_RESPONSE")
        if getattr(self, "last_command_source", "") == "telegram":
            chat_id = getattr(self, "last_telegram_chat_id", None)
            if chat_id:
                self.send_telegram_reply(chat_id, response)
        if getattr(self, "streamed_fallback_active", False):
            self.streamed_fallback_active = False
            logger.info("Fallback response was streamed and already sent to speech service. Bypassing repeat speak.")
        else:
            speech.speak(response)
        self._schedule_return_to_session_after_speech()

    @pyqtSlot(str)
    def _on_worker_failed(self, error):
        logger.error(f"CommandWorker failed: {error}")
        salutation = config.salutation
        self.transition_to("SPEAKING_RESPONSE")
        if getattr(self, "last_command_source", "") == "telegram":
            chat_id = getattr(self, "last_telegram_chat_id", None)
            if chat_id:
                self.send_telegram_reply(chat_id, f"Sorry {salutation}, an error occurred while executing the command: {error}")
        speech.speak(f"Sorry {salutation}, an error occurred while executing the command.")
        self._schedule_return_to_session_after_speech()

    def _speak_and_return_to_session(self, text):
        self.transition_to("SPEAKING_RESPONSE")
        if getattr(self, "last_command_source", "") == "telegram":
            chat_id = getattr(self, "last_telegram_chat_id", None)
            if chat_id:
                self.send_telegram_reply(chat_id, text)
        speech.speak(text)
        self._schedule_return_to_session_after_speech()

    # -----------------------------------------------------------------------
    # Return helpers
    # -----------------------------------------------------------------------
    def _schedule_return_to_session_after_speech(self):
        """Wait for speech to finish, then return to SESSION_LISTENING or passive."""
        def _check():
            if speech.is_speaking:
                QTimer.singleShot(100, _check)
            else:
                if self.in_session:
                    was_speaking_response = (self.state == "SPEAKING_RESPONSE")
                    self.transition_to("SESSION_LISTENING")
                    if was_speaking_response:
                        self.awaiting_followup = True
                        self._start_followup_timer()
                    self._reset_session_timer()
                else:
                    self._return_to_passive()
        QTimer.singleShot(100, _check)

    def _schedule_return_to_passive_after_speech(self):
        """Wait for speech to finish, then return to passive (non-session path)."""
        def _check():
            if speech.is_speaking:
                QTimer.singleShot(100, _check)
            else:
                self._return_to_passive()
        QTimer.singleShot(100, _check)

    def _return_to_passive(self):
        """Clean return to passive listening with wake lock release."""
        self.session_timer.stop()
        self.wake_timer.stop()
        self.in_session = False
        self.pending_command = None
        self.pending_command_type = None
        self.misheard_command = None
        self.transition_to("COOLDOWN")
        QTimer.singleShot(800, self._finish_cooldown)
    def _finish_cooldown(self):
        self.wake_locked = False
        self.transition_to("PASSIVE_WAKE_LISTENING")

    # -----------------------------------------------------------------------
    # Ambiguous action choice resolver â€” handles WAITING_FOR_CONFIRMATION with
    # a PendingActionChoice (two-option disambiguation step)
    # -----------------------------------------------------------------------
    def _try_resolve_ambiguous_choice(self, raw_text: str, source: str, session_id: str, request_id: str) -> bool:
        """
        If a PendingActionChoice is active, try to match the user's response to one of the
        available options. Returns True if the choice was handled (action chosen or cancelled).
        Returns False if no choice is active (caller should continue normal processing).
        """
        ambig_obj = getattr(self, "pending_action_choice", None)
        if ambig_obj is None:
            return False

        salutation = config.salutation
        text_lower = raw_text.lower().strip()

        # Source/session guard
        if ambig_obj.source != source or ambig_obj.session_id != session_id:
            logger.warning("Ambiguous choice response from wrong source/session â€” ignored.")
            return True

        # Expiry guard
        if time.time() > ambig_obj.expires_at:
            logger.info("Ambiguous choice expired.")
            self.pending_action_choice = None
            self.pending_command = None
            self.pending_command_type = None
            self.transition_to("SPEAKING_RESPONSE")
            speech.speak(f"Confirmation expired, {salutation}.", request_id=request_id)
            self._schedule_return_to_session_after_speech()
            return True

        from services.conversation.models import SensitiveActionType, PendingConfirmation

        exit_app_phrases = [
            "close jarvis", "exit jarvis", "close the app", "close app",
            "close application", "exit app", "exit application", "first one",
            "the first one", "first", "application"
        ]
        shutdown_pc_phrases = [
            "shut down the computer", "shutdown computer", "shut down pc",
            "turn off the computer", "turn off pc", "shut down windows",
            "shut down my computer", "second one", "the second one",
            "second", "computer"
        ]
        cancel_phrases = ["cancel", "neither", "never mind", "no", "nope", "stop"]

        if any(p in text_lower for p in cancel_phrases):
            self.pending_action_choice = None
            self.pending_command = None
            self.pending_command_type = None
            self.transition_to("SPEAKING_RESPONSE")
            speech.speak(f"Understood. No action taken, {salutation}.", request_id=request_id)
            self._schedule_return_to_session_after_speech()
            return True

        chosen_type = None
        if any(p in text_lower for p in exit_app_phrases):
            chosen_type = SensitiveActionType.EXIT_APPLICATION
        elif any(p in text_lower for p in shutdown_pc_phrases):
            chosen_type = SensitiveActionType.SHUTDOWN_COMPUTER

        if chosen_type is None:
            # Generic "yes" or unrecognized response â€” re-prompt
            logger.info("Ambiguous choice: unrecognized response. Re-prompting.")
            self.transition_to("SPEAKING_RESPONSE")
            speech.speak(f"Please say 'close JARVIS' or 'shut down the computer,' {salutation}.", request_id=request_id)
            self._schedule_return_to_session_after_speech()
            return True

        # User made a specific choice â€” now create a real PendingConfirmation for that action
        self.pending_action_choice = None
        self.pending_command_type = "sensitive_action"
        if chosen_type == SensitiveActionType.EXIT_APPLICATION:
            self.pending_command = "exit app"
            confirm_prompt = f"Do you want me to close JARVIS, {salutation}-"
        else:
            self.pending_command = "shut down pc"
            confirm_prompt = f"Do you want me to shut down your PC, {salutation}-"

        self.pending_confirmation_obj = PendingConfirmation(
            request_id=request_id,
            session_id=session_id,
            action_type=chosen_type,
            action_payload={"command": self.pending_command},
            source=source,
            created_at=time.time(),
            expires_at=time.time() - 30.0
        )
        self.transition_to("WAITING_FOR_CONFIRMATION")
        speech.speak(confirm_prompt, request_id=request_id)
        return True

    # -----------------------------------------------------------------------
    # Central sensitive-action executor
    # -----------------------------------------------------------------------
    def execute_confirmed_sensitive_action(
        self,
        action_type,
        cmd_payload: str,
        request_id: str | None = None
    ) -> None:
        """
        Central dispatcher for all confirmed sensitive actions.
        Maps SensitiveActionType values to the correct handlers.
        SHUTDOWN_COMPUTER â†’ Windows shutdown skill (NOT sleep_jarvis).
        EXIT_APPLICATION  â†’ full_exit_jarvis().
        sleep_jarvis()    â†’ ONLY called for explicit passive/standby commands.
        """
        from services.conversation.models import SensitiveActionType
        from services.system_power_controller import system_power_controller

        logger.info(f"execute_confirmed_sensitive_action: type={action_type}, payload='{cmd_payload}', req={request_id}")

        if action_type == SensitiveActionType.EXIT_APPLICATION:
            self.full_exit_jarvis()

        elif action_type == SensitiveActionType.SHUTDOWN_COMPUTER:
            salutation = config.salutation
            self.transition_to("SPEAKING_RESPONSE")
            speech.speak(f"Shutting down your PC now, {salutation}.", request_id=request_id)
            import threading
            def _delayed_shutdown():
                import time as _t
                _t.sleep(3.5)
                system_power_controller.shutdown_pc()
            threading.Thread(target=_delayed_shutdown, daemon=True).start()

        elif action_type == SensitiveActionType.RESTART_COMPUTER:
            salutation = config.salutation
            self.transition_to("SPEAKING_RESPONSE")
            speech.speak(f"Restarting your PC now, {salutation}.", request_id=request_id)
            import threading
            def _delayed_restart():
                import time as _t
                _t.sleep(3.5)
                system_power_controller.restart_pc()
            threading.Thread(target=_delayed_restart, daemon=True).start()

        elif action_type == SensitiveActionType.LOG_OUT_WINDOWS:
            salutation = config.salutation
            self.transition_to("SPEAKING_RESPONSE")
            speech.speak(f"Logging you out now, {salutation}.", request_id=request_id)
            import threading
            def _delayed_logout():
                import time as _t
                _t.sleep(3.5)
                system_power_controller.logout_pc()
            threading.Thread(target=_delayed_logout, daemon=True).start()

        elif action_type == SensitiveActionType.LOCK_COMPUTER:
            salutation = config.salutation
            self.transition_to("SPEAKING_RESPONSE")
            speech.speak(f"Locking your PC, {salutation}.", request_id=request_id)
            import threading
            def _delayed_lock():
                import time as _t
                _t.sleep(1.5)
                system_power_controller.lock_pc()
            threading.Thread(target=_delayed_lock, daemon=True).start()

        else:
            # Generic sensitive action â€” route through command worker
            self.transition_to("TRANSCRIBING_COMMAND")
            self._launch_worker(cmd_payload, request_id=request_id)

    # -----------------------------------------------------------------------
    # Sleep Jarvis â€” hide HUD, keep passive listener alive
    # -----------------------------------------------------------------------
    def sleep_jarvis(self):
        """
        Put JARVIS to sleep:
          - End session
          - Speak 'Going passive, Sir.'
          - Emit hide_hud_requested after speech ends
          - Transition to PASSIVE_WAKE_LISTENING

        The tray icon and passive wake listener remain alive.
        """
        logger.info("Sleep command. Hiding HUD and returning to passive.")
        self.session_timer.stop()
        self.wake_timer.stop()
        self.in_session = False
        self.consecutive_invalid = 0
        self.pending_command = None
        self.pending_command_type = None
        self.misheard_command = None
        self.transition_to("SLEEPING")
        salutation = config.salutation
        import random
        phrase = random.choice(SLEEP_PHRASES).format(salutation=salutation)
        speech.speak(phrase)
        # on_speech_ended() handles SLEEPING -> _do_sleep_transition()

    def _do_sleep_transition(self):
        """Called once sleep speech finishes. Hides HUD, enters passive."""
        bus.hide_hud_requested.emit()
        self.transition_to("COOLDOWN")
        QTimer.singleShot(800, self._finish_cooldown)

    # -----------------------------------------------------------------------
    # Full exit â€” terminate the application
    # -----------------------------------------------------------------------
    def full_exit_jarvis(self):
        """
        Initiate a complete application shutdown:
          - Speak a randomized offline exit phrase.
          - After speech: emit full_exit_requested -> HUDWindow.exit_app()
        """
        logger.info("Full application exit initiated.")
        self.session_timer.stop()
        self.wake_timer.stop()
        self.wake_locked = True
        self.in_session = False
        self.pending_command = None
        self.pending_command_type = None
        self.misheard_command = None
        self.transition_to("SHUTTING_DOWN")
        salutation = config.salutation
        import random
        phrase = random.choice(EXIT_PHRASES).format(salutation=salutation)
        speech.speak(phrase)
        # on_speech_ended() handles SHUTTING_DOWN -> full_exit_requested

    # -----------------------------------------------------------------------
    # Fuzzy command correction
    # -----------------------------------------------------------------------
    def correct_command(self, command: str):
        """Fuzzy matching. Returns (corrected_command, confidence_float)."""
        cmd = command.lower().strip()

        for key, variants in KNOWN_COMMANDS.items():
            if cmd == key or cmd in variants:
                return key, 1.0

        best_match = None
        best_score = 0.0

        for key, variants in KNOWN_COMMANDS.items():
            score = SequenceMatcher(None, cmd, key).ratio()
            if score > best_score:
                best_score = score
                best_match = key
            for variant in variants:
                score = SequenceMatcher(None, cmd, variant).ratio()
                if score > best_score:
                    best_score = score
                    best_match = key

        return best_match, best_score

    # -----------------------------------------------------------------------
    # Command execution routing
    # -----------------------------------------------------------------------
    def route_and_execute(self, command: str, fallback_only: bool = False) -> str:
        """Execute a normalized command string. Called from CommandWorker thread."""
        command = (command or "").strip()
        if not command:
            return f"Sorry Sir, I did not receive a command."

        if fallback_only:
            logger.info(f"Bypassing skill routing. Directing command to brain: {command!r}")
            return brain.think_stream(command)

        cmd_lower = command.lower()
        salutation = config.salutation
        logger.info(f"Executing normalized command: {command!r}")

        # Intercept Music Space commands if currently active
        if getattr(self, "current_space", None) == "music":
            from services.music_space_controller import music_space_controller
            res = music_space_controller.handle_voice_command(command)
            if res is not None:
                speech.speak(res)
                return res

        # Handle Music Space Toggles
        cmd_clean = re.sub(r"[.,!-;:'\"]-", "", cmd_lower).strip()
        if cmd_clean in ("open music space", "go to music space", "music space"):
            if getattr(self, "current_space", None) == "music":
                return f"Music space is already open, {salutation}."
            self.current_space = "music"
            bus.command_status.emit("space_changed:music")
            from services.music_space_controller import music_space_controller
            music_space_controller.sync()
            speech.speak("Music space opened, ready.")
            return f"Music space opened, ready."

        if cmd_clean in ("close music space", "exit music space"):
            if getattr(self, "current_space", None) != "music":
                return f"We are not in music space, {salutation}."
            self.current_space = None
            bus.command_status.emit("space_changed:none")
            speech.speak("Exiting music space.")
            return f"Exiting music space."

        # Handle confirmed phone call executions
        if command.startswith("place_call_confirmed:"):
            parts = command.split(":")
            number = parts[1]
            name = parts[2] if len(parts) > 2 else "Unknown"

            # Record interaction
            if name != "Unknown":
                from services.contacts_service import contacts_service
                contacts_service.record_interaction(name)

            # Dispatch call trigger via local HTTP phone bridge
            from services.phone_bridge import trigger_phone_call
            success, msg = trigger_phone_call(number)
            if not success:
                speech.speak(msg)
                if getattr(self, "last_command_source", "") == "telegram":
                    chat_id = getattr(self, "last_telegram_chat_id", None)
                    if chat_id:
                        self.send_telegram_reply(chat_id, msg)
                return msg

            return f"Placing call to {name}, {salutation}."

        # Handle direct file creation confirmed executions
        if command.startswith("create_file_confirmed:"):
            filepath = command[len("create_file_confirmed:"):].strip()
            filename = os.path.basename(filepath)

            user_home = os.path.expanduser("~")
            if filepath.startswith(os.path.join(user_home, "Desktop")):
                loc_disp = "desktop"
            elif filepath.startswith(os.path.join(user_home, "Documents")):
                loc_disp = "documents"
            elif filepath.startswith(os.path.join(user_home, "Downloads")):
                loc_disp = "downloads"
            else:
                loc_disp = "workspace"

            try:
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(f"# Mapped file created by JARVIS M7 on {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

                logger.info(f"File created successfully: '{filepath}'")
                if getattr(self, "last_command_source", "") == "telegram":
                    chat_id = getattr(self, "last_telegram_chat_id", None)
                    if chat_id:
                        self.telegram_bot.send_document(chat_id, filepath, f"Here is the created file: <b>{filename}</b>")
                return f"I have successfully created the file {filename} in your {loc_disp}, {salutation}."
            except Exception as e:
                logger.error(f"Failed to create file: {e}")
                return f"I failed to create the file {filename}, {salutation}."

        # System-level tray trigger
        if cmd_lower in ("settings", "open settings"):
            QTimer.singleShot(500, lambda: bus.command_status.emit("settings_request"))
            return f"Opening Configuration Panel, {salutation}."

        # Handle direct app discovery refresh
        if cmd_lower == "refresh app index":
            from services.app_discovery_service import app_discovery_service
            apps = app_discovery_service.discover_all()
            return f"App index refreshed. I found {len(apps)} applications installed, {salutation}."

        # Handle enable autostart
        if cmd_lower in ("enable autostart", "enable auto start"):
            try:
                config.set("autostart_enabled", True)
                return f"Autostart has been enabled, {salutation}."
            except Exception as e:
                logger.error(f"Failed to enable autostart: {e}")
                return f"Sorry {salutation}, I failed to enable autostart in the registry."

        # Handle disable autostart
        if cmd_lower in ("disable autostart", "disable auto start"):
            try:
                config.set("autostart_enabled", False)
                return f"Autostart has been disabled, {salutation}."
            except Exception as e:
                logger.error(f"Failed to disable autostart: {e}")
                return f"Sorry {salutation}, I failed to disable autostart in the registry."

        # Handle open app
        if cmd_lower.startswith(("open ", "launch ", "start ", "run ")):
            verb, _, target = cmd_lower.partition(" ")
            target = target.strip()
            if target:
                from services.app_resolver import app_resolver
                match = app_resolver.resolve_app(target)
                if match:
                    try:
                        os.startfile(match.launch_target)
                        from core.telemetry import pipeline_timer
                        pipeline_timer.log_event("action executed OR LLM response received")
                        logger.info(f"Opened app: {match.display_name}")
                        return f"Opening {match.display_name}, {salutation}."
                    except Exception as e:
                        logger.error(f"Failed to open {match.display_name}: {e}")
                        return f"I encountered an error trying to open {match.display_name}, {salutation}."

        # Handle close / kill app
        if cmd_lower.startswith(("close ", "stop ", "kill ", "quit ")):
            verb, _, target = cmd_lower.partition(" ")
            target = target.strip()
            if target:
                from services.app_resolver import app_resolver
                match = app_resolver.resolve_app(target)
                if match and match.process_names:
                    import psutil
                    closed_any = False
                    for proc in psutil.process_iter(["pid", "name"]):
                        try:
                            pname = proc.info["name"]
                            if pname and pname.lower() in [n.lower() for n in match.process_names]:
                                proc.terminate()
                                closed_any = True
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                    if closed_any:
                        logger.info(f"Closed app: {match.display_name}")
                        return f"Closing {match.display_name}, {salutation}."
                    else:
                        return f"{match.display_name} is not currently running, {salutation}."

        # Local registered skills
        local_result = skill_manager.route_command(command, engine=self)
        if local_result is not None:
            return local_result

        # Fallback to Gemini Brain
        if config.gemini_quota_saver_mode:
            cmd_lower = command.lower()
            app_control_verbs = {"open", "close", "launch", "start", "run", "stop", "kill", "exit"}
            if any(verb in cmd_lower.split() for verb in app_control_verbs):
                return f"I cannot resolve that application control command offline, {salutation}."

        return brain.think_stream(command)
