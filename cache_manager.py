import time
import json
import logging
from typing import Any, Optional, Dict, Tuple
from config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


class LocalCache:
    """High-speed in-memory fallback cache with TTL expiration."""
    def __init__(self):
        self._store: Dict[str, Tuple[Any, float]] = {}

    def set(self, key: str, value: Any, ttl_seconds: int = 300) -> None:
        expire_at = time.time() + ttl_seconds
        self._store[key] = (value, expire_at)

    def get(self, key: str) -> Optional[Any]:
        if key not in self._store:
            return None
        value, expire_at = self._store[key]
        if time.time() > expire_at:
            del self._store[key]
            return None
        return value

    def delete(self, key: str) -> None:
        if key in self._store:
            del self._store[key]


class HybridCacheManager:
    """
    Enterprise Hybrid Cache
    Primary: Upstash Redis (Cloud)
    Fallback: Local In-Memory Store (Triggers on quota limit / network errors)
    """
    def __init__(self):
        self.local_cache = LocalCache()
        self.redis_client = None
        self.use_redis = False
        self._init_redis()

    def _init_redis(self) -> None:
        """Attempts connection to Upstash Redis if URL is provided in config."""
        if getattr(settings, "UPSTASH_REDIS_URL", ""):
            try:
                import redis
                self.redis_client = redis.Redis.from_url(
                    settings.UPSTASH_REDIS_URL,
                    socket_timeout=2.0,
                    decode_responses=True
                )
                self.redis_client.ping()
                self.use_redis = True
                logging.info("[CACHE] Connected successfully to Upstash Redis Cloud!")
            except Exception as e:
                logging.warning(f"[CACHE] Upstash Redis connection failed/disabled ({e}). Defaulting to Local Cache Fallback.")
                self.use_redis = False
        else:
            logging.info("[CACHE] No Upstash URL configured. Running on high-performance Local Memory Cache.")

    def set(self, key: str, value: Any, ttl_seconds: int = 300) -> bool:
        """Sets cache key with automatic fallback handling and bulletproof JSON serialization."""
        self.local_cache.set(key, value, ttl_seconds)

        if self.use_redis and self.redis_client:
            try:
                str_value = json.dumps(value)
                self.redis_client.setex(key, ttl_seconds, str_value)
                return True
            except Exception as e:
                logging.error(f"[CACHE ALERT] Upstash Redis failed or quota exceeded ({e}). Switched to Local Fallback.")
                self.use_redis = False
                return False
        return True

    def get(self, key: str) -> Optional[Any]:
        """Gets cache key, prioritizing Redis then falling back to local memory."""
        if self.use_redis and self.redis_client:
            try:
                val = self.redis_client.get(key)
                if val is not None:
                    return json.loads(val)
            except Exception as e:
                logging.error(f"[CACHE ALERT] Upstash Redis read error ({e}). Reading from Local Fallback.")
                self.use_redis = False

        return self.local_cache.get(key)

    def is_duplicate_signal(self, sig_hash: str) -> bool:
        """Checks if a signal hash has already been processed to prevent duplicate executions."""
        key = f"sig:{sig_hash}"
        return self.get(key) is not None

    def mark_signal_processed(self, sig_hash: str, ttl_seconds: int = 60) -> bool:
        """Marks a signal hash as processed for a specified TTL period (default: 60s)."""
        key = f"sig:{sig_hash}"
        return self.set(key, "processed", ttl_seconds=ttl_seconds)


# --- Self-Testing Verification ---
if __name__ == "__main__":
    print("--- Testing Hybrid Cache Engine ---")
    cache = HybridCacheManager()

    mock_signal = {
        "symbol": "EURUSD",
        "action": "BUY",
        "price": 1.0850,
        "active": True,
        "count": 5
    }
    
    print("\n1. Storing Mock Signal in Hybrid Cache...")
    cache.set("latest_signal_EURUSD", mock_signal, ttl_seconds=60)

    print("2. Retrieving Signal from Cache...")
    retrieved = cache.get("latest_signal_EURUSD")
    print(f">> Retrieved Data: {retrieved}")

    assert retrieved is not None, "Cache retrieval failed!"

    print("\n3. Testing Deduplication Methods...")
    test_hash = "hash_12345"
    assert not cache.is_duplicate_signal(test_hash), "Initial check failed!"
    cache.mark_signal_processed(test_hash, ttl_seconds=10)
    assert cache.is_duplicate_signal(test_hash), "Deduplication detection failed!"
    
    print("\n>> HYBRID CACHE MANAGER TEST PASSED 100%! <<")