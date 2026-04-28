"""
Category rules: display labels, time-sensitivity flags, URL-based inference.
TTL values are now driven by freshness.yaml via ragraphe.config.freshness.get_ttl().
CATEGORY_TTL is kept as a fallback for code paths that don't have topic context.
"""

# Fallback TTL (days) used when no topic context is available.
# Prefer calling freshness.get_ttl(topic, category) when goal_text is known.
CATEGORY_TTL: dict[str, int] = {
    "concept":  0,    # Conceptual knowledge — never expires
    "how_to":   90,   # Step-by-step guides
    "resource": 30,   # Resource recommendations
    "general":  30,   # Default
    "event":    7,    # Events / festivals
    "schedule": 7,    # Timetables / opening hours
    "pricing":  7,    # Prices / admission fees
    "news":     3,    # News articles
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
    "news":     "📰 新聞",
}

# Time-sensitive categories: frontend shows a staleness warning for these
TIME_SENSITIVE: set[str] = {"pricing", "event", "schedule", "news"}

# Satellite scoring: base score added on top of snippet quality score.
# Final score = _snippet_quality() + category_bonus + content_signal_bonuses.
# Threshold to appear as satellite: SATELLITE_THRESHOLD (defined in main.py, default 0.55).
# KB-imported content gets +0.30 bonus and always passes regardless of category.
SATELLITE_SCORE_BONUS: dict[str, float] = {
    "pricing":  0.25,   # Concrete prices/fees — hard to get from LLM
    "schedule": 0.25,   # Opening hours / timetables — time-sensitive
    "event":    0.20,   # Events / festivals — time-sensitive
    "news":     0.15,   # Recent news — LLM training data may be outdated
    "how_to":   0.10,   # Step-by-step guides — useful but LLM can approximate
    "resource": 0.10,   # Resource links — useful but LLM can approximate
    "concept":  -0.20,  # General knowledge — LLM already knows this
    "general":  -0.15,  # Uncategorised web content — low signal
}

SATELLITE_THRESHOLD: float = 0.55   # Minimum score to show as satellite dot

# URL keywords → auto-infer category (used for Wikipedia / DuckDuckGo results)
_URL_RULES: list[tuple[list[str], str]] = [
    (["ticket", "admission", "entry", "票", "入場", "門票"],     "pricing"),
    (["price", "cost", "fee", "費", "價格", "收費"],             "pricing"),
    (["event", "festival", "活動", "節慶", "祭"],                "event"),
    (["schedule", "timetable", "hours", "時間", "班表"],         "schedule"),
    (["how-to", "guide", "tutorial", "指南", "教學", "步驟"],    "how_to"),
    (["resource", "tool", "library", "資源", "工具"],            "resource"),
    (["news", "latest", "新聞", "最新", "報導"],                 "news"),
]


def infer_category(url: str) -> str:
    """Infer content category from a URL. Returns 'general' when no rule matches."""
    url_lower = url.lower()
    for keywords, cat in _URL_RULES:
        if any(kw in url_lower for kw in keywords):
            return cat
    return "general"


def get_ttl(category: str, topic: str = "default") -> int:
    """
    Return TTL in days for a category, using topic-aware freshness config when available.
    Falls back to CATEGORY_TTL when freshness config is unavailable.
    """
    try:
        from ragraphe.config.freshness import get_ttl as _freshness_ttl
        return _freshness_ttl(topic, category)
    except Exception:
        return CATEGORY_TTL.get(category, 30)
