from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Mapping
import os


def _load_dotenv(path: Path, target: dict[str, str]) -> None:
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in target:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        target[key] = value


def _boolean(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Invalid boolean configuration value: {value!r}")


def _port(value: str | None) -> int:
    port = int(value or "8787")
    if not 0 <= port <= 65535:
        raise ValueError("GRAVITY_PORT must be between 0 and 65535")
    return port


def _resolved_path(root: Path, value: str, default: str) -> Path:
    candidate = Path(value or default).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    return candidate.resolve()


@dataclass(frozen=True, slots=True)
class Settings:
    root_dir: Path
    web_dir: Path
    migrations_dir: Path
    data_dir: Path
    log_dir: Path
    backup_dir: Path
    database_path: Path
    environment: str
    host: str
    port: int
    app_base_url: str
    log_level: str
    trust_proxy: bool

    @classmethod
    def load(
        cls,
        *,
        root_dir: Path | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> "Settings":
        root = (root_dir or Path(__file__).resolve().parents[2]).resolve()
        values = dict(os.environ if environ is None else environ)
        _load_dotenv(root / ".env", values)

        data_dir = _resolved_path(root, values.get("GRAVITY_DATA_DIR", ""), ".gravity/data")
        log_dir = _resolved_path(root, values.get("GRAVITY_LOG_DIR", ""), ".gravity/logs")
        backup_dir = _resolved_path(root, values.get("GRAVITY_BACKUP_DIR", ""), ".gravity/backups")
        host = values.get("GRAVITY_HOST", "127.0.0.1").strip() or "127.0.0.1"
        port = _port(values.get("GRAVITY_PORT"))
        environment = values.get("GRAVITY_ENV", "development").strip().lower() or "development"
        base_url = values.get("APP_BASE_URL", f"http://{host}:{port}").strip().rstrip("/")

        return cls(
            root_dir=root,
            web_dir=(root / "web").resolve(),
            migrations_dir=(root / "server" / "migrations").resolve(),
            data_dir=data_dir,
            log_dir=log_dir,
            backup_dir=backup_dir,
            database_path=data_dir / "gravity.sqlite3",
            environment=environment,
            host=host,
            port=port,
            app_base_url=base_url,
            log_level=values.get("GRAVITY_LOG_LEVEL", "INFO").strip().upper() or "INFO",
            trust_proxy=_boolean(values.get("GRAVITY_TRUST_PROXY"), False),
        )

    @property
    def production(self) -> bool:
        return self.environment == "production"

    def ensure_directories(self) -> None:
        if not self.web_dir.is_dir():
            raise RuntimeError(f"Public web directory is missing: {self.web_dir}")
        if not self.migrations_dir.is_dir():
            raise RuntimeError(f"Migrations directory is missing: {self.migrations_dir}")
        for directory in (self.data_dir, self.log_dir, self.backup_dir):
            directory.mkdir(parents=True, exist_ok=True)

    def with_network(self, *, host: str | None = None, port: int | None = None) -> "Settings":
        return replace(self, host=host or self.host, port=self.port if port is None else port)
