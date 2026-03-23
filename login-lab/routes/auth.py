import os
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from flask import Blueprint, jsonify, render_template, request
from werkzeug.security import check_password_hash, generate_password_hash


@dataclass
class LoginPolicy:
    account_max_failures: int
    account_lockout_seconds: int
    ip_max_attempts: int
    ip_window_seconds: int


class LoginGuard:
    def __init__(self, policy: LoginPolicy) -> None:
        self.policy = policy
        self.failed_attempts_by_user = defaultdict(int)
        self.locked_until_by_user = {}
        self.attempt_timestamps_by_ip = defaultdict(deque)

    def _now(self) -> float:
        return time.time()

    def _clean_old_ip_attempts(self, client_ip: str) -> None:
        now = self._now()
        cutoff = now - self.policy.ip_window_seconds
        attempts = self.attempt_timestamps_by_ip[client_ip]
        while attempts and attempts[0] < cutoff:
            attempts.popleft()

    def check_ip_rate_limit(self, client_ip: str) -> tuple[bool, int]:
        self._clean_old_ip_attempts(client_ip)
        attempt_count = len(self.attempt_timestamps_by_ip[client_ip])
        remaining = max(self.policy.ip_max_attempts - attempt_count, 0)
        return attempt_count < self.policy.ip_max_attempts, remaining

    def record_ip_attempt(self, client_ip: str) -> None:
        self.attempt_timestamps_by_ip[client_ip].append(self._now())

    def is_user_locked(self, username: str) -> tuple[bool, int]:
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
        self.failed_attempts_by_user[username] += 1
        remaining_before_lock = self.policy.account_max_failures - self.failed_attempts_by_user[username]
        if self.failed_attempts_by_user[username] >= self.policy.account_max_failures:
            self.locked_until_by_user[username] = self._now() + self.policy.account_lockout_seconds
            return True, 0
        return False, max(remaining_before_lock, 0)

    def record_successful_login(self, username: str) -> None:
        self.failed_attempts_by_user[username] = 0
        self.locked_until_by_user.pop(username, None)

    def reset_all(self) -> None:
        self.failed_attempts_by_user.clear()
        self.locked_until_by_user.clear()
        self.attempt_timestamps_by_ip.clear()


class UserStore:
    def __init__(self, username: str, password_plaintext: str) -> None:
        self.username = username
        self.password_hash = generate_password_hash(password_plaintext)

    def verify(self, username: str, password: str) -> bool:
        if username != self.username:
            return False
        return check_password_hash(self.password_hash, password)


policy = LoginPolicy(
    account_max_failures=int(os.getenv("ACCOUNT_MAX_FAILURES", "5")),
    account_lockout_seconds=int(os.getenv("ACCOUNT_LOCKOUT_SECONDS", "300")),
    ip_max_attempts=int(os.getenv("IP_MAX_ATTEMPTS", "20")),
    ip_window_seconds=int(os.getenv("IP_WINDOW_SECONDS", "60")),
)

user_store = UserStore(
    username=os.getenv("LAB_USERNAME", "test_user"),
    password_plaintext=os.getenv("LAB_PASSWORD", "correct horse battery staple"),
)

guard = LoginGuard(policy)
auth_bp = Blueprint("auth", __name__)


@auth_bp.get("/")
def index():
    return render_template("login.html", policy=policy, username=user_store.username)


@auth_bp.post("/login")
def login():
    payload = request.get_json(silent=True) or request.form
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    client_ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()

    ip_allowed, ip_remaining = guard.check_ip_rate_limit(client_ip)
    if not ip_allowed:
        return jsonify(
            {
                "ok": False,
                "reason": "ip_rate_limited",
                "message": "Too many attempts from this IP.",
                "ip_attempts_remaining": ip_remaining,
            }
        ), 429

    guard.record_ip_attempt(client_ip)

    locked, retry_after = guard.is_user_locked(username)
    if locked:
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
        }
    ), 401


@auth_bp.post("/reset")
def reset():
    guard.reset_all()
    return jsonify({"ok": True, "message": "State reset."})


@auth_bp.get("/health")
def health():
    return jsonify({"ok": True})
