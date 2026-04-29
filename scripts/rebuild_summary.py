"""Reconstruct summary.json / summary.txt for a benchmark run dir from its
per-trial CSVs (used when the orchestrator timed out before writing them).

Walks every config subdir in the given run dir, parses each `trial_NN_attack.csv`
plus the matching `trial_NN_wordlist.txt`, and rebuilds a payload that looks
the same to render_report.py as a freshly-finished run.

Usage:

    python scripts/rebuild_summary.py login-lab/logs/benchmark/<stamp>/

Notes:
* `base_seed` and per-trial `seed` are not recoverable from the on-disk
  artifacts, so they're emitted as -1 placeholders.
* `elapsed_seconds` is recomputed as (last CSV row timestamp - first), which
  matches the inner attack loop's wall-clock to within sub-second noise.
* Configs without a directory or without any complete CSV are simply omitted
  from the rebuilt payload.
"""

from __future__ import annotations

import csv
import dataclasses
import datetime
import json
import statistics
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TARGET_PASSWORD = "password123"

sys.path.insert(0, str(REPO_ROOT / "scripts"))
import benchmark_defenses  # noqa: E402 - sibling script, not a package


def parse_attack_csv(csv_path: Path) -> dict | None:
    """Return per-trial counts plus first/last timestamps; None if unreadable."""
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
        "first_ts": None,
        "last_ts": None,
    }
    if not csv_path.exists():
        return None
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            counts["requests_made"] += 1
            ts = row.get("timestamp_utc", "")
            if ts:
                try:
                    parsed = datetime.datetime.fromisoformat(ts)
                except ValueError:
                    parsed = None
                if parsed is not None:
                    if counts["first_ts"] is None:
                        counts["first_ts"] = parsed
                    counts["last_ts"] = parsed
            try:
                status = int(row["status_code"])
            except (KeyError, ValueError):
                continue
            reason = row.get("event_reason", "")
            if status == 200:
                counts["successes"] += 1
                if counts["first_success_attempt"] is None:
                    try:
                        counts["first_success_attempt"] = int(row["attempt"])
                    except (KeyError, ValueError):
                        counts["first_success_attempt"] = counts["requests_made"]
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


def find_target_position(wordlist_path: Path) -> tuple[int, int]:
    """Return (1-indexed target position, total list size). 0 if not found."""
    if not wordlist_path.exists():
        return (0, 0)
    pos = 0
    size = 0
    for i, line in enumerate(wordlist_path.read_text(encoding="utf-8").splitlines(), start=1):
        size += 1
        if line.strip() == TARGET_PASSWORD and pos == 0:
            pos = i
    return (pos, size)


def trial_files(cfg_dir: Path) -> list[tuple[int, Path, Path]]:
    pairs: list[tuple[int, Path, Path]] = []
    for csv_path in sorted(cfg_dir.glob("trial_*_attack.csv")):
        idx_str = csv_path.stem.split("_")[1]
        try:
            idx = int(idx_str)
        except ValueError:
            continue
        wl = cfg_dir / f"trial_{idx:02d}_wordlist.txt"
        pairs.append((idx, csv_path, wl))
    return pairs


def build_result_for_config(
    cfg: benchmark_defenses.Config,
    cfg_dir: Path,
) -> benchmark_defenses.Result | None:
    if not cfg_dir.exists():
        return None
    pairs = trial_files(cfg_dir)
    if not pairs:
        return None

    result = benchmark_defenses.Result(
        name=cfg.name,
        description=cfg.description,
        category=cfg.category,
        env=dict(cfg.env),
    )
    result.notes.append("reconstructed from per-trial CSVs (no live wall-clock)")

    for idx, csv_path, wl_path in pairs:
        counts = parse_attack_csv(csv_path)
        if counts is None or counts["requests_made"] == 0:
            continue
        target_pos, wl_size = find_target_position(wl_path)
        first_ts = counts.pop("first_ts", None)
        last_ts = counts.pop("last_ts", None)
        if first_ts is not None and last_ts is not None and last_ts > first_ts:
            elapsed = (last_ts - first_ts).total_seconds()
        else:
            elapsed = 0.0
        rps = (counts["requests_made"] / elapsed) if elapsed > 0 else 0.0
        trial = benchmark_defenses.TrialResult(
            seed=-1,
            wordlist_path=str(wl_path.relative_to(REPO_ROOT)) if wl_path.exists() else "",
            target_position=target_pos,
            wordlist_size=wl_size,
            requests_made=counts["requests_made"],
            invalid_credentials=counts["invalid_credentials"],
            blocked_423=counts["blocked_423"],
            blocked_429=counts["blocked_429"],
            blocked_403=counts["blocked_403"],
            pow_required=counts["pow_required"],
            captcha_required=counts["captcha_required"],
            successes=counts["successes"],
            first_success_attempt=counts["first_success_attempt"],
            elapsed_seconds=round(elapsed, 2),
            requests_per_second=round(rps, 2),
        )
        result.trials.append(trial)

    if not result.trials:
        return None
    benchmark_defenses.aggregate(result)
    return result


def detect_wordlist_size(run_dir: Path) -> int:
    """Look at the first wordlist we can find and count its lines."""
    for wl in run_dir.glob("*/trial_*_wordlist.txt"):
        try:
            return sum(1 for _ in wl.open("r", encoding="utf-8"))
        except OSError:
            continue
    return 0


def rebuild(run_dir: Path) -> None:
    if not run_dir.exists():
        sys.exit(f"run dir not found: {run_dir}")
    cfgs = benchmark_defenses.configs()

    results: list[benchmark_defenses.Result] = []
    for cfg in cfgs:
        cfg_dir = run_dir / cfg.name
        r = build_result_for_config(cfg, cfg_dir)
        if r is not None:
            results.append(r)

    if not results:
        sys.exit(f"no usable per-trial CSVs found under {run_dir}")

    table = benchmark_defenses.render_table(results)
    total_trials = sum(len(r.trials) for r in results)
    suite_total_seconds = sum(t.elapsed_seconds for r in results for t in r.trials)
    wordlist_size = detect_wordlist_size(run_dir)
    trials_per_config = max((len(r.trials) for r in results), default=0)

    summary_path = run_dir / "summary.txt"
    summary_path.write_text(table, encoding="utf-8")

    payload = {
        "timestamp_utc": run_dir.name,
        "wordlist_source": "passwords/raw/SecLists/Common-Credentials/10k-most-common.txt",
        "wordlist_size": wordlist_size,
        "trials_per_config": trials_per_config,
        "base_seed": -1,
        "suite_started_utc": None,
        "suite_finished_utc": None,
        "suite_total_seconds": round(suite_total_seconds, 2),
        "total_trials": total_trials,
        "reconstructed": True,
        "results": [dataclasses.asdict(r) for r in results],
    }
    json_path = run_dir / "summary.json"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"rebuilt {run_dir}:")
    print(f"  {summary_path}")
    print(f"  {json_path}  ({total_trials} trials, {len(results)} configs, wordlist={wordlist_size})")


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: python scripts/rebuild_summary.py <run_dir>")
    rebuild(Path(sys.argv[1]).resolve())


if __name__ == "__main__":
    main()
