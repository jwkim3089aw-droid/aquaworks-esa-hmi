# run_sim.ps1
param([switch]$ActivateVenv)
$ErrorActionPreference = "Stop"

# [0] 프로세스 정리
$lingering_procs = Get-WmiObject Win32_Process -Filter "Name = 'python.exe' AND CommandLine LIKE '%app.ui.main%'"
if ($lingering_procs) {
    foreach ($proc in $lingering_procs) { Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 1
}

# [1] 경로 및 로그 설정 (삭제 로직 제거, 누적 방식)
$CODE_DIR = $PSScriptRoot
Set-Location $CODE_DIR
$LOG_DIR = Join-Path $CODE_DIR "logs"

if (-not (Test-Path $LOG_DIR)) {
    New-Item -ItemType Directory -Path $LOG_DIR -Force | Out-Null
}

# [2] 웹 서버 환경변수 (통신 하드코딩 싹 제거!)
$env:ESA_DEV = "0"
$env:NICEGUI_SHOW = "0"
$env:ESA_UI_HOST = "127.0.0.1"
$env:ESA_UI_PORT = "8090"

# [3] 실행
$PYTHON_EXE = Join-Path $CODE_DIR ".venv\Scripts\python.exe"
Write-Host "Starting Python Application (ESA_HMI)..."
& $PYTHON_EXE -u -m app.ui.main
