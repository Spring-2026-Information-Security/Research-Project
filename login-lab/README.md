# Login Lab for Password Guessing Tests

This is a local login target for your CS project experiments.

## What it includes

- A single test account with configurable password
- Account lockout after repeated failures
- IP-based rate limiting per time window
- A reset endpoint for repeatable lab runs
- A browser UI and JSON API
- Attack demo script that can read generated wordlists from `passwords/raw`

## Quick start

1. Install dependencies from repo root:

```powershell
pip install -r requirements.txt
```

2. Start the app from repo root:

```powershell
python login-lab/app.py
```

3. Open in browser:

- http://127.0.0.1:5000/

## Environment variables

- `LAB_USERNAME` default: `test_user`
- `LAB_PASSWORD` default: `correct horse battery staple`
- `ACCOUNT_MAX_FAILURES` default: `5`
- `ACCOUNT_LOCKOUT_SECONDS` default: `300`
- `IP_MAX_ATTEMPTS` default: `20`
- `IP_WINDOW_SECONDS` default: `60`
- `PORT` default: `5000`

## API

- `POST /login`
  - body: `{ "username": "...", "password": "..." }`
  - returns `200`, `401`, `423`, or `429`
- `POST /reset`
  - clears lockout and IP rate-limit state
- `GET /health`

## Using generated password scripts

Run your generators first (from repo root):

```powershell
python passwords/download-scripts/run_all.py
```

This populates files under `passwords/raw/...`.

Then run the attack demo against all generated `.txt` files:

```powershell
python login-lab/attack_demo.py --generated-root passwords/raw --pattern *.txt --max-passwords 500
```

If lockout/rate-limit blocks the run and you want to continue collecting attempts,
use automatic reset behavior:

```powershell
python login-lab/attack_demo.py --generated-root passwords/raw --pattern *.txt --max-passwords 500 --auto-reset-on-block
```

By default, lines beginning with `#` are skipped (useful for list headers/comments).
If you want to include those lines, add `--keep-comment-lines`.

By default, every attempt is logged to CSV under `login-lab/logs/`.
The CSV includes:

- `timestamp_utc`
- `attempt`
- `username`
- `wordlist_file`
- `password`
- `status_code`
- `event_reason`
- `message`

You can set an explicit CSV output path:

```powershell
python login-lab/attack_demo.py --generated-root passwords/raw --pattern *.txt --csv-log login-lab/logs/run1.csv
```

Or point to specific file(s)/folder(s):

```powershell
python login-lab/attack_demo.py --wordlist passwords/raw/breach/breach.txt --max-passwords 200
python login-lab/attack_demo.py --wordlist passwords/raw/SecLists --pattern *.txt --max-passwords 200
```

Reset lab state between runs:

```powershell
curl -X POST http://127.0.0.1:5000/reset
```
