from __future__ import annotations

import argparse
import getpass
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
from .http import create_server
from .logging_config import configure_logging


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Gravity Fitness application server")
    parser.add_argument("--host", help="Override GRAVITY_HOST")
    parser.add_argument("--port", type=int, help="Override GRAVITY_PORT")
    parser.add_argument("--check-db", action="store_true", help="Apply migrations and check SQLite integrity")
    parser.add_argument("--root", type=Path, help="Repository root (primarily for tests/operations)")
    parser.add_argument("--bootstrap-owner", metavar="USERNAME", help="Create the first owner securely")
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
        server.serve_forever(poll_interval=0.25)
    finally:
        server.server_close()
        logger.info("server_stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
