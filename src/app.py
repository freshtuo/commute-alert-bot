"""Cron-friendly entry point for the commute alert bot."""

from __future__ import annotations

import json
import logging
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

from src.alert_filter import build_email_lines, filter_relevant_alerts
from src.email_sender import send_email
from src.mta_client import FeedParseError, fetch_all_alerts


def load_config(config_path: Path) -> dict[str, Any]:
    """Load the shared config and merge an optional local override file."""
    with config_path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}

    local_config_path = config_path.with_name("config.local.yaml")
    if local_config_path.exists():
        with local_config_path.open("r", encoding="utf-8") as handle:
            local_config = yaml.safe_load(handle) or {}
        config = deep_merge_dicts(config, local_config)

    return config


def deep_merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge two dictionaries, preferring the override values."""
    merged = dict(base)
    for key, override_value in override.items():
        base_value = merged.get(key)
        if isinstance(base_value, dict) and isinstance(override_value, dict):
            merged[key] = deep_merge_dicts(base_value, override_value)
        else:
            merged[key] = override_value
    return merged


def setup_logging(config: dict[str, Any], project_root: Path) -> logging.Logger:
    """Create the log directory and return a file-backed logger."""
    logging_config = config.get("logging", {})
    log_dir = project_root / logging_config.get("directory", "logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    log_path = log_dir / logging_config.get("file", "commute-alert-bot.log")
    logger = logging.getLogger("commute_alert_bot")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if not logger.handlers:
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        )
        logger.addHandler(file_handler)

        if logging_config.get("console_enabled", True):
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
            logger.addHandler(console_handler)

    return logger


def get_now_in_timezone(config: dict[str, Any]) -> datetime:
    """Return the current time in the configured timezone."""
    timezone_name = config.get("timezone", "America/New_York")
    return datetime.now(ZoneInfo(timezone_name))


def parse_clock(value: str) -> time:
    """Parse a HH:MM string from config into a time object."""
    return time.fromisoformat(value)


def is_within_commute_window(config: dict[str, Any], current_time: datetime) -> bool:
    """Return True when the current time falls inside any configured window."""
    windows = config.get("commute_windows", {})
    if windows.get("weekdays_only", True) and current_time.weekday() >= 5:
        return False

    for name in ("morning", "evening"):
        window = windows.get(name)
        if not window:
            continue

        start = parse_clock(window["start"])
        end = parse_clock(window["end"])
        if start <= current_time.time() <= end:
            return True

    return False


def load_cache(cache_path: Path) -> dict[str, dict[str, str]]:
    """Load previously-sent alert fingerprints from disk."""
    if not cache_path.exists():
        return {}

    with cache_path.open("r", encoding="utf-8") as handle:
        try:
            data = json.load(handle)
        except json.JSONDecodeError:
            return {}

    alerts = data.get("alerts", {})
    if not isinstance(alerts, dict):
        return {}

    normalized: dict[str, dict[str, str]] = {}
    for fingerprint, value in alerts.items():
        if isinstance(value, str):
            normalized[fingerprint] = {
                "sent_at": value,
                "first_sent_at": value,
            }
        elif isinstance(value, dict):
            sent_at = value.get("sent_at")
            if isinstance(sent_at, str):
                normalized[fingerprint] = {
                    key: str(raw_value)
                    for key, raw_value in value.items()
                    if isinstance(raw_value, (str, int, float))
                }
                normalized[fingerprint].setdefault("first_sent_at", sent_at)
    return normalized


def save_cache(cache_path: Path, fingerprints: dict[str, dict[str, str]]) -> None:
    """Persist sent alert fingerprints so repeat cron runs stay quiet."""
    payload = {"alerts": fingerprints}
    with cache_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)


def save_snapshot(
    *,
    config: dict[str, Any],
    project_root: Path,
    current_time: datetime,
    snapshot_name: str,
    payload: dict[str, Any],
) -> None:
    """Write one JSON snapshot for debugging and prune older snapshot files."""
    snapshot_config = config.get("snapshots", {})
    if not snapshot_config.get("enabled", True):
        return

    snapshot_dir = project_root / snapshot_config.get("directory", "data/snapshots")
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    timestamp = current_time.strftime("%Y%m%d-%H%M%S")
    snapshot_path = snapshot_dir / f"{timestamp}-{snapshot_name}.json"
    with snapshot_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)

    keep_last = int(snapshot_config.get("keep_last", 10))
    prune_snapshot_files(snapshot_dir, keep_last)


def prune_snapshot_files(snapshot_dir: Path, keep_last: int) -> None:
    """Keep only the newest N snapshot files."""
    snapshot_files = sorted(snapshot_dir.glob("*.json"))
    excess_count = len(snapshot_files) - keep_last
    if excess_count <= 0:
        return

    for snapshot_file in snapshot_files[:excess_count]:
        snapshot_file.unlink(missing_ok=True)


def save_raw_error_snapshot(
    *,
    config: dict[str, Any],
    project_root: Path,
    current_time: datetime,
    snapshot_name: str,
    response_bytes: bytes,
) -> str | None:
    """Optionally save raw fetch-error bytes and return the file path."""
    snapshot_config = config.get("snapshots", {})
    if not snapshot_config.get("enabled", True):
        return None
    if not snapshot_config.get("raw_on_error", False):
        return None

    snapshot_dir = project_root / snapshot_config.get("directory", "data/snapshots")
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    timestamp = current_time.strftime("%Y%m%d-%H%M%S")
    raw_path = snapshot_dir / f"{timestamp}-{snapshot_name}.bin"
    raw_max_bytes = int(snapshot_config.get("raw_max_bytes", 250000))
    with raw_path.open("wb") as handle:
        handle.write(response_bytes[:raw_max_bytes])

    return str(raw_path.relative_to(project_root))


def prune_cache(
    fingerprints: dict[str, dict[str, str]], current_time: datetime, retention_hours: int
) -> dict[str, dict[str, str]]:
    """Drop stale fingerprints so the cache stays small over time."""
    cutoff = current_time - timedelta(hours=retention_hours)
    pruned: dict[str, dict[str, str]] = {}

    for fingerprint, metadata in fingerprints.items():
        seen_at = metadata.get("sent_at")
        if not seen_at:
            continue
        try:
            seen_dt = datetime.fromisoformat(seen_at)
        except ValueError:
            continue

        if seen_dt >= cutoff:
            pruned[fingerprint] = metadata

    return pruned


def should_send_alert(
    alert: dict[str, Any],
    sent_cache: dict[str, dict[str, str]],
    current_time: datetime,
    reminder_after_minutes: int,
) -> str | None:
    """Return the reason to send an alert now, or None when it should stay suppressed."""
    fingerprint = alert["fingerprint"]
    metadata = sent_cache.get(fingerprint)
    if not metadata:
        return "new"

    sent_at = metadata.get("sent_at")
    if not sent_at:
        return "new"

    try:
        sent_dt = datetime.fromisoformat(sent_at)
    except ValueError:
        return "new"

    if current_time - sent_dt >= timedelta(minutes=reminder_after_minutes):
        return "reminder"

    return None


def build_cache_record(alert: dict[str, Any], current_time: datetime) -> dict[str, str]:
    """Create a human-readable cache entry for a sent alert."""
    route_text = ",".join(alert.get("routes", []))
    stop_text = ",".join(alert.get("stops", []))
    agency_text = ",".join(alert.get("agencies", []))
    sent_at = current_time.isoformat()
    return {
        "sent_at": sent_at,
        "first_sent_at": alert.get("first_sent_at", sent_at),
        "header": alert.get("header", ""),
        "agencies": agency_text,
        "routes": route_text,
        "stops": stop_text,
        "alert_id": alert.get("id", ""),
        "active_period_signature": alert.get("active_period_signature", ""),
        "detail_url": alert.get("detail_url", ""),
    }


def build_subject(
    config: dict[str, Any], new_count: int, reminder_count: int
) -> str:
    """Build a more noticeable email subject line."""
    prefix = config.get("notifications", {}).get("subject_prefix", "🚨 Commute Alert")
    if reminder_count:
        body = f"{new_count} new, {reminder_count} ongoing service issue(s)"
    else:
        body = f"{new_count} new service issue(s)"

    if prefix:
        return f"{prefix}: {body}"
    return body


def build_fetch_error_snapshot_payload(
    exc: Exception,
    *,
    config: dict[str, Any],
    project_root: Path,
    current_time: datetime,
) -> dict[str, Any]:
    """Build a detailed snapshot payload for fetch errors."""
    payload: dict[str, Any] = {
        "checked_at": current_time.isoformat(),
        "status": "fetch_error",
        "error": str(exc),
        "error_type": type(exc).__name__,
    }

    if isinstance(exc, FeedParseError):
        raw_path = save_raw_error_snapshot(
            config=config,
            project_root=project_root,
            current_time=current_time,
            snapshot_name="fetch-error-raw",
            response_bytes=exc.response_bytes,
        )
        payload.update(
            {
                "feed_url": exc.url,
                "status_code": exc.status_code,
                "content_type": exc.content_type,
                "preview_text": exc.preview_text,
                "raw_snapshot_path": raw_path,
                "raw_bytes_saved": min(
                    len(exc.response_bytes),
                    int(config.get("snapshots", {}).get("raw_max_bytes", 250000)),
                ),
            }
        )

    return payload


def main() -> int:
    """Run one poll cycle: fetch alerts, filter them, and send one email if needed."""
    project_root = Path(__file__).resolve().parent.parent
    config = load_config(project_root / "config" / "config.yaml")
    logger = setup_logging(config, project_root)
    now = get_now_in_timezone(config)

    logger.info("Starting commute alert check")

    if not is_within_commute_window(config, now):
        logger.info("Outside commute window; exiting without checking feeds")
        return 0

    cache_config = config.get("cache", {})
    cache_path = project_root / cache_config.get("file", "data/alert_cache.json")
    retention_hours = int(cache_config.get("retention_hours", 48))
    reminder_after_minutes = int(cache_config.get("reminder_after_minutes", 90))
    sent_cache = prune_cache(load_cache(cache_path), now, retention_hours)

    try:
        all_alerts = fetch_all_alerts(config)
    except Exception as exc:
        logger.exception("Failed to fetch MTA alerts: %s", exc)
        save_snapshot(
            config=config,
            project_root=project_root,
            current_time=now,
            snapshot_name="fetch-error",
            payload=build_fetch_error_snapshot_payload(
                exc,
                config=config,
                project_root=project_root,
                current_time=now,
            ),
        )
        return 1

    logger.info("Fetched %s total alerts from the MTA service alerts feed", len(all_alerts))

    relevant_alerts = filter_relevant_alerts(all_alerts, config, now)
    alerts_to_send: list[dict[str, Any]] = []
    for alert in relevant_alerts:
        send_reason = should_send_alert(
            alert=alert,
            sent_cache=sent_cache,
            current_time=now,
            reminder_after_minutes=reminder_after_minutes,
        )
        if not send_reason:
            continue
        enriched_alert = dict(alert)
        enriched_alert["send_reason"] = send_reason
        existing = sent_cache.get(alert["fingerprint"], {})
        enriched_alert["first_sent_at"] = existing.get("first_sent_at", now.isoformat())
        alerts_to_send.append(enriched_alert)

    if not alerts_to_send:
        logger.info(
            "No sendable relevant alerts found. Checked=%s Relevant=%s",
            len(all_alerts),
            len(relevant_alerts),
        )
        save_cache(cache_path, sent_cache)
        save_snapshot(
            config=config,
            project_root=project_root,
            current_time=now,
            snapshot_name="no-send",
            payload={
                "checked_at": now.isoformat(),
                "status": "no_send",
                "total_alerts": len(all_alerts),
                "relevant_alerts": len(relevant_alerts),
                "alerts_to_send": 0,
                "fetched_alerts": all_alerts,
                "matched_alerts": relevant_alerts,
            },
        )
        return 0

    new_count = sum(1 for alert in alerts_to_send if alert["send_reason"] == "new")
    reminder_count = len(alerts_to_send) - new_count
    subject = build_subject(config, new_count, reminder_count)
    body_lines = build_email_lines(alerts_to_send, now, config)
    body = "\n".join(body_lines)

    try:
        send_email(config, subject, body)
    except Exception as exc:
        logger.exception("Failed to send email: %s", exc)
        save_snapshot(
            config=config,
            project_root=project_root,
            current_time=now,
            snapshot_name="email-error",
            payload={
                "checked_at": now.isoformat(),
                "status": "email_error",
                "error": str(exc),
                "subject": subject,
                "body": body,
                "total_alerts": len(all_alerts),
                "relevant_alerts": len(relevant_alerts),
                "alerts_to_send": alerts_to_send,
            },
        )
        return 1

    for alert in alerts_to_send:
        sent_cache[alert["fingerprint"]] = build_cache_record(alert, now)

    save_cache(cache_path, sent_cache)
    save_snapshot(
        config=config,
        project_root=project_root,
        current_time=now,
        snapshot_name="email-sent",
        payload={
            "checked_at": now.isoformat(),
            "status": "email_sent",
            "subject": subject,
            "body": body,
            "total_alerts": len(all_alerts),
            "relevant_alerts": len(relevant_alerts),
            "new_alerts": new_count,
            "ongoing_reminders": reminder_count,
            "fetched_alerts": all_alerts,
            "matched_alerts": relevant_alerts,
            "sent_alerts": alerts_to_send,
        },
    )
    logger.info(
        "Sent email for %s alerts (%s new, %s ongoing reminders). Relevant=%s Checked=%s",
        len(alerts_to_send),
        new_count,
        reminder_count,
        len(relevant_alerts),
        len(all_alerts),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
