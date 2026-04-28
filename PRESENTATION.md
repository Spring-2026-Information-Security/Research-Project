---
marp: true
theme: default
paginate: true
---

# Measuring Online Password Guessing Resistance

A reproducible measurement framework for authentication defenses

Austin & Ian . CS 47205/57205 . Project 3

<!-- ~30s. Open with the goal: we want to compare login defenses with data, not anecdote. -->

---

## The problem

Online password guessing is the single most common identity attack on the public Internet.

Every authentication system ships a different mix of defenses: account lockout, rate limiting, progressive delays, CAPTCHAs, MFA, anomaly detection, bot filters.

These defenses interact in non-obvious ways and are often misconfigured.

**Question:** how do these defenses actually compare under controlled, repeatable measurement?

**Goal:** build attacker + target framework, drive each defense through hundreds of trials, produce a comparable security profile.

---

## Threat model

We model an online, single-source attacker.

| Dimension | In scope | Out of scope (future work) |
|---|---|---|
| Attempts | Sequential HTTP login requests | Parallel / distributed |
| Source IPs | Single IP | Botnets, proxy pools |
| Targets | One known username | Credential stuffing, password spraying |
| Wordlist | Real public corpora (SecLists 10k) | Adaptive / personalised guesses |
| Knowledge | Black-box: only HTTP responses | Insider / source-code visibility |

Attacker capability tiers (naive bot, header-aware bot, PoW-solving bot, human-in-the-loop) are explicit knobs in the framework.

---

# Section 1 - Testbed

---

## Testbed architecture

Four pieces, each independently configurable.

- **Target system**: a small Flask login service. Every defense is a tunable knob.
- **Attacker client**: a single password-guessing tool with capability flags for naive bots, PoW-solving bots, and human-in-the-loop attackers.
- **Orchestrator**: boots a fresh target per configuration, runs the attacker, aggregates results.
- **Wordlist source**: real public corpora (SecLists), sampled per trial.

Each trial gets an isolated process and a fresh port - no state leaks between configurations. Every measurement is seeded and reproducible from the same inputs.

---

## Wordlist methodology

Old approach: one fixed wordlist with the password at a known position. One data point.

New approach: every trial gets its own randomized wordlist.

1. Sample 100 entries from a real public password corpus.
2. Insert the target password at a uniformly-random position.
3. Record the seed and target position so the trial is reproducible.

5 trials per config x 22 configs = 110 attack runs in the headline experiment. Same defense exercised against 5 different target depths gives a measurement distribution.

Total wall-clock for the full sweep: about 57 minutes on a laptop.

---

## Attacker capability tiers

| Tier | Behaviour |
|---|---|
| Naive scripted bot | Sends username and password. No JavaScript, no humans, no header spoofing. |
| Header-aware bot | Same as above, but spoofs a normal browser User-Agent. |
| PoW-solving bot | Includes a SHA-256 puzzle solver in its loop. |
| Human-in-the-loop | A human (or commercial solver service) handles CAPTCHAs. |

Same attacker tool models all four tiers - we toggle behaviour per run to compare each defense across the spectrum.

---

# Section 2 - Protections

---

## Ten defenses, four required categories

| Category | Mechanism | What it does |
|---|---|---|
| **Account lockout** | Account lockout | Freezes the account for a duration after N consecutive failures. |
| **Rate limiting** | IP rate limit | Caps attempts from a single IP in a sliding window. |
| **Rate limiting** | Permanent IP ban | Blacklists the IP after K failures within a long window. |
| **Progressive delays** | Tarpit | Server sleeps a fixed amount before each failed response. |
| **Progressive delays** | IP exponential backoff | Per-IP cooldown that doubles with each failure, with a cap. |
| Cost amplification | Slow password hash | pbkdf2 or scrypt to inflate per-attempt CPU cost. |
| Bot vs human filter | Proof-of-work | Server demands a SHA-256 puzzle after N failures. |
| Bot vs human filter | CAPTCHA challenge | Server demands a human-solvable token after N failures. |
| Bot vs human filter | Honeypot usernames | Contact with watched usernames triggers an instant ban. |
| Bot vs human filter | Header anomaly detection | Block requests missing typical browser headers. |

Required project categories highlighted in bold.

---

## How they're measured

Every config produces six metrics.

1. **Breach rate** - fraction of trials where the attacker hit the password.
2. **Median time-to-crack** - wall-clock seconds, with min/max range.
3. **Effective request rate** - requests/sec the attacker could sustain.
4. **Response status mix** - counts of 401 / 423 / 429 / 403 by reason.
5. **First-hit position** - where in the wordlist the password landed in the breached trials.
6. **Position vs time** - scatter showing how time-to-crack scales with target depth.

These six together form a security profile that lets two configs be compared visually.

---

# Section 3 - Results

---

## Summary across 22 configs x 5 trials

Three clean groups in the data.

- **Always blocked (0%)** - 11 of 22 configs. Every trial stopped.
- **Always breached (100%)** - 10 of 22. Defense was a slow-down only.
- **Probabilistic (80%)** - 1 config (F2_pow_22bit). Solver sometimes timed out.

---

## Hard stoppers

Every trial against these configs ended with the attacker exhausting the wordlist without a hit.

| Config | Median elapsed | Note |
|---|---|---|
| B_account_lockout | 3.4s | 5 fail -> 60s account lock |
| C_ip_rate_limit | 4.8s | 10 attempts / 30s window |
| E_ip_exp_backoff | 3.5s | 0.25s base, doubles, cap 8s |
| I_perma_ban | 3.8s | 8 failures -> blacklist |
| G_pow_naive_attacker | 3.7s | PoW vs bot with no solver |
| J_captcha_naive | 4.5s | CAPTCHA vs bot with no solver |
| L_honeypot_username | 3.2s | Banned on first request |
| M_anomaly_no_ua | 3.7s | Missing User-Agent flagged |
| H / H2 / H3 layered | ~30s | All three layered configs |

---

## Slow-downs only

These cost the attacker time, but the password came out.

| Config | Median time | Slowdown vs baseline |
|---|---|---|
| A_baseline | 16s | 1x |
| K2_slow_hash_scrypt (default werkzeug params) | 12s | 0.7x - worse than baseline |
| J2_captcha_human (human solver) | 12s | 0.75x |
| F_pow_smart_attacker (18-bit) | 14s | 0.9x |
| K_slow_hash_pbkdf2 (600k iters) | 23s | 1.5x |
| D_tarpit_500ms | 62s | 4x |
| F2_pow_22bit (smart, 22-bit) | 95s (80% breach) | 6x |
| D2_tarpit_1s | 112s | 7x |
| **D3_tarpit_2s** | **214s** | **13x** |

Tarpit's slowdown is linear in wordlist depth times per-failure delay - predictable, tunable.

---

## Finding 1: scrypt was barely a defense

`scrypt:32768:8:1` (werkzeug's default) finished **faster** than baseline (12s vs 16s).

- Server-side scrypt cost dominated by n=32768 (~16ms on test hardware).
- Lost in HTTP roundtrip noise.
- `pbkdf2:sha256:600000` was meaningfully slower (23s, 1.5x baseline).

**Lesson:** "we use a slow hash" is not a defense unless parameters are tuned for the target hardware. Production should benchmark and aim for ~100ms per verify. Don't trust library defaults.

---

## Finding 2: PoW has a sharp probabilistic cliff

| Config | Difficulty | Breach rate | Median time |
|---|---|---|---|
| F_pow_smart_attacker | 18-bit | 100% | 14s |
| F2_pow_22bit | 22-bit | **80%** | 95s |

At 22-bit difficulty the attacker's solver hits its 5M-attempt budget often enough that one trial in five times out. The defense moves from a slow-down to a probabilistic block.

Real configuration sweet spot - but the line depends on attacker hardware.

---

## Layered defense converges

| Config | Defenses | Median time | Breach |
|---|---|---|---|
| H_layered_basic | lockout + rate-limit + tarpit + PoW | 30s | 0% |
| H2_layered_with_ban | + perma-ban + slow hash | 30s | 0% |
| H3_full_stack | + CAPTCHA + honeypot + anomaly | 30s | 0% |

Identical wall-clock, identical 0% breach. Once account-lockout fires at attempt 5, the other defenses never get a chance to activate.

That's a feature, not a bug: the cheapest defense wins, the rest are insurance for when it fails or is misconfigured. Defense-in-depth is about failure modes, not steady-state performance.

---

# Section 4 - Recommendations

---

## What to actually deploy

Minimum-viable stack: three layers with tuned parameters.

| Layer | Configuration |
|---|---|
| 1. Account lockout | ~5 failures -> >=60s lockout. Reset on legitimate login. Cheap, hard-stops named-target attacks. |
| 2. IP-based throttling | Sliding window or exponential backoff. Cap, don't permanent-ban (avoid IP-reuse pain). |
| 3. Slow password hash | argon2id or pbkdf2, tuned to ~100ms/verify on prod hardware. Verify cost - defaults are weak. |

**Don't rely on** (against motivated attackers): tarpits alone, default-parameter scrypt, header anomaly checks (trivially defeated by a User-Agent string), low-bit PoW.

**Useful add-ons:** honeypot usernames, geographic anomaly scoring, MFA on sensitive accounts.

---

## Future work

Where the framework can be extended.

- **Distributed attacker** - multi-IP, multi-process to expose IP-only defenses.
- **Cross-system comparison** - point the same attack client at WordPress, Authelia, Gitea, Keycloak. Framework already speaks plain HTTP.
- **Adaptive attackers** - observe response timing and codes, switch strategy mid-run.
- **Real CAPTCHA / MFA endpoints** - replace magic-token stubs with hCaptcha or TOTP.
- **Cost modeling** - translate "13x slowdown" into dollar cost per credential at cloud-attacker rates.

---

# Questions?
