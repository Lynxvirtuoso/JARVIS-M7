from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPlainTextEdit, QLabel
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QColor, QFont, QTextCursor
from core.event_bus import bus

class ConsoleWidget(QWidget):
    """
    HUD console feed. Shows live application logs, transcribed commands,
    responses, and system states.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        
        # Header label
        self.header = QLabel("SYSTEM FEED LOG", self)
        self.header.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        self.header.setStyleSheet("color: #00bfff; letter-spacing: 1px;")
        layout.addWidget(self.header)
        
        # Text display
        self.text_area = QPlainTextEdit(self)
        self.text_area.setReadOnly(True)
        self.text_area.setFont(QFont("Consolas", 9))
        self.text_area.setMaximumBlockCount(200) # Prevents memory leaks
        
        # Cyberpunk style stylesheet
        self.text_area.setStyleSheet("""
            QPlainTextEdit {
                background-color: rgba(10, 15, 28, 180);
                border: 1px solid #00bfff;
                border-radius: 4px;
                color: #ffffff;
            }
            QScrollBar:vertical {
                border: none;
                background: rgba(10, 15, 28, 50);
                width: 6px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #00bfff;
                min-height: 20px;
                border-radius: 3px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                border: none;
                background: none;
            }
        """)
        layout.addWidget(self.text_area)
        
        # Connect to event bus
        bus.console_log.connect(self.append_log)
        
        # Initial greeting in the feed
        self.append_log("INFO", "Initializing system modules...")
        self.append_log("INFO", "Event bus listening on channel JARVIS-MAIN.")

    def append_log(self, level, message):
        color = "#ffffff"
        if level == "ERROR":
            color = "#ff4c4c"
        elif level == "WARN" or level == "WARNING":
            color = "#ffa500"
        elif level == "INFO":
            color = "#00bfff"
        elif level == "SUCCESS":
            color = "#00ff7f"
            
        html_msg = f'<font color="{color}">[{level}]</font> {message}'
        self.text_area.appendHtml(html_msg)
        
        # Auto scroll to bottom
        self.text_area.moveCursor(QTextCursor.MoveOperation.End)
