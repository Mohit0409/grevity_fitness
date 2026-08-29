from __future__ import annotations

import argparse
import json
import ntpath
import os
import shlex
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


class AdoptionError(ValueError):
    pass


def _windows_path(value: object) -> str:
    text = str(value or "").strip().strip('"')
    return ntpath.normpath(text).casefold() if text else ""


def _parse_time(value: object, label: str) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise AdoptionError(f"missing {label}")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise AdoptionError(f"invalid {label}") from error
    if parsed.tzinfo is None:
        raise AdoptionError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _matching_tunnels(tunnels: object, target: str) -> list[dict[str, Any]]:
    if not isinstance(tunnels, list):
        raise AdoptionError("ngrok API did not return a tunnel list")
    matches: list[dict[str, Any]] = []
    for item in tunnels:
        if not isinstance(item, dict):
            continue
        config = item.get("config")
        address = config.get("addr") if isinstance(config, dict) else None
        public_url = str(item.get("public_url") or "")
        if str(address or "") == target and public_url.startswith("https://"):
            matches.append(item)
    return matches



def _command_tokens(command_line: str) -> list[str]:
    try:
        raw = shlex.split(command_line, posix=False)
    except ValueError as error:
        raise AdoptionError("ngrok command line cannot be parsed") from error
    tokens: list[str] = []
    for token in raw:
        token = token.strip()
        if len(token) >= 2 and token[0] == token[-1] and token[0] in {"'", '"'}:
            token = token[1:-1]
        tokens.append(token)
    return tokens


def _option_values(tokens: list[str], name: str) -> list[str]:
    values: list[str] = []
    folded_name = name.casefold()
    for index, token in enumerate(tokens):
        folded = token.casefold()
        if folded == folded_name:
            if index + 1 >= len(tokens):
                raise AdoptionError(f"{name} is missing its value")
            values.append(tokens[index + 1])
        elif folded.startswith(folded_name + "="):
            values.append(token.split("=", 1)[1])
    return values

def validate_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    pid = int(evidence.get("pid") or 0)
    if pid <= 0 or not evidence.get("processExists", False):
        raise AdoptionError("stale ngrok PID")
    if str(evidence.get("processName") or "").casefold() != "ngrok.exe":
        raise AdoptionError("PID belongs to a foreign process")

    expected_executable = _windows_path(evidence.get("expectedExecutable"))
    actual_executable = _windows_path(evidence.get("processExecutable"))
    if not expected_executable or actual_executable != expected_executable:
        raise AdoptionError("ngrok executable path does not match the expected deployment path")

    expected_config = _windows_path(evidence.get("expectedConfig"))
    target = str(evidence.get("target") or "").strip()
    if not expected_config:
        raise AdoptionError("expected ngrok config path is required")
    if not target.startswith("http://127.0.0.1:"):
        raise AdoptionError("ngrok target must be the Gravity loopback endpoint")
    try:
        port = int(target.rsplit(":", 1)[1])
    except (IndexError, ValueError) as error:
        raise AdoptionError("invalid Gravity loopback target") from error
    if port < 1 or port > 65535:
        raise AdoptionError("invalid Gravity loopback port")

    command_line = str(evidence.get("commandLine") or "")
    lowered_command = command_line.casefold()
    if "--authtoken" in lowered_command or "authtoken=" in lowered_command:
        raise AdoptionError("ngrok command line must not contain an auth token")
    tokens = _command_tokens(command_line)
    if not any(token.casefold() == target.casefold() for token in tokens):
        raise AdoptionError("ngrok command line does not target the expected Gravity port")
    config_values = _option_values(tokens, "--config")
    if len(config_values) != 1 or _windows_path(config_values[0]) != expected_config:
        raise AdoptionError("ngrok command line does not use the expected config path")

    process_start = _parse_time(evidence.get("processStartedAt"), "process start time")
    creation_time = _parse_time(evidence.get("processCreationTime"), "process creation time")
    if abs((process_start - creation_time).total_seconds()) > 120:
        raise AdoptionError("ngrok process start metadata does not match")
    if process_start > datetime.now(timezone.utc) + timedelta(seconds=120):
        raise AdoptionError("ngrok process start time is too far in the future")

    matches = _matching_tunnels(evidence.get("tunnels"), target)
    if not matches:
        raise AdoptionError("ngrok API has no HTTPS tunnel for the expected Gravity target")
    if len(matches) != 1:
        raise AdoptionError("multiple ngrok tunnels target the same Gravity endpoint")

    public_url = str(matches[0].get("public_url") or "").rstrip("/")
    return {
        "ready": True,
        "pid": pid,
        "executable": str(evidence.get("processExecutable")),
        "configPath": str(evidence.get("expectedConfig")),
        "target": target,
        "startedAt": process_start.isoformat().replace("+00:00", "Z"),
        "publicUrl": public_url,
    }


def _atomic_temp(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        os.unlink(temporary)
        raise
    return Path(temporary)


def write_managed_state(runtime_dir: Path, report: dict[str, Any]) -> None:
    pid_path = runtime_dir / "ngrok.pid"
    state_path = runtime_dir / "ngrok.state.json"
    url_path = runtime_dir / "ngrok.public-url"

    state = {
        "formatVersion": 1,
        "pid": report["pid"],
        "executable": report["executable"],
        "configPath": report["configPath"],
        "target": report["target"],
        "startedAt": report["startedAt"],
        "adoptedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    state_text = json.dumps(state, indent=2, sort_keys=True) + "\n"
    state_tmp = _atomic_temp(state_path, state_text)
    url_tmp = _atomic_temp(url_path, str(report["publicUrl"]) + "\n")
    pid_tmp = _atomic_temp(pid_path, str(report["pid"]) + "\n")
    try:
        os.replace(state_tmp, state_path)
        os.replace(url_tmp, url_path)
        os.replace(pid_tmp, pid_path)
    finally:
        for temporary in (state_tmp, url_tmp, pid_tmp):
            if temporary.exists():
                temporary.unlink()


def existing_state_status(runtime_dir: Path, report: dict[str, Any]) -> str:
    pid_path = runtime_dir / "ngrok.pid"
    state_path = runtime_dir / "ngrok.state.json"
    url_path = runtime_dir / "ngrok.public-url"
    present = [path.exists() for path in (pid_path, state_path, url_path)]
    if not any(present):
        return "absent"
    if not all(present):
        raise AdoptionError("partial managed ngrok state already exists")
    try:
        saved_pid = int(pid_path.read_text(encoding="utf-8").strip())
        saved_state = json.loads(state_path.read_text(encoding="utf-8-sig"))
        saved_url = url_path.read_text(encoding="utf-8").strip().rstrip("/")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise AdoptionError("existing managed ngrok state is invalid") from error
    if (
        saved_pid == report["pid"]
        and int(saved_state.get("pid") or 0) == report["pid"]
        and _windows_path(saved_state.get("executable")) == _windows_path(report["executable"])
        and _windows_path(saved_state.get("configPath")) == _windows_path(report["configPath"])
        and str(saved_state.get("target") or "") == report["target"]
        and saved_url == report["publicUrl"]
    ):
        saved_start = _parse_time(saved_state.get("startedAt"), "saved process start time")
        report_start = _parse_time(report.get("startedAt"), "validated process start time")
        if abs((saved_start - report_start).total_seconds()) <= 120:
            return "matching"
    raise AdoptionError("conflicting managed ngrok state already exists")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and atomically adopt an existing ngrok tunnel.")
    parser.add_argument("--evidence-json", required=True)
    parser.add_argument("--runtime-dir", required=True)
    parser.add_argument("--probe-only", action="store_true")
    args = parser.parse_args()

    evidence = json.loads(Path(args.evidence_json).read_text(encoding="utf-8-sig"))
    runtime_dir = Path(args.runtime_dir).resolve()
    try:
        report = validate_evidence(evidence)
        status = existing_state_status(runtime_dir, report)
        report["managedState"] = status
        report["probeOnly"] = bool(args.probe_only)
        if not args.probe_only and status == "absent":
            write_managed_state(runtime_dir, report)
            report["managedState"] = "adopted"
        elif not args.probe_only and status == "matching":
            report["managedState"] = "already_managed"
        print(json.dumps(report, separators=(",", ":")))
        return 0
    except AdoptionError as error:
        print(json.dumps({"ready": False, "error": str(error)}, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
