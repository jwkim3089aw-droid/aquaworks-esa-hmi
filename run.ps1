# run.ps1

# FastAPI 서버 실행 (백그라운드)
Start-Process python -ArgumentList "-m uvicorn app.main:app --reload --port 8003" -NoNewWindow

# ui/main.py 실행 (백그라운드)
Start-Process python -ArgumentList ".\app\ui\main.py" -NoNewWindow

Write-Host "FastAPI 서버와 main.py가 백그라운드에서 실행되었습니다."