from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QLineEdit, QPushButton, QComboBox, QFormLayout,
                             QTabWidget, QCheckBox, QSlider, QGridLayout, QGroupBox, QFileDialog, QListWidget)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor
from core.config import config
from core.logger import logger
from core.event_bus import bus
import sounddevice as sd
import numpy as np
import threading
import json

class CalibrationWizardWindow(QWidget):
    """
    Step-by-step guided Voice Calibration Wizard window.
    """
    def __init__(self, parent=None):
        super().__init__()
        self.parent_win = parent
        self.setWindowTitle("JARVIS M7 - VOICE CALIBRATION WIZARD")
        self.resize(500, 420)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet("""
            QWidget {
                background-color: #081124;
                color: #ffffff;
                font-family: Consolas;
            }
            QLabel {
                color: #00bfff;
            }
            QPushButton {
                background-color: rgba(0, 191, 255, 30);
                border: 1px solid #00bfff;
                border-radius: 4px;
                color: #00bfff;
                font-weight: bold;
                padding: 10px;
            }
            QPushButton:hover {
                background-color: #00bfff;
                color: #000000;
            }
            QPushButton:disabled {
                background-color: rgba(100, 100, 100, 20);
                border: 1px solid #555555;
                color: #777777;
            }
        """)
        
        self.phrases = [
            "Wake up Jarvis",
            "Open Chrome",
            "Open Notepad",
            "Open VS Code",
            "Take screenshot",
            "Increase volume",
            "Decrease volume",
            "Shutdown Jarvis"
        ]
        self.current_step = 0
        
        # Load existing corrections
        try:
            val = config.get("personal_corrections")
            if val:
                self.recorded_corrections = json.loads(val)
            else:
                self.recorded_corrections = self.get_empty_corrections()
        except Exception:
            self.recorded_corrections = self.get_empty_corrections()
            
        self.init_ui()

    def get_empty_corrections(self):
        return {
            "open chrome": [],
            "open notepad": [],
            "open vs code": [],
            "take screenshot": [],
            "increase volume": [],
            "decrease volume": [],
            "mute volume": [],
            "shutdown jarvis": []
        }

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(15)
        
        self.title_lbl = QLabel("VOICE CALIBRATION WIZARD", self)
        self.title_lbl.setFont(QFont("Consolas", 12, QFont.Weight.Bold))
        self.title_lbl.setStyleSheet("color: #00ffff; letter-spacing: 1px;")
        layout.addWidget(self.title_lbl)
        
        self.desc_lbl = QLabel("Please read the following phrase in your natural voice and accent:", self)
        self.desc_lbl.setWordWrap(True)
        self.desc_lbl.setStyleSheet("color: #ffffff;")
        layout.addWidget(self.desc_lbl)
        
        # Big phrase text
        self.phrase_lbl = QLabel(self.phrases[0], self)
        self.phrase_lbl.setFont(QFont("Consolas", 18, QFont.Weight.Bold))
        self.phrase_lbl.setStyleSheet("color: #00ff7f; margin: 15px 0;")
        self.phrase_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.phrase_lbl)
        
        # Results area
        self.result_group = QGroupBox("DIAGNOSTICS RESULTS", self)
        self.result_group.setStyleSheet("color: #00bfff; border: 1px solid rgba(0, 191, 255, 50); font-size: 10px; font-weight: bold; margin-top: 10px; padding: 10px;")
        res_layout = QVBoxLayout(self.result_group)
        
        self.raw_lbl = QLabel("Raw Transcription: -", self)
        self.corr_lbl = QLabel("Corrected Command: -", self)
        self.conf_lbl = QLabel("Confidence Score: -", self)
        
        for lbl in [self.raw_lbl, self.corr_lbl, self.conf_lbl]:
            lbl.setFont(QFont("Consolas", 9))
            lbl.setStyleSheet("color: #ffffff;")
            res_layout.addWidget(lbl)
            
        layout.addWidget(self.result_group)
        
        # Controls Layout
        ctrl_layout = QHBoxLayout()
        
        self.cancel_btn = QPushButton("CANCEL", self)
        self.cancel_btn.clicked.connect(self.close)
        ctrl_layout.addWidget(self.cancel_btn)
        
        self.record_btn = QPushButton("RECORD AND PROCESS", self)
        self.record_btn.setStyleSheet("background-color: rgba(0, 255, 127, 30); border: 1px solid #00ff7f; color: #00ff7f;")
        self.record_btn.clicked.connect(self.record_phrase)
        ctrl_layout.addWidget(self.record_btn)
        
        self.next_btn = QPushButton("NEXT", self)
        self.next_btn.setEnabled(False)
        self.next_btn.clicked.connect(self.next_step)
        ctrl_layout.addWidget(self.next_btn)
        
        layout.addLayout(ctrl_layout)

    def record_phrase(self):
        self.record_btn.setEnabled(False)
        self.record_btn.setText("LISTENING (3s)...")
        self.next_btn.setEnabled(False)
        
        def run_rec():
            try:
                device_idx = None
                saved_name = config.get("mic_device_name")
                if saved_name:
                    devices = sd.query_devices()
                    for idx, dev in enumerate(devices):
                        if dev.get("name") == saved_name:
                            device_idx = idx
                            break
                if device_idx is None:
                    device_idx = sd.default.device[0]
                
                device_info = sd.query_devices(device_idx)
                native_rate = int(device_info.get("default_samplerate", 16000))
                
                fs = native_rate
                duration = 3.5
                recording = sd.rec(int(duration * fs), samplerate=fs, channels=1, dtype='float32', device=device_idx)
                sd.wait()
                
                self.record_btn.setText("PROCESSING...")
                audio_data = recording.flatten()
                
                gain_db = float(config.get("input_gain_boost_db", "0"))
                if gain_db != 0:
                    gain_factor = 10 ** (gain_db / 20.0)
                    audio_data = audio_data * gain_factor
                
                if fs != 16000:
                    xp = np.linspace(0, 1, len(audio_data))
                    x = np.linspace(0, 1, int(duration * 16000))
                    audio_data = np.interp(x, xp, audio_data).astype(np.float32)
                
                peak_val = np.max(np.abs(audio_data))
                if peak_val > 0:
                    audio_data = audio_data / peak_val * 0.9
                
                from services.audio_service import audio_service
                if audio_service.model_loaded and audio_service.whisper_model:
                    initial_prompt = (
                        "This is a short voice command for a Windows desktop assistant named Jarvis. "
                        "The user may say commands such as: open Chrome, open Notepad, open VS Code, "
                        "close window, increase volume, decrease volume, mute volume, take screenshot, "
                        "search Google, open downloads, open documents, shutdown Jarvis, exit Jarvis, "
                        "lock computer, what time is it, turn on lights, turn off lights."
                    )
                    segments, info = audio_service.whisper_model.transcribe(
                        audio_data, beam_size=5, language="en",
                        temperature=0, condition_on_previous_text=False,
                        vad_filter=True, initial_prompt=initial_prompt
                    )
                    raw_text = " ".join([s.text for s in segments]).strip()
                else:
                    raw_text = ""
                
                if raw_text:
                    from core.engine import CommandWorker, JarvisEngine
                    normalized = CommandWorker.normalize_command(raw_text)
                    
                    temp_engine = JarvisEngine()
                    corrected, confidence = temp_engine.correct_command(normalized)
                    pct = int(confidence * 100)
                    
                    expected = self.phrases[self.current_step].lower()
                    
                    if normalized != expected and expected in self.recorded_corrections:
                        if normalized and normalized not in self.recorded_corrections[expected]:
                            self.recorded_corrections[expected].append(normalized)
                        raw_lower = raw_text.lower().strip()
                        if raw_lower and raw_lower not in self.recorded_corrections[expected]:
                            self.recorded_corrections[expected].append(raw_lower)
                    
                    self.raw_lbl.setText(f"Raw Transcription: '{raw_text}'")
                    self.corr_lbl.setText(f"Corrected Command: '{corrected}'")
                    self.conf_lbl.setText(f"Confidence Score: {pct}%")
                    
                    bus.console_log.emit("INFO", f"Calibration Step {self.current_step + 1}: Raw='{raw_text}' (Expected: '{expected}')")
                else:
                    self.raw_lbl.setText("Raw Transcription: (No speech detected)")
                    self.corr_lbl.setText("Corrected Command: -")
                    self.conf_lbl.setText("Confidence Score: -")
                    bus.console_log.emit("WARN", "Calibration Step: No speech transcribed.")
                    
            except Exception as e:
                logger.error(f"Calibration recording step error: {e}")
                bus.console_log.emit("ERROR", f"Wizard recording error: {e}")
            finally:
                self.record_btn.setEnabled(True)
                self.record_btn.setText("RECORD AND PROCESS")
                self.next_btn.setEnabled(True)
                
        threading.Thread(target=run_rec, daemon=True).start()

    def next_step(self):
        self.current_step += 1
        if self.current_step < len(self.phrases):
            self.phrase_lbl.setText(self.phrases[self.current_step])
            self.raw_lbl.setText("Raw Transcription: -")
            self.corr_lbl.setText("Corrected Command: -")
            self.conf_lbl.setText("Confidence Score: -")
            self.next_btn.setEnabled(False)
        else:
            config.set("personal_corrections", json.dumps(self.recorded_corrections))
            logger.info("Personal voice corrections memory updated.")
            bus.console_log.emit("INFO", "Guided voice calibration complete! Corrections saved.")
            
            from services.speech_service import speech
            speech.speak("Voice calibration complete, Sir. Your voice profile has been personalized.")
            self.close()

class SettingsWindow(QWidget):
    """
    Futuristic tabbed settings panel for JARVIS M7 configurations.
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("JARVIS M7 - CONFIGURATION PANEL")
        self.resize(540, 840)
        self.setStyleSheet("""
            QWidget {
                background-color: #0c162a;
                color: #ffffff;
                font-family: Consolas;
            }
            QLabel {
                color: #00bfff;
                font-size: 11px;
                font-weight: bold;
            }
            QLineEdit {
                background-color: #0a0f1c;
                border: 1px solid #00bfff;
                border-radius: 4px;
                color: #ffffff;
                padding: 6px;
            }
            QComboBox {
                background-color: #0a0f1c;
                border: 1px solid #00bfff;
                border-radius: 4px;
                color: #ffffff;
                padding: 6px;
            }
            QPushButton {
                background-color: rgba(0, 191, 255, 30);
                border: 1px solid #00bfff;
                border-radius: 4px;
                color: #00bfff;
                font-weight: bold;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #00bfff;
                color: #000000;
            }
            QTabWidget::pane {
                border: 1px solid #00bfff;
                background-color: #0c162a;
                border-radius: 6px;
            }
            QTabBar::tab {
                background-color: #0a0f1c;
                color: #00bfff;
                border: 1px solid #00bfff;
                padding: 8px 16px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background-color: #0c162a;
                color: #00ffff;
                border-bottom-color: #0c162a;
            }
            QSlider::groove:horizontal {
                border: 1px solid #00bfff;
                height: 8px;
                background: #0a0f1c;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #00bfff;
                border: 1px solid #00ffff;
                width: 16px;
                height: 16px;
                margin: -4px 0;
                border-radius: 8px;
            }
            QCheckBox {
                color: #00bfff;
                font-weight: bold;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border: 1px solid #00bfff;
                background-color: #0a0f1c;
                border-radius: 3px;
            }
            QCheckBox::indicator:checked {
                background-color: #00ff7f;
                border: 1px solid #00ff7f;
            }
            QListWidget {
                background-color: #0a0f1c;
                border: 1px solid #00bfff;
                color: #ffffff;
                max-height: 100px;
                font-size: 10px;
            }
        """)
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)
        
        title = QLabel("JARVIS OS CONFIGURATION", self)
        title.setFont(QFont("Consolas", 14, QFont.Weight.Bold))
        title.setStyleSheet("color: #00ffff; letter-spacing: 2px; margin-bottom: 5px;")
        main_layout.addWidget(title)
        
        self.tabs = QTabWidget(self)
        
        # --- TAB 1: GENERAL SETTINGS ---
        tab_general = QWidget()
        form_general = QFormLayout(tab_general)
        form_general.setContentsMargins(15, 15, 15, 15)
        form_general.setSpacing(15)
        
        self.salutation_edit = QLineEdit(self)
        self.salutation_edit.setText(config.get("salutation", "Sir"))
        form_general.addRow("SALUTATION:", self.salutation_edit)
        
        self.gemini_edit = QLineEdit(self)
        self.gemini_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.gemini_edit.setText(config.get("gemini_api_key", ""))
        form_general.addRow("GEMINI API KEY:", self.gemini_edit)
        
        self.tts_combo = QComboBox(self)
        self.tts_combo.addItems(["kokoro", "piper", "sapi"])
        self.tts_combo.setCurrentText(config.get("tts_provider", "kokoro"))
        form_general.addRow("TTS ENGINE:", self.tts_combo)
        
        self.hass_url_edit = QLineEdit(self)
        self.hass_url_edit.setText(config.get("home_assistant_url", ""))
        form_general.addRow("HASS INSTANCE URL:", self.hass_url_edit)
        
        self.hass_token_edit = QLineEdit(self)
        self.hass_token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.hass_token_edit.setText(config.get("home_assistant_token", ""))
        form_general.addRow("HASS ACCESS TOKEN:", self.hass_token_edit)
        
        self.tabs.addTab(tab_general, "GENERAL")
        
        # --- TAB 2: AUDIO SETTINGS ---
        tab_audio = QWidget()
        form_audio = QFormLayout(tab_audio)
        form_audio.setContentsMargins(15, 15, 15, 15)
        form_audio.setSpacing(12)
        
        # Selected microphone dropdown
        self.mic_combo = QComboBox(self)
        try:
            devices = sd.query_devices()
            hostapis = sd.query_hostapis()
            input_devices = []
            for idx, dev in enumerate(devices):
                if dev.get("max_input_channels", 0) > 0:
                    backend_name = hostapis[dev.get("hostapi")]["name"]
                    input_devices.append((idx, dev.get("name"), backend_name))
            
            for idx, name, backend in input_devices:
                self.mic_combo.addItem(f"[{idx}] {name} ({backend})", {"name": name, "backend": backend})
                
            saved_name = config.get("mic_device_name")
            saved_backend = config.get("mic_device_backend")
            
            if saved_name:
                for i in range(self.mic_combo.count()):
                    data = self.mic_combo.itemData(i)
                    if data and data.get("name") == saved_name and data.get("backend") == saved_backend:
                        self.mic_combo.setCurrentIndex(i)
                        break
        except Exception as e:
            logger.error(f"Failed to query audio input devices: {e}")
            self.mic_combo.addItem("Default Microphone", None)
            
        form_audio.addRow("MICROPHONE:", self.mic_combo)
        
        # Microphones Profile Presets dropdown
        self.preset_combo = QComboBox(self)
        self.preset_combo.addItems(["Custom Profile", "Laptop Microphone", "Headset Microphone", "External USB Microphone", "Noisy Room", "Quiet Room"])
        self.preset_combo.setCurrentText("Custom Profile")
        self.preset_combo.currentTextChanged.connect(self.apply_preset)
        form_audio.addRow("MICROPHONE PRESET:", self.preset_combo)
        
        # Launch calibration wizard button
        self.wizard_btn = QPushButton("LAUNCH VOICE CALIBRATION WIZARD", self)
        self.wizard_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 255, 255, 30);
                border: 1px solid #00ffff;
                color: #00ffff;
                font-weight: bold;
                padding: 10px;
                margin-top: 5px;
                margin-bottom: 5px;
            }
            QPushButton:hover {
                background-color: #00ffff;
                color: #000000;
            }
        """)
        self.wizard_btn.clicked.connect(self.launch_wizard)
        form_audio.addRow(self.wizard_btn)
        
        # Whisper model size dropdown (English-only)
        self.model_combo = QComboBox(self)
        self.model_combo.addItems(["tiny.en", "base.en", "small.en", "medium.en"])
        self.model_combo.setCurrentText(config.get("whisper_model", "small.en"))
        form_audio.addRow("WHISPER MODEL:", self.model_combo)
        
        # Wake word enabled: Checkbox
        self.wake_word_cb = QCheckBox("Enable Wake Word Detection", self)
        self.wake_word_cb.setChecked(config.get("wake_word_enabled", "true").lower() == "true")
        form_audio.addRow("WAKE WORD:", self.wake_word_cb)
        
        # Clap wake enabled: Checkbox
        self.clap_wake_cb = QCheckBox("Enable Double Clap Activation", self)
        self.clap_wake_cb.setChecked(config.get("clap_wake_enabled", "false").lower() == "true")
        form_audio.addRow("CLAP WAKE:", self.clap_wake_cb)
        
        # Safe Mode Enabled Checkbox
        self.safe_mode_cb = QCheckBox("Enable Safe Mode (Confirm every command)", self)
        self.safe_mode_cb.setChecked(config.get("safe_mode_enabled", "false").lower() == "true")
        form_audio.addRow("SAFE MODE:", self.safe_mode_cb)
        
        # Auto Learning Enabled Checkbox
        self.auto_learn_cb = QCheckBox("Enable Automatic Voice Learning", self)
        self.auto_learn_cb.setChecked(config.get("enable_auto_voice_learning", "true").lower() == "true")
        form_audio.addRow("AUTO LEARNING:", self.auto_learn_cb)
        
        # Wake sensitivity slider (1 to 100) -> 0.002 to 0.200
        self.wake_sens_slider = QSlider(Qt.Orientation.Horizontal, self)
        self.wake_sens_slider.setRange(1, 100)
        wake_sens_val = float(config.get("wake_sensitivity", "0.05"))
        self.wake_sens_slider.setValue(int(wake_sens_val * 500))
        self.wake_sens_label = QLabel(f"{wake_sens_val:.3f}", self)
        self.wake_sens_label.setStyleSheet("color: #00ffff; font-weight: bold; min-width: 50px;")
        self.wake_sens_slider.valueChanged.connect(self.update_wake_sens_label)
        
        wake_layout = QHBoxLayout()
        wake_layout.addWidget(self.wake_sens_slider)
        wake_layout.addWidget(self.wake_sens_label)
        form_audio.addRow("WAKE SENSITIVITY:", wake_layout)
        
        # Command sensitivity slider (Noise gate sensitivity VAD) (1 to 100) -> 0.001 to 0.100
        self.cmd_sens_slider = QSlider(Qt.Orientation.Horizontal, self)
        self.cmd_sens_slider.setRange(1, 100)
        cmd_sens_val = float(config.get("command_sensitivity", "0.015"))
        self.cmd_sens_slider.setValue(int(cmd_sens_val * 1000))
        self.cmd_sens_label = QLabel(f"{cmd_sens_val:.3f}", self)
        self.cmd_sens_label.setStyleSheet("color: #00ffff; font-weight: bold; min-width: 50px;")
        self.cmd_sens_slider.valueChanged.connect(self.update_cmd_sens_label)
        
        cmd_layout = QHBoxLayout()
        cmd_layout.addWidget(self.cmd_sens_slider)
        cmd_layout.addWidget(self.cmd_sens_label)
        form_audio.addRow("NOISE GATE (VAD):", cmd_layout)
        
        # Input Gain Boost Slider (0 to 20 dB)
        self.gain_slider = QSlider(Qt.Orientation.Horizontal, self)
        self.gain_slider.setRange(0, 20)
        gain_val = int(config.get("input_gain_boost_db", "0"))
        self.gain_slider.setValue(gain_val)
        self.gain_label = QLabel(f"{gain_val} dB", self)
        self.gain_label.setStyleSheet("color: #00ffff; font-weight: bold; min-width: 50px;")
        self.gain_slider.valueChanged.connect(self.update_gain_label)
        
        gain_layout = QHBoxLayout()
        gain_layout.addWidget(self.gain_slider)
        gain_layout.addWidget(self.gain_label)
        form_audio.addRow("INPUT GAIN BOOST:", gain_layout)
        
        # Command timeout seconds (5 to 30)
        self.cmd_timeout_slider = QSlider(Qt.Orientation.Horizontal, self)
        self.cmd_timeout_slider.setRange(5, 30)
        cmd_timeout_val = int(config.get("command_timeout_seconds", "12"))
        self.cmd_timeout_slider.setValue(cmd_timeout_val)
        self.cmd_timeout_label = QLabel(f"{cmd_timeout_val}s", self)
        self.cmd_timeout_label.setStyleSheet("color: #00ffff; font-weight: bold; min-width: 50px;")
        self.cmd_timeout_slider.valueChanged.connect(self.update_cmd_timeout_label)
        
        timeout_layout = QHBoxLayout()
        timeout_layout.addWidget(self.cmd_timeout_slider)
        timeout_layout.addWidget(self.cmd_timeout_label)
        form_audio.addRow("CMD TIMEOUT:", timeout_layout)
        
        # Silence timeout milliseconds (500 to 3000)
        self.silence_timeout_slider = QSlider(Qt.Orientation.Horizontal, self)
        self.silence_timeout_slider.setRange(500, 3000)
        self.silence_timeout_slider.setSingleStep(100)
        silence_timeout_val = int(config.get("silence_timeout_ms", "1500"))
        self.silence_timeout_slider.setValue(silence_timeout_val)
        self.silence_timeout_label = QLabel(f"{silence_timeout_val}ms", self)
        self.silence_timeout_label.setStyleSheet("color: #00ffff; font-weight: bold; min-width: 50px;")
        self.silence_timeout_slider.valueChanged.connect(self.update_silence_timeout_label)
        
        silence_layout = QHBoxLayout()
        silence_layout.addWidget(self.silence_timeout_slider)
        silence_layout.addWidget(self.silence_timeout_label)
        form_audio.addRow("SILENCE TIMEOUT:", silence_layout)
        
        # TTS microphone cooldown milliseconds (200 to 2000)
        self.tts_cooldown_slider = QSlider(Qt.Orientation.Horizontal, self)
        self.tts_cooldown_slider.setRange(200, 2000)
        self.tts_cooldown_slider.setSingleStep(50)
        tts_cooldown_val = int(config.get("tts_mic_cooldown_ms", "800"))
        self.tts_cooldown_slider.setValue(tts_cooldown_val)
        self.tts_cooldown_label = QLabel(f"{tts_cooldown_val}ms", self)
        self.tts_cooldown_label.setStyleSheet("color: #00ffff; font-weight: bold; min-width: 50px;")
        self.tts_cooldown_slider.valueChanged.connect(self.update_tts_cooldown_label)
        
        cooldown_layout = QHBoxLayout()
        cooldown_layout.addWidget(self.tts_cooldown_slider)
        cooldown_layout.addWidget(self.tts_cooldown_label)
        form_audio.addRow("TTS MIC COOLDOWN:", cooldown_layout)
        
        # Diagnostics group
        diag_group = QGroupBox("DIAGNOSTICS & CALIBRATION", tab_audio)
        diag_group.setStyleSheet("""
            QGroupBox {
                border: 1px solid #00bfff;
                border-radius: 6px;
                margin-top: 15px;
                padding-top: 15px;
                font-weight: bold;
                color: #00ffff;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px 0 3px;
            }
        """)
        diag_layout = QGridLayout(diag_group)
        diag_layout.setSpacing(10)
        
        self.test_mic_btn = QPushButton("TEST MICROPHONE", self)
        self.test_mic_btn.clicked.connect(self.test_microphone)
        diag_layout.addWidget(self.test_mic_btn, 0, 0)
        
        self.recal_btn = QPushButton("RECALIBRATE AMBIENT", self)
        self.recal_btn.clicked.connect(self.recalibrate_ambient)
        diag_layout.addWidget(self.recal_btn, 0, 1)
        
        self.test_wake_btn = QPushButton("TEST WAKE WORD", self)
        self.test_wake_btn.clicked.connect(self.test_wake_word)
        diag_layout.addWidget(self.test_wake_btn, 1, 0)
        
        self.test_tts_btn = QPushButton("TEST TTS", self)
        self.test_tts_btn.clicked.connect(self.test_tts)
        diag_layout.addWidget(self.test_tts_btn, 1, 1)
        
        self.test_cmd_btn = QPushButton("RECORD TEST COMMAND", self)
        self.test_cmd_btn.clicked.connect(self.record_test_command)
        diag_layout.addWidget(self.test_cmd_btn, 2, 0, 1, 2)
        
        self.export_btn = QPushButton("EXPORT VOICE PROFILE", self)
        self.export_btn.clicked.connect(self.export_profile)
        diag_layout.addWidget(self.export_btn, 3, 0)
        
        self.import_btn = QPushButton("IMPORT VOICE PROFILE", self)
        self.import_btn.clicked.connect(self.import_profile)
        diag_layout.addWidget(self.import_btn, 3, 1)
        
        form_audio.addRow(diag_group)
        
        # Edit Personal Corrections group
        alias_group = QGroupBox("EDIT PERSONAL VOICE ALIASES", tab_audio)
        alias_group.setStyleSheet("""
            QGroupBox {
                border: 1px solid #00bfff;
                border-radius: 6px;
                margin-top: 15px;
                padding-top: 15px;
                font-weight: bold;
                color: #00ffff;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px 0 3px;
            }
        """)
        alias_layout = QVBoxLayout(alias_group)
        
        h_layout = QHBoxLayout()
        self.cmd_select_combo = QComboBox(self)
        self.cmd_select_combo.addItems([
            "open chrome", "open notepad", "open vs code", "take screenshot", 
            "increase volume", "decrease volume", "mute volume", "shutdown jarvis"
        ])
        self.cmd_select_combo.currentTextChanged.connect(self.load_aliases_for_selected)
        h_layout.addWidget(self.cmd_select_combo)
        
        self.delete_alias_btn = QPushButton("DELETE SELECTED ALIAS", self)
        self.delete_alias_btn.clicked.connect(self.delete_selected_alias)
        h_layout.addWidget(self.delete_alias_btn)
        alias_layout.addLayout(h_layout)
        
        self.alias_list = QListWidget(self)
        alias_layout.addWidget(self.alias_list)
        
        form_audio.addRow(alias_group)
        self.tabs.addTab(tab_audio, "AUDIO / VOICE")
        
        # --- TAB 3: VOICE PROVIDERS ---
        tab_providers = QWidget()
        form_providers = QFormLayout(tab_providers)
        form_providers.setContentsMargins(15, 15, 15, 15)
        form_providers.setSpacing(10)
        
        # STT Group
        stt_group = QGroupBox("SPEECH-TO-TEXT PROVIDERS")
        stt_group.setStyleSheet("QGroupBox { border: 1px solid #00bfff; border-radius: 6px; margin-top: 10px; padding: 10px; font-weight: bold; color: #00ffff; }")
        stt_layout = QFormLayout(stt_group)
        
        self.stt_provider_combo = QComboBox(self)
        self.stt_provider_combo.addItems(["groq_stt", "local_faster_whisper", "deepgram", "openai_whisper", "openai_stt", "gemini_stt"])
        self.stt_provider_combo.setCurrentText(config.get("stt_provider", "groq_stt"))
        stt_layout.addRow("STT PROVIDER:", self.stt_provider_combo)
        
        self.stt_whisper_model_combo = QComboBox(self)
        self.stt_whisper_model_combo.addItems(["tiny.en", "base.en", "small.en", "medium.en"])
        self.stt_whisper_model_combo.setCurrentText(config.get("whisper_model", "small.en"))
        stt_layout.addRow("WHISPER MODEL:", self.stt_whisper_model_combo)
        
        self.stt_whisper_device_combo = QComboBox(self)
        self.stt_whisper_device_combo.addItems(["auto", "cpu", "cuda"])
        self.stt_whisper_device_combo.setCurrentText(config.get("whisper_device", "auto"))
        stt_layout.addRow("WHISPER DEVICE:", self.stt_whisper_device_combo)
        
        self.stt_whisper_compute_combo = QComboBox(self)
        self.stt_whisper_compute_combo.addItems(["auto", "int8", "float16", "float32"])
        self.stt_whisper_compute_combo.setCurrentText(config.get("whisper_compute_type", "auto"))
        stt_layout.addRow("WHISPER COMPUTE TYPE:", self.stt_whisper_compute_combo)
        
        self.stt_deepgram_key_edit = QLineEdit(self)
        self.stt_deepgram_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.stt_deepgram_key_edit.setText(config.get("deepgram_api_key", ""))
        stt_layout.addRow("DEEPGRAM API KEY:", self.stt_deepgram_key_edit)
        
        self.stt_openai_key_edit = QLineEdit(self)
        self.stt_openai_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.stt_openai_key_edit.setText(config.get("openai_api_key", ""))
        stt_layout.addRow("OPENAI API KEY:", self.stt_openai_key_edit)
        
        self.test_stt_btn = QPushButton("TEST SELECTED STT PROVIDER", self)
        self.test_stt_btn.clicked.connect(self.test_stt_provider)
        stt_layout.addRow(self.test_stt_btn)
        
        form_providers.addRow(stt_group)
        
        # TTS Group
        tts_group = QGroupBox("TEXT-TO-SPEECH PROVIDERS")
        tts_group.setStyleSheet("QGroupBox { border: 1px solid #00bfff; border-radius: 6px; margin-top: 10px; padding: 10px; font-weight: bold; color: #00ffff; }")
        tts_layout = QFormLayout(tts_group)
        
        self.tts_provider_combo = QComboBox(self)
        self.tts_provider_combo.addItems(["windows_sapi", "piper", "kokoro", "openai_tts", "cartesia", "gemini_tts"])
        self.tts_provider_combo.setCurrentText(config.get("tts_provider", "gemini_tts"))
        self.tts_provider_combo.currentTextChanged.connect(self.update_voice_dropdown_options)
        tts_layout.addRow("TTS PROVIDER:", self.tts_provider_combo)
        
        self.tts_voice_combo = QComboBox(self)
        tts_layout.addRow("VOICE:", self.tts_voice_combo)
        
        self.tts_speed_slider = QSlider(Qt.Orientation.Horizontal, self)
        self.tts_speed_slider.setRange(5, 20)
        self.tts_speed_slider.setValue(int(float(config.get("tts_speed", "1.0")) * 10))
        self.tts_speed_lbl = QLabel(f"{float(config.get('tts_speed', '1.0')):.1f}x", self)
        self.tts_speed_slider.valueChanged.connect(lambda v: self.tts_speed_lbl.setText(f"{v/10.0:.1f}x"))
        speed_h_layout = QHBoxLayout()
        speed_h_layout.addWidget(self.tts_speed_slider)
        speed_h_layout.addWidget(self.tts_speed_lbl)
        tts_layout.addRow("SPEED:", speed_h_layout)
        
        self.tts_cartesia_key_edit = QLineEdit(self)
        self.tts_cartesia_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.tts_cartesia_key_edit.setText(config.get("cartesia_api_key", ""))
        tts_layout.addRow("CARTESIA API KEY:", self.tts_cartesia_key_edit)
        
        self.test_tts_provider_btn = QPushButton("TEST SELECTED TTS PROVIDER", self)
        self.test_tts_provider_btn.clicked.connect(self.test_tts_provider)
        tts_layout.addRow(self.test_tts_provider_btn)
        
        form_providers.addRow(tts_group)
        
        # Health & Status Group
        health_group = QGroupBox("PROVIDER HEALTH STATUS")
        health_group.setStyleSheet("QGroupBox { border: 1px solid #00ff7f; border-radius: 6px; margin-top: 10px; padding: 10px; font-weight: bold; color: #00ff7f; }")
        health_layout = QVBoxLayout(health_group)
        
        self.health_status_lbl = QLabel("Checking status...", self)
        self.health_status_lbl.setStyleSheet("color: #ffffff; font-family: Consolas; font-size: 10px;")
        health_layout.addWidget(self.health_status_lbl)
        
        self.refresh_health_btn = QPushButton("REFRESH HEALTH STATUS", self)
        self.refresh_health_btn.clicked.connect(self.refresh_provider_health)
        health_layout.addWidget(self.refresh_health_btn)
        
        form_providers.addRow(health_group)
        
        self.tabs.addTab(tab_providers, "VOICE PROVIDERS")
        # --- TAB 4: AI / API CONFIG ---
        tab_ai_api = QWidget()
        form_ai_api = QFormLayout(tab_ai_api)
        form_ai_api.setContentsMargins(15, 15, 15, 15)
        form_ai_api.setSpacing(12)
        self.stt_mode_combo = QComboBox(self)
        self.stt_mode_combo.addItems(["offline_only", "offline_first_cloud_fallback", "cloud_first"])
        self.stt_mode_combo.setCurrentText(config.get("stt_mode", "offline_first_cloud_fallback"))
        form_ai_api.addRow("STT MODE:", self.stt_mode_combo)
        self.cloud_intent_cb = QCheckBox("Enable Optional Cloud Intent normalizer", self)
        self.cloud_intent_cb.setChecked(config.get("enable_cloud_intent", "false").lower() == "true")
        form_ai_api.addRow("CLOUD INTENT:", self.cloud_intent_cb)
        self.intent_prov_combo = QComboBox(self)
        self.intent_prov_combo.addItems(["none", "groq", "openai"])
        self.intent_prov_combo.setCurrentText(config.get("intent_provider", "none"))
        form_ai_api.addRow("INTENT PROVIDER:", self.intent_prov_combo)
        self.ai_api_gemini_edit = QLineEdit(self)
        self.ai_api_gemini_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.ai_api_gemini_edit.setText(config.get("gemini_api_key", ""))
        form_ai_api.addRow("GEMINI API KEY:", self.ai_api_gemini_edit)
        self.ai_api_openai_edit = QLineEdit(self)
        self.ai_api_openai_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.ai_api_openai_edit.setText(config.get("openai_api_key", ""))
        form_ai_api.addRow("OPENAI API KEY:", self.ai_api_openai_edit)

        # --- API status & Test Buttons ---
        from dotenv import load_dotenv
        import os
        load_dotenv()
        gemini_val = os.getenv("GEMINI_API_KEY") or config.get("gemini_api_key", "")
        openai_val = os.getenv("OPENAI_API_KEY") or config.get("openai_api_key", "")
        
        def mask_key(k):
            if not k: return "Missing"
            if len(k) <= 8: return "Ready (Masked)"
            return f"{k[:4]}...{k[-4:]}"
            
        self.gemini_status_lbl = QLabel(f'Gemini API key status: ' + ('Ready' if gemini_val else 'Missing'), self)
        self.gemini_status_lbl.setStyleSheet("color: #00ff7f; font-weight: bold;")
        form_ai_api.addRow(self.gemini_status_lbl)
        
        self.openai_status_lbl = QLabel(f'OpenAI API key status: ' + ('Ready' if openai_val else 'Missing'), self)
        self.openai_status_lbl.setStyleSheet("color: #00ff7f; font-weight: bold;")
        form_ai_api.addRow(self.openai_status_lbl)
        
        # Test Gemini Intent Button
        self.test_gemini_intent_btn = QPushButton("TEST GEMINI INTENT", self)
        self.test_gemini_intent_btn.clicked.connect(self.test_gemini_intent_clicked)
        form_ai_api.addRow(self.test_gemini_intent_btn)
        
        # Test OpenAI STT Button
        self.test_openai_stt_btn = QPushButton("TEST OPENAI STT", self)
        self.test_openai_stt_btn.clicked.connect(self.test_openai_stt_clicked)
        form_ai_api.addRow(self.test_openai_stt_btn)

        # Test Gemini STT Button
        self.test_gemini_stt_btn = QPushButton("TEST GEMINI STT", self)
        self.test_gemini_stt_btn.clicked.connect(self.test_gemini_stt_clicked)
        form_ai_api.addRow(self.test_gemini_stt_btn)

        # Test Gemini TTS Button
        self.test_gemini_tts_btn = QPushButton("TEST GEMINI TTS", self)
        self.test_gemini_tts_btn.clicked.connect(self.test_gemini_tts_clicked)
        form_ai_api.addRow(self.test_gemini_tts_btn)

        # Test OpenAI TTS Button
        self.test_openai_tts_btn = QPushButton("TEST OPENAI TTS", self)
        self.test_openai_tts_btn.clicked.connect(self.test_openai_tts_clicked)
        form_ai_api.addRow(self.test_openai_tts_btn)
        
        self.tabs.addTab(tab_ai_api, "AI / API")

        # --- TAB: PHONE BRIDGE ---
        tab_phone = QWidget()
        form_phone = QFormLayout(tab_phone)
        form_phone.setContentsMargins(15, 15, 15, 15)
        form_phone.setSpacing(12)
        
        self.phone_ip_edit = QLineEdit(self)
        self.phone_ip_edit.setText(config.get("phone_ip", ""))
        self.phone_ip_edit.setPlaceholderText("e.g. 192.168.1.15")
        form_phone.addRow("PHONE IP:", self.phone_ip_edit)
        
        # Generate a random token on first setup if not already in config
        current_token = config.get("phone_call_token", "")
        if not current_token:
            import secrets
            current_token = secrets.token_hex(16)
            config.set("phone_call_token", current_token)
            
        self.phone_token_edit = QLineEdit(self)
        self.phone_token_edit.setText(current_token)
        self.phone_token_edit.setPlaceholderText("Authentication Secret Token")
        form_phone.addRow("BRIDGE TOKEN:", self.phone_token_edit)
        
        self.tabs.addTab(tab_phone, "PHONE BRIDGE")

        # --- TAB 5: APPS & ACTIONS ---
        tab_apps = QWidget()
        vbox_apps = QVBoxLayout(tab_apps)
        vbox_apps.setContentsMargins(15, 15, 15, 15)
        vbox_apps.setSpacing(10)
        self.refresh_index_btn = QPushButton("REFRESH WINDOWS APP INDEX", self)
        self.refresh_index_btn.clicked.connect(self.refresh_app_index_clicked)
        vbox_apps.addWidget(self.refresh_index_btn)
        vbox_apps.addWidget(QLabel("MANUAL APP VOICE ALIASES:", self))
        self.aliases_list_widget = QListWidget(self)
        self.load_app_aliases_to_ui()
        vbox_apps.addWidget(self.aliases_list_widget)
        h_add = QHBoxLayout()
        self.alias_input = QLineEdit(self)
        self.alias_input.setPlaceholderText("Voice Alias (e.g. edge)")
        self.app_name_input = QLineEdit(self)
        self.app_name_input.setPlaceholderText("Canonical App Display Name (e.g. Microsoft Edge)")
        h_add.addWidget(self.alias_input)
        h_add.addWidget(self.app_name_input)
        self.add_alias_pair_btn = QPushButton("ADD ALIAS", self)
        self.add_alias_pair_btn.clicked.connect(self.add_alias_pair)
        h_add.addWidget(self.add_alias_pair_btn)
        vbox_apps.addLayout(h_add)
        self.remove_alias_pair_btn = QPushButton("REMOVE SELECTED ALIAS", self)
        self.remove_alias_pair_btn.clicked.connect(self.remove_selected_alias_pair)
        vbox_apps.addWidget(self.remove_alias_pair_btn)
        self.tabs.addTab(tab_apps, "APPS & ACTIONS")
        
        # Populate voice options initially
        self.update_voice_dropdown_options(self.tts_provider_combo.currentText())
        self.refresh_provider_health()
        
        main_layout.addWidget(self.tabs)
        
        # Save / Cancel Buttons
        btns = QHBoxLayout()
        btns.addStretch()
        
        cancel_btn = QPushButton("CANCEL", self)
        cancel_btn.clicked.connect(self.close)
        
        save_btn = QPushButton("SAVE CONFIG", self)
        save_btn.clicked.connect(self.save_settings)
        
        btns.addWidget(cancel_btn)
        btns.addWidget(save_btn)
        main_layout.addLayout(btns)
        
        # Initial load of aliases list
        self.load_aliases_for_selected(self.cmd_select_combo.currentText())

    def launch_wizard(self):
        self.wizard_window = CalibrationWizardWindow(parent=self)
        self.wizard_window.show()

    def load_aliases_for_selected(self, command_name):
        self.alias_list.clear()
        try:
            from core.engine import get_personal_corrections
            pcs = get_personal_corrections()
            aliases = pcs.get(command_name, [])
            for alias in aliases:
                self.alias_list.addItem(alias)
        except Exception as e:
            logger.error(f"Failed to load aliases for settings: {e}")

    def delete_selected_alias(self):
        selected_item = self.alias_list.currentItem()
        if not selected_item:
            return
        alias_text = selected_item.text()
        command_name = self.cmd_select_combo.currentText()
        
        try:
            from core.engine import get_personal_corrections
            pcs = get_personal_corrections()
            if command_name in pcs and alias_text in pcs[command_name]:
                pcs[command_name].remove(alias_text)
                config.set("personal_corrections", json.dumps(pcs))
                bus.console_log.emit("INFO", f"Deleted personal voice alias '{alias_text}' from '{command_name}'")
                self.load_aliases_for_selected(command_name)
        except Exception as e:
            logger.error(f"Failed to delete alias: {e}")

    def apply_preset(self, name):
        presets = {
            "Laptop Microphone": {
                "input_gain_boost_db": 10,
                "wake_sensitivity": 0.03,
                "command_sensitivity": 0.015,
                "silence_timeout_ms": 1500
            },
            "Headset Microphone": {
                "input_gain_boost_db": 4,
                "wake_sensitivity": 0.04,
                "command_sensitivity": 0.02,
                "silence_timeout_ms": 1200
            },
            "External USB Microphone": {
                "input_gain_boost_db": 0,
                "wake_sensitivity": 0.05,
                "command_sensitivity": 0.015,
                "silence_timeout_ms": 1500
            },
            "Noisy Room": {
                "input_gain_boost_db": 2,
                "wake_sensitivity": 0.08,
                "command_sensitivity": 0.03,
                "silence_timeout_ms": 1000
            },
            "Quiet Room": {
                "input_gain_boost_db": 6,
                "wake_sensitivity": 0.03,
                "command_sensitivity": 0.01,
                "silence_timeout_ms": 1800
            }
        }
        if name in presets:
            p = presets[name]
            self.gain_slider.setValue(p["input_gain_boost_db"])
            self.wake_sens_slider.setValue(int(p["wake_sensitivity"] * 500))
            self.cmd_sens_slider.setValue(int(p["command_sensitivity"] * 1000))
            self.silence_timeout_slider.setValue(p["silence_timeout_ms"])
            bus.console_log.emit("INFO", f"Preset '{name}' applied successfully. Save settings to apply.")

    def export_profile(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export Voice Profile", "jarvis_voice_profile.json", "JSON Files (*.json)")
        if path:
            try:
                try:
                    val = config.get("personal_corrections")
                    pcs = json.loads(val) if val else {}
                except Exception:
                    pcs = {}
                
                profile = {
                    "salutation": self.salutation_edit.text(),
                    "tts_provider": self.tts_combo.currentText(),
                    "wake_word_enabled": "true" if self.wake_word_cb.isChecked() else "false",
                    "clap_wake_enabled": "true" if self.clap_wake_cb.isChecked() else "false",
                    "safe_mode_enabled": "true" if self.safe_mode_cb.isChecked() else "false",
                    "enable_auto_voice_learning": "true" if self.auto_learn_cb.isChecked() else "false",
                    "wake_sensitivity": str(self.wake_sens_slider.value() / 500.0),
                    "command_sensitivity": str(self.cmd_sens_slider.value() / 1000.0),
                    "input_gain_boost_db": str(self.gain_slider.value()),
                    "command_timeout_seconds": str(self.cmd_timeout_slider.value()),
                    "silence_timeout_ms": str(self.silence_timeout_slider.value()),
                    "tts_mic_cooldown_ms": str(self.tts_cooldown_slider.value()),
                    "personal_corrections": pcs
                }
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(profile, f, indent=4)
                bus.console_log.emit("INFO", f"Voice profile exported successfully to {path}")
            except Exception as e:
                logger.error(f"Failed to export voice profile: {e}")
                bus.console_log.emit("ERROR", f"Export failed: {e}")

    def import_profile(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import Voice Profile", "", "JSON Files (*.json)")
        if path:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    profile = json.load(f)
                
                if "salutation" in profile: self.salutation_edit.setText(profile["salutation"])
                if "tts_provider" in profile: self.tts_combo.setCurrentText(profile["tts_provider"])
                if "wake_word_enabled" in profile: self.wake_word_cb.setChecked(profile["wake_word_enabled"] == "true")
                if "clap_wake_enabled" in profile: self.clap_wake_cb.setChecked(profile["clap_wake_enabled"] == "true")
                if "safe_mode_enabled" in profile: self.safe_mode_cb.setChecked(profile["safe_mode_enabled"] == "true")
                if "enable_auto_voice_learning" in profile: self.auto_learn_cb.setChecked(profile["enable_auto_voice_learning"] == "true")
                
                if "wake_sensitivity" in profile: self.wake_sens_slider.setValue(int(float(profile["wake_sensitivity"]) * 500))
                if "command_sensitivity" in profile: self.cmd_sens_slider.setValue(int(float(profile["command_sensitivity"]) * 1000))
                if "input_gain_boost_db" in profile: self.gain_slider.setValue(int(profile["input_gain_boost_db"]))
                if "command_timeout_seconds" in profile: self.cmd_timeout_slider.setValue(int(profile["command_timeout_seconds"]))
                if "silence_timeout_ms" in profile: self.silence_timeout_slider.setValue(int(profile["silence_timeout_ms"]))
                if "tts_mic_cooldown_ms" in profile: self.tts_cooldown_slider.setValue(int(profile["tts_mic_cooldown_ms"]))
                
                if "personal_corrections" in profile:
                    config.set("personal_corrections", json.dumps(profile["personal_corrections"]))
                    self.load_aliases_for_selected(self.cmd_select_combo.currentText())
                    
                bus.console_log.emit("INFO", f"Voice profile imported successfully from {path}")
            except Exception as e:
                logger.error(f"Failed to import voice profile: {e}")
                bus.console_log.emit("ERROR", f"Import failed: {e}")

    def update_wake_sens_label(self, value):
        self.wake_sens_label.setText(f"{value / 500.0:.3f}")

    def update_cmd_sens_label(self, value):
        self.cmd_sens_label.setText(f"{value / 1000.0:.3f}")

    def update_gain_label(self, value):
        self.gain_label.setText(f"{value} dB")

    def update_cmd_timeout_label(self, value):
        self.cmd_timeout_label.setText(f"{value}s")

    def update_silence_timeout_label(self, value):
        self.silence_timeout_label.setText(f"{value}ms")

    def update_tts_cooldown_label(self, value):
        self.tts_cooldown_label.setText(f"{value}ms")

    def test_microphone(self):
        self.test_mic_btn.setEnabled(False)
        self.test_mic_btn.setText("RECORDING...")
        
        def run_test():
            try:
                selected_mic = self.mic_combo.currentData()
                device_idx = None
                if selected_mic:
                    devices = sd.query_devices()
                    for idx, dev in enumerate(devices):
                        if dev.get("name") == selected_mic.get("name"):
                            device_idx = idx
                            break
                if device_idx is None:
                    device_idx = sd.default.device[0]
                    
                fs = 16000
                duration = 3.0
                bus.console_log.emit("INFO", "Microphone Test: Recording 3 seconds of audio...")
                recording = sd.rec(int(duration * fs), samplerate=fs, channels=1, dtype='float32', device=device_idx)
                sd.wait()
                
                self.test_mic_btn.setText("PLAYING...")
                bus.console_log.emit("INFO", "Microphone Test: Playing back audio...")
                sd.play(recording, fs)
                sd.wait()
                bus.console_log.emit("INFO", "Microphone Test complete.")
            except Exception as e:
                logger.error(f"Microphone test failed: {e}")
                bus.console_log.emit("ERROR", f"Mic test failed: {e}")
            finally:
                self.test_mic_btn.setEnabled(True)
                self.test_mic_btn.setText("TEST MICROPHONE")
                
        threading.Thread(target=run_test, daemon=True).start()

    def recalibrate_ambient(self):
        self.recal_btn.setEnabled(False)
        self.recal_btn.setText("CALIBRATING...")
        
        def run_recal():
            try:
                from services.audio_service import audio_service
                bus.console_log.emit("INFO", "Calibrating ambient noise floor...")
                audio_service._calibrate_ambient()
                bus.console_log.emit("INFO", f"Calibration complete. Ambient floor RMS: {audio_service.ambient_rms:.4f}")
            except Exception as e:
                logger.error(f"Calibration failed: {e}")
                bus.console_log.emit("ERROR", f"Calibration failed: {e}")
            finally:
                self.recal_btn.setEnabled(True)
                self.recal_btn.setText("RECALIBRATE AMBIENT")
                
        threading.Thread(target=run_recal, daemon=True).start()

    def test_wake_word(self):
        bus.console_log.emit("INFO", "Wake Word Test: Simulating wake phrase trigger...")
        bus.wake_detected.emit("test_button")

    def test_tts(self):
        from services.speech_service import speech
        bus.console_log.emit("INFO", "TTS Test: Speaking test prompt...")
        speech.speak("Testing text to speech engine. Hello Sir, I am functioning perfectly.")

    def record_test_command(self):
        self.test_cmd_btn.setEnabled(False)
        self.test_cmd_btn.setText("LISTENING (5s)...")
        
        def run_test():
            try:
                selected_mic = self.mic_combo.currentData()
                device_idx = None
                if selected_mic:
                    devices = sd.query_devices()
                    for idx, dev in enumerate(devices):
                        if dev.get("name") == selected_mic.get("name"):
                            device_idx = idx
                            break
                if device_idx is None:
                    device_idx = sd.default.device[0]
                
                device_info = sd.query_devices(device_idx)
                native_rate = int(device_info.get("default_samplerate", 16000))
                
                fs = native_rate
                duration = 5.0
                bus.console_log.emit("INFO", "PTT Test: Recording 5 seconds of command audio...")
                recording = sd.rec(int(duration * fs), samplerate=fs, channels=1, dtype='float32', device=device_idx)
                sd.wait()
                
                self.test_cmd_btn.setText("PROCESSING...")
                bus.console_log.emit("INFO", "PTT Test: Downsampling and normalising audio...")
                audio_data = recording.flatten()
                
                gain_db = float(config.get("input_gain_boost_db", "0"))
                if gain_db != 0:
                    gain_factor = 10 ** (gain_db / 20.0)
                    audio_data = audio_data * gain_factor
                
                if fs != 16000:
                    xp = np.linspace(0, 1, len(audio_data))
                    x = np.linspace(0, 1, int(duration * 16000))
                    audio_data = np.interp(x, xp, audio_data).astype(np.float32)
                
                peak_val = np.max(np.abs(audio_data))
                if peak_val > 0:
                    audio_data = audio_data / peak_val * 0.9
                
                from services.audio_service import audio_service
                if audio_service.model_loaded and audio_service.whisper_model:
                    initial_prompt = (
                        "This is a short voice command for a Windows desktop assistant named Jarvis. "
                        "The user may say commands such as: open Chrome, open Notepad, open VS Code, "
                        "close window, increase volume, decrease volume, mute volume, take screenshot, "
                        "search Google, open downloads, open documents, shutdown Jarvis, exit Jarvis, "
                        "lock computer, what time is it, turn on lights, turn off lights."
                    )
                    segments, info = audio_service.whisper_model.transcribe(
                        audio_data, beam_size=5, language="en",
                        temperature=0, condition_on_previous_text=False,
                        vad_filter=True, initial_prompt=initial_prompt
                    )
                    raw_text = " ".join([s.text for s in segments]).strip()
                else:
                    raw_text = "(STT model not loaded yet)"
                
                if raw_text:
                    from core.engine import CommandWorker, JarvisEngine
                    normalized = CommandWorker.normalize_command(raw_text)
                    
                    temp_engine = JarvisEngine()
                    corrected, confidence = temp_engine.correct_command(normalized)
                        
                    pct = int(confidence * 100)
                    
                    bus.console_log.emit("INFO", f"PTT Test Results:")
                    bus.console_log.emit("INFO", f"  Raw: '{raw_text}'")
                    bus.console_log.emit("INFO", f"  Normalized: '{normalized}'")
                    bus.console_log.emit("INFO", f"  Corrected: '{corrected}' (Confidence: {pct}%)")
                    
                    bus.command_diagnostics.emit({
                        "raw": raw_text,
                        "normalized": normalized,
                        "personal": "NONE",
                        "fuzzy": corrected,
                        "confidence": f"{pct}%",
                        "rms": "0.0000",
                        "peak": f"{peak_val:.4f}",
                        "duration": f"{duration:.1f}s",
                        "decision": "NONE (TEST MODE)"
                    })
                else:
                    bus.console_log.emit("WARN", "PTT Test: No speech transcribed.")
                    
            except Exception as e:
                logger.error(f"PTT command test failed: {e}")
                bus.console_log.emit("ERROR", f"PTT command test failed: {e}")
            finally:
                self.test_cmd_btn.setEnabled(True)
                self.test_cmd_btn.setText("RECORD TEST COMMAND")
                
        threading.Thread(target=run_test, daemon=True).start()

    def load_app_aliases_to_ui(self):
        self.aliases_list_widget.clear()
        try:
            import os
            import json
            alias_path = os.path.join("config", "app_aliases.json")
            if os.path.exists(alias_path):
                with open(alias_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for k, v in data.items():
                    self.aliases_list_widget.addItem(f"{k} -> {v}")
        except Exception as e:
            logger.error(f"Failed to load app_aliases: {e}")

    def add_alias_pair(self):
        alias_text = self.alias_input.text().strip().lower()
        app_text = self.app_name_input.text().strip()
        if alias_text and app_text:
            try:
                import os
                import json
                alias_path = os.path.join("config", "app_aliases.json")
                data = {}
                if os.path.exists(alias_path):
                    with open(alias_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                data[alias_text] = app_text
                os.makedirs("config", exist_ok=True)
                with open(alias_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4)
                self.load_app_aliases_to_ui()
                self.alias_input.clear()
                self.app_name_input.clear()
                bus.console_log.emit("INFO", f"Added app alias: '{alias_text}' -> '{app_text}'")
            except Exception as e:
                logger.error(f"Failed to add app alias: {e}")

    def remove_selected_alias_pair(self):
        item = self.aliases_list_widget.currentItem()
        if item:
            text = item.text()
            if " -> " in text:
                alias_key = text.split(" -> ")[0].strip()
                try:
                    import os
                    import json
                    alias_path = os.path.join("config", "app_aliases.json")
                    if os.path.exists(alias_path):
                        with open(alias_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        if alias_key in data:
                            del data[alias_key]
                            with open(alias_path, "w", encoding="utf-8") as f:
                                json.dump(data, f, indent=4)
                            self.load_app_aliases_to_ui()
                            bus.console_log.emit("INFO", f"Removed app alias for '{alias_key}'")
                except Exception as e:
                    logger.error(f"Failed to remove alias: {e}")

    def refresh_app_index_clicked(self):
        self.refresh_index_btn.setEnabled(False)
        self.refresh_index_btn.setText("DISCOVERING APPS...")
        def run_disc():
            try:
                from services.app_discovery_service import app_discovery_service
                apps = app_discovery_service.discover_all()
                bus.console_log.emit("INFO", f"Discovered {len(apps)} apps successfully.")
            except Exception as e:
                logger.error(f"Discovery error: {e}")
            finally:
                self.refresh_index_btn.setEnabled(True)
                self.refresh_index_btn.setText("REFRESH WINDOWS APP INDEX")
        import threading
        threading.Thread(target=run_disc, daemon=True).start()

    def test_gemini_intent_clicked(self):
        self.test_gemini_intent_btn.setEnabled(False)
        self.test_gemini_intent_btn.setText("TESTING GEMINI INTENT...")
        def run_test():
            try:
                from services.intent.gemini_intent_provider import GeminiIntentProvider
                provider = GeminiIntentProvider()
                res = provider.parse_intent("Jarvis open Microsoft Edge")
                bus.console_log.emit("INFO", f"Gemini Intent Test Result: action={res.action}, target={res.target}, confidence={res.confidence}")
            except Exception as e:
                bus.console_log.emit("ERROR", f"Gemini Intent Test failed: {e}")
            finally:
                self.test_gemini_intent_btn.setEnabled(True)
                self.test_gemini_intent_btn.setText("TEST GEMINI INTENT")
        import threading
        threading.Thread(target=run_test, daemon=True).start()

    def test_openai_stt_clicked(self):
        self.test_openai_stt_btn.setEnabled(False)
        self.test_openai_stt_btn.setText("RECORDING TEST OPENAI STT (3s)...")
        def run_test():
            try:
                import sounddevice as sd
                import numpy as np
                import io
                import soundfile as sf
                from services.stt.openai_stt_provider import OpenAISTTProvider
                
                device_idx = sd.default.device[0]
                fs = 16000
                duration = 3.0
                bus.console_log.emit("INFO", f"Recording test audio for OpenAI STT (3s)...")
                recording = sd.rec(int(duration * fs), samplerate=fs, channels=1, dtype="float32", device=device_idx)
                sd.wait()
                
                self.test_openai_stt_btn.setText("TRANSCRIBING VIA OPENAI STT...")
                audio_data = recording.flatten()
                wav_io = io.BytesIO()
                sf.write(wav_io, audio_data, fs, format="WAV", subtype="PCM_16")
                wav_bytes = wav_io.getvalue()
                
                provider = OpenAISTTProvider()
                res = provider.transcribe(wav_bytes)
                bus.console_log.emit("INFO", f"OpenAI STT Test Result: '{res.text}'")
            except Exception as e:
                bus.console_log.emit("ERROR", f"OpenAI STT Test failed: {e}")
            finally:
                self.test_openai_stt_btn.setEnabled(True)
                self.test_openai_stt_btn.setText("TEST OPENAI STT")
        import threading
        threading.Thread(target=run_test, daemon=True).start()

    def test_gemini_stt_clicked(self):
        self.test_gemini_stt_btn.setEnabled(False)
        self.test_gemini_stt_btn.setText("RECORDING TEST GEMINI STT (3s)...")
        def run_test():
            try:
                import sounddevice as sd
                import numpy as np
                import io
                import soundfile as sf
                from services.stt.gemini_stt_provider import GeminiSTTProvider
                
                device_idx = sd.default.device[0]
                fs = 16000
                duration = 3.0
                bus.console_log.emit("INFO", f"Recording test audio for Gemini STT (3s)...")
                recording = sd.rec(int(duration * fs), samplerate=fs, channels=1, dtype="float32", device=device_idx)
                sd.wait()
                
                self.test_gemini_stt_btn.setText("TRANSCRIBING VIA GEMINI STT...")
                audio_data = recording.flatten()
                wav_io = io.BytesIO()
                sf.write(wav_io, audio_data, fs, format="WAV", subtype="PCM_16")
                wav_bytes = wav_io.getvalue()
                
                provider = GeminiSTTProvider()
                res = provider.transcribe(wav_bytes)
                bus.console_log.emit("INFO", f"Gemini STT Test Result: '{res.text}'")
            except Exception as e:
                bus.console_log.emit("ERROR", f"Gemini STT Test failed: {e}")
            finally:
                self.test_gemini_stt_btn.setEnabled(True)
                self.test_gemini_stt_btn.setText("TEST GEMINI STT")
        import threading
        threading.Thread(target=run_test, daemon=True).start()

    def test_gemini_tts_clicked(self):
        self.test_gemini_tts_btn.setEnabled(False)
        self.test_gemini_tts_btn.setText("TESTING GEMINI TTS...")
        def run_test():
            try:
                from services.tts.gemini_tts_provider import GeminiTTSProvider
                provider = GeminiTTSProvider()
                bus.console_log.emit("INFO", "TTS Test: Speaking via Gemini TTS...")
                provider.speak("Gemini Cloud TTS system operational, Sir.")
                bus.console_log.emit("INFO", "TTS Test complete.")
            except Exception as e:
                bus.console_log.emit("ERROR", f"Gemini TTS Test failed: {e}")
            finally:
                self.test_gemini_tts_btn.setEnabled(True)
                self.test_gemini_tts_btn.setText("TEST GEMINI TTS")
        import threading
        threading.Thread(target=run_test, daemon=True).start()

    def test_openai_tts_clicked(self):
        self.test_openai_tts_btn.setEnabled(False)
        self.test_openai_tts_btn.setText("TESTING OPENAI TTS...")
        def run_test():
            try:
                from services.tts.openai_tts_provider import OpenAIWhisperTTSProvider
                provider = OpenAIWhisperTTSProvider()
                bus.console_log.emit("INFO", "TTS Test: Speaking via OpenAI TTS...")
                provider.speak("OpenAI Cloud TTS system operational, Sir.")
                bus.console_log.emit("INFO", "TTS Test complete.")
            except Exception as e:
                bus.console_log.emit("ERROR", f"OpenAI TTS Test failed: {e}")
            finally:
                self.test_openai_tts_btn.setEnabled(True)
                self.test_openai_tts_btn.setText("TEST OPENAI TTS")
        import threading
        threading.Thread(target=run_test, daemon=True).start()

    def save_settings(self):
        config.set("stt_mode", self.stt_mode_combo.currentText())
        config.set("enable_cloud_intent", "true" if self.cloud_intent_cb.isChecked() else "false")
        config.set("intent_provider", self.intent_prov_combo.currentText())
        if self.ai_api_gemini_edit.text().strip():
            config.set("gemini_api_key", self.ai_api_gemini_edit.text().strip())
        if self.ai_api_openai_edit.text().strip():
            config.set("openai_api_key", self.ai_api_openai_edit.text().strip())
        config.set("salutation", self.salutation_edit.text().strip())
        config.set("gemini_api_key", self.gemini_edit.text().strip())
        
        # Save provider configurations
        config.set("stt_provider", self.stt_provider_combo.currentText())
        config.set("whisper_model", self.stt_whisper_model_combo.currentText())
        config.set("whisper_device", self.stt_whisper_device_combo.currentText())
        config.set("whisper_compute_type", self.stt_whisper_compute_combo.currentText())
        config.set("deepgram_api_key", self.stt_deepgram_key_edit.text().strip())
        config.set("openai_api_key", self.stt_openai_key_edit.text().strip())
        
        config.set("tts_provider", self.tts_provider_combo.currentText())
        config.set("tts_voice_id", self.tts_voice_combo.currentText())
        config.set("tts_speed", str(self.tts_speed_slider.value() / 10.0))
        config.set("cartesia_api_key", self.tts_cartesia_key_edit.text().strip())
        
        # Sync old controls if they exist
        self.tts_combo.setCurrentText(self.tts_provider_combo.currentText())
        self.model_combo.setCurrentText(self.stt_whisper_model_combo.currentText())
        
        selected_mic = self.mic_combo.currentData()
        if selected_mic:
            config.set("mic_device_name", selected_mic.get("name"))
            config.set("mic_device_backend", selected_mic.get("backend"))
            # Extract index from currentText "[idx] ..."
            mic_text = self.mic_combo.currentText()
            if mic_text.startswith("["):
                idx = mic_text.split("]")[0].replace("[", "").strip()
                config.set("selected_microphone_index", idx)
        else:
            config.set("mic_device_name", "")
            config.set("mic_device_backend", "")
            config.set("selected_microphone_index", "0")
            
        config.set("input_gain_boost_db", str(self.gain_slider.value()))
        
        config.set("wake_word_enabled", "true" if self.wake_word_cb.isChecked() else "false")
        config.set("clap_wake_enabled", "true" if self.clap_wake_cb.isChecked() else "false")
        config.set("safe_mode_enabled", "true" if self.safe_mode_cb.isChecked() else "false")
        config.set("enable_auto_voice_learning", "true" if self.auto_learn_cb.isChecked() else "false")
        
        wake_sens = self.wake_sens_slider.value() / 500.0
        cmd_sens = self.cmd_sens_slider.value() / 1000.0
        cmd_timeout = self.cmd_timeout_slider.value()
        silence_timeout = self.silence_timeout_slider.value()
        tts_cooldown = self.tts_cooldown_slider.value()
        
        config.set("wake_sensitivity", str(wake_sens))
        config.set("command_sensitivity", str(cmd_sens))
        config.set("command_timeout_seconds", str(cmd_timeout))
        config.set("wake_timeout", str(cmd_timeout)) 
        config.set("silence_timeout_ms", str(silence_timeout))
        config.set("tts_mic_cooldown_ms", str(tts_cooldown))
        
        config.set("home_assistant_url", self.hass_url_edit.text().strip())
        config.set("home_assistant_token", self.hass_token_edit.text().strip())
        
        # Phone Bridge Settings
        config.set("phone_ip", self.phone_ip_edit.text().strip())
        config.set("phone_call_token", self.phone_token_edit.text().strip())
        
        logger.info("Configuration parameters saved to database.")
        
        from services.audio_service import audio_service
        audio_service.restart_stream()
        
        self.close()

    def update_voice_dropdown_options(self, provider_id):
        self.tts_voice_combo.clear()
        if provider_id == "windows_sapi":
            try:
                from services.tts.windows_sapi_provider import WindowsSapiProvider
                voices = WindowsSapiProvider().available_voices()
                self.tts_voice_combo.addItems(voices)
            except Exception:
                self.tts_voice_combo.addItem("Default SAPI Voice")
        elif provider_id == "piper":
            try:
                from services.tts.piper_provider import PiperProvider
                self.tts_voice_combo.addItems(PiperProvider().available_voices())
            except Exception:
                self.tts_voice_combo.addItem("Default Piper Voice")
        elif provider_id == "kokoro":
            try:
                from services.tts.kokoro_provider import KokoroProvider
                self.tts_voice_combo.addItems(KokoroProvider().available_voices())
            except Exception:
                self.tts_voice_combo.addItem("bm_daniel")
        elif provider_id == "openai_tts":
            self.tts_voice_combo.addItems(["alloy", "echo", "fable", "onyx", "nova", "shimmer"])
        elif provider_id == "cartesia":
            self.tts_voice_combo.addItems([
                "a0e99841-438c-4a64-b679-ae501e7d6091",
                "c8f7835e-28a3-4f0c-80d7-c1302ac62aae"
            ])
        elif provider_id == "gemini_tts":
            self.tts_voice_combo.addItems(["default", "Puck", "Charon", "Kore", "Fenrir", "Aoede"])
            
        saved_voice = config.get("tts_voice_id", "")
        idx = self.tts_voice_combo.findText(saved_voice)
        if idx >= 0:
            self.tts_voice_combo.setCurrentIndex(idx)

    def refresh_provider_health(self):
        try:
            from services.stt.provider_manager import stt_manager
            from services.tts.provider_manager import tts_manager
            stt_report = stt_manager.get_health_report(force=True)
            tts_report = tts_manager.get_health_report(force=True)
            
            lines = []
            lines.append("--- STT PROVIDERS ---")
            for pid, status in stt_report.items():
                name = pid.replace("_", " ").upper()
                lines.append(f"{name}: {status['status']}")
                
            lines.append("\n--- TTS PROVIDERS ---")
            for pid, status in tts_report.items():
                name = pid.replace("_", " ").upper()
                lines.append(f"{name}: {status['status']}")
            
            self.health_status_lbl.setText("\n".join(lines))
        except Exception as e:
            self.health_status_lbl.setText(f"Error checking health: {e}")

    def test_stt_provider(self):
        self.test_stt_btn.setEnabled(False)
        self.test_stt_btn.setText("RECORDING TEST STT (3s)...")
        
        stt_provider = self.stt_provider_combo.currentText()
        whisper_model = self.stt_whisper_model_combo.currentText()
        whisper_device = self.stt_whisper_device_combo.currentText()
        whisper_compute_type = self.stt_whisper_compute_combo.currentText()
        deepgram_key = self.stt_deepgram_key_edit.text().strip()
        openai_key = self.stt_openai_key_edit.text().strip()
        
        def run_test():
            try:
                # Save temp configs in db so the manager loads them for testing
                old_stt = config.get("stt_provider")
                old_model = config.get("whisper_model")
                old_device = config.get("whisper_device")
                old_compute = config.get("whisper_compute_type")
                old_dg_key = config.get("deepgram_api_key")
                old_oa_key = config.get("openai_api_key")
                
                config.set("stt_provider", stt_provider)
                config.set("whisper_model", whisper_model)
                config.set("whisper_device", whisper_device)
                config.set("whisper_compute_type", whisper_compute_type)
                config.set("deepgram_api_key", deepgram_key)
                config.set("openai_api_key", openai_key)
                
                device_idx = sd.default.device[0]
                fs = 16000
                duration = 3.0
                bus.console_log.emit("INFO", f"STT Test: Recording {duration}s using {stt_provider}...")
                recording = sd.rec(int(duration * fs), samplerate=fs, channels=1, dtype='float32', device=device_idx)
                sd.wait()
                
                self.test_stt_btn.setText("TRANSCRIBING...")
                audio_data = recording.flatten()
                
                import io
                import soundfile as sf
                wav_io = io.BytesIO()
                sf.write(wav_io, audio_data, fs, format='WAV', subtype='PCM_16')
                wav_bytes = wav_io.getvalue()
                
                from services.stt.provider_manager import stt_manager
                res = stt_manager.transcribe(wav_bytes)
                bus.console_log.emit("INFO", f"STT Test Result ({res.provider}): '{res.text}'")
                
                # Restore original configs
                config.set("stt_provider", old_stt)
                config.set("whisper_model", old_model)
                config.set("whisper_device", old_device)
                config.set("whisper_compute_type", old_compute)
                config.set("deepgram_api_key", old_dg_key)
                config.set("openai_api_key", old_oa_key)
            except Exception as e:
                logger.error(f"STT Test failed: {e}")
                bus.console_log.emit("ERROR", f"STT Test failed: {e}")
            finally:
                self.test_stt_btn.setEnabled(True)
                self.test_stt_btn.setText("TEST SELECTED STT PROVIDER")
                self.refresh_provider_health()
                
        threading.Thread(target=run_test, daemon=True).start()

    def test_tts_provider(self):
        self.test_tts_provider_btn.setEnabled(False)
        self.test_tts_provider_btn.setText("TESTING TTS...")
        
        tts_provider = self.tts_provider_combo.currentText()
        voice_id = self.tts_voice_combo.currentText()
        speed = self.tts_speed_slider.value() / 10.0
        cartesia_key = self.tts_cartesia_key_edit.text().strip()
        openai_key = self.stt_openai_key_edit.text().strip()
        
        def run_test():
            try:
                old_tts = config.get("tts_provider")
                old_voice = config.get("tts_voice_id")
                old_speed = config.get("tts_speed")
                old_cartesia = config.get("cartesia_api_key")
                old_openai = config.get("openai_api_key")
                
                config.set("tts_provider", tts_provider)
                config.set("tts_voice_id", voice_id)
                config.set("tts_speed", str(speed))
                config.set("cartesia_api_key", cartesia_key)
                config.set("openai_api_key", openai_key)
                
                # Set dynamic keys
                if tts_provider == "openai_tts":
                    config.set("openai_tts_voice", voice_id)
                elif tts_provider == "cartesia":
                    config.set("cartesia_voice_id", voice_id)
                elif tts_provider == "kokoro":
                    config.set("kokoro_voice", voice_id)
                    
                bus.console_log.emit("INFO", f"TTS Test: Speaking via {tts_provider}...")
                from services.tts.provider_manager import tts_manager
                tts_manager.speak("Voice provider test successful, Sir.")
                bus.console_log.emit("INFO", "TTS Test complete.")
                
                # Restore settings
                config.set("tts_provider", old_tts)
                config.set("tts_voice_id", old_voice)
                config.set("tts_speed", old_speed)
                config.set("cartesia_api_key", old_cartesia)
                config.set("openai_api_key", old_openai)
            except Exception as e:
                logger.error(f"TTS Test failed: {e}")
                bus.console_log.emit("ERROR", f"TTS Test failed: {e}")
            finally:
                self.test_tts_provider_btn.setEnabled(True)
                self.test_tts_provider_btn.setText("TEST SELECTED TTS PROVIDER")
                self.refresh_provider_health()
                
        threading.Thread(target=run_test, daemon=True).start()
