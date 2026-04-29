"""Cross-run scaling chart: how does each defense scale with wordlist size?

Reads summary.json from each of the four 50-trial runs (100 / 200 / 300 / 500
wordlist) and plots median elapsed seconds vs wordlist size for a curated set
of configs. Output PNG is written to the chosen run's directory so the slide
deck can pick it up alongside the other charts.

Usage:

    python scripts/chart_wordlist_scaling.py
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
BENCH_DIR = REPO_ROOT / "login-lab" / "logs" / "benchmark"

# (label, stamp, wordlist_size) — ordered low to high.
RUNS = [
    ("100-word",  "20260428T164449Z", 100),
    ("200-word",  "20260428T164727Z", 200),
    ("300-word",  "20260428T164742Z", 300),
    ("500-word",  "20260428T164809Z", 500),
]

# Curated configs to plot — one per family that tells the scaling story.
TIME_CONFIGS = [
    ("A_baseline",          "#888888", "-"),
    ("D_tarpit_500ms",      "#a657d8", "-"),
    ("D2_tarpit_1s",        "#7d2db8", "-"),
    ("D3_tarpit_2s",        "#4f1e7a", "-"),
    ("K_slow_hash_pbkdf2",  "#3d7bd8", "-"),
    ("K2_slow_hash_scrypt", "#5fa5e8", "--"),
    ("F_pow_smart_attacker", "#2d8f5a", "-"),
]

BREACH_CONFIGS = [
    ("B_account_lockout",   "#d33636", "-"),
    ("G_pow_naive_attacker", "#e8a13a", "-"),
    ("J_captcha_naive",     "#c87a00", "--"),
    ("I_perma_ban",         "#7b2eb8", "-"),
    ("C_ip_rate_limit",     "#3d7bd8", "-"),
]


def load_run(stamp: str) -> dict:
    return json.loads((BENCH_DIR / stamp / "summary.json").read_text(encoding="utf-8"))


def find_config(payload: dict, name: str) -> dict | None:
    for r in payload["results"]:
        if r["name"] == name:
            return r
    return None


def chart_elapsed_scaling(out_path: Path) -> None:
    runs = [(label, load_run(stamp), wl) for label, stamp, wl in RUNS]
    fig, ax = plt.subplots(figsize=(11, 6))
    for cfg_name, color, style in TIME_CONFIGS:
        xs, ys = [], []
        for _, payload, wl in runs:
            r = find_config(payload, cfg_name)
            if r is None or not r["trials"]:
                continue
            xs.append(wl)
            ys.append(r["median_elapsed_seconds"])
        if not xs:
            continue
        ax.plot(xs, ys, marker="o", color=color, linestyle=style, linewidth=2,
                markersize=7, label=cfg_name)
    ax.set_xlabel("wordlist size (entries)")
    ax.set_ylabel("median elapsed seconds (50 trials per point)")
    ax.set_title("Time-to-exhaust scales linearly with wordlist depth\n"
                 "(slope = per-attempt cost imposed by the defense)")
    ax.set_xticks([100, 200, 300, 500])
    ax.grid(True, linestyle="--", alpha=0.4)
    ax.legend(loc="upper left", fontsize=10, framealpha=0.95)
    fig.tight_layout()
    fig.savefig(out_path, dpi=130)
    plt.close(fig)


def chart_breach_scaling(out_path: Path) -> None:
    runs = [(label, load_run(stamp), wl) for label, stamp, wl in RUNS]
    fig, ax = plt.subplots(figsize=(11, 5.5))
    for cfg_name, color, style in BREACH_CONFIGS:
        xs, ys = [], []
        for _, payload, wl in runs:
            r = find_config(payload, cfg_name)
            if r is None or not r["trials"]:
                continue
            xs.append(wl)
            ys.append(r["success_rate"] * 100)
        if not xs:
            continue
        ax.plot(xs, ys, marker="o", color=color, linestyle=style, linewidth=2,
                markersize=8, label=cfg_name)

    # 5/N expectation curve as a reference: P(target in first 5 entries) = 5/N.
    ref_x = [100, 200, 300, 500]
    ref_y = [5.0 / x * 100 for x in ref_x]
    ax.plot(ref_x, ref_y, color="#bbbbbb", linestyle=":", linewidth=2,
            label="5 / N reference (P[target in first 5 attempts])")

    ax.set_xlabel("wordlist size (entries)")
    ax.set_ylabel("breach rate (% of 50 trials)")
    ax.set_title("Defenses gated on N=5 failures: breach rate decays as wordlist grows\n"
                 "(only breach when the password lands before the defense fires)")
    ax.set_xticks([100, 200, 300, 500])
    ax.set_ylim(-0.5, 7.0)
    ax.grid(True, linestyle="--", alpha=0.4)
    ax.legend(loc="upper right", fontsize=10, framealpha=0.95)
    fig.tight_layout()
    fig.savefig(out_path, dpi=130)
    plt.close(fig)


def main() -> None:
    target_dir = BENCH_DIR / RUNS[0][1]
    elapsed_out = target_dir / "chart_wordlist_scaling.png"
    breach_out = target_dir / "chart_breach_scaling.png"
    chart_elapsed_scaling(elapsed_out)
    chart_breach_scaling(breach_out)
    print(f"wrote {elapsed_out}")
    print(f"wrote {breach_out}")


if __name__ == "__main__":
    main()
