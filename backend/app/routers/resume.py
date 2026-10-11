from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.services.resume_extractor import (
    InvalidPDFError,
    OCRUnavailableError,
    PasswordProtectedPDFError,
    extract_text,
)
from app.services.resume_parser import extract_email, parse_sections
from app.services.resume_sanitizer import sanitize_resume, sanitize_text
from app.services.session_service import get_session, save_resume

router = APIRouter(tags=["resume"])

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MIN_TEXT_CHARS = 50


@router.post("/resume/upload")
def upload_resume(file: UploadFile = File(...), session_id: str = Form(...)):
    """Upload a resume PDF, parse it, and store it for the session."""
    if get_session(session_id) is None:
        raise HTTPException(
            status_code=404, detail="Session not found or expired"
        )
    raw = file.file.read(MAX_UPLOAD_BYTES + 1) or b""
    if len(raw) == 0:
        raise HTTPException(status_code=422, detail="Empty file")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large")
    if raw[:5] != b"%PDF-":
        raise HTTPException(
            status_code=415, detail="Only PDF files are accepted"
        )
    try:
        extracted = extract_text(raw)
    except InvalidPDFError:
        raise HTTPException(status_code=422, detail="Invalid PDF file")
    except PasswordProtectedPDFError:
        raise HTTPException(
            status_code=422, detail="This PDF is password protected"
        )
    except OCRUnavailableError:
        raise HTTPException(
            status_code=503, detail="OCR is temporarily unavailable"
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to process resume")
    text = extracted.get("text", "") or ""
    if len(text) < MIN_TEXT_CHARS:
        raise HTTPException(
            status_code=422, detail="Could not read any text from this PDF"
        )
    try:
        email = extract_email(text)
        cleaned = sanitize_text(text)
        parsed = parse_sections(cleaned.get("text", ""))
        contact = parsed.get("contact")
        if isinstance(contact, dict):
            contact.pop("email", None)
        sanitized = sanitize_resume(parsed)
        all_flags = list(cleaned.get("flags", [])) + list(
            sanitized.get("flags", [])
        )
        save_resume(
            session_id, sanitized.get("resume", {}), email, all_flags
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to process resume")
    resume = sanitized.get("resume", {}) or {}

    def _count(key: str) -> int:
        value = resume.get(key)
        return len(value) if isinstance(value, list) else 0

    return {
        "method": extracted.get("method"),
        "pages": extracted.get("pages"),
        "flags": all_flags,
        "email_found": email is not None,
        "email": email,
        "sections": {
            "education": _count("education"),
            "skills": _count("skills"),
            "projects": _count("projects"),
            "experience": _count("experience"),
        },
    }
