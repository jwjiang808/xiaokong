"""后端接口调用。"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator

import httpx

BACKEND_URL = os.getenv("XIAOKONG_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")


class BackendError(RuntimeError):
    pass


async def chat(messages: list[dict[str, str]]) -> AsyncIterator[str]:
    """调用 /chat，逐个 yield 文本增量。"""
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream(
            "POST",
            f"{BACKEND_URL}/chat",
            json={"messages": messages},
        ) as response:
            if response.status_code >= 400:
                body = (await response.aread()).decode("utf-8", "replace")
                raise BackendError(f"后端 /chat 失败 {response.status_code}: {body}")

            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    return
                payload = json.loads(data)
                if "error" in payload:
                    raise BackendError(payload["error"])
                yield payload["text"]


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
