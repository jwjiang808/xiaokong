"""后端接口调用。"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from typing import Any

import httpx

BACKEND_URL = os.getenv("XIAOKONG_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")


class BackendError(RuntimeError):
    pass


async def chat(
    messages: list[dict[str, object]],
    conversation_id: str,
    display_text: str,
) -> AsyncIterator[dict[str, Any]]:
    """调用 /chat，逐个 yield 结构化事件。"""
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream(
            "POST",
            f"{BACKEND_URL}/chat",
            json={
                "messages": messages,
                "conversation_id": conversation_id,
                "display_text": display_text,
            },
        ) as response:
            if response.status_code >= 400:
                body = (await response.aread()).decode("utf-8", "replace")
                raise BackendError(f"后端 /chat 失败 {response.status_code}: {body}")

            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                payload = json.loads(data)
                if payload.get("type") == "error":
                    raise BackendError(payload["error"])
                yield payload
                if payload.get("type") == "done":
                    return


async def list_conversations() -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(f"{BACKEND_URL}/conversations")
    if response.status_code >= 400:
        raise BackendError(f"读取会话列表失败: {response.text[:300]}")
    return response.json()["items"]


async def get_conversation(conversation_id: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.get(f"{BACKEND_URL}/conversations/{conversation_id}")
    if response.status_code >= 400:
        raise BackendError(f"读取会话失败: {response.text[:300]}")
    return response.json()


async def tts(text: str) -> bytes:
    async with httpx.AsyncClient(timeout=180) as client:
        response = await client.post(f"{BACKEND_URL}/tts", json={"text": text})
    if response.status_code >= 400:
        raise BackendError(f"后端 /tts 失败: {response.text[:300]}")
    return response.content


async def asr(audio: bytes, filename: str) -> str:
    async with httpx.AsyncClient(timeout=180) as client:
        response = await client.post(
            f"{BACKEND_URL}/asr",
            files={"file": (filename, audio, "audio/wav")},
        )
    if response.status_code >= 400:
        raise BackendError(f"后端 /asr 失败: {response.text[:300]}")
    return response.json()["text"]
