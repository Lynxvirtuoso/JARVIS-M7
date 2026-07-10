import os
import logging
from datetime import datetime
from core.event_bus import bus

# Ensure logs directory exists
os.makedirs("logs", exist_ok=True)

class EventBusLogHandler(logging.Handler):
    """Custom logging handler to redirect logs to the PyQt EventBus."""
    def emit(self, record):
        try:
            from PyQt6.QtWidgets import QApplication
            if QApplication.instance() is None:
                return
            msg = self.format(record)
            bus.console_log.emit(record.levelname, msg)
        except Exception:
            self.handleError(record)

def setup_logger():
    logger = logging.getLogger("JARVIS")
    logger.setLevel(logging.DEBUG)
    
    # Avoid duplicate handlers if setup is called multiple times
    if logger.handlers:
        return logger
        
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] (%(filename)s:%(lineno)d) - %(message)s')
    
    # File Handler
    log_file = os.path.join("logs", f"jarvis_{datetime.now().strftime('%Y%m%d')}.log")
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    
    # Console Handler (Stdout)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    
    # Event Bus Handler
    bus_handler = EventBusLogHandler()
    bus_handler.setLevel(logging.INFO)
    # Simpler format for the HUD screen
    hud_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S')
    bus_handler.setFormatter(hud_formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    logger.addHandler(bus_handler)
    
    return logger

logger = setup_logger()
