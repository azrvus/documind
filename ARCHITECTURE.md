# Architecture

```text
Next.js dashboard → FastAPI → PyMuPDF / UTF-8 validation
                            → SQLite documents, collections, and chunks
                            → SQLite FTS5 + BM25 → ranked verbatim excerpts
                                                ↘ optional OpenAI completion
```

The browser saves its existing workspace UUID, theme, and display name locally. All data endpoints require `X-Workspace-Id` containing a UUID. The backend scopes document reads, assignment, collection mutations, and retrieval to that UUID. It is not a sign-in credential. Health requires no workspace ID and reports backend availability separately from the optional provider.

On startup access, a transactional migration adds collections, optional file sizes, and a passage index and backfills previously stored chunks. Uploads extract text without sending it to a provider. Chunks retain one-based PDF page numbers and stable passage IDs; TXT uses an internal page value of 1. Foreign keys and SQLite triggers remove chunks and FTS entries when a document is deleted or expires. Collections can only be deleted when empty.

Search quotes and caps query tokens, applies English stemming and question-word filtering, and ranks matching chunks with SQLite BM25. It returns the top five scoped passages with verbatim text and metadata. BM25 term statistics are shared by the database; returned excerpts are scoped. With explicit OpenAI opt-in, matching excerpts can support a generative answer; existing embeddings can supplement lexical ranking. Provider errors return a generic failure. An empty search gives a local no-match message, with or without credentials.

| Method | Path | Behavior |
|---|---|---|
| GET | `/api/health` | Check SQLite and report provider status |
| GET, POST | `/api/documents` | List documents or upload a multipart PDF/TXT |
| GET, PATCH, DELETE | `/api/documents/{id}` | Read extracted passages, set `collection_id` (or null), or delete |
| GET, POST | `/api/collections` | List or create collections |
| PATCH, DELETE | `/api/collections/{id}` | Rename or delete an empty collection |
| POST | `/api/chat` | Search using `question`, optional `document_ids`, `collection_id`, and `use_provider` |

Search returns `mode`, a nullable `answer`, and a `sources` array with document and passage IDs, filename, page, and excerpt. Local successful matches use the excerpts as the result. The UI reads document details and uses the passage ID to focus the cited passage.
