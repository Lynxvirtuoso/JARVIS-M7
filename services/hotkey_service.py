import ctypes
import ctypes.wintypes
import threading
from core.logger import logger
from core.event_bus import bus

class GlobalHotkeyService(threading.Thread):
    def __init__(self):
        super().__init__()
        self.daemon = True
        self.running = True
        
    def run(self):
        user32 = ctypes.windll.user32
        
        # Force creation of the Win32 message queue for this background thread
        # before attempting to register hotkeys or read messages.
        msg = ctypes.wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)
        
        # Modifier codes
        MOD_ALT = 0x0001
        MOD_CONTROL = 0x0002
        MOD_SHIFT = 0x0004
        
        # Virtual key codes
        VK_SPACE = 0x20
        VK_K = 0x4B
        VK_I = 0x49
        VK_PAUSE = 0x19 # Pause/Break key
        
        # Register combinations:
        # ID 1: Ctrl+Space
        # ID 2: Ctrl+Shift+K
        # ID 3: Ctrl+Alt+I (Highly unique fallback)
        # ID 4: Pause (Standalone fallback)
        h1 = user32.RegisterHotKey(None, 1, MOD_CONTROL, VK_SPACE)
        h2 = user32.RegisterHotKey(None, 2, MOD_CONTROL | MOD_SHIFT, VK_K)
        h3 = user32.RegisterHotKey(None, 3, MOD_CONTROL | MOD_ALT, VK_I)
        h4 = user32.RegisterHotKey(None, 4, 0, VK_PAUSE)
        
        if h1: logger.info("Global hotkey Ctrl+Space registered successfully.")
        else: logger.warning("Failed to register global hotkey Ctrl+Space (already in use).")
            
        if h2: logger.info("Global hotkey Ctrl+Shift+K registered successfully.")
        else: logger.warning("Failed to register global hotkey Ctrl+Shift+K (already in use).")
            
        if h3: logger.info("Global hotkey Ctrl+Alt+I registered successfully.")
        else: logger.warning("Failed to register global hotkey Ctrl+Alt+I.")
            
        if h4: logger.info("Global hotkey Pause/Break registered successfully.")
        else: logger.warning("Failed to register global hotkey Pause/Break.")
            
        if not any([h1, h2, h3, h4]):
            logger.error("No global hotkeys could be registered. Global interrupt fallback will be unavailable.")
            return
            
        while self.running:
            # GetMessageW blocks until a message is posted to this thread's queue
            if user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
                if msg.message == 0x0312: # WM_HOTKEY
                    hotkey_id = msg.wParam
                    logger.info(f"Global hotkey triggered (ID: {hotkey_id})! Halting playback.")
                    try:
                        # Stop speech playback immediately
                        from services.tts.provider_manager import tts_manager
                        tts_manager.stop_speaking()
                        
                        # Emit interrupted signal so engine updates state
                        bus.speech_interrupted.emit()
                    except Exception as e:
                        logger.error(f"Error executing global hotkey action: {e}", exc_info=True)
                        
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
                
        # Cleanup
        for hotkey_id in [1, 2, 3, 4]:
            user32.UnregisterHotKey(None, hotkey_id)
        logger.info("Global hotkeys unregistered.")

    def stop(self):
        self.running = False
        # Send a dummy message to break the blocking GetMessage call
        ctypes.windll.user32.PostThreadMessageW(self.ident, 0x0000, 0, 0)
