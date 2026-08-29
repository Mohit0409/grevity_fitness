from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping
from urllib.request import Request, urlopen
import json

from .config import Settings
from .launch import LaunchGate


DEFAULT_SCHEDULER_MAX_AGE_MINUTES = 90.0
PROVIDER_KEYS = ("email", "sms", "whatsapp", "owner_email", "owner_phone", "owner_whatsapp")
PROVIDER_STATUSES = {
    "ready", "configured", "missing_recipient", "blocked_external_config", "blocked_adapter_missing",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp_age_minutes(value: object, now: datetime) -> float | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return round(max(0.0, (now - parsed.astimezone(timezone.utc)).total_seconds() / 60), 3)


def _read_object(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _safe_provider_readiness(value: object) -> dict[str, dict[str, str]]:
    if not isinstance(value, dict):
        return {}
    result = {}
    for key in PROVIDER_KEYS:
        item = value.get(key)
        status = item.get("status") if isinstance(item, dict) else None
        if status in PROVIDER_STATUSES:
            result[key] = {"status": str(status)}
    return result


def _default_backend_probe(url: str) -> Mapping[str, object]:
    request = Request(url, headers={"Accept": "application/json"})
    with urlopen(request, timeout=3) as response:
        if response.status != 200:
            return {}
        payload = json.loads(response.read() or b"{}")
    return payload if isinstance(payload, dict) else {}


class AdminHealthCheck:
    """PII-free daily operational status for the browser-admin deployment."""

    def __init__(
        self,
        settings: Settings,
        runtime_dir: Path,
        *,
        base_url: str | None = None,
        scheduler_max_age_minutes: float = DEFAULT_SCHEDULER_MAX_AGE_MINUTES,
        launch_gate: LaunchGate | None = None,
        backend_probe: Callable[[str], Mapping[str, object]] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.settings = settings
        self.runtime_dir = runtime_dir.expanduser().resolve()
        self.base_url = (base_url or f"http://127.0.0.1:{settings.port}").rstrip("/")
        self.scheduler_max_age_minutes = float(scheduler_max_age_minutes)
        self.launch_gate = launch_gate or LaunchGate(settings)
        self.backend_probe = backend_probe or _default_backend_probe
        self.clock = clock or _utc_now

    def _backend_state(self) -> dict[str, object]:
        try:
            payload = self.backend_probe(f"{self.base_url}/api/health")
        except Exception:
            payload = {}
        healthy = bool(
            payload.get("service") == "Gravity Fitness"
            and payload.get("status") == "ok"
            and payload.get("database") == "ok"
        )
        return {"healthy": healthy, "status": "ok" if healthy else "unavailable"}

    def _scheduler_state(self) -> dict[str, object]:
        state = _read_object(self.runtime_dir / "notification-state.json")
        now = self.clock()
        scan_age = _timestamp_age_minutes(state.get("last_successful_scan_at"), now)
        delivery_age = _timestamp_age_minutes(state.get("last_successful_delivery_at"), now)
        last_report = state.get("last_report")
        report_status = last_report.get("status") if isinstance(last_report, dict) else None
        consecutive_failures = state.get("consecutive_failures", 0)
        try:
            consecutive_failures = max(0, int(consecutive_failures))
        except (TypeError, ValueError):
            consecutive_failures = 0
        recent = bool(
            scan_age is not None
            and delivery_age is not None
            and scan_age <= self.scheduler_max_age_minutes
            and delivery_age <= self.scheduler_max_age_minutes
        )
        healthy = bool(recent and report_status == "ok" and consecutive_failures == 0)
        if healthy:
            status = "ok"
        elif not state:
            status = "never_run"
        elif report_status == "failed" or consecutive_failures:
            status = "failed"
        else:
            status = "stale"
        readiness = state.get("provider_readiness")
        return {
            "healthy": healthy,
            "status": status,
            "lastScanAgeMinutes": scan_age,
            "lastDeliveryAgeMinutes": delivery_age,
            "maxAgeMinutes": self.scheduler_max_age_minutes,
            "consecutiveFailures": consecutive_failures,
            "providerReadiness": _safe_provider_readiness(readiness),
        }

    def report(self) -> dict[str, object]:
        launch = self.launch_gate.report()
        operations = launch.get("operations") if isinstance(launch, dict) else {}
        readiness = launch.get("readiness") if isinstance(launch, dict) else {}
        database = operations.get("database") if isinstance(operations, dict) else {}
        backup = operations.get("backup") if isinstance(operations, dict) else {}
        notification_providers = readiness.get("notifications") if isinstance(readiness, dict) else {}
        backend = self._backend_state()
        scheduler = self._scheduler_state()
        provider_ready = any(
            isinstance(item, dict) and item.get("status") == "ready"
            for item in notification_providers.values()
        ) if isinstance(notification_providers, dict) else False

        checks = {
            "backend": bool(backend["healthy"]),
            "database": bool(isinstance(database, dict) and database.get("healthy")),
            "migrations": bool(isinstance(database, dict) and database.get("migrationsCurrent")),
            "backup": bool(
                isinstance(backup, dict)
                and backup.get("verified")
                and backup.get("recent")
                and backup.get("recoveryDrillPassed")
            ),
            "notificationScheduler": bool(scheduler["healthy"]),
            "notificationProvider": provider_ready,
            "productionConfiguration": bool(launch.get("launchReady")) if isinstance(launch, dict) else False,
        }
        blockers = [name for name, passed in checks.items() if not passed]
        return {
            "healthy": not blockers,
            "blockers": blockers,
            "checks": checks,
            "backend": backend,
            "database": database if isinstance(database, dict) else {},
            "backup": backup if isinstance(backup, dict) else {},
            "notificationScheduler": scheduler,
            "providerReadiness": notification_providers if isinstance(notification_providers, dict) else {},
            "productionConfigurationReady": bool(launch.get("launchReady")) if isinstance(launch, dict) else False,
            "productionConfigurationBlockers": list(launch.get("blockers") or []) if isinstance(launch, dict) else [],
        }
