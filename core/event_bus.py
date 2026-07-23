from PyQt6.QtCore import QObject, pyqtSignal

class EventBus(QObject):
    """
    A thread-safe Event Bus using PyQt6 signals.
    Decouples modules (wake listener, engine, UI HUD, logging).
    """
    # Wake events
    wake_detected = pyqtSignal(str)  # wake source: 'voice', 'clap', 'shortcut', 'tray'
    sleep_timeout = pyqtSignal()     # returned to passive listening
    
    # State transitions
    # States: 'Passive Listening', 'Listening', 'Thinking', 'Executing', 'Speaking', 'Completed'
    state_changed = pyqtSignal(str)  
    
    # Audio/Speech events
    speech_started = pyqtSignal(str) # text being spoken
    speech_ended = pyqtSignal()
    speech_interrupted = pyqtSignal()
    command_heard = pyqtSignal(str)  # transcribed text command
    stream_token_received = pyqtSignal(str) # streamed LLM token sentence chunk

    # Audio lifecycle — emitted by audio_service, consumed by engine
    # Engine owns ALL state transitions; audio_service never emits state_changed for engine states.
    command_recording_started      = pyqtSignal()       # user voice detected in ACTIVE_COMMAND_LISTENING
    command_recording_stopped      = pyqtSignal()       # silence ended recording (before transcription)
    command_transcription_started  = pyqtSignal()       # STT pipeline is about to run
    command_transcription_completed = pyqtSignal(str)   # transcription succeeded; payload = text
    command_transcription_failed   = pyqtSignal(str)    # transcription failed or empty; payload = reason

    # Command execution events
    command_received = pyqtSignal(str) # raw text command to process
    command_status = pyqtSignal(str)   # visual update status (e.g. "Opening VS Code, Sir")
    command_completed = pyqtSignal(bool, str) # success status, message
    command_diagnostics = pyqtSignal(dict) # raw, normalized, corrected, confidence, executed
    
    # System monitor events
    system_stats_updated = pyqtSignal(dict) # CPU, RAM, Storage, Battery, Net
    
    # HUD lifecycle events (engine → UI)
    show_hud_requested = pyqtSignal()   # Wake detected while HUD hidden — show and bring to front
    hide_hud_requested = pyqtSignal()   # Sleep/passive command — hide HUD, keep tray & listener alive
    full_exit_requested = pyqtSignal()  # Full app termination — stop all threads, quit QApplication

    # Console feed events
    console_log = pyqtSignal(str, str) # level (INFO, WARN, etc), message
    
    # Music Space events (engine -> HUD)
    music_space_updated = pyqtSignal(dict)
    
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = EventBus()
        return cls._instance

# Global event bus access
bus = EventBus.get_instance()
