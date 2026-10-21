"""Turn a streaming markdown reply into speakable sentence chunks.

The assistant reply arrives token by token. To avoid waiting for the whole
answer before the robot can talk, we cut the stream into sentences as soon as
each one is complete and hand them to the TTS queue one by one.
"""

from __future__ import annotations

import re
from typing import Final

# Sentence terminators. Commas are not included: cutting on every comma sounds
# choppy, so commas are only used when a chunk grows past ``max_chars``.
_HARD_ENDINGS: Final = "。！？!?；;…\n"
_SOFT_ENDINGS: Final = "，,、：:"

_FENCED_CODE = re.compile(r"```.*?```", re.DOTALL)
_DANGLING_FENCE = re.compile(r"```.*$", re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`]*)`")
_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_URL = re.compile(r"https?://\S+")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s*", re.MULTILINE)
_BULLET = re.compile(r"^\s{0,3}(?:[-*+]|\d+[.)])\s+", re.MULTILINE)
_EMPHASIS = re.compile(r"(\*\*|__|\*|_|~~)")
_SPACES = re.compile(r"[ \t\u3000]+")
_BLANK_LINES = re.compile(r"\n{2,}")


def clean_for_speech(text: str) -> str:
    """Strip markdown noise that should not be read out loud."""
    if not text:
        return ""
    cleaned = _FENCED_CODE.sub(" ", text)
    cleaned = _DANGLING_FENCE.sub(" ", cleaned)
    cleaned = _IMAGE.sub(" ", cleaned)
    cleaned = _LINK.sub(r"\1", cleaned)
    cleaned = _URL.sub(" ", cleaned)
    cleaned = _INLINE_CODE.sub(r"\1", cleaned)
    cleaned = _HEADING.sub("", cleaned)
    cleaned = _BULLET.sub("", cleaned)
    cleaned = _EMPHASIS.sub("", cleaned)
    cleaned = cleaned.replace("|", "，").replace(">", "")
    cleaned = _SPACES.sub(" ", cleaned)
    cleaned = _BLANK_LINES.sub("\n", cleaned)
    return cleaned.strip()


class SentenceSplitter:
    """Feed streamed deltas in, get complete speakable sentences out."""

    def __init__(self, min_chars: int = 2, max_chars: int = 60) -> None:
        self._buffer = ""
        self._min_chars = max(1, min_chars)
        self._max_chars = max(self._min_chars, max_chars)

    @property
    def pending(self) -> str:
        return self._buffer

    def push(self, delta: str) -> list[str]:
        if delta:
            self._buffer += delta
        chunks: list[str] = []
        while True:
            cut = self._next_cut()
            if cut is None:
                break
            piece = self._buffer[:cut]
            self._buffer = self._buffer[cut:]
            spoken = clean_for_speech(piece)
            if spoken:
                chunks.append(spoken)
        return chunks

    def flush(self) -> list[str]:
        remainder = clean_for_speech(self._buffer)
        self._buffer = ""
        return [remainder] if remainder else []

    def _next_cut(self) -> int | None:
        buffer = self._buffer
        if not buffer:
            return None

        # Scan outside code fences so a fence body is never spoken. Only cut
        # outside a fence, which keeps the leftover buffer starting outside one
        # too, so a rescan from index 0 always sees the right fence state.
        in_fence = False
        index = 0
        length = len(buffer)
        while index < length:
            if buffer.startswith("```", index):
                in_fence = not in_fence
                index += 3
                continue
            if not in_fence and buffer[index] in _HARD_ENDINGS:
                return index + 1
            index += 1

        if in_fence or length < self._max_chars:
            return None

        # Too long without a terminator: break at the last natural pause.
        window = buffer[: self._max_chars]
        for index in range(len(window) - 1, self._min_chars - 1, -1):
            if window[index] in _SOFT_ENDINGS:
                return index + 1
        for index in range(len(window) - 1, self._min_chars - 1, -1):
            if window[index] in " \n":
                return index + 1
        return self._max_chars
