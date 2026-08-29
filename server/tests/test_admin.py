from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import unittest

from server.gravity.admin import (
    AdminChallengeExpired,
    AdminConflict,
    AdminCsrfInvalid,
    AdminForbidden,
    AdminInvalidSecondFactor,
    AdminSessionInvalid,
    AdminValidationError,
    AdminService,
    _totp_code,
)
from server.gravity.config import Settings
from server.gravity.database import Database


ROOT = Path(__file__).resolve().parents[2]
TEST_SECRET = "phase-three-admin-secret-key-that-is-long-enough"


class MutableClock:
    def __init__(self, value: int = 2_100_000_000) -> None:
        self.value = value

    def __call__(self) -> float:
        return float(self.value)

    def advance(self, seconds: int) -> None:
        self.value += seconds


class AdminSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        root = Path(self.temporary.name)
        self.settings = Settings.load(
            root_dir=ROOT,
            environ={
                "SECRET_KEY": TEST_SECRET,
                "GRAVITY_DATA_DIR": str(root / "data"),
                "GRAVITY_LOG_DIR": str(root / "logs"),
                "GRAVITY_BACKUP_DIR": str(root / "backups"),
                "APP_BASE_URL": "http://127.0.0.1:8787",
            },
        )
        self.settings.ensure_directories()
        self.database = Database(self.settings.database_path, self.settings.migrations_dir)
        self.database.migrate()
        self.clock = MutableClock()
        self.service = AdminService(self.database, self.settings, clock=self.clock)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def bootstrap(self, username: str = "owner"):
        return self.service.bootstrap_owner(username, "Gravity!Owner123")

    def login(self, username: str, password: str, secret: str):
        challenge = self.service.begin_login(
            {"username": username, "password": password},
            "127.0.0.1",
        )
        code = _totp_code(secret, self.clock.value // 30)
        return self.service.verify_second_factor(
            challenge.challenge_token,
            code,
            remote_addr="127.0.0.1",
            user_agent="GravityAdminTest/1.0",
            request_id="test-request",
        )

    def test_bootstrap_totp_session_csrf_and_replay_protection(self):
        result = self.bootstrap()
        issue = self.login("owner", "Gravity!Owner123", result.totp_secret)
        session = self.service.resolve_session(issue.session_token)
        self.assertEqual(session.admin["role"], "owner")
        self.service.verify_csrf(session, issue.csrf_token, issue.csrf_token)
        with self.assertRaises(AdminCsrfInvalid):
            self.service.verify_csrf(session, "wrong", issue.csrf_token)

        challenge = self.service.begin_login(
            {"username": "owner", "password": "Gravity!Owner123"},
            "127.0.0.1",
        )
        reused_code = _totp_code(result.totp_secret, self.clock.value // 30)
        with self.assertRaises(AdminInvalidSecondFactor):
            self.service.verify_second_factor(
                challenge.challenge_token,
                reused_code,
                remote_addr="127.0.0.1",
                user_agent="GravityAdminTest/1.0",
                request_id="replay",
            )

        self.clock.advance(30)
        fresh = self.login("owner", "Gravity!Owner123", result.totp_secret)
        self.assertTrue(fresh.session_token)

    def test_recovery_code_is_one_time(self):
        result = self.bootstrap()
        challenge = self.service.begin_login(
            {"username": "owner", "password": "Gravity!Owner123"},
            "127.0.0.1",
        )
        recovery = result.recovery_codes[0]
        issue = self.service.verify_second_factor(
            challenge.challenge_token,
            recovery,
            remote_addr="127.0.0.1",
            user_agent="GravityAdminTest/1.0",
            request_id="recovery",
        )
        self.assertTrue(issue.session_token)
        challenge2 = self.service.begin_login(
            {"username": "owner", "password": "Gravity!Owner123"},
            "127.0.0.1",
        )
        with self.assertRaises(AdminInvalidSecondFactor):
            self.service.verify_second_factor(
                challenge2.challenge_token,
                recovery,
                remote_addr="127.0.0.1",
                user_agent="GravityAdminTest/1.0",
                request_id="recovery-reuse",
            )

    def test_owner_rbac_and_admin_session_revocation(self):
        owner = self.bootstrap()
        owner_issue = self.login("owner", "Gravity!Owner123", owner.totp_secret)
        owner_session = self.service.resolve_session(owner_issue.session_token)
        with self.assertRaises(AdminValidationError):
            self.service.create_admin(
                owner_session,
                "secondowner",
                "Gravity!Owner456",
                "owner",
            )
        with self.database.session() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM admin_users WHERE role='owner'").fetchone()[0], 1)
        trainer = self.service.create_admin(
            owner_session,
            "coach",
            "Gravity!Coach123",
            "trainer",
        )
        trainer_issue = self.login("coach", "Gravity!Coach123", trainer.totp_secret)
        trainer_session = self.service.resolve_session(trainer_issue.session_token)
        with self.assertRaises(AdminForbidden):
            self.service.list_admins(trainer_session)
        with self.assertRaises(AdminConflict):
            self.service.set_admin_status(
                owner_session, owner_session.admin_user_id, "disabled", request_id="self-disable"
            )
        self.service.set_admin_status(
            owner_session,
            str(trainer.admin["id"]),
            "disabled",
            request_id="disable-trainer",
        )
        with self.assertRaises(AdminSessionInvalid):
            self.service.resolve_session(trainer_issue.session_token)

    def test_reception_membership_permissions(self):
        owner = self.bootstrap()
        owner_issue = self.login("owner", "Gravity!Owner123", owner.totp_secret)
        owner_session = self.service.resolve_session(owner_issue.session_token)
        receptionist = self.service.create_admin(
            owner_session, "frontdesk", "Gravity!Desk123", "reception"
        )
        receptionist_issue = self.login(
            "frontdesk", "Gravity!Desk123", receptionist.totp_secret
        )
        receptionist_session = self.service.resolve_session(receptionist_issue.session_token)
        self.service.require_permission(receptionist_session, "memberships.manage")
        with self.assertRaises(AdminForbidden):
            self.service.require_permission(receptionist_session, "membership_plans.manage")
    def test_disabling_customer_revokes_customer_sessions(self):
        owner = self.bootstrap()
        owner_issue = self.login("owner", "Gravity!Owner123", owner.totp_secret)
        owner_session = self.service.resolve_session(owner_issue.session_token)
        now = self.clock.value
        with self.database.session() as connection:
            connection.execute(
                "INSERT INTO customers(id,status,display_name,created_at,updated_at) VALUES(?,?,?,?,?)",
                ("customer-1", "active", "Member One", now, now),
            )
            connection.execute(
                "INSERT INTO customer_sessions(id,customer_id,token_hash,csrf_hash,created_at,last_seen_at,idle_expires_at,absolute_expires_at) VALUES(?,?,?,?,?,?,?,?)",
                ("session-1", "customer-1", "token-hash", "csrf-hash", now, now, now + 600, now + 3600),
            )

        result = self.service.set_customer_status(
            owner_session,
            "customer-1",
            "disabled",
            request_id="disable-member",
        )
        self.assertEqual(result["status"], "disabled")
        with self.database.session() as connection:
            row = connection.execute(
                "SELECT revoked_at,revoke_reason FROM customer_sessions WHERE id='session-1'"
            ).fetchone()
        self.assertIsNotNone(row["revoked_at"])
        self.assertEqual(row["revoke_reason"], "admin_disabled")


if __name__ == "__main__":
    unittest.main()
