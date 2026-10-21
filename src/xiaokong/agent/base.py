"""Agent contract shared by every implementation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, ClassVar, Protocol

from .events import AgentEvent


@dataclass(slots=True)
class Attachment:
    """A document the user attached to the current question."""

    name: str
    text: str


@dataclass(slots=True)
class AgentContext:
    """Everything an agent needs to answer one question.

    ``history`` excludes the system prompt and the current user message; the
    agent receives the current question separately as ``user_text``.
    """

    system_prompt: str
    history: list[dict[str, str]] = field(default_factory=list)
    attachments: list[Attachment] = field(default_factory=list)


class Tool(Protocol):
    """Minimal tool contract for future tool-calling agents."""

    name: str
    description: str

    async def run(self, **kwargs: Any) -> str:
        ...


class Agent(ABC):
    """Produces a stream of :class:`AgentEvent` for one user turn."""

    name: ClassVar[str] = "agent"

    @abstractmethod
    def stream(
        self,
        context: AgentContext,
        user_text: str,
    ) -> AsyncIterator[AgentEvent]:
        """Yield text deltas (and, later, tool events) for this turn."""

    async def close(self) -> None:  # noqa: B027 - optional hook
        """Release resources. Default implementation does nothing."""
