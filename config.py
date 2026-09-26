import os


class Config:
    # --- Quotex Credentials ---
    QUOTEX_EMAIL: str = os.getenv("QUOTEX_EMAIL", "")
    QUOTEX_PASSWORD: str = os.getenv("QUOTEX_PASSWORD", "")

    # --- Approved Assets (Live Market Pairs Only) ---
    APPROVED_LIVE_PAIRS: set[str] = {
        "EURUSD", "GBPJPY", "USDJPY", "GBPUSD", "AUDUSD",
        "USDCAD", "USDCHF", "EURGBP", "EURJPY", "AUDJPY",
        "NZDUSD", "EURAUD", "GBPCAD", "EURCAD", "AUDCAD"
    }

    # --- Timeframe Mapping (In Seconds) ---
    TIMEFRAME_MAP: dict[str, int] = {
        "1m": 60,
        "5m": 300,
        "10m": 600,
        "15m": 900,
        "30m": 1800,
        "1hr": 3600,
    }

    # --- Phase 1 Parameters (Binance Fallback) ---
    BINANCE_BASE_WS_URL: str = "wss://stream.binance.com:9443"
    BINANCE_WS_URL: str = "wss://stream.binance.com:9443/ws/btcusdt@trade"
    PROXIES: list[str] = []

    # --- Multi-Pair Dynamic Binance URL Builder ---
    @classmethod
    def get_binance_stream_url(cls, symbols: list[str] = None) -> str:
        if not symbols:
            symbols = ["BTCUSDT"]
            
        clean_symbols = [cls.clean_and_normalize_symbol(s).lower() for s in symbols]
        
        if len(clean_symbols) == 1:
            return f"{cls.BINANCE_BASE_WS_URL}/ws/{clean_symbols[0]}@trade"
        else:
            streams = "/".join([f"{s}@trade" for s in clean_symbols])
            return f"{cls.BINANCE_BASE_WS_URL}/stream?streams={streams}"
            
    # --- Phase 2 Parameters ---
    UPSTASH_REDIS_URL: str = os.getenv("UPSTASH_REDIS_URL", "")
    UPSTASH_REDIS_TOKEN: str = os.getenv("UPSTASH_REDIS_TOKEN", "")
    FCM_CREDENTIALS_FILE: str = "fcm_credentials.json"

    @classmethod
    def clean_and_normalize_symbol(cls, raw_symbol: str) -> str:
        if not raw_symbol:
            return ""
        return raw_symbol.upper().replace(" ", "").replace("/", "").replace("-", "").replace("_", "")

    @classmethod
    def is_approved_live_pair(cls, asset_name: str) -> bool:
        if not asset_name:
            return False
        upper_raw = asset_name.upper()
        # OTC Pair Blocked
        if "OTC" in upper_raw:
            return False
        clean_symbol = cls.clean_and_normalize_symbol(asset_name)
        base_symbol = clean_symbol.split(".")[0]
        return base_symbol in cls.APPROVED_LIVE_PAIRS


settings = Config()