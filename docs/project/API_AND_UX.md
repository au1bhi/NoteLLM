# Phase 0 API and UX Design

## API Contract Draft

All endpoints require the existing bearer authentication and return `404` for resources the caller does not own. The generated TypeScript client is refreshed after OpenAPI changes; streaming uses `fetch` because generated clients do not model server-sent events well.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET`, `POST` | `/api/v1/notebooks/` | List or create the caller's notebooks |
| `GET`, `PUT`, `DELETE` | `/api/v1/notebooks/{notebook_id}` | Read, edit, or delete one notebook |
| `GET`, `POST` | `/api/v1/notebooks/{notebook_id}/sources/` | List sources or upload one multipart file |
| `GET`, `DELETE` | `/api/v1/sources/{source_id}` | Read processing state/metadata or delete the source and chunks |
| `GET`, `POST` | `/api/v1/notebooks/{notebook_id}/conversations/` | List or create conversations |
| `GET` | `/api/v1/conversations/{conversation_id}` | Read messages and citations |
| `POST` | `/api/v1/conversations/{conversation_id}/messages/stream` | Send `{ "content": "..." }` and receive an SSE answer stream |

The streaming endpoint emits `delta` text events, then one `citations` event containing source name, page number, excerpt, and chunk ID, followed by `done`. It emits `error` with a user-safe message on failure. It must reject questions when the notebook has no `ready` sources.

## Low-Fidelity Page Flow

```text
Notebook list
 ├─ [New notebook]
 └─ Notebook card ───────────────────────────┐
                                               ▼
Notebook workspace
 ├─ Left: source list + [Upload]
 ├─ Centre: conversation + question input
 └─ Right/below answer: expandable citations
                                               │
                                               ▼
Upload and processing state
 ├─ validate type/size
 ├─ pending → processing → ready
 └─ failed: show safe error + [Remove] / [Retry]
```

The workspace must distinguish an empty notebook, an upload in progress, a processing failure, no retrieved evidence, and a streaming response. Citation links open a source preview at the cited page when available; otherwise they highlight the stored excerpt.

## Acceptance Walkthrough

1. Sign in as a normal user and create a notebook.
2. Upload a small PDF and wait until status is `ready`.
3. Ask a question whose answer appears in the PDF.
4. Confirm the streamed answer has at least one citation and its excerpt/page supports the claim.
5. Refresh the page; confirm the source and conversation remain visible.
6. Sign in as another user; confirm the notebook cannot be listed, read, or queried.

## Evaluation Fixture

Before phase 3, add 3–5 non-sensitive source documents and 30–50 questions with expected supporting page/section. Track Recall@5, citation correctness, faithfulness, and response time in a checked-in Markdown or CSV report. These fixtures are for repeatable evaluation, not training data.
