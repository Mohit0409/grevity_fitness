from __future__ import annotations

from ipaddress import ip_network

from .config import Settings


class ReadinessService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @staticmethod
    def _state(configured: bool, *, adapter_ready: bool = True) -> dict[str, object]:
        if configured and adapter_ready:
            status = "ready"
        elif configured:
            status = "blocked_adapter_missing"
        else:
            status = "blocked_external_config"
        return {
            "configured": configured,
            "adapterReady": adapter_ready,
            "status": status,
        }

    def report(self) -> dict[str, object]:
        s = self.settings
        https_base = s.app_base_url.startswith("https://")
        strong_secret = len(s.secret_key.encode("utf-8")) >= 32
        service_account_file_present = bool(
            s.firebase_service_account_path and s.firebase_service_account_path.is_file()
        )
        loopback_host = s.host in {"127.0.0.1", "::1", "localhost"}
        loopback_v4 = ip_network("127.0.0.0/8")
        loopback_v6 = ip_network("::1/128")
        proxy_networks = tuple(ip_network(cidr, strict=False) for cidr in s.trusted_proxy_cidrs)
        trusted_proxy_boundary = bool(
            s.trust_proxy
            and proxy_networks
            and all(
                network.subnet_of(loopback_v4) if network.version == 4 else network.subnet_of(loopback_v6)
                for network in proxy_networks
            )
        )
        runtime = {
            "productionMode": s.production,
            "httpsBaseUrl": https_base,
            "strongSecret": strong_secret,
            "loopbackHost": loopback_host,
            "trustedProxyBoundary": trusted_proxy_boundary,
        }
        firebase = {
            "clientConfigured": s.firebase_client_configured,
            "backendConfigured": s.firebase_backend_configured,
            "serviceAccountFilePresent": service_account_file_present,
        }
        razorpay = {
            "mode": s.razorpay_mode,
            "liveMode": s.razorpay_mode == "live",
            "checkoutConfigured": s.razorpay_checkout_configured,
            "webhookConfigured": s.razorpay_webhook_configured,
        }
        notifications = {
            "email": self._state(s.smtp_configured, adapter_ready=True),
            "sms": self._state(s.sms_credentials_configured, adapter_ready=False),
            "whatsapp": self._state(s.whatsapp_credentials_configured, adapter_ready=False),
        }
        business = {
            "identityConfigured": s.business_identity_configured,
            "gstinConfigured": bool(s.business_gstin),
            "gstinFormatValid": s.gstin_format_valid,
            "taxInvoiceEnabled": s.tax_invoice_enabled,
            "taxInvoiceIdentityConfigured": s.tax_invoice_identity_configured,
        }
        analytics = {
            "googleConfigured": s.google_analytics_configured,
            "metaConfigured": s.meta_pixel_configured,
            "networkLoadingEnabled": False,
        }
        blockers: list[str] = []
        for code, ready in (
            ("production_mode", s.production),
            ("https_base_url", https_base),
            ("strong_secret", strong_secret),
            ("loopback_host", loopback_host),
            ("trusted_proxy_boundary", trusted_proxy_boundary),
            ("firebase_client", s.firebase_client_configured),
            ("firebase_backend", s.firebase_backend_configured),
            ("firebase_service_account_file", service_account_file_present),
            ("razorpay_live_mode", s.razorpay_mode == "live"),
            ("razorpay_checkout", s.razorpay_checkout_configured),
            ("razorpay_webhook", s.razorpay_webhook_configured),
            ("business_identity", s.business_identity_configured),
            ("tax_invoice_identity", s.tax_invoice_identity_configured),
        ):
            if not ready:
                blockers.append(code)
        return {
            "productionReady": not blockers,
            "blockers": blockers,
            "runtime": runtime,
            "firebase": firebase,
            "razorpay": razorpay,
            "notifications": notifications,
            "business": business,
            "analytics": analytics,
        }
