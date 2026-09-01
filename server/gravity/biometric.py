from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from hmac import compare_digest
from ipaddress import ip_address
from json import dumps, loads
from socket import create_connection, timeout as SocketTimeout
from typing import Iterable, Mapping, Protocol
from uuid import uuid4
from zoneinfo import ZoneInfo
import base64
import re
import sqlite3
import time

from cryptography.fernet import Fernet

from .admin import AdminService
from .database import Database


DEVICE_STATUSES = {"not_configured", "online", "offline", "authentication_failed", "syncing", "error"}
CONNECTION_MODES = {"tcp", "adms", "mock"}
VERIFICATION_TYPES = {"fingerprint", "face", "card", "password", "unknown"}
ENROLLED_STATUSES = {"unknown", "registered", "not_registered"}
HOST_PATTERN = re.compile(r"^[A-Za-z0-9.-]{1,253}$")
DEVICE_USER_PATTERN = re.compile(r"^[A-Za-z0-9_.@+-]{1,64}$")


def _timezone(name: str):
    try:
        return ZoneInfo(name)
    except Exception:
        if name == "Asia/Kolkata":
            return timezone(timedelta(hours=5, minutes=30), "Asia/Kolkata")
        raise


INDIA_ZONE = _timezone("Asia/Kolkata")


class BiometricError(Exception):
    pass


class BiometricNotFound(BiometricError):
    pass


class BiometricConflict(BiometricError):
    pass


class BiometricValidationError(BiometricError):
    def __init__(self, fields: Mapping[str, str]) -> None:
        super().__init__("Biometric validation failed")
        self.fields = dict(fields)


class BiometricAdapterError(BiometricError):
    def __init__(self, status: str, message: str = "") -> None:
        super().__init__(message or status)
        self.status = status if status in DEVICE_STATUSES else "error"


@dataclass(frozen=True, slots=True)
class BiometricConnectionResult:
    status: str
    message: str = ""
    device_serial: str | None = None


@dataclass(frozen=True, slots=True)
class BiometricDeviceUser:
    device_user_id: str
    display_name: str | None = None
    privilege: str | None = None
    enabled: bool = True
    raw: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class BiometricScanEvent:
    device_user_id: str
    event_time: int | str | datetime
    verification_type: str = "unknown"
    attendance_state: str | None = None
    device_event_id: str | None = None
    raw: Mapping[str, object] = field(default_factory=dict)


class BiometricDeviceAdapter(Protocol):
    def test_connection(self, device: Mapping[str, object], comm_key: str | None = None) -> BiometricConnectionResult:
        ...

    def get_device_info(self, device: Mapping[str, object], comm_key: str | None = None) -> Mapping[str, object]:
        ...

    def get_users(self, device: Mapping[str, object], comm_key: str | None = None) -> Iterable[BiometricDeviceUser]:
        ...

    def get_events_since(
        self,
        device: Mapping[str, object],
        cursor: Mapping[str, object] | None,
        comm_key: str | None = None,
    ) -> Iterable[BiometricScanEvent]:
        ...

    def get_status(self, device: Mapping[str, object], comm_key: str | None = None) -> BiometricConnectionResult:
        ...


class MockBiometricAdapter:
    def __init__(
        self,
        *,
        users: Iterable[BiometricDeviceUser] = (),
        events: Iterable[BiometricScanEvent] = (),
        mode: str = "online",
    ) -> None:
        self.users = list(users)
        self.events = list(events)
        self.mode = mode

    def _result(self) -> BiometricConnectionResult:
        if self.mode == "online":
            return BiometricConnectionResult("online", "Mock fingerprint machine is online.", "MOCK-F09")
        if self.mode == "offline":
            raise BiometricAdapterError("offline", "Machine offline")
        if self.mode == "timeout":
            raise BiometricAdapterError("offline", "Connection timed out")
        if self.mode == "auth_failed":
            raise BiometricAdapterError("authentication_failed", "Communication key rejected")
        raise BiometricAdapterError("error", "Mock biometric adapter error")

    def test_connection(self, device: Mapping[str, object], comm_key: str | None = None) -> BiometricConnectionResult:
        return self._result()

    def get_device_info(self, device: Mapping[str, object], comm_key: str | None = None) -> Mapping[str, object]:
        self._result()
        return {"model": "F09", "deviceSerial": "MOCK-F09", "platform": "ZAM70_TFT"}

    def get_users(self, device: Mapping[str, object], comm_key: str | None = None) -> Iterable[BiometricDeviceUser]:
        self._result()
        return tuple(self.users)

    def get_events_since(
        self,
        device: Mapping[str, object],
        cursor: Mapping[str, object] | None,
        comm_key: str | None = None,
    ) -> Iterable[BiometricScanEvent]:
        self._result()
        after = int((cursor or {}).get("lastEventTime", 0) or 0)
        return tuple(event for event in self.events if _event_timestamp(event.event_time) >= after)

    def get_status(self, device: Mapping[str, object], comm_key: str | None = None) -> BiometricConnectionResult:
        return self._result()


class ZKTecoF09Adapter:
    def test_connection(self, device: Mapping[str, object], comm_key: str | None = None) -> BiometricConnectionResult:
        host = str(device.get("host") or "")
        port = int(device.get("port") or 4370)
        try:
            with create_connection((host, port), timeout=5):
                pass
        except SocketTimeout as error:
            raise BiometricAdapterError("offline", "Connection timed out") from error
        except OSError as error:
            raise BiometricAdapterError("offline", "Machine offline") from error
        try:
            info = self.get_device_info(device, comm_key)
        except BiometricAdapterError:
            return BiometricConnectionResult("online", "TCP port is reachable.")
        return BiometricConnectionResult("online", "Machine is online.", str(info.get("deviceSerial") or "") or None)

    def _zk(self, device: Mapping[str, object], comm_key: str | None = None):
        try:
            from zk import ZK  # type: ignore
        except Exception as error:
            raise BiometricAdapterError("error", "ZKTeco Python driver is not installed") from error
        key = 0
        if comm_key:
            try:
                key = int(comm_key)
            except ValueError as error:
                raise BiometricAdapterError("authentication_failed", "Communication key must be numeric for this driver") from error
        return ZK(
            str(device.get("host") or ""),
            port=int(device.get("port") or 4370),
            timeout=5,
            password=key,
            force_udp=False,
            ommit_ping=True,
        )

    def get_device_info(self, device: Mapping[str, object], comm_key: str | None = None) -> Mapping[str, object]:
        zk = self._zk(device, comm_key)
        conn = None
        try:
            conn = zk.connect()
            serial = str(conn.get_serialnumber() or "")
            platform = str(conn.get_platform() or "")
            return {"model": str(device.get("model") or "F09"), "deviceSerial": serial, "platform": platform}
        except Exception as error:
            raise BiometricAdapterError("authentication_failed", "Could not authenticate with fingerprint machine") from error
        finally:
            if conn is not None:
                try:
                    conn.disconnect()
                except Exception:
                    pass

    def get_users(self, device: Mapping[str, object], comm_key: str | None = None) -> Iterable[BiometricDeviceUser]:
        zk = self._zk(device, comm_key)
        conn = None
        try:
            conn = zk.connect()
            users = []
            for user in conn.get_users():
                users.append(BiometricDeviceUser(
                    device_user_id=str(getattr(user, "user_id", "") or getattr(user, "uid", "")),
                    display_name=str(getattr(user, "name", "") or "") or None,
                    privilege=str(getattr(user, "privilege", "") or "") or None,
                    enabled=True,
                    raw={},
                ))
            return tuple(users)
        except Exception as error:
            raise BiometricAdapterError("authentication_failed", "Could not read users from fingerprint machine") from error
        finally:
            if conn is not None:
                try:
                    conn.disconnect()
                except Exception:
                    pass

    def get_events_since(
        self,
        device: Mapping[str, object],
        cursor: Mapping[str, object] | None,
        comm_key: str | None = None,
    ) -> Iterable[BiometricScanEvent]:
        zk = self._zk(device, comm_key)
        conn = None
        last = int((cursor or {}).get("lastEventTime", 0) or 0)
        try:
            conn = zk.connect()
            events = []
            for record in conn.get_attendance():
                event_time = getattr(record, "timestamp", None)
                timestamp = _event_timestamp(event_time)
                if timestamp < last:
                    continue
                events.append(BiometricScanEvent(
                    device_user_id=str(getattr(record, "user_id", "") or ""),
                    event_time=timestamp,
                    verification_type=_verification_label(getattr(record, "punch", None)),
                    attendance_state=str(getattr(record, "status", "") or "") or None,
                    device_event_id=None,
                    raw={},
                ))
            return tuple(events)
        except Exception as error:
            raise BiometricAdapterError("authentication_failed", "Could not read attendance from fingerprint machine") from error
        finally:
            if conn is not None:
                try:
                    conn.disconnect()
                except Exception:
                    pass

    def get_status(self, device: Mapping[str, object], comm_key: str | None = None) -> BiometricConnectionResult:
        return self.test_connection(device, comm_key)


def _verification_label(value: object) -> str:
    text = str(value or "").strip().casefold()
    if text in VERIFICATION_TYPES:
        return text
    if text in {"0", "finger", "fp"}:
        return "fingerprint"
    if text in {"15", "face"}:
        return "face"
    if text in {"2", "card"}:
        return "card"
    if text in {"3", "password"}:
        return "password"
    return "unknown"


def _clean_text(value: object, field: str, *, minimum: int = 1, maximum: int = 120) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} is required")
    cleaned = " ".join(value.strip().split())
    if not minimum <= len(cleaned) <= maximum or "\x00" in cleaned:
        raise ValueError(f"{field} must be {minimum}-{maximum} characters")
    return cleaned


def _clean_optional_text(value: object, field: str, *, maximum: int = 120) -> str | None:
    if value in (None, ""):
        return None
    return _clean_text(value, field, minimum=1, maximum=maximum)


def _clean_device_user_id(value: object) -> str:
    cleaned = str(value or "").strip()
    if not DEVICE_USER_PATTERN.fullmatch(cleaned):
        raise ValueError("Device user ID must be 1-64 letters, numbers, dots, dashes or underscores")
    return cleaned


def _clean_host(value: object) -> str | None:
    if value in (None, ""):
        return None
    host = str(value).strip()
    try:
        ip_address(host)
        return host
    except ValueError:
        pass
    if not HOST_PATTERN.fullmatch(host) or ".." in host or host.startswith(".") or host.endswith("."):
        raise ValueError("Enter a valid IP address or hostname")
    return host


def _clean_port(value: object) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError("Port must be a number") from error
    if not 1 <= port <= 65535:
        raise ValueError("Port must be between 1 and 65535")
    return port


def _clean_positive_int(value: object, *, field: str, minimum: int, maximum: int, default: int) -> int:
    if value in (None, ""):
        return default
    try:
        number = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be a number") from error
    if not minimum <= number <= maximum:
        raise ValueError(f"{field} must be between {minimum} and {maximum} seconds")
    return number


def _safe_json(value: Mapping[str, object] | None) -> str:
    return dumps(dict(value or {}), sort_keys=True, separators=(",", ":"))


def _loads_json(value: str | None) -> dict[str, object]:
    if not value:
        return {}
    try:
        loaded = loads(value)
    except ValueError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _event_timestamp(value: int | str | datetime | object) -> int:
    if isinstance(value, datetime):
        date = value
        if date.tzinfo is None:
            date = date.replace(tzinfo=INDIA_ZONE)
        return int(date.timestamp())
    if isinstance(value, (int, float)):
        number = int(value)
        return number // 1000 if number > 10_000_000_000 else number
    if isinstance(value, str):
        text = value.strip()
        if text.isdigit():
            return _event_timestamp(int(text))
        try:
            date = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("Event time is invalid") from error
        if date.tzinfo is None:
            date = date.replace(tzinfo=INDIA_ZONE)
        return int(date.timestamp())
    raise ValueError("Event time is invalid")


def _visit_date(timestamp: int, tz_name: str) -> str:
    try:
        zone = _timezone(tz_name)
    except Exception:
        zone = INDIA_ZONE
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone(zone).date().isoformat()


def _event_hash(device_user_id: str, event_time: int, verification_type: str, attendance_state: str | None, device_event_id: str | None) -> str:
    stable = "|".join((device_user_id, str(event_time), verification_type, attendance_state or "", device_event_id or ""))
    return sha256(stable.encode("utf-8")).hexdigest()


class BiometricService:
    def __init__(
        self,
        database: Database,
        settings,
        admin_service: AdminService,
        *,
        clock=time.time,
        adapters: Mapping[str, BiometricDeviceAdapter] | None = None,
    ) -> None:
        self.database = database
        self.settings = settings
        self.admin_service = admin_service
        self.clock = clock
        self.adapters = dict(adapters or {})
        self.adapters.setdefault("mock", MockBiometricAdapter())
        self.adapters.setdefault("tcp", ZKTecoF09Adapter())

    def _now(self) -> int:
        return int(self.clock())

    def _fernet(self) -> Fernet:
        if len(str(self.settings.secret_key).encode("utf-8")) < 32:
            raise BiometricValidationError({"commKey": "Configure a strong SECRET_KEY before saving a communication key"})
        digest = sha256(b"gravity-biometric-comm-key\x00" + self.settings.secret_key.encode("utf-8")).digest()
        return Fernet(base64.urlsafe_b64encode(digest))

    def _encrypt_secret(self, value: object) -> str | None:
        if value in (None, ""):
            return None
        text = str(value).strip()
        if not text:
            return None
        if len(text) > 128 or "\x00" in text:
            raise BiometricValidationError({"commKey": "Communication key is invalid"})
        return self._fernet().encrypt(text.encode("utf-8")).decode("ascii")

    def _decrypt_secret(self, value: object) -> str | None:
        if not value:
            return None
        return self._fernet().decrypt(str(value).encode("ascii")).decode("utf-8")

    @staticmethod
    def _safe_device(row) -> dict[str, object]:
        return {
            "id": row["id"],
            "name": row["name"],
            "vendor": row["vendor"],
            "model": row["model"],
            "deviceSerial": row["device_serial"],
            "deviceIdentifier": row["device_identifier"],
            "host": row["host"],
            "port": int(row["port"]),
            "connectionMode": row["connection_mode"],
            "enabled": bool(row["enabled"]),
            "status": row["status"],
            "lastSeenAt": int(row["last_seen_at"]) if row["last_seen_at"] is not None else None,
            "lastSyncAt": int(row["last_sync_at"]) if row["last_sync_at"] is not None else None,
            "timezone": row["timezone"],
            "pollIntervalSeconds": int(row["poll_interval_seconds"]),
            "duplicateWindowSeconds": int(row["duplicate_window_seconds"]),
            "visitGapSeconds": int(row["visit_gap_seconds"]),
            "commKeyConfigured": bool(row["comm_key_encrypted"]),
            "createdAt": int(row["created_at"]),
            "updatedAt": int(row["updated_at"]),
        }

    @staticmethod
    def _safe_mapping(row) -> dict[str, object]:
        return {
            "id": row["id"],
            "deviceId": row["device_id"],
            "personId": row["person_id"],
            "deviceUserId": row["device_user_id"],
            "deviceDisplayName": row["device_display_name"],
            "enabled": bool(row["enabled"]),
            "enrolledStatus": row["enrolled_status"],
            "lastVerifiedAt": int(row["last_verified_at"]) if row["last_verified_at"] is not None else None,
            "createdAt": int(row["created_at"]),
            "updatedAt": int(row["updated_at"]),
        }

    @staticmethod
    def _safe_device_user(row, event_count: int = 0) -> dict[str, object]:
        return {
            "id": row["id"],
            "deviceId": row["device_id"],
            "deviceUserId": row["device_user_id"],
            "displayName": row["display_name"],
            "privilege": row["privilege"],
            "enabled": bool(row["enabled"]),
            "syncedAt": int(row["synced_at"]),
            "eventCount": event_count,
        }

    @staticmethod
    def _safe_event(row) -> dict[str, object]:
        return {
            "id": row["id"],
            "deviceId": row["device_id"],
            "deviceUserId": row["device_user_id"],
            "personId": row["person_id"],
            "visitId": row["visit_id"],
            "eventTime": int(row["event_time"]),
            "receivedAt": int(row["received_at"]),
            "verificationType": row["verification_type"],
            "attendanceState": row["attendance_state"],
            "source": row["source"],
            "processingStatus": row["processing_status"],
            "duplicate": bool(row["is_duplicate"]),
        }

    def create_device(self, payload: Mapping[str, object], *, actor_admin_user_id: str) -> dict[str, object]:
        errors: dict[str, str] = {}
        try:
            name = _clean_text(payload.get("name", "Gravity Entrance"), "Name", maximum=80)
        except ValueError as error:
            name = ""
            errors["name"] = str(error)
        vendor = str(payload.get("vendor", "zkteco")).strip().casefold() or "zkteco"
        model = str(payload.get("model", "F09")).strip() or "F09"
        if vendor != "zkteco" and payload.get("connectionMode", "tcp") != "mock":
            errors["vendor"] = "Only ZKTeco devices are supported in this version"
        try:
            device_identifier = _clean_text(payload.get("deviceIdentifier", payload.get("deviceId", "1")), "Device ID", maximum=80)
        except ValueError as error:
            device_identifier = ""
            errors["deviceIdentifier"] = str(error)
        try:
            host = _clean_host(payload.get("host"))
        except ValueError as error:
            host = None
            errors["host"] = str(error)
        try:
            port = _clean_port(payload.get("port", 4370))
        except ValueError as error:
            port = 4370
            errors["port"] = str(error)
        mode = str(payload.get("connectionMode", "tcp")).strip().casefold() or "tcp"
        if mode not in CONNECTION_MODES:
            errors["connectionMode"] = "Connection mode must be TCP, ADMS or mock"
        try:
            poll = _clean_positive_int(payload.get("pollIntervalSeconds"), field="Poll interval", minimum=10, maximum=3600, default=30)
            duplicate = _clean_positive_int(payload.get("duplicateWindowSeconds"), field="Duplicate window", minimum=10, maximum=1800, default=120)
            visit_gap = _clean_positive_int(payload.get("visitGapSeconds"), field="Visit gap", minimum=600, maximum=86400, default=14400)
        except ValueError as error:
            poll, duplicate, visit_gap = 30, 120, 14400
            errors["timing"] = str(error)
        timezone_name = str(payload.get("timezone", "Asia/Kolkata")).strip() or "Asia/Kolkata"
        try:
            _timezone(timezone_name)
        except Exception:
            errors["timezone"] = "Select a valid timezone"
        if mode == "tcp" and not host:
            errors["host"] = "IP address is required for TCP connection"
        if errors:
            raise BiometricValidationError(errors)
        encrypted = self._encrypt_secret(payload.get("commKey"))
        device_id = uuid4().hex
        now = self._now()
        try:
            with self.database.session() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "INSERT INTO biometric_devices(id,name,vendor,model,device_serial,device_identifier,host,port,"
                    "connection_mode,enabled,status,timezone,poll_interval_seconds,duplicate_window_seconds,"
                    "visit_gap_seconds,comm_key_encrypted,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        device_id, name, vendor, model, _clean_optional_text(payload.get("deviceSerial"), "Serial", maximum=120),
                        device_identifier, host, port, mode, 1 if payload.get("enabled", True) else 0,
                        "not_configured", timezone_name, poll, duplicate, visit_gap, encrypted, now, now,
                    ),
                )
                self.admin_service._audit(
                    connection,
                    actor_admin_user_id,
                    "biometric_device_created",
                    target_type="biometric_device",
                    target_id=device_id,
                    metadata={"vendor": vendor, "model": model, "connectionMode": mode},
                )
                row = connection.execute("SELECT * FROM biometric_devices WHERE id=?", (device_id,)).fetchone()
                connection.commit()
        except sqlite3.IntegrityError as error:
            raise BiometricConflict("A fingerprint machine with this device ID already exists") from error
        return {"device": self._safe_device(row)}

    def update_device(self, device_id: str, payload: Mapping[str, object], *, actor_admin_user_id: str) -> dict[str, object]:
        allowed = {
            "name", "model", "deviceSerial", "deviceIdentifier", "host", "port", "connectionMode",
            "enabled", "timezone", "pollIntervalSeconds", "duplicateWindowSeconds", "visitGapSeconds",
            "commKey", "clearCommKey",
        }
        unexpected = sorted(set(payload) - allowed)
        if unexpected:
            raise BiometricValidationError({field: "Unexpected field" for field in unexpected})
        with self.database.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM biometric_devices WHERE id=?", (device_id,)).fetchone()
            if row is None:
                raise BiometricNotFound("Fingerprint machine not found")
            values = dict(row)
            errors: dict[str, str] = {}
            setters: list[str] = []
            args: list[object] = []
            field_map = {
                "name": ("name", lambda value: _clean_text(value, "Name", maximum=80)),
                "model": ("model", lambda value: _clean_text(value, "Model", maximum=80)),
                "deviceSerial": ("device_serial", lambda value: _clean_optional_text(value, "Serial", maximum=120)),
                "deviceIdentifier": ("device_identifier", lambda value: _clean_text(value, "Device ID", maximum=80)),
                "host": ("host", _clean_host),
                "port": ("port", _clean_port),
                "timezone": ("timezone", lambda value: str(value or "Asia/Kolkata").strip() or "Asia/Kolkata"),
                "pollIntervalSeconds": ("poll_interval_seconds", lambda value: _clean_positive_int(value, field="Poll interval", minimum=10, maximum=3600, default=int(values["poll_interval_seconds"]))),
                "duplicateWindowSeconds": ("duplicate_window_seconds", lambda value: _clean_positive_int(value, field="Duplicate window", minimum=10, maximum=1800, default=int(values["duplicate_window_seconds"]))),
                "visitGapSeconds": ("visit_gap_seconds", lambda value: _clean_positive_int(value, field="Visit gap", minimum=600, maximum=86400, default=int(values["visit_gap_seconds"]))),
            }
            if "connectionMode" in payload:
                mode = str(payload["connectionMode"]).strip().casefold()
                if mode not in CONNECTION_MODES:
                    errors["connectionMode"] = "Connection mode must be TCP, ADMS or mock"
                else:
                    values["connection_mode"] = mode
                    setters.append("connection_mode=?")
                    args.append(mode)
            if "enabled" in payload:
                enabled = 1 if payload.get("enabled") else 0
                values["enabled"] = enabled
                setters.append("enabled=?")
                args.append(enabled)
            for source, (column, cleaner) in field_map.items():
                if source in payload:
                    try:
                        cleaned = cleaner(payload[source])
                        if source == "timezone":
                            _timezone(str(cleaned))
                    except Exception as error:
                        errors[source] = str(error) or "Invalid value"
                        continue
                    values[column] = cleaned
                    setters.append(f"{column}=?")
                    args.append(cleaned)
            if values["connection_mode"] == "tcp" and not values["host"]:
                errors["host"] = "IP address is required for TCP connection"
            if errors:
                raise BiometricValidationError(errors)
            if payload.get("clearCommKey"):
                setters.append("comm_key_encrypted=NULL")
            elif "commKey" in payload and payload.get("commKey") not in (None, ""):
                setters.append("comm_key_encrypted=?")
                args.append(self._encrypt_secret(payload.get("commKey")))
            if setters:
                now = self._now()
                setters.append("updated_at=?")
                args.extend((now, device_id))
                connection.execute(f"UPDATE biometric_devices SET {', '.join(setters)} WHERE id=?", args)
                self.admin_service._audit(
                    connection,
                    actor_admin_user_id,
                    "biometric_device_updated",
                    target_type="biometric_device",
                    target_id=device_id,
                    metadata={"fields": sorted(set(payload) - {"commKey"})},
                )
            updated = connection.execute("SELECT * FROM biometric_devices WHERE id=?", (device_id,)).fetchone()
            connection.commit()
        return {"device": self._safe_device(updated)}

    def list_devices(self) -> list[dict[str, object]]:
        with self.database.session() as connection:
            rows = connection.execute("SELECT * FROM biometric_devices ORDER BY created_at ASC,id ASC").fetchall()
        return [self._safe_device(row) for row in rows]

    def _device_row(self, connection, device_id: str):
        row = connection.execute("SELECT * FROM biometric_devices WHERE id=?", (device_id,)).fetchone()
        if row is None:
            raise BiometricNotFound("Fingerprint machine not found")
        return row

    def _adapter_for(self, row) -> BiometricDeviceAdapter:
        return self.adapters.get(row["connection_mode"]) or self.adapters["tcp"]

    def test_connection(self, device_id: str, *, actor_admin_user_id: str) -> dict[str, object]:
        with self.database.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = self._device_row(connection, device_id)
            adapter = self._adapter_for(row)
            try:
                result = adapter.test_connection(self._safe_device(row), self._decrypt_secret(row["comm_key_encrypted"]))
                status = result.status if result.status in DEVICE_STATUSES else "online"
                serial = result.device_serial or row["device_serial"]
            except BiometricAdapterError as error:
                status = error.status
                serial = row["device_serial"]
            now = self._now()
            connection.execute(
                "UPDATE biometric_devices SET status=?,device_serial=COALESCE(?,device_serial),last_seen_at=CASE WHEN ?='online' THEN ? ELSE last_seen_at END,updated_at=? WHERE id=?",
                (status, serial, status, now, now, device_id),
            )
            self.admin_service._audit(
                connection,
                actor_admin_user_id,
                "biometric_device_tested",
                target_type="biometric_device",
                target_id=device_id,
                metadata={"status": status},
            )
            updated = connection.execute("SELECT * FROM biometric_devices WHERE id=?", (device_id,)).fetchone()
            connection.commit()
        return {"device": self._safe_device(updated), "status": status}

    def sync_device(self, device_id: str, *, actor_admin_user_id: str) -> dict[str, object]:
        with self.database.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = self._device_row(connection, device_id)
            connection.execute("UPDATE biometric_devices SET status='syncing',updated_at=? WHERE id=?", (self._now(), device_id))
            connection.commit()
        try:
            users = tuple(self._adapter_for(row).get_users(self._safe_device(row), self._decrypt_secret(row["comm_key_encrypted"])))
            events = tuple(self._adapter_for(row).get_events_since(self._safe_device(row), _loads_json(row["sync_cursor_json"]), self._decrypt_secret(row["comm_key_encrypted"])))
        except BiometricAdapterError as error:
            with self.database.session() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("UPDATE biometric_devices SET status=?,updated_at=? WHERE id=?", (error.status, self._now(), device_id))
                connection.commit()
            raise
        with self.database.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = self._device_row(connection, device_id)
            synced_users = self._upsert_device_users(connection, row, users)
            stored = self._record_events(connection, row, events, source=row["connection_mode"])
            cursor = {"lastEventTime": stored["lastEventTime"] or _loads_json(row["sync_cursor_json"]).get("lastEventTime", 0)}
            now = self._now()
            connection.execute(
                "UPDATE biometric_devices SET status='online',last_seen_at=?,last_sync_at=?,sync_cursor_json=?,updated_at=? WHERE id=?",
                (now, now, _safe_json(cursor), now, device_id),
            )
            self.admin_service._audit(
                connection,
                actor_admin_user_id,
                "biometric_device_synced",
                target_type="biometric_device",
                target_id=device_id,
                metadata={"users": synced_users, "events": stored["stored"], "duplicates": stored["duplicates"], "unmatched": stored["unmatched"]},
            )
            updated = connection.execute("SELECT * FROM biometric_devices WHERE id=?", (device_id,)).fetchone()
            connection.commit()
        return {"device": self._safe_device(updated), "usersSynced": synced_users, **stored}

    def _upsert_device_users(self, connection, device, users: Iterable[BiometricDeviceUser]) -> int:
        now = self._now()
        count = 0
        for user in users:
            user_id = _clean_device_user_id(user.device_user_id)
            count += 1
            connection.execute(
                "INSERT INTO biometric_device_users(id,device_id,device_user_id,display_name,privilege,enabled,synced_at,raw_payload_json) "
                "VALUES (?,?,?,?,?,?,?,?) "
                "ON CONFLICT(device_id,device_user_id) DO UPDATE SET display_name=excluded.display_name,privilege=excluded.privilege,"
                "enabled=excluded.enabled,synced_at=excluded.synced_at,raw_payload_json=excluded.raw_payload_json",
                (uuid4().hex, device["id"], user_id, user.display_name, user.privilege, 1 if user.enabled else 0, now, _safe_json(user.raw)),
            )
        return count

    def create_mapping(self, payload: Mapping[str, object], *, actor_admin_user_id: str) -> dict[str, object]:
        errors: dict[str, str] = {}
        device_id = str(payload.get("deviceId", "")).strip()
        person_id = str(payload.get("personId", "")).strip()
        try:
            device_user_id = _clean_device_user_id(payload.get("deviceUserId"))
        except ValueError as error:
            device_user_id = ""
            errors["deviceUserId"] = str(error)
        status = str(payload.get("enrolledStatus", "registered")).strip().casefold() or "registered"
        if status not in ENROLLED_STATUSES:
            errors["enrolledStatus"] = "Enrollment status is invalid"
        if errors:
            raise BiometricValidationError(errors)
        mapping_id = uuid4().hex
        now = self._now()
        try:
            with self.database.session() as connection:
                connection.execute("BEGIN IMMEDIATE")
                self._device_row(connection, device_id)
                person = connection.execute(
                    "SELECT id,person_type,status FROM customers WHERE id=? AND status!='deleted'",
                    (person_id,),
                ).fetchone()
                if person is None:
                    raise BiometricNotFound("Person not found")
                connection.execute(
                    "INSERT INTO biometric_person_mappings(id,device_id,person_id,device_user_id,device_display_name,enabled,enrolled_status,created_at,updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        mapping_id, device_id, person_id, device_user_id,
                        _clean_optional_text(payload.get("deviceDisplayName"), "Display name", maximum=80),
                        1, status, now, now,
                    ),
                )
                connection.execute(
                    "UPDATE attendance_events SET person_id=? WHERE device_id=? AND device_user_id=? AND person_id IS NULL",
                    (person_id, device_id, device_user_id),
                )
                self._rebuild_visits_for_person(connection, person_id)
                self.admin_service._audit(
                    connection,
                    actor_admin_user_id,
                    "biometric_mapping_created",
                    target_type="customer",
                    target_id=person_id,
                    metadata={"deviceId": device_id, "deviceUserId": device_user_id},
                )
                row = self._mapping_join(connection, "m.id=?", (mapping_id,))
                connection.commit()
        except sqlite3.IntegrityError as error:
            raise BiometricConflict("This fingerprint ID or person is already linked on this machine") from error
        return {"mapping": row}

    def remove_mapping(self, mapping_id: str, *, actor_admin_user_id: str) -> dict[str, object]:
        with self.database.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM biometric_person_mappings WHERE id=? AND enabled=1", (mapping_id,)).fetchone()
            if row is None:
                raise BiometricNotFound("Biometric mapping not found")
            now = self._now()
            connection.execute("UPDATE biometric_person_mappings SET enabled=0,updated_at=? WHERE id=?", (now, mapping_id))
            self.admin_service._audit(
                connection,
                actor_admin_user_id,
                "biometric_mapping_removed",
                target_type="customer",
                target_id=row["person_id"],
                metadata={"deviceId": row["device_id"], "deviceUserId": row["device_user_id"]},
            )
            connection.commit()
        return {"removed": True}

    def list_mappings(self, *, person_id: str = "", device_id: str = "") -> list[dict[str, object]]:
        clauses = ["m.enabled=1"]
        args: list[object] = []
        if person_id:
            clauses.append("m.person_id=?")
            args.append(person_id)
        if device_id:
            clauses.append("m.device_id=?")
            args.append(device_id)
        with self.database.session() as connection:
            rows = connection.execute(
                "SELECT m.*,d.name AS device_name,c.display_name,c.person_type,c.status AS person_status "
                "FROM biometric_person_mappings m "
                "JOIN biometric_devices d ON d.id=m.device_id "
                "JOIN customers c ON c.id=m.person_id "
                f"WHERE {' AND '.join(clauses)} ORDER BY c.display_name COLLATE NOCASE,m.device_user_id",
                args,
            ).fetchall()
        return [self._mapping_payload(row) for row in rows]

    def list_device_users(self, device_id: str, *, unmatched_only: bool = False, query: str = "") -> list[dict[str, object]]:
        needle = query.strip().casefold()[:100]
        pattern = f"%{needle}%"
        with self.database.session() as connection:
            self._device_row(connection, device_id)
            rows = connection.execute(
                "SELECT u.*,COUNT(e.id) AS event_count FROM biometric_device_users u "
                "LEFT JOIN attendance_events e ON e.device_id=u.device_id AND e.device_user_id=u.device_user_id "
                "LEFT JOIN biometric_person_mappings m ON m.device_id=u.device_id AND m.device_user_id=u.device_user_id AND m.enabled=1 "
                "WHERE u.device_id=? AND (?=0 OR m.id IS NULL) "
                "AND (?='' OR lower(COALESCE(u.display_name,'')) LIKE ? OR lower(u.device_user_id) LIKE ?) "
                "GROUP BY u.id ORDER BY u.display_name COLLATE NOCASE,u.device_user_id LIMIT 500",
                (device_id, 1 if unmatched_only else 0, needle, pattern, pattern),
            ).fetchall()
        return [self._safe_device_user(row, int(row["event_count"])) for row in rows]

    def _mapping_join(self, connection, where: str, args: tuple[object, ...]) -> dict[str, object]:
        row = connection.execute(
            "SELECT m.*,d.name AS device_name,c.display_name,c.person_type,c.status AS person_status "
            "FROM biometric_person_mappings m "
            "JOIN biometric_devices d ON d.id=m.device_id "
            "JOIN customers c ON c.id=m.person_id "
            f"WHERE {where}",
            args,
        ).fetchone()
        if row is None:
            raise BiometricNotFound("Biometric mapping not found")
        return self._mapping_payload(row)

    def _mapping_payload(self, row) -> dict[str, object]:
        item = self._safe_mapping(row)
        item["deviceName"] = row["device_name"]
        item["person"] = {
            "id": row["person_id"],
            "displayName": row["display_name"],
            "personType": row["person_type"],
            "status": row["person_status"],
        }
        return item

    def record_event(self, device_id: str, event: BiometricScanEvent | Mapping[str, object], *, source: str = "mock") -> dict[str, object]:
        with self.database.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            device = self._device_row(connection, device_id)
            stored = self._record_events(connection, device, (self._coerce_event(event),), source=source)
            connection.commit()
        return stored

    def _coerce_event(self, event: BiometricScanEvent | Mapping[str, object]) -> BiometricScanEvent:
        if isinstance(event, BiometricScanEvent):
            return event
        return BiometricScanEvent(
            device_user_id=str(event.get("deviceUserId", event.get("device_user_id", ""))),
            event_time=event.get("eventTime", event.get("event_time", self._now())),
            verification_type=str(event.get("verificationType", event.get("verification_type", "unknown"))),
            attendance_state=event.get("attendanceState", event.get("attendance_state")),
            device_event_id=event.get("deviceEventId", event.get("device_event_id")),
            raw=dict(event.get("raw", {}) or {}),
        )

    def _record_events(self, connection, device, events: Iterable[BiometricScanEvent], *, source: str) -> dict[str, object]:
        stored = duplicates = unmatched = malformed = 0
        last_event_time = 0
        last_event = None
        for event in events:
            try:
                device_user_id = _clean_device_user_id(event.device_user_id)
                event_time = _event_timestamp(event.event_time)
                verification = _verification_label(event.verification_type)
            except ValueError:
                malformed += 1
                continue
            event_hash = _event_hash(device_user_id, event_time, verification, event.attendance_state, event.device_event_id)
            if connection.execute(
                "SELECT 1 FROM attendance_events WHERE device_id=? AND raw_event_hash=?",
                (device["id"], event_hash),
            ).fetchone():
                duplicates += 1
                last_event_time = max(last_event_time, event_time)
                continue
            mapping = connection.execute(
                "SELECT * FROM biometric_person_mappings WHERE device_id=? AND device_user_id=? AND enabled=1",
                (device["id"], device_user_id),
            ).fetchone()
            person_id = mapping["person_id"] if mapping is not None else None
            visit_id = None
            is_duplicate = 0
            status = "stored"
            if person_id:
                visit_id, is_duplicate = self._attach_visit(connection, device, person_id, event_time, verification)
                if mapping is not None:
                    connection.execute(
                        "UPDATE biometric_person_mappings SET last_verified_at=?,updated_at=? WHERE id=?",
                        (event_time, self._now(), mapping["id"]),
                    )
            else:
                unmatched += 1
                status = "unmatched"
            if is_duplicate:
                duplicates += 1
                status = "duplicate"
            connection.execute(
                "INSERT INTO attendance_events(id,device_id,device_event_id,device_user_id,person_id,visit_id,event_time,"
                "received_at,verification_type,attendance_state,raw_event_hash,source,processing_status,is_duplicate,raw_payload_json,created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    uuid4().hex, device["id"], event.device_event_id, device_user_id, person_id, visit_id, event_time,
                    self._now(), verification, event.attendance_state, event_hash, source, status, is_duplicate,
                    _safe_json(event.raw), self._now(),
                ),
            )
            stored += 1
            last_event_time = max(last_event_time, event_time)
            last_event = self._event_by_hash(connection, device["id"], event_hash)
        return {
            "stored": stored,
            "duplicates": duplicates,
            "unmatched": unmatched,
            "malformed": malformed,
            "lastEventTime": last_event_time,
            "event": last_event,
        }

    def _event_by_hash(self, connection, device_id: str, event_hash: str) -> dict[str, object] | None:
        row = connection.execute(
            "SELECT * FROM attendance_events WHERE device_id=? AND raw_event_hash=?",
            (device_id, event_hash),
        ).fetchone()
        return self._safe_event(row) if row is not None else None

    def _attach_visit(self, connection, device, person_id: str, event_time: int, verification: str) -> tuple[str, int]:
        duplicate_window = int(device["duplicate_window_seconds"])
        visit_gap = int(device["visit_gap_seconds"])
        visit_date = _visit_date(event_time, str(device["timezone"]))
        recent = connection.execute(
            "SELECT * FROM attendance_visits WHERE person_id=? AND device_id=? AND visit_date=? "
            "ORDER BY last_scan_at DESC LIMIT 1",
            (person_id, device["id"], visit_date),
        ).fetchone()
        now = self._now()
        if recent is not None and 0 <= event_time - int(recent["last_scan_at"]) <= duplicate_window:
            connection.execute(
                "UPDATE attendance_visits SET last_scan_at=MAX(last_scan_at,?),scan_count=scan_count+1,verification_summary=?,updated_at=? WHERE id=?",
                (event_time, _merge_verification(recent["verification_summary"], verification), now, recent["id"]),
            )
            return str(recent["id"]), 1
        if recent is not None and 0 <= event_time - int(recent["last_scan_at"]) <= visit_gap:
            connection.execute(
                "UPDATE attendance_visits SET last_scan_at=MAX(last_scan_at,?),scan_count=scan_count+1,verification_summary=?,updated_at=? WHERE id=?",
                (event_time, _merge_verification(recent["verification_summary"], verification), now, recent["id"]),
            )
            return str(recent["id"]), 0
        visit_id = uuid4().hex
        connection.execute(
            "INSERT INTO attendance_visits(id,person_id,device_id,visit_date,first_scan_at,last_scan_at,scan_count,verification_summary,status,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (visit_id, person_id, device["id"], visit_date, event_time, event_time, 1, verification, "present", now, now),
        )
        return visit_id, 0

    def _rebuild_visits_for_person(self, connection, person_id: str) -> None:
        connection.execute("DELETE FROM attendance_visits WHERE person_id=?", (person_id,))
        connection.execute("UPDATE attendance_events SET visit_id=NULL,is_duplicate=0,processing_status='stored' WHERE person_id=?", (person_id,))
        rows = connection.execute(
            "SELECT * FROM attendance_events WHERE person_id=? ORDER BY event_time ASC,id ASC",
            (person_id,),
        ).fetchall()
        for row in rows:
            device = self._device_row(connection, row["device_id"])
            visit_id, duplicate = self._attach_visit(connection, device, person_id, int(row["event_time"]), row["verification_type"])
            connection.execute(
                "UPDATE attendance_events SET visit_id=?,is_duplicate=?,processing_status=? WHERE id=?",
                (visit_id, duplicate, "duplicate" if duplicate else "stored", row["id"]),
            )

    def attendance_stats(self, *, date: str = "") -> dict[str, object]:
        start, end, label = self._range_for_date(date)
        with self.database.session() as connection:
            self._reconcile_memberships(connection)
            row = connection.execute(
                "SELECT COUNT(*) AS visits,COUNT(DISTINCT CASE WHEN c.person_type='member' THEN v.person_id END) AS members,"
                "COUNT(DISTINCT CASE WHEN c.person_type='staff' THEN v.person_id END) AS staff,"
                "COUNT(DISTINCT v.person_id) AS present FROM attendance_visits v JOIN customers c ON c.id=v.person_id "
                "WHERE v.first_scan_at>=? AND v.first_scan_at<?",
                (start, end),
            ).fetchone()
            busiest = connection.execute(
                "SELECT CAST(strftime('%H', datetime(first_scan_at,'unixepoch','+5 hours','+30 minutes')) AS INTEGER) AS hour,COUNT(*) AS count "
                "FROM attendance_visits WHERE first_scan_at>=? AND first_scan_at<? GROUP BY hour ORDER BY count DESC,hour ASC LIMIT 1",
                (start, end),
            ).fetchone()
            devices = connection.execute("SELECT * FROM biometric_devices ORDER BY created_at ASC").fetchall()
        return {
            "date": label,
            "presentToday": int(row["present"] or 0),
            "members": int(row["members"] or 0),
            "staff": int(row["staff"] or 0),
            "totalVisits": int(row["visits"] or 0),
            "busiestHour": None if busiest is None else {"hour": int(busiest["hour"]), "visits": int(busiest["count"])},
            "devices": [self._safe_device(device) for device in devices],
        }

    def list_attendance(
        self,
        *,
        start_date: str = "",
        end_date: str = "",
        person_type: str = "",
        query: str = "",
        membership_status: str = "",
        limit: object = 200,
    ) -> dict[str, object]:
        start, end = self._range_for_dates(start_date, end_date)
        ptype = person_type.strip().casefold()
        if ptype not in {"", "member", "staff"}:
            raise BiometricValidationError({"personType": "Person type must be member or staff"})
        mstatus = membership_status.strip().casefold()
        if mstatus not in {"", "active", "expired", "none"}:
            raise BiometricValidationError({"membershipStatus": "Invalid membership filter"})
        needle = query.strip().casefold()[:100]
        pattern = f"%{needle}%"
        with self.database.session() as connection:
            self._reconcile_memberships(connection)
            rows = connection.execute(
                "SELECT v.*,c.display_name,c.phone_e164,c.person_type,c.status AS person_status,c.staff_designation,"
                "m.membership_number,m.status AS membership_status,m.ends_at AS membership_ends_at,d.name AS device_name "
                "FROM attendance_visits v JOIN customers c ON c.id=v.person_id "
                "JOIN biometric_devices d ON d.id=v.device_id "
                "LEFT JOIN memberships m ON m.id=("
                "SELECT mx.id FROM memberships mx WHERE mx.customer_id=c.id AND c.person_type='member' "
                "AND mx.status IN ('active','scheduled','expired') "
                "ORDER BY CASE mx.status WHEN 'active' THEN 0 WHEN 'scheduled' THEN 1 WHEN 'expired' THEN 2 ELSE 3 END,"
                "mx.ends_at DESC,mx.created_at DESC LIMIT 1"
                ") "
                "WHERE v.first_scan_at>=? AND v.first_scan_at<? AND (?='' OR c.person_type=?) "
                "AND (?='' OR lower(c.display_name) LIKE ? OR c.phone_e164 LIKE ? OR lower(COALESCE(m.membership_number,'')) LIKE ? OR lower(COALESCE(c.staff_designation,'')) LIKE ?) "
                "ORDER BY v.first_scan_at DESC,v.id DESC LIMIT ?",
                (start, end, ptype, ptype, needle, pattern, pattern, pattern, pattern, _bounded_limit(limit)),
            ).fetchall()
            events = connection.execute(
                "SELECT e.*,d.name AS device_name FROM attendance_events e JOIN biometric_devices d ON d.id=e.device_id "
                "WHERE e.event_time>=? AND e.event_time<? AND e.person_id IS NULL ORDER BY e.event_time DESC LIMIT 100",
                (start, end),
            ).fetchall()
        visits = [self._visit_payload(row) for row in rows]
        if mstatus:
            visits = [row for row in visits if row["membershipStatus"] == mstatus]
        return {"visits": visits, "unmatched": [self._unmatched_event_payload(row) for row in events]}

    def person_attendance(self, person_id: str) -> dict[str, object]:
        now = self._now()
        day_start, day_end, today = self._range_for_date("")
        current = datetime.fromtimestamp(now, tz=INDIA_ZONE)
        month_start = int(current.replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp())
        previous_month_end = month_start
        previous_month = (current.replace(day=1) - timedelta(days=1)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        previous_month_start = int(previous_month.timestamp())
        with self.database.session() as connection:
            person = connection.execute(
                "SELECT id,display_name,person_type,status FROM customers WHERE id=? AND status!='deleted'",
                (person_id,),
            ).fetchone()
            if person is None:
                raise BiometricNotFound("Person not found")
            today_row = connection.execute(
                "SELECT * FROM attendance_visits WHERE person_id=? AND first_scan_at>=? AND first_scan_at<? ORDER BY first_scan_at ASC LIMIT 1",
                (person_id, day_start, day_end),
            ).fetchone()
            counts = connection.execute(
                "SELECT "
                "SUM(CASE WHEN first_scan_at>=? THEN 1 ELSE 0 END) AS month_count,"
                "SUM(CASE WHEN first_scan_at>=? AND first_scan_at<? THEN 1 ELSE 0 END) AS previous_count,"
                "SUM(CASE WHEN first_scan_at>=? THEN 1 ELSE 0 END) AS week_count,"
                "SUM(CASE WHEN first_scan_at>=? THEN 1 ELSE 0 END) AS thirty_count "
                "FROM attendance_visits WHERE person_id=?",
                (month_start, previous_month_start, previous_month_end, now - 7 * 86400, now - 30 * 86400, person_id),
            ).fetchone()
            recent = connection.execute(
                "SELECT v.*,d.name AS device_name FROM attendance_visits v JOIN biometric_devices d ON d.id=v.device_id "
                "WHERE v.person_id=? ORDER BY v.first_scan_at DESC LIMIT 10",
                (person_id,),
            ).fetchall()
            mappings = self.list_mappings(person_id=person_id)
        return {
            "person": {"id": person["id"], "displayName": person["display_name"], "personType": person["person_type"], "status": person["status"]},
            "today": self._visit_payload(today_row) if today_row is not None else None,
            "todayLabel": today,
            "thisMonth": int(counts["month_count"] or 0),
            "lastMonth": int(counts["previous_count"] or 0),
            "last7Days": int(counts["week_count"] or 0),
            "last30Days": int(counts["thirty_count"] or 0),
            "lastVisit": self._visit_payload(recent[0]) if recent else None,
            "recentVisits": [self._visit_payload(row) for row in recent],
            "mappings": mappings,
        }

    def unmatched_activity(self, *, device_id: str = "") -> list[dict[str, object]]:
        clauses = ["e.person_id IS NULL"]
        args: list[object] = []
        if device_id:
            clauses.append("e.device_id=?")
            args.append(device_id)
        with self.database.session() as connection:
            rows = connection.execute(
                "SELECT e.device_id,e.device_user_id,d.name AS device_name,COUNT(*) AS events,MAX(e.event_time) AS last_seen,"
                "u.display_name AS device_display_name FROM attendance_events e "
                "JOIN biometric_devices d ON d.id=e.device_id "
                "LEFT JOIN biometric_device_users u ON u.device_id=e.device_id AND u.device_user_id=e.device_user_id "
                f"WHERE {' AND '.join(clauses)} GROUP BY e.device_id,e.device_user_id ORDER BY last_seen DESC LIMIT 200",
                args,
            ).fetchall()
        return [
            {
                "deviceId": row["device_id"],
                "deviceName": row["device_name"],
                "deviceUserId": row["device_user_id"],
                "deviceDisplayName": row["device_display_name"],
                "eventCount": int(row["events"]),
                "lastSeenAt": int(row["last_seen"]),
            }
            for row in rows
        ]

    def _range_for_date(self, value: str) -> tuple[int, int, str]:
        label = value.strip() if value else datetime.fromtimestamp(self._now(), tz=INDIA_ZONE).date().isoformat()
        try:
            day = datetime.fromisoformat(label).date()
        except ValueError as error:
            raise BiometricValidationError({"date": "Date must be YYYY-MM-DD"}) from error
        start = datetime(day.year, day.month, day.day, tzinfo=INDIA_ZONE)
        return int(start.timestamp()), int((start + timedelta(days=1)).timestamp()), day.isoformat()

    def _range_for_dates(self, start_date: str, end_date: str) -> tuple[int, int]:
        start, _unused, _label = self._range_for_date(start_date)
        if end_date:
            _end_start, end, _end_label = self._range_for_date(end_date)
        else:
            end = _unused
        if end <= start:
            raise BiometricValidationError({"endDate": "End date must be on or after start date"})
        if end - start > 366 * 86400:
            raise BiometricValidationError({"dateRange": "Date range cannot exceed one year"})
        return start, end

    def _visit_payload(self, row) -> dict[str, object] | None:
        if row is None:
            return None
        person_type = row["person_type"] if "person_type" in row.keys() else None
        membership_status = row["membership_status"] if "membership_status" in row.keys() else None
        if person_type == "member" and not membership_status:
            membership_status = "none"
        return {
            "id": row["id"],
            "personId": row["person_id"],
            "displayName": row["display_name"] if "display_name" in row.keys() else None,
            "personType": person_type,
            "personStatus": row["person_status"] if "person_status" in row.keys() else None,
            "staffDesignation": row["staff_designation"] if "staff_designation" in row.keys() else None,
            "membershipNumber": row["membership_number"] if "membership_number" in row.keys() else None,
            "membershipStatus": membership_status,
            "membershipEndsAt": row["membership_ends_at"] if "membership_ends_at" in row.keys() else None,
            "deviceId": row["device_id"],
            "deviceName": row["device_name"] if "device_name" in row.keys() else None,
            "date": row["visit_date"],
            "firstScanAt": int(row["first_scan_at"]),
            "lastScanAt": int(row["last_scan_at"]),
            "scanCount": int(row["scan_count"]),
            "verificationSummary": row["verification_summary"],
            "status": row["status"],
        }

    def _unmatched_event_payload(self, row) -> dict[str, object]:
        item = self._safe_event(row)
        item["deviceName"] = row["device_name"]
        return item

    def _reconcile_memberships(self, connection) -> None:
        now = self._now()
        connection.execute("UPDATE memberships SET status='expired',updated_at=? WHERE status='active' AND ends_at<?", (now, now))
        connection.execute("UPDATE memberships SET status='active',updated_at=? WHERE status='scheduled' AND starts_at<=?", (now, now))


def _merge_verification(existing: str | None, current: str) -> str:
    values = [item for item in str(existing or "").split(",") if item]
    if current not in values:
        values.append(current)
    return ",".join(values[:4])


def _bounded_limit(value: object, default: int = 200) -> int:
    try:
        return min(max(int(value), 1), 500)
    except (TypeError, ValueError):
        return default
