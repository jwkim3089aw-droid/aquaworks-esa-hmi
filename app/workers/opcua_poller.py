# app/workers/opcua_poller.py
import asyncio
import logging
import math
import os
from time import time
from asyncua import Client, ua
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import engine
from app.models.settings import ConnectionConfig, BackendType
from app.stream.state import ingest_q, command_q, Sample

# 로그 설정
logging.getLogger("asyncua").setLevel(logging.WARNING)
logging.getLogger("uaprocessor").setLevel(logging.WARNING)
logger = logging.getLogger("OPCUA_POLLER")

AsyncSessionLocal = async_sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
)


def _safe_float(val, default=0.0) -> float:
    if val is None:
        return default
    try:
        f_val = float(val)
        if math.isnan(f_val) or math.isinf(f_val):
            return default
        return f_val
    except:
        return default


async def get_opc_config():
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(ConnectionConfig).where(ConnectionConfig.id == 1))
        config = res.scalar_one_or_none()
        if config and config.backend_type == BackendType.OPCUA:
            return {"host": config.host, "port": config.port, "ns": config.namespace_uri}
        return None


async def run_opcua_poller():
    logger.info("🚀 OPC UA Worker Started (Fixed Valve Mapping)")

    while True:
        conf = await get_opc_config()
        if not conf:
            conf = {
                "host": os.getenv("OPCUA_HOST", "127.0.0.1"),
                "port": 4845,
                "ns": "http://aquaworks.co.kr/ESA",
            }

        url = f"opc.tcp://{conf['host']}:{conf['port']}/freeopcua/server/"
        ns_uri = conf.get("ns", "http://aquaworks.co.kr/ESA")

        try:
            async with Client(url=url) as client:
                logger.info(f"✅ Connected to {url}")

                # 네임스페이스 인덱스
                try:
                    idx = await client.get_namespace_index(ns_uri)
                except:
                    idx = 2

                # -----------------------------------------------------
                # [1] 노드 찾기 (다양한 이름 시도)
                # -----------------------------------------------------
                def find_node(candidates):
                    """여러 이름 중 하나라도 걸리면 그 노드 반환"""
                    for name in candidates:
                        try:
                            node = client.get_node(f"ns={idx};s={name}")
                            return node
                        except:
                            continue
                    return None

                # 읽기 매핑 (가장 중요한 부분)
                # 여기서 찾은 노드 객체를 쓰기 때도 그대로 쓸 것임!
                read_map = {}
                read_map["do"] = find_node(["DO", "do"])
                read_map["mlss"] = find_node(["MLSS", "mlss"])
                read_map["temp"] = find_node(["Temp", "temp", "Temperature"])
                read_map["ph"] = find_node(["pH", "ph"])
                read_map["air_flow"] = find_node(["AirFlow", "airflow"])
                read_map["power"] = find_node(["Power", "power"])
                read_map["energy"] = find_node(["Energy", "energy"])

                # 제어 변수들 (펌프, 밸브)
                read_map["pump_hz"] = find_node(["PumpHz", "pump_hz", "PumpSpeed"])

                # [핵심 수정] 밸브 노드 찾기 우선순위: Valve -> ValvePos
                # 이전에 작동했던 이름인 "Valve"를 먼저 찾게 함
                read_map["valve_pos"] = find_node(["Valve", "ValvePos", "valve", "valve_pos"])

                # -----------------------------------------------------
                # [2] 쓰기 매핑 (읽기 노드 재사용 -> 불일치 해결)
                # -----------------------------------------------------
                write_map = {}

                if read_map["pump_hz"]:
                    write_map["set_hz"] = read_map["pump_hz"]

                if read_map["valve_pos"]:
                    # HMI가 보내는 키("valve_pos")를 실제 찾은 노드에 연결
                    write_map["valve_pos"] = read_map["valve_pos"]
                    write_map["set_air"] = read_map["valve_pos"]  # 호환성
                    logger.info(f"🔑 Valve Mapped to Node: {read_map['valve_pos']}")
                else:
                    logger.error("❌ CRITICAL: Valve Node Not Found on Server!")

                logger.info("Looping...")

                while True:
                    # A. [WRITE] 명령 처리
                    while not command_q.empty():
                        key, val = await command_q.get()

                        target_node = write_map.get(key)
                        if target_node:
                            try:
                                f_val = float(val)
                                # 범위 제한
                                if key in ["valve_pos", "set_air"]:
                                    f_val = max(0.0, min(100.0, f_val))
                                elif key == "set_hz":
                                    f_val = max(0.0, min(60.0, f_val))

                                await target_node.write_value(
                                    ua.DataValue(ua.Variant(f_val, ua.VariantType.Double))
                                )
                            except Exception as e:
                                logger.error(f"❌ Write Fail ({key}): {e}")
                        else:
                            logger.warning(f"⚠️ No mapped node for command: {key}")

                        command_q.task_done()

                    # B. [READ] 데이터 읽기
                    try:
                        # 매핑된 노드만 읽기 리스트 생성
                        active_tags = [tag for tag, node in read_map.items() if node is not None]
                        nodes_to_read = [read_map[tag] for tag in active_tags]

                        if nodes_to_read:
                            values = await client.read_values(nodes_to_read)
                            data = dict(zip(active_tags, values))

                            s = Sample(
                                ts=time(),
                                do=_safe_float(data.get("do")),
                                mlss=_safe_float(data.get("mlss")),
                                temp=_safe_float(data.get("temp")),
                                ph=_safe_float(data.get("ph")),
                                air_flow=_safe_float(data.get("air_flow")),
                                power=_safe_float(data.get("power")),
                                energy_kwh=_safe_float(data.get("energy")),
                                pump_hz=_safe_float(data.get("pump_hz")),
                                valve_pos=_safe_float(data.get("valve_pos")),
                            )
                            await ingest_q.put(s)

                        await asyncio.sleep(0.5)

                    except Exception as e:
                        logger.error(f"Polling Error: {e}")
                        break

        except Exception as e:
            logger.error(f"Connection Error: {e}")
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(run_opcua_poller())
