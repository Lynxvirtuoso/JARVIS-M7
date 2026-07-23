"""
ui/hud/stats_widget.py
CPU / RAM / DISK circular ring gauges — updated to use HUD theme colors.
"""
import psutil
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QVBoxLayout
from PyQt6.QtCore import Qt, QTimer, QPointF
from PyQt6.QtGui import QPainter, QPen, QColor, QFont

from ui.hud.theme import BG_VOID, COLOR_TEXT, get_mono_family


class StatRing(QWidget):
    """Circular donut gauge showing a percentage with label."""
    def __init__(self, label: str, color: QColor, parent=None):
        super().__init__(parent)
        self.label      = label
        self.color      = color
        self._pct       = 0.0
        self.setFixedSize(68, 68)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)

    def set_percentage(self, val: float):
        self._pct = max(0.0, min(float(val), 100.0))
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(BG_VOID))

        cx, cy = self.width() / 2.0, self.height() / 2.0
        r = min(self.width(), self.height()) / 2.0 - 7

        # Track ring
        bg_pen = QPen(QColor(self.color.red(), self.color.green(), self.color.blue(), 28))
        bg_pen.setWidth(5)
        p.setPen(bg_pen)
        p.drawEllipse(QPointF(cx, cy), r, r)

        # Progress arc
        fg_pen = QPen(self.color)
        fg_pen.setWidth(5)
        fg_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(fg_pen)
        span = int(-self._pct * 3.6 * 16)
        p.drawArc(
            int(cx - r), int(cy - r), int(r * 2), int(r * 2),
            90 * 16, span
        )

        # Centre text
        p.setPen(QColor(COLOR_TEXT))
        p.setFont(QFont(get_mono_family(), 8, QFont.Weight.Bold))
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                   f"{int(self._pct)}%\n{self.label}")


from ui.hud.panels import HUDCollapsiblePanel

class StatsWidget(HUDCollapsiblePanel):
    """Row of three StatRings: CPU (cyan), RAM (green), DISK (amber) — now collapsible & detachable."""
    def __init__(self, parent=None):
        super().__init__("SYSTEM PERFORMANCE", parent, module_id="system_performance")

        inner = QWidget(self.body)
        inner.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        layout = QHBoxLayout(inner)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(15)
        layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self.cpu_ring  = StatRing("CPU",  QColor(79,  227, 255), inner)
        self.ram_ring  = StatRing("RAM",  QColor(0,   230, 118), inner)
        self.disk_ring = StatRing("DISK", QColor(255, 180, 84),  inner)

        for ring in (self.cpu_ring, self.ram_ring, self.disk_ring):
            layout.addWidget(ring)

        self.body_layout.addWidget(inner)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(1500)
        self._poll()

    def _poll(self):
        try:
            self.cpu_ring.set_percentage(psutil.cpu_percent())
            self.ram_ring.set_percentage(psutil.virtual_memory().percent)
            self.disk_ring.set_percentage(psutil.disk_usage("C:\\").percent)
        except Exception:
            pass
