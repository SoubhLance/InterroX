"""Parse a resume PDF into structured JSON. No Redis needed."""

import argparse
import copy
import json
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


def mask_email(email: str) -> str:
    if not email or "@" not in email:
        return email
    local, _, domain = email.partition("@")
    return (local[:1] + "***@" + domain) if local else "***@" + domain


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse a resume PDF to JSON")
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
    parsed = parse_sections(result["text"])
    masked = copy.deepcopy(parsed)
    masked["contact"]["email"] = mask_email(masked["contact"]["email"])
    print(json.dumps(masked, indent=2))
    print(f"extraction: method={result['method']} pages={result['pages']}")
    print(f"summary_chars: {len(parsed['summary'])}")
    print(f"education: {len(parsed['education'])}")
    print(f"skills: {len(parsed['skills'])}")
    print(f"projects: {len(parsed['projects'])}")
    print(f"experience: {len(parsed['experience'])}")
    print(f"other: {len(parsed['other'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
