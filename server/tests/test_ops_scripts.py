from pathlib import Path
from tempfile import TemporaryDirectory
import importlib.util
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
ENV_RUNNER = ROOT / "scripts" / "gravity-env.py"


class OperationsScriptTests(unittest.TestCase):
    def test_dotenv_runner_preserves_spaces_without_shell_evaluation(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            marker = root / "must-not-exist"
            config = root / "gravity.env"
            config.write_text(
                "GRAVITY_PORT=9099\n"
                "BUSINESS_NAME=Gravity Fitness\n"
                f"UNTRUSTED=$(touch {marker})\n",
                encoding="utf-8",
            )
            spec = importlib.util.spec_from_file_location("gravity_env", ENV_RUNNER)
            self.assertIsNotNone(spec)
            self.assertIsNotNone(spec.loader)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            values = module.load_file(config)
            self.assertEqual(
                [values["BUSINESS_NAME"], values["UNTRUSTED"]],
                ["Gravity Fitness", f"$(touch {marker})"],
            )
            self.assertFalse(marker.exists())

    def test_dotenv_print_is_restricted_to_non_secret_operations_keys(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ENV_RUNNER), "--print", "SECRET_KEY"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_managed_launchers_pin_the_backend_to_loopback(self) -> None:
        files = [
            ROOT / "scripts" / "start-gravity.ps1",
            ROOT / "scripts" / "start-gravity.sh",
            ROOT / "deploy" / "termux" / "services" / "gravity" / "run",
        ]
        for path in files:
            text = path.read_text(encoding="utf-8")
            self.assertIn("127.0.0.1", text, path)
            self.assertIn("server.gravity", text, path)

    def test_tunnel_targets_loopback_and_token_is_not_in_git(self) -> None:
        tunnel = (
            ROOT / "deploy" / "termux" / "services" / "gravity-tunnel" / "run"
        ).read_text(encoding="utf-8")
        example = (ROOT / "deploy" / "termux" / "gravity.env.example").read_text(
            encoding="utf-8"
        )
        self.assertIn("--token-file", tunnel)
        self.assertNotRegex(example, r"(?m)^SECRET_KEY=.+$")
        self.assertNotRegex(example, r"(?m)^CLOUDFLARED_TOKEN=.+$")

    def test_termux_installer_has_network_audit_dependency_and_safe_boot_install(self) -> None:
        installer = (ROOT / "deploy" / "termux" / "install-termux.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("iproute2", installer)
        self.assertRegex(installer, r"for command in python3 git curl ss sv svlogd")
        self.assertNotIn("ln -sfn", installer)
        self.assertIn("Refusing to replace existing boot script", installer)

    def test_migration_runbook_uses_valid_windows_script_paths(self) -> None:
        runbook = (ROOT / "docs" / "TERMUX_MIGRATION_RUNBOOK.md").read_text(
            encoding="utf-8"
        )
        self.assertIn(".\\scripts\\status-gravity.ps1", runbook)
        self.assertIn(".\\scripts\\export-gravity-migration.ps1", runbook)
        self.assertNotIn(".scriptsstatus-gravity.ps1", runbook)
        self.assertNotIn(".scriptsexport-gravity-migration.ps1", runbook)

    def test_system_watchdog_requires_explicit_ngrok_paths(self) -> None:
        installer = (ROOT / "scripts" / "install-gravity-tasks.ps1").read_text(
            encoding="utf-8"
        )
        watchdog = (ROOT / "scripts" / "watch-gravity.ps1").read_text(
            encoding="utf-8"
        )
        tunnel = (ROOT / "scripts" / "start-ngrok.ps1").read_text(
            encoding="utf-8"
        )
        runbook = (ROOT / "docs" / "OPERATIONS_RUNBOOK.md").read_text(
            encoding="utf-8"
        )
        for text in (installer, watchdog, tunnel):
            self.assertIn("NgrokConfigPath", text)
            self.assertIn("NgrokExecutablePath", text)
        self.assertIn("task runs as SYSTEM", installer)
        self.assertIn("ngrok configuration was not found", installer)
        self.assertIn("ngrok executable was not found", installer)
        self.assertIn("SYSTEM task recovery", watchdog)
        self.assertIn("-ExplicitPath $NgrokExecutablePath", tunnel)
        self.assertIn("-NgrokConfigPath C:\\ProgramData\\GravityFitness\\ngrok.yml", runbook)
        self.assertIn("-NgrokExecutablePath 'C:\\Program Files\\ngrok\\ngrok.exe'", runbook)


if __name__ == "__main__":
    unittest.main()
