$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    python -m venv .venv
    & '.\.venv\Scripts\python.exe' -m pip install -r requirements.txt
}
Write-Host 'EvalPilot: http://127.0.0.1:8765'
& '.\.venv\Scripts\python.exe' -m uvicorn evalpilot.app:app --host 127.0.0.1 --port 8765
