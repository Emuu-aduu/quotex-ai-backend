import asyncio
import logging
import os
from typing import Any, Dict, List, Optional
import pandas as pd

# Pocket Option Async/WebSocket Library Robust Multi-Path Import Guard
PocketOption = None
_import_errors = []

# Try Path 1: Direct Async Module Import (Most Common for ChipaDevTeam / Async repos)
try:
    from pocketoptionapi_async import PocketOption
except Exception as e:
    _import_errors.append(f"pocketoptionapi_async: {e}")

# Try Path 2: Async Module with stable_api
if PocketOption is None:
    try:
        from pocketoptionapi_async.stable_api import PocketOption
    except Exception as e:
        _import_errors.append(f"pocketoptionapi_async.stable_api: {e}")

# Try Path 3: Async Module with api
if PocketOption is None:
    try:
        from pocketoptionapi_async.api import PocketOption
    except Exception as e:
        _import_errors.append(f"pocketoptionapi_async.api: {e}")

# Try Path 4: Standard pocketoptionapi Module
if PocketOption is None:
    try:
        from pocketoptionapi import PocketOption
    except Exception as e:
        _import_errors.append(f"pocketoptionapi: {e}")

# Try Path 5: Standard pocketoptionapi with stable_api
if PocketOption is None:
    try:
        from pocketoptionapi.stable_api import PocketOption
    except Exception as e:
        _import_errors.append(f"pocketoptionapi.stable_api: {e}")

# Safe Config & Single Source Pair List Import
try:
    from config import settings
except ImportError:
    settings = None

logger = logging.getLogger(__name__)

# Single Source of Truth for Default Pairs
DEFAULT_PAIRS = getattr(
    settings,
    "DEFAULT_PAIRS",
    [
        "EURUSD_otc", "GBPUSD_otc", "USDJPY_otc", "AUDCAD_otc", "EURGBP_otc",
        "USDCHF_otc", "NZDUSD_otc", "EURJPY_otc", "GBPJPY_otc", "AUDUSD_otc",
        "USDCAD_otc", "AUDJPY_otc", "CADCHF_otc", "EURAUD_otc", "GBPAUD_otc",
        "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD"
    ],
)


class PocketOptionFeed:
    """Production-Grade Persistent Pocket Option API Data Feed Handler.

    Fully compatible with Config, StrategyEngine, LiveFetcher, and TrustEngine pipelines.
    Handles persistent connection, SSID/Credentials authentication, and DataFrame conversion.
    """

    def __init__(
        self,
        ssid: Optional[str] = None,
        email: Optional[str] = None,
        password: Optional[str] = None,
        allow_otc: bool = True,
    ):
        self.ssid = ssid or os.getenv("POCKETOPTION_SSID", "")
        self.email = (
            email
            or getattr(settings, "POCKETOPTION_EMAIL", "")
            or os.getenv("POCKETOPTION_EMAIL", "")
            or os.getenv("POCKET_EMAIL", "")
        )
        self.password = (
            password
            or getattr(settings, "POCKETOPTION_PASSWORD", "")
            or os.getenv("POCKETOPTION_PASSWORD", "")
            or os.getenv("POCKET_PASSWORD", "")
        )
        self.allow_otc = (
            allow_otc
            if allow_otc is not None
            else getattr(settings, "ALLOW_OTC", True)
        )
        self.client: Optional[Any] = None
        self._is_connected = False
        self._lock = asyncio.Lock()

    async def connect(self) -> bool:
        """Establishes thread/coro safe connection to Pocket Option WebSocket."""
        async with self._lock:
            if self._is_connected and self.client:
                return True

            if PocketOption is None:
                logger.error(
                    f"[POCKET OPTION ERROR] Could not import PocketOption library! Attempted paths failed: {_import_errors}"
                )
                return False

            try:
                # Primary auth via SSID or Email/Password fallback
                if self.ssid:
                    self.client = PocketOption(ssid=self.ssid)
                elif self.email and self.password:
                    self.client = PocketOption(email=self.email, password=self.password)
                else:
                    logger.error(
                        "[POCKET OPTION ERROR] Neither SSID nor Email/Password found in Config/Env!"
                    )
                    return False

                # Connect coroutine execution via thread wrapper for synchronous SDKs
                res = await asyncio.to_thread(self.client.connect)

                # Tuple extraction guard for (bool, msg) return types
                if isinstance(res, tuple):
                    check = bool(res[0])
                    reason = res[1] if len(res) > 1 else ""
                else:
                    check = bool(res)
                    reason = ""

                if check:
                    self._is_connected = True
                    logger.info("[POCKET OPTION CONNECTED] Persistent WebSocket active.")
                    return True
                else:
                    logger.error(f"[POCKET OPTION FAILED] Connection refused by broker. Reason: {reason}")
                    self._is_connected = False
                    return False

            except Exception as err:
                logger.error(f"[POCKET OPTION CONNECT ERROR] Exception: {err}")
                self._is_connected = False
                return False

    async def close(self):
        """Closes active Pocket Option session safely."""
        async with self._lock:
            if self.client:
                try:
                    disconnect_fn = getattr(self.client, "disconnect", None) or getattr(
                        self.client, "close", None
                    )
                    if disconnect_fn:
                        if asyncio.iscoroutinefunction(disconnect_fn):
                            await disconnect_fn()
                        else:
                            await asyncio.to_thread(disconnect_fn)
                except Exception as err:
                    logger.debug(f"[POCKET OPTION CLOSE NOTICE] {err}")

            self._is_connected = False
            self.client = None
            logger.info("[POCKET OPTION DISCONNECTED] Session terminated.")

    def _format_symbol_for_pocket(self, raw_symbol: str) -> str:
        """Formats standard symbols to Pocket Option internal naming."""
        clean_fn = getattr(
            settings,
            "clean_and_normalize_symbol",
            lambda s: s.strip().replace(" ", "").replace("/", "").replace("-", ""),
        )
        clean = clean_fn(raw_symbol)

        # Pocket Option prefixes OTC assets with '#' internally in some API versions
        if "OTC" in clean.upper() and not clean.startswith("#"):
            return f"#{clean}"
        return clean

    async def get_candles(
        self, symbol: str, period_sec: int = 60, count: int = 50
    ) -> List[Dict[str, Any]]:
        """Fetches historical candles asynchronously with auto-reconnect fallback."""
        if not self._is_connected or not self.client:
            connected = await self.connect()
            if not connected:
                return []

        # Validate against OTC and Approved Pairs settings
        check_otc = getattr(settings, "ALLOW_OTC", self.allow_otc)
        if not check_otc and "OTC" in symbol.upper():
            logger.warning(f"[SECURITY FILTER] OTC Pair Blocked: '{symbol}'")
            return []

        is_approved_fn = getattr(settings, "is_approved_pair", lambda p: True)
        if not is_approved_fn(symbol):
            logger.debug(f"[FILTERED] Non-approved pair ignored: '{symbol}'")
            return []

        po_symbol = self._format_symbol_for_pocket(symbol)

        try:
            # Non-blocking async fetch from SDK
            candles = await asyncio.to_thread(
                self.client.get_candles, po_symbol, period_sec, count
            )

            if candles and isinstance(candles, list):
                logger.debug(
                    f"[POCKET OPTION FETCH] Asset: {symbol} ({po_symbol}) | Count: {len(candles)}"
                )
                return candles[-count:]

            # Fallback retry without '#' prefix if first attempt returned empty
            alt_symbol = po_symbol.lstrip("#")
            if alt_symbol != po_symbol:
                candles = await asyncio.to_thread(
                    self.client.get_candles, alt_symbol, period_sec, count
                )
                if candles and isinstance(candles, list):
                    return candles[-count:]

            logger.warning(f"[POCKET OPTION EMPTY] No candles for: {symbol}")
            return []

        except Exception as err:
            logger.error(f"[POCKET OPTION FEED ERROR] Asset: {symbol} | Error: {err}")
            self._is_connected = False
            return []

    async def fetch_candles_df(
        self, symbol: str, period_sec: int = 60, count: int = 50
    ) -> Optional[pd.DataFrame]:
        """Adapter for StrategyEngine and LiveFetcher: Returns clean, standardized DataFrame."""
        candles = await self.get_candles(
            symbol=symbol, period_sec=period_sec, count=count
        )
        if not candles:
            return None

        df = pd.DataFrame(candles)
        if df.empty:
            return None

        # Standardize column casing to lowercase
        df.columns = [str(col).lower() for col in df.columns]

        # Standardize timestamp key & dynamic unit detection
        ts_col = next((c for c in ["time", "timestamp", "t"] if c in df.columns), None)
        if ts_col:
            try:
                first_ts = float(df[ts_col].iloc[0])
                unit = "ms" if first_ts > 1e11 else "s"
                df["timestamp"] = pd.to_datetime(df[ts_col], unit=unit, errors="coerce")
                if ts_col != "timestamp":
                    df = df.drop(columns=[ts_col])
            except Exception as ts_err:
                logger.debug(f"[TIMESTAMP CONVERT WARNING] {ts_err}")

        return df

    async def get_active_symbols(self) -> List[str]:
        """Provides dynamic pair list respecting OTC setting."""
        pairs = getattr(settings, "DEFAULT_PAIRS", DEFAULT_PAIRS)
        check_otc = getattr(settings, "ALLOW_OTC", self.allow_otc)

        if not check_otc:
            return [s for s in pairs if "OTC" not in s.upper()]
        return pairs


# Class Alias for Backward Compatibility
PocketOptionDataFeed = PocketOptionFeed


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    async def test_pocket_feed():
        print("--- Testing Production Pocket Option Data Feed ---")
        feed = PocketOptionFeed(allow_otc=True)

        connected = await feed.connect()
        print(f"Connection Status: {connected}")

        if connected:
            print("\n1. Testing Candle DataFrame Fetch (EURUSD_otc):")
            df = await feed.fetch_candles_df("EURUSD_otc", period_sec=60, count=10)
            if df is not None:
                print(f"DataFrame Shape: {df.shape}")
                print(df.tail(2))

            await feed.close()

    asyncio.run(test_pocket_feed())