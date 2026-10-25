"""把验证过的代码从 work/ 发布到 output/。"""

from __future__ import annotations

import shutil

from langchain_core.tools import tool

from backend.workspace import workspace_dir


@tool
def publish_project(project: str) -> str:
    """把 work/<project> 中验证通过的代码发布到 output/<project>。"""
    root = workspace_dir()
    source = root / "work" / project
    target = root / "output" / project

    if not source.is_dir():
        return f"未找到项目目录：{source}"

    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)
    return f"已发布到 {target}"
