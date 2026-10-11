"""Print sanitizer flags and counts for a resume PDF. No resume text. No Redis."""

import argparse
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.services.resume_extractor import (
    extract_text,
    InvalidPDFError,
    PasswordProtectedPDFError,
    OCRUnavailableError,
)
from app.services.resume_parser import parse_sections
from app.services.resume_sanitizer import sanitize_text, sanitize_resume


def main() -> int:
    parser = argparse.ArgumentParser(description="Sanitize a resume PDF")
    parser.add_argument("pdf_path", help="Path to a PDF file")
    args = parser.parse_args()
    try:
        data = Path(args.pdf_path).read_bytes()
    except OSError as exc:
        print(f"Cannot read file: {exc}")
        return 1
    try:
        result = extract_text(data)
    except InvalidPDFError as exc:
        print(f"Invalid PDF: {exc}")
        return 1
    except PasswordProtectedPDFError as exc:
        print(f"Password protected PDF: {exc}")
        return 1
    except OCRUnavailableError as exc:
        print(f"OCR unavailable: {exc}")
        return 1
    cleaned = sanitize_text(result["text"])
    parsed = parse_sections(cleaned["text"])
    final = sanitize_resume(parsed)
    resume = final["resume"]
    print(f"extraction: method={result['method']} pages={result['pages']}")
    print(f"text_flags: {cleaned['flags']}")
    print(f"resume_flags: {final['flags']}")
    print(f"summary_chars: {len(resume.get('summary', ''))}")
    print(f"education: {len(resume.get('education', []))}")
    print(f"skills: {len(resume.get('skills', []))}")
    print(f"projects: {len(resume.get('projects', []))}")
    print(f"experience: {len(resume.get('experience', []))}")
    print(f"other: {len(resume.get('other', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
