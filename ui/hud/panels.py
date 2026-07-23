"""
ui/hud/panels.py
Futuristic collapsible HUD panels with integrated Detachable / Resizable module capabilities.
Allows panels to run docked in the HUD window OR double-click to detach as floating windows.
Saves and restores positions/sizes to SQLite.
"""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QDialog
from PyQt6.QtCore import Qt, QPoint, QSize, pyqtSignal, QTimer
from PyQt6.QtGui import QPainter, QPen, QColor, QLinearGradient, QMouseEvent

from ui.hud.theme import (
    BG_PANEL, COLOR_CYAN, COLOR_CYAN_DIM, COLOR_CYAN_FAINT,
    COLOR_TEXT, COLOR_TEXT_DIM, get_orbitron_family, get_mono_family
)

PANEL_WIDTH = 240


# ── Floating Window Wrapper ──────────────────────────────
class HUDFloatingWindow(QDialog):
    """Borderless container for detached modules. Allows drag moving & resizing."""
    def __init__(self, module, parent=None):
        super().__init__(parent)
        self.module = module
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setStyleSheet(f"background-color: {BG_PANEL};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1) # thin cyber border
        layout.setSpacing(0)
        layout.addWidget(module)

        self._drag_pos = None
        self._resize_margin = 8
        self._is_resizing = False

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Glow outer border when floating
        p.setPen(QPen(QColor(COLOR_CYAN_DIM), 1))
        p.drawRect(0, 0, self.width() - 1, self.height() - 1)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            # Check edge resize zones
            pos = event.position().toPoint()
            w, h = self.width(), self.height()
            if pos.x() > w - self._resize_margin or pos.y() > h - self._resize_margin:
                self._is_resizing = True
            else:
                self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._is_resizing:
            pos = event.position().toPoint()
            new_w = max(120, pos.x())
            new_h = max(60, pos.y())
            self.resize(new_w, new_h)
            self.module.resize(new_w, new_h)
        elif self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._drag_pos = None
        self._is_resizing = False
        # Save geometry update
        self.module.save_module_state()


# ── Collapsible Panel with Detachment ────────────────────
class HUDCollapsiblePanel(QWidget):
    """
    Futuristic collapsible panel supporting:
      - Collapsing via title bar click or button
      - Double-click title bar to detach/reattach
      - Persistent layout positioning/floating in SQLite settings table
    """
    detached = pyqtSignal()
    reattached = pyqtSignal()

    def __init__(self, title: str, parent=None, module_id: str = ""):
        super().__init__(parent)
        self.title_text = title
        self.module_id = module_id or title.lower().replace(" ", "_")
        self.collapsed = False
        self._rows: dict[str, QLabel] = {}
        self.floating_win = None
        self._is_floating = False

        self.setFixedWidth(PANEL_WIDTH)
        self.setProperty("class", "HUDPanel")

        # ── Root layout ─────────────────────────────────────
        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(12, 10, 12, 10)
        self.root_layout.setSpacing(0)

        # ── Title row ────────────────────────────────────────
        self.title_row = QWidget(self)
        self.title_row.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.tr_layout = QHBoxLayout(self.title_row)
        self.tr_layout.setContentsMargins(0, 0, 0, 8)
        self.tr_layout.setSpacing(4)

        self.lbl_title = QLabel(title.upper(), self.title_row)
        self.lbl_title.setProperty("class", "HUDPanelTitle")
        self.lbl_title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.lbl_title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.tr_layout.addWidget(self.lbl_title)

        self.min_btn = QPushButton("−", self.title_row)
        self.min_btn.setProperty("class", "HUDMinBtn")
        self.min_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.min_btn.clicked.connect(self.toggle_collapse)
        self.tr_layout.addWidget(self.min_btn)

        self.root_layout.addWidget(self.title_row)

        # ── Body ─────────────────────────────────────────────
        self.body = QWidget(self)
        self.body.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(6)
        self.root_layout.addWidget(self.body)

        # Connect double click filter
        self.title_row.installEventFilter(self)

        # Debounced save QTimer
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._do_save_state)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        p.fillRect(0, 0, w, h, QColor(BG_PANEL))

        # Cyan gradient header strip
        grad = QLinearGradient(0, 0, w, 0)
        grad.setColorAt(0.0, QColor(79, 227, 255, 28))
        grad.setColorAt(0.6, QColor(79, 227, 255, 8))
        grad.setColorAt(1.0, QColor(79, 227, 255, 0))
        p.fillRect(0, 0, w, 30, grad)

        # Faint cyan border
        p.setPen(QPen(QColor(COLOR_CYAN_FAINT), 1))
        p.drawRect(0, 0, w - 1, h - 1)

        # Cyber corners
        p.setPen(QPen(QColor(COLOR_CYAN_DIM), 1.5))
        bl = 7
        p.drawLine(0, 0, bl, 0);       p.drawLine(0, 0, 0, bl)
        p.drawLine(w-1, 0, w-1-bl, 0); p.drawLine(w-1, 0, w-1, bl)
        p.drawLine(0, h-1, bl, h-1);   p.drawLine(0, h-1, 0, h-1-bl)
        p.drawLine(w-1, h-1, w-1-bl, h-1); p.drawLine(w-1, h-1, w-1, h-1-bl)

    def eventFilter(self, obj, event):
        if event.type() == event.Type.MouseButtonDblClick:
            self.toggle_detach()
            return True
        elif event.type() == event.Type.MouseButtonPress and not self._is_floating:
            # Single click collapse only when docked
            self.toggle_collapse()
            return True
        return super().eventFilter(obj, event)

    def toggle_collapse(self):
        self.collapsed = not self.collapsed
        self.body.setVisible(not self.collapsed)
        self.min_btn.setText("+" if self.collapsed else "−")
        self.updateGeometry()

    def add_row(self, name_text: str, val_text: str, is_html: bool = False) -> QWidget:
        row = QWidget(self.body)
        row.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(4)

        lbl_name = QLabel(name_text.upper(), row)
        lbl_name.setProperty("class", "HUDPanelRowLabel")
        rl.addWidget(lbl_name)
        rl.addStretch()

        lbl_val = QLabel(row)
        lbl_val.setProperty("class", "HUDPanelRowValue")
        lbl_val.setText(val_text if is_html else val_text.upper())
        rl.addWidget(lbl_val)

        self.body_layout.addWidget(row)
        self._rows[name_text.upper()] = lbl_val
        return row

    def update_row_value(self, name_text: str, new_value: str, is_html: bool = False):
        key = name_text.upper()
        if key in self._rows:
            self._rows[key].setText(new_value if is_html else new_value.upper())

    # ── Detachable Logic ──────────────────────────────────
    def toggle_detach(self):
        if self._is_floating:
            self.reattach()
        else:
            self.detach()

    def detach(self):
        if self._is_floating:
            return
        self._is_floating = True
        self.setMaximumSize(16777215, 16777215)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # Unlock fixed width when floating
        self.setMinimumWidth(120)
        self.setMaximumWidth(16777215)

        # Notify parent to remove from layout
        self.detached.emit()

        # Wrap in floating dialog
        self.floating_win = HUDFloatingWindow(self, self.window())
        self.floating_win.resize(self.sizeHint())
        self.restore_module_state()
        self.floating_win.show()
        self.save_module_state()

    def reattach(self):
        if not self._is_floating:
            return
        self._is_floating = False
        if self.floating_win:
            self.floating_win.layout().removeWidget(self)
            self.floating_win.close()
            self.floating_win = None

        self.setFixedWidth(PANEL_WIDTH)
        self.reattached.emit()
        self.save_module_state()

    # ── State Persistence ────────────────────────────────
    def save_module_state(self):
        self._save_timer.start(500) # debounce db writes

    def _do_save_state(self):
        try:
            from core.database import db
            if self._is_floating and self.floating_win:
                geom = self.floating_win.geometry()
                val = f"{geom.x()},{geom.y()},{geom.width()},{geom.height()},1"
            else:
                val = "0,0,0,0,0"
            db.set_setting(f"hud_module_{self.module_id}", val)
        except Exception:
            pass

    def restore_module_state(self):
        try:
            from core.database import db
            val = db.get_setting(f"hud_module_{self.module_id}")
            if val and val.endswith(",1") and self.floating_win:
                parts = val.split(",")
                x, y = int(parts[0]), int(parts[1])
                w, h = int(parts[2]), int(parts[3])
                self.floating_win.setGeometry(x, y, w, h)
                self.resize(w, h)
        except Exception:
            pass
