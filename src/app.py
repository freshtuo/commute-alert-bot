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
from src.mta_client import fetch_all_alerts


def load_config(config_path: Path) -> dict[str, Any]:
    """Load the YAML configuration file into a dictionary."""
    with config_path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def setup_logging(config: dict[str, Any], project_root: Path) -> logging.Logger:
    """Create the log directory and return a file-backed logger."""
    logging_config = config.get("logging", {})
    log_dir = project_root / logging_config.get("directory", "logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    log_path = log_dir / logging_config.get("file", "commute-alert-bot.log")
    logger = logging.getLogger("commute_alert_bot")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        )
        logger.addHandler(file_handler)

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


def load_cache(cache_path: Path) -> dict[str, str]:
    """Load previously-sent alert fingerprints from disk."""
    if not cache_path.exists():
        return {}

    with cache_path.open("r", encoding="utf-8") as handle:
        try:
            data = json.load(handle)
        except json.JSONDecodeError:
            return {}

    alerts = data.get("alerts", {})
    return alerts if isinstance(alerts, dict) else {}


def save_cache(cache_path: Path, fingerprints: dict[str, str]) -> None:
    """Persist sent alert fingerprints so repeat cron runs stay quiet."""
    payload = {"alerts": fingerprints}
    with cache_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)


def prune_cache(
    fingerprints: dict[str, str], current_time: datetime, retention_hours: int
) -> dict[str, str]:
    """Drop stale fingerprints so the cache stays small over time."""
    cutoff = current_time - timedelta(hours=retention_hours)
    pruned: dict[str, str] = {}

    for fingerprint, seen_at in fingerprints.items():
        try:
            seen_dt = datetime.fromisoformat(seen_at)
        except ValueError:
            continue

        if seen_dt >= cutoff:
            pruned[fingerprint] = seen_at

    return pruned


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
    retention_hours = int(cache_config.get("retention_hours", 168))
    sent_cache = prune_cache(load_cache(cache_path), now, retention_hours)

    try:
        all_alerts = fetch_all_alerts(config)
    except Exception as exc:
        logger.exception("Failed to fetch MTA alerts: %s", exc)
        return 1

    relevant_alerts = filter_relevant_alerts(all_alerts, config, now)
    new_alerts = [alert for alert in relevant_alerts if alert["fingerprint"] not in sent_cache]

    if not new_alerts:
        logger.info(
            "No new relevant alerts found. Checked=%s Relevant=%s",
            len(all_alerts),
            len(relevant_alerts),
        )
        save_cache(cache_path, sent_cache)
        return 0

    subject = f"Commute alert: {len(new_alerts)} new service issue(s)"
    body_lines = build_email_lines(new_alerts, now, config)
    body = "\n".join(body_lines)

    try:
        send_email(config, subject, body)
    except Exception as exc:
        logger.exception("Failed to send email: %s", exc)
        return 1

    timestamp = now.isoformat()
    for alert in new_alerts:
        sent_cache[alert["fingerprint"]] = timestamp

    save_cache(cache_path, sent_cache)
    logger.info(
        "Sent email for %s new alerts. Relevant=%s Checked=%s",
        len(new_alerts),
        len(relevant_alerts),
        len(all_alerts),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
