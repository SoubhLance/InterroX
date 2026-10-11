from pathlib import Path
import sys
from io import BytesIO

import pymupdf
import pytest
from PIL import Image, ImageDraw, ImageFont

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.services.resume_extractor import (
    extract_text,
    InvalidPDFError,
    PasswordProtectedPDFError,
    OCRUnavailableError,
)


def _tesseract_available() -> bool:
    try:
        import pytesseract

        from app.config import settings

        cmd = (settings.TESSERACT_CMD or "").strip()
        if cmd:
            pytesseract.pytesseract.tesseract_cmd = cmd
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def _single_column_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    body = (
        "John Doe Python Engineer with experience in FastAPI, testing, "
        "and backend development. Skilled in Python, REST APIs, Docker, "
        "and SQL databases. Built interview tools and resume parsers. "
        "Open source contributor and team mentor. "
    )
    text = (body * 4).strip()
    assert len(text) > 400
    rect = pymupdf.Rect(50, 50, 545, 800)
    page.insert_textbox(rect, text, fontsize=11)
    return doc.tobytes()


def _two_column_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    y = 72.0
    for i in range(1, 6):
        page.insert_text((50, y), f"LEFT{i} lorem ipsum dolor {i}", fontsize=11)
        y += 20.0
    y = 72.0
    for ch in ["A", "B", "C", "D", "E"]:
        page.insert_text((320, y), f"RIGHT{ch} zebra qux data {ch}", fontsize=11)
        y += 20.0
    return doc.tobytes()


def _image_only_pdf(words=("PYTHON", "ENGINEER", "RESUME")) -> bytes:
    W, H = 1600, 1000
    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 72)
    except Exception:
        font = ImageFont.load_default()
    y = 200
    for w in words:
        draw.text((200, y), w, fill="black", font=font)
        y += 150
    buf = BytesIO()
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_image(page.rect, stream=png_bytes)
    return doc.tobytes()


def _garbage_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    garbage = ("#@$%&*?! " * 120).strip()
    assert len(garbage) > 300
    rect = pymupdf.Rect(50, 50, 545, 800)
    page.insert_textbox(rect, garbage, fontsize=11)
    return doc.tobytes()


def _six_page_pdf() -> bytes:
    doc = pymupdf.open()
    filler = "lorem ipsum dolor sit amet consectetur adipiscing elit "
    for i in range(6):
        page = doc.new_page()
        text = f"PAGE{i} marker content " + filler * 6
        rect = pymupdf.Rect(50, 50, 545, 800)
        page.insert_textbox(rect, text, fontsize=11)
    return doc.tobytes()


def _encrypted_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 100), "secret content here", fontsize=11)
    return doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="pw")


def test_single_column_text_layer():
    pdf = _single_column_pdf()
    result = extract_text(pdf)
    assert result["method"] == "text_layer"
    assert result["pages"] == 1
    assert "Python" in result["text"]
    assert "Engineer" in result["text"]
    assert len(result["text"]) > 300


def test_two_column_reading_order():
    pdf = _two_column_pdf()
    result = extract_text(pdf)
    text = result["text"]
    left_idx = [text.find(f"LEFT{i}") for i in range(1, 6)]
    right_idx = [text.find(f"RIGHT{c}") for c in ["A", "B", "C", "D", "E"]]
    assert all(i >= 0 for i in left_idx), text[:500]
    assert all(i >= 0 for i in right_idx), text[:500]
    assert max(left_idx) < min(right_idx)


def test_image_only_falls_back_to_ocr():
    if not _tesseract_available():
        pytest.skip("Tesseract binary unavailable")
    pdf = _image_only_pdf()
    result = extract_text(pdf)
    assert result["method"] == "ocr"
    assert "PYTHON" in result["text"].upper()
    assert "ENGINEER" in result["text"].upper()


def test_invalid_bytes_raise():
    with pytest.raises(InvalidPDFError):
        extract_text(b"this is not a pdf")


def test_encrypted_pdf_raises():
    pdf = _encrypted_pdf()
    with pytest.raises(PasswordProtectedPDFError):
        extract_text(pdf)


def test_six_page_pdf_processes_only_four():
    pdf = _six_page_pdf()
    result = extract_text(pdf)
    assert result["pages"] == 4


def test_garbage_text_layer_falls_back_to_ocr():
    if not _tesseract_available():
        pytest.skip("Tesseract binary unavailable")
    pdf = _garbage_pdf()
    result = extract_text(pdf)
    assert result["method"] == "ocr"
