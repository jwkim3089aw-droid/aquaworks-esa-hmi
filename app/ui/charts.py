# app/ui/charts.py
from __future__ import annotations

# Import from sub-modules to maintain backward compatibility
from app.ui.charts_ui.builder import build_trend_options
from app.ui.charts_ui.updater import update_multi_metric_chart
from app.ui.charts_ui.utils import short_ts
from app.ui.charts_ui.config import PALETTE as _PALETTE

# _PALETTE is re-exported for compatibility if any external code uses it directly
__all__ = ["build_trend_options", "update_multi_metric_chart", "short_ts", "_PALETTE"]
