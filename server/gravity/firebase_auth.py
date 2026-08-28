from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Mapping, Protocol
from importlib.util import find_spec
import json
import os
import time

from .config import Settings


SUPPORTED_SIGN_IN_PROVIDERS = {"google.com", "password", "phone"}


class FirebaseAuthError(Exception):
    """Base class for safe Firebase identity-boundary failures."""


class FirebaseUnavailable(FirebaseAuthError):
    pass


class InvalidFirebaseToken(FirebaseAuthError):
    pass


class FirebaseAccountDisabled(FirebaseAuthError):
    pass


class FirebaseIdentityUnverified(FirebaseAuthError):
    pass


@dataclass(frozen=True, slots=True)
class VerifiedFirebaseIdentity:
    project_id: str
    uid: str
    sign_in_provider: str
    provider_subject: str
    auth_time: int
    email: str | None = None
    email_verified: bool = False
    phone_number: str | None = None
    display_name: str | None = None
    photo_url: str | None = None


class IdentityVerifier(Protocol):
    @property
    def configured(self) -> bool: ...

    def verify(self, id_token: str) -> VerifiedFirebaseIdentity: ...


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


class FirebaseAdminVerifier:
    """Lazily initializes Firebase Admin and returns only verified identity claims."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._app = None
        self._lock = Lock()

    @property
    def configured(self) -> bool:
        if not self.settings.firebase_backend_configured or find_spec("firebase_admin") is None:
            return False
        try:
            self._validated_service_account()
            return True
        except FirebaseUnavailable:
            return False

    def _validated_service_account(self) -> Path:
        path = self.settings.firebase_service_account_path
        if not path or not path.is_absolute():
            raise FirebaseUnavailable("Firebase service account path is not configured")
        try:
            resolved = path.resolve(strict=True)
        except OSError as error:
            raise FirebaseUnavailable("Firebase service account file is unavailable") from error
        if _is_within(resolved, self.settings.web_dir.resolve()):
            raise FirebaseUnavailable("Firebase service account cannot be stored in the public web root")
        if not resolved.is_file() or resolved.stat().st_size > 131_072:
            raise FirebaseUnavailable("Firebase service account file is invalid")
        if os.name == "posix" and resolved.stat().st_mode & 0o077:
            raise FirebaseUnavailable("Firebase service account permissions must be owner-only")
        try:
            document = json.loads(resolved.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise FirebaseUnavailable("Firebase service account file is unreadable") from error
        if document.get("type") != "service_account":
            raise FirebaseUnavailable("Firebase credential must be a service account")
        if document.get("project_id") != self.settings.firebase_project_id:
            raise FirebaseUnavailable("Firebase credential project does not match FIREBASE_PROJECT_ID")
        return resolved

    def _get_app(self):
        if self._app is not None:
            return self._app
        with self._lock:
            if self._app is not None:
                return self._app
            if not self.settings.firebase_backend_configured:
                raise FirebaseUnavailable("Firebase backend is not configured")
            if self.settings.production and os.environ.get("FIREBASE_AUTH_EMULATOR_HOST"):
                raise FirebaseUnavailable("Firebase Auth emulator is forbidden in production")
            credential_path = self._validated_service_account()
            try:
                import firebase_admin
                from firebase_admin import credentials
            except ImportError as error:
                raise FirebaseUnavailable("Firebase Admin SDK is not installed") from error
            try:
                credential = credentials.Certificate(credential_path)
                self._app = firebase_admin.initialize_app(
                    credential,
                    {"projectId": self.settings.firebase_project_id},
                    name=f"gravity-{self.settings.firebase_project_id}-{id(self)}",
                )
            except Exception as error:
                raise FirebaseUnavailable("Firebase Admin initialization failed") from error
            return self._app

    def probe(self) -> None:
        """Perform a read-only Firebase Admin connectivity/permission check."""
        try:
            from firebase_admin import auth
        except ImportError as error:
            raise FirebaseUnavailable("Firebase Admin SDK is not installed") from error
        try:
            auth.list_users(max_results=1, app=self._get_app())
        except FirebaseUnavailable:
            raise
        except Exception as error:
            raise FirebaseUnavailable("Firebase Admin connectivity check failed") from error

    def verify(self, id_token: str) -> VerifiedFirebaseIdentity:
        if not isinstance(id_token, str) or not 20 <= len(id_token) <= 16_384:
            raise InvalidFirebaseToken("Invalid Firebase token")
        try:
            from firebase_admin import auth

            decoded = auth.verify_id_token(id_token, app=self._get_app(), check_revoked=True)
        except FirebaseUnavailable:
            raise
        except ImportError as error:
            raise FirebaseUnavailable("Firebase Admin SDK is not installed") from error
        except Exception as error:
            error_name = type(error).__name__
            if error_name == "UserDisabledError":
                raise FirebaseAccountDisabled("Firebase account is disabled") from error
            if error_name in {
                "ExpiredIdTokenError",
                "InvalidIdTokenError",
                "RevokedIdTokenError",
                "ValueError",
            }:
                raise InvalidFirebaseToken("Invalid Firebase token") from error
            raise FirebaseUnavailable("Firebase verification is temporarily unavailable") from error
        return self._identity_from_claims(decoded)

    def _identity_from_claims(self, decoded: Mapping[str, object]) -> VerifiedFirebaseIdentity:
        project_id = self.settings.firebase_project_id
        uid = decoded.get("uid")
        subject = decoded.get("sub")
        if not isinstance(uid, str) or not isinstance(subject, str) or uid != subject:
            raise InvalidFirebaseToken("Firebase UID claims are inconsistent")
        if not 1 <= len(uid) <= 128:
            raise InvalidFirebaseToken("Firebase UID is invalid")
        if decoded.get("aud") != project_id:
            raise InvalidFirebaseToken("Firebase token audience is invalid")
        if decoded.get("iss") != f"https://securetoken.google.com/{project_id}":
            raise InvalidFirebaseToken("Firebase token issuer is invalid")
        auth_time = decoded.get("auth_time")
        now = int(time.time())
        if isinstance(auth_time, bool) or not isinstance(auth_time, int) or auth_time > now + 60 or auth_time < now - 600:
            raise InvalidFirebaseToken("Firebase authentication is not recent")

        firebase_claim = decoded.get("firebase")
        if not isinstance(firebase_claim, Mapping):
            raise InvalidFirebaseToken("Firebase provider claim is missing")
        if firebase_claim.get("tenant") is not None:
            raise InvalidFirebaseToken("Firebase tenant identities are not enabled")
        provider = firebase_claim.get("sign_in_provider")
        if not isinstance(provider, str) or provider not in SUPPORTED_SIGN_IN_PROVIDERS:
            raise InvalidFirebaseToken("Firebase provider is unsupported")
        identities = firebase_claim.get("identities")
        if not isinstance(identities, Mapping):
            raise InvalidFirebaseToken("Firebase provider identities are missing")
        subjects = identities.get(provider)
        if not isinstance(subjects, list) or len(subjects) != 1 or not isinstance(subjects[0], str):
            raise InvalidFirebaseToken("Firebase provider subject is invalid")
        provider_subject = subjects[0].strip()
        if not provider_subject or len(provider_subject) > 320:
            raise InvalidFirebaseToken("Firebase provider subject is invalid")

        email = decoded.get("email")
        email = email.strip() if isinstance(email, str) and email.strip() else None
        email_verified = decoded.get("email_verified") is True
        phone = decoded.get("phone_number")
        phone = phone.strip() if isinstance(phone, str) and phone.strip() else None
        if provider in {"google.com", "password"} and (not email or not email_verified):
            raise FirebaseIdentityUnverified("A verified Firebase email is required")
        if provider == "phone" and not phone:
            raise FirebaseIdentityUnverified("A verified Firebase phone is required")

        name = decoded.get("name")
        photo = decoded.get("picture")
        return VerifiedFirebaseIdentity(
            project_id=project_id,
            uid=uid,
            sign_in_provider=provider,
            provider_subject=provider_subject,
            auth_time=auth_time,
            email=email,
            email_verified=email_verified,
            phone_number=phone,
            display_name=name.strip()[:120] if isinstance(name, str) and name.strip() else None,
            photo_url=photo.strip()[:1000] if isinstance(photo, str) and photo.strip() else None,
        )
