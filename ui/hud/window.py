import sys
import math
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QLineEdit, QLabel, QPushButton, QSystemTrayIcon, QMenu,
                             QGroupBox, QTextEdit, QPlainTextEdit, QSizePolicy, QScrollArea)
from PyQt6.QtCore import Qt, QPoint, QPointF, QTimer, pyqtSlot
from PyQt6.QtGui import (QColor, QFont, QIcon, QPainter, QBrush, QAction,
                         QPen, QKeySequence, QShortcut, QTextCursor, QLinearGradient)

from core.event_bus import bus
from core.logger import logger
from core.config import config
from ui.hud.core_widget import AICoreWidget
from ui.hud.waveform import WaveformWidget
from ui.hud.stats_widget import StatsWidget

# ──────────────────────────────────────────────────────────
# Design constants — exact match to approved mockup
# ──────────────────────────────────────────────────────────
BG_DARK     = "rgba(5, 11, 20, 235)"
BORDER_DIM  = "rgba(34, 211, 238, 60)"
BORDER_MED  = "rgba(34, 211, 238, 120)"
BORDER_FULL = "#22d3ee"
ACCENT_CYAN = "#22d3ee"
ACCENT_TEAL = "#5eead4"
TEXT_DIM    = "#94a3b8"
TEXT_BRIGHT = "#e2e8f0"
FONT_MONO   = "Consolas"

PANEL_STYLE = f"""
QGroupBox {{
    background-color: rgba(5, 15, 30, 200);
    border: 1px solid {BORDER_DIM};
    border-radius: 4px;
    margin-top: 14px;
    padding: 6px 8px 8px 8px;
    font-family: {FONT_MONO};
    font-size: 9px;
    font-weight: bold;
    color: {ACCENT_CYAN};
    letter-spacing: 2px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 4px;
    color: {ACCENT_CYAN};
}}
"""

SCROLLBAR_STYLE = f"""
QScrollBar:vertical {{
    border: none;
    background: rgba(5,11,20,100);
    width: 4px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {BORDER_MED};
    min-height: 20px;
    border-radius: 2px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    border: none; background: none;
}}
"""


# ──────────────────────────────────────────────────────────
# Separator line widget
# ──────────────────────────────────────────────────────────
class HUDSeparator(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(1)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def paintEvent(self, event):
        painter = QPainter(self)
        gradient = QLinearGradient(0, 0, self.width(), 0)
        gradient.setColorAt(0.0,  QColor(34, 211, 238, 0))
        gradient.setColorAt(0.3,  QColor(34, 211, 238, 120))
        gradient.setColorAt(0.7,  QColor(34, 211, 238, 120))
        gradient.setColorAt(1.0,  QColor(34, 211, 238, 0))
        painter.fillRect(self.rect(), gradient)


# ──────────────────────────────────────────────────────────
# Main HUD Window
# ──────────────────────────────────────────────────────────
class HUDWindow(QMainWindow):
    """
    JARVIS M7 — Stark Industries two-column HUD.
    Left:  Arc Reactor | Waveform | System Feed Log | Ring Gauges | Voice Input
    Right: Core Output | System providers | Routines
    """
    def __init__(self, settings_cb=None):
        super().__init__()
        self.settings_cb = settings_cb
        self.drag_position = QPoint()
        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.timeout.connect(self._clear_core_output)
        self.transcript_history = []

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.SubWindow
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        # Wide two-column layout: 1000×680
        self.resize(1000, 680)
        self._center_on_screen()
        self._build_ui()

        # Event bus connections
        bus.state_changed.connect(self.on_state_changed)
        bus.command_status.connect(self.on_command_status)
        bus.command_completed.connect(self.on_command_completed)
        bus.system_stats_updated.connect(self.on_stats_updated)
        bus.command_transcription_completed.connect(self.on_transcription_completed)
        bus.stream_token_received.connect(self.on_stream_token_received)
        bus.speech_ended.connect(self.on_speech_ended)
        bus.speech_interrupted.connect(self.on_speech_interrupted)
        bus.show_hud_requested.connect(self.on_show_hud_requested)
        bus.hide_hud_requested.connect(self.on_hide_hud_requested)
        bus.full_exit_requested.connect(self.exit_app)
        bus.console_log.connect(self._on_console_log)

        self._init_tray()
        self._refresh_routines_panel()
        logger.info("HUD window initialized.")

    # ── Layout helpers ──────────────────────────────────────

    def _center_on_screen(self):
        screen = self.screen().availableGeometry()
        self.move(
            (screen.width()  - self.width())  // 2,
            (screen.height() - self.height()) // 2
        )

    def _panel_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setFont(QFont(FONT_MONO, 8, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color: {ACCENT_CYAN}; letter-spacing: 2px; background: transparent;")
        return lbl

    def _mono_label(self, text: str, size: int = 9, color: str = TEXT_BRIGHT) -> QLabel:
        lbl = QLabel(text)
        lbl.setFont(QFont(FONT_MONO, size))
        lbl.setStyleSheet(f"color: {color}; background: transparent;")
        return lbl

    # ── Main UI ─────────────────────────────────────────────

    def _build_ui(self):
        root = QWidget(self)
        root.setObjectName("HUDRoot")
        root.setStyleSheet(f"""
            QWidget#HUDRoot {{
                background-color: {BG_DARK};
                border: 1px solid {BORDER_MED};
                border-radius: 8px;
            }}
            QLabel {{ background: transparent; color: {TEXT_BRIGHT}; }}
        """)

        outer = QVBoxLayout(root)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(8)

        # ── HEADER ──
        outer.addLayout(self._build_header())
        outer.addWidget(self._build_mic_row())
        outer.addWidget(HUDSeparator(self))

        # ── TWO COLUMNS ──
        cols = QHBoxLayout()
        cols.setSpacing(14)

        left = self._build_left_column()
        right = self._build_right_column()

        cols.addLayout(left, stretch=52)
        cols.addLayout(right, stretch=48)

        outer.addLayout(cols, stretch=1)

        # ── COMMAND INPUT ──
        outer.addWidget(HUDSeparator(self))
        outer.addLayout(self._build_input_row())

        self.setCentralWidget(root)

    # ── HEADER ──────────────────────────────────────────────

    def _build_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)

        self.title_label = QLabel("JARVIS M7")
        self.title_label.setFont(QFont(FONT_MONO, 14, QFont.Weight.Bold))
        self.title_label.setStyleSheet(f"color: {ACCENT_CYAN}; letter-spacing: 3px;")

        self.state_badge = QLabel("PASSIVE LISTENING")
        self.state_badge.setFont(QFont(FONT_MONO, 8, QFont.Weight.Bold))
        self.state_badge.setStyleSheet(f"""
            color: {ACCENT_CYAN};
            border: 1px solid {ACCENT_CYAN};
            border-radius: 3px;
            padding: 2px 8px;
            letter-spacing: 1px;
        """)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setFont(QFont(FONT_MONO, 10))
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: 1px solid rgba(239,68,68,150);
                border-radius: 12px;
                color: rgba(239,68,68,200);
            }}
            QPushButton:hover {{
                background: rgba(239,68,68,180);
                color: white;
                border-color: #ef4444;
            }}
        """)
        close_btn.clicked.connect(self.hide)

        row.addWidget(self.title_label)
        row.addWidget(self.state_badge)
        row.addStretch()
        row.addWidget(close_btn)
        return row

    def _build_mic_row(self) -> QWidget:
        self.mic_label = QLabel("MIC: INITIALIZING...")
        self.mic_label.setFont(QFont(FONT_MONO, 8))
        self.mic_label.setStyleSheet(f"color: {ACCENT_TEAL}; letter-spacing: 1px;")
        return self.mic_label

    # ── LEFT COLUMN ─────────────────────────────────────────

    def _build_left_column(self) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(8)

        # 1. Arc Reactor
        self.ai_core = AICoreWidget(self)
        self.ai_core.setMinimumSize(200, 200)
        self.ai_core.setMaximumSize(260, 260)
        col.addWidget(self.ai_core, alignment=Qt.AlignmentFlag.AlignHCenter)

        # 2. Waveform
        self.waveform = WaveformWidget(self)
        self.waveform.setFixedHeight(36)
        col.addWidget(self.waveform)

        # 3. System Feed Log
        col.addWidget(self._build_feed_log_panel())

        # 4. Ring gauges (CPU / RAM / DISK)
        col.addWidget(self._build_stats_panel())

        # 5. Voice Input transcript
        col.addWidget(self._build_transcript_panel(), stretch=1)

        return col

    def _build_feed_log_panel(self) -> QGroupBox:
        box = QGroupBox("SYSTEM FEED LOG")
        box.setStyleSheet(PANEL_STYLE)
        lay = QVBoxLayout(box)
        lay.setContentsMargins(4, 4, 4, 4)

        self.feed_log = QPlainTextEdit()
        self.feed_log.setReadOnly(True)
        self.feed_log.setMaximumBlockCount(200)
        self.feed_log.setFont(QFont(FONT_MONO, 8))
        self.feed_log.setFixedHeight(68)
        self.feed_log.setStyleSheet(f"""
            QPlainTextEdit {{
                background: transparent;
                border: none;
                color: {TEXT_DIM};
            }}
            {SCROLLBAR_STYLE}
        """)
        lay.addWidget(self.feed_log)
        return box

    def _build_stats_panel(self) -> QWidget:
        self.stats = StatsWidget(self)
        self.stats.setFixedHeight(110)
        return self.stats

    def _build_transcript_panel(self) -> QGroupBox:
        box = QGroupBox("VOICE INPUT")
        box.setStyleSheet(PANEL_STYLE)
        lay = QVBoxLayout(box)
        lay.setContentsMargins(4, 4, 4, 4)

        self.transcript_area = QTextEdit()
        self.transcript_area.setReadOnly(True)
        self.transcript_area.setFont(QFont(FONT_MONO, 9))
        self.transcript_area.setStyleSheet(f"""
            QTextEdit {{
                background: transparent;
                border: none;
                color: {TEXT_BRIGHT};
            }}
            {SCROLLBAR_STYLE}
        """)
        self.transcript_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        lay.addWidget(self.transcript_area)
        return box

    # ── RIGHT COLUMN ─────────────────────────────────────────

    def _build_right_column(self) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(8)

        # 1. JARVIS CORE OUTPUT (tall, top)
        col.addWidget(self._build_core_output_panel(), stretch=5)

        # 2. SYSTEM providers (middle)
        col.addWidget(self._build_system_panel(), stretch=2)

        # 3. ROUTINES (bottom)
        col.addWidget(self._build_routines_panel(), stretch=2)

        return col

    def _build_core_output_panel(self) -> QGroupBox:
        box = QGroupBox("JARVIS CORE OUTPUT")
        box.setStyleSheet(PANEL_STYLE)
        lay = QVBoxLayout(box)
        lay.setContentsMargins(8, 6, 8, 8)

        self.core_output = QTextEdit()
        self.core_output.setReadOnly(True)
        self.core_output.setFont(QFont(FONT_MONO, 10))
        self.core_output.setStyleSheet(f"""
            QTextEdit {{
                background: transparent;
                border: none;
                color: {TEXT_BRIGHT};
                line-height: 1.6;
            }}
            {SCROLLBAR_STYLE}
        """)
        self.core_output.setPlaceholderText("Awaiting response...")
        self.core_output.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        lay.addWidget(self.core_output)

        # Typing cursor indicator (thin animated bar)
        self._cursor_bar = QWidget()
        self._cursor_bar.setFixedHeight(2)
        self._cursor_bar.setStyleSheet(f"background: {ACCENT_TEAL}; border-radius: 1px;")
        self._cursor_bar.setVisible(False)
        lay.addWidget(self._cursor_bar)

        return box

    def _build_system_panel(self) -> QGroupBox:
        box = QGroupBox("SYSTEM")
        box.setStyleSheet(PANEL_STYLE)
        lay = QVBoxLayout(box)
        lay.setContentsMargins(8, 4, 8, 8)
        lay.setSpacing(4)

        self.stt_label  = self._mono_label("STT  : faster-whisper (local)", 9)
        self.brain_label = self._mono_label("BRAIN: ollama (local)", 9)
        self.tts_label  = self._mono_label("TTS  : kokoro (local)", 9)

        for lbl in (self.stt_label, self.brain_label, self.tts_label):
            lbl.setStyleSheet(f"color: {TEXT_DIM}; font-family: {FONT_MONO};")
            lay.addWidget(lbl)

        # Refresh provider info now
        QTimer.singleShot(500, self._refresh_system_panel)
        return box

    def _build_routines_panel(self) -> QGroupBox:
        box = QGroupBox("ROUTINES")
        box.setStyleSheet(PANEL_STYLE)
        self._routines_layout = QVBoxLayout(box)
        self._routines_layout.setContentsMargins(8, 4, 8, 8)
        self._routines_layout.setSpacing(3)

        self._routines_placeholder = self._mono_label("No routines saved.", 9, TEXT_DIM)
        self._routines_layout.addWidget(self._routines_placeholder)
        return box

    # ── COMMAND INPUT ────────────────────────────────────────

    def _build_input_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(6)

        self.command_input = QLineEdit()
        self.command_input.setPlaceholderText("Enter command, Sir...")
        self.command_input.setFont(QFont(FONT_MONO, 10))
        self.command_input.setStyleSheet(f"""
            QLineEdit {{
                background: rgba(5,15,30,200);
                border: 1px solid {BORDER_DIM};
                border-radius: 4px;
                color: {TEXT_BRIGHT};
                padding: 5px 10px;
            }}
            QLineEdit:focus {{ border: 1px solid {ACCENT_CYAN}; }}
        """)
        self.command_input.returnPressed.connect(self.submit_command)

        self.wake_btn = QPushButton("WAKE")
        self.send_btn = QPushButton("RUN")
        for btn, color in ((self.wake_btn, "#5eead4"), (self.send_btn, ACCENT_CYAN)):
            btn.setFont(QFont(FONT_MONO, 9, QFont.Weight.Bold))
            btn.setFixedHeight(32)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    border: 1px solid {color};
                    border-radius: 4px;
                    color: {color};
                    padding: 4px 12px;
                }}
                QPushButton:hover {{ background: {color}; color: #050b14; }}
            """)
        self.wake_btn.clicked.connect(self.manual_wake)
        self.send_btn.clicked.connect(self.submit_command)

        row.addWidget(self.command_input, stretch=1)
        row.addWidget(self.wake_btn)
        row.addWidget(self.send_btn)
        return row

    # ── Drag support ─────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self.drag_position:
            self.move(event.globalPosition().toPoint() - self.drag_position)

    # ── Tray ─────────────────────────────────────────────────

    def _init_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        
        # Create a dynamic premium cyan icon for the tray (highly compatible across platforms like Windows)
        from PyQt6.QtGui import QPixmap
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw a beautiful glowing cyan outer ring representing the JARVIS core
        painter.setPen(QPen(QColor(ACCENT_CYAN), 2))
        painter.setBrush(QBrush(Qt.GlobalColor.transparent))
        painter.drawEllipse(2, 2, 28, 28)
        
        # Inner cyan circle
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(ACCENT_CYAN)))
        painter.drawEllipse(9, 9, 14, 14)
        
        painter.end()
        self.tray_icon.setIcon(QIcon(pixmap))

        tray_menu = QMenu()
        show_action = QAction("Show JARVIS", self)
        show_action.triggered.connect(self.show)
        settings_action = QAction("Settings", self)
        settings_action.triggered.connect(lambda: self.settings_cb() if self.settings_cb else None)
        quit_action = QAction("Exit", self)
        quit_action.triggered.connect(self.exit_app)

        tray_menu.addAction(show_action)
        tray_menu.addAction(settings_action)
        tray_menu.addSeparator()
        tray_menu.addAction(quit_action)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show()
            self.raise_()
            self.activateWindow()

    # ── Hotkeys ──────────────────────────────────────────────

    def _register_global_hotkeys(self):
        self.wake_shortcut = QShortcut(QKeySequence("Ctrl+Alt+J"), self)
        self.wake_shortcut.activated.connect(self.manual_wake)
        try:
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = int(self.winId())
            MOD_CONTROL, MOD_SHIFT, MOD_ALT = 0x0002, 0x0004, 0x0001
            
            hotkeys = [
                (1, MOD_CONTROL | MOD_ALT, 0x20, "Ctrl+Alt+Space"),
                (2, MOD_CONTROL | MOD_ALT, 0x43, "Ctrl+Alt+C"),
                (3, MOD_CONTROL | MOD_ALT, 0x48, "Ctrl+Alt+H"),
                (4, 0, 0x13, "Pause/Break"),
            ]
            
            for hk_id, mod, vk, desc in hotkeys:
                user32.UnregisterHotKey(hwnd, hk_id)
                ok = user32.RegisterHotKey(hwnd, hk_id, mod, vk)
                if not ok:
                    logger.warning(
                        f"Failed to register global hotkey {desc} (ID {hk_id}). "
                        f"This hotkey may already be claimed by another running application."
                    )
                else:
                    logger.info(f"Successfully registered global hotkey {desc} (ID {hk_id}) for speech interrupt.")
        except Exception as e:
            logger.error(f"Error registering native global hotkeys: {e}")

    def nativeEvent(self, eventType, message):
        if eventType == b"windows_generic_MSG":
            try:
                import ctypes, ctypes.wintypes
                msg = ctypes.wintypes.MSG.from_address(int(message))
                if msg.message == 0x0312:
                    try:
                        from services.tts.provider_manager import tts_manager
                        tts_manager.stop_speaking()
                        bus.speech_interrupted.emit()
                    except Exception as e:
                        logger.error(f"Error in native hotkey handler: {e}")
                    return True, 0
            except Exception:
                pass
        return False, 0

    # ── Show / Hide ──────────────────────────────────────────

    def showEvent(self, event):
        self.ai_core.timer.start(33)
        super().showEvent(event)

    def hideEvent(self, event):
        self.ai_core.timer.stop()
        super().hideEvent(event)

    # ── Data refresh helpers ─────────────────────────────────

    def _refresh_system_panel(self):
        """Pull live provider names from manager objects."""
        try:
            from services.stt.provider_manager import stt_manager
            stt_name = stt_manager.get_fallback_order()[0]
            _STT_DISPLAY = {
                "local_faster_whisper": "faster-whisper (local)",
                "groq_stt": "groq (cloud)",
                "gemini_stt": "gemini (cloud)",
                "openai_stt": "openai (cloud)",
                "deepgram": "deepgram (cloud)",
            }
            stt_text = _STT_DISPLAY.get(stt_name, stt_name)
        except Exception:
            stt_text = "unknown"

        try:
            from services.brain.provider_manager import brain_manager
            brain_name = brain_manager.get_fallback_order()[0]
            _BRAIN_DISPLAY = {
                "ollama": f"ollama {config.get('ollama_model', 'qwen2.5:1.5b')}",
                "groq": "groq (cloud)",
                "gemini": "gemini (cloud)",
            }
            brain_text = _BRAIN_DISPLAY.get(brain_name, brain_name)
        except Exception:
            brain_text = "unknown"

        try:
            from services.tts.provider_manager import tts_manager
            tts_name = tts_manager.get_fallback_order()[0]
            _TTS_DISPLAY = {
                "kokoro": "kokoro (local)",
                "windows_sapi": "windows sapi (local)",
                "piper": "piper (local)",
                "openai_tts": "openai (cloud)",
                "cartesia": "cartesia (cloud)",
            }
            tts_text = _TTS_DISPLAY.get(tts_name, tts_name)
        except Exception:
            tts_text = "unknown"

        self.stt_label.setText(f"STT  : {stt_text}")
        self.brain_label.setText(f"BRAIN: {brain_text}")
        self.tts_label.setText(f"TTS  : {tts_text}")

    def _refresh_routines_panel(self):
        """Load saved routines and memory fact count from DB."""
        try:
            from core.database import db
            routines = db.get_all_routines()

            # Remove old widgets from layout
            while self._routines_layout.count():
                item = self._routines_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

            if not routines:
                self._routines_layout.addWidget(
                    self._mono_label("No routines saved.", 9, TEXT_DIM)
                )
            else:
                for name in routines[:5]:   # show at most 5
                    lbl = self._mono_label(f"– {name}", 9, TEXT_DIM)
                    self._routines_layout.addWidget(lbl)

            # Facts count from memory table
            try:
                with db.get_connection() as conn:
                    cur = conn.cursor()
                    cur.execute("SELECT COUNT(*) FROM memory")
                    fact_count = cur.fetchone()[0]
            except Exception:
                fact_count = 0

            facts_lbl = self._mono_label(f"{fact_count} fact{'s' if fact_count != 1 else ''} remembered", 9, ACCENT_TEAL)
            self._routines_layout.addWidget(facts_lbl)
            self._routines_layout.addStretch()

        except Exception as e:
            logger.error(f"Error refreshing routines panel: {e}")

    # ── Event slots ─────────────────────────────────────────

    @pyqtSlot(str)
    def on_state_changed(self, state: str):
        # Stop pending dismiss timers and clear text if starting a new interaction
        if state in ("TRANSCRIBING_COMMAND", "EXECUTING_COMMAND"):
            self._dismiss_timer.stop()
            self._clear_core_output()

        # Map engine state string to display badge text and core widget state
        _BADGE = {
            "PASSIVE_WAKE_LISTENING": ("PASSIVE LISTENING", "Passive Listening", ACCENT_CYAN),
            "SESSION_LISTENING":      ("LISTENING",         "Listening",          "#33ff77"),
            "TRANSCRIBING_COMMAND":   ("PROCESSING",        "Processing",          "#a855f7"),
            "EXECUTING_COMMAND":      ("EXECUTING",         "Executing",          ACCENT_CYAN),
            "SPEAKING_ACKNOWLEDGEMENT": ("SPEAKING",        "Speaking",           ACCENT_TEAL),
            "SPEAKING_RESPONSE":      ("SPEAKING",          "Speaking",           ACCENT_TEAL),
            "WAITING_FOR_CONFIRMATION": ("AWAITING CONFIRM","Executing",          "#f59e0b"),
            "COOLDOWN":               ("COOLDOWN",          "Completed",          ACCENT_CYAN),
            "SHUTTING_DOWN":          ("SHUTTING DOWN",     "Passive Listening",  "#ef4444"),
        }
        badge_text, core_state, badge_color = _BADGE.get(
            state, ("ONLINE", "Passive Listening", ACCENT_CYAN)
        )
        self.state_badge.setText(badge_text)
        self.state_badge.setStyleSheet(f"""
            color: {badge_color};
            border: 1px solid {badge_color};
            border-radius: 3px;
            padding: 2px 8px;
            letter-spacing: 1px;
            font-family: {FONT_MONO};
            font-size: 9px;
            font-weight: bold;
        """)
        self.ai_core.set_state(core_state)

        # Waveform amplitude hint
        _AMP = {
            "SESSION_LISTENING": 30.0,
            "SPEAKING_ACKNOWLEDGEMENT": 40.0,
            "SPEAKING_RESPONSE": 40.0,
            "WAITING_FOR_CONFIRMATION": 20.0,
        }
        self.waveform.set_amplitude(_AMP.get(state, 8.0))

    @pyqtSlot(str)
    def on_command_status(self, status: str):
        # Command status updates go to feed log
        self._on_console_log("INFO", status)

    @pyqtSlot(str)
    def on_transcription_completed(self, text: str):
        if text:
            # Wrap in structured block elements with margins to prevent Qt font metric overlap
            self.transcript_history.append(
                f"<p style='margin: 4px 0px; line-height: 120%; color: rgba(34,211,238,0.7);'>USER: {text}</p>"
            )
            self._update_transcript()

    @pyqtSlot(str)
    def on_stream_token_received(self, chunk: str):
        """Append streaming sentence chunks into the Core Output panel."""
        self._dismiss_timer.stop()
        self._cursor_bar.setVisible(True)
        current = self.core_output.toPlainText()
        if current:
            self.core_output.setPlainText(current + " " + chunk)
        else:
            self.core_output.setPlainText(chunk)
        # Scroll to end
        sb = self.core_output.verticalScrollBar()
        sb.setValue(sb.maximum())

    @pyqtSlot()
    def on_speech_ended(self):
        # Only start the clear timer if the speech service has completely finished speaking all chunks
        from services.speech_service import speech
        if speech.is_speaking or not speech.engine.queue.empty() or not speech.engine.audio_queue.empty():
            logger.info("Speech chunk ended, but speech service is still active. Postponing clear timer.")
            return

        self._cursor_bar.setVisible(False)
        delay_ms = int(config.response_popup_dismiss_delay * 1000)
        self._dismiss_timer.start(delay_ms)
        # Also append JARVIS response to transcript
        text = self.core_output.toPlainText().strip()
        if text:
            self.transcript_history.append(
                f"<p style='margin: 4px 0px; line-height: 120%; color: {ACCENT_TEAL};'><b>JARVIS:</b> {text}</p>"
            )
            self._update_transcript()

        # Print telemetry summary at the end of the entire response playback
        from core.telemetry import pipeline_timer
        pipeline_timer.print_summary()

    @pyqtSlot()
    def on_speech_interrupted(self):
        self._cursor_bar.setVisible(False)
        self._clear_core_output()
        from core.telemetry import pipeline_timer
        pipeline_timer.print_summary()

    @pyqtSlot(bool, str)
    def on_command_completed(self, success: bool, response: str):
        if not success:
            self._on_console_log("WARN", f"Command failed: {response[:80]}")

    @pyqtSlot(dict)
    def on_stats_updated(self, stats: dict):
        if "mic_level" in stats:
            level = stats["mic_level"]
            self.ai_core.set_audio_level(level)
            if self.ai_core.state in ("Listening", "Speaking"):
                self.waveform.set_amplitude(level * 400.0)

        if "active_mic" in stats:
            mic = stats["active_mic"]
            if len(mic) > 45:
                mic = mic[:42] + "..."
            self.mic_label.setText(f"MIC: {mic.upper()} — ACTIVE")

    # ── HUD lifecycle ────────────────────────────────────────

    @pyqtSlot()
    def on_show_hud_requested(self):
        self.show()
        self.raise_()
        self.activateWindow()

    @pyqtSlot()
    def on_hide_hud_requested(self):
        self.hide()

    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, "_hotkeys_registered", False):
            self._register_global_hotkeys()
            self._hotkeys_registered = True

    # ── Internal helpers ─────────────────────────────────────

    def _clear_core_output(self):
        self.core_output.clear()

    def _update_transcript(self):
        if len(self.transcript_history) > 12:
            self.transcript_history = self.transcript_history[-12:]
        # Join paragraphs directly since block margin handles separation
        self.transcript_area.setHtml("".join(self.transcript_history))
        sb = self.transcript_area.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_console_log(self, level: str, message: str):
        _COLOR = {
            "ERROR": "#ef4444", "WARN": "#f59e0b", "WARNING": "#f59e0b",
            "SUCCESS": "#22c55e", "INFO": ACCENT_TEAL,
        }
        color = _COLOR.get(level, TEXT_DIM)
        short = message[:120]
        self.feed_log.appendHtml(f'<font color="{color}">[{level}]</font> <font color="{TEXT_DIM}">{short}</font>')
        self.feed_log.moveCursor(QTextCursor.MoveOperation.End)

    # ── Commands ─────────────────────────────────────────────

    def submit_command(self):
        text = self.command_input.text().strip()
        if text:
            self.command_input.clear()
            bus.command_received.emit(text)

    def manual_wake(self):
        bus.wake_detected.emit("shortcut")

    # ── Exit ─────────────────────────────────────────────────

    def exit_app(self):
        logger.info("Initiating clean exit sequence...")
        try:
            from services.audio_service import audio_service
            audio_service.stop()
        except Exception as e:
            logger.error(f"Error stopping audio service: {e}")
        try:
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = int(self.winId())
            for hk_id in [1, 2, 3, 4]:
                user32.UnregisterHotKey(hwnd, hk_id)
        except Exception:
            pass
        try:
            import time
            from services.speech_service import speech
            t0 = time.time()
            while speech.is_speaking and (time.time() - t0) < 3.0:
                time.sleep(0.05)
            speech.stop()
        except Exception as e:
            logger.error(f"Error stopping speech: {e}")
        try:
            self.tray_icon.hide()
        except Exception:
            pass
        from PyQt6.QtWidgets import QApplication
        QApplication.quit()
        import sys
        sys.exit(0)


# ──────────────────────────────────────────────────────────
# Separator kept for backwards compat (used by QFrameWidget ref elsewhere)
# ──────────────────────────────────────────────────────────
class QFrameWidget(QWidget):
    """Thin decorative separator — kept for legacy import compatibility."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(1)

    def paintEvent(self, event):
        painter = QPainter(self)
        pen = QPen(QColor(34, 211, 238, 80))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawLine(0, 0, self.width(), 0)
