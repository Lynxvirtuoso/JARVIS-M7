import subprocess
import os
import time
from datetime import datetime
from skills.base_skill import BaseSkill
from core.config import config
from core.logger import logger

try:
    import pyperclip
    PYCLIPBOARD_AVAILABLE = True
except ImportError:
    PYCLIPBOARD_AVAILABLE = False

try:
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False

class ProductivitySkill(BaseSkill):
    @property
    def name(self) -> str:
        return "Productivity Skill"

    @property
    def description(self) -> str:
        return "Manages developer productivity tasks like launching VS Code, terminals, notes, clipboard, screenshots, and text-to-speech."

    def matches(self, command: str) -> bool:
        cmd = command.lower()
        if any(np in cmd for np in ["open notepad", "open note pad", "launch notepad", "start notepad"]):
            return False
            
        triggers = [
            "visual studio code", "vs code", "vscode", 
            "note", "write note", "create note",
            "clipboard", "read clipboard",
            "screenshot", "capture screen"
        ]
        return any(x in cmd for x in triggers)

    def execute(self, command: str) -> str:
        cmd = command.lower()
        salutation = config.salutation
        
        # 1. Launch VS Code
        if "visual studio code" in cmd or "vs code" in cmd or "vscode" in cmd:
            try:
                # 'code' command is usually added to Windows PATH
                subprocess.Popen("code .", shell=True)
                return f"Opening Visual Studio Code in current directory, {salutation}."
            except Exception as e:
                logger.error(f"Failed to launch VS Code: {e}")
                return f"Unable to locate or launch Visual Studio Code, {salutation}."

        # 2. Create Note
        elif "note" in cmd or "create note" in cmd:
            parts = cmd.split("note", 1)
            content = parts[1].strip() if len(parts) > 1 else ""
            if not content:
                return f"What content would you like me to write in the note, {salutation}?"
                
            try:
                os.makedirs("notes", exist_ok=True)
                filename = f"notes/note_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(content)
                return f"Note saved successfully to {filename}, {salutation}."
            except Exception as e:
                logger.error(f"Failed to write note: {e}")
                return f"I failed to save the note, {salutation}."

        # 3. Clipboard manipulation
        elif "clipboard" in cmd:
            if not PYCLIPBOARD_AVAILABLE:
                return f"Pyperclip library is unavailable to read the clipboard, {salutation}."
                
            if "read" in cmd or "get" in cmd or "speak" in cmd:
                text = pyperclip.paste()
                if text:
                    # Trigger TTS read
                    from services.speech_service import speech
                    speech.speak(f"Clipboard contents: {text}")
                    return f"Reading clipboard aloud, {salutation}."
                else:
                    return f"The clipboard is currently empty, {salutation}."
            elif "copy" in cmd or "write" in cmd:
                # Stub for copying
                return f"Clipboard copy ready, {salutation}."

        # 4. Take Screenshot
        elif "screenshot" in cmd or "capture" in cmd:
            if not PYAUTOGUI_AVAILABLE:
                return f"PyAutoGUI is not available to capture screenshots, {salutation}."
            try:
                os.makedirs("screenshots", exist_ok=True)
                filename = f"screenshots/screen_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                pyautogui.screenshot(filename)
                return f"Screenshot captured and saved to {filename}, {salutation}."
            except Exception as e:
                logger.error(f"Screenshot capture failed: {e}")
                return f"Failed to capture screenshot, {salutation}."

        return f"Productivity skill command executed, {salutation}."
