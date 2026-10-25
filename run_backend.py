"""后端启动入口（命令行 / PyInstaller 共用）。"""

import sys
from pathlib import Path

import uvicorn

# 允许从任意工作目录运行 `python E:\...\xiaokong\run_backend.py`
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.main import app  # noqa: E402

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000, log_config=None)
