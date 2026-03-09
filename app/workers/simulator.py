# app/workers/simulator.py
# [UPGRADED] 시뮬레이터 매니저: 내부 랜덤 생성 or 외부 통신 서버(Modbus/OPCUA) 실행
from __future__ import annotations

import asyncio
import logging
import os
from math import sin, pi
from random import random
from time import time

from app.stream.state import ingest_q, Sample

# [IMPORT] 우리가 정리한 Modbus/OPC UA 시뮬레이터 함수들 가져오기
# (파일 경로가 정확해야 합니다. app/adapters/plc/... 구조 기준)
try:
    from app.adapters.plc.modbus.simulator import run_tcp_sim
    from app.adapters.plc.opcua.simulator import run_opcua_sim
except ImportError:
    # 혹시 경로가 꼬여서 import 실패해도 죽지 않게 처리
    run_tcp_sim = None
    run_opcua_sim = None

_logger = logging.getLogger("WORKER_SIM")

# 기본 주기(초)
SIM_DT = 0.5


def _jitter(span: float) -> float:
    """[-span, +span] 범위의 작은 랜덤 노이즈."""
    return (2.0 * random() - 1.0) * span


async def start_network_simulators():
    """
    환경변수를 확인하여 Modbus TCP 또는 OPC UA '서버'를 백그라운드 태스크로 띄웁니다.
    """
    # 1. Modbus Simulator 확인
    if os.getenv("MODBUS_START_SIM") == "1" and run_tcp_sim:
        host = os.getenv("MODBUS_TCP_HOST", "127.0.0.1")
        port = int(os.getenv("MODBUS_TCP_PORT", 5020))
        _logger.info(f"[SIM-MGR] Launching Modbus TCP Server at {host}:{port}")
        # 백그라운드에서 영원히 돔
        asyncio.create_task(run_tcp_sim(host=host, port=port))

    # 2. OPC UA Simulator 확인
    if os.getenv("OPCUA_START_SIM") == "1" and run_opcua_sim:
        host = os.getenv("OPCUA_HOST", "127.0.0.1")
        port = int(os.getenv("OPCUA_PORT", 4840))
        _logger.info(f"[SIM-MGR] Launching OPC UA Server at {host}:{port}")
        # 백그라운드에서 영원히 돔
        asyncio.create_task(run_opcua_sim(host=host, port=port))


async def sim_loop(dt: float = SIM_DT) -> None:
    """
    [메인 로직]
    1. 네트워크 시뮬레이터(서버)가 필요하면 실행시킵니다.
    2. 만약 'ESA_BACKEND'가 'dummy' 모드라면 -> 여기서 직접 가짜 데이터를 생성해서 큐에 넣습니다.
       (Modbus나 OPCUA 모드라면, 별도의 Poller가 데이터를 넣을 테니 여기선 아무것도 안 함)
    """

    # 1. 서버(시뮬레이터) 실행 (Modbus/OPCUA 켜져있을 경우)
    await start_network_simulators()

    # 2. 백엔드 모드 확인
    backend_mode = os.getenv("ESA_BACKEND", "dummy").lower()

    if backend_mode != "dummy":
        _logger.info(f"[SIM-MGR] Backend is '{backend_mode}'. Internal data generator PAUSED.")
        # Modbus나 OPCUA 모드일 때는, 이 함수는 서버만 띄워주고 할 일이 끝납니다.
        # 데이터 수집은 'modbus_poller.py' 또는 'opcua_client.py'가 담당해야 중복이 안 됩니다.
        while True:
            await asyncio.sleep(3600)  # 그냥 대기 (프로세스 종료 방지용)
        return

    # -----------------------------------------------------------
    # 아래는 'dummy' 모드일 때만 실행되는 내부 랜덤 생성기 (기존 코드 유지)
    # -----------------------------------------------------------
    _logger.info("[SIM-MGR] Backend is 'dummy'. Starting internal random generator.")
    t0 = time()

    while True:
        now = time()
        elapsed = now - t0
        phase = 2 * pi * (elapsed / 60.0)  # 1분 주기 진동

        # --- Air flow (L/min) ---
        air_flow = 180.0 + 70.0 * (0.5 + 0.5 * sin(phase)) + _jitter(5.0)
        air_flow = max(50.0, min(400.0, air_flow))

        # --- DO (mg/L) ---
        do = 1.5 + 1.0 * (0.5 + 0.5 * sin(phase - 0.3)) + _jitter(0.2)
        do = max(0.0, min(8.0, do))

        # --- MLSS (mg/L) ---
        mlss = 3500.0 + 800.0 * (0.5 + 0.5 * sin(phase / 2.0)) + _jitter(200.0)
        mlss = max(200.0, min(10000.0, mlss))

        # --- Temp (°C) ---
        temp = 20.0 + 6.0 * (0.5 + 0.5 * sin(phase / 3.0)) + _jitter(0.5)
        temp = max(5.0, min(40.0, temp))

        # --- pH ---
        ph = 7.0 + 0.4 * (0.5 + 0.5 * sin(phase / 4.0)) + _jitter(0.05)
        ph = max(6.0, min(8.5, ph))

        # --- Power (kW) ---
        power = 2.0 + 0.01 * max(0.0, air_flow - 100.0) + _jitter(0.2)
        power = max(0.3, min(20.0, power))

        s = Sample(
            ts=now,
            do=do,
            mlss=mlss,
            temp=temp,
            ph=ph,
            air_flow=air_flow,
            power=power,
        )

        await ingest_q.put(s)
        await asyncio.sleep(dt)
