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

Prefer one reliable end-to-end flow.

## Architecture & Project Structure

- `backend/app/` owns authentication, ingestion, retrieval, model calls, and persistence. Keep routes in `app/api/routes/` and logic in service modules.
- `backend/tests/` mirrors API and service modules; migrations belong in `backend/app/alembic/versions/`.
- `frontend/src/routes/` defines pages; `components/` contains reusable UI; `hooks/` contains stateful behavior.
- `frontend/src/client/` and `routeTree.gen.ts` are generated. Change the backend OpenAPI schema, then run `bash scripts/generate-client.sh`; never edit generated files.
- Core entities are `Notebook`, `Source`, `Chunk`, `Conversation`, `Message`, and `Citation`. Enforce ownership on every notebook query.

Keep LLM and embedding providers behind interfaces. Keys, retrieval, prompts, and citation validation stay in the backend; the frontend only consumes results or streams.

## Development Commands

- `docker compose watch`: run all services.
- `bun run dev`: run Vite at `http://localhost:5173`.
- `cd backend && fastapi dev app/main.py`: run the API at `http://localhost:8000`.
- `bun run --filter frontend build && bun run lint`: build and check the frontend.
- `cd backend && bash scripts/lint.sh && bash scripts/test.sh`: run mypy, ty, Ruff, pytest, and coverage.
- `uv run prek run --all-files`: run the complete pre-commit suite.

## Code & Testing Standards

Python 3.14 uses four spaces, strict typing, `snake_case`, and Ruff. TypeScript uses Biome, two spaces, `PascalCase.tsx` components, and `useCamelCase.ts` hooks.

Name tests `test_*.py`. Cover authorization, ingestion failures, retrieval ordering, and citation mapping. Mock AI providers; tests must not spend API credits or require network access. For RAG changes, maintain a fixed evaluation set and report retrieval/citation quality.

## Commits, PRs, and Thesis Evidence

Use short imperative commits, optionally matching existing emoji prefixes. PRs should explain schema or prompt changes, link issues, include tests, and attach UI screenshots. Record architecture decisions and evaluation methods in Markdown so thesis results are reproducible.

## Security & Data Handling

Never commit secrets or uploaded documents. Validate uploads, isolate each user’s data, and delete derived chunks/indexes with their source. Treat source text as untrusted prompt input; it must not override system instructions.
