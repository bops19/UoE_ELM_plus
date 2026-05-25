"""Simple CPU-oriented PDF -> Markdown conversion service.

Workflow:
1) Detect scanned/image-only PDFs.
2) Extract text directly for born-digital PDFs.
3) Use Tesseract OCR for scanned PDFs.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from typing import List


def _module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _import_pymupdf():
    try:
        import fitz  # type: ignore

        return fitz
    except Exception:
        try:
            import pymupdf  # type: ignore

            return pymupdf
        except Exception:
            return None


def clean_text_for_markdown(text: str) -> str:
    """Light cleanup to keep Markdown readable."""
    normalized = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    normalized = re.sub(r"[ \t]+\n", "\n", normalized)
    normalized = normalized.strip()
    return (normalized + "\n") if normalized else ""


def detect_scanned_pdf(
    pdf_path: Path,
    sample_pages: int = 6,
    text_threshold: int = 120,
) -> bool:
    """Return True when the PDF looks mostly scanned/image-only."""
    fitz = _import_pymupdf()
    if fitz is None:
        return False

    with fitz.open(str(pdf_path)) as doc:
        page_count = min(sample_pages, len(doc))
        if page_count <= 0:
            return True

        total_chars = 0
        for page_index in range(page_count):
            total_chars += len((doc[page_index].get_text("text") or "").strip())

    return total_chars < text_threshold


def extract_born_digital_markdown(pdf_path: Path) -> str:
    """Extract plain text page-by-page from a born-digital PDF."""
    fitz = _import_pymupdf()
    if fitz is None:
        raise RuntimeError("PyMuPDF is required for PDF text extraction.")

    chunks: List[str] = []
    with fitz.open(str(pdf_path)) as doc:
        for index, page in enumerate(doc):
            text = (page.get_text("text") or "").strip()
            if not text:
                continue
            chunks.append(f"\n## Page {index + 1}\n\n{text}\n")

    if not chunks:
        raise ValueError("No extractable text found in PDF.")
    return clean_text_for_markdown("\n".join(chunks))


def extract_scanned_markdown_with_ocr(pdf_path: Path, ocr_lang: str = "eng") -> str:
    """Run Tesseract OCR page-by-page on a scanned PDF."""
    fitz = _import_pymupdf()
    if fitz is None:
        raise RuntimeError("PyMuPDF is required for OCR extraction.")
    if not _module_available("pytesseract") or not _module_available("PIL"):
        raise RuntimeError("OCR dependencies missing: pip install pytesseract pillow")

    import pytesseract  # type: ignore
    from PIL import Image  # type: ignore

    chunks: List[str] = []
    with fitz.open(str(pdf_path)) as doc:
        for index, page in enumerate(doc):
            pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), alpha=False)
            image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            text = (pytesseract.image_to_string(image, lang=ocr_lang) or "").strip()
            if not text:
                continue
            chunks.append(f"\n## Page {index + 1}\n\n{text}\n")

    if not chunks:
        raise ValueError("OCR produced no text.")
    return clean_text_for_markdown("\n".join(chunks))


def convert_pdf_to_markdown(
    pdf_path: Path,
    force_mode: str = "auto",
    ocr_lang: str = "eng",
) -> str:
    """Return markdown text for a single PDF path."""
    mode = (force_mode or "auto").strip().lower()
    if mode not in {"auto", "digital", "scanned"}:
        raise ValueError("force_mode must be one of: auto, digital, scanned")
    if not pdf_path.exists() or not pdf_path.is_file():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    if mode == "digital":
        return extract_born_digital_markdown(pdf_path)
    if mode == "scanned":
        return extract_scanned_markdown_with_ocr(pdf_path, ocr_lang=ocr_lang)

    if detect_scanned_pdf(pdf_path):
        return extract_scanned_markdown_with_ocr(pdf_path, ocr_lang=ocr_lang)
    return extract_born_digital_markdown(pdf_path)
