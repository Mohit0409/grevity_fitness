"""Run Playwright against an isolated in-process Gravity server."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Thread

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.gravity.config import Settings  # noqa: E402
from server.gravity.http import create_server  # noqa: E402


def main() -> int:
    port = int(os.environ.get("GRAVITY_E2E_PORT", "8791"))
    base_url = f"http://127.0.0.1:{port}"
    runtime = TemporaryDirectory(prefix="gravity-e2e-")
    runtime_path = Path(runtime.name)
    environment = dict(os.environ)
    environment.update(
        {
            "GRAVITY_ENV": "development",
            "GRAVITY_HOST": "127.0.0.1",
            "GRAVITY_PORT": str(port),
            "APP_BASE_URL": base_url,
            "GRAVITY_DATA_DIR": str(runtime_path / "data"),
            "GRAVITY_LOG_DIR": str(runtime_path / "logs"),
            "GRAVITY_BACKUP_DIR": str(runtime_path / "backups"),
            "GRAVITY_LOG_LEVEL": "WARNING",
            "SECRET_KEY": "gravity-e2e-secret-key-with-more-than-thirty-two-bytes",
            "FIREBASE_PROJECT_ID": "",
            "FIREBASE_WEB_API_KEY": "",
            "FIREBASE_AUTH_DOMAIN": "",
            "FIREBASE_APP_ID": "",
            "RAZORPAY_KEY_ID": "",
            "RAZORPAY_KEY_SECRET": "",
            "RAZORPAY_WEBHOOK_SECRET": "",
        }
    )
    settings = Settings.load(root_dir=ROOT, environ=environment)
    server = create_server(settings)
    thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    runner_environment = dict(os.environ)
    runner_environment.update(
        {
            "GRAVITY_E2E_EXTERNAL_SERVER": "1",
            "GRAVITY_E2E_PORT": str(port),
        }
    )
    node = os.environ.get("GRAVITY_E2E_NODE", "node")
    cli = ROOT / "node_modules" / "@playwright" / "test" / "cli.js"
    try:
        result = subprocess.run(
            [node, str(cli), "test", *sys.argv[1:]],
            cwd=ROOT,
            env=runner_environment,
            check=False,
        )
        return result.returncode
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        runtime.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
