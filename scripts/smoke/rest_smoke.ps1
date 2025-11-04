# 1) 샘플 1건 적재
$body = @{
  ts = (Get-Date).ToUniversalTime().ToString("o")
  DO = 1.9; MLSS = 3600; temp = 22.3; pH = 6.95; air_flow = 185; power = 0.85; total_energy_calc = 0.0
} | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8003/api/v1/telemetry -Method POST -ContentType application/json -Body $body

# 2) 최근값
Invoke-RestMethod http://127.0.0.1:8003/api/v1/last

# 3) 최근 1시간 스냅샷
Invoke-RestMethod "http://127.0.0.1:8003/api/v1/telemetry?hours=1"
