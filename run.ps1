$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    uv venv .venv --python 3.13
}

# Editable install so `src/xiaokong` is importable from main.py.
uv pip install --python ".venv\Scripts\python.exe" -e ".[dev]"

.\.venv\Scripts\flet.exe run main.py
