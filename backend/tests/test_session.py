from pathlib import Path
import sys
import pytest
import redis
from fastapi.testclient import TestClient

# Ensure backend directory is in sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.config import settings
from app.main import app
from app.services.session_service import (
    create_session,
    get_session,
    touch_session,
    update_session,
    incr_followups,
    mark_emailed,
    end_session,
    key_session,
    key_resume,
    key_qpool,
    key_answers,
    key_rl_email,
)
from app.services.rate_limiter import allow_email


@pytest.fixture(autouse=True)
def redis_test_client(monkeypatch):
    """Isolate tests in Redis DB 15, flushing only DB 15 before and after each test."""
    test_client = redis.Redis.from_url("redis://localhost:6379/15", decode_responses=True)
    test_client.flushdb()
    monkeypatch.setattr("app.redis_client.redis_client", test_client)
    monkeypatch.setattr("app.services.session_service.redis_client", test_client)
    monkeypatch.setattr("app.services.rate_limiter.redis_client", test_client)
    monkeypatch.setattr("app.routers.dev.redis_client", test_client)
    yield test_client
    test_client.flushdb()
    test_client.close()


@pytest.fixture
def api_client():
    return TestClient(app)


def test_create_then_get_session_fields_and_types():
    """create_session followed by get_session returns expected fields and int types for numerics."""
    sid = create_session("fast", 15)
    assert isinstance(sid, str)
    assert len(sid) > 0

    session = get_session(sid)
    assert session is not None
    assert session["mode"] == "fast"
    assert isinstance(session["mode"], str)
    assert session["duration_min"] == 15
    assert isinstance(session["duration_min"], int)
    assert session["segment"] == "intro"
    assert isinstance(session["segment"], str)
    assert session["time_left_sec"] == 900
    assert isinstance(session["time_left_sec"], int)
    assert session["followup_count"] == 0
    assert isinstance(session["followup_count"], int)
    assert session["emailed"] == 0
    assert isinstance(session["emailed"], int)
    assert isinstance(session["created_at"], int)
    assert session["created_at"] > 0


def test_session_ttl_is_set_and_valid(redis_test_client):
    """Session TTL is set upon creation and is <= SESSION_TTL_SECONDS."""
    sid = create_session("deep", 45)
    ttl = redis_test_client.ttl(key_session(sid))
    assert 0 < ttl <= settings.SESSION_TTL_SECONDS


def test_update_session_does_not_reset_ttl(redis_test_client):
    """update_session updates fields without resetting or altering the remaining TTL."""
    sid = create_session("fast", 20)
    # Artificially set a lower TTL
    redis_test_client.expire(key_session(sid), 500)
    ttl_before = redis_test_client.ttl(key_session(sid))
    assert ttl_before <= 500

    success = update_session(sid, segment="technical", time_left_sec=600)
    assert success is True

    updated = get_session(sid)
    assert updated["segment"] == "technical"
    assert updated["time_left_sec"] == 600
    assert isinstance(updated["time_left_sec"], int)

    ttl_after = redis_test_client.ttl(key_session(sid))
    # TTL should not have been reset back to 7200
    assert ttl_after <= 500


def test_touch_session_refreshes_ttl(redis_test_client):
    """touch_session refreshes TTL on session, resume, qpool, and answers keys that exist."""
    sid = create_session("fast", 15)
    redis_test_client.set(key_resume(sid), "resume data")
    redis_test_client.set(key_qpool(sid), "qpool data")
    redis_test_client.set(key_answers(sid), "answers data")

    # Artificially set lower TTLs on all keys
    for k in [key_session(sid), key_resume(sid), key_qpool(sid), key_answers(sid)]:
        redis_test_client.expire(k, 60)
        assert redis_test_client.ttl(k) <= 60

    touch_session(sid)

    # Verify all existing keys were refreshed to SESSION_TTL_SECONDS
    for k in [key_session(sid), key_resume(sid), key_qpool(sid), key_answers(sid)]:
        ttl = redis_test_client.ttl(k)
        assert ttl > 60
        assert ttl <= settings.SESSION_TTL_SECONDS


def test_mark_emailed_returns_true_then_false():
    """mark_emailed uses HSETNX to return True only the first time and False subsequently."""
    sid = create_session("fast", 15)
    assert get_session(sid)["emailed"] == 0

    # First call must succeed
    first_attempt = mark_emailed(sid)
    assert first_attempt is True
    assert get_session(sid)["emailed"] == 1

    # Second call must be rejected (idempotent / concurrency-safe)
    second_attempt = mark_emailed(sid)
    assert second_attempt is False
    assert get_session(sid)["emailed"] == 1


def test_end_session_removes_resume_and_qpool_but_keeps_session_and_answers(redis_test_client):
    """end_session removes resume and qpool keys immediately while keeping session and answers."""
    sid = create_session("fast", 15)
    redis_test_client.set(key_resume(sid), "resume payload")
    redis_test_client.set(key_qpool(sid), "qpool payload")
    redis_test_client.set(key_answers(sid), "answers payload")

    end_session(sid)

    assert redis_test_client.exists(key_resume(sid)) == 0
    assert redis_test_client.exists(key_qpool(sid)) == 0
    assert redis_test_client.exists(key_session(sid)) == 1
    assert redis_test_client.exists(key_answers(sid)) == 1


def test_rate_limiter_allows_limit_and_blocks_excess(redis_test_client):
    """Rate limiter allows 5 calls, blocks the 6th, and ensures counter has TTL."""
    ip = "1.2.3.4"
    for _ in range(5):
        assert allow_email(ip, limit=5, window=3600) is True

    # 6th call should be blocked
    assert allow_email(ip, limit=5, window=3600) is False

    # Counter key must have an active TTL
    ttl = redis_test_client.ttl(key_rl_email(ip))
    assert 0 < ttl <= 3600


def test_missing_session_returns_none_not_exception():
    """Missing session returns None rather than raising an exception."""
    missing_sid = "nonexistent_sid_12345"
    assert get_session(missing_sid) is None
    assert update_session(missing_sid, segment="closing") is False
    assert mark_emailed(missing_sid) is False


def test_incr_followups_increments_and_returns_new_value():
    """incr_followups increments followup_count and returns new integer value."""
    sid = create_session("fast", 15)
    assert incr_followups(sid) == 1
    assert incr_followups(sid) == 2
    session = get_session(sid)
    assert session["followup_count"] == 2


def test_dev_endpoints(api_client, redis_test_client):
    """Test temporary dev endpoints for session lifecycle and rate limiting."""
    # 1. POST /dev/session
    res = api_client.post("/dev/session", json={"mode": "deep", "duration_min": 30})
    assert res.status_code == 200
    sid = res.json()["sid"]

    # 2. GET /dev/session/{sid}
    res = api_client.get(f"/dev/session/{sid}")
    assert res.status_code == 200
    data = res.json()
    assert data["mode"] == "deep"
    assert data["duration_min"] == 30
    assert data["ttl_remaining"] > 0
    assert data["followup_count"] == 0
    assert data["emailed"] == 0

    # 3. GET missing session returns 404
    res = api_client.get("/dev/session/missing_sid")
    assert res.status_code == 404

    # 4. POST /dev/rate-limit/{ip}
    test_ip = "10.0.0.1"
    for _ in range(5):
        res = api_client.post(f"/dev/rate-limit/{test_ip}")
        assert res.status_code == 200
        assert res.json()["allowed"] is True

    # 6th call blocked
    res = api_client.post(f"/dev/rate-limit/{test_ip}")
    assert res.status_code == 200
    assert res.json()["allowed"] is False

    # 5. POST /dev/session/{sid}/end
    redis_test_client.set(key_resume(sid), "resume_val")
    redis_test_client.set(key_qpool(sid), "qpool_val")
    res = api_client.post(f"/dev/session/{sid}/end")
    assert res.status_code == 200
    assert redis_test_client.exists(key_resume(sid)) == 0
    assert redis_test_client.exists(key_qpool(sid)) == 0
    assert redis_test_client.exists(key_session(sid)) == 1
