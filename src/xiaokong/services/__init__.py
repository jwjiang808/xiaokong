"""Upstream provider clients (LLM, ASR, TTS)."""

from .asr import transcribe_audio
from .asr_stream import DoubaoStreamingASR, DoubaoStreamingError
from .common import ApiError
from .llm import chat_completion, stream_chat_completion
from .tts import synthesize_speech

__all__ = [
    "ApiError",
    "DoubaoStreamingASR",
    "DoubaoStreamingError",
    "chat_completion",
    "stream_chat_completion",
    "synthesize_speech",
    "transcribe_audio",
]
