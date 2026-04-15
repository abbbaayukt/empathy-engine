"""
file_reader.py — Extract plain text from .txt, .pdf, and .docx files.
"""

import os

SUPPORTED_EXTENSIONS = {".txt", ".pdf", ".docx"}


def extract_text(file_path: str) -> str:
    """
    Extract text from a file given its path on disk.
    Supports: .txt, .pdf, .docx
    Returns the extracted text as a plain string.
    """
    _, ext = os.path.splitext(file_path)
    ext = ext.lower()

    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type '{ext}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    if ext == ".txt":
        return _read_txt(file_path)
    elif ext == ".pdf":
        return _read_pdf(file_path)
    elif ext == ".docx":
        return _read_docx(file_path)


def extract_text_from_bytes(filename: str, content: bytes) -> str:
    """
    Extract text directly from raw bytes + original filename (for API uploads).
    """
    import tempfile

    _, ext = os.path.splitext(filename)
    ext = ext.lower()

    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type '{ext}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    # Write to a temp file so existing readers can handle it
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        return extract_text(tmp_path)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Format-specific readers
# ---------------------------------------------------------------------------

def _read_txt(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read().strip()


def _read_pdf(path: str) -> str:
    try:
        import PyPDF2
    except ImportError:
        raise ImportError("PyPDF2 is required for PDF support. Run: pip install PyPDF2")

    text_parts = []
    with open(path, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text.strip())

    return "\n".join(text_parts).strip()


def _read_docx(path: str) -> str:
    try:
        import docx
    except ImportError:
        raise ImportError("python-docx is required for DOCX support. Run: pip install python-docx")

    doc = docx.Document(path)
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    return "\n".join(paragraphs).strip()
