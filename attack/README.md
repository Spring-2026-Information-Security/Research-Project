# Attack Client

HTTP password-guessing client used as the attacker side of the measurement framework. Same binary models several attacker capability tiers via flags, so the framework can compare each defense against naive bots, sophisticated bots, and human-in-the-loop attackers.

## What it does

- POSTs `(username, password)` to a target login endpoint.
- Iterates one or more wordlists; can also discover wordlists under a directory tree.
- Logs each attempt to a CSV (`timestamp_utc, mode, attempt, username, wordlist_file, password, status_code, event_reason, message`).
- Optionally solves SHA-256 proof-of-work challenges or CAPTCHA gates issued by the server.
- Optionally strips the `User-Agent` header to model a naive scripted attacker.

## Modes

- `--mode cli` (default) - JSON body
- `--mode web` - form-encoded body
- `--mode both` - run cli then web sequentially

## Examples

Attack a server that's already running:

```
python attack/main.py --base-url http://127.0.0.1:5000 \
    --password-list login-lab/wordlists/benchmark.txt \
    --no-auto-reset-on-block
```

Use a real wordlist from SecLists:

```
python attack/main.py --base-url http://127.0.0.1:5000 \
    --password-list passwords/raw/SecLists/Common-Credentials/10k-most-common.txt \
    --max-passwords 200 \
    --no-auto-reset-on-block
```

Discover wordlists from a directory tree:

```
python attack/main.py --mode both \
    --generated-root passwords/raw --pattern '*.txt' \
    --no-auto-reset-on-block
```

## Attacker capability flags

| Flag | Models |
|---|---|
| (default) | Naive scripted bot - sends username/password, no JS, no humans |
| `--solve-pow` | Sophisticated bot with a SHA-256 proof-of-work solver in its loop |
| `--solve-captcha` | Human-in-the-loop attacker (sends magic CAPTCHA token) |
| `--no-user-agent` | Lazy script that didn't bother spoofing browser headers |
| `--no-auto-reset-on-block` | Honest measurement - blocks really stop the run |

Without `--no-auto-reset-on-block` the client calls `POST /reset` whenever it sees a 423 or 429 and continues. That's useful for demos but masks defense effectiveness; benchmark runs always pass it.

## Other flags

- `--base-url URL` (default `http://127.0.0.1:5000`)
- `--username NAME` (default `test_user`)
- `--password-list PATH` (repeatable; can also point at a directory)
- `--max-passwords N` cap on attempts (`0` = unlimited)
- `--delay SEC` per-attempt sleep
- `--csv-log PATH` per-attempt CSV path (default: a fresh timestamped path under `login-lab/logs/`)
- `--log-dir PATH` directory for per-run logs; produces `attack_attempts_cli.csv` / `attack_attempts_web.csv` inside

## Environment

If a `attack/.env` file is present, the client reads `ATTACK_*` defaults from it. Command-line flags always override env values. The benchmark orchestrator constructs its own per-trial environment, so the env file only matters for manual runs.
