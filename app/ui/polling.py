# app/ui/polling.py
from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import httpx
from nicegui import ui

from .charts import short_ts, update_multi_metric_chart


async def poll_loop(
    api_base: str,
    metrics: list[dict[str, Any]],
    label_map: dict[str, Any],
    trend_embed: Any,
    trend_full: Any,
    trend_single: Any,
    get_single_key: Callable[[], str | None],
    sparks: dict[str, Any],
    inp_hours: Any,
    sel_bucket: Any,
) -> None:
    async with httpx.AsyncClient(timeout=5.0) as client:
        while True:
            # 1) 최신 KPI
            try:
                r = await client.get(f"{api_base}/api/v1/last")
                if r.status_code == 200 and r.json():
                    d = r.json()
                    label_map["DO"].text = f"{d.get('DO', 0):.2f}"
                    label_map["MLSS"].text = f"{d.get('MLSS', 0):.0f}"
                    label_map["temp"].text = f"{d.get('temp', 0):.2f}"
                    label_map["pH"].text = f"{d.get('pH', 0):.2f}"
                    label_map["air_flow"].text = f"{d.get('air_flow', 0):.1f}"
                    label_map["power"].text = f"{d.get('power', 0):.2f}"
            except Exception as e:
                ui.notify(f"KPI fetch error: {e}", color="negative")

            # 2) 트렌드
            try:
                hrs = float(inp_hours.value or 0.5)
                bkt = int(sel_bucket.value or 5)
                fields = ",".join([m["key"] for m in metrics])
                url = f"{api_base}/api/v1/trend?fields={fields}&hours={hrs}&bucket_sec={bkt}"
                r2 = await client.get(url)
                if r2.status_code == 200:
                    rows: list[dict[str, Any]] = r2.json() or []
                    xs = [short_ts(row.get("ts")) for row in rows]

                    no_data = len(rows) == 0
                    trend_embed.options["title"]["show"] = no_data
                    trend_full.options["title"]["show"] = no_data

                    await update_multi_metric_chart(trend_embed, metrics, xs, rows)
                    await update_multi_metric_chart(trend_full, metrics, xs, rows)

                    single_key = get_single_key()
                    if single_key:
                        meta = next((m for m in metrics if m["key"] == single_key), None)
                        if meta:
                            trend_single.options["xAxis"]["data"] = xs
                            trend_single.options["series"][0]["data"] = [
                                row.get(meta["key"]) for row in rows
                            ]
                            await trend_single.update()

                    for key, spark in sparks.items():
                        spark.options["xAxis"]["data"] = xs
                        spark.options["series"][0]["data"] = [row.get(key) for row in rows]
                        await spark.update()

            except Exception as e:
                ui.notify(f"Trend fetch error: {e}", color="negative")

            await asyncio.sleep(1.0)


def start_polling(  # [CHANGED] *args/**kwargs 제거, 명시적 시그니처로 Pylance 경고 제거
    api_base: str,
    metrics: list[dict[str, Any]],
    label_map: dict[str, Any],
    trend_embed: Any,
    trend_full: Any,
    trend_single: Any,
    get_single_key: Callable[[], str | None],
    sparks: dict[str, Any],
    inp_hours: Any,
    sel_bucket: Any,
) -> None:
    ui.timer(
        0.1,
        lambda: asyncio.create_task(
            poll_loop(
                api_base=api_base,
                metrics=metrics,
                label_map=label_map,
                trend_embed=trend_embed,
                trend_full=trend_full,
                trend_single=trend_single,
                get_single_key=get_single_key,
                sparks=sparks,
                inp_hours=inp_hours,
                sel_bucket=sel_bucket,
            )
        ),
        once=True,
    )
