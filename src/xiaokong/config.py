from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

try:  # local-only file with baked-in credentials; absent in a clean clone
    from .embedded_secrets import get_embedded_secrets
except ImportError:  # pragma: no cover - clean clone without local secrets
    def get_embedded_secrets() -> dict[str, str]:
        return {}

APP_DIR_NAME = "小控"
SETTINGS_FILE_NAME = "settings.json"
LEGACY_APP_DIR_NAMES = ("问答助手", "FletVoiceQA")

PROJECT_ROOT = Path(__file__).resolve().parents[2]

try:  # optional at import time; it is a declared dependency
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - fallback for stripped installs
    load_dotenv = None  # type: ignore[assignment]

_dotenv_loaded = False


def _env_file_candidates() -> list[Path]:
    """Where to look for ``.env``, highest priority first."""
    candidates: list[Path] = []
    explicit = os.getenv("XIAOKONG_ENV_FILE")
    if explicit:
        candidates.append(Path(explicit))
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / ".env")
    candidates.append(PROJECT_ROOT / ".env")
    candidates.append(Path.cwd() / ".env")

    unique: list[Path] = []
    seen: set[Path] = set()
    for path in candidates:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(resolved)
    return unique


def load_env() -> Path | None:
    """Load the first existing ``.env`` without overriding real env vars."""
    global _dotenv_loaded
    if os.getenv("XIAOKONG_SKIP_DOTENV", "").lower() in {"1", "true", "yes"}:
        _dotenv_loaded = True
        return None
    if _dotenv_loaded or load_dotenv is None:
        return None
    _dotenv_loaded = True
    for path in _env_file_candidates():
        if path.is_file():
            load_dotenv(path, override=False)
            return path
    return None


# Explicit aliases first, then a generic XIAOKONG_<FIELD> name for every field.
ENV_ALIASES: dict[str, tuple[str, ...]] = {
    "llm_base_url": (
        "XIAOKONG_LLM_BASE_URL",
        "LLM_BASE_URL",
        "OPENAI_BASE_URL",
        "OPENAI_API_BASE",
    ),
    "llm_api_key": (
        "XIAOKONG_LLM_API_KEY",
        "LLM_API_KEY",
        "OPENAI_API_KEY",
    ),
    "chat_model": ("XIAOKONG_CHAT_MODEL", "CHAT_MODEL", "OPENAI_MODEL"),
    "asr_provider": ("XIAOKONG_ASR_PROVIDER", "ASR_PROVIDER"),
    "asr_base_url": ("XIAOKONG_ASR_BASE_URL", "ASR_BASE_URL"),
    "asr_api_key": ("XIAOKONG_ASR_API_KEY", "ASR_API_KEY"),
    "asr_model": ("XIAOKONG_ASR_MODEL", "ASR_MODEL"),
    "tts_provider": ("XIAOKONG_TTS_PROVIDER", "TTS_PROVIDER"),
    "tts_base_url": ("XIAOKONG_TTS_BASE_URL", "TTS_BASE_URL"),
    "tts_api_key": ("XIAOKONG_TTS_API_KEY", "TTS_API_KEY"),
    "tts_model": ("XIAOKONG_TTS_MODEL", "TTS_MODEL"),
    "tts_voice": ("XIAOKONG_TTS_VOICE", "TTS_VOICE"),
    "doubao_api_key": ("XIAOKONG_DOUBAO_API_KEY", "DOUBAO_API_KEY"),
    "system_prompt": ("XIAOKONG_SYSTEM_PROMPT", "SYSTEM_PROMPT"),
    "agent_kind": ("XIAOKONG_AGENT_KIND", "AGENT_KIND"),
}

_BOOL_FIELDS = {"auto_send_voice", "auto_speak_replies"}


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on", "y", "t"}


def env_overrides() -> dict[str, object]:
    """Read settings from ``.env`` / real environment variables.

    Environment values have the highest priority: they let a deployment or a
    developer point the app at a different model endpoint without editing the
    UI-saved ``settings.json``.
    """
    load_env()
    result: dict[str, object] = {}
    for field in AppSettings.__dataclass_fields__:
        names = ENV_ALIASES.get(field, ()) + (f"XIAOKONG_{field.upper()}",)
        for name in names:
            raw = os.getenv(name)
            if raw is None or not raw.strip():
                continue
            result[field] = _parse_bool(raw) if field in _BOOL_FIELDS else raw.strip()
            break
    return result

DEFAULT_SYSTEM_PROMPT = """你是「小控」，一名专业的课程问答助手。

【角色】
你是学生的课程导师，负责帮助学生理解课程内容、梳理知识结构、解决课程相关问题。讲课时语气沉稳、有耐心，像一位讲得清楚的好老师。

【能力】
1. 阅读并分析用户提供的课件与资料（PPT、Word、Excel、PDF、TXT 等），能提炼要点、归纳结构、说明知识点之间的逻辑关系。
2. 回答各类课程问题：概念解释、原理论证、例题讲解、作业与复习辅导、知识串联、考点梳理。
3. 能对知识点做对比、总结与延伸，并主动指出常见误区和易错点。

【回答要求】
1. 专业准确：使用规范的学科术语，结论要有依据，推理过程要站得住。
2. 讲得清楚：先给结论，再讲原因和推导；内容较多时分点、分步骤，由浅入深。
3. 结合材料：用户提供了课件或资料时，优先依据材料作答，并说明结论来自材料还是通用知识。
4. 面向理解：必要时举例或类比帮助理解，避免空话、套话和无关的铺垫。
5. 不编造：不确定的地方明确说明，不虚构数据、引用或结论。
6. 语言：默认使用中文回答，除非用户要求其他语言。

【输出风格】
简洁但不失完整；可用小标题和编号列表帮助阅读，但不要堆砌无关格式。"""

# Prompts shipped as defaults by earlier versions. If the stored prompt is one
# of these, the user never edited it, so it is upgraded to the current default
# instead of keeping the old wording forever.
LEGACY_SYSTEM_PROMPTS = (
    "你是一个简洁、可靠的中文课程助手。直接回答问题；不确定时明确说明，不要编造事实。",
    "你是一个简洁、可靠的中文问答助手。直接回答问题；不确定时明确说明，不要编造事实。",
)


@dataclass
class AppSettings:
    llm_base_url: str = "https://opencode.ai/zen/go/v1"
    llm_api_key: str = ""
    chat_model: str = "deepseek-v4.1-flash"

    asr_provider: str = "doubao"
    asr_base_url: str = "https://api.groq.com/openai/v1"
    asr_api_key: str = ""
    asr_model: str = "whisper-large-v3-turbo"

    tts_provider: str = "doubao"
    tts_base_url: str = "https://api.tts.ai"
    tts_api_key: str = ""
    tts_model: str = "kokoro"
    tts_voice: str = "zf_xiaoxiao"

    doubao_api_key: str = ""
    doubao_tts_resource_id: str = "seed-tts-2.0"
    doubao_tts_voice: str = "zh_female_vv_uranus_bigtts"
    doubao_asr_resource_id: str = "volc.seedasr.sauc.duration"
    doubao_asr_model: str = "bigmodel"

    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    auto_send_voice: bool = True
    auto_speak_replies: bool = True

    # Reserved for the agent layer: which registered agent implementation to
    # use ("chat" today; a tool-calling agent can be added later).
    agent_kind: str = "chat"


def get_data_dir() -> Path:
    base_dir = os.getenv("APPDATA")
    if base_dir:
        base_path = Path(base_dir)
    else:
        base_path = Path.home()
        base_dir = None

    data_dir = (
        base_path / APP_DIR_NAME
        if base_dir
        else base_path / f".{APP_DIR_NAME.lower()}"
    )

    # Migrate data written under an older app name so renaming the app does not
    # lose the saved settings and conversation history.
    legacy_dirs = [
        base_path / legacy_name
        if base_dir
        else base_path / f".{legacy_name.lower()}"
        for legacy_name in LEGACY_APP_DIR_NAMES
    ]
    legacy_dirs = [
        path for path in legacy_dirs if path != data_dir and path.exists()
    ]

    if legacy_dirs and not data_dir.exists():
        # Fast path: the folder can usually just be renamed.
        for legacy_dir in legacy_dirs:
            try:
                legacy_dir.rename(data_dir)
                break
            except OSError:
                continue

    data_dir.mkdir(parents=True, exist_ok=True)

    # Top up any file the new directory is still missing. This covers a partial
    # earlier migration and multiple legacy names, and never overwrites data
    # that already lives in the new directory.
    for legacy_dir in legacy_dirs:
        if not legacy_dir.exists():
            continue
        try:
            entries = list(legacy_dir.iterdir())
        except OSError:
            continue
        for item in entries:
            target = data_dir / item.name
            if target.exists() or not item.is_file():
                continue
            try:
                shutil.copy2(item, target)
            except OSError:
                continue

    return data_dir


def get_settings_path() -> Path:
    return get_data_dir() / SETTINGS_FILE_NAME


def load_settings() -> AppSettings:
    load_env()
    embedded = get_embedded_secrets()
    defaults = AppSettings(
        **{
            key: value
            for key, value in embedded.items()
            if key in AppSettings.__dataclass_fields__
        }
    )
    merged = asdict(defaults)

    path = get_settings_path()
    if not path.exists():
        for legacy_name in LEGACY_APP_DIR_NAMES:
            base_dir = os.getenv("APPDATA")
            legacy_root = (
                Path(base_dir) / legacy_name
                if base_dir
                else Path.home() / f".{legacy_name.lower()}"
            )
            legacy_path = legacy_root / SETTINGS_FILE_NAME
            if legacy_path.exists():
                path = legacy_path
                break

    data: dict[str, object] = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
        except (OSError, json.JSONDecodeError):
            data = {}

    # Migrate settings produced by the first single-provider version.
    if "llm_base_url" not in data and "base_url" in data:
        data["llm_base_url"] = data["base_url"]
    if "llm_api_key" not in data and "api_key" in data:
        data["llm_api_key"] = data["api_key"]

    known_fields = AppSettings.__dataclass_fields__
    merged.update(
        {
            key: value
            for key, value in data.items()
            if key in known_fields and value not in (None, "")
        }
    )

    # Upgrade a never-customised prompt to the current default wording.
    prompt_upgraded = False
    if merged.get("system_prompt") in LEGACY_SYSTEM_PROMPTS:
        merged["system_prompt"] = DEFAULT_SYSTEM_PROMPT
        prompt_upgraded = True

    # .env / real environment variables win over the UI-saved settings.
    merged.update(env_overrides())

    settings = AppSettings(**merged)
    if path.exists() and (path != get_settings_path() or prompt_upgraded):
        save_settings(settings)
    return settings


def save_settings(settings: AppSettings) -> None:
    path = get_settings_path()
    path.write_text(
        json.dumps(asdict(settings), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
