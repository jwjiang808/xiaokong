"""Events emitted by an agent while it produces a reply.

The UI consumes only these events, so swapping the current direct-LLM
implementation for a tool-calling agent later does not touch the UI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True, frozen=True)
class TextDelta:
    """A chunk of assistant text, ready to display and speak."""

    text: str


@dataclass(slots=True, frozen=True)
class ToolCall:
    """The agent wants to run a tool (reserved for tool-calling agents)."""

    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class ToolResult:
    """Outcome of a tool run (reserved for tool-calling agents)."""

    name: str
    ok: bool
    content: str


@dataclass(slots=True, frozen=True)
class AgentDone:
    """Final reply text; ``text`` is the full, trimmed answer."""

    text: str


AgentEvent = TextDelta | ToolCall | ToolResult | AgentDone
