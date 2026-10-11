import copy
import json
import secrets
import time
from typing import Optional, Dict, Any, List
from app.redis_client import redis_client
from app.config import settings


def key_session(sid: str) -> str:
    return f"session:{sid}"


def key_resume(sid: str) -> str:
    return f"resume:{sid}"


def key_qpool(sid: str) -> str:
    return f"qpool:{sid}"


def key_answers(sid: str) -> str:
    return f"answers:{sid}"


def key_rl_email(ip: str) -> str:
    return f"rl:email:{ip}"


NUMERIC_FIELDS = {"duration_min", "time_left_sec", "followup_count", "emailed", "created_at"}


def create_session(mode: str, duration_min: int) -> str:
    """Creates a new interview session in Redis with configured TTL.

    Session key: session:{sid}
    Fields: mode, duration_min, segment="intro", time_left_sec, followup_count=0, created_at
    Note: 'emailed' is omitted initially so mark_emailed can use HSETNX atomically.
    """
    sid = secrets.token_urlsafe(16)
    key = key_session(sid)
    mapping = {
        "mode": mode,
        "duration_min": duration_min,
        "segment": "intro",
        "time_left_sec": duration_min * 60,
        "followup_count": 0,
        "created_at": int(time.time()),
    }
    redis_client.hset(key, mapping=mapping)
    redis_client.expire(key, settings.SESSION_TTL_SECONDS)
    return sid


def get_session(sid: str) -> Optional[Dict[str, Any]]:
    """Retrieves session data from Redis.

    Returns None if missing or expired.
    Converts numeric fields to int and defaults 'emailed' to 0 if not yet set.
    """
    key = key_session(sid)
    data = redis_client.hgetall(key)
    if not data:
        return None

    if "emailed" not in data:
        data["emailed"] = 0
    if "followup_count" not in data:
        data["followup_count"] = 0

    for k, v in list(data.items()):
        if k in NUMERIC_FIELDS:
            try:
                data[k] = int(v)
            except (ValueError, TypeError):
                pass
        elif isinstance(v, str) and (v.isdigit() or (v.startswith("-") and v[1:].isdigit())):
            try:
                data[k] = int(v)
            except (ValueError, TypeError):
                pass

    return data


def touch_session(sid: str) -> None:
    """Refreshes TTL to SESSION_TTL_SECONDS on session, resume, qpool, and answers keys that exist."""
    keys = [key_session(sid), key_resume(sid), key_qpool(sid), key_answers(sid)]
    for key in keys:
        if redis_client.exists(key):
            redis_client.expire(key, settings.SESSION_TTL_SECONDS)


def update_session(sid: str, **fields) -> bool:
    """Updates only the given fields in session hash without altering TTL.

    Returns False if session does not exist.
    """
    key = key_session(sid)
    if not redis_client.exists(key):
        return False
    if fields:
        redis_client.hset(key, mapping=fields)
    return True


def incr_followups(sid: str) -> int:
    """Increments followup_count using HINCRBY and returns new value."""
    return redis_client.hincrby(key_session(sid), "followup_count", 1)


def mark_emailed(sid: str) -> bool:
    """Sets emailed to 1 using HSETNX.

    Returns True only the first time, ensuring concurrent clicks cannot duplicate sends.
    Returns False if session does not exist or was already marked emailed.
    """
    key = key_session(sid)
    if not redis_client.exists(key):
        return False
    return bool(redis_client.hsetnx(key, "emailed", 1))


def end_session(sid: str) -> None:
    """Ends session by deleting resume:{sid} and qpool:{sid}.

    Keeps session:{sid} and answers:{sid} for results processing.
    """
    redis_client.delete(key_resume(sid), key_qpool(sid))


def save_resume(
    sid: str, resume: Dict[str, Any], email: Optional[str], flags: List[str]
) -> bool:
    """Stores the parsed resume for a session.

    Returns False if session:{sid} does not exist (writes nothing).
    SETs resume:{sid} to JSON with EX = remaining session TTL if > 0,
    else SESSION_TTL_SECONDS. HSETs email (only if not None) and
    resume_flags (comma-joined) on the session hash without changing TTL.
    The email is never stored inside the resume JSON.
    """
    skey = key_session(sid)
    if not redis_client.exists(skey):
        return False
    ttl = redis_client.ttl(skey)
    resume_ttl = (
        ttl
        if isinstance(ttl, int) and ttl > 0
        else settings.SESSION_TTL_SECONDS
    )
    payload = copy.deepcopy(resume) if isinstance(resume, dict) else {}
    contact = payload.get("contact")
    if isinstance(contact, dict) and "email" in contact:
        contact = dict(contact)
        contact.pop("email", None)
        payload["contact"] = contact
    redis_client.set(key_resume(sid), json.dumps(payload), ex=resume_ttl)
    fields = {"resume_flags": ",".join(flags or [])}
    if email is not None:
        fields["email"] = email
    redis_client.hset(skey, mapping=fields)
    return True


def get_resume(sid: str) -> Optional[Dict[str, Any]]:
    """Returns the stored resume dict, or None if the key is missing."""
    raw = redis_client.get(key_resume(sid))
    if raw is None:
        return None
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None
