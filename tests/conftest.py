from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Keep tests hermetic: never load the developer's real project .env.
os.environ["XIAOKONG_SKIP_DOTENV"] = "1"


@pytest.fixture(autouse=True)
def _isolate_dotenv(monkeypatch):
    """Flet loads ``.env`` on import; strip those values for every test."""
    for key in list(os.environ):
        if key.startswith("XIAOKONG_") and key != "XIAOKONG_SKIP_DOTENV":
            monkeypatch.delenv(key, raising=False)

    import xiaokong.config as config

    monkeypatch.setattr(config, "_dotenv_loaded", False, raising=False)
    yield
