# Scripts

Helpers for environment setup, the benchmark suite, and reporting.

## Benchmark and reporting

- [benchmark_defenses.py](benchmark_defenses.py) - the orchestrator. Boots a fresh lab process per configuration, drives the attack client, aggregates per-trial results, writes summary JSON / TXT.
- [build_wordlist.py](build_wordlist.py) - samples a real password corpus and inserts the target password at a random position. Used internally by the benchmark, callable on its own for ad-hoc wordlists.
- [render_report.py](render_report.py) - reads a `summary.json` and produces 6 chart PNGs plus an HTML and Markdown report.
- [make_charts.py](make_charts.py) - convenience wrapper around `render_report.py` that finds the latest run automatically (`--all` and `--run STAMP` available).
- [build_presentation.py](build_presentation.py) - builds a 21-slide `Presentation.pptx` deck with embedded chart PNGs.

### Common invocations

```
# Full statistical sweep (~57 min; 22 configs x 5 trials)
python scripts/benchmark_defenses.py --trials 5 --seed 1337

# Quick smoke run (1 trial each, ~5 min)
python scripts/benchmark_defenses.py

# Faster representative run that skips the slowest configs
python scripts/benchmark_defenses.py --trials 5 --skip-slow --seed 42

# Only specific configs
python scripts/benchmark_defenses.py --trials 10 --seed 42 \
    --configs B_account_lockout,C_ip_rate_limit,E_ip_exp_backoff

# Render charts and report (latest run by default)
python scripts/make_charts.py
python scripts/make_charts.py --open       # open the HTML in default browser
python scripts/make_charts.py --all        # re-render every historical run
python scripts/make_charts.py --run 20260427T160006Z

# Rebuild the PowerPoint deck against the latest run's charts
python scripts/build_presentation.py
```

### Benchmark output layout

Each run writes to `login-lab/logs/benchmark/<UTC stamp>/`:

- `summary.json` - full per-trial measurements (the source of truth)
- `summary.txt` - human-readable aggregate table
- `report.html` / `report.md` - generated report
- `chart_*.png` - matplotlib outputs (verdict, elapsed, request rate, status mix, first-hit, position-vs-time)
- `<config>/trial_NN_attack.csv` - per-attempt log
- `<config>/trial_NN_server.log` - lab stdout/stderr for that trial
- `<config>/trial_NN_wordlist.txt` - the randomized wordlist for that trial
- `<config>/trial_NN_wordlist.txt.meta.json` - seed and target position metadata

## Setup helpers

- [install_env.ps1](install_env.ps1) / [install_env.sh](install_env.sh) - create the venv and install dependencies.
- [activate.ps1](activate.ps1) / [activate.sh](activate.sh) - activate the repo venv.

## Demo runner

- [run_login_lab_demo.ps1](run_login_lab_demo.ps1) - starts the lab, runs the attack client once, stops the lab if it started it. Good for live demos. Add `-NoManageLab` if the lab is already running.

```
.\scripts\run_login_lab_demo.ps1 -Mode both -GeneratedRoot passwords/raw -Pattern *.txt
```

For statistical measurement use `benchmark_defenses.py`; the demo runner is for one-off interactive sessions.
