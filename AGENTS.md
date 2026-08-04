# Repository Guidelines

## Persistent Project Plan

Before starting NoteLLM work, read `docs/project/GOAL.md` and `docs/project/PLAN.md`. Follow the current milestone, keep the scope at graduation-project level, and update the plan with completion evidence after meaningful work.

## Product Goal

NoteLLM is a Google NotebookLM-inspired graduation project: users organize sources and ask questions answered with verifiable citations. Treat the current CRUD as template code. Prioritize this MVP:

1. Create a notebook and upload a PDF or text source.
2. Parse, chunk, embed, and index the source.
3. Retrieve relevant chunks for a question.
4. Stream a grounded answer with source/page citations.
5. Reopen the notebook and conversation.

Answers support three selectable modes (per-question, request-only — not persisted to the DB):

- `grounded` (default): answer strictly from the notebook's sources; citations required.
- `hybrid`: sources are the primary basis, but the model may supplement with general knowledge.
- `knowledge`: free-form answer from the model's own knowledge; skips retrieval, no citations.

The mode selector sits in the chat composer; the backend branches in `app/services/answers.py`.

Prefer one reliable end-to-end flow.

## Architecture & Project Structure

- `backend/app/` owns authentication, ingestion, retrieval, model calls, and persistence. Keep routes in `app/api/routes/` and logic in service modules.
  - `app/services/answers.py` builds prompts and answers per answer mode; `retrieval.py` handles chunk retrieval; `sources.py` owns parsing/chunking/indexing; `overview.py` and `study_guide.py` own their structured generations; `chat.py` and `embeddings.py` are provider interfaces.
  - Conversation title/pin state is editable via `PATCH /api/v1/conversations/{id}` (body: `ConversationUpdate`); notebook title/description/pin state via `PUT /api/v1/notebooks/{id}`. Deleting a notebook cascades its sources, chunks, conversations, messages, and citations and unlinks its upload directory. Preserve the same file cleanup when changing any account-deletion path.
- `backend/tests/` mirrors API and service modules; migrations belong in `backend/app/alembic/versions/`.
- `frontend/src/routes/` defines pages; `components/` contains reusable UI (`Notebooks/` holds the Add/Edit/Delete notebook dialogs, sources panel, chat panel, collapsible citations, and markdown renderer); `hooks/` contains stateful behavior.
  - `hooks/useMobile.ts` provides `useIsMobile` (@768px) and `useIsDesktop` (@1024px) — align JS breakpoint decisions with the CSS `lg` breakpoint.
- `frontend/src/client/` and `routeTree.gen.ts` are generated. Change the backend OpenAPI schema, then run `bash scripts/generate-client.sh` (it imports `app.main.app.openapi()` directly, no running server needed); never edit generated files.
- Core RAG entities are `Notebook`, `Source`, `Chunk`, `Conversation`, `ConversationMessage`, and `Citation`. Supporting account/billing entities include `UserProviderSettings`, `UserUsage`, and `EmailUsageTombstone`. Enforce ownership on every notebook, source, conversation, overview, and study-guide query; cross-user resource access should return 404 rather than disclose existence.

Keep LLM and embedding providers behind interfaces. Keys, retrieval, prompts, and citation validation stay in the backend; the frontend only consumes results or streams.

Users can bring their own API keys (BYOK): per-user provider settings live in `user_provider_settings` (chat + embedding base URL / key / model / API format). Keys are Fernet-encrypted at rest in `app/core/security.py` (keyed off `SECRET_KEY`) and never returned to the client — the API (`GET/PUT/DELETE /users/me/provider-settings`, in `app/api/routes/users.py`) only returns a masked preview. Effective configs are resolved in `app/services/provider_settings.py`; providers (`app/services/chat.py`, `embeddings.py`) take a `ProviderConfig`. Always resolve settings through the owning user before constructing a provider. A user-selected model is honored only when that user supplies the corresponding key; server-billed calls must use the operator-configured model.

Notebook overview generation is lazy and persisted; regeneration replaces the stored summary/topics. Study guides are request-time structured output and are not persisted. Both consume chat quota and must remain source-grounded. Pinning affects list ordering only and does not bypass ownership.

## Authentication, Provider, and Quota Invariants

- When SMTP is configured, registration creates an unverified account and sends a 72-hour verification link. Unverified users may log in and use BYOK, but cannot consume server-funded model quota. With no mail backend, accounts are marked verified so local development is not blocked.
- Email changes require the current password. With SMTP enabled they are staged in `pending_email` until the new address verifies; without a mail backend they apply immediately because no verification can complete. Public signup, recovery, resend, and verification responses must stay generic to prevent account enumeration. Verification and reset JWTs are purpose-scoped and travel in URL fragments; the frontend consumes and removes the fragment immediately.
- `password_changed_at` is embedded in access/reset tokens. Any password change revokes older access tokens and makes reset links single-use. Preserve the frontend's startup/timer/focus expiry checks and no-retry behavior for 401/403 responses.
- `canonical_email()` collapses case, subaddress, dot, and known provider-alias variants. `email_canonical` remains unique; `email_history` and `EmailUsageTombstone` carry current-month usage through email changes, account deletion, and re-registration. Do not weaken this flow when editing user CRUD or migrations.
- User-supplied provider URLs are untrusted. Validate them with `app/core/ssrf.py`, and perform provider/model-discovery requests with `pinned_request()` so DNS rebinding, private ranges (including CGNAT and IPv4-mapped IPv6), redirects, and proxy environment variables cannot bypass validation. Do not replace these calls with raw `httpx` requests.
- Auth rate limits and recipient mail cooldowns are in-process, bounded stores. They are suitable for the current single-host deployment but are per worker; preserve route-template/IP keying, `Retry-After`, generic mail responses, and the autouse reset fixture in tests.
- Free quota applies only to server-billed dimensions and only for verified users: 100k chat tokens and 300k embedding characters per calendar month by default. Before every provider call (chat stream, search, ingestion/retry, overview, study guide, and model discovery), atomically reserve worst-case usage with `reserve_usage`; afterward reconcile actual usage or refund failures with `settle_usage`. Only settle amounts actually reserved—phantom refunds can recreate free quota. BYOK dimensions reserve zero.
- Provider calls are bounded per process, chat output is capped, uploads have both per-file and per-user storage limits, and failed source processing must never leave a source stuck in `processing`.

## Frontend Conventions & Gotchas

- Biome's lint with `--unsafe` strips `useEffect` dependencies it considers unused. Intentional reactive deps (auto-scroll on new messages, textarea auto-resize) must be kept with `// biome-ignore lint/correctness/useExhaustiveDependencies: <reason>`.
- Stacking order: the sticky header is `z-30`; Radix modals (dialog/sheet/dropdown) are `z-50`. A `position: relative` wrapper without an explicit z-index does NOT create a stacking context, so inner `z-10` content escapes and can paint over the sticky header when scrolled — wrap such sections with `isolate` (see the dashboard hero and notebook cards).
- The sources query polls every 2s while any source is `processing` (via `refetchInterval`), so uploaded files reach `ready` without a manual refresh.
- Sending a question optimistically appends the user message to the conversation cache and invalidates the conversation query on error to roll back. The Enter-to-send handler checks `event.nativeEvent.isComposing` so Chinese IME composition isn't submitted early.
- Upload/retry toasts are status-aware (ready / processing / failed) — a fresh upload returns `processing`, not an error.
- `OpenAPI.BASE` is build-time configuration. Local Vite development may use an ignored `frontend/.env.local` with `VITE_API_URL=http://localhost:8000`; production and release artifacts must keep `VITE_API_URL=""` for same-origin `/api` proxying. Use `scripts/build-frontend-dist.sh` for low-memory deployment artifacts; do not bake a developer URL into a release bundle.
- The full-page watermark is server-controlled by `WATERMARK_ENABLED` / `WATERMARK_TEXT` through the public `/api/v1/meta/watermark` endpoint and intentionally covers unauthenticated pages too. Keep its static and JavaScript-managed layers aligned.

## Development Commands

- `docker compose watch`: run all services.
- `bash install.sh --local`: guided local installation; `DOMAIN=example.com bash install.sh --prod --yes` performs unattended production setup.
- `bun run dev`: run Vite at `http://localhost:5173`.
- `cd backend && fastapi dev app/main.py`: run the API at `http://localhost:8000`.
- `bun run --filter frontend build && bun run lint`: build and check the frontend.
- `cd backend && bash scripts/lint.sh && bash scripts/test.sh`: run mypy, ty, Ruff, pytest, and coverage.
- `uv run prek run --all-files`: run the complete pre-commit suite.

Compose files are `compose.yml` plus environment-specific overlays: `compose.override.yml` for local development, `compose.traefik.yml` for HTTPS production, and `compose.lowmem.yml` for serving a prebuilt SPA on small servers. CI (`.github/workflows/`) runs `test-backend` (pytest + coverage, gate at 80%) and `test-docker-compose` on pushes to `master` and pull requests. There are no Playwright/e2e tests and no `playwright` or `mailcatcher` compose services — do not add a Playwright workflow or reference those services without first adding the real setup.

## Code & Testing Standards

Python supports 3.12+ (the checked-in development/runtime version is currently 3.14) and uses four spaces, strict typing, `snake_case`, and Ruff targeting Python 3.12 syntax. TypeScript uses Biome, two spaces, `PascalCase.tsx` components, and `useCamelCase.ts` hooks.

Name tests `test_*.py`. Cover authorization, ingestion failures, retrieval ordering, citation mapping, conversation rename isolation, and answer modes (`tests/services/test_answers.py`: knowledge mode skips retrieval; hybrid answers from knowledge without evidence). Mock AI providers; tests must not spend API credits or require network access. For RAG changes, maintain a fixed evaluation set and report retrieval/citation quality.

## Commits, PRs, and Thesis Evidence

Use short imperative commits, optionally matching existing emoji prefixes. Commit after each major update. PRs should explain schema or prompt changes, link issues, include tests, and attach UI screenshots. Record architecture decisions and evaluation methods in Markdown so thesis results are reproducible.

## Security & Data Handling

Never commit secrets or uploaded documents. Validate uploads, isolate each user's data, and delete derived chunks/indexes with their source. Treat source text as untrusted prompt input; it must not override system instructions.

Production requires a non-default `SECRET_KEY` of at least 32 characters and an HTTPS, non-localhost `FRONTEND_HOST`; API docs are disabled in production. Keep application and management service ports on loopback or internal Docker networks, expose public traffic only through nginx/Traefik, retain CSP/HSTS and related security headers, and keep Adminer/Traefik dashboards behind Basic Auth.

## Recent Iterations (2026-08)

Feature work landed after the original scaffold. Keep these invariants intact when changing code:

- **Free-tier quota**: `FREE_QUOTA_CHAT_TOKENS` (100k) and `FREE_QUOTA_EMBEDDING_CHARS` (300k) apply **only to server-billed usage**. Users who configure their own API key (`user_provider_settings.chat_api_key` / `embedding_api_key`) are unlimited for that dimension. `app/services/usage.py` atomically reserves allowance before provider calls and settles actual usage/refunds afterward; source upload also uses a fast preflight before saving and exact reservation before embedding. Counters roll over by calendar month (`period_start` on `user_usage`, lazy reset in `ensure_period`). Usage + quota + billing source is returned by `GET /users/me/usage`.
- **Switch-back cooldown**: after configuring an own key, clearing provider settings (reverting to server default) is blocked for `PROVIDER_SWITCH_COOLDOWN_HOURS` (24). Gated by `provider_changed_at`; `GET /users/me/provider-settings` returns `cooldown_until`; DELETE returns 429 while locked.
- **API format**: per-provider `chat_api_format` / `embedding_api_format` in `user_provider_settings`, values `"openai"` (base URL already has a version path) or `"openai_v1"` (root domain, auto-append `/v1`). `resolve_api_base(base_url, api_format)` in `app/services/provider_settings.py`; used by chat, embeddings, and the model-fetch endpoint. Model fetch also probes `/v1` as a fallback for root-domain URLs.
- **Auth rate limiting**: in-process fixed-window limiter in `app/core/rate_limit.py` (`rate_limit(limit, window)`), applied to login, signup, password recovery/reset, and password change. 429 responses carry `Retry-After`. Tests reset buckets via the autouse `_reset_rate_limits` fixture in `tests/conftest.py`.
- **New-user onboarding**: `frontend/src/components/Common/OnboardingChecklist.tsx` on the home page steps a new user through model config → notebook → source → first question; dismissible via `localStorage`. Settings page deep-links via `?tab=model`.
- **Conversation delete**: `DELETE /api/v1/conversations/{id}` cascades messages/citations; per-chip delete button in the chat panel header with a confirm dialog.
- **UI localization & theme**: all user-facing copy is Chinese (keep it that way); kraft/ink OKLCH theme, no blue. `--font-display` must resolve to a static CJK serif (e.g. `Noto Serif CJK SC`); do not reintroduce variable CJK fonts — they rasterize brokenly at fractional zoom (e.g. 110%).
- **Email identity and verification**: optional SMTP-backed verification, SMTP-gated staged email changes, domain allowlisting, canonical mailbox uniqueness, usage tombstones, password-bound token revocation, generic anti-enumeration responses, and fragment-delivered purpose tokens are now part of the account boundary.
- **Deployment and operability**: `install.sh` supports remote/local/production installs, restricted-network registry/package mirrors, repeatable upgrades from either Git clones or codeload archives, dry runs, and automatic low-memory frontend deployment. Production frontend builds are same-origin; do not commit `.env.local` or generated `frontend-dist.tar.gz` artifacts.
- **Defense in depth**: provider SSRF protection pins validated public IPs; provider concurrency and uploads are bounded; production hides OpenAPI docs; nginx/Traefik keep management surfaces authenticated and application ports on loopback; the watermark is controlled by backend configuration.
