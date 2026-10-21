from __future__ import annotations

from typing import Any

from xiaokong.agent import (
    AgentContext,
    AgentDone,
    Attachment,
    ChatAgent,
    DeepAgentAdapter,
    TextDelta,
    ToolRegistry,
    available_agents,
    create_agent,
)
from xiaokong.agent import chat as chat_module
from xiaokong.agent.deep import _chunk_text
from xiaokong.config import AppSettings


def test_registry_contains_chat_and_deep() -> None:
    assert "chat" in available_agents()
    assert "deep" in available_agents()
    assert isinstance(create_agent("chat", AppSettings()), ChatAgent)
    assert isinstance(create_agent("deep", AppSettings()), DeepAgentAdapter)
    # Unknown kinds fall back to the default chat agent.
    assert isinstance(create_agent("nope", AppSettings()), ChatAgent)


async def test_chat_agent_builds_messages_and_streams(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_stream(settings, messages):
        captured["messages"] = messages
        yield "你好"
        yield "，同学"

    monkeypatch.setattr(chat_module, "stream_chat_completion", fake_stream)

    agent = ChatAgent(AppSettings())
    context = AgentContext(
        system_prompt="你是小控。",
        history=[{"role": "user", "content": "上一问"}],
        attachments=[Attachment(name="第1讲.pptx", text="课件正文")],
    )
    events = [event async for event in agent.stream(context, "这一问")]

    assert events[0] == TextDelta("你好")
    assert events[1] == TextDelta("，同学")
    assert events[-1] == AgentDone("你好，同学")

    messages = captured["messages"]
    assert messages[0] == {"role": "system", "content": "你是小控。"}
    assert "第1讲.pptx" in messages[1]["content"]
    assert messages[2] == {"role": "user", "content": "上一问"}
    assert messages[-1] == {"role": "user", "content": "这一问"}


def test_tool_registry() -> None:
    class EchoTool:
        name = "echo"
        description = "回显输入"

        async def run(self, **kwargs: Any) -> str:
            return str(kwargs.get("text", ""))

    registry = ToolRegistry()
    tool = EchoTool()
    registry.register(tool)

    assert registry.get("echo") is tool
    assert "echo" in registry
    specs = registry.specs()
    assert [spec.name for spec in specs] == ["echo"]


def test_deep_chunk_text_handles_strings_and_blocks() -> None:
    class Chunk:
        def __init__(self, content):
            self.content = content

    assert _chunk_text(Chunk("你好")) == "你好"
    blocks = [{"type": "text", "text": "你"}, {"type": "text", "text": "好"}]
    assert (
        _chunk_text(Chunk(blocks)) == "你好"
    )
    assert _chunk_text(Chunk(None)) == ""


def test_deep_agent_registers_tools_and_invalidates_graph() -> None:
    adapter = DeepAgentAdapter(AppSettings())

    class Tool:
        name = "t"
        description = "d"

        async def run(self, **kwargs):
            return ""

    adapter.register_tool(Tool())
    assert len(adapter._tools) == 1

    adapter.register_subagent({"name": "s", "description": "d"})
    assert len(adapter._subagents) == 1
