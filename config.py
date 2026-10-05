import os
import re
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

# Auto load .env file variables securely
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger("Config")


class Config:
    """Production Configuration Manager for TradingView Signal Bot.
    
    Single source of truth for Webhook Receiver, Dynamic Market Filters,
    Symbol Normalization, and Strategy Settings.
    """

    @staticmethod
    def _get_env_int(key: str, default: int) -> int:
        val = os.getenv(key)
        if not val:
            return default
        try:
            return int(val.strip())
        except ValueError:
            logger.warning(f"Invalid integer for env var '{key}': '{val}'. Falling back to default: {default}")
            return default

    @staticmethod
    def _get_env_float(key: str, default: float) -> float:
        val = os.getenv(key)
        if not val:
            return default
        try:
            return float(val.strip())
        except ValueError:
            logger.warning(f"Invalid float for env var '{key}': '{val}'. Falling back to default: {default}")
            return default

    @staticmethod
    def _get_env_bool(key: str, default: bool) -> bool:
        val = os.getenv(key)
        if not val:
            return default
        return val.strip().lower() in ("true", "1", "t", "yes")

    def __init__(self):
        # --- Environment & Server Setup ---
        self.ENV: str = os.getenv("ENV", "development").lower()
        self.HOST: str = os.getenv("HOST", "0.0.0.0")
        self.PORT: int = self._get_env_int("PORT", 8000)
        
        # Secure Webhook Verification Secret with Guaranteed Fallback
        env_secret = os.getenv("WEBHOOK_SECRET")
        if env_secret and env_secret.strip():
            secret = env_secret.strip()
        else:
            if self.ENV == "production":
                raise ValueError("CRITICAL SECURITY ERROR: 'WEBHOOK_SECRET' environment variable must be set in production!")
            logger.warning("WEBHOOK_SECRET not found in environment. Using secure local fallback.")
            secret = "Emon04+Adiba05"
        self.WEBHOOK_SECRET: str = secret

        # --- Signal & Strategy Hyperparameters ---
        self.DEFAULT_TIMEFRAME: str = os.getenv("DEFAULT_TIMEFRAME", "1m")
        self.MIN_STABILITY_SCORE: float = self._get_env_float("MIN_STABILITY_SCORE", 0.60)
        self.CONFIDENCE_THRESHOLD: float = self._get_env_float("CONFIDENCE_THRESHOLD", 0.75)
        self.MAX_DAILY_SIGNALS: int = self._get_env_int("MAX_DAILY_SIGNALS", 50)
        
        # Global OTC Override Switch
        self.ALLOW_OTC: bool = self._get_env_bool("ALLOW_OTC", True)

        # --- Approved Base Assets (16 Core Pairs) ---
        self.DEFAULT_PAIRS: List[str] = [
            "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD",
            "USDCHF", "NZDUSD", "EURGBP", "EURJPY", "GBPJPY",
            "AUDJPY", "CADCHF", "EURAUD", "GBPAUD", "BTCUSD", "ETHUSD"
        ]

        # Fast set lookup for approved base symbols
        self.APPROVED_BASES: Set[str] = {p.strip().upper() for p in self.DEFAULT_PAIRS}

        # Complete TradingView Symbol Prefix Normalization Map
        self.TV_SYMBOL_MAP: Dict[str, str] = {
            "FX:EURUSD": "EURUSD", "OANDA:EURUSD": "EURUSD",
            "FX:GBPUSD": "GBPUSD", "OANDA:GBPUSD": "GBPUSD",
            "FX:USDJPY": "USDJPY", "OANDA:USDJPY": "USDJPY",
            "FX:AUDUSD": "AUDUSD", "OANDA:AUDUSD": "AUDUSD",
            "FX:USDCAD": "USDCAD", "OANDA:USDCAD": "USDCAD",
            "FX:USDCHF": "USDCHF", "OANDA:USDCHF": "USDCHF",
            "FX:NZDUSD": "NZDUSD", "OANDA:NZDUSD": "NZDUSD",
            "FX:EURGBP": "EURGBP", "OANDA:EURGBP": "EURGBP",
            "FX:EURJPY": "EURJPY", "OANDA:EURJPY": "EURJPY",
            "FX:GBPJPY": "GBPJPY", "OANDA:GBPJPY": "GBPJPY",
            "FX:AUDJPY": "AUDJPY", "OANDA:AUDJPY": "AUDJPY",
            "FX:CADCHF": "CADCHF", "OANDA:CADCHF": "CADCHF",
            "FX:EURAUD": "EURAUD", "OANDA:EURAUD": "EURAUD",
            "FX:GBPAUD": "GBPAUD", "OANDA:GBPAUD": "GBPAUD",
            "BITSTAMP:BTCUSD": "BTCUSD", "BINANCE:BTCUSDT": "BTCUSD",
            "BITSTAMP:ETHUSD": "ETHUSD", "BINANCE:ETHUSDT": "ETHUSD",
        }

        # Extensive Timeframe Mapping (In Seconds)
        self.TIMEFRAME_MAP: Dict[str, int] = {
            "1": 60, "1m": 60, "1min": 60,
            "5": 300, "5m": 300, "5min": 300,
            "10": 600, "10m": 600,
            "15": 900, "15m": 900,
            "30": 1800, "30m": 1800,
            "60": 3600, "1h": 3600, "1hr": 3600, "1hour": 3600,
            "240": 14400, "4h": 14400, "4hr": 14400, "1d": 86400, "1day": 86400, "D": 86400,
        }

    def clean_and_normalize_symbol(self, raw_symbol: str) -> str:
        """Normalizes symbol input by stripping provider prefixes."""
        if not raw_symbol:
            return ""
        
        symbol = raw_symbol.strip().upper()

        if symbol in self.TV_SYMBOL_MAP:
            return self.TV_SYMBOL_MAP[symbol]

        if ":" in symbol:
            symbol = symbol.split(":")[-1]

        clean = re.sub(r'[\s/\-#]', '', symbol)
        return clean

    def is_otc_pair(self, raw_symbol: str) -> bool:
        """Strictly validates if symbol is an OTC asset using standardized regex."""
        if not raw_symbol:
            return False

        clean = self.clean_and_normalize_symbol(raw_symbol)
        
        if re.search(r'(_?OTC)$', clean, flags=re.IGNORECASE):
            base_candidate = re.sub(r'(_?OTC)$', '', clean, flags=re.IGNORECASE)
            return base_candidate in self.APPROVED_BASES

        return False

    def get_base_symbol(self, raw_symbol: str) -> str:
        """Extracts base currency pair by stripping OTC suffix using unified regex."""
        clean = self.clean_and_normalize_symbol(raw_symbol)
        if self.is_otc_pair(raw_symbol):
            return re.sub(r'(_?OTC)$', '', clean, flags=re.IGNORECASE)
        return clean

    def is_approved_pair(self, asset_name: str, override_allow_otc: Optional[bool] = None) -> bool:
        """Validates asset based on configuration."""
        if not asset_name:
            return False

        is_otc = self.is_otc_pair(asset_name)
        effective_allow_otc = override_allow_otc if override_allow_otc is not None else self.ALLOW_OTC

        if is_otc and not effective_allow_otc:
            return False

        base_clean = self.get_base_symbol(asset_name)
        return base_clean in self.APPROVED_BASES


# Standard Singleton Instance
settings = Config()
config = settings
ConfigInstance = settings