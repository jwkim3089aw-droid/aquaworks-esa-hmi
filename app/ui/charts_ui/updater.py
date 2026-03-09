# app/ui/charts_ui/updater.py
from typing import Any, Dict, List
from collections.abc import Sequence


async def update_multi_metric_chart(
    chart: Any,
    metrics: Sequence[Dict[str, Any]],
    xs: List[str],
    rows: List[Dict[str, Any]],
) -> None:
    """차트 데이터를 비동기로 업데이트합니다."""

    # 데이터가 없으면 타이틀 표시
    if not xs:
        chart.options["title"]["show"] = True
        chart.options["xAxis"]["data"] = []
        chart.options["series"] = []
        chart.update()
        return

    chart.options["title"]["show"] = False

    # x축 데이터 (시간) 업데이트
    # 짧은 시간 형식으로 변환해서 넣기 (선택 사항)
    # chart.options["xAxis"]["data"] = [short_ts(x) for x in xs]
    chart.options["xAxis"]["data"] = xs

    # 시리즈 데이터 업데이트
    for i, meta in enumerate(metrics):
        key = meta["key"]
        # 안전한 데이터 추출 (키 없으면 None)
        new_data = [row.get(key) for row in rows]

        # 기존 옵션 유지하며 데이터만 교체
        if i < len(chart.options["series"]):
            chart.options["series"][i]["data"] = new_data

    chart.update()
