# Attack Client

This directory contains the reusable password-guessing client in [main.py](main.py).

## What it does

- Talks to the login lab backend over HTTP.
- Supports `cli`, `web`, and `both` modes.
- Accepts one or more password lists with `--password-list`.
- Can discover wordlists from a generated root with `--generated-root` and `--pattern`.
- Logs each attempt to CSV.

## Examples

```powershell
python attack/main.py --mode cli --password-list login-lab/wordlists/sample.txt
python attack/main.py --mode web --password-list passwords/raw/breach/breach.txt --max-passwords 200
python attack/main.py --mode both --generated-root passwords/raw --pattern *.txt --auto-reset-on-block
```

## Environment

The client reads [./.env](.env) through the shared loader, so attack defaults stay aligned with the demo runner.

If you do not pass command-line options, the client uses the `ATTACK_*` values from [./.env](.env). It keeps writing results after lockout blocks by default, resetting the lab and continuing until the list is exhausted or you stop it.