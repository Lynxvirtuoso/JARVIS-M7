"""
ui/hud/window.py
Main HUD window — Stage 2 layout manager changes:
  1. Integrates DetachableModule wiring for all panels (SYSTEM, CONTACTS,
     TELEMETRY, PROVIDERS, CORE OUTPUT, ROUTINES, DEV CONSOLE).
  2. Double-click panel title bar → detaches as a floating window.
  3. Window restores panel floating layout from SQLite settings at startup.
  4. Includes promoted ConsoleWidget.
"""
import sys
import time

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QStackedWidget,
    QVBoxLayout, QHBoxLayout,
    QScrollArea, QSizePolicy,
    QLabel, QPushButton,
    QSystemTrayIcon, QMenu,
    QGraphicsOpacityEffect,
    QApplication,
)
from PyQt6.QtCore  import Qt, QPoint, QTimer, QVariantAnimation, pyqtSlot
from PyQt6.QtGui   import (QColor, QIcon, QPainter, QBrush, QAction,
                            QPen, QKeySequence, QShortcut, QPixmap)

from core.event_bus import bus
from core.logger    import logger
from core.config    import config

from ui.hud.theme          import (get_hud_styling, CornerBracketOverlay,
                                   BG_VOID, BG_PANEL, COLOR_CYAN, COLOR_CYAN_FAINT,
                                   COLOR_TEXT_DIM, COLOR_AMBER, get_mono_family,
                                   get_orbitron_family)
from ui.hud.boot_widget    import BootWidget, CoreFlashOverlay
from ui.hud.hud_layout     import TopStatusBar, ScanlineOverlay, TranscriptWidget
from ui.hud.panels         import HUDCollapsiblePanel
from ui.hud.dock_media_output import (ModulesDockPanel, CoreOutputLogPanel,
                                       RoutinesDockPanel)
from ui.hud.vision_mode    import VisionOverlayWidget
from ui.hud.stats_widget   import StatsWidget
from ui.hud.config_panel   import ConfigPanel
from ui.hud.core_widget    import AICoreWidget
from ui.hud.console        import ConsoleWidget   # promoted detachable console
from ui.hud.music_space_widget import MusicSpaceHUDWidget


# ──────────────────────────────────────────────────────────
# Mic Status Bar
# ──────────────────────────────────────────────────────────
class MicStatusBar(QWidget):
    """Thin bar below TopStatusBar showing active microphone name + state."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(26)
        self.setStyleSheet(
            f"background-color: {BG_PANEL};"
            f"border-bottom: 1px solid {COLOR_CYAN_FAINT};"
        )
        hl = QHBoxLayout(self)
        hl.setContentsMargins(28, 0, 28, 0)
        hl.setSpacing(6)

        dot = QLabel("●", self)
        dot.setStyleSheet(f"font-size: 8px; color: {COLOR_CYAN}; background: transparent;")
        hl.addWidget(dot)

        self.lbl = QLabel("MIC: DETECTING…", self)
        self.lbl.setStyleSheet(
            f"font-family: '{get_mono_family()}'; font-size: 9px;"
            f"color: {COLOR_TEXT_DIM}; letter-spacing: 1px; background: transparent;"
        )
        hl.addWidget(self.lbl)
        hl.addStretch()

    def set_mic(self, name: str, state: str = "ACTIVE"):
        self.lbl.setText(f"MIC: {name.upper()} — {state}")


# ──────────────────────────────────────────────────────────
# System Feed Log
# ──────────────────────────────────────────────────────────
class SystemFeedLog(HUDCollapsiblePanel):
    """Scrolling [INFO/WARN/ERROR] timestamped feed. Fixed width PANEL_WIDTH, collapsible and detachable."""
    MAX_LINES = 80

    def __init__(self, parent=None):
        super().__init__("SYSTEM FEED LOG", parent, module_id="system_feed_log")

        self._scroll = QScrollArea(self.body)
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("QScrollArea { border: 1px solid #12303A; background: #080E13; }")
        self._scroll.setFixedHeight(80)

        self._inner = QWidget()
        self._inner.setStyleSheet("background: #080E13;")
        self._vbox  = QVBoxLayout(self._inner)
        self._vbox.setContentsMargins(6, 4, 6, 4)
        self._vbox.setSpacing(1)
        self._vbox.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._scroll.setWidget(self._inner)
        self.body_layout.addWidget(self._scroll)

        self._lines: list[QLabel] = []

    def add_line(self, level: str, message: str):
        ts    = time.strftime("%H:%M:%S")
        color = COLOR_CYAN if level == "INFO" else COLOR_AMBER if level in ("WARNING", "WARN") else "#FF6B6B"
        lbl   = QLabel(self._inner)
        lbl.setText(
            f'<span style="color:{color};">[{level[:4]}]</span>'
            f'<span style="color:#3A5F6A;"> {ts} </span>'
            f'<span style="color:#5D8A96;">{message[:90]}</span>'
        )
        lbl.setStyleSheet(
            f"font-family: '{get_mono_family()}'; font-size: 9px; background: transparent;"
        )
        self._vbox.addWidget(lbl)
        self._lines.append(lbl)

        if len(self._lines) > self.MAX_LINES:
            old = self._lines.pop(0)
            self._vbox.removeWidget(old)
            old.deleteLater()

        QTimer.singleShot(30, self._scroll_bottom)

    def _scroll_bottom(self):
        vb = self._scroll.verticalScrollBar()
        vb.setValue(vb.maximum())


# ──────────────────────────────────────────────────────────
# Provider Info Panel
# ──────────────────────────────────────────────────────────
class ProviderInfoPanel(HUDCollapsiblePanel):
    """Shows active STT / Brain / TTS providers."""
    def __init__(self, parent=None):
        super().__init__("SYSTEM PROVIDERS", parent, module_id="system_providers")
        self.add_row("STT",   "—")
        self.add_row("BRAIN", "—")
        self.add_row("TTS",   "—")

    def update_providers(self, stt: str, brain: str, tts: str):
        self.update_row_value("STT",   stt)
        self.update_row_value("BRAIN", brain)
        self.update_row_value("TTS",   tts)


# ──────────────────────────────────────────────────────────
# Main HUD Window
# ──────────────────────────────────────────────────────────
class HUDWindow(QMainWindow):
    def __init__(self, settings_cb=None):
        super().__init__()
        self.settings_cb         = settings_cb
        self.drag_position       = QPoint()
        self._hotkeys_registered = False

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.resize(1280, 820)
        self._center_on_screen()
        self._build_ui()
        self._connect_bus()
        self._init_tray()
        self._refresh_system_panel()
        self._restore_module_layout() # restore floating layouts
        logger.info("HUD window initialized.")

    def _center_on_screen(self):
        geo = self.screen().availableGeometry()
        self.move((geo.width()  - self.width())  // 2,
                  (geo.height() - self.height()) // 2)

    def _build_ui(self):
        self.setStyleSheet(get_hud_styling())

        self.container = QWidget(self)
        self.container.setStyleSheet(f"background-color: {BG_VOID};")
        self.setCentralWidget(self.container)

        root = QVBoxLayout(self.container)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.stack = QStackedWidget(self.container)
        root.addWidget(self.stack)

        self.boot_screen = BootWidget(self.stack)
        self.stack.addWidget(self.boot_screen)

        self.hud_screen = QWidget(self.stack)
        self.hud_screen.setStyleSheet(f"background-color: {BG_VOID};")
        self._opacity = QGraphicsOpacityEffect(self.hud_screen)
        self._opacity.setOpacity(1.0)
        self.hud_screen.setGraphicsEffect(self._opacity)
        self._build_hud_screen()
        self.stack.addWidget(self.hud_screen)

        self.music_space_screen = MusicSpaceHUDWidget(self.stack)
        self.stack.addWidget(self.music_space_screen)

        self.scanlines     = ScanlineOverlay(self.container)
        self.brackets      = CornerBracketOverlay(self.container)
        self.vision        = VisionOverlayWidget(self.container)
        self.flash_overlay = CoreFlashOverlay(self.container)
        self.config_panel  = ConfigPanel(self.container)

        for ov in (self.scanlines, self.brackets, self.vision, self.flash_overlay):
            ov.raise_()
        self.config_panel.raise_()

        self._demo_running = False

        self.boot_screen.boot_finished.connect(self.flash_overlay.start_flash)
        self.flash_overlay.flash_midpoint.connect(
            lambda: self.stack.setCurrentWidget(self.hud_screen)
        )
        self.stack.setCurrentWidget(self.boot_screen)

    def _build_hud_screen(self):
        vbox = QVBoxLayout(self.hud_screen)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        # ── Top bar ────────────────────────────────────────
        top_row = QWidget(self.hud_screen)
        top_row.setStyleSheet(f"background: {BG_PANEL}; border-bottom: 1px solid {COLOR_CYAN_FAINT};")
        top_row.setFixedHeight(54)
        top_hl = QHBoxLayout(top_row)
        top_hl.setContentsMargins(0, 0, 12, 0)
        top_hl.setSpacing(0)

        self.top_bar = TopStatusBar(top_row)
        top_hl.addWidget(self.top_bar, stretch=1)

        cfg_btn = QPushButton("⚙", top_row)
        cfg_btn.setFixedSize(32, 32)
        cfg_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {COLOR_TEXT_DIM};
                border: 1px solid {COLOR_CYAN_FAINT}; font-size: 15px;
            }}
            QPushButton:hover {{ color: {COLOR_CYAN}; border-color: {COLOR_CYAN}; }}
        """)
        cfg_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        cfg_btn.clicked.connect(self._toggle_config)
        top_hl.addWidget(cfg_btn)

        close_btn = QPushButton("✕", top_row)
        close_btn.setFixedSize(32, 32)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {COLOR_TEXT_DIM};
                border: 1px solid {COLOR_CYAN_FAINT}; font-size: 13px; margin-left: 6px;
            }}
            QPushButton:hover {{ color: #FF6B6B; border-color: #FF6B6B; }}
        """)
        close_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        close_btn.clicked.connect(self.exit_app)
        top_hl.addWidget(close_btn)
        vbox.addWidget(top_row)

        self.mic_bar = MicStatusBar(self.hud_screen)
        vbox.addWidget(self.mic_bar)

        # ── Body ───────────────────────────────────────────
        body = QWidget(self.hud_screen)
        body.setStyleSheet(f"background-color: {BG_VOID};")
        body_row = QHBoxLayout(body)
        body_row.setContentsMargins(18, 10, 18, 0)
        body_row.setSpacing(0)

        # LEFT COLUMN ─────────────────────────────────────
        self.left_col = QWidget(body)
        self.left_col.setFixedWidth(250)
        self.left_col.setStyleSheet(f"background-color: {BG_VOID};")
        self.left_vbox = QVBoxLayout(self.left_col)
        self.left_vbox.setContentsMargins(0, 0, 0, 0)
        self.left_vbox.setSpacing(10)
        self.left_vbox.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.system_panel = HUDCollapsiblePanel("SYSTEM", self.left_col, module_id="system")
        self.system_panel.add_row("STATE",         "PASSIVE_LISTEN")
        self.system_panel.add_row("MIC LEVEL",     "0.000")
        self.system_panel.add_row("MIC GAIN",      "0 dB")
        self.left_vbox.addWidget(self.system_panel)

        self.contacts_panel = HUDCollapsiblePanel("CONTACTS", self.left_col, module_id="contacts")
        self.contacts_panel.add_row("CACHED",     "—")
        self.contacts_panel.add_row("LAST MATCH", "—")
        self.contacts_panel.add_row(
            "TRUST GATE",
            '<span style="color:#FFB454; font-size:13px; vertical-align:-1px;">●</span> '
            '<b style="color:#E8F4F8;">ARMED</b>',
            is_html=True
        )
        self.left_vbox.addWidget(self.contacts_panel)

        self.feed_log = SystemFeedLog(self.left_col)
        self.left_vbox.addWidget(self.feed_log)

        self.stats = StatsWidget(self.left_col)
        self.left_vbox.addWidget(self.stats)

        self.left_vbox.addStretch()

        body_row.addWidget(self.left_col)

        # CENTER COLUMN (iris) ────────────────────────────
        center_col = QWidget(body)
        center_col.setStyleSheet(f"background-color: {BG_VOID};")
        center_vbox = QVBoxLayout(center_col)
        center_vbox.setContentsMargins(12, 0, 12, 0)
        center_vbox.setSpacing(0)
        center_vbox.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.iris = AICoreWidget(center_col)
        center_vbox.addWidget(self.iris, alignment=Qt.AlignmentFlag.AlignHCenter)

        body_row.addWidget(center_col, stretch=1)

        # RIGHT COLUMN (scrollable) ───────────────────────
        right_scroll = QScrollArea(body)
        right_scroll.setFixedWidth(264)
        right_scroll.setWidgetResizable(True)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        right_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        right_scroll.setStyleSheet(f"""
            QScrollArea  {{ border: none; background: {BG_VOID}; }}
            QScrollBar:vertical {{
                border: none; background: #050B14; width: 3px; margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: #1B4855; min-height: 14px; border-radius: 1px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                border: none; background: none;
            }}
        """)

        right_inner = QWidget()
        right_inner.setStyleSheet(f"background-color: {BG_VOID};")
        self.right_vbox = QVBoxLayout(right_inner)
        self.right_vbox.setContentsMargins(0, 0, 4, 0)
        self.right_vbox.setSpacing(10)
        self.right_vbox.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.telemetry_panel = HUDCollapsiblePanel("TELEMETRY", right_inner, module_id="telemetry")
        self.telemetry_panel.add_row("STT LATENCY", "—")
        self.telemetry_panel.add_row("NLU LATENCY", "—")
        self.telemetry_panel.add_row("PROVIDER",    "—")
        self.telemetry_panel.add_row("WAKE METHOD", "exact")
        self.right_vbox.addWidget(self.telemetry_panel)

        self.provider_panel = ProviderInfoPanel(right_inner)
        self.right_vbox.addWidget(self.provider_panel)

        self.dock = ModulesDockPanel(right_inner)
        self.right_vbox.addWidget(self.dock)

        self.output_log = CoreOutputLogPanel(right_inner)
        self.right_vbox.addWidget(self.output_log)

        self.routines_panel = RoutinesDockPanel(right_inner)
        self.right_vbox.addWidget(self.routines_panel)

        # Developer Console module added to right vbox
        self.console_panel = ConsoleWidget(right_inner)
        self.right_vbox.addWidget(self.console_panel)

        self.right_vbox.addStretch()
        right_scroll.setWidget(right_inner)
        body_row.addWidget(right_scroll)

        vbox.addWidget(body, stretch=1)

        # ── Bottom bar ─────────────────────────────────────
        bottom = QWidget(self.hud_screen)
        bottom.setStyleSheet(f"background-color: {BG_VOID};")
        bottom_hl = QHBoxLayout(bottom)
        bottom_hl.setContentsMargins(18, 0, 18, 10)
        bottom_hl.setSpacing(10)

        # DEMO Button (safely in layout, avoiding z-order collision)
        self.demo_btn = QPushButton('DEMO: "Jarvis, what\'s on screen"', bottom)
        self.demo_btn.setFixedSize(190, 38)
        self.demo_btn.setStyleSheet(f"""
            QPushButton {{
                font-family: '{get_mono_family()}'; font-size: 9px; font-weight: bold;
                background: #0A1218; color: {COLOR_TEXT_DIM};
                border: 1px solid {COLOR_CYAN_FAINT}; padding: 4px;
            }}
            QPushButton:hover {{ color: {COLOR_CYAN}; border-color: #1B4855; }}
        """)
        self.demo_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.demo_btn.clicked.connect(self._trigger_vision_demo)
        bottom_hl.addWidget(self.demo_btn)

        self.transcript = TranscriptWidget(bottom)
        self.transcript.input_box.returnPressed.connect(self.submit_command)
        bottom_hl.addWidget(self.transcript, stretch=1)

        wake_btn = QPushButton("WAKE [DEV]", bottom)
        wake_btn.setFixedSize(92, 38)
        wake_btn.setStyleSheet(f"""
            QPushButton {{
                font-family: '{get_mono_family()}'; font-size: 10px; font-weight: bold;
                background: transparent; color: {COLOR_CYAN};
                border: 1px solid {COLOR_CYAN}; letter-spacing: 1px;
            }}
            QPushButton:hover {{ background: {COLOR_CYAN}; color: {BG_VOID}; }}
        """)
        wake_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        wake_btn.setToolTip("[DEV] Manually trigger voice listening mode (wake word bypass)")
        wake_btn.clicked.connect(self.manual_wake)
        bottom_hl.addWidget(wake_btn)

        run_btn = QPushButton("RUN [DEV]", bottom)
        run_btn.setFixedSize(92, 38)
        run_btn.setStyleSheet(f"""
            QPushButton {{
                font-family: '{get_mono_family()}'; font-size: 10px; font-weight: bold;
                background: {COLOR_CYAN}; color: {BG_VOID};
                border: 1px solid {COLOR_CYAN}; letter-spacing: 1px;
            }}
            QPushButton:hover {{ background: #2BB8D4; }}
        """)
        run_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        run_btn.setToolTip("[DEV] Manually execute the typed command")
        run_btn.clicked.connect(self.submit_command)
        bottom_hl.addWidget(run_btn)

        # Initialize SQLite contacts cache count telemetry
        try:
            from core.database import db
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM contacts")
                count = cursor.fetchone()[0]
                self.contacts_panel.update_row_value("CACHED", str(count))
        except Exception:
            self.contacts_panel.update_row_value("CACHED", "0")

        vbox.addWidget(bottom)

        self._module_layout_map = {
            self.system_panel:     self.left_vbox,
            self.contacts_panel:   self.left_vbox,
            self.feed_log:         self.left_vbox,
            self.stats:            self.left_vbox,
            self.telemetry_panel:  self.right_vbox,
            self.provider_panel:   self.right_vbox,
            self.output_log:       self.right_vbox,
            self.routines_panel:   self.right_vbox,
            self.console_panel:    self.right_vbox,
        }
        for mod, layout in self._module_layout_map.items():
            mod.detached.connect(lambda m=mod: self._on_module_detached(m))
            mod.reattached.connect(lambda m=mod: self._on_module_reattached(m))

    # ── Detachable module layout actions ─────────────────
    def _on_module_detached(self, module):
        layout = self._module_layout_map[module]
        layout.removeWidget(module)
        module.setParent(None)

    def _on_module_reattached(self, module):
        layout = self._module_layout_map[module]
        if layout == self.left_vbox:
            # Map left column order: system (0), contacts (1), feed_log (2), stats (3)
            if module == self.system_panel:
                self.left_vbox.insertWidget(0, module)
            elif module == self.contacts_panel:
                idx = 1 if self.system_panel.parent() is not None else 0
                self.left_vbox.insertWidget(idx, module)
            elif module == self.feed_log:
                idx = 0
                if self.system_panel.parent() is not None: idx += 1
                if self.contacts_panel.parent() is not None: idx += 1
                self.left_vbox.insertWidget(idx, module)
            elif module == self.stats:
                idx = 0
                if self.system_panel.parent() is not None: idx += 1
                if self.contacts_panel.parent() is not None: idx += 1
                if self.feed_log.parent() is not None: idx += 1
                self.left_vbox.insertWidget(idx, module)
        else:
            # Right column: insert before the stretch at the end
            layout.insertWidget(layout.count() - 1 if layout.count() > 0 else 0, module)

    def _restore_module_layout(self):
        """Checks SQLite configuration for floating modules and triggers detach."""
        try:
            from core.database import db
            for mod in self._module_layout_map.keys():
                val = db.get_setting(f"hud_module_{mod.module_id}")
                if val and val.endswith(",1"):
                    mod.detach()
        except Exception as e:
            logger.warning(f"Error restoring module layouts: {e}")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w, h = self.width(), self.height()
        for ov in (self.scanlines, self.brackets, self.vision, self.flash_overlay):
            ov.setGeometry(0, 0, w, h)
        self.config_panel.setGeometry(w - 460, 0, 460, h)

    # ── Config toggle ─────────────────────────────────────
    def _toggle_config(self):
        if self.config_panel.isVisible():
            self.config_panel.close_panel()
        else:
            self.config_panel.open_panel()

    # ── Vision demo ───────────────────────────────────────
    def _trigger_vision_demo(self):
        if self._demo_running:
            return
        self._demo_running = True
        self.transcript.lbl_prefix.setText("COMMAND RECEIVED")
        self.transcript.lbl_text.setText("Jarvis, what's on screen")
        self.output_log.add_log_line("YOU", "jarvis what's on screen", is_user=True)
        QTimer.singleShot(500,  self._fade_hud_out)
        QTimer.singleShot(950,  self.vision.start_overlay)
        QTimer.singleShot(4600, self._stop_vision_demo)

    def _fade_hud_out(self):
        self._anim_fade(1.0, 0.1, 450)

    def _stop_vision_demo(self):
        self.vision.stop_overlay()
        self._anim_fade(0.1, 1.0, 550)
        self.transcript.lbl_prefix.setText("AWAITING COMMAND")
        reply = 'I see a laptop, notebook and coffee mug. The document reads "Q3 Roadmap — Draft."'
        self.transcript.lbl_text.setText(reply)
        self.output_log.add_log_line("JARVIS", reply)
        self._demo_running = False

    def _anim_fade(self, start: float, end: float, ms: int):
        anim = QVariantAnimation(self)
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.setDuration(ms)
        anim.valueChanged.connect(self._opacity.setOpacity)
        anim.start()
        self._current_anim = anim

    # ── Drag ──────────────────────────────────────────────
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = (event.globalPosition().toPoint()
                                  - self.frameGeometry().topLeft())

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self.drag_position:
            self.move(event.globalPosition().toPoint() - self.drag_position)

    # ── Tray ──────────────────────────────────────────────
    def _init_tray(self):
        pm = QPixmap(32, 32)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(COLOR_CYAN), 2))
        p.setBrush(QBrush(Qt.GlobalColor.transparent))
        p.drawEllipse(2, 2, 28, 28)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(COLOR_CYAN)))
        p.drawEllipse(9, 9, 14, 14)
        p.end()

        self.tray_icon = QSystemTrayIcon(QIcon(pm), self)
        menu = QMenu()
        menu.addAction(QAction("Show JARVIS",   self, triggered=self.show))
        menu.addAction(QAction("Configuration", self, triggered=self._toggle_config))
        menu.addAction(QAction("Settings",      self,
                               triggered=lambda: self.settings_cb() if self.settings_cb else None))
        menu.addSeparator()
        menu.addAction(QAction("Exit", self, triggered=self.exit_app))
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(
            lambda r: (self.show(), self.raise_(), self.activateWindow())
            if r == QSystemTrayIcon.ActivationReason.DoubleClick else None
        )
        self.tray_icon.show()

    # ── Hotkeys ───────────────────────────────────────────
    def showEvent(self, event):
        super().showEvent(event)
        if not self._hotkeys_registered:
            self._register_global_hotkeys()
            self._hotkeys_registered = True

    def _register_global_hotkeys(self):
        QShortcut(QKeySequence("Ctrl+Alt+J"), self).activated.connect(self.manual_wake)
        try:
            import ctypes
            user32 = ctypes.windll.user32
            hwnd   = int(self.winId())
            CTRL, ALT = 0x0002, 0x0001
            for hk_id, mod, vk, desc in [
                (1, CTRL | ALT, 0x20, "Ctrl+Alt+Space"),
                (2, CTRL | ALT, 0x43, "Ctrl+Alt+C"),
                (3, CTRL | ALT, 0x48, "Ctrl+Alt+H"),
                (4, 0,          0x13, "Pause/Break"),
            ]:
                user32.UnregisterHotKey(hwnd, hk_id)
                if user32.RegisterHotKey(hwnd, hk_id, mod, vk):
                    logger.info(f"Registered hotkey {desc} (ID {hk_id})")
                else:
                    logger.warning(f"Failed to register hotkey {desc}")
        except Exception as e:
            logger.error(f"Hotkey registration error: {e}")

    def nativeEvent(self, eventType, message):
        if eventType == b"windows_generic_MSG":
            try:
                import ctypes, ctypes.wintypes
                if ctypes.wintypes.MSG.from_address(int(message)).message == 0x0312:
                    try:
                        from services.tts.provider_manager import tts_manager
                        tts_manager.stop_speaking()
                        bus.speech_interrupted.emit()
                    except Exception as e:
                        logger.error(f"Hotkey handler: {e}")
                    return True, 0
            except Exception:
                pass
        return False, 0

    # ── Event Bus ─────────────────────────────────────────
    def _connect_bus(self):
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
        bus.wake_detected.connect(self.on_wake_detected)
        bus.music_space_updated.connect(self.on_music_space_updated)

    # ── System refresh ────────────────────────────────────
    def _refresh_system_panel(self):
        try:
            from services.stt.provider_manager import stt_manager
            stt = stt_manager.get_fallback_order()[0]
        except Exception:
            stt = config.get("stt_provider", "groq_stt")

        _MAP = {
            "local_faster_whisper": "faster-whisper (local)",
            "groq_stt":             "groq (cloud)",
            "gemini_stt":           "gemini (cloud)",
        }
        stt_display = _MAP.get(stt, stt)
        self.telemetry_panel.update_row_value("PROVIDER", stt_display)

        tts   = config.get("tts_provider",   "kokoro")
        brain = config.get("brain_provider", "groq")
        self.provider_panel.update_providers(
            stt_display,
            f"{brain} (cloud)",
            f"{tts} ({'local' if tts == 'kokoro' else 'cloud'})"
        )

        try:
            import pyaudio
            pa   = pyaudio.PyAudio()
            idx  = int(config.get("selected_microphone_index", "0") or 0)
            info = pa.get_device_info_by_index(idx)
            mic_name = info.get("name", "Unknown")[:50]
            pa.terminate()
            self.mic_bar.set_mic(mic_name)
        except Exception:
            self.mic_bar.set_mic("Default Microphone")

        self.system_panel.update_row_value("MIC GAIN",
            f"{config.get('input_gain_boost_db', '0')} dB")

    # ── Bus slots ─────────────────────────────────────────
    @pyqtSlot(str)
    def on_state_changed(self, state: str):
        self.system_panel.update_row_value("STATE", state)

        _LABEL = {
            "PASSIVE_WAKE_LISTENING":    "PASSIVE LISTENING MODE",
            "SESSION_LISTENING":         "LISTENING FOR COMMAND",
            "ACTIVE_COMMAND_LISTENING":  "LISTENING FOR COMMAND",
            "COMMAND_RECORDING":         "RECORDING COMMAND",
            "TRANSCRIBING_COMMAND":      "PROCESSING INPUT",
            "EXECUTING_COMMAND":         "EXECUTING COMMAND",
            "SPEAKING_ACKNOWLEDGEMENT":  "SPEAKING",
            "SPEAKING_RESPONSE":         "SPEAKING",
            "WAITING_FOR_CONFIRMATION":  "AWAITING CONFIRMATION",
            "COOLDOWN":                  "COOLDOWN",
            "SHUTTING_DOWN":             "SHUTTING DOWN",
        }
        self.transcript.lbl_prefix.setText(_LABEL.get(state, "AWAITING COMMAND"))

        self.iris.set_state(state)

    @pyqtSlot(str)
    def on_command_status(self, status: str):
        if status.startswith("space_changed:"):
            space_name = status.split(":")[1]
            self.top_bar.set_space_indicator(space_name)
            if space_name == "music":
                self.stack.setCurrentWidget(self.music_space_screen)
            else:
                self.stack.setCurrentWidget(self.hud_screen)
        else:
            self.transcript.lbl_prefix.setText(status.upper())

    @pyqtSlot(dict)
    def on_music_space_updated(self, state: dict):
        if "raga_name" in state:
            self.music_space_screen.set_raga(state["raga_name"], state["raga_category"], state["raga_swaras"])
        if "playback_mode" in state:
            self.music_space_screen.set_mode(state["playback_mode"])
        if "tonic" in state:
            self.music_space_screen.set_tonic(state["tonic"])
        if "transport_status" in state:
            self.music_space_screen.set_transport(state["transport_status"], state["tempo"], state["loop"])
        if "sounding_idx" in state:
            self.music_space_screen.set_sounding_index(state["sounding_idx"])

    @pyqtSlot(str)
    def on_transcription_completed(self, text: str):
        if text:
            self.transcript.lbl_text.setText(text)

    @pyqtSlot(str)
    def on_stream_token_received(self, chunk: str):
        pass

    @pyqtSlot()
    def on_speech_ended(self):
        self.output_log.finalize_response()
        self.transcript.lbl_text.setText("Awaiting command...")

    @pyqtSlot()
    def on_speech_interrupted(self):
        self.output_log.finalize_response()
        self.transcript.lbl_text.setText("Speech interrupted.")

    @pyqtSlot(bool, str)
    def on_command_completed(self, success: bool, response: str):
        pass

    @pyqtSlot(dict)
    def on_stats_updated(self, stats: dict):
        if "stt_latency" in stats:
            self.telemetry_panel.update_row_value("STT LATENCY",
                                                  f"{stats['stt_latency']:.2f}s")
        if "nlu_latency" in stats:
            self.telemetry_panel.update_row_value("NLU LATENCY",
                                                  f"{stats['nlu_latency']:.2f}s")
        if "cached_contacts" in stats:
            self.contacts_panel.update_row_value("CACHED", str(stats["cached_contacts"]))
        if "last_contact_match" in stats:
            self.contacts_panel.update_row_value("LAST MATCH", str(stats["last_contact_match"]))

        if "mic_level" in stats:
            level = float(stats["mic_level"])
            self.system_panel.update_row_value("MIC LEVEL", f"{level:.4f}")
            self.iris.set_audio_level(level)

        if "active_mic" in stats:
            self.mic_bar.set_mic(str(stats["active_mic"]))

    @pyqtSlot(str)
    def on_wake_detected(self, source: str):
        self.telemetry_panel.update_row_value("WAKE METHOD", source)

    @pyqtSlot()
    def on_show_hud_requested(self):
        self.show(); self.raise_(); self.activateWindow()

    @pyqtSlot()
    def on_hide_hud_requested(self):
        self.hide()

    def _on_console_log(self, level: str, message: str):
        self.feed_log.add_line(level, message)

    def submit_command(self):
        text = self.transcript.input_box.text().strip()
        if text:
            self.transcript.input_box.clear()
            self.telemetry_panel.update_row_value("WAKE METHOD", "typed")
            bus.command_transcription_completed.emit(text)
            bus.command_received.emit(text)

    def manual_wake(self):
        bus.wake_detected.emit("shortcut")

    def exit_app(self):
        logger.info("Initiating clean exit…")
        for fn, label in [
            (lambda: __import__("services.audio_service", fromlist=["audio_service"]).audio_service.stop(),
             "audio_service"),
            (lambda: __import__("services.speech_service", fromlist=["speech"]).speech.stop(),
             "speech_service"),
        ]:
            try:
                fn()
            except Exception as e:
                logger.error(f"Error stopping {label}: {e}")
        try:
            import ctypes
            user32 = ctypes.windll.user32
            hwnd   = int(self.winId())
            for hk_id in [1, 2, 3, 4]:
                user32.UnregisterHotKey(hwnd, hk_id)
        except Exception:
            pass
        try:
            self.tray_icon.hide()
        except Exception:
            pass
        QApplication.quit()
        sys.exit(0)


class HUDSeparator(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(1)
    def paintEvent(self, event):
        pass
