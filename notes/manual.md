# Setup and Operations Manual

## 1. Create a virtual environment

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 2. Configure the bot

Edit `config/config.yaml` for shared safe defaults.
Use `config/config.local.yaml` for personal/local values that should not go to GitHub.

Typical `config/config.local.yaml` values:

- real sender Gmail address
- real recipient email addresses
- a local-only subject prefix

Edit the config and set:

- commute windows
- sender Gmail address
- recipient email addresses
- any LIRR text filters you want

## 3. Set environment variables

For Gmail, use an App Password from your Google Account, not your normal Gmail password.
You can create one at `https://myaccount.google.com/apppasswords` after enabling 2-Step Verification.

PowerShell example:

```powershell
$env:GMAIL_APP_PASSWORD = "your-16-character-google-app-password"
$env:MTA_API_KEY = "optional-if-needed"
```

Notes:

- `GMAIL_APP_PASSWORD` is required for Gmail SMTP email sending
- `MTA_API_KEY` is optional for v1 subway and LIRR alert checks
- for cron or a server environment, set these in the scheduler or shell profile instead of hard-coding them

## 4. Run the script

```powershell
python main.py
```

The root `main.py` is a small launcher that calls the code under `src/app.py`.
You should now see short status messages in the terminal as well as the detailed log file.

For testing outside the normal commute windows, the easiest approach is to temporarily widen a window in `config/config.local.yaml`, for example:

```yaml
commute_windows:
  morning:
    start: "00:00"
    end: "23:59"
```

## 5. Cron example

Linux weekday cron example that runs every 10 minutes:

```cron
*/10 7-9,16-18 * * 1-5 cd /path/to/commute-alert-bot && /path/to/python main.py
```

The script also checks the configured time windows itself, so an extra off-window run is harmless.

## 6. Files to watch

- `logs/commute-alert-bot.log`: execution log
- `data/alert_cache.json`: sent-alert history used for de-duplication and controlled reminder sends
- `data/snapshots/`: per-run JSON snapshots of fetched alerts, matched alerts, and email decisions for debugging
  If `snapshots.raw_on_error` is enabled, fetch failures can also save a raw response `.bin` file for deeper debugging.

## 7. Expected email behavior

- No email is sent when there are no new relevant alerts
- One plain-text email is sent per run when new relevant alerts are found
- Ongoing alerts can be re-sent as reminders after the configured reminder interval
- The default reminder interval is now 60 minutes
- Old cache entries are pruned automatically based on `cache.retention_hours`
- A small number of JSON snapshots are kept automatically based on `snapshots.keep_last`
