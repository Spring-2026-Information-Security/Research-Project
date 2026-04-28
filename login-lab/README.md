# Login Lab

Flask login target used as the system-under-test for the password-guessing measurement framework. All defenses are configurable per run via environment variables, so the same binary serves every benchmark configuration.

## Endpoints

- `POST /login` - JSON `{ "username": "...", "password": "..." }` or form body. Returns `200`, `401`, `423`, `429`, or `403` depending on which defense fired.
- `POST /reset` - clears all defense state (lockouts, rate-limit windows, ban list, PoW challenges, CAPTCHA tokens, etc.). Used between benchmark runs.
- `GET /health` - cheap liveness check used by the orchestrator.
- `GET /pow_challenge` - issues a fresh proof-of-work challenge (when PoW is enabled).
- `GET /` - browser UI for manual exploration.

## Quick start

From the repo root:

```
pip install -r requirements.txt
python login-lab/app.py
```

Then open http://127.0.0.1:5000/ in a browser. The default port is 5000; override with `PORT=5050 python login-lab/app.py`.

## Defenses and their environment variables

Set an env var to `0` (or empty) to disable a defense.

| Project category | Mechanism | Env vars |
|---|---|---|
| Account lockout | Account lockout (per user) | `ACCOUNT_MAX_FAILURES`, `ACCOUNT_LOCKOUT_SECONDS` |
| Rate limiting | IP rate limit (sliding window) | `IP_MAX_ATTEMPTS`, `IP_WINDOW_SECONDS` |
| Rate limiting | Permanent IP ban | `PERMA_BAN_THRESHOLD`, `PERMA_BAN_WINDOW_SECONDS` |
| Progressive delays | Tarpit (fixed sleep on failure) | `TARPIT_SECONDS` |
| Progressive delays | IP exponential backoff | `IP_BACKOFF_BASE_SECONDS`, `IP_BACKOFF_CAP_SECONDS` |
| Cost amplification | Slow password hash | `PASSWORD_HASH_METHOD` (e.g. `pbkdf2:sha256:600000`, `scrypt:32768:8:1`) |
| Bot vs human filter | Proof-of-work challenge | `POW_FAILURES_BEFORE_CHALLENGE`, `POW_DIFFICULTY_BITS` |
| Bot vs human filter | CAPTCHA gate | `CAPTCHA_FAILURES_BEFORE_CHALLENGE` |
| Bot vs human filter | Honeypot usernames | `HONEYPOT_USERNAMES` (comma-separated) |
| Bot vs human filter | Header anomaly detection | `ANOMALY_BLOCK_MISSING_HEADERS`, `ANOMALY_REQUIRED_HEADERS` |

Other env vars:

- `LAB_USERNAME` (default `test_user`)
- `LAB_PASSWORD` (default `correct horse battery staple`)
- `PORT` (default `5000`)

The app loads [./.env](.env) at startup, so values there override the defaults above. Command-line invocations of the orchestrator construct their own per-config env, so `.env` only matters when you run the lab manually.

## Manual exploration

Override defaults inline to flip on a single defense and play with it:

```
ACCOUNT_MAX_FAILURES=3 ACCOUNT_LOCKOUT_SECONDS=60 python login-lab/app.py
```

Then point the attack client at it ([attack/README.md](../attack/README.md)) or hit `/login` with `curl`:

```
curl -i -X POST http://127.0.0.1:5000/login \
    -H 'Content-Type: application/json' \
    -d '{"username":"test_user","password":"wrong"}'
```

## Logs

Each manual run writes to `login-lab/logs/`. Benchmark sweeps write to `login-lab/logs/benchmark/<UTC stamp>/` with a per-config subdirectory containing the server stdout/stderr, generated wordlist, and per-attempt attack CSV.
