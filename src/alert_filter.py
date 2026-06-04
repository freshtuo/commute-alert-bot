"""Filtering rules for commute-relevant alerts."""

from __future__ import annotations

from datetime import datetime
from typing import Any


def filter_relevant_alerts(
    alerts: list[dict[str, Any]], config: dict[str, Any], current_time: datetime
) -> list[dict[str, Any]]:
    """Keep only current alerts that match the monitored routes and keywords."""
    monitoring = config.get("monitoring", {})
    keywords = [keyword.lower() for keyword in config.get("keywords", [])]
    subway_routes = set(monitoring.get("subway_routes", []))
    rail_filters = [
        value.lower() for value in monitoring.get("rail", {}).get("text_filters", [])
    ]
    lirr_enabled = monitoring.get("rail", {}).get("lirr_enabled", True)

    relevant_alerts: list[dict[str, Any]] = []
    for alert in alerts:
        if not alert_is_active_now(alert, current_time):
            continue

        if not alert_matches_keywords(alert, keywords):
            continue

        if alert["source"] == "subway" and subway_routes.intersection(alert.get("routes", [])):
            relevant_alerts.append(alert)
            continue

        if alert["source"] == "lirr" and lirr_enabled and alert_matches_lirr_scope(alert, rail_filters):
            relevant_alerts.append(alert)

    return relevant_alerts


def alert_is_active_now(alert: dict[str, Any], current_time: datetime) -> bool:
    """Return True when the alert is active at the current time."""
    active_periods = alert.get("active_periods", [])
    if not active_periods:
        return True

    for period in active_periods:
        start_text = period.get("start")
        end_text = period.get("end")
        start = datetime.fromisoformat(start_text) if start_text else None
        end = datetime.fromisoformat(end_text) if end_text else None

        if start and current_time < start:
            continue
        if end and current_time > end:
            continue
        return True

    return False


def alert_matches_keywords(alert: dict[str, Any], keywords: list[str]) -> bool:
    """Check whether the alert text includes one of the disruption keywords."""
    haystack = " ".join(
        [
            alert.get("header", ""),
            alert.get("description", ""),
            " ".join(alert.get("routes", [])),
            " ".join(alert.get("stops", [])),
        ]
    ).lower()

    return any(keyword in haystack for keyword in keywords)


def alert_matches_lirr_scope(alert: dict[str, Any], text_filters: list[str]) -> bool:
    """Keep LIRR alerts broad by default, but allow config text filters to narrow them."""
    if not text_filters:
        return True

    haystack = " ".join(
        [
            alert.get("header", ""),
            alert.get("description", ""),
            " ".join(alert.get("routes", [])),
            " ".join(alert.get("stops", [])),
        ]
    ).lower()

    return any(text_filter in haystack for text_filter in text_filters)


def build_email_lines(
    alerts: list[dict[str, Any]], current_time: datetime, config: dict[str, Any]
) -> list[str]:
    """Create a short plain-text email with one bullet per new alert."""
    timezone_name = config.get("timezone", "America/New_York")
    lines = [
        "Commute Alert Bot found new relevant MTA service alerts.",
        "",
        f"Checked at: {current_time.strftime('%Y-%m-%d %I:%M %p')} ({timezone_name})",
        "",
        "Alerts:",
    ]

    for alert in alerts:
        summary = build_alert_summary(alert)
        lines.append(f"- {summary}")

    lines.extend(
        [
            "",
            "This email only includes newly detected alerts to avoid repeat notifications.",
        ]
    )
    return lines


def build_alert_summary(alert: dict[str, Any]) -> str:
    """Render one alert as a compact single-line summary."""
    route_text = ", ".join(alert.get("routes", [])) or alert.get("source", "").upper()
    header = (alert.get("header") or "Service alert").strip()
    description = clean_text(alert.get("description", ""))

    if description:
        return f"[{route_text}] {header}: {description}"
    return f"[{route_text}] {header}"


def clean_text(text: str, limit: int = 280) -> str:
    """Normalize whitespace and trim long descriptions for email readability."""
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."
