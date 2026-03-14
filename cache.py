import json
import logging
import os

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
CACHE_TTL = 24 * 60 * 60  # 24 hours

_client = None


def _connect():
    global _client
    if _client is not None:
        return _client

    # Try real Redis first
    try:
        import redis
        c = redis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=2)
        c.ping()
        logger.info("Connected to Redis at %s", REDIS_URL)
        _client = c
        return _client
    except Exception as e:
        logger.warning("Redis unavailable (%s), falling back to fakeredis", e)

    # Fall back to fakeredis
    try:
        import fakeredis
        _client = fakeredis.FakeRedis(decode_responses=True)
        logger.info("Using fakeredis in-memory cache")
        return _client
    except ImportError:
        raise RuntimeError(
            "Neither Redis nor fakeredis is available. "
            "Install fakeredis: pip install fakeredis"
        )


def _cache_key(domain: str, depth: str) -> str:
    return f"enrich:{domain}:{depth}"


def get_cached(domain: str, depth: str) -> dict | None:
    try:
        c = _connect()
        raw = c.get(_cache_key(domain, depth))
        if raw:
            return json.loads(raw)
    except Exception as e:
        logger.warning("Cache get error: %s", e)
    return None


def set_cached(domain: str, depth: str, data: dict) -> None:
    try:
        c = _connect()
        c.setex(_cache_key(domain, depth), CACHE_TTL, json.dumps(data))
    except Exception as e:
        logger.warning("Cache set error: %s", e)


def delete_cached(domain: str, depth: str) -> None:
    try:
        c = _connect()
        c.delete(_cache_key(domain, depth))
    except Exception as e:
        logger.warning("Cache delete error: %s", e)
