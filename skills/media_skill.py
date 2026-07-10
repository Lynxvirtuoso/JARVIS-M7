import ctypes
import re
from skills.base_skill import BaseSkill
from core.config import config
from core.logger import logger

# Pycaw imports for audio endpoint control
try:
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    PYCAW_AVAILABLE = True
except ImportError:
    PYCAW_AVAILABLE = False

# Windows Virtual Key codes for media keys
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_PLAY_PAUSE = 0xB3
VK_VOLUME_MUTE = 0xAD
KEYEVENTF_KEYUP = 0x0002

class MediaSkill(BaseSkill):
    @property
    def name(self) -> str:
        return "Media Skill"

    @property
    def description(self) -> str:
        return "Controls PC volume, mute status, and media playback."

    def matches(self, command: str) -> bool:
        cmd = command.lower()
        triggers = ["volume", "mute", "unmute", "play", "pause", "skip", "next song", "previous song", "spotify", "youtube control"]
        return any(x in cmd for x in triggers)

    def execute(self, command: str) -> str:
        cmd = command.lower()
        salutation = config.salutation
        
        # 1. Volume operations (requires Pycaw)
        if "volume" in cmd:
            if not PYCAW_AVAILABLE:
                return f"Pycaw is not available to adjust volume, {salutation}."
                
            try:
                # Get speakers volume control
                devices = AudioUtilities.GetSpeakers()
                interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                volume_control = ctypes.cast(interface, ctypes.POINTER(IAudioEndpointVolume))
                
                # Check for specific numbers (e.g. "set volume to 50")
                match = re.search(r'(\d+)\s*%', cmd) or re.search(r'to\s+(\d+)', cmd) or re.search(r'volume\s+(\d+)', cmd)
                
                if match:
                    target_vol = int(match.group(1))
                    target_vol = max(0, min(target_vol, 100)) # Clamp 0-100
                    # Set master volume scalar (0.0 to 1.0)
                    volume_control.SetMasterVolumeLevelScalar(target_vol / 100.0, None)
                    return f"Volume set to {target_vol} percent, {salutation}."
                
                elif "increase" in cmd or "up" in cmd:
                    current_vol = volume_control.GetMasterVolumeLevelScalar()
                    new_vol = min(1.0, current_vol + 0.1) # Up by 10%
                    volume_control.SetMasterVolumeLevelScalar(new_vol, None)
                    return f"Volume increased to {int(new_vol * 100)} percent, {salutation}."
                    
                elif "decrease" in cmd or "down" in cmd:
                    current_vol = volume_control.GetMasterVolumeLevelScalar()
                    new_vol = max(0.0, current_vol - 0.1) # Down by 10%
                    volume_control.SetMasterVolumeLevelScalar(new_vol, None)
                    return f"Volume decreased to {int(new_vol * 100)} percent, {salutation}."
                    
            except Exception as e:
                logger.error(f"Volume adjustment failed: {e}")
                return f"I failed to adjust the volume, {salutation}."
                
        # 2. Mute / Unmute
        if "mute" in cmd or "unmute" in cmd:
            if not PYCAW_AVAILABLE:
                return f"Pycaw is not available, {salutation}."
            try:
                devices = AudioUtilities.GetSpeakers()
                interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                volume_control = ctypes.cast(interface, ctypes.POINTER(IAudioEndpointVolume))
                
                if "unmute" in cmd:
                    volume_control.SetMute(0, None)
                    return f"System unmuted, {salutation}."
                else:
                    volume_control.SetMute(1, None)
                    return f"System muted, {salutation}."
            except Exception as e:
                logger.error(f"Mute toggle failed: {e}")
                return f"Unable to modify mute status, {salutation}."

        # 3. Play / Pause / Skip (Virtual Keys)
        if "play" in cmd or "pause" in cmd:
            self._send_key(VK_MEDIA_PLAY_PAUSE)
            return f"Toggling media playback, {salutation}."
            
        elif "next" in cmd or "skip" in cmd:
            self._send_key(VK_MEDIA_NEXT_TRACK)
            return f"Playing next track, {salutation}."
            
        elif "previous" in cmd or "prev" in cmd:
            self._send_key(VK_MEDIA_PREV_TRACK)
            return f"Playing previous track, {salutation}."
            
        return f"Media command processed, {salutation}."

    def _send_key(self, vk):
        """Simulates virtual key press."""
        try:
            ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
            ctypes.windll.user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
        except Exception as e:
            logger.error(f"Failed to send key code {vk}: {e}")
