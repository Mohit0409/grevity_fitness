#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import argparse
import json
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.gravity.admin_health import AdminHealthCheck
from server.gravity.config import Settings

def main() -> int:
    parser = argparse.ArgumentParser(description="Run a PII-free Gravity admin operations health check")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--runtime-dir", type=Path)
    parser.add_argument("--base-url")
    parser.add_argument("--scheduler-max-age-minutes", type=float, default=90.0)
    args = parser.parse_args()

    root = args.root.expanduser().resolve()
    settings = Settings.load(root_dir=root)
    runtime_value = args.runtime_dir or Path(os.environ.get("GRAVITY_RUNTIME_DIR", root / ".gravity"))
    if not runtime_value.is_absolute():
        runtime_value = root / runtime_value
    report = AdminHealthCheck(
        settings,
        runtime_value,
        base_url=args.base_url,
        scheduler_max_age_minutes=args.scheduler_max_age_minutes,
    ).report()
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
