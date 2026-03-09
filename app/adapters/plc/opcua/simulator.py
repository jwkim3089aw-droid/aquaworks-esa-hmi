# app/adapters/plc/opcua/simulator.py
import asyncio
import logging
import math
import os
import random
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from asyncua import Server, ua

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    force=True,
)
_logger = logging.getLogger("OPCUA_SIM")
logging.getLogger("asyncua").setLevel(logging.WARNING)


@dataclass
class SimConfig:
    host: str = "127.0.0.1"
    port: int = 4840
    endpoint_path: str = "/freeopcua/server/"
    namespace_uri: str = "http://esa-hmi.com"
    interval: float = 1.0


async def _sim_loop(server: Server, idx: int, nodes: Dict[str, Any], interval: float):
    _logger.info(f"[SIM] Simulation loop started. Interval: {interval}s")

    state = {
        "timer": 0.0,
        "air_flow_base": 180.0,
        "pump_hz_base": 40.0,
        "energy_acc": 0.0,
    }

    while True:
        await asyncio.sleep(interval)
        state["timer"] += interval
        t = state["timer"]

        air_flow = state["air_flow_base"] + 10.0 * math.sin(t / 10.0) + random.uniform(-2, 2)
        pump_hz = state["pump_hz_base"] + 1.0 * math.sin(t / 5.0) + random.uniform(-0.5, 0.5)

        do_val = 1.5 + (air_flow - 150) * 0.01 + random.uniform(-0.05, 0.05)
        do_val = max(0.1, min(do_val, 8.0))

        power_val = 3.0 * ((pump_hz / 40.0) ** 3) + random.uniform(-0.1, 0.1)
        state["energy_acc"] += power_val * (interval / 3600.0)

        mlss_val = 3500.0 + 100.0 * math.sin(t / 60.0) + random.uniform(-10, 10)
        temp_val = 22.0 + 2.0 * math.sin(t / 300.0) + random.uniform(-0.1, 0.1)
        ph_val = 7.0 + 0.2 * math.sin(t / 100.0) + random.uniform(-0.05, 0.05)

        try:
            await nodes["DO"].write_value(round(do_val, 2))
            await nodes["MLSS"].write_value(round(mlss_val, 1))
            await nodes["Temp"].write_value(round(temp_val, 1))
            await nodes["pH"].write_value(round(ph_val, 2))
            await nodes["AirFlow"].write_value(round(air_flow, 1))
            await nodes["PumpHz"].write_value(round(pump_hz, 1))
            await nodes["Power"].write_value(round(power_val, 2))
            await nodes["Energy"].write_value(round(state["energy_acc"], 4))
        except Exception as e:
            _logger.error(f"[SIM] Error updating nodes: {e}")


async def run_opcua_sim(host: Optional[str] = None, port: Optional[int] = None) -> None:
    cfg = SimConfig(
        host=host or os.getenv("OPCUA_HOST", "127.0.0.1"),
        port=int(port or os.getenv("OPCUA_PORT", 4840)),
    )

    server = Server()
    await server.init()

    endpoint = f"opc.tcp://{cfg.host}:{cfg.port}{cfg.endpoint_path}"
    server.set_endpoint(endpoint)
    server.set_server_name("ESA_HMI_Simulation_Server")

    idx = await server.register_namespace(cfg.namespace_uri)
    _logger.info(f"[INIT] Namespace registered: '{cfg.namespace_uri}' (idx={idx})")

    objects = server.nodes.objects
    # 폴더 생성
    plc_obj = await objects.add_object(idx, "ESA_PLC")

    nodes = {}
    tags = [
        ("DO", 1.5),
        ("MLSS", 3500.0),
        ("Temp", 22.0),
        ("pH", 6.9),
        ("AirFlow", 180.0),
        ("PumpHz", 40.0),
        ("Power", 3.0),
        ("Energy", 0.0),
    ]

    for name, init_val in tags:
        # [핵심 수정] NodeID를 명시적으로 지정! (ns={idx};s={name})
        # 이렇게 해야 Client가 's=DO' 형태로 찾을 수 있음
        node_id = f"ns={idx};s={name}"

        node = await plc_obj.add_variable(node_id, name, init_val, ua.VariantType.Double)
        await node.set_writable()
        nodes[name] = node

    _logger.info(f"[INIT] Nodes created with Explicit IDs: {list(nodes.keys())}")
    _logger.info(f"[SERVER] Starting OPC UA Server at {endpoint}")

    async with server:
        sim_task = asyncio.create_task(_sim_loop(server, idx, nodes, cfg.interval))
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            _logger.info("[SERVER] Stopping...")
        finally:
            sim_task.cancel()
            await server.stop()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()

    try:
        asyncio.run(run_opcua_sim(host=args.host, port=args.port))
    except KeyboardInterrupt:
        print("\n[CLI] Terminated.")
