from __future__ import annotations

from typing import Callable

from .canary import run_provider_canaries
from .config import Settings
from .launch import LaunchGate
from .smoke import run_smoke


class CutoverVerifier:
    def __init__(
        self,
        settings: Settings,
        *,
        launch_gate: LaunchGate | None = None,
        provider_runner: Callable[[Settings], dict[str, object]] = run_provider_canaries,
        smoke_runner: Callable[..., dict[str, object]] = run_smoke,
    ) -> None:
        self.settings = settings
        self.launch_gate = launch_gate or LaunchGate(settings)
        self.provider_runner = provider_runner
        self.smoke_runner = smoke_runner

    def report(self, base_url: str | None = None) -> dict[str, object]:
        target = (base_url or self.settings.app_base_url).rstrip("/")
        launch = self.launch_gate.report()
        blockers = list(launch.get("blockers", []))

        if launch.get("launchReady"):
            providers = self.provider_runner(self.settings)
        else:
            providers = {
                "ok": False,
                "notRun": True,
                "code": "launch_gate",
            }

        if not providers.get("ok"):
            if providers.get("notRun"):
                if "provider_canaries" not in blockers:
                    blockers.append("provider_canaries")
            else:
                for name in ("firebase", "razorpay"):
                    result = providers.get(name)
                    if isinstance(result, dict) and not result.get("ok"):
                        code = str(result.get("code") or f"{name}_canary")
                        blocker = f"canary_{code}"
                        if blocker not in blockers:
                            blockers.append(blocker)

        if launch.get("launchReady") and providers.get("ok"):
            smoke = self.smoke_runner(target, require_https=True)
        else:
            smoke = {"ok": False, "notRun": True, "baseUrl": target, "checks": []}

        if not smoke.get("ok"):
            if smoke.get("notRun"):
                if "public_smoke" not in blockers:
                    blockers.append("public_smoke")
            else:
                for check in smoke.get("checks", []):
                    if isinstance(check, dict) and not check.get("ok"):
                        blocker = f"smoke_{check.get('name', 'unknown')}"
                        if blocker not in blockers:
                            blockers.append(blocker)

        return {
            "cutoverReady": not blockers,
            "blockers": blockers,
            "baseUrl": target,
            "launch": launch,
            "providers": providers,
            "smoke": smoke,
        }
