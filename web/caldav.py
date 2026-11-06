"""iCloud-календарь через CalDAV.

iCloud отдаёт календарь по протоколу CalDAV (сервер caldav.icloud.com).
Авторизация — Apple ID (email) + app-specific password (генерится в настройках
Apple ID, НЕ основной пароль). Пароль храним в settings зашифрованным: ключ
выводится из SESSION_SECRET, обратимость нужна, чтобы снова ходить в iCloud.

Только стандартная библиотека для шифрования (scrypt + HMAC-CTR), чтобы не
тащить `cryptography` в контейнер. Обёртка над caldav скрывает детали discovery.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from caldav import DAVClient

log = logging.getLogger("caldav")

ICLOUD_URL = "https://caldav.icloud.com/"
LOCAL_TZ = ZoneInfo("Europe/Bratislava")

# iCloud отдаёт список напоминаний как «календарь», но VEVENT'ов в нём нет.
_REMINDER_NAMES = {"напоминания", "reminders", "reminder"}


def _is_reminder(name: str | None) -> bool:
    return (name or "").strip().lower() in _REMINDER_NAMES

# Ключи settings (те же ключи, что в db.set_setting)
SET_CALDAV_USERNAME = "caldav_username"      # Apple ID (email)
SET_CALDAV_PASSWORD = "caldav_password"      # app-specific password (encrypted)
SET_CALDAV_CALENDAR = "caldav_calendar"      # имя выбранного календаря (опц.)


# --- Шифрование пароля на диске (stdlib only) --------------------------------

def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _derive_key(secret: str, salt: bytes) -> bytes:
    return hashlib.scrypt(secret.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    blocks = (length + 31) // 32
    return b"".join(
        hashlib.sha256(key + nonce + i.to_bytes(8, "big")).digest() for i in range(blocks)
    )[:length]


def encrypt_value(secret: str, plaintext: str) -> str:
    salt = secrets.token_bytes(16)
    key = _derive_key(secret, salt)
    nonce = secrets.token_bytes(8)
    data = plaintext.encode()
    ct = bytes(a ^ b for a, b in zip(data, _keystream(key, nonce, len(data))))
    mac = hmac.new(key, nonce + ct, hashlib.sha256).digest()
    return f"enc1${_b64(salt)}${_b64(nonce)}${_b64(ct)}${_b64(mac)}"


def decrypt_value(secret: str, token: str) -> str | None:
    try:
        scheme, salt, nonce, ct, mac = token.split("$")
        if scheme != "enc1":
            return None
        salt_b, nonce_b, ct_b, mac_b = _unb64(salt), _unb64(nonce), _unb64(ct), _unb64(mac)
        key = _derive_key(secret, salt_b)
        expected = hmac.new(key, nonce_b + ct_b, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, mac_b):
            return None
        data = bytes(a ^ b for a, b in zip(ct_b, _keystream(key, nonce_b, len(ct_b))))
        return data.decode()
    except (ValueError, TypeError, UnicodeDecodeError):
        return None


# --- Работа с датами --------------------------------------------------------

def _to_utc_iso(value) -> tuple[str, bool]:
    """icalendar-значение → (ISO-строка в UTC, all_day).

    all_day-события приходят как date; у timed-событий datetime (может быть
    наивным — iCloud такие отдаёт «плавающими» в UTC).
    """
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat(), False
    # date → all-day
    return value.isoformat(), True


class CalDAVError(RuntimeError):
    """Понятная пользователю ошибка подключения/синхронизации календаря."""


class ICloudCalendar:
    def __init__(self, username: str, password: str, calendar_name: str | None = None):
        self.username = username
        self.password = password
        self.calendar_name = calendar_name
        self._client: DAVClient | None = None
        self._principal = None

    def _connect(self) -> DAVClient:
        if self._client is None:
            try:
                self._client = DAVClient(
                    url=ICLOUD_URL, username=self.username, password=self.password
                )
                self._principal = self._client.principal()
            except Exception as exc:  # caldav бросает разное — важно донести суть
                log.warning("CalDAV connect failed: %s", exc)
                raise CalDAVError(
                    "не удалось подключиться к iCloud: проверь Apple ID и app-specific password"
                ) from exc
        return self._client

    def calendars(self) -> list[dict]:
        """Список календарей: [{name, url}, ...]."""
        self._connect()
        out = []
        try:
            for cal in self._principal.calendars():
                out.append({"name": cal.name, "url": str(cal.url)})
        except Exception as exc:
            log.warning("CalDAV list calendars failed: %s", exc)
            raise CalDAVError("не удалось получить список календарей") from exc
        return out

    def _select_calendar(self):
        self._connect()
        cals = self._principal.calendars()
        if not cals:
            raise CalDAVError("в iCloud нет ни одного календаря")
        if self.calendar_name:
            for cal in cals:
                if cal.name == self.calendar_name:
                    return cal
        # По умолчанию берём первый календарь с событиями, пропуская списки
        # напоминаний — у iCloud это отдельная сущность, VEVENT'ов там нет.
        for cal in cals:
            if not _is_reminder(cal.name):
                return cal
        return cals[0]

    def default_name(self) -> str | None:
        """Имя календаря, который реально будет использоваться по умолчанию."""
        self._connect()
        cals = self._principal.calendars()
        if not cals:
            return None
        if self.calendar_name:
            return self.calendar_name
        for cal in cals:
            if not _is_reminder(cal.name):
                return cal.name
        return cals[0].name

    def events(self, start: date, end: date) -> list[dict]:
        """События в диапазоне [start, end] включительно, рекуррентные развёрнуты."""
        cal = self._select_calendar()
        start_dt = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
        end_dt = datetime(end.year, end.month, end.day, 23, 59, 59, tzinfo=timezone.utc)
        try:
            found = cal.date_search(start=start_dt, end=end_dt, compfilter="VEVENT", expand="maybe")
        except Exception as exc:
            log.warning("CalDAV date_search failed: %s", exc)
            raise CalDAVError("не удалось прочитать события из iCloud") from exc

        result: list[dict] = []
        for ev in found:
            try:
                comp = ev.get_icalendar_component()
            except Exception:
                continue
            if comp is None or comp.name != "VEVENT":
                continue
            uid = str(comp.get("UID", ""))
            summary = str(comp.get("SUMMARY", "") or "")
            start_raw = comp.get("DTSTART")
            if start_raw is None:
                continue
            start_iso, all_day = _to_utc_iso(start_raw.dt)
            end_iso = start_iso
            end_raw = comp.get("DTEND")
            if end_raw is not None:
                end_iso, _ = _to_utc_iso(end_raw.dt)
            else:
                duration = comp.get("DURATION")
                if duration is not None and isinstance(start_raw.dt, datetime):
                    end_iso = (start_raw.dt + duration.dt).astimezone(timezone.utc).isoformat()
            result.append({
                "uid": uid,
                "summary": summary,
                "description": str(comp.get("DESCRIPTION", "") or ""),
                "location": str(comp.get("LOCATION", "") or ""),
                "start": start_iso,
                "end": end_iso,
                "all_day": all_day,
                "calendar": cal.name,
            })
        result.sort(key=lambda e: e["start"])
        return result

    def add_event(self, summary: str, start: datetime, end: datetime | None = None,
                  description: str | None = None, all_day: bool = False) -> str:
        """Создаёт событие, возвращает его UID."""
        cal = self._select_calendar()
        uid = f"{secrets.token_hex(12)}@orbita"
        kwargs: dict = {"summary": summary, "uid": uid}
        if all_day:
            kwargs["dtstart"] = start.date()
            kwargs["dtend"] = (end.date() + timedelta(days=1)) if end else start.date() + timedelta(days=1)
        else:
            kwargs["dtstart"] = start.astimezone(LOCAL_TZ) if start.tzinfo else start.replace(tzinfo=LOCAL_TZ)
            kwargs["dtend"] = end.astimezone(LOCAL_TZ) if (end and end.tzinfo) else end
        if description:
            kwargs["description"] = description
        try:
            cal.add_event(**kwargs)
        except Exception as exc:
            log.warning("CalDAV add_event failed: %s", exc)
            raise CalDAVError("не удалось создать событие в iCloud") from exc
        return uid

    def delete_event(self, uid: str) -> bool:
        cal = self._select_calendar()
        try:
            ev = cal.event_by_uid(uid)
        except Exception:
            return False
        if ev is None:
            return False
        try:
            ev.delete()
            return True
        except Exception as exc:
            log.warning("CalDAV delete_event failed: %s", exc)
            raise CalDAVError("не удалось удалить событие из iCloud") from exc


def build_client(settings: dict, secret: str) -> ICloudCalendar | None:
    """Собирает клиент из значений settings или возвращает None, если не настроен."""
    username = settings.get(SET_CALDAV_USERNAME)
    encrypted = settings.get(SET_CALDAV_PASSWORD)
    if not username or not encrypted:
        return None
    password = decrypt_value(secret, encrypted)
    if not password:
        return None
    return ICloudCalendar(username, password, settings.get(SET_CALDAV_CALENDAR))
