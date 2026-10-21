from __future__ import annotations

import asyncio
import time

from xiaokong.speech.pipeline import SpeechPipeline

CONFIG = {"synth": 0.45, "play": 0.90}


def make_pipeline(events: list[tuple[str, str, float]], *, play_scale=1.0):
    async def synthesize(text: str) -> bytes:
        events.append(("synth_start", text, time.perf_counter()))
        await asyncio.sleep(CONFIG["synth"])
        events.append(("synth_end", text, time.perf_counter()))
        return text.encode("utf-8")

    async def play_clip(audio: bytes) -> None:
        text = audio.decode("utf-8")
        events.append(("play_start", text, time.perf_counter()))
        await asyncio.sleep(CONFIG["play"] * play_scale)
        events.append(("play_end", text, time.perf_counter()))

    return SpeechPipeline(synthesize=synthesize, play_clip=play_clip)


async def test_sentences_play_in_order_before_stream_finishes() -> None:
    events: list[tuple[str, str, float]] = []
    pipeline = make_pipeline(events)
    pipeline.start()

    reply = "第一句话。第二句话。第三句话。"
    for char in reply:
        pipeline.push(char)
        await asyncio.sleep(0.06)
    stream_done = time.perf_counter()
    pipeline.close()
    await pipeline.wait()

    order = [text for kind, text, _ in events if kind == "play_start"]
    assert order == ["第一句话。", "第二句话。", "第三句话。"]

    first_play = next(t for k, _, t in events if k == "play_start")
    assert first_play < stream_done - 0.2, "speech must start before the reply ends"

    starts = {text: t for k, text, t in events if k == "play_start"}
    ends = {text: t for k, text, t in events if k == "play_end"}
    gaps = [
        starts["第二句话。"] - ends["第一句话。"],
        starts["第三句话。"] - ends["第二句话。"],
    ]
    # Without lookahead each gap would be roughly the synthesis time (0.45 s).
    assert all(gap < 0.25 for gap in gaps)


async def test_cancel_stops_remaining_sentences() -> None:
    events: list[tuple[str, str, float]] = []
    pipeline = make_pipeline(events, play_scale=6.0)
    pipeline.start()
    pipeline.push("第一句。")
    await asyncio.sleep(0.35)
    pipeline.push("第二句。第三句。")
    pipeline.close()
    await asyncio.sleep(0.5)
    pipeline.cancel()
    await pipeline.wait()

    played = [text for kind, text, _ in events if kind == "play_start"]
    assert played == ["第一句。"]


async def test_wait_is_safe_without_start() -> None:
    pipeline = SpeechPipeline(synthesize=_unused, play_clip=_unused)
    await pipeline.wait()


async def _unused(*_args, **_kwargs):
    raise AssertionError("should not be called")
