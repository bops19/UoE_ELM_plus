"""CPU-oriented PDF -> Markdown conversion service.

Workflow:
1) Detect scanned/image-only PDFs.
2) Use born-digital extraction when text exists.
3) Use OCR path for scanned PDFs when OCR deps are available.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from typing import List

from pypdf import PdfReader


def _module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def clean_text_for_markdown(text: str) -> str:
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = text.strip()
    return (text + "\n") if text else ""


def detect_scanned_pdf(
    pdf_path: Path,
    sample_pages: int = 6,
    text_threshold: int = 120,
) -> bool:
    """Heuristic scan detection: low extracted text in first pages => scanned."""
    try:
        import fitz  # type: ignore
    except Exception:
        # If PyMuPDF is not installed, assume digital path first.
        return False

    with fitz.open(str(pdf_path)) as doc:
        n = min(sample_pages, len(doc))
        if n <= 0:
            return True
        total_chars = 0
        for i in range(n):
            total_chars += len((doc[i].get_text("text") or "").strip())
    return total_chars < text_threshold


def extract_born_digital_markdown(pdf_path: Path) -> str:
    """Prefer pymupdf4llm markdown output when present, else pypdf fallback."""
    if _module_available("pymupdf4llm"):
        import pymupdf4llm  # type: ignore

        md = pymupdf4llm.to_markdown(str(pdf_path))
        if md and str(md).strip():
            return clean_text_for_markdown(str(md))

    reader = PdfReader(str(pdf_path))
    chunks: List[str] = []
    for i, page in enumerate(reader.pages):
        page_text = (page.extract_text() or "").strip()
        if not page_text:
            continue
        chunks.append(f"\n## Page {i + 1}\n\n{page_text}\n")
    if not chunks:
        raise ValueError("No extractable text found in PDF.")
    return clean_text_for_markdown("\n".join(chunks))


def extract_scanned_markdown_with_ocr(pdf_path: Path, ocr_lang: str = "eng") -> str:
    if not _module_available("fitz"):
        raise RuntimeError("PyMuPDF is required for OCR path: pip install pymupdf")
    if not _module_available("pytesseract") or not _module_available("PIL"):
        raise RuntimeError("OCR dependencies missing: pip install pytesseract pillow")

    import fitz  # type: ignore
    import pytesseract  # type: ignore
    from PIL import Image  # type: ignore

    chunks: List[str] = []
    with fitz.open(str(pdf_path)) as doc:
        for i, page in enumerate(doc):
            mat = fitz.Matrix(2.0, 2.0)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            text = (pytesseract.image_to_string(img, lang=ocr_lang) or "").strip()
            if text:
                chunks.append(f"\n## Page {i + 1}\n\n{text}\n")
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

    scanned = detect_scanned_pdf(pdf_path)
    if scanned:
        try:
            return extract_scanned_markdown_with_ocr(pdf_path, ocr_lang=ocr_lang)
        except Exception:
            # Graceful fallback for environments without OCR tooling.
            return extract_born_digital_markdown(pdf_path)
    return extract_born_digital_markdown(pdf_path)

