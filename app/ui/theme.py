# app/ui/theme.py
from __future__ import annotations

from nicegui import ui


def apply_theme(colors: dict[str, str]) -> None:
    ui.dark_mode().enable()  # [CHANGED] 다크 기본
    ui.colors(primary=colors["primary"])

    ui.add_css(
        f"""
        :root {{
          --aw-bg: {colors.get('bg')};
          --aw-card: {colors.get('card')};
          --aw-panel: {colors.get('panel', colors.get('card'))};
          --aw-border: {colors.get('border')};
          --aw-ink: {colors.get('ink')};
          --aw-ink-sub: {colors.get('ink_sub')};
          --aw-primary: {colors.get('primary')};
          --aw-accent: {colors.get('accent')};
        }}
        body {{
          background: var(--aw-bg) !important;
          color: var(--aw-ink);
        }}
        .aw-card {{
          background: var(--aw-card);
          border: 1px solid var(--aw-border);
          border-radius: 16px;
          box-shadow: 0 8px 28px rgba(0,0,0,0.25);
        }}
        .aw-panel {{
          background: var(--aw-panel);
          border: 1px solid var(--aw-border);
          border-radius: 16px;
          box-shadow: 0 12px 40px rgba(0,0,0,0.35);
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
        /* ECharts 다크 축/레이블 대비 */
        .echarts text {{ fill: var(--aw-ink-sub) !important; }}
        """
    )
