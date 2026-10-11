"""Resume sanitizer: prompt-injection cleaning and size caps.

Pure functions only: no Redis, no network, no LLM.
Never logs resume text. Flags carry category names only, never matched text.
"""

import copy
import re

MAX_LINE_CHARS = 800
MAX_SUMMARY_CHARS = 1000
MAX_BULLET_CHARS = 400
MAX_DESC_CHARS = 400
MAX_SKILLS = 60
MAX_SKILL_CHARS = 60
MAX_PROJECTS = 10
MAX_EXPERIENCE = 10
MAX_EDUCATION = 5
MAX_OTHER = 20
MAX_OTHER_CHARS = 400
MAX_TECH = 20

# Invisible / zero-width characters, built from code points so no
# literal invisible character ever appears in this source file.
_INVISIBLE_CHARS = "".join(
    [chr(0x200B), chr(0x200C), chr(0x200D), chr(0x2060), chr(0xFEFF)]
)
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")

_SEP = r"[^A-Za-z0-9]+"

_PATTERNS = [
    (
        "injection:ignore_instructions",
        r"\bignore" + _SEP + r"(?:all" + _SEP + r")?(?:previous|prior|above)"
        + _SEP + r"instructions\b",
    ),
    (
        "injection:disregard",
        r"\bdisregard" + _SEP + r"(?:the" + _SEP + r")?(?:previous|above|system)\b",
    ),
    ("injection:you_are_now", r"\byou" + _SEP + r"are" + _SEP + r"now\b"),
    ("injection:system_prompt", r"\bsystem" + _SEP + r"prompt\b"),
    (
        "injection:score_boost",
        r"\bgive" + _SEP + r"(?:me" + _SEP + r")?(?:full|maximum|top|perfect)"
        + _SEP + r"(?:marks|score)\b",
    ),
    (
        "injection:act_as",
        r"(?:^|[.!?;:\n\"'(\[]\s*)act" + _SEP + r"as\b|\byou" + _SEP + r"act"
        + _SEP + r"as\b",
    ),
    (
        "injection:pretend",
        r"\bpretend" + _SEP + r"(?:to" + _SEP + r"be\b|you" + _SEP + r"are\b)",
    ),
    ("injection:new_instructions", r"\bnew" + _SEP + r"instructions\b"),
    ("injection:jailbreak", r"\bjailbreak\w*\b|\bjail\s+break\w*\b"),
    ("injection:developer_mode", r"\bdeveloper" + _SEP + r"mode\b"),
    (
        "injection:do_anything_now",
        r"\bdo" + _SEP + r"anything" + _SEP + r"now\b",
    ),
    ("injection:override", r"\boverride\b"),
]

_COMPILED = [(cat, re.compile(rx, re.IGNORECASE)) for cat, rx in _PATTERNS]


def find_injection_categories(line: str) -> list:
    """Return flag categories matching a single line (no matched text)."""
    if not isinstance(line, str) or not line:
        return []
    return [cat for cat, rx in _COMPILED if rx.search(line)]


def _remove_invisible(text: str):
    had = any(c in text for c in _INVISIBLE_CHARS) or bool(
        _CONTROL_RE.search(text)
    )
    if had:
        text = "".join(c for c in text if c not in _INVISIBLE_CHARS)
        text = _CONTROL_RE.sub("", text)
    return text, had


def _add_flag(flags: list, flag: str) -> None:
    if flag not in flags:
        flags.append(flag)


def sanitize_text(text: str) -> dict:
    """Clean raw extracted text before parsing.

    Returns {"text": cleaned_text, "flags": [str]}.
    """
    if not isinstance(text, str):
        return {"text": "", "flags": []}
    flags: list = []
    cleaned, had_invisible = _remove_invisible(text)
    if had_invisible:
        flags.append("invisible_chars")
    kept: list = []
    for line in cleaned.split("\n"):
        cats = find_injection_categories(line)
        if cats:
            for cat in cats:
                _add_flag(flags, cat)
            continue
        kept.append(line)
    out_lines: list = []
    truncated = False
    for line in kept:
        if len(line) > MAX_LINE_CHARS:
            out_lines.append(line[:MAX_LINE_CHARS])
            truncated = True
        else:
            out_lines.append(line)
    if truncated:
        flags.append("long_line")
    return {"text": "\n".join(out_lines), "flags": flags}


def _check_scalar(value, flags: list):
    """Return (cleaned, dropped). Injected scalars become ""."""
    if not isinstance(value, str):
        return value, False
    cats = find_injection_categories(value)
    if cats:
        for cat in cats:
            _add_flag(flags, cat)
        return "", True
    return value, False


def _cap_str(value, limit: int, flags: list, field: str):
    if isinstance(value, str) and len(value) > limit:
        _add_flag(flags, f"capped:{field}")
        return value[:limit]
    return value


def _cap_count(items: list, limit: int, flags: list, field: str):
    if isinstance(items, list) and len(items) > limit:
        _add_flag(flags, f"capped:{field}")
        return items[:limit]
    return items


def _clean_str_list(items, flags: list, field: str, item_limit=None):
    """Drop injected items, cap item lengths. Returns a new list."""
    out = []
    for item in items or []:
        if not isinstance(item, str):
            out.append(item)
            continue
        cats = find_injection_categories(item)
        if cats:
            for cat in cats:
                _add_flag(flags, cat)
            continue
        if item_limit is not None and len(item) > item_limit:
            _add_flag(flags, f"capped:{field}")
            item = item[:item_limit]
        out.append(item)
    return out


def _clean_project(proj: dict, flags: list) -> dict:
    proj = dict(proj)
    if isinstance(proj.get("name"), str):
        proj["name"], _ = _check_scalar(proj["name"], flags)
    if isinstance(proj.get("description"), str):
        desc, dropped = _check_scalar(proj["description"], flags)
        proj["description"] = desc if dropped else _cap_str(
            desc, MAX_DESC_CHARS, flags, "description"
        )
    if isinstance(proj.get("bullets"), list):
        proj["bullets"] = _clean_str_list(
            proj["bullets"], flags, "bullets", MAX_BULLET_CHARS
        )
    if isinstance(proj.get("tech"), list):
        proj["tech"] = _cap_count(
            _clean_str_list(proj["tech"], flags, "tech"), MAX_TECH, flags, "tech"
        )
    return proj


def _clean_experience(entry: dict, flags: list) -> dict:
    entry = dict(entry)
    for key in ("company", "role", "period"):
        if isinstance(entry.get(key), str):
            entry[key], _ = _check_scalar(entry[key], flags)
    if isinstance(entry.get("bullets"), list):
        entry["bullets"] = _clean_str_list(
            entry["bullets"], flags, "bullets", MAX_BULLET_CHARS
        )
    return entry


def _clean_education(entry: dict, flags: list) -> dict:
    entry = dict(entry)
    for key in ("institution", "degree", "year"):
        if isinstance(entry.get(key), str):
            entry[key], _ = _check_scalar(entry[key], flags)
    if isinstance(entry.get("details"), list):
        entry["details"] = _clean_str_list(
            entry["details"], flags, "education", MAX_BULLET_CHARS
        )
    return entry


def _deep_clean(value, flags: list):
    """Injection check for unknown-shape fields. Returns cleaned value."""
    if isinstance(value, str):
        cats = find_injection_categories(value)
        if cats:
            for cat in cats:
                _add_flag(flags, cat)
            return ""
        return value
    if isinstance(value, list):
        out = []
        for item in value:
            if isinstance(item, str):
                cats = find_injection_categories(item)
                if cats:
                    for cat in cats:
                        _add_flag(flags, cat)
                    continue
                out.append(item)
            elif isinstance(item, (dict, list)):
                out.append(_deep_clean(item, flags))
            else:
                out.append(item)
        return out
    if isinstance(value, dict):
        return {k: _deep_clean(v, flags) for k, v in value.items()}
    return value


_KNOWN_KEYS = {
    "contact",
    "summary",
    "education",
    "skills",
    "projects",
    "experience",
    "other",
}


def sanitize_resume(resume: dict) -> dict:
    """Enforce size limits on a parsed resume dict. Never mutates input.

    Returns {"resume": capped_dict, "flags": [str]}.
    """
    flags: list = []
    if not isinstance(resume, dict):
        return {"resume": {}, "flags": []}
    out = copy.deepcopy(resume)
    if isinstance(out.get("contact"), dict):
        for key in ("name", "email"):
            if isinstance(out["contact"].get(key), str):
                out["contact"][key], _ = _check_scalar(
                    out["contact"][key], flags
                )
    if isinstance(out.get("summary"), str):
        summary, dropped = _check_scalar(out["summary"], flags)
        out["summary"] = (
            summary if dropped else _cap_str(summary, MAX_SUMMARY_CHARS, flags, "summary")
        )
    if isinstance(out.get("education"), list):
        out["education"] = _cap_count(
            [_clean_education(e, flags) if isinstance(e, dict) else e
             for e in out["education"]],
            MAX_EDUCATION,
            flags,
            "education",
        )
    if isinstance(out.get("skills"), list):
        out["skills"] = _cap_count(
            _clean_str_list(out["skills"], flags, "skills", MAX_SKILL_CHARS),
            MAX_SKILLS,
            flags,
            "skills",
        )
    if isinstance(out.get("projects"), list):
        out["projects"] = _cap_count(
            [_clean_project(p, flags) if isinstance(p, dict) else p
             for p in out["projects"]],
            MAX_PROJECTS,
            flags,
            "projects",
        )
    if isinstance(out.get("experience"), list):
        out["experience"] = _cap_count(
            [_clean_experience(e, flags) if isinstance(e, dict) else e
             for e in out["experience"]],
            MAX_EXPERIENCE,
            flags,
            "experience",
        )
    if isinstance(out.get("other"), list):
        out["other"] = _cap_count(
            _clean_str_list(out["other"], flags, "other", MAX_OTHER_CHARS),
            MAX_OTHER,
            flags,
            "other",
        )
    for key in list(out.keys()):
        if key not in _KNOWN_KEYS:
            out[key] = _deep_clean(out[key], flags)
    return {"resume": out, "flags": flags}
