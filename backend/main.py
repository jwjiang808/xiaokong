"""小控后端接口。

启动：
    python -m backend.main
接口：
    GET  /health
    POST /chat   流式返回 SSE
    POST /tts    返回 MP3
    POST /asr    返回识别文字
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from .agent import build_agent
from .audio import synthesize, transcribe

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("xiaokong.api")

agent = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global agent
    log.info("starting backend, building deep agent...")
    agent = build_agent()
    log.info("deep agent ready")
    yield
    log.info("backend stopped")


app = FastAPI(title="小控 API", lifespan=lifespan)


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[Message]


class TTSRequest(BaseModel):
    text: str


def chunk_text(chunk) -> str:
    """从 LangChain 消息块里取出纯文本。"""
    content = getattr(chunk, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(item.get("text", ""))
            for item in content
            if isinstance(item, dict)
        )
    return ""


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/chat")
async def chat(request: ChatRequest):
    messages = [message.model_dump() for message in request.messages]
    log.info("chat request: %d messages", len(messages))

    async def event_stream():
        total = 0
        try:
            async for chunk, _metadata in agent.astream(
                {"messages": messages},
                stream_mode="messages",
            ):
                text = chunk_text(chunk)
                if not text:
                    continue
                total += len(text)
                payload = json.dumps({"text": text}, ensure_ascii=False)
                yield f"data: {payload}\n\n"
            log.info("chat done: %d chars", total)
        except Exception as exc:
            log.exception("chat failed")
            payload = json.dumps({"error": str(exc)}, ensure_ascii=False)
            yield f"data: {payload}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/tts")
async def tts(request: TTSRequest):
    log.info("tts request: %d chars", len(request.text))
    audio = await synthesize(request.text)
    log.info("tts done: %d bytes", len(audio))
    return Response(content=audio, media_type="audio/mpeg")


@app.post("/asr")
async def asr(file: UploadFile = File(...)):
    audio = await file.read()
    log.info("asr request: %s %d bytes", file.filename, len(audio))
    text = await transcribe(audio, file.filename or "audio.wav")
    log.info("asr done: %d chars", len(text))
    return {"text": text}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
