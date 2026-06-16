"""Greenhouse job source: fetch postings from public Greenhouse boards.

Greenhouse exposes a public, no-auth JSON API per company "board token":
    https://boards-api.greenhouse.io/v1/boards/<board>/jobs?content=true
"""
import html
import re

import requests

from bot.sources.base import Job, Source

API_URL = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"


def _clean_html(content: str) -> str:
    """Greenhouse 'content' is entity-escaped HTML -> return plain text.

    Order matters: unescape FIRST (&lt;p&gt; -> <p>), then strip tags, then
    collapse whitespace. Stripping before unescaping leaves escaped tags as text.
    """
    text = html.unescape(content or "")        # entities -> real chars (handles None)
    text = re.sub(r"<[^>]+>", " ", text)        # drop HTML tags
    return re.sub(r"\s+", " ", text).strip()    # collapse runs of whitespace



INTERN_TERMS = ("intern", "internship", "co-op")


def _looks_like_intern(title: str, description: str) -> bool:
    text = f"{title} {description}".lower()
    return any(re.search(rf"\b{re.escape(t)}\b", text) for t in INTERN_TERMS)


class GreenhouseSource(Source):
    """Fetches jobs from one or more public Greenhouse board tokens."""

    def __init__(self, boards: list[str]):
        self.boards = boards

    def fetch(self) -> list[Job]:
        """Fetch + normalize jobs across every configured board."""
        jobs: list[Job] = []
        for board in self.boards:
            try:
                jobs.extend(self._fetch_board(board))
            except Exception as e:
                # one dead/invalid board token must not crash the whole run
                print(f"[greenhouse] failed to fetch {board!r}: {type(e).__name__}: {e}")
        return jobs

    def _fetch_board(self, board: str) -> list[Job]:
        """Fetch + normalize a board's postings, keeping only intern-looking roles.

        (Greenhouse has no employment-type field, so we filter on the text.)
        """
        resp = requests.get(API_URL.format(board=board), timeout=10)
        resp.raise_for_status()
        raw_jobs = resp.json().get("jobs", [])   # .get(..., []) -> safe if key missing
        jobs = [self._to_job(board, raw) for raw in raw_jobs]
        return [j for j in jobs if _looks_like_intern(j.title, j.description)]

    def _to_job(self, board: str, raw: dict) -> Job:
        # Translate the Greenhouse JSON -> Job
        return Job(
            source='greenhouse',
            external_id=str(raw["id"]),
            title=raw["title"],
            company=board,
            description=_clean_html(raw.get("content")),
            url=raw["absolute_url"],
            location=(raw.get("location") or {}).get("name", ""),
            raw=raw,
        )