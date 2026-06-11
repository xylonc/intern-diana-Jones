"""Keyword scoring: decide whether a job is worth alerting about."""
from bot.sources.base import Job


def matches(job: Job, keywords: list[str]) -> bool:
    """Return True if the job matches any of the keywords.
    """
    text = job.title.lower()
    return any(kw in text for kw in keywords)
