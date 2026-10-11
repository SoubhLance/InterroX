import redis.exceptions
from app.redis_client import redis_client
from app.services.session_service import key_rl_email


def allow_email(ip: str, limit: int = 5, window: int = 3600) -> bool:
    """Rate limits email actions per IP address using a windowed counter in Redis.

    Uses a pipeline to INCR the key, then EXPIRE with nx=True so a crash
    between the two operations never leaves an unexpiring counter.
    Falls back to SET key 0 EX window NX, then INCR if Redis does not support EXPIRE NX.
    Returns True if count <= limit, False otherwise.
    """
    key = key_rl_email(ip)
    try:
        pipe = redis_client.pipeline()
        pipe.incr(key)
        pipe.expire(key, window, nx=True)
        results = pipe.execute()
        count = results[0]
    except redis.exceptions.ResponseError:
        pipe = redis_client.pipeline()
        pipe.set(key, 0, ex=window, nx=True)
        pipe.incr(key)
        results = pipe.execute()
        count = results[1]

    return count <= limit
