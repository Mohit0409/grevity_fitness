from pathlib import Path
import unittest

from server.gravity.config import Settings
from server.gravity.cutover import CutoverVerifier


ROOT = Path(__file__).resolve().parents[2]


class FakeLaunchGate:
    def __init__(self, report):
        self._report = report

    def report(self):
        return self._report


class CutoverVerifierTests(unittest.TestCase):
    def settings(self) -> Settings:
        return Settings.load(root_dir=ROOT, environ={
            "GRAVITY_ENV": "production",
            "APP_BASE_URL": "https://gravity.example",
            "SECRET_KEY": "x" * 40,
        })

    def test_cutover_passes_only_when_all_three_gates_pass(self):
        settings = self.settings()
        verifier = CutoverVerifier(
            settings,
            launch_gate=FakeLaunchGate({"launchReady": True, "blockers": []}),
            provider_runner=lambda _settings: {
                "ok": True,
                "firebase": {"ok": True},
                "razorpay": {"ok": True},
            },
            smoke_runner=lambda base_url, require_https=False: {
                "ok": require_https and base_url == "https://gravity.example",
                "baseUrl": base_url,
                "checks": [],
            },
        )
        report = verifier.report()
        self.assertTrue(report["cutoverReady"])
        self.assertEqual(report["blockers"], [])

    def test_launch_failure_prevents_provider_and_public_network_checks(self):
        settings = self.settings()
        calls = []
        verifier = CutoverVerifier(
            settings,
            launch_gate=FakeLaunchGate({"launchReady": False, "blockers": ["active_owner"]}),
            provider_runner=lambda _settings: calls.append("providers"),
            smoke_runner=lambda *_args, **_kwargs: calls.append("smoke"),
        )
        report = verifier.report()
        self.assertFalse(report["cutoverReady"])
        self.assertEqual(calls, [])
        self.assertIn("active_owner", report["blockers"])
        self.assertIn("provider_canaries", report["blockers"])
        self.assertIn("public_smoke", report["blockers"])
    def test_provider_failure_blocks_smoke_and_surfaces_safe_code(self):
        settings = self.settings()
        calls = []
        verifier = CutoverVerifier(
            settings,
            launch_gate=FakeLaunchGate({"launchReady": True, "blockers": []}),
            provider_runner=lambda _settings: {
                "ok": False,
                "firebase": {"ok": True, "code": None},
                "razorpay": {"ok": False, "code": "razorpay_http_401"},
            },
            smoke_runner=lambda *_args, **_kwargs: calls.append("smoke"),
        )
        report = verifier.report()
        self.assertFalse(report["cutoverReady"])
        self.assertEqual(calls, [])
        self.assertIn("canary_razorpay_http_401", report["blockers"])
        self.assertIn("public_smoke", report["blockers"])


if __name__ == "__main__":
    unittest.main()
