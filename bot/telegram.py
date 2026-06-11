"""Telegram send wrapper: push a message to the configured chat.

Contract: send_message() either delivers the message or RAISES. It never
returns normally on failure. The pipeline relies on "returned == delivered"
for its send-then-log crash-safety, so do not swallow errors here.
"""
import requests

from bot.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

API_URL = "https://api.telegram.org/bot{token}/sendMessage"


def send_message(text: str) -> None:
    """Send `text` to the configured Telegram chat; raise on any failure."""
    url = API_URL.format(token=TELEGRAM_BOT_TOKEN)
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}

    response = requests.post(url, data=payload, timeout=10)
    response.raise_for_status()
    #raised so that if the connection breaks it will not continue to update the status