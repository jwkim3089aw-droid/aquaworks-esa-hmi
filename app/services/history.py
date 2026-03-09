# app/services/history.py
import traceback
import logging
import math
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

try:
    import pandas as pd
    import numpy as np
except ImportError:
    pd = None  # type: ignore
    np = None

from app.core.tsdb import tsdb

logger = logging.getLogger("ESA_HMI.history")


def get_auto_window(start_dt: datetime, end_dt: datetime, target_points: int = 1500) -> str:
    """
    [핵심 로직] 조회 기간에 따라 최적의 데이터 간격(Window)을 계산합니다.
    목표 포인트(target_points) 수를 넘지 않도록 간격을 자동으로 넓힙니다.

    :param start_dt: 시작 시간
    :param end_dt: 종료 시간
    :param target_points: 차트에 표현할 목표 점의 개수 (기본 1500개)
    :return: InfluxDB Flux 호환 기간 문자열 (예: '1s', '10s', '2m', '1h')
    """
    total_seconds = (end_dt - start_dt).total_seconds()

    # 데이터가 너무 적으면 그냥 1초 단위
    if total_seconds <= 0:
        return "1s"

    # 이상적인 간격(초) 계산
    interval_sec = total_seconds / target_points

    if interval_sec <= 1:
        return "1s"  # 1초 미만은 1초로 고정
    elif interval_sec < 60:
        return f"{int(math.ceil(interval_sec))}s"  # 초 단위 (예: 10s)
    elif interval_sec < 3600:
        return f"{int(math.ceil(interval_sec / 60))}m"  # 분 단위 (예: 2m)
    else:
        return f"{int(math.ceil(interval_sec / 3600))}h"  # 시간 단위 (예: 1h)


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

        # 2. 동적 윈도우 계산 (SCADA 핵심 최적화)
        # 기간이 길수록 window 값이 커짐 (예: '1s' -> '5m')
        window = get_auto_window(start_dt, end_dt)
        logger.info(f"[History] Searching... Window Size: {window} (Range: {start_dt} ~ {end_dt})")

        # 3. InfluxDB Flux 쿼리 작성
        # aggregateWindow: 지정된 시간(window)마다 데이터의 평균(mean)을 구함
        # pivot: 태그별로 컬럼을 회전시켜 DataFrame 변환 준비
        query = f"""
        from(bucket: "{tsdb.bucket}")
          |> range(start: {start_dt.isoformat()}, stop: {end_dt.isoformat()})
          |> filter(fn: (r) => r["_measurement"] == "sensors")
          |> aggregateWindow(every: {window}, fn: mean, createEmpty: false)
          |> pivot(rowKey:["_time"], columnKey: ["tag_name"], valueColumn: "_value")
          |> drop(columns: ["_start", "_stop", "_measurement"])
        """

        # 4. 쿼리 실행
        raw_df = tsdb.query_raw(query)

        if raw_df is None:
            logger.warning("[History] Query returned None.")
            return None

        # raw_df가 리스트로 올 경우 첫 번째 테이블 사용
        df = raw_df[0] if isinstance(raw_df, list) else raw_df

        # 데이터가 비어있는지 확인
        if not hasattr(df, "empty") or df.empty:
            logger.warning("[History] DataFrame is empty.")
            return None

        # 5. 데이터 후처리 (Pandas)

        # (A) 시간축 정리: UTC -> KST(한국시간) 변환
        # InfluxDB는 결과를 UTC로 줍니다. +9시간 보정
        if "_time" in df.columns:
            df["_time"] = pd.to_datetime(df["_time"]).dt.tz_convert("Asia/Seoul")
        else:
            # _time 컬럼이 없는 경우(매우 드뭄) 방어 코드
            logger.error("[History] '_time' column missing in result.")
            return None

        # (B) 시간 정렬 (오름차순)
        df = df.sort_values(by="_time")

        # (C) UI 전송용 시간 리스트 생성 (문자열 포맷)
        times = df["_time"].dt.strftime("%Y-%m-%d %H:%M:%S").tolist()

        # (D) 시리즈 데이터 추출
        # UI에서 기대하는 키 목록
        target_keys = ["DO", "MLSS", "Temp", "pH", "AirFlow", "Power", "Energy", "PumpHz"]
        series_data = {}

        for key in target_keys:
            if key in df.columns:
                # 데이터가 있으면 NaN을 None으로 변환하여 리스트로 저장 (JSON 직렬화 호환)
                # where(cond, other) -> cond가 거짓이면 other 반환. 즉, NaN이면 None 넣음
                series_data[key] = df[key].where(pd.notnull(df[key]), None).tolist()
            else:
                # DB에 해당 태그 데이터가 아예 없으면 None 리스트로 채움 (차트 에러 방지)
                series_data[key] = [None] * len(times)

        logger.info(f"[History] Fetch Success. Rows: {len(times)}, Step: {window}")
        return {"times": times, "series": series_data}

    except Exception as e:
        logger.error(f"[History] Critical Error: {e}")
        traceback.print_exc()
        return None
