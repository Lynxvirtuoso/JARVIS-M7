import math
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import QTimer, QPointF, Qt
from PyQt6.QtGui import QPainter, QPen, QColor, QBrush, QRadialGradient

class AICoreWidget(QWidget):
    """
    Futuristic rotating AI Core HUD.
    Visualizes current JARVIS states:
    - 'Passive Listening': Calm cyan, slow rotation
    - 'Listening': Pulsing bright cyan/green, reacts to sound levels
    - 'Processing': Rapid counter-rotating concentric rings (violet/orange)
    - 'Executing': Active blue rotating gears/dashes
    - 'Speaking': Waves pulsing outward from center
    - 'Completed': Double bright flash, returns to Passive
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.state = "Passive Listening"
        self.angle1 = 0
        self.angle2 = 0
        self.pulse_val = 1.0
        self.pulse_dir = 1
        self.audio_level = 0.0 # From microphone or speaker
        
        # Setup animation timer (30 FPS)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_animation)
        self.timer.start(33)
        self.setMinimumSize(220, 220)

    def set_state(self, state):
        if self.state != state:
            self.state = state
            # CPU optimization: Run at 10 FPS during passive/idle state, 30 FPS when active
            if state == "Passive Listening":
                self.timer.setInterval(100)
            else:
                self.timer.setInterval(33)
            self.update()

    def set_status(self, status: str):
        """Alias kept for legacy callers."""
        pass  # Status strings are handled by HUDWindow, not the core widget directly

    def set_audio_level(self, level):
        self.audio_level = self.audio_level * 0.4 + level * 0.6
        self.update()

    def update_animation(self):
        # Update rotation angles based on active state
        if self.state == "Passive Listening":
            self.angle1 += 0.5
            self.angle2 -= 0.25
            self.pulse_val += 0.005 * self.pulse_dir
            if self.pulse_val >= 1.05 or self.pulse_val <= 0.95:
                self.pulse_dir *= -1
        elif self.state == "Listening":
            self.angle1 += 3.0
            self.angle2 -= 2.0
            self.pulse_val = 0.9 + self.audio_level * 0.8
        elif self.state == "Processing":
            self.angle1 += 8.0
            self.angle2 -= 6.0
            self.pulse_val += 0.05 * self.pulse_dir
            if self.pulse_val >= 1.3 or self.pulse_val <= 0.7:
                self.pulse_dir *= -1
        elif self.state == "Executing":
            self.angle1 += 4.0
            self.angle2 -= 4.0
            self.pulse_val += 0.03 * self.pulse_dir
            if self.pulse_val >= 1.15 or self.pulse_val <= 0.85:
                self.pulse_dir *= -1
        elif self.state == "Speaking":
            self.angle1 += 2.0
            self.angle2 -= 1.0
            self.pulse_val = 1.0 + self.audio_level * 0.5
        elif self.state == "Completed":
            self.angle1 += 1.5
            self.angle2 -= 1.5
            self.pulse_val = max(0.5, self.pulse_val - 0.05)
            
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        width = self.width()
        height = self.height()
        center = QPointF(width / 2.0, height / 2.0)
        radius = min(width, height) / 2.0 - 20
        
        # Stark-Industries Electric Cyan color scheme per state
        color_scheme = {
            "Passive Listening": QColor(0, 240, 255),    # High-tech Electric Cyan
            "Listening": QColor(51, 255, 119),           # Active Green
            "Processing": QColor(138, 43, 226),           # Purple
            "Executing": QColor(0, 240, 255),            # Cyan
            "Speaking": QColor(0, 240, 255),             # Cyan
            "Completed": QColor(51, 255, 119)            # Active Green
        }
        
        base_color = color_scheme.get(self.state, QColor(0, 240, 255))
        
        # 1. Outer Arc segments (Dashed thin ring)
        pen = QPen(QColor(base_color.red(), base_color.green(), base_color.blue(), 160))
        pen.setWidth(1)
        painter.setPen(pen)
        
        painter.save()
        painter.translate(center)
        painter.rotate(self.angle1)
        
        # Draw Stark circular outer brackets
        for i in range(12):
            painter.drawArc(
                int(-radius), int(-radius),
                int(radius * 2), int(radius * 2),
                i * 30 * 16 + 5 * 16, 20 * 16
            )
        painter.restore()
        
        # 2. Concentric inner rotating ring (Thicker geometric brackets)
        pen.setColor(QColor(base_color.red(), base_color.green(), base_color.blue(), 200))
        pen.setWidth(2)
        painter.setPen(pen)
        
        painter.save()
        painter.translate(center)
        painter.rotate(self.angle2)
        
        # Draw 4 arcs representing reactor brackets
        arc_len = 45 * 16
        for i in range(4):
            painter.drawArc(
                int(-radius + 15), int(-radius + 15),
                int((radius - 15) * 2), int((radius - 15) * 2),
                i * 90 * 16 + 10 * 16, arc_len
            )
        painter.restore()
        
        # 3. Middle glowing breathing core border
        dynamic_r = radius * 0.6 * self.pulse_val
        pen.setColor(QColor(base_color.red(), base_color.green(), base_color.blue(), 80))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawEllipse(center, dynamic_r, dynamic_r)
        
        # 4. Central Glowing Arc Reactor Core
        core_r = radius * 0.3 * (1.0 + (self.pulse_val - 1.0) * 0.2)
        gradient = QRadialGradient(center, core_r)
        gradient.setColorAt(0.0, QColor(base_color.red(), base_color.green(), base_color.blue(), 255))
        gradient.setColorAt(0.5, QColor(base_color.red(), base_color.green(), base_color.blue(), 120))
        gradient.setColorAt(1.0, QColor(base_color.red(), base_color.green(), base_color.blue(), 0))
        
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(gradient))
        painter.drawEllipse(center, core_r, core_r)
        
        # 5. Core Hexagon/Geometric detail lines
        pen.setColor(QColor(255, 255, 255, 220))
        pen.setWidthF(1.5)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        
        hex_r = core_r * 0.4
        painter.save()
        painter.translate(center)
        painter.rotate(-self.angle1 * 1.5)
        
        # Inner geometric triangle/hexagon details
        points = []
        for i in range(6):
            angle = i * (math.pi / 3)
            points.append(QPointF(hex_r * math.cos(angle), hex_r * math.sin(angle)))
        
        for i in range(6):
            painter.drawLine(points[i], points[(i + 1) % 6])
            # Draw radial spoke lines outward
            painter.drawLine(points[i] * 0.5, points[i] * 1.4)
        painter.restore()
