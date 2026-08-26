from __future__ import annotations

import argparse
import logging
import signal
from pathlib import Path
from threading import Thread

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
    return parser


def main() -> int:
    args = _parser().parse_args()
    settings = Settings.load(root_dir=args.root)
    if args.host or args.port is not None:
        settings = settings.with_network(host=args.host, port=args.port)
    settings.ensure_directories()
    configure_logging(settings)

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
