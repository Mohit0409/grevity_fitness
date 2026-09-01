#!/usr/bin/env python3
from __future__ import annotations

import argparse
from getpass import getpass
from http.cookiejar import CookieJar
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener

APPROVAL_PURPOSE = "gravity-f09-read-only-integration"
DEFAULT_DEVICE_IP = "192.168.1.201"
DEFAULT_DEVICE_PORT = 4370
DEFAULT_DEVICE_ID = "1"
DEFAULT_CONFIG = Path.home() / ".config/gravity/gravity.env"
DEFAULT_APPROVAL = Path.home() / ".config/gravity/f09-approval.json"

def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key.strip()] = value
    return values


def repo_root() -> Path:
    configured = Path.home() / ".config/gravity/repository"
    if configured.is_file():
        return Path(configured.read_text(encoding="utf-8").strip()).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


def current_commit(root: Path) -> str:
    result = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, check=True)
    return result.stdout.strip()

def json_request(opener, base_url: str, path: str, method: str, *, body=None, csrf: str | None = None):
    headers = {
        "Accept": "application/json",
        "Origin": base_url,
        "User-Agent": "Gravity Fitness tablet F09 setup",
        "ngrok-skip-browser-warning": "true",
    }
    if csrf:
        headers["X-CSRF-Token"] = csrf
    data = None
    if body is not None:
        data = json.dumps(body, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(base_url + path, data=data, headers=headers, method=method)
    try:
        with opener.open(request, timeout=20) as response:
            payload = response.read()
    except HTTPError as error:
        payload = error.read()
        try:
            detail = json.loads(payload.decode("utf-8"))
        except Exception:
            detail = {"error": f"HTTP {error.code}"}
        raise RuntimeError(str(detail.get("error") or detail)) from error
    except URLError as error:
        raise RuntimeError(str(error.reason)) from error
    return json.loads(payload.decode("utf-8")) if payload else {}

def health(url: str) -> bool:
    request = Request(url, headers={"ngrok-skip-browser-warning": "true", "User-Agent": "Gravity F09 preflight"})
    try:
        with build_opener().open(request, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return payload.get("status") == "ok" and payload.get("service") == "Gravity Fitness" and payload.get("database") == "ok"
    except Exception:
        return False


def driver_ready() -> bool:
    try:
        from zk import ZK  # type: ignore  # noqa: F401
        return True
    except Exception:
        return False


def consume_approval(path: Path, root: Path, device_ip: str, device_port: int) -> dict[str, object]:
    if not path.is_file():
        raise RuntimeError("One-time owner approval is missing. Do not configure the F09 without explicit approval.")
    if os.name != "nt" and stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise RuntimeError("F09 approval file permissions are unsafe; expected mode 600.")
    approval = json.loads(path.read_text(encoding="utf-8"))
    if approval.get("purpose") != APPROVAL_PURPOSE:
        raise RuntimeError("F09 approval purpose is invalid.")
    if approval.get("deviceIp") != device_ip or int(approval.get("devicePort", 0)) != device_port:
        raise RuntimeError("F09 approval does not match the requested device target.")
    if str(approval.get("commit") or "") != current_commit(root):
        raise RuntimeError("F09 approval was issued for a different project commit.")
    if int(approval.get("expiresAt", 0)) < int(time.time()):
        raise RuntimeError("F09 approval has expired. Ask the owner again before configuring.")
    path.unlink()
    return approval

def authenticate(opener, base_url: str) -> tuple[dict[str, object], str]:
    username = input("Owner/admin username: ").strip()
    if not username:
        raise RuntimeError("Owner/admin username is required.")
    password = getpass("Admin password: ")
    login = json_request(opener, base_url, "/api/admin/login", "POST", body={"username": username, "password": password})
    password = ""
    if not login.get("authenticated"):
        if not login.get("secondFactorRequired"):
            raise RuntimeError("Admin authentication failed.")
        factor = getpass("Authenticator or recovery code: ")
        login = json_request(opener, base_url, "/api/admin/verify", "POST", body={"code": factor})
        factor = ""
    if not login.get("authenticated") or not login.get("csrfToken"):
        raise RuntimeError("Admin authentication did not complete.")
    permissions = set(login.get("admin", {}).get("permissions") or [])
    if "*" not in permissions and "biometric.manage" not in permissions:
        raise RuntimeError("This account cannot manage biometric devices.")
    return login, str(login["csrfToken"])


def ensure_tcp(device_ip: str, device_port: int) -> None:
    try:
        with socket.create_connection((device_ip, device_port), timeout=5):
            return
    except OSError as error:
        raise RuntimeError(f"F09 is unreachable at {device_ip}:{device_port}. Do not change device settings automatically.") from error

def configure(base_url: str, device_ip: str, device_port: int, device_identifier: str) -> dict[str, object]:
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    login, csrf = authenticate(opener, base_url)
    response = json_request(opener, base_url, "/api/admin/biometric/devices", "GET")
    matches = [item for item in response.get("devices", []) if item.get("vendor") == "zkteco" and str(item.get("deviceIdentifier")) == device_identifier]
    if len(matches) > 1:
        raise RuntimeError("More than one Gravity ZKTeco record uses this Device ID; resolve it manually first.")
    existing = matches[0] if matches else None
    prompt = "F09 numeric Comm Key (blank retains existing stored key): " if existing else "F09 numeric Comm Key: "
    comm_key = getpass(prompt).strip()
    if comm_key and not comm_key.isdigit():
        raise RuntimeError("F09 Comm Key must be numeric. Never guess or reset it.")
    if not existing and not comm_key:
        raise RuntimeError("A new F09 record requires the real Comm Key.")
    if existing and not existing.get("commKeyConfigured") and not comm_key:
        raise RuntimeError("The existing Gravity F09 record has no stored Comm Key.")
    body: dict[str, object] = {
        "name": "Gravity Entrance F09", "model": "F09", "deviceIdentifier": device_identifier,
        "host": device_ip, "port": device_port, "connectionMode": "tcp", "enabled": True,
        "timezone": "Asia/Kolkata", "duplicateWindowSeconds": 120, "visitGapSeconds": 14400,
    }
    if comm_key:
        body["commKey"] = comm_key
    if existing:
        saved = json_request(opener, base_url, f"/api/admin/biometric/devices/{existing['id']}", "PATCH", body=body, csrf=csrf)
    else:
        saved = json_request(opener, base_url, "/api/admin/biometric/devices", "POST", body=body, csrf=csrf)
    comm_key = ""
    device = saved["device"]
    sync = json_request(opener, base_url, f"/api/admin/biometric/devices/{device['id']}/sync", "POST", csrf=csrf)
    return {
        "configured": True,
        "deviceId": device["id"],
        "usersSynced": int(sync.get("usersSynced", 0)),
        "newAttendanceEvents": int(sync.get("stored", 0)),
        "unmatched": int(sync.get("unmatched", 0)),
        "deviceSafety": {
            "hardwareWrites": False,
            "changesNetworkOrAdms": False,
            "changesClock": False,
            "changesUsersOrTemplates": False,
            "clearsAttendanceLogs": False,
            "backgroundPollingEnabled": False,
        },
        "adminRole": login.get("admin", {}).get("role"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Approval-gated F09 setup for the Gravity Termux host")
    parser.add_argument("mode", choices=("preflight", "configure"))
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--approval-file", type=Path, default=DEFAULT_APPROVAL)
    parser.add_argument("--device-ip", default=DEFAULT_DEVICE_IP)
    parser.add_argument("--device-port", type=int, default=DEFAULT_DEVICE_PORT)
    parser.add_argument("--device-identifier", default=DEFAULT_DEVICE_ID)
    args = parser.parse_args()

    config = args.config.expanduser().resolve()
    if not config.is_file():
        raise RuntimeError(f"Gravity config missing: {config}")
    values = load_env(config)
    base_url = values.get("APP_BASE_URL", "").rstrip("/")
    if not base_url.startswith("https://"):
        raise RuntimeError("Tablet production APP_BASE_URL must be HTTPS before F09 setup.")
    local_port = int(values.get("GRAVITY_PORT", "8787") or "8787")
    root = repo_root()
    preflight = {
        "mode": args.mode,
        "commit": current_commit(root),
        "gravityLocalHealthy": health(f"http://127.0.0.1:{local_port}/api/health"),
        "gravityPublicHealthy": health(base_url + "/api/health"),
        "driverReady": driver_ready(),
        "deviceTarget": f"{args.device_ip}:{args.device_port}",
        "deviceContacted": False,
        "approvalRequiredForDeviceContact": True,
        "automaticWifiTrigger": False,
        "backgroundPollingEnabled": False,
        "hardwareMutationAllowed": False,
    }
    if args.mode == "preflight":
        print(json.dumps(preflight, indent=2, sort_keys=True))
        return 0 if all((preflight["gravityLocalHealthy"], preflight["gravityPublicHealthy"], preflight["driverReady"])) else 1

    if not preflight["gravityLocalHealthy"] or not preflight["gravityPublicHealthy"]:
        raise RuntimeError("Gravity must be healthy locally and publicly before F09 configuration.")
    if not preflight["driverReady"]:
        raise RuntimeError("Pinned ZKTeco driver is not installed. Run f09-onsite.sh prepare first.")
    consume_approval(args.approval_file.expanduser().resolve(), root, args.device_ip, args.device_port)
    ensure_tcp(args.device_ip, args.device_port)
    result = configure(base_url, args.device_ip, args.device_port, args.device_identifier)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError, subprocess.CalledProcessError) as error:
        print(f"F09 setup stopped safely: {error}", file=sys.stderr)
        raise SystemExit(2)
