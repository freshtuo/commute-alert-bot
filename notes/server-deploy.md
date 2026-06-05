# Server Deployment Guide

## Goal

This guide shows a simple Linux server setup for running `commute-alert-bot` from cron.

The design stays intentionally small:

- one project folder
- one Python virtual environment
- one cron entry
- local config and environment variables for secrets

## Suggested Folder Layout

Example server path:

```text
/opt/commute-alert-bot
```

Inside that folder:

- project source
- `.venv/`
- `config/config.local.yaml`
- `logs/`
- `data/`

## 1. Copy the Project to the Server

Example:

```bash
git clone <your-repo-url> /opt/commute-alert-bot
cd /opt/commute-alert-bot
```

## 2. Create the Python Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 3. Create Local Config

Keep the shared repo-safe defaults in:

```text
config/config.yaml
```

Put personal/server-specific values in:

```text
config/config.local.yaml
```

Example:

```yaml
notifications:
  sender_email: "your-bot@gmail.com"
  recipients:
    - "you@example.com"
    - "wife@example.com"
  subject_prefix: "🚨 Commute Alert"
```

You can also override commute windows locally if needed.

## 4. Set Secrets Safely

The bot expects:

- `GMAIL_APP_PASSWORD`
- optionally `MTA_API_KEY`

Do not hard-code these in tracked files.

### Option A: small wrapper script

Create a file such as:

```text
/opt/commute-alert-bot/run.sh
```

Example:

```bash
#!/usr/bin/env bash
set -euo pipefail

cd /opt/commute-alert-bot
export GMAIL_APP_PASSWORD='your_16_character_app_password'
# export MTA_API_KEY='optional_if_needed'

/opt/commute-alert-bot/.venv/bin/python main.py
```

Make it executable:

```bash
chmod +x /opt/commute-alert-bot/run.sh
```

### Option B: put env vars directly in cron

This works too, but many people prefer the wrapper script because it is easier to read and update.

## 5. Test Manually on the Server

Before using cron:

```bash
cd /opt/commute-alert-bot
source .venv/bin/activate
export GMAIL_APP_PASSWORD='your_16_character_app_password'
python main.py
```

Check:

- terminal output
- `logs/commute-alert-bot.log`
- `data/alert_cache.json`
- `data/snapshots/`

## 6. Add the Cron Job

Edit crontab:

```bash
crontab -e
```

### Recommended cron example using `run.sh`

```cron
*/10 7-9,16-18 * * 1-5 /opt/commute-alert-bot/run.sh >> /opt/commute-alert-bot/logs/cron.log 2>&1
```

This means:

- every 10 minutes
- during hours 7-9 and 16-18
- Monday through Friday

The Python script also checks commute windows itself, so slightly broader cron scheduling is okay.

### Direct cron example without wrapper script

```cron
*/10 7-9,16-18 * * 1-5 cd /opt/commute-alert-bot && GMAIL_APP_PASSWORD='your_16_character_app_password' /opt/commute-alert-bot/.venv/bin/python main.py >> /opt/commute-alert-bot/logs/cron.log 2>&1
```

## 7. Verify Cron Is Working

Things to check:

- does `logs/cron.log` get updated?
- does `logs/commute-alert-bot.log` show runs?
- does `data/snapshots/` show recent snapshots?
- are email alerts arriving?

If needed, inspect the server time:

```bash
date
timedatectl
```

Make sure the server timezone matches your expectations, or keep the app timezone in config as `America/New_York`.

## 8. Common Issues

### Cron runs but no email arrives

Check:

- `GMAIL_APP_PASSWORD`
- sender and recipients in `config/config.local.yaml`
- spam/junk folders
- `logs/commute-alert-bot.log`

### Cron runs but no alerts are checked

Likely causes:

- current time is outside the configured commute window
- config override is not what you expected

### Cron cannot find Python or dependencies

Use the full virtualenv path:

```text
/opt/commute-alert-bot/.venv/bin/python
```

### Fetch or parse errors

Check:

- `logs/commute-alert-bot.log`
- latest JSON snapshot in `data/snapshots/`
- any raw `.bin` snapshot created on fetch failure

## 9. Recommended Operational Habit

For a small project like this, a good habit is:

- test manually after each config/code change
- then let cron take over
- periodically review:
  - `logs/commute-alert-bot.log`
  - `logs/cron.log`
  - `data/snapshots/`

This keeps the deployment simple and easy to debug.
