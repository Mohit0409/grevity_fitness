from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import ctypes
import json
import os
import re
import shutil
import sqlite3
import zipfile

from .config import Settings
from .database import Database


BACKUP_FORMAT_VERSION = 1
BACKUP_DATABASE_NAME = "gravity.sqlite3"
BACKUP_MANIFEST_NAME = "manifest.json"
LABEL_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")


class OperationsError(Exception):
    pass


class BackupInvalid(OperationsError):
    pass


class RestoreUnsafe(OperationsError):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: datetime) -> str:
    return value.strftime("%Y%m%dT%H%M%S%fZ")


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        process_query_limited_information = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            process_query_limited_information, False, pid
        )
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _inspect_database(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise BackupInvalid("Database file is missing")
    try:
        connection = sqlite3.connect(path)
        connection.row_factory = sqlite3.Row
        quick_check = connection.execute("PRAGMA quick_check").fetchone()[0]
        foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
        table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
        ).fetchone()
        if quick_check != "ok" or foreign_key_errors or table is None:
            raise BackupInvalid("Database integrity validation failed")
        migrations = [
            {
                "version": row["version"],
                "name": row["name"],
                "checksum": row["checksum"],
            }
            for row in connection.execute(
                "SELECT version,name,checksum FROM schema_migrations ORDER BY version"
            ).fetchall()
        ]
        stage_row = connection.execute(
            "SELECT value FROM app_metadata WHERE key='schema_stage'"
        ).fetchone()
    except sqlite3.Error as error:
        raise BackupInvalid("Database could not be inspected") from error
    finally:
        if "connection" in locals():
            connection.close()
    return {
        "quickCheck": "ok",
        "foreignKeyErrors": 0,
        "migrations": migrations,
        "schemaStage": stage_row["value"] if stage_row else None,
    }


class BackupManager:
    def __init__(self, settings: Settings, database: Database | None = None) -> None:
        self.settings = settings
        self.database = database or Database(settings.database_path, settings.migrations_dir)

    def pid_files(self) -> tuple[Path, ...]:
        defaults = [self.settings.root_dir / ".gravity" / "gravity.pid"]
        runtime = os.environ.get("GRAVITY_RUNTIME_DIR", "").strip()
        if runtime:
            custom = Path(runtime).expanduser()
            if not custom.is_absolute():
                custom = self.settings.root_dir / custom
            candidate = custom.resolve() / "gravity.pid"
            if candidate not in defaults:
                defaults.append(candidate)
        return tuple(defaults)

    def server_running(self) -> bool:
        for pid_file in self.pid_files():
            if not pid_file.is_file():
                continue
            try:
                pid = int(pid_file.read_text(encoding="ascii").strip())
            except (OSError, ValueError):
                continue
            if _pid_is_running(pid):
                return True
        return False

    def _online_copy(self, target: Path) -> None:
        source_path = self.settings.database_path
        if not source_path.is_file():
            raise OperationsError("Gravity database does not exist")
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            source = sqlite3.connect(source_path, timeout=10)
            destination = sqlite3.connect(target)
            with destination:
                source.backup(destination)
        except sqlite3.Error as error:
            raise OperationsError("SQLite backup failed") from error
        finally:
            if "destination" in locals():
                destination.close()
            if "source" in locals():
                source.close()

    def create_backup(self, label: str = "manual") -> dict[str, object]:
        normalized = label.strip().lower()
        if not LABEL_PATTERN.fullmatch(normalized):
            raise OperationsError("Backup label must use lowercase letters, numbers, or hyphens")
        self.settings.ensure_directories()
        created = _utc_now()
        archive_name = f"gravity-{normalized}-{_timestamp(created)}.zip"
        archive_path = self.settings.backup_dir / archive_name
        temporary_archive = archive_path.with_suffix(".zip.tmp")
        with TemporaryDirectory(dir=self.settings.backup_dir) as temporary:
            temp_root = Path(temporary)
            database_copy = temp_root / BACKUP_DATABASE_NAME
            self._online_copy(database_copy)
            inspection = _inspect_database(database_copy)
            manifest = {
                "formatVersion": BACKUP_FORMAT_VERSION,
                "createdAt": created.isoformat(),
                "databaseFile": BACKUP_DATABASE_NAME,
                "databaseBytes": database_copy.stat().st_size,
                "databaseSha256": _sha256_file(database_copy),
                "schemaStage": inspection["schemaStage"],
                "migrations": inspection["migrations"],
            }
            manifest_path = temp_root / BACKUP_MANIFEST_NAME
            manifest_path.write_text(
                json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
            )
            with zipfile.ZipFile(temporary_archive, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.write(database_copy, BACKUP_DATABASE_NAME)
                archive.write(manifest_path, BACKUP_MANIFEST_NAME)
            os.replace(temporary_archive, archive_path)
        try:
            os.chmod(archive_path, 0o600)
        except OSError:
            pass
        verification = self.verify_backup(archive_path)
        return {
            "path": str(archive_path),
            "createdAt": manifest["createdAt"],
            "databaseSha256": manifest["databaseSha256"],
            "migrations": len(manifest["migrations"]),
            "archiveSha256": _sha256_file(archive_path),
            "verified": bool(verification["valid"]),
        }

    def _materialize_archive(self, archive_path: Path, destination: Path) -> dict[str, object]:
        if not archive_path.is_file():
            raise BackupInvalid("Backup archive does not exist")
        try:
            with zipfile.ZipFile(archive_path, "r") as archive:
                names = set(archive.namelist())
                expected = {BACKUP_DATABASE_NAME, BACKUP_MANIFEST_NAME}
                if names != expected:
                    raise BackupInvalid("Backup archive contains unexpected files")
                manifest = json.loads(archive.read(BACKUP_MANIFEST_NAME).decode("utf-8"))
                with archive.open(BACKUP_DATABASE_NAME, "r") as source, destination.open("wb") as target:
                    shutil.copyfileobj(source, target)
        except (OSError, zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise BackupInvalid("Backup archive could not be read") from error
        if not isinstance(manifest, dict):
            raise BackupInvalid("Backup manifest must be a JSON object")
        if manifest.get("formatVersion") != BACKUP_FORMAT_VERSION:
            raise BackupInvalid("Unsupported backup format version")
        if manifest.get("databaseFile") != BACKUP_DATABASE_NAME:
            raise BackupInvalid("Backup manifest database name is invalid")
        return manifest

    def verify_backup(self, archive_path: Path) -> dict[str, object]:
        archive_path = archive_path.expanduser().resolve()
        with TemporaryDirectory() as temporary:
            restored = Path(temporary) / BACKUP_DATABASE_NAME
            manifest = self._materialize_archive(archive_path, restored)
            actual_hash = _sha256_file(restored)
            if actual_hash != manifest.get("databaseSha256"):
                raise BackupInvalid("Backup database checksum does not match manifest")
            try:
                expected_size = int(manifest.get("databaseBytes", -1))
            except (TypeError, ValueError) as error:
                raise BackupInvalid("Backup manifest database size is invalid") from error
            if restored.stat().st_size != expected_size:
                raise BackupInvalid("Backup database size does not match manifest")
            inspection = _inspect_database(restored)
            if inspection["migrations"] != manifest.get("migrations"):
                raise BackupInvalid("Backup migration inventory does not match manifest")
            if inspection["schemaStage"] != manifest.get("schemaStage"):
                raise BackupInvalid("Backup schema stage does not match manifest")
        return {
            "valid": True,
            "path": str(archive_path),
            "createdAt": manifest.get("createdAt"),
            "databaseSha256": actual_hash,
            "migrations": len(inspection["migrations"]),
            "schemaStage": inspection["schemaStage"],
        }

    def restore_backup(
        self,
        archive_path: Path,
        target_path: Path,
        *,
        overwrite: bool = False,
        allow_live: bool = False,
    ) -> dict[str, object]:
        archive_path = archive_path.expanduser().resolve()
        target_path = target_path.expanduser().resolve()
        verification = self.verify_backup(archive_path)
        live_target = target_path == self.settings.database_path.resolve()
        if live_target and not allow_live:
            raise RestoreUnsafe("Live database restore requires explicit confirmation")
        if live_target and self.server_running():
            raise RestoreUnsafe("Stop Gravity Fitness before restoring the live database")
        if target_path.exists() and not overwrite:
            raise RestoreUnsafe("Restore target already exists")

        safety_backup = None
        if live_target and target_path.exists():
            safety_backup = self.create_backup("pre-restore")["path"]
            for suffix in ("-wal", "-shm"):
                sidecar = Path(str(target_path) + suffix)
                if sidecar.exists():
                    sidecar.unlink()
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=target_path.parent) as temporary:
            candidate = Path(temporary) / BACKUP_DATABASE_NAME
            manifest = self._materialize_archive(archive_path, candidate)
            if _sha256_file(candidate) != manifest.get("databaseSha256"):
                raise BackupInvalid("Restore candidate checksum does not match manifest")
            inspection = _inspect_database(candidate)
            if inspection["migrations"] != manifest.get("migrations"):
                raise BackupInvalid("Restore candidate migration inventory is invalid")
            os.replace(candidate, target_path)
        try:
            os.chmod(target_path, 0o600)
        except OSError:
            pass
        post = _inspect_database(target_path)
        return {
            "restored": True,
            "target": str(target_path),
            "source": str(archive_path),
            "safetyBackup": safety_backup,
            "databaseSha256": verification["databaseSha256"],
            "migrations": len(post["migrations"]),
            "schemaStage": post["schemaStage"],
        }

    def recovery_drill(self, archive_path: Path) -> dict[str, object]:
        with TemporaryDirectory() as temporary:
            target = Path(temporary) / "recovered.sqlite3"
            restored = self.restore_backup(
                archive_path,
                target,
                overwrite=False,
                allow_live=False,
            )
            inspection = _inspect_database(target)
            try:
                connection = sqlite3.connect(target)
                customer_count = connection.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
                membership_count = connection.execute("SELECT COUNT(*) FROM memberships").fetchone()[0]
                payment_count = connection.execute("SELECT COUNT(*) FROM payment_intents").fetchone()[0]
                paid_payment_count = connection.execute(
                    "SELECT COUNT(*) FROM payment_intents WHERE status='paid'"
                ).fetchone()[0]
                payment_amount_paise = connection.execute(
                    "SELECT COALESCE(SUM(amount_paise),0) FROM payment_intents"
                ).fetchone()[0]
                paid_payment_amount_paise = connection.execute(
                    "SELECT COALESCE(SUM(amount_paise),0) FROM payment_intents WHERE status='paid'"
                ).fetchone()[0]
                has_manual_ledger = connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='membership_payments'"
                ).fetchone() is not None
                if has_manual_ledger:
                    manual_payment_count = connection.execute(
                        "SELECT COUNT(*) FROM membership_payments"
                    ).fetchone()[0]
                    recorded_manual_payment_count = connection.execute(
                        "SELECT COUNT(*) FROM membership_payments WHERE status='recorded'"
                    ).fetchone()[0]
                    manual_payment_amount_paise = connection.execute(
                        "SELECT COALESCE(SUM(amount_paise),0) FROM membership_payments"
                    ).fetchone()[0]
                    recorded_manual_payment_amount_paise = connection.execute(
                        "SELECT COALESCE(SUM(amount_paise),0) FROM membership_payments WHERE status='recorded'"
                    ).fetchone()[0]
                else:
                    manual_payment_count = 0
                    recorded_manual_payment_count = 0
                    manual_payment_amount_paise = 0
                    recorded_manual_payment_amount_paise = 0
                reminder_count = connection.execute(
                    "SELECT COUNT(*) FROM notification_reminders"
                ).fetchone()[0]
                delivery_count = connection.execute(
                    "SELECT COUNT(*) FROM notification_deliveries"
                ).fetchone()[0]
                active_owner_count = connection.execute(
                    "SELECT COUNT(*) FROM admin_users WHERE role='owner' AND status='active'"
                ).fetchone()[0]
                active_plan_count = connection.execute(
                    "SELECT COUNT(*) FROM membership_plans WHERE status='active'"
                ).fetchone()[0]
            except sqlite3.Error as error:
                raise BackupInvalid("Recovered database could not answer application queries") from error
            finally:
                if "connection" in locals():
                    connection.close()
        return {
            "drillPassed": True,
            "archive": str(archive_path.expanduser().resolve()),
            "migrations": len(inspection["migrations"]),
            "schemaStage": inspection["schemaStage"],
            "customerRows": int(customer_count),
            "membershipRows": int(membership_count),
            "paymentRows": int(payment_count),
            "paidPaymentRows": int(paid_payment_count),
            "paymentAmountPaise": int(payment_amount_paise),
            "paidPaymentAmountPaise": int(paid_payment_amount_paise),
            "manualPaymentRows": int(manual_payment_count),
            "recordedManualPaymentRows": int(recorded_manual_payment_count),
            "manualPaymentAmountPaise": int(manual_payment_amount_paise),
            "recordedManualPaymentAmountPaise": int(recorded_manual_payment_amount_paise),
            "notificationReminderRows": int(reminder_count),
            "notificationDeliveryRows": int(delivery_count),
            "activeOwnerRows": int(active_owner_count),
            "activePlanRows": int(active_plan_count),
            "databaseSha256": restored["databaseSha256"],
        }

    def restore_live(self, archive_path: Path) -> dict[str, object]:
        return self.restore_backup(
            archive_path,
            self.settings.database_path,
            overwrite=True,
            allow_live=True,
        )
