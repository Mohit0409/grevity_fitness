from __future__ import annotations

from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import base64
import json

from .config import Settings
from .firebase_auth import FirebaseAdminVerifier, FirebaseUnavailable


RAZORPAY_ORDERS_ENDPOINT = "https://api.razorpay.com/v1/orders?count=1"
MAX_CANARY_RESPONSE_BYTES = 131_072


def _firebase_auth_policy_code(settings: Settings) -> str | None:
    """Read Firebase Auth project policy without exposing provider data or secrets."""
    try:
        from google.auth.transport.requests import AuthorizedSession
        from google.oauth2 import service_account
    except ImportError:
        return "firebase_auth_policy_probe"

    path = settings.firebase_service_account_path
    if not path or not path.is_file():
        return "firebase_service_account_file"
    try:
        credentials = service_account.Credentials.from_service_account_file(
            str(Path(path)),
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
        session = AuthorizedSession(credentials)
        base = f"https://identitytoolkit.googleapis.com/admin/v2/projects/{settings.firebase_project_id}"
        config_response = session.get(f"{base}/config", timeout=8)
        if not config_response.ok:
            return "firebase_auth_policy_probe"
        config = config_response.json()
        phone = ((config.get("signIn") or {}).get("phoneNumber") or {})
        if not phone.get("enabled"):
            return "firebase_phone_provider"
        allowed_regions = (
            (((config.get("smsRegionConfig") or {}).get("allowlistOnly") or {}).get("allowedRegions"))
            or []
        )
        if "IN" not in allowed_regions:
            return "firebase_sms_region"

        google_response = session.get(f"{base}/defaultSupportedIdpConfigs/google.com", timeout=8)
        if not google_response.ok or not (google_response.json() or {}).get("enabled"):
            return "firebase_google_provider"
    except Exception:
        return "firebase_auth_policy_probe"
    return None


def firebase_canary(
    settings: Settings,
    *,
    probe: Callable[[], None] | None = None,
    policy_probe: Callable[[], str | None] | None = None,
) -> dict[str, object]:
    if not settings.production:
        return {"ok": False, "status": "blocked", "code": "production_mode"}
    if not settings.firebase_client_configured:
        return {"ok": False, "status": "blocked", "code": "firebase_client"}
    if not settings.firebase_backend_configured:
        return {"ok": False, "status": "blocked", "code": "firebase_backend"}
    if not settings.firebase_service_account_path or not settings.firebase_service_account_path.is_file():
        return {"ok": False, "status": "blocked", "code": "firebase_service_account_file"}
    try:
        (probe or FirebaseAdminVerifier(settings).probe)()
    except FirebaseUnavailable:
        return {"ok": False, "status": "failed", "code": "firebase_admin_probe"}
    except Exception:
        return {"ok": False, "status": "failed", "code": "firebase_admin_probe"}
    try:
        policy_code = (policy_probe or (lambda: _firebase_auth_policy_code(settings)))()
    except Exception:
        policy_code = "firebase_auth_policy_probe"
    if policy_code:
        return {"ok": False, "status": "failed", "code": policy_code}
    return {"ok": True, "status": "passed", "code": None}


def razorpay_canary(
    settings: Settings,
    *,
    opener: Callable[..., object] = urlopen,
) -> dict[str, object]:
    if not settings.razorpay_requested:
        return {"ok": True, "status": "skipped", "code": "razorpay_disabled"}
    if not settings.production:
        return {"ok": False, "status": "blocked", "code": "production_mode"}
    if settings.razorpay_mode != "live":
        return {"ok": False, "status": "blocked", "code": "razorpay_live_mode"}
    if not settings.razorpay_checkout_configured:
        return {"ok": False, "status": "blocked", "code": "razorpay_checkout"}
    if not settings.razorpay_webhook_configured:
        return {"ok": False, "status": "blocked", "code": "razorpay_webhook"}

    token = base64.b64encode(
        f"{settings.razorpay_key_id}:{settings.razorpay_key_secret}".encode("utf-8")
    ).decode("ascii")
    request = Request(
        RAZORPAY_ORDERS_ENDPOINT,
        method="GET",
        headers={
            "Authorization": f"Basic {token}",
            "Accept": "application/json",
            "User-Agent": "GravityProviderCanary/1.0",
        },
    )
    try:
        with opener(request, timeout=8) as response:
            body = response.read(MAX_CANARY_RESPONSE_BYTES)
            status = getattr(response, "status", 200)
    except HTTPError as error:
        return {
            "ok": False,
            "status": "failed",
            "code": f"razorpay_http_{int(error.code)}",
        }
    except (URLError, OSError, TimeoutError):
        return {"ok": False, "status": "failed", "code": "razorpay_unreachable"}
    except Exception:
        return {"ok": False, "status": "failed", "code": "razorpay_unreachable"}

    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"ok": False, "status": "failed", "code": "razorpay_invalid_response"}
    valid = bool(
        status == 200
        and isinstance(payload, dict)
        and payload.get("entity") == "collection"
        and isinstance(payload.get("count"), int)
        and isinstance(payload.get("items"), list)
    )
    if not valid:
        return {"ok": False, "status": "failed", "code": "razorpay_invalid_response"}
    return {"ok": True, "status": "passed", "code": None}


def run_provider_canaries(
    settings: Settings,
    *,
    firebase_probe: Callable[[], None] | None = None,
    firebase_policy_probe: Callable[[], str | None] | None = None,
    razorpay_opener: Callable[..., object] = urlopen,
) -> dict[str, object]:
    firebase = firebase_canary(
        settings,
        probe=firebase_probe,
        policy_probe=firebase_policy_probe,
    )
    razorpay = razorpay_canary(settings, opener=razorpay_opener)
    return {
        "ok": bool(firebase["ok"] and razorpay["ok"]),
        "firebase": firebase,
        "razorpay": razorpay,
    }
