from __future__ import annotations

from dataclasses import dataclass
import base64
import binascii
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
import secrets
import time
from typing import Any

from app.core.config import AuthSettings


LOGGER = logging.getLogger(__name__)
PASSWORD_ITERATIONS = 390_000
SESSION_COOKIE = "webrobot_session"
SESSION_VERSION = 1


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def build_password_record(password: str) -> dict[str, Any]:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    )
    return {
        "algorithm": "pbkdf2_sha256",
        "iterations": PASSWORD_ITERATIONS,
        "salt": _encode(salt),
        "hash": _encode(digest),
    }


def write_credentials(path: Path, username: str, password: str) -> None:
    """Create credentials and rotate the signing key used by browser sessions."""
    if not 1 <= len(username) <= 64:
        raise ValueError("用户名长度必须为 1 到 64 个字符")
    if len(password) < 10:
        raise ValueError("管理员密码至少需要 10 个字符")

    document = {
        "version": 1,
        "username": username,
        "password": build_password_record(password),
        "session_secret": _encode(secrets.token_bytes(32)),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.chmod(temporary, 0o600)
    temporary.replace(path)
    os.chmod(path, 0o600)


@dataclass(frozen=True)
class SessionIdentity:
    username: str
    expires_at: int


@dataclass
class _FailureState:
    attempts: int
    first_failure: float
    locked_until: float = 0


class AuthenticationLockedError(RuntimeError):
    def __init__(self, retry_after: int) -> None:
        super().__init__("登录尝试过于频繁，请稍后再试")
        self.retry_after = retry_after


class AuthManager:
    def __init__(self, settings: AuthSettings, backend_root: Path) -> None:
        self.settings = settings
        credential_path = Path(settings.credential_file)
        self.credential_path = (
            credential_path
            if credential_path.is_absolute()
            else (backend_root / credential_path).resolve()
        )
        self._credentials: dict[str, Any] = {}
        self._failures: dict[str, _FailureState] = {}

    @property
    def enabled(self) -> bool:
        return self.settings.enabled

    def initialize(self) -> None:
        if not self.enabled:
            LOGGER.warning("Web authentication is disabled by configuration")
            return
        if not self.credential_path.exists():
            username = os.environ.get("WEBROBOT_ADMIN_USERNAME", "admin").strip() or "admin"
            password = os.environ.get("WEBROBOT_ADMIN_PASSWORD", "")
            generated = not password
            if generated:
                password = secrets.token_urlsafe(15)
            write_credentials(self.credential_path, username, password)
            LOGGER.warning("Created the initial WebRobotTools administrator account")
            LOGGER.warning("Initial login username: %s", username)
            if generated:
                LOGGER.warning("Initial login password: %s", password)
                LOGGER.warning(
                    "Save this password now; it will not be printed on later starts"
                )
        self._credentials = self._load_credentials()

    def _load_credentials(self) -> dict[str, Any]:
        try:
            document = json.loads(self.credential_path.read_text(encoding="utf-8"))
            password = document["password"]
            if document.get("version") != 1:
                raise ValueError("unsupported credential version")
            required = (
                document["username"],
                document["session_secret"],
                password["salt"],
                password["hash"],
                password["iterations"],
            )
            if not all(str(value) for value in required):
                raise ValueError("credential fields cannot be empty")
            if password.get("algorithm") != "pbkdf2_sha256":
                raise ValueError("unsupported password algorithm")
            if not 100_000 <= int(password["iterations"]) <= 2_000_000:
                raise ValueError("unsafe password iteration count")
            if len(str(document["username"])) > 64:
                raise ValueError("username too long")
            if len(_decode(str(document["session_secret"]))) != 32:
                raise ValueError("invalid session secret")
            if len(_decode(str(password["salt"]))) != 16:
                raise ValueError("invalid password salt")
            if len(_decode(str(password["hash"]))) != 32:
                raise ValueError("invalid password hash")
            os.chmod(self.credential_path, 0o600)
            return document
        except (
            OSError,
            KeyError,
            TypeError,
            ValueError,
            binascii.Error,
            json.JSONDecodeError,
        ) as exc:
            raise RuntimeError(
                f"认证凭据文件无效：{self.credential_path}。请运行密码重置脚本修复。"
            ) from exc

    def authenticate(self, username: str, password: str, client_id: str) -> bool:
        if not self.enabled:
            return True
        now = time.monotonic()
        failure = self._failures.get(client_id)
        if failure and failure.locked_until > now:
            raise AuthenticationLockedError(max(1, int(failure.locked_until - now)))
        if failure and now - failure.first_failure > self.settings.lockout_seconds:
            self._failures.pop(client_id, None)
            failure = None

        record = self._credentials["password"]
        supplied = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            _decode(str(record["salt"])),
            int(record["iterations"]),
        )
        username_valid = hmac.compare_digest(
            username.encode("utf-8"), str(self._credentials["username"]).encode("utf-8")
        )
        password_valid = hmac.compare_digest(supplied, _decode(str(record["hash"])))
        if username_valid and password_valid:
            self._failures.pop(client_id, None)
            return True

        if failure is None:
            failure = _FailureState(attempts=0, first_failure=now)
            self._failures[client_id] = failure
        failure.attempts += 1
        if failure.attempts >= self.settings.max_attempts:
            failure.locked_until = now + self.settings.lockout_seconds
            raise AuthenticationLockedError(self.settings.lockout_seconds)
        return False

    def issue_session(self, username: str) -> tuple[str, SessionIdentity]:
        now = int(time.time())
        identity = SessionIdentity(
            username=username,
            expires_at=now + self.settings.session_hours * 3600,
        )
        payload = {
            "v": SESSION_VERSION,
            "sub": identity.username,
            "iat": now,
            "exp": identity.expires_at,
            "nonce": secrets.token_hex(8),
        }
        encoded = _encode(
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        )
        signature = hmac.new(
            _decode(str(self._credentials["session_secret"])),
            encoded.encode("ascii"),
            hashlib.sha256,
        ).digest()
        return f"{encoded}.{_encode(signature)}", identity

    def validate_session(self, token: str | None) -> SessionIdentity | None:
        if not self.enabled:
            return SessionIdentity(username="local", expires_at=2**31 - 1)
        if not token:
            return None
        try:
            encoded, supplied_signature = token.split(".", 1)
            expected_signature = hmac.new(
                _decode(str(self._credentials["session_secret"])),
                encoded.encode("ascii"),
                hashlib.sha256,
            ).digest()
            if not hmac.compare_digest(expected_signature, _decode(supplied_signature)):
                return None
            payload = json.loads(_decode(encoded))
            if payload.get("v") != SESSION_VERSION:
                return None
            if not hmac.compare_digest(
                str(payload.get("sub", "")), str(self._credentials["username"])
            ):
                return None
            expires_at = int(payload["exp"])
            if expires_at <= int(time.time()):
                return None
            return SessionIdentity(username=str(payload["sub"]), expires_at=expires_at)
        except (
            ValueError,
            TypeError,
            KeyError,
            binascii.Error,
            json.JSONDecodeError,
        ):
            return None
