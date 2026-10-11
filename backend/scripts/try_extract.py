"""CLI to try resume extraction on a PDF file. No Redis needed."""

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


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract text from a resume PDF")
    parser.add_argument("pdf_path", help="Path to a PDF file")
    args = parser.parse_args()
    data = Path(args.pdf_path).read_bytes()
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
    print(f"method: {result['method']}")
    print(f"pages: {result['pages']}")
    print(f"chars: {len(result['text'])}")
    print(result["text"][:500])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
