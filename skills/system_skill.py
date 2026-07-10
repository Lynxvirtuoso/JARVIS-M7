import os
import ctypes
import re
import subprocess
import psutil
from skills.base_skill import BaseSkill
from core.config import config
from core.logger import logger

# Import win32 libraries safely
try:
    import win32gui
    import win32con
    import win32process
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False

class SystemSkill(BaseSkill):
    @property
    def name(self) -> str:
        return "System Control Skill"

    @property
    def description(self) -> str:
        return "Controls local Windows system, running applications, window sizes, and queries statistics."

    def matches(self, command: str) -> bool:
        cmd = command.lower()
        triggers = [
            "lock", "sleep", "shutdown", "restart pc",
            "cpu", "ram", "memory", "battery", "storage", "disk", "hardware status",
            "minimize", "maximize", "restore window", "close window",
            "open calculator", "open notepad", "open note pad", "launch notepad", "start notepad", "open command prompt"
        ]
        return any(trigger in cmd for trigger in triggers)

    def execute(self, command: str) -> str:
        cmd = command.lower()
        salutation = config.salutation
        
        # 1. Lock Workstation
        if "lock" in cmd:
            try:
                ctypes.windll.user32.LockWorkStation()
                return f"Locking workstation, {salutation}."
            except Exception as e:
                logger.error(f"Failed to lock workstation: {e}")
                return f"I was unable to lock the workstation, {salutation}."
                
        # 2. Sleep PC
        elif "sleep" in cmd:
            if "confirm" in cmd or "yes" in cmd:
                try:
                    os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
                    return f"Entering sleep mode, {salutation}."
                except Exception as e:
                    logger.error(f"Failed to sleep PC: {e}")
                    return f"Unable to put the system to sleep, {salutation}."
            else:
                return f"Sleep command requires authorization. Please confirm to proceed, {salutation}."
                
        # 3. Shutdown PC
        elif "shutdown" in cmd:
            if "confirm" in cmd or "yes" in cmd:
                os.system("shutdown /s /t 60")
                return f"Initiating system shutdown in 60 seconds, {salutation}."
            else:
                return f"Shutdown command requires authorization. Please confirm to proceed, {salutation}."

        # 4. Restart PC
        elif "restart" in cmd:
            if "confirm" in cmd or "yes" in cmd:
                os.system("shutdown /r /t 60")
                return f"Initiating system restart in 60 seconds, {salutation}."
            else:
                return f"Restart command requires authorization. Please confirm to proceed, {salutation}."
                
        # 4. Window Operations (Minimize/Maximize)
        elif "minimize" in cmd:
            if WIN32_AVAILABLE:
                hwnd = win32gui.GetForegroundWindow()
                win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
                return f"Active window minimized, {salutation}."
            return f"Win32 API unavailable, {salutation}."
            
        elif "maximize" in cmd:
            if WIN32_AVAILABLE:
                hwnd = win32gui.GetForegroundWindow()
                win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
                return f"Active window maximized, {salutation}."
            return f"Win32 API unavailable, {salutation}."
            
        # 5. Core HW Metrics
        elif any(metric in cmd for metric in ["cpu", "ram", "memory", "battery", "storage", "hardware"]):
            cpu = psutil.cpu_percent()
            ram = psutil.virtual_memory().percent
            disk = psutil.disk_usage('C:\\').percent
            
            report = f"Current system metrics, {salutation}: CPU usage is at {cpu} percent, memory is at {ram} percent, and C drive storage is at {disk} percent."
            
            # Check battery if available
            battery = psutil.sensors_battery()
            if battery:
                plugged = "plugged in" if battery.power_plugged else "discharging"
                report += f" Battery is at {battery.percent} percent, currently {plugged}."
                
            return report

        # 6. Default App Launches
        elif "calculator" in cmd:
            subprocess.Popen("calc.exe")
            return f"Opening Calculator, {salutation}."
            
        elif "notepad" in cmd or "note pad" in cmd:
            subprocess.Popen("notepad.exe")
            return f"Opening Notepad, {salutation}."
            
        elif "command prompt" in cmd or "terminal" in cmd:
            subprocess.Popen("cmd.exe")
            return f"Launching Terminal, {salutation}."
            
        return f"System skill matched but action not recognized, {salutation}."
