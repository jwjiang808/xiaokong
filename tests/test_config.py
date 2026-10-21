from __future__ import annotations

import json

from xiaokong import config


def test_default_prompt_is_the_professional_course_assistant() -> None:
    prompt = config.DEFAULT_SYSTEM_PROMPT
    for required in ("小控", "课程问答助手", "课件", "老师", "不编造"):
        assert required in prompt
    assert len(prompt) < 800


def test_legacy_default_prompt_is_upgraded_and_persisted(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    data_dir = tmp_path / config.APP_DIR_NAME
    data_dir.mkdir(parents=True)
    legacy = config.LEGACY_SYSTEM_PROMPTS[0]
    (data_dir / config.SETTINGS_FILE_NAME).write_text(
        json.dumps({"system_prompt": legacy}, ensure_ascii=False),
        encoding="utf-8",
    )

    settings = config.load_settings()

    assert settings.system_prompt == config.DEFAULT_SYSTEM_PROMPT
    saved = json.loads(
        (data_dir / config.SETTINGS_FILE_NAME).read_text(encoding="utf-8")
    )
    assert saved["system_prompt"] == config.DEFAULT_SYSTEM_PROMPT


def test_custom_prompt_is_never_overwritten(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    data_dir = tmp_path / config.APP_DIR_NAME
    data_dir.mkdir(parents=True)
    custom = "你是我的私人助教，只用一句话回答，并且必须用英文。"
    (data_dir / config.SETTINGS_FILE_NAME).write_text(
        json.dumps({"system_prompt": custom}, ensure_ascii=False),
        encoding="utf-8",
    )

    settings = config.load_settings()

    assert settings.system_prompt == custom


def test_legacy_data_directory_is_migrated(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    legacy_dir = tmp_path / "问答助手"
    legacy_dir.mkdir()
    (legacy_dir / "settings.json").write_text(
        json.dumps({"llm_api_key": "legacy-key"}),
        encoding="utf-8",
    )
    (legacy_dir / "conversations.json").write_text("[]", encoding="utf-8")

    data_dir = config.get_data_dir()

    assert data_dir == tmp_path / "小控"
    assert (data_dir / "conversations.json").exists()
    assert config.load_settings().llm_api_key == "legacy-key"


def test_agent_kind_defaults_to_chat(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert config.AppSettings().agent_kind == "chat"


def test_env_overrides_beat_settings_json(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    data_dir = tmp_path / config.APP_DIR_NAME
    data_dir.mkdir(parents=True)
    (data_dir / config.SETTINGS_FILE_NAME).write_text(
        json.dumps(
            {
                "llm_base_url": "https://from-file/v1",
                "chat_model": "file-model",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("XIAOKONG_LLM_BASE_URL", "https://from-env/v1")
    monkeypatch.setenv("XIAOKONG_CHAT_MODEL", "env-model")

    settings = config.load_settings()

    assert settings.llm_base_url == "https://from-env/v1"
    assert settings.chat_model == "env-model"


def test_openai_aliases_are_supported(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://alias/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "alias-key")

    overrides = config.env_overrides()

    assert overrides["llm_base_url"] == "https://alias/v1"
    assert overrides["llm_api_key"] == "alias-key"


def test_multiline_prompt_keeps_newlines(monkeypatch):
    monkeypatch.setenv("XIAOKONG_SYSTEM_PROMPT", "第一行\n第二行")
    assert config.env_overrides()["system_prompt"] == "第一行\n第二行"
