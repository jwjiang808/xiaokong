"""后端智能体：一个 create_deep_agent 调用，把参数传进去。"""

from __future__ import annotations

import logging
import uuid

from deepagents import create_deep_agent
from langchain_openai import ChatOpenAI

from .config import settings

log = logging.getLogger("xiaokong.agent")

# 以后要加课程工具 / 子智能体，直接往这两个列表里加。
TOOLS: list = []
SUBAGENTS: list = []
SESSION_ID = uuid.uuid4().hex


def build_model() -> ChatOpenAI:
    headers = {}
    if "opencode.ai/zen/go" in settings.llm_base_url:
        headers["x-opencode-session"] = SESSION_ID
    return ChatOpenAI(
        model=settings.chat_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        temperature=0.7,
        default_headers=headers or None,
    )


def build_agent():
    log.info(
        "create_deep_agent model=%s base_url=%s",
        settings.chat_model,
        settings.llm_base_url,
    )
    return create_deep_agent(
        model=build_model(),
        tools=TOOLS,
        subagents=SUBAGENTS or None,
        system_prompt=settings.system_prompt,
        name="xiaokong",
    )
