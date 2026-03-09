# app/ui/charts_ui/builder.py
from typing import Any, Dict, List, Tuple
from collections.abc import Sequence
from app.ui.charts_ui.config import PALETTE, TOOLTIP_FORMATTER_JS


def build_trend_options(
    metrics: Sequence[Dict[str, Any]],
    axis_positions: Sequence[Tuple[str, int]],
) -> Dict[str, Any]:
    """
    ECharts 라인 차트 설정을 생성합니다.
    - 다중 Y축 지원
    - 데이터-축 색상 일치 (가독성 향상)
    - 대용량 데이터 최적화 (LTTB)
    """
    y_axes: List[Dict[str, Any]] = []
    series: List[Dict[str, Any]] = []

    for i, meta in enumerate(metrics):
        # 팔레트 색상 순환 할당
        color = PALETTE[i % len(PALETTE)]
        pos, offset = axis_positions[i]

        # 1. Y축 설정
        axis_conf: Dict[str, Any] = {
            "type": "value",
            "name": meta["label"],
            "position": pos,
            "offset": offset,
            "axisLine": {
                "show": True,
                "lineStyle": {"color": color},  # [개선] 축 색상을 데이터 색상과 통일
            },
            "axisLabel": {
                "color": color,  # [개선] 라벨 색상도 통일
                "formatter": "{value}",
            },
            "nameTextStyle": {
                "color": color,
                "fontWeight": "bold",
            },
            # 첫 번째 축만 격자선 표시 (너무 많으면 지저분함)
            "splitLine": {
                "show": (i == 0),
                "lineStyle": {"color": "#1f2937", "opacity": 0.5},
            },
            "scale": True,  # 데이터 범위에 맞춰 자동 스케일링
        }

        # [도메인 로직] pH는 범위 고정
        if meta["key"] == "pH":
            axis_conf["min"] = 6.0
            axis_conf["max"] = 8.0
            axis_conf["scale"] = False

        y_axes.append(axis_conf)

        # 2. 시리즈(데이터 선) 설정
        series.append(
            {
                "name": meta["label"],
                "type": "line",
                "smooth": True,  # 부드러운 곡선
                "showSymbol": False,  # 데이터 포인트 점 숨김 (성능 향상)
                "yAxisIndex": meta["axis"],
                "data": [],
                "lineStyle": {"width": 2, "color": color},
                "itemStyle": {"color": color},
                # [핵심 최적화] 대용량 데이터 렌더링 성능 확보
                "sampling": "lttb",
                "large": True,
                "largeThreshold": 2000,
            }
        )

    return {
        "backgroundColor": "transparent",
        # [개선] 색상 팔레트 전역 적용
        "color": PALETTE,
        # [개선] 툴팁 가독성 향상
        "tooltip": {
            "trigger": "axis",
            "backgroundColor": "rgba(15, 23, 42, 0.9)",  # 다크 배경
            "borderColor": "#334155",
            "textStyle": {"color": "#f1f5f9"},
            "axisPointer": {"type": "cross", "label": {"backgroundColor": "#334155"}},
            # 소수점 2자리로 끊어서 보여주는 포맷터 (JS)
            "formatter": TOOLTIP_FORMATTER_JS,
        },
        "legend": {
            "show": True,
            "type": "scroll",  # 태그 많으면 스크롤
            "top": 5,
            "textStyle": {"color": "#cbd5e1"},
            "data": [m["label"] for m in metrics],
        },
        # [개선] 줌 기능 추가 (마우스 휠로 확대/축소)
        "dataZoom": [
            {"type": "inside", "xAxisIndex": 0, "filterMode": "filter"},
            {
                "type": "slider",
                "xAxisIndex": 0,
                "filterMode": "filter",
                "height": 20,
                "bottom": 10,
                "borderColor": "transparent",
                "backgroundColor": "#1e293b",
                "fillerColor": "rgba(96, 165, 250, 0.2)",
            },
        ],
        "grid": {
            "left": 60,
            "right": 60,
            "bottom": 60,  # 슬라이더 공간 확보
            "top": 60,
            "containLabel": True,  # 라벨 잘림 방지
        },
        "xAxis": {
            "type": "category",
            "data": [],
            "boundaryGap": False,  # 선이 축 끝까지 꽉 차게
            "axisLine": {"lineStyle": {"color": "#475569"}},
            "axisLabel": {"color": "#94a3b8"},
        },
        "yAxis": y_axes,
        "series": series,
        # 데이터 없을 때 표시
        "title": {
            "show": False,
            "text": "No Data",
            "left": "center",
            "top": "center",
            "textStyle": {"color": "#64748b", "fontSize": 14},
        },
    }
