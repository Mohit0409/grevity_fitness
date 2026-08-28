from __future__ import annotations

from http.client import HTTPMessage
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import json


MAX_RESPONSE_BYTES = 1024 * 1024


def _fetch(base_url: str, path: str) -> tuple[int | None, HTTPMessage | None, bytes]:
    request = Request(
        base_url.rstrip("/") + path,
        headers={"User-Agent": "GravityLaunchSmoke/1.0", "Accept": "application/json,text/html,*/*"},
    )
    try:
        with urlopen(request, timeout=8) as response:
            return response.status, response.headers, response.read(MAX_RESPONSE_BYTES)
    except HTTPError as error:
        return error.code, error.headers, error.read(MAX_RESPONSE_BYTES)
    except (URLError, OSError, TimeoutError):
        return None, None, b""


def _json(body: bytes) -> object | None:
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def run_smoke(base_url: str, *, require_https: bool = False) -> dict[str, object]:
    checks: list[dict[str, object]] = []

    def record(name: str, ok: bool, status: int | None) -> None:
        checks.append({"name": name, "ok": bool(ok), "status": status})

    if require_https:
        record("https_transport", base_url.lower().startswith("https://"), None)

    root_status, root_headers, _root_body = _fetch(base_url, "/")
    record("public_home", root_status == 200, root_status)
    header_ok = bool(
        root_headers
        and root_headers.get("X-Content-Type-Options") == "nosniff"
        and root_headers.get("X-Frame-Options") == "DENY"
        and "frame-ancestors 'none'" in root_headers.get("Content-Security-Policy", "")
    )
    record("security_headers", header_ok, root_status)
    if base_url.lower().startswith("https://"):
        hsts_ok = bool(root_headers and root_headers.get("Strict-Transport-Security"))
        record("hsts", hsts_ok, root_status)

    health_status, _headers, health_body = _fetch(base_url, "/api/health")
    health = _json(health_body)
    health_ok = bool(
        health_status == 200
        and isinstance(health, dict)
        and health.get("status") == "ok"
        and health.get("service") == "Gravity Fitness"
        and health.get("database") == "ok"
    )
    record("health_contract", health_ok, health_status)

    for name, path in (("account_page", "/account"), ("admin_page", "/admin")):
        status, _headers, _body = _fetch(base_url, path)
        record(name, status == 200, status)

    plan_status, _headers, plan_body = _fetch(base_url, "/api/membership/plans")
    plans = _json(plan_body)
    plans_ok = bool(
        plan_status == 200
        and isinstance(plans, dict)
        and isinstance(plans.get("plans"), list)
        and len(plans["plans"]) > 0
    )
    record("active_membership_catalog", plans_ok, plan_status)

    for name, path, expected in (
        ("customer_private_boundary", "/api/me", 401),
        ("admin_private_boundary", "/api/admin/readiness", 401),
        ("dotenv_not_public", "/.env", 404),
        ("server_source_not_public", "/server/gravity/config.py", 404),
    ):
        status, _headers, _body = _fetch(base_url, path)
        record(name, status == expected, status)

    return {
        "ok": all(bool(check["ok"]) for check in checks),
        "baseUrl": base_url.rstrip("/"),
        "checks": checks,
    }
