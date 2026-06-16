
"""Lever job source: fetch postings from public Lever boards.

Public, no-auth JSON API per company token:
    https://api.lever.co/v0/postings/<company>?mode=json   -> a JSON array
"""
import requests

from bot.sources.base import Job, Source, is_intern_type

API_URL = "https://api.lever.co/v0/postings/{company}?mode=json"


class LeverSource(Source):
    """Fetches jobs from one or more public Lever company tokens."""

    def __init__(self, companies: list[str]):
        self.companies = companies

    def fetch(self) -> list[Job]:
        jobs: list[Job] = []
        for company in self.companies:
            try:
                jobs.extend(self._fetch_company(company))
            except Exception as e:
                # one dead/invalid token must not crash the whole run
                print(f"[lever] failed to fetch {company!r}: {type(e).__name__}: {e}")
        return jobs

    def _fetch_company(self, company: str) -> list[Job]:
        resp = requests.get(API_URL.format(company=company), timeout=10)
        resp.raise_for_status()
        postings = resp.json()   # Lever returns a bare JSON array
        jobs = [self._to_job(company, raw) for raw in postings]
        # keep only intern / short-term roles (structured employment type)
        return [j for j in jobs if is_intern_type(j.employment_type)]

    def _to_job(self, company: str, raw: dict) -> Job:
        categories = raw.get("categories") or {}
        return Job(
            source="lever",
            external_id=str(raw["id"]),
            title=raw["text"],
            company=company,
            url=raw["hostedUrl"],
            location=categories.get("location", ""),
            description=raw.get("descriptionPlain", ""),
            employment_type=categories.get("commitment", ""),
            raw=raw,
        )