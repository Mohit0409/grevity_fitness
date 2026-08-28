from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest

from server.gravity.config import Settings
from server.gravity.http import create_server
from server.gravity.smoke import run_smoke


ROOT = Path(__file__).resolve().parents[2]
TEST_SECRET = "phase-eleven-smoke-secret-long-enough"


@contextmanager
def running_server(*, active_plan: bool):
    with TemporaryDirectory() as temporary:
        runtime = Path(temporary)
        base = Settings.load(root_dir=ROOT, environ={
            "SECRET_KEY": TEST_SECRET,
            "GRAVITY_PORT": "0",
            "GRAVITY_LOG_LEVEL": "CRITICAL",
        })
        settings = replace(
            base,
            data_dir=runtime / "data",
            log_dir=runtime / "logs",
            backup_dir=runtime / "backups",
            database_path=runtime / "data" / "gravity.sqlite3",
            host="127.0.0.1",
            port=0,
        )
        server = create_server(settings)
        with server.database.session() as connection:
            if active_plan:
                connection.execute(
                    "UPDATE membership_plans SET status='active' WHERE code IN ('basic-monthly','pro-monthly','elite-monthly')"
                )
            else:
                connection.execute("UPDATE membership_plans SET status='inactive'")
        actual_base = f"http://127.0.0.1:{server.server_port}"
        server.settings = replace(server.settings, app_base_url=actual_base)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield actual_base
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


class LaunchSmokeTests(unittest.TestCase):
    def test_smoke_passes_public_private_and_security_boundaries(self):
        with running_server(active_plan=True) as base_url:
            report = run_smoke(base_url)
        self.assertTrue(report["ok"])
        failed = [check for check in report["checks"] if not check["ok"]]
        self.assertEqual(failed, [])

    def test_production_smoke_requires_https_transport(self):
        with running_server(active_plan=True) as base_url:
            report = run_smoke(base_url, require_https=True)
        self.assertFalse(report["ok"])
        transport = next(check for check in report["checks"] if check["name"] == "https_transport")
        self.assertFalse(transport["ok"])

    def test_smoke_fails_when_no_active_membership_plan_is_public(self):
        with running_server(active_plan=False) as base_url:
            report = run_smoke(base_url)
        self.assertFalse(report["ok"])
        catalog = next(
            check for check in report["checks"] if check["name"] == "active_membership_catalog"
        )
        self.assertFalse(catalog["ok"])
        self.assertEqual(catalog["status"], 200)
