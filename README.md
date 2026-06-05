# commute-alert-bot

Small Python script that checks official MTA service alerts during weekday commute windows and emails two recipients when there are new relevant disruptions for subway routes `Q`, `1`, `2`, `3`, bus routes `M96`, `M106`, and LIRR.

## Project layout

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

## What v1 does

- checks fixed commute windows from `config/config.yaml`
- fetches the combined MTA GTFS-Realtime service alerts feed and filters it down to subway, bus, and LIRR
- filters alerts to the monitored routes and disruption keywords
- avoids duplicate notifications with `data/alert_cache.json`
- sends one concise Gmail SMTP email when new alerts are found
- writes a simple log file under `logs/`
- also prints short status messages to the console for easier local testing

## What v1 does not do

- trip planning
- alternate-route suggestions
- maps
- exact bus arrival / location tracking
- exact next-train arrival checks

## Quick start

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

Keep `config/config.yaml` safe for GitHub.
Put real personal values such as sender/recipient email addresses in `config/config.local.yaml`, which is gitignored and merged automatically at runtime.

Set these environment variables before running:

- `GMAIL_APP_PASSWORD`
  This is the 16-character Google App Password for your dedicated sender Gmail account, not your normal Gmail password.
- `MTA_API_KEY` if your environment or feed access requires it
  For v1 subway and LIRR alerts, this is usually optional.

More details are in [notes/manual.md](/d:/Tools/commute-alert-bot/notes/manual.md).

For implementation details, see [notes/developer-guide.md](/d:/Tools/commute-alert-bot/notes/developer-guide.md).

For Linux server and cron setup, see [notes/server-deploy.md](/d:/Tools/commute-alert-bot/notes/server-deploy.md).
