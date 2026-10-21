"""Template for local-only baked-in credentials.

Copy to ``embedded_secrets.py`` and fill in only if you want keys embedded in
the packaged EXE. That file is gitignored and must never be committed.

Most users should leave this empty and put credentials in ``.env`` instead.
"""

from __future__ import annotations

_EMBEDDED: dict[str, str] = {}


def get_embedded_secrets() -> dict[str, str]:
    return dict(_EMBEDDED)
