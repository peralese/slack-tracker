"""
document_extractor.py — Extract plain text from document file bytes.

Supports:
    .docx  — python-docx
    .pptx  — python-pptx
    .pdf   — pypdf

Usage:
    text = extract_text(file_bytes, "report.docx")
"""

from __future__ import annotations

import io
import logging
import os

logger = logging.getLogger(__name__)

# Supported extensions mapped to their extractor functions
_SUPPORTED_EXTENSIONS = {".docx", ".pptx", ".pdf"}


def extract_text(file_bytes: bytes, filename: str) -> str | None:
    """Extract plain text from document bytes.

    Args:
        file_bytes: Raw file content in memory.
        filename:   Original filename — used to determine file type.

    Returns:
        Extracted text string, or None if the file type is unsupported or
        extraction fails.
    """
    ext = os.path.splitext(filename.lower())[1]

    if ext not in _SUPPORTED_EXTENSIONS:
        logger.debug("Unsupported file type for extraction: %s", filename)
        return None

    try:
        if ext == ".docx":
            return _extract_docx(file_bytes)
        elif ext == ".pptx":
            return _extract_pptx(file_bytes)
        elif ext == ".pdf":
            return _extract_pdf(file_bytes)
    except Exception as exc:
        logger.error("Failed to extract text from %s: %s", filename, exc)
        return None

    return None


def _extract_docx(file_bytes: bytes) -> str:
    """Extract text from a .docx file."""
    import docx  # python-docx
    doc = docx.Document(io.BytesIO(file_bytes))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n".join(paragraphs)


def _extract_pptx(file_bytes: bytes) -> str:
    """Extract text from a .pptx file."""
    from pptx import Presentation  # python-pptx
    prs = Presentation(io.BytesIO(file_bytes))
    lines: list[str] = []
    for slide in prs.slides:
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text.strip():
                lines.append(shape.text.strip())
    return "\n".join(lines)


def _extract_pdf(file_bytes: bytes) -> str:
    """Extract text from a .pdf file."""
    import pypdf
    reader = pypdf.PdfReader(io.BytesIO(file_bytes))
    pages: list[str] = []
    for page in reader.pages:
        text = page.extract_text()
        if text and text.strip():
            pages.append(text.strip())
    return "\n".join(pages)
