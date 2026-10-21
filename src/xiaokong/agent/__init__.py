"""Agent layer: the only place that talks to a model.

Adding a new agent later means: subclass :class:`Agent`, decorate it with
``@register_agent("name")``, and set ``agent_kind`` in settings. The UI keeps
consuming ``AgentEvent`` objects and does not change.
"""

from .base import Agent, AgentContext, Attachment, Tool
from .chat import ChatAgent  # imported for its registration side effect
from .deep import DeepAgentAdapter  # imported for its registration side effect
from .events import AgentDone, AgentEvent, TextDelta, ToolCall, ToolResult
from .registry import available_agents, create_agent, register_agent
from .tools import ToolRegistry, ToolSpec

__all__ = [
    "Agent",
    "AgentContext",
    "AgentDone",
    "AgentEvent",
    "Attachment",
    "ChatAgent",
    "DeepAgentAdapter",
    "TextDelta",
    "Tool",
    "ToolCall",
    "ToolRegistry",
    "ToolResult",
    "ToolSpec",
    "available_agents",
    "create_agent",
    "register_agent",
]
