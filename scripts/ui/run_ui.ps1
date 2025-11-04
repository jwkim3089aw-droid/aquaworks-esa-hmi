# scripts/ui/run_ui.ps1
$env:PYTHONPATH = (Get-Location).Path
python -m app.ui.main
