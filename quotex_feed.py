import logging
import os
from typing import List, Dict, Any
from quotexpy import Quotex

# Safe Config Import
try:
    from config import settings
except ImportError:
    settings = None

logger = logging.getLogger(__name__)


class QuotexDataFeed:
    """
    Production-Grade Quotex API Data Feed Handler for fetching candle data.
    """

    def __init__(self, email: str = None, password: str = None):
        self.email = email or getattr(settings, "QUOTEX_EMAIL", "") or os.getenv("QUOTEX_EMAIL", "")
        self.password = password or getattr(settings, "QUOTEX_PASSWORD", "") or os.getenv("QUOTEX_PASSWORD", "")

    async def get_candles(self, symbol: str, period_sec: int = 60, count: int = 50) -> List[Dict[str, Any]]:
        """
        Fetches historical candle data asynchronously from Quotex API.
        """
        if not self.email or not self.password:
            logger.error("[QUOTEX ERROR] Account credentials missing in config/environment variables!")
            return []

        # Safe symbol normalization
        normalize_func = getattr(settings, "clean_and_normalize_symbol", lambda s: s.replace("/", "").replace("-", ""))
        clean_symbol = normalize_func(symbol)

        # OTC Pair Check Guard
        if "OTC" in clean_symbol.upper():
            logger.warning(f"[SECURITY ALERT] OTC Pair Detected: '{clean_symbol}'. Disconnecting/Blocking...")
            return []

        # Approved Pair Check Guard
        is_approved_func = getattr(settings, "is_approved_live_pair", lambda pair: True)
        if not is_approved_func(clean_symbol):
            logger.debug(f"[FILTERED] Non-approved pair ignored: '{clean_symbol}'")
            return []

        client = Quotex(email=self.email, password=self.password)

        try:
            check, reason = await client.connect()
            if not check:
                logger.error(f"[QUOTEX CONNECTION FAILED] Reason: {reason}")
                return []

            # Fetch candles from Quotex API
            candles = await client.get_candles(clean_symbol, period_sec)

            if candles and isinstance(candles, list):
                logger.info(f"[QUOTEX FETCH SUCCESS] Asset: {clean_symbol} | Count: {len(candles)}")
                return candles[-count:]

            logger.warning(f"[QUOTEX EMPTY] No candle data received for asset: {clean_symbol}")
            return []

        except Exception as err:
            logger.error(f"[QUOTEX FEED ERROR] Asset: {clean_symbol} | Error: {err}")
            return []

        finally:
            client.close()


if __name__ == "__main__":
    import asyncio

    async def test_feed():
        print("--- Testing Quotex Data Feed Logic Validation ---")
        feed = QuotexDataFeed()

        print("\n1. Testing Valid Pair (EURUSD):")
        data = await feed.get_candles("EURUSD", period_sec=60, count=10)
        print(f"Candles Fetched Count: {len(data)}")

        print("\n2. Testing OTC Pair Guard (EURUSD_OTC):")
        otc_data = await feed.get_candles("EURUSD_OTC", period_sec=60, count=10)
        print(f"OTC Block Test Result Count: {len(otc_data)}")

    asyncio.run(test_feed())