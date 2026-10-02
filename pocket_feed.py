import asyncio
import importlib
import logging
import os
from typing import Any, Dict, List, Optional
import pandas as pd

logger = logging.getLogger(__name__)

# Dynamic Auto-Discovery Engine for PocketOption Library Classes
PocketOption = None
_import_details = []

try:
    import pocketoptionapi_async as po_async
    _import_details.append(f"pocketoptionapi_async exports: {dir(po_async)}")

    # 1. Search main package for common class names
    for attr_name in ["PocketOptionAsync", "PocketOption", "AsyncPocketOption", "PocketOptionClient", "Client"]:
        if hasattr(po_async, attr_name):
            PocketOption = getattr(po_async, attr_name)
            logger.info(f"[POCKET OPTION IMPORT SUCCESS] Loaded '{attr_name}' from pocketoptionapi_async")
            break

    # 2. Search sub-modules if not found in main module
    if PocketOption is None:
        sub_modules = ["pocketoption", "client", "api", "stable_api", "async_api", "main"]
        for sub_name in sub_modules:
            try:
                sub_mod = importlib.import_module(f"pocketoptionapi_async.{sub_name}")
                for attr_name in ["PocketOptionAsync", "PocketOption", "AsyncPocketOption", "PocketOptionClient", "Client"]:
                    if hasattr(sub_mod, attr_name):
                        PocketOption = getattr(sub_mod, attr_name)
                        logger.info(f"[POCKET OPTION IMPORT SUCCESS] Loaded '{attr_name}' from pocketoptionapi_async.{sub_name}")
                        break
                if PocketOption is not None:
                    break
            except ImportError:
                continue
except ImportError as e:
    _import_details.append(f"pocketoptionapi_async import error: {e}")

# Fallback to sync pocketoptionapi package if installed
if PocketOption is None:
    for pkg_path in ["pocketoptionapi.stable_api", "pocketoptionapi"]:
        try:
            mod = importlib.import_module(pkg_path)
            for attr_name in ["PocketOption", "PocketOptionAsync"]:
                if hasattr(mod, attr_name):
                    PocketOption = getattr(mod, attr_name)
                    logger.info(f"[POCKET OPTION IMPORT SUCCESS] Loaded '{attr_name}' from {pkg_path}")
                    break
            if PocketOption is not None:
                break
        except ImportError as e:
            _import_details.append(f"{pkg_path} import error: {e}")

# Safe Config & Single Source Pair List Import
try:
    from config import settings
except ImportError:
    settings = None

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
    """Production-Grade Persistent Pocket Option API Data Feed Handler."""

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
        """Establishes safe connection supporting both sync and async SDK methods."""
        async with self._lock:
            if self._is_connected and self.client:
                return True

            if PocketOption is None:
                logger.error(
                    f"[POCKET OPTION ERROR] Could not locate valid PocketOption class! Details: {_import_details}"
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

                # Connect supporting both async coroutines and sync blocking functions
                connect_fn = getattr(self.client, "connect", None)
                if connect_fn:
                    if asyncio.iscoroutinefunction(connect_fn):
                        res = await connect_fn()
                    else:
                        res = await asyncio.to_thread(connect_fn)
                else:
                    res = True

                # Extract status if tuple returned
                if isinstance(res, tuple):
                    check = bool(res[0])
                    reason = res[1] if len(res) > 1 else ""
                else:
                    check = bool(res) if res is not None else True
                    reason = ""

                if check:
                    self._is_connected = True
                    logger.info("[POCKET OPTION CONNECTED] Persistent WebSocket active.")
                    return True
                else:
                    logger.error(f"[POCKET OPTION FAILED] Connection refused. Reason: {reason}")
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

        if "OTC" in clean.upper() and not clean.startswith("#"):
            return f"#{clean}"
        return clean

    async def get_candles(
        self, symbol: str, period_sec: int = 60, count: int = 50
    ) -> List[Dict[str, Any]]:
        """Fetches historical candles asynchronously with fallback retry."""
        if not self._is_connected or not self.client:
            connected = await self.connect()
            if not connected:
                return []

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
            get_candles_fn = getattr(self.client, "get_candles", None)
            if not get_candles_fn:
                logger.error("[POCKET OPTION ERROR] 'get_candles' method missing on client.")
                return []

            if asyncio.iscoroutinefunction(get_candles_fn):
                candles = await get_candles_fn(po_symbol, period_sec, count)
            else:
                candles = await asyncio.to_thread(get_candles_fn, po_symbol, period_sec, count)

            if candles and isinstance(candles, list):
                return candles[-count:]

            # Retry without '#' prefix
            alt_symbol = po_symbol.lstrip("#")
            if alt_symbol != po_symbol:
                if asyncio.iscoroutinefunction(get_candles_fn):
                    candles = await get_candles_fn(alt_symbol, period_sec, count)
                else:
                    candles = await asyncio.to_thread(get_candles_fn, alt_symbol, period_sec, count)

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
        """Returns clean, standardized DataFrame."""
        candles = await self.get_candles(symbol=symbol, period_sec=period_sec, count=count)
        if not candles:
            return None

        df = pd.DataFrame(candles)
        if df.empty:
            return None

        df.columns = [str(col).lower() for col in df.columns]

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
            df = await feed.fetch_candles_df("EURUSD_otc", period_sec=60, count=10)
            if df is not None:
                print(f"DataFrame Shape: {df.shape}")
                print(df.tail(2))

            await feed.close()

    asyncio.run(test_pocket_feed())