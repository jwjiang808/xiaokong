"""边生成边朗读：切句 → 调后端 TTS → 播放，按真实播放进度驱动字幕。"""

from __future__ import annotations

import asyncio
import contextlib
import re

import flet_audio as fta
import miniaudio
import numpy as np

from . import api

ENDINGS = "。！？!?；;\n"
_MARKUP = re.compile(
    r"(```.*?```|`[^`]*`|\*\*|__|!\[[^\]]*\]\([^)]*\)|https?://\S+)",
    re.S,
)


def clean(text: str) -> str:
    """去掉不该念出来的 Markdown / 代码 / 链接。"""
    return _MARKUP.sub("", text).strip()


def build_envelope(audio: bytes) -> list[float]:
    """按 45ms 一帧算归一化音量，用于嘴型。"""
    decoded = miniaudio.decode(
        audio,
        output_format=miniaudio.SampleFormat.SIGNED16,
        nchannels=1,
        sample_rate=16000,
    )
    samples = np.frombuffer(bytes(decoded.samples), dtype=np.int16).astype(np.float32)
    hop = int(16000 * 0.045)
    if samples.size < hop:
        return []
    frames = samples[: samples.size // hop * hop].reshape(-1, hop)
    rms = np.sqrt(np.mean(frames * frames, axis=1))
    peak = float(np.percentile(rms, 95))
    if peak <= 0:
        return []
    return [float(min(1.0, value / peak)) for value in rms]


class SpeechQueue:
    """当前句播放时预取下一句；字幕进度来自真实播放位置。"""

    def __init__(self, page, robot, on_finish) -> None:
        self.page = page
        self.robot = robot
        self.on_finish = on_finish
        self.buffer = ""
        self.queue: asyncio.Queue[str | None] = asyncio.Queue()
        self.spoken: list[str] = []
        self.audio: fta.Audio | None = None
        self.task = page.run_task(self._run)

    def push(self, delta: str) -> None:
        self.buffer += delta
        while any(end in self.buffer for end in ENDINGS):
            index = min(self.buffer.index(end) for end in ENDINGS if end in self.buffer)
            sentence, self.buffer = self.buffer[: index + 1], self.buffer[index + 1 :]
            if text := clean(sentence):
                self.queue.put_nowait(text)

    def close(self) -> None:
        if text := clean(self.buffer):
            self.queue.put_nowait(text)
        self.buffer = ""
        self.queue.put_nowait(None)

    def cancel(self) -> None:
        if self.task and not self.task.done():
            self.task.cancel()
        if self.audio is not None:
            self.page.run_task(self.audio.release)
        self.robot.set_speaking(False)

    async def _run(self) -> None:
        try:
            sentence = await self.queue.get()
            while sentence is not None:
                audio = await api.tts(sentence)
                self.spoken.append(sentence)
                await self._play(sentence, audio)
                sentence = await self.queue.get()
        finally:
            self.on_finish()

    async def _play(self, sentence: str, audio: bytes) -> None:
        finished = asyncio.Event()

        def on_state(event: fta.AudioStateChangeEvent) -> None:
            if event.state in (
                fta.AudioState.COMPLETED,
                fta.AudioState.STOPPED,
                fta.AudioState.DISPOSED,
            ):
                finished.set()

        player = fta.Audio(
            src=audio,
            release_mode=fta.ReleaseMode.STOP,
            on_state_change=on_state,
        )
        self.audio = player
        self.page.services.append(player)
        self.page.update()
        self.robot.set_speaking(True)
        await player.play()

        envelope = build_envelope(audio)
        previous = sum(len(item) for item in self.spoken[:-1])
        total_ms = len(envelope) * 45

        async def follow() -> None:
            try:
                while not finished.is_set():
                    position = await player.get_current_position()
                    if position is None:
                        break
                    ms = position.in_milliseconds
                    if envelope:
                        index = min(len(envelope) - 1, ms // 45)
                        self.robot.set_mouth_level(envelope[index])
                    if total_ms:
                        ratio = min(1.0, ms / total_ms)
                        self.robot.set_read_spoken(
                            previous + round(len(sentence) * ratio)
                        )
                    await asyncio.sleep(0.04)
            finally:
                self.robot.clear_mouth_level()

        self.page.run_task(follow)
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(finished.wait(), timeout=120)
        self.robot.set_read_spoken(previous + len(sentence))

        with contextlib.suppress(Exception):
            await asyncio.wait_for(player.release(), timeout=2)
        with contextlib.suppress(Exception):
            self.page.services.remove(player)
        self.audio = None
