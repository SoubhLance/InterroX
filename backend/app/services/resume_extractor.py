"""Resume text extraction from PDF bytes (Phase 2, step 2)."""

import re
from io import BytesIO

import pymupdf
from PIL import Image

import pytesseract

from app.config import settings


class InvalidPDFError(Exception):
    pass


class PasswordProtectedPDFError(Exception):
    pass


class OCRUnavailableError(Exception):
    pass


MAX_PAGES = 4
TEXT_LAYER_MIN_CHARS = 300
NON_ALNUM_MAX_RATIO = 0.30
MIN_AVG_WORD_LEN = 2.0
OCR_DPI = 250


def order_blocks(blocks, page_width):
    """Order text blocks in reading order.

    Two clear columns (left group and right group with a gap containing
    the page middle, each with >= 2 blocks) -> whole left column top to
    bottom, then right column. Otherwise sort by y then x.
    """
    text_blocks = [b for b in blocks if not (len(b) > 6 and b[6] != 0)]
    if len(text_blocks) < 4:
        return sorted(text_blocks, key=lambda b: (b[1], b[0]))
    mid = page_width / 2.0
    left = []
    right = []
    for b in text_blocks:
        cx = (b[0] + b[2]) / 2.0
        if cx < mid:
            left.append(b)
        else:
            right.append(b)
    if len(left) >= 2 and len(right) >= 2:
        max_x1_left = max(b[2] for b in left)
        min_x0_right = min(b[0] for b in right)
        if (
            max_x1_left < mid
            and min_x0_right > mid
            and (min_x0_right - max_x1_left) > 20
        ):
            left_sorted = sorted(left, key=lambda b: (b[1], b[0]))
            right_sorted = sorted(right, key=lambda b: (b[1], b[0]))
            return left_sorted + right_sorted
    return sorted(text_blocks, key=lambda b: (b[1], b[0]))


def _normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip(" \t") for line in text.split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _needs_ocr(text: str) -> bool:
    if len(text.strip()) < TEXT_LAYER_MIN_CHARS:
        return True
    non_space = [c for c in text if not c.isspace()]
    if not non_space:
        return True
    bad = sum(1 for c in non_space if not c.isalnum())
    if bad / len(non_space) > NON_ALNUM_MAX_RATIO:
        return True
    words = text.split()
    if not words:
        return True
    avg = sum(len(w) for w in words) / len(words)
    if avg < MIN_AVG_WORD_LEN:
        return True
    return False


def _configure_tesseract() -> None:
    cmd = (settings.TESSERACT_CMD or "").strip()
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd


def _ocr_pages(doc, page_count: int) -> str:
    _configure_tesseract()
    zoom = OCR_DPI / 72.0
    out: list[str] = []
    for i in range(page_count):
        page = doc[i]
        try:
            pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
            img = Image.open(BytesIO(pix.tobytes("png")))
            out.append(pytesseract.image_to_string(img) or "")
        except Exception as exc:
            raise OCRUnavailableError("Tesseract is unavailable or failed") from exc
    return "\n".join(out)


def extract_text(pdf_bytes: bytes) -> dict:
    """Extract text from PDF bytes.

    Returns {"text": str, "method": "text_layer" | "ocr", "pages": int}.
    """
    if not isinstance(pdf_bytes, (bytes, bytearray)) or len(pdf_bytes) == 0:
        raise InvalidPDFError("Not a valid PDF")
    try:
        doc = pymupdf.open(stream=bytes(pdf_bytes), filetype="pdf")
    except Exception as exc:
        raise InvalidPDFError("Not a valid PDF") from exc
    with doc:
        if getattr(doc, "needs_pass", False):
            raise PasswordProtectedPDFError("PDF is password protected")
        page_count = min(doc.page_count, MAX_PAGES)
        if page_count == 0:
            return {"text": "", "method": "text_layer", "pages": 0}
        page_texts: list[str] = []
        for i in range(page_count):
            page = doc[i]
            blocks = page.get_text("blocks")
            ordered = order_blocks(blocks, page.rect.width)
            texts = [b[4] for b in ordered if len(b) > 4 and b[4]]
            page_texts.append("\n".join(texts))
        combined = "\n".join(page_texts)
        if not _needs_ocr(combined):
            return {"text": _normalize(combined), "method": "text_layer", "pages": page_count}
        ocr_text = _ocr_pages(doc, page_count)
        return {"text": _normalize(ocr_text), "method": "ocr", "pages": page_count}
