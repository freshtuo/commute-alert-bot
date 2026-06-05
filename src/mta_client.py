"""Fetch and normalize MTA GTFS-Realtime alert feeds."""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from typing import Any

import requests
from google.protobuf.message import DecodeError
from google.transit import gtfs_realtime_pb2


class FeedParseError(ValueError):
    """Raised when an MTA feed response cannot be parsed as GTFS-Realtime."""

    def __init__(
        self,
        message: str,
        *,
        url: str,
        status_code: int,
        content_type: str,
        response_bytes: bytes,
        preview_text: str,
    ) -> None:
        super().__init__(message)
        self.url = url
        self.status_code = status_code
        self.content_type = content_type
        self.response_bytes = response_bytes
        self.preview_text = preview_text


def fetch_all_alerts(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Fetch MTA service alerts and return them in one normalized list."""
    feeds = config.get("feeds", {})
    timeout = int(feeds.get("timeout_seconds", 20))
    api_key_env = feeds.get("api_key_env")
    api_key = os.getenv(api_key_env) if api_key_env else None

    service_alerts_url = feeds.get("service_alerts_url")
    if not service_alerts_url:
        raise ValueError("Missing feeds.service_alerts_url in config/config.yaml")

    return fetch_feed(
        url=service_alerts_url,
        source="service_alerts",
        timeout=timeout,
        api_key=api_key,
    )


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
    try:
        feed.ParseFromString(response.content)
    except DecodeError as exc:
        preview = response.text[:200].replace("\n", " ").strip()
        raise FeedParseError(
            "MTA feed did not return valid GTFS-Realtime protobuf data. "
            f"URL={url} Preview={preview!r}",
            url=url,
            status_code=response.status_code,
            content_type=response.headers.get("Content-Type", ""),
            response_bytes=response.content,
            preview_text=preview,
        ) from exc

    normalized_alerts: list[dict[str, Any]] = []
    for entity in feed.entity:
        if not entity.HasField("alert"):
            continue
        normalized_alerts.append(normalize_alert(entity, source))

    return normalized_alerts


def normalize_alert(entity: Any, source: str) -> dict[str, Any]:
    """Convert one protobuf alert into a plain dictionary used by the app."""
    alert = entity.alert
    agencies = sorted(
        {
            informed.agency_id.strip()
            for informed in alert.informed_entity
            if getattr(informed, "agency_id", "").strip()
        }
    )
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
    detail_url = get_translated_text(alert.url)
    active_periods = [
        {
            "start": unix_to_iso(period.start) if period.HasField("start") else None,
            "end": unix_to_iso(period.end) if period.HasField("end") else None,
        }
        for period in alert.active_period
    ]
    active_period_signature = build_active_period_signature(active_periods)

    payload = {
        "id": entity.id or "",
        "source": source,
        "agencies": agencies,
        "routes": routes,
        "stops": stops,
        "header": header_text,
        "description": description_text,
        "detail_url": detail_url,
        "active_periods": active_periods,
        "active_period_signature": active_period_signature,
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
    """Build a stable incident key for de-duplication across cron runs."""
    raw = "|".join(
        [
            alert.get("source", ""),
            alert.get("id", ""),
            ",".join(alert.get("agencies", [])),
            ",".join(alert.get("routes", [])),
            ",".join(alert.get("stops", [])),
            alert.get("active_period_signature", ""),
            alert.get("header", ""),
            alert.get("description", ""),
            alert.get("detail_url", ""),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_active_period_signature(active_periods: list[dict[str, str | None]]) -> str:
    """Collapse active-period start and end times into a stable fingerprint field."""
    parts: list[str] = []
    for period in active_periods:
        start = period.get("start") or ""
        end = period.get("end") or ""
        parts.append(f"{start}>{end}")
    return "|".join(parts)
