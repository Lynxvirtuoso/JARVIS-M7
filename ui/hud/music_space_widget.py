import re
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QStackedWidget, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont

from ui.hud.theme import (
    BG_VOID, BG_PANEL, COLOR_CYAN, COLOR_CYAN_FAINT,
    COLOR_TEXT_DIM, COLOR_AMBER, get_mono_family, get_orbitron_family
)
from services.transposition_engine import TranspositionEngine

# ──────────────────────────────────────────────────────────
# Piano Key Widget
# ──────────────────────────────────────────────────────────
class PianoKey(QWidget):
    def __init__(self, note_name: str, is_black: bool = False, parent=None):
        super().__init__(parent)
        self.note_name = note_name
        self.is_black = is_black
        self.swara_text = ""
        
        self.active_in_raga = False
        self.currently_sounding = False
        
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self._update_styles()

    def set_state(self, active_in_raga: bool, swara_text: str = "", currently_sounding: bool = False):
        self.active_in_raga = active_in_raga
        self.swara_text = swara_text
        self.currently_sounding = currently_sounding
        self._update_styles()

    def _update_styles(self):
        # Determine background and borders
        if self.is_black:
            if self.currently_sounding:
                bg = "rgba(255, 180, 84, 0.9)"
                border = f"1px solid {COLOR_AMBER}"
                shadow = "0 0 15px rgba(255, 180, 84, 0.8)"
            elif self.active_in_raga:
                bg = "rgba(255, 180, 84, 0.25)"
                border = f"1px solid {COLOR_AMBER}"
                shadow = "none"
            else:
                bg = "#05080b"
                border = "1px solid rgba(79, 227, 255, 0.1)"
                shadow = "none"
        else:
            if self.currently_sounding:
                bg = "rgba(255, 180, 84, 0.85)"
                border = f"1px solid {COLOR_AMBER}"
                shadow = "0 0 20px rgba(255, 180, 84, 0.7)"
            elif self.active_in_raga:
                bg = "rgba(79, 227, 255, 0.2)"
                border = f"1px solid {COLOR_CYAN}"
                shadow = "inset 0 -15px 30px rgba(79, 227, 255, 0.15)"
            else:
                bg = "#1a242d"
                border = f"1px solid {COLOR_CYAN_FAINT}"
                shadow = "none"

        self.setStyleSheet(f"""
            QWidget {{
                background-color: {bg};
                border: {border};
                border-bottom-left-radius: 4px;
                border-bottom-right-radius: 4px;
            }}
        """)

        # Recreate child labels based on state
        for child in self.findChildren(QLabel):
            child.deleteLater()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 12 if not self.is_black else 6)
        layout.setSpacing(2)
        layout.setAlignment(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter)

        if self.active_in_raga and self.swara_text:
            swara_lbl = QLabel(self.swara_text, self)
            swara_lbl.setStyleSheet(f"""
                QLabel {{
                    background: transparent;
                    color: {COLOR_AMBER if self.is_black else COLOR_CYAN};
                    font-weight: bold;
                    font-size: {'11px' if self.is_black else '14px'};
                    font-family: '{get_mono_family()}';
                }}
            """)
            swara_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(swara_lbl)

        note_lbl = QLabel(self.note_name, self)
        note_color = "#ffffff" if self.currently_sounding else COLOR_TEXT_DIM
        note_lbl.setStyleSheet(f"""
            QLabel {{
                background: transparent;
                color: {note_color};
                font-size: {'9px' if self.is_black else '11px'};
                font-family: '{get_mono_family()}';
            }}
        """)
        note_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(note_lbl)


# ──────────────────────────────────────────────────────────
# Piano Keyboard Layout Widget
# ──────────────────────────────────────────────────────────
class PianoKeyboardWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(280)
        self.setMinimumWidth(800)
        
        self.white_keys = []
        self.black_keys = []
        
        self.white_notes = ["C", "D", "E", "F", "G", "A", "B", "C", "D"]
        # Position mapping matching mockup
        self.black_positions = [
            (0, "C#"), # inside C
            (1, "D#"), # inside D
            (3, "F#"), # inside F
            (4, "G#"), # inside G
            (5, "A#"), # inside A
            (7, "C#")  # inside C'
        ]
        
        self._build_keyboard()

    def _build_keyboard(self):
        # 1. Base container for keys
        self.keyboard_container = QWidget(self)
        self.keyboard_container.setGeometry(0, 0, 780, 270)
        self.keyboard_container.setStyleSheet("background-color: rgba(0, 0, 0, 0.2); border-radius: 8px;")
        
        # 2. Add White Keys Side-by-Side
        white_layout_widget = QWidget(self.keyboard_container)
        white_layout_widget.setGeometry(10, 10, 760, 250)
        white_layout = QHBoxLayout(white_layout_widget)
        white_layout.setContentsMargins(0, 0, 0, 0)
        white_layout.setSpacing(4)
        
        # Width of a white key is (760 - 8*4)/9 = ~80px
        for idx, note in enumerate(self.white_notes):
            key = PianoKey(note, is_black=False, parent=white_layout_widget)
            key.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            white_layout.addWidget(key)
            self.white_keys.append(key)

        # 3. Add Black Keys absolutely overlaid
        # On a 760px wide container, we calculate center boundaries:
        # White key index centers:
        # Key width = 80px, spacing = 4px.
        # Boundary between key i and i+1 is at: (i+1)*80 + i*4 + 2
        for idx, note in self.black_positions:
            bkey = PianoKey(note, is_black=True, parent=self.keyboard_container)
            # Position black key overlapping the boundary
            x_pos = (idx + 1) * 80 + idx * 4 + 10 - 22
            bkey.setGeometry(x_pos, 10, 44, 145)
            bkey.raise_()
            self.black_keys.append(bkey)

    def update_keys(self, active_notes: list, sounding_note_idx: int = -1):
        """
        active_notes: list of dicts, e.g. [{"note": "D", "swara": "S"}, ...]
        sounding_note_idx: index in active_notes list of the note currently playing
        """
        # Build lookup maps
        raga_map = {item["note"].upper(): item["swara"] for item in active_notes}
        sounding_note = ""
        if sounding_note_idx >= 0 and sounding_note_idx < len(active_notes):
            sounding_note = active_notes[sounding_note_idx]["note"].upper()
            
        # Reset & Update white keys
        for key in self.white_keys:
            n = key.note_name.upper()
            is_active = n in raga_map
            is_sounding = is_active and (n == sounding_note)
            key.set_state(is_active, raga_map.get(n, ""), is_sounding)
            
        # Reset & Update black keys
        for key in self.black_keys:
            n = key.note_name.upper()
            is_active = n in raga_map
            is_sounding = is_active and (n == sounding_note)
            key.set_state(is_active, raga_map.get(n, ""), is_sounding)


# ──────────────────────────────────────────────────────────
# Swaras Syllabus Visualiser (Swaras Mode)
# ──────────────────────────────────────────────────────────
class SwarasVisualizerWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(120)
        
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(20, 20, 20, 20)
        self.layout.setSpacing(15)
        
        self.cells = []

    def update_swaras(self, active_notes: list, sounding_idx: int = -1):
        # Clear existing cells
        for cell in self.cells:
            self.layout.removeWidget(cell)
            cell.deleteLater()
        self.cells.clear()
        
        for idx, item in enumerate(active_notes):
            cell = QWidget(self)
            is_sounding = (idx == sounding_idx)
            
            bg = "rgba(79, 227, 255, 0.15)" if is_sounding else "rgba(18, 48, 58, 0.2)"
            border = f"1px solid {COLOR_CYAN}" if is_sounding else f"1px solid {COLOR_CYAN_FAINT}"
            
            cell.setStyleSheet(f"""
                QWidget {{
                    background-color: {bg};
                    border: {border};
                    border-radius: 6px;
                }}
            """)
            cell.setMinimumWidth(80)
            cell.setFixedHeight(80)
            
            cell_layout = QVBoxLayout(cell)
            cell_layout.setContentsMargins(6, 6, 6, 6)
            cell_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            lbl_swara = QLabel(item["swara"], cell)
            lbl_swara.setStyleSheet(f"""
                QLabel {{
                    background: transparent;
                    color: {"#ffffff" if is_sounding else COLOR_CYAN};
                    font-size: 20px;
                    font-weight: bold;
                    font-family: '{get_mono_family()}';
                }}
            """)
            lbl_swara.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cell_layout.addWidget(lbl_swara)
            
            lbl_note = QLabel(item["note"], cell)
            lbl_note.setStyleSheet(f"""
                QLabel {{
                    background: transparent;
                    color: {"#ffffff" if is_sounding else COLOR_TEXT_DIM};
                    font-size: 11px;
                    font-family: '{get_mono_family()}';
                }}
            """)
            lbl_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cell_layout.addWidget(lbl_note)
            
            self.layout.addWidget(cell)
            self.cells.append(cell)


# ──────────────────────────────────────────────────────────
# Full Music Space HUD Screen
# ──────────────────────────────────────────────────────────
class MusicSpaceHUDWidget(QWidget):
    back_clicked = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {BG_VOID};")
        
        # State indicators
        self.active_raga_name = "Kalyani"
        self.raga_classification = "Melakarta (72-scale tradition)"
        self.swara_sequence_list = ["S", "R2", "G3", "M2", "P", "D2", "N3", "S"]
        self.tonic_key = "D"
        self.playback_mode = "PIANO ROLL"
        self.tempo = 60
        self.loop_enabled = True
        self.transport_status = "STOPPED"
        self.sounding_idx = -1
        
        self._build_ui()
        self.update_hud()

    def _build_ui(self):
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(30, 20, 30, 20)
        vbox.setSpacing(20)
        
        # 1. Header
        header = QHBoxLayout()
        self.lbl_back = QLabel("< ESC", self)
        self.lbl_back.setStyleSheet(f"font-family: '{get_mono_family()}'; font-size: 14px; color: {COLOR_TEXT_DIM};")
        header.addWidget(self.lbl_back)
        
        self.lbl_title = QLabel("SPACE_MUSIC", self)
        self.lbl_title.setStyleSheet(f"""
            QLabel {{
                font-family: '{get_orbitron_family()}';
                font-size: 18px;
                font-weight: bold;
                color: {COLOR_AMBER};
                letter-spacing: 5px;
            }}
        """)
        header.addWidget(self.lbl_title, alignment=Qt.AlignmentFlag.AlignCenter)
        
        status_layout = QHBoxLayout()
        status_layout.setSpacing(8)
        self.status_dot = QLabel("●", self)
        self.status_dot.setStyleSheet(f"color: {COLOR_CYAN}; font-size: 12px;")
        self.status_text = QLabel("LISTENING", self)
        self.status_text.setStyleSheet(f"font-family: '{get_mono_family()}'; font-size: 10px; color: {COLOR_CYAN}; letter-spacing: 2px;")
        status_layout.addWidget(self.status_dot)
        status_layout.addWidget(self.status_text)
        header.addLayout(status_layout)
        vbox.addLayout(header)
        
        # 2. Tabs Row
        tabs = QHBoxLayout()
        tabs.setSpacing(15)
        self.tab_notes = QLabel("NOTES", self)
        self.tab_notes.setStyleSheet(f"color: {COLOR_AMBER}; font-weight: bold; font-family: '{get_mono_family()}'; font-size: 11px; letter-spacing: 1.5px; border-bottom: 2px solid {COLOR_AMBER}; padding-bottom: 4px;")
        tabs.addWidget(self.tab_notes)
        
        for name in ["TANPURA DRONE", "PRACTICE MODE", "RAGA LIBRARY"]:
            lbl = QLabel(name, self)
            lbl.setStyleSheet(f"color: {COLOR_TEXT_DIM}; font-family: '{get_mono_family()}'; font-size: 11px; letter-spacing: 1.5px; opacity: 0.4;")
            tabs.addWidget(lbl)
        tabs.addStretch()
        vbox.addLayout(tabs)
        
        # 3. Raga Metadata panels
        meta_row = QHBoxLayout()
        meta_row.setSpacing(20)
        
        # Raga metadata card
        self.panel_raga = QWidget(self)
        self.panel_raga.setStyleSheet(f"background-color: rgba(13, 27, 34, 0.3); border: 1px solid {COLOR_CYAN_FAINT}; border-radius: 8px;")
        raga_vbox = QVBoxLayout(self.panel_raga)
        raga_vbox.setContentsMargins(15, 15, 15, 15)
        
        lbl_raga_title = QLabel("ACTIVE RAGA", self.panel_raga)
        lbl_raga_title.setStyleSheet(f"font-family: '{get_mono_family()}'; font-size: 10px; color: {COLOR_TEXT_DIM}; letter-spacing: 2px;")
        raga_vbox.addWidget(lbl_raga_title)
        
        self.lbl_raga_name = QLabel("Kalyani", self.panel_raga)
        self.lbl_raga_name.setStyleSheet(f"font-family: '{get_orbitron_family()}'; font-size: 24px; font-weight: bold; color: {COLOR_AMBER};")
        raga_vbox.addWidget(self.lbl_raga_name)
        
        self.lbl_raga_desc = QLabel("Melakarta (72-scale tradition)", self.panel_raga)
        self.lbl_raga_desc.setStyleSheet(f"font-family: '{get_mono_family()}'; font-size: 11px; color: #ffffff;")
        raga_vbox.addWidget(self.lbl_raga_desc)
        
        self.lbl_raga_swaras = QLabel("S R2 G3 M2 P D2 N3 S", self.panel_raga)
        self.lbl_raga_swaras.setStyleSheet(f"font-family: '{get_mono_family()}'; font-size: 14px; color: {COLOR_CYAN}; font-weight: bold; letter-spacing: 4px;")
        raga_vbox.addWidget(self.lbl_raga_swaras)
        meta_row.addWidget(self.panel_raga, stretch=2)
        
        # Mode card
        self.panel_mode = QWidget(self)
        self.panel_mode.setStyleSheet(f"background-color: rgba(13, 27, 34, 0.3); border: 1px solid {COLOR_CYAN_FAINT}; border-radius: 8px;")
        mode_vbox = QVBoxLayout(self.panel_mode)
        mode_vbox.setContentsMargins(15, 15, 15, 15)
        lbl_mode_title = QLabel("PLAYBACK MODE", self.panel_mode)
        lbl_mode_title.setStyleSheet(f"font-family: '{get_mono_family()}'; font-size: 10px; color: {COLOR_TEXT_DIM}; letter-spacing: 2px;")
        mode_vbox.addWidget(lbl_mode_title)
        self.lbl_mode_val = QLabel("PIANO ROLL", self.panel_mode)
        self.lbl_mode_val.setStyleSheet(f"font-family: '{get_orbitron_family()}'; font-size: 20px; font-weight: bold; color: {COLOR_CYAN};")
        mode_vbox.addWidget(self.lbl_mode_val)
        lbl_mode_sub = QLabel("PCM Sine Synthesis", self.panel_mode)
        lbl_mode_sub.setStyleSheet(f"font-family: '{get_mono_family()}'; font-size: 10px; color: {COLOR_TEXT_DIM};")
        mode_vbox.addWidget(lbl_mode_sub)
        meta_row.addWidget(self.panel_mode, stretch=1)
        
        # Tonic card
        self.panel_tonic = QWidget(self)
        self.panel_tonic.setStyleSheet(f"background-color: rgba(13, 27, 34, 0.3); border: 1px solid {COLOR_CYAN_FAINT}; border-radius: 8px;")
        tonic_vbox = QVBoxLayout(self.panel_tonic)
        tonic_vbox.setContentsMargins(15, 15, 15, 15)
        lbl_tonic_title = QLabel("TONIC", self.panel_tonic)
        lbl_tonic_title.setStyleSheet(f"font-family: '{get_mono_family()}'; font-size: 10px; color: {COLOR_TEXT_DIM}; letter-spacing: 2px;")
        tonic_vbox.addWidget(lbl_tonic_title)
        self.lbl_tonic_val = QLabel("KEY: D", self.panel_tonic)
        self.lbl_tonic_val.setStyleSheet(f"font-family: '{get_orbitron_family()}'; font-size: 20px; font-weight: bold; color: {COLOR_AMBER};")
        tonic_vbox.addWidget(self.lbl_tonic_val)
        lbl_tonic_sub = QLabel("Root reference pitch", self.panel_tonic)
        lbl_tonic_sub.setStyleSheet(f"font-family: '{get_mono_family()}'; font-size: 10px; color: {COLOR_TEXT_DIM};")
        tonic_vbox.addWidget(lbl_tonic_sub)
        meta_row.addWidget(self.panel_tonic, stretch=1)
        
        vbox.addLayout(meta_row)
        
        # 4. Playback Visualiser Container (Stack white/black keyboard and Swara slots)
        self.visualizer_stack = QStackedWidget(self)
        
        # Keyboard visualizer
        self.keyboard_widget = PianoKeyboardWidget(self)
        self.visualizer_stack.addWidget(self.keyboard_widget)
        
        # Swaras visualizer
        self.swaras_widget = SwarasVisualizerWidget(self)
        self.visualizer_stack.addWidget(self.swaras_widget)
        
        vbox.addWidget(self.visualizer_stack)
        
        # 5. Transport Panel
        self.transport_panel = QWidget(self)
        self.transport_panel.setStyleSheet(f"background-color: rgba(13, 27, 34, 0.4); border: 1px solid {COLOR_CYAN_FAINT}; border-radius: 8px;")
        trans_layout = QHBoxLayout(self.transport_panel)
        trans_layout.setContentsMargins(20, 12, 20, 12)
        
        lbl_trans_status_lbl = QLabel("TRANSPORT STATUS:", self.transport_panel)
        lbl_trans_status_lbl.setStyleSheet(f"font-family: '{get_mono_family()}'; font-size: 10px; color: {COLOR_TEXT_DIM}; letter-spacing: 2px;")
        trans_layout.addWidget(lbl_trans_status_lbl)
        
        self.lbl_trans_status = QLabel("STOPPED", self.transport_panel)
        self.lbl_trans_status.setStyleSheet(f"font-family: '{get_mono_family()}'; font-size: 12px; font-weight: bold; color: {COLOR_AMBER};")
        trans_layout.addWidget(self.lbl_trans_status)
        trans_layout.addSpacing(40)
        
        lbl_tempo_lbl = QLabel("TEMPO:", self.transport_panel)
        lbl_tempo_lbl.setStyleSheet(f"font-family: '{get_mono_family()}'; font-size: 10px; color: {COLOR_TEXT_DIM}; letter-spacing: 2px;")
        trans_layout.addWidget(lbl_tempo_lbl)
        
        self.lbl_tempo = QLabel("60 BPM", self.transport_panel)
        self.lbl_tempo.setStyleSheet(f"font-family: '{get_mono_family()}'; font-size: 12px; font-weight: bold; color: {COLOR_CYAN};")
        trans_layout.addWidget(self.lbl_tempo)
        trans_layout.addSpacing(40)
        
        lbl_loop_lbl = QLabel("LOOP MODE:", self.transport_panel)
        lbl_loop_lbl.setStyleSheet(f"font-family: '{get_mono_family()}'; font-size: 10px; color: {COLOR_TEXT_DIM}; letter-spacing: 2px;")
        trans_layout.addWidget(lbl_loop_lbl)
        
        self.lbl_loop = QLabel("ON", self.transport_panel)
        self.lbl_loop.setStyleSheet(f"font-family: '{get_mono_family()}'; font-size: 12px; font-weight: bold; color: {COLOR_CYAN};")
        trans_layout.addWidget(self.lbl_loop)
        trans_layout.addStretch()
        
        vbox.addWidget(self.transport_panel)
        
        # 6. Hint Area
        hint_panel = QWidget(self)
        hint_panel.setStyleSheet(f"border: 1px dashed {COLOR_CYAN_FAINT}; border-radius: 8px; background-color: rgba(79, 227, 255, 0.01);")
        hint_layout = QHBoxLayout(hint_panel)
        hint_layout.setContentsMargins(15, 12, 15, 12)
        
        lbl_hint_arr = QLabel("➔", hint_panel)
        lbl_hint_arr.setStyleSheet(f"color: {COLOR_CYAN}; font-size: 14px;")
        hint_layout.addWidget(lbl_hint_arr)
        
        lbl_hint_title = QLabel("SAY A COMMAND:", hint_panel)
        lbl_hint_title.setStyleSheet(f"font-family: '{get_mono_family()}'; font-size: 10px; font-weight: bold; color: {COLOR_CYAN}; letter-spacing: 2px;")
        hint_layout.addWidget(lbl_hint_title)
        
        self.lbl_hint_phrase = QLabel('"play the arohana", "play it in D", "switch to piano mode", "set tempo to 75"', hint_panel)
        self.lbl_hint_phrase.setStyleSheet(f"font-family: '{get_mono_family()}'; font-size: 12px; color: {COLOR_TEXT_DIM};")
        hint_layout.addWidget(self.lbl_hint_phrase)
        hint_layout.addStretch()
        
        vbox.addWidget(hint_panel)

    def set_raga(self, name: str, category: str, swaras: list):
        self.active_raga_name = name
        self.raga_classification = category
        self.swara_sequence_list = swaras
        self.update_hud()

    def set_mode(self, mode: str):
        self.playback_mode = mode.upper().strip()
        self.update_hud()

    def set_tonic(self, tonic: str):
        self.tonic_key = tonic.upper().strip()
        self.update_hud()

    def set_transport(self, status: str, tempo: int, loop: bool):
        self.transport_status = status.upper().strip()
        self.tempo = tempo
        self.loop_enabled = loop
        self.update_hud()

    def set_sounding_index(self, idx: int):
        self.sounding_idx = idx
        self.update_hud()

    def update_hud(self):
        # Update metadata card labels
        self.lbl_raga_name.setText(self.active_raga_name)
        self.lbl_raga_desc.setText(self.raga_classification)
        self.lbl_raga_swaras.setText(" ".join(self.swara_sequence_list))
        
        # Update mode and tonic
        self.lbl_mode_val.setText(self.playback_mode)
        self.lbl_tonic_val.setText(f"KEY: {self.tonic_key}")
        
        # Transpose notes to display on keyboard / swaras roll
        transposed = TranspositionEngine.transpose(
            self.swara_sequence_list,
            self.tonic_key,
            scale_type="arohana" # default to arohana visual layout
        )
        
        # Update stack display based on playback mode
        if self.playback_mode == "PIANO ROLL":
            self.visualizer_stack.setCurrentWidget(self.keyboard_widget)
            self.keyboard_widget.update_keys(transposed, self.sounding_idx)
        else:
            self.visualizer_stack.setCurrentWidget(self.swaras_widget)
            self.swaras_widget.update_swaras(transposed, self.sounding_idx)
            
        # Update transport
        self.lbl_trans_status.setText(self.transport_status)
        self.lbl_tempo.setText(f"{self.tempo} BPM")
        self.lbl_loop.setText("ON" if self.loop_enabled else "OFF")
