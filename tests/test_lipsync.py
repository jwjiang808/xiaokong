from __future__ import annotations

import asyncio
import io
import wave

import numpy as np

from xiaokong.speech.analysis import (
    ENVELOPE_HOP_MS,
    build_envelope,
    follow_playback,
    level_at,
)
from xiaokong.ui.robot import MOUTH_CLOSED, MOUTH_OPEN, TechRobotDoll


def make_wav(seconds: float = 0.6, rate: int = 16000) -> bytes:
    t = np.linspace(0, seconds, int(rate * seconds), endpoint=False)
    gate = (np.mod(t, 0.2) < 0.12).astype(np.float32)
    samples = (0.45 * np.sin(2 * np.pi * 440 * t) * gate * 32767).astype(np.int16)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(samples.tobytes())
    return buffer.getvalue()


class FakeDuration:
    def __init__(self, ms: int) -> None:
        self.in_milliseconds = ms


class FakePlayer:
    def __init__(self, total_ms: int) -> None:
        self.ms = 0
        self.total_ms = total_ms

    async def get_current_position(self) -> FakeDuration:
        position = FakeDuration(self.ms)
        self.ms = min(self.total_ms, self.ms + ENVELOPE_HOP_MS)
        return position


def test_envelope_has_quiet_and_loud_frames() -> None:
    envelope = build_envelope(make_wav())
    assert envelope
    assert max(envelope) > 0.5
    assert min(envelope) == 0.0


async def test_mouth_tracks_level_linearly() -> None:
    robot = TechRobotDoll()
    task = asyncio.create_task(robot._animate())
    await asyncio.sleep(0.1)
    robot.set_speaking(True)

    for level in (0.0, 0.25, 0.5, 0.75, 1.0):
        robot.set_mouth_level(level)
        await asyncio.sleep(0.12)
        expected = MOUTH_CLOSED + level * (MOUTH_OPEN - MOUTH_CLOSED)
        assert abs(robot.mouth.scale.scale_y - expected) < 0.02

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def test_follow_playback_maps_positions_and_stops() -> None:
    envelope = build_envelope(make_wav()) or [0.5] * 40
    player = FakePlayer(len(envelope) * ENVELOPE_HOP_MS)
    observed: list[float] = []

    await follow_playback(
        player=player,
        envelope=envelope,
        apply_level=observed.append,
        is_active=lambda: True,
        interval=0.001,
    )

    assert len(observed) >= len(envelope) - 2
    for index, level in enumerate(observed):
        expected = level_at(envelope, index * ENVELOPE_HOP_MS)
        assert abs(level - expected) < 1e-9


async def test_stalled_and_broken_players_exit() -> None:
    class Stalled:
        async def get_current_position(self):
            return FakeDuration(0)

    class Broken:
        async def get_current_position(self):
            raise RuntimeError("player released")

    envelope = [0.5] * 20
    for player in (Stalled(), Broken()):
        await asyncio.wait_for(
            follow_playback(
                player=player,
                envelope=envelope,
                apply_level=lambda _level: None,
                is_active=lambda: True,
                interval=0.001,
            ),
            timeout=5,
        )
