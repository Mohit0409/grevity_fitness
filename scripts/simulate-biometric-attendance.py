from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.gravity.admin import AdminService
from server.gravity.biometric import BiometricConflict, BiometricScanEvent, BiometricService
from server.gravity.config import Settings
from server.gravity.database import Database


def main() -> int:
    parser = argparse.ArgumentParser(description="Store a development biometric attendance scan.")
    parser.add_argument("--device-id", help="Existing biometric_devices.id to use.")
    parser.add_argument("--device-user-id", default="mock-101", help="Fingerprint machine user ID.")
    parser.add_argument("--person-id", help="Optional Gravity customer/staff id to map before scanning.")
    parser.add_argument("--event-time", type=int, default=int(time.time()), help="Unix timestamp for the scan.")
    args = parser.parse_args()

    settings = Settings.load(root_dir=ROOT)
    if settings.production:
        print("Refusing to simulate biometric attendance while GRAVITY_ENV=production.", file=sys.stderr)
        return 2
    settings.ensure_directories()
    database = Database(settings.database_path, settings.migrations_dir)
    database.migrate()
    admin = AdminService(database, settings)
    service = BiometricService(database, settings, admin)

    with database.session() as connection:
        actor = connection.execute(
            "SELECT id FROM admin_users WHERE status='active' ORDER BY CASE role WHEN 'owner' THEN 0 ELSE 1 END,created_at LIMIT 1"
        ).fetchone()
    if actor is None:
        print("Create an active owner/admin before running the simulator.", file=sys.stderr)
        return 3
    actor_id = actor["id"]

    device_id = args.device_id
    if not device_id:
        with database.session() as connection:
            row = connection.execute(
                "SELECT id FROM biometric_devices WHERE connection_mode='mock' ORDER BY created_at LIMIT 1"
            ).fetchone()
        if row is not None:
            device_id = row["id"]
        else:
            try:
                created = service.create_device(
                    {
                        "name": "Development Mock F09",
                        "vendor": "zkteco",
                        "model": "F09",
                        "deviceIdentifier": "mock-f09-dev",
                        "connectionMode": "mock",
                    },
                    actor_admin_user_id=actor_id,
                )
            except BiometricConflict:
                with database.session() as connection:
                    existing = connection.execute(
                        "SELECT id FROM biometric_devices WHERE device_identifier='mock-f09-dev' LIMIT 1"
                    ).fetchone()
                if existing is None:
                    raise
                device_id = existing["id"]
            else:
                device_id = created["device"]["id"]

    if args.person_id:
        try:
            service.create_mapping(
                {
                    "deviceId": device_id,
                    "deviceUserId": args.device_user_id,
                    "personId": args.person_id,
                    "enrolledStatus": "registered",
                },
                actor_admin_user_id=actor_id,
            )
        except BiometricConflict:
            pass

    result = service.record_event(
        device_id,
        BiometricScanEvent(
            device_user_id=args.device_user_id,
            event_time=args.event_time,
            verification_type="fingerprint",
            attendance_state="check-in",
            device_event_id=f"sim-{args.device_user_id}-{args.event_time}",
        ),
        source="mock",
    )
    print(
        "stored={stored} duplicates={duplicates} unmatched={unmatched} device_id={device_id}".format(
            device_id=device_id,
            **result,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
