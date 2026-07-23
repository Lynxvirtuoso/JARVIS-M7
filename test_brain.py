import os
import json
import unittest
import logging
from unittest.mock import patch, MagicMock

from core.config import config, parse_bool
from core.database import db
from core.logger import RedactingFormatter
from services.brain.base import BrainResult
from services.brain.ollama_brain_provider import (
    OllamaBrainProvider, OllamaAvailabilityStatus, ProviderHealth, _NOTIFIED_MISSING_MODELS
)
from services.brain.provider_manager import (
    BrainProviderManager, BrainRequest, BrainRoute, get_provider_order, is_valid_result
)
from core.brain import needs_web_search


class TestOllamaUpgradeAndBrainRouting(unittest.TestCase):

    def setUp(self):
        _NOTIFIED_MISSING_MODELS.clear()

    # --- 1. Boolean Parsing ---
    def test_canonical_parse_bool(self):
        self.assertTrue(parse_bool(True))
        self.assertFalse(parse_bool(False))

        self.assertTrue(parse_bool(1))
        self.assertFalse(parse_bool(0))

        self.assertTrue(parse_bool("true"))
        self.assertTrue(parse_bool("TRUE"))
        self.assertTrue(parse_bool("1"))
        self.assertTrue(parse_bool("yes"))
        self.assertTrue(parse_bool("on"))
        self.assertTrue(parse_bool("enabled"))

        self.assertFalse(parse_bool("false"))
        self.assertFalse(parse_bool("FALSE"))
        self.assertFalse(parse_bool("0"))
        self.assertFalse(parse_bool("no"))
        self.assertFalse(parse_bool("off"))
        self.assertFalse(parse_bool("disabled"))
        self.assertFalse(parse_bool(""))
        self.assertFalse(parse_bool(None))
        self.assertFalse(parse_bool("unexpected"))

    def test_parse_bool_payload_and_local_only(self):
        provider = OllamaBrainProvider()
        config.set("ollama_think", "false")
        payload1 = provider._build_payload([{"role": "user", "content": "hi"}], stream=False)
        self.assertIs(payload1["think"], False)

        config.set("ollama_think", "true")
        payload2 = provider._build_payload([{"role": "user", "content": "hi"}], stream=False)
        self.assertIs(payload2["think"], True)
        config.set("ollama_think", "false")

        manager = BrainProviderManager()
        config.set("local_only_mode", "false")
        _, p_normal, _ = manager.determine_route("hi")
        self.assertNotEqual(p_normal, ["ollama"])

        config.set("local_only_mode", "true")
        _, p_local, _ = manager.determine_route("hi")
        self.assertEqual(p_local, ["ollama"])
        config.set("local_only_mode", "false")

    # --- 2. Model Migration ---
    def test_default_model_is_qwen3_1_7b(self):
        provider = OllamaBrainProvider()
        self.assertEqual(provider.model, config.get("ollama_model", "qwen3:1.7b"))

    def test_empty_stored_model_migrates_to_qwen3_1_7b(self):
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE settings SET value = '' WHERE key = 'ollama_model'")
            conn.commit()

        db.init_db()
        self.assertEqual(db.get_setting("ollama_model"), "qwen3:1.7b")

    def test_old_default_migrates_to_qwen3_1_7b(self):
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE settings SET value = 'qwen2.5:1.5b' WHERE key = 'ollama_model'")
            conn.commit()

        db.init_db()
        self.assertEqual(db.get_setting("ollama_model"), "qwen3:1.7b")

    def test_custom_stored_model_is_preserved(self):
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE settings SET value = 'llama3.2:3b' WHERE key = 'ollama_model'")
            conn.commit()

        db.init_db()
        self.assertEqual(db.get_setting("ollama_model"), "llama3.2:3b")
        db.set_setting("ollama_model", "qwen3:1.7b")

    def test_migration_is_idempotent(self):
        db.set_setting("ollama_model", "qwen3:1.7b")
        db.init_db()
        self.assertEqual(db.get_setting("ollama_model"), "qwen3:1.7b")
        db.init_db()
        self.assertEqual(db.get_setting("ollama_model"), "qwen3:1.7b")

    # --- 3. Ollama Payloads & Context Size ---
    def test_think_is_false_by_default(self):
        provider = OllamaBrainProvider()
        payload = provider._build_payload([{"role": "user", "content": "hi"}], stream=False)
        self.assertFalse(payload["think"])
        self.assertIsInstance(payload["think"], bool)

    def test_explicit_think_true_override(self):
        provider = OllamaBrainProvider()
        payload = provider._build_payload([{"role": "user", "content": "hi"}], stream=False, think=True)
        self.assertTrue(payload["think"])

    def test_explicit_think_false_override(self):
        provider = OllamaBrainProvider()
        payload = provider._build_payload([{"role": "user", "content": "hi"}], stream=False, think=False)
        self.assertFalse(payload["think"])

    def test_think_none_resolves_to_boolean(self):
        provider = OllamaBrainProvider()
        payload = provider._build_payload([{"role": "user", "content": "hi"}], stream=False, think=None)
        self.assertIsInstance(payload["think"], bool)

    def test_payload_never_contains_think_none(self):
        provider = OllamaBrainProvider()
        payload = provider._build_payload([{"role": "user", "content": "hi"}], stream=False, think=None)
        self.assertIsNotNone(payload["think"])

    def test_streaming_and_non_streaming_options_match(self):
        provider = OllamaBrainProvider()
        p1 = provider._build_payload([{"role": "user", "content": "hi"}], stream=False)
        p2 = provider._build_payload([{"role": "user", "content": "hi"}], stream=True)
        self.assertEqual(p1["options"], p2["options"])
        self.assertFalse(p1["stream"])
        self.assertTrue(p2["stream"])

    def test_context_size_wiring(self):
        provider = OllamaBrainProvider()
        config.set("ollama_num_ctx", "4096")
        p_4096 = provider._build_payload([{"role": "user", "content": "hi"}], stream=False)
        self.assertEqual(p_4096["options"]["num_ctx"], 4096)

        config.set("ollama_num_ctx", "999999")
        p_invalid = provider._build_payload([{"role": "user", "content": "hi"}], stream=False)
        self.assertEqual(p_invalid["options"]["num_ctx"], 2048)
        config.set("ollama_num_ctx", "2048")

    # --- 4. Thinking Output Isolation ---
    def test_thinking_token_end_to_end_isolation(self):
        token = "PRIVATE_INTERNAL_THINKING_TOKEN_93841"
        provider = OllamaBrainProvider()
        fake_response_data = json.dumps({
            "message": {
                "role": "assistant",
                "thinking": token,
                "content": "Final safe answer."
            }
        }).encode('utf-8')

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_res = MagicMock()
            mock_res.status = 200
            mock_res.read.return_value = fake_response_data
            mock_res.__enter__.return_value = mock_res
            mock_urlopen.return_value = mock_res

            with patch.object(provider, "check_availability", return_value=(OllamaAvailabilityStatus.AVAILABLE, "Ready", ["qwen3:1.7b"])):
                mock_tts = MagicMock()
                mock_db = MagicMock()
                mock_bus = MagicMock()

                res = provider.think("hello")
                self.assertTrue(res.success)
                self.assertEqual(res.text, "Final safe answer.")
                self.assertNotIn(token, res.text)
                self.assertEqual(res.thinking, token)

                # Simulated outputs
                mock_tts.speak(res.text)
                mock_db.add_history("model", res.text)
                mock_bus.command_completed.emit(True, res.text)

                for m in [mock_tts, mock_db, mock_bus]:
                    for call in m.mock_calls:
                        self.assertNotIn(token, str(call))

    def test_streaming_thinking_chunks_are_ignored(self):
        provider = OllamaBrainProvider()
        chunk1 = json.dumps({"message": {"thinking": "PRIVATE_INTERNAL_THINKING_TOKEN_93841", "content": ""}}).encode('utf-8') + b"\n"
        chunk2 = json.dumps({"message": {"thinking": "More hidden reasoning", "content": ""}}).encode('utf-8') + b"\n"
        chunk3 = json.dumps({"message": {"thinking": "", "content": "Final "}}).encode('utf-8') + b"\n"
        chunk4 = json.dumps({"message": {"thinking": "", "content": "safe answer."}}).encode('utf-8') + b"\n"

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_res = MagicMock()
            mock_res.__iter__.return_value = [chunk1, chunk2, chunk3, chunk4]
            mock_res.__enter__.return_value = mock_res
            mock_urlopen.return_value = mock_res

            with patch.object(provider, "check_availability", return_value=(OllamaAvailabilityStatus.AVAILABLE, "Ready", ["qwen3:1.7b"])):
                streamed = list(provider.think_stream("hello"))
                self.assertEqual(streamed, ["Final ", "safe answer."])
                full_stream = "".join(streamed)
                self.assertEqual(full_stream, "Final safe answer.")
                self.assertNotIn("PRIVATE_INTERNAL_THINKING_TOKEN_93841", full_stream)

    # --- 5. Genuine Web-Enabled Groq Routing ---
    def test_groq_use_web_routing(self):
        manager = BrainProviderManager()
        mock_groq = MagicMock()
        mock_groq.think.return_value = BrainResult(text="Bitcoin price info", provider="groq", success=True)
        manager.providers["groq"] = mock_groq

        # Make Ollama unavailable so Groq is the fallback
        mock_ollama = MagicMock()
        mock_ollama.think.return_value = BrainResult(text="", provider="ollama", success=False)
        manager.providers["ollama"] = mock_ollama

        # General knowledge -> use_web=False, goes to SIMPLE_CHAT, Ollama fails -> Groq called with use_web=False
        manager.think("What is Bitcoin?")
        mock_groq.think.assert_called_with("What is Bitcoin?", None, use_web=False)

        # Current info -> use_web=True
        manager.think("What is Bitcoin's current price?")
        mock_groq.think.assert_called_with("What is Bitcoin's current price?", None, use_web=True)

        # Electric current -> use_web=False (not a live/current-info request)
        mock_ollama.think.return_value = BrainResult(text="", provider="ollama", success=False)
        manager.think("Explain electric current")
        mock_groq.think.assert_called_with("Explain electric current", None, use_web=False)

        # Current president -> use_web=True
        manager.think("Who is the current president of India?")
        mock_groq.think.assert_called_with("Who is the current president of India?", None, use_web=True)

    def test_groq_brain_provider_use_web_execution(self):
        from services.brain.groq_brain_provider import GroqBrainProvider
        provider = GroqBrainProvider()

        with patch.object(provider, "think_compound_mini", return_value=["Search results for price"]) as mock_compound:
            res = provider.think("current price", use_web=True)
            self.assertTrue(res.success)
            self.assertEqual(res.text, "Search results for price")
            mock_compound.assert_called_once()

    # --- 6. Provider Order & Fallback ---
    def test_get_provider_order(self):
        self.assertEqual(get_provider_order("groq"), ["groq", "ollama", "gemini"])
        self.assertEqual(get_provider_order("ollama"), ["ollama", "groq", "gemini"])
        self.assertEqual(get_provider_order("gemini"), ["gemini", "ollama", "groq"])

    def test_failed_provider_triggers_fallback(self):
        manager = BrainProviderManager()

        p_ollama = MagicMock()
        p_ollama.think.return_value = BrainResult(success=False, text="", error="Failed")
        p_groq = MagicMock()
        p_groq.think.return_value = BrainResult(success=True, text="Groq response")

        manager.providers["ollama"] = p_ollama
        manager.providers["groq"] = p_groq

        res = manager.think("hello")
        self.assertTrue(res.success)
        self.assertEqual(res.text, "Groq response")

    def test_empty_provider_response_triggers_fallback(self):
        manager = BrainProviderManager()

        p_ollama = MagicMock()
        p_ollama.think.return_value = BrainResult(success=True, text="   ")
        p_groq = MagicMock()
        p_groq.think.return_value = BrainResult(success=True, text="Groq text")

        manager.providers["ollama"] = p_ollama
        manager.providers["groq"] = p_groq

        res = manager.think("hello")
        self.assertEqual(res.text, "Groq text")

    def test_is_valid_result(self):
        self.assertTrue(is_valid_result(BrainResult(success=True, text="Valid")))
        self.assertFalse(is_valid_result(BrainResult(success=False, text="Valid")))
        self.assertFalse(is_valid_result(BrainResult(success=True, text="")))
        self.assertFalse(is_valid_result(BrainResult(success=True, text="   \n")))
        self.assertFalse(is_valid_result(None))

    # --- 7. Missing Model Handling & Deduplication ---
    def test_missing_model_skips_ollama_without_circuit_breaker_increment(self):
        provider = OllamaBrainProvider()
        with patch.object(provider, "check_availability", return_value=(OllamaAvailabilityStatus.MODEL_NOT_INSTALLED, "Model missing", [])):
            res = provider.think("hello")
            self.assertFalse(res.success)
            self.assertEqual(res.error_type, "model_not_installed")
            self.assertIn("ollama pull qwen3:1.7b", res.error)
            self.assertEqual(provider.health_state.consecutive_service_failures, 0)

    def test_missing_model_notification_deduplication(self):
        provider = OllamaBrainProvider()
        with patch.object(provider, "check_availability", return_value=(OllamaAvailabilityStatus.MODEL_NOT_INSTALLED, "Model missing", [])):
            with patch("core.logger.logger.warning") as mock_warn:
                provider.think("hello 1")
                provider.think("hello 2")
                provider.think("hello 3")
                self.assertEqual(mock_warn.call_count, 1)

    def test_refresh_models_updates_status(self):
        provider = OllamaBrainProvider()
        with patch.object(provider, "check_availability", side_effect=[
            (OllamaAvailabilityStatus.MODEL_NOT_INSTALLED, "Missing", ["qwen2.5:1.5b"]),
            (OllamaAvailabilityStatus.AVAILABLE, "Ready", ["qwen2.5:1.5b", "qwen3:1.7b"])
        ]):
            status1, _, _ = provider.refresh_models()
            self.assertEqual(status1, OllamaAvailabilityStatus.MODEL_NOT_INSTALLED)
            status2, _, _ = provider.refresh_models()
            self.assertEqual(status2, OllamaAvailabilityStatus.AVAILABLE)

    # --- 8. Circuit Breaker ---
    def test_circuit_breaker_activates_after_3_service_failures(self):
        provider = OllamaBrainProvider()
        with patch("urllib.request.urlopen", side_effect=Exception("Connection refused")):
            with patch.object(provider, "check_availability", return_value=(OllamaAvailabilityStatus.SERVICE_UNREACHABLE, "Unreachable", [])):
                provider.think("msg 1")
                provider.think("msg 2")
                res = provider.think("msg 3")
                self.assertFalse(res.success)
                self.assertEqual(provider.health_state.consecutive_service_failures, 3)
                self.assertTrue(provider.health_state.unavailable_until > 0)

                res_cb = provider.think("msg 4")
                self.assertEqual(res_cb.error_type, "circuit_breaker_open")

    def test_circuit_breaker_resets_on_success(self):
        provider = OllamaBrainProvider()
        provider.health_state.consecutive_service_failures = 2
        fake_response_data = json.dumps({"message": {"content": "OK"}}).encode('utf-8')

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_res = MagicMock()
            mock_res.status = 200
            mock_res.read.return_value = fake_response_data
            mock_res.__enter__.return_value = mock_res
            mock_urlopen.return_value = mock_res

            with patch.object(provider, "check_availability", return_value=(OllamaAvailabilityStatus.AVAILABLE, "Ready", ["qwen3:1.7b"])):
                res = provider.think("hello")
                self.assertTrue(res.success)
                self.assertEqual(provider.health_state.consecutive_service_failures, 0)

    # --- 9. Deterministic Direct Command Bypass ---
    def test_deterministic_commands_bypass_all_brain_providers(self):
        from core.engine import JarvisEngine

        mock_ollama = MagicMock()
        mock_groq = MagicMock()
        mock_gemini = MagicMock()

        with patch("services.brain.provider_manager.brain_manager.providers", {"ollama": mock_ollama, "groq": mock_groq, "gemini": mock_gemini}):
            with patch("os.startfile", return_value=True):
                with patch("core.engine.speech", MagicMock()):
                    with patch("core.engine.bus", MagicMock()):
                        engine = MagicMock(spec=JarvisEngine)
                        engine.current_space = None
                        engine.telegram_bot = MagicMock()
                        engine.hud = MagicMock()
                        
                        # Bind unbound route_and_execute method to mock instance
                        res_func = JarvisEngine.route_and_execute.__get__(engine, JarvisEngine)

                        commands = [
                            "open chrome",
                            "open settings",
                            "refresh app index",
                            "enable autostart",
                            "disable autostart"
                        ]
                        for cmd in commands:
                            res = res_func(cmd)
                            self.assertIsInstance(res, str)

                        self.assertEqual(mock_ollama.think.call_count, 0)
                        self.assertEqual(mock_groq.think.call_count, 0)
                        self.assertEqual(mock_gemini.think.call_count, 0)

    # --- 10. Privacy & Offline Routing ---
    def test_privacy_and_local_only_routing(self):
        manager = BrainProviderManager()

        req_private = BrainRequest(text="Summarize my notes", contains_private_data=True, cloud_allowed=False)
        route, providers, web = manager.determine_route(req_private)
        self.assertEqual(route, BrainRoute.PRIVATE_LOCAL)
        self.assertEqual(providers, ["ollama"])
        self.assertFalse(web)

        req_phrase = BrainRequest(text="keep this local and analyze this file")
        route_p, providers_p, web_p = manager.determine_route(req_phrase)
        self.assertEqual(route_p, BrainRoute.PRIVATE_LOCAL)
        self.assertEqual(providers_p, ["ollama"])

    # --- 11. UI Persistence & Config Wiring ---
    def test_config_panel_ui_save_and_reload_wiring(self):
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])

        from ui.hud.config_panel import ConfigPanel
        panel1 = ConfigPanel()

        # Set widget values
        panel1.brain_mode_combo.setCurrentText("manual")
        panel1.brain_combo.setCurrentText("groq")
        panel1.ollama_model_edit.setText("qwen3:4b")
        panel1.ollama_think_check.setChecked(False)
        panel1.ollama_ctx_combo.setCurrentText("4096")
        panel1.local_only_check.setChecked(True)

        # Save config through UI action
        panel1.save_config()

        # Destroy first panel
        panel1.deleteLater()

        # Instantiate second panel as if application restarted
        panel2 = ConfigPanel()

        # Assert widgets display saved values
        self.assertEqual(panel2.brain_mode_combo.currentText(), "manual")
        self.assertEqual(panel2.brain_combo.currentText(), "groq")
        self.assertEqual(panel2.ollama_model_edit.text(), "qwen3:4b")
        self.assertFalse(panel2.ollama_think_check.isChecked())
        self.assertEqual(panel2.ollama_ctx_combo.currentText(), "4096")
        self.assertTrue(panel2.local_only_check.isChecked())

        # Assert runtime provider payload and routing read reloaded config correctly
        provider = OllamaBrainProvider()
        payload = provider._build_payload([{"role": "user", "content": "test"}], stream=False)
        self.assertIs(payload["think"], False)
        self.assertEqual(payload["options"]["num_ctx"], 4096)

        manager = BrainProviderManager()
        _, providers, _ = manager.determine_route("test query")
        self.assertEqual(providers, ["ollama"])

        panel2.deleteLater()

        # Restore default values
        config.set("brain_mode", "smart_auto")
        config.set("brain_provider", "groq")
        config.set("ollama_model", "qwen3:1.7b")
        config.set("ollama_think", "false")
        config.set("ollama_num_ctx", "2048")
        config.set("local_only_mode", "false")

    # --- 12. Log Redaction ---
    def test_log_redaction(self):
        formatter = RedactingFormatter("%(message)s")
        record = logging.LogRecord("test", logging.INFO, "", 0, "Groq API key: gsk_123456789012345678901234", (), None)
        out = formatter.format(record)
        self.assertNotIn("gsk_123456789012345678901234", out)
        self.assertIn("gsk_***REDACTED***", out)


if __name__ == "__main__":
    unittest.main()
