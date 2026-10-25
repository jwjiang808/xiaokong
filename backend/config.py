"""后端配置：全部从项目根目录的 .env 读取。"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# 源码运行读项目根目录；打包后读 EXE 同目录。
if getattr(sys, "frozen", False):
    ENV_FILE = Path(sys.executable).parent / ".env"
else:
    ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(ENV_FILE)


DEFAULT_SYSTEM_PROMPT = """你是「小控」，一个可靠、务实的通用智能体。

【角色】
你负责理解用户目标，调用可用工具完成实际任务，并把结果清楚地交付给用户。语气冷静、直接、有耐心。

【能力】
1. 阅读和分析用户提供的文件、图片、表格、文档、演示文稿和本地目录。
2. 使用文件、代码执行、搜索和其他可用工具完成任务，而不是只给操作建议。
3. 编写、修改、运行和验证代码，整理资料，制作文档与演示文稿。
4. 对复杂任务先拆解，再逐步执行；需要用户提供信息时只问关键问题。

【回答要求】
1. 先完成用户真正要求的任务，再给出简洁说明。
2. 结论有依据；不确定的信息明确说明，不编造数据、引用或执行结果。
3. 多步骤任务给出简短进度，不暴露内部推理过程。
4. 输出保持清晰可读，避免无关铺垫和重复。
5. 默认使用中文，除非用户要求其他语言。"""

LOCAL_FILE_PROMPT = """

【本地资料】
当用户给出本机文件或目录路径时，直接读取该路径并分析，不要要求用户复制或粘贴内容。
外部路径使用 execute 的 PowerShell 或 Python 读取；内置 read_file 只用于工作区虚拟路径。
只访问用户明确选择的路径，不主动浏览其他个人目录。"""


@dataclass(frozen=True)
class Settings:
    llm_base_url: str
    llm_api_key: str
    chat_model: str
    system_prompt: str

    doubao_api_key: str
    doubao_tts_resource_id: str
    doubao_tts_voice: str
    doubao_asr_resource_id: str
    doubao_asr_model: str


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


settings = Settings(
    llm_base_url=env("XIAOKONG_LLM_BASE_URL", "https://opencode.ai/zen/go/v1"),
    llm_api_key=env("XIAOKONG_LLM_API_KEY"),
    chat_model=env("XIAOKONG_CHAT_MODEL", "deepseek-v4.1-flash"),
    system_prompt=env("XIAOKONG_SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT)
    + LOCAL_FILE_PROMPT,
    doubao_api_key=env("XIAOKONG_DOUBAO_API_KEY"),
    doubao_tts_resource_id=env("XIAOKONG_DOUBAO_TTS_RESOURCE_ID", "seed-tts-2.0"),
    doubao_tts_voice=env(
        "XIAOKONG_DOUBAO_TTS_VOICE", "zh_female_vv_uranus_bigtts"
    ),
    doubao_asr_resource_id=env(
        "XIAOKONG_DOUBAO_ASR_RESOURCE_ID", "volc.seedasr.sauc.duration"
    ),
    doubao_asr_model=env("XIAOKONG_DOUBAO_ASR_MODEL", "bigmodel"),
)
