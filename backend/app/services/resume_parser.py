"""Resume parsing from extracted text (Phase 2, step 3).

Pure functions only: no Redis, no network, no LLM.
Never logs resume text or emails.
"""

import re

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

_BULLET_RE = re.compile(r"^\s*(?:[•*–]\s*|-\s+)")

_MONTH = (
    r"(?:January|February|March|April|May|June|July|August|September|October|"
    r"November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?"
)
_MONTH_YEAR = _MONTH + r"\s+(?:19|20)\d{2}"
_RANGE_SEP = r"(?:–|—|-|to)"
_RANGE_END = (
    r"(?:" + _MONTH_YEAR + r"|(?:19|20)\d{2}|Present|present|Now|now|Current|current)"
)
_YEAR_RANGE_RE = re.compile(
    _MONTH_YEAR + r"\s*" + _RANGE_SEP + r"\s*" + _RANGE_END
    + r"|\b(?:19|20)\d{2}\s*" + _RANGE_SEP + r"\s*(?:(?:19|20)\d{2}|"
    r"Present|present|Now|now|Current|current)\b"
)
_SINGLE_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")

_DEGREE_LONG_RE = re.compile(
    r"\b(Bachelor|Master|Doctorate|Associate|MBA|"
    r"B\.?\s?Sc\.?|M\.?\s?Sc\.?|B\.?\s?Tech|M\.?\s?Tech)\b",
    re.IGNORECASE,
)
_DEGREE_SHORT_RE = re.compile(r"(?<![A-Za-z])(B\.E\.?|M\.S\.?|BE|MS|Ph\.?D\.?|BSc|MSc)(?![A-Za-z])")

_PHONE_CANDIDATE_RE = re.compile(r"\+?\d[\d\s().\-]{6,}\d")
_LINKEDIN_RE = re.compile(
    r"https?://[^\s]*linkedin\.com[^\s]*|(?<![\w.])"
    r"(?:www\.)?linkedin\.com/[^\s]*",
    re.IGNORECASE,
)
_GITHUB_RE = re.compile(
    r"https?://[^\s]*github\.com[^\s]*|(?<![\w.])"
    r"(?:www\.)?github\.com/[^\s]*",
    re.IGNORECASE,
)

_HEADING_MAP = {
    "summary": "summary",
    "objective": "summary",
    "profile": "summary",
    "education": "education",
    "experience": "experience",
    "work experience": "experience",
    "internships": "experience",
    "projects": "projects",
    "skills": "skills",
    "technical skills": "skills",
    "achievements": "other",
    "certifications": "other",
    "publications": "other",
    "research": "other",
    "awards": "other",
}

_TECH_DROP = {"github", "live", "demo"}

_TECH_TOKEN_DROP = {
    "github",
    "live",
    "demo",
    "published",
    "paper",
    "award",
    "winner",
    "journal",
}

_DROP_SEG_RE = re.compile(
    r"\b(publish\w*|papers?|awards?|winners?|github|live|demo)\b",
    re.IGNORECASE,
)

_CONTINUATION_RE = re.compile(r"^[\(\[a-z0-9\)\]\}]")

_DETAIL_PREFIXES = ("cgpa", "gpa", "coursework", "grade", "percentage", "relevant")


def extract_email(text: str) -> str | None:
    """Return the first email in raw text, lowercased, or None."""
    if not text:
        return None
    match = _EMAIL_RE.search(text)
    return match.group(0).lower() if match else None


def parse_with_llm(text: str) -> dict:
    """LLM-based parsing stub (later phase)."""
    raise NotImplementedError("LLM parsing comes in a later phase")


def _empty_result() -> dict:
    return {
        "contact": {"name": "", "email": ""},
        "summary": "",
        "education": [],
        "skills": [],
        "projects": [],
        "experience": [],
        "other": [],
    }


def _is_known_heading(line: str) -> bool:
    return line.strip().lower() in _HEADING_MAP


def _is_bullet_line(line: str) -> bool:
    return bool(_BULLET_RE.match(line))


def _strip_bullet(line: str) -> str:
    return _BULLET_RE.sub("", line, count=1).strip()


def _is_date_line(line: str) -> bool:
    s = line.strip()
    if not s or len(s) > 60 or "|" in s or _is_bullet_line(line):
        return False
    if _YEAR_RANGE_RE.search(s):
        return True
    return bool(re.search(_MONTH_YEAR, s))


def _is_continuation(line: str) -> bool:
    """A wrapped line continues the previous bullet/line.

    Starts with '(', a lowercase letter, a digit or a closing bracket,
    and does not start with a bullet char.
    """
    s = line.strip()
    if not s or _is_bullet_line(line):
        return False
    return bool(_CONTINUATION_RE.match(s))


def _ends_unbalanced(text: str) -> bool:
    """True when text has an unclosed quote or bracket.

    Covers curly quotes (“ ”), straight double quotes, and ( ) / [ ].
    """
    if text.count("“") > text.count("”"):
        return True
    if text.count('"') % 2 == 1:
        return True
    if text.count("(") > text.count(")"):
        return True
    if text.count("[") > text.count("]"):
        return True
    return False


def _bullets_text_unbalanced(raw_lines: list) -> bool:
    return _ends_unbalanced(
        " ".join(_strip_bullet(l) if _is_bullet_line(l) else l.strip() for l in raw_lines)
    )


def _is_location_line(line: str) -> bool:
    """Looks like 'City, State/Country': short, has a comma, no digits."""
    s = line.strip()
    return (
        bool(s)
        and "," in s
        and not any(c.isdigit() for c in s)
        and len(s) <= 60
        and "|" not in s
    )


def _is_detail_line(line: str) -> bool:
    """CGPA/GPA/Coursework/Grade/Percentage/Relevant lines."""
    low = line.strip().lower()
    if not low:
        return False
    if "cgpa:" in low:
        return True
    return low.startswith(_DETAIL_PREFIXES)


def _next_nonblank(lines: list, start: int):
    for k in range(start, len(lines)):
        if lines[k].strip():
            return lines[k]
    return None


def _is_unknown_heading(lines: list, i: int) -> bool:
    s = lines[i].strip()
    if not s or _is_bullet_line(lines[i]) or _is_known_heading(s):
        return False
    core = s[:-1].strip() if s.endswith(":") else s
    if not core or " " in core or len(core) > 30:
        return False
    if not re.fullmatch(r"[A-Za-z][A-Za-z&'\-.]*", core):
        return False
    if not core[0].isupper() or core.lower() in _HEADING_MAP:
        return False
    if i > 0 and lines[i - 1].strip():
        return False
    nxt = _next_nonblank(lines, i + 1)
    if nxt is None:
        return False
    ns = nxt.strip()
    if _is_bullet_line(nxt) or _is_date_line(nxt) or _is_known_heading(ns):
        return False
    if " " not in ns:
        return False
    seen_content = False
    for k in range(i + 1, len(lines)):
        t = lines[k].strip()
        if not t or _is_known_heading(t):
            break
        if _is_bullet_line(lines[k]) or _is_date_line(lines[k]):
            return False
        seen_content = True
    return seen_content


def _split_sections(text: str):
    sections = {
        "summary": [],
        "education": [],
        "skills": [],
        "projects": [],
        "experience": [],
        "other": [],
    }
    contact_lines: list = []
    current = None
    lines = text.split("\n")
    for i, raw in enumerate(lines):
        if _is_known_heading(raw):
            current = _HEADING_MAP[raw.strip().lower()]
            continue
        if current is not None and _is_unknown_heading(lines, i):
            current = "other"
            continue
        if current is None:
            contact_lines.append(raw)
        else:
            sections[current].append(raw)
    return contact_lines, sections


def _join_bullets(lines: list) -> list:
    bullets: list = []
    for raw in lines:
        s = raw.strip()
        if not s or _is_known_heading(raw):
            continue
        if _is_bullet_line(raw):
            bullets.append(_strip_bullet(raw))
        elif bullets and (_is_continuation(raw) or _ends_unbalanced(bullets[-1])):
            bullets[-1] = (bullets[-1] + " " + s).strip()
        else:
            bullets.append(s)
    return bullets


def _entry_starts_ahead(lines: list, i: int) -> bool:
    nxt = _next_nonblank(lines, i + 1)
    if nxt is None:
        return False
    return _is_bullet_line(nxt) or _is_date_line(nxt)


def _group_entries(lines: list) -> list:
    groups: list = []
    cur = None
    for i, raw in enumerate(lines):
        s = raw.strip()
        if not s or _is_known_heading(raw):
            continue
        if _is_bullet_line(raw):
            if cur is None:
                cur = {"header": [], "bullets": []}
            cur["bullets"].append(raw)
        elif _is_date_line(raw):
            if cur is None or cur["bullets"]:
                if cur is not None and cur["bullets"]:
                    groups.append(cur)
                cur = {"header": [raw], "bullets": []}
            else:
                cur["header"].append(raw)
        else:
            if cur is None:
                cur = {"header": [raw], "bullets": []}
            elif not cur["bullets"]:
                cur["header"].append(raw)
            elif _is_continuation(raw):
                cur["bullets"].append(raw)
            elif cur["bullets"] and _bullets_text_unbalanced(cur["bullets"]):
                # Previous bullet has an unclosed quote/bracket: a capitalised
                # wrapped line still continues it instead of starting an entry.
                cur["bullets"].append(raw)
            elif "|" in s or _entry_starts_ahead(lines, i):
                groups.append(cur)
                cur = {"header": [raw], "bullets": []}
            else:
                cur["bullets"].append(raw)
    if cur is not None:
        groups.append(cur)
    return groups


def _looks_like_url(token: str) -> bool:
    t = token.lower()
    return (
        "http" in t
        or "www." in t
        or "linkedin" in t
        or bool(re.search(r"\.(com|io|dev|ai|net|org)\b", t))
    )


def _parse_project_header(header_lines: list, skills: list):
    skills_lower = {s.lower() for s in skills}
    non_date = [h.strip() for h in header_lines if not _is_date_line(h)]
    header = " ".join(non_date).strip()
    if "|" in header:
        parts = [p.strip() for p in header.split("|")]
        name = parts[0]
        tech: list = []

        def _keep(token: str) -> None:
            t = token.strip()
            if not t or t.lower() in _TECH_TOKEN_DROP or _looks_like_url(t):
                return
            if t not in tech:
                tech.append(t)

        for part in parts[1:]:
            if not part or _looks_like_url(part):
                continue
            if "," in part:
                for tok in part.split(","):
                    _keep(tok)
            elif _DROP_SEG_RE.search(part):
                continue
            elif len(part.split()) == 1:
                if part.lower() in skills_lower:
                    _keep(part)
            else:
                _keep(part)
        return name, tech
    return header, []


def _parse_projects(lines: list, skills: list) -> list:
    out = []
    for group in _group_entries(lines):
        name, tech = _parse_project_header(group["header"], skills)
        bullets = _join_bullets(group["bullets"])
        description = " ".join(bullets).strip()
        out.append(
            {"name": name, "description": description, "bullets": bullets, "tech": tech}
        )
    return out


def _parse_experience(lines: list) -> list:
    out = []
    for group in _group_entries(lines):
        header = [h.strip() for h in group["header"] if h.strip()]
        date_idx = next(
            (k for k, h in enumerate(header) if _is_date_line(h)), None
        )
        period = header[date_idx] if date_idx is not None else ""
        before = header[:date_idx] if date_idx is not None else []
        after = header[date_idx + 1 :] if date_idx is not None else list(header)
        role = next((h for h in before if not _is_location_line(h)), "")
        if not role:
            role = next((h for h in after if not _is_location_line(h)), "")
        # Company is the line immediately after the date line. A location-like
        # line there is skipped only when another non-bullet header line
        # follows it (and that line is not location-like itself); otherwise
        # the line right after the date is the company, commas and all.
        company = ""
        if after:
            first, rest_after = after[0], after[1:]
            if (
                _is_location_line(first)
                and rest_after
                and not _is_location_line(rest_after[0])
            ):
                company = rest_after[0]
            else:
                company = first
        if not company and date_idx is None:
            nonloc = [h for h in header if not _is_location_line(h)]
            role = nonloc[0] if len(nonloc) > 0 else ""
            company = nonloc[1] if len(nonloc) > 1 else ""
        if not company and date_idx is not None:
            nonloc_before = [
                h for h in before if not _is_location_line(h) and h != role
            ]
            company = nonloc_before[0] if nonloc_before else ""
        bullets = _join_bullets(group["bullets"])
        out.append(
            {"company": company, "role": role, "period": period, "bullets": bullets}
        )
    return out


def _parse_education(lines: list) -> list:
    blocks: list = []
    cur: list = []
    for raw in lines + [""]:
        s = raw.strip()
        if not s or _is_known_heading(raw):
            if cur:
                blocks.append(cur)
                cur = []
            continue
        text = _strip_bullet(raw) if _is_bullet_line(raw) else s
        if _is_detail_line(text) and (cur or blocks):
            # CGPA/Coursework lines belong to the previous entry,
            # never start a new one.
            if cur:
                cur.append(text)
            else:
                blocks[-1].append(text)
            continue
        cur.append(text)
    if cur:
        blocks.append(cur)
    out = []
    for block in blocks:
        if not block:
            continue
        content = [line for line in block if not _is_detail_line(line)]
        details = [line for line in block if _is_detail_line(line)]
        if not content:
            content = list(block)
            details = []
        institution = content[0]
        degree = next(
            (
                line
                for line in content
                if _DEGREE_LONG_RE.search(line) or _DEGREE_SHORT_RE.search(line)
            ),
            "",
        )
        year = ""
        for line in content:
            m = _YEAR_RANGE_RE.search(line)
            if m:
                year = m.group(0)
                break
        if not year:
            for line in content:
                m = _SINGLE_YEAR_RE.search(line)
                if m:
                    year = m.group(0)
                    break
        out.append(
            {
                "institution": institution,
                "degree": degree,
                "year": year,
                "details": details,
            }
        )
    return out


def _parse_skills(lines: list) -> list:
    out: list = []
    for raw in lines:
        s = raw.strip()
        if not s or _is_known_heading(raw):
            continue
        if _is_bullet_line(raw):
            s = _strip_bullet(raw)
        if ":" in s:
            _, _, right = s.partition(":")
            parts = re.split(r"[,|]", right)
        else:
            parts = re.split(r"[,|]", s)
        for part in parts:
            t = part.strip()
            if not t or t in ("-", "•", "*", "–"):
                continue
            if _looks_like_url(t):
                continue
            if t not in out:
                out.append(t)
    return out


def _parse_summary(lines: list) -> str:
    parts = []
    for raw in lines:
        s = raw.strip()
        if not s or _is_known_heading(raw):
            continue
        if _is_bullet_line(raw):
            s = _strip_bullet(raw)
        parts.append(s)
    return " ".join(parts).strip()


def _parse_other(lines: list) -> list:
    # Bullets (e.g. achievements/leadership) are joined with their
    # wrapped continuation lines; plain lines stay separate items.
    return _join_bullets(lines)


def _digit_count(s: str) -> int:
    return sum(c.isdigit() for c in s)


def _scrub(s: str) -> str:
    s = _LINKEDIN_RE.sub("", s)
    s = _GITHUB_RE.sub("", s)
    s = _PHONE_CANDIDATE_RE.sub(
        lambda m: "" if _digit_count(m.group(0)) >= 10 else m.group(0), s
    )
    s = re.sub(r"[ \t]+", " ", s).strip()
    return s


def _scrub_list(items: list) -> list:
    return [s for s in (_scrub(x) for x in items) if s]


def parse_sections(text: str) -> dict:
    """Parse resume text into structured sections. Never raises on content."""
    result = _empty_result()
    if not text or not text.strip():
        return result
    _, sections = _split_sections(text)
    first_line = next((l.strip() for l in text.split("\n") if l.strip()), "")
    result["contact"] = {
        "name": _scrub(first_line),
        "email": extract_email(text) or "",
    }
    result["summary"] = _scrub(_parse_summary(sections["summary"]))
    result["education"] = [
        {
            "institution": _scrub(e["institution"]),
            "degree": _scrub(e["degree"]),
            "year": _scrub(e["year"]),
            "details": _scrub_list(e["details"]),
        }
        for e in _parse_education(sections["education"])
    ]
    skills = _scrub_list(_parse_skills(sections["skills"]))
    result["skills"] = skills
    result["projects"] = [
        {
            "name": _scrub(p["name"]),
            "description": _scrub(p["description"]),
            "bullets": _scrub_list(p["bullets"]),
            "tech": _scrub_list(p["tech"]),
        }
        for p in _parse_projects(sections["projects"], skills)
    ]
    result["experience"] = [
        {
            "company": _scrub(x["company"]),
            "role": _scrub(x["role"]),
            "period": _scrub(x["period"]),
            "bullets": _scrub_list(x["bullets"]),
        }
        for x in _parse_experience(sections["experience"])
    ]
    result["other"] = _scrub_list(_parse_other(sections["other"]))
    return result
