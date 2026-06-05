# Developer Guide

## Purpose

`commute-alert-bot` is a small cron-friendly Python script that checks official MTA service alerts during configured commute windows and sends email when new relevant disruptions are found.

The project is intentionally simple:

- no database
- no web server
- no background daemon
- no route planning
- no UI

One run of the script performs one full check, then exits.

## Folder Structure

```text
commute-alert-bot/
|-- main.py
|-- src/
|-- config/
|-- data/
|-- logs/
|-- notes/
|-- requirements.txt
`-- README.md
```

## File Overview

### Root files

- `main.py`
  Small launcher. This is the easiest entry point for local testing and cron.
- `requirements.txt`
  Python dependencies.
- `README.md`
  High-level project overview and quick-start instructions.

### Source code

- `src/app.py`
  Main application flow. This is the real runtime entry for the bot logic.
- `src/mta_client.py`
  Fetches official MTA GTFS-Realtime alert feeds and converts protobuf alerts into plain Python dictionaries.
- `src/alert_filter.py`
  Applies the route and keyword filtering rules and builds concise email text.
- `src/email_sender.py`
  Sends plain-text Gmail SMTP email to the configured recipients.
- `src/__init__.py`
  Marks `src` as a Python package.

### Configuration and state

- `config/config.yaml`
  Main config file for commute windows, monitored routes, feed URLs, notification settings, and keyword matching.
- `config/config.local.yaml`
  Optional gitignored local override file for personal addresses and other machine-specific settings.
- `data/alert_cache.json`
  Stores fingerprints of alerts already sent, along with send timestamps and small metadata used for de-duplication and reminder sends.
- `data/snapshots/`
  Stores a small rolling set of JSON snapshots showing what the bot fetched, matched, and decided to email.

### Support folders

- `logs/`
  Stores runtime log output.
- `notes/`
  Design notes, manual, and developer documentation.

## Entry Point

There are two layers:

- `main.py`
  Tiny launcher so the run command is simple: `python main.py`
- `src/app.py`
  Real application logic

This split keeps usage easy while keeping the implementation organized.

## Runtime Flow

Each execution of `python main.py` follows this sequence:

1. Root `main.py` imports and calls `src.app.main()`
2. `src/app.py` loads `config/config.yaml`
3. If present, `src/app.py` merges `config/config.local.yaml` on top of the shared config
4. Logging is initialized
5. Current time is checked against the configured commute windows
6. If the current time is outside the allowed window, the script logs that and exits
7. If inside the window, the script fetches the combined MTA service alerts feed
8. The protobuf alert data is normalized into simple dictionaries
9. The alert list is filtered for:
   - monitored subway routes
   - monitored bus routes
   - LIRR text relevance
   - disruption keywords
   - alerts active right now
10. The bot loads `data/alert_cache.json`
11. Alerts already seen before are suppressed unless they have reached the reminder interval
12. If any new or reminder-eligible relevant alerts remain, one email is sent
13. A JSON snapshot is written for debugging
14. Alert fingerprints and send metadata are written to the cache
15. The script logs the result and exits

## How Real-Time Info Is Fetched

The bot uses official MTA GTFS-Realtime service alert feeds.

The feed URL is defined in `config/config.yaml`:

- `feeds.service_alerts_url`

### Implementation details

- `src/mta_client.py` uses `requests.get(...)` to download the feed
- the response body is parsed using `gtfs-realtime-bindings`
- only entities with an `alert` field are processed
- each alert is normalized into a standard Python dictionary
- the app then filters those alerts locally for the monitored subway routes, monitored bus routes, and LIRR scope

The normalized structure includes:

- `id`
- `source`
- `agencies`
- `routes`
- `stops`
- `header`
- `description`
- `active_periods`
- `active_period_signature`
- `detail_url`
- `fingerprint`

This normalization step makes the rest of the app independent from raw protobuf objects.

### About `MTA_API_KEY`

`MTA_API_KEY` is optional in this project.

- the config keeps an `api_key_env` field as a fallback
- the HTTP client sends the key only if that environment variable is set
- for v1 subway and LIRR alerts, the bot is intended to work without requiring the key
- this leaves room for future feed or environment differences without complicating the normal setup

## How Alerts Are Filtered

Filtering happens in `src/alert_filter.py`.

### 1. Active now

`alert_is_active_now(...)` checks the GTFS active period and keeps only alerts that are in effect now.

This prevents emailing about alerts that only start later.

### 2. Keyword match

`alert_matches_keywords(...)` checks the alert header and description for words such as:

- `delay`
- `delayed`
- `cancelled`
- `canceled`
- `suspended`
- `reroute`
- `signal problem`
- `switch problem`
- `service change`

These keywords come from `config/config.yaml`.

### 3. Route or rail scope match

`filter_relevant_alerts(...)` then applies commute-specific scope:

- subway alerts must match one of the monitored routes: `Q`, `1`, `2`, `3`
- bus alerts can match monitored routes such as `M96` and `M106`
- LIRR alerts must pass the configured text filters such as:
  - `great neck`
  - `penn station`
  - `grand central`
  - `port washington`

This keeps the bot focused on your regular commute instead of all citywide service notices.

## How Email Notification Works

Notification is handled by `src/email_sender.py`.

### SMTP flow

1. Read sender and recipient settings from `config/config.yaml`
2. Read the Gmail App Password from the environment variable named in config
3. Build a plain-text email with `email.message.EmailMessage`
4. Connect to Gmail SMTP
5. Upgrade to TLS with `starttls()`
6. Log in with the sender Gmail account and app password
7. Send the message

When possible, the email also includes a human-readable link:

- first choice: the alert's own GTFS `url` field, if present
- fallback for all modes: `https://www.mta.info/`
  This uses the MTA homepage, where the Service Status area is the better real-time fallback than the broader planned-service alerts page.

### What the Gmail App Password is

The Gmail App Password is a 16-character code generated in the Google Account security settings for the dedicated sender account.

- it is not the normal Gmail password
- it is created after 2-Step Verification is enabled
- it can be revoked without changing the main account password
- it is what the bot stores in `GMAIL_APP_PASSWORD`

Useful setup link:

- `https://myaccount.google.com/apppasswords`

### Why Gmail App Passwords are used

- safer than hard-coding credentials
- easy to use with cron or server environment variables
- avoids storing secrets in the repo

## How Duplicate Alerts Are Avoided

Duplicate prevention is handled by `data/alert_cache.json` plus the cache functions in `src/app.py`.

### Why the cache exists

MTA alerts often remain active for a while. Since cron may run every 10 minutes, the same alert would otherwise trigger repeated emails.

### How it works

1. Every normalized alert gets a `fingerprint`
2. The fingerprint is built in `src/mta_client.py` from stable incident fields such as the MTA alert ID, agencies, routes, stops, active period signature, header, and description
3. Before sending email, `src/app.py` loads the existing cache
4. If a fingerprint is new, the bot sends it immediately
5. If a fingerprint is already known but the alert is still active and the reminder interval has passed, the bot can send one controlled reminder
6. After a successful email send, the cache stores the send time plus a small amount of human-readable alert metadata

Example cache shape:

```json
{
  "alerts": {
    "some_fingerprint_hash": {
      "sent_at": "2026-06-05T08:40:12-04:00",
      "first_sent_at": "2026-06-04T17:09:46-04:00",
      "header": "Delays on the [Q] train",
      "routes": "Q",
      "alert_id": "lmm:alert:104907",
      "active_period_signature": "2026-06-05T12:00:00+00:00>2026-06-05T15:00:00+00:00"
    }
  }
}
```

### Cache cleanup

`prune_cache(...)` removes old entries based on `cache.retention_hours` from config so the file stays small.
`should_send_alert(...)` allows a still-active alert to send again after `cache.reminder_after_minutes`.

## Debug Snapshots

The bot now writes a small rolling set of JSON snapshots to `data/snapshots/`.

These snapshots are for debugging questions like:

- what did the MTA feed contain at that moment?
- which alerts matched the commute rules?
- what exactly was emailed?
- why did a run send nothing?

Snapshot files are written for:

- successful email sends
- no-send runs
- fetch failures
- email failures

If `snapshots.raw_on_error` is enabled, fetch failures can also save a `.bin` file containing the raw feed response body, capped by `snapshots.raw_max_bytes`.

This is especially useful because MTA alerts can change or disappear later.

## Main Functions and Their Roles

### `src/app.py`

- `load_config(config_path)`
  Loads YAML config from disk.
- `setup_logging(config, project_root)`
  Creates the log folder and file logger.
- `get_now_in_timezone(config)`
  Returns the current time in the configured timezone.
- `parse_clock(value)`
  Parses `HH:MM` config strings into Python `time` objects.
- `is_within_commute_window(config, current_time)`
  Checks whether the bot should run right now.
- `load_cache(cache_path)`
  Reads previously-sent alert fingerprints.
- `save_cache(cache_path, fingerprints)`
  Writes the updated cache back to disk.
- `save_snapshot(config, project_root, current_time, snapshot_name, payload)`
  Writes one JSON debugging snapshot and prunes older snapshot files.
- `save_raw_error_snapshot(config, project_root, current_time, snapshot_name, response_bytes)`
  Optionally writes the raw feed response body for fetch-error debugging.
- `prune_snapshot_files(snapshot_dir, keep_last)`
  Keeps only the newest configured snapshot files.
- `prune_cache(fingerprints, current_time, retention_hours)`
  Removes stale cache entries.
- `should_send_alert(alert, sent_cache, current_time, reminder_after_minutes)`
  Decides whether an alert is new, reminder-eligible, or still suppressed.
- `build_cache_record(alert, current_time)`
  Builds the cache entry written after a successful send.
- `build_subject(config, new_count, reminder_count)`
  Creates a more noticeable email subject line.
- `main()`
  Coordinates the entire run.

### `src/mta_client.py`

- `fetch_all_alerts(config)`
  Fetches both subway and LIRR alerts.
- `fetch_feed(...)`
  Downloads and parses one GTFS-Realtime feed.
- `normalize_alert(entity, source)`
  Converts protobuf alert data into the internal dictionary format.
- `build_active_period_signature(active_periods)`
  Collapses active periods into a stable string used for fingerprinting.
- `get_translated_text(translated_string)`
  Extracts text from GTFS translated string fields.
- `unix_to_iso(timestamp)`
  Converts Unix timestamps to ISO strings.
- `build_fingerprint(alert)`
  Creates a stable incident-aware de-duplication key.

### `src/alert_filter.py`

- `filter_relevant_alerts(alerts, config, current_time)`
  Applies the main filtering rules.
- `alert_is_active_now(alert, current_time)`
  Checks whether the alert is active at the current time.
- `alert_matches_keywords(alert, keywords)`
  Checks disruption keywords.
- `alert_matches_lirr_scope(alert, text_filters)`
  Narrows LIRR alerts to the commute-related scope.
- `build_email_lines(alerts, current_time, config)`
  Creates the plain-text email body.
- `build_alert_summary(alert)`
  Builds one compact line per alert.
- `clean_text(text, limit=280)`
  Normalizes whitespace and trims long descriptions.

### `src/email_sender.py`

- `send_email(config, subject, body)`
  Sends the final plain-text email through Gmail SMTP.

## Configuration Summary

`config/config.yaml` controls:

- timezone
- weekday-only commute windows
- subway and LIRR feed URLs
- request timeout
- monitored subway routes
- subway enabled flag
- monitored bus routes and bus enabled flag
- LIRR route IDs, stop IDs, route names, station names, and text filters
- optional future bus arrivals/vehicle tracking work
- notification sender and recipients
- email subject prefix
- keyword list
- cache file, retention period, and reminder interval
- snapshot directory and how many snapshots to keep
- whether raw fetch-error bodies should be saved, and how many bytes to keep
- log folder and file name

## GTFS Bindings vs MTA `updated_at`

The project currently uses `gtfs-realtime-bindings`, which is the standard Python package for reading ordinary GTFS-Realtime protobuf messages such as:

- feed header
- alert entities
- informed entities
- active periods
- header text
- description text

MTA also publishes Mercury-specific extensions in its alerts feed documentation, including fields such as:

- `created_at`
- `updated_at`
- `alert_type`
- `display_before_active`

Those extension fields are not part of the standard GTFS-Realtime Python bindings by default.

That is why the current code can read standard GTFS-Realtime alert fields but does not yet read MTA Mercury `updated_at`.

To use `updated_at` directly, we would need to add support for MTA's Mercury protobuf extensions or generated classes for that schema.

## How To Test the Tool

### Local Windows test

1. Install dependencies
2. Set `GMAIL_APP_PASSWORD`
3. Optionally set `MTA_API_KEY`
4. Temporarily widen the commute window in `config/config.local.yaml`
5. Run `python main.py`
6. Check:
   - email inbox
   - `logs/commute-alert-bot.log`
   - `data/alert_cache.json`

### Good behavior checks

- run twice in a row and confirm the same alert is not emailed twice
- remove the Gmail App Password env var and confirm the error is clear
- set the current time outside the commute window and confirm the script exits quietly

## Linux Server / Cron Notes

The code is already designed for cron:

- one execution performs one check
- it exits on completion
- it keeps state in a small JSON file
- it does not need a long-running process manager

Typical cron usage is simply to call:

```bash
python /path/to/commute-alert-bot/main.py
```

on a repeating schedule such as every 10 minutes during weekdays.

## Why This Design Is Maintainable

- clear separation between fetch, filter, notify, and state tracking
- simple config file instead of hard-coded values
- no external database or service dependencies beyond MTA feeds and Gmail SMTP
- small number of files with focused responsibilities
- easy to test manually on Windows before moving to Linux

## Future Follow-Ups

- `monitoring.rail.route_ids` and `monitoring.rail.stop_ids` are intentionally present but currently empty.
- They are placeholders for exact GTFS IDs that should be added later once we load trustworthy static LIRR reference data.
- Current LIRR matching still relies mainly on `route_names`, `station_names`, and `text_filters`.
- Bus service alert handling is supported, but exact bus arrival/location features are still out of scope.
- The app does not yet parse MTA Mercury extension fields such as `updated_at`; adding that would improve update detection.

### Personalized Notification Profiles

A good future enhancement would be to add profile-aware routing, for example:

- `profiles.you`
- `profiles.wife`
- `profiles.shared`

Each profile could define:

- subway routes
- bus routes
- rail scope
- recipient email addresses

That would allow the bot to keep the current shared-notification behavior while optionally sending more targeted alerts when only one person's commute is affected.
