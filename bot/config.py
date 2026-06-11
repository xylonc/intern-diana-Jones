"""Configuration loaded from environment / .env.

Every tunable lives here so the rest of the code never calls os.getenv
directly. load_dotenv() reads a local .env file (gitignored) into the
process environment, keeping secrets out of the repo.
"""
import os

from dotenv import load_dotenv

load_dotenv()


def _list(name: str) -> list[str]:
    raw = os.getenv(name, "")
   
    companies_pre_stripped = raw.split(",")
    companies = []
    for s in companies_pre_stripped:
        s = s.strip()
        if s != "":
            companies.append(s)
    return companies  


TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
GREENHOUSE_BOARDS = _list("GREENHOUSE_BOARDS")
KEYWORDS = [k.lower() for k in _list("KEYWORDS")]
DB_PATH = os.getenv("DB_PATH", "jobs.db")
