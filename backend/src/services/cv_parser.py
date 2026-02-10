"""
CV/Resume parser: PDF and DOCX text extraction and validation.
Structured parsing is done by services.llm.profile_analyzer.
"""
import io

from PyPDF2 import PdfReader
from docx import Document as DocxDocument

from src.config import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Magic bytes for PDF and DOCX
PDF_SIGNATURE = b"%PDF"
DOCX_SIGNATURE = b"PK"  # ZIP-based format
ALLOWED_PDF = "application/pdf"
ALLOWED_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class FileValidationError(Exception):
    """Raised when file type or size is invalid."""

    pass


def _read_pdf(content: bytes) -> str:
    """Extract text from PDF bytes."""
    reader = PdfReader(io.BytesIO(content))
    parts = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


def _read_docx(content: bytes) -> str:
    """Extract text from DOCX bytes."""
    doc = DocxDocument(io.BytesIO(content))
    return "\n".join(p.text for p in doc.paragraphs if p.text).strip()


def validate_file(content: bytes, content_type: str | None, filename: str | None) -> None:
    """
    Validate file size and type (magic bytes). Raises FileValidationError if invalid.
    """
    settings = get_settings()
    if len(content) > settings.cv_max_size_bytes:
        raise FileValidationError(
            f"File too large. Maximum size is {settings.cv_max_size_mb}MB."
        )
    if len(content) < 10:
        raise FileValidationError("File is too small or empty.")

    # Prefer magic bytes over content_type
    if content.startswith(PDF_SIGNATURE):
        if content_type and content_type not in (ALLOWED_PDF, "application/octet-stream"):
            logger.warning("Content-Type mismatch for PDF", extra={"content_type": content_type})
        return
    if content[:2] == DOCX_SIGNATURE and b"word/document" in content[:5000]:
        if content_type and content_type not in (
            ALLOWED_DOCX,
            "application/octet-stream",
        ):
            logger.warning("Content-Type mismatch for DOCX", extra={"content_type": content_type})
        return
    raise FileValidationError(
        "Invalid file type. Only PDF and DOCX are allowed."
    )


def extract_text(content: bytes, content_type: str | None, filename: str | None) -> str:
    """
    Validate and extract raw text from PDF or DOCX. Raises FileValidationError on invalid input.
    """
    validate_file(content, content_type, filename)
    if content.startswith(PDF_SIGNATURE):
        return _read_pdf(content)
    if content[:2] == DOCX_SIGNATURE:
        return _read_docx(content)
    raise FileValidationError("Unsupported file format.")


# Structured CV data is produced by services.llm.profile_analyzer.ProfileAnalyzer.analyze_cv_text()
