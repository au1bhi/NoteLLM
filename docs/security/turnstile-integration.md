# NoteLLM existing Turnstile widget integration

Existing public site key: `0x4AAAAAAFSZqpTS9XSOMui_`.
Expected production frontend hostname: `notellm.au1bhi.com`.
No replacement widget is created. Its current domains and clearance level must be verified through the authorized existing-widget flow, not inferred from the public key.

## Application contract

| Frontend | Backend | Expected Siteverify action |
| --- | --- | --- |
| `/login` | `POST /api/v1/login/access-token` | `login` |
| `/signup` | `POST /api/v1/users/signup` | `signup` |
| `/recover-password` | `POST /api/v1/password-recovery/{email}` | `password_recovery` |

The frontend sends the single-use token in the existing `X-Turnstile-Token` header. FastAPI calls Cloudflare Siteverify before the existing handler and requires strict boolean `success=true`, an exact matching action, and an exact hostname from `TURNSTILE_HOSTNAMES`. Missing/invalid tokens are rejected with Chinese HTTP 400 errors; unavailable verification returns 503 and does not bypass verification. Siteverify is never called from the browser. Forms reset their widget after submission, and expired/error tokens cannot submit.

## Deployment configuration

The intended production destination is `/root/NoteLLM/.env`, using the existing backend setting name `TURNSTILE_SECRET_KEY`. SSH must work and the file's ignored status must be confirmed before a secret is retrieved or written.

```dotenv
TURNSTILE_SITE_KEY=0x4AAAAAAFSZqpTS9XSOMui_
# Populate only through the confirmed secret retrieval/store operation:
TURNSTILE_SECRET_KEY=<matching-widget-secret>
TURNSTILE_REQUIRED=true
TURNSTILE_HOSTNAMES=notellm.au1bhi.com
```

Never use the placeholder as a real configuration value. The secret must not appear in a commit, command argument, log, diff, temporary file, or chat. Production expected-hostname lists must exclude localhost and private IPs. Local development can leave both keys unset, or use a separate local/test widget and explicitly scoped local hosts.

Both the frontend action changes and the backend validation must be deployed together. Build the same-origin frontend locally/CI, inject the prebuilt artifact on the VPS, and recreate the backend without building on the VPS. Enabling these stricter backend checks with an old frontend that emits no action will reject legitimate tokens.

## Existing-widget recovery gate

Follow [Cloudflare Spin's existing-widget flow](https://developers.cloudflare.com/turnstile/spin/prompt.md):

1. Obtain approval for an absolute, non-project Wrangler executable and its exact version (at least 4.109), authenticate it, and pin the Cloudflare account ID. Do not install/update Wrangler automatically or invoke credential-bearing commands through project package resolution.
2. Confirm the secret destination exists and is ignored. Present a concrete manifest containing the executable/version, account, site key, expected domains, project, and exact secret destination; obtain explicit confirmation before any secret-bearing getter or write.
3. Retrieve metadata without exposing the secret, confirm the site key/domains/clearance level, and preserve the existing widget. Validate the retrieved secret with Siteverify's dummy-token probe before storing it through stdin in the confirmed env/secret store.
4. Test the actual protected backend with a fresh real token, then replay the same token and verify rejection. A mocked unit test or `enabled=true` metadata response does not establish live end-to-end success.

## Deployed runtime

On 2026-10-10, production was fast-forwarded from `f00fdba` to `a8397d5`. The same-origin frontend was built locally and injected into the existing `notellm_frontend-dist` volume. No build ran on the VPS. Backend and scheduler retain their read-only source mounts. The updated nginx configuration is mounted through the operator-owned `/root/notellm-runtime.yml` overlay; preserve this overlay when recreating services:

```bash
cd /root/NoteLLM
docker compose -f compose.yml -f compose.traefik.yml -f compose.lowmem.yml \
  -f /root/notellm-runtime.yml up -d --no-build --no-deps backend scheduler frontend
```

The runtime overlay also sets the backend command to `bash scripts/start-service.sh fastapi run --workers 2 --no-proxy-headers`, reduced from four workers at the user's request. The migration gate and disabled uvicorn proxy-header rewriting are preserved. Verification counted two worker processes plus one multiprocessing resource tracker; container health and public readiness returned 200, the login page returned 200, and missing-token login remained HTTP 400. Backend container memory fell from approximately 641 MiB to 431 MiB (one observed sample, not a peak-load benchmark). The previous overlay is backed up at `/root/notellm-runtime.before-workers-20261010.yml`. This was a runtime-only adjustment; application code, frontend artifacts, and the previously validated 421-test revision were unchanged.

The previous frontend and nginx config are backed up under `/root/notellm-pre-turnstile-20261010/`. Old hashed frontend assets were retained for open tabs. The real widget secret was retrieved through the approved external Wrangler executable, validated with a dummy-token Siteverify probe, and sent through SSH stdin directly into the existing ignored `.env` (mode 0600). It was not printed, passed as an argument, committed, or stored in a temporary file. Both keys, `TURNSTILE_REQUIRED=true`, and the exact production hostname allowlist are active. The widget's existing parent domain `au1bhi.com` and clearance configuration were preserved; Cloudflare's parent-domain rule covers `notellm.au1bhi.com`.

## Verification

Code verification before deployment: 421 backend tests passed, coverage 91%, security-ring modules 100%; mypy, ty, Ruff/format, frontend lint/type checking/production build, generated-client consistency, and production Compose validation passed. Local container verification used an explicitly marked placeholder secret and mocked Siteverify; those results alone do not prove real-token success.

Production verification: public metadata exposes `enabled=true` and only the public site key; public readiness returns 200; backend and database are healthy, scheduler and nginx run normally. Origin requests without a token return Chinese HTTP 400 on login, signup, and recovery. `/docs`, `/docs/`, and `/api/v1/openapi.json` return 404. `/api` redirects relatively to `/api/`, without exposing the internal port. `nginx -t` and deployment Compose validation pass.

A normal VPS reboot was performed with explicit permission after sustained I/O/memory PSI above 90%, load around 20, and Docker/socket/readiness timeouts blocked deployment. A temporary snapd stop had not resolved the issue; its socket was restored. After reboot and deployment, the server remained healthy for approximately 11 hours, with load around 0.1. These observations establish recovery, not the precise root cause of the earlier resource pressure.

The user verified a fresh production token in their ordinary browser: submitting a nonexistent account returned “邮箱或密码错误”, demonstrating that the protected login handler ran after Siteverify accepted the token. This is user-reported manual evidence. The user then replayed the original `access-token` request and confirmed HTTP 400 with “人机验证失败”. Fresh-token acceptance and rejection of the same token on replay are therefore confirmed by user-performed manual checks against the deployed backend. The production widget rendered in a headed Playwright browser, but challenges failed or timed out. [Cloudflare documents that automated browsers may be detected as bots](https://developers.cloudflare.com/turnstile/troubleshooting/testing/), so this does not establish that ordinary browsers fail. The ordinary-browser checks passed. Do not substitute test keys in production. These checks establish the real login validation and single-use boundary; they do not establish a complete authenticated RAG workflow or independently captured HTTP evidence.

## Additional server maintenance

At the user's explicit request, 3x-ui was stopped and removed: `/usr/local/x-ui`, `/etc/x-ui`, `/usr/bin/x-ui`, and `/etc/systemd/system/x-ui.service`. Its startup link was disabled and systemd reloaded. A root-only backup remains at `/root/3x-ui-backup-20261010.tar.gz`. Verification found the service `not-found` and inactive, no x-ui/xray processes, both existing Cloudflare Tunnel services active, and NoteLLM readiness 200. The backup may contain credentials and must remain on the server with mode 0600.
