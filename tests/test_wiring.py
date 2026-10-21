"""Regression guards for two subtle Flet behaviours.

1. The recorder only streams when the client sees ``on_stream``; Flet's
   ``invoke_method`` does not flush pending properties, so ``update()`` is
   mandatory before ``start_recording``.
2. ``flet_audio`` must receive the MP3 as bytes; a temp-file path never fires
   ``on_loaded`` and playback stays silent.
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "xiaokong"


def test_asr_streaming_wiring_order() -> None:
    source = (SRC / "ui" / "app.py").read_text(encoding="utf-8")

    assign = source.index("self.recorder.on_stream = self.handle_stream_chunk")
    update = source.index("self.recorder.update()", assign)
    start = source.index("await self.recorder.start_recording(", update)
    assert assign < update < start

    assert "if not started:" in source, "start_recording result must be checked"


def test_audio_is_handed_to_flet_as_bytes() -> None:
    source = (SRC / "speech" / "player.py").read_text(encoding="utf-8")

    assert "src=audio_bytes" in source
    assert "src=str(" not in source
    assert "qa_assistant_tts_" not in source

    append = source.index("self._page.services.append(player)")
    update = source.index("self._page.update()", append)
    play = source.index("await asyncio.wait_for(player.play()", update)
    assert append < update < play
