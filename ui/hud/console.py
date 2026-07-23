"""
ui/hud/console.py
HUD raw developer console feed promoted to a detachable module.
"""
from PyQt6.QtWidgets import QPlainTextEdit, QSizePolicy
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QTextCursor

from core.event_bus import bus
from ui.hud.panels import HUDCollapsiblePanel
from ui.hud.theme import COLOR_CYAN, COLOR_CYAN_DIM, COLOR_TEXT, get_mono_family


class ConsoleWidget(HUDCollapsiblePanel):
    """
    Developer Console Module.
    Subscribes to bus.console_log and displays raw application logging.
    Can be floated or resized.
    """
    def __init__(self, parent=None):
        super().__init__("DEV CONSOLE", parent, module_id="dev_console")

        self.text_area = QPlainTextEdit(self.body)
        self.text_area.setReadOnly(True)
        self.text_area.setFont(QFont(get_mono_family(), 9))
        self.text_area.setMaximumBlockCount(150)
        self.text_area.setFixedHeight(120)
        self.text_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.text_area.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: #050A0F;
                border: 1px solid #142834;
                color: {COLOR_TEXT};
            }}
            QScrollBar:vertical {{
                border: none; background: #050B14; width: 3px; margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {COLOR_CYAN_DIM}; min-height: 14px; border-radius: 1px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                border: none; background: none;
            }}
        """)
        self.body_layout.addWidget(self.text_area)

        # Wire up bus
        bus.console_log.connect(self.append_log)

        # Seed initial log lines
        self.append_log("INFO", "Developer console active.")

    def append_log(self, level: str, message: str):
        color = "#ffffff"
        if level == "ERROR":
            color = "#FF5555"
        elif level in ("WARN", "WARNING"):
            color = "#FFB454"
        elif level == "INFO":
            color = COLOR_CYAN
        elif level == "SUCCESS":
            color = "#55FF55"

        html_msg = f'<font color="{color}">[{level[:4]}]</font> <font color="#A5C6D0">{message}</font>'
        self.text_area.appendHtml(html_msg)

        # Auto scroll
        self.text_area.moveCursor(QTextCursor.MoveOperation.End)
