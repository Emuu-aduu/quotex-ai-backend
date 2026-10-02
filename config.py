import os
from typing import Dict, List, Optional

# Auto load .env file variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class Config:
    """Central Production Configuration Manager for Pocket Option Bot.
    
    Acts as the single source of truth for Feed, Strategy Engine, 
    Trust Engine, and WebSockets.
    """

    # --- Environment & Operational Setup ---
    ENV: str = os.getenv("ENV", "production")
    DEMO_MODE: bool = os.getenv("DEMO_MODE", "true").lower() in ("true", "1", "t")
    ALLOW_OTC: bool = os.getenv("ALLOW_OTC", "true").lower() in ("true", "1", "t")
    API_KEY: str = os.getenv("API_KEY", "")

    # --- Pocket Option Credentials ---
    POCKETOPTION_SSID: str = os.getenv("POCKETOPTION_SSID", "")
    POCKETOPTION_EMAIL: str = os.getenv("POCKETOPTION_EMAIL", "") or os.getenv("POCKET_EMAIL", "")
    POCKETOPTION_PASSWORD: str = os.getenv("POCKETOPTION_PASSWORD", "") or os.getenv("POCKET_PASSWORD", "")

    # --- GitHub / TrustEngine Audit Trail Credentials ---
    GITHUB_TOKEN: str = os.getenv("GITHUB_TOKEN", "") or os.getenv("TOKEN", "")
    REPO_OWNER: str = os.getenv("REPO_OWNER", "") or os.getenv("GITHUB_REPO_OWNER", "")
    REPO_NAME: str = os.getenv("REPO_NAME", "") or os.getenv("GITHUB_REPO_NAME", "")
    GITHUB_BRANCH: str = os.getenv("GITHUB_BRANCH", "main")

    # --- Telegram Bot Config ---
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

    # --- Trading Engine & Strategy Hyperparameters ---
    DEFAULT_TIMEFRAME: str = os.getenv("DEFAULT_TIMEFRAME", "1m")
    DEFAULT_CANDLE_COUNT: int = int(os.getenv("DEFAULT_CANDLE_COUNT", "200"))
    MIN_STABILITY_SCORE: float = float(os.getenv("MIN_STABILITY_SCORE", "0.60"))
    CONFIDENCE_THRESHOLD: float = float(os.getenv("CONFIDENCE_THRESHOLD", "0.75"))
    MAX_DAILY_TRADES: int = int(os.getenv("MAX_DAILY_TRADES", "50"))
    MAX_RISK_PER_TRADE: float = float(os.getenv("MAX_RISK_PER_TRADE", "0.02"))  # 2% Risk

    # --- SINGLE SOURCE OF TRUTH: Default Assets List (Live & OTC) ---
    DEFAULT_PAIRS: List[str] = [
        "EURUSD_otc", "GBPUSD_otc", "USDJPY_otc", "AUDCAD_otc", "EURGBP_otc",
        "USDCHF_otc", "NZDUSD_otc", "EURJPY_otc", "GBPJPY_otc", "AUDUSD_otc",
        "USDCAD_otc", "AUDJPY_otc", "CADCHF_otc", "EURAUD_otc", "GBPAUD_otc",
        "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD"
    ]

    # Supported Binance Forex Spot Proxies for Validation/Cross-Verification
    BINANCE_FOREX_MAP: Dict[str, str] = {
        "EURUSD": "EURUSDT",
        "GBPUSD": "GBPUSDT",
        "AUDUSD": "AUDUSDT",
        "NZDUSD": "NZDUSDT",
        "USDCAD": "USDCAD",
        "USDJPY": "USDJPY",
        "BTCUSD": "BTCUSDT",
        "ETHUSD": "ETHUSDT",
    }

    # --- Timeframe Mapping (In Seconds) ---
    TIMEFRAME_MAP: Dict[str, int] = {
        "1m": 60,
        "5m": 300,
        "10m": 600,
        "15m": 900,
        "30m": 1800,
        "1hr": 3600,
    }

    # --- Binance Fallback Config ---
    BINANCE_BASE_WS_URL: str = "wss://stream.binance.com:9443"

    @classmethod
    def clean_and_normalize_symbol(cls, raw_symbol: str) -> str:
        """Cleans and normalizes symbol string across all modules."""
        if not raw_symbol:
            return ""
        return (
            raw_symbol.strip()
            .replace(" ", "")
            .replace("/", "")
            .replace("-", "")
            .replace("#", "")
        )

    @classmethod
    def get_base_symbol(cls, raw_symbol: str) -> str:
        """Extracts core pair name removing OTC suffixes."""
        clean = cls.clean_and_normalize_symbol(raw_symbol).upper()
        for suffix in ["_OTC", "OTC"]:
            if clean.endswith(suffix):
                clean = clean[:-len(suffix)]
        return clean.strip("_")

    @classmethod
    def is_approved_pair(cls, asset_name: str, allow_otc: Optional[bool] = None) -> bool:
        """Validates if asset is approved by configuration."""
        if not asset_name:
            return False

        clean_symbol = cls.clean_and_normalize_symbol(asset_name)
        check_otc = allow_otc if allow_otc is not None else cls.ALLOW_OTC

        # Security check: Block OTC if disabled in config
        if "OTC" in clean_symbol.upper() and not check_otc:
            return False

        base_clean = cls.get_base_symbol(clean_symbol)
        approved_bases = {cls.get_base_symbol(p) for p in cls.DEFAULT_PAIRS}
        
        return base_clean in approved_bases

    is_approved_live_pair = is_approved_pair

    @classmethod
    def get_binance_stream_url(cls, symbols: Optional[List[str]] = None) -> str:
        """Generates Binance WebSocket stream URL for forex/crypto proxies."""
        if not symbols:
            symbols = ["BTCUSDT"]

        valid_streams = []
        for raw_s in symbols:
            base_s = cls.get_base_symbol(raw_s)
            
            if base_s.endswith("USDT") or base_s.endswith("BUSD"):
                valid_streams.append(base_s.lower())
            elif base_s in cls.BINANCE_FOREX_MAP:
                valid_streams.append(cls.BINANCE_FOREX_MAP[base_s].lower())

        if not valid_streams:
            valid_streams = ["btcusdt"]

        # Deduplicate streams
        valid_streams = list(set(valid_streams))

        if len(valid_streams) == 1:
            return f"{cls.BINANCE_BASE_WS_URL}/ws/{valid_streams[0]}@trade"
        else:
            streams_str = "/".join([f"{s}@trade" for s in valid_streams])
            return f"{cls.BINANCE_BASE_WS_URL}/stream?streams={streams_str}"


# Standard Singleton Instance
settings = Config()

# Import Safety Aliases (Prevents ImportError across different coding conventions)
config = settings
ConfigInstance = settings


if __name__ == "__main__":
    print("--- Testing Refined Config Engine ---")
    print(f"Environment: {settings.ENV}")
    print(f"Allow OTC Config: {settings.ALLOW_OTC}")
    print(f"Demo Mode: {settings.DEMO_MODE}")
    print(f"Is 'EURUSD_otc' approved: {settings.is_approved_pair('EURUSD_otc')}")
    print(f"Base Symbol 'EURUSD_otc': {settings.get_base_symbol('EURUSD_otc')}")
    print(f"Binance WS Stream: {settings.get_binance_stream_url(['EURUSD_otc', 'GBPUSD_otc'])}")