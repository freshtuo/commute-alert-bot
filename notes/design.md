# Commute Alert Bot Design

## Goal

Version 1 is a small cron-run Python script that watches official MTA service alerts for:

- Subway routes `Q`, `1`, `2`, `3`
- LIRR alerts relevant to the Great Neck / Penn Station / Grand Central commute

It sends one email to two recipients when new relevant alerts appear during weekday commute windows.

## Non-goals

- No route planning
- No alternate-route suggestions
- No maps
- No arrivals prediction
- No bus implementation in v1
- No database
- No web app

## Runtime Flow

1. Load `config/config.yaml`
2. Check whether current time is inside the morning or evening commute window
3. Fetch subway and LIRR GTFS-Realtime alert feeds
4. Normalize the protobuf alerts into plain Python dictionaries
5. Filter alerts by:
   - monitored subway routes
   - LIRR scope text filters
   - disruption keywords
6. Compare alert fingerprints against `data/alert_cache.json`
7. If there are new alerts, send one concise email
8. Update cache and write a log line

## Why the design is intentionally simple

- Each file has one job
- Python source lives under `src/` so the top-level repo stays easier to scan
- The cache is a small JSON file instead of a database
- Cron is used instead of a long-running worker
- Plain-text email is easier to debug than HTML email
- Bus is represented in config now so it can be added later without restructuring the project

## Notes on MTA feed access

The MTA developer documentation describes GTFS-Realtime feeds for subway, rail, and alerts, while bus APIs still require a key. Some MTA documentation also references API-gateway access for alerts.

To keep v1 flexible:

- feed URLs live in `config/config.yaml`
- an optional `MTA_API_KEY` environment variable can be used if your environment requires it, but v1 subway and LIRR alerts are intended to work without depending on it
- the script still keeps the configuration and code minimal if no key is needed in practice
