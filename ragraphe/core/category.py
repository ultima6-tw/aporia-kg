"""
Category rules: category → TTL, display label, freshness warning.
All categorization behavior is driven by this module; no category logic is hardcoded elsewhere.
"""

# category → cache duration in days (0 = never expires)
CATEGORY_TTL: dict[str, int] = {
    "concept":  0,    # conceptual knowledge, never expires
    "how_to":   90,   # step-by-step instructions, 90 days
    "resource": 30,   # resource recommendations, 30 days
    "general":  30,   # default, 30 days
    "event":    14,   # events / festivals, 14 days
    "schedule": 7,    # timetables / opening hours, 7 days
    "pricing":  7,    # prices / admission fees, 7 days
}

# category → frontend display label
CATEGORY_LABEL: dict[str, str] = {
    "concept":  "📖 概念",
    "how_to":   "🛠 操作",
    "resource": "🔗 資源",
    "general":  "📄 一般",
    "event":    "📅 活動",
    "schedule": "🕐 時程",
    "pricing":  "💰 費用",
}

# Time-sensitive categories: the frontend shows a staleness warning for these
TIME_SENSITIVE: set[str] = {"pricing", "event", "schedule"}

# URL keywords → auto-infer category (used for Wikipedia / DuckDuckGo results)
_URL_RULES: list[tuple[list[str], str]] = [
    (["ticket", "admission", "entry", "票", "入場", "門票"], "pricing"),
    (["price", "cost", "fee", "費", "價格", "收費"],        "pricing"),
    (["event", "festival", "活動", "節慶", "祭"],           "event"),
    (["schedule", "timetable", "hours", "時間", "班表"],    "schedule"),
    (["how-to", "guide", "tutorial", "指南", "教學", "步驟"], "how_to"),
    (["resource", "tool", "library", "資源", "工具"],       "resource"),
]


def infer_category(url: str) -> str:
    """Infer category from a URL; returns 'general' when no rule matches."""
    url_lower = url.lower()
    for keywords, cat in _URL_RULES:
        if any(kw in url_lower for kw in keywords):
            return cat
    return "general"
