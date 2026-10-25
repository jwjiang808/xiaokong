"""语音：豆包 TTS + 豆包流式 ASR。"""

from __future__ import annotations

import base64
import io
import json
import uuid
import wave

import httpx

from backend.asr_doubao import DoubaoStreamingASR
from backend.config import settings

DOUBAO_TTS_URL = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"


def _headers(resource_id: str) -> dict[str, str]:
    return {
        "X-Api-Key": settings.doubao_api_key,
        "X-Api-Resource-Id": resource_id,
        "X-Api-Request-Id": str(uuid.uuid4()),
        "Content-Type": "application/json",
    }


async def synthesize(text: str) -> bytes:
    """豆包 TTS：文字 → MP3 字节。"""
    payload = {
        "user": {"uid": "xiaokong"},
        "req_params": {
            "text": text,
            "speaker": settings.doubao_tts_voice,
            "audio_params": {"format": "mp3", "sample_rate": 24000},
        },
    }
    async with httpx.AsyncClient(timeout=180) as client:
        response = await client.post(
            DOUBAO_TTS_URL,
            headers=_headers(settings.doubao_tts_resource_id),
            json=payload,
        )
    response.raise_for_status()

    audio = bytearray()
    decoder = json.JSONDecoder()
    raw = response.content.decode("utf-8", errors="replace")
    position = 0
    while position < len(raw):
        while position < len(raw) and raw[position].isspace():
            position += 1
        if position >= len(raw):
            break
        frame, position = decoder.raw_decode(raw, position)
        if frame.get("code") == 20000000:
            break
        if frame.get("code") != 0:
            raise RuntimeError(f"豆包 TTS 失败：{frame.get('message')}")
        if frame.get("data"):
            audio.extend(base64.b64decode(frame["data"]))
    if not audio:
        raise RuntimeError("豆包 TTS 返回空音频")
    return bytes(audio)


async def _ignore_partial(_text: str) -> None:
    return None


async def transcribe(audio: bytes, _filename: str) -> str:
    """豆包流式 ASR（sauc）：把录音分块送进去，返回最终文字。"""
    with wave.open(io.BytesIO(audio), "rb") as wav:
        pcm = wav.readframes(wav.getnframes())
        rate = wav.getframerate()

    session = DoubaoStreamingASR(
        api_key=settings.doubao_api_key,
        resource_id=settings.doubao_asr_resource_id,
        on_partial=_ignore_partial,
        sample_rate=rate,
        model=settings.doubao_asr_model,
    )
    await session.start()
    try:
        for offset in range(0, len(pcm), 16000):
            await session.send_audio(pcm[offset : offset + 16000])
        return await session.finish()
    finally:
        await session.cancel()
