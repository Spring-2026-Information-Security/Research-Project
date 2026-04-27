"""Boot the lab under different defense configs, attack each, tabulate results.

Run from the repo root:

    python scripts/benchmark_defenses.py                     # 1 trial per config
    python scripts/benchmark_defenses.py --trials 5          # 5 trials each
    python scripts/benchmark_defenses.py --trials 5 --skip-slow
    python scripts/benchmark_defenses.py --configs A_baseline,B_account_lockout

Each trial uses a freshly generated wordlist (sampled from the SecLists corpus
with the target inserted at a random position), giving us a measurement
distribution rather than a single point. Each config gets a fresh server
instance on a unique port; the attack runs with auto-reset disabled so blocks
actually stop the attacker. Results are written as a human-readable table and
a JSON file consumed by render_report.py.
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import datetime
import json
import os
import random
import socket
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
DEFAULT_WORDLIST_SOURCE = (
    REPO_ROOT / "passwords" / "raw" / "SecLists" / "Common-Credentials" / "10k-most-common.txt"
)
RESULTS_DIR = REPO_ROOT / "login-lab" / "logs" / "benchmark"
USERNAME_TARGET = "test_user"
PASSWORD_TARGET = "password123"

# Configs that take a long time per trial (tarpit, high-bit PoW). Skipped when
# --skip-slow is passed.
SLOW_CONFIGS = {"D2_tarpit_1s", "D3_tarpit_2s", "F2_pow_22bit"}


@dataclass
class Config:
    name: str
    description: str
    category: str  # "none", "single", "variant", "layered"
    env: dict[str, str]
    attack_username: str = USERNAME_TARGET
    solve_pow: bool = False
    solve_captcha: bool = False
    no_user_agent: bool = False


@dataclass
class TrialResult:
    seed: int
    wordlist_path: str
    target_position: int
    wordlist_size: int
    requests_made: int = 0
    invalid_credentials: int = 0
    blocked_423: int = 0
    blocked_429: int = 0
    blocked_403: int = 0
    pow_required: int = 0
    captcha_required: int = 0
    successes: int = 0
    first_success_attempt: int | None = None
    elapsed_seconds: float = 0.0
    requests_per_second: float = 0.0


@dataclass
class Result:
    name: str
    description: str
    category: str
    trials: list[TrialResult] = field(default_factory=list)
    success_rate: float = 0.0
    median_elapsed_seconds: float = 0.0
    median_requests_per_second: float = 0.0
    median_first_success: float | None = None
    min_elapsed_seconds: float = 0.0
    max_elapsed_seconds: float = 0.0
    notes: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)


# ── plumbing ────────────────────────────────────────────────────────────────


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def base_env() -> dict[str, str]:
    env = os.environ.copy()
    env["LAB_USERNAME"] = USERNAME_TARGET
    env["LAB_PASSWORD"] = PASSWORD_TARGET
    for k in [
        "ACCOUNT_MAX_FAILURES",
        "ACCOUNT_LOCKOUT_SECONDS",
        "IP_MAX_ATTEMPTS",
        "IP_WINDOW_SECONDS",
        "TARPIT_SECONDS",
        "IP_BACKOFF_BASE_SECONDS",
        "IP_BACKOFF_CAP_SECONDS",
        "POW_FAILURES_BEFORE_CHALLENGE",
        "POW_DIFFICULTY_BITS",
        "PERMA_BAN_THRESHOLD",
        "CAPTCHA_FAILURES_BEFORE_CHALLENGE",
    ]:
        env[k] = "0"
    env["PERMA_BAN_WINDOW_SECONDS"] = "3600"
    env["HONEYPOT_USERNAMES"] = ""
    env["ANOMALY_BLOCK_MISSING_HEADERS"] = "false"
    env["ANOMALY_REQUIRED_HEADERS"] = ""
    env["PASSWORD_HASH_METHOD"] = ""
    return env


def configs() -> list[Config]:
    out: list[Config] = []

    out.append(Config(
        name="A_baseline",
        description="No protections - pure baseline",
        category="none",
        env={},
    ))

    # Single-mechanism configs
    out.append(Config(
        name="B_account_lockout",
        description="Account lockout (5 fail -> 60s)",
        category="single",
        env={"ACCOUNT_MAX_FAILURES": "5", "ACCOUNT_LOCKOUT_SECONDS": "60"},
    ))
    out.append(Config(
        name="C_ip_rate_limit",
        description="IP rate limit (10 / 30s)",
        category="single",
        env={"IP_MAX_ATTEMPTS": "10", "IP_WINDOW_SECONDS": "30"},
    ))
    out.append(Config(
        name="D_tarpit_500ms",
        description="Tarpit 0.5s per failure",
        category="single",
        env={"TARPIT_SECONDS": "0.5"},
    ))
    out.append(Config(
        name="E_ip_exp_backoff",
        description="IP exponential backoff (0.25s, cap 8s)",
        category="single",
        env={"IP_BACKOFF_BASE_SECONDS": "0.25", "IP_BACKOFF_CAP_SECONDS": "8"},
    ))
    out.append(Config(
        name="F_pow_smart_attacker",
        description="PoW 18-bit after 5 fails (attacker solves)",
        category="single",
        env={"POW_FAILURES_BEFORE_CHALLENGE": "5", "POW_DIFFICULTY_BITS": "18"},
        solve_pow=True,
    ))
    out.append(Config(
        name="G_pow_naive_attacker",
        description="PoW 18-bit after 5 fails (naive attacker)",
        category="single",
        env={"POW_FAILURES_BEFORE_CHALLENGE": "5", "POW_DIFFICULTY_BITS": "18"},
        solve_pow=False,
    ))
    out.append(Config(
        name="I_perma_ban",
        description="Permanent IP ban after 8 fails / 1h",
        category="single",
        env={"PERMA_BAN_THRESHOLD": "8", "PERMA_BAN_WINDOW_SECONDS": "3600"},
    ))
    out.append(Config(
        name="J_captcha_naive",
        description="CAPTCHA after 5 fails (naive attacker - no solver)",
        category="single",
        env={"CAPTCHA_FAILURES_BEFORE_CHALLENGE": "5"},
        solve_captcha=False,
    ))
    out.append(Config(
        name="J2_captcha_human",
        description="CAPTCHA after 5 fails (human-in-loop attacker solves)",
        category="single",
        env={"CAPTCHA_FAILURES_BEFORE_CHALLENGE": "5"},
        solve_captcha=True,
    ))
    out.append(Config(
        name="K_slow_hash_pbkdf2",
        description="Slow password hash (pbkdf2:sha256:600000)",
        category="single",
        env={"PASSWORD_HASH_METHOD": "pbkdf2:sha256:600000"},
    ))
    out.append(Config(
        name="K2_slow_hash_scrypt",
        description="Slow password hash (scrypt:32768:8:1)",
        category="single",
        env={"PASSWORD_HASH_METHOD": "scrypt:32768:8:1"},
    ))
    out.append(Config(
        name="L_honeypot_username",
        description="Honeypot usernames (attacker hits 'admin')",
        category="single",
        env={"HONEYPOT_USERNAMES": "admin,root,administrator,sa"},
        attack_username="admin",
    ))
    out.append(Config(
        name="M_anomaly_no_ua",
        description="Anomaly detection (attacker omits User-Agent)",
        category="single",
        env={"ANOMALY_BLOCK_MISSING_HEADERS": "true", "ANOMALY_REQUIRED_HEADERS": "User-Agent"},
        no_user_agent=True,
    ))
    out.append(Config(
        name="M2_anomaly_normal_ua",
        description="Anomaly detection (attacker sends normal User-Agent)",
        category="single",
        env={"ANOMALY_BLOCK_MISSING_HEADERS": "true", "ANOMALY_REQUIRED_HEADERS": "User-Agent"},
        no_user_agent=False,
    ))

    # Variant tuning
    out.append(Config(
        name="D2_tarpit_1s",
        description="Tarpit 1s per failure",
        category="variant",
        env={"TARPIT_SECONDS": "1.0"},
    ))
    out.append(Config(
        name="D3_tarpit_2s",
        description="Tarpit 2s per failure",
        category="variant",
        env={"TARPIT_SECONDS": "2.0"},
    ))
    out.append(Config(
        name="F2_pow_22bit",
        description="PoW 22-bit after 5 fails (smart attacker)",
        category="variant",
        env={"POW_FAILURES_BEFORE_CHALLENGE": "5", "POW_DIFFICULTY_BITS": "22"},
        solve_pow=True,
    ))

    # Layered combinations
    out.append(Config(
        name="H_layered_basic",
        description="Layered: lockout + IP rate limit + tarpit + PoW",
        category="layered",
        env={
            "ACCOUNT_MAX_FAILURES": "5",
            "ACCOUNT_LOCKOUT_SECONDS": "60",
            "IP_MAX_ATTEMPTS": "15",
            "IP_WINDOW_SECONDS": "30",
            "TARPIT_SECONDS": "0.25",
            "POW_FAILURES_BEFORE_CHALLENGE": "5",
            "POW_DIFFICULTY_BITS": "16",
        },
        solve_pow=True,
    ))
    out.append(Config(
        name="H2_layered_with_ban",
        description="Layered + permanent IP ban + slow hash",
        category="layered",
        env={
            "ACCOUNT_MAX_FAILURES": "5",
            "ACCOUNT_LOCKOUT_SECONDS": "60",
            "IP_MAX_ATTEMPTS": "15",
            "IP_WINDOW_SECONDS": "30",
            "TARPIT_SECONDS": "0.25",
            "POW_FAILURES_BEFORE_CHALLENGE": "5",
            "POW_DIFFICULTY_BITS": "16",
            "PERMA_BAN_THRESHOLD": "10",
            "PASSWORD_HASH_METHOD": "pbkdf2:sha256:600000",
        },
        solve_pow=True,
    ))
    out.append(Config(
        name="H3_full_stack",
        description="Full stack: every mechanism enabled",
        category="layered",
        env={
            "ACCOUNT_MAX_FAILURES": "5",
            "ACCOUNT_LOCKOUT_SECONDS": "60",
            "IP_MAX_ATTEMPTS": "15",
            "IP_WINDOW_SECONDS": "30",
            "TARPIT_SECONDS": "0.25",
            "IP_BACKOFF_BASE_SECONDS": "0.25",
            "IP_BACKOFF_CAP_SECONDS": "4",
            "POW_FAILURES_BEFORE_CHALLENGE": "5",
            "POW_DIFFICULTY_BITS": "16",
            "PERMA_BAN_THRESHOLD": "10",
            "CAPTCHA_FAILURES_BEFORE_CHALLENGE": "3",
            "HONEYPOT_USERNAMES": "admin,root,administrator,sa",
            "ANOMALY_BLOCK_MISSING_HEADERS": "true",
            "ANOMALY_REQUIRED_HEADERS": "User-Agent",
            "PASSWORD_HASH_METHOD": "pbkdf2:sha256:600000",
        },
        solve_pow=True,
        solve_captcha=True,
    ))

    return out


def wait_for_health(base_url: str, timeout: float = 15.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            r = requests.get(f"{base_url}/health", timeout=1)
            if r.ok:
                return True
        except requests.RequestException:
            pass
        time.sleep(0.2)
    return False


def start_server(env: dict[str, str], port: int, log_path: Path) -> subprocess.Popen:
    env = {**env, "PORT": str(port)}
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_handle = log_path.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        [PYTHON, str(REPO_ROOT / "login-lab" / "app.py")],
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        cwd=str(REPO_ROOT),
    )
    return proc


def stop_server(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


def run_attack_subprocess(
    cfg: Config, base_url: str, csv_log: Path, wordlist_path: Path
) -> tuple[int, str]:
    args = [
        PYTHON,
        str(REPO_ROOT / "attack" / "main.py"),
        "--mode", "cli",
        "--base-url", base_url,
        "--username", cfg.attack_username,
        "--password-list", str(wordlist_path),
        "--no-auto-reset-on-block",
        "--csv-log", str(csv_log),
        "--delay", "0",
    ]
    if cfg.solve_pow:
        args.append("--solve-pow")
    if cfg.solve_captcha:
        args.append("--solve-captcha")
    if cfg.no_user_agent:
        args.append("--no-user-agent")
    proc = subprocess.run(args, capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=900)
    return proc.returncode, proc.stdout + "\n" + proc.stderr


def parse_attack_log(csv_log: Path) -> dict:
    counts = {
        "requests_made": 0,
        "invalid_credentials": 0,
        "blocked_423": 0,
        "blocked_429": 0,
        "blocked_403": 0,
        "pow_required": 0,
        "captcha_required": 0,
        "successes": 0,
        "first_success_attempt": None,
    }
    if not csv_log.exists():
        return counts
    with csv_log.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            counts["requests_made"] += 1
            status = int(row["status_code"])
            reason = row["event_reason"]
            if status == 200:
                counts["successes"] += 1
                if counts["first_success_attempt"] is None:
                    counts["first_success_attempt"] = int(row["attempt"])
            elif status == 401:
                counts["invalid_credentials"] += 1
            elif status == 423:
                counts["blocked_423"] += 1
            elif status == 429:
                if reason == "pow_required":
                    counts["pow_required"] += 1
                elif reason == "captcha_required":
                    counts["captcha_required"] += 1
                else:
                    counts["blocked_429"] += 1
            elif status == 403:
                counts["blocked_403"] += 1
    return counts


def build_trial_wordlist(
    source: Path, size: int, seed: int, out_path: Path
) -> tuple[Path, int, int]:
    rng = random.Random(seed)
    with source.open("r", encoding="utf-8", errors="ignore") as f:
        corpus = [w.strip() for w in f if w.strip() and not w.startswith("#")]
    if not corpus:
        raise SystemExit(f"empty corpus: {source}")
    pool = [w for w in corpus if w != PASSWORD_TARGET]
    sample_size = min(size - 1, len(pool))
    sample = rng.sample(pool, sample_size)
    insert_at = rng.randint(0, sample_size)
    sample.insert(insert_at, PASSWORD_TARGET)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="\n") as f:
        for word in sample:
            f.write(word + "\n")
    return out_path, insert_at + 1, len(sample)


def benchmark_one(
    cfg: Config,
    run_dir: Path,
    trials: int,
    source: Path,
    wordlist_size: int,
    base_seed: int,
) -> Result:
    print(f"\n=== {cfg.name}: {cfg.description} ===  ({trials} trial{'s' if trials != 1 else ''})")
    result = Result(
        name=cfg.name,
        description=cfg.description,
        category=cfg.category,
        env=dict(cfg.env),
    )
    cfg_dir = run_dir / cfg.name
    cfg_dir.mkdir(parents=True, exist_ok=True)

    for t in range(trials):
        seed = base_seed * 1000 + t
        wordlist_path = cfg_dir / f"trial_{t:02d}_wordlist.txt"
        wl_path, target_pos, wl_size = build_trial_wordlist(
            source, wordlist_size, seed, wordlist_path
        )
        print(f"  trial {t + 1}/{trials}  seed={seed}  target@{target_pos}/{wl_size}", end="", flush=True)

        env = base_env()
        env.update(cfg.env)
        port = find_free_port()
        base_url = f"http://127.0.0.1:{port}"
        server_log = cfg_dir / f"trial_{t:02d}_server.log"
        attack_log = cfg_dir / f"trial_{t:02d}_attack.csv"

        proc = start_server(env, port, server_log)
        try:
            if not wait_for_health(base_url):
                stop_server(proc)
                result.notes.append(f"trial {t}: server failed health check")
                print("  FAILED HEALTH CHECK")
                continue

            start = time.monotonic()
            rc, _out = run_attack_subprocess(cfg, base_url, attack_log, wl_path)
            elapsed = time.monotonic() - start
        finally:
            stop_server(proc)

        counts = parse_attack_log(attack_log)
        trial = TrialResult(
            seed=seed,
            wordlist_path=str(wl_path.relative_to(REPO_ROOT)),
            target_position=target_pos,
            wordlist_size=wl_size,
            elapsed_seconds=round(elapsed, 2),
            requests_per_second=round(counts["requests_made"] / elapsed, 2) if elapsed > 0 else 0.0,
            **counts,
        )
        result.trials.append(trial)
        if rc != 0:
            result.notes.append(f"trial {t}: attack rc={rc}")
        verdict = "FOUND" if trial.successes else "blocked"
        print(f"  -> {verdict} in {trial.elapsed_seconds:.1f}s ({trial.requests_made} reqs)")

    aggregate(result)
    return result


def aggregate(result: Result) -> None:
    if not result.trials:
        return
    elapsed = [t.elapsed_seconds for t in result.trials]
    rates = [t.requests_per_second for t in result.trials]
    successes = [1 for t in result.trials if t.successes]
    found_positions = [t.first_success_attempt for t in result.trials if t.first_success_attempt]

    result.success_rate = round(len(successes) / len(result.trials), 3)
    result.median_elapsed_seconds = round(statistics.median(elapsed), 2)
    result.median_requests_per_second = round(statistics.median(rates), 2)
    result.min_elapsed_seconds = round(min(elapsed), 2)
    result.max_elapsed_seconds = round(max(elapsed), 2)
    if found_positions:
        result.median_first_success = round(statistics.median(found_positions), 1)


def render_table(results: list[Result]) -> str:
    headers = [
        "config",
        "category",
        "trials",
        "found%",
        "med_pos",
        "med_elapsed",
        "min..max_s",
        "med_req/s",
    ]
    rows = []
    for r in results:
        rows.append([
            r.name,
            r.category,
            f"{len(r.trials)}",
            f"{r.success_rate * 100:.0f}%",
            f"{r.median_first_success:.0f}" if r.median_first_success else "-",
            f"{r.median_elapsed_seconds:.2f}s",
            f"{r.min_elapsed_seconds:.1f}..{r.max_elapsed_seconds:.1f}",
            f"{r.median_requests_per_second:.2f}",
        ])
    if not rows:
        return "(no results)"
    widths = [max(len(h), *(len(row[i]) for row in rows)) for i, h in enumerate(headers)]

    def fmt(row: list[str]) -> str:
        return "  ".join(cell.ljust(w) for cell, w in zip(row, widths))

    lines = [fmt(headers), fmt(["-" * w for w in widths])]
    lines.extend(fmt(row) for row in rows)
    lines.append("")
    lines.append("Descriptions:")
    for r in results:
        note = f" [notes: {', '.join(r.notes)}]" if r.notes else ""
        lines.append(f"  {r.name}: {r.description}{note}")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--trials", type=int, default=1, help="Number of randomized trials per config")
    ap.add_argument(
        "--wordlist-source",
        type=Path,
        default=DEFAULT_WORDLIST_SOURCE,
        help="Source corpus to sample from",
    )
    ap.add_argument(
        "--wordlist-size", type=int, default=100, help="Entries per generated wordlist"
    )
    ap.add_argument(
        "--configs",
        type=str,
        default="",
        help="Comma-separated config names to include (default: all)",
    )
    ap.add_argument("--skip-slow", action="store_true", help="Skip configs marked as slow")
    ap.add_argument("--seed", type=int, default=None, help="Base RNG seed (default: random)")
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    if not args.wordlist_source.exists():
        sys.exit(f"wordlist source missing: {args.wordlist_source}")

    requested = {n.strip() for n in args.configs.split(",") if n.strip()}
    selected: list[Config] = []
    for cfg in configs():
        if requested and cfg.name not in requested:
            continue
        if args.skip_slow and cfg.name in SLOW_CONFIGS:
            continue
        selected.append(cfg)
    if not selected:
        sys.exit("no configs selected")

    base_seed = args.seed if args.seed is not None else random.SystemRandom().randint(1, 1_000_000)

    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = RESULTS_DIR / stamp
    run_dir.mkdir(parents=True, exist_ok=True)

    print(f"Run dir       : {run_dir}")
    print(f"Wordlist src  : {args.wordlist_source}")
    print(f"Trials/config : {args.trials}")
    print(f"Wordlist size : {args.wordlist_size}")
    print(f"Base seed     : {base_seed}")
    print(f"Configs       : {len(selected)}")

    suite_started_at = time.monotonic()
    suite_started_wall = datetime.datetime.now(datetime.timezone.utc).isoformat()
    results: list[Result] = []
    for cfg in selected:
        results.append(
            benchmark_one(cfg, run_dir, args.trials, args.wordlist_source, args.wordlist_size, base_seed)
        )
    suite_total_seconds = round(time.monotonic() - suite_started_at, 2)
    suite_finished_wall = datetime.datetime.now(datetime.timezone.utc).isoformat()

    table = render_table(results)
    total_trials = sum(len(r.trials) for r in results)
    print("\n" + "=" * 80)
    print("BENCHMARK SUMMARY")
    print("=" * 80)
    print(table)
    mins, secs = divmod(int(suite_total_seconds), 60)
    avg_per_trial = suite_total_seconds / total_trials if total_trials else 0.0
    print(
        f"\nTotal suite time: {mins}m {secs}s "
        f"({suite_total_seconds:.1f}s wall-clock, {total_trials} trials, "
        f"avg {avg_per_trial:.1f}s/trial)"
    )

    summary_path = run_dir / "summary.txt"
    summary_path.write_text(table, encoding="utf-8")

    json_path = run_dir / "summary.json"
    json_payload = {
        "timestamp_utc": stamp,
        "wordlist_source": str(args.wordlist_source.relative_to(REPO_ROOT))
        if args.wordlist_source.is_relative_to(REPO_ROOT)
        else str(args.wordlist_source),
        "wordlist_size": args.wordlist_size,
        "trials_per_config": args.trials,
        "base_seed": base_seed,
        "suite_started_utc": suite_started_wall,
        "suite_finished_utc": suite_finished_wall,
        "suite_total_seconds": suite_total_seconds,
        "total_trials": total_trials,
        "results": [dataclasses.asdict(r) for r in results],
    }
    json_path.write_text(json.dumps(json_payload, indent=2), encoding="utf-8")

    print(f"\nResults written to {run_dir}")
    print(f"  summary.txt  : {summary_path}")
    print(f"  summary.json : {json_path}")
    print(f"\nGenerate the chart report with:")
    print(f"  python scripts/render_report.py {json_path}")


if __name__ == "__main__":
    main()
