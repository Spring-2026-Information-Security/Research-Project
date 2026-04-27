"""One-command chart generator for benchmark runs.

Usage:

    python scripts/make_charts.py              # latest run only
    python scripts/make_charts.py --all        # every run that has summary.json
    python scripts/make_charts.py --run 20260427T154434Z   # specific run
    python scripts/make_charts.py --open       # also open the HTML in default browser

Wraps `render_report.py` so you don't have to remember the JSON path.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import webbrowser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = REPO_ROOT / "login-lab" / "logs" / "benchmark"
RENDER = REPO_ROOT / "scripts" / "render_report.py"


def list_runs() -> list[Path]:
    if not RUNS_DIR.exists():
        return []
    return sorted(p for p in RUNS_DIR.iterdir() if p.is_dir() and (p / "summary.json").exists())


def render(run_dir: Path) -> Path:
    summary = run_dir / "summary.json"
    rc = subprocess.run([sys.executable, str(RENDER), str(summary)], cwd=str(REPO_ROOT))
    if rc.returncode != 0:
        sys.exit(f"render_report.py failed for {run_dir}")
    return run_dir / "report.html"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--all", action="store_true", help="Render every run that has summary.json")
    g.add_argument("--run", type=str, default="", help="Render a specific run by timestamp dir name")
    ap.add_argument("--open", dest="open_browser", action="store_true", help="Open report.html in browser when done")
    args = ap.parse_args()

    runs = list_runs()
    if not runs:
        sys.exit(f"no benchmark runs found under {RUNS_DIR}")

    if args.all:
        targets = runs
    elif args.run:
        targets = [r for r in runs if r.name == args.run]
        if not targets:
            sys.exit(f"run not found: {args.run} (have: {[r.name for r in runs]})")
    else:
        targets = [runs[-1]]

    rendered: list[Path] = []
    for run_dir in targets:
        print(f"\n--- rendering {run_dir.name} ---")
        rendered.append(render(run_dir))

    print("\nDone.")
    for p in rendered:
        print(f"  {p}")

    if args.open_browser and rendered:
        webbrowser.open(rendered[-1].as_uri())


if __name__ == "__main__":
    main()
