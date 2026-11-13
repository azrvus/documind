import hashlib
import re
from dataclasses import dataclass

import fitz


class DocumentError(ValueError):
    pass


@dataclass
class ExtractedPage:
    page_number: int
    text: str


def extract_document(filename: str, content: bytes) -> list[ExtractedPage]:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if not content or not content.strip():
        raise DocumentError("The file is empty or contains no readable text.")
    if ext == "txt":
        if content.startswith(b"%PDF-"):
            raise DocumentError("The file content does not match its TXT extension.")
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise DocumentError("Text files must use UTF-8 encoding.") from exc
        text = normalize(text)
        if len(text) > 2_000_000:
            raise DocumentError("Extracted document text exceeds the 2 MB processing limit.")
        if not text:
            raise DocumentError("The file contains no readable text.")
        return [ExtractedPage(1, text)]
    if ext != "pdf":
        raise DocumentError("Only PDF and TXT files are supported.")
    if not content.startswith(b"%PDF-"):
        raise DocumentError("The file does not have a valid PDF signature.")
    try:
        doc = fitz.open(stream=content, filetype="pdf")
        if doc.is_encrypted:
            raise DocumentError("Encrypted PDFs are not supported.")
        if len(doc) > 500:
            doc.close()
            raise DocumentError("PDFs are limited to 500 pages.")
        pages = [ExtractedPage(index + 1, normalize(page.get_text())) for index, page in enumerate(doc)]
        doc.close()
    except DocumentError:
        raise
    except Exception as exc:
        raise DocumentError("The PDF is malformed or could not be read.") from exc
    pages = [page for page in pages if page.text]
    if sum(len(page.text) for page in pages) > 2_000_000:
        raise DocumentError("Extracted document text exceeds the 2 MB processing limit.")
    if not pages:
        raise DocumentError("No readable text was found. Scanned image PDFs are not supported yet.")
    return pages


def normalize(text: str) -> str:
    return re.sub(r"[ \t]+", " ", text.replace("\x00", "")).strip()


def chunk_pages(pages: list[ExtractedPage], chunk_size: int = 900, overlap: int = 140) -> list[dict]:
    chunks: list[dict] = []
    for page in pages:
        text = page.text
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            if end < len(text):
                boundary = text.rfind(" ", start + chunk_size // 2, end)
                if boundary > start:
                    end = boundary
            piece = text[start:end].strip()
            if piece:
                chunks.append({"text": piece, "page_number": page.page_number})
            if end >= len(text):
                break
            start = max(end - overlap, start + 1)
    return chunks


def content_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
