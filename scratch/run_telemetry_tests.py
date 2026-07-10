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
from core.engine import JarvisEngine
from services.speech_service import speech
from core.telemetry import pipeline_timer

def run_case_a(app, engine):
    logger.info("\n=== RUNNING CASE A: 'open Notepad' (Deterministic) ===")
    
    # Reset engine state
    engine.state = "TRANSCRIBING_COMMAND"
    engine.in_session = False
    engine.pending_command = None
    engine.pending_command_type = None
    
    pipeline_timer.start_pipeline("open Notepad")
    # Trigger command with source="typed" so TrustGate evaluates to EXECUTE directly
    engine._process_received_command("open Notepad", source="typed")
    
    # Wait 12 seconds for Case A to fully finish playing
    QTimer.singleShot(12000, lambda: run_case_b(app, engine))

def run_case_b(app, engine):
    logger.info("\n=== RUNNING CASE B: 'what's the capital of France' (LLM / Open-ended) ===")
    
    # Reset engine state
    engine.state = "TRANSCRIBING_COMMAND"
    engine.in_session = False
    engine.pending_command = None
    engine.pending_command_type = None
    
    pipeline_timer.start_pipeline("what's the capital of France")
    engine._process_received_command("what's the capital of France", source="voice")
    
    # Wait 25 seconds for Case B to finish, then exit
    QTimer.singleShot(25000, lambda: exit_app(app))

def exit_app(app):
    logger.info("Tests complete! Exiting...")
    app.quit()

def main():
    app = QApplication(sys.argv)
    
    # Initialize Engine (do not start audio_service to avoid microphone lock)
    engine = JarvisEngine()
    
    # Start testing in the event loop after 10 seconds to let Kokoro pre-caching complete in the background
    logger.info("Waiting 10 seconds for Kokoro background warmup to finish...")
    QTimer.singleShot(10000, lambda: run_case_a(app, engine))
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
