from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest

from server.gravity.coaching import (
    CoachingConflict,
    CoachingService,
    CoachingValidationError,
    GENERAL_NUTRITION_DISCLAIMER,
)
from server.gravity.config import Settings
from server.gravity.database import Database


ROOT = Path(__file__).resolve().parents[2]
TEST_SECRET = "phase-seven-coaching-test-secret-long-enough"


class MutableClock:
    def __init__(self, value: int) -> None:
        self.value = value

    def __call__(self) -> float:
        return float(self.value)

    def advance(self, seconds: int) -> None:
        self.value += seconds


class CoachingServiceTests(unittest.TestCase):
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
        self.clock = MutableClock(int(time.time()))
        self.service = CoachingService(self.database, clock=self.clock)
        with self.database.session() as connection:
            connection.execute(
                "INSERT INTO customers(id,status,display_name,created_at,updated_at) VALUES (?,?,?,?,?)",
                ("customer-1", "active", "Member One", self.clock.value, self.clock.value),
            )
            connection.execute(
                "INSERT INTO admin_users(id,username,password_hash,role,status,encrypted_totp_secret,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                ("trainer-1", "coach", "x", "trainer", "active", "x", self.clock.value, self.clock.value),
            )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_measurements_are_bounded_and_summary_is_server_owned(self) -> None:
        first = self.service.add_measurement(
            "customer-1", "weight_kg", 80.2,
            measured_at=None, actor_admin_user_id="trainer-1",
        )
        self.clock.advance(86400)
        second = self.service.add_measurement(
            "customer-1", "weight_kg", 79.4,
            measured_at=None, actor_admin_user_id="trainer-1",
        )
        summary = self.service.customer_summary("customer-1")
        self.assertEqual(summary["latestMeasurements"]["weight_kg"]["id"], second["id"])
        self.assertEqual(len(summary["measurementHistory"]), 2)
        self.assertEqual(first["unit"], "kg")
        with self.assertRaises(CoachingValidationError):
            self.service.add_measurement(
                "customer-1", "body_fat_pct", 99,
                measured_at=None, actor_admin_user_id="trainer-1",
            )

    def test_goal_replacement_preserves_history_and_completion(self) -> None:
        first = self.service.set_goal(
            "customer-1", "weight_kg", 75,
            target_at=self.clock.value + 90 * 86400,
            actor_admin_user_id="trainer-1",
        )
        self.clock.advance(60)
        second = self.service.set_goal(
            "customer-1", "weight_kg", 74,
            target_at=self.clock.value + 120 * 86400,
            actor_admin_user_id="trainer-1",
        )
        summary = self.service.customer_summary("customer-1")
        states = {item["id"]: item["status"] for item in summary["goals"]}
        self.assertEqual(states[first["id"]], "cancelled")
        self.assertEqual(states[second["id"]], "active")
        completed = self.service.complete_goal(
            "customer-1", second["id"], actor_admin_user_id="trainer-1",
        )
        self.assertEqual(completed["status"], "completed")
        with self.assertRaises(CoachingConflict):
            self.service.complete_goal("customer-1", second["id"], actor_admin_user_id="trainer-1")

    def test_diet_versions_are_immutable_and_assignments_keep_history(self) -> None:
        template = self.service.create_diet_template(
            "balanced-indian", "Balanced Indian", "General fitness meal structure",
            actor_admin_user_id="trainer-1",
        )
        with self.assertRaises(CoachingConflict):
            self.service.set_template_status(template["id"], "active", actor_admin_user_id="trainer-1")
        v1 = self.service.create_diet_version(
            template["id"], "Balanced Indian v1",
            {
                "dietType": "vegetarian",
                "meals": [
                    {"name": "Breakfast", "items": ["Poha with vegetables", "Curd"]},
                    {"name": "Lunch", "items": ["Dal", "Rice", "Mixed vegetables"]},
                ],
                "notes": ["Adjust portions with your coach."],
            },
            actor_admin_user_id="trainer-1",
        )
        self.service.set_template_status(template["id"], "active", actor_admin_user_id="trainer-1")
        first = self.service.assign_diet(
            "customer-1", v1["id"], note="Initial coaching plan",
            actor_admin_user_id="trainer-1",
        )
        self.assertEqual(first["plan"]["version"], 1)
        self.assertEqual(first["plan"]["disclaimer"], GENERAL_NUTRITION_DISCLAIMER)
        v2 = self.service.create_diet_version(
            template["id"], "Balanced Indian v2",
            {
                "dietType": "vegetarian",
                "meals": [
                    {"name": "Breakfast", "items": ["Besan chilla", "Fruit"]},
                    {"name": "Lunch", "items": ["Rajma", "Rice", "Salad"]},
                ],
                "notes": ["Hydration and portions should be individualized."],
            },
            actor_admin_user_id="trainer-1",
        )
        before = self.service.customer_summary("customer-1")
        self.assertEqual(before["currentDiet"]["plan"]["version"], 1)
        self.assertIn("Poha", before["currentDiet"]["plan"]["content"]["meals"][0]["items"][0])
        second = self.service.assign_diet(
            "customer-1", v2["id"], note="Updated coaching plan",
            actor_admin_user_id="trainer-1",
        )
        self.assertEqual(second["plan"]["version"], 2)
        after = self.service.customer_summary("customer-1")
        self.assertEqual(after["currentDiet"]["plan"]["version"], 2)
        self.assertEqual(after["dietHistory"][1]["status"], "ended")
        self.assertEqual(after["dietHistory"][1]["plan"]["version"], 1)
        self.assertEqual(self.service.list_diet_versions(template["id"])[1]["content"], v1["content"])

    def test_diet_content_rejects_unbounded_or_invalid_structure(self) -> None:
        template = self.service.create_diet_template(
            "simple-plan", "Simple Plan", None, actor_admin_user_id="trainer-1",
        )
        with self.assertRaises(CoachingValidationError):
            self.service.create_diet_version(
                template["id"], "Invalid", {"dietType": "medical", "meals": []},
                actor_admin_user_id="trainer-1",
            )
        with self.assertRaises(CoachingValidationError):
            self.service.create_diet_version(
                template["id"], "Invalid", {"dietType": "vegetarian", "meals": []},
                actor_admin_user_id="trainer-1",
            )
