# run.ps1

Set-Location $PSScriptRoot
$env:PYTHONPATH = $PSScriptRoot

# 로그 폴더
New-Item -ItemType Directory -Force -Path "$PSScriptRoot\logs" | Out-Null

# pythonw.exe 경로 (venv 우선)
$pyw = if ($env:VIRTUAL_ENV) {
  Join-Path $env:VIRTUAL_ENV "Scripts\pythonw.exe"
} else {
  "pythonw"  # PATH에 있으면 사용
}

# FastAPI (uvicorn) - 백그라운드, 창 숨김, 로그 파일로 리다이렉트
Start-Process -FilePath $pyw `
  -ArgumentList "-m uvicorn app.main:app --reload --port 8003" `
  -WorkingDirectory $PSScriptRoot `
  -WindowStyle Hidden `
  -RedirectStandardOutput "$PSScriptRoot\logs\api.out.log" `
  -RedirectStandardError "$PSScriptRoot\logs\api.err.log"

# UI (NiceGUI) - 모듈 실행, 창 숨김, 로그 파일로 리다이렉트
Start-Process -FilePath $pyw `
  -ArgumentList "-m app.ui.main" `
  -WorkingDirectory $PSScriptRoot `
  -WindowStyle Hidden `
  -RedirectStandardOutput "$PSScriptRoot\logs\ui.out.log" `
  -RedirectStandardError "$PSScriptRoot\logs\ui.err.log"

Write-Host "FastAPI와 UI를 백그라운드로 시작했습니다. (logs/*.log 참고)"
