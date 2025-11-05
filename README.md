# ESA_HMI

[![CI](https://github.com/junwook3089/ESA_HMI/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/junwook3089/ESA_HMI/actions/workflows/ci.yml)  <!-- [ADDED] CI 배지 -->
[![Release](https://img.shields.io/github/v/release/junwook3089/ESA_HMI?display_name=tag&sort=semver)](https://github.com/junwook3089/ESA_HMI/releases)       <!-- [ADDED] 릴리스 배지 -->
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen)](https://pre-commit.com/)                                                <!-- [ADDED] pre-commit 배지 -->

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
