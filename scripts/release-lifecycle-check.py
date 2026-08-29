#!/usr/bin/env python3
"""Validate read-only post-reboot Gravity lifecycle evidence."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import sys
from pathlib import Path
from typing import Any

BOOT_TASKS = {"GravityFitness-Watchdog", "GravityFitness-Notifications"}
ALL_TASKS = BOOT_TASKS | {"GravityFitness-DailyBackup"}


def _time(value: object) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _same_path(left: object, right: object) -> bool:
    if not left or not right:
        return False
    return os.path.normcase(os.path.abspath(str(left))) == os.path.normcase(os.path.abspath(str(right)))


def _after(value: object, boundary: datetime | None) -> bool:
    parsed = _time(value)
    return bool(parsed and boundary and parsed >= boundary)


def evaluate(evidence: dict[str, Any]) -> dict[str, Any]:
    blockers: list[str] = list(evidence.get("collectionBlockers") or [])
    warnings: list[str] = []
    boot = _time(evidence.get("bootTime"))
    now = _time(evidence.get("now")) or datetime.now(timezone.utc)
    release = dict(evidence.get("release") or {})

    if release.get("actualSha") != release.get("expectedSha"):
        blockers.append("release_sha_mismatch")
    if not release.get("clean"):
        blockers.append("release_checkout_dirty")
    if not release.get("detached"):
        blockers.append("release_checkout_not_detached")
    if int(release.get("port") or 0) != 8787:
        blockers.append("gravity_port_not_8787")
    if not _same_path(release.get("projectRoot"), release.get("stateProjectRoot")):
        blockers.append("gravity_state_project_root_mismatch")
    if not _same_path(release.get("expectedPython"), release.get("stateExecutable")):
        blockers.append("gravity_state_python_mismatch")
    if not _same_path(release.get("expectedPython"), release.get("processExecutable")):
        blockers.append("gravity_process_python_mismatch")
    if release.get("pid") != release.get("statePid") or release.get("pid") != release.get("pidFile"):
        blockers.append("gravity_pid_ownership_mismatch")
    if not release.get("commandValid"):
        blockers.append("gravity_command_mismatch")
    if not release.get("listenerValid"):
        blockers.append("gravity_listener_mismatch")
    if not release.get("healthOk"):
        blockers.append("gravity_health_failed")
    if not _after(release.get("processStartedAt"), boot):
        blockers.append("gravity_process_not_from_current_boot")
    if not _after(release.get("stateStartedAt"), boot):
        blockers.append("gravity_state_not_from_current_boot")
    process_started = _time(release.get("processStartedAt"))
    state_started = _time(release.get("stateStartedAt"))
    if not process_started or not state_started or abs((state_started - process_started).total_seconds()) > 120:
        blockers.append("gravity_start_metadata_mismatch")

    static_tasks = dict(evidence.get("taskVerification") or {})
    if not static_tasks.get("ready"):
        blockers.extend(f"task_config:{item}" for item in static_tasks.get("blockers") or ["verification_failed"])
    task_items = {str(item.get("name")): item for item in evidence.get("tasks") or []}
    for name in sorted(ALL_TASKS):
        item = task_items.get(name)
        if not item or not item.get("present"):
            blockers.append(f"task_runtime_missing:{name}")
            continue
        if not item.get("enabled"):
            blockers.append(f"task_runtime_disabled:{name}")
        if int(item.get("missedRuns") or 0) > 0:
            blockers.append(f"task_missed_runs:{name}")
        last_result = item.get("lastTaskResult")
        last_run = _time(item.get("lastRunTime"))
        next_run = _time(item.get("nextRunTime"))
        if name in BOOT_TASKS:
            if last_result != 0:
                blockers.append(f"task_last_result_failed:{name}")
            if not last_run or not boot or last_run < boot:
                blockers.append(f"task_not_run_current_boot:{name}")
        else:
            if last_run:
                if last_result != 0:
                    blockers.append(f"task_last_result_failed:{name}")
            elif not next_run or next_run <= now:
                blockers.append("daily_backup_task_overdue")
            if next_run and next_run <= now:
                blockers.append("daily_backup_next_run_overdue")

    ngrok = dict(evidence.get("ngrok") or {})
    if not ngrok.get("managed"):
        blockers.append("ngrok_unmanaged")
    if ngrok.get("pid") != ngrok.get("statePid") or ngrok.get("pid") != ngrok.get("pidFile"):
        blockers.append("ngrok_pid_ownership_mismatch")
    if not _same_path(ngrok.get("expectedExecutable"), ngrok.get("stateExecutable")):
        blockers.append("ngrok_state_executable_mismatch")
    if not _same_path(ngrok.get("expectedExecutable"), ngrok.get("processExecutable")):
        blockers.append("ngrok_process_executable_mismatch")
    if not _same_path(ngrok.get("expectedConfig"), ngrok.get("stateConfig")):
        blockers.append("ngrok_config_mismatch")
    if ngrok.get("target") != "http://127.0.0.1:8787":
        blockers.append("ngrok_target_mismatch")
    if ngrok.get("tunnelCount") != 1:
        blockers.append("ngrok_tunnel_count_mismatch")
    if ngrok.get("stateUrl") != ngrok.get("tunnelUrl"):
        blockers.append("ngrok_public_url_mismatch")
    if not ngrok.get("commandValid"):
        blockers.append("ngrok_command_mismatch")
    if not ngrok.get("publicHealthOk"):
        blockers.append("ngrok_public_health_failed")
    if not _after(ngrok.get("processStartedAt"), boot):
        blockers.append("ngrok_process_not_from_current_boot")
    if not _after(ngrok.get("stateStartedAt"), boot):
        blockers.append("ngrok_state_not_from_current_boot")
    ngrok_process_started = _time(ngrok.get("processStartedAt"))
    ngrok_state_started = _time(ngrok.get("stateStartedAt"))
    if not ngrok_process_started or not ngrok_state_started or abs((ngrok_state_started - ngrok_process_started).total_seconds()) > 120:
        blockers.append("ngrok_start_metadata_mismatch")

    notifications = dict(evidence.get("notifications") or {})
    if not notifications.get("statePresent"):
        blockers.append("notification_state_missing")
    if notifications.get("lastReportStatus") != "ok":
        blockers.append("notification_last_cycle_not_ok")
    if int(notifications.get("consecutiveFailures") or 0) != 0:
        blockers.append("notification_consecutive_failures")
    if not _after(notifications.get("lastSuccessfulScanAt"), boot):
        blockers.append("notification_scan_not_from_current_boot")
    if not _after(notifications.get("lastSuccessfulDeliveryAt"), boot):
        blockers.append("notification_delivery_not_from_current_boot")
    if notifications.get("lockPresent"):
        blockers.append("notification_runner_lock_present")

    backup = dict(evidence.get("backup") or {})
    backup_time = _time(backup.get("lastVerifiedAt"))
    backup_age_hours = round(max(0.0, (now - backup_time).total_seconds() / 3600), 3) if backup_time else None
    if not backup.get("evidencePresent"):
        warnings.append("backup_evidence_unavailable")
    elif not backup.get("recoveryDrillPassed"):
        blockers.append("backup_recovery_drill_not_recorded")
    if backup.get("evidencePresent") and backup_age_hours is None:
        warnings.append("backup_evidence_timestamp_invalid")
    elif backup_age_hours is not None and backup_age_hours > 36:
        warnings.append("backup_evidence_stale")

    public_url = ngrok.get("stateUrl") if isinstance(ngrok.get("stateUrl"), str) else None
    return {
        "ready": not blockers,
        "blockers": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
        "bootTime": evidence.get("bootTime"),
        "release": {
            "sha": release.get("actualSha"), "expectedSha": release.get("expectedSha"),
            "pid": release.get("pid"), "healthOk": bool(release.get("healthOk")),
        },
        "tasks": evidence.get("tasks") or [],
        "ngrok": {"pid": ngrok.get("pid"), "publicUrl": public_url, "publicHealthOk": bool(ngrok.get("publicHealthOk"))},
        "notifications": {
            "status": notifications.get("lastReportStatus"),
            "lastSuccessfulScanAt": notifications.get("lastSuccessfulScanAt"),
            "lastSuccessfulDeliveryAt": notifications.get("lastSuccessfulDeliveryAt"),
            "consecutiveFailures": int(notifications.get("consecutiveFailures") or 0),
            "providerReadiness": notifications.get("providerReadiness") or {},
        },
        "backup": {
            "evidencePresent": bool(backup.get("evidencePresent")),
            "lastVerifiedAt": backup.get("lastVerifiedAt"),
            "ageHours": backup_age_hours,
            "recoveryDrillPassed": bool(backup.get("recoveryDrillPassed")),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Gravity post-reboot lifecycle evidence")
    parser.add_argument("--evidence-json", type=Path)
    args = parser.parse_args()
    try:
        raw = args.evidence_json.read_text(encoding="utf-8-sig") if args.evidence_json else sys.stdin.read()
        evidence = json.loads(raw.lstrip("\ufeff"))
        report = evaluate(evidence)
    except Exception:
        report = {"ready": False, "blockers": ["invalid_lifecycle_evidence"], "warnings": []}
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report.get("ready") else 2


if __name__ == "__main__":
    raise SystemExit(main())
