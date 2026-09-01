from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import os
import sys

from .config import Settings


class RuntimeLeaseError(RuntimeError):
    pass


def runtime_dir(settings: Settings) -> Path:
    configured = os.environ.get("GRAVITY_RUNTIME_DIR", "").strip()
    candidate = Path(configured).expanduser() if configured else settings.root_dir / ".gravity"
    if not candidate.is_absolute():
        candidate = settings.root_dir / candidate
    return candidate.resolve()


def _system_boot_id() -> str | None:
    if os.name == "nt":
        return None
    try:
        value = Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip()
    except (FileNotFoundError, OSError):
        return None
    return value or None


def _pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        # Windows does not implement os.kill(pid, 0) consistently for every
        # process type. A failed probe must not make a live restore less safe.
        if os.name == "nt":
            import ctypes

            handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
        return False


class RuntimeLease:
    """Owns the PID/state files for the actual server process.

    Launchers never invent PID ownership. This lets Task Scheduler, runit,
    Termux:Boot, and manual foreground runs share the same restore guard.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.directory = runtime_dir(settings)
        self.pid_file = self.directory / "gravity.pid"
        self.state_file = self.directory / "gravity.state.json"
        self.pid = os.getpid()
        self.acquired = False

    def acquire(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        try:
            existing = int(self.pid_file.read_text(encoding="ascii").strip())
        except (FileNotFoundError, OSError, ValueError):
            existing = 0
        existing_state: dict[str, object] = {}
        try:
            loaded = json.loads(self.state_file.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                existing_state = loaded
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError):
            pass

        current_boot_id = _system_boot_id()
        existing_boot_id = existing_state.get("bootId") if existing_state.get("pid") == existing else None
        same_boot = not (
            current_boot_id
            and isinstance(existing_boot_id, str)
            and existing_boot_id
            and existing_boot_id != current_boot_id
        )
        if existing and existing != self.pid and same_boot and _pid_is_running(existing):
            raise RuntimeLeaseError(f"Gravity is already running with PID {existing}")

        state = {
            "formatVersion": 1,
            "pid": self.pid,
            "bootId": current_boot_id,
            "projectRoot": str(self.settings.root_dir.resolve()),
            "executable": str(Path(sys.executable).resolve()),
            "module": "server.gravity",
            "host": self.settings.host,
            "port": self.settings.port,
            "startedAt": datetime.now(timezone.utc).isoformat(),
        }
        temporary_pid = self.pid_file.with_suffix(".pid.tmp")
        temporary_state = self.state_file.with_suffix(".json.tmp")
        temporary_pid.write_text(f"{self.pid}\n", encoding="ascii")
        temporary_state.write_text(
            json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.replace(temporary_pid, self.pid_file)
        os.replace(temporary_state, self.state_file)
        for path in (self.pid_file, self.state_file):
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
        self.acquired = True

    def release(self) -> None:
        if not self.acquired:
            return
        try:
            owner = int(self.pid_file.read_text(encoding="ascii").strip())
        except (FileNotFoundError, OSError, ValueError):
            owner = 0
        if owner == self.pid:
            self.pid_file.unlink(missing_ok=True)
            self.state_file.unlink(missing_ok=True)
        self.acquired = False

    def __enter__(self) -> "RuntimeLease":
        self.acquire()
        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        self.release()
