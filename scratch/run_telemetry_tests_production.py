import sys
import os
import time
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

# Ensure correct pathing
project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(project_dir)
sys.path.append(project_dir)

from core.logger import logger
from main import JarvisApp
from core.telemetry import pipeline_timer

def run_case_a(app):
    logger.info("\n=== RUNNING CASE A: 'open Notepad' (Deterministic) ===")
    
    # Reset engine state
    app.engine.state = "TRANSCRIBING_COMMAND"
    app.engine.in_session = False
    app.engine.pending_command = None
    app.engine.pending_command_type = None
    
    pipeline_timer.start_pipeline("open Notepad")
    # Trigger command with source="typed" so TrustGate evaluates to EXECUTE directly
    app.engine._process_received_command("open Notepad", source="typed")
    
    # Wait 12 seconds for Case A to fully finish playing
    QTimer.singleShot(12000, lambda: run_case_b(app))

def run_case_b(app):
    logger.info("\n=== RUNNING CASE B: 'what's the capital of France' (LLM / Open-ended) ===")
    
    # Reset engine state
    app.engine.state = "TRANSCRIBING_COMMAND"
    app.engine.in_session = False
    app.engine.pending_command = None
    app.engine.pending_command_type = None
    
    pipeline_timer.start_pipeline("what's the capital of France")
    app.engine._process_received_command("what's the capital of France", source="voice")
    
    # Wait 25 seconds for Case B to finish, then exit
    QTimer.singleShot(25000, lambda: exit_app(app))

def exit_app(app):
    logger.info("Tests complete! Exiting...")
    from services.audio_service import audio_service
    audio_service.stop()
    app.app.quit()

def main():
    # Instantiate the actual production JARVIS application (loads audio_service on boot)
    app = JarvisApp()
    
    # Start testing in the event loop after 10 seconds to let Kokoro pre-caching complete in the background
    logger.info("Waiting 10 seconds for Kokoro background warmup to finish...")
    QTimer.singleShot(10000, lambda: run_case_a(app))
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
