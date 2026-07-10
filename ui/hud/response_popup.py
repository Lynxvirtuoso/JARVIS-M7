import sys
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTextEdit, QLabel
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QPen, QPainter, QBrush

class ResponsePopupWindow(QWidget):
    """
    Auto-popup response window that attaches to the main HUD window.
    Appears for LLM responses, receives text streamed sentence-by-sentence,
    and auto-dismisses after a configurable delay when speech finishes.
    """
    def __init__(self, parent_hud, dismiss_delay=5):
        super().__init__()
        self.parent_hud = parent_hud
        self.dismiss_delay = dismiss_delay
        
        # Configure window properties (non-focus stealing, stays on top, tool window)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        
        self.resize(320, 220)
        
        # Setup UI layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # Header Label (Small monospace CAP style)
        self.title_label = QLabel("JARVIS CORE OUTPUT", self)
        self.title_label.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        self.title_label.setStyleSheet("color: #00f0ff; letter-spacing: 1px;")
        layout.addWidget(self.title_label)
        
        # Content scrolling text edit (styled as terminal feed)
        self.text_area = QTextEdit(self)
        self.text_area.setReadOnly(True)
        self.text_area.setFont(QFont("Consolas", 10))
        self.text_area.setStyleSheet("""
            QTextEdit {
                background-color: transparent;
                border: none;
                color: #00f0ff;
            }
        """)
        # Disable scrollbars visually for HUD aesthetics
        self.text_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.text_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(self.text_area)
        
        # Auto-dismiss timer
        self.dismiss_timer = QTimer(self)
        self.dismiss_timer.setSingleShot(True)
        self.dismiss_timer.timeout.connect(self.hide_popup)
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Translucent glass backplate with cyan glowing border
        rect = self.rect()
        bg_color = QColor(6, 12, 22, 220)
        border_color = QColor(0, 240, 255, 180)
        
        # Draw rounded card background
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(bg_color))
        painter.drawRoundedRect(rect.adjusted(2, 2, -2, -2), 8.0, 8.0)
        
        # Draw thin accent border
        pen = QPen(border_color, 1)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect.adjusted(2, 2, -2, -2), 8.0, 8.0)

    def position_popup(self):
        """Position popup relative to main HUD, safe for screen bounds."""
        if not self.parent_hud:
            return
            
        hud_geom = self.parent_hud.geometry()
        screen = self.parent_hud.screen().availableGeometry()
        
        # Default positioning on the left side
        target_x = hud_geom.x() - self.width() - 10
        target_y = hud_geom.y() + (hud_geom.height() - self.height()) // 2
        
        # Check bounds: if left space is insufficient, flip to the right
        if target_x < screen.left():
            target_x = hud_geom.x() + hud_geom.width() + 10
            
        self.move(target_x, target_y)

    def show_popup(self):
        self.dismiss_timer.stop()
        self.position_popup()
        if not self.isVisible():
            self.text_area.clear()
            self.show()
        
    def append_text_chunk(self, text):
        self.show_popup()
        # Append sentence with space
        self.text_area.insertPlainText(text + " ")
        # Ensure scroll is at the bottom
        scrollbar = self.text_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def start_dismiss_countdown(self):
        """Called when speech completes."""
        self.dismiss_timer.start(self.dismiss_delay * 1000)

    def hide_popup(self):
        self.hide()
