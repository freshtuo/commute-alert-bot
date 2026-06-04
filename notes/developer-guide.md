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
- `data/alert_cache.json`
  Stores fingerprints of alerts already sent, so the bot does not send the same alert repeatedly.

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
3. Logging is initialized
4. Current time is checked against the configured commute windows
5. If the current time is outside the allowed window, the script logs that and exits
6. If inside the window, the script fetches subway and LIRR alert feeds
7. The protobuf alert data is normalized into simple dictionaries
8. The alert list is filtered for:
   - monitored subway routes
   - LIRR text relevance
   - disruption keywords
   - alerts active right now
9. The bot loads `data/alert_cache.json`
10. Alerts already seen before are removed
11. If any new relevant alerts remain, one email is sent
12. New alert fingerprints are written to the cache
13. The script logs the result and exits

## How Real-Time Info Is Fetched

The bot uses official MTA GTFS-Realtime service alert feeds.

The feed URLs are defined in `config/config.yaml`:

- `feeds.subway_alerts_url`
- `feeds.lirr_alerts_url`

### Implementation details

- `src/mta_client.py` uses `requests.get(...)` to download the feed
- the response body is parsed using `gtfs-realtime-bindings`
- only entities with an `alert` field are processed
- each alert is normalized into a standard Python dictionary

The normalized structure includes:

- `id`
- `source`
- `routes`
- `stops`
- `header`
- `description`
- `active_periods`
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
2. The fingerprint is built in `src/mta_client.py` by hashing stable alert fields
3. Before sending email, `src/app.py` loads the existing cache
4. Any alert whose fingerprint is already in the cache is skipped
5. After a successful email send, the new fingerprints are stored with a timestamp

Example cache shape:

```json
{
  "alerts": {
    "some_fingerprint_hash": "2026-06-03T08:40:12-04:00"
  }
}
```

### Cache cleanup

`prune_cache(...)` removes old entries based on `cache.retention_hours` from config so the file stays small.

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
- `prune_cache(fingerprints, current_time, retention_hours)`
  Removes stale cache entries.
- `main()`
  Coordinates the entire run.

### `src/mta_client.py`

- `fetch_all_alerts(config)`
  Fetches both subway and LIRR alerts.
- `fetch_feed(...)`
  Downloads and parses one GTFS-Realtime feed.
- `normalize_alert(entity, source)`
  Converts protobuf alert data into the internal dictionary format.
- `get_translated_text(translated_string)`
  Extracts text from GTFS translated string fields.
- `unix_to_iso(timestamp)`
  Converts Unix timestamps to ISO strings.
- `build_fingerprint(alert)`
  Creates a stable de-duplication key.

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
- LIRR text filters
- optional future bus config
- notification sender and recipients
- keyword list
- cache file and retention period
- log folder and file name

## How To Test the Tool

### Local Windows test

1. Install dependencies
2. Set `GMAIL_APP_PASSWORD`
3. Optionally set `MTA_API_KEY`
4. Temporarily widen the commute window in config
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
