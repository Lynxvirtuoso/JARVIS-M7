import os
import sqlite3
import json
from core.logger import logger

class DatabaseManager:
    """Manages the SQLite database for settings, memory, routines and logs."""
    def __init__(self, db_path="database/jarvis.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.init_db()

    def get_connection(self):
        return sqlite3.connect(self.db_path)

    def init_db(self):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Settings table (configurations)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS settings (
                        key TEXT PRIMARY KEY,
                        value TEXT
                    )
                """)
                
                # Memory table (facts, preferences, learning)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS memory (
                        key TEXT PRIMARY KEY,
                        value TEXT,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Conversation history
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS conversation_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        role TEXT,
                        content TEXT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Custom routines (macros)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS routines (
                        name TEXT PRIMARY KEY,
                        steps TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Cooldowns table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS cooldowns (
                        key TEXT PRIMARY KEY,
                        until REAL
                    )
                """)
                
                # Ragas table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS ragas (
                        id INTEGER PRIMARY KEY,
                        name TEXT NOT NULL UNIQUE,
                        category TEXT NOT NULL,
                        tradition TEXT,
                        parent_id INTEGER,
                        FOREIGN KEY (parent_id) REFERENCES ragas(id)
                    )
                """)
                
                # Raga notes table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS raga_notes (
                        raga_id INTEGER,
                        scale_type TEXT NOT NULL,
                        note_position INTEGER NOT NULL,
                        note TEXT NOT NULL,
                        PRIMARY KEY (raga_id, scale_type, note_position),
                        FOREIGN KEY (raga_id) REFERENCES ragas(id) ON DELETE CASCADE
                    )
                """)
                
                conn.commit()
                logger.info("SQLite database initialized successfully.")
                
                # Insert default configurations
                self.set_setting_default("salutation", "Sir")
                self.set_setting_default("wake_timeout", "12") # in seconds
                self.set_setting_default("speech_rate", "180")
                
                # STT Default Settings
                self.set_setting_default("stt_provider", "groq_stt")
                self.set_setting_default("whisper_model", "small.en")
                self.set_setting_default("whisper_device", "cpu")
                self.set_setting_default("whisper_compute_type", "int8")
                self.set_setting_default("deepgram_api_key", "")
                self.set_setting_default("deepgram_model", "nova-2")
                self.set_setting_default("openai_api_key", "")
                self.set_setting_default("openai_stt_model", "whisper-1")
                
                # TTS Default Settings
                self.set_setting_default("tts_provider", "windows_sapi")
                self.set_setting_default("tts_voice_id", "")
                self.set_setting_default("tts_speed", "1.0")
                self.set_setting_default("openai_tts_model", "gpt-4o-mini-tts")
                self.set_setting_default("openai_tts_voice", "onyx")
                self.set_setting_default("cartesia_api_key", "")
                self.set_setting_default("cartesia_voice_id", "a0e99841-438c-4a64-b679-ae501e7d6091")
                self.set_setting_default("kokoro_enabled", "true")
                
                # Pipeline Settings
                self.set_setting_default("command_timeout_seconds", "12")
                self.set_setting_default("silence_timeout_ms", "1500")
                self.set_setting_default("minimum_command_duration_seconds", "0.8")
                self.set_setting_default("tts_mic_cooldown_ms", "800")
                self.set_setting_default("input_gain_boost_db", "6")
                
                self.set_setting_default("voice_wake_enabled", "1")
                self.set_setting_default("clap_wake_enabled", "1")
                
                # Brain & Ollama Default Settings
                self.set_setting_default("ollama_model", "qwen3:1.7b")
                self.set_setting_default("brain_mode", "smart_auto")
                self.set_setting_default("ollama_think", "false")
                self.set_setting_default("ollama_num_ctx", "2048")

                # Migration: if whisper_device is "auto", migrate to "cpu" and "int8"
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT value FROM settings WHERE key = 'whisper_device'")
                    row = cursor.fetchone()
                    if row and row[0] == "auto":
                        logger.info("Migrating whisper_device setting from 'auto' to 'cpu'.")
                        cursor.execute("UPDATE settings SET value = 'cpu' WHERE key = 'whisper_device'")
                        cursor.execute("UPDATE settings SET value = 'int8' WHERE key = 'whisper_compute_type'")
                        conn.commit()

                    # Migration: ollama_model qwen2.5:1.5b or empty -> qwen3:1.7b
                    cursor.execute("SELECT value FROM settings WHERE key = 'ollama_model'")
                    row = cursor.fetchone()
                    if not row or row[0] is None or str(row[0]).strip() == "" or str(row[0]).strip() == "qwen2.5:1.5b":
                        logger.info("Migrating ollama_model setting to 'qwen3:1.7b'.")
                        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('ollama_model', 'qwen3:1.7b')")
                        conn.commit()
                
        except Exception as e:
            logger.error(f"Error initializing SQLite database: {e}", exc_info=True)

    def set_setting_default(self, key, value):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM settings WHERE key = ?", (key,))
            if not cursor.fetchone():
                cursor.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (key, value))
                conn.commit()

    def get_setting(self, key, default=None):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
                row = cursor.fetchone()
                return row[0] if row else default
        except Exception as e:
            logger.error(f"Database error reading setting '{key}': {e}")
            return default

    def set_setting(self, key, value):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
                conn.commit()
        except Exception as e:
            logger.error(f"Database error writing setting '{key}': {e}")

    def get_memory(self, key, default=None):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT value FROM memory WHERE key = ?", (key,))
                row = cursor.fetchone()
                return json.loads(row[0]) if row else default
        except Exception as e:
            logger.error(f"Database error reading memory '{key}': {e}")
            return default

    def set_memory(self, key, value):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                val_str = json.dumps(value)
                cursor.execute("INSERT OR REPLACE INTO memory (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)", (key, val_str))
                conn.commit()
        except Exception as e:
            logger.error(f"Database error writing memory '{key}': {e}")

    def add_history(self, role, content):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO conversation_history (role, content) VALUES (?, ?)", (role, content))
                conn.commit()
        except Exception as e:
            logger.error(f"Database error adding history: {e}")

    def get_history(self, limit=50):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT role, content, timestamp FROM conversation_history ORDER BY id DESC LIMIT ?", (limit,))
                rows = cursor.fetchall()
                # Return in chronological order
                return [{"role": r[0], "content": r[1], "timestamp": r[2]} for r in reversed(rows)]
        except Exception as e:
            logger.error(f"Database error retrieving history: {e}")
            return []

    def get_routine(self, name):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT steps FROM routines WHERE name = ?", (name,))
                row = cursor.fetchone()
                return json.loads(row[0]) if row else None
        except Exception as e:
            logger.error(f"Database error retrieving routine '{name}': {e}")
            return None

    def save_routine(self, name, steps):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                steps_str = json.dumps(steps)
                cursor.execute("INSERT OR REPLACE INTO routines (name, steps) VALUES (?, ?)", (name, steps_str))
                conn.commit()
        except Exception as e:
            logger.error(f"Database error saving routine '{name}': {e}")

    def get_cooldowns(self):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT key, until FROM cooldowns")
                return {row[0]: row[1] for row in cursor.fetchall()}
        except Exception as e:
            logger.error(f"Database error reading cooldowns: {e}")
            return {}

    def set_cooldown(self, key, until):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT OR REPLACE INTO cooldowns (key, until) VALUES (?, ?)", (key, until))
                conn.commit()
        except Exception as e:
            logger.error(f"Database error writing cooldown: {e}")

    def remove_cooldown(self, key):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM cooldowns WHERE key = ?", (key,))
                conn.commit()
        except Exception as e:
            logger.error(f"Database error removing cooldown '{key}': {e}")

    def get_all_routines(self):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM routines")
                return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Database error listing routines: {e}")
            return []

    def delete_routine(self, name):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM routines WHERE name = ?", (name,))
                conn.commit()
        except Exception as e:
            logger.error(f"Database error deleting routine '{name}': {e}")

# Global db instance
db = DatabaseManager()
