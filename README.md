# Research Project: Online Password Guessing Resistance

A controlled, reproducible measurement framework for evaluating how well authentication systems resist online password-guessing attacks (CS 47205 Project 3).

The framework spins up a Flask login service, drives it with an HTTP password-guessing client, and reports comparable security profiles across many defense configurations. Ten defense mechanisms covering all four required project categories are implemented behind environment variables, and the attack client models several attacker capability tiers via flags.

## Layout

- [login-lab/](login-lab/) - Flask target. All defenses configurable per-run via env vars.
- [attack/](attack/) - HTTP password-guessing client. Attacker capabilities behind CLI flags.
- [scripts/](scripts/) - Benchmark orchestrator, wordlist generator, chart renderer.
- [passwords/](passwords/) - Downloaded SecLists corpus and helper download scripts.
- [PROJECT3_OVERVIEW.md](PROJECT3_OVERVIEW.md) - Deliverable mapping for the project rubric.

## Headline experiment

50 trials per configuration, randomized wordlists from SecLists, 4 wordlist depths.

| Wordlist size | Configs | Trials | Suite wall-clock |
|---|---|---|---|
| 100 | 21 (full set incl. layered) | 1,050 | 13.7 h |
| 200 | 18 (no layered) | 900 | 21.5 h |
| 300 | 18 (no layered) | 900 | 23.9 h |
| 400 | 18 (one config partial) | 851 | 32.1 h |
| 500 | 17 (no layered, no F2) | 850 | 24.9 h |

The 200/300/400/500-word runs were stopped before reaching the layered configurations because the tarpit and high-bit PoW configs would have run for days more.

## Quick start

Install dependencies from the repo root:

```
pip install -r requirements.txt
```

### Run a benchmark sweep

Full statistical sweep at the headline depth (~13 hours wall-clock):

```
python scripts/benchmark_defenses.py --trials 50 --seed 1337
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
| Cost amplification (extension) | Slow password hash (pbkdf2 / scrypt) |
| Bot vs human filters (extension) | Proof-of-work; CAPTCHA; honeypot usernames; header anomaly detection |

All ten are in [login-lab/routes/auth.py](login-lab/routes/auth.py) behind env vars; see that directory's README for the knobs.

## Configuration

- [login-lab/.env](login-lab/.env) - lab defaults (used when running the lab manually; the orchestrator constructs its own env per config)
- All command-line flags override env file values
