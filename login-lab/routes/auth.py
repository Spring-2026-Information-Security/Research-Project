import hashlib
import os
import secrets
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field

from flask import Blueprint, jsonify, render_template, request
from werkzeug.security import check_password_hash, generate_password_hash


@dataclass
class LoginPolicy:
    account_max_failures: int
    account_lockout_seconds: int
    ip_max_attempts: int
    ip_window_seconds: int
    tarpit_seconds: float
    ip_backoff_base_seconds: float
    ip_backoff_cap_seconds: float
    pow_failures_before_challenge: int
    pow_difficulty_bits: int
    perma_ban_threshold: int
    perma_ban_window_seconds: int
    captcha_failures_before_challenge: int
    honeypot_usernames: list[str] = field(default_factory=list)
    anomaly_block_missing_headers: bool = False
    anomaly_required_headers: list[str] = field(default_factory=list)
    password_hash_method: str = ""


class LoginGuard:
    def __init__(self, policy: LoginPolicy) -> None:
        self.policy = policy
        self.failed_attempts_by_user = defaultdict(int)
        self.locked_until_by_user = {}
        self.attempt_timestamps_by_ip = defaultdict(deque)
        self.failed_attempts_by_ip = defaultdict(int)
        self.ip_backoff_until = {}
        self.pow_challenges = {}
        self.permanent_bans = set()
        self.failure_history_by_ip = defaultdict(deque)
        self.captcha_pending = set()

    def _now(self) -> float:
        return time.time()

    def _clean_old_ip_attempts(self, client_ip: str) -> None:
        now = self._now()
        cutoff = now - self.policy.ip_window_seconds
        attempts = self.attempt_timestamps_by_ip[client_ip]
        while attempts and attempts[0] < cutoff:
            attempts.popleft()

    def check_ip_rate_limit(self, client_ip: str) -> tuple[bool, int]:
        if self.policy.ip_max_attempts <= 0 or self.policy.ip_window_seconds <= 0:
            return True, 0

        self._clean_old_ip_attempts(client_ip)
        attempt_count = len(self.attempt_timestamps_by_ip[client_ip])
        remaining = max(self.policy.ip_max_attempts - attempt_count, 0)
        return attempt_count < self.policy.ip_max_attempts, remaining

    def record_ip_attempt(self, client_ip: str) -> None:
        self.attempt_timestamps_by_ip[client_ip].append(self._now())

    def is_user_locked(self, username: str) -> tuple[bool, int]:
        if self.policy.account_max_failures <= 0 or self.policy.account_lockout_seconds <= 0:
            return False, 0

        now = self._now()
        locked_until = self.locked_until_by_user.get(username)
        if locked_until is None:
            return False, 0
        if locked_until <= now:
            del self.locked_until_by_user[username]
            self.failed_attempts_by_user[username] = 0
            return False, 0
        return True, int(locked_until - now)

    def record_failed_login(self, username: str) -> tuple[bool, int]:
        if self.policy.account_max_failures <= 0 or self.policy.account_lockout_seconds <= 0:
            return False, 0

        self.failed_attempts_by_user[username] += 1
        remaining_before_lock = self.policy.account_max_failures - self.failed_attempts_by_user[username]
        if self.failed_attempts_by_user[username] >= self.policy.account_max_failures:
            self.locked_until_by_user[username] = self._now() + self.policy.account_lockout_seconds
            return True, 0
        return False, max(remaining_before_lock, 0)

    def record_successful_login(self, username: str) -> None:
        self.failed_attempts_by_user[username] = 0
        self.locked_until_by_user.pop(username, None)

    def is_ip_in_backoff(self, client_ip: str) -> tuple[bool, float]:
        if self.policy.ip_backoff_base_seconds <= 0:
            return False, 0.0
        until = self.ip_backoff_until.get(client_ip)
        if until is None:
            return False, 0.0
        now = self._now()
        if until <= now:
            del self.ip_backoff_until[client_ip]
            return False, 0.0
        return True, until - now

    def record_ip_failure(self, client_ip: str) -> float:
        self.failed_attempts_by_ip[client_ip] += 1
        history = self.failure_history_by_ip[client_ip]
        history.append(self._now())
        if self.policy.perma_ban_window_seconds > 0:
            cutoff = self._now() - self.policy.perma_ban_window_seconds
            while history and history[0] < cutoff:
                history.popleft()
        if (
            self.policy.perma_ban_threshold > 0
            and len(history) >= self.policy.perma_ban_threshold
        ):
            self.permanent_bans.add(client_ip)
        if self.policy.ip_backoff_base_seconds <= 0:
            return 0.0
        n = self.failed_attempts_by_ip[client_ip]
        delay = self.policy.ip_backoff_base_seconds * (2 ** (n - 1))
        if self.policy.ip_backoff_cap_seconds > 0:
            delay = min(delay, self.policy.ip_backoff_cap_seconds)
        self.ip_backoff_until[client_ip] = self._now() + delay
        return delay

    def is_permanently_banned(self, client_ip: str) -> bool:
        return client_ip in self.permanent_bans

    def ban_ip(self, client_ip: str) -> None:
        self.permanent_bans.add(client_ip)

    def needs_pow(self, client_ip: str) -> bool:
        if self.policy.pow_failures_before_challenge <= 0 or self.policy.pow_difficulty_bits <= 0:
            return False
        return self.failed_attempts_by_ip[client_ip] >= self.policy.pow_failures_before_challenge

    def issue_pow_challenge(self, client_ip: str) -> dict:
        nonce = secrets.token_hex(8)
        self.pow_challenges[client_ip] = nonce
        return {
            "nonce": nonce,
            "difficulty_bits": self.policy.pow_difficulty_bits,
            "algorithm": "sha256",
            "instruction": "Find solution s such that sha256(nonce + ':' + s) starts with N zero bits.",
        }

    def verify_pow(self, client_ip: str, solution: str) -> bool:
        nonce = self.pow_challenges.get(client_ip)
        if not nonce or not solution:
            return False
        digest = hashlib.sha256(f"{nonce}:{solution}".encode("utf-8")).digest()
        bits = self.policy.pow_difficulty_bits
        full_bytes, remainder_bits = divmod(bits, 8)
        if any(b != 0 for b in digest[:full_bytes]):
            return False
        if remainder_bits and (digest[full_bytes] >> (8 - remainder_bits)) != 0:
            return False
        del self.pow_challenges[client_ip]
        self.failed_attempts_by_ip[client_ip] = 0
        self.ip_backoff_until.pop(client_ip, None)
        return True

    def needs_captcha(self, client_ip: str) -> bool:
        if self.policy.captcha_failures_before_challenge <= 0:
            return False
        return self.failed_attempts_by_ip[client_ip] >= self.policy.captcha_failures_before_challenge

    def issue_captcha(self, client_ip: str) -> dict:
        token = secrets.token_hex(8)
        self.captcha_pending.add(client_ip)
        return {
            "token": token,
            "image_url": f"/captcha_image/{token}",
            "instruction": "Submit the visible characters as captcha_solution.",
        }

    def verify_captcha(self, client_ip: str, solution: str) -> bool:
        if client_ip not in self.captcha_pending:
            return False
        # Treat the magic token "__human__" as a successful CAPTCHA solve. A
        # real deployment would compare against a server-issued image/audio
        # answer; here we only need to demonstrate the gate.
        if solution == "__human__":
            self.captcha_pending.discard(client_ip)
            self.failed_attempts_by_ip[client_ip] = 0
            return True
        return False

    def is_honeypot_username(self, username: str) -> bool:
        if not self.policy.honeypot_usernames:
            return False
        return username.lower() in {u.lower() for u in self.policy.honeypot_usernames}

    def is_anomalous_request(self, headers) -> tuple[bool, str]:
        if not self.policy.anomaly_block_missing_headers:
            return False, ""
        required = self.policy.anomaly_required_headers or ["User-Agent", "Accept"]
        for header in required:
            if not headers.get(header):
                return True, f"missing header: {header}"
        return False, ""

    def reset_all(self) -> None:
        self.failed_attempts_by_user.clear()
        self.locked_until_by_user.clear()
        self.attempt_timestamps_by_ip.clear()
        self.failed_attempts_by_ip.clear()
        self.ip_backoff_until.clear()
        self.pow_challenges.clear()
        self.permanent_bans.clear()
        self.failure_history_by_ip.clear()
        self.captcha_pending.clear()


class UserStore:
    def __init__(self, username: str, password_plaintext: str, hash_method: str = "") -> None:
        self.username = username
        if hash_method:
            self.password_hash = generate_password_hash(password_plaintext, method=hash_method)
        else:
            self.password_hash = generate_password_hash(password_plaintext)

    def verify(self, username: str, password: str) -> bool:
        if username != self.username:
            return False
        return check_password_hash(self.password_hash, password)


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _env_list(name: str) -> list[str]:
    value = os.getenv(name, "")
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


policy = LoginPolicy(
    account_max_failures=int(os.getenv("ACCOUNT_MAX_FAILURES", "5")),
    account_lockout_seconds=int(os.getenv("ACCOUNT_LOCKOUT_SECONDS", "300")),
    ip_max_attempts=int(os.getenv("IP_MAX_ATTEMPTS", "20")),
    ip_window_seconds=int(os.getenv("IP_WINDOW_SECONDS", "60")),
    tarpit_seconds=_env_float("TARPIT_SECONDS", 0.0),
    ip_backoff_base_seconds=_env_float("IP_BACKOFF_BASE_SECONDS", 0.0),
    ip_backoff_cap_seconds=_env_float("IP_BACKOFF_CAP_SECONDS", 30.0),
    pow_failures_before_challenge=int(os.getenv("POW_FAILURES_BEFORE_CHALLENGE", "0")),
    pow_difficulty_bits=int(os.getenv("POW_DIFFICULTY_BITS", "0")),
    perma_ban_threshold=int(os.getenv("PERMA_BAN_THRESHOLD", "0")),
    perma_ban_window_seconds=int(os.getenv("PERMA_BAN_WINDOW_SECONDS", "3600")),
    captcha_failures_before_challenge=int(os.getenv("CAPTCHA_FAILURES_BEFORE_CHALLENGE", "0")),
    honeypot_usernames=_env_list("HONEYPOT_USERNAMES"),
    anomaly_block_missing_headers=_env_bool("ANOMALY_BLOCK_MISSING_HEADERS", False),
    anomaly_required_headers=_env_list("ANOMALY_REQUIRED_HEADERS"),
    password_hash_method=os.getenv("PASSWORD_HASH_METHOD", ""),
)

user_store = UserStore(
    username=os.getenv("LAB_USERNAME", "test_user"),
    password_plaintext=os.getenv("LAB_PASSWORD", "correct horse battery staple"),
    hash_method=policy.password_hash_method,
)

guard = LoginGuard(policy)
auth_bp = Blueprint("auth", __name__)


@auth_bp.get("/")
def index():
    return render_template("login.html", policy=policy, username=user_store.username)


@auth_bp.get("/pow_challenge")
def pow_challenge():
    client_ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()
    return jsonify({"ok": True, "challenge": guard.issue_pow_challenge(client_ip)})


@auth_bp.post("/login")
def login():
    payload = request.get_json(silent=True) or request.form
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    pow_solution = payload.get("pow_solution") or ""
    captcha_solution = payload.get("captcha_solution") or ""
    client_ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()

    if guard.is_permanently_banned(client_ip):
        if policy.tarpit_seconds > 0:
            time.sleep(policy.tarpit_seconds)
        return jsonify(
            {
                "ok": False,
                "reason": "ip_perma_banned",
                "message": "Source address is permanently banned.",
            }
        ), 403

    is_anomaly, reason = guard.is_anomalous_request(request.headers)
    if is_anomaly:
        guard.ban_ip(client_ip)
        if policy.tarpit_seconds > 0:
            time.sleep(policy.tarpit_seconds)
        return jsonify(
            {
                "ok": False,
                "reason": "anomaly_detected",
                "message": f"Anomalous request blocked ({reason}).",
            }
        ), 403

    if guard.is_honeypot_username(username):
        guard.ban_ip(client_ip)
        if policy.tarpit_seconds > 0:
            time.sleep(policy.tarpit_seconds)
        return jsonify(
            {
                "ok": False,
                "reason": "honeypot_triggered",
                "message": "Source address banned for hitting honeypot account.",
            }
        ), 403

    ip_allowed, ip_remaining = guard.check_ip_rate_limit(client_ip)
    if not ip_allowed:
        if policy.tarpit_seconds > 0:
            time.sleep(policy.tarpit_seconds)
        return jsonify(
            {
                "ok": False,
                "reason": "ip_rate_limited",
                "message": "Too many attempts from this IP.",
                "ip_attempts_remaining": ip_remaining,
            }
        ), 429

    in_backoff, retry_after = guard.is_ip_in_backoff(client_ip)
    if in_backoff:
        if policy.tarpit_seconds > 0:
            time.sleep(policy.tarpit_seconds)
        return jsonify(
            {
                "ok": False,
                "reason": "ip_backoff",
                "message": "IP is in exponential backoff.",
                "retry_after_seconds": round(retry_after, 3),
            }
        ), 429

    if guard.needs_captcha(client_ip):
        if not guard.verify_captcha(client_ip, captcha_solution):
            challenge = guard.issue_captcha(client_ip)
            return jsonify(
                {
                    "ok": False,
                    "reason": "captcha_required",
                    "message": "CAPTCHA required.",
                    "challenge": challenge,
                }
            ), 429

    if guard.needs_pow(client_ip):
        if not guard.verify_pow(client_ip, pow_solution):
            challenge = guard.issue_pow_challenge(client_ip)
            return jsonify(
                {
                    "ok": False,
                    "reason": "pow_required",
                    "message": "Proof-of-work challenge required.",
                    "challenge": challenge,
                }
            ), 429

    guard.record_ip_attempt(client_ip)

    locked, retry_after = guard.is_user_locked(username)
    if locked:
        if policy.tarpit_seconds > 0:
            time.sleep(policy.tarpit_seconds)
        return jsonify(
            {
                "ok": False,
                "reason": "account_locked",
                "message": "Account is locked.",
                "retry_after_seconds": retry_after,
            }
        ), 423

    if user_store.verify(username, password):
        guard.record_successful_login(username)
        return jsonify({"ok": True, "message": "Login successful."})

    now_locked, account_remaining = guard.record_failed_login(username)
    backoff_delay = guard.record_ip_failure(client_ip)

    if policy.tarpit_seconds > 0:
        time.sleep(policy.tarpit_seconds)

    if now_locked:
        return jsonify(
            {
                "ok": False,
                "reason": "account_locked",
                "message": "Account locked due to repeated failures.",
                "retry_after_seconds": policy.account_lockout_seconds,
                "account_attempts_remaining": 0,
            }
        ), 423

    return jsonify(
        {
            "ok": False,
            "reason": "invalid_credentials",
            "message": "Invalid username or password.",
            "account_attempts_remaining": account_remaining,
            "ip_backoff_seconds": round(backoff_delay, 3) if backoff_delay > 0 else 0,
        }
    ), 401


@auth_bp.post("/reset")
def reset():
    guard.reset_all()
    return jsonify({"ok": True, "message": "State reset."})


@auth_bp.get("/health")
def health():
    return jsonify({"ok": True})
