from contextlib import closing
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import os
import sqlite3
import unittest
from unittest import mock
import zipfile

from server.gravity.config import Settings
from server.gravity.database import Database
from server.gravity import operations as operations_module
from server.gravity.operations import BackupInvalid, BackupManager, RestoreUnsafe


ROOT = Path(__file__).resolve().parents[2]


class OperationsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        runtime = Path(self.temporary.name)
        base = Settings.load(root_dir=ROOT, environ={"SECRET_KEY": "x" * 40})
        self.settings = replace(
            base,
            root_dir=runtime,
            web_dir=ROOT / "web",
            migrations_dir=ROOT / "server" / "migrations",
            data_dir=runtime / "data",
            log_dir=runtime / "logs",
            backup_dir=runtime / "backups",
            database_path=runtime / "data" / "gravity.sqlite3",
        )
        self.settings.ensure_directories()
        self.database = Database(self.settings.database_path, self.settings.migrations_dir)
        self.database.migrate()
        with self.database.session() as connection:
            now = 1_800_000_000
            connection.execute(
                "INSERT INTO customers(id,status,display_name,created_at,updated_at) VALUES (?,?,?,?,?)",
                ("customer-1", "active", "Member One", now, now),
            )
        self.manager = BackupManager(self.settings, self.database)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_online_backup_verify_and_recovery_drill(self) -> None:
        backup = self.manager.create_backup("test")
        archive = Path(backup["path"])
        self.assertTrue(archive.is_file())
        self.assertEqual(archive.parent, self.settings.backup_dir)
        self.assertTrue(backup["verified"])
        verified = self.manager.verify_backup(archive)
        self.assertTrue(verified["valid"])
        self.assertEqual(verified["migrations"], 12)
        drill = self.manager.recovery_drill(archive)
        self.assertTrue(drill["drillPassed"])
        self.assertEqual(drill["customerRows"], 1)
        self.assertEqual(drill["membershipRows"], 0)
        with zipfile.ZipFile(archive) as handle:
            manifest = json.loads(handle.read("manifest.json"))
        self.assertNotIn("SECRET_KEY", json.dumps(manifest))

    def test_tampered_archive_is_rejected(self) -> None:
        original = Path(self.manager.create_backup("tamper")["path"])
        tampered = self.settings.backup_dir / "tampered.zip"
        with zipfile.ZipFile(original, "r") as source, zipfile.ZipFile(tampered, "w") as target:
            target.writestr("manifest.json", source.read("manifest.json"))
            target.writestr("gravity.sqlite3", source.read("gravity.sqlite3") + b"tamper")
        with self.assertRaises(BackupInvalid):
            self.manager.verify_backup(tampered)

    def test_restore_to_new_target_and_overwrite_guard(self) -> None:
        archive = Path(self.manager.create_backup("restore")["path"])
        target = Path(self.temporary.name) / "restored" / "gravity.sqlite3"
        result = self.manager.restore_backup(archive, target)
        self.assertTrue(result["restored"])
        with closing(sqlite3.connect(target)) as connection:
            count = connection.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
        self.assertEqual(count, 1)
        with self.assertRaises(RestoreUnsafe):
            self.manager.restore_backup(archive, target)

    def test_live_restore_requires_confirmation_and_stopped_server(self) -> None:
        archive = Path(self.manager.create_backup("live-guard")["path"])
        with self.assertRaises(RestoreUnsafe):
            self.manager.restore_backup(
                archive, self.settings.database_path, overwrite=True, allow_live=False
            )
        pid_file = self.settings.root_dir / ".gravity" / "gravity.pid"
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        pid_file.write_text(str(os.getpid()), encoding="ascii")
        with self.assertRaises(RestoreUnsafe):
            self.manager.restore_live(archive)

    def test_live_restore_creates_verified_safety_backup(self) -> None:
        archive = Path(self.manager.create_backup("baseline")["path"])
        with self.database.session() as connection:
            now = 1_800_000_100
            connection.execute(
                "INSERT INTO customers(id,status,display_name,created_at,updated_at) VALUES (?,?,?,?,?)",
                ("customer-2", "active", "Member Two", now, now),
            )
        result = self.manager.restore_live(archive)
        self.assertTrue(result["restored"])
        self.assertIsNotNone(result["safetyBackup"])
        safety = Path(str(result["safetyBackup"]))
        self.assertTrue(self.manager.verify_backup(safety)["valid"])
        with self.database.session() as connection:
            count = connection.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
        self.assertEqual(count, 1)
        drill = self.manager.recovery_drill(safety)
        self.assertEqual(drill["customerRows"], 2)


    def test_custom_runtime_pid_blocks_live_restore(self) -> None:
        archive = Path(self.manager.create_backup("custom-runtime-guard")["path"])
        runtime_dir = Path(self.temporary.name) / "custom-runtime"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        (runtime_dir / "gravity.pid").write_text(str(os.getpid()), encoding="ascii")
        with mock.patch.dict(os.environ, {"GRAVITY_RUNTIME_DIR": str(runtime_dir)}):
            with self.assertRaises(RestoreUnsafe):
                self.manager.restore_live(archive)

    def test_live_restore_removes_stale_sqlite_sidecars(self) -> None:
        archive = Path(self.manager.create_backup("sidecar-baseline")["path"])
        with self.database.session() as connection:
            now = 1_800_000_200
            connection.execute(
                "INSERT INTO customers(id,status,display_name,created_at,updated_at) VALUES (?,?,?,?,?)",
                ("customer-sidecar", "active", "Sidecar Member", now, now),
            )

        original_create_backup = self.manager.create_backup
        wal = Path(str(self.settings.database_path) + "-wal")
        shm = Path(str(self.settings.database_path) + "-shm")

        def create_safety_backup_then_sidecars(label: str = "manual") -> dict[str, object]:
            result = original_create_backup(label)
            wal.write_bytes(b"stale-wal")
            shm.write_bytes(b"stale-shm")
            return result

        with mock.patch.object(
            self.manager,
            "create_backup",
            side_effect=create_safety_backup_then_sidecars,
        ):
            result = self.manager.restore_live(archive)

        self.assertTrue(result["restored"])
        self.assertFalse(wal.exists())
        self.assertFalse(shm.exists())
        with self.database.session() as connection:
            count = connection.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
        self.assertEqual(count, 1)

    def test_malformed_manifest_is_rejected_as_backup_invalid(self) -> None:
        original = Path(self.manager.create_backup("bad-manifest")["path"])
        malformed = self.settings.backup_dir / "malformed-manifest.zip"
        with zipfile.ZipFile(original, "r") as source, zipfile.ZipFile(malformed, "w") as target:
            target.writestr("manifest.json", b"{not-json")
            target.writestr("gravity.sqlite3", source.read("gravity.sqlite3"))
        with self.assertRaises(BackupInvalid):
            self.manager.verify_backup(malformed)

    def test_posix_permission_error_pid_probe_fails_closed(self) -> None:
        with mock.patch.object(operations_module.os, "name", "posix"):
            with mock.patch.object(operations_module.os, "kill", side_effect=PermissionError):
                self.assertTrue(operations_module._pid_is_running(12345))


if __name__ == "__main__":
    unittest.main()
