from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from typing import Iterator
import re
import sqlite3


MIGRATION_NAME = re.compile(r"^(?P<version>\d{3,})_(?P<name>[a-z0-9_]+)\.sql$")


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


class Database:
    def __init__(self, path: Path, migrations_dir: Path) -> None:
        self.path = path
        self.migrations_dir = migrations_dir

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
            connection.close()
            raise RuntimeError("SQLite foreign key enforcement could not be enabled")
        return connection

    @contextmanager
    def session(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            yield connection
        finally:
            connection.close()

    def migrate(self) -> list[str]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        applied_now: list[str] = []
        with self.session() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    checksum TEXT NOT NULL,
                    applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                )
                """
            )
            for migration in sorted(self.migrations_dir.glob("*.sql")):
                match = MIGRATION_NAME.match(migration.name)
                if not match:
                    raise RuntimeError(f"Invalid migration filename: {migration.name}")
                version = match.group("version")
                name = match.group("name")
                sql = migration.read_text(encoding="utf-8")
                checksum = sha256(sql.encode("utf-8")).hexdigest()
                current = connection.execute(
                    "SELECT checksum FROM schema_migrations WHERE version = ?", (version,)
                ).fetchone()
                if current:
                    if current["checksum"] != checksum:
                        raise RuntimeError(f"Applied migration {version} has changed on disk")
                    continue
                script = (
                    "BEGIN IMMEDIATE;\n"
                    + sql
                    + "\nINSERT INTO schema_migrations(version, name, checksum) VALUES ("
                    + ", ".join((_sql_literal(version), _sql_literal(name), _sql_literal(checksum)))
                    + ");\nCOMMIT;"
                )
                try:
                    connection.executescript(script)
                except Exception:
                    connection.rollback()
                    raise
                applied_now.append(version)
        return applied_now

    def health(self) -> dict[str, str]:
        try:
            with self.session() as connection:
                quick_check = connection.execute("PRAGMA quick_check").fetchone()[0]
                foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
                migration_count = connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
            if quick_check != "ok" or foreign_key_errors:
                return {"database": "error", "migrations": "unknown"}
            return {"database": "ok", "migrations": str(migration_count)}
        except (OSError, sqlite3.Error, RuntimeError):
            return {"database": "error", "migrations": "unknown"}
