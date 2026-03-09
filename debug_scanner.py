# debug_scanner.py (프로젝트 루트에 생성)
import asyncio
from asyncua import Client

# 서버 주소
URL = "opc.tcp://127.0.0.1:4840/freeopcua/server/"


async def scan_server():
    print(f"📡 서버({URL})에 접속 시도 중...")

    try:
        async with Client(url=URL) as client:
            print("✅ 접속 성공!")

            # 1. 네임스페이스 목록 출력
            print("\n[1] 네임스페이스 목록:")
            ns_array = await client.get_namespace_array()
            for i, ns in enumerate(ns_array):
                print(f"   Index {i}: {ns}")

            # 2. Objects 폴더 밑에 있는 거 다 뒤지기
            print("\n[2] Objects 폴더 스캔:")
            objects = client.nodes.objects
            children = await objects.get_children()

            for child in children:
                browse_name = await child.read_browse_name()
                print(f"   - 발견된 폴더/객체: {browse_name.Name} (NodeID: {child.nodeid})")

                # ESA_System이라고 의심되는 녀석 내부 스캔
                if "ESA" in browse_name.Name:
                    print(f"     ㄴ 🎯 ESA 시스템 내부 변수 스캔:")
                    vars = await child.get_children()
                    for v in vars:
                        v_name = await v.read_browse_name()
                        v_val = await v.read_value()
                        print(f"        🔹 {v_name.Name} = {v_val}")

    except ConnectionRefusedError:
        print("❌ 서버 연결 실패: 시뮬레이터(main.py)가 꺼져 있거나 포트가 막혔습니다.")
    except Exception as e:
        print(f"❌ 에러 발생: {e}")


if __name__ == "__main__":
    asyncio.run(scan_server())
