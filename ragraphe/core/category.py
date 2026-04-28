"""
Category rules: display labels, time-sensitivity flags, URL-based and text-based inference.
TTL values are now driven by freshness.yaml via ragraphe.config.freshness.get_ttl().
CATEGORY_TTL is kept as a fallback for code paths that don't have topic context.
"""
import re

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
# Keys match the *display* categories returned by _infer_display_category() in main.py:
# travel, learning, news, product, concept, general
# DB-only categories (pricing, schedule, event, how_to, resource) map to these via _infer_display_category.
SATELLITE_SCORE_BONUS: dict[str, float] = {
    "travel":   0.20,   # Destination-specific info — highly contextual, LLM may be outdated
    "product":  0.20,   # Specific product/tool info — concrete, hard to guess
    "news":     0.15,   # Recent events — LLM training data may be outdated
    "learning": 0.10,   # Tutorials / how-to — useful but LLM can approximate
    "concept":  -0.20,  # General knowledge — LLM already knows this
    "general":  -0.15,  # Uncategorised web content — low signal
}

SATELLITE_THRESHOLD: float = 0.55   # Minimum score to show as satellite dot

# Exponential time-decay rate (k) per display category.
# Effective bonus = SATELLITE_SCORE_BONUS[cat] * exp(-k * age_days)
# Higher k = faster decay. Only applies when crawled_at is present; missing = no decay.
# Half-life = ln(2) / k ≈ 0.693 / k days.
SATELLITE_DECAY_RATE: dict[str, float] = {
    "news":   0.50,   # half-life ≈ 1.4 days  — news goes stale within days
    "travel": 0.03,   # half-life ≈ 23 days   — travel info changes over weeks
    "product": 0.01,  # half-life ≈ 69 days   — product info changes slowly
}

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


# Text-based keyword patterns for display category inference
_KW_TRAVEL  = re.compile(r"(旅遊|景點|交通|住宿|餐廳|美食|景色|寺廟|神社|旅行|觀光|"
                          r"參觀|門票|入場|行程|旅館|溫泉|海灘|博物館|古蹟|tour|sightseeing)", re.IGNORECASE)
_KW_LEARN   = re.compile(r"(學習|教學|課程|概念|原理|定義|算法|演算|入門|教程|tutorial|guide|learn)", re.IGNORECASE)
_KW_NEWS    = re.compile(r"(最新|報導|新聞|消息|公告|發佈|更新|2024|2025|2026)", re.IGNORECASE)
_KW_PRODUCT = re.compile(r"(購買|推薦|評測|比較|價格|促銷|限時|優惠|product|review)", re.IGNORECASE)
_KW_CONCEPT = re.compile(r"(定義|是指|概念|理論|解釋|包含|分為|指的是)", re.IGNORECASE)


def infer_display_categories(text: str, db_cat: str = "general") -> list[str]:
    """Return ALL matching display categories for a chunk (score >= 1 keyword hits).

    Display categories: travel | learning | news | product | concept | general
    These map directly to SATELLITE_SCORE_BONUS keys.
    Returned list is sorted by score descending; always contains at least one element.
    """
    forced: list[str] = []
    if db_cat == "how_to":
        forced.append("learning")
    if db_cat == "event":
        forced.append("news")

    scores = {
        "travel":   len(_KW_TRAVEL.findall(text)),
        "learning": len(_KW_LEARN.findall(text)),
        "news":     len(_KW_NEWS.findall(text)),
        "product":  len(_KW_PRODUCT.findall(text)),
        "concept":  len(_KW_CONCEPT.findall(text)),
    }
    matched = sorted(
        [cat for cat, s in scores.items() if s >= 1],
        key=lambda c: scores[c], reverse=True
    )
    # Merge: forced categories first, then keyword-matched, deduplicated
    result: list[str] = []
    seen: set[str] = set()
    for c in forced + matched:
        if c not in seen:
            result.append(c)
            seen.add(c)
    if not result:
        result.append("concept" if db_cat == "concept" else "general")
    return result


def infer_display_category(text: str, db_cat: str = "general") -> str:
    """Single-category convenience wrapper — returns the top-scoring category."""
    return infer_display_categories(text, db_cat)[0]


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
