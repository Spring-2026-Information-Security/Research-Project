# Research Project: Online Password Guessing Resistance

A controlled, reproducible measurement framework for evaluating how well authentication systems resist online password-guessing attacks (CS 47205/57205 Project 3).

The framework spins up a Flask login service, drives it with an HTTP password-guessing client, and reports comparable security profiles across many defense configurations. Ten defense mechanisms covering all four required project categories are implemented behind environment variables, and the attack client models several attacker capability tiers via flags.

## Layout

- [login-lab/](login-lab/) - Flask target. All defenses configurable per-run via env vars.
- [attack/](attack/) - HTTP password-guessing client. Attacker capabilities behind CLI flags.
- [scripts/](scripts/) - Benchmark orchestrator, wordlist generator, chart renderer, presentation builder.
- [passwords/](passwords/) - Downloaded SecLists corpus and helper download scripts.
- [PROJECT3_OVERVIEW.md](PROJECT3_OVERVIEW.md) - Deliverable mapping for the project rubric.
- [PRESENTATION.md](PRESENTATION.md) / [Presentation.pptx](Presentation.pptx) - 15-minute talk outline and built deck.

## Quick start

Install dependencies from the repo root:

```
pip install -r requirements.txt
```

### Run a full benchmark sweep

22 configurations x 5 randomized trials (~57 minutes wall-clock):

```
python scripts/benchmark_defenses.py --trials 5 --seed 1337
```

Faster sanity run (1 trial each, ~5 minutes):

```
python scripts/benchmark_defenses.py
```

Render charts and report from the latest run:

```
python scripts/make_charts.py --open
```

### Attack a server you already have running

If the lab is up on the default port, drive it directly with the attack client:

```
python attack/main.py --base-url http://127.0.0.1:5000 --password-list login-lab/wordlists/benchmark.txt --no-auto-reset-on-block
```

## What the framework measures

For every (defense, attacker-capability) combination it reports:

- Breach rate across trials (fraction where the attacker hit the password)
- Median time-to-crack with min/max range
- Effective attacker request rate (requests/sec)
- Response status mix (401 / 423 / 429 / 403 with the specific reason)
- First-hit position in the wordlist for breached trials
- Position-vs-time scatter showing how time-to-crack scales with target depth

Outputs land in `login-lab/logs/benchmark/<UTC stamp>/` as JSON, CSV per attempt, server logs, generated wordlists, six chart PNGs, and an HTML/MD report.

## Defenses implemented

| Project category | Mechanisms |
|---|---|
| Account lockout | Account lockout (per-user) |
| Rate limiting | IP rate limit; permanent IP ban |
| Progressive delays | Tarpit (fixed); IP exponential backoff |
| (extension) cost amplification | Slow password hash (pbkdf2 / scrypt) |
| (extension) bot vs human filters | Proof-of-work; CAPTCHA; honeypot usernames; header anomaly detection |

All ten are in [login-lab/routes/auth.py](login-lab/routes/auth.py) behind env vars; see that directory's README for the knobs.

## Configuration

- [login-lab/.env](login-lab/.env) - lab defaults
- [attack/.env](attack/.env) - attacker defaults
- All command-line flags override the env file values
