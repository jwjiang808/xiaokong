"""Tool registry skeleton for future tool-calling agents.

Nothing registers a tool yet, but the shape is in place: an agent can look up
the tools available for a turn, emit ``ToolCall`` events, run a tool and feed
the ``ToolResult`` back into the model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .base import Tool


@dataclass(slots=True)
class ToolSpec:
    """Provider-neutral description of a tool."""

    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if not tool.name:
            raise ValueError("工具必须有 name")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def specs(self) -> list[ToolSpec]:
        return [
            ToolSpec(name=tool.name, description=tool.description)
            for tool in self._tools.values()
        ]

    def __contains__(self, name: object) -> bool:
        return name in self._tools
