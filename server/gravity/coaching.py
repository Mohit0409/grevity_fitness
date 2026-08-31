from __future__ import annotations

from typing import Callable
from uuid import uuid4
import json
import re
import time

from .database import Database


GENERAL_NUTRITION_DISCLAIMER = (
    "General fitness nutrition guidance only. Not medical advice, diagnosis, or treatment. "
    "For medical conditions, allergies, pregnancy, eating disorders, or clinical nutrition needs, "
    "consult a qualified healthcare professional."
)

MEASUREMENT_SPECS = {
    "weight_kg": ("kg", 20.0, 500.0),
    "body_fat_pct": ("percent", 1.0, 75.0),
    "waist_cm": ("cm", 30.0, 300.0),
    "chest_cm": ("cm", 40.0, 300.0),
    "arm_cm": ("cm", 10.0, 100.0),
    "thigh_cm": ("cm", 20.0, 150.0),
}
GOAL_SPECS = {
    "weight_kg": ("kg", 20.0, 500.0),
    "body_fat_pct": ("percent", 1.0, 75.0),
    "waist_cm": ("cm", 30.0, 300.0),
    "workouts_per_week": ("sessions_per_week", 1.0, 14.0),
}
CODE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{2,63}$")

class CoachingError(Exception):
    pass


class CoachingNotFound(CoachingError):
    pass


class CoachingConflict(CoachingError):
    pass


class CoachingValidationError(CoachingError):
    def __init__(self, fields: dict[str, str]):
        super().__init__("Coaching validation failed")
        self.fields = fields

def _bounded_text(value: object, field: str, *, maximum: int, required: bool = True) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str):
        raise CoachingValidationError({field: "Enter valid text"})
    cleaned = " ".join(value.split())
    if required and not cleaned:
        raise CoachingValidationError({field: "This field is required"})
    if len(cleaned) > maximum:
        raise CoachingValidationError({field: f"Use at most {maximum} characters"})
    return cleaned or None


def _number(value: object, field: str, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise CoachingValidationError({field: "Enter a valid number"}) from error
    if not minimum <= number <= maximum:
        raise CoachingValidationError({field: f"Use a value between {minimum:g} and {maximum:g}"})
    return round(number, 2)


class CoachingService:
    def __init__(self, database: Database, *, clock: Callable[[], float] | None = None) -> None:
        self.database = database
        self.clock = clock or time.time

    def _now(self) -> int:
        return int(self.clock())

    def _customer(self, connection, customer_id: str):
        row = connection.execute(
            "SELECT id,status,display_name,person_type FROM customers WHERE id=?",
            (customer_id,),
        ).fetchone()
        if row is None or row["status"] == "deleted" or row["person_type"] != "member":
            raise CoachingNotFound("Customer not found")
        return row

    @staticmethod
    def _safe_goal(row) -> dict[str, object]:
        return {
            "id": row["id"],
            "metricKey": row["metric_key"],
            "targetValue": float(row["target_value"]),
            "unit": row["unit"],
            "status": row["status"],
            "targetAt": row["target_at"],
            "completedAt": row["completed_at"],
            "createdAt": int(row["created_at"]),
            "updatedAt": int(row["updated_at"]),
        }

    @staticmethod
    def _safe_measurement(row) -> dict[str, object]:
        return {
            "id": row["id"],
            "metricKey": row["metric_key"],
            "value": float(row["value"]),
            "unit": row["unit"],
            "measuredAt": int(row["measured_at"]),
            "createdAt": int(row["created_at"]),
        }

    def add_measurement(
        self,
        customer_id: str,
        metric_key: str,
        value: object,
        *,
        measured_at: object | None,
        actor_admin_user_id: str,
    ) -> dict[str, object]:
        if metric_key not in MEASUREMENT_SPECS:
            raise CoachingValidationError({"metricKey": "Unsupported progress metric"})
        unit, minimum, maximum = MEASUREMENT_SPECS[metric_key]
        measured_value = _number(value, "value", minimum, maximum)
        now = self._now()
        timestamp = now if measured_at is None else int(measured_at)
        if timestamp > now + 300 or timestamp < now - 10 * 365 * 86400:
            raise CoachingValidationError({"measuredAt": "Measurement time is outside the allowed range"})
        with self.database.session() as connection:
            self._customer(connection, customer_id)
            measurement_id = uuid4().hex
            connection.execute(
                "INSERT INTO progress_measurements(id,customer_id,metric_key,value,unit,measured_at,created_by_admin_user_id,created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (measurement_id, customer_id, metric_key, measured_value, unit, timestamp, actor_admin_user_id, now),
            )
            row = connection.execute("SELECT * FROM progress_measurements WHERE id=?", (measurement_id,)).fetchone()
        return self._safe_measurement(row)

    def set_goal(
        self,
        customer_id: str,
        metric_key: str,
        target_value: object,
        *,
        target_at: object | None,
        actor_admin_user_id: str,
    ) -> dict[str, object]:
        if metric_key not in GOAL_SPECS:
            raise CoachingValidationError({"metricKey": "Unsupported goal metric"})
        unit, minimum, maximum = GOAL_SPECS[metric_key]
        target = _number(target_value, "targetValue", minimum, maximum)
        now = self._now()
        target_timestamp = None if target_at in (None, "") else int(target_at)
        if target_timestamp is not None and target_timestamp <= now:
            raise CoachingValidationError({"targetAt": "Goal target time must be in the future"})
        with self.database.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._customer(connection, customer_id)
            connection.execute(
                "UPDATE progress_goals SET status='cancelled',updated_at=? "
                "WHERE customer_id=? AND metric_key=? AND status='active'",
                (now, customer_id, metric_key),
            )
            goal_id = uuid4().hex
            connection.execute(
                "INSERT INTO progress_goals(id,customer_id,metric_key,target_value,unit,status,target_at,created_by_admin_user_id,created_at,updated_at) "
                "VALUES (?,?,?,?,?,'active',?,?,?,?)",
                (goal_id, customer_id, metric_key, target, unit, target_timestamp, actor_admin_user_id, now, now),
            )
            row = connection.execute("SELECT * FROM progress_goals WHERE id=?", (goal_id,)).fetchone()
            connection.commit()
        return self._safe_goal(row)

    def complete_goal(self, customer_id: str, goal_id: str, *, actor_admin_user_id: str) -> dict[str, object]:
        now = self._now()
        with self.database.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM progress_goals WHERE id=? AND customer_id=?",
                (goal_id, customer_id),
            ).fetchone()
            if row is None:
                raise CoachingNotFound("Goal not found")
            if row["status"] != "active":
                raise CoachingConflict("Goal is not active")
            connection.execute(
                "UPDATE progress_goals SET status='completed',completed_at=?,updated_at=? WHERE id=?",
                (now, now, goal_id),
            )
            row = connection.execute("SELECT * FROM progress_goals WHERE id=?", (goal_id,)).fetchone()
            connection.commit()
        return self._safe_goal(row)

    @staticmethod
    def _validate_diet_content(payload: object) -> dict[str, object]:
        if not isinstance(payload, dict):
            raise CoachingValidationError({"content": "Diet content must be an object"})
        diet_type = payload.get("dietType", "vegetarian")
        if diet_type not in {"vegetarian", "eggetarian", "vegan", "non_vegetarian"}:
            raise CoachingValidationError({"dietType": "Unsupported diet type"})
        meals = payload.get("meals")
        if not isinstance(meals, list) or not 1 <= len(meals) <= 10:
            raise CoachingValidationError({"meals": "Provide between 1 and 10 meal sections"})
        safe_meals: list[dict[str, object]] = []
        for meal in meals:
            if not isinstance(meal, dict):
                raise CoachingValidationError({"meals": "Each meal must be an object"})
            name = _bounded_text(meal.get("name"), "mealName", maximum=80)
            items = meal.get("items")
            if not isinstance(items, list) or not 1 <= len(items) <= 12:
                raise CoachingValidationError({"items": "Each meal needs 1 to 12 items"})
            safe_items = [_bounded_text(item, "item", maximum=180) for item in items]
            safe_meals.append({"name": name, "items": safe_items})
        notes = payload.get("notes", [])
        if not isinstance(notes, list) or len(notes) > 10:
            raise CoachingValidationError({"notes": "Use at most 10 notes"})
        safe_notes = [_bounded_text(note, "note", maximum=240) for note in notes]
        return {"dietType": diet_type, "meals": safe_meals, "notes": safe_notes}

    @staticmethod
    def _safe_template(row) -> dict[str, object]:
        return {
            "id": row["id"],
            "code": row["code"],
            "name": row["name"],
            "description": row["description"],
            "status": row["status"],
            "createdAt": int(row["created_at"]),
            "updatedAt": int(row["updated_at"]),
        }

    @staticmethod
    def _safe_version(row) -> dict[str, object]:
        return {
            "id": row["id"],
            "templateId": row["template_id"],
            "version": int(row["version_number"]),
            "title": row["title"],
            "content": json.loads(row["content_json"]),
            "disclaimer": row["disclaimer"],
            "createdAt": int(row["created_at"]),
        }

    def create_diet_template(
        self,
        code: object,
        name: object,
        description: object,
        *,
        actor_admin_user_id: str,
    ) -> dict[str, object]:
        clean_code = _bounded_text(code, "code", maximum=64)
        if not CODE_PATTERN.fullmatch(clean_code or ""):
            raise CoachingValidationError({"code": "Use lowercase letters, numbers, hyphens, or underscores"})
        clean_name = _bounded_text(name, "name", maximum=100)
        clean_description = _bounded_text(description, "description", maximum=400, required=False)
        now = self._now()
        template_id = uuid4().hex
        with self.database.session() as connection:
            try:
                connection.execute(
                    "INSERT INTO diet_plan_templates(id,code,name,description,status,created_by_admin_user_id,created_at,updated_at) "
                    "VALUES (?,?,?,?,'inactive',?,?,?)",
                    (template_id, clean_code, clean_name, clean_description, actor_admin_user_id, now, now),
                )
            except Exception as error:
                if "UNIQUE" in str(error).upper():
                    raise CoachingConflict("Diet template code already exists") from error
                raise
            row = connection.execute("SELECT * FROM diet_plan_templates WHERE id=?", (template_id,)).fetchone()
        return self._safe_template(row)

    def set_template_status(
        self,
        template_id: str,
        status: str,
        *,
        actor_admin_user_id: str,
    ) -> dict[str, object]:
        if status not in {"active", "inactive"}:
            raise CoachingValidationError({"status": "Use active or inactive"})
        now = self._now()
        with self.database.session() as connection:
            if status == "active":
                version = connection.execute(
                    "SELECT 1 FROM diet_plan_versions WHERE template_id=? LIMIT 1",
                    (template_id,),
                ).fetchone()
                if version is None:
                    raise CoachingConflict("Diet template needs a version before activation")
            changed = connection.execute(
                "UPDATE diet_plan_templates SET status=?,updated_at=? WHERE id=?",
                (status, now, template_id),
            ).rowcount
            if not changed:
                raise CoachingNotFound("Diet template not found")
            row = connection.execute("SELECT * FROM diet_plan_templates WHERE id=?", (template_id,)).fetchone()
        return self._safe_template(row)

    def create_diet_version(
        self,
        template_id: str,
        title: object,
        content: object,
        *,
        actor_admin_user_id: str,
    ) -> dict[str, object]:
        clean_title = _bounded_text(title, "title", maximum=120)
        safe_content = self._validate_diet_content(content)
        now = self._now()
        version_id = uuid4().hex
        with self.database.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            template = connection.execute(
                "SELECT * FROM diet_plan_templates WHERE id=?",
                (template_id,),
            ).fetchone()
            if template is None:
                raise CoachingNotFound("Diet template not found")
            current = connection.execute(
                "SELECT COALESCE(MAX(version_number),0) FROM diet_plan_versions WHERE template_id=?",
                (template_id,),
            ).fetchone()[0]
            version_number = int(current) + 1
            connection.execute(
                "INSERT INTO diet_plan_versions(id,template_id,version_number,title,content_json,disclaimer,created_by_admin_user_id,created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (version_id, template_id, version_number, clean_title, json.dumps(safe_content, separators=(",", ":"), sort_keys=True), GENERAL_NUTRITION_DISCLAIMER, actor_admin_user_id, now),
            )
            connection.execute(
                "INSERT INTO diet_plan_events(template_id,event_type,actor_admin_user_id,metadata_json,created_at) "
                "VALUES (?,?,?,?,?)",
                (template_id, "version_created", actor_admin_user_id, json.dumps({"version": version_number}), now),
            )
            row = connection.execute("SELECT * FROM diet_plan_versions WHERE id=?", (version_id,)).fetchone()
            connection.commit()
        return self._safe_version(row)

    def list_diet_templates(self) -> list[dict[str, object]]:
        with self.database.session() as connection:
            rows = connection.execute(
                "SELECT t.*, (SELECT MAX(version_number) FROM diet_plan_versions v WHERE v.template_id=t.id) AS latest_version "
                "FROM diet_plan_templates t ORDER BY name COLLATE NOCASE"
            ).fetchall()
        result = []
        for row in rows:
            item = self._safe_template(row)
            item["latestVersion"] = row["latest_version"]
            result.append(item)
        return result

    def list_diet_versions(self, template_id: str) -> list[dict[str, object]]:
        with self.database.session() as connection:
            rows = connection.execute(
                "SELECT * FROM diet_plan_versions WHERE template_id=? ORDER BY version_number DESC",
                (template_id,),
            ).fetchall()
        return [self._safe_version(row) for row in rows]

    @staticmethod
    def _safe_assignment(row, version=None) -> dict[str, object]:
        item = {
            "id": row["id"],
            "customerId": row["customer_id"],
            "versionId": row["version_id"],
            "status": row["status"],
            "startsAt": int(row["starts_at"]),
            "endsAt": row["ends_at"],
            "note": row["assignment_note"],
            "endedAt": row["ended_at"],
            "createdAt": int(row["created_at"]),
        }
        if version is not None:
            item["plan"] = CoachingService._safe_version(version)
        return item

    def assign_diet(
        self,
        customer_id: str,
        version_id: str,
        *,
        note: object = None,
        actor_admin_user_id: str,
    ) -> dict[str, object]:
        clean_note = _bounded_text(note, "note", maximum=500, required=False)
        now = self._now()
        with self.database.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._customer(connection, customer_id)
            version = connection.execute(
                "SELECT v.*, t.status AS template_status FROM diet_plan_versions v "
                "JOIN diet_plan_templates t ON t.id=v.template_id WHERE v.id=?",
                (version_id,),
            ).fetchone()
            if version is None:
                raise CoachingNotFound("Diet plan version not found")
            if version["template_status"] != "active":
                raise CoachingConflict("Diet template is not active")
            previous = connection.execute(
                "SELECT id FROM diet_plan_assignments WHERE customer_id=? AND status='active'",
                (customer_id,),
            ).fetchall()
            connection.execute(
                "UPDATE diet_plan_assignments SET status='ended',ends_at=?,ended_at=?,updated_at=? "
                "WHERE customer_id=? AND status='active'",
                (now, now, now, customer_id),
            )
            for old in previous:
                connection.execute(
                    "INSERT INTO diet_plan_events(assignment_id,event_type,actor_admin_user_id,metadata_json,created_at) "
                    "VALUES (?,?,?,?,?)",
                    (old["id"], "assignment_ended", actor_admin_user_id, "{}", now),
                )
            assignment_id = uuid4().hex
            connection.execute(
                "INSERT INTO diet_plan_assignments(id,customer_id,version_id,status,starts_at,assignment_note,assigned_by_admin_user_id,created_at,updated_at) "
                "VALUES (?,?,?,'active',?,?,?,?,?)",
                (assignment_id, customer_id, version_id, now, clean_note, actor_admin_user_id, now, now),
            )
            connection.execute(
                "INSERT INTO diet_plan_events(assignment_id,event_type,actor_admin_user_id,metadata_json,created_at) "
                "VALUES (?,?,?,?,?)",
                (assignment_id, "assigned", actor_admin_user_id, json.dumps({"versionId": version_id}), now),
            )
            row = connection.execute("SELECT * FROM diet_plan_assignments WHERE id=?", (assignment_id,)).fetchone()
            connection.commit()
        return self._safe_assignment(row, version)

    def end_diet_assignment(
        self,
        customer_id: str,
        assignment_id: str,
        *,
        actor_admin_user_id: str,
    ) -> dict[str, object]:
        now = self._now()
        with self.database.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM diet_plan_assignments WHERE id=? AND customer_id=?",
                (assignment_id, customer_id),
            ).fetchone()
            if row is None:
                raise CoachingNotFound("Diet assignment not found")
            if row["status"] != "active":
                raise CoachingConflict("Diet assignment is not active")
            connection.execute(
                "UPDATE diet_plan_assignments SET status='ended',ends_at=?,ended_at=?,updated_at=? WHERE id=?",
                (now, now, now, assignment_id),
            )
            connection.execute(
                "INSERT INTO diet_plan_events(assignment_id,event_type,actor_admin_user_id,metadata_json,created_at) "
                "VALUES (?,?,?,?,?)",
                (assignment_id, "assignment_ended", actor_admin_user_id, "{}", now),
            )
            row = connection.execute("SELECT * FROM diet_plan_assignments WHERE id=?", (assignment_id,)).fetchone()
            version = connection.execute("SELECT * FROM diet_plan_versions WHERE id=?", (row["version_id"],)).fetchone()
            connection.commit()
        return self._safe_assignment(row, version)

    def customer_summary(self, customer_id: str) -> dict[str, object]:
        with self.database.session() as connection:
            self._customer(connection, customer_id)
            goals = connection.execute(
                "SELECT * FROM progress_goals WHERE customer_id=? ORDER BY updated_at DESC, created_at DESC LIMIT 50",
                (customer_id,),
            ).fetchall()
            measurements = connection.execute(
                "SELECT * FROM progress_measurements WHERE customer_id=? "
                "ORDER BY measured_at DESC, created_at DESC LIMIT 100",
                (customer_id,),
            ).fetchall()
            assignments = connection.execute(
                "SELECT * FROM diet_plan_assignments WHERE customer_id=? "
                "ORDER BY starts_at DESC, created_at DESC LIMIT 20",
                (customer_id,),
            ).fetchall()
            versions = {}
            for assignment in assignments:
                version = connection.execute(
                    "SELECT * FROM diet_plan_versions WHERE id=?",
                    (assignment["version_id"],),
                ).fetchone()
                if version is not None:
                    versions[assignment["version_id"]] = version
        latest: dict[str, dict[str, object]] = {}
        safe_measurements = [self._safe_measurement(row) for row in measurements]
        for item in safe_measurements:
            latest.setdefault(str(item["metricKey"]), item)
        safe_assignments = [
            self._safe_assignment(row, versions.get(row["version_id"])) for row in assignments
        ]
        return {
            "goals": [self._safe_goal(row) for row in goals],
            "latestMeasurements": latest,
            "measurementHistory": safe_measurements,
            "currentDiet": next((item for item in safe_assignments if item["status"] == "active"), None),
            "dietHistory": safe_assignments,
            "nutritionDisclaimer": GENERAL_NUTRITION_DISCLAIMER,
        }
