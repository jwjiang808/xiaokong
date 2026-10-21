"""deepagents-backed agent (opt-in via ``agent_kind = "deep"``).

Built against ``deepagents==0.7.28``. The library returns a LangGraph
``CompiledStateGraph``; we stream it with ``stream_mode="messages"`` and turn
the message chunks into the same ``TextDelta`` events the UI already consumes.

Why this adapter exists
-----------------------
``deepagents`` provides planning, a virtual filesystem, subagents and tool
calling out of the box. None of that should leak into the UI, so everything is
hidden behind :class:`~xiaokong.agent.base.Agent`.

Reserved extension points
-------------------------
* :meth:`DeepAgentAdapter.register_tool` — add course-specific tools
  (e.g. "look up a concept in the uploaded courseware").
* :meth:`DeepAgentAdapter.register_subagent` — add declarative ``SubAgent``
  specs (e.g. a "courseware analyst" and a "quiz writer").
* ``backend`` / ``checkpointer`` parameters of ``create_deep_agent`` can be
  supplied later for persistent agent memory.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from ..config import AppSettings
from .base import Agent, AgentContext
from .chat import attachment_message
from .events import AgentDone, AgentEvent, TextDelta
from .registry import register_agent


def _chunk_text(chunk: Any) -> str:
    """Extract plain text from a LangChain message chunk."""
    content = getattr(chunk, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
        return "".join(parts)
    return ""


@register_agent("deep")
class DeepAgentAdapter(Agent):
    """Adapts ``deepagents.create_deep_agent`` to our agent contract."""

    name = "deep"

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings
        self._graph: Any = None
        self._graph_key: tuple[str, str, str] | None = None
        self._tools: list[Any] = []
        self._subagents: list[Any] = []

    # -- reserved extension points -------------------------------------
    def register_tool(self, tool: Any) -> None:
        """Add a LangChain tool; rebuilds the graph on the next turn."""
        self._tools.append(tool)
        self._graph = None

    def register_subagent(self, spec: Any) -> None:
        """Add a deepagents ``SubAgent`` spec; rebuilt on the next turn."""
        self._subagents.append(spec)
        self._graph = None

    # -- agent contract -------------------------------------------------
    def _build_model(self) -> Any:
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise RuntimeError(
                "使用 deepagents 智能体需要安装 langchain-openai。"
            ) from exc

        return ChatOpenAI(
            model=self._settings.chat_model,
            api_key=self._settings.llm_api_key,
            base_url=self._settings.llm_base_url,
            temperature=0.7,
        )

    def _ensure_graph(self, system_prompt: str) -> Any:
        key = (
            self._settings.chat_model,
            self._settings.llm_base_url,
            system_prompt,
        )
        if self._graph is not None and self._graph_key == key:
            return self._graph

        try:
            from deepagents import create_deep_agent
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise RuntimeError(
                "尚未安装 deepagents，请运行 `uv pip install deepagents==0.7.28`。"
            ) from exc

        self._graph = create_deep_agent(
            model=self._build_model(),
            tools=self._tools or None,
            system_prompt=system_prompt,
            subagents=self._subagents or None,
            name="xiaokong",
        )
        self._graph_key = key
        return self._graph

    async def stream(
        self,
        context: AgentContext,
        user_text: str,
    ) -> AsyncIterator[AgentEvent]:
        graph = self._ensure_graph(context.system_prompt)

        messages: list[dict[str, str]] = [
            attachment_message(item) for item in context.attachments
        ]
        messages.extend(context.history)
        messages.append({"role": "user", "content": user_text})

        parts: list[str] = []
        async for chunk, _metadata in graph.astream(
            {"messages": messages},
            stream_mode="messages",
        ):
            text = _chunk_text(chunk)
            if not text:
                continue
            parts.append(text)
            yield TextDelta(text)

        yield AgentDone("".join(parts).strip())
