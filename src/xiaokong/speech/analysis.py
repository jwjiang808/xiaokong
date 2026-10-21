"""Turn decoded speech audio into a loudness envelope for lip-sync.

The robot mouth is driven by a normalized RMS curve measured from the real
TTS audio, so a louder syllable opens the mouth wider and silence closes it.
Decoding uses ``miniaudio`` (bundled MP3/WAV/OGG/FLAC decoders, no external
binaries) and the maths uses ``numpy``. Both imports are intentionally
top-level so PyInstaller picks them up when building the single-file EXE.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Final

try:  # pragma: no cover - exercised indirectly
    import miniaudio
except Exception:  # pragma: no cover
    miniaudio = None  # type: ignore[assignment]

try:  # pragma: no cover - exercised indirectly
    import numpy as np
except Exception:  # pragma: no cover
    np = None  # type: ignore[assignment]


ENVELOPE_HOP_MS: Final = 45
_TARGET_RATE: Final = 16000
# Below this normalized loudness the mouth is treated as fully closed; the
# rest of the range is stretched so quiet speech still moves the mouth.
_NOISE_GATE: Final = 0.06


def envelope_available() -> bool:
    return miniaudio is not None and np is not None


def build_envelope(
    audio_bytes: bytes | None,
    hop_ms: int = ENVELOPE_HOP_MS,
) -> list[float] | None:
    """Return one loudness value (0.0-1.0) per ``hop_ms`` of audio.

    Returns ``None`` when the audio cannot be decoded so callers can fall back
    to a synthetic mouth motion instead of failing.
    """
    if not audio_bytes or miniaudio is None or np is None:
        return None

    try:
        decoded = miniaudio.decode(
            audio_bytes,
            output_format=miniaudio.SampleFormat.SIGNED16,
            nchannels=1,
            sample_rate=_TARGET_RATE,
        )
    except Exception:
        return None

    try:
        samples = np.frombuffer(bytes(decoded.samples), dtype=np.int16)
        if samples.size == 0:
            return None
        rate = int(decoded.sample_rate or _TARGET_RATE)
        hop = max(1, int(rate * max(1, hop_ms) / 1000))
        usable = (samples.size // hop) * hop
        if usable == 0:
            return None

        frames = samples[:usable].astype(np.float32).reshape(-1, hop)
        rms = np.sqrt(np.mean(frames * frames, axis=1))

        # Normalize against the 95th percentile rather than the absolute peak
        # so one loud transient does not flatten the whole animation.
        reference = float(np.percentile(rms, 95))
        if reference <= 0:
            reference = float(rms.max())
        if reference <= 0:
            return None

        normalized = np.clip(rms / reference, 0.0, 1.0)
        gated = np.clip(
            (normalized - _NOISE_GATE) / (1.0 - _NOISE_GATE),
            0.0,
            1.0,
        )
        return [float(value) for value in gated]
    except Exception:
        return None


def level_at(envelope: list[float] | None, position_ms: float) -> float:
    """Look up the loudness for a playback position in milliseconds."""
    if not envelope:
        return 0.0
    index = int(max(0.0, position_ms) // ENVELOPE_HOP_MS)
    if index >= len(envelope):
        index = len(envelope) - 1
    return envelope[index]


async def follow_playback(
    *,
    player,
    envelope: list[float],
    apply_level: Callable[[float], None],
    is_active: Callable[[], bool],
    on_progress: Callable[[float], None] | None = None,
    interval: float = 0.035,
    trailing_ms: int = 1500,
) -> None:
    """Drive ``apply_level`` from the player's real playback position.

    Stops when ``is_active`` turns false, when the clip is replaced, when the
    position stops advancing (paused/released player), or just after the
    envelope ends. Position read errors end the loop quietly so the caller can
    fall back to the synthetic mouth motion.
    """
    if not envelope:
        return

    max_ms = len(envelope) * ENVELOPE_HOP_MS + trailing_ms
    total_ms = len(envelope) * ENVELOPE_HOP_MS
    stall_limit = int(trailing_ms / ENVELOPE_HOP_MS) + 4
    last_ms = -1.0
    stalled = 0

    while is_active():
        try:
            position = await player.get_current_position()
        except Exception:
            return
        if position is None:
            return

        current_ms = float(position.in_milliseconds)
        if current_ms > max_ms:
            return
        if current_ms <= last_ms:
            stalled += 1
            if stalled > stall_limit:
                return
        else:
            stalled = 0
        last_ms = current_ms

        apply_level(level_at(envelope, current_ms))
        if on_progress is not None and total_ms > 0:
            on_progress(min(1.0, current_ms / total_ms))
        await asyncio.sleep(interval)
