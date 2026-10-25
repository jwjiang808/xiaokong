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

import asyncio
import json
import sys
from contextlib import asynccontextmanager
from pathlib import Path, PurePosixPath
from typing import Any

import uvicorn
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage
from loguru import logger
from pydantic import BaseModel

# 允许直接运行 `python backend/main.py`（任意工作目录）。
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.logging_setup import setup_logging  # noqa: E402
from backend.agent import build_agent  # noqa: E402
from backend.audio import synthesize, transcribe  # noqa: E402
from backend import history  # noqa: E402

setup_logging()

agent = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global agent
    logger.info("starting backend, building deep agent...")
    db_path = history.init_db()
    logger.info("history database: {}", db_path)
    agent = build_agent()
    logger.info("deep agent ready")
    yield
    logger.info("backend stopped")


app = FastAPI(title="小控 API", lifespan=lifespan)


class Message(BaseModel):
    role: str
    content: str | list[dict[str, Any]]


class ChatRequest(BaseModel):
    messages: list[Message]
    conversation_id: str | None = None
    display_text: str | None = None


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


def compact(value: object, limit: int = 160) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def log_text(value: object, limit: int = 6000) -> str:
    text = str(value or "")
    return text if len(text) <= limit else text[:limit] + f"\n… [截断，共 {len(text)} 字符]"


def ui_detail(value: object, limit: int = 1200) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "\n\n… 已截断预览；完整内容已保存到 SQLite。"


def tool_input_text(name: str, args: dict[str, Any]) -> str:
    if name == "execute" and args.get("command"):
        return str(args["command"])
    return json.dumps(args, ensure_ascii=False, indent=2, default=str)


def describe_tool(name: str, args: dict[str, Any]) -> tuple[str, str, str]:
    """Return kind, title and quiet detail for the front-end step row."""
    file_path = str(args.get("file_path") or args.get("path") or "")
    if name == "read_file" and file_path.startswith("/skills/"):
        skill = PurePosixPath(file_path).parent.name
        return "skill", "读取技能", skill
    if name == "read_file":
        return "read", "读取文件", file_path or "文件"
    if name in {"write_file", "edit_file"}:
        return "write", "修改文件", file_path or "文件"
    if name == "ls":
        return "read", "查看目录", file_path or "/"
    if name == "glob":
        return "search", "查找文件", compact(args.get("pattern"), 100)
    if name == "grep":
        return "search", "搜索内容", compact(args.get("pattern"), 100)
    if name == "execute":
        return "shell", "运行命令", compact(args.get("command"), 120)
    if name == "task":
        return "task", "分派子任务", compact(args.get("description"), 120)
    if name == "publish_project":
        return "publish", "发布项目", compact(args.get("project"), 100)
    return "tool", name.replace("_", " ").title(), compact(args, 120)


def tool_failed(content: str) -> bool:
    value = content.strip()
    if value.lower().startswith(("error", "traceback", "failed")):
        return True
    return "\nExit code: " in value and "\nExit code: 0" not in value


def sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/conversations")
async def conversations() -> dict:
    return {"items": history.list_conversations()}


@app.get("/conversations/{conversation_id}")
async def conversation(conversation_id: str) -> dict:
    item = history.get_conversation(conversation_id)
    if item is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return item


@app.post("/chat")
async def chat(request: ChatRequest):
    messages = [message.model_dump() for message in request.messages]
    logger.info("chat request: {} messages", len(messages))
    last_user = next(
        (message for message in reversed(messages) if message.get("role") == "user"),
        {"content": ""},
    )
    user_content = last_user.get("content", "")
    logger.info(
        "user input:\n{}",
        log_text(history.content_text(user_content), 6000),
    )

    run_id = None
    try:
        conversation_id, run_id = history.start_run(
            request.conversation_id or "",
            user_content,
            [last_user],
            request.display_text,
        )
        logger.info(
            "history run started: conversation={} run={}",
            conversation_id,
            run_id,
        )
    except Exception:
        logger.exception("history run could not be created")

    async def event_stream():
        nonlocal run_id
        total = 0
        phase_step = None
        phase_id = None
        tools: dict[str, dict[str, str]] = {}
        stored_text_steps: set[str] = set()
        assistant_parts: list[str] = []
        sequence = 0
        final_status = "completed"
        final_error = None

        def emit(
            event: dict[str, Any],
            *,
            store: bool = False,
            stored: dict[str, Any] | None = None,
        ) -> str:
            nonlocal sequence
            if store and run_id:
                try:
                    history.record_step(run_id, sequence, stored or event)
                    sequence += 1
                except Exception:
                    logger.exception("history step could not be saved")
            return sse(event)

        try:
            async for mode, data in agent.astream(
                {"messages": messages},
                stream_mode=["messages", "updates"],
            ):
                if mode == "updates":
                    for update in data.values():
                        if not isinstance(update, dict):
                            continue
                        for message in update.get("messages", []):
                            if isinstance(message, AIMessage):
                                model_text = chunk_text(message)
                                step_key = f"model-{phase_step or message.id}"
                                if model_text and step_key not in stored_text_steps:
                                    stored_text_steps.add(step_key)
                                    if run_id:
                                        try:
                                            history.record_message_block(
                                                run_id,
                                                sequence,
                                                step_key,
                                                model_text,
                                            )
                                            sequence += 1
                                        except Exception:
                                            logger.exception(
                                                "history message block could not be saved"
                                            )
                            for call in getattr(message, "tool_calls", None) or []:
                                call_id = call.get("id")
                                if not call_id or call_id in tools:
                                    continue
                                name = call.get("name") or "tool"
                                args = call.get("args") or {}
                                kind, title, detail = describe_tool(name, args)
                                tools[call_id] = {
                                    "name": name,
                                    "kind": kind,
                                    "title": title,
                                    "detail": detail,
                                }
                                input_text = tool_input_text(name, args)
                                logger.info(
                                    "tool start: {} {}\n{}",
                                    name,
                                    detail,
                                    log_text(input_text, 3000),
                                )
                                if phase_id:
                                    yield emit(
                                        {
                                            "type": "step",
                                            "id": phase_id,
                                            "status": "done",
                                        },
                                        store=True,
                                    )
                                    phase_id = None
                                event = {
                                    "type": "tool",
                                    "id": call_id,
                                    "status": "running",
                                    "content": ui_detail(input_text),
                                    **tools[call_id],
                                }
                                yield emit(
                                    event,
                                    store=True,
                                    stored={**event, "content": input_text},
                                )
                    continue

                message, metadata = data
                if isinstance(message, ToolMessage):
                    call_id = message.tool_call_id
                    info = tools.get(
                        call_id,
                        {
                            "name": message.name or "tool",
                            "kind": "tool",
                            "title": message.name or "工具",
                            "detail": "",
                        },
                    )
                    content = str(message.content or "")
                    status = "error" if tool_failed(content) else "done"
                    summary = (
                        compact(content, 220)
                        if status == "error"
                        else "完成"
                    )
                    if info["kind"] == "skill":
                        detail_content = (
                            "技能正文已读取。界面不展开，完整内容已保存到 SQLite。"
                        )
                        logger.info(
                            "tool done: {} skill={} bytes={}",
                            info["name"],
                            info["detail"],
                            len(content),
                        )
                    else:
                        detail_content = ui_detail(content)
                        logger.info(
                            "tool done: {} status={} bytes={}\n{}",
                            info["name"],
                            status,
                            len(content),
                            log_text(content, 3000),
                        )
                    event = {
                        "type": "tool",
                        "id": call_id,
                        "status": status,
                        "summary": summary,
                        "content": detail_content,
                        **info,
                    }
                    yield emit(
                        event,
                        store=True,
                        stored={**event, "content": content},
                    )
                    continue

                if not isinstance(message, AIMessageChunk):
                    continue
                step = metadata.get("langgraph_step")
                if step != phase_step:
                    phase_step = step
                    phase_id = f"model-{step}"
                    yield emit(
                        {
                            "type": "step",
                            "id": phase_id,
                            "status": "running",
                            "kind": "thinking",
                            "title": "思考中",
                        },
                        store=True,
                    )

                text = chunk_text(message)
                if not text:
                    continue
                if phase_id:
                    yield emit(
                        {"type": "step", "id": phase_id, "status": "done"},
                        store=True,
                    )
                    phase_id = None
                total += len(text)
                assistant_parts.append(text)
                yield emit({"type": "text", "text": text, "step": step})
            if phase_id:
                yield emit(
                    {"type": "step", "id": phase_id, "status": "done"},
                    store=True,
                )
            logger.info("chat done: {} chars", total)
        except asyncio.CancelledError:
            final_status = "interrupted"
            final_error = "client disconnected"
            raise
        except Exception as exc:
            final_status = "failed"
            final_error = str(exc)
            logger.exception("chat failed")
            yield emit(
                {
                    "type": "error",
                    "id": "run-error",
                    "kind": "tool",
                    "title": "执行失败",
                    "detail": compact(exc, 220),
                    "status": "error",
                    "content": str(exc),
                    "error": str(exc),
                },
                store=True,
            )
        finally:
            assistant_content = "".join(assistant_parts)
            logger.info(
                "assistant output:\n{}",
                log_text(assistant_content, 12000),
            )
            if run_id:
                try:
                    history.finish_run(
                        run_id,
                        final_status,
                        assistant_content,
                        final_error,
                    )
                except Exception:
                    logger.exception("history run could not be finished")
        yield emit({"type": "done"})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/tts")
async def tts(request: TTSRequest):
    logger.info("tts request: {} chars", len(request.text))
    try:
        audio = await synthesize(request.text)
    except Exception as exc:
        logger.exception("tts failed")
        raise HTTPException(status_code=502, detail=f"TTS failed: {exc}") from exc
    logger.info("tts done: {} bytes", len(audio))
    return Response(content=audio, media_type="audio/mpeg")


@app.post("/asr")
async def asr(file: UploadFile = File(...)):
    audio = await file.read()
    logger.info("asr request: {} {} bytes", file.filename, len(audio))
    text = await transcribe(audio, file.filename or "audio.wav")
    logger.info("asr done: {} chars", len(text))
    return {"text": text}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000, log_config=None)
