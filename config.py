class Config:
    # --- Phase 1 Parameters ---
    BINANCE_BASE_WS_URL: str = "wss://stream.binance.com:9443"
    BINANCE_WS_URL: str = "wss://stream.binance.com:9443/ws/btcusdt@trade"  # Backward compatibility fallback
    
    PROXIES: list[str] = []
    APPROVED_LIVE_PAIRS: set[str] = {
        "EURUSD", "GBPJPY", "USDJPY", "GBPUSD", "AUDUSD",
        "USDCAD", "USDCHF", "EURGBP", "EURJPY", "AUDJPY",
        "NZDUSD", "EURAUD", "GBPCAD", "EURCAD", "AUDCAD"
    }

    # --- Multi-Pair Dynamic Binance URL Builder ---
    @classmethod
    def get_binance_stream_url(cls, symbols: list[str] = None) -> str:
        """
        Dynamically generates Binance WebSocket URL for single or combined multi-pair streams.
        Example single: 'btcusdt@trade'
        Example multi: 'stream?streams=btcusdt@trade/eurusdt@trade'
        """
        if not symbols:
            symbols = ["BTCUSDT"]
            
        clean_symbols = [cls.clean_and_normalize_symbol(s).lower() for s in symbols]
        
        if len(clean_symbols) == 1:
            return f"{cls.BINANCE_BASE_WS_URL}/ws/{clean_symbols[0]}@trade"
        else:
            streams = "/".join([f"{s}@trade" for s in clean_symbols])
            return f"{cls.BINANCE_BASE_WS_URL}/stream?streams={streams}"
            
    # --- Phase 2 Parameters ---
    UPSTASH_REDIS_URL: str = ""
    UPSTASH_REDIS_TOKEN: str = ""
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
        if "OTC" in upper_raw:
            return False
        clean_symbol = cls.clean_and_normalize_symbol(asset_name)
        base_symbol = clean_symbol.split(".")[0]
        return base_symbol in cls.APPROVED_LIVE_PAIRS


settings = Config()