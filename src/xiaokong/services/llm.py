"""OpenAI-compatible chat completion client (streaming and blocking)."""

from __future__ import annotations

import json
from typing import Any

import httpx

from ..config import AppSettings
from .common import ApiError, auth_headers, error_message, join_url


async def chat_completion(
    settings: AppSettings,
    messages: list[dict[str, str]],
) -> str:
    """Blocking helper kept for agents/tools that do not need streaming."""
    parts: list[str] = []
    async for delta in stream_chat_completion(settings, messages):
        parts.append(delta)
    text = "".join(parts).strip()
    if not text:
        raise ApiError("问答接口返回了空内容。")
    return text


async def stream_chat_completion(
    settings: AppSettings,
    messages: list[dict[str, str]],
):
    """Yield text deltas from an OpenAI-compatible ``chat/completions`` API."""
    url = join_url(settings.llm_base_url, "chat/completions")
    payload: dict[str, Any] = {
        "model": settings.chat_model.strip(),
        "messages": messages,
        "temperature": 0.7,
        "stream": True,
        "thinking": {"type": "disabled"},
    }
    if not payload["model"]:
        raise ApiError("请先填写对话模型名称。")

    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream(
            "POST",
            url,
            headers=auth_headers(
                settings.llm_api_key,
                base_url=settings.llm_base_url,
            ),
            json=payload,
        ) as response:
            if response.status_code >= 400:
                await response.aread()
                raise ApiError(f"问答接口失败：{error_message(response)}")

            content_type = response.headers.get("content-type", "")
            if "text/event-stream" not in content_type:
                # Some gateways ignore ``stream`` and return one JSON body.
                raw = await response.aread()
                try:
                    data = json.loads(raw.decode("utf-8"))
                    content = data["choices"][0]["message"]["content"]
                except (ValueError, KeyError, IndexError, TypeError) as exc:
                    raise ApiError("问答接口返回了无法识别的数据。") from exc
                text = content_to_text(content)
                if text:
                    yield text
                return

            async for line in response.aiter_lines():
                line = line.strip()
                if not line or not line.startswith("data:"):
                    continue
                data_text = line[5:].strip()
                if data_text == "[DONE]":
                    return
                try:
                    data = json.loads(data_text)
                    choice = data["choices"][0]
                    delta = choice.get("delta") or {}
                    content = delta.get("content")
                except (ValueError, KeyError, IndexError, TypeError):
                    continue
                text = content_to_text(content)
                if text:
                    yield text


def content_to_text(content: Any) -> str:
    """Normalise string or list-of-parts message content to plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(item["text"])
            for item in content
            if isinstance(item, dict) and item.get("text")
        )
    return ""
