from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import os
import unittest
from unittest import mock

from server.gravity.config import Settings
from server.gravity.runtime import RuntimeLease, RuntimeLeaseError, runtime_dir


ROOT = Path(__file__).resolve().parents[2]


class RuntimeLeaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        root = Path(self.temporary.name)
        base = Settings.load(root_dir=ROOT, environ={"SECRET_KEY": "x" * 40})
        self.settings = replace(base, root_dir=root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_lease_writes_process_owned_metadata_and_cleans_up(self) -> None:
        with RuntimeLease(self.settings) as lease:
            self.assertEqual(int(lease.pid_file.read_text()), os.getpid())
            state = json.loads(lease.state_file.read_text(encoding="utf-8"))
            self.assertEqual(state["pid"], os.getpid())
            self.assertIn("bootId", state)
            # Windows may expose the same directory through an 8.3 short path
            # (for example RUNNER~1) and its long-name alias. Compare filesystem
            # identity rather than the textual spelling of those equivalent paths.
            self.assertTrue(os.path.samefile(state["projectRoot"], self.settings.root_dir))
            self.assertTrue(os.path.samefile(state["executable"], os.sys.executable))
            self.assertEqual(state["module"], "server.gravity")
            self.assertEqual(state["host"], "127.0.0.1")
        self.assertFalse(lease.pid_file.exists())
        self.assertFalse(lease.state_file.exists())

    def test_live_foreign_pid_is_rejected(self) -> None:
        lease = RuntimeLease(self.settings)
        lease.directory.mkdir(parents=True)
        lease.pid_file.write_text(str(os.getpid() + 1), encoding="ascii")
        with mock.patch("server.gravity.runtime._pid_is_running", return_value=True):
            with self.assertRaises(RuntimeLeaseError):
                lease.acquire()

    def test_stale_pid_is_replaced(self) -> None:
        lease = RuntimeLease(self.settings)
        lease.directory.mkdir(parents=True)
        lease.pid_file.write_text("999999999", encoding="ascii")
        with mock.patch("server.gravity.runtime._pid_is_running", return_value=False):
            with lease:
                self.assertEqual(int(lease.pid_file.read_text()), os.getpid())


    def test_pid_reused_after_reboot_is_replaced(self) -> None:
        lease = RuntimeLease(self.settings)
        lease.directory.mkdir(parents=True)
        reused_pid = os.getpid() + 1
        lease.pid_file.write_text(str(reused_pid), encoding="ascii")
        lease.state_file.write_text(
            json.dumps({"pid": reused_pid, "bootId": "previous-boot"}),
            encoding="utf-8",
        )
        with (
            mock.patch("server.gravity.runtime._system_boot_id", return_value="current-boot"),
            mock.patch("server.gravity.runtime._pid_is_running", return_value=True) as running,
        ):
            with lease:
                self.assertEqual(int(lease.pid_file.read_text()), os.getpid())
            running.assert_not_called()

    def test_custom_runtime_directory_is_resolved_from_project(self) -> None:
        with mock.patch.dict(os.environ, {"GRAVITY_RUNTIME_DIR": "runtime-state"}):
            self.assertEqual(
                runtime_dir(self.settings),
                (self.settings.root_dir / "runtime-state").resolve(),
            )


if __name__ == "__main__":
    unittest.main()
