"""Write a ``.env`` from the currently active settings.

Useful for moving configuration out of ``%APPDATA%\\小控\\settings.json`` into
the project. Values are written to the file and never printed to stdout.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from xiaokong.config import (  # noqa: E402
    ENV_ALIASES,
    AppSettings,
    get_embedded_secrets,
    get_settings_path,
)


def env_name(field: str) -> str:
    names = ENV_ALIASES.get(field)
    return names[0] if names else f"XIAOKONG_{field.upper()}"


def main() -> None:
    # Read settings.json directly: this script's job is to move the UI-saved
    # values into .env, so an existing .env must not influence the export.
    path = get_settings_path()
    stored = {}
    if path.exists():
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            stored = {}

    merged = asdict(AppSettings())
    merged.update(get_embedded_secrets())
    merged.update(
        {
            key: value
            for key, value in stored.items()
            if key in AppSettings.__dataclass_fields__ and value not in (None, "")
        }
    )
    settings = AppSettings(**merged)

    lines = [
        "# 由 scripts/export_env.py 从当前设置生成。",
        "# 本文件包含密钥，绝不能提交 Git。",
        "",
    ]
    for field in AppSettings.__dataclass_fields__:
        value = getattr(settings, field)
        if isinstance(value, bool):
            value = "true" if value else "false"
        text = str(value or "")
        # python-dotenv interprets escapes inside double-quoted values, so a
        # JSON string is the safe encoding for multi-line prose.
        needs_quotes = any(char in text for char in '\n\r#"\\') or text != text.strip()
        encoded = json.dumps(text, ensure_ascii=False) if needs_quotes else text
        lines.append(f"{env_name(field)}={encoded}")

    target = ROOT / ".env"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {target}")
    print("secrets were written to the file, not printed here")


if __name__ == "__main__":
    main()
