#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path


PRINTABLE_KEYS = {
    "APP_BASE_URL",
    "GRAVITY_HOST",
    "GRAVITY_PORT",
    "GRAVITY_PYTHON",
    "GRAVITY_RUNTIME_DIR",
}


def load_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key.replace("_", "a").isalnum() or key[0].isdigit():
            raise SystemExit(f"Invalid environment variable name in {path}: {key}")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values.setdefault(key, value)
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description="Load a Gravity dotenv file without shell evaluation")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--print", dest="print_key", choices=sorted(PRINTABLE_KEYS))
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    environment = dict(os.environ)
    if args.config:
        path = args.config.expanduser().resolve()
        if not path.is_file():
            raise SystemExit(f"Gravity environment file does not exist: {path}")
        environment.update(load_file(path))
        environment["GRAVITY_ENV_FILE"] = str(path)

    if args.print_key:
        print(environment.get(args.print_key, ""))
        return 0
    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("a command is required unless --print is used")
    os.execvpe(command[0], command, environment)
    return 127


if __name__ == "__main__":
    raise SystemExit(main())
