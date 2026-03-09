# app/ui/charts_ui/config.py

# 다크 모드에서 선명하게 보이는 네온 계열 팔레트
# (Cyan, Blue, Teal, Green, Amber, Purple, Orange, Pink)
PALETTE = [
    "#22d3ee",  # Cyan
    "#60a5fa",  # Blue
    "#34d399",  # Green
    "#fbbf24",  # Amber
    "#a78bfa",  # Purple
    "#f472b6",  # Pink
    "#fb923c",  # Orange
    "#94a3b8",  # Gray (Fallback)
]

# 툴팁용 JS 포맷터 (소수점 2자리 처리)
TOOLTIP_FORMATTER_JS = """
    function (params) {
        if (!params.length) return '';
        var s = params[0].axisValue + '<br/>';
        for (var i = 0; i < params.length; i++) {
            var val = params[i].value;
            if (typeof val === 'number') {
                val = val.toFixed(2); // 소수점 2자리
            }
            s += params[i].marker + ' ' + params[i].seriesName + ': <b>' + val + '</b><br/>';
        }
        return s;
    }
"""
