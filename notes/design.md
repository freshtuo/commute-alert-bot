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
3. Fetch the combined MTA GTFS-Realtime service alerts feed
4. Normalize the protobuf alerts into plain Python dictionaries
5. Filter alerts by:
   - monitored subway routes
   - LIRR scope text filters
   - disruption keywords
6. Compare alert fingerprints against `data/alert_cache.json`
7. If there are new alerts, or still-active alerts that have reached the reminder interval, send one concise email
8. Save a JSON debugging snapshot for the run
9. On feed parse failures, optionally save the raw response bytes for debugging
10. Update cache and write a log line

## Why the design is intentionally simple

- Each file has one job
- Python source lives under `src/` so the top-level repo stays easier to scan
- The cache is a small JSON file instead of a database
- The cache stores both send times and a little alert metadata so reminders and cleanup stay simple
- Cron is used instead of a long-running worker
- Plain-text email is easier to debug than HTML email
- Bus is represented in config now so it can be added later without restructuring the project

## Notes on MTA feed access

The MTA developer documentation describes GTFS-Realtime feeds for subway, rail, and alerts, while bus APIs still require a key. For v1, the bot uses the combined service alerts feed and filters it down locally to the commute-relevant subway and LIRR alerts.

To keep v1 flexible:

- feed URLs live in `config/config.yaml`
- an optional `MTA_API_KEY` environment variable can be used if your environment requires it, but v1 subway and LIRR alerts are intended to work without depending on it
- the script still keeps the configuration and code minimal if no key is needed in practice

## To Be Implemented Later

- Populate `monitoring.rail.route_ids` with the exact GTFS route ID for the Port Washington Branch when static LIRR GTFS reference data is wired in.
- Populate `monitoring.rail.stop_ids` with exact GTFS stop IDs for Great Neck, Penn Station, and Grand Central.
- Decide whether to add exact GTFS IDs for bus routes/stops when bus monitoring is added in v2.
- Add direct support for MTA Mercury extension fields such as `updated_at` if we want more precise alert-update detection.
- Revisit whether raw snapshots should also be saved for successful runs, or only for fetch failures.
