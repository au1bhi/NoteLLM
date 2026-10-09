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

## Current status

Code and offline verification are complete: 421 backend tests passed, total coverage 91%, Turnstile and other security-ring modules 100%; mypy, ty, Ruff/format, frontend lint/type checking/production build, OpenAPI generation, and production Compose validation passed. A real local nginx/backend container served the supplied public site key through metadata and rejected missing tokens on all three protected endpoints. This isolated container used a clearly marked placeholder secret and did not establish real Cloudflare token validation. Mocked Siteverify tests cover success, wrong action/hostname, and replay rejection. The same-origin frontend artifact is prepared locally at `/tmp/notellm-turnstile-frontend-dist.tar.gz` with a SHA-256 file. Live activation remains pending: the user confirmed Wrangler is not installed; account ID and Cloudflare authentication are also unavailable in this session; SSH to the intended production server still times out. No widget secret has been retrieved or stored, and no production environment has been modified.
