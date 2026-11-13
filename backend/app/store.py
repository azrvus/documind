import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

# Ignore question boilerplate; quoted FTS tokens are data, never FTS syntax.
STOP_WORDS = set("""a an and are about can could did do does for from had has have how i in is it its me my of on or our please should tell that the their them there these they this those to was were what when where which who why will with would you your document documents file files discuss discussed mentioned main key find show""".split())


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    if db.execute("PRAGMA user_version").fetchone()[0] < 1:
        try:
            migrate(db)
        except Exception:
            db.close()
            raise
    return db


def migrate(db: sqlite3.Connection) -> None:
    with db:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("PRAGMA user_version").fetchone()[0] >= 1:
            return
        statements = [
            """CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY, session_id TEXT NOT NULL, filename TEXT NOT NULL,
                file_hash TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
                UNIQUE(session_id, file_hash))""",
            """CREATE TABLE IF NOT EXISTS chunks (
                id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                page_number INTEGER NOT NULL, text TEXT NOT NULL, embedding TEXT)""",
            """CREATE TABLE collections (
                id TEXT PRIMARY KEY, session_id TEXT NOT NULL, name TEXT NOT NULL,
                name_key TEXT NOT NULL, UNIQUE(session_id, name_key))""",
            "ALTER TABLE documents ADD COLUMN size_bytes INTEGER",
            "ALTER TABLE documents ADD COLUMN collection_id TEXT REFERENCES collections(id) ON DELETE RESTRICT",
            "CREATE INDEX IF NOT EXISTS idx_docs_session ON documents(session_id, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id)",
            "CREATE INDEX idx_docs_collection ON documents(collection_id)",
            """CREATE VIRTUAL TABLE passage_search USING fts5(
                text, content='chunks', content_rowid='rowid', tokenize='porter unicode61')""",
            """CREATE TRIGGER passage_insert AFTER INSERT ON chunks BEGIN
                INSERT INTO passage_search(rowid, text) VALUES (new.rowid, new.text); END""",
            """CREATE TRIGGER passage_delete AFTER DELETE ON chunks BEGIN
                INSERT INTO passage_search(passage_search, rowid, text)
                VALUES ('delete', old.rowid, old.text); END""",
            "INSERT INTO passage_search(passage_search) VALUES ('rebuild')",
            "PRAGMA user_version=1",
        ]
        for statement in statements:
            db.execute(statement)


def add_document(db, session_id, filename, digest, chunks, size_bytes) -> str:
    doc_id = str(uuid4())
    db.execute("""INSERT INTO documents (id, session_id, filename, file_hash, status, created_at, size_bytes)
        VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (doc_id, session_id, filename, digest, "ready", datetime.now(timezone.utc).isoformat(), size_bytes))
    db.executemany("INSERT INTO chunks (id, document_id, page_number, text) VALUES (?, ?, ?, ?)",
                   [(str(uuid4()), doc_id, chunk["page_number"], chunk["text"]) for chunk in chunks])
    return doc_id


def list_documents(db, session_id, document_id=None) -> list[dict]:
    rows = db.execute("""SELECT d.id, d.filename, lower(substr(d.filename, -3)) AS file_type,
        d.status, d.created_at, d.size_bytes, d.collection_id, count(c.id) AS chunks
        FROM documents d LEFT JOIN chunks c ON c.document_id=d.id
        WHERE d.session_id=? AND (? IS NULL OR d.id=?)
        GROUP BY d.id ORDER BY d.created_at DESC""", (session_id, document_id, document_id))
    return [dict(row) for row in rows]


def list_collections(db, session_id) -> list[dict]:
    return [dict(row) for row in db.execute("""SELECT c.id, c.name, count(d.id) AS document_count
        FROM collections c LEFT JOIN documents d ON d.collection_id=c.id AND d.session_id=c.session_id
        WHERE c.session_id=? GROUP BY c.id ORDER BY c.name_key, c.id""", (session_id,))]


def document_scope(document_ids, collection_id):
    where, params = "", []
    if document_ids:
        where += " AND d.id IN (" + ",".join("?" for _ in document_ids) + ")"
        params.extend(document_ids)
    if collection_id:
        where += " AND d.collection_id=?"
        params.append(collection_id)
    return where, params


PASSAGE_FIELDS = "c.id AS passage_id, c.document_id, d.filename, c.page_number, c.text"


def get_chunks(db, session_id, document_ids=None, collection_id=None, embedded_only=False) -> list[dict]:
    where, params = document_scope(document_ids, collection_id)
    if embedded_only:
        where += " AND c.embedding IS NOT NULL"
    fields = PASSAGE_FIELDS + (", c.embedding" if embedded_only else "")
    return [dict(row) for row in db.execute(f"""SELECT {fields} FROM chunks c
        JOIN documents d ON d.id=c.document_id WHERE d.session_id=? {where}
        ORDER BY c.page_number, c.rowid""", (session_id, *params))]


def search_passages(db, session_id, question, document_ids=None, collection_id=None) -> list[dict]:
    words = re.findall(r"[^\W_]+", question.lower())
    keywords = list(dict.fromkeys(word for word in words if word not in STOP_WORDS))[:32]
    if not keywords:
        return []
    query = " OR ".join(f'"{word}"' for word in keywords)
    where, params = document_scope(document_ids, collection_id)
    return [dict(row) for row in db.execute(f"""SELECT {PASSAGE_FIELDS} FROM passage_search
        JOIN chunks c ON c.rowid=passage_search.rowid JOIN documents d ON d.id=c.document_id
        WHERE passage_search MATCH ? AND d.session_id=? {where}
        ORDER BY bm25(passage_search), c.rowid LIMIT 5""", (query, session_id, *params))]


def cleanup_expired(db, ttl_days) -> None:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=ttl_days)).isoformat()
    db.execute("DELETE FROM documents WHERE created_at < ?", (cutoff,))
