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
  - `app/services/answers.py` builds prompts and answers per answer mode; `app/services/retrieval.py` handles chunk retrieval; `app/services/chat.py` and `embeddings.py` are provider interfaces.
  - Conversation titles are editable via `PATCH /api/v1/conversations/{id}` (body: `ConversationCreate`); notebooks via `PUT /api/v1/notebooks/{id}`; `DELETE /api/v1/notebooks/{id}` cascades sources and conversations.
- `backend/tests/` mirrors API and service modules; migrations belong in `backend/app/alembic/versions/`.
- `frontend/src/routes/` defines pages; `components/` contains reusable UI (`Notebooks/` holds the Add/Edit/Delete notebook dialogs, sources panel, chat panel, collapsible citations, and markdown renderer); `hooks/` contains stateful behavior.
  - `hooks/useMobile.ts` provides `useIsMobile` (@768px) and `useIsDesktop` (@1024px) — align JS breakpoint decisions with the CSS `lg` breakpoint.
- `frontend/src/client/` and `routeTree.gen.ts` are generated. Change the backend OpenAPI schema, then run `bash scripts/generate-client.sh` (it imports `app.main.app.openapi()` directly, no running server needed); never edit generated files.
- Core entities are `Notebook`, `Source`, `Chunk`, `Conversation`, `Message`, and `Citation`. Enforce ownership on every notebook query.

Keep LLM and embedding providers behind interfaces. Keys, retrieval, prompts, and citation validation stay in the backend; the frontend only consumes results or streams.

## Frontend Conventions & Gotchas

- Biome's lint with `--unsafe` strips `useEffect` dependencies it considers unused. Intentional reactive deps (auto-scroll on new messages, textarea auto-resize) must be kept with `// biome-ignore lint/correctness/useExhaustiveDependencies: <reason>`.
- Stacking order: the sticky header is `z-30`; Radix modals (dialog/sheet/dropdown) are `z-50`. A `position: relative` wrapper without an explicit z-index does NOT create a stacking context, so inner `z-10` content escapes and can paint over the sticky header when scrolled — wrap such sections with `isolate` (see the dashboard hero and notebook cards).
- The sources query polls every 2s while any source is `processing` (via `refetchInterval`), so uploaded files reach `ready` without a manual refresh.
- Sending a question optimistically appends the user message to the conversation cache and invalidates the conversation query on error to roll back. The Enter-to-send handler checks `event.nativeEvent.isComposing` so Chinese IME composition isn't submitted early.
- Upload/retry toasts are status-aware (ready / processing / failed) — a fresh upload returns `processing`, not an error.

## Development Commands

- `docker compose watch`: run all services.
- `bun run dev`: run Vite at `http://localhost:5173`.
- `cd backend && fastapi dev app/main.py`: run the API at `http://localhost:8000`.
- `bun run --filter frontend build && bun run lint`: build and check the frontend.
- `cd backend && bash scripts/lint.sh && bash scripts/test.sh`: run mypy, ty, Ruff, pytest, and coverage.
- `uv run prek run --all-files`: run the complete pre-commit suite.

CI (`.github/workflows/`) runs `test-backend` (pytest + coverage, gate at 80%) and `test-docker-compose` on push to `master`. There are no Playwright/e2e tests and no `playwright` or `mailcatcher` compose services — do not re-add a Playwright workflow or reference those services in CI without first adding the real setup.

## Code & Testing Standards

Python 3.14 uses four spaces, strict typing, `snake_case`, and Ruff. TypeScript uses Biome, two spaces, `PascalCase.tsx` components, and `useCamelCase.ts` hooks.

Name tests `test_*.py`. Cover authorization, ingestion failures, retrieval ordering, citation mapping, conversation rename isolation, and answer modes (`tests/services/test_answers.py`: knowledge mode skips retrieval; hybrid answers from knowledge without evidence). Mock AI providers; tests must not spend API credits or require network access. For RAG changes, maintain a fixed evaluation set and report retrieval/citation quality.

## Commits, PRs, and Thesis Evidence

Use short imperative commits, optionally matching existing emoji prefixes. Commit after each major update. PRs should explain schema or prompt changes, link issues, include tests, and attach UI screenshots. Record architecture decisions and evaluation methods in Markdown so thesis results are reproducible.

## Security & Data Handling

Never commit secrets or uploaded documents. Validate uploads, isolate each user's data, and delete derived chunks/indexes with their source. Treat source text as untrusted prompt input; it must not override system instructions.
