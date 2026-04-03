# app/workers/ai/utils.py
import os
import time
import random
import shutil
import lzma
import pickle
import math
from pathlib import Path
from typing import Any, Optional
import torch

from app.workers.ai.config import STRICT_DURABILITY, STRICT_DIRSYNC


def _safe_float_opt(x: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if x is None or isinstance(x, bool):
            return default
        v = float(x)
        return v if math.isfinite(v) else default
    except Exception:
        return default


def _safe_float(x: Any, default: float) -> float:
    v = _safe_float_opt(x, default=None)
    return v if v is not None else default


def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def _unique_suffix() -> str:
    return f"{os.getpid()}.{time.time_ns()}.{random.getrandbits(32):08x}"


def _unique_tmp(path: Path) -> Path:
    return path.with_name(f"{path.name}.tmp.{_unique_suffix()}")


def _unique_corrupt(path: Path) -> Path:
    return path.with_name(f"{path.name}.corrupt.{_unique_suffix()}")


def _fsync_fd(fd: int) -> None:
    try:
        os.fsync(fd)
    except Exception:
        if STRICT_DURABILITY:
            raise


def _fsync_path_ro(path: Path) -> None:
    fd = None
    try:
        flags = os.O_RDONLY
        if hasattr(os, "O_CLOEXEC"):
            flags |= getattr(os, "O_CLOEXEC")
        fd = os.open(str(path), flags)
        os.fsync(fd)
    except Exception:
        if STRICT_DURABILITY:
            raise
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except Exception:
                pass


def _fsync_dir(target_path: Path) -> None:
    if os.name == "nt":
        return
    parent = target_path.parent
    if not parent.is_dir():
        return
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= getattr(os, "O_DIRECTORY")
    if hasattr(os, "O_CLOEXEC"):
        flags |= getattr(os, "O_CLOEXEC")
    fd = None
    try:
        fd = os.open(str(parent), flags)
        os.fsync(fd)
    except Exception:
        if STRICT_DURABILITY and STRICT_DIRSYNC:
            raise
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except Exception:
                pass


def _atomic_replace_with_barriers(tmp: Path, dst: Path) -> None:
    os.replace(tmp, dst)
    _fsync_path_ro(dst)
    _fsync_dir(dst)


def _gc_files(dir_path: Path, pattern: str, older_than_sec: int = 7 * 24 * 3600) -> None:
    try:
        now = time.time()
        for p in dir_path.glob(pattern):
            try:
                if not p.is_file():
                    continue
                if older_than_sec <= 0:
                    p.unlink()
                else:
                    if now - p.stat().st_mtime > older_than_sec:
                        p.unlink()
            except Exception:
                pass
    except Exception:
        pass


def _durable_backup(src: Path, bak: Path) -> None:
    tmp = _unique_tmp(bak)
    try:
        with open(src, "rb") as r, open(tmp, "wb") as w:
            shutil.copyfileobj(r, w)
            w.flush()
            _fsync_fd(w.fileno())
        _fsync_path_ro(tmp)
        _atomic_replace_with_barriers(tmp, bak)
    except Exception:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass
        raise


def _save_torch_atomic(dst: Path, obj: dict) -> None:
    # 🚀 [PATCH] 대상 경로 부모 폴더 자동 생성 (.data/ai_models 등 격리 아키텍처 지원)
    dst.parent.mkdir(parents=True, exist_ok=True)

    tmp = _unique_tmp(dst)
    try:
        with open(tmp, "wb") as f:
            torch.torch.save(obj, f)
            f.flush()
            _fsync_fd(f.fileno())
        _fsync_path_ro(tmp)
        _atomic_replace_with_barriers(tmp, dst)
    except Exception:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass
        raise


def _save_lzma_pickle_atomic(dst: Path, data: Any) -> None:
    # 🚀 [PATCH] 대상 경로 부모 폴더 자동 생성 (.data/ai_models 등 격리 아키텍처 지원)
    dst.parent.mkdir(parents=True, exist_ok=True)

    tmp = _unique_tmp(dst)
    try:
        with open(tmp, "wb") as raw:
            with lzma.open(raw, "wb") as zf:
                pickle.dump(data, zf)
                zf.flush()
            raw.flush()
            _fsync_fd(raw.fileno())
        _fsync_path_ro(tmp)
        _atomic_replace_with_barriers(tmp, dst)
    except Exception:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass
        raise


class EMAFilter:
    __slots__ = ("alpha", "value")

    def __init__(self, alpha: float = 0.3):
        self.alpha = alpha
        self.value: Optional[float] = None

    def update(self, new_val: Optional[float]) -> float:
        safe_val = _safe_float_opt(new_val, default=None)
        if safe_val is None:
            return self.value if self.value is not None else 0.0
        if self.value is None:
            self.value = safe_val
        else:
            self.value = self.alpha * safe_val + (1 - self.alpha) * self.value
        return self.value


class SafetyLayer:
    @staticmethod
    def apply_guard(current_hz: float, proposed_hz: float, config) -> float:
        max_delta_hz = 2.0

        delta = proposed_hz - current_hz
        if delta > max_delta_hz:
            safe_hz = current_hz + max_delta_hz
        elif delta < -max_delta_hz:
            safe_hz = current_hz - max_delta_hz
        else:
            safe_hz = proposed_hz

        # 🚀 [FIX] 축 파손 방지를 위한 절대 하한선 40.0Hz 강제!
        actual_min_hz = max(40.0, config.min_hz)

        return max(actual_min_hz, min(config.max_hz, safe_hz))
