from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Job:
    source: str
    external_id: str
    title: str
    company: str = ""
    url: str = ""
    location: str = ""
    description: str = ""
    raw: dict = field(default_factory=dict)


class Source(ABC):
    @abstractmethod
    def fetch(self) -> list[Job]:
        pass
