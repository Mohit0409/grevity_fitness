# Gravity Fitness Final Launch Runbook

Last updated: 2026-08-28

This runbook is the go/no-go procedure for the production cutover. It does not invent or embed credentials, legal identity, pricing, tax data, or provider success. Gravity must stay fail-closed until verified values are supplied by the operator.

## Non-negotiable launch rules

- Keep the Python server bound to loopback (`127.0.0.1` or `::1`). Never expose the raw application port to the public internet.
- Terminate public HTTPS at a trusted reverse proxy or tunnel and trust forwarded client IPs only from the exact proxy CIDR.
- Keep `.env`, Firebase service-account files, SQLite data, logs, and backups outside Git.
- Use Razorpay `live` mode only with verified live credentials and a verified webhook secret.
- Do not activate imported membership-plan drafts until name, price, duration, currency, and business approval are verified.
- Do not bootstrap the first owner until the final strong `SECRET_KEY` is in place; protect the one-time TOTP secret and recovery codes offline.
- Do not call a receipt a tax invoice unless verified business identity, a format-valid GSTIN, and explicit tax-invoice enablement are present.

## 1. Prepare verified production configuration

Copy `.env.example` to `.env` and replace only values you have independently verified. Production requires `GRAVITY_ENV=production`, an HTTPS `APP_BASE_URL`, a strong `SECRET_KEY`, loopback binding, Firebase client configuration, an absolute Firebase service-account path, verified business identity, and the tax-invoice identity required by the current launch policy. Razorpay is optional: leave `RAZORPAY_MODE=test` and all Razorpay credentials blank to keep online checkout disabled; if any Razorpay configuration is supplied, the strict live checkout/webhook gates apply.
For a same-host reverse proxy, the normal trust boundary is:

```dotenv
GRAVITY_HOST=127.0.0.1
GRAVITY_TRUST_PROXY=true
GRAVITY_TRUSTED_PROXY_CIDRS=127.0.0.1/32
```

Use a different CIDR only when it matches the real proxy peer. Do not trust broad LAN or internet ranges.

The Firebase service-account path must be absolute and must point to an existing file. Gravity's readiness gate checks file presence but a real Firebase login canary is still required before launch.

Before copying any public Firebase web configuration, confirm the authenticated Firebase CLI account can access the exact project configured by `FIREBASE_PROJECT_ID`. For the current Gravity auth boundary that project is `gravity-authe`:

```powershell
firebase projects:list
firebase apps:list WEB --project gravity-authe
firebase apps:sdkconfig WEB VERIFIED_WEB_APP_ID --project gravity-authe
```

The SDK config supplies public client values such as API key, auth domain, project ID, and app ID; it does **not** replace the private Firebase Admin service-account credential. Refuse project-ID mismatches. In particular, do not copy the older `gravityfitnessnmh` web configuration into the `gravity-authe` auth boundary merely because that project is accessible. Keep the service-account JSON outside the repository and public web root.

## 2. Put HTTPS in front of Gravity

`deploy/Caddyfile.example` is a provider-neutral same-host TLS template. Set `GRAVITY_PUBLIC_DOMAIN` to the verified production hostname and point public DNS to the approved TLS host before starting the cutover.

Caddy example invocation:

```sh
GRAVITY_PUBLIC_DOMAIN=fitness.example.com caddy run --config deploy/Caddyfile.example
```

The example domain above is illustrative only. Use the actual verified domain. If Cloudflare Tunnel, nginx, or another gateway is used instead, preserve the same invariant: public HTTPS -> trusted proxy -> `127.0.0.1:8787`.
## 3. Run the fail-closed launch gate

Windows:

```powershell
.\scripts\launch-check.ps1
```

Linux / Termux:

```sh
./scripts/launch-check.sh
```

Exit code `0` is the only go signal. The JSON report must show `launchReady: true` and an empty blocker list. The gate checks production/HTTPS mode, strong secret, loopback binding, trusted proxy boundary, Firebase client/backend configuration and service-account file presence, verified business identity plus either receipt-only mode or valid enabled GST tax-invoice identity, SQLite health/current migrations, an active owner, at least one active membership plan, and a verified recovery-tested backup no older than 24 hours. Razorpay is checked only when online payments are requested; otherwise it is reported as disabled and does not block launch.

Do not bypass or manually edit the result. Fix the named blocker and rerun the gate.

## 4. Bootstrap the first owner

Only after the final production secret is configured:

```powershell
.\.venv\Scripts\python.exe -m server.gravity --bootstrap-owner <verified-owner-username>
```

On Linux use `.venv/bin/python`. The command is intentionally interactive. Save the TOTP enrollment material and one-time recovery codes in a secure offline location. Bootstrap is disabled after an owner exists.
## 5. Verify and activate membership plans

Sign in to `/admin` as the owner/admin and review every imported draft against the business-approved offering. Activate only plans whose price, duration, currency, name, and description are verified. Public pricing comes only from active server-owned plans.

Rerun the launch gate. `active_owner` and `active_membership_plan` must disappear from blockers.

## 6. Create the final prelaunch recovery point

Windows:

```powershell
.\scripts\backup-gravity.ps1 -Label prelaunch
.\scripts\verify-backup.ps1 -BackupPath <created-archive>
.\scripts\recovery-drill.ps1 -BackupPath <created-archive>
```

Linux / Termux uses the equivalent `.sh` wrappers. Keep a verified copy off-host on protected storage. The launch gate independently verifies and recovery-drills the newest Gravity backup, requires it to be at most 24 hours old, requires its migration set to match current code, and confirms the recovered copy itself contains an active owner and at least one active membership plan.

## 7. Perform external-provider canaries

Gravity includes read-only connectivity canaries for Firebase and optional Razorpay. They do not create customers, orders, payments, memberships, or other provider-side state.

Windows:

```powershell
.\scripts\provider-canaries.ps1
```

Linux / Termux:

```sh
./scripts/provider-canaries.sh
```

The Firebase probe validates the configured Admin SDK credential/project and performs a one-user list permission/connectivity request without returning user data. If Razorpay is intentionally disabled, its probe reports `skipped` and the combined canary may still pass. If Razorpay is requested, its probe performs only `GET /v1/orders?count=1` using verified live credentials and returns no order details; in that state it must pass for exit code `0`.

These read-only probes do not replace end-to-end business canaries. Before accepting production traffic, complete one approved real Firebase customer sign-in and verify the Gravity first-party session. For Razorpay, perform a business-approved controlled live transaction only when the owner intends a real charge, and verify server-side order/signature/webhook handling plus persisted payment/membership state. SMTP is optional; SMS and WhatsApp remain blocked until real adapters exist.
## 8. Start and run the launch smoke suite

Start Gravity with the normal platform launcher, then run:

```powershell
.\scripts\smoke-gravity.ps1
```

or:

```sh
./scripts/smoke-gravity.sh
```

The smoke suite checks the public home/account/admin surfaces, health contract, security headers, HSTS on HTTPS, non-empty active membership catalog, customer/admin private boundaries, and denial of `.env`/server-source paths. Exit code `0` is required.

You may explicitly target a verified URL during cutover:

```powershell
.\scripts\smoke-gravity.ps1 -BaseUrl https://fitness.example.com
```

```sh
./scripts/smoke-gravity.sh https://fitness.example.com
```

Use the actual verified production domain, not the illustrative hostname above.
## 9. Run the combined cutover verifier

After the local launch gate is green and the public HTTPS endpoint is running, use the combined verifier. It refuses to run provider/public network checks while the local launch gate is blocked.

```powershell
.\scripts\cutover-check.ps1 -BaseUrl https://<verified-domain>
```

```sh
./scripts/cutover-check.sh https://<verified-domain>
```

Exit code `0` and `cutoverReady: true` mean the local launch gate, both read-only provider canaries, and exact-URL HTTPS smoke all passed in one run.

## 10. Go / no-go decision

Go live only when all of the following are true:

- `cutover-check` exits `0` with no blockers.
- `launch-check` independently exits `0` with no blockers.
- GitHub Actions is green on the exact deployed commit for Ubuntu and Windows.
- The final backup is verified, recovery-drilled, and copied to protected off-host storage.
- First owner TOTP/recovery material is secured.
- At least one business-approved membership plan is active.
- The Firebase canary has passed with real verified configuration; Razorpay canary/transaction checks are required only if online payments are enabled.
- Public HTTPS resolves to the intended host and the launch smoke suite exits `0` against that exact URL.
- No secrets, database files, logs, or backup archives are tracked by Git.
- `npm run test:e2e` is green on the deployed commit, including all eight responsive widths, isolated enquiry submission, serious/critical automated accessibility checks, and account/provider fail-closed behavior.
- The privacy notice no longer carries `REQUIRES_OPERATOR_LEGAL_REVIEW` because the operator and appropriate legal reviewer have approved the final text.

Any failed item is a no-go. Keep the previous known-good deployment available until the cutover is proven healthy.

An ngrok warning/interstitial URL may be used as a named staging endpoint, but it is always `BLOCKED_EXTERNAL_DOMAIN` for production. A successful staging smoke or browser pass must not be reported as a production launch.

## 11. Rollback

If the application code fails after cutover, revert/deploy a known-good Git commit without manually downgrading migrations. If data recovery is required, follow `docs/OPERATIONS_RUNBOOK.md`: stop Gravity, verify the chosen archive again, perform the guarded restore, restart, then repeat launch smoke checks.

Do not restore while the server is running and do not delete the generated `pre-restore` safety backup until the recovered deployment is verified.
