import re
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from openai import OpenAI
from pydantic import BaseModel, Field

from .config import get_settings
from .processing import DocumentError, chunk_pages, content_hash, extract_document
from .rag import answer, retrieve
from .store import add_document, cleanup_expired, connect, get_chunks, list_collections, list_documents, search_passages

settings = get_settings()
DB_PATH = settings.data_dir / "workspace.sqlite3"
provider_status = "unverified"
app = FastAPI(title="AI Document Intelligence API", version="1.0.0")


@app.middleware("http")
async def limit_content_length(request: Request, call_next):
    length = request.headers.get("content-length")
    if length:
        try:
            if int(length) > settings.max_request_bytes:
                return JSONResponse(status_code=413, content={"detail": "Request exceeds the maximum allowed size."})
        except ValueError:
            return JSONResponse(status_code=400, content={"detail": "Invalid Content-Length header."})
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > settings.max_request_bytes:
            return JSONResponse(status_code=413, content={"detail": "Request exceeds the maximum allowed size."})
        body.extend(chunk)
    request._body = bytes(body)
    return await call_next(request)


# Apply CORS to validation errors from the request size middleware too.
app.add_middleware(CORSMiddleware, allow_origins=settings.origins, allow_credentials=False,
                   allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["Content-Type", "X-Workspace-Id"])


@contextmanager
def database():
    with closing(connect(DB_PATH)) as db, db:
        yield db


def workspace_id(value: str | None) -> str:
    if value and len(value) <= 64:
        try:
            return str(UUID(value))
        except ValueError:
            pass
    raise HTTPException(status_code=400, detail="A valid X-Workspace-Id is required.")


def ai_client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key, timeout=30, max_retries=0)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=settings.max_question_chars)
    document_ids: list[str] = Field(default_factory=list, max_length=settings.max_documents_per_session)
    collection_id: str | None = None
    use_provider: bool = False


class CollectionName(BaseModel):
    name: str = Field(min_length=1, max_length=60)


class CollectionAssignment(BaseModel):
    collection_id: str | None


def require_collection(db, sid, collection_id):
    if not db.execute("SELECT 1 FROM collections WHERE id=? AND session_id=?", (collection_id, sid)).fetchone():
        raise HTTPException(status_code=404, detail="Collection not found.")


@app.get("/api/health")
def health():
    with database() as db:
        db.execute("SELECT 1 FROM passage_search LIMIT 1").fetchone()
    configured = bool(settings.openai_api_key)
    return {"status": "ok", "ai_configured": configured, "provider": "openai",
            "provider_status": provider_status if configured else "not_configured"}


@app.get("/api/documents")
def documents(x_workspace_id: str | None = Header(default=None)):
    sid = workspace_id(x_workspace_id)
    with database() as db:
        cleanup_expired(db, settings.session_ttl_days)
        return {"documents": list_documents(db, sid)}


@app.get("/api/documents/{document_id}")
def document_detail(document_id: str, x_workspace_id: str | None = Header(default=None)):
    sid = workspace_id(x_workspace_id)
    with database() as db:
        rows = list_documents(db, sid, document_id)
        if not rows:
            raise HTTPException(status_code=404, detail="Document not found.")
        return {"document": rows[0], "passages": get_chunks(db, sid, [document_id])}


@app.post("/api/documents", status_code=201)
def upload_document(file: UploadFile = File(...), x_workspace_id: str | None = Header(default=None)):
    sid = workspace_id(x_workspace_id)
    filename = Path((file.filename or "").replace("\\", "/")).name
    filename = re.sub(r"[\x00-\x1f\x7f]", "_", filename).strip(" .")
    stem, extension = Path(filename).stem, Path(filename).suffix.lower()
    if not stem or not extension:
        raise HTTPException(status_code=400, detail="Choose a PDF or TXT file with a valid filename.")
    if extension not in {".pdf", ".txt"}:
        raise HTTPException(status_code=415, detail="Only PDF and TXT files are supported.")
    filename = filename if len(filename) <= 160 else stem[:156] + extension
    content = file.file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="File exceeds the configured upload limit.")
    try:
        chunks = chunk_pages(extract_document(filename, content))
    except DocumentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not chunks:
        raise HTTPException(status_code=422, detail="No readable text was found.")

    digest = content_hash(content)
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        cleanup_expired(db, settings.session_ttl_days)
        if db.execute("SELECT 1 FROM documents WHERE session_id=? AND file_hash=?", (sid, digest)).fetchone():
            raise HTTPException(status_code=409, detail="This document is already in your workspace.")
        count = db.execute("SELECT count(*) FROM documents WHERE session_id=?", (sid,)).fetchone()[0]
        if count >= settings.max_documents_per_session:
            raise HTTPException(status_code=429, detail="Workspace document limit reached. Delete a document to continue.")
        doc_id = add_document(db, sid, filename, digest, chunks, len(content))
        return list_documents(db, sid, doc_id)[0]


@app.delete("/api/documents/{document_id}", status_code=204)
def remove_document(document_id: str, x_workspace_id: str | None = Header(default=None)):
    sid = workspace_id(x_workspace_id)
    with database() as db:
        if not db.execute("DELETE FROM documents WHERE id=? AND session_id=?", (document_id, sid)).rowcount:
            raise HTTPException(status_code=404, detail="Document not found.")


@app.get("/api/collections")
def collections(x_workspace_id: str | None = Header(default=None)):
    sid = workspace_id(x_workspace_id)
    with database() as db:
        cleanup_expired(db, settings.session_ttl_days)
        return {"collections": list_collections(db, sid)}


def save_collection(db, sid, payload, collection_id=None):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Enter a collection name.")
    try:
        if collection_id:
            updated = db.execute("UPDATE collections SET name=?, name_key=? WHERE id=? AND session_id=?",
                                 (name, name.casefold(), collection_id, sid))
            if not updated.rowcount:
                raise HTTPException(status_code=404, detail="Collection not found.")
        else:
            collection_id = str(uuid4())
            db.execute("INSERT INTO collections VALUES (?, ?, ?, ?)", (collection_id, sid, name, name.casefold()))
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="A collection with that name already exists.") from exc
    return next(item for item in list_collections(db, sid) if item["id"] == collection_id)


@app.post("/api/collections", status_code=201)
def create_collection(payload: CollectionName, x_workspace_id: str | None = Header(default=None)):
    with database() as db:
        return save_collection(db, workspace_id(x_workspace_id), payload)


@app.patch("/api/collections/{collection_id}")
def rename_collection(collection_id: str, payload: CollectionName, x_workspace_id: str | None = Header(default=None)):
    with database() as db:
        return save_collection(db, workspace_id(x_workspace_id), payload, collection_id)


@app.delete("/api/collections/{collection_id}", status_code=204)
def remove_collection(collection_id: str, x_workspace_id: str | None = Header(default=None)):
    sid = workspace_id(x_workspace_id)
    with database() as db:
        try:
            deleted = db.execute("DELETE FROM collections WHERE id=? AND session_id=?", (collection_id, sid))
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="Move the documents out before deleting this collection.") from exc
        if not deleted.rowcount:
            raise HTTPException(status_code=404, detail="Collection not found.")


@app.patch("/api/documents/{document_id}")
def assign_collection(document_id: str, payload: CollectionAssignment, x_workspace_id: str | None = Header(default=None)):
    sid = workspace_id(x_workspace_id)
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        if payload.collection_id is not None:
            require_collection(db, sid, payload.collection_id)
        if not db.execute("UPDATE documents SET collection_id=? WHERE id=? AND session_id=?",
                          (payload.collection_id, document_id, sid)).rowcount:
            raise HTTPException(status_code=404, detail="Document not found.")
        return list_documents(db, sid, document_id)[0]


def chat_result(mode, text, passages):
    sources = [{**{key: row[key] for key in ("passage_id", "document_id", "filename", "page_number")},
                "excerpt": row["text"]} for row in passages]
    return {"mode": mode, "answer": text, "sources": sources}


@app.post("/api/chat")
def chat(payload: ChatRequest, x_workspace_id: str | None = Header(default=None)):
    global provider_status
    sid = workspace_id(x_workspace_id)
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="Enter a question or keywords.")
    use_provider = bool(payload.use_provider and settings.openai_api_key)
    with database() as db:
        docs = list_documents(db, sid)
        if payload.collection_id is not None:
            require_collection(db, sid, payload.collection_id)
        allowed = {doc["id"] for doc in docs if not payload.collection_id or doc["collection_id"] == payload.collection_id}
        if not set(payload.document_ids).issubset(allowed):
            raise HTTPException(status_code=404, detail="One or more selected documents were not found in this search scope.")
        scope = (sid, payload.document_ids, payload.collection_id)
        matches = search_passages(db, sid, question, payload.document_ids, payload.collection_id)
        vectors = get_chunks(db, *scope, embedded_only=True) if use_provider else []
    if use_provider and (matches or vectors):
        try:
            client = ai_client()
            if vectors:
                embedding = client.embeddings.create(model=settings.openai_embedding_model, input=question).data[0].embedding
                ranked = retrieve(question, vectors, embedding)
                seen = {row["passage_id"] for row in ranked}
                matches = (ranked + [row for row in matches if row["passage_id"] not in seen])[:5]
            if matches:
                response = answer(client, settings.openai_chat_model, question, matches)
                provider_status = "ready"
                return chat_result("generative", response, matches)
        except Exception:
            provider_status = "error"
            raise HTTPException(status_code=502, detail="OpenAI request failed. Switch to local search to continue without a provider.") from None
    if not matches:
        return chat_result("local", "No relevant passages found. Try a more specific keyword or a wider document selection.", [])
    return chat_result("local", None, matches)
