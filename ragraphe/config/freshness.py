"""
Topic detection and knowledge freshness configuration.

Reads freshness.yaml and exposes three public functions:

  detect_topic(goal_text)            -> topic key (str)
  get_ttl(topic_key, category)       -> TTL in days (int)
  needs_realtime(topic_key, message) -> True if message triggers live search (bool)

The YAML is loaded once and cached. Edit freshness.yaml to tune topics and TTLs
without touching Python code.
"""

import yaml
from functools import lru_cache
from pathlib import Path

_CONFIG_PATH = Path(__file__).parent / "freshness.yaml"


@lru_cache(maxsize=1)
def _load() -> dict:
    """Load and cache freshness.yaml. Returns the 'topics' dict."""
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)["topics"]


def detect_topic(goal_text: str) -> str:
    """
    Match goal_text against each topic's detect_keywords.
    Keywords are comma-separated within each list item (supports mixed CJK + Latin).
    Returns the first matching topic key, or 'default' if nothing matches.
    """
    if not goal_text:
        return "default"

    text = goal_text.lower()
    topics = _load()

    for key, cfg in topics.items():
        if key == "default":
            continue
        for kw_line in cfg.get("detect_keywords", []):
            for kw in kw_line.split(","):
                kw = kw.strip()
                if kw and kw.lower() in text:
                    return key

    return "default"


def get_ttl(topic_key: str, category: str) -> int:
    """
    Return TTL in days for a (topic, content-category) pair.
    Falls back to the default topic if topic_key is unknown.
    Falls back to 30 days if category is not defined in either topic.
    """
    topics = _load()
    cfg = topics.get(topic_key) or topics.get("default", {})
    ttl = cfg.get("ttl", {}).get(category)

    if ttl is None:
        # Secondary fallback: check default topic
        ttl = topics.get("default", {}).get("ttl", {}).get(category, 30)

    return int(ttl)


def needs_realtime(topic_key: str, message_text: str) -> bool:
    """
    Return True if message_text contains a realtime trigger for the given topic.
    When True, the caller should perform a live search regardless of cached TTL.
    """
    if not message_text:
        return False

    topics = _load()
    text = message_text.lower()

    # Check topic-specific triggers
    cfg = topics.get(topic_key) or {}
    for trigger_line in cfg.get("realtime_triggers", []):
        for trigger in trigger_line.split(","):
            trigger = trigger.strip()
            if trigger and trigger.lower() in text:
                return True

    # Always check default triggers as a catch-all
    for trigger_line in topics.get("default", {}).get("realtime_triggers", []):
        for trigger in trigger_line.split(","):
            trigger = trigger.strip()
            if trigger and trigger.lower() in text:
                return True

    return False


def get_topic_name(topic_key: str) -> str:
    """Return the human-readable name for a topic key."""
    topics = _load()
    return topics.get(topic_key, {}).get("name", topic_key)
