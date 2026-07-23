"""
ui/hud/dock_media_output.py
Right-column panel widgets: Modules Dock, Core Output Log (with live streaming),
Routines Panel.
Spotify/YouTube panels defined but NOT registered in default layout
until those integrations are built.
"""
import random
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                              QGridLayout, QScrollArea, QSizePolicy, QTextEdit)
from PyQt6.QtCore import Qt, QTimer, QPoint
from PyQt6.QtGui  import QPainter, QPen, QColor, QFont, QPolygon, QTextCursor

from core.event_bus import bus
from core.logger    import logger

from ui.hud.panels import HUDCollapsiblePanel, PANEL_WIDTH
from ui.hud.theme  import (
    BG_PANEL_2, BG_VOID, COLOR_CYAN, COLOR_CYAN_DIM, COLOR_CYAN_FAINT,
    COLOR_TEXT, COLOR_TEXT_DIM, COLOR_AMBER, get_mono_family, get_orbitron_family
)

_W = PANEL_WIDTH


# ── Music Visualizer Bars ─────────────────────────────────
class MusicVisualizerWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(18, 18)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self._heights = [6, 16, 10, 12]
        t = QTimer(self); t.timeout.connect(self._animate); t.start(140)

    def _animate(self):
        self._heights = [random.randint(3, 18) for _ in range(4)]
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(COLOR_CYAN))
        for i, h in enumerate(self._heights):
            p.drawRect(i * 4, 18 - h, 3, h)


# ── Dock Tile ─────────────────────────────────────────────
class DockTileWidget(QWidget):
    def __init__(self, symbol: str, title: str, active: bool = False,
                 empty: bool = False, parent=None):
        super().__init__(parent)
        self.setFixedSize(44, 44)
        self.symbol = symbol
        self.active = active
        self.empty  = empty
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setToolTip(title)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        if self.empty:
            p.fillRect(0, 0, w, h, QColor(BG_PANEL_2))
            p.setPen(QPen(QColor(COLOR_CYAN_DIM), 1, Qt.PenStyle.DashLine))
            p.drawRect(0, 0, w - 1, h - 1)
            p.setPen(QPen(QColor(COLOR_CYAN_DIM), 1))
            p.setFont(QFont(get_mono_family(), 12))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "+")
        else:
            p.fillRect(0, 0, w, h, QColor(BG_PANEL_2))
            border = QColor(COLOR_CYAN_DIM) if self.active else QColor(COLOR_CYAN_FAINT)
            p.setPen(QPen(border, 1))
            p.drawRect(0, 0, w - 1, h - 1)
            sym_color = QColor(COLOR_CYAN) if self.active else QColor(COLOR_TEXT_DIM)
            p.setPen(QPen(sym_color, 1))
            p.setFont(QFont(get_mono_family(), 15 if self.active else 12))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.symbol)
            if self.active:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(COLOR_CYAN))
                p.drawEllipse(int(w / 2 - 1.5), h - 5, 3, 3)


# ── Modules Dock Panel ────────────────────────────────────
class ModulesDockPanel(HUDCollapsiblePanel):
    def __init__(self, parent=None):
        super().__init__("MODULES", parent)
        gc = QWidget(self.body)
        gc.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        gl = QGridLayout(gc)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.setSpacing(6)

        tiles = [
            ("♪", "Spotify",  False),   # Not yet integrated
            ("▶", "YouTube",  False),   # Not yet integrated
            ("▦", "Calendar", False),
            ("☁", "Weather",  False),
            ("✉", "Mail",     False),
            ("◎", "Vision",   False),
            ("☎", "Phone",    False),
        ]
        row = col = 0
        for sym, title, active in tiles:
            gl.addWidget(DockTileWidget(sym, title, active=active, parent=gc), row, col)
            col += 1
            if col >= 4:
                col = 0; row += 1
        gl.addWidget(DockTileWidget("", "Add module", empty=True, parent=gc), row, col)
        self.body_layout.addWidget(gc)


# ── Spotify Panel (defined, not in default layout) ────────
class SpotifyMediaPanel(HUDCollapsiblePanel):
    def __init__(self, parent=None):
        super().__init__("NOW PLAYING · SPOTIFY", parent)
        row = QWidget(self.body)
        row.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(8)
        self.viz = MusicVisualizerWidget(row)
        rl.addWidget(self.viz)
        lbl = QLabel("Not connected", row)
        lbl.setStyleSheet(
            f"font-family: '{get_mono_family()}'; font-size: 11px;"
            f"color: {COLOR_TEXT_DIM}; background: transparent;"
        )
        rl.addWidget(lbl)
        rl.addStretch()
        self.body_layout.addWidget(row)


# ── YouTube Panel (defined, not in default layout) ────────
class YouTubeMediaPanel(HUDCollapsiblePanel):
    def __init__(self, parent=None):
        super().__init__("YOUTUBE", parent)
        lbl = QLabel("Not connected", self.body)
        lbl.setStyleSheet(
            f"font-family: '{get_mono_family()}'; font-size: 10px;"
            f"color: {COLOR_TEXT_DIM}; background: transparent;"
        )
        self.body_layout.addWidget(lbl)


# ── Core Output Log — directly wired to streaming ─────────
class CoreOutputLogPanel(HUDCollapsiblePanel):
    """
    Live-streaming CORE OUTPUT panel.
    Directly subscribed to:
      bus.stream_token_received  → appends token text in real-time
      bus.command_transcription_completed → clears output for new command
    Maintains a separate user-input log.
    On interrupt, retains partial text (does NOT clear).
    """
    def __init__(self, parent=None):
        super().__init__("CORE OUTPUT", parent)

        # QTextEdit for streaming LLM output — read-only, word-wrap
        self._output = QTextEdit(self.body)
        self._output.setReadOnly(True)
        self._output.setWordWrapMode(
            __import__("PyQt6.QtGui", fromlist=["QTextOption"]).QTextOption.WrapMode.WordWrap
        )
        self._output.setFixedHeight(160)
        self._output.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._output.setStyleSheet(f"""
            QTextEdit {{
                background: #06100D;
                border: 1px solid {COLOR_CYAN_FAINT};
                color: {COLOR_TEXT};
                font-family: '{get_mono_family()}';
                font-size: 10px;
                padding: 4px;
            }}
            QScrollBar:vertical {{
                border: none; background: #050B14; width: 3px; margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {COLOR_CYAN_DIM}; min-height: 12px; border-radius: 1px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                border: none; background: none;
            }}
        """)
        self.body_layout.addWidget(self._output)

        # Conversation log below (YOU / JARVIS turns)
        self._scroll = QScrollArea(self.body)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFixedHeight(80)
        self._scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._scroll.setStyleSheet(f"""
            QScrollArea  {{ border: none; background: transparent; }}
            QScrollBar:vertical {{
                border: none; background: #050B14; width: 3px; margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {COLOR_CYAN_DIM}; min-height: 12px; border-radius: 1px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                border: none; background: none;
            }}
        """)
        self._log_inner = QWidget()
        self._log_inner.setStyleSheet("background: transparent;")
        self._log_layout = QVBoxLayout(self._log_inner)
        self._log_layout.setContentsMargins(0, 0, 0, 0)
        self._log_layout.setSpacing(2)
        self._log_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._scroll.setWidget(self._log_inner)
        self.body_layout.addWidget(self._scroll)

        self._log_lines: list[QLabel] = []
        self._is_streaming = False
        self._current_stream_text = ""

        # ── Connect directly to bus ───────────────────
        bus.stream_token_received.connect(self._on_stream_token)
        bus.command_transcription_completed.connect(self._on_new_command)

    # ── Stream handlers ───────────────────────────────
    def _on_new_command(self, user_text: str):
        """New command transcribed — add user turn, clear the output area."""
        self._output.clear()
        self._current_stream_text = ""
        self._is_streaming = True
        if user_text.strip():
            self.add_log_line("YOU", user_text.strip(), is_user=True)

    def _on_stream_token(self, token: str):
        """Called for each sentence-chunk from the LLM — appends in real time."""
        self._current_stream_text += token + " "
        self._output.setPlainText(self._current_stream_text.strip())
        # Scroll to bottom
        cur = self._output.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.End)
        self._output.setTextCursor(cur)
        self._output.ensureCursorVisible()

    def finalize_response(self):
        """
        Called when streaming is complete (on speech_ended from window.py).
        Adds the full response to the conversation log.
        Safe to call even if interrupted (retains whatever was streamed).
        """
        if self._current_stream_text.strip():
            self.add_log_line("JARVIS", self._current_stream_text.strip())
        self._is_streaming = False
        self._current_stream_text = ""

    # ── Conversation log ──────────────────────────────
    def add_log_line(self, who: str, message: str, is_user: bool = False):
        lbl = QLabel(self._log_inner)
        lbl.setWordWrap(True)
        lbl.setFont(QFont(get_mono_family(), 9))
        lbl.setStyleSheet("background: transparent;")
        who_color = COLOR_AMBER if is_user else COLOR_CYAN
        lbl.setText(
            f'<span style="color:{who_color}; font-weight:bold;">{who}</span> '
            f'<span style="color:{COLOR_TEXT_DIM};">{message[:200]}</span>'
        )
        self._log_layout.addWidget(lbl)
        self._log_lines.append(lbl)
        # Trim to 30 lines
        if len(self._log_lines) > 30:
            old = self._log_lines.pop(0)
            self._log_layout.removeWidget(old)
            old.deleteLater()
        QTimer.singleShot(30, self._scroll_bottom)

    def _scroll_bottom(self):
        vb = self._scroll.verticalScrollBar()
        vb.setValue(vb.maximum())


# ── Routines Panel — reads real DB data ──────────────────
class RoutinesDockPanel(HUDCollapsiblePanel):
    """Shows saved routines and memory fact count from SQLite."""
    def __init__(self, parent=None):
        super().__init__("ROUTINES", parent)
        self._routines_row = self.add_row("SAVED ROUTINES", "—")
        self._facts_row    = self.add_row("FACTS REMEMBERED", "—")
        self._refresh()
        # Refresh every 30s in case routines/facts change at runtime
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh)
        self._refresh_timer.start(30_000)

    def _refresh(self):
        try:
            from core.database import db
            routine_names = db.get_all_routines()
            routine_count = len(routine_names)

            # Direct count from memory table
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM memory")
                row = cursor.fetchone()
                fact_count = row[0] if row else 0

            self.update_row_value("SAVED ROUTINES",    str(routine_count))
            self.update_row_value("FACTS REMEMBERED",  str(fact_count))
        except Exception as e:
            logger.warning(f"RoutinesDockPanel refresh failed: {e}")
