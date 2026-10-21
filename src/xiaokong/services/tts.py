"""Text-to-speech providers: Doubao, TTS.ai and OpenAI-compatible APIs."""

from __future__ import annotations

import asyncio
import base64
import json
from typing import Any

import httpx

from ..config import AppSettings
from .common import (
    ApiError,
    auth_headers,
    doubao_headers,
    error_message,
    join_url,
    tts_ai_root,
)

DOUBAO_TTS_URL = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"


async def synthesize_speech(settings: AppSettings, text: str) -> bytes:
    """Return MP3 bytes for ``text`` using the configured TTS provider."""
    if settings.tts_provider == "doubao":
        return await _synthesize_doubao(settings, text)
    if settings.tts_provider == "tts_ai":
        return await _synthesize_tts_ai(settings, text)

    url = join_url(settings.tts_base_url, "audio/speech")
    payload: dict[str, Any] = {
        "model": settings.tts_model.strip(),
        "voice": settings.tts_voice.strip(),
        "input": text,
        "response_format": "mp3",
    }
    if not payload["model"]:
        raise ApiError("请先填写 TTS 模型名称。")
    if not payload["voice"]:
        raise ApiError("请先填写 TTS 音色。")

    async with httpx.AsyncClient(timeout=180) as client:
        response = await client.post(
            url,
            headers=auth_headers(
                settings.tts_api_key,
                base_url=settings.tts_base_url,
            ),
            json=payload,
        )

    if response.status_code >= 400:
        raise ApiError(f"TTS 接口失败：{error_message(response)}")
    if not response.content:
        raise ApiError("TTS 接口返回了空音频。")
    return response.content


async def _synthesize_tts_ai(settings: AppSettings, text: str) -> bytes:
    root = tts_ai_root(settings.tts_base_url)
    url = join_url(root, "v1/tts/")
    payload: dict[str, Any] = {
        "model": settings.tts_model.strip(),
        "voice": settings.tts_voice.strip(),
        "text": text,
        "format": "mp3",
    }
    if not payload["model"]:
        raise ApiError("请先填写 TTS 模型名称。")
    if not payload["voice"]:
        raise ApiError("请先填写 TTS 音色。")

    async with httpx.AsyncClient(timeout=180) as client:
        response = await client.post(
            url,
            headers=auth_headers(
                settings.tts_api_key,
                require_key=False,
            ),
            json=payload,
        )
        if response.status_code >= 400:
            raise ApiError(f"TTS 接口失败：{error_message(response)}")

        content_type = response.headers.get("content-type", "")
        if content_type.startswith("audio/") or response.content.startswith(b"ID3"):
            return response.content

        try:
            data = response.json()
        except ValueError as exc:
            raise ApiError("TTS 接口返回了无法识别的数据。") from exc

        result_url = data.get("result_url")
        status = data.get("status")
        uuid_value = data.get("uuid")

        if not result_url and uuid_value:
            poll_url = join_url(root, "v1/speech/results/")
            for _ in range(45):
                if status == "completed":
                    break
                if status == "failed":
                    raise ApiError(str(data.get("error") or "TTS 生成失败。"))
                await asyncio.sleep(0.7)
                poll_response = await client.get(
                    poll_url,
                    params={"uuid": uuid_value},
                )
                if poll_response.status_code >= 400:
                    raise ApiError(
                        f"TTS 结果查询失败：{error_message(poll_response)}"
                    )
                data = poll_response.json()
                status = data.get("status")
                result_url = data.get("result_url")

        if not result_url:
            raise ApiError("TTS 接口没有返回音频地址。")

        audio_url = (
            result_url
            if str(result_url).startswith(("http://", "https://"))
            else join_url(root, str(result_url))
        )
        audio_response = await client.get(audio_url)
        if audio_response.status_code >= 400:
            raise ApiError(f"TTS 音频下载失败：{error_message(audio_response)}")
        if not audio_response.content:
            raise ApiError("TTS 音频为空。")
        return audio_response.content


async def _synthesize_doubao(settings: AppSettings, text: str) -> bytes:
    if not settings.doubao_tts_resource_id.strip():
        raise ApiError("请先填写豆包 TTS Resource ID。")
    if not settings.doubao_tts_voice.strip():
        raise ApiError("请先填写豆包 TTS 音色。")

    payload = {
        "user": {"uid": "xiaokong"},
        "req_params": {
            "text": text,
            "speaker": settings.doubao_tts_voice.strip(),
            "audio_params": {"format": "mp3", "sample_rate": 24000},
        },
    }

    async with httpx.AsyncClient(timeout=180) as client:
        response = await client.post(
            DOUBAO_TTS_URL,
            headers=doubao_headers(
                settings.doubao_tts_resource_id,
                settings.doubao_api_key,
            ),
            json=payload,
        )

    if response.status_code >= 400:
        raise ApiError(f"豆包 TTS 接口失败：{error_message(response)}")

    audio_parts: list[bytes] = []
    completed = False
    decoder = json.JSONDecoder()
    raw_text = response.content.decode("utf-8", errors="replace")
    position = 0

    while position < len(raw_text):
        while position < len(raw_text) and raw_text[position].isspace():
            position += 1
        if position >= len(raw_text):
            break
        try:
            frame, position = decoder.raw_decode(raw_text, position)
        except json.JSONDecodeError as exc:
            raise ApiError("豆包 TTS 返回了无法识别的数据。") from exc

        if not isinstance(frame, dict):
            raise ApiError("豆包 TTS 返回了无效数据。")

        code = frame.get("code")
        if code == 20000000:
            completed = True
            break
        if code != 0:
            raise ApiError(f"豆包 TTS 生成失败：{code} {frame.get('message', '')}")

        encoded = frame.get("data")
        if not encoded:
            continue
        try:
            audio_parts.append(base64.b64decode(encoded, validate=True))
        except (ValueError, TypeError) as exc:
            raise ApiError("豆包 TTS 返回了无效音频。") from exc

    if not completed:
        raise ApiError("豆包 TTS 未返回完成标记。")
    audio = b"".join(audio_parts)
    if not audio:
        raise ApiError("豆包 TTS 返回了空音频。")
    return audio
