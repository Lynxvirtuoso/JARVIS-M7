import math
import random
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QPainter, QPen, QColor, QPainterPath

class WaveformWidget(QWidget):
    """
    Futuristic neon voice waveform.
    Animates a sine-based waveform reflecting microphone input or speech playback.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.phase = 0.0
        self.amplitude = 15.0
        self.target_amplitude = 15.0
        self.frequency = 0.05
        self.lines_count = 3  # Multiple overlapping wave lines for neon effect
        
        # State colors
        self.color = QColor(0, 191, 255) # Cyan
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_wave)
        self.timer.start(25) # 40 FPS
        self.setMinimumHeight(80)

    def set_amplitude(self, amp):
        self.target_amplitude = max(5.0, min(amp, 60.0))

    def set_color(self, qcolor):
        self.color = qcolor

    def update_wave(self):
        self.phase += 0.15
        # Interpolate amplitude to smooth out spikes
        self.amplitude = self.amplitude * 0.8 + self.target_amplitude * 0.2
        # Automatically decay amplitude when idle
        if self.target_amplitude > 5.0:
            self.target_amplitude *= 0.95
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        width = self.width()
        height = self.height()
        mid_y = height / 2.0
        
        # Draw background grids/borders in dark HUD blue
        grid_pen = QPen(QColor(0, 191, 255, 30))
        grid_pen.setWidth(1)
        painter.setPen(grid_pen)
        painter.drawLine(0, int(mid_y), width, int(mid_y))
        
        # Draw wave lines
        for i in range(self.lines_count):
            # Scale down outer waves for depth
            scale = 1.0 - (i * 0.3)
            opacity = int(220 * scale)
            
            pen = QPen(QColor(self.color.red(), self.color.green(), self.color.blue(), opacity))
            pen.setWidth(2 if i == 0 else 1)
            painter.setPen(pen)
            
            path = QPainterPath()
            path.moveTo(0, mid_y)
            
            # Draw sine wave path across the width
            for x in range(0, width, 5):
                # Calculate envelope to pinch wave at edges
                envelope = math.sin((x / width) * math.pi)
                
                # Dynamic formula: sine + phase + noise
                angle = (x * self.frequency) - self.phase + (i * 1.5)
                y = mid_y + (self.amplitude * envelope * scale * math.sin(angle))
                
                path.lineTo(x, y)
                
            path.lineTo(width, mid_y)
            painter.drawPath(path)
            
        # Draw small end circles for detail
        painter.setBrush(self.color)
        painter.drawEllipse(0, int(mid_y - 2), 4, 4)
        painter.drawEllipse(width - 4, int(mid_y - 2), 4, 4)
