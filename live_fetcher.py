import asyncio
import logging
import os
import pandas as pd
from typing import Optional
from dotenv import load_dotenv
from quotex_feed import QuotexDataFeed

# Safe Config Import
try:
    from config import settings
except ImportError:
    settings = None

# Environment variables load kora
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger("QuotexLiveFetcher")


class LiveFetcher:
    """Quotex Live Market Data Fetcher.

    Fetches real-time market data from Quotex API and returns structured DataFrames
    for StrategyEngine analysis.
    """

    def __init__(self):
        self.feed = QuotexDataFeed()

    async def fetch_candles_df(self, symbol: str, timeframe: str = "1m", count: int = 50) -> pd.DataFrame:
        """Fetches historical candle data for a given symbol and converts it to a Pandas DataFrame."""
        timeframe_map = getattr(settings, "TIMEFRAME_MAP", {
            "1m": 60,
            "5m": 300,
            "10m": 600,
            "15m": 900,
            "30m": 1800,
            "1hr": 3600,
        })
        period_sec = timeframe_map.get(timeframe, 60)

        # Fetch candles from Quotex feed
        raw_candles = await self.feed.get_candles(symbol=symbol, period_sec=period_sec, count=count)

        if not raw_candles:
            logger.warning(f"[LIVE FETCHER] No data received for asset: {symbol}")
            return pd.DataFrame()

        df = pd.DataFrame(raw_candles)

        # Standardize Quotex candle keys ('o', 'h', 'l', 'c', 'v') to standard column names
        column_mapping = {
            "o": "Open",
            "h": "High",
            "l": "Low",
            "c": "Close",
            "v": "Volume",
            "time": "Timestamp"
        }
        df = df.rename(columns=column_mapping)

        # Ensure essential columns are numeric
        for col in ["Open", "High", "Low", "Close"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df.dropna(subset=["Close", "High", "Low"]).reset_index(drop=True)
        return df


if __name__ == "__main__":

    async def main():
        print("--- Testing Live Fetcher DataFrame Output ---")
        fetcher = LiveFetcher()
        df = await fetcher.fetch_candles_df("EURUSD", timeframe="1m", count=10)
        print("DataFrame Shape:", df.shape)
        if not df.empty:
            print(df.head())

    asyncio.run(main())