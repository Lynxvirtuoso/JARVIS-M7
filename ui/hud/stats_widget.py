from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt, QTimer, QPointF
from PyQt6.QtGui import QPainter, QPen, QColor, QFont
import psutil

class StatRing(QWidget):
    """Circular ring gauge showing percentage of a system stat."""
    def __init__(self, label="CPU", color=QColor(0, 191, 255), parent=None):
        super().__init__(parent)
        self.label = label
        self.color = color
        self.percentage = 0.0
        self.setMinimumSize(80, 80)
        self.setMaximumSize(120, 120)

    def set_percentage(self, val):
        self.percentage = max(0.0, min(float(val), 100.0))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        width = self.width()
        height = self.height()
        center = QPointF(width / 2.0, height / 2.0)
        radius = min(width, height) / 2.0 - 8
        
        # 1. Background ring (faint)
        bg_pen = QPen(QColor(self.color.red(), self.color.green(), self.color.blue(), 30))
        bg_pen.setWidth(6)
        painter.setPen(bg_pen)
        painter.drawEllipse(center, radius, radius)
        
        # 2. Foreground percentage arc
        fg_pen = QPen(self.color)
        fg_pen.setWidth(6)
        fg_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(fg_pen)
        
        # SAPI coordinates start at 3 o'clock (0 degrees), we start at 12 o'clock (90 degrees) and rotate clockwise (negative)
        start_angle = 90 * 16
        span_angle = int(-self.percentage * 3.6 * 16)
        
        painter.drawArc(
            int(center.x() - radius), int(center.y() - radius),
            int(radius * 2), int(radius * 2),
            start_angle, span_angle
        )
        
        # 3. Label text (e.g. "CPU 45%")
        painter.setPen(QColor(255, 255, 255, 220))
        painter.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        text_rect = self.rect()
        # Adjust text center slightly downwards
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, f"{int(self.percentage)}%\n{self.label}")

class StatsWidget(QWidget):
    """HUD sidebar displaying real-time CPU, RAM, and Disk metrics."""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(15)
        
        self.cpu_ring = StatRing("CPU", QColor(0, 191, 255), self)
        self.ram_ring = StatRing("RAM", QColor(0, 255, 127), self)
        self.disk_ring = StatRing("DISK", QColor(255, 165, 0), self)
        
        layout.addWidget(self.cpu_ring)
        layout.addWidget(self.ram_ring)
        layout.addWidget(self.disk_ring)
        
        # Update timer (every 1 second)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll_stats)
        self.timer.start(1000)
        
        # Initial poll
        self.poll_stats()

    def poll_stats(self):
        # Heavy work should be delegated to system monitor service, but quick psutil queries are non-blocking on Windows
        try:
            cpu = psutil.cpu_percent()
            ram = psutil.virtual_memory().percent
            disk = psutil.disk_usage('C:\\').percent
            
            self.cpu_ring.set_percentage(cpu)
            self.ram_ring.set_percentage(ram)
            self.disk_ring.set_percentage(disk)
        except Exception:
            pass # Keep previous stats on transient errors
