$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    uv venv .venv --python 3.13
}
uv pip install --python ".venv\Scripts\python.exe" -e ".[dev]"

# 后端和前端分两个窗口启动
Start-Process -FilePath ".\.venv\Scripts\python.exe" `
    -ArgumentList "-m", "backend.main" `
    -WorkingDirectory $Root

Start-Sleep -Seconds 2
.\.venv\Scripts\flet.exe run main.py
