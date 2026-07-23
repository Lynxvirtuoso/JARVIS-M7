import sys
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout
from PyQt6.QtCore import Qt, QTimer, QVariantAnimation, QEasingCurve, pyqtSignal
from PyQt6.QtGui import QPainter, QPen, QColor, QFont
from ui.hud.theme import (
    COLOR_VOID, COLOR_CYAN, COLOR_CYAN_DIM, COLOR_CYAN_FAINT,
    COLOR_TEXT, COLOR_TEXT_DIM, get_mono_family
)

class BootWidget(QWidget):
    # Emitted when the boot sequence finishes (during the core flash)
    boot_finished = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {COLOR_VOID};")
        
        # Dimensions and properties of the 4 iris rings
        self.ring_configs = [
            {"target_size": 40,  "color": COLOR_CYAN_DIM,   "delay": 50},
            {"target_size": 120, "color": COLOR_CYAN_FAINT, "delay": 150},
            {"target_size": 260, "color": COLOR_CYAN_DIM,   "delay": 300},
            {"target_size": 480, "color": COLOR_CYAN_FAINT, "delay": 450}
        ]
        
        # Animation states
        self.ring_scales = [0.6] * 4
        self.ring_opacities = [0.0] * 4
        self.animations = []

        # Boot log configuration
        self.boot_lines = [
            ("SYS", "Cold boot sequence initiated"),
            ("AUDIO", "Microphone device stream online"),
            ("STT", "groq_stt provider selected"),
            ("NLU", "llama-3.3-70b-versatile ready"),
            ("CONTACTS", "829 contacts cached"),
            ("BRIDGE", "Phone bridge handshake OK"),
            ("TRUST", "TrustGate policy loaded"),
            ("CORE", "Arc reactor stable")
        ]
        self.current_log_index = 0

        # Layout for boot log
        self.log_container = QWidget(self)
        self.log_layout = QVBoxLayout(self.log_container)
        self.log_layout.setContentsMargins(0, 0, 0, 0)
        self.log_layout.setSpacing(6)
        self.log_container.setFixedWidth(420)
        self.log_container.setFixedHeight(220)

        # Trigger sequence
        QTimer.singleShot(100, self.start_ring_animations)
        QTimer.singleShot(700, self.start_boot_log)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Center the log container at the bottom
        w = self.width()
        h = self.height()
        self.log_container.move(
            int((w - self.log_container.width()) / 2),
            int(h - self.log_container.height() - h * 0.08)
        )

    def start_ring_animations(self):
        for i, config in enumerate(self.ring_configs):
            self.schedule_ring_anim(i, config["delay"])

    def schedule_ring_anim(self, index, delay):
        QTimer.singleShot(delay, lambda: self.animate_ring(index))

    def animate_ring(self, index):
        anim = QVariantAnimation(self)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setDuration(600)
        anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        
        def update_frame(val):
            # scale goes 0.6 -> 1.0, opacity 0.0 -> 1.0
            self.ring_scales[index] = 0.6 + 0.4 * val
            self.ring_opacities[index] = val
            self.update()

        anim.valueChanged.connect(update_frame)
        self.animations.append(anim)
        anim.start()

    def start_boot_log(self):
        self.show_next_log_line()

    def show_next_log_line(self):
        if self.current_log_index < len(self.boot_lines):
            tag, msg = self.boot_lines[self.current_log_index]
            
            # Create line widget
            line_lbl = QLabel()
            line_lbl.setFont(QFont(get_mono_family(), 10))
            line_lbl.setText(
                f'<span style="color:{COLOR_TEXT_DIM}">[{tag}]</span> '
                f'<span style="color:{COLOR_TEXT}">{msg}</span> '
                f'<span style="color:{COLOR_CYAN}">OK</span>'
            )
            line_lbl.setStyleSheet("background: transparent;")
            self.log_layout.addWidget(line_lbl)
            
            self.current_log_index += 1
            # 160ms delay between log lines
            QTimer.singleShot(160, self.show_next_log_line)
        else:
            # End of log lines, trigger transition flash after 500ms
            QTimer.singleShot(500, self.trigger_flash)

    def trigger_flash(self):
        self.boot_finished.emit()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Center of the screen
        cx = self.width() / 2.0
        cy = self.height() / 2.0
        
        for i, config in enumerate(self.ring_configs):
            opacity = self.ring_opacities[i]
            if opacity <= 0.0:
                continue
                
            scale = self.ring_scales[i]
            size = config["target_size"] * scale
            
            color = QColor(config["color"])
            color.setAlpha(int(opacity * 255))
            
            pen = QPen(color, 1)
            painter.setPen(pen)
            painter.drawEllipse(int(cx - size/2), int(cy - size/2), int(size), int(size))


class CoreFlashOverlay(QWidget):
    flash_midpoint = pyqtSignal()
    flash_completed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setVisible(False)
        self.opacity = 0.0

    def start_flash(self):
        self.setVisible(True)
        # Fade in to 1.0 (pure cyan) in 150ms
        self.in_anim = QVariantAnimation(self)
        self.in_anim.setStartValue(0.0)
        self.in_anim.setEndValue(1.0)
        self.in_anim.setDuration(150)
        
        def update_in(val):
            self.opacity = val
            self.update()
            
        self.in_anim.valueChanged.connect(update_in)
        self.in_anim.finished.connect(self.start_fade_out)
        self.in_anim.start()

    def start_fade_out(self):
        self.flash_midpoint.emit()
        # Fade out to 0.0 in 500ms
        self.out_anim = QVariantAnimation(self)
        self.out_anim.setStartValue(1.0)
        self.out_anim.setEndValue(0.0)
        self.out_anim.setDuration(500)
        
        def update_out(val):
            self.opacity = val
            self.update()
            
        self.out_anim.valueChanged.connect(update_out)
        self.out_anim.finished.connect(self.finish_flash)
        self.out_anim.start()

    def finish_flash(self):
        self.setVisible(False)
        self.flash_completed.emit()

    def paintEvent(self, event):
        painter = QPainter(self)
        color = QColor(COLOR_CYAN)
        color.setAlpha(int(self.opacity * 255))
        painter.fillRect(self.rect(), color)
