"""
services/system_power_controller.py
Dedicated system power management controller for Windows OS actions (shutdown, restart, logout, lock).
Supports mock execution during unit testing and automated validation.
"""
import os
import subprocess
from core.logger import logger


class SystemPowerController:
    """
    Manages Windows system lifecycle commands safely.
    Allows mocking of real OS execution during unit tests.
    """
    def __init__(self, mock_mode: bool = False):
        self.mock_mode = mock_mode

    def shutdown_pc(self) -> bool:
        logger.info("[SYSTEM POWER] Executing PC shutdown...")
        if self.mock_mode:
            logger.info("[SYSTEM POWER MOCK] Shutdown simulated successfully.")
            return True
        try:
            subprocess.run(["shutdown", "/s", "/t", "5"], check=True)
            return True
        except Exception as e:
            logger.error(f"[SYSTEM POWER] Shutdown command failed: {e}")
            return False

    def restart_pc(self) -> bool:
        logger.info("[SYSTEM POWER] Executing PC restart...")
        if self.mock_mode:
            logger.info("[SYSTEM POWER MOCK] Restart simulated successfully.")
            return True
        try:
            subprocess.run(["shutdown", "/r", "/t", "5"], check=True)
            return True
        except Exception as e:
            logger.error(f"[SYSTEM POWER] Restart command failed: {e}")
            return False

    def logout_pc(self) -> bool:
        logger.info("[SYSTEM POWER] Executing PC logout...")
        if self.mock_mode:
            logger.info("[SYSTEM POWER MOCK] Logout simulated successfully.")
            return True
        try:
            subprocess.run(["shutdown", "/l"], check=True)
            return True
        except Exception as e:
            logger.error(f"[SYSTEM POWER] Logout command failed: {e}")
            return False

    def lock_pc(self) -> bool:
        logger.info("[SYSTEM POWER] Executing PC lock...")
        if self.mock_mode:
            logger.info("[SYSTEM POWER MOCK] Lock simulated successfully.")
            return True
        try:
            subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"], check=True)
            return True
        except Exception as e:
            logger.error(f"[SYSTEM POWER] Lock command failed: {e}")
            return False


# Canonical system power controller instance
system_power_controller = SystemPowerController()
