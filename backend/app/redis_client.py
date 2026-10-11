import redis
from app.config import settings

# Single shared Redis connection
redis_client: redis.Redis = redis.Redis.from_url(
    settings.REDIS_URL,
    decode_responses=True,
    socket_connect_timeout=2.0,
    socket_timeout=2.0,
)
