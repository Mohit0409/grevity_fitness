from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
import sqlite3

from .admin import AdminService
from .config import Settings
from .database import Database
from .membership import MembershipService
from .operations import BackupManager, OperationsError
from .readiness import ReadinessService


DEFAULT_BACKUP_MAX_AGE_HOURS = 24.0


class LaunchGate:
    def __init__(
        self,
        settings: Settings,
        database: Database | None = None,
        *,
        backup_max_age_hours: float = DEFAULT_BACKUP_MAX_AGE_HOURS,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.settings = settings
        self.database = database or Database(settings.database_path, settings.migrations_dir)
        self.backup_max_age_hours = float(backup_max_age_hours)
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _database_state(self) -> dict[str, object]:
        expected = len(tuple(self.settings.migrations_dir.glob("*.sql")))
        if not self.settings.database_path.is_file():
            return {
                "healthy": False,
                "migrationsCurrent": False,
                "appliedMigrations": 0,
                "expectedMigrations": expected,
            }
        health = self.database.health()
        try:
            applied = int(health.get("migrations", "0"))
        except (TypeError, ValueError):
            applied = 0
        healthy = health.get("database") == "ok"
        return {
            "healthy": healthy,
            "migrationsCurrent": healthy and applied == expected,
            "appliedMigrations": applied,
            "expectedMigrations": expected,
        }

    def _business_state(self, database_ready: bool) -> dict[str, object]:
        if not database_ready:
            return {"activeOwner": False, "activePlanCount": 0}
        try:
            active_owner = not AdminService(self.database, self.settings).bootstrap_required()
            active_plans = MembershipService(self.database).list_plans(active_only=True)
        except (OSError, RuntimeError, sqlite3.Error):
            return {"activeOwner": False, "activePlanCount": 0}
        return {"activeOwner": active_owner, "activePlanCount": len(active_plans)}

    def _backup_state(self) -> dict[str, object]:
        state: dict[str, object] = {
            "archive": None,
            "verified": False,
            "recoveryDrillPassed": False,
            "ageHours": None,
            "maxAgeHours": self.backup_max_age_hours,
            "recent": False,
            "migrationsCurrent": False,
            "containsActiveOwner": False,
            "activePlanCount": 0,
        }
        try:
            archives = sorted(
                self.settings.backup_dir.glob("gravity-*.zip"),
                key=lambda item: item.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            return state
        if not archives:
            return state
        archive = archives[0]
        state["archive"] = archive.name
        manager = BackupManager(self.settings, self.database)
        try:
            verification = manager.verify_backup(archive)
            state["verified"] = bool(verification.get("valid"))
            expected_migrations = len(tuple(self.settings.migrations_dir.glob("*.sql")))
            state["migrationsCurrent"] = verification.get("migrations") == expected_migrations
            created_raw = verification.get("createdAt")
            if isinstance(created_raw, str):
                created = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                age = max(0.0, (self.clock() - created.astimezone(timezone.utc)).total_seconds() / 3600)
                state["ageHours"] = round(age, 3)
                state["recent"] = age <= self.backup_max_age_hours
            drill = manager.recovery_drill(archive)
            state["recoveryDrillPassed"] = bool(drill.get("drillPassed"))
            state["containsActiveOwner"] = int(drill.get("activeOwnerRows", 0)) > 0
            state["activePlanCount"] = int(drill.get("activePlanRows", 0))
        except (OperationsError, OSError, TypeError, ValueError):
            return state
        return state

    def report(self) -> dict[str, object]:
        readiness = ReadinessService(self.settings).report()
        database = self._database_state()
        database_ready = bool(database["healthy"] and database["migrationsCurrent"])
        business = self._business_state(database_ready)
        backup = self._backup_state()

        blockers = list(readiness["blockers"])
        for code, ready in (
            ("database_health", database["healthy"]),
            ("database_migrations", database["migrationsCurrent"]),
            ("active_owner", business["activeOwner"]),
            ("active_membership_plan", int(business["activePlanCount"]) > 0),
            ("recent_verified_backup", backup["verified"] and backup["recent"]),
            ("backup_migrations", backup["migrationsCurrent"]),
            ("recovery_drill", backup["recoveryDrillPassed"]),
            ("backup_active_owner", backup["containsActiveOwner"]),
            ("backup_active_membership_plan", int(backup["activePlanCount"]) > 0),
        ):
            if not ready and code not in blockers:
                blockers.append(code)

        return {
            "launchReady": not blockers,
            "blockers": blockers,
            "readiness": readiness,
            "operations": {
                "database": database,
                "business": business,
                "backup": backup,
            },
        }
