from __future__ import annotations

from contextlib import closing, contextmanager
from dataclasses import replace
from http.client import HTTPConnection
from http.cookies import SimpleCookie
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier, Lock, Thread
from typing import Iterator
import json
import sqlite3
import time
import unittest

from server.gravity.config import Settings
from server.gravity.firebase_auth import (
    FirebaseAdminVerifier,
    FirebaseIdentityUnverified,
    InvalidFirebaseToken,
    VerifiedFirebaseIdentity,
)
from server.gravity.http import create_server


ROOT = Path(__file__).resolve().parents[2]
TEST_SECRET = "phase-two-test-secret-key-that-is-long-enough"


class MutableClock:
    def __init__(self, value: int = 2_000_000_000) -> None:
        self.value = value

    def __call__(self) -> float:
        return float(self.value)

    def advance(self, seconds: int) -> None:
        self.value += seconds


class FakeVerifier:
    def __init__(self, identities: dict[str, VerifiedFirebaseIdentity], *, configured: bool = True) -> None:
        self.identities = identities
        self.configured = configured

    def verify(self, id_token: str) -> VerifiedFirebaseIdentity:
        result = self.identities.get(id_token)
        if not result:
            raise InvalidFirebaseToken("invalid")
        return result


def identity(
    clock: MutableClock,
    uid: str,
    *,
    provider: str = "password",
    subject: str | None = None,
    email: str | None = None,
    email_verified: bool = True,
    phone: str | None = None,
    name: str | None = "Gravity Member",
    auth_time: int | None = None,
) -> VerifiedFirebaseIdentity:
    return VerifiedFirebaseIdentity(
        project_id="gravity-authe",
        uid=uid,
        sign_in_provider=provider,
        provider_subject=subject or email or phone or uid,
        auth_time=clock.value if auth_time is None else auth_time,
        email=email,
        email_verified=email_verified,
        phone_number=phone,
        display_name=name,
    )


class AuthHarness:
    def __init__(self, server, settings: Settings, clock: MutableClock) -> None:
        self.server = server
        self.settings = settings
        self.clock = clock
        self.base_host = "127.0.0.1"
        self.base_port = server.server_port

    def request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        body: bytes | dict[str, object] | None = None,
    ) -> tuple[int, list[tuple[str, str]], dict[str, object]]:
        prepared_headers = dict(headers or {})
        prepared_body: bytes | None
        if isinstance(body, dict):
            prepared_body = json.dumps(body).encode("utf-8")
            prepared_headers.setdefault("Content-Type", "application/json")
        else:
            prepared_body = body
        connection = HTTPConnection(self.base_host, self.base_port, timeout=5)
        try:
            connection.request(method, path, body=prepared_body, headers=prepared_headers)
            response = connection.getresponse()
            raw = response.read()
            payload = json.loads(raw) if raw else {}
            return response.status, response.getheaders(), payload
        finally:
            connection.close()

    def exchange(
        self,
        token: str,
        *,
        cookie: str | None = None,
        origin: str | None = None,
        forwarded_for: str | None = None,
    ) -> tuple[int, list[tuple[str, str]], dict[str, object]]:
        headers = {
            "Authorization": f"Bearer {token}",
            "Origin": origin or self.settings.app_base_url,
            "User-Agent": "GravityAuthTest/1.0",
        }
        if cookie:
            headers["Cookie"] = cookie
        if forwarded_for:
            headers["X-Forwarded-For"] = forwarded_for
        return self.request("POST", "/api/auth/session", headers=headers, body=b"")


def cookies_from(headers: list[tuple[str, str]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for name, value in headers:
        if name.lower() != "set-cookie":
            continue
        parsed = SimpleCookie()
        parsed.load(value)
        for key, morsel in parsed.items():
            result[key] = morsel.value
    return result


def cookie_header(cookies: dict[str, str]) -> str:
    return "; ".join(f"{key}={value}" for key, value in cookies.items())


@contextmanager
def running_auth_server(
    verifier: FakeVerifier,
    clock: MutableClock,
    *,
    production: bool = False,
    trust_proxy: bool = False,
    trusted_proxy_cidrs: tuple[str, ...] = (),
) -> Iterator[AuthHarness]:
    with TemporaryDirectory() as temporary:
        runtime = Path(temporary)
        environment = {
            "GRAVITY_PORT": "0",
            "GRAVITY_LOG_LEVEL": "CRITICAL",
            "GRAVITY_ENV": "production" if production else "development",
            "APP_BASE_URL": "https://gravity.example" if production else "http://127.0.0.1:0",
            "SECRET_KEY": TEST_SECRET,
            "FIREBASE_PROJECT_ID": "gravity-authe",
            "FIREBASE_WEB_API_KEY": "public-test-api-key",
            "FIREBASE_AUTH_DOMAIN": "gravity-authe.firebaseapp.com",
            "FIREBASE_APP_ID": "1:123:web:test",
        }
        base = Settings.load(root_dir=ROOT, environ=environment)
        settings = replace(
            base,
            data_dir=runtime / "data",
            log_dir=runtime / "logs",
            backup_dir=runtime / "backups",
            database_path=runtime / "data" / "gravity.sqlite3",
            host="127.0.0.1",
            port=0,
            trust_proxy=trust_proxy,
            trusted_proxy_cidrs=trusted_proxy_cidrs,
        )
        server = create_server(settings, verifier=verifier, clock=clock)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield AuthHarness(server, settings, clock)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


class CustomerAuthHttpTests(unittest.TestCase):
    def test_registration_session_persistence_and_hash_only_storage(self):
        clock = MutableClock()
        verifier = FakeVerifier(
            {"token-alice": identity(clock, "uid-alice", email="Alice@Example.COM", subject="alice-sub")}
        )
        with running_auth_server(verifier, clock) as app:
            status, _headers, config = app.request("GET", "/api/auth/config")
            self.assertEqual(status, 200)
            self.assertTrue(config["enabled"])
            self.assertEqual(config["providers"], ["google.com", "phone"])
            self.assertNotIn("serviceAccount", json.dumps(config))

            status, headers, payload = app.exchange("token-alice")
            self.assertEqual(status, 200)
            self.assertTrue(payload["authenticated"])
            self.assertEqual(payload["user"]["email"], "Alice@Example.COM")
            self.assertEqual(payload["user"]["providers"], ["password"])
            self.assertFalse(payload["user"]["profileComplete"])
            cookies = cookies_from(headers)
            self.assertIn("gravity_session", cookies)
            self.assertIn("gravity_csrf", cookies)

            set_cookie_headers = [value for name, value in headers if name.lower() == "set-cookie"]
            session_header = next(value for value in set_cookie_headers if value.startswith("gravity_session="))
            csrf_header = next(value for value in set_cookie_headers if value.startswith("gravity_csrf="))
            self.assertIn("HttpOnly", session_header)
            self.assertIn("SameSite=Lax", session_header)
            self.assertNotIn("Secure", session_header)
            self.assertNotIn("HttpOnly", csrf_header)

            status, _headers, session = app.request(
                "GET", "/api/auth/session", headers={"Cookie": cookie_header(cookies)}
            )
            self.assertEqual(status, 200)
            self.assertTrue(session["authenticated"])

            with closing(sqlite3.connect(app.settings.database_path)) as connection:
                dump = "\n".join(connection.iterdump())
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM customers").fetchone()[0], 1)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM customer_sessions").fetchone()[0], 1)
                token_hash, csrf_hash = connection.execute(
                    "SELECT token_hash, csrf_hash FROM customer_sessions"
                ).fetchone()
                self.assertEqual(len(token_hash), 64)
                self.assertEqual(len(csrf_hash), 64)
                self.assertNotIn(cookies["gravity_session"], dump)
                self.assertNotIn(cookies["gravity_csrf"], dump)
                self.assertNotIn("token-alice", dump)

    def test_duplicate_verified_email_phone_and_provider_are_rejected(self):
        clock = MutableClock()
        verifier = FakeVerifier(
            {
                "email-a": identity(clock, "uid-email-a", email="Member@Example.com", subject="sub-a"),
                "email-b": identity(clock, "uid-email-b", email="member@example.COM", subject="sub-b"),
                "phone-a": identity(
                    clock, "uid-phone-a", provider="phone", phone="+919876543210", subject="+919876543210"
                ),
                "phone-b": identity(
                    clock,
                    "uid-phone-b",
                    provider="google.com",
                    email="other@example.com",
                    phone="+919876543210",
                    subject="google-other",
                ),
            }
        )
        with running_auth_server(verifier, clock) as app:
            self.assertEqual(app.exchange("email-a")[0], 200)
            status, _headers, body = app.exchange("email-b")
            self.assertEqual((status, body["error"]), (409, "account_link_required"))
            self.assertEqual(app.exchange("phone-a")[0], 200)
            status, _headers, body = app.exchange("phone-b")
            self.assertEqual((status, body["error"]), (409, "account_link_required"))
            with closing(sqlite3.connect(app.settings.database_path)) as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM customers").fetchone()[0], 2)

    def test_unverified_identifier_never_auto_links_or_blocks(self):
        clock = MutableClock()
        verifier = FakeVerifier(
            {
                "verified": identity(clock, "uid-a", email="member@example.com", subject="sub-a"),
                "unverified": identity(
                    clock,
                    "uid-b",
                    provider="phone",
                    subject="+919999999999",
                    phone="+919999999999",
                    email="MEMBER@example.com",
                    email_verified=False,
                ),
            }
        )
        with running_auth_server(verifier, clock) as app:
            self.assertEqual(app.exchange("verified")[0], 200)
            self.assertEqual(app.exchange("unverified")[0], 200)
            with closing(sqlite3.connect(app.settings.database_path)) as connection:
                rows = connection.execute(
                    "SELECT normalized_email, email_verified FROM customers ORDER BY created_at, rowid"
                ).fetchall()
                self.assertEqual(rows, [("member@example.com", 1), (None, 0)])

    def test_profile_requires_session_origin_and_csrf_then_confirms_by_refetch(self):
        clock = MutableClock()
        verifier = FakeVerifier({"member": identity(clock, "uid-member", email="member@example.com")})
        with running_auth_server(verifier, clock) as app:
            _, headers, login = app.exchange("member")
            cookies = cookies_from(headers)
            common = {
                "Cookie": cookie_header(cookies),
                "Origin": app.settings.app_base_url,
                "X-CSRF-Token": cookies["gravity_csrf"],
            }
            status, _headers, body = app.request(
                "PATCH",
                "/api/me",
                headers={"Cookie": cookie_header(cookies), "Origin": app.settings.app_base_url},
                body={"displayName": "Member Name"},
            )
            self.assertEqual((status, body["error"]), (403, "invalid_csrf"))

            cross_origin = dict(common, Origin="https://evil.example")
            status, _headers, body = app.request(
                "PATCH", "/api/me", headers=cross_origin, body={"displayName": "Member Name"}
            )
            self.assertEqual((status, body["error"]), (403, "invalid_origin"))

            status, _headers, body = app.request(
                "PATCH",
                "/api/me",
                headers=common,
                body={
                    "displayName": "Member Name",
                    "dateOfBirth": "1995-04-12",
                    "gender": "prefer_not_to_say",
                    "emergencyContactPhone": "+919123456789",
                },
            )
            self.assertEqual(status, 200)
            self.assertTrue(body["user"]["profileComplete"])
            status, _headers, refreshed = app.request(
                "GET", "/api/me", headers={"Cookie": cookie_header(cookies)}
            )
            self.assertEqual(status, 200)
            self.assertEqual(refreshed["user"]["displayName"], "Member Name")
            self.assertEqual(refreshed["user"]["profile"]["dateOfBirth"], "1995-04-12")
            self.assertEqual(login["csrfToken"], cookies["gravity_csrf"])

    def test_logout_revocation_and_disabled_account_handling(self):
        clock = MutableClock()
        verifier = FakeVerifier({"member": identity(clock, "uid-member", email="member@example.com")})
        with running_auth_server(verifier, clock) as app:
            _, headers, _payload = app.exchange("member")
            cookies = cookies_from(headers)
            base_headers = {
                "Cookie": cookie_header(cookies),
                "Origin": app.settings.app_base_url,
                "X-CSRF-Token": "wrong",
            }
            status, _headers, body = app.request("POST", "/api/auth/logout", headers=base_headers, body=b"")
            self.assertEqual((status, body["error"]), (403, "invalid_csrf"))
            base_headers["X-CSRF-Token"] = cookies["gravity_csrf"]
            status, clear_headers, body = app.request(
                "POST", "/api/auth/logout", headers=base_headers, body=b""
            )
            self.assertEqual(status, 200)
            self.assertFalse(body["authenticated"])
            self.assertTrue(any("Max-Age=0" in value for name, value in clear_headers if name.lower() == "set-cookie"))
            status, _headers, body = app.request(
                "GET", "/api/me", headers={"Cookie": cookie_header(cookies)}
            )
            self.assertEqual((status, body["error"]), (401, "unauthenticated"))

            _, second_headers, _payload = app.exchange("member")
            second_cookies = cookies_from(second_headers)
            with closing(sqlite3.connect(app.settings.database_path)) as connection:
                connection.execute("UPDATE customers SET status = 'disabled'")
                connection.commit()
            status, _headers, body = app.request(
                "GET", "/api/me", headers={"Cookie": cookie_header(second_cookies)}
            )
            self.assertEqual((status, body["error"]), (403, "account_disabled"))
            status, _headers, body = app.exchange("member")
            self.assertEqual((status, body["error"]), (403, "account_disabled"))

    def test_idle_expiry_rotation_and_active_session_cap(self):
        clock = MutableClock()
        verifier = FakeVerifier({"member": identity(clock, "uid-member", email="member@example.com")})
        with running_auth_server(verifier, clock) as app:
            _, first_headers, _payload = app.exchange("member")
            first = cookies_from(first_headers)
            _, second_headers, _payload = app.exchange("member", cookie=cookie_header(first))
            second = cookies_from(second_headers)
            status, _headers, _body = app.request(
                "GET", "/api/me", headers={"Cookie": cookie_header(first)}
            )
            self.assertEqual(status, 401)
            status, _headers, _body = app.request(
                "GET", "/api/me", headers={"Cookie": cookie_header(second)}
            )
            self.assertEqual(status, 200)

            clock.advance(app.settings.session_idle_seconds + 1)
            status, _headers, body = app.request(
                "GET", "/api/me", headers={"Cookie": cookie_header(second)}
            )
            self.assertEqual((status, body["error"]), (401, "unauthenticated"))
            with closing(sqlite3.connect(app.settings.database_path)) as connection:
                reasons = {row[0] for row in connection.execute("SELECT revoke_reason FROM customer_sessions")}
                self.assertIn("rotated", reasons)
                self.assertIn("expired", reasons)

    def test_active_session_cap_logout_all_and_duplicate_cookie_rejection(self):
        clock = MutableClock()
        verifier = FakeVerifier({"member": identity(clock, "uid-member", email="member@example.com")})
        with running_auth_server(verifier, clock) as app:
            issued = []
            for _index in range(6):
                status, headers, _payload = app.exchange("member")
                self.assertEqual(status, 200)
                issued.append(cookies_from(headers))
                clock.advance(61)
            with closing(sqlite3.connect(app.settings.database_path)) as connection:
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM customer_sessions WHERE revoked_at IS NULL"
                    ).fetchone()[0],
                    5,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM customer_sessions WHERE revoke_reason = 'session_limit'"
                    ).fetchone()[0],
                    1,
                )
            self.assertEqual(
                app.request("GET", "/api/me", headers={"Cookie": cookie_header(issued[0])})[0], 401
            )
            latest = issued[-1]
            status, _headers, body = app.request(
                "GET",
                "/api/me",
                headers={"Cookie": f"gravity_session={latest['gravity_session']}; gravity_session=duplicate"},
            )
            self.assertEqual((status, body["error"]), (400, "invalid_request"))
            status, _headers, _body = app.request(
                "POST",
                "/api/auth/logout-all",
                headers={
                    "Cookie": cookie_header(latest),
                    "Origin": app.settings.app_base_url,
                    "X-CSRF-Token": latest["gravity_csrf"],
                },
                body=b"",
            )
            self.assertEqual(status, 200)
            self.assertEqual(
                app.request("GET", "/api/me", headers={"Cookie": cookie_header(issued[4])})[0], 401
            )

    def test_concurrent_normalized_identifier_collision_creates_one_customer(self):
        clock = MutableClock()
        verifier = FakeVerifier(
            {
                "one": identity(clock, "uid-one", email="Member@Example.com", subject="subject-one"),
                "two": identity(clock, "uid-two", email="member@example.COM", subject="subject-two"),
            }
        )
        with running_auth_server(verifier, clock) as app:
            barrier = Barrier(3)
            result_lock = Lock()
            statuses: list[int] = []

            def exchange_token(token: str) -> None:
                barrier.wait()
                status, _headers, _payload = app.exchange(token)
                with result_lock:
                    statuses.append(status)

            threads = [Thread(target=exchange_token, args=(token,)) for token in ("one", "two")]
            for thread in threads:
                thread.start()
            barrier.wait()
            for thread in threads:
                thread.join(timeout=5)
            self.assertEqual(sorted(statuses), [200, 409])
            with closing(sqlite3.connect(app.settings.database_path)) as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM customers").fetchone()[0], 1)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM firebase_identities").fetchone()[0], 1)

    def test_explicit_identity_link_rotates_session_and_prevents_cross_account_merge(self):
        clock = MutableClock()
        verifier = FakeVerifier(
            {
                "email": identity(clock, "uid-email", email="member@example.com", subject="email-sub"),
                "phone": identity(
                    clock, "uid-phone", provider="phone", phone="+919876543210", subject="+919876543210"
                ),
            }
        )
        with running_auth_server(verifier, clock) as app:
            _, email_headers, _payload = app.exchange("email")
            email_cookies = cookies_from(email_headers)
            link_headers = {
                "Authorization": "Bearer phone",
                "Cookie": cookie_header(email_cookies),
                "Origin": app.settings.app_base_url,
                "X-CSRF-Token": email_cookies["gravity_csrf"],
            }
            status, linked_headers, linked = app.request(
                "POST", "/api/auth/link", headers=link_headers, body=b""
            )
            self.assertEqual(status, 200)
            self.assertEqual(linked["user"]["phone"], "+919876543210")
            self.assertEqual(linked["user"]["providers"], ["password", "phone"])
            linked_cookies = cookies_from(linked_headers)
            self.assertNotEqual(linked_cookies["gravity_session"], email_cookies["gravity_session"])
            with closing(sqlite3.connect(app.settings.database_path)) as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM customers").fetchone()[0], 1)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM firebase_identities").fetchone()[0], 2)

            status, _headers, _body = app.request(
                "GET", "/api/me", headers={"Cookie": cookie_header(email_cookies)}
            )
            self.assertEqual(status, 401)
            status, _headers, _body = app.request(
                "GET", "/api/me", headers={"Cookie": cookie_header(linked_cookies)}
            )
            self.assertEqual(status, 200)

        clock = MutableClock()
        verifier = FakeVerifier(
            {
                "first": identity(clock, "uid-first", email="first@example.com"),
                "second": identity(clock, "uid-second", email="second@example.com"),
            }
        )
        with running_auth_server(verifier, clock) as app:
            _, first_headers, _ = app.exchange("first")
            app.exchange("second")
            first_cookies = cookies_from(first_headers)
            status, _headers, body = app.request(
                "POST",
                "/api/auth/link",
                headers={
                    "Authorization": "Bearer second",
                    "Cookie": cookie_header(first_cookies),
                    "Origin": app.settings.app_base_url,
                    "X-CSRF-Token": first_cookies["gravity_csrf"],
                },
                body=b"",
            )
            self.assertEqual((status, body["error"]), (409, "account_conflict"))
            with closing(sqlite3.connect(app.settings.database_path)) as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM customers").fetchone()[0], 2)

    def test_invalid_stale_unavailable_and_rate_limited_exchanges_fail_closed(self):
        clock = MutableClock()
        stale = identity(clock, "uid-stale", email="stale@example.com", auth_time=clock.value - 601)
        verifier = FakeVerifier({"stale-token": stale})
        with running_auth_server(verifier, clock) as app:
            status, _headers, body = app.exchange("missing-token")
            self.assertEqual((status, body["error"]), (401, "invalid_credentials"))
            status, _headers, body = app.exchange("stale-token")
            self.assertEqual((status, body["error"]), (401, "invalid_credentials"))
            for index in range(3):
                self.assertEqual(app.exchange(f"invalid-{index}")[0], 401)
            status, headers, body = app.exchange("sixth-attempt")
            self.assertEqual((status, body["error"]), (429, "rate_limited"))
            self.assertTrue(any(name.lower() == "retry-after" for name, _value in headers))

        clock = MutableClock()
        with running_auth_server(FakeVerifier({}, configured=False), clock) as app:
            status, _headers, config = app.request("GET", "/api/auth/config")
            self.assertEqual((status, config), (200, {"enabled": False}))
            status, _headers, body = app.exchange("any-token")
            self.assertEqual((status, body["error"]), (503, "authentication_unavailable"))

    def test_spoofed_forwarded_for_does_not_bypass_rate_limit(self):
        clock = MutableClock()
        with running_auth_server(FakeVerifier({}), clock, trust_proxy=False) as app:
            for index in range(5):
                self.assertEqual(
                    app.exchange(f"invalid-{index}", forwarded_for=f"203.0.113.{index + 1}")[0], 401
                )
            self.assertEqual(app.exchange("invalid-six", forwarded_for="198.51.100.40")[0], 429)

    def test_known_routes_reject_wrong_methods_and_login_csrf(self):
        clock = MutableClock()
        verifier = FakeVerifier({"member": identity(clock, "uid-member", email="member@example.com")})
        with running_auth_server(verifier, clock) as app:
            status, headers, body = app.request("POST", "/api/auth/config", body=b"")
            self.assertEqual((status, body["error"]), (405, "method_not_allowed"))
            self.assertTrue(any(name.lower() == "allow" for name, _value in headers))
            status, _headers, body = app.request(
                "POST", "/api/auth/session", headers={"Authorization": "Bearer member"}, body=b""
            )
            self.assertEqual((status, body["error"]), (403, "invalid_origin"))
            status, _headers, body = app.request(
                "POST",
                "/api/auth/session",
                headers={
                    "Authorization": "Bearer member",
                    "Origin": app.settings.app_base_url,
                    "Content-Type": "application/json",
                },
                body={"idToken": "member"},
            )
            self.assertEqual((status, body["error"]), (400, "invalid_request"))

    def test_production_cookie_names_and_flags_are_host_only_secure(self):
        clock = MutableClock()
        verifier = FakeVerifier({"member": identity(clock, "uid-member", email="member@example.com")})
        with running_auth_server(verifier, clock, production=True) as app:
            status, headers, _payload = app.exchange("member")
            self.assertEqual(status, 200)
            cookie_headers = [value for name, value in headers if name.lower() == "set-cookie"]
            session = next(value for value in cookie_headers if value.startswith("__Host-gravity_session="))
            csrf = next(value for value in cookie_headers if value.startswith("__Host-gravity_csrf="))
            self.assertIn("Secure", session)
            self.assertIn("HttpOnly", session)
            self.assertIn("Path=/", session)
            self.assertNotIn("Domain=", session)
            self.assertIn("Secure", csrf)
            self.assertNotIn("HttpOnly", csrf)


class FirebaseClaimTests(unittest.TestCase):
    def test_claim_boundary_pins_uid_project_provider_verification_and_recency(self):
        settings = Settings.load(
            root_dir=ROOT,
            environ={"FIREBASE_PROJECT_ID": "gravity-authe", "SECRET_KEY": TEST_SECRET},
        )
        verifier = FirebaseAdminVerifier(settings)
        now = int(time.time())
        claims = {
            "uid": "firebase-uid",
            "sub": "firebase-uid",
            "aud": "gravity-authe",
            "iss": "https://securetoken.google.com/gravity-authe",
            "auth_time": now,
            "email": "member@example.com",
            "email_verified": True,
            "firebase": {
                "sign_in_provider": "google.com",
                "identities": {"google.com": ["google-subject"]},
            },
        }
        result = verifier._identity_from_claims(claims)
        self.assertEqual(result.uid, "firebase-uid")
        self.assertEqual(result.provider_subject, "google-subject")

        for mutation in (
            {"aud": "other-project"},
            {"iss": "https://securetoken.google.com/other-project"},
            {"sub": "other-uid"},
            {"auth_time": now - 601},
            {"email_verified": False},
            {"auth_time": True},
        ):
            changed = dict(claims)
            changed.update(mutation)
            with self.assertRaises((InvalidFirebaseToken, FirebaseIdentityUnverified)):
                verifier._identity_from_claims(changed)
        tenant_claims = dict(claims)
        tenant_claims["firebase"] = dict(claims["firebase"], tenant="tenant-a")
        with self.assertRaises(InvalidFirebaseToken):
            verifier._identity_from_claims(tenant_claims)

    def test_production_configuration_requires_https_and_strong_secret(self):
        settings = Settings.load(
            root_dir=ROOT,
            environ={"GRAVITY_ENV": "production", "APP_BASE_URL": "http://gravity.example"},
        )
        with self.assertRaisesRegex(RuntimeError, "HTTPS"):
            settings.ensure_directories()
        settings = Settings.load(
            root_dir=ROOT,
            environ={"GRAVITY_ENV": "production", "APP_BASE_URL": "https://gravity.example", "SECRET_KEY": ""},
        )
        with self.assertRaisesRegex(RuntimeError, "SECRET_KEY"):
            settings.ensure_directories()


if __name__ == "__main__":
    unittest.main()
