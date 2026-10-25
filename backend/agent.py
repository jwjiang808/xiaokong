"""后端智能体：一个 create_deep_agent 调用，把参数传进去。"""

from __future__ import annotations

import uuid

from deepagents import create_deep_agent
from langchain_openai import ChatOpenAI
from loguru import logger

from backend.config import settings
from backend.mcp import load_mcp_tools
from backend.tools import TOOLS as LOCAL_TOOLS
from backend.workspace import build_backend, workspace_dir

# 以后要加子智能体，直接往这个列表里加。
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
    backend = build_backend()
    tools = [*LOCAL_TOOLS, *load_mcp_tools()]
    logger.info(
        "create_deep_agent model={} base_url={} workspace={} tools={}",
        settings.chat_model,
        settings.llm_base_url,
        workspace_dir(),
        len(tools),
    )
    return create_deep_agent(
        model=build_model(),
        tools=tools,
        backend=backend,
        memory=["/AGENTS.md"],
        skills=["/skills/"],
        subagents=SUBAGENTS or None,
        system_prompt=settings.system_prompt,
        name="xiaokong",
    )
