"""Redis connection and the small set of keys the platform relies on."""

from __future__ import annotations

import json
from typing import Any

import redis

from app.core.config import settings

_pool = redis.ConnectionPool.from_url(settings.redis_url, decode_responses=True)


def get_redis() -> redis.Redis:
    return redis.Redis(connection_pool=_pool)


def ping() -> bool:
    try:
        return bool(get_redis().ping())
    except redis.RedisError:
        return False


# --- Key namespace --------------------------------------------------------


class Keys:
    LAST_TICK = "md:tick:{token}"                 # latest tick payload
    LIVE_CANDLE = "md:candle:{token}:{tf}"        # in-progress candle
    MARKET_STATUS = "md:status"
    FEED_HEARTBEAT = "md:heartbeat"
    SUBSCRIPTIONS = "md:subscriptions"
    KILL_SWITCH = "risk:kill_switch"
    DAILY_PNL = "risk:daily_pnl:{date}"
    TRADE_COUNT = "risk:trade_count:{date}"
    SIGNAL_DEDUPE = "sig:dedupe:{strategy}:{token}:{tf}:{candle_ts}"
    IMPORT_PROGRESS = "import:progress:{job_id}"
    AI_USAGE_MONTH = "ai:usage:{month}"


def set_json(key: str, value: Any, ttl: int | None = None) -> None:
    r = get_redis()
    payload = json.dumps(value, default=str)
    r.set(key, payload, ex=ttl) if ttl else r.set(key, payload)


def get_json(key: str) -> Any | None:
    raw = get_redis().get(key)
    return json.loads(raw) if raw else None
