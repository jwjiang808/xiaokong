"""Audio clip playback with lip-sync and caption progress."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from typing import TYPE_CHECKING

import flet as ft
import flet_audio as fta

from .analysis import ENVELOPE_HOP_MS, build_envelope, follow_playback

if TYPE_CHECKING:
    from ..ui.robot import TechRobotDoll


class ClipPlayer:
    """Plays one TTS clip at a time and reports playback progress.

    ``flet_audio`` must receive the MP3 as **bytes**: a temp file path never
    fires ``on_loaded`` and playback stays silent.
    """

    def __init__(self, page: ft.Page, robot: TechRobotDoll) -> None:
        self._page = page
        self._robot = robot
        self._audio: fta.Audio | None = None
        self._generation = 0

    @property
    def current(self) -> fta.Audio | None:
        return self._audio

    async def play(
        self,
        audio_bytes: bytes,
        *,
        wait: bool = False,
        on_progress: Callable[[float], None] | None = None,
    ) -> None:
        # Decode off the event loop and build the loudness curve for lip-sync.
        envelope = await asyncio.to_thread(build_envelope, audio_bytes)

        self._generation += 1
        generation = self._generation
        await self._release_current()

        audio_ready = asyncio.Event()
        finished = asyncio.Event()

        def handle_state(event: fta.AudioStateChangeEvent) -> None:
            if event.state == fta.AudioState.PLAYING:
                self._robot.set_speaking(True)
            elif event.state in (
                fta.AudioState.COMPLETED,
                fta.AudioState.STOPPED,
                fta.AudioState.PAUSED,
                fta.AudioState.DISPOSED,
            ):
                # The caller owns the speaking state so queued sentences do not
                # blink back to idle between clips.
                finished.set()

        player = fta.Audio(
            src=audio_bytes,
            release_mode=fta.ReleaseMode.STOP,
            volume=1.0,
            on_loaded=lambda _e: audio_ready.set(),
            on_state_change=handle_state,
        )
        self._audio = player
        self._page.services.append(player)
        self._page.update()
        await asyncio.wait_for(audio_ready.wait(), timeout=15)
        self._robot.set_speaking(True)

        if envelope:
            async def follow_audio() -> None:
                try:
                    await follow_playback(
                        player=player,
                        envelope=envelope,
                        apply_level=self._robot.set_mouth_level,
                        on_progress=on_progress,
                        is_active=lambda: (
                            not finished.is_set()
                            and generation == self._generation
                        ),
                    )
                finally:
                    if generation == self._generation:
                        self._robot.clear_mouth_level()

            self._page.run_task(follow_audio)

        try:
            await asyncio.wait_for(player.play(), timeout=10)
        except Exception:
            self._robot.clear_mouth_level()
            raise

        if not wait:
            return

        timeout = (
            len(envelope) * ENVELOPE_HOP_MS / 1000 + 10
            if envelope
            else 600
        )
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(finished.wait(), timeout=timeout)

    async def stop(self) -> None:
        """Stop whatever is playing right now."""
        self._generation += 1
        await self._release_current()
        self._robot.set_speaking(False)
        self._robot.clear_mouth_level()

    async def _release_current(self) -> None:
        player = self._audio
        self._audio = None
        if player is None:
            return
        self._robot.clear_mouth_level()
        with contextlib.suppress(Exception):
            await asyncio.wait_for(player.release(), timeout=2)
        with contextlib.suppress(Exception):
            self._page.services.remove(player)
