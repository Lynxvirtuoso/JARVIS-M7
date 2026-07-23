"""
ui/hud/hud_layout.py
Core HUD layout widgets: ScanlineOverlay, TopStatusBar, ArcReactorWidget, TranscriptWidget.
"""
import math
import time

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QLineEdit, QSizePolicy
from PyQt6.QtCore    import Qt, QTimer, QTime
from PyQt6.QtGui     import QPainter, QPen, QColor, QFont, QRadialGradient, QBrush

from ui.hud.theme import (
    BG_VOID, COLOR_CYAN, COLOR_CYAN_DIM, COLOR_CYAN_FAINT,
    COLOR_TEXT, COLOR_TEXT_DIM, COLOR_AMBER, get_orbitron_family, get_mono_family
)


# ── Scanline overlay ──────────────────────────────────────
class ScanlineOverlay(QWidget):
    """Full-window cyan scanline texture (pure paint, transparent to mouse)."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setPen(QPen(QColor(79, 227, 255, 4), 1))
        for y in range(0, self.height(), 3):
            p.drawLine(0, y, self.width(), y)


# ── Top Status Bar ────────────────────────────────────────
class TopStatusBar(QWidget):
    """Brand name, status indicators, live clock."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(54)
        self.setStyleSheet(
            f"background-color: {BG_VOID};"
            f"border-bottom: 1px solid {COLOR_CYAN_FAINT};"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(28, 0, 28, 0)
        layout.setSpacing(0)

        # Brand
        brand = QLabel("JARVIS", self)
        brand.setStyleSheet(
            f"font-family: '{get_orbitron_family()}'; font-size: 15px; font-weight: bold;"
            f"color: {COLOR_CYAN}; letter-spacing: 7px; background: transparent; border: none;"
        )
        layout.addWidget(brand)
        layout.addStretch()

        # Status chips
        status_row = QHBoxLayout()
        status_row.setSpacing(24)

        self.stt_lbl    = self._chip("GROQ STT", "ONLINE")
        self.nlu_lbl    = self._chip("NLU", "READY")
        self.bridge_lbl = self._chip("PHONE BRIDGE", "LINKED")
        self.space_lbl  = self._chip("SPACE", "CORE")

        for lbl in (self.stt_lbl, self.nlu_lbl, self.bridge_lbl, self.space_lbl):
            status_row.addWidget(lbl)

        # Clock
        self.clock_lbl = QLabel(self)
        self.clock_lbl.setStyleSheet(
            f"font-family: '{get_mono_family()}'; font-size: 11px;"
            f"color: {COLOR_TEXT_DIM}; letter-spacing: 1px; background: transparent; border: none;"
        )
        status_row.addWidget(self.clock_lbl)
        layout.addLayout(status_row)

        timer = QTimer(self)
        timer.timeout.connect(self._tick)
        timer.start(1000)
        self._tick()

    def _chip(self, name: str, state: str) -> QLabel:
        lbl = QLabel(self)
        lbl.setText(
            f'<span style="color:{COLOR_CYAN}; font-size:13px; vertical-align:-1px;">●</span> '
            f'<span style="color:{COLOR_TEXT_DIM};">{name}&nbsp;</span>'
            f'<b style="color:{COLOR_CYAN};">{state}</b>'
        )
        lbl.setStyleSheet(
            f"font-family: '{get_mono_family()}'; font-size: 10px; background: transparent; border: none;"
        )
        return lbl

    def _tick(self):
        self.clock_lbl.setText(QTime.currentTime().toString("HH:mm:ss"))

    def set_space_indicator(self, space_name: str):
        if not space_name or space_name.lower() == "none":
            self.space_lbl.setText(
                f'<span style="color:{COLOR_CYAN}; font-size:13px; vertical-align:-1px;">●</span> '
                f'<span style="color:{COLOR_TEXT_DIM};">SPACE&nbsp;</span>'
                f'<b style="color:{COLOR_CYAN};">CORE</b>'
            )
        else:
            space_upper = space_name.upper()
            self.space_lbl.setText(
                f'<span style="color:{COLOR_AMBER}; font-size:13px; vertical-align:-1px;">●</span> '
                f'<span style="color:{COLOR_TEXT_DIM};">SPACE&nbsp;</span>'
                f'<b style="color:{COLOR_AMBER};">{space_upper}</b>'
            )
        self.space_lbl.adjustSize()





# ── Transcript / Command Input ────────────────────────────
class TranscriptWidget(QWidget):
    """
    Bottom centre widget: mode label, live speech transcript display,
    and a separate text box for typing manual commands.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(102)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet(f"background-color: {BG_VOID};")

        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(4)

        # Mode prefix
        self.lbl_prefix = QLabel("AWAITING JARVIS-PREFIXED COMMAND", self)
        self.lbl_prefix.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_prefix.setStyleSheet(
            f"font-family: '{get_mono_family()}'; font-size: 10px;"
            f"color: {COLOR_CYAN}; letter-spacing: 1px; background: transparent;"
        )
        vbox.addWidget(self.lbl_prefix)

        # ── 1. Live Speech Transcript Display Row ──
        row = QWidget(self)
        row.setStyleSheet("background: transparent;")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(2)
        rl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Display-only QLabel for STT voice transcription
        self.lbl_text = QLabel("Yes, Sir.", self)
        self.lbl_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_text.setStyleSheet(
            f"font-family: '{get_mono_family()}'; font-size: 14px;"
            f"color: {COLOR_TEXT}; background: transparent; border: none;"
        )
        rl.addWidget(self.lbl_text)

        self.cursor_lbl = QLabel("█", self)
        self.cursor_lbl.setStyleSheet(
            f"font-size: 13px; color: {COLOR_CYAN}; background: transparent;"
        )
        rl.addWidget(self.cursor_lbl)
        vbox.addWidget(row)

        # ── 2. Manual Command Text Box Row ──
        input_container = QWidget(self)
        input_container.setStyleSheet("background: transparent;")
        icl = QHBoxLayout(input_container)
        icl.setContentsMargins(40, 2, 40, 0)
        icl.setSpacing(6)

        lbl_prompt = QLabel("CMD >", self)
        lbl_prompt.setStyleSheet(
            f"font-family: '{get_mono_family()}'; font-size: 11px; color: {COLOR_CYAN}; font-weight: bold;"
        )
        icl.addWidget(lbl_prompt)

        self.input_box = QLineEdit(self)
        self.input_box.setPlaceholderText("Type manual command here...")
        self.input_box.setStyleSheet(f"""
            QLineEdit {{
                font-family: '{get_mono_family()}'; font-size: 11px;
                color: #A5C6D0; background: #070F14;
                border: 1px solid {COLOR_CYAN_FAINT}; padding: 3px 8px;
            }}
            QLineEdit:focus {{
                border: 1px solid {COLOR_CYAN};
                color: {COLOR_TEXT};
            }}
        """)
        icl.addWidget(self.input_box)
        vbox.addWidget(input_container)

        self._blink = QTimer(self)
        self._blink.timeout.connect(self._toggle_cursor)
        self._blink.start(500)
        self._cursor_on = True

    def _toggle_cursor(self):
        self._cursor_on = not self._cursor_on
        self.cursor_lbl.setVisible(self._cursor_on)
