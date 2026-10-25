"""SQLite persistence for conversations, runs and agent steps."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.workspace import workspace_dir

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    user_content TEXT NOT NULL,
    assistant_content TEXT NOT NULL DEFAULT '',
    input_json TEXT NOT NULL,
    error TEXT,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);

CREATE TABLE IF NOT EXISTS steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    step_id TEXT,
    kind TEXT,
    title TEXT,
    detail TEXT,
    status TEXT,
    content TEXT,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(id)
);

CREATE TABLE IF NOT EXISTS step_records (
    run_id TEXT NOT NULL,
    step_id TEXT NOT NULL,
    first_sequence INTEGER NOT NULL DEFAULT 0,
    kind TEXT,
    title TEXT,
    detail TEXT,
    status TEXT,
    input_content TEXT,
    output_content TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    PRIMARY KEY (run_id, step_id),
    FOREIGN KEY (run_id) REFERENCES runs(id)
);

CREATE TABLE IF NOT EXISTS message_blocks (
    run_id TEXT NOT NULL,
    block_id TEXT NOT NULL,
    first_sequence INTEGER NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (run_id, block_id),
    FOREIGN KEY (run_id) REFERENCES runs(id)
);

CREATE INDEX IF NOT EXISTS idx_runs_conversation
    ON runs(conversation_id, started_at);
CREATE INDEX IF NOT EXISTS idx_steps_run
    ON steps(run_id, sequence);

CREATE VIEW IF NOT EXISTS readable_runs AS
SELECT
    r.id AS run_id,
    c.id AS conversation_id,
    c.title,
    r.started_at,
    r.finished_at,
    r.status,
    r.user_content,
    r.assistant_content,
    r.error
FROM runs r
JOIN conversations c ON c.id = r.conversation_id;

DROP VIEW IF EXISTS readable_steps;
CREATE VIEW readable_steps AS
SELECT
    d.run_id,
    d.step_id,
    d.kind,
    d.title,
    d.detail,
    d.status,
    d.input_content,
    d.output_content,
    d.started_at,
    d.finished_at
FROM step_records d;

DROP VIEW IF EXISTS readable_messages;
CREATE VIEW readable_messages AS
SELECT
    run_id,
    block_id,
    first_sequence,
    content,
    created_at
FROM message_blocks;
"""


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def database_path() -> Path:
    raw = os.getenv("XIAOKONG_DB_PATH", "").strip()
    return Path(raw).expanduser().resolve() if raw else workspace_dir() / "xiaokong.db"


def _connect() -> sqlite3.Connection:
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db() -> Path:
    path = database_path()
    with _connect() as conn:
        conn.executescript(SCHEMA)
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(step_records)")
        }
        if "first_sequence" not in columns:
            conn.execute(
                "ALTER TABLE step_records "
                "ADD COLUMN first_sequence INTEGER NOT NULL DEFAULT 0"
            )
    return path


def content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content or "")
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            parts.append(str(item))
            continue
        if item.get("type") == "text":
            parts.append(str(item.get("text") or ""))
        elif item.get("type") == "image_url":
            parts.append("[图片]")
    return "\n".join(parts)


def _title_from_user(content: Any) -> str:
    text = " ".join(content_text(content).split())
    return text[:80] or "未命名会话"


def start_run(
    conversation_id: str,
    user_content: Any,
    messages: list[dict[str, Any]],
    display_text: str | None = None,
) -> tuple[str, str]:
    conversation_id = conversation_id or uuid.uuid4().hex
    run_id = uuid.uuid4().hex
    now = _now()
    user_text = (display_text or content_text(user_content)).strip()
    title = _title_from_user(user_text)
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO conversations(id, title, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at
            """,
            (conversation_id, title, now, now),
        )
        conn.execute(
            """
            INSERT INTO runs(
                id, conversation_id, started_at, status,
                user_content, input_json
            ) VALUES (?, ?, ?, 'running', ?, ?)
            """,
            (
                run_id,
                conversation_id,
                now,
                user_text,
                json.dumps(messages, ensure_ascii=False),
            ),
        )
    return conversation_id, run_id


def record_step(run_id: str, sequence: int, event: dict[str, Any]) -> None:
    now = _now()
    step_id = str(event.get("id") or "")
    event_type = str(event.get("type") or "")
    status = str(event.get("status") or "")
    content = str(event.get("content") or "")
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO steps(
                run_id, sequence, event_type, step_id, kind, title,
                detail, status, content, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                sequence,
                event_type,
                step_id,
                str(event.get("kind") or ""),
                str(event.get("title") or ""),
                str(event.get("detail") or ""),
                str(event.get("status") or ""),
                content,
                json.dumps(event, ensure_ascii=False),
                now,
            ),
        )
        if not step_id or event_type not in {"step", "tool", "error"}:
            return
        conn.execute(
            """
            INSERT INTO step_records(
                run_id, step_id, first_sequence, kind, title, detail, status,
                input_content, output_content, started_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id, step_id) DO UPDATE SET
                kind=COALESCE(NULLIF(excluded.kind, ''), step_records.kind),
                title=COALESCE(NULLIF(excluded.title, ''), step_records.title),
                detail=COALESCE(NULLIF(excluded.detail, ''), step_records.detail),
                status=COALESCE(NULLIF(excluded.status, ''), step_records.status),
                input_content=CASE
                    WHEN excluded.input_content != '' THEN excluded.input_content
                    ELSE step_records.input_content
                END,
                output_content=CASE
                    WHEN excluded.output_content != '' THEN excluded.output_content
                    ELSE step_records.output_content
                END,
                finished_at=CASE
                    WHEN excluded.status IN ('done', 'error') THEN excluded.started_at
                    ELSE step_records.finished_at
                END
            """,
            (
                run_id,
                step_id,
                sequence,
                str(event.get("kind") or ""),
                str(event.get("title") or ""),
                str(event.get("detail") or ""),
                status,
                content if status == "running" else "",
                content if status in {"done", "error"} else "",
                now,
            ),
        )


def finish_run(
    run_id: str,
    status: str,
    assistant_content: str,
    error: str | None = None,
) -> None:
    with _connect() as conn:
        conn.execute(
            """
            UPDATE runs
            SET finished_at=?, status=?, assistant_content=?, error=?
            WHERE id=?
            """,
            (_now(), status, assistant_content, error, run_id),
        )


def record_message_block(
    run_id: str,
    sequence: int,
    step_id: str,
    content: str,
) -> None:
    if not content:
        return
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO message_blocks(
                run_id, block_id, first_sequence, content, created_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(run_id, block_id) DO NOTHING
            """,
            (run_id, step_id, sequence, content, _now()),
        )


def _preview(value: str | None, limit: int = 1200) -> str:
    text = value or ""
    if len(text) <= limit:
        return text
    return text[:limit] + "\n\n… 完整内容请查看 SQLite。"


def list_conversations(limit: int = 50) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT
                c.id,
                c.title,
                c.updated_at,
                COUNT(r.id) AS run_count
            FROM conversations c
            LEFT JOIN runs r ON r.conversation_id = c.id
            GROUP BY c.id
            ORDER BY c.updated_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        {
            "id": row[0],
            "title": row[1],
            "updated_at": row[2],
            "run_count": row[3],
        }
        for row in rows
    ]


def get_conversation(conversation_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        conversation = conn.execute(
            "SELECT id, title, created_at, updated_at "
            "FROM conversations WHERE id=?",
            (conversation_id,),
        ).fetchone()
        if conversation is None:
            return None
        run_rows = conn.execute(
            """
            SELECT id, started_at, finished_at, status, user_content,
                   assistant_content, input_json, error
            FROM runs
            WHERE conversation_id=?
            ORDER BY started_at, id
            """,
            (conversation_id,),
        ).fetchall()
        run_ids = [row[0] for row in run_rows]
        step_rows = []
        if run_ids:
            placeholders = ",".join("?" for _ in run_ids)
            step_rows = conn.execute(
                f"""
                SELECT run_id, step_id, first_sequence, kind, title, detail, status,
                       input_content, output_content, started_at, finished_at
                FROM step_records
                WHERE run_id IN ({placeholders})
                ORDER BY run_id, first_sequence, started_at
                """,
                run_ids,
            ).fetchall()
            message_rows = conn.execute(
                f"""
                SELECT run_id, block_id AS step_id, first_sequence, content
                FROM message_blocks
                WHERE run_id IN ({placeholders})
                ORDER BY run_id, first_sequence
                """,
                run_ids,
            ).fetchall()
        else:
            message_rows = []

    steps_by_run: dict[str, list[dict[str, Any]]] = {}
    for row in step_rows:
        steps_by_run.setdefault(row[0], []).append(
            {
                "step_id": row[1],
                "first_sequence": row[2],
                "kind": row[3],
                "title": row[4],
                "detail": row[5],
                "status": row[6],
                "input_content": _preview(row[7]),
                "output_content": _preview(row[8]),
                "started_at": row[9],
                "finished_at": row[10],
            }
        )
    messages_by_run: dict[str, list[dict[str, Any]]] = {}
    for row in message_rows:
        messages_by_run.setdefault(row[0], []).append(
            {
                "type": "text",
                "step": row[1],
                "first_sequence": row[2],
                "content": row[3],
            }
        )

    runs = []
    for row in run_rows:
        try:
            input_messages = json.loads(row[6])
        except (TypeError, json.JSONDecodeError):
            input_messages = []
        last_user = next(
            (
                message
                for message in reversed(input_messages)
                if isinstance(message, dict) and message.get("role") == "user"
            ),
            {"role": "user", "content": row[4]},
        )
        blocks = [
            {"type": "step", **step}
            for step in steps_by_run.get(row[0], [])
        ] + messages_by_run.get(row[0], [])
        blocks.sort(key=lambda item: item.get("first_sequence", 0))
        runs.append(
            {
                "id": row[0],
                "started_at": row[1],
                "finished_at": row[2],
                "status": row[3],
                "user_content": row[4],
                "user_input": last_user.get("content", row[4]),
                "assistant_content": row[5],
                "error": row[7],
                "steps": steps_by_run.get(row[0], []),
                "blocks": blocks,
            }
        )
    return {
        "id": conversation[0],
        "title": conversation[1],
        "created_at": conversation[2],
        "updated_at": conversation[3],
        "runs": runs,
    }
