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
from typing import List, Optional

from pypdf import PdfReader


def _module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def clean_text_for_markdown(text: str) -> str:
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = _repair_fraction_line_breaks(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = text.strip()
    return (text + "\n") if text else ""


def _looks_math_expression(text: str) -> bool:
    if not text:
        return False
    sample = text.strip()
    if not sample:
        return False
    math_chars = sum(1 for ch in sample if ch in "0123456789+-=*/^()[]{}\\_.,")
    return (math_chars / max(1, len(sample))) >= 0.35


def _repair_fraction_line_breaks(text: str) -> str:
    """Repair OCR/PDF line-broken fractions into \\frac{...}{...} form."""
    lines = (text or "").splitlines()
    out: List[str] = []
    i = 0
    while i < len(lines):
        cur = lines[i].strip()
        nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
        nxt2 = lines[i + 2].strip() if i + 2 < len(lines) else ""

        # Pattern: numerator, horizontal bar, denominator
        if (
            cur
            and nxt
            and nxt2
            and len(cur) <= 120
            and len(nxt2) <= 120
            and re.fullmatch(r"[-_=~]{2,}", nxt) is not None
            and _looks_math_expression(cur)
            and _looks_math_expression(nxt2)
        ):
            out.append(rf"\frac{{{cur}}}{{{nxt2}}}")
            i += 3
            continue

        # Pattern: numerator, "/", denominator
        if (
            cur
            and nxt == "/"
            and nxt2
            and len(cur) <= 120
            and len(nxt2) <= 120
            and _looks_math_expression(cur)
            and _looks_math_expression(nxt2)
        ):
            out.append(rf"\frac{{{cur}}}{{{nxt2}}}")
            i += 3
            continue

        out.append(lines[i])
        i += 1
    return "\n".join(out)


def _text_quality_score(text: str) -> float:
    normalized = (text or "").strip()
    if not normalized:
        return 0.0
    lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    if not lines:
        return 0.0
    chars = len(normalized)
    bad_glyphs = normalized.count("�")
    short_fragments = sum(1 for line in lines if len(line) <= 2)
    return chars - (bad_glyphs * 12) - (short_fragments * 2.5)


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
            text = (pytesseract.image_to_string(
                img,
                lang=ocr_lang,
                config="--oem 3 --psm 6",
            ) or "").strip()
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

    scanned_hint = detect_scanned_pdf(pdf_path)
    digital_md: Optional[str] = None
    ocr_md: Optional[str] = None
    digital_error: Optional[Exception] = None
    ocr_error: Optional[Exception] = None

    try:
        digital_md = extract_born_digital_markdown(pdf_path)
    except Exception as exc:
        digital_error = exc

    digital_score = _text_quality_score(digital_md or "")
    digital_weak = digital_score < 180.0

    # If scan is likely (or digital extraction looks poor), OCR should be attempted.
    if scanned_hint or digital_weak or digital_md is None:
        try:
            ocr_md = extract_scanned_markdown_with_ocr(pdf_path, ocr_lang=ocr_lang)
        except Exception as exc:
            ocr_error = exc

    if ocr_md and digital_md:
        ocr_score = _text_quality_score(ocr_md)
        # Prefer OCR when its quality is materially better or scan is hinted.
        if scanned_hint or ocr_score > (digital_score * 1.05):
            return ocr_md
        return digital_md
    if ocr_md:
        return ocr_md
    if digital_md:
        return digital_md

    if ocr_error:
        raise RuntimeError(f"Both digital and OCR extraction failed. OCR error: {ocr_error}") from ocr_error
    if digital_error:
        raise RuntimeError(f"Digital extraction failed: {digital_error}") from digital_error
    raise RuntimeError("PDF extraction failed for unknown reasons.")
