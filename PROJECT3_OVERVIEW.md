# Project 3 — Measuring Online Password Guessing Resistance

This document maps the framework in this repository to the Project 3 deliverables and explains how to reproduce the measurements.

## Goal restated

> Design and implement a controlled and reproducible measurement framework that evaluates how well authentication systems resist automated online password guessing attacks. Quantitatively characterize commonly deployed defensive mechanisms under realistic attacker strategies.

## Deliverable coverage

### 1. Controlled attacker framework — [`attack/main.py`](attack/main.py)

A reusable HTTP password-guessing client.

- Iterates a wordlist against a target login endpoint.
- Two transports: JSON (`--mode cli`) and form-encoded (`--mode web`).
- Auto-reset toggle so blocks are honored (`--no-auto-reset-on-block`).
- Per-attempt CSV log: `timestamp_utc, mode, attempt, username, wordlist_file, password, status_code, event_reason, message`.
- Sophistication knobs (model real-world attacker capability):
  - `--solve-pow` — solves SHA-256 proof-of-work challenges and retries.
  - `--solve-captcha` — sends magic token to bypass CAPTCHA gate (models human-in-the-loop).
  - `--no-user-agent` — strips `User-Agent` header (models naive scripted attacker).

### 2. Defensive mechanisms — [`login-lab/routes/auth.py`](login-lab/routes/auth.py)

All policies are env-driven so the same binary runs many configurations:

| Project category | Implemented mechanisms (env vars) | Configs |
|---|---|---|
| **Rate limiting** | IP rate limit (`IP_MAX_ATTEMPTS`, `IP_WINDOW_SECONDS`); permanent IP ban (`PERMA_BAN_THRESHOLD`, `PERMA_BAN_WINDOW_SECONDS`) | `C_ip_rate_limit`, `I_perma_ban` |
| **Progressive delays** | Tarpit (`TARPIT_SECONDS`); IP exponential backoff (`IP_BACKOFF_BASE_SECONDS`, `IP_BACKOFF_CAP_SECONDS`) | `D_tarpit_500ms`, `D2_tarpit_1s`, `D3_tarpit_2s`, `E_ip_exp_backoff` |
| **Lockout behaviour** | Account lockout (`ACCOUNT_MAX_FAILURES`, `ACCOUNT_LOCKOUT_SECONDS`) | `B_account_lockout` |
| **Account-based throttling** | Account lockout (above) | `B_account_lockout` |
| **IP-based throttling** | IP rate limit, IP exponential backoff, permanent IP ban | `C_ip_rate_limit`, `E_ip_exp_backoff`, `I_perma_ban` |
| **Bot-vs-human filters (extension)** | Proof-of-work; CAPTCHA; honeypot usernames; header anomaly detection | `F_*`, `G_*`, `J_*`, `J2_*`, `L_honeypot_username`, `M_*` |
| **Cost amplification (extension)** | Slow password hash (`PASSWORD_HASH_METHOD`) | `K_slow_hash_pbkdf2`, `K2_slow_hash_scrypt` |
| **Layered defenses** | All combined | `H_layered_basic`, `H2_layered_with_ban`, `H3_full_stack` |

### 3. Experimental testbed

- **Target system** — [`login-lab/`](login-lab/) is a small Flask service that exposes `/login`, `/reset`, `/health`, `/pow_challenge`. Its policies are configured per run via environment variables, so each measurement uses a fresh, deterministic system state.
- **Wordlist corpus** — [`passwords/raw/SecLists`](passwords/raw/SecLists/) (10k-most-common, 500-worst, etc.) supplied via the existing [`passwords/download-scripts/`](passwords/download-scripts/) tooling. The benchmark samples N entries per trial and inserts the target password at a random position via [`scripts/build_wordlist.py`](scripts/build_wordlist.py).
- **Isolation** — every config gets a freshly spawned Flask process on its own port, so mechanism state from one configuration does not leak into the next.

### 4. Reproducibility

- All runs are seeded. Pass `--seed N` to [`scripts/benchmark_defenses.py`](scripts/benchmark_defenses.py); the same seed reproduces the same wordlists and target positions.
- Each run dir under `login-lab/logs/benchmark/<UTC stamp>/` contains:
  - `summary.json` — full per-trial measurements (no-loss raw data)
  - `summary.txt` — human-readable table
  - `report.html` / `report.md` — generated overview
  - `chart_*.png` — matplotlib chart outputs
  - per-config subdir with the generated wordlists, server logs, and per-attempt attack CSVs

### 5. Comparable system-level security profile

For each (mechanism, attacker-capability) pair the framework reports:

- **Breach rate** — fraction of trials in which the attacker hit the password.
- **Median time-to-crack** — wall-clock seconds across trials, with min/max range.
- **Effective request rate** — requests/second the attacker could sustain. Lower is better for the defender.
- **Response status mix** — counts of 401 / 423 / 429 / 403 and the specific reason (PoW required, CAPTCHA required, account locked, IP banned, anomaly), so the dominant defense is identifiable.
- **First-hit position** — where in the (randomized) wordlist the password landed in the trials that breached.
- **Position vs time scatter** — a point per breached trial showing how time-to-crack scales with target depth.

These produce a system-level profile that lets two configurations be compared with a single chart.

## Reproducing the headline numbers

Prerequisites: Python venv with `requirements.txt` installed.

```bash
# (Optional) refresh wordlist corpora
python passwords/download-scripts/run_all.py

# Quick run: 1 trial per config, all 22 configs, ~5 minutes
python scripts/benchmark_defenses.py

# Full statistical run: 5 trials per config, skip the very slow ones
python scripts/benchmark_defenses.py --trials 5 --skip-slow --seed 42

# Subset for iteration: just lockout vs IP rate limit, 10 trials each
python scripts/benchmark_defenses.py \
    --trials 10 --seed 42 \
    --configs B_account_lockout,C_ip_rate_limit,E_ip_exp_backoff

# Render charts and HTML/MD report from the JSON
python scripts/render_report.py login-lab/logs/benchmark/<stamp>/summary.json
```

## Threat model and limitations

- **Attacker is online and serial** (one HTTP client, one IP). We do not yet model distributed attackers (botnets, residential proxy pools), credential stuffing across many usernames, or password-spraying.
- **Network is local** so latency variance is small. Measurements isolate defense cost, not network cost.
- **Deterministic attacker schedules** — the attacker iterates the wordlist linearly with no adaptive logic. A real attacker may switch usernames, rotate IPs, or back off. The current framework can simulate the basic forms via additional config dimensions (future work).
- **Implementation choices in the lab** (werkzeug hashes, in-memory state) are representative but not identical to production stacks. The framework is the contribution; the specific lab is one example target.

## Future extensions (matches the project's open-source-testbed deliverable)

The `attack/` client speaks plain HTTP with configurable URLs and payload shape, so it can be aimed at any real authentication endpoint. To add an open-source target as a comparison point:

1. Stand the target up locally (Docker is fine).
2. Adapt the username/password payload format if needed.
3. Add a config row in `scripts/benchmark_defenses.py` whose `env` block is empty (defenses are configured by the target itself, not by us).
4. Run the same `benchmark_defenses.py` invocation. The resulting profile is directly comparable to the in-tree lab profiles.

Suggested candidates for cross-system comparison:
- WordPress (with and without `Limit Login Attempts Reloaded`)
- Gitea / Forgejo (built-in rate limit + lockout)
- Authelia (configurable rate limiter + Argon2 hash)
- Keycloak (sophisticated brute-force detection)
- Django default `LoginView` (no defenses out of the box)
