import sys
import os

# Ensure correct pathing and working directory
project_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(project_dir)
sys.path.append(project_dir)

# Redirect stdout/stderr if launched in startup mode
startup_mode = "--startup" in sys.argv
if startup_mode:
    try:
        os.makedirs(os.path.join(project_dir, "logs"), exist_ok=True)
        startup_log_path = os.path.join(project_dir, "logs", "startup_errors.log")
        # Line-buffered write mode to ensure logs are written out immediately
        startup_log = open(startup_log_path, "a", encoding="utf-8", buffering=1)
        sys.stdout = startup_log
        sys.stderr = startup_log
    except Exception:
        pass

import time
for attempt in range(4):
    try:
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import QObject, pyqtSlot
        break
    except (ImportError, ModuleNotFoundError) as e:
        sys.stderr.write(f"Import failed (attempt {attempt+1}/4), retrying in 5s: {e}\n")
        sys.stderr.flush()
        if attempt == 3:
            raise e
        time.sleep(5)

from core.logger import logger

# Uncaught exception hook
def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logger.critical("Unhandled exception during execution", exc_info=(exc_type, exc_value, exc_traceback))
    sys.stderr.write(f"\n[{os.path.basename(__file__)}] Unhandled exception: {exc_type.__name__}: {exc_value}\n")
    import traceback
    traceback.print_tb(exc_traceback, file=sys.stderr)
    sys.stderr.flush()

sys.excepthook = handle_exception

from core.database import db
from core.config import config
from core.engine import JarvisEngine
from core.event_bus import bus
from ui.hud.window import HUDWindow
from ui.settings.window import SettingsWindow

class JarvisApp(QObject):
    def __init__(self):
        super().__init__()
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False) # Keep running in tray even if HUD is closed
        
        # Initialize Settings Window (lazy loaded)
        self.settings_window = None
        
        # Initialize HUD Window
        self.hud = HUDWindow(settings_cb=self.open_settings)
        
        # Initialize Engine
        self.engine = JarvisEngine()
        self.engine.hud = self.hud
        
        # Start background Audio Service
        from services.audio_service import audio_service
        audio_service.start()
        # Detect startup mode
        self.startup_mode = "--startup" in sys.argv

        # Hook special HUD action callbacks (settings, exit) from the engine/skills
        bus.command_status.connect(self.handle_system_request)

        # Full exit signal from engine (spoken 'Jarvis exit app' or 'Jarvis fully shutdown')
        # Also wired in HUDWindow directly, but connect here as belt-and-suspenders.
        bus.full_exit_requested.connect(self.hud.exit_app)

        # Show HUD on launch
        if not self.startup_mode:
            self.hud.show()
        else:
            logger.info("Launched via --startup. App initialized in system tray / minimized mode.")

        # Start Engine
        self.engine.start(startup_mode=self.startup_mode)

    def open_settings(self):
        if self.settings_window is None:
            self.settings_window = SettingsWindow()
        self.settings_window.show()
        self.settings_window.raise_()
        self.settings_window.activateWindow()

    @pyqtSlot(str)
    def handle_system_request(self, status):
        if status == "exit_request":
            self.hud.exit_app()
        elif status == "settings_request":
            self.open_settings()

    def exec(self):
        return self.app.exec()

def main():
    logger.info("Starting JARVIS M7 OS...")
    
    import socket
    global_lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        global_lock_socket.bind(("127.0.0.1", 47777))
    except socket.error:
        logger.warning("Another instance of JARVIS is already running. Exiting.")
        sys.exit(0)

    try:
        from core.autostart import reconcile_autostart_config
        reconcile_autostart_config()
    except Exception as e:
        logger.error(f"Error during autostart reconciliation: {e}")

    try:
        app = JarvisApp()
        sys.exit(app.exec())
    except Exception as e:
        logger.critical(f"Unhandled exception during JARVIS startup: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
