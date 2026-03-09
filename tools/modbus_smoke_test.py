# tools/modbus_smoke_test.py
from __future__ import annotations

import argparse
import asyncio
import logging
import inspect
from typing import Any, Awaitable, Callable, cast

log = logging.getLogger("smoke.modbus")
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

# pymodbus 3.x 우선 임포트, 실패 시 2.5.x 호환
try:
    from pymodbus.client import AsyncModbusTcpClient as _TcpClient  # type: ignore
    from pymodbus.client import AsyncModbusSerialClient as _SerialClient  # type: ignore
except Exception:  # pragma: no cover
    try:
        # 2.5.x (deprecated 경로)
        from pymodbus.client.async import AsyncModbusTCPClient as _TcpClient  # type: ignore
        from pymodbus.client.async import AsyncModbusSerialClient as _SerialClient  # type: ignore
    except Exception:  # 최후 보루
        _TcpClient = Any  # type: ignore
        _SerialClient = Any  # type: ignore

_ReadFn = Callable[..., Awaitable[Any]]


def _fmt_regs(rr: Any) -> str:
    if not rr:
        return "<None>"
    if hasattr(rr, "isError") and callable(getattr(rr, "isError")) and rr.isError():  # type: ignore[call-arg]
        return f"<Error {rr}>"
    data = getattr(rr, "registers", None)
    if data is None:
        data = getattr(rr, "bits", None)
    return str(data)


async def _safe_call(fn: _ReadFn, addr: int, count: int, unit: int) -> Any:
    """
    pymodbus 버전별 시그니처 차이를 try-다단계로 흡수.
    """
    try:
        return await fn(addr, count=count, unit=unit)
    except TypeError as e1:
        try:
            return await fn(addr, count=count, slave=unit)  # 일부 버전은 slave 사용
        except TypeError as e2:
            try:
                return await fn(addr, count=count)  # RTU 경우 unit 고정인 구현도 존재
            except Exception as e3:
                raise RuntimeError(f"modbus call failed: {e1}; {e2}; {e3}") from e3


async def _maybe_await_close(client: Any) -> None:
    close = getattr(cast(object, client), "close", None)  # [CHANGED]
    if close is None:
        return
    if asyncio.iscoroutinefunction(close):
        await close()  # type: ignore[misc]
    else:
        close()


def _new_serial_client(
    device: str,
    baud: int,
    stopbits: int,
    bytesize: int,
    parity: str,
    timeout: float = 2.0,
) -> Any:
    """
    3.x: AsyncModbusSerialClient(port=..., baudrate=..., bytesize=..., parity=..., stopbits=..., timeout=...)
    2.5.x: AsyncModbusSerialClient(method='rtu', port=..., baudrate=..., ...)
    (사인검사로 'method' 지원 여부를 우선 판별)
    """
    kwargs = dict(port=device, baudrate=baud, stopbits=stopbits, bytesize=bytesize, parity=parity, timeout=timeout)
    try:
        sig = inspect.signature(_SerialClient)  # type: ignore[misc]
    except Exception:
        sig = None

    if sig and "method" in sig.parameters:
        # 2.5.x 경로
        try:
            return cast(Callable[..., Any], _SerialClient)(method="rtu", **kwargs)  # [CHANGED]
        except TypeError:
            return cast(Callable[..., Any], _SerialClient)(**kwargs)  # [CHANGED]
    else:
        # 3.x 경로
        try:
            return cast(Callable[..., Any], _SerialClient)(**kwargs)  # [CHANGED]
        except TypeError:
            return cast(Callable[..., Any], _SerialClient)(method="rtu", **kwargs)  # [CHANGED]


def _new_tcp_client(host: str, port: int) -> Any:  # [ADDED]
    ctor = cast(Callable[..., Any], _TcpClient)
    try:
        return ctor(host=host, port=port)
    except TypeError:
        return ctor(host, port)  # 일부 구버전 시그니처


async def _run_tcp(host: str, port: int, unit: int, count: int) -> int:
    client: Any = _new_tcp_client(host, port)  # [CHANGED]
    log.info(f"[SMOKE] TCP connect to {host}:{port}")
    await client.connect()  # type: ignore[attr-defined]
    try:
        connected = bool(getattr(cast(object, client), "connected", False))  # [CHANGED]
        log.info(f"[SMOKE] connect ok={connected} connected={connected}")

        rr_ir = await _safe_call(getattr(cast(object, client), "read_input_registers"), 0, count, unit)   # [CHANGED]
        log.info(f"IR: {_fmt_regs(rr_ir)}")

        rr_hr = await _safe_call(getattr(cast(object, client), "read_holding_registers"), 0, count, unit)  # [CHANGED]
        log.info(f"HR: {_fmt_regs(rr_hr)}")

        rr_co = await _safe_call(getattr(cast(object, client), "read_coils"), 0, count, unit)             # [CHANGED]
        log.info(f"Coils: {_fmt_regs(rr_co)}")

        rr_di = await _safe_call(getattr(cast(object, client), "read_discrete_inputs"), 0, count, unit)   # [CHANGED]
        log.info(f"DI: {_fmt_regs(rr_di)}")

        errs = [
            getattr(rr_ir, "isError", lambda: False)(),
            getattr(rr_hr, "isError", lambda: False)(),
            getattr(rr_co, "isError", lambda: False)(),
            getattr(rr_di, "isError", lambda: False)(),
        ]
        return 0 if not any(errs) else 2
    finally:
        await _maybe_await_close(client)


async def _run_rtu(
    device: str,
    baud: int,
    unit: int,
    count: int,
    stopbits: int = 1,
    bytesize: int = 8,
    parity: str = "N",
) -> int:
    client: Any = _new_serial_client(device, baud, stopbits, bytesize, parity)
    log.info(f"[SMOKE] RTU open {device} ({baud}bps)")
    await client.connect()  # type: ignore[attr-defined]
    try:
        connected = bool(getattr(cast(object, client), "connected", False))  # [CHANGED]
        log.info(f"[SMOKE] open ok={connected} connected={connected}")

        rr_ir = await _safe_call(getattr(cast(object, client), "read_input_registers"), 0, count, unit)   # [CHANGED]
        log.info(f"IR: {_fmt_regs(rr_ir)}")

        rr_hr = await _safe_call(getattr(cast(object, client), "read_holding_registers"), 0, count, unit) # [CHANGED]
        log.info(f"HR: {_fmt_regs(rr_hr)}")

        ok = not (getattr(rr_ir, "isError", lambda: False)() or getattr(rr_hr, "isError", lambda: False)())
        return 0 if ok else 2
    finally:
        await _maybe_await_close(client)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Modbus smoke test (TCP/RTU)")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--tcp", action="store_true", help="use Modbus TCP")
    g.add_argument("--rtu", action="store_true", help="use Modbus RTU (serial)")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=5020)
    p.add_argument("--device", default="COM3", help="Serial device (e.g., COM3 or /dev/ttyUSB0)")
    p.add_argument("--baud", type=int, default=9600)
    p.add_argument("--unit", type=int, default=1)
    p.add_argument("--count", type=int, default=16)
    return p.parse_args()


async def _amain() -> int:
    a = _parse_args()
    if a.tcp:
        return await _run_tcp(a.host, a.port, a.unit, a.count)
    else:
        return await _run_rtu(a.device, a.baud, a.unit, a.count)


def main() -> None:
    raise SystemExit(asyncio.run(_amain()))


if __name__ == "__main__":
    main()
