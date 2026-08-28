from __future__ import annotations

import argparse
import getpass
import json
import logging
import signal
from pathlib import Path
from threading import Thread

from .admin import (
    AdminConflict,
    AdminService,
    AdminUnavailable,
    AdminValidationError,
)
from .config import Settings
from .database import Database
from .delivery import NotificationDispatcher
from .membership import MembershipService
from .notification import NotificationService
from .operations import BackupManager, OperationsError
from .runtime import RuntimeLease, RuntimeLeaseError
from .http import create_server
from .enquiry import EnquiryService
from .logging_config import configure_logging
from .canary import run_provider_canaries
from .cutover import CutoverVerifier
from .launch import LaunchGate
from .smoke import run_smoke


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Gravity Fitness application server")
    parser.add_argument("--host", help="Override GRAVITY_HOST")
    parser.add_argument("--port", type=int, help="Override GRAVITY_PORT")
    parser.add_argument("--check-db", action="store_true", help="Apply migrations and check SQLite integrity")
    parser.add_argument("--root", type=Path, help="Repository root (primarily for tests/operations)")
    parser.add_argument("--bootstrap-owner", metavar="USERNAME", help="Create the first owner securely")
    parser.add_argument("--scan-notifications", type=int, metavar="DAYS", help="Create expiry reminders for a day window")
    parser.add_argument("--deliver-notifications", action="store_true", help="Attempt due notifications using configured adapters")
    operations = parser.add_mutually_exclusive_group()
    operations.add_argument("--create-backup", action="store_true", help="Create a verified online SQLite backup")
    operations.add_argument("--verify-backup", type=Path, metavar="ARCHIVE", help="Verify a Gravity backup archive")
    operations.add_argument("--recovery-drill", type=Path, metavar="ARCHIVE", help="Restore a backup into a temporary drill database and validate it")
    operations.add_argument("--restore-backup", type=Path, metavar="ARCHIVE", help="Restore the live database from a verified backup")
    operations.add_argument("--launch-check", action="store_true", help="Run the fail-closed production launch gate")
    operations.add_argument("--provider-canaries", action="store_true", help="Run read-only Firebase and Razorpay production canaries")
    operations.add_argument("--smoke", action="store_true", help="Run the public/private launch smoke suite")
    operations.add_argument("--cutover-check", action="store_true", help="Run launch gate, provider canaries, and public HTTPS smoke")
    operations.add_argument("--purge-expired-enquiries", action="store_true", help="Delete enquiry PII whose 180-day retention period has elapsed")
    parser.add_argument("--smoke-base-url", help="Override APP_BASE_URL for smoke/cutover verification")
    parser.add_argument("--backup-label", default="manual", help="Label used when creating a backup")
    parser.add_argument("--confirm-live-restore", action="store_true", help="Required confirmation for replacing the live database")
    return parser


def _bootstrap_owner(settings: Settings, username: str) -> int:
    database = Database(settings.database_path, settings.migrations_dir)
    database.migrate()
    service = AdminService(database, settings)
    password = getpass.getpass("New Gravity owner password: ")
    confirmation = getpass.getpass("Confirm owner password: ")
    if password != confirmation:
        print("Owner passwords did not match.")
        return 2
    try:
        result = service.bootstrap_owner(username, password)
    except AdminUnavailable:
        print("Admin security is unavailable. Configure a strong SECRET_KEY first.")
        return 2
    except AdminValidationError as error:
        print("Owner bootstrap validation failed:", error.fields)
        return 2
    except AdminConflict:
        print("A Gravity owner already exists; bootstrap is disabled.")
        return 2

    print("Gravity Fitness owner created.")
    print("Store this TOTP and recovery data securely; it is shown only now.")
    print(f"TOTP secret: {result.totp_secret}")
    print(f"TOTP URI: {result.otpauth_uri}")
    print("Recovery codes:")
    for code in result.recovery_codes:
        print(f"  {code}")
    return 0


def main() -> int:
    args = _parser().parse_args()
    settings = Settings.load(root_dir=args.root)
    if args.host or args.port is not None:
        settings = settings.with_network(host=args.host, port=args.port)

    if args.launch_check:
        report = LaunchGate(settings).report()
        print(json.dumps(report, sort_keys=True))
        return 0 if report["launchReady"] else 2

    if args.provider_canaries:
        report = run_provider_canaries(settings)
        print(json.dumps(report, sort_keys=True))
        return 0 if report["ok"] else 2

    if args.smoke:
        report = run_smoke(args.smoke_base_url or settings.app_base_url, require_https=settings.production)
        print(json.dumps(report, sort_keys=True))
        return 0 if report["ok"] else 2

    if args.cutover_check:
        report = CutoverVerifier(settings).report(args.smoke_base_url)
        print(json.dumps(report, sort_keys=True))
        return 0 if report["cutoverReady"] else 2

    settings.ensure_directories()
    configure_logging(settings)

    if args.bootstrap_owner:
        return _bootstrap_owner(settings, args.bootstrap_owner)

    if args.check_db:
        database = Database(settings.database_path, settings.migrations_dir)
        database.migrate()
        result = database.health()
        print(result)
        return 0 if result["database"] == "ok" else 1

    if args.create_backup or args.verify_backup or args.recovery_drill or args.restore_backup:
        manager = BackupManager(settings, Database(settings.database_path, settings.migrations_dir))
        try:
            if args.create_backup:
                result = manager.create_backup(args.backup_label)
            elif args.verify_backup:
                result = manager.verify_backup(args.verify_backup)
            elif args.recovery_drill:
                result = manager.recovery_drill(args.recovery_drill)
            else:
                if not args.confirm_live_restore:
                    print("Live restore requires --confirm-live-restore and a stopped Gravity server.")
                    return 2
                result = manager.restore_live(args.restore_backup)
        except OperationsError as error:
            print(f"Gravity operation failed: {error}")
            return 2
        print(json.dumps(result, sort_keys=True))
        return 0

    if args.purge_expired_enquiries:
        database = Database(settings.database_path, settings.migrations_dir)
        database.migrate()
        service = EnquiryService(database, settings, AdminService(database, settings))
        print({"expiredEnquiriesPurged": service.purge_expired()})
        return 0

    if args.scan_notifications is not None or args.deliver_notifications:
        database = Database(settings.database_path, settings.migrations_dir)
        database.migrate()
        memberships = MembershipService(database)
        notifications = NotificationService(database, memberships, settings)
        if args.scan_notifications is not None:
            print({"scan": notifications.scan_expiring(args.scan_notifications)})
        if args.deliver_notifications:
            result = NotificationDispatcher.from_settings(notifications, settings).process_due()
            print({"delivery": result})
            return 1 if result["failed"] else 0
        return 0

    server = create_server(settings)
    logger = logging.getLogger("gravity.server")
    def stop_server(_signum: int, _frame: object) -> None:
        logger.info("shutdown_requested")
        Thread(target=server.shutdown, daemon=True).start()

    for signal_name in ("SIGINT", "SIGTERM"):
        if hasattr(signal, signal_name):
            signal.signal(getattr(signal, signal_name), stop_server)

    host, port = server.server_address[:2]
    logger.info("server_started", extra={"event_data": {"host": host, "port": port}})
    print(f"Gravity Fitness listening on http://{host}:{port}")
    try:
        with RuntimeLease(settings):
            server.serve_forever(poll_interval=0.25)
    except RuntimeLeaseError as error:
        logger.error("runtime_lease_failed", extra={"event_data": {"error": str(error)}})
        print(f"Gravity startup failed: {error}")
        return 2
    finally:
        server.server_close()
        logger.info("server_stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
