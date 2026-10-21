"""Batch speech-to-text providers: Doubao, TTS.ai and OpenAI-compatible APIs."""

from __future__ import annotations

import asyncio
import base64
from pathlib import Path

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

DOUBAO_ASR_URL = (
    "https://openspeech.bytedance.com/api/v3/auc/bigmodel/recognize/flash"
)
DOUBAO_ASR_SUBMIT_URL = (
    "https://openspeech.bytedance.com/api/v3/auc/bigmodel/submit"
)
DOUBAO_ASR_QUERY_URL = (
    "https://openspeech.bytedance.com/api/v3/auc/bigmodel/query"
)


async def transcribe_audio(settings: AppSettings, audio_path: Path) -> str:
    """Transcribe a recorded WAV file using the configured ASR provider."""
    if settings.asr_provider == "doubao":
        return await _transcribe_doubao(settings, audio_path)

    if settings.asr_provider == "tts_ai":
        url = join_url(tts_ai_root(settings.asr_base_url), "v1/stt/")
    else:
        url = join_url(settings.asr_base_url, "audio/transcriptions")

    data = {"model": settings.asr_model.strip()}
    if not data["model"]:
        raise ApiError("请先填写 ASR 模型名称。")

    async with httpx.AsyncClient(timeout=180) as client:
        with audio_path.open("rb") as audio_file:
            response = await client.post(
                url,
                headers=auth_headers(
                    settings.asr_api_key,
                    base_url=settings.asr_base_url,
                ),
                data=data,
                files={
                    "file": (audio_path.name, audio_file, "audio/wav"),
                },
            )

    if response.status_code >= 400:
        raise ApiError(f"ASR 接口失败：{error_message(response)}")

    try:
        text = response.json().get("text", "")
    except (ValueError, AttributeError) as exc:
        raise ApiError("ASR 接口返回了无法识别的数据。") from exc

    text = str(text).strip()
    if not text:
        raise ApiError("没有识别到语音内容。")
    return text


async def _transcribe_doubao(settings: AppSettings, audio_path: Path) -> str:
    resource_id = settings.doubao_asr_resource_id.strip()
    if resource_id == "volc.bigasr.auc_turbo":
        return await _transcribe_doubao_flash(settings, audio_path)
    return await _transcribe_doubao_standard(settings, audio_path)


async def _transcribe_doubao_standard(
    settings: AppSettings,
    audio_path: Path,
) -> str:
    resource_id = settings.doubao_asr_resource_id.strip()
    audio_bytes = await asyncio.to_thread(audio_path.read_bytes)
    audio_format = audio_path.suffix.lstrip(".").lower() or "wav"
    payload = {
        "user": {"uid": "xiaokong"},
        "audio": {
            "format": audio_format,
            "data": base64.b64encode(audio_bytes).decode("ascii"),
        },
        "request": {
            "model_name": settings.doubao_asr_model.strip(),
            "enable_punc": True,
            "enable_itn": True,
        },
    }
    submit_headers = doubao_headers(resource_id, settings.doubao_api_key)
    submit_headers["X-Api-Sequence"] = "-1"

    async with httpx.AsyncClient(timeout=180) as client:
        submit = await client.post(
            DOUBAO_ASR_SUBMIT_URL,
            headers=submit_headers,
            json=payload,
        )
        raise_doubao_asr_error(submit)

        try:
            submit_data = submit.json()
        except ValueError as exc:
            raise ApiError("豆包 ASR 提交任务返回了无法识别的数据。") from exc

        task_id = (
            submit_data.get("task_id")
            or submit_data.get("id")
            or submit_headers["X-Api-Request-Id"]
        )
        query_headers = {
            "X-Api-Key": settings.doubao_api_key.strip(),
            "X-Api-Resource-Id": resource_id,
            "X-Api-Request-Id": str(task_id),
            "Content-Type": "application/json",
        }

        for _ in range(60):
            query = await client.post(
                DOUBAO_ASR_QUERY_URL,
                headers=query_headers,
                json={},
            )
            query_code = query.headers.get("x-api-status-code", "")
            if query_code in {"20000001", "20000002"}:
                await asyncio.sleep(0.8)
                continue
            raise_doubao_asr_error(query)
            try:
                text = query.json()["result"]["text"]
            except (ValueError, KeyError, TypeError) as exc:
                raise ApiError("豆包 ASR 返回了无法识别的数据。") from exc
            text = str(text).strip()
            if not text:
                raise ApiError("没有识别到语音内容。")
            return text

    raise ApiError("豆包 ASR 等待结果超时。")


async def _transcribe_doubao_flash(
    settings: AppSettings,
    audio_path: Path,
) -> str:
    if not settings.doubao_asr_resource_id.strip():
        raise ApiError("请先填写豆包 ASR Resource ID。")
    if not settings.doubao_asr_model.strip():
        raise ApiError("请先填写豆包 ASR 模型名。")

    audio_bytes = await asyncio.to_thread(audio_path.read_bytes)
    audio_format = audio_path.suffix.lstrip(".").lower() or "wav"
    payload = {
        "user": {"uid": "xiaokong"},
        "audio": {
            "format": audio_format,
            "data": base64.b64encode(audio_bytes).decode("ascii"),
        },
        "request": {
            "model_name": settings.doubao_asr_model.strip(),
            "enable_punc": True,
            "enable_itn": True,
        },
    }
    headers = doubao_headers(
        settings.doubao_asr_resource_id,
        settings.doubao_api_key,
    )
    headers["X-Api-Sequence"] = "-1"

    async with httpx.AsyncClient(timeout=180) as client:
        response = await client.post(DOUBAO_ASR_URL, headers=headers, json=payload)

    raise_doubao_asr_error(response)

    try:
        text = response.json()["result"]["text"]
    except (ValueError, KeyError, TypeError) as exc:
        raise ApiError("豆包 ASR 返回了无法识别的数据。") from exc

    text = str(text).strip()
    if not text:
        raise ApiError("没有识别到语音内容。")
    return text


def raise_doubao_asr_error(response: httpx.Response) -> None:
    status_code = response.headers.get("x-api-status-code", "")
    status_message = response.headers.get("x-api-message", "")
    if response.status_code >= 400:
        raise ApiError(
            f"豆包 ASR 接口失败：HTTP {response.status_code} "
            f"{status_message or error_message(response)}"
        )
    if status_code == "20000003":
        raise ApiError("没有识别到语音内容。")
    if status_code and status_code != "20000000":
        raise ApiError(
            f"豆包 ASR 接口失败：{status_code} "
            f"{status_message or error_message(response)}"
        )
