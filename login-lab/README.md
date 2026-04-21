# Login Lab

This directory contains the Flask login target used for local password-guessing experiments.

## What it includes

- A single test account with configurable password
- Account lockout after repeated failures
- IP-based rate limiting per time window
- A reset endpoint for repeatable lab runs
- A browser UI and JSON API

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

Set `ACCOUNT_MAX_FAILURES`, `ACCOUNT_LOCKOUT_SECONDS`, `IP_MAX_ATTEMPTS`, or `IP_WINDOW_SECONDS` to `0` to disable that control.

The app loads [./.env](.env) on startup, so values in that file override the defaults above.

When you use [../scripts/run_login_lab_demo.ps1](../scripts/run_login_lab_demo.ps1), each run is stored in a timestamped folder under [./logs](logs/) with the lab stdout/stderr logs and the attack CSV outputs.

## API

- `POST /login`
  - body: `{ "username": "...", "password": "..." }`
  - returns `200`, `401`, `423`, or `429`
- `POST /reset`
  - clears lockout and IP rate-limit state
- `GET /health`

