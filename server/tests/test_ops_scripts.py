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
        self.assertIn("Controlled Windows lifecycle cutover", runbook)
        self.assertIn("-ExpectedReleaseSha $releaseSha -RequireDetachedHead -PreflightOnly", runbook)
        self.assertIn(".\\scripts\\adopt-ngrok.ps1", runbook)
        self.assertIn("-ConfirmAdopt", runbook)
        self.assertIn(".\\scripts\\verify-gravity-tasks.ps1", runbook)

    def test_windows_ngrok_refuses_duplicate_unmanaged_loopback_tunnel(self) -> None:
        tunnel = (ROOT / "scripts" / "start-ngrok.ps1").read_text(encoding="utf-8")
        selector = '[string]$_.config.addr -eq "http://127.0.0.1:$($context.Port)"'
        refusal = "Refusing to start a second ngrok process"
        launcher = "Start-Process -FilePath $ngrokExe"
        self.assertIn(selector, tunnel)
        self.assertIn(refusal, tunnel)
        self.assertLess(tunnel.index(refusal), tunnel.index(launcher))

    def test_notification_scheduler_is_isolated_from_lifecycle_tasks(self) -> None:
        installer = (ROOT / "scripts" / "install-gravity-tasks.ps1").read_text(
            encoding="utf-8"
        )
        termux_installer = (ROOT / "deploy" / "termux" / "install-termux.sh").read_text(
            encoding="utf-8"
        )
        boot = (ROOT / "deploy" / "termux" / "termux-boot-gravity.sh").read_text(
            encoding="utf-8"
        )
        service = (
            ROOT / "deploy" / "termux" / "services" / "gravity-notifications" / "run"
        ).read_text(encoding="utf-8")
        self.assertIn("GravityFitness-Notifications", installer)
        self.assertIn("GravityFitness-Watchdog", installer)
        self.assertIn("GravityFitness-DailyBackup", installer)
        self.assertIn("New-ScheduledTaskTrigger -AtStartup", installer)
        self.assertIn("-MultipleInstances IgnoreNew", installer)
        self.assertIn("run-notifications.ps1", installer)
        self.assertNotIn("SMTP_PASSWORD", installer)
        self.assertNotIn("SMS_API_KEY", installer)
        self.assertNotIn("WHATSAPP_ACCESS_TOKEN", installer)
        self.assertIn("gravity-notifications", termux_installer)
        self.assertIn("gravity-notifications", boot)
        self.assertIn("INTERVAL_SECONDS=3600", service)
        self.assertIn("run-notifications.sh", service)

    def test_admin_health_wrappers_are_read_only_and_task_commands_are_secret_free(self) -> None:
        powershell = (ROOT / "scripts" / "admin-health-check.ps1").read_text(encoding="utf-8")
        shell = (ROOT / "scripts" / "admin-health-check.sh").read_text(encoding="utf-8")
        installer = (ROOT / "scripts" / "install-gravity-tasks.ps1").read_text(encoding="utf-8")
        self.assertIn("admin-health-check.py", powershell)
        self.assertIn("admin-health-check.py", shell)
        self.assertIn("--runtime-dir", powershell)
        self.assertIn("--runtime-dir", shell)
        forbidden = (
            "SECRET_KEY=", "SMTP_PASSWORD=", "SMS_API_KEY=", "WHATSAPP_ACCESS_TOKEN=",
            "RAZORPAY_KEY_SECRET=", "RAZORPAY_WEBHOOK_SECRET=", "FIREBASE_SERVICE_ACCOUNT=",
        )
        for text in (powershell, shell, installer):
            for marker in forbidden:
                self.assertNotIn(marker, text)

    @unittest.skipUnless(sys.platform == "win32", "Windows Task Scheduler preflight")
    def test_task_installer_preflight_is_non_mutating_and_secret_free(self) -> None:
        installer = ROOT / "scripts" / "install-gravity-tasks.ps1"
        with TemporaryDirectory() as temporary:
            config = Path(temporary) / "gravity.env"
            config.write_text("GRAVITY_HOST=127.0.0.1\nGRAVITY_PORT=8799\n", encoding="utf-8")
            result = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(installer),
                 "-ConfigPath", str(config), "-PreflightOnly"],
                cwd=ROOT, capture_output=True, text=True,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = __import__("json").loads(result.stdout.strip())
        self.assertEqual([item["name"] for item in plan["tasks"]], [
            "GravityFitness-Watchdog", "GravityFitness-DailyBackup", "GravityFitness-Notifications"
        ])
        self.assertTrue(all(item["principal"] == "SYSTEM" for item in plan["tasks"]))
        self.assertTrue(all(item["runLevel"] == "Highest" for item in plan["tasks"]))
        for marker in ("SECRET_KEY=", "SMTP_PASSWORD=", "SMS_API_KEY=", "authtoken="):
            self.assertNotIn(marker, result.stdout)

    def test_task_verifier_is_read_only_and_checks_release_identity(self) -> None:
        verifier = (ROOT / "scripts" / "verify-gravity-tasks.ps1").read_text(encoding="utf-8")
        self.assertIn("Get-ScheduledTask", verifier)
        self.assertNotIn("Register-ScheduledTask", verifier)
        self.assertIn("ExpectedReleaseSha", verifier)
        self.assertIn("RequireDetachedHead", verifier)
        self.assertIn("MSFT_TaskBootTrigger", verifier)
        self.assertIn("MultipleInstances", verifier)
        self.assertIn("working_directory_mismatch", verifier)
        self.assertIn("secret_marker", verifier)

    def test_ngrok_adoption_defaults_to_probe_only_and_requires_explicit_commit(self) -> None:
        adoption = (ROOT / "scripts" / "adopt-ngrok.ps1").read_text(encoding="utf-8")
        self.assertIn("ConfirmAdopt", adoption)
        self.assertIn("--probe-only", adoption)
        self.assertIn("Gravity loopback health must be green", adoption)
        self.assertIn("ngrok-skip-browser-warning", adoption)
        self.assertIn("Remove-Item -LiteralPath $temporaryEvidence", adoption)
        self.assertNotIn("authtoken", adoption.casefold())

    def test_release_lifecycle_check_is_read_only_and_secret_safe(self) -> None:
        script = (ROOT / "scripts" / "release-lifecycle-check.ps1").read_text(encoding="utf-8")
        self.assertIn("Get-ScheduledTaskInfo", script)
        self.assertIn("Get-NetTCPConnection", script)
        self.assertIn("verify-gravity-tasks.ps1", script)
        self.assertIn("ngrok-skip-browser-warning", script)
        self.assertNotIn("Register-ScheduledTask", script)
        self.assertNotIn("Stop-Process", script)
        self.assertNotIn("Set-Content", script)
        self.assertNotIn("Remove-Item", script)
        for marker in ("SECRET_KEY=", "SMTP_PASSWORD=", "SMS_API_KEY=", "WHATSAPP_ACCESS_TOKEN="):
            self.assertNotIn(marker, script)
        self.assertIn("--authtoken|authtoken=", script)

    def test_operations_runbook_has_single_post_reboot_acceptance_command(self) -> None:
        runbook = (ROOT / "docs" / "OPERATIONS_RUNBOOK.md").read_text(encoding="utf-8")
        self.assertIn("release-lifecycle-check.ps1", runbook)
        self.assertIn("Exit `0` with `\"ready\":true`", runbook)
        self.assertIn("does not start/stop processes", runbook)
        self.assertIn("Do not proceed to the fresh `pre-admin-v1` backup", runbook)

    def test_managed_ngrok_state_pins_config_path_for_reboot_verification(self) -> None:
        script = (ROOT / "scripts" / "start-ngrok.ps1").read_text(encoding="utf-8")
        self.assertIn("configPath = $ngrokConfig", script)
        self.assertIn("$state.configPath", script)
        self.assertIn("$ngrokConfig", script)

    def test_browser_assets_contain_no_server_secret_configuration_names(self) -> None:
        forbidden = (
            "RAZORPAY_KEY_SECRET", "RAZORPAY_WEBHOOK_SECRET", "SMTP_PASSWORD",
            "WHATSAPP_ACCESS_TOKEN", "SMS_API_KEY", "SECRET_KEY", "session_token",
        )
        for path in (ROOT / "web").rglob("*"):
            if path.suffix not in {".js", ".html"}:
                continue
            text = path.read_text(encoding="utf-8")
            for marker in forbidden:
                self.assertNotIn(marker, text, path)


if __name__ == "__main__":
    unittest.main()
