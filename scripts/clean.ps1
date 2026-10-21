$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

function Remove-Safe([string]$Path) {
    $resolved = [System.IO.Path]::GetFullPath($Path)
    if (-not $resolved.StartsWith($Root, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to delete outside the project: $resolved"
    }
    if (Test-Path -LiteralPath $resolved) {
        Remove-Item -LiteralPath $resolved -Recurse -Force
        Write-Host "removed $resolved"
    }
}

Get-ChildItem -Path $Root -Filter "*.log" -File | ForEach-Object {
    Remove-Safe $_.FullName
}

Get-ChildItem -Path $Root -Recurse -Directory -Filter "__pycache__" |
    Where-Object { $_.FullName -notmatch '\\.venv\\|\\build\\|\\dist\\' } |
    ForEach-Object { Remove-Safe $_.FullName }

Remove-Safe (Join-Path $Root ".pytest_cache")
Remove-Safe (Join-Path $Root ".ruff_cache")
