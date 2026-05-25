"""CPU-oriented PDF -> Markdown conversion service.

Workflow:
1) Detect scanned/image-only PDFs.
2) Use born-digital extraction when text exists.
3) Use OCR path for scanned PDFs when OCR deps are available.
"""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from pypdf import PdfReader


@dataclass
class EquationRegion:
    page_number: int
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    latex: Optional[str] = None


def _module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _command_available(name: str) -> bool:
    return shutil.which(name) is not None


def _build_model_cache_env() -> dict[str, str]:
    env = os.environ.copy()
    cache_root = Path(tempfile.gettempdir()) / "pdf_markdown_model_cache"
    torch_home = cache_root / "torch"
    hf_home = cache_root / "huggingface"
    for path in (cache_root, torch_home, hf_home):
        path.mkdir(parents=True, exist_ok=True)
    env["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"
    env["XDG_CACHE_HOME"] = str(cache_root)
    env["TORCH_HOME"] = str(torch_home)
    env["HF_HOME"] = str(hf_home)
    return env


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
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = _patch_equation_blocks(text)
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


def _looks_display_equation_line(text: str) -> bool:
    sample = (text or "").strip()
    if not sample:
        return False
    if len(sample) > 180:
        return False
    if sample.startswith("## "):
        return False
    equation_markers = ["=", "\\sum", "\\int", "\\frac", ">=", "<=", "->", "+", "-", "*", "/"]
    marker_hits = sum(1 for marker in equation_markers if marker in sample)
    alpha_chars = sum(1 for ch in sample if ch.isalpha())
    non_space_chars = sum(1 for ch in sample if not ch.isspace())
    symbol_chars = sum(1 for ch in sample if ch in "0123456789+-=*/^()[]{}\\_.,<>|")
    symbol_ratio = symbol_chars / max(1, non_space_chars)
    return marker_hits >= 2 or (marker_hits >= 1 and symbol_ratio >= 0.28 and alpha_chars <= max(16, len(sample) // 2))


def _patch_equation_blocks(text: str) -> str:
    lines = (text or "").splitlines()
    out: List[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            out.append(line)
            i += 1
            continue

        block = [stripped]
        j = i + 1
        while j < len(lines):
            nxt = lines[j].strip()
            if not nxt or len(block) >= 4:
                break
            if _looks_math_expression(nxt) or _looks_display_equation_line(nxt) or re.fullmatch(r"[-_=~]{2,}", nxt):
                block.append(nxt)
                j += 1
                continue
            break

        if block and any(_looks_display_equation_line(entry) for entry in block):
            patched_block = _repair_fraction_line_breaks("\n".join(block)).strip()
            if patched_block:
                out.append("$$")
                out.append(patched_block)
                out.append("$$")
                i = j
                continue

        out.append(line)
        i += 1
    return "\n".join(out)


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
    fitz = _import_pymupdf()
    if fitz is None:
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


def detect_equation_regions(pdf_path: Path, sample_pages: int = 12) -> List[EquationRegion]:
    """Find likely equation blocks using layout geometry plus text heuristics."""
    fitz = _import_pymupdf()
    if fitz is None:
        return []

    regions: List[EquationRegion] = []
    with fitz.open(str(pdf_path)) as doc:
        for page_index, page in enumerate(doc):
            if page_index >= sample_pages:
                break
            blocks = page.get_text("blocks") or []
            for block in blocks:
                if len(block) < 5:
                    continue
                x0, y0, x1, y1, text = block[:5]
                text_value = str(text or "").strip()
                if not text_value:
                    continue
                lines = [line.strip() for line in text_value.splitlines() if line.strip()]
                if not lines:
                    continue
                if any(_looks_display_equation_line(line) for line in lines) or any(_looks_math_expression(line) for line in lines):
                    regions.append(
                        EquationRegion(
                            page_number=page_index + 1,
                            text=text_value,
                            x0=float(x0),
                            y0=float(y0),
                            x1=float(x1),
                            y1=float(y1),
                        )
                    )
    return regions


def _normalize_latex_candidate(text: str) -> str:
    candidate = clean_text_for_markdown(text).strip()
    if not candidate:
        return ""
    candidate = candidate.replace("[MISSING_PAGE_EMPTY:1]", "").replace("[MISSING_PAGE_FAIL:1]", "").strip()
    candidate = candidate.strip("$").strip()
    candidate = re.sub(r"^```(?:latex)?\s*", "", candidate)
    candidate = re.sub(r"\s*```$", "", candidate)
    candidate = re.sub(r"\n{2,}", "\n", candidate).strip()
    if not candidate:
        return ""
    if not any(token in candidate for token in ("\\", "=", "+", "-", "^", "_", r"\frac", r"\sum", r"\int")):
        return ""
    return candidate


def _run_nougat_on_pdf(pdf_path: Path) -> str:
    if not _command_available("nougat"):
        raise RuntimeError("nougat CLI is not available")

    with tempfile.TemporaryDirectory(prefix="nougat_pdf_") as tmpdir:
        env = _build_model_cache_env()
        cmd = [
            "nougat",
            "--out",
            tmpdir,
            "--batchsize",
            "1",
            "--full-precision",
            "--markdown",
            str(pdf_path),
        ]
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        if completed.returncode != 0:
            stderr = (completed.stderr or completed.stdout or "").strip()
            raise RuntimeError(f"Nougat conversion failed: {stderr}")

        candidates = sorted(Path(tmpdir).glob("*.mmd"))
        if not candidates:
            raise RuntimeError("Nougat conversion did not produce a markdown file.")
        return candidates[0].read_text(encoding="utf-8", errors="replace")


def _render_equation_crop_pdf(pdf_path: Path, region: EquationRegion, output_path: Path) -> None:
    fitz = _import_pymupdf()
    if fitz is None:
        raise RuntimeError("PyMuPDF is required for equation crop rendering.")

    with fitz.open(str(pdf_path)) as doc:
        page = doc[region.page_number - 1]
        page_rect = page.rect
        pad_x = max(8.0, (region.x1 - region.x0) * 0.08)
        pad_y = max(6.0, (region.y1 - region.y0) * 0.18)
        clip = fitz.Rect(
            max(page_rect.x0, region.x0 - pad_x),
            max(page_rect.y0, region.y0 - pad_y),
            min(page_rect.x1, region.x1 + pad_x),
            min(page_rect.y1, region.y1 + pad_y),
        )
        pix = page.get_pixmap(matrix=fitz.Matrix(3.0, 3.0), clip=clip, alpha=False)
        crop_doc = fitz.open()
        crop_page = crop_doc.new_page(width=float(pix.width), height=float(pix.height))
        crop_page.insert_image(
            fitz.Rect(0, 0, float(pix.width), float(pix.height)),
            pixmap=pix,
        )
        crop_doc.save(str(output_path))
        crop_doc.close()


def enrich_equation_regions_with_latex(
    pdf_path: Path,
    equation_regions: List[EquationRegion],
    max_regions: int = 16,
) -> List[EquationRegion]:
    if not equation_regions or not _command_available("nougat"):
        return equation_regions

    enriched: List[EquationRegion] = []
    with tempfile.TemporaryDirectory(prefix="equation_regions_") as tmpdir:
        for index, region in enumerate(equation_regions):
            updated = region
            width = max(0.0, region.x1 - region.x0)
            height = max(0.0, region.y1 - region.y0)
            if index < max_regions and width >= 24.0 and height >= 10.0:
                crop_pdf = Path(tmpdir) / f"equation_region_{index + 1}.pdf"
                try:
                    _render_equation_crop_pdf(pdf_path, region, crop_pdf)
                    latex = _normalize_latex_candidate(_run_nougat_on_pdf(crop_pdf))
                    if latex:
                        updated = EquationRegion(
                            page_number=region.page_number,
                            text=region.text,
                            x0=region.x0,
                            y0=region.y0,
                            x1=region.x1,
                            y1=region.y1,
                            latex=latex,
                        )
                except Exception:
                    updated = region
            enriched.append(updated)
    return enriched


def extract_marker_markdown(pdf_path: Path) -> str:
    """Use Marker as the primary structured markdown pipeline when available."""
    if not _command_available("marker_single"):
        raise RuntimeError("marker_single CLI is not available")

    with tempfile.TemporaryDirectory(prefix="marker_pdf_") as tmpdir:
        env = _build_model_cache_env()
        cmd = [
            "marker_single",
            str(pdf_path),
            "--output_dir",
            tmpdir,
            "--output_format",
            "markdown",
            "--disable_multiprocessing",
            "--disable_tqdm",
        ]
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        if completed.returncode != 0:
            stderr = (completed.stderr or completed.stdout or "").strip()
            raise RuntimeError(f"Marker conversion failed: {stderr}")

        candidates = sorted(Path(tmpdir).glob("*.md"))
        if not candidates:
            raise RuntimeError("Marker conversion did not produce a markdown file.")
        marker_md = candidates[0].read_text(encoding="utf-8", errors="replace")
        return clean_text_for_markdown(marker_md)


def patch_equations_into_markdown(markdown: str, equation_regions: List[EquationRegion]) -> str:
    """Patch likely equation text into display-math blocks inside markdown."""
    patched = markdown
    for region in equation_regions:
        raw = clean_text_for_markdown(region.text).strip()
        if not raw:
            continue
        display = _normalize_latex_candidate(region.latex or "") or _repair_fraction_line_breaks(raw).strip()
        if not display:
            continue
        replacement = f"$$\n{display}\n$$"
        tokens = [re.escape(token) for token in re.split(r"\s+", raw) if token]
        loose_pattern = r"\s+".join(tokens)
        patched, count = re.subn(loose_pattern, replacement, patched, count=1)
        if count == 0 and raw in patched:
            patched = patched.replace(raw, replacement, 1)
    return patched


def extract_born_digital_markdown(pdf_path: Path) -> str:
    """Prefer Marker, then pymupdf4llm markdown output, else pypdf fallback."""
    equation_regions = enrich_equation_regions_with_latex(pdf_path, detect_equation_regions(pdf_path))

    if _command_available("marker_single"):
        try:
            marker_md = extract_marker_markdown(pdf_path)
            return patch_equations_into_markdown(marker_md, equation_regions)
        except Exception:
            # Fall back to lighter extractors when Marker fails on a document.
            pass

    if _module_available("pymupdf4llm"):
        import pymupdf4llm  # type: ignore

        md = pymupdf4llm.to_markdown(str(pdf_path))
        if md and str(md).strip():
            cleaned = clean_text_for_markdown(str(md))
            return patch_equations_into_markdown(cleaned, equation_regions)

    reader = PdfReader(str(pdf_path))
    chunks: List[str] = []
    for i, page in enumerate(reader.pages):
        page_text = (page.extract_text() or "").strip()
        if not page_text:
            continue
        chunks.append(f"\n## Page {i + 1}\n\n{page_text}\n")
    if not chunks:
        raise ValueError("No extractable text found in PDF.")
    cleaned = clean_text_for_markdown("\n".join(chunks))
    return patch_equations_into_markdown(cleaned, equation_regions)


def extract_scanned_markdown_with_ocr(pdf_path: Path, ocr_lang: str = "eng") -> str:
    fitz = _import_pymupdf()
    if fitz is None:
        raise RuntimeError("PyMuPDF is required for OCR path: pip install pymupdf")
    if not _module_available("pytesseract") or not _module_available("PIL"):
        raise RuntimeError("OCR dependencies missing: pip install pytesseract pillow")

    import pytesseract  # type: ignore
    from PIL import Image  # type: ignore

    equation_regions = enrich_equation_regions_with_latex(pdf_path, detect_equation_regions(pdf_path))
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
    cleaned = clean_text_for_markdown("\n".join(chunks))
    return patch_equations_into_markdown(cleaned, equation_regions)


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
        if _command_available("marker_single"):
            try:
                return extract_marker_markdown(pdf_path)
            except Exception:
                pass
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
