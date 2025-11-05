# app/ui/theme.py
from __future__ import annotations

from nicegui import ui


# [ADDED] 전역 테마/CSS 적용
def apply_theme(colors: dict[str, str]) -> None:
    ui.dark_mode().disable()  # 라이트 기본
    ui.colors(primary=colors["primary"])

    ui.add_css(
        f"""
        :root {{
          --aw-bg: {colors['bg']};
          --aw-card: {colors['card']};
          --aw-border: {colors['border']};
          --aw-ink: {colors['ink']};
          --aw-ink-sub: {colors['ink_sub']};
          --aw-primary: {colors['primary']};
          --aw-accent: {colors['accent']};
        }}
        body {{ background: var(--aw-bg) !important; color: var(--aw-ink); }}
        .aw-card {{
          background: var(--aw-card);
          border: 1px solid var(--aw-border);
          border-radius: 16px;
          box-shadow: 0 2px 10px rgba(2, 18, 53, 0.04);
        }}
        .aw-panel {{
          background: var(--aw-card);
          border: 1px solid var(--aw-border);
          border-radius: 16px;
          box-shadow: 0 4px 18px rgba(2, 18, 53, 0.06);
        }}
        .aw-title {{ font-weight: 600; color: var(--aw-ink); }}
        .aw-subtle {{ color: var(--aw-ink-sub); }}
        .aw-btn {{
          background: var(--aw-primary) !important;
          color: white !important;
          border-radius: 10px !important;
          padding: 6px 14px !important;
        }}
        .aw-section-title {{
          font-size: 13px; color: var(--aw-ink-sub); margin-bottom: 6px;
        }}
        /* ECharts 기본 폰트/축 스타일 */
        .echarts text {{ fill: var(--aw-ink-sub) !important; }}
        """
    )
