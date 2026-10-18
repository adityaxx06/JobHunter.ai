"""Provider-independent AI interface (Phase 1 skeleton).

Future match_engine / trust_engine must depend on this ABC only,
so Gemini can be swapped for another provider later.
No API calls here.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class AIRequest:
    """Generic AI request (prompt + structured-output hint)."""

    prompt: str
    schema_name: str = ""


@dataclass
class AIResponse:
    """Generic AI response (raw text only for now)."""

    text: str = ""


class BaseAIProvider(ABC):
    """Common contract all providers (Gemini, future others) implement."""

    name: str = "base"

    @abstractmethod
    def configure(self) -> None:
        """Read env config only. Must NOT make network calls in Phase 1."""
        raise NotImplementedError

    @abstractmethod
    def generate(self, request: AIRequest) -> AIResponse:
        """Generate completion. NOT wired in Phase 1 (raise until Phase 6)."""
        raise NotImplementedError
