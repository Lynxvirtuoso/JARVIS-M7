"""
ui/hud/config_panel.py
Full-screen futuristic configuration overlay panel.
Allows live editing of STT/Brain/TTS providers, microphone,
gain, trust gates, salutation, and autostart.
"""
import psutil
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QSlider, QCheckBox, QLineEdit, QScrollArea,
    QFrame, QSizePolicy, QSpacerItem, QProgressBar,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QPainter, QPen, QColor, QLinearGradient

from core.logger import logger

from ui.hud.theme import (
    BG_VOID, BG_PANEL, BG_PANEL_2, COLOR_CYAN, COLOR_CYAN_DIM,
    COLOR_CYAN_FAINT, COLOR_TEXT, COLOR_TEXT_DIM, COLOR_AMBER,
    get_orbitron_family, get_mono_family
)


# ── Reusable Section Header ───────────────────────────────
class _SectionHeader(QLabel):
    def __init__(self, text: str, parent=None):
        super().__init__(text.upper(), parent)
        self.setStyleSheet(
            f"font-family: '{get_orbitron_family()}'; font-size: 9px; font-weight: 700;"
            f"color: {COLOR_CYAN}; letter-spacing: 3px; padding: 0; background: transparent;"
        )
        self.setFixedHeight(20)


# ── Reusable Labeled Row ──────────────────────────────────
class _Row(QWidget):
    def __init__(self, label: str, widget: QWidget, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        hl = QHBoxLayout(self)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(12)

        lbl = QLabel(label, self)
        lbl.setFixedWidth(170)
        lbl.setStyleSheet(
            f"font-family: '{get_mono_family()}'; font-size: 10px;"
            f"color: {COLOR_TEXT_DIM}; background: transparent;"
        )
        hl.addWidget(lbl)
        hl.addWidget(widget, stretch=1)


# ── HUD-styled QComboBox ──────────────────────────────────
def _make_combo(items: list[str], current: str = "") -> QComboBox:
    cb = QComboBox()
    cb.addItems(items)
    if current in items:
        cb.setCurrentText(current)
    cb.setStyleSheet(f"""
        QComboBox {{
            font-family: '{get_mono_family()}'; font-size: 10px;
            background: {BG_PANEL_2}; color: {COLOR_TEXT};
            border: 1px solid {COLOR_CYAN_FAINT}; padding: 4px 8px;
        }}
        QComboBox:hover {{ border-color: {COLOR_CYAN_DIM}; }}
        QComboBox::drop-down {{ border: none; }}
        QComboBox QAbstractItemView {{
            background: {BG_PANEL}; color: {COLOR_TEXT};
            border: 1px solid {COLOR_CYAN_DIM};
            selection-background-color: {COLOR_CYAN_DIM};
        }}
    """)
    return cb


# ── HUD-styled QSlider ────────────────────────────────────
def _make_slider(min_v: int, max_v: int, value: int) -> QSlider:
    sl = QSlider(Qt.Orientation.Horizontal)
    sl.setRange(min_v, max_v)
    sl.setValue(value)
    sl.setStyleSheet(f"""
        QSlider::groove:horizontal {{
            height: 2px; background: {COLOR_CYAN_FAINT};
        }}
        QSlider::handle:horizontal {{
            width: 12px; height: 12px; margin: -5px 0;
            background: {COLOR_CYAN}; border-radius: 6px;
        }}
        QSlider::sub-page:horizontal {{
            background: {COLOR_CYAN_DIM};
        }}
    """)
    return sl


# ── HUD-styled QLineEdit ──────────────────────────────────
def _make_edit(text: str = "") -> QLineEdit:
    le = QLineEdit(text)
    le.setStyleSheet(f"""
        QLineEdit {{
            font-family: '{get_mono_family()}'; font-size: 10px;
            background: {BG_PANEL_2}; color: {COLOR_TEXT};
            border: 1px solid {COLOR_CYAN_FAINT}; padding: 4px 8px;
        }}
        QLineEdit:focus {{ border-color: {COLOR_CYAN}; }}
    """)
    return le


# ── HUD-styled QCheckBox ──────────────────────────────────
def _make_check(checked: bool = False) -> QCheckBox:
    cb = QCheckBox()
    cb.setChecked(checked)
    cb.setStyleSheet(f"""
        QCheckBox::indicator {{
            width: 14px; height: 14px;
            border: 1px solid {COLOR_CYAN_DIM};
            background: {BG_PANEL_2};
        }}
        QCheckBox::indicator:checked {{
            background: {COLOR_CYAN};
            border-color: {COLOR_CYAN};
        }}
    """)
    return cb


# ── Separator ─────────────────────────────────────────────
def _make_sep() -> QFrame:
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.HLine)
    sep.setFixedHeight(1)
    sep.setStyleSheet(f"background: {COLOR_CYAN_FAINT}; border: none;")
    return sep


# ── Main Config Panel ─────────────────────────────────────
class ConfigPanel(QWidget):
    """
    Futuristic full-overlay configuration panel.
    Slide in from the right via show()/hide().
    """
    closed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(460)
        self.setStyleSheet(f"background-color: {BG_VOID};")
        self.setVisible(False)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Title bar ─────────────────────────────────────
        title_bar = QWidget(self)
        title_bar.setFixedHeight(54)
        title_bar.setStyleSheet(
            f"background: {BG_PANEL}; border-bottom: 1px solid {COLOR_CYAN_FAINT};"
        )
        tb_layout = QHBoxLayout(title_bar)
        tb_layout.setContentsMargins(20, 0, 16, 0)
        tb_layout.setSpacing(0)

        title_lbl = QLabel("CONFIGURATION", title_bar)
        title_lbl.setStyleSheet(
            f"font-family: '{get_orbitron_family()}'; font-size: 13px; font-weight: bold;"
            f"color: {COLOR_CYAN}; letter-spacing: 5px; background: transparent;"
        )
        tb_layout.addWidget(title_lbl)
        tb_layout.addStretch()

        close_btn = QPushButton("✕", title_bar)
        close_btn.setFixedSize(28, 28)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {COLOR_TEXT_DIM};
                border: 1px solid {COLOR_CYAN_FAINT}; font-size: 12px;
            }}
            QPushButton:hover {{ color: {COLOR_CYAN}; border-color: {COLOR_CYAN}; }}
        """)
        close_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        close_btn.clicked.connect(self.close_panel)
        tb_layout.addWidget(close_btn)
        root.addWidget(title_bar)

        # ── Scrollable body ───────────────────────────────
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet(f"""
            QScrollArea {{ border: none; background: {BG_VOID}; }}
            QScrollBar:vertical {{
                border: none; background: #050B14; width: 3px; margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {COLOR_CYAN_DIM}; min-height: 14px; border-radius: 1px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                border: none; background: none;
            }}
        """)

        body = QWidget()
        body.setStyleSheet(f"background: {BG_VOID};")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(20, 20, 20, 20)
        body_layout.setSpacing(14)

        # ── Load current config ───────────────────────────
        try:
            from core.config import config
        except Exception:
            config = None

        def _get(key, default=""):
            if config:
                v = config.get(key, default)
                return str(v) if v is not None else default
            return default

        # ════ PROVIDERS ════
        body_layout.addWidget(_SectionHeader("Providers"))
        body_layout.addWidget(_make_sep())

        self.stt_combo = _make_combo(
            ["groq_stt", "local_faster_whisper", "gemini_stt", "openai_stt", "deepgram"],
            _get("stt_provider", "groq_stt")
        )
        body_layout.addWidget(_Row("STT Provider", self.stt_combo))

        self.brain_combo = _make_combo(
            ["groq", "ollama", "gemini"],
            _get("brain_provider", "groq")
        )
        body_layout.addWidget(_Row("Brain Provider", self.brain_combo))

        self.brain_mode_combo = _make_combo(
            ["smart_auto", "manual"],
            _get("brain_mode", "smart_auto")
        )
        body_layout.addWidget(_Row("Brain Mode", self.brain_mode_combo))

        self.ollama_model_edit = _make_edit(_get("ollama_model", "qwen3:1.7b"))
        body_layout.addWidget(_Row("Ollama Model", self.ollama_model_edit))

        self.ollama_think_check = _make_check(_get("ollama_think", "false").lower() == "true")
        body_layout.addWidget(_Row("Qwen Thinking Mode", self.ollama_think_check))

        self.ollama_ctx_combo = _make_combo(["2048", "4096"], _get("ollama_num_ctx", "2048"))
        body_layout.addWidget(_Row("Local Context Size", self.ollama_ctx_combo))

        self.local_only_check = _make_check(_get("local_only_mode", "false").lower() == "true")
        body_layout.addWidget(_Row("Local-Only Mode", self.local_only_check))

        self.tts_combo = _make_combo(
            ["kokoro", "gemini_tts", "sapi", "elevenlabs"],
            _get("tts_provider", "kokoro")
        )
        body_layout.addWidget(_Row("TTS Provider", self.tts_combo))

        # ════ AUDIO ════
        body_layout.addSpacing(8)
        body_layout.addWidget(_SectionHeader("Audio"))
        body_layout.addWidget(_make_sep())

        # Mic selector — populated from pyaudio
        mic_names = self._get_mic_list()
        current_mic = _get("selected_microphone_index", "0")
        try:
            current_mic_idx = int(current_mic)
        except ValueError:
            current_mic_idx = 0
        self.mic_combo = _make_combo(
            mic_names,
            mic_names[current_mic_idx] if current_mic_idx < len(mic_names) else (mic_names[0] if mic_names else "")
        )
        body_layout.addWidget(_Row("Microphone", self.mic_combo))

        gain_val = int(float(_get("input_gain_boost_db", "0")))
        self.gain_slider = _make_slider(-10, 20, gain_val)
        self.gain_val_lbl = QLabel(f"{gain_val:+d} dB", self)
        self.gain_val_lbl.setFixedWidth(50)
        self.gain_val_lbl.setStyleSheet(
            f"font-family: '{get_mono_family()}'; font-size: 10px;"
            f"color: {COLOR_CYAN}; background: transparent;"
        )
        self.gain_slider.valueChanged.connect(self.on_gain_slider_changed)
        gain_row_w = QWidget(); gain_row_w.setStyleSheet("background:transparent;")
        gain_row_hl = QHBoxLayout(gain_row_w)
        gain_row_hl.setContentsMargins(0,0,0,0); gain_row_hl.setSpacing(8)
        gain_row_hl.addWidget(self.gain_slider, stretch=1)
        gain_row_hl.addWidget(self.gain_val_lbl)
        body_layout.addWidget(_Row("Input Gain Boost", gain_row_w))

        # ════ MIC TEST & MONITOR ════
        body_layout.addSpacing(8)
        body_layout.addWidget(_SectionHeader("Mic Test & Monitor"))
        body_layout.addWidget(_make_sep())

        # Feedback warning label
        feedback_warning = QLabel("⚠️ USE HEADPHONES TO PREVENT ACOUSTIC FEEDBACK", self)
        feedback_warning.setStyleSheet(
            f"font-family: '{get_orbitron_family()}'; font-size: 8px; font-weight: bold;"
            f"color: #FF5E5E; background: transparent; padding: 2px 0;"
        )
        body_layout.addWidget(feedback_warning)

        # Toggle Button
        self.monitor_btn = QPushButton("Start Monitoring", self)
        self.monitor_btn.setFixedHeight(30)
        self.monitor_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {COLOR_CYAN};
                border: 1px solid {COLOR_CYAN_FAINT}; font-size: 11px;
            }}
            QPushButton:hover {{ background: #082137; }}
        """)
        self.monitor_btn.clicked.connect(self.toggle_monitoring)
        body_layout.addWidget(_Row("Live Monitor", self.monitor_btn))

        # Live Level Meter
        self.vu_bar = QProgressBar(self)
        self.vu_bar.setRange(0, 100)
        self.vu_bar.setValue(0)
        self.vu_bar.setTextVisible(False)
        self.vu_bar.setFixedHeight(8)
        self.vu_bar.setStyleSheet(f"""
            QProgressBar {{
                border: 1px solid {COLOR_CYAN_FAINT};
                background: #02060C;
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background-color: {COLOR_CYAN};
            }}
        """)
        body_layout.addWidget(_Row("Level Meter", self.vu_bar))

        # Setup monitoring variables & timer
        self.monitor_stream = None
        self.live_monitor_gain = float(gain_val)
        self.current_monitor_rms = 0.0
        
        self.vu_timer = QTimer(self)
        self.vu_timer.timeout.connect(self.update_vu_meter)

        # ════ IDENTITY ════
        body_layout.addSpacing(8)
        body_layout.addWidget(_SectionHeader("Identity"))
        body_layout.addWidget(_make_sep())

        self.salutation_edit = _make_edit(_get("salutation", "Sir"))
        body_layout.addWidget(_Row("Salutation", self.salutation_edit))

        self.owner_edit = _make_edit(_get("owner_name", ""))
        body_layout.addWidget(_Row("Owner Name", self.owner_edit))

        # ════ TRUST GATE ════
        body_layout.addSpacing(8)
        body_layout.addWidget(_SectionHeader("Trust Gate"))
        body_layout.addWidget(_make_sep())

        tg_typed = int(float(_get("trust_gate_typed_min_confidence", "0.4")) * 100)
        self.tg_typed_slider = _make_slider(0, 100, tg_typed)
        self.tg_typed_lbl = QLabel(f"{tg_typed}%", self)
        self.tg_typed_lbl.setFixedWidth(40)
        self.tg_typed_lbl.setStyleSheet(
            f"font-family: '{get_mono_family()}'; font-size: 10px;"
            f"color: {COLOR_CYAN}; background: transparent;"
        )
        self.tg_typed_slider.valueChanged.connect(
            lambda v: self.tg_typed_lbl.setText(f"{v}%")
        )
        tg_typed_w = QWidget(); tg_typed_w.setStyleSheet("background:transparent;")
        tg_typed_hl = QHBoxLayout(tg_typed_w)
        tg_typed_hl.setContentsMargins(0,0,0,0); tg_typed_hl.setSpacing(8)
        tg_typed_hl.addWidget(self.tg_typed_slider, stretch=1)
        tg_typed_hl.addWidget(self.tg_typed_lbl)
        body_layout.addWidget(_Row("Typed Min Confidence", tg_typed_w))

        tg_voice = int(float(_get("trust_gate_voice_min_confidence", "0.6")) * 100)
        self.tg_voice_slider = _make_slider(0, 100, tg_voice)
        self.tg_voice_lbl = QLabel(f"{tg_voice}%", self)
        self.tg_voice_lbl.setFixedWidth(40)
        self.tg_voice_lbl.setStyleSheet(
            f"font-family: '{get_mono_family()}'; font-size: 10px;"
            f"color: {COLOR_CYAN}; background: transparent;"
        )
        self.tg_voice_slider.valueChanged.connect(
            lambda v: self.tg_voice_lbl.setText(f"{v}%")
        )
        tg_voice_w = QWidget(); tg_voice_w.setStyleSheet("background:transparent;")
        tg_voice_hl = QHBoxLayout(tg_voice_w)
        tg_voice_hl.setContentsMargins(0,0,0,0); tg_voice_hl.setSpacing(8)
        tg_voice_hl.addWidget(self.tg_voice_slider, stretch=1)
        tg_voice_hl.addWidget(self.tg_voice_lbl)
        body_layout.addWidget(_Row("Voice Min Confidence", tg_voice_w))

        # ════ SYSTEM ════
        body_layout.addSpacing(8)
        body_layout.addWidget(_SectionHeader("System"))
        body_layout.addWidget(_make_sep())

        self.autostart_check = _make_check(
            _get("autostart_enabled", "false").lower() == "true"
        )
        body_layout.addWidget(_Row("Launch on Windows Startup", self.autostart_check))

        self.quota_saver_check = _make_check(
            _get("gemini_quota_saver_mode", "true").lower() == "true"
        )
        body_layout.addWidget(_Row("Gemini Quota Saver Mode", self.quota_saver_check))

        popup_delay = int(_get("response_popup_dismiss_delay", "5"))
        self.popup_slider = _make_slider(1, 30, popup_delay)
        self.popup_lbl = QLabel(f"{popup_delay}s", self)
        self.popup_lbl.setFixedWidth(40)
        self.popup_lbl.setStyleSheet(
            f"font-family: '{get_mono_family()}'; font-size: 10px;"
            f"color: {COLOR_CYAN}; background: transparent;"
        )
        self.popup_slider.valueChanged.connect(
            lambda v: self.popup_lbl.setText(f"{v}s")
        )
        popup_w = QWidget(); popup_w.setStyleSheet("background:transparent;")
        popup_hl = QHBoxLayout(popup_w)
        popup_hl.setContentsMargins(0,0,0,0); popup_hl.setSpacing(8)
        popup_hl.addWidget(self.popup_slider, stretch=1)
        popup_hl.addWidget(self.popup_lbl)
        body_layout.addWidget(_Row("Response Popup Delay", popup_w))

        body_layout.addStretch()
        scroll.setWidget(body)
        root.addWidget(scroll, stretch=1)

        # ── Bottom Save bar ────────────────────────────────
        save_bar = QWidget(self)
        save_bar.setFixedHeight(60)
        save_bar.setStyleSheet(
            f"background: {BG_PANEL}; border-top: 1px solid {COLOR_CYAN_FAINT};"
        )
        sb_layout = QHBoxLayout(save_bar)
        sb_layout.setContentsMargins(20, 0, 20, 0)
        sb_layout.setSpacing(10)

        self.status_lbl = QLabel("", save_bar)
        self.status_lbl.setStyleSheet(
            f"font-family: '{get_mono_family()}'; font-size: 10px;"
            f"color: {COLOR_CYAN}; background: transparent;"
        )
        sb_layout.addWidget(self.status_lbl, stretch=1)

        cancel_btn = QPushButton("CANCEL", save_bar)
        cancel_btn.setFixedSize(90, 32)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                font-family: '{get_mono_family()}'; font-size: 10px;
                background: transparent; color: {COLOR_TEXT_DIM};
                border: 1px solid {COLOR_CYAN_FAINT}; padding: 0;
            }}
            QPushButton:hover {{ color: {COLOR_TEXT}; border-color: {COLOR_CYAN_DIM}; }}
        """)
        cancel_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        cancel_btn.clicked.connect(self.close_panel)
        sb_layout.addWidget(cancel_btn)

        save_btn = QPushButton("SAVE", save_bar)
        save_btn.setFixedSize(90, 32)
        save_btn.setStyleSheet(f"""
            QPushButton {{
                font-family: '{get_mono_family()}'; font-size: 10px;
                background: {COLOR_CYAN_DIM}; color: {COLOR_CYAN};
                border: 1px solid {COLOR_CYAN}; padding: 0;
            }}
            QPushButton:hover {{ background: {COLOR_CYAN}; color: {BG_VOID}; }}
        """)
        save_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        save_btn.clicked.connect(self.save_config)
        sb_layout.addWidget(save_btn)

        root.addWidget(save_bar)

    # ── Helpers ───────────────────────────────────────────
    def _get_mic_list(self) -> list[str]:
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            hostapis = sd.query_hostapis()
            mics = []
            for i, dev in enumerate(devices):
                if dev.get("max_input_channels", 0) > 0:
                    backend = hostapis[dev.get("hostapi")]["name"]
                    mics.append(f"[{i}] {dev['name'][:30]} ({backend})")
            return mics if mics else ["[0] Default Microphone"]
        except Exception as e:
            logger.error(f"Error querying mic list: {e}")
            return ["[0] Default Microphone"]

    def open_panel(self):
        self.setVisible(True)
        self.raise_()

    def close_panel(self):
        self.stop_monitoring()
        self.setVisible(False)
        self.closed.emit()

    def toggle_monitoring(self):
        if self.monitor_stream is not None:
            self.stop_monitoring()
        else:
            self.start_monitoring()

    def start_monitoring(self):
        try:
            from services.audio_service import audio_service
            logger.info("Suspending main audio service for mic test...")
            audio_service.suspend_listening()

            # Resolve selected mic index
            mic_text = self.mic_combo.currentText()
            input_device_idx = 0
            if mic_text.startswith("["):
                input_device_idx = int(mic_text.split("]")[0].replace("[", "").strip())

            import sounddevice as sd
            import numpy as np
            self.live_monitor_gain = float(self.gain_slider.value())
            self.current_monitor_rms = 0.0

            # Combined duplex stream callback (capture and play back immediately)
            def callback(indata, outdata, frames, time, status):
                # Save input RMS for level meter
                self.current_monitor_rms = float(np.sqrt(np.mean(indata**2)))

                # Apply live gain boost from self.live_monitor_gain in real time
                gain_db = self.live_monitor_gain
                gain_factor = 10 ** (gain_db / 20.0)

                # Acoustic feedback loop limit: cap playback gain factor to +12dB
                max_play_factor = 10 ** (12.0 / 20.0)
                effective_factor = min(gain_factor, max_play_factor)

                processed = indata * effective_factor
                # Apply soft limiter to avoid howling spikes
                processed = np.clip(processed, -0.95, 0.95)

                outdata[:] = processed

            try:
                device_info = sd.query_devices(input_device_idx)
                rate = int(device_info.get("default_samplerate", 16000))
            except Exception:
                rate = 16000

            logger.info(f"Opening low-latency duplex Stream on mic index {input_device_idx} at {rate}Hz...")
            self.monitor_stream = sd.Stream(
                device=(input_device_idx, None),  # Selected mic in, default output out
                samplerate=rate, channels=1,
                callback=callback, blocksize=512,
                latency='low', dtype='float32'
            )
            self.monitor_stream.start()

            self.monitor_btn.setText("Stop Monitoring")
            self.monitor_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {COLOR_CYAN_FAINT}; color: {COLOR_CYAN};
                    border: 1px solid {COLOR_CYAN}; font-size: 11px; font-weight: bold;
                }}
            """)

            self.vu_timer.start(50)
            logger.info("Low-latency mic test monitoring stream started.")
        except Exception as e:
            logger.error(f"Failed to start mic monitoring: {e}")
            self.status_lbl.setText(f"✗ Mic Test Error: {e}")
            self.stop_monitoring()

    def stop_monitoring(self):
        self.vu_timer.stop()
        self.vu_bar.setValue(0)

        if self.monitor_stream is not None:
            try:
                self.monitor_stream.stop()
                self.monitor_stream.close()
            except Exception as e:
                logger.error(f"Error stopping duplex stream: {e}")
            self.monitor_stream = None

        self.monitor_btn.setText("Start Monitoring")
        self.monitor_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {COLOR_CYAN};
                border: 1px solid {COLOR_CYAN_FAINT}; font-size: 11px;
            }}
            QPushButton:hover {{ background: #082137; }}
        """)

        # Resume main audio service listening
        try:
            from services.audio_service import audio_service
            audio_service.resume_listening()
        except Exception as e:
            logger.error(f"Error resuming main audio service: {e}")

    def update_vu_meter(self):
        # Translate RMS to 0-100 range visually
        # A typical speech level goes up to 0.15-0.20 RMS
        val = int(min(1.0, self.current_monitor_rms / 0.15) * 100)
        self.vu_bar.setValue(val)

    def on_gain_slider_changed(self, val):
        self.gain_val_lbl.setText(f"{val:+d} dB")
        # Update live monitor gain in real time for duplex stream
        self.live_monitor_gain = float(val)

    def save_config(self):
        try:
            from core.config import config

            config.set("stt_provider",   self.stt_combo.currentText())
            config.set("brain_provider", self.brain_combo.currentText())
            config.set("brain_mode",     self.brain_mode_combo.currentText())
            config.set("ollama_model",   self.ollama_model_edit.text().strip() or "qwen3:1.7b")
            config.set("ollama_think",   str(self.ollama_think_check.isChecked()).lower())
            config.set("ollama_num_ctx", self.ollama_ctx_combo.currentText())
            config.set("local_only_mode", str(self.local_only_check.isChecked()).lower())
            config.set("tts_provider",   self.tts_combo.currentText())
            config.set("salutation",     self.salutation_edit.text().strip() or "Sir")
            config.set("owner_name",     self.owner_edit.text().strip())
            config.set("input_gain_boost_db", str(self.gain_slider.value()))
            config.set("trust_gate_typed_min_confidence",
                       str(self.tg_typed_slider.value() / 100.0))
            config.set("trust_gate_voice_min_confidence",
                       str(self.tg_voice_slider.value() / 100.0))
            config.set("autostart_enabled",        str(self.autostart_check.isChecked()).lower())
            config.set("gemini_quota_saver_mode",  str(self.quota_saver_check.isChecked()).lower())
            config.set("response_popup_dismiss_delay", str(self.popup_slider.value()))

            # Mic: extract index from "[idx] Name"
            mic_text = self.mic_combo.currentText()
            if mic_text.startswith("["):
                idx_str = mic_text.split("]")[0].replace("[", "").strip()
                config.set("selected_microphone_index", idx_str)
                try:
                    idx = int(idx_str)
                    import sounddevice as sd
                    dev_info = sd.query_devices(idx)
                    hostapis = sd.query_hostapis()
                    backend = hostapis[dev_info.get("hostapi")]["name"]
                    config.set("mic_device_name", dev_info.get("name"))
                    config.set("mic_device_backend", backend)
                except Exception as e:
                    logger.error(f"Error resolving mic name/backend for index {idx_str}: {e}")

            # Recalibrate noise floor since device or gain settings changed
            try:
                from services.audio_service import audio_service
                audio_service.calibrated = False
                audio_service.restart_stream()
            except Exception:
                pass

            self.status_lbl.setText("✓ Saved — restart to apply provider changes")
            QTimer.singleShot(3000, lambda: self.status_lbl.setText(""))
        except Exception as e:
            self.status_lbl.setText(f"✗ Error: {e}")

    # ── Paint ─────────────────────────────────────────────
    def paintEvent(self, event):
        p = QPainter(self)
        # Left edge accent line
        p.setPen(QPen(QColor(COLOR_CYAN_DIM), 1))
        p.drawLine(0, 0, 0, self.height())
