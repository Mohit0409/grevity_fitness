#!/usr/bin/env python3
"""Safely schedule Gravity's server-owned notification CLI operations."""
from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Mapping
from uuid import uuid4


SCAN_WINDOWS = (7, 3, 1, 0)
MAX_LOG_BYTES = 1_048_576


class NotificationCycleError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temporary.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _process_running(process_id: object) -> bool:
    try:
        process_id = int(process_id)
    except (TypeError, ValueError):
        return False
    if process_id < 1:
        return False
    try:
        os.kill(process_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


class CycleLock:
    def __init__(self, path: Path, stale_after_seconds: int) -> None:
        self.path = path
        self.stale_after_seconds = stale_after_seconds
        self.token = uuid4().hex

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"pid": os.getpid(), "startedAt": _timestamp(), "token": self.token}
        for _ in range(2):
            try:
                descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                existing = _read_json(self.path)
                if "pid" in existing:
                    if _process_running(existing.get("pid")):
                        return False
                else:
                    try:
                        age = time.time() - self.path.stat().st_mtime
                    except OSError:
                        continue
                    if age < self.stale_after_seconds:
                        return False
                try:
                    self.path.unlink()
                except FileNotFoundError:
                    continue
                continue
            else:
                with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                    json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
                    handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                return True
        return False

    def release(self) -> None:
        existing = _read_json(self.path)
        if existing.get("token") == self.token:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass


def _provider_readiness(root: Path, environ: Mapping[str, str] | None = None) -> dict[str, dict[str, str]]:
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from server.gravity.config import Settings

    settings = Settings.load(root_dir=root, environ=environ)
    return {
        # Keep these statuses aligned with NotificationService.provider_blockers().
        # Credentials alone do not install an SMS or WhatsApp delivery adapter.
        "email": {"status": "ready" if settings.smtp_configured else "blocked_external_config"},
        "sms": {
            "status": "blocked_adapter_missing"
            if settings.sms_credentials_configured
            else "blocked_external_config"
        },
        "whatsapp": {
            "status": "blocked_adapter_missing"
            if settings.whatsapp_credentials_configured
            else "blocked_external_config"
        },
        "owner_email": {"status": "configured" if settings.owner_email else "blocked"},
        "owner_phone": {"status": "configured" if settings.owner_phone else "blocked"},
        "owner_whatsapp": {"status": "configured" if settings.owner_whatsapp else "blocked"},
    }


def _parse_cli_result(stdout: str, key: str) -> dict[str, Any]:
    for line in reversed(stdout.splitlines()):
        try:
            value = ast.literal_eval(line)
        except (SyntaxError, ValueError):
            continue
        if isinstance(value, dict) and isinstance(value.get(key), dict):
            return dict(value[key])
    raise NotificationCycleError("notification_cli_invalid_output")


def _run_cli(root: Path, python_path: Path, arguments: list[str], key: str, timeout_seconds: int) -> tuple[dict[str, Any], int]:
    try:
        result = subprocess.run(
            [str(python_path), "-m", "server.gravity", *arguments],
            cwd=root,
            env=dict(os.environ),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise NotificationCycleError("notification_cli_timeout") from error
    if result.returncode != 0 and key == "scan":
        return {}, result.returncode
    summary = _parse_cli_result(result.stdout, key)
    return summary, result.returncode


def _number(value: object) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _rotate_log(path: Path) -> None:
    try:
        if path.is_file() and path.stat().st_size >= MAX_LOG_BYTES:
            archive = path.with_name(f"{path.name}.1")
            archive.unlink(missing_ok=True)
            os.replace(path, archive)
    except OSError:
        pass


def _write_log(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _rotate_log(path)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n")


def _update_state(path: Path, report: dict[str, Any], *, scan_succeeded: bool, delivery_succeeded: bool) -> None:
    state = _read_json(path)
    timestamp = str(report["finished_at"])
    if scan_succeeded:
        state["last_successful_scan_at"] = timestamp
    if delivery_succeeded:
        state["last_successful_delivery_at"] = timestamp
    if report["status"] == "ok":
        state["consecutive_failures"] = 0
    elif report["status"] == "failed":
        state["consecutive_failures"] = _number(state.get("consecutive_failures")) + 1
        state["last_failure_at"] = timestamp
        state["last_failure"] = report.get("failure", "notification_cycle_failed")
    state["provider_readiness"] = report["provider_readiness"]
    state["last_report"] = {
        key: report[key]
        for key in (
            "status",
            "created",
            "deduped",
            "suppressed_renewed",
            "delivery_attempted",
            "delivery_sent",
            "delivery_failed",
            "delivery_skipped",
            "finished_at",
        )
    }
    _write_json(path, state)


def _base_report(provider_readiness: dict[str, dict[str, str]]) -> dict[str, Any]:
    return {
        "event": "notification_cycle",
        "status": "failed",
        "scan_windows": list(SCAN_WINDOWS),
        "scan_results": [],
        "created": 0,
        "deduped": 0,
        "suppressed_renewed": 0,
        "delivery_attempted": 0,
        "delivery_sent": 0,
        "delivery_failed": 0,
        "delivery_skipped": 0,
        "provider_readiness": provider_readiness,
        "started_at": _timestamp(),
        "finished_at": "",
    }


def run_cycle(root: Path, runtime_dir: Path, python_path: Path, timeout_seconds: int, stale_lock_seconds: int) -> tuple[dict[str, Any], int]:
    try:
        provider_readiness = _provider_readiness(root)
    except Exception:
        report = _base_report({})
        report["failure"] = "notification_configuration_invalid"
        report["finished_at"] = _timestamp()
        _write_log(runtime_dir / "notifications.log", report)
        _update_state(runtime_dir / "notification-state.json", report, scan_succeeded=False, delivery_succeeded=False)
        return report, 1

    lock = CycleLock(runtime_dir / "notification-runner.lock", stale_lock_seconds)
    if not lock.acquire():
        report = _base_report(provider_readiness)
        report["status"] = "already_running"
        report["finished_at"] = _timestamp()
        _write_log(runtime_dir / "notifications.log", report)
        return report, 0

    report = _base_report(provider_readiness)
    scan_succeeded = False
    delivery_succeeded = False
    try:
        for window in SCAN_WINDOWS:
            scan, return_code = _run_cli(root, python_path, ["--scan-notifications", str(window)], "scan", timeout_seconds)
            if return_code != 0:
                raise NotificationCycleError("notification_scan_failed")
            result = {
                "scan_window": window,
                "created": _number(scan.get("created")),
                "deduped": _number(scan.get("deduped")),
                "suppressed_renewed": _number(scan.get("suppressedRenewed")),
            }
            report["scan_results"].append(result)
            report["created"] += result["created"]
            report["deduped"] += result["deduped"]
            report["suppressed_renewed"] += result["suppressed_renewed"]
        scan_succeeded = True

        delivery, return_code = _run_cli(root, python_path, ["--deliver-notifications"], "delivery", timeout_seconds)
        report["delivery_attempted"] = _number(delivery.get("attempted"))
        report["delivery_sent"] = _number(delivery.get("sent"))
        report["delivery_failed"] = _number(delivery.get("failed"))
        report["delivery_skipped"] = _number(delivery.get("skipped"))
        if return_code != 0:
            raise NotificationCycleError("notification_delivery_failed")
        delivery_succeeded = True
        report["status"] = "ok"
        exit_code = 0
    except NotificationCycleError as error:
        report["failure"] = error.code
        exit_code = 1
    finally:
        report["finished_at"] = _timestamp()
        _write_log(runtime_dir / "notifications.log", report)
        _update_state(
            runtime_dir / "notification-state.json",
            report,
            scan_succeeded=scan_succeeded,
            delivery_succeeded=delivery_succeeded,
        )
        lock.release()
    return report, exit_code


def main() -> int:
    parser = argparse.ArgumentParser(description="Run scheduled Gravity notification scans and delivery safely")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--runtime-dir", type=Path, required=True)
    parser.add_argument("--python", dest="python_path", type=Path, default=Path(sys.executable))
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--stale-lock-seconds", type=int, default=1_200)
    parser.add_argument("--status", action="store_true", help="Print safe scheduler state without sending notifications")
    args = parser.parse_args()
    if args.timeout_seconds < 30 or args.stale_lock_seconds < args.timeout_seconds:
        parser.error("lock timeout must be at least the command timeout, which must be at least 30 seconds")
    root = args.root.expanduser().resolve()
    runtime_dir = args.runtime_dir.expanduser().resolve()
    python_path = args.python_path.expanduser().resolve()
    if args.status:
        try:
            readiness = _provider_readiness(root)
        except Exception:
            print(json.dumps({"event": "notification_status", "status": "configuration_invalid"}, sort_keys=True))
            return 1
        print(json.dumps({"event": "notification_status", "provider_readiness": readiness, "state": _read_json(runtime_dir / "notification-state.json")}, sort_keys=True))
        return 0
    report, exit_code = run_cycle(root, runtime_dir, python_path, args.timeout_seconds, args.stale_lock_seconds)
    print(json.dumps(report, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
