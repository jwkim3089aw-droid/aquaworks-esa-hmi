# stop.ps1

# 백그라운드에서 실행 중인 uvicorn 프로세스를 종료
Get-Process python | Where-Object { $_.Path -like "*uvicorn*" } | Stop-Process

# 백그라운드에서 실행 중인 main.py 프로세스를 종료
Get-Process python | Where-Object { $_.Path -like "*main.py*" } | Stop-Process

Write-Host "FastAPI 서버와 main.py가 중지되었습니다."
