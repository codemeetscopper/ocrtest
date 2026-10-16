$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$appPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $appPython)) {
    throw 'Create .venv and install the project first. See README.md.'
}
Write-Host 'OCR Bench: http://127.0.0.1:8765'
& $appPython -m ocrbench serve
