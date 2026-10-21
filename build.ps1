$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    uv venv .venv --python 3.13
}
uv pip install --python ".venv\Scripts\python.exe" -e ".[packaging]"

# 后端 EXE
.\.venv\Scripts\pyinstaller.exe --onefile --name "xiaokong-server" `
    --distpath "dist\server" `
    --collect-data magika `
    run_backend.py

# 前端 EXE
.\.venv\Scripts\flet.exe pack main.py `
    --name "小控" `
    --product-name "小控-你的专用课程助手" `
    --file-description "小控-你的专用课程助手" `
    --pyinstaller-build-args=--collect-data `
    --pyinstaller-build-args=magika `
    --yes

Write-Host ""
Write-Host "后端: $Root\dist\server\xiaokong-server.exe"
Write-Host "前端: $Root\dist\小控.exe"
