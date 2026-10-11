import logging
from fastapi import APIRouter
from app.redis_client import redis_client
from redis.exceptions import RedisError

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


@router.get("/health")
def health_check():
    """Health check endpoint.

    Returns {"status": "ok", "redis": "up"|"down"}.
    Pings Redis; if Redis is unreachable returns redis "down" (does not crash).
    """
    redis_status = "down"
    try:
        if redis_client.ping():
            redis_status = "up"
    except (RedisError, Exception) as exc:
        logger.warning("Redis ping check failed: %s", exc)
        redis_status = "down"

    return {"status": "ok", "redis": redis_status}
