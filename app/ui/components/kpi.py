# app/ui/components/kpi.py
from typing import List, Dict, Any, Set, Tuple, Callable
from nicegui import ui
from app.ui.metrics import create_metric_card
from app.ui.common import title_of, metric_name_and_unit

METRIC_WRAPPER_BASE_CLASS = "metric-card-wrapper w-full rounded-xl transition-all duration-150"
ACTIVE_WRAPPER_CLASSES = "metric-card-wrapper--active bg-slate-800/80"


def create_kpi_section(
    metrics: List[Dict[str, Any]], active_keys: Set[str], on_selection_change: Callable[[], Any]
) -> Tuple[Dict[str, Any], Dict[str, Tuple[Any, Any, Any]]]:
    """
    좌측 KPI 카드 영역 생성
    Returns: (metric_wrappers, card_map)
    """
    metric_wrappers: Dict[str, Any] = {}
    card_map: Dict[str, Tuple[Any, Any, Any]] = {}

    with ui.element("div").classes("flex flex-col gap-2 w-[215px] h-[852px] justify-between"):
        for m in metrics:
            key = str(m.get("key", title_of(m)))
            wrapper = ui.element("div").classes(METRIC_WRAPPER_BASE_CLASS)
            metric_wrappers[key] = wrapper

            with wrapper:
                c, v, u, _ = create_metric_card(
                    title_of(m), str(m.get("unit", "")), compact=True, width_px=205
                )
            card_map[key] = (c, v, u)

            # 핸들러 클로저 생성
            def _make_handler(metric_key: str, w=wrapper):
                async def _on_click(_: Any) -> None:
                    if metric_key in active_keys:
                        active_keys.remove(metric_key)
                    else:
                        active_keys.add(metric_key)

                    # 활성 상태 클래스 토글
                    for k, mw in metric_wrappers.items():
                        if k in active_keys:
                            mw.classes(add=ACTIVE_WRAPPER_CLASSES)
                        else:
                            mw.classes(remove=ACTIVE_WRAPPER_CLASSES)

                    # 외부 콜백(차트 업데이트 등) 호출
                    result = on_selection_change()
                    if result and hasattr(result, "__await__"):
                        await result

                w.on("click", _on_click)

            _make_handler(key)

            # 초기 상태 반영
            if key in active_keys:
                wrapper.classes(add=ACTIVE_WRAPPER_CLASSES)

    return metric_wrappers, card_map
