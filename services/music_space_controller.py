import re
import time
import ctypes
import threading
import win32com.client
from core.event_bus import bus
from core.logger import logger
from services.transposition_engine import TranspositionEngine, NOTE_TO_SEMITONE

# ──────────────────────────────────────────────────────────
# Background Playback Thread
# ──────────────────────────────────────────────────────────
class MusicSpacePlaybackThread(threading.Thread):
    def __init__(self, controller, notes: list, mode: str, tempo: int, loop: bool):
        super().__init__()
        self.controller = controller
        self.notes = notes
        self.mode = mode
        self.tempo = tempo
        self.loop = loop
        self.stop_event = threading.Event()
        
        self.midi_device = None
        self.winmm = None
        
        if self.mode == "PIANO ROLL":
            try:
                self.winmm = ctypes.windll.winmm
                self.midi_device = ctypes.c_uint()
                res = self.winmm.midiOutOpen(ctypes.byref(self.midi_device), -1, 0, 0, 0)
                if res == 0:
                    # Grand Piano Program Change (Program 0 on Channel 0)
                    self.winmm.midiOutShortMsg(self.midi_device, 0xC0)
                else:
                    self.midi_device = None
            except Exception as e:
                logger.error(f"[MusicSpace] Failed to open MIDI device: {e}")
                self.midi_device = None

    def run(self):
        import pythoncom
        pythoncom.CoInitialize()
        
        sapi_voice = None
        if self.mode == "SWARAS":
            try:
                sapi_voice = win32com.client.Dispatch("SAPI.SpVoice")
            except Exception as e:
                logger.error(f"[MusicSpace] Failed to initialize SAPI SpVoice: {e}")

        swara_speech_map = {
            "S": "Sa", "R1": "Ri", "R2": "Ri", "R3": "Ri",
            "G1": "Ga", "G2": "Ga", "G3": "Ga",
            "M1": "Ma", "M2": "Ma",
            "P": "Pa",
            "D1": "Dha", "D2": "Dha", "D3": "Dha",
            "N1": "Ni", "N2": "Ni", "N3": "Ni"
        }

        while not self.stop_event.is_set():
            for idx, item in enumerate(self.notes):
                if self.stop_event.is_set():
                    break
                
                # 1. Update UI highlight
                self.controller.set_sounding_index(idx)
                
                # 2. Sound play
                note_name = item["note"]
                swara_name = item["swara"]
                clean_swara = re.sub(r"[^\w]", "", swara_name).strip()
                speech_text = swara_speech_map.get(clean_swara, clean_swara)
                
                midi_note = None
                if self.mode == "PIANO ROLL" and self.midi_device:
                    # Calculate MIDI: Middle C (60) + semitone offset + tonic offset relative to C
                    tonic_offset = NOTE_TO_SEMITONE.get(self.controller.tonic.upper(), 0)
                    midi_note = 60 + item["semitone"] + tonic_offset
                    # Note On
                    logger.info(f"[MusicSpace] MIDI Note ON: MIDI={midi_note} ({note_name}) for swara {swara_name}")
                    self.winmm.midiOutShortMsg(self.midi_device, 0x90 | (midi_note << 8) | (110 << 16))
                elif self.mode == "SWARAS" and sapi_voice:
                    try:
                        logger.info(f"[MusicSpace] SAPI SpVoice SPEAK: '{speech_text}' (Pitch offset={item['semitone']} semitones) for swara {swara_name}")
                        sapi_voice.Speak(speech_text, 1) # async
                    except Exception as e:
                        logger.error(f"[MusicSpace] SAPI Speak error: {e}")
                
                # 3. Tempo wait
                sleep_sec = 60.0 / self.tempo
                # Wait in small intervals to allow fast interruption
                steps = int(sleep_sec / 0.05)
                for _ in range(steps):
                    if self.stop_event.is_set():
                        break
                    time.sleep(0.05)
                
                # Note Off
                if self.mode == "PIANO ROLL" and self.midi_device and midi_note is not None:
                    self.winmm.midiOutShortMsg(self.midi_device, 0x80 | (midi_note << 8))
            
            if not self.loop:
                break
                
        # Final cleanup
        if self.midi_device:
            try:
                self.winmm.midiOutClose(self.midi_device)
            except Exception:
                pass
        pythoncom.CoUninitialize()
        
        # Mark stopped in controller safely
        self.controller.sounding_idx = -1
        self.controller.transport_status = "STOPPED"
        self.controller.sync()


# ──────────────────────────────────────────────────────────
# Music Space Controller
# ──────────────────────────────────────────────────────────
class MusicSpaceController:
    def __init__(self):
        self.raga_name = "Kalyani"
        self.raga_category = "Melakarta (72-scale tradition)"
        self.raga_swaras = ["S", "R2", "G3", "M2", "P", "D2", "N3", "S"]
        self.playback_mode = "PIANO ROLL"
        self.tonic = "D"
        self.transport_status = "STOPPED"
        self.tempo = 60
        self.loop = True
        self.sounding_idx = -1
        
        self.playback_thread = None
        self.last_playback_direction = "arohana"

    def set_raga(self, name: str, category: str, swaras: list):
        self.raga_name = name
        self.raga_category = category
        self.raga_swaras = swaras
        logger.info(f"[MusicSpace] Raga updated: {name} ({category})")
        # If playing, restart playback to load new notes
        if self.transport_status.startswith("PLAYING"):
            direction = self.last_playback_direction
            self.stop_playback()
            self.start_playback(direction)
        else:
            self.sync()

    def set_mode(self, mode: str):
        mode_upper = mode.upper().strip()
        if mode_upper in ("PIANO ROLL", "PIANO"):
            self.playback_mode = "PIANO ROLL"
        elif mode_upper in ("SWARAS", "SWARA"):
            self.playback_mode = "SWARAS"
        logger.info(f"[MusicSpace] Mode updated: {self.playback_mode}")
        if self.transport_status.startswith("PLAYING"):
            direction = self.last_playback_direction
            self.stop_playback()
            self.start_playback(direction)
        else:
            self.sync()

    def set_tonic(self, tonic: str):
        self.tonic = tonic.upper().strip()
        logger.info(f"[MusicSpace] Tonic updated: {self.tonic}")
        if self.transport_status.startswith("PLAYING"):
            direction = self.last_playback_direction
            self.stop_playback()
            self.start_playback(direction)
        else:
            self.sync()

    def set_tempo(self, tempo: int):
        self.tempo = max(20, min(300, tempo))
        logger.info(f"[MusicSpace] Tempo updated: {self.tempo} BPM")
        # Update running thread tempo dynamically
        if self.playback_thread and self.playback_thread.is_alive():
            self.playback_thread.tempo = self.tempo
        self.sync()

    def set_loop(self, loop: bool):
        self.loop = loop
        logger.info(f"[MusicSpace] Loop mode: {self.loop}")
        if self.playback_thread and self.playback_thread.is_alive():
            self.playback_thread.loop = self.loop
        self.sync()

    def set_transport(self, status: str):
        self.transport_status = status.upper().strip()
        logger.info(f"[MusicSpace] Transport status: {self.transport_status}")
        self.sync()

    def set_sounding_index(self, idx: int):
        self.sounding_idx = idx
        self.sync()

    def sync(self):
        state = {
            "raga_name": self.raga_name,
            "raga_category": self.raga_category,
            "raga_swaras": self.raga_swaras,
            "playback_mode": self.playback_mode,
            "tonic": self.tonic,
            "transport_status": self.transport_status,
            "tempo": self.tempo,
            "loop": self.loop,
            "sounding_idx": self.sounding_idx
        }
        bus.music_space_updated.emit(state)

    def handle_voice_command(self, command: str) -> str:
        cmd = command.lower().strip()
        cmd_clean = re.sub(r"[.,!?;:'\"]+", "", cmd).strip()
        
        # 1. Switch mode
        if "switch to piano mode" in cmd_clean or "switch to piano" in cmd_clean:
            self.set_mode("PIANO ROLL")
            return "Switched to piano roll mode."
        elif any(x in cmd_clean for x in ["switch to swaras mode", "switch to swaras", "suarez mode", "suarez", "swara mode", "swara"]):
            self.set_mode("SWARAS")
            return "Switched to swaras mode."
            
        # 2. Key change
        key_match = re.search(r"\b(play it in|change key to|set key to)\s+([a-g]#?|flat|sharp)?", cmd_clean)
        if key_match:
            words = cmd_clean.split()
            for idx, word in enumerate(words):
                if word in ("in", "to") and idx + 1 < len(words):
                    potential_key = words[idx + 1].upper()
                    if re.match(r"^[A-G]#?$", potential_key):
                        self.set_tonic(potential_key)
                        return f"Key transposed to {potential_key}."
            
        # 3. Tempo change
        tempo_match = re.search(r"\b(set tempo to|change tempo to|tempo)\s+(\d+)\b", cmd_clean)
        if tempo_match:
            new_tempo = int(tempo_match.group(2))
            self.set_tempo(new_tempo)
            return f"Tempo set to {new_tempo} beats per minute."
            
        # 4. Loop mode
        if "loop it" in cmd_clean or "enable loop" in cmd_clean or "turn loop on" in cmd_clean:
            self.set_loop(True)
            return "Looping enabled."
        elif "disable loop" in cmd_clean or "turn loop off" in cmd_clean:
            self.set_loop(False)
            return "Looping disabled."
            
        # 5. Playback commands
        if "play the arohana" in cmd_clean or "play arohana" in cmd_clean:
            self.start_playback("arohana")
            return "Playing arohana."
        elif "play the avarohana" in cmd_clean or "play avarohana" in cmd_clean:
            self.start_playback("avarohana")
            return "Playing avarohana."
        elif "play it again" in cmd_clean or "play again" in cmd_clean:
            self.start_playback("again")
            return "Playing scale."
        elif "stop playback" in cmd_clean or "stop music" in cmd_clean or "stop playing" in cmd_clean:
            self.stop_playback()
            return "Playback stopped."

        return None

    def start_playback(self, direction: str):
        self.stop_playback()
        
        if direction == "again":
            direction = self.last_playback_direction
        else:
            self.last_playback_direction = direction

        # Resolve swaras from the active raga scale
        # For simplicity, we fetch them from self.raga_swaras (arohana sequence).
        # If direction is avarohana, we use a reversed/avarohana sequence:
        # Let's check if the active raga is Kalyani or similar: we can query the database to get the exact avarohana sequence!
        scale_type = "avarohana" if direction == "avarohana" else "arohana"
        
        # Retrieve actual notes from DB for the current raga
        from services.ragas_service import ragas_service
        res = ragas_service.resolve_raga(self.raga_name)
        if res["status"] == "resolved":
            swaras_list = res["raga"][scale_type]
        else:
            # Fallback if DB query fails
            swaras_list = self.raga_swaras
            if direction == "avarohana":
                swaras_list = list(reversed(self.raga_swaras))

        transposed_notes = TranspositionEngine.transpose(
            swaras_list,
            self.tonic,
            scale_type=scale_type
        )
        
        self.set_transport(f"PLAYING ({direction.upper()})")
        self.playback_thread = MusicSpacePlaybackThread(
            self,
            transposed_notes,
            self.playback_mode,
            self.tempo,
            self.loop
        )
        self.playback_thread.start()
        
    def stop_playback(self):
        if self.playback_thread and self.playback_thread.is_alive():
            self.playback_thread.stop_event.set()
            self.playback_thread.join()
        self.set_transport("STOPPED")
        self.set_sounding_index(-1)

music_space_controller = MusicSpaceController()
