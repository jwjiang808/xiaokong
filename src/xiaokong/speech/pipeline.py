"""Speak a streaming reply sentence by sentence.

The reply text arrives in small deltas. Each completed sentence is queued for
TTS immediately, so the robot starts talking while the rest of the answer is
still being generated. The worker also synthesizes the *next* sentence while
the current one is playing, which removes the silence between sentences.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from typing import Final

from .text import SentenceSplitter

SENTENCE_END: Final = None


class SpeechPipeline:
    """Queue streamed text into sentence chunks and speak them in order."""

    def __init__(
        self,
        *,
        synthesize: Callable[[str], Awaitable[bytes]],
        play_clip: Callable[[bytes], Awaitable[None]],
        on_start: Callable[[], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        on_finish: Callable[[], None] | None = None,
    ) -> None:
        self._synthesize = synthesize
        self._play_clip = play_clip
        self._on_start = on_start
        self._on_error = on_error
        self._on_finish = on_finish
        self._splitter = SentenceSplitter()
        self._queue: asyncio.Queue[str | None] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None
        self._closed = False
        self.spoken: list[str] = []

    @property
    def finished(self) -> bool:
        return self._task is not None and self._task.done()

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    def push(self, delta: str) -> None:
        """Feed a streamed text delta; complete sentences are queued at once."""
        if self._closed or not delta:
            return
        for sentence in self._splitter.push(delta):
            self._queue.put_nowait(sentence)

    def close(self) -> None:
        """No more text: speak the tail and stop the worker."""
        if self._closed:
            return
        self._closed = True
        for sentence in self._splitter.flush():
            self._queue.put_nowait(sentence)
        self._queue.put_nowait(SENTENCE_END)

    async def wait(self) -> None:
        if self._task is None:
            return
        with contextlib.suppress(asyncio.CancelledError):
            await self._task

    def cancel(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()

    async def _run(self) -> None:
        queue = self._queue
        next_audio: asyncio.Task[bytes] | None = None
        play_task: asyncio.Task[None] | None = None
        started = False
        try:
            text = await queue.get()
            while text is not None:
                if next_audio is None:
                    next_audio = asyncio.create_task(self._synthesize(text))
                try:
                    audio = await next_audio
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    next_audio = None
                    if self._on_error is not None:
                        self._on_error(str(exc))
                    text = await queue.get()
                    continue
                next_audio = None

                if not started and self._on_start is not None:
                    started = True
                    self._on_start()
                self.spoken.append(text)

                play_task = asyncio.create_task(self._play_clip(audio))
                # Line up the next sentence while this one is playing.
                text = await queue.get()
                if text is not None:
                    next_audio = asyncio.create_task(self._synthesize(text))
                with contextlib.suppress(Exception):
                    await play_task
                play_task = None
        finally:
            for pending in (next_audio, play_task):
                if pending is not None:
                    pending.cancel()
            if self._on_finish is not None:
                self._on_finish()
