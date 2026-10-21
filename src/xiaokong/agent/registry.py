"""Agent registry, so the implementation can be swapped from settings."""

from __future__ import annotations

from collections.abc import Callable

from ..config import AppSettings
from .base import Agent

_AGENTS: dict[str, Callable[[AppSettings], Agent]] = {}


def register_agent(name: str) -> Callable[[type[Agent]], type[Agent]]:
    """Class decorator: ``@register_agent("chat")``."""

    def decorator(cls: type[Agent]) -> type[Agent]:
        _AGENTS[name] = cls
        return cls

    return decorator


def create_agent(kind: str, settings: AppSettings) -> Agent:
    """Build the configured agent, falling back to the default chat agent."""
    factory = _AGENTS.get(kind) or _AGENTS.get("chat")
    if factory is None:
        raise ValueError(f"没有可用的智能体实现：{kind!r}（也没有注册 'chat'）")
    return factory(settings)


def available_agents() -> tuple[str, ...]:
    return tuple(sorted(_AGENTS))
