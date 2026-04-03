# app/services/history.py
import os
import logging
import math
from datetime import datetime, timezone
from logging.handlers import TimedRotatingFileHandler
from typing import Any, Dict, Optional

try:
    import pandas as pd
    import numpy as np
except ImportError:
    pd = None  # type: ignore
    np = None

# 🚀 중앙 통제식 경로 설정 불러오기
from app.core.config import get_settings
from app.core.tsdb import tsdb

settings = get_settings()

# =====================================================================
# 📝 History 전용 애플리케이션 이벤트 로거 세팅 (30일 Retention 적용)
# =====================================================================
logger = logging.getLogger("ESA_HMI.history")
logger.setLevel(logging.INFO)

log_file_path = settings.APP_LOG_DIR / "history_query.log"
file_handler = TimedRotatingFileHandler(
    filename=str(log_file_path),
    when="midnight",
    interval=1,
    backupCount=30,  # 30일 보관 후 자동 삭제
    encoding="utf-8",
)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - [%(funcName)s] %(message)s")
file_handler.setFormatter(formatter)

if not logger.handlers:
    logger.addHandler(file_handler)

    # 🚀 [PATCH] 개발 모드(ESA_DEV=1)일 때만 콘솔 출력 활성화 (NSSM 로그 중복 방지)
    if os.getenv("ESA_DEV") == "1":
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)


def get_auto_window(start_dt: datetime, end_dt: datetime, target_points: int = 1500) -> str:
    """
    [핵심 로직] 조회 기간에 따라 최적의 데이터 간격(Window)을 계산합니다.
    목표 포인트(target_points) 수를 넘지 않도록 간격을 자동으로 넓힙니다.
    """
    total_seconds = (end_dt - start_dt).total_seconds()

    if total_seconds <= 0:
        return "1s"

    interval_sec = total_seconds / target_points

    if interval_sec <= 1:
        return "1s"
    elif interval_sec < 60:
        return f"{int(math.ceil(interval_sec))}s"
    elif interval_sec < 3600:
        return f"{int(math.ceil(interval_sec / 60))}m"
    else:
        return f"{int(math.ceil(interval_sec / 3600))}h"


def fetch_history_data(start_dt: datetime, end_dt: datetime) -> Optional[Dict[str, Any]]:
    """
    InfluxDB에서 기간별 데이터를 조회합니다.
    데이터 양이 많을 경우 DB단에서 평균(Mean) 처리하여 가져옵니다.
    """
    if pd is None:
        logger.error("Pandas library is not installed.")
        return None

    try:
        # 1. Timezone 처리 (InfluxDB는 UTC 기준)
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=timezone.utc)

        window = get_auto_window(start_dt, end_dt)
        logger.info(
            f"🔍 [History] Searching... Window: {window} | Range: {start_dt.strftime('%Y-%m-%d %H:%M:%S')} ~ {end_dt.strftime('%Y-%m-%d %H:%M:%S')}"
        )

        # 2. InfluxDB Flux 쿼리 작성
        query = f"""
        from(bucket: "{tsdb.bucket}")
          |> range(start: {start_dt.isoformat()}, stop: {end_dt.isoformat()})
          |> filter(fn: (r) => r["_measurement"] == "sensors")
          |> aggregateWindow(every: {window}, fn: mean, createEmpty: false)
          |> pivot(rowKey:["_time"], columnKey: ["tag_name"], valueColumn: "_value")
          |> drop(columns: ["_start", "_stop", "_measurement"])
        """

        # 3. 쿼리 실행
        raw_df = tsdb.query_raw(query)

        if raw_df is None:
            logger.warning("⚠️ [History] Query returned None (No data matched the query).")
            return None

        df = raw_df[0] if isinstance(raw_df, list) else raw_df

        if not hasattr(df, "empty") or df.empty:
            logger.warning("⚠️ [History] DataFrame is empty.")
            return None

        # 4. 데이터 후처리 (Pandas)
        if "_time" in df.columns:
            df["_time"] = pd.to_datetime(df["_time"]).dt.tz_convert("Asia/Seoul")
        else:
            logger.error(
                "🚨 [History] '_time' column missing in result. Invalid DB schema or pivot failed."
            )
            return None

        df = df.sort_values(by="_time")
        times = df["_time"].dt.strftime("%Y-%m-%d %H:%M:%S").tolist()

        target_keys = ["DO", "MLSS", "Temp", "pH", "AirFlow", "Power", "Energy", "PumpHz"]
        series_data = {}

        for key in target_keys:
            if key in df.columns:
                series_data[key] = df[key].where(pd.notnull(df[key]), None).tolist()
            else:
                series_data[key] = [None] * len(times)

        logger.info(f"✅ [History] Fetch Success | Rows: {len(times)} | Step: {window}")
        return {"times": times, "series": series_data}

    except Exception as e:
        # 🚀 [개선점] 콘솔에만 출력되던 traceback을 파일 로거로 안전하게 격리 저장!
        logger.exception(f"🚨 [History] Critical Query Error: {e}")
        return None
