"""
ui/hud/vision_mode.py
Vision overlay: reticle animation, scan sweep, and typewriter readout panel.
Updated to use the renamed `body` / `body_layout` from panels.py rewrite.
"""
import math
import time

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel
from PyQt6.QtCore    import Qt, QTimer, QVariantAnimation, QEasingCurve, QPoint
from PyQt6.QtGui     import (QPainter, QPen, QColor, QRadialGradient,
                              QLinearGradient, QBrush)

from ui.hud.theme  import (BG_VOID, COLOR_CYAN, COLOR_CYAN_DIM, COLOR_CYAN_FAINT,
                            COLOR_TEXT, COLOR_TEXT_DIM,
                            get_mono_family, get_orbitron_family)
from ui.hud.panels import HUDCollapsiblePanel


# ── Typewriter Row ────────────────────────────────────────
class TypewriterRow(QWidget):
    """Animates a key-value row with a per-character typewriter effect."""
    def __init__(self, label: str, full_value: str, delay_ms: int, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self._full = full_value
        self._idx  = 0

        rl = QHBoxLayout(self)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(4)

        lbl_name = QLabel(label.upper(), self)
        lbl_name.setProperty("class", "HUDPanelRowLabel")
        rl.addWidget(lbl_name)
        rl.addStretch()

        self.lbl_val = QLabel(self)
        self.lbl_val.setProperty("class", "HUDPanelRowValue")
        self.lbl_val.setStyleSheet(f"border-right: 2px solid {COLOR_CYAN};")
        rl.addWidget(self.lbl_val)

        QTimer.singleShot(delay_ms, self._start)

    def _start(self):
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(38)

    def _tick(self):
        if self._idx < len(self._full):
            self._idx += 1
            self.lbl_val.setText(self._full[:self._idx])
        else:
            self._timer.stop()
            self.lbl_val.setStyleSheet("")   # remove cursor border


# ── Vision Readout Panel ──────────────────────────────────
class VisionReadoutPanel(HUDCollapsiblePanel):
    """HUD panel showing vision analysis rows with typewriter animation."""
    def __init__(self, parent=None):
        super().__init__("VISION ANALYSIS", parent)
        self.setFixedWidth(460)

        # Use self.body (renamed from body_widget in the rewrite)
        self.row1 = TypewriterRow(
            "OBJECTS", "Laptop, coffee mug, notebook, phone", 0, self.body)
        self.body_layout.addWidget(self.row1)

        self.row2 = TypewriterRow(
            "TEXT DETECTED", '"Q3 Roadmap — Draft"', 1700, self.body)
        self.body_layout.addWidget(self.row2)

        self.row3 = TypewriterRow(
            "SUMMARY", "Workspace, open document, active session", 2600, self.body)
        self.body_layout.addWidget(self.row3)


# ── Vision Overlay Widget ─────────────────────────────────
class VisionOverlayWidget(QWidget):
    """
    Full-window overlay for vision mode:
    • Vignette background
    • Expanding reticle circle
    • Horizontal scan sweep
    • Animated readout panel
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setVisible(False)

        self._reticle_scale   = 0.0
        self._reticle_opacity = 0.0
        self._scan_pos        = -320.0

        # Status label
        self.lbl_status = QLabel("ANALYZING FIELD OF VIEW", self)
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setStyleSheet(
            f"font-family: '{get_orbitron_family()}'; font-size: 11px;"
            f"color: {COLOR_CYAN}; letter-spacing: 3px; background: transparent;"
        )

        # Readout panel
        self.panel = VisionReadoutPanel(self)

        # Scan sweep timer
        self._scan_timer = QTimer(self)
        self._scan_timer.timeout.connect(self._tick_scan)

    # ── Public API ────────────────────────────────────────
    def start_overlay(self):
        self.setVisible(True)
        self._reticle_scale   = 0.0
        self._reticle_opacity = 0.9
        self._scan_pos        = -320.0

        # Rebuild panel to restart typewriter animations
        self.panel.deleteLater()
        self.panel = VisionReadoutPanel(self)
        self.panel.show()
        self._reposition()

        # Reticle expand animation
        self._reticle_anim = QVariantAnimation(self)
        self._reticle_anim.setStartValue(0.0)
        self._reticle_anim.setEndValue(1.0)
        self._reticle_anim.setDuration(1100)
        self._reticle_anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        self._reticle_anim.valueChanged.connect(self._on_reticle)
        self._reticle_anim.start()

        self._scan_timer.start(16)

    def stop_overlay(self):
        self._scan_timer.stop()
        self.setVisible(False)

    # ── Internal ──────────────────────────────────────────
    def _on_reticle(self, val: float):
        self._reticle_scale   = val
        self._reticle_opacity = 0.9 - 0.68 * val
        self.update()

    def _tick_scan(self):
        self._scan_pos += 6.4
        if self._scan_pos > 320.0:
            self._scan_pos = -320.0
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition()

    def _reposition(self):
        w, h = self.width(), self.height()
        self.lbl_status.setGeometry(0, int(h / 2 - 360), w, 20)
        self.panel.move(
            int((w - self.panel.width()) / 2),
            int(h - self.panel.height() - h * 0.14)
        )

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0

        # Vignette
        vig = QRadialGradient(cx, cy, max(w, h) / 1.8)
        vig.setColorAt(0.0, QColor(0, 0, 0, 0))
        vig.setColorAt(1.0, QColor(0, 0, 0, 130))
        p.fillRect(self.rect(), vig)

        # Reticle
        if self._reticle_scale > 0.0:
            rc = QColor(COLOR_CYAN)
            rc.setAlpha(int(self._reticle_opacity * 255))
            p.setPen(QPen(rc, 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            r = int(320.0 * self._reticle_scale)
            p.drawEllipse(QPoint(int(cx), int(cy)), r, r)

        # Scan sweep
        norm = (self._scan_pos + 320.0) / 640.0
        alpha = math.sin(norm * math.pi) * 0.9
        y = int(cy + self._scan_pos)
        sg = QLinearGradient(int(cx - 320), y, int(cx + 320), y)
        sc = QColor(COLOR_CYAN); sc.setAlpha(int(alpha * 255))
        sg.setColorAt(0.0, QColor(0, 0, 0, 0))
        sg.setColorAt(0.5, sc)
        sg.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setPen(QPen(QBrush(sg), 2))
        p.drawLine(int(cx - 320), y, int(cx + 320), y)
