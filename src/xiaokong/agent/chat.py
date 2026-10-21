"""Default agent: one OpenAI-compatible chat completion per turn."""

from __future__ import annotations

from collections.abc import AsyncIterator

from ..config import AppSettings
from ..services.llm import stream_chat_completion
from .base import Agent, AgentContext, Attachment
from .events import AgentDone, AgentEvent, TextDelta
from .registry import register_agent


def attachment_message(attachment: Attachment) -> dict[str, str]:
    return {
        "role": "system",
        "content": (
            f"用户上传了文件《{attachment.name}》。"
            "以下是从文件中提取的内容，请结合它回答用户问题：\n\n"
            f"{attachment.text}"
        ),
    }


@register_agent("chat")
class ChatAgent(Agent):
    """Streams a normal chat completion; the current production behaviour."""

    name = "chat"

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings

    async def stream(
        self,
        context: AgentContext,
        user_text: str,
    ) -> AsyncIterator[AgentEvent]:
        messages: list[dict[str, str]] = [
            {"role": "system", "content": context.system_prompt}
        ]
        messages.extend(
            attachment_message(item) for item in context.attachments
        )
        messages.extend(context.history)
        messages.append({"role": "user", "content": user_text})

        parts: list[str] = []
        async for delta in stream_chat_completion(self._settings, messages):
            parts.append(delta)
            yield TextDelta(delta)
        yield AgentDone("".join(parts).strip())
