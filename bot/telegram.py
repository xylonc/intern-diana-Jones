"""Telegram wrapper: send messages, and read incoming updates (self-registration).

send_message: deliver the message or RAISE (the pipeline relies on "returned == delivered").
get_updates: poll incoming messages so users can register themselves via /start, /keyword.
"""
import requests

from bot.config import TELEGRAM_BOT_TOKEN

API_BASE = "https://api.telegram.org/bot{token}"


def send_message(text: str, chat_id: str) -> None:
    """Send `text` to the given Telegram chat id; raise on any failure."""
    url = API_BASE.format(token=TELEGRAM_BOT_TOKEN) + "/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    response = requests.post(url, data=payload, timeout=10)
    response.raise_for_status()


def get_updates(offset: int = 0) -> list[dict]:
    """Fetch incoming updates (messages) with update_id >= offset.

    Passing offset = last_update_id + 1 acknowledges everything before it, so the
    same message isn't processed twice. timeout=0 = short poll (don't long-poll in cron).
    """
    url = API_BASE.format(token=TELEGRAM_BOT_TOKEN) + "/getUpdates"
    response = requests.get(url, params={"offset": offset, "timeout": 0}, timeout=15)
    response.raise_for_status()
    return response.json().get("result", [])