param(
    [Parameter(Mandatory=$true)][ValidateSet('rapidocr','paddleocr','easyocr','tesseract')][string]$Engine,
    [Parameter(Mandatory=$true)][string]$Python,
    [ValidateSet('cpu','gpu')][string]$Device = 'cpu'
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$extra = $Engine
if ($Device -eq 'gpu') {
    if ($Engine -eq 'tesseract') { throw 'Tesseract supports CPU only. Select CPU for this engine.' }
    $extra = "$Engine-gpu"
}
$engineDirectory = Join-Path $projectRoot ".engines\$extra"
& $Python -m venv $engineDirectory
if ($LASTEXITCODE -ne 0) { throw 'Environment creation failed. Use a standard Python installation with ensurepip.' }
$enginePython = Join-Path $engineDirectory 'Scripts\python.exe'
& $enginePython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'pip setup failed' }
if ($Device -eq 'gpu' -and $Engine -eq 'easyocr') {
    & $enginePython -m pip install torch==2.14.1 torchvision==0.29.1 --index-url https://download.pytorch.org/whl/cu130
    if ($LASTEXITCODE -ne 0) { throw 'CUDA PyTorch installation failed' }
}
if ($Device -eq 'gpu' -and $Engine -eq 'paddleocr') {
    & $enginePython -m pip install --no-deps paddlepaddle-gpu==3.3.1 --index-url https://www.paddlepaddle.org.cn/packages/stable/cu130/
    if ($LASTEXITCODE -ne 0) { throw 'CUDA PaddlePaddle installation failed' }
    # Resolve NVIDIA and ordinary dependencies from PyPI after installing the
    # official CUDA-specific framework wheel. Keep the selected CUDA build.
    & $enginePython -m pip install paddlepaddle-gpu==3.3.1
    if ($LASTEXITCODE -ne 0) { throw 'CUDA PaddlePaddle dependency installation failed' }
}
& $enginePython -m pip install -e "${projectRoot}[$extra]"
if ($LASTEXITCODE -ne 0) { throw 'Engine installation failed. Check Python/backend compatibility.' }
Write-Host "Set this interpreter in the dashboard Environments page: $enginePython"
if ($Device -eq 'gpu') { Write-Host 'CUDA libraries installed locally. A compatible NVIDIA driver is required; run preflight to verify CUDA sessions.' }
else { Write-Host 'CPU baseline installed.' }
if ($Engine -eq 'tesseract') { Write-Host 'Install the native Tesseract executable and language data separately; configure tesseract_cmd in engine options if it is not on PATH.' }
