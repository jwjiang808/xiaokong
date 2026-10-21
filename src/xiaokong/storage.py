from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from .config import get_data_dir

HISTORY_FILE_NAME = "conversations.json"
MAX_CONVERSATIONS = 100


@dataclass
class Conversation:
    id: str
    title: str
    created_at: float
    updated_at: float
    messages: list[dict[str, str]] = field(default_factory=list)


class ConversationStore:
    def __init__(self) -> None:
        self.path = get_data_dir() / HISTORY_FILE_NAME
        self._conversations: list[Conversation] = []
        self.load()

    def load(self) -> None:
        self._conversations = []
        if not self.path.exists():
            return
        try:
            data: Any = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(data, list):
            return

        for item in data:
            if not isinstance(item, dict):
                continue
            try:
                conversation = Conversation(
                    id=str(item["id"]),
                    title=str(item.get("title") or "新对话"),
                    created_at=float(item.get("created_at") or time.time()),
                    updated_at=float(item.get("updated_at") or time.time()),
                    messages=[
                        {
                            "role": str(message["role"]),
                            "content": str(message["content"]),
                        }
                        for message in item.get("messages", [])
                        if isinstance(message, dict)
                        and message.get("role") in {"user", "assistant"}
                    ],
                )
            except (KeyError, TypeError, ValueError):
                continue
            self._conversations.append(conversation)
        self._sort()

    def all(self) -> list[Conversation]:
        return list(self._conversations)

    def get(self, conversation_id: str) -> Conversation | None:
        return next(
            (
                conversation
                for conversation in self._conversations
                if conversation.id == conversation_id
            ),
            None,
        )

    def create(self, title: str = "新对话") -> Conversation:
        now = time.time()
        conversation = Conversation(
            id=str(uuid.uuid4()),
            title=title,
            created_at=now,
            updated_at=now,
        )
        self._conversations.insert(0, conversation)
        self.save()
        return conversation

    def update(
        self,
        conversation_id: str,
        *,
        title: str | None = None,
        messages: list[dict[str, str]] | None = None,
    ) -> Conversation | None:
        conversation = self.get(conversation_id)
        if conversation is None:
            return None
        if title is not None:
            conversation.title = title
        if messages is not None:
            conversation.messages = [
                {
                    "role": str(message.get("role", "")),
                    "content": str(message.get("content", "")),
                }
                for message in messages
                if message.get("role") in {"user", "assistant"}
            ]
        conversation.updated_at = time.time()
        self._sort()
        self.save()
        return conversation

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [
            asdict(conversation)
            for conversation in self._conversations[:MAX_CONVERSATIONS]
        ]
        temp_path = self.path.with_suffix(".tmp")
        temp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp_path.replace(self.path)

    def _sort(self) -> None:
        self._conversations.sort(
            key=lambda conversation: conversation.updated_at,
            reverse=True,
        )
