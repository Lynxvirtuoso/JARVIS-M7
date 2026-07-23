"""
ui/hud/core_widget.py
AICoreWidget — the JARVIS iris.

Serves as the central background layer of the HUD (NOT a detachable module).
Reacts to engine state with distinct visual modes:
  Passive Listening  → slow cyan pulse
  Listening          → active green, reacts to mic amplitude
  Processing         → rapid counter-rotating purple rings
  Executing          → blue dashes
  Speaking           → cyan rings + waveform rendered inside the iris
  Completed          → bright flash, returns to passive

The waveform is rendered INSIDE this widget during Speaking state,
replacing the standalone WaveformWidget.
"""
import math
from PyQt6.QtWidgets import QWidget, QSizePolicy
from PyQt6.QtCore    import QTimer, QPointF, Qt
from PyQt6.QtGui     import (QPainter, QPen, QColor, QBrush,
                              QRadialGradient, QPainterPath)

from ui.hud.theme import BG_VOID, COLOR_CYAN


class AICoreWidget(QWidget):
    """
    Opaque state-reactive iris widget.
    Parent should call:
      set_state(state_str)     — on bus.state_changed
      set_audio_level(float)   — on bus.system_stats_updated["mic_level"]
    """

    # Map engine bus state strings → internal mode keys
    _STATE_MAP = {
        "PASSIVE_WAKE_LISTENING":   "Passive Listening",
        "WAKE_DETECTED":            "Listening",
        "SPEAKING_ACKNOWLEDGEMENT": "Speaking",
        "SESSION_LISTENING":        "Listening",
        "ACTIVE_COMMAND_LISTENING": "Listening",
        "COMMAND_RECORDING":        "Listening",
        "TRANSCRIBING_COMMAND":     "Processing",
        "EXECUTING_COMMAND":        "Executing",
        "SPEAKING_RESPONSE":        "Speaking",
        "WAITING_FOR_CONFIRMATION": "Executing",
        "COOLDOWN":                 "Completed",
        "SLEEPING":                 "Passive Listening",
        "SHUTTING_DOWN":            "Passive Listening",
    }

    _COLORS = {
        "Passive Listening":  QColor(0,   240, 255),   # electric cyan
        "Listening":          QColor(51,  255, 119),   # active green
        "Processing":         QColor(138, 43,  226),   # violet
        "Executing":          QColor(0,   191, 255),   # deepskyblue
        "Speaking":           QColor(0,   240, 255),   # cyan
        "Completed":          QColor(51,  255, 119),   # green flash
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setFixedSize(360, 360)

        # Animation state
        self._mode       = "Passive Listening"
        self._angle1     = 0.0
        self._angle2     = 0.0
        self._pulse_val  = 1.0
        self._pulse_dir  = 1

        # Audio level (mic RMS from bus)
        self._audio_level  = 0.0
        self._smooth_audio = 0.0

        # Waveform (used during Speaking)
        self._wave_phase   = 0.0

        # Timer — 30 FPS when active, 10 FPS when passive
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)

    # ── Public API ────────────────────────────────────────
    def set_state(self, bus_state: str):
        mode = self._STATE_MAP.get(bus_state, "Passive Listening")
        if mode == self._mode:
            return
        self._mode = mode
        # Throttle FPS when idle
        self._timer.setInterval(100 if mode == "Passive Listening" else 33)
        self.update()

    def set_audio_level(self, level: float):
        """Receive normalised mic RMS (typically 0.0–1.0 from audio_service)."""
        self._audio_level = float(level)
        self.update()

    # ── Animation tick ────────────────────────────────────
    def _tick(self):
        mode = self._mode

        if mode == "Passive Listening":
            self._angle1 += 0.4
            self._angle2 -= 0.2
            self._pulse_val += 0.004 * self._pulse_dir
            if self._pulse_val >= 1.06 or self._pulse_val <= 0.94:
                self._pulse_dir *= -1

        elif mode == "Listening":
            self._angle1 += 3.5
            self._angle2 -= 2.5
            # Smooth mic level
            self._smooth_audio = self._smooth_audio * 0.6 + self._audio_level * 0.4
            self._pulse_val = 0.9 + min(self._smooth_audio * 60.0, 1.0) * 0.5

        elif mode == "Processing":
            self._angle1 += 9.0
            self._angle2 -= 7.0
            self._pulse_val += 0.06 * self._pulse_dir
            if self._pulse_val >= 1.35 or self._pulse_val <= 0.65:
                self._pulse_dir *= -1

        elif mode == "Executing":
            self._angle1 += 4.5
            self._angle2 -= 4.5
            self._pulse_val += 0.03 * self._pulse_dir
            if self._pulse_val >= 1.18 or self._pulse_val <= 0.82:
                self._pulse_dir *= -1

        elif mode == "Speaking":
            self._angle1 += 2.0
            self._angle2 -= 1.2
            self._smooth_audio = self._smooth_audio * 0.5 + self._audio_level * 0.5
            self._pulse_val = 1.0 + min(self._smooth_audio * 40.0, 0.5) * 0.4
            self._wave_phase += 0.18

        elif mode == "Completed":
            self._angle1 += 1.5
            self._angle2 -= 1.5
            self._pulse_val = max(0.5, self._pulse_val - 0.04)

        self.update()

    # ── Paint ─────────────────────────────────────────────
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # ── Solid opaque background ─────────────────────
        p.fillRect(self.rect(), QColor(BG_VOID))

        w, h = float(self.width()), float(self.height())
        cx, cy = w / 2.0, h / 2.0
        center  = QPointF(cx, cy)
        radius  = min(w, h) / 2.0 - 18.0

        base    = self._COLORS.get(self._mode, QColor(0, 240, 255))
        r, g, b = base.red(), base.green(), base.blue()

        # ── 1. Outer segmented ring (12 arcs, rotating) ─
        p.save()
        p.translate(center)
        p.rotate(self._angle1)
        seg_pen = QPen(QColor(r, g, b, 140), 1)
        p.setPen(seg_pen)
        for i in range(12):
            p.drawArc(int(-radius), int(-radius),
                      int(radius * 2), int(radius * 2),
                      i * 30 * 16 + 5 * 16, 20 * 16)
        p.restore()

        # ── 2. Inner bracket ring (4 arcs, counter-rotating) ─
        p.save()
        p.translate(center)
        p.rotate(self._angle2)
        mid_r = radius - 14.0
        bkt_pen = QPen(QColor(r, g, b, 200), 2)
        p.setPen(bkt_pen)
        arc_span = 45 * 16
        for i in range(4):
            p.drawArc(int(-mid_r), int(-mid_r),
                      int(mid_r * 2), int(mid_r * 2),
                      i * 90 * 16 + 10 * 16, arc_span)
        p.restore()

        # ── 3. Breathing mid-ring ──────────────────────
        dyn_r = radius * 0.60 * self._pulse_val
        mid_pen = QPen(QColor(r, g, b, 60), 1)
        p.setPen(mid_pen)
        p.drawEllipse(center, dyn_r, dyn_r)

        # ── 4. Radial glow core ────────────────────────
        core_r = radius * 0.30 * (1.0 + (self._pulse_val - 1.0) * 0.25)
        grad = QRadialGradient(center, core_r)
        grad.setColorAt(0.0, QColor(r, g, b, 255))
        grad.setColorAt(0.45, QColor(r, g, b, 110))
        grad.setColorAt(1.0,  QColor(r, g, b, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(grad))
        p.drawEllipse(center, core_r, core_r)

        # ── 5. Hexagon detail lines ────────────────────
        hex_r = core_r * 0.42
        p.save()
        p.translate(center)
        p.rotate(-self._angle1 * 1.5)
        p.setPen(QPen(QColor(255, 255, 255, 200), 1.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        pts = []
        for i in range(6):
            a = i * (math.pi / 3)
            pts.append(QPointF(hex_r * math.cos(a), hex_r * math.sin(a)))
        for i in range(6):
            p.drawLine(pts[i], pts[(i + 1) % 6])
            p.drawLine(pts[i] * 0.5, pts[i] * 1.45)
        p.restore()

        # ── 6. SPEAKING waveform rendered inside iris ──
        if self._mode == "Speaking":
            self._draw_iris_waveform(p, cx, cy, radius, r, g, b)

    def _draw_iris_waveform(self, p: QPainter, cx: float, cy: float,
                             radius: float, r: int, g: int, b: int):
        """Sine wave bands drawn inside the iris ring during Speaking state."""
        amp_base = 12.0 + min(self._smooth_audio * 300.0, 28.0)
        mid_y    = cy  # horizontal axis = centre of widget

        wave_w_left  = cx - radius * 0.25
        wave_w_right = cx + radius * 0.25
        wave_w       = wave_w_right - wave_w_left

        # Three overlapping waves with decreasing opacity
        for layer in range(3):
            scale   = 1.0 - layer * 0.28
            opacity = int(190 * scale)
            freq    = 0.055 + layer * 0.012

            pen = QPen(QColor(r, g, b, opacity), 2 if layer == 0 else 1)
            p.setPen(pen)

            path = QPainterPath()
            path.moveTo(wave_w_left, mid_y)

            steps = int(wave_w / 3)
            for step in range(steps + 1):
                x        = wave_w_left + (step / max(steps, 1)) * wave_w
                env      = math.sin((step / max(steps, 1)) * math.pi)
                angle    = step * freq * 10.0 - self._wave_phase + layer * 1.5
                y        = mid_y + amp_base * scale * env * math.sin(angle)
                if step == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)

            p.drawPath(path)

        # End-cap dots
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(r, g, b, 180))
        p.drawEllipse(QPointF(wave_w_left,  mid_y), 3, 3)
        p.drawEllipse(QPointF(wave_w_right, mid_y), 3, 3)
