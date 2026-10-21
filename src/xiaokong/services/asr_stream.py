from __future__ import annotations

import asyncio
import contextlib
import gzip
import json
import struct
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import websockets

DOUBAO_ASR_STREAM_URL = (
    "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async"
)

MSG_FULL_CLIENT_REQUEST = 0b0001
MSG_AUDIO_ONLY_REQUEST = 0b0010
MSG_FULL_SERVER_RESPONSE = 0b1001
MSG_ERROR = 0b1111

FLAG_NO_SEQUENCE = 0b0000
FLAG_POSITIVE_SEQUENCE = 0b0001
FLAG_LAST_NO_SEQUENCE = 0b0010
FLAG_NEGATIVE_SEQUENCE = 0b0011

SERIALIZATION_JSON = 0b0001
SERIALIZATION_RAW = 0b0000
COMPRESSION_GZIP = 0b0001
COMPRESSION_NONE = 0b0000


class DoubaoStreamingError(RuntimeError):
    pass


def _build_frame(
    message_type: int,
    flags: int,
    *,
    serialization: int,
    compression: int,
    sequence: int | None = None,
    payload: bytes = b"",
) -> bytes:
    frame = bytearray(
        [
            0x11,
            (message_type << 4) | flags,
            (serialization << 4) | compression,
            0x00,
        ]
    )
    if sequence is not None:
        frame.extend(struct.pack(">i", sequence))
    frame.extend(struct.pack(">I", len(payload)))
    frame.extend(payload)
    return bytes(frame)


def _parse_frame(data: bytes) -> tuple[int, int, dict[str, Any] | None]:
    if len(data) < 4:
        raise DoubaoStreamingError("豆包流式 ASR 返回了无效数据。")

    header_size = (data[0] & 0x0F) * 4
    message_type = data[1] >> 4
    flags = data[1] & 0x0F
    serialization = data[2] >> 4
    compression = data[2] & 0x0F
    position = header_size

    if flags in (FLAG_POSITIVE_SEQUENCE, FLAG_NEGATIVE_SEQUENCE):
        position += 4

    if message_type == MSG_ERROR:
        if len(data) < position + 8:
            raise DoubaoStreamingError("豆包流式 ASR 返回错误帧。")
        error_code = struct.unpack(">I", data[position : position + 4])[0]
        position += 4
        payload_size = struct.unpack(">I", data[position : position + 4])[0]
        position += 4
        payload = data[position : position + payload_size]
        if compression == COMPRESSION_GZIP and payload:
            with contextlib.suppress(OSError):
                payload = gzip.decompress(payload)
        message = payload.decode("utf-8", errors="replace")
        raise DoubaoStreamingError(
            f"豆包流式 ASR 错误 {error_code}: {message}"
        )

    if message_type != MSG_FULL_SERVER_RESPONSE:
        return message_type, flags, None
    if len(data) < position + 4:
        raise DoubaoStreamingError("豆包流式 ASR 返回了不完整数据。")

    payload_size = struct.unpack(">I", data[position : position + 4])[0]
    position += 4
    payload = data[position : position + payload_size]

    if compression == COMPRESSION_GZIP and payload:
        payload = gzip.decompress(payload)

    if serialization != SERIALIZATION_JSON or not payload:
        return message_type, flags, None

    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DoubaoStreamingError("豆包流式 ASR 返回了无效 JSON。") from exc
    return message_type, flags, decoded


class DoubaoStreamingASR:
    def __init__(
        self,
        *,
        api_key: str,
        resource_id: str,
        on_partial: Callable[[str], Awaitable[None]],
        sample_rate: int = 16000,
    ) -> None:
        self.api_key = api_key.strip()
        self.resource_id = resource_id.strip()
        self.on_partial = on_partial
        self.sample_rate = sample_rate

        self._websocket: Any = None
        self._send_queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._sender_task: asyncio.Task[None] | None = None
        self._receiver_task: asyncio.Task[None] | None = None
        self._final_event = asyncio.Event()
        self._final_text = ""
        self._partial_text = ""
        self._error: Exception | None = None

    async def start(self) -> None:
        if not self.api_key:
            raise DoubaoStreamingError("请先填写豆包语音 API Key。")
        if not self.resource_id:
            raise DoubaoStreamingError("请先填写豆包流式 ASR Resource ID。")

        headers = {
            "X-Api-Key": self.api_key,
            "X-Api-Resource-Id": self.resource_id,
            "X-Api-Connect-Id": str(uuid.uuid4()),
            "X-Api-Request-Id": str(uuid.uuid4()),
        }
        try:
            self._websocket = await websockets.connect(
                DOUBAO_ASR_STREAM_URL,
                additional_headers=headers,
                max_size=16 * 1024 * 1024,
                open_timeout=15,
                ping_interval=20,
                ping_timeout=20,
                proxy=None,
            )
        except Exception as exc:
            raise DoubaoStreamingError(f"豆包流式 ASR 连接失败：{exc}") from exc

        init_payload = {
            "user": {"uid": "qa_assistant"},
            "audio": {
                "format": "pcm",
                "codec": "raw",
                "rate": self.sample_rate,
                "bits": 16,
                "channel": 1,
            },
            "request": {
                "model_name": "bigmodel",
                "enable_itn": True,
                "enable_punc": True,
                "enable_ddc": True,
                "show_utterances": True,
                "result_type": "full",
                "enable_nonstream": False,
            },
        }
        init_frame = _build_frame(
            MSG_FULL_CLIENT_REQUEST,
            FLAG_POSITIVE_SEQUENCE,
            serialization=SERIALIZATION_JSON,
            compression=COMPRESSION_GZIP,
            sequence=1,
            payload=gzip.compress(
                json.dumps(init_payload, ensure_ascii=False).encode("utf-8")
            ),
        )
        await self._websocket.send(init_frame)

        self._receiver_task = asyncio.create_task(self._receiver())
        self._sender_task = asyncio.create_task(self._sender())

    async def send_audio(self, chunk: bytes) -> None:
        if chunk:
            await self._send_queue.put(bytes(chunk))

    async def finish(self, timeout: float = 20) -> str:
        await self._send_queue.put(None)
        if self._sender_task:
            await self._sender_task
        try:
            await asyncio.wait_for(self._final_event.wait(), timeout=timeout)
        except TimeoutError:
            if not self._partial_text:
                raise DoubaoStreamingError("豆包流式 ASR 等待结果超时。") from None

        if self._error and not self._partial_text:
            raise self._error
        return self._final_text or self._partial_text

    async def cancel(self) -> None:
        await self._send_queue.put(None)
        for task in (self._sender_task, self._receiver_task):
            if task and not task.done():
                task.cancel()
        for task in (self._sender_task, self._receiver_task):
            if task:
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
        await self._close()

    async def _sender(self) -> None:
        sequence = 2
        try:
            while True:
                chunk = await self._send_queue.get()
                is_last = chunk is None
                flags = FLAG_NEGATIVE_SEQUENCE if is_last else FLAG_POSITIVE_SEQUENCE
                frame_sequence = -sequence if is_last else sequence
                payload = gzip.compress(b"" if chunk is None else chunk)
                frame = _build_frame(
                    MSG_AUDIO_ONLY_REQUEST,
                    flags,
                    serialization=SERIALIZATION_RAW,
                    compression=COMPRESSION_GZIP,
                    sequence=frame_sequence,
                    payload=payload,
                )
                await self._websocket.send(frame)
                if is_last:
                    return
                sequence += 1
        except Exception as exc:
            self._error = DoubaoStreamingError(f"豆包流式 ASR 发送失败：{exc}")
            self._final_event.set()

    async def _receiver(self) -> None:
        try:
            async for message in self._websocket:
                if not isinstance(message, bytes):
                    continue
                message_type, flags, payload = _parse_frame(message)
                if message_type != MSG_FULL_SERVER_RESPONSE or not payload:
                    continue

                result = payload.get("result")
                if not isinstance(result, dict):
                    continue

                text = str(result.get("text") or "").strip()
                if text and text != self._partial_text:
                    self._partial_text = text
                    await self.on_partial(text)

                if result.get("is_final") or flags & FLAG_LAST_NO_SEQUENCE:
                    self._final_text = text
                    self._final_event.set()
                    return
        except Exception as exc:
            self._error = DoubaoStreamingError(f"豆包流式 ASR 接收失败：{exc}")
            self._final_event.set()
        finally:
            self._final_event.set()

    async def _close(self) -> None:
        if self._websocket is not None:
            with contextlib.suppress(Exception):
                await self._websocket.close()
            self._websocket = None
