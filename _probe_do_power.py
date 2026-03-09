# code/_probe_do_power.py
from __future__ import annotations

import argparse
import math
from statistics import mean
from typing import Any, Iterable, List, Tuple, Dict

try:
    # ESA_HMI 런타임에서 제공되는 함수
    from app.stream.state import get_last  # type: ignore
except Exception:
    get_last = None  # type: ignore


def _nan_aware(values: Iterable[Any]) -> List[float]:
    """
    입력에 숫자/문자열 섞여 와도 안전하게 float 변환 후 NaN 제외.
    (Pylance: '불필요한 isinstance' 경고 제거)
    """
    out: List[float] = []
    for v in values:
        try:
            f = float(v)  # type: ignore[arg-type]
        except Exception:
            continue
        if not math.isnan(f):
            out.append(f)
    return out


def _summarize(xs: List[Any], data: Dict[str, List[Any]], key: str) -> Tuple[int, float, float, float]:
    arr = _nan_aware(data.get(key, []))
    n = len(arr)
    if n == 0:
        return 0, float("nan"), float("nan"), float("nan")
    return n, arr[-1], mean(arr), max(arr)


def run(window: int = 300) -> int:
    if get_last is None:
        print("[WARN] app.stream.state.get_last 가 없습니다. ESA_HMI 환경에서 실행하세요.")
        return 1

    xs, data = get_last(window)  # type: ignore[misc]
    n_do, last_do, avg_do, max_do = _summarize(xs, data, "do")
    n_pw, last_pw, avg_pw, max_pw = _summarize(xs, data, "power")

    print("=== Probe: DO & Power ===")
    print(f"- samples window: {len(xs)}")
    print(f"- DO:    n={n_do:>4} | last={last_do:.3f} | avg={avg_do:.3f} | max={max_do:.3f}")
    print(f"- Power: n={n_pw:>4} | last={last_pw:.3f} | avg={avg_pw:.3f} | max={max_pw:.3f}")

    if n_do and n_pw:
        # 최근 60개만 사용한 간단 공분산 지표
        k = min(60, n_do, n_pw)
        do_tail = _nan_aware(data.get("do", [])[-k:])
        pw_tail = _nan_aware(data.get("power", [])[-k:])
        if len(do_tail) == len(pw_tail) and len(do_tail) >= 3:
            do_m, pw_m = mean(do_tail), mean(pw_tail)
            cov = mean([(d - do_m) * (p - pw_m) for d, p in zip(do_tail, pw_tail)])
            print(f"- crude cov(DO, Power) over last {k} = {cov:.6f}")
    return 0


def _parse() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Probe DO & Power from runtime buffer")
    ap.add_argument("--window", type=int, default=300, help="seconds (approx. samples)")
    return ap.parse_args()


if __name__ == "__main__":
    args = _parse()
    raise SystemExit(run(args.window))
