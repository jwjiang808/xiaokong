"""Streaming speech: sentence splitting, synthesis queue, playback, lip-sync."""

from .analysis import ENVELOPE_HOP_MS, build_envelope, follow_playback, level_at
from .pipeline import SpeechPipeline
from .player import ClipPlayer
from .text import SentenceSplitter, clean_for_speech

__all__ = [
    "ClipPlayer",
    "ENVELOPE_HOP_MS",
    "SentenceSplitter",
    "SpeechPipeline",
    "build_envelope",
    "clean_for_speech",
    "follow_playback",
    "level_at",
]
