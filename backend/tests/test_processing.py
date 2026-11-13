import pytest

from app.processing import DocumentError, chunk_pages, extract_document


def test_extracts_utf8_text_and_chunks():
    pages = extract_document("notes.txt", ("Alpha sentence. " * 100).encode())
    chunks = chunk_pages(pages, chunk_size=180, overlap=30)
    assert pages[0].page_number == 1
    assert len(chunks) > 1
    assert all(chunk["page_number"] == 1 for chunk in chunks)


def test_rejects_empty_and_bad_text():
    with pytest.raises(DocumentError):
        extract_document("empty.txt", b"  \n")
    with pytest.raises(DocumentError):
        extract_document("bad.txt", b"\xff")


def test_rejects_malformed_and_encrypted_pdf():
    with pytest.raises(DocumentError, match="signature"):
        extract_document("bad.pdf", b"not a pdf")
    # Minimal PDF-shaped data is rejected safely by the parser.
    with pytest.raises(DocumentError):
        extract_document("broken.pdf", b"%PDF-1.4 broken")


def test_unsupported_extension():
    with pytest.raises(DocumentError):
        extract_document("run.py", b"print('no')")


def test_rejects_encrypted_pdf():
    import fitz

    doc = fitz.open()
    doc.new_page()
    encrypted = doc.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="reader")
    doc.close()
    with pytest.raises(DocumentError, match="Encrypted"):
        extract_document("locked.pdf", encrypted)
