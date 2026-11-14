"""Versioned authorized Metricool connector export contract; no embedded credentials."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
import math
import re
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

FIELDS = ("TKPO02", "TKPO03", "TKPO05", "TKPO06", "TKPO07", "TKPO08", "TKPO09",
          "TKPO10", "TKPO11", "TKPO13", "TKPO14", "TKPO15", "TKPO22")
METRICS = {"TKPO06": ("duration", "seconds"), "TKPO07": ("views", "count"),
           "TKPO08": ("likes", "count"), "TKPO09": ("comments", "count"),
           "TKPO10": ("shares", "count"), "TKPO11": ("reach", "count"),
           "TKPO13": ("completion_rate", "percent"), "TKPO14": ("total_watch_time", "seconds"),
           "TKPO15": ("average_watch_time", "seconds")}


def aware_time(value):
    try:
        result = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Timestamp must be ISO 8601") from exc
    if result.tzinfo is None:
        raise ValueError("Timestamp must include timezone")
    return result.astimezone(timezone.utc)


def number(value, unit):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("Boolean is not a metric")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Metric must be numeric or null") from exc
    if not math.isfinite(result) or result < 0:
        raise ValueError("Metric must be finite and nonnegative")
    if unit == "count" and not result.is_integer():
        raise ValueError("Count must be an integer")
    if unit == "percent" and result > 100:
        raise ValueError("Percent must be between 0 and 100")
    return result


@dataclass(frozen=True)
class Post:
    post_id: str
    published_at: str
    caption: str
    content_type: str
    metrics: dict


def parse_export(data):
    """Require field order and provenance instead of guessing positional schemas."""
    allowed = {"schema", "source", "account", "brand_id", "timezone", "observed_at", "fields", "rows", "observation_note"}
    if not isinstance(data, dict) or set(data) - allowed:
        raise ValueError("Unexpected export fields; never import credentials")
    if data.get("schema") != "s_ml.metricool-export.v1":
        raise ValueError("Unsupported export schema")
    if data.get("source") != "metricool_authorized_connector":
        raise ValueError("Expected authorized connector provenance")
    account, brand = data.get("account"), data.get("brand_id")
    if not isinstance(account, str) or not re.fullmatch(r"[\w.]{1,64}", account, re.ASCII):
        raise ValueError("Invalid account identifier")
    if not isinstance(brand, str) or not brand.isdecimal():
        raise ValueError("Invalid brand identifier")
    observed = aware_time(data.get("observed_at"))
    fields = data.get("fields")
    if not isinstance(fields, list) or len(fields) != len(set(fields)) or set(fields) != set(FIELDS):
        raise ValueError("Export must contain all versioned contract fields exactly once")
    rows = data.get("rows")
    if not isinstance(rows, list) or len(rows) > 10000:
        raise ValueError("Expected at most 10000 rows per batch")
    tz = ZoneInfo(data["timezone"])
    posts, seen = [], set()
    for row in rows:
        if not isinstance(row, list) or len(row) != len(fields):
            raise ValueError("Row width differs from declared fields")
        item = dict(zip(fields, row))
        url = urlsplit(item["TKPO03"])
        match = re.fullmatch(r"/@([^/]+)/(?:video|photo)/(\d+)", url.path)
        if url.scheme != "https" or url.hostname not in ("www.tiktok.com", "tiktok.com") or not match:
            raise ValueError("Expected official TikTok post URL with platform ID")
        if match[1] != account:
            raise ValueError("Post belongs to a different account")
        if match[2] in seen:
            raise ValueError("Duplicate platform ID within batch")
        seen.add(match[2])
        published = datetime.strptime(item["TKPO02"], "%Y%m%d%H%M%S").replace(tzinfo=tz)
        if published > observed:
            raise ValueError("Publication cannot occur after observation")
        caption, kind = item["TKPO05"], item["TKPO22"]
        if not isinstance(caption, str) or len(caption) > 20000 or kind not in ("VIDEO", "PHOTO"):
            raise ValueError("Invalid caption or content type")
        metrics = {name: {"value": number(item[field], unit), "unit": unit,
                          "availability": "unavailable" if item[field] in (None, "") else "observed"}
                   for field, (name, unit) in METRICS.items()}
        # Metricool emits duration=0 for PHOTO, not a measured video duration.
        if kind == "PHOTO":
            metrics["duration"] = {"value": None, "unit": "seconds", "availability": "not_applicable"}
        posts.append(Post(match[2], published.astimezone(timezone.utc).isoformat(), caption, kind, metrics))
    return posts
