# Login Lab Defense Benchmark - 20260428T164742Z

- Wordlist source: `passwords/raw/SecLists/Common-Credentials/10k-most-common.txt` (300 entries per generated wordlist)
- Trials per config: **50** (target inserted at random position each trial)
- Base RNG seed: `-1`
- Total suite runtime: **23h 51m 34s** across 851 trials (avg 100.9s/trial; _wall-clock_)

## Verdict matrix

| config | category | breach % | med elapsed | min..max | med req/s | med pos | trials | description |
|---|---|---|---|---|---|---|---|---|
| `A_baseline` | none | 100% **COMPROMISED** | 42.37s | 42.1..42.7 | 7.08 | 153 | 50 | No protections - pure baseline |
| `B_account_lockout` | single | 0% blocked | 1.50s | 1.2..1.6 | 199.35 | - | 50 | Account lockout (5 fail -> 60s) |
| `C_ip_rate_limit` | single | 2% **partial** | 2.31s | 1.9..2.4 | 129.65 | 6 | 50 | IP rate limit (10 / 30s) |
| `D_tarpit_500ms` | single | 100% **COMPROMISED** | 191.14s | 190.8..191.5 | 1.57 | 153 | 50 | Tarpit 0.5s per failure |
| `E_ip_exp_backoff` | single | 0% blocked | 1.04s | 0.8..1.1 | 287.39 | - | 50 | IP exponential backoff (0.25s, cap 8s) |
| `F_pow_smart_attacker` | single | 100% **COMPROMISED** | 102.25s | 87.8..125.1 | 2.94 | 153 | 50 | PoW 18-bit after 5 fails (attacker solves) |
| `G_pow_naive_attacker` | single | 0% blocked | 1.54s | 1.2..1.6 | 194.94 | - | 50 | PoW 18-bit after 5 fails (naive attacker) |
| `I_perma_ban` | single | 2% **partial** | 2.00s | 1.6..2.2 | 150.13 | 6 | 50 | Permanent IP ban after 8 fails / 1h |
| `J_captcha_naive` | single | 0% blocked | 1.53s | 1.2..1.6 | 196.30 | - | 50 | CAPTCHA after 5 fails (naive attacker - no solver) |
| `J2_captcha_human` | single | 100% **COMPROMISED** | 42.29s | 41.7..42.5 | 7.09 | 153 | 50 | CAPTCHA after 5 fails (human-in-loop attacker solves) |
| `K_slow_hash_pbkdf2` | single | 100% **COMPROMISED** | 248.72s | 248.4..249.1 | 1.21 | 153 | 50 | Slow password hash (pbkdf2:sha256:600000) |
| `K2_slow_hash_scrypt` | single | 100% **COMPROMISED** | 41.80s | 41.3..42.1 | 7.17 | 153 | 50 | Slow password hash (scrypt:32768:8:1) |
| `L_honeypot_username` | single | 0% blocked | 0.70s | 0.7..0.8 | 427.55 | - | 50 | Honeypot usernames (attacker hits 'admin') |
| `M_anomaly_no_ua` | single | 0% blocked | 0.71s | 0.7..0.8 | 423.24 | - | 50 | Anomaly detection (attacker omits User-Agent) |
| `M2_anomaly_normal_ua` | single | 100% **COMPROMISED** | 41.83s | 40.9..42.0 | 7.17 | 153 | 50 | Anomaly detection (attacker sends normal User-Agent) |
| `D2_tarpit_1s` | variant | 100% **COMPROMISED** | 340.07s | 339.8..340.4 | 0.88 | 153 | 50 | Tarpit 1s per failure |
| `D3_tarpit_2s` | variant | 100% **COMPROMISED** | 638.07s | 637.9..638.4 | 0.47 | 153 | 50 | Tarpit 2s per failure |
| `F2_pow_22bit` | variant | 100% **COMPROMISED** | 879.67s | 879.7..879.7 | 0.31 | 132 | 1 | PoW 22-bit after 5 fails (smart attacker) |

## Charts

![verdict](chart_verdict.png)

![first hit](chart_first_hit.png)

![elapsed](chart_elapsed.png)

![request rate](chart_request_rate.png)

![status mix](chart_status_mix.png)

![position vs time](chart_position_vs_time.png)

## Mechanisms in the lab

- **Account lockout** - after N consecutive failures, the account is frozen.
- **IP rate limit** - caps attempts per IP in a sliding window.
- **Tarpit** - artificial server-side sleep on every failed response.
- **IP exponential backoff** - per-IP cooldown that doubles with each failure.
- **Proof-of-Work** - server demands a SHA-256 puzzle after N failures.
- **Permanent IP ban** - blacklist after K failures within a window.
- **CAPTCHA** - server demands a human-solvable token after N failures.
- **Slow password hash** - pbkdf2 / scrypt to inflate per-attempt CPU cost.
- **Honeypot usernames** - contact with watched usernames triggers an instant ban.
- **Anomaly detection** - block requests missing typical browser headers.