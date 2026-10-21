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


DEFAULT_SYSTEM_PROMPT = """你是「小控」，一名专业的课程问答助手。

【角色】
你是学生的课程导师，帮助学生理解课程内容、梳理知识结构、解决课程相关问题。语气沉稳、有耐心，像一位讲得清楚的好老师。

【能力】
1. 阅读并分析用户提供的课件与资料（PPT、Word、Excel、PDF、TXT 等），提炼要点、归纳结构、说明知识点之间的逻辑关系。
2. 回答课程问题：概念解释、原理论证、例题讲解、作业与复习辅导、知识串联、考点梳理。
3. 对知识点做对比、总结与延伸，并主动指出常见误区和易错点。

【回答要求】
1. 专业准确：使用规范术语，结论有依据，推理站得住。
2. 讲得清楚：先给结论，再讲原因和推导；内容较多时分点、分步骤。
3. 结合材料：优先依据用户提供的课件作答，并说明结论来源。
4. 不编造：不确定的地方明确说明，不虚构数据、引用或结论。
5. 默认使用中文回答，除非用户要求其他语言。"""


@dataclass(frozen=True)
class Settings:
    llm_base_url: str
    llm_api_key: str
    chat_model: str
    system_prompt: str

    tts_provider: str
    tts_base_url: str
    tts_api_key: str
    tts_model: str
    tts_voice: str

    asr_provider: str
    asr_base_url: str
    asr_api_key: str
    asr_model: str

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
    system_prompt=env("XIAOKONG_SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT),
    tts_provider=env("XIAOKONG_TTS_PROVIDER", "doubao"),
    tts_base_url=env("XIAOKONG_TTS_BASE_URL", "https://api.tts.ai"),
    tts_api_key=env("XIAOKONG_TTS_API_KEY"),
    tts_model=env("XIAOKONG_TTS_MODEL", "kokoro"),
    tts_voice=env("XIAOKONG_TTS_VOICE", "zf_xiaoxiao"),
    asr_provider=env("XIAOKONG_ASR_PROVIDER", "doubao"),
    asr_base_url=env("XIAOKONG_ASR_BASE_URL", "https://api.groq.com/openai/v1"),
    asr_api_key=env("XIAOKONG_ASR_API_KEY"),
    asr_model=env("XIAOKONG_ASR_MODEL", "whisper-large-v3-turbo"),
    doubao_api_key=env("XIAOKONG_DOUBAO_API_KEY"),
    doubao_tts_resource_id=env(
        "XIAOKONG_DOUBAO_TTS_RESOURCE_ID", "seed-tts-2.0"
    ),
    doubao_tts_voice=env(
        "XIAOKONG_DOUBAO_TTS_VOICE", "zh_female_vv_uranus_bigtts"
    ),
    doubao_asr_resource_id=env(
        "XIAOKONG_DOUBAO_ASR_RESOURCE_ID", "volc.bigasr.auc_turbo"
    ),
    doubao_asr_model=env("XIAOKONG_DOUBAO_ASR_MODEL", "bigmodel"),
)
