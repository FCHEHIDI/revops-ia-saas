"""Multi-format document parser for the RAG ingestion pipeline.

Supported formats:
    .txt / .md / .csv  — plain UTF-8 read
    .pdf               — pypdf page-by-page extraction
    .docx              — python-docx paragraph extraction
    .xlsx / .xls       — openpyxl sheet → tabular text
    everything else    — best-effort UTF-8 decode (binary fallback)

All public functions are synchronous (CPU-bound) and should be called via
``asyncio.get_event_loop().run_in_executor(None, ...)`` from async context.
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_text(file_path: str) -> str:
    """Extract plain text from *file_path*, dispatching by file extension.

    Args:
        file_path: Absolute or relative path to the source file.

    Returns:
        Extracted text as a single string.  Never raises — falls back to an
        empty string with a logged warning on unrecoverable errors.

    Raises:
        FileNotFoundError: If the file does not exist at *file_path*.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Document not found: {file_path}")

    ext = path.suffix.lower()

    try:
        if ext == ".pdf":
            return _extract_pdf(path)
        elif ext in (".docx",):
            return _extract_docx(path)
        elif ext in (".xlsx", ".xls"):
            return _extract_xlsx(path)
        else:
            # .txt, .md, .csv, .json, .yaml, unknown binary → UTF-8
            return _extract_plaintext(path)
    except Exception as exc:
        logger.error(
            "Text extraction failed for '%s' (ext=%s): %s",
            file_path,
            ext,
            exc,
            exc_info=True,
        )
        return ""


def detect_document_type(filename: str) -> str:
    """Infer a document_type tag from the file extension / name.

    Args:
        filename: The file name (basename, with extension).

    Returns:
        A document_type string compatible with ``TextChunker.split()``:
        one of ``playbook``, ``report``, ``contract``, ``spreadsheet``,
        ``presentation``, or ``other``.
    """
    name = filename.lower()
    ext = Path(filename).suffix.lower()

    # Extension-based detection first
    if ext in (".xlsx", ".xls", ".csv"):
        return "spreadsheet"

    # Name-based heuristics
    for keyword in ("playbook", "runbook", "guide"):
        if keyword in name:
            return "playbook"
    for keyword in ("report", "rapport", "bilan", "analyse"):
        if keyword in name:
            return "report"
    for keyword in ("contrat", "contract", "accord", "agreement", "avenant"):
        if keyword in name:
            return "contract"

    return "other"


# ---------------------------------------------------------------------------
# Format-specific extractors
# ---------------------------------------------------------------------------


def _extract_plaintext(path: Path) -> str:
    """Read a plain-text file, tolerating encoding errors.

    Args:
        path: Path to the text file.

    Returns:
        File contents as a string.
    """
    return path.read_text(encoding="utf-8", errors="replace")


def _extract_pdf(path: Path) -> str:
    """Extract text from a PDF using pypdf.

    Iterates over all pages and joins them with a page separator so the
    chunker can preserve approximate page-level context.

    Args:
        path: Path to the PDF file.

    Returns:
        Concatenated text from all pages.
    """
    try:
        from pypdf import PdfReader  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(
            "pypdf is required for PDF parsing. "
            "Install it with: pip install pypdf"
        ) from exc

    reader = PdfReader(str(path))
    pages: list[str] = []

    for page_num, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text() or ""
        if page_text.strip():
            pages.append(f"[Page {page_num}]\n{page_text.strip()}")

    logger.debug("Extracted %d pages from PDF '%s'", len(pages), path.name)
    return "\n\n".join(pages)


def _extract_docx(path: Path) -> str:
    """Extract text from a DOCX file using python-docx.

    Preserves heading structure by inserting blank lines between sections.

    Args:
        path: Path to the DOCX file.

    Returns:
        Extracted text with heading/paragraph structure preserved.
    """
    try:
        import docx  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(
            "python-docx is required for DOCX parsing. "
            "Install it with: pip install python-docx"
        ) from exc

    doc = docx.Document(str(path))
    lines: list[str] = []

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        # Add extra spacing after headings to hint the chunker
        if para.style.name.lower().startswith("heading"):
            lines.append(f"\n## {text}\n")
        else:
            lines.append(text)

    logger.debug("Extracted %d paragraphs from DOCX '%s'", len(lines), path.name)
    return "\n".join(lines)


def _extract_xlsx(path: Path) -> str:
    """Extract tabular data from an XLSX/XLS file as human-readable text.

    Each sheet is rendered as a TSV-like block with a sheet header.
    Empty rows are skipped.

    Args:
        path: Path to the Excel file.

    Returns:
        All sheets concatenated as plain text.
    """
    try:
        import openpyxl  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(
            "openpyxl is required for Excel parsing. "
            "Install it with: pip install openpyxl"
        ) from exc

    wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    sheets: list[str] = []

    for sheet in wb.worksheets:
        rows: list[str] = []
        for row in sheet.iter_rows(values_only=True):
            cells = [str(c) if c is not None else "" for c in row]
            if any(cells):
                rows.append("\t".join(cells))
        if rows:
            sheets.append(f"[Feuille: {sheet.title}]\n" + "\n".join(rows))

    wb.close()
    logger.debug("Extracted %d sheet(s) from Excel '%s'", len(sheets), path.name)
    return "\n\n".join(sheets)
