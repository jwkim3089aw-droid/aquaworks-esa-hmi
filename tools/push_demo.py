# tools/push_demo.py
# [NEW] UI 파이프라인 강제 주입: Modbus 없이도 트렌드가 그려지는지 확인
from __future__ import annotations
import asyncio
import math
from time import time
from argparse import ArgumentParser

from app.stream.state import ingest_q, Sample

async def main() -> None:
    ap = ArgumentParser()
    ap.add_argument("--n", type=int, default=60, help="샘플 개수")
    ap.add_argument("--dt", type=float, default=0.5, help="샘플 간격(s)")
    args = ap.parse_args()

    print(f"[PUSH] sending {args.n} samples to ingest_q (dt={args.dt}s)")
    t0 = time()
    for i in range(args.n):
        el = time() - t0
        phase = 2.0 * math.pi * (el / 10.0)
        s = Sample(
            ts=time(),
            do=1.6 + 0.2*math.sin(phase),
            mlss=3500 + 10*math.sin(phase/2),
            temp=22.0 + 0.05*math.sin(phase/3),
            ph=6.9 + 0.01*math.sin(phase/4),
            air_flow=180 + 2*math.sin(phase),
            power=3.2 + 0.1*math.sin(phase*1.1),
        )
        await ingest_q.put(s)
        await asyncio.sleep(args.dt)
    print("[PUSH] done")

if __name__ == "__main__":
    asyncio.run(main())
