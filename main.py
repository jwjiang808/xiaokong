"""小控前端入口（Flet）。"""

import sys
from pathlib import Path

# 允许从任意工作目录运行 `python E:\...\xiaokong\main.py`
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from frontend.main import run  # noqa: E402

if __name__ == "__main__":
    run()
