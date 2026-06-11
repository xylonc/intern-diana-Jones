"""Greenhouse job source: fetch postings from public Greenhouse boards.

Greenhouse exposes a public, no-auth JSON API per company "board token":
    https://boards-api.greenhouse.io/v1/boards/<board>/jobs?content=true
"""
import requests

from bot.sources.base import Job, Source

API_URL = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"


class GreenhouseSource(Source):
    """Fetches jobs from one or more public Greenhouse board tokens."""

    def __init__(self, boards: list[str]):
        self.boards = boards

    def fetch(self) -> list[Job]:
        """Fetch + normalize jobs across every configured board."""
        jobs: list[Job] = []
        for board in self.boards:
            jobs.extend(self._fetch_board(board))
        return jobs

    def _fetch_board(self, board: str) -> list[Job]:
        """Fetch + normalize all postings from a single board token."""
        resp = requests.get(API_URL.format(board=board), timeout=10)
        resp.raise_for_status()                 
        raw_jobs = resp.json().get("jobs", [])   # .get(..., []) -> safe if key missing
        return [self._to_job(board, raw) for raw in raw_jobs]

    def _to_job(self, board: str, raw: dict) -> Job:
        #Translate the GREENHOUSE JSON -> Job 
        job = Job(
            source='greenhouse', 
            external_id=str(raw["id"]), 
            title=raw["title"], 
            company=board , 
            url=raw["absolute_url"], 
            location=(raw.get("location") or {}).get("name",""), raw=raw
            )
        return job
