import os
import time
import requests
from PyQt6.QtCore import QThread, pyqtSignal
from core.logger import logger
from core.config import config

class TelegramBotService(QThread):
    message_received = pyqtSignal(str, int)  # text, chat_id
    callback_received = pyqtSignal(str, int) # callback_data, chat_id

    def __init__(self, engine):
        super().__init__()
        self.engine = engine
        self.running = False
        self.bot_token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
        self.allowed_user_id = (os.getenv("TELEGRAM_USER_ID") or "").strip()
        
        # Fallbacks
        if not self.bot_token:
            self.bot_token = config.get("telegram_bot_token", "")
        if not self.allowed_user_id:
            self.allowed_user_id = config.get("telegram_user_id", "")

        if self.allowed_user_id:
            try:
                self.allowed_user_id = int(self.allowed_user_id)
            except ValueError:
                logger.error("TELEGRAM_USER_ID is not a valid integer")
                self.allowed_user_id = None

    def run(self):
        if not self.bot_token:
            logger.warning("Telegram Bot Token is missing. Bot bridge is disabled.")
            return
        if not self.allowed_user_id:
            logger.warning("Telegram User ID is missing or invalid. Bot bridge is disabled.")
            return

        # Register slash commands programmatically at boot
        self.register_slash_commands()

        self.running = True
        offset = 0
        logger.info("Telegram Bot Service started.")

        while self.running:
            try:
                url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
                params = {"timeout": 30, "offset": offset}
                response = requests.get(url, params=params, timeout=35)
                
                if response.status_code == 401:
                    logger.error("Telegram Bot Token is invalid (Unauthorized). Service stopped.")
                    break
                elif response.status_code != 200:
                    logger.warning(f"Telegram returned status code {response.status_code}. Retrying in 10s...")
                    time.sleep(10)
                    continue

                data = response.json()
                if not data.get("ok"):
                    logger.warning(f"Telegram API response not OK: {data.get('description')}")
                    time.sleep(5)
                    continue

                for update in data.get("result", []):
                    update_id = update.get("update_id")
                    offset = update_id + 1

                    # 1. Handle inline button callback query
                    callback_query = update.get("callback_query")
                    if callback_query:
                        from_user = callback_query.get("from", {})
                        user_id = from_user.get("id")

                        if user_id != self.allowed_user_id:
                            continue

                        callback_id = callback_query.get("id")
                        callback_data = callback_query.get("data", "")
                        message = callback_query.get("message", {})
                        chat = message.get("chat", {})
                        chat_id = chat.get("id")

                        # Answer callback query to dismiss spinner in Telegram client
                        self.answer_callback_query(callback_id)

                        if callback_data and chat_id:
                            self.callback_received.emit(callback_data, chat_id)
                        continue

                    # 2. Handle normal text messages
                    message = update.get("message")
                    if not message:
                        continue

                    from_user = message.get("from", {})
                    user_id = from_user.get("id")

                    if user_id != self.allowed_user_id:
                        logger.debug(f"Silently ignoring message from unauthorized user ID: {user_id}")
                        continue

                    chat = message.get("chat", {})
                    chat_id = chat.get("id")
                    text = message.get("text", "").strip()

                    if text:
                        self.message_received.emit(text, chat_id)

            except requests.RequestException as e:
                logger.warning(f"Telegram connection error: {e}. Retrying in 15s...")
                time.sleep(15)
            except Exception as e:
                logger.error(f"Unexpected error in Telegram Bot loop: {e}", exc_info=True)
                time.sleep(5)

    def register_slash_commands(self):
        url = f"https://api.telegram.org/bot{self.bot_token}/setMyCommands"
        payload = {
            "commands": [
                {"command": "help", "description": "List what JARVIS can do via Telegram"},
                {"command": "status", "description": "Quick system status (providers, uptime)"},
                {"command": "cancel", "description": "Force-clear any pending confirmation"}
            ]
        }
        try:
            res = requests.post(url, json=payload, timeout=10)
            if res.status_code == 200:
                logger.info("Successfully registered Telegram slash commands.")
            else:
                logger.warning(f"Failed to register slash commands, status code {res.status_code}")
        except Exception as e:
            logger.error(f"Failed to register Telegram slash commands: {e}")

    def answer_callback_query(self, callback_id: str):
        url = f"https://api.telegram.org/bot{self.bot_token}/answerCallbackQuery"
        payload = {"callback_query_id": callback_id}
        try:
            requests.post(url, json=payload, timeout=10)
        except Exception as e:
            logger.error(f"Failed to answer callback query: {e}")

    def get_default_reply_markup(self):
        return {
            "keyboard": [
                [{"text": "/status"}, {"text": "/cancel"}, {"text": "/help"}]
            ],
            "resize_keyboard": True
        }

    def send_message(self, chat_id: int, text: str):
        if not self.bot_token:
            return
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "reply_markup": self.get_default_reply_markup()
        }
        try:
            requests.post(url, json=payload, timeout=10)
        except Exception as e:
            logger.error(f"Failed to send message via Telegram: {e}")

    def send_message_and_get_id(self, chat_id: int, text: str) -> int:
        if not self.bot_token:
            return None
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "reply_markup": self.get_default_reply_markup()
        }
        try:
            res = requests.post(url, json=payload, timeout=10)
            if res.status_code == 200:
                data = res.json()
                if data.get("ok"):
                    return data.get("result", {}).get("message_id")
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
        return None

    def edit_message(self, chat_id: int, message_id: int, text: str):
        if not self.bot_token or not message_id:
            return
        url = f"https://api.telegram.org/bot{self.bot_token}/editMessageText"
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text
        }
        try:
            requests.post(url, json=payload, timeout=10)
        except Exception as e:
            logger.error(f"Failed to edit message via Telegram: {e}")

    def send_confirmation_keyboard(self, chat_id: int, text: str) -> int:
        if not self.bot_token:
            return None
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "reply_markup": {
                "inline_keyboard": [
                    [
                        {"text": "✅ Confirm", "callback_data": "confirm_yes"},
                        {"text": "❌ Cancel", "callback_data": "confirm_no"}
                    ]
                ]
            }
        }
        try:
            res = requests.post(url, json=payload, timeout=10)
            if res.status_code == 200:
                data = res.json()
                if data.get("ok"):
                    return data.get("result", {}).get("message_id")
        except Exception as e:
            logger.error(f"Failed to send confirmation keyboard: {e}")
        return None

    def remove_inline_keyboard(self, chat_id: int, message_id: int):
        if not self.bot_token or not message_id:
            return
        url = f"https://api.telegram.org/bot{self.bot_token}/editMessageReplyMarkup"
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "reply_markup": {"inline_keyboard": []}
        }
        try:
            requests.post(url, json=payload, timeout=10)
        except Exception as e:
            logger.error(f"Failed to remove inline keyboard: {e}")

    def send_typing_indicator(self, chat_id: int):
        if not self.bot_token:
            return
        url = f"https://api.telegram.org/bot{self.bot_token}/sendChatAction"
        payload = {
            "chat_id": chat_id,
            "action": "typing"
        }
        try:
            requests.post(url, json=payload, timeout=10)
        except Exception as e:
            logger.error(f"Failed to send typing indicator: {e}")

    def stop(self):
        self.running = False


def notify_telegram(message: str):
    """
    Send a proactive message to the authorized user's Telegram.
    """
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN") or config.get("telegram_bot_token")
    user_id = os.getenv("TELEGRAM_USER_ID") or config.get("telegram_user_id")
    if not bot_token or not user_id:
        return
    
    try:
        user_id = int(user_id)
    except ValueError:
        return
        
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": user_id,
        "text": message
    }
    try:
        import threading
        def do_send():
            try:
                requests.post(url, json=payload, timeout=10)
            except Exception as e:
                logger.error(f"Failed to send Telegram notification: {e}")
        threading.Thread(target=do_send, daemon=True).start()
    except Exception as e:
        logger.error(f"Error starting Telegram notification thread: {e}")
