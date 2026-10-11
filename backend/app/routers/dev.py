from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional
from app.redis_client import redis_client
from app.services.session_service import (
    create_session,
    get_session,
    end_session,
    key_session,
)
from app.services.rate_limiter import allow_email

router = APIRouter(prefix="/dev", tags=["dev"])


class KeyValueRequest(BaseModel):
    key: str
    value: str
    ttl_seconds: int = Field(default=30, gt=0, description="Time to live in seconds")


class CreateSessionRequest(BaseModel):
    mode: str = Field(default="fast", description="Session mode: fast or deep")
    duration_min: int = Field(default=15, gt=0, description="Session duration in minutes")


@router.post("/kv", status_code=status.HTTP_200_OK)
def set_kv(payload: KeyValueRequest):
    """Sets a key-value pair in Redis with expiration (TTL)."""
    redis_client.set(name=payload.key, value=payload.value, ex=payload.ttl_seconds)
    return {
        "key": payload.key,
        "value": payload.value,
        "ttl_seconds": payload.ttl_seconds,
    }


@router.get("/kv/{key}", status_code=status.HTTP_200_OK)
def get_kv(key: str):
    """Retrieves a key-value pair and remaining TTL from Redis.

    Returns 404 if the key is missing or expired.
    """
    value = redis_client.get(key)
    ttl_remaining = redis_client.ttl(key)

    if value is None or ttl_remaining == -2:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Key '{key}' not found or expired",
        )

    return {
        "key": key,
        "value": value,
        "ttl_remaining": ttl_remaining,
    }


@router.post("/session", status_code=status.HTTP_200_OK)
def create_session_endpoint(payload: CreateSessionRequest):
    """Creates a new session and returns the session id."""
    sid = create_session(mode=payload.mode, duration_min=payload.duration_min)
    return {"sid": sid}


@router.get("/session/{sid}", status_code=status.HTTP_200_OK)
def get_session_endpoint(sid: str):
    """Retrieves session dict plus ttl_remaining, or 404 if missing/expired."""
    session_data = get_session(sid)
    if session_data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{sid}' not found or expired",
        )
    ttl_remaining = redis_client.ttl(key_session(sid))
    return {
        **session_data,
        "ttl_remaining": ttl_remaining,
    }


@router.post("/session/{sid}/end", status_code=status.HTTP_200_OK)
def end_session_endpoint(sid: str):
    """Ends the session by deleting transient resume and qpool keys."""
    end_session(sid)
    return {"status": "ended", "sid": sid}


@router.post("/rate-limit/{ip}", status_code=status.HTTP_200_OK)
def check_rate_limit(ip: str):
    """Checks whether email action for the given IP is allowed under rate limits."""
    allowed = allow_email(ip)
    return {"allowed": allowed}
