"""本地工作区：智能体的文件读写、代码执行和交付目录。"""

from __future__ import annotations

import os
from pathlib import Path

from backend.shell import WorkspaceShellBackend

DEFAULT_WORKSPACE = Path.home() / "Documents" / "小控工作区"

AGENTS_MD = """# 小控工作区

- 所有文件读写都在本工作区内。
- 开发中的代码放 `work/<项目名>/`。
- 运行测试或示例确认可用后，调用 `publish_project` 把代码发布到 `output/<项目名>/`。
- 需要新能力时，写成 `skills/<名称>/SKILL.md`。
- Windows 下运行 Python 用 `python`，不要用 `python3`。
- 用户给出外部文件或目录路径时，可直接使用 `execute` 的 PowerShell/Python 读取。
- 内置 `read_file` 只接受工作区虚拟路径，外部路径不要交给 `read_file`。
"""

# 只给 shell 必要的系统变量，避免把 API Key 暴露给命令。
_ENV_KEYS = (
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "SYSTEMDRIVE",
    "WINDIR",
    "TEMP",
    "TMP",
    "USERPROFILE",
    "APPDATA",
    "LOCALAPPDATA",
    "COMSPEC",
    "HOME",
)


def workspace_dir() -> Path:
    raw = os.getenv("XIAOKONG_WORKSPACE", "").strip()
    return (Path(raw).expanduser() if raw else DEFAULT_WORKSPACE).resolve()


def ensure_workspace() -> Path:
    root = workspace_dir()
    for name in ("work", "output", "skills"):
        (root / name).mkdir(parents=True, exist_ok=True)
    agents = root / "AGENTS.md"
    if not agents.exists():
        agents.write_text(AGENTS_MD, encoding="utf-8")
    return root


def build_backend() -> WorkspaceShellBackend:
    root = ensure_workspace()
    env = {key: os.environ[key] for key in _ENV_KEYS if key in os.environ}
    return WorkspaceShellBackend(
        root_dir=root,
        virtual_mode=True,
        timeout=120,
        inherit_env=False,
        env=env,
    )
