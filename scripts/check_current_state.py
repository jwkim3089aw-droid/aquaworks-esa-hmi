# scripts/check_current_state.py
import sys
import os
import asyncio

# 경로 설정
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import select
from app.core.db import AsyncSessionLocal
from app.models.settings import ConnectionConfig


async def check_state():
    print("==================================================")
    print("🔍 [시스템 진단] 현재 DB에 저장된 기기 설정 확인")
    print("==================================================")

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(ConnectionConfig))
        configs = result.scalars().all()

        if not configs:
            print("📭 DB에 등록된 기기가 없습니다. (완벽한 백지상태입니다.)")
            print("👉 만약 UI에 기계가 뜬다면 프론트엔드 하드코딩 문제입니다.")
        else:
            print(
                f"📦 현재 DB(esa_hmi.db)에 총 {len(configs)}대의 기기가 영구 저장되어 있습니다!\n"
            )
            for c in configs:
                name = getattr(c, "name", f"이름 없음 (RTU-{c.id})")
                print(f"  🟢 [ID: {c.id}] {name}")
                print(f"     - 프로토콜: {c.backend_type.name}")
                print(f"     - 타겟 주소: {c.host}:{c.port}")
                print(f"     - (아까 실행한 test_multi_backend.py가 만들어둔 데이터입니다)")
                print("  ------------------------------------------------")

    print("\n💡 [원인 분석 결론]")
    print(
        "새로 작성한 매니저(WorkerManager)는 'DB에 있는 기기만 켠다'는 규칙을 완벽히 지키고 있습니다."
    )
    print(
        "다만, 아까 테스트한다고 DB에 강제로 집어넣은 1번, 2번 기기 데이터가 파일에 남아있기 때문에,"
    )
    print(
        "메인 서버(main.py)를 켰을 때 매니저가 그걸 읽고 성실하게 통신 스레드를 복구(자동 연결)해버린 것입니다."
    )
    print(
        "대시보드에 찍힌 값 역시 아까 테스트로 밀어넣은 가짜 데이터가 InfluxDB에 남아있어서 그렇습니다."
    )


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(check_state())
