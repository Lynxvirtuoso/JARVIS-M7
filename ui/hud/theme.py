"""
ui/hud/theme.py
Design system: palette, fonts, global QSS, overlay widgets.
"""
import os
import urllib.request
from PyQt6.QtGui import QFontDatabase, QColor, QPainter, QPen
from PyQt6.QtCore import Qt, QCoreApplication
from PyQt6.QtWidgets import QWidget

# ── Try project logger, fallback to stdlib ────────────────
try:
    from core.logger import logger
    log_info  = logger.info
    log_error = logger.error
except ImportError:
    import logging
    logging.basicConfig(level=logging.INFO)
    log_info  = logging.info
    log_error = logging.error

# ── Palette ───────────────────────────────────────────────
BG_VOID        = "#050708"
BG_PANEL       = "#0A1218"
BG_PANEL_2     = "#0D1B22"
COLOR_CYAN      = "#4FE3FF"
COLOR_CYAN_DIM  = "#1B4855"
COLOR_CYAN_FAINT= "#12303A"
COLOR_AMBER     = "#FFB454"
COLOR_TEXT      = "#E8F4F8"
COLOR_TEXT_DIM  = "#5D8A96"

# Legacy aliases kept for backward compat with other modules
COLOR_VOID       = BG_VOID
COLOR_PANEL      = BG_PANEL
COLOR_PANEL_SOLID= BG_PANEL

# ── Font setup ────────────────────────────────────────────
FONTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
FONT_URLS = {
    "Orbitron-Regular.ttf": "https://github.com/theleagueof/orbitron/raw/master/Orbitron%20Medium.ttf",
    "Orbitron-Bold.ttf":    "https://github.com/theleagueof/orbitron/raw/master/Orbitron%20Bold.ttf",
    "JetBrainsMono-Regular.ttf": "https://github.com/JetBrains/JetBrainsMono/raw/master/fonts/ttf/JetBrainsMono-Regular.ttf",
    "JetBrainsMono-Bold.ttf":    "https://github.com/JetBrains/JetBrainsMono/raw/master/fonts/ttf/JetBrainsMono-Bold.ttf",
}
_FONTS_LOADED = False


def load_fonts() -> bool:
    global _FONTS_LOADED
    if _FONTS_LOADED:
        return True
    os.makedirs(FONTS_DIR, exist_ok=True)
    for name, url in FONT_URLS.items():
        path = os.path.join(FONTS_DIR, name)
        if not os.path.exists(path):
            try:
                with urllib.request.urlopen(url, timeout=1.5) as r:
                    open(path, "wb").write(r.read())
            except Exception as e:
                log_error(f"Font download failed ({name}): {e}")
    if not QCoreApplication.instance():
        return False
    loaded = False
    for name in FONT_URLS:
        p = os.path.join(FONTS_DIR, name)
        if os.path.exists(p) and QFontDatabase.addApplicationFont(p) != -1:
            loaded = True
    if loaded:
        log_info("Custom fonts loaded")
        _FONTS_LOADED = True
    else:
        log_info("Using fallback fonts (download failed/unavailable)")
    return _FONTS_LOADED


load_fonts()  # attempt pre-app load; will skip QFontDatabase silently


def get_orbitron_family() -> str:
    return "Orbitron" if (_FONTS_LOADED or load_fonts()) else "Segoe UI"


def get_mono_family() -> str:
    return "JetBrains Mono" if (_FONTS_LOADED or load_fonts()) else "Consolas"


def get_hud_styling() -> str:
    orb  = get_orbitron_family()
    mono = get_mono_family()
    return f"""
QMainWindow, QWidget {{
    background-color: {BG_VOID};
    font-family: '{mono}';
}}

/* ── Collapsible Panels ── */
.HUDPanel {{
    background-color: {BG_PANEL};
    border: 1px solid {COLOR_CYAN_FAINT};
}}
.HUDPanelTitle {{
    font-family: '{orb}';
    font-size: 9px;
    font-weight: 700;
    color: {COLOR_CYAN};
    letter-spacing: 2px;
}}
.HUDPanelRowLabel {{
    font-family: '{mono}';
    font-size: 10px;
    color: {COLOR_TEXT_DIM};
    background: transparent;
}}
.HUDPanelRowValue {{
    font-family: '{mono}';
    font-size: 10px;
    font-weight: bold;
    color: {COLOR_TEXT};
    background: transparent;
}}
.HUDMinBtn {{
    border: 1px solid {COLOR_CYAN_DIM};
    color: {COLOR_TEXT_DIM};
    background: transparent;
    font-size: 11px;
    max-width: 16px;
    max-height: 16px;
    min-width: 16px;
    min-height: 16px;
    padding: 0px;
}}
.HUDMinBtn:hover {{
    color: {COLOR_CYAN};
    border-color: {COLOR_CYAN};
}}
"""


# ── Corner Bracket Overlay Widget ─────────────────────────
class CornerBracketOverlay(QWidget):
    """Transparent overlay that draws sci-fi corner brackets over parent."""
    def __init__(self, parent=None, bracket_len: int = 24,
                 offset: int = 14, color: str = COLOR_CYAN_DIM):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.bracket_len = bracket_len
        self.offset = offset
        self.color = color

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(self.color), 1.5))
        w, h = self.width(), self.height()
        o, l = self.offset, self.bracket_len
        # TL
        p.drawLine(o, o, o + l, o); p.drawLine(o, o, o, o + l)
        # TR
        p.drawLine(w - o, o, w - o - l, o); p.drawLine(w - o, o, w - o, o + l)
        # BL
        p.drawLine(o, h - o, o + l, h - o); p.drawLine(o, h - o, o, h - o - l)
        # BR
        p.drawLine(w - o, h - o, w - o - l, h - o); p.drawLine(w - o, h - o, w - o, h - o - l)
