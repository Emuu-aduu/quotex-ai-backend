import asyncio
import logging
from typing import Any, Dict, List, Optional, Union
import pandas as pd

logger = logging.getLogger(__name__)

# Safe Feed Import with explicit fallback
try:
    from pocket_feed import PocketOptionFeed
except ImportError:
    PocketOptionFeed = None
    logger.warning("[LiveFetcher] 'pocket_feed.py' not found. Ensure PocketOptionFeed is implemented.")

# Safe Config Import
try:
    from config import settings
except ImportError:
    settings = None

# Pre-defined timeframe mapping constant
DEFAULT_TIMEFRAME_MAP = {
    "1m": 60,
    "5m": 300,
    "10m": 600,
    "15m": 900,
    "30m": 1800,
    "1hr": 3600,
}

# Fix #2: Standardized Lowercase Column Mapping across all engines
COLUMN_MAPPING = {
    "o": "open", "open": "open", "Open": "open",
    "h": "high", "high": "high", "High": "high",
    "l": "low", "low": "low", "Low": "low",
    "c": "close", "close": "close", "Close": "close",
    "v": "volume", "volume": "volume", "Volume": "volume",
    "time": "timestamp", "timestamp": "timestamp", "Timestamp": "timestamp"
}


class LiveFetcher:
    """10/10 Production-grade Pocket Option Live Market Data Fetcher.

    Fetches real-time market data and returns clean, sorted Pandas DataFrames
    ready for technical analysis and strategy engines.
    """

    def __init__(self, feed: Optional[Any] = None):
        if feed:
            self.feed = feed
        elif PocketOptionFeed is not None:
            self.feed = PocketOptionFeed()
        else:
            self.feed = None

        self.timeframe_map = getattr(settings, "TIMEFRAME_MAP", DEFAULT_TIMEFRAME_MAP)

    async def fetch_candles_df(
        self, 
        symbol: str, 
        timeframe: str = "1m", 
        period_sec: Optional[int] = None,
        count: int = 200,
        **kwargs: Any
    ) -> pd.DataFrame:
        """Fetches historical candle data for a symbol and returns a clean, validated DataFrame."""

        if not self.feed:
            logger.error("[LIVE FETCHER] PocketOptionFeed instance is unavailable.")
            return pd.DataFrame()

        # Fix #1: Handle period_sec passed directly by StrategyEngine
        if period_sec is None:
            period_sec = self.timeframe_map.get(timeframe, 60)

        # 1. Network & API Execution
        try:
            if hasattr(self.feed, "get_candles"):
                raw_candles = await self.feed.get_candles(symbol=symbol, period_sec=period_sec, count=count)
            elif hasattr(self.feed, "fetch_candles"):
                raw_candles = await self.feed.fetch_candles(symbol=symbol, period_sec=period_sec, count=count)
            else:
                logger.error("[LIVE FETCHER] Feed instance lacks candle fetching methods.")
                return pd.DataFrame()

        except Exception as e:
            logger.error(f"[LIVE FETCHER] Network/API Error fetching candles for {symbol}: {str(e)}", exc_info=True)
            return pd.DataFrame()

        # 2. Data Type & Structure Validation
        if not raw_candles or not isinstance(raw_candles, list):
            logger.warning(f"[LIVE FETCHER] Invalid or empty candle payload received for asset: {symbol}")
            return pd.DataFrame()

        if not isinstance(raw_candles[0], dict):
            logger.error(f"[LIVE FETCHER] Candle data structure is not list of dicts for asset: {symbol}")
            return pd.DataFrame()

        # 3. DataFrame Construction & Column Renaming
        df = pd.DataFrame(raw_candles)
        df = df.rename(columns=COLUMN_MAPPING)

        # 4. Numeric Formatting
        numeric_cols = ["open", "high", "low", "close", "volume"]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # 5. Smart Dynamic Timestamp Unit Auto-Detection
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce")
            valid_ts = df["timestamp"].dropna()
            if not valid_ts.empty:
                unit = "ms" if valid_ts.iloc[0] > 1e11 else "s"
                df["timestamp"] = pd.to_datetime(df["timestamp"], unit=unit, errors="coerce")

        # 6. Complete dropna logic
        required_cols = [c for c in ["open", "high", "low", "close", "timestamp"] if c in df.columns]
        df = df.dropna(subset=required_cols)

        # 7. Sort chronologically (Oldest -> Newest)
        if "timestamp" in df.columns:
            df = df.sort_values("timestamp", ascending=True)

        return df.reset_index(drop=True)

    # Fix #4: Alias method for direct candle list access or strategy fallback
    async def get_candles(
        self, 
        symbol: str, 
        period_sec: int = 60, 
        count: int = 200, 
        **kwargs: Any
    ) -> Union[pd.DataFrame, List[Dict[str, Any]]]:
        """Backward compatibility alias for StrategyEngine integration."""
        return await self.fetch_candles_df(symbol=symbol, period_sec=period_sec, count=count, **kwargs)

    # Fix #3: Direct Active Symbols Resolver
    async def get_active_symbols(self) -> List[str]:
        """Returns currently active trading symbols from Feed or Config."""
        if self.feed and hasattr(self.feed, "get_active_symbols") and callable(self.feed.get_active_symbols):
            try:
                symbols = await self.feed.get_active_symbols()
                if symbols:
                    return symbols
            except Exception as err:
                logger.warning(f"[LIVE FETCHER] Failed to fetch active symbols from feed: {err}")

        # Fallback to Config default pairs
        if settings and hasattr(settings, "DEFAULT_PAIRS"):
            return settings.DEFAULT_PAIRS

        return ["EURUSD_otc", "GBPUSD_otc", "USDJPY_otc", "EURUSD", "GBPUSD"]


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
    )

    async def main():
        logger.info("--- Testing Production Live Fetcher DataFrame Output ---")
        fetcher = LiveFetcher()
        df = await fetcher.fetch_candles_df("EURUSD_otc", timeframe="1m", count=200)
        logger.info(f"DataFrame Shape: {df.shape}")
        if not df.empty:
            print(df.head())

    asyncio.run(main())