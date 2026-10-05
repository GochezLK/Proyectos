$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = "C:\Users\tamay\futbol-ai\.venv\Scripts\python.exe"

Set-Location $ProjectDir

& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    --windowed `
    --name "SPOT Clips" `
    --add-data "video_processor.py;." `
    --add-data "consolidate_events.py;." `
    --add-data "group_sequences.py;." `
    --add-data "generate_clips.py;." `
    --add-data "checkpoints;checkpoints" `
    --add-data "config;config" `
    --collect-submodules "model" `
    --collect-submodules "util" `
    "gui.py"

$ExePath = Join-Path $ProjectDir "dist\SPOT Clips\SPOT Clips.exe"

if (-not (Test-Path -LiteralPath $ExePath)) {
    throw "No se encontro el ejecutable esperado: $ExePath"
}

Write-Host ""
Write-Host "Ejecutable listo:"
Write-Host $ExePath
