from __future__ import annotations

import base64
import io
import logging
import os
import re
import shutil
import subprocess
import tempfile
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

from app.schemas import ContentPart, ImageUrlPart, PdfPart, TextPart

logger = logging.getLogger(__name__)
PDF_OCR_MAX_PAGES = int(os.getenv("PDF_OCR_MAX_PAGES", "80"))
MIN_PAGE_TEXT_CHARS = int(os.getenv("PDF_MIN_PAGE_TEXT_CHARS", "40"))


@dataclass(frozen=True)
class PdfExtraction:
    text: str
    page_count: int
    ocr_used: bool
    warnings: list[str]


def clean_pdf_text(text: str) -> str:
    """Clean common PDF extraction artifacts while preserving legal headings."""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\u00ad", "").replace("\u00a0", " ").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"(?<=\w)-\n(?=\w)", "", text)
    raw_lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    meaningful = [line.casefold() for line in raw_lines if line and len(line) <= 140]
    repeated = {line for line, count in Counter(meaningful).items() if count >= 3}
    cleaned: list[str] = []
    for line in raw_lines:
        if not line:
            if cleaned and cleaned[-1] != "":
                cleaned.append("")
            continue
        if re.fullmatch(r"[-–—]?\s*\d+\s*[-–—]?", line):
            continue
        if re.match(r"^(?:halaman|page)\s+\d+\b", line, re.IGNORECASE):
            continue
        if line.casefold() in repeated and len(line) < 140:
            continue
        cleaned.append(line)
    while cleaned and cleaned[-1] == "":
        cleaned.pop()
    return "\n".join(cleaned).strip()


def _extract_with_pdftotext(raw: bytes) -> str:
    executable = shutil.which("pdftotext")
    if not executable:
        return ""
    try:
        result = subprocess.run(
            [executable, "-layout", "-", "-"],
            input=raw,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=45,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("pdftotext fallback failed: %s", exc)
        return ""
    if result.returncode != 0:
        logger.warning(
            "pdftotext fallback returned %s: %s",
            result.returncode,
            result.stderr.decode("utf-8", errors="replace")[:500],
        )
        return ""
    return result.stdout.decode("utf-8", errors="replace")


def _decode_pdf_data(data: str) -> bytes:
    if data.startswith("data:") and "," in data:
        data = data.split(",", 1)[1]
    return base64.b64decode(data)


def _page_marker(page_number: int) -> str:
    return f"[HALAMAN {page_number}]"


def _format_pages(pages: list[str]) -> str:
    blocks = []
    for page_number, page in enumerate(pages, start=1):
        cleaned = clean_pdf_text(page)
        if cleaned:
            blocks.append(f"{_page_marker(page_number)}\n{cleaned}")
    return "\n\n".join(blocks).strip()


def _ocr_pages(raw: bytes, wanted_pages: set[int]) -> tuple[dict[int, str], str | None]:
    pdftoppm = shutil.which("pdftoppm")
    tesseract = shutil.which("tesseract")
    if not pdftoppm or not tesseract:
        return {}, "OCR tidak tersedia di server; instal pdftoppm dan Tesseract untuk PDF hasil scan."
    if not wanted_pages:
        return {}, None

    limited_pages = set(sorted(wanted_pages)[:PDF_OCR_MAX_PAGES])
    warning = None
    if len(wanted_pages) > len(limited_pages):
        warning = f"OCR dibatasi hingga {PDF_OCR_MAX_PAGES} halaman pertama yang membutuhkan OCR."

    with tempfile.TemporaryDirectory(prefix="sinergi-ocr-") as tmp:
        tmp_dir = Path(tmp)
        pdf_path = tmp_dir / "source.pdf"
        prefix = tmp_dir / "page"
        pdf_path.write_bytes(raw)
        try:
            rendered = subprocess.run(
                [pdftoppm, "-jpeg", "-r", "200", str(pdf_path), str(prefix)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=240,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {}, f"Rendering PDF untuk OCR gagal: {exc}"
        if rendered.returncode != 0:
            detail = rendered.stderr.decode("utf-8", errors="replace")[:300]
            return {}, f"Rendering PDF untuk OCR gagal: {detail or rendered.returncode}"

        images = sorted(
            tmp_dir.glob("page-*.jpg"),
            key=lambda path: int(path.stem.rsplit("-", 1)[-1]),
        )
        output: dict[int, str] = {}
        for image in images:
            page_number = int(image.stem.rsplit("-", 1)[-1])
            if page_number not in limited_pages:
                continue
            try:
                result = subprocess.run(
                    [tesseract, str(image), "stdout", "-l", "ind+eng", "--psm", "6"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=90,
                    check=False,
                )
                if result.returncode != 0:
                    result = subprocess.run(
                        [tesseract, str(image), "stdout", "-l", "eng", "--psm", "6"],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        timeout=90,
                        check=False,
                    )
            except (OSError, subprocess.TimeoutExpired):
                continue
            text = result.stdout.decode("utf-8", errors="replace")
            if text.strip():
                output[page_number] = text
        return output, warning


def extract_pdf_document(data: str) -> PdfExtraction:
    warnings: list[str] = []
    try:
        raw = _decode_pdf_data(data)
    except Exception as exc:
        logger.warning("PDF base64 decoding failed: %s", exc)
        return PdfExtraction("", 0, False, ["Data PDF tidak valid."])

    pages: list[str] = []
    try:
        reader = PdfReader(io.BytesIO(raw), strict=False)
        if reader.is_encrypted:
            reader.decrypt("")
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:
        logger.warning("pypdf extraction failed; trying pdftotext: %s", exc)

    if not any(page.strip() for page in pages):
        fallback = _extract_with_pdftotext(raw)
        if fallback.strip():
            pages = fallback.split("\f")

    weak_pages = {
        index
        for index, page in enumerate(pages, start=1)
        if len(clean_pdf_text(page)) < MIN_PAGE_TEXT_CHARS
    }
    ocr_used = False
    if weak_pages or not pages:
        wanted = weak_pages or {1}
        ocr_text, ocr_warning = _ocr_pages(raw, wanted)
        if ocr_warning:
            warnings.append(ocr_warning)
        if ocr_text:
            if not pages:
                pages = [""] * max(ocr_text)
            for page_number, text in ocr_text.items():
                while len(pages) < page_number:
                    pages.append("")
                if len(clean_pdf_text(text)) > len(clean_pdf_text(pages[page_number - 1])):
                    pages[page_number - 1] = text
                    ocr_used = True

    unreadable = [
        index
        for index, page in enumerate(pages, start=1)
        if len(clean_pdf_text(page)) < MIN_PAGE_TEXT_CHARS
    ]
    if unreadable:
        preview = ", ".join(str(page) for page in unreadable[:10])
        suffix = "…" if len(unreadable) > 10 else ""
        warnings.append(f"Teks halaman {preview}{suffix} mungkin tidak terbaca lengkap.")

    return PdfExtraction(
        text=_format_pages(pages),
        page_count=len(pages),
        ocr_used=ocr_used,
        warnings=warnings,
    )


def extract_pdf_text(data: str, max_chars: int | None = 32_000, collapse: bool = True) -> str:
    extracted = extract_pdf_document(data)
    result = " ".join(extracted.text.split()) if collapse else extracted.text
    return result if max_chars is None else result[:max_chars]


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    count = 0
    for word in re.split(r"\s+", text.strip()):
        if word:
            count += max(1, -(-len(re.sub(r"[^\w]", "", word)) // 4))
            count += len(re.findall(r"[^\w\s]+", word))
    return max(1, count)


def expand_content(content: str | list[ContentPart] | list[dict]) -> str | list[dict]:
    if isinstance(content, str):
        return content
    parts: list[dict] = []
    for part in content:
        if isinstance(part, TextPart):
            parts.append({"type": "text", "text": part.text})
        elif isinstance(part, ImageUrlPart):
            parts.append({"type": "image_url", "image_url": part.image_url})
        elif isinstance(part, PdfPart):
            text = extract_pdf_text(part.data, max_chars=None, collapse=False)
            parts.append({"type": "text", "text": f"Konteks:\n{text}" if text else f"[PDF tidak terbaca: {part.name}]"})
        elif isinstance(part, dict):
            if part.get("type") == "pdf":
                text = extract_pdf_text(part.get("data", ""), max_chars=None, collapse=False)
                parts.append({"type": "text", "text": f"Konteks:\n{text}" if text else f"[PDF tidak terbaca: {part.get('name', 'dokumen.pdf')}]"})
            elif part.get("type") in {"text", "image_url"}:
                parts.append({"type": part["type"], part["type"]: part.get(part["type"], "")})
    return parts[0]["text"] if len(parts) == 1 and parts[0]["type"] == "text" else parts


def flatten_content(content: str | list[ContentPart]) -> str:
    expanded = expand_content(content)
    if isinstance(expanded, str):
        return expanded
    return "\n".join(part.get("text", "") for part in expanded if part.get("type") == "text")
