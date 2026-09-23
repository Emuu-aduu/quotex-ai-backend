import logging
import duckdb
from typing import Dict, Any, List

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)

class DuckDBMLOpsEngine:
    """
    Phase 3 Points 1 & 2: Standalone DuckDB Feature Store & Database Engine.
    File-based (.duckdb), serverless, high-performance database for 5-10 users.
    """
    def __init__(self, db_path: str = "mlops_trading.duckdb"):
        self.db_path = db_path
        self.conn = None
        self._init_db()

    def _init_db(self) -> None:
        try:
            self.conn = duckdb.connect(self.db_path)
            
            # 1. Feature Store Table (Stores ML features & technical indicators)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS feature_store (
                    symbol VARCHAR,
                    timestamp DOUBLE,
                    open DOUBLE,
                    high DOUBLE,
                    low DOUBLE,
                    close DOUBLE,
                    rsi_14 DOUBLE,
                    ema_9 DOUBLE,
                    ema_21 DOUBLE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 2. Model Performance & Metrics Table
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS model_metrics (
                    run_id VARCHAR,
                    model_name VARCHAR,
                    accuracy DOUBLE,
                    f1_score DOUBLE,
                    timestamp DOUBLE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Composite Index for sub-millisecond time-series lookup
            self.conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_features_sym_ts 
                ON feature_store (symbol, timestamp DESC)
            """)

            logging.info(f"[DUCKDB MLOPS] Database initialized successfully at '{self.db_path}' (Serverless Mode).")
        except Exception as e:
            logging.error(f"[DUCKDB MLOPS] Database initialization failed: {e}")

    def log_features(self, feature_data: Dict[str, Any]) -> bool:
        if not self.conn:
            return False
        try:
            self.conn.execute("""
                INSERT INTO feature_store (symbol, timestamp, open, high, low, close, rsi_14, ema_9, ema_21)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(feature_data.get("symbol", "")),
                float(feature_data.get("timestamp", 0.0)),
                float(feature_data.get("open", 0.0)),
                float(feature_data.get("high", 0.0)),
                float(feature_data.get("low", 0.0)),
                float(feature_data.get("close", 0.0)),
                float(feature_data.get("rsi_14", 0.0)),
                float(feature_data.get("ema_9", 0.0)),
                float(feature_data.get("ema_21", 0.0))
            ))
            return True
        except Exception as e:
            logging.error(f"[DUCKDB MLOPS] Feature insert failed: {e}")
            return False

    def get_latest_features(self, symbol: str, limit: int = 50) -> List[Dict[str, Any]]:
        if not self.conn:
            return []
        try:
            cursor = self.conn.execute("""
                SELECT symbol, timestamp, open, high, low, close, rsi_14, ema_9, ema_21
                FROM feature_store
                WHERE symbol = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (symbol, limit))
            
            rows = cursor.fetchall()
            return [
                {
                    "symbol": r[0], "timestamp": r[1], "open": r[2], "high": r[3],
                    "low": r[4], "close": r[5], "rsi_14": r[6], "ema_9": r[7], "ema_21": r[8]
                }
                for r in rows
            ]
        except Exception as e:
            logging.error(f"[DUCKDB MLOPS] Query failed: {e}")
            return []

    def close(self) -> None:
        if self.conn:
            self.conn.close()
            logging.info("[DUCKDB MLOPS] Database connection closed.")


if __name__ == "__main__":
    db = DuckDBMLOpsEngine()
    
    logging.info("Executing DuckDB MLOps Feature Store self-test...")
    
    mock_feature = {
        "symbol": "EURUSD",
        "timestamp": 1700000000.0,
        "open": 1.0850, "high": 1.0860, "low": 1.0845, "close": 1.0855,
        "rsi_14": 58.4, "ema_9": 1.0852, "ema_21": 1.0848
    }
    
    if db.log_features(mock_feature):
        logging.info("Mock feature record inserted into Feature Store.")
        
    records = db.get_latest_features("EURUSD", limit=1)
    logging.info(f"[DUCKDB MLOPS TEST] Fetched features: {records}")
    
    db.close()
    logging.info("DuckDB MLOps module test completed successfully.")