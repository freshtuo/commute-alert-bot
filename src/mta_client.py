"""Fetch and normalize MTA GTFS-Realtime alert feeds."""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from typing import Any

import requests
from google.transit import gtfs_realtime_pb2


def fetch_all_alerts(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Fetch subway and LIRR alerts and return them in one normalized list."""
    feeds = config.get("feeds", {})
    timeout = int(feeds.get("timeout_seconds", 20))
    api_key_env = feeds.get("api_key_env")
    api_key = os.getenv(api_key_env) if api_key_env else None

    alerts: list[dict[str, Any]] = []
    feed_map = {
        "subway": feeds.get("subway_alerts_url"),
        "lirr": feeds.get("lirr_alerts_url"),
    }

    for source, url in feed_map.items():
        if not url:
            continue
        alerts.extend(fetch_feed(url=url, source=source, timeout=timeout, api_key=api_key))

    return alerts


def fetch_feed(
    *, url: str, source: str, timeout: int, api_key: str | None = None
) -> list[dict[str, Any]]:
    """Download one GTFS-Realtime alert feed and normalize each alert entity."""
    headers = {"User-Agent": "commute-alert-bot/1.0"}
    if api_key:
        headers["x-api-key"] = api_key

    response = requests.get(url, timeout=timeout, headers=headers)
    response.raise_for_status()

    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(response.content)

    normalized_alerts: list[dict[str, Any]] = []
    for entity in feed.entity:
        if not entity.HasField("alert"):
            continue
        normalized_alerts.append(normalize_alert(entity, source))

    return normalized_alerts


def normalize_alert(entity: Any, source: str) -> dict[str, Any]:
    """Convert one protobuf alert into a plain dictionary used by the app."""
    alert = entity.alert
    routes = sorted(
        {
            informed.route_id.strip()
            for informed in alert.informed_entity
            if getattr(informed, "route_id", "").strip()
        }
    )
    stops = sorted(
        {
            informed.stop_id.strip()
            for informed in alert.informed_entity
            if getattr(informed, "stop_id", "").strip()
        }
    )

    header_text = get_translated_text(alert.header_text)
    description_text = get_translated_text(alert.description_text)
    active_periods = [
        {
            "start": unix_to_iso(period.start) if period.HasField("start") else None,
            "end": unix_to_iso(period.end) if period.HasField("end") else None,
        }
        for period in alert.active_period
    ]

    payload = {
        "id": entity.id or "",
        "source": source,
        "routes": routes,
        "stops": stops,
        "header": header_text,
        "description": description_text,
        "active_periods": active_periods,
    }
    payload["fingerprint"] = build_fingerprint(payload)
    return payload


def get_translated_text(translated_string: Any) -> str:
    """Return the first non-empty translation from a GTFS translated string."""
    for translation in translated_string.translation:
        text = translation.text.strip()
        if text:
            return text
    return ""


def unix_to_iso(timestamp: int) -> str:
    """Convert a protobuf Unix timestamp into an ISO 8601 string."""
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def build_fingerprint(alert: dict[str, Any]) -> str:
    """Build a stable fallback key for de-duplication across cron runs."""
    raw = "|".join(
        [
            alert.get("source", ""),
            alert.get("id", ""),
            ",".join(alert.get("routes", [])),
            alert.get("header", ""),
            alert.get("description", ""),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
