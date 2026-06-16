"""Keyword scoring: decide whether a job is worth alerting about."""
import re

from bot.sources.base import Job


def matches(job: Job, keywords: list[str]) -> bool:
    r"""True if any keyword appears as a WHOLE WORD in the job's title or description.

    - searches title + description (a keyword in the body counts, not just the title)
    - \b word boundaries so 'intern' doesn't match 'International'/'internal'
    - re.escape(kw) so a keyword with regex-special chars ('c++', 'ai/ml') can't
      break (or crash) the pattern
    Keywords are expected pre-lowercased; the text is lowercased here to match.
    """
    text = f"{job.title} {job.description}".lower()
    return any(re.search(rf"\b{re.escape(kw)}\b", text) for kw in keywords)