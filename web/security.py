"""Пароль, сессионная кука и лимит попыток входа для веб-версии.

Только стандартная библиотека: scrypt из hashlib и собственный HMAC-подписанный
токен вместо argon2/itsdangerous. Лишняя зависимость в маленьком контейнере —
лишний риск при сборке, а криптопримитивы здесь штатные.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

COOKIE_NAME = "expense_session"
SESSION_TTL = 30 * 24 * 3600          # 30 дней
LOGIN_MAX_FAILS = 5                   # попыток на IP
LOGIN_WINDOW = 15 * 60                # окно, секунд

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P, _DK = 2 ** 14, 8, 1, 32


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_DK)
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${_b64(salt)}${_b64(dk)}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        dk = hashlib.scrypt(
            password.encode(), salt=_unb64(salt), n=int(n), r=int(r), p=int(p), dklen=len(_unb64(digest))
        )
        return hmac.compare_digest(dk, _unb64(digest))
    except (ValueError, TypeError):
        return False


def password_fingerprint(stored: str | None) -> str:
    """Отпечаток хеша: смена пароля делает старые куки недействительными."""
    return hashlib.sha256((stored or "").encode()).hexdigest()[:12]


def make_token(secret: str, username: str, fingerprint: str, ttl: int = SESSION_TTL) -> str:
    payload = {"u": username, "pv": fingerprint, "exp": int(time.time()) + ttl}
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def read_token(secret: str, token: str | None, fingerprint: str) -> str | None:
    """Возвращает имя пользователя или None, если токен битый/просрочен/от другого пароля."""
    if not token or "." not in token:
        return None
    body, sig = token.rsplit(".", 1)
    expected = _b64(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        payload = json.loads(_unb64(body))
    except (ValueError, TypeError):
        return None
    if int(payload.get("exp", 0)) < time.time():
        return None
    if payload.get("pv") != fingerprint:
        return None
    return payload.get("u")


class LoginLimiter:
    """Счётчик неудачных входов по IP — чтобы подбор пароля не был бесплатным."""

    def __init__(self, max_fails: int = LOGIN_MAX_FAILS, window: int = LOGIN_WINDOW):
        self.max_fails = max_fails
        self.window = window
        self._fails: dict[str, list[float]] = {}

    def _prune(self, ip: str) -> list[float]:
        now = time.time()
        kept = [t for t in self._fails.get(ip, []) if now - t < self.window]
        if kept:
            self._fails[ip] = kept
        else:
            self._fails.pop(ip, None)
        return kept

    def blocked_for(self, ip: str) -> int:
        fails = self._prune(ip)
        if len(fails) < self.max_fails:
            return 0
        return max(1, int(self.window - (time.time() - min(fails))))

    def register_fail(self, ip: str) -> None:
        self._fails.setdefault(ip, []).append(time.time())

    def reset(self, ip: str) -> None:
        self._fails.pop(ip, None)
