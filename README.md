# ESA_HMI

FastAPI + NiceGUI 기반 ESA HMI.

## Quick Start (Windows / PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .[all]

# 개발 서버
.\run.ps1
# 중지
.\stop.ps1

GET /health : 헬스체크 (200 OK -> {"status":"ok"})