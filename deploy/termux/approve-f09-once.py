#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import time

PURPOSE = "gravity-f09-read-only-integration"
PHRASE = "APPROVE F09 READ-ONLY INTEGRATION"
DEFAULT_APPROVAL = Path.home() / ".config/gravity/f09-approval.json"


def repo_root() -> Path:
    marker = Path.home() / ".config/gravity/repository"
    if not marker.is_file():
        raise SystemExit("Gravity repository marker is missing.")
    return Path(marker.read_text(encoding="utf-8").strip()).expanduser().resolve()


def commit(root: Path) -> str:
    result = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, check=True)
    return result.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Create one short-lived F09 owner approval")
    parser.add_argument("--device-ip", default="192.168.1.201")
    parser.add_argument("--device-port", type=int, default=4370)
    parser.add_argument("--minutes", type=int, default=15, choices=range(5, 31))
    parser.add_argument("--approval-file", type=Path, default=DEFAULT_APPROVAL)
    args = parser.parse_args()
    print("This authorizes one read-only integration session with the existing F09.")
    print("It does NOT authorize changing F09 network, ADMS, clock, users, templates, or attendance logs.")
    typed = input(f"Type exactly: {PHRASE}\n> ").strip()
    if typed != PHRASE:
        raise SystemExit("Approval phrase did not match; nothing was authorized.")

    now = int(time.time())
    path = args.approval_file.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "purpose": PURPOSE,
        "deviceIp": args.device_ip,
        "devicePort": args.device_port,
        "commit": commit(repo_root()),
        "issuedAt": now,
        "expiresAt": now + args.minutes * 60,
        "nonce": secrets.token_hex(16),
        "hardwareMutationAllowed": False,
        "backgroundPollingAllowed": False,
    }
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)
    os.chmod(path, 0o600)
    print(f"approvalCreated={path}")
    print(f"expiresAt={payload['expiresAt']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
