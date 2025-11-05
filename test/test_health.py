# test/test_health.py
# [REPLACED] stray character 'p' 제거 및 안정 테스트로 교체

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok() -> None:
    # [ADDED] /health 200 및 페이로드 확인
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_trend_smoke() -> None:
    # [ADDED] 트렌드 엔드포인트 스모크: 리스트 반환(비어 있어도 OK)
    r = client.get("/api/v1/trend?hours=0.001")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
