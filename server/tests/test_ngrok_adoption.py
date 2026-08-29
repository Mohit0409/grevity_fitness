from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "scripts" / "ngrok-adoption.py"
spec = importlib.util.spec_from_file_location("gravity_ngrok_adoption", HELPER)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class NgrokAdoptionTests(unittest.TestCase):
    def evidence(self) -> dict[str, object]:
        started = datetime.now(timezone.utc) - timedelta(minutes=2)
        target = "http://127.0.0.1:8787"
        config = r"C:\ProgramData\GravityFitness\ngrok.yml"
        executable = r"C:\Program Files\ngrok\ngrok.exe"
        return {
            "pid": 43210,
            "processExists": True,
            "processName": "ngrok.exe",
            "processExecutable": executable,
            "commandLine": f'"{executable}" http {target} --config "{config}"',
            "processStartedAt": started.isoformat(),
            "processCreationTime": started.isoformat(),
            "expectedExecutable": executable,
            "expectedConfig": config,
            "target": target,
            "tunnels": [
                {"public_url": "https://gravity.example", "config": {"addr": target}}
            ],
        }

    def test_valid_adoption_writes_atomic_managed_state(self) -> None:
        report = module.validate_evidence(self.evidence())
        with TemporaryDirectory() as temporary:
            runtime = Path(temporary)
            self.assertEqual(module.existing_state_status(runtime, report), "absent")
            module.write_managed_state(runtime, report)
            self.assertEqual((runtime / "ngrok.pid").read_text().strip(), "43210")
            state = json.loads((runtime / "ngrok.state.json").read_text())
            self.assertEqual(state["pid"], 43210)
            self.assertEqual(state["target"], "http://127.0.0.1:8787")
            self.assertEqual(state["configPath"], r"C:\ProgramData\GravityFitness\ngrok.yml")
            self.assertEqual((runtime / "ngrok.public-url").read_text().strip(), "https://gravity.example")
            self.assertNotIn("authtoken", json.dumps(state).casefold())

    def test_mismatched_target_is_rejected(self) -> None:
        evidence = self.evidence()
        evidence["tunnels"] = [
            {"public_url": "https://gravity.example", "config": {"addr": "http://127.0.0.1:9999"}}
        ]
        with self.assertRaisesRegex(module.AdoptionError, "no HTTPS tunnel"):
            module.validate_evidence(evidence)

    def test_mismatched_executable_path_is_rejected(self) -> None:
        evidence = self.evidence()
        evidence["processExecutable"] = r"C:\Temp\ngrok.exe"
        with self.assertRaisesRegex(module.AdoptionError, "executable path"):
            module.validate_evidence(evidence)

    def test_stale_pid_is_rejected(self) -> None:
        evidence = self.evidence()
        evidence["processExists"] = False
        with self.assertRaisesRegex(module.AdoptionError, "stale ngrok PID"):
            module.validate_evidence(evidence)

    def test_foreign_process_is_rejected(self) -> None:
        evidence = self.evidence()
        evidence["processName"] = "python.exe"
        with self.assertRaisesRegex(module.AdoptionError, "foreign process"):
            module.validate_evidence(evidence)

    def test_command_line_auth_token_is_rejected(self) -> None:
        evidence = self.evidence()
        evidence["commandLine"] = str(evidence["commandLine"]) + " --authtoken super-secret"
        with self.assertRaisesRegex(module.AdoptionError, "must not contain an auth token"):
            module.validate_evidence(evidence)

    def test_duplicate_matching_tunnels_are_rejected(self) -> None:
        evidence = self.evidence()
        evidence["tunnels"] = [
            {"public_url": "https://one.example", "config": {"addr": evidence["target"]}},
            {"public_url": "https://two.example", "config": {"addr": evidence["target"]}},
        ]
        with self.assertRaisesRegex(module.AdoptionError, "multiple ngrok tunnels"):
            module.validate_evidence(evidence)

    def test_probe_only_cli_never_writes_managed_state(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence_path = root / "evidence.json"
            runtime = root / "runtime"
            evidence_path.write_text(json.dumps(self.evidence()), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(HELPER), "--evidence-json", str(evidence_path),
                 "--runtime-dir", str(runtime), "--probe-only"],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertTrue(report["ready"])
            self.assertTrue(report["probeOnly"])
            self.assertFalse((runtime / "ngrok.pid").exists())
            self.assertFalse((runtime / "ngrok.state.json").exists())


if __name__ == "__main__":
    unittest.main()
