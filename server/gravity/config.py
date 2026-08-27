from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Mapping
from ipaddress import ip_network
import os
import re


GSTIN_PATTERN = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")


def _load_dotenv(path: Path, target: dict[str, str]) -> None:
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in target:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        target[key] = value


def _boolean(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Invalid boolean configuration value: {value!r}")


def _port(value: str | None) -> int:
    port = int(value or "8787")
    if not 0 <= port <= 65535:
        raise ValueError("GRAVITY_PORT must be between 0 and 65535")
    return port


def _resolved_path(root: Path, value: str, default: str) -> Path:
    candidate = Path(value or default).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    return candidate.resolve()


@dataclass(frozen=True, slots=True)
class Settings:
    root_dir: Path
    web_dir: Path
    migrations_dir: Path
    data_dir: Path
    log_dir: Path
    backup_dir: Path
    database_path: Path
    environment: str
    host: str
    port: int
    app_base_url: str
    log_level: str
    trust_proxy: bool
    trusted_proxy_cidrs: tuple[str, ...]
    secret_key: str
    firebase_project_id: str
    firebase_web_api_key: str
    firebase_auth_domain: str
    firebase_app_id: str
    firebase_service_account_path: Path | None
    razorpay_mode: str
    razorpay_key_id: str
    razorpay_key_secret: str
    razorpay_webhook_secret: str
    whatsapp_provider: str
    whatsapp_access_token: str
    whatsapp_phone_number_id: str
    sms_provider: str
    sms_api_key: str
    smtp_host: str
    smtp_port: int
    smtp_security: str
    smtp_username: str
    smtp_password: str
    email_from: str
    owner_phone: str
    owner_whatsapp: str
    owner_email: str
    business_name: str
    business_address: str
    business_gstin: str
    tax_invoice_enabled: bool
    business_instagram: str
    google_analytics_id: str
    meta_pixel_id: str
    session_idle_seconds: int
    session_absolute_seconds: int

    @classmethod
    def load(
        cls,
        *,
        root_dir: Path | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> "Settings":
        root = (root_dir or Path(__file__).resolve().parents[2]).resolve()
        values = dict(os.environ if environ is None else environ)
        _load_dotenv(root / ".env", values)

        data_dir = _resolved_path(root, values.get("GRAVITY_DATA_DIR", ""), ".gravity/data")
        log_dir = _resolved_path(root, values.get("GRAVITY_LOG_DIR", ""), ".gravity/logs")
        backup_dir = _resolved_path(root, values.get("GRAVITY_BACKUP_DIR", ""), ".gravity/backups")
        host = values.get("GRAVITY_HOST", "127.0.0.1").strip() or "127.0.0.1"
        port = _port(values.get("GRAVITY_PORT"))
        environment = values.get("GRAVITY_ENV", "development").strip().lower() or "development"
        base_url = values.get("APP_BASE_URL", f"http://{host}:{port}").strip().rstrip("/")
        service_account_value = values.get("FIREBASE_SERVICE_ACCOUNT_PATH", "").strip()
        if service_account_value and not Path(service_account_value).expanduser().is_absolute():
            raise ValueError("FIREBASE_SERVICE_ACCOUNT_PATH must be absolute")
        service_account_path = (
            _resolved_path(root, service_account_value, service_account_value)
            if service_account_value
            else None
        )
        razorpay_mode = values.get("RAZORPAY_MODE", "test").strip().lower() or "test"
        if razorpay_mode not in {"test", "live"}:
            raise ValueError("RAZORPAY_MODE must be test or live")
        smtp_port = int(values.get("SMTP_PORT", "587") or "587")
        if not 1 <= smtp_port <= 65535:
            raise ValueError("SMTP_PORT must be between 1 and 65535")
        smtp_security = values.get("SMTP_SECURITY", "starttls").strip().lower() or "starttls"
        if smtp_security not in {"starttls", "ssl", "none"}:
            raise ValueError("SMTP_SECURITY must be starttls, ssl, or none")
        idle_seconds = int(values.get("SESSION_IDLE_SECONDS", "43200"))
        absolute_seconds = int(values.get("SESSION_ABSOLUTE_SECONDS", "2592000"))
        if idle_seconds < 300 or absolute_seconds < idle_seconds:
            raise ValueError("Session durations must be at least five minutes and absolute >= idle")
        trusted_proxy_cidrs = tuple(
            value.strip()
            for value in values.get("GRAVITY_TRUSTED_PROXY_CIDRS", "").split(",")
            if value.strip()
        )
        for cidr in trusted_proxy_cidrs:
            ip_network(cidr, strict=False)

        return cls(
            root_dir=root,
            web_dir=(root / "web").resolve(),
            migrations_dir=(root / "server" / "migrations").resolve(),
            data_dir=data_dir,
            log_dir=log_dir,
            backup_dir=backup_dir,
            database_path=data_dir / "gravity.sqlite3",
            environment=environment,
            host=host,
            port=port,
            app_base_url=base_url,
            log_level=values.get("GRAVITY_LOG_LEVEL", "INFO").strip().upper() or "INFO",
            trust_proxy=_boolean(values.get("GRAVITY_TRUST_PROXY"), False),
            trusted_proxy_cidrs=trusted_proxy_cidrs,
            secret_key=values.get("SECRET_KEY", "").strip(),
            firebase_project_id=values.get("FIREBASE_PROJECT_ID", "").strip(),
            firebase_web_api_key=values.get("FIREBASE_WEB_API_KEY", "").strip(),
            firebase_auth_domain=values.get("FIREBASE_AUTH_DOMAIN", "").strip(),
            firebase_app_id=values.get("FIREBASE_APP_ID", "").strip(),
            firebase_service_account_path=service_account_path,
            razorpay_mode=razorpay_mode,
            razorpay_key_id=values.get("RAZORPAY_KEY_ID", "").strip(),
            razorpay_key_secret=values.get("RAZORPAY_KEY_SECRET", "").strip(),
            razorpay_webhook_secret=values.get("RAZORPAY_WEBHOOK_SECRET", "").strip(),
            whatsapp_provider=values.get("WHATSAPP_PROVIDER", "").strip(),
            whatsapp_access_token=values.get("WHATSAPP_ACCESS_TOKEN", "").strip(),
            whatsapp_phone_number_id=values.get("WHATSAPP_PHONE_NUMBER_ID", "").strip(),
            sms_provider=values.get("SMS_PROVIDER", "").strip(),
            sms_api_key=values.get("SMS_API_KEY", "").strip(),
            smtp_host=values.get("SMTP_HOST", "").strip(),
            smtp_port=smtp_port,
            smtp_security=smtp_security,
            smtp_username=values.get("SMTP_USERNAME", "").strip(),
            smtp_password=values.get("SMTP_PASSWORD", "").strip(),
            email_from=values.get("EMAIL_FROM", "").strip(),
            owner_phone=values.get("OWNER_PHONE", "").strip(),
            owner_whatsapp=values.get("OWNER_WHATSAPP", "").strip(),
            owner_email=values.get("OWNER_EMAIL", "").strip(),
            business_name=values.get("BUSINESS_NAME", "Gravity Fitness").strip() or "Gravity Fitness",
            business_address=values.get("BUSINESS_ADDRESS", "").strip(),
            business_gstin=values.get("BUSINESS_GSTIN", "").strip().upper(),
            tax_invoice_enabled=_boolean(values.get("TAX_INVOICE_ENABLED"), False),
            business_instagram=values.get("BUSINESS_INSTAGRAM", "").strip(),
            google_analytics_id=values.get("GOOGLE_ANALYTICS_ID", "").strip(),
            meta_pixel_id=values.get("META_PIXEL_ID", "").strip(),
            session_idle_seconds=idle_seconds,
            session_absolute_seconds=absolute_seconds,
        )

    @property
    def production(self) -> bool:
        return self.environment == "production"

    def ensure_directories(self) -> None:
        if not self.web_dir.is_dir():
            raise RuntimeError(f"Public web directory is missing: {self.web_dir}")
        if not self.migrations_dir.is_dir():
            raise RuntimeError(f"Migrations directory is missing: {self.migrations_dir}")
        for directory in (self.data_dir, self.log_dir, self.backup_dir):
            directory.mkdir(parents=True, exist_ok=True)
        if self.production:
            if not self.app_base_url.startswith("https://"):
                raise RuntimeError("APP_BASE_URL must use HTTPS in production")
            if len(self.secret_key.encode("utf-8")) < 32:
                raise RuntimeError("SECRET_KEY must contain at least 32 bytes in production")
            if self.trust_proxy and not self.trusted_proxy_cidrs:
                raise RuntimeError("GRAVITY_TRUST_PROXY requires GRAVITY_TRUSTED_PROXY_CIDRS")

    @property
    def firebase_client_configured(self) -> bool:
        return all(
            (
                self.firebase_project_id,
                self.firebase_web_api_key,
                self.firebase_auth_domain,
                self.firebase_app_id,
            )
        )

    @property
    def firebase_backend_configured(self) -> bool:
        return bool(
            self.firebase_project_id
            and self.firebase_service_account_path
            and len(self.secret_key.encode("utf-8")) >= 32
        )

    @property
    def razorpay_checkout_configured(self) -> bool:
        return bool(self.razorpay_key_id and self.razorpay_key_secret)

    @property
    def razorpay_webhook_configured(self) -> bool:
        return bool(self.razorpay_webhook_secret)

    @property
    def whatsapp_credentials_configured(self) -> bool:
        return bool(self.whatsapp_provider and self.whatsapp_access_token and self.whatsapp_phone_number_id)

    @property
    def sms_credentials_configured(self) -> bool:
        return bool(self.sms_provider and self.sms_api_key)

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_username and self.smtp_password and self.email_from)

    @property
    def business_identity_configured(self) -> bool:
        return bool(self.business_name and self.business_address and (self.owner_phone or self.owner_email))

    @property
    def gstin_format_valid(self) -> bool:
        return bool(self.business_gstin and GSTIN_PATTERN.fullmatch(self.business_gstin))

    @property
    def tax_invoice_identity_configured(self) -> bool:
        return bool(self.tax_invoice_enabled and self.business_identity_configured and self.gstin_format_valid)

    @property
    def google_analytics_configured(self) -> bool:
        return bool(self.google_analytics_id)

    @property
    def meta_pixel_configured(self) -> bool:
        return bool(self.meta_pixel_id)

    @property
    def session_cookie_name(self) -> str:
        if self.production and self.app_base_url.startswith("https://"):
            return "__Host-gravity_session"
        return "gravity_session"

    @property
    def csrf_cookie_name(self) -> str:
        if self.production and self.app_base_url.startswith("https://"):
            return "__Host-gravity_csrf"
        return "gravity_csrf"

    @property
    def admin_session_cookie_name(self) -> str:
        if self.production and self.app_base_url.startswith("https://"):
            return "__Host-gravity_admin_session"
        return "gravity_admin_session"

    @property
    def admin_csrf_cookie_name(self) -> str:
        if self.production and self.app_base_url.startswith("https://"):
            return "__Host-gravity_admin_csrf"
        return "gravity_admin_csrf"

    @property
    def admin_challenge_cookie_name(self) -> str:
        if self.production and self.app_base_url.startswith("https://"):
            return "__Host-gravity_admin_challenge"
        return "gravity_admin_challenge"

    def with_network(self, *, host: str | None = None, port: int | None = None) -> "Settings":
        return replace(self, host=host or self.host, port=self.port if port is None else port)
