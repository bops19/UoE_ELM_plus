"""PDF -> Markdown conversion pipeline with optional external providers.

Workflow:
1) Detect whether a PDF is mostly born-digital or scanned.
2) Try full-document conversion with external providers:
   - Primary: Pix2Text
   - Optional fallback: Marker
3) Keep extracted markdown plus any provider-created assets/images.
4) Validate likely equation blocks.
5) For weak equation blocks, crop the source region and re-run formula OCR with
   Pix2Text or pix2tex when available.
6) Return final markdown with LaTeX math patches.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional


@dataclass
class EquationRegion:
    page_number: int
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    latex: Optional[str] = None


@dataclass
class ConversionBundle:
    markdown_text: str
    provider: str
    scanned: bool
    output_dir: Optional[Path] = None
    assets_dir: Optional[Path] = None


def _module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _command_available(name: str) -> bool:
    return shutil.which(name) is not None


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
    normalized = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    normalized = re.sub(r"[ \t]+\n", "\n", normalized)
    normalized = normalized.strip()
    return (normalized + "\n") if normalized else ""


def _looks_math_expression(text: str) -> bool:
    sample = (text or "").strip()
    if not sample:
        return False
    math_chars = sum(1 for ch in sample if ch in "0123456789+-=*/^()[]{}\\_.,")
    return (math_chars / max(1, len(sample))) >= 0.35


def _looks_display_equation_line(text: str) -> bool:
    sample = (text or "").strip()
    if not sample or len(sample) > 180 or sample.startswith("## "):
        return False
    equation_markers = ["=", "\\sum", "\\int", "\\frac", ">=", "<=", "->", "+", "-", "*", "/"]
    marker_hits = sum(1 for marker in equation_markers if marker in sample)
    alpha_chars = sum(1 for ch in sample if ch.isalpha())
    non_space_chars = sum(1 for ch in sample if not ch.isspace())
    symbol_chars = sum(1 for ch in sample if ch in "0123456789+-=*/^()[]{}\\_.,<>|")
    symbol_ratio = symbol_chars / max(1, non_space_chars)
    return marker_hits >= 2 or (marker_hits >= 1 and symbol_ratio >= 0.28 and alpha_chars <= max(16, len(sample) // 2))


def _normalize_formula_candidate(text: str) -> str:
    candidate = clean_text_for_markdown(text).strip()
    if not candidate:
        return ""
    candidate = candidate.strip("$").strip()
    candidate = re.sub(r"^```(?:latex)?\s*", "", candidate)
    candidate = re.sub(r"\s*```$", "", candidate)
    candidate = re.sub(r"\n{2,}", "\n", candidate).strip()
    if not candidate:
        return ""
    if not any(token in candidate for token in ("\\", "=", "+", "-", "^", "_", r"\frac", r"\sum", r"\int")):
        return ""
    if "\ufffd" in candidate or candidate.count("?") >= 3:
        return ""
    return candidate


def _equation_needs_repair(text: str) -> bool:
    sample = (text or "").strip()
    if not sample:
        return False
    bad_patterns = [
        "\ufffd",
        "???",
        "-----",
        "____",
        "| |",
    ]
    if any(pattern in sample for pattern in bad_patterns):
        return True
    if sample.count("{") != sample.count("}"):
        return True
    if sample.count("(") != sample.count(")"):
        return True
    return _looks_math_expression(sample) and "\\" not in sample and sample.count("=") + sample.count("/") + sample.count("^") >= 2


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


def detect_equation_regions(pdf_path: Path, sample_pages: int = 16) -> List[EquationRegion]:
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
                if any(_looks_display_equation_line(line) or _equation_needs_repair(line) for line in lines):
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


def _run_command(cmd: list[str], cwd: Optional[Path] = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=False,
    )


def _read_best_markdown_file(output_dir: Path) -> str:
    candidates = list(output_dir.rglob("output.md"))
    if not candidates:
        candidates = list(output_dir.rglob("*.md"))
    if not candidates:
        raise RuntimeError("No markdown file was generated by the converter.")
    candidates.sort(key=lambda path: (len(path.parts), path.name))
    return candidates[0].read_text(encoding="utf-8", errors="replace")


def _guess_assets_dir(output_dir: Path) -> Optional[Path]:
    image_dirs: list[Path] = []
    for candidate in output_dir.rglob("*"):
        if not candidate.is_dir():
            continue
        if any(child.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"} for child in candidate.iterdir()):
            image_dirs.append(candidate)
    if not image_dirs:
        return None
    image_dirs.sort(key=lambda path: (len(path.parts), path.name))
    return image_dirs[0]


def _run_pix2text_document(pdf_path: Path, output_dir: Path) -> ConversionBundle:
    output_dir.mkdir(parents=True, exist_ok=True)

    if _command_available("p2t"):
        completed = _run_command(
            [
                "p2t",
                "predict",
                "--file-type",
                "pdf",
                "-i",
                str(pdf_path),
                "-o",
                str(output_dir),
            ]
        )
        if completed.returncode != 0:
            stderr = (completed.stderr or completed.stdout or "").strip()
            raise RuntimeError(f"Pix2Text failed: {stderr}")
        markdown = clean_text_for_markdown(_read_best_markdown_file(output_dir))
        return ConversionBundle(
            markdown_text=markdown,
            provider="pix2text",
            scanned=False,
            output_dir=output_dir,
            assets_dir=_guess_assets_dir(output_dir),
        )

    if _module_available("pix2text"):
        from pix2text import Pix2Text  # type: ignore

        p2t = Pix2Text.from_config()
        doc = p2t.recognize_pdf(str(pdf_path))
        doc.to_markdown(str(output_dir))
        markdown = clean_text_for_markdown(_read_best_markdown_file(output_dir))
        return ConversionBundle(
            markdown_text=markdown,
            provider="pix2text",
            scanned=False,
            output_dir=output_dir,
            assets_dir=_guess_assets_dir(output_dir),
        )

    raise RuntimeError("Pix2Text is not installed.")


def _run_marker(pdf_path: Path, output_dir: Path) -> ConversionBundle:
    output_dir.mkdir(parents=True, exist_ok=True)

    if _command_available("marker_single"):
        completed = _run_command(
            [
                "marker_single",
                str(pdf_path),
                "--output_dir",
                str(output_dir),
                "--output_format",
                "markdown",
                "--disable_multiprocessing",
                "--disable_tqdm",
            ]
        )
        if completed.returncode != 0:
            stderr = (completed.stderr or completed.stdout or "").strip()
            raise RuntimeError(f"Marker failed: {stderr}")
        markdown = clean_text_for_markdown(_read_best_markdown_file(output_dir))
        return ConversionBundle(
            markdown_text=markdown,
            provider="marker",
            scanned=False,
            output_dir=output_dir,
            assets_dir=_guess_assets_dir(output_dir),
        )

    if _module_available("marker.converters.pdf"):
        from marker.converters.pdf import PdfConverter  # type: ignore
        from marker.models import create_model_dict  # type: ignore
        from marker.output import text_from_rendered  # type: ignore

        converter = PdfConverter(artifact_dict=create_model_dict())
        rendered = converter(str(pdf_path))
        text, _, images = text_from_rendered(rendered)
        assets_dir = None
        if images:
            assets_dir = output_dir / "images"
            assets_dir.mkdir(parents=True, exist_ok=True)
            for image_name, image in images.items():
                image_path = assets_dir / image_name
                image.save(image_path)
        return ConversionBundle(
            markdown_text=clean_text_for_markdown(text),
            provider="marker",
            scanned=False,
            output_dir=output_dir,
            assets_dir=assets_dir,
        )

    raise RuntimeError("Marker is not installed.")


def extract_born_digital_markdown(pdf_path: Path) -> str:
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


def _iter_provider_chain() -> Iterable[str]:
    configured = (os.environ.get("PDF_MARKDOWN_PROVIDERS") or "").strip()
    if configured:
        providers = [item.strip().lower() for item in configured.split(",") if item.strip()]
        if providers:
            return providers
    return ("pix2text", "marker")


def _convert_with_provider(provider: str, pdf_path: Path, output_dir: Path) -> ConversionBundle:
    if provider == "pix2text":
        return _run_pix2text_document(pdf_path, output_dir)
    if provider == "marker":
        return _run_marker(pdf_path, output_dir)
    raise RuntimeError(f"Unknown PDF provider: {provider}")


def _run_formula_ocr_cli(image_path: Path) -> str:
    if _command_available("p2t"):
        completed = _run_command(
            [
                "p2t",
                "predict",
                "--file-type",
                "formula",
                "-i",
                str(image_path),
            ]
        )
        if completed.returncode == 0:
            lines = [line.strip() for line in (completed.stdout or "").splitlines() if line.strip()]
            if lines:
                return _normalize_formula_candidate(lines[-1])
    return ""


def _run_formula_ocr(image_path: Path) -> str:
    if _module_available("pix2text"):
        try:
            from pix2text import Pix2Text  # type: ignore

            p2t = Pix2Text.from_config()
            return _normalize_formula_candidate(p2t.recognize_formula(str(image_path)))
        except Exception:
            pass

    if _module_available("pix2tex.cli"):
        try:
            from PIL import Image  # type: ignore
            from pix2tex.cli import LatexOCR  # type: ignore

            model = LatexOCR()
            with Image.open(image_path) as image:
                return _normalize_formula_candidate(model(image))
        except Exception:
            pass

    return _run_formula_ocr_cli(image_path)


def _render_equation_crop(pdf_path: Path, region: EquationRegion, output_path: Path) -> None:
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
        pix.save(str(output_path))


def _repair_equations(markdown: str, pdf_path: Path, output_dir: Path, max_regions: int = 16) -> str:
    regions = detect_equation_regions(pdf_path)
    if not regions:
        return markdown

    equation_dir = output_dir / "equation_crops"
    equation_dir.mkdir(parents=True, exist_ok=True)

    patched = markdown
    for index, region in enumerate(regions[:max_regions]):
        if not _equation_needs_repair(region.text):
            continue
        crop_path = equation_dir / f"equation_{index + 1}.png"
        try:
            _render_equation_crop(pdf_path, region, crop_path)
            latex = _run_formula_ocr(crop_path)
        except Exception:
            latex = ""
        if not latex:
            continue

        raw = clean_text_for_markdown(region.text).strip()
        if not raw:
            continue
        replacement = f"$$\n{latex}\n$$"
        tokens = [re.escape(token) for token in re.split(r"\s+", raw) if token]
        if not tokens:
            continue
        pattern = r"\s+".join(tokens)
        patched, count = re.subn(pattern, replacement, patched, count=1)
        if count == 0 and raw in patched:
            patched = patched.replace(raw, replacement, 1)
    return clean_text_for_markdown(patched)


def convert_pdf_to_markdown_bundle(
    pdf_path: Path,
    output_dir: Optional[Path] = None,
    force_mode: str = "auto",
    ocr_lang: str = "eng",
) -> ConversionBundle:
    mode = (force_mode or "auto").strip().lower()
    if mode not in {"auto", "digital", "scanned"}:
        raise ValueError("force_mode must be one of: auto, digital, scanned")
    if not pdf_path.exists() or not pdf_path.is_file():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    work_dir = output_dir or pdf_path.parent / f"{pdf_path.stem}_artifacts"
    work_dir.mkdir(parents=True, exist_ok=True)
    scanned = detect_scanned_pdf(pdf_path) if mode == "auto" else (mode == "scanned")

    errors: list[str] = []
    if mode == "auto":
        for provider in _iter_provider_chain():
            provider_dir = work_dir / provider
            try:
                bundle = _convert_with_provider(provider, pdf_path, provider_dir)
                bundle.scanned = scanned
                bundle.markdown_text = _repair_equations(bundle.markdown_text, pdf_path, work_dir)
                return bundle
            except Exception as exc:
                errors.append(f"{provider}: {exc}")
    elif mode == "digital":
        bundle = ConversionBundle(
            markdown_text=extract_born_digital_markdown(pdf_path),
            provider="local-digital",
            scanned=False,
            output_dir=work_dir,
        )
        bundle.markdown_text = _repair_equations(bundle.markdown_text, pdf_path, work_dir)
        return bundle
    else:
        bundle = ConversionBundle(
            markdown_text=extract_scanned_markdown_with_ocr(pdf_path, ocr_lang=ocr_lang),
            provider="local-ocr",
            scanned=True,
            output_dir=work_dir,
        )
        bundle.markdown_text = _repair_equations(bundle.markdown_text, pdf_path, work_dir)
        return bundle

    if scanned:
        markdown_text = extract_scanned_markdown_with_ocr(pdf_path, ocr_lang=ocr_lang)
        provider = "local-ocr"
    else:
        markdown_text = extract_born_digital_markdown(pdf_path)
        provider = "local-digital"

    bundle = ConversionBundle(
        markdown_text=markdown_text,
        provider=provider if not errors else f"{provider} (fallback after {', '.join(errors)})",
        scanned=scanned,
        output_dir=work_dir,
    )
    bundle.markdown_text = _repair_equations(bundle.markdown_text, pdf_path, work_dir)
    return bundle


def convert_pdf_to_markdown(
    pdf_path: Path,
    force_mode: str = "auto",
    ocr_lang: str = "eng",
) -> str:
    return convert_pdf_to_markdown_bundle(
        pdf_path=pdf_path,
        output_dir=None,
        force_mode=force_mode,
        ocr_lang=ocr_lang,
    ).markdown_text
