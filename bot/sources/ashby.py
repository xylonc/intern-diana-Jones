"""Ashby job source: fetch postings from public Ashby job boards.

Public, no-auth JSON API per board name:
    https://api.ashbyhq.com/posting-api/job-board/<name>   -> {"jobs": [...]}
"""
import requests

from bot.sources.base import Job, Source, is_intern_type

API_URL = "https://api.ashbyhq.com/posting-api/job-board/{name}"


class AshbySource(Source):
    """Fetches jobs from one or more public Ashby job board names."""

    def __init__(self, boards: list[str]):
        self.boards = boards

    def fetch(self) -> list[Job]:
        jobs: list[Job] = []
        for board in self.boards:
            try:
                jobs.extend(self._fetch_board(board))
            except Exception as e:
                # one dead/invalid board name must not crash the whole run
                print(f"[ashby] failed to fetch {board!r}: {type(e).__name__}: {e}")
        return jobs

    def _fetch_board(self, board: str) -> list[Job]:
        resp = requests.get(API_URL.format(name=board), timeout=10)
        resp.raise_for_status()
        raw_jobs = resp.json().get("jobs", [])
        jobs = [self._to_job(board, raw) for raw in raw_jobs]
        # keep only intern / short-term roles (structured employment type)
        return [j for j in jobs if is_intern_type(j.employment_type)]

    def _to_job(self, board: str, raw: dict) -> Job:
        return Job(
            source="ashby",
            external_id=str(raw["id"]),
            title=raw["title"],
            company=board,
            url=raw["jobUrl"],
            location=raw.get("location") or "",
            description=raw.get("descriptionPlain", ""),
            employment_type=raw.get("employmentType", ""),
            raw=raw,
        )