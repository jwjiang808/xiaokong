"""Shared HTTP helpers and errors for the upstream providers."""

from __future__ import annotations

import uuid

import httpx


class ApiError(RuntimeError):
    """Raised when an upstream LLM / ASR / TTS provider fails."""


# Stable per-process session id used by the OpenCode gateway.
OPENCODE_SESSION_ID = uuid.uuid4().hex


def join_url(base_url: str, path: str) -> str:
    base = base_url.strip().rstrip("/")
    if not base:
        raise ApiError("API Base URL 不能为空。")
    return f"{base}/{path.lstrip('/')}"


def tts_ai_root(base_url: str) -> str:
    """TTS.ai exposes its API under the host root, not under ``/v1``."""
    base = base_url.strip().rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    return base


def auth_headers(
    api_key: str,
    *,
    base_url: str = "",
    require_key: bool = True,
) -> dict[str, str]:
    key = api_key.strip()
    if require_key and not key:
        raise ApiError("请先在设置中填写对应的 API Key。")


    headers = {"Accept": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    if "opencode.ai/zen/go" in base_url:
        headers["x-opencode-session"] = OPENCODE_SESSION_ID
    return headers


def doubao_headers(resource_id: str, api_key: str) -> dict[str, str]:
    if not api_key.strip():
        raise ApiError("请先在设置中填写豆包语音 API Key。")
    return {
        "X-Api-Key": api_key.strip(),
        "X-Api-Resource-Id": resource_id.strip(),
        "X-Api-Request-Id": str(uuid.uuid4()),
        "Content-Type": "application/json",
    }


def error_message(response: httpx.Response) -> str:
    """Best-effort extraction of a readable provider error message."""
    try:
        payload = response.json()
    except ValueError:
        payload = None

    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])
        if payload.get("message"):
            return str(payload["message"])

    text = response.text.strip()
    return text[:500] if text else f"HTTP {response.status_code}"
