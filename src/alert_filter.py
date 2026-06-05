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
    subway_config = monitoring.get("subway", {})
    subway_enabled = subway_config.get("enabled", True)
    subway_routes = set(subway_config.get("routes", []))
    rail_config = monitoring.get("rail", {})
    rail_filters = [value.lower() for value in rail_config.get("text_filters", [])]
    rail_route_ids = set(rail_config.get("route_ids", []))
    rail_stop_ids = set(rail_config.get("stop_ids", []))
    rail_route_names = [value.lower() for value in rail_config.get("route_names", [])]
    rail_station_names = [value.lower() for value in rail_config.get("station_names", [])]
    lirr_enabled = rail_config.get("lirr_enabled", True)

    relevant_alerts: list[dict[str, Any]] = []
    for alert in alerts:
        if not alert_is_active_now(alert, current_time):
            continue

        if not alert_matches_keywords(alert, keywords):
            continue

        if subway_enabled and alert_matches_subway_scope(alert, subway_routes):
            relevant_alerts.append(alert)
            continue

        if lirr_enabled and alert_matches_lirr_scope(
            alert=alert,
            route_ids=rail_route_ids,
            stop_ids=rail_stop_ids,
            route_names=rail_route_names,
            station_names=rail_station_names,
            text_filters=rail_filters,
        ):
            relevant_alerts.append(alert)

    return relevant_alerts


def alert_matches_subway_scope(alert: dict[str, Any], subway_routes: set[str]) -> bool:
    """Return True when the alert targets the monitored subway routes."""
    agencies = set(alert.get("agencies", []))
    routes = set(alert.get("routes", []))
    return bool({"MTASBWY", "MTA NYCT"} & agencies and subway_routes & routes)


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
            " ".join(alert.get("agencies", [])),
            " ".join(alert.get("routes", [])),
            " ".join(alert.get("stops", [])),
        ]
    ).lower()

    return any(keyword in haystack for keyword in keywords)


def alert_matches_lirr_scope(
    *,
    alert: dict[str, Any],
    route_ids: set[str],
    stop_ids: set[str],
    route_names: list[str],
    station_names: list[str],
    text_filters: list[str],
) -> bool:
    """Match LIRR alerts using route IDs, stop IDs, and route/station text hints."""
    agencies = set(alert.get("agencies", []))
    if "LI" not in agencies:
        return False

    routes = set(alert.get("routes", []))
    stops = set(alert.get("stops", []))
    if route_ids and route_ids.intersection(routes):
        return True
    if stop_ids and stop_ids.intersection(stops):
        return True

    haystack = " ".join(
        [
            alert.get("header", ""),
            alert.get("description", ""),
            " ".join(alert.get("agencies", [])),
            " ".join(alert.get("routes", [])),
            " ".join(alert.get("stops", [])),
        ]
    ).lower()

    combined_filters = route_names + station_names + text_filters
    if not combined_filters and not route_ids and not stop_ids:
        return True

    return any(text_filter in haystack for text_filter in combined_filters)


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
        link = get_human_alert_link(alert)
        if link:
            lines.append(f"  More info: {link}")

    lines.extend(
        [
            "",
            "This email only includes newly detected alerts to avoid repeat notifications.",
        ]
    )
    return lines


def build_alert_summary(alert: dict[str, Any]) -> str:
    """Render one alert as a compact single-line summary."""
    prefix = "[ONGOING] " if alert.get("send_reason") == "reminder" else ""
    route_text = ", ".join(alert.get("routes", [])) or alert.get("source", "").upper()
    header = (alert.get("header") or "Service alert").strip()
    description = clean_text(alert.get("description", ""))

    if description:
        return f"{prefix}[{route_text}] {header}: {description}"
    return f"{prefix}[{route_text}] {header}"


def clean_text(text: str, limit: int = 280) -> str:
    """Normalize whitespace and trim long descriptions for email readability."""
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


def get_human_alert_link(alert: dict[str, Any]) -> str:
    """Return the best human-readable link for an alert."""
    detail_url = (alert.get("detail_url") or "").strip()
    if detail_url:
        return detail_url

    # MTA's homepage Service Status area is the best general real-time fallback.
    return "https://www.mta.info/"
