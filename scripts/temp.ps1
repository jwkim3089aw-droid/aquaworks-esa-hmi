# 2) 라우트 확인: /api/v1/air/setpoint 가 보여야 함
$spec = Invoke-RestMethod "http://127.0.0.1:8003/openapi.json"
$spec.paths.Keys | ? { $_ -match "/api/v1" } | sort

# 3) 커맨드 발행
$base="http://127.0.0.1:8003"
Invoke-RestMethod "$base/api/v1/air/setpoint" -Method POST -ContentType application/json -Body (@{
  unit_id="blower-1"; kind="AIR_SETPOINT"; value=185.0
} | ConvertTo-Json)

# 4) 큐 조회 (state 흐름: queued → sending → done)
Invoke-RestMethod "$base/api/v1/commands"