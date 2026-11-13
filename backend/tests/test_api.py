import sqlite3
from types import SimpleNamespace

import fitz

from app import main

from .conftest import workspace

H = {"X-Workspace-Id": workspace()}
OTHER = {"X-Workspace-Id": "00000000-0000-4000-8000-000000000002"}


def upload(client, name, text, headers=H):
    result = client.post("/api/documents", headers=headers, files={"file": (name, text)})
    assert result.status_code == 201, result.text
    return result.json()


def search(client, question, headers=H, **options):
    result = client.post("/api/chat", headers=headers, json={"question": question, **options})
    assert result.status_code == 200, result.text
    return result.json()


def test_health_and_local_search_with_no_credentials(client, monkeypatch):
    def forbidden():
        raise AssertionError("Local mode must not create a provider client")

    monkeypatch.setattr(main, "ai_client", forbidden)
    assert client.get("/api/health").json() == {
        "status": "ok", "ai_configured": False, "provider": "openai", "provider_status": "not_configured",
    }
    content = "Account access is available on weekdays."
    doc = upload(client, "guide.txt", content.encode())
    assert doc["file_type"] == "txt" and doc["size_bytes"] == len(content)
    result = search(client, "When can I access my account?", use_provider=True)
    assert result["mode"] == "local" and result["answer"] is None
    source, = result["sources"]
    assert source == {"document_id": doc["id"], "filename": "guide.txt", "page_number": 1,
                      "passage_id": source["passage_id"], "excerpt": content}
    detail = client.get(f"/api/documents/{doc['id']}", headers=H).json()
    assert detail["passages"][0]["passage_id"] == source["passage_id"]
    assert detail["passages"][0]["text"] == content


def test_upload_validation(client):
    for name, body, status in [("x.exe", b"x", 415), ("x.txt", b"  ", 422), ("fake.pdf", b"%PDF-no", 422),
                               ("invalid.txt", b"\xff", 422)]:
        assert client.post("/api/documents", headers=H, files={"file": (name, body)}).status_code == status
    upload(client, "real.txt", b"An original document.")
    assert client.post("/api/documents", headers=H, files={"file": ("copy.txt", b"An original document.")}).status_code == 409


def test_ranked_pdf_excerpts_and_page_numbers(client):
    with fitz.open() as pdf:
        pdf.new_page().insert_text((72, 72), "General information about filing.")
        pdf.new_page().insert_text((72, 72), "Encryption requirements: backups must use encryption.")
        doc = upload(client, "handbook.pdf", pdf.tobytes())
    upload(client, "notes.txt", b"Requirements vary depending on the project.")
    matches = search(client, "What are the encryption requirements in this document?")["sources"]
    assert matches[0]["document_id"] == doc["id"]
    assert matches[0]["page_number"] == 2
    assert "backups must use encryption" in matches[0]["excerpt"]
    assert all(source["page_number"] != 1 or source["document_id"] != doc["id"] for source in matches)
    assert search(client, "encipherment")["sources"] == []
    assert search(client, 'when is it?')["answer"].startswith("No relevant passages")
    assert search(client, '"requirements" OR * --')["sources"]


def test_workspace_scope_and_fts_deletion(client):
    doc = upload(client, "private.txt", b"Private keyword axolotl.")
    path = f"/api/documents/{doc['id']}"
    assert client.get("/api/documents").status_code == 400
    assert client.get("/api/documents", headers={"X-Workspace-Id": "invalid"}).status_code == 400
    assert client.get(path, headers=OTHER).status_code == 404
    assert client.delete(path, headers=OTHER).status_code == 404
    assert client.get("/api/documents", headers=OTHER).json()["documents"] == []
    assert search(client, "axolotl", OTHER)["sources"] == []
    assert client.post("/api/chat", headers=OTHER, json={"question": "axolotl", "document_ids": [doc["id"]]}).status_code == 404
    assert client.delete(path, headers=H).status_code == 204
    assert client.get("/api/documents", headers=H).json()["documents"] == []
    assert search(client, "axolotl")["sources"] == []
    with main.database() as db:
        db.execute("CREATE VIRTUAL TABLE temp.terms USING fts5vocab(main, passage_search, row)")
        assert db.execute("SELECT count(*) FROM terms WHERE term='axolotl'").fetchone()[0] == 0


def test_collection_lifecycle_and_scope(client):
    def create(name, headers=H):
        return client.post("/api/collections", headers=headers, json={"name": name})
    created = create("  Projects  ")
    assert created.status_code == 201
    group = created.json()
    assert group["name"] == "Projects" and group["document_count"] == 0
    assert create("PROJECTS").status_code == 409
    assert create("PROJECTS", OTHER).status_code == 201
    collection = f"/api/collections/{group['id']}"
    assert client.patch(collection, headers=OTHER, json={"name": "Foreign"}).status_code == 404
    assert client.delete(collection, headers=OTHER).status_code == 404
    assert client.patch(collection, headers=H, json={"name": "Research"}).json()["name"] == "Research"
    doc = upload(client, "one.txt", b"Sequoia details from research.")
    upload(client, "two.txt", b"Sequoia details in a different file.")
    doc_path = f"/api/documents/{doc['id']}"
    assert client.patch(doc_path, headers=OTHER, json={"collection_id": group["id"]}).status_code == 404
    assert client.patch(doc_path, headers=H, json={"collection_id": group["id"]}).json()["collection_id"] == group["id"]
    assert client.get("/api/collections", headers=H).json()["collections"][0]["document_count"] == 1
    assert client.delete(collection, headers=H).status_code == 409
    assert [item["document_id"] for item in search(client, "sequoia", collection_id=group["id"])["sources"]] == [doc["id"]]
    assert client.post("/api/chat", headers=OTHER, json={"question": "sequoia", "collection_id": group["id"]}).status_code == 404
    assert client.patch(doc_path, headers=H, json={"collection_id": None}).json()["collection_id"] is None
    assert client.delete(collection, headers=H).status_code == 204
    assert client.get("/api/collections", headers=H).json()["collections"] == []


def test_provider_status_changes_only_after_explicit_real_path(client, monkeypatch):
    monkeypatch.setattr(main.settings, "openai_api_key", "test-key")
    assert client.get("/api/health").json()["provider_status"] == "unverified"
    upload(client, "guide.txt", b"Access is available on weekdays.")
    assert search(client, "weekdays")["mode"] == "local"
    assert client.get("/api/health").json()["provider_status"] == "unverified"
    def completion(**kwargs):
        assert "Access is available on weekdays." in kwargs["messages"][1]["content"]
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="Weekday access."))])
    monkeypatch.setattr(main, "ai_client", lambda: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=completion))))
    result = search(client, "weekdays", use_provider=True)
    assert result["mode"] == "generative" and result["answer"] == "Weekday access."
    assert client.get("/api/health").json()["provider_status"] == "ready"
    def failing():
        raise RuntimeError("secret exception text")
    monkeypatch.setattr(main, "ai_client", failing)
    error = client.post("/api/chat", headers=H, json={"question": "weekdays", "use_provider": True})
    assert error.status_code == 502 and "secret exception text" not in error.text
    assert client.get("/api/health").json()["provider_status"] == "error"
    assert search(client, "weekdays")["sources"]


def test_migration_indexes_existing_passages_without_changing_citations(client):
    with sqlite3.connect(main.DB_PATH) as db:
        db.executescript("""
        CREATE TABLE documents (id TEXT PRIMARY KEY, session_id TEXT NOT NULL, filename TEXT NOT NULL,
          file_hash TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(session_id, file_hash));
        CREATE TABLE chunks (id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
          page_number INTEGER NOT NULL, text TEXT NOT NULL, embedding TEXT);
        """)
        db.execute("INSERT INTO documents VALUES (?, ?, ?, ?, ?, datetime('now'))",
                   ("old-document", workspace(), "archive.pdf", "hash", "ready"))
        db.execute("INSERT INTO chunks VALUES ('old-passage', 'old-document', 7, 'Historical aperture settings', NULL)")
    source, = search(client, "aperture")["sources"]
    assert source["passage_id"] == "old-passage" and source["page_number"] == 7
    assert client.get("/api/documents", headers=H).json()["documents"][0]["size_bytes"] is None


def test_request_size_limit_and_cors(client, monkeypatch):
    monkeypatch.setattr(main.settings, "max_request_bytes", 128)
    result = client.post("/api/chat", content=b"x" * 129, headers={"Origin": "http://localhost:3003"})
    assert result.status_code == 413
    assert result.headers["access-control-allow-origin"] == "http://localhost:3003"
    assert "access-control-allow-origin" not in client.get("/api/health", headers={"Origin": "http://other.test"}).headers
