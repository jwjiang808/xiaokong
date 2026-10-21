"""语音接口：TTS 合成 + ASR 识别（豆包 / OpenAI 兼容）。"""

from __future__ import annotations

import base64
import json
import uuid

import httpx

from .config import settings

DOUBAO_TTS_URL = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
DOUBAO_ASR_URL = (
    "https://openspeech.bytedance.com/api/v3/auc/bigmodel/recognize/flash"
)


def _join(base: str, path: str) -> str:
    return f"{base.rstrip('/')}/{path.lstrip('/')}"


def _doubao_headers(resource_id: str) -> dict[str, str]:
    return {
        "X-Api-Key": settings.doubao_api_key,
        "X-Api-Resource-Id": resource_id,
        "X-Api-Request-Id": str(uuid.uuid4()),
        "Content-Type": "application/json",
    }


async def synthesize(text: str) -> bytes:
    """文字转 MP3 字节。"""
    if settings.tts_provider == "doubao":
        return await _doubao_tts(text)
    return await _openai_tts(text)


async def transcribe(audio: bytes, filename: str) -> str:
    """录音文件转文字。"""
    if settings.asr_provider == "doubao":
        return await _doubao_asr(audio, filename)
    return await _openai_asr(audio, filename)


async def _doubao_tts(text: str) -> bytes:
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
            headers=_doubao_headers(settings.doubao_tts_resource_id),
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


async def _openai_tts(text: str) -> bytes:
    url = _join(settings.tts_base_url, "audio/speech")
    async with httpx.AsyncClient(timeout=180) as client:
        response = await client.post(
            url,
            headers={"Authorization": f"Bearer {settings.tts_api_key}"},
            json={
                "model": settings.tts_model,
                "voice": settings.tts_voice,
                "input": text,
                "response_format": "mp3",
            },
        )
    response.raise_for_status()
    return response.content


async def _doubao_asr(audio: bytes, filename: str) -> str:
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else "wav"
    payload = {
        "user": {"uid": "xiaokong"},
        "audio": {
            "format": suffix,
            "data": base64.b64encode(audio).decode("ascii"),
        },
        "request": {
            "model_name": settings.doubao_asr_model,
            "enable_punc": True,
            "enable_itn": True,
        },
    }
    headers = _doubao_headers(settings.doubao_asr_resource_id)
    headers["X-Api-Sequence"] = "-1"

    async with httpx.AsyncClient(timeout=180) as client:
        response = await client.post(DOUBAO_ASR_URL, headers=headers, json=payload)

    code = response.headers.get("x-api-status-code", "")
    if response.status_code >= 400 or code not in ("", "20000000"):
        message = response.headers.get("x-api-message", response.text[:300])
        raise RuntimeError(f"豆包 ASR 失败：{code} {message}")
    return str(response.json()["result"]["text"]).strip()


async def _openai_asr(audio: bytes, filename: str) -> str:
    url = _join(settings.asr_base_url, "audio/transcriptions")
    async with httpx.AsyncClient(timeout=180) as client:
        response = await client.post(
            url,
            headers={"Authorization": f"Bearer {settings.asr_api_key}"},
            data={"model": settings.asr_model},
            files={"file": (filename, audio, "audio/wav")},
        )
    response.raise_for_status()
    return str(response.json().get("text", "")).strip()
