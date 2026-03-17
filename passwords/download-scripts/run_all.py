#!/usr/bin/env python3
"""Run multiple Python scripts in parallel with easy extensibility.

Usage examples:
  python scripts/run_all.py                # runs scripts/download_*.py
  python scripts/run_all.py scripts/a.py   # run specific scripts
  python scripts/run_all.py --pattern "*_task.py" --max-workers 4
  python scripts/run_all.py --config run_list.txt

The script finds target Python files, launches each with the current Python
interpreter in a separate process, and shows a concise summary on completion.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import glob
import os
import subprocess
import sys
import time
from typing import List, Tuple


def discover_targets(positional: List[str], pattern: str, directory: str, config: str) -> List[str]:
    if positional:
        return [os.path.abspath(p) for p in positional]
    if config:
        cfg = os.path.abspath(config)
        if not os.path.exists(cfg):
            raise SystemExit(f"Config file not found: {cfg}")
        with open(cfg, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip() and not l.strip().startswith('#')]
        return [os.path.abspath(l) for l in lines]
    search = os.path.join(directory, pattern)
    return [os.path.abspath(p) for p in sorted(glob.glob(search))]


def run_script(path: str, timeout: float | None = None) -> Tuple[str, int, str, str]:
    cmd = [sys.executable, path]
    start = time.time()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        duration = time.time() - start
        return path, proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as e:
        duration = time.time() - start
        return path, -1, e.stdout or "", (e.stderr or f"Timed out after {timeout}s")
    except Exception as e:
        return path, -1, "", str(e)


def main(argv: List[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Run multiple Python scripts in parallel")
    p.add_argument("scripts", nargs="*", help="Specific script files to run (overrides discovery)")
    p.add_argument("--pattern", default="download_*.py", help="Glob pattern for discovery (default: download_*.py)")
    p.add_argument("--directory", default=os.path.join(os.path.dirname(__file__)), help="Directory to search for scripts")
    p.add_argument("--config", help="Path to a newline-separated file listing scripts to run")
    p.add_argument("--max-workers", type=int, default=4, help="Max parallel workers (default: 4)")
    p.add_argument("--timeout", type=float, default=None, help="Per-script timeout in seconds")
    p.add_argument("--quiet", action="store_true", help="Minimize per-script output; only show summary")
    args = p.parse_args(argv)

    targets = discover_targets(args.scripts, args.pattern, args.directory, args.config)
    if not targets:
        print("No target scripts found. Try passing filenames or use --pattern/--config.")
        return 2

    print(f"Running {len(targets)} script(s) with up to {args.max_workers} workers...")

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.max_workers) as ex:
        futures = {ex.submit(run_script, t, args.timeout): t for t in targets}
        for fut in concurrent.futures.as_completed(futures):
            path, code, out, err = fut.result()
            results.append((path, code, out, err))
            if not args.quiet:
                sep = "=" * 8
                print(f"\n{sep} {os.path.basename(path)} (exit {code}) {sep}")
                if out:
                    print(out.rstrip())
                if err:
                    print("-- stderr --")
                    print(err.rstrip())

    # summary
    print("\nSummary:")
    success = 0
    for path, code, _, _ in results:
        status = "OK" if code == 0 else "FAIL"
        print(f"- {os.path.basename(path)}: {status} (exit {code})")
        if code == 0:
            success += 1

    print(f"{success}/{len(results)} succeeded")
    return 0 if success == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
