from __future__ import annotations

import subprocess
import sys


def _github_escape(value: str) -> str:
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def main() -> int:
    command = [sys.executable, "-m", "unittest", "discover", "-s", "server/tests", "-v"]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.stdout:
        sys.stdout.write(result.stdout)
    if result.stderr:
        sys.stderr.write(result.stderr)
    if result.returncode != 0:
        combined = (result.stdout + "\n" + result.stderr).strip()
        tail = combined[-3500:]
        print(f"::error title=Python unittest failure::{_github_escape(tail)}")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
