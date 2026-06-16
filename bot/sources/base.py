import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


# compare after normalizing to letters-only lowercase ("full-time"->"fulltime").
INTERN_TYPES = {"intern", "internship", "contract", "parttime", "temporary"}


def is_intern_type(employment_type: str) -> bool:
    """True if this employment type is intern/short-term (spelling-agnostic).
    """
    normalized = re.sub(r"[^a-z]", "", (employment_type or "").lower())
    return normalized in INTERN_TYPES


@dataclass
class Job:
    source: str
    external_id: str
    title: str
    company: str = ""
    url: str = ""
    location: str = ""
    description: str = ""
    employment_type: str = ""
    raw: dict = field(default_factory=dict)


class Source(ABC):
    @abstractmethod
    def fetch(self) -> list[Job]:
        pass