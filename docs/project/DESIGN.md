# Phase 0 Design: NoteLLM MVP

## Technical Decisions

| Concern | Decision |
| --- | --- |
| API and UI | Existing FastAPI/SQLModel backend and React/Vite frontend |
| Relational data and vectors | PostgreSQL with the pgvector extension; use cosine-distance Top-K retrieval |
| Source files | Local Docker volume, outside the application source tree |
| Supported sources | PDF, UTF-8 TXT, and Markdown only |
| PDF extraction | PyMuPDF; preserve source page numbers |
| LLM and embeddings | One OpenAI-compatible provider, configured only through backend environment variables |
| Initial chunking | 1,000 characters with 150-character overlap; tune only from evaluation results |
| Retrieval | Top 5 chunks from the current notebook only |
| Background work | Synchronous processing first; introduce FastAPI background tasks only if uploads make the request unusable |

The implementation must use a PostgreSQL image that includes pgvector and enable the extension through migration/startup SQL. The present `postgres:18` image does not itself prove pgvector availability; verify the chosen image before changing Compose.

Configuration names: `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `EMBEDDING_BASE_URL`, `EMBEDDING_API_KEY`, `EMBEDDING_MODEL`, and `EMBEDDING_DIMENSIONS`. Chat and embedding providers may be different; all keys remain backend-only deployment configuration.

`LLM_BASE_URL` must point at the OpenAI-compatible API version root (for example, `https://api.deepseek.com`). Upload processing requires `EMBEDDING_BASE_URL`, `EMBEDDING_API_KEY`, and `EMBEDDING_MODEL`; if they are absent or the provider returns a wrong-size vector, the source is retained with `failed` status and can be retried after configuration is corrected. `EMBEDDING_DIMENSIONS` must match the configured model and the database migration (currently 1024 for Zhipu Embedding-3).

## Data Model

All identifiers are UUIDs. All timestamps are UTC. Deleting a parent deletes its children and derived data.

```text
User 1 ── * Notebook 1 ── * Source 1 ── * Chunk
                    │
                    └── * Conversation 1 ── * Message 1 ── * Citation ── 1 Chunk
```

| Entity | Required fields | Notes |
| --- | --- | --- |
| `Notebook` | `id`, `owner_id`, `title`, `description`, `created_at`, `updated_at` | `title` max 255 characters |
| `Source` | `id`, `notebook_id`, `display_name`, `storage_path`, `media_type`, `status`, `file_size_bytes`, `created_at` | Status: `pending`, `processing`, `ready`, `failed`; retain `error_message`, `page_count`, `processed_at` when available |
| `Chunk` | `id`, `source_id`, `ordinal`, `content`, `page_number`, `char_start`, `char_end`, `embedding` | Unique `(source_id, ordinal)`; `page_number` is nullable for TXT/Markdown |
| `Conversation` | `id`, `notebook_id`, `title`, `created_at`, `updated_at` | Title may initially derive from the first question |
| `Message` | `id`, `conversation_id`, `role`, `content`, `created_at` | Roles are `user` or `assistant` |
| `Citation` | `id`, `message_id`, `chunk_id`, `ordinal`, `quote` | Only assistant messages have citations; `quote` is a bounded excerpt stored for stable display |

Ownership is checked by joining every notebook-scoped entity back to `Notebook.owner_id`; never trust an ID supplied by the client without this check.

## Grounding Contract

The backend retrieves chunks, constructs the prompt, invokes the model, validates citations, and persists the result. The frontend never sends API keys or decides which sources support an answer.

The prompt must instruct the model to use only supplied chunks, state that evidence is insufficient when needed, and cite evidence using supplied chunk IDs. The backend stores citations only when their IDs belong to the retrieved set. It must reject or remove unknown IDs, and return a safe “insufficient information” response if no usable evidence exists.
