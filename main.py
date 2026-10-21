"""Flet entry point.

Kept at the project root because ``flet run`` / ``flet pack`` expect a script.
The real application lives in ``src/xiaokong``.
"""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from xiaokong.ui.app import run  # noqa: E402

if __name__ == "__main__":
    run()
