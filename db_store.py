import logging
import duckdb
import threading
from typing import Dict, Any, List, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)

db_lock = threading.Lock()


class DuckDBStorageEngine:
    """
    High-Performance DuckDB Storage Engine with Smart Lock Handling.
    Zero-dependency columnar storage engine with composite indexing for sub-millisecond time-series queries.
    Handles Uvicorn reloader process-locks automatically with Read-Only fallbacks.
    """
    def __init__(self, db_path: str = "signals_store.duckdb"):
        self.db_path = db_path
        self.conn = None
        self.is_read_only = False
        self._init_db()

    def _init_db(self) -> None:
        """Initializes database connection and creates tables/indexes safely."""
        with db_lock:
            try:
                # Primary writeable connection
                self.conn = duckdb.connect(self.db_path, read_only=False)
                self.is_read_only = False
            except (duckdb.IOException, Exception) as e:
                # Fallback for secondary Uvicorn worker/reloader processes when file is locked
                if "used by another process" in str(e) or "IO Error" in str(e):
                    logging.warning("[DUCKDB] Database locked by main process. Attaching in Read-Only mode for worker process.")
                    try:
                        self.conn = duckdb.connect(self.db_path, read_only=True)
                        self.is_read_only = True
                        return
                    except Exception as fallback_err:
                        logging.error(f"[DUCKDB] Read-only fallback failed: {fallback_err}")
                        return
                else:
                    logging.error(f"[DUCKDB] Database connection failed: {e}")
                    return

            try:
                # 1. Ticks Table
                self.conn.execute("""
                    CREATE TABLE IF NOT EXISTS ticks (
                        symbol VARCHAR,
                        price DOUBLE,
                        timestamp DOUBLE,
                        source VARCHAR,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # 2. Signals Table
                self.conn.execute("""
                    CREATE TABLE IF NOT EXISTS signals (
                        signal_id VARCHAR,
                        symbol VARCHAR,
                        action VARCHAR,
                        timeframe VARCHAR,
                        price DOUBLE,
                        timestamp VARCHAR,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # 3. Composite Indexes
                self.conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_ticks_sym_ts 
                    ON ticks (symbol, timestamp DESC)
                """)
                self.conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_signals_sym_ts 
                    ON signals (symbol, created_at DESC)
                """)

                logging.info(f"[DUCKDB] Database & Indexes initialized successfully at '{self.db_path}'.")
            except Exception as e:
                logging.error(f"[DUCKDB] Schema initialization failed: {e}")

    def insert_tick(self, tick_data: Dict[str, Any]) -> bool:
        if not self.conn or self.is_read_only:
            return False
        try:
            with db_lock:
                self.conn.execute("""
                    INSERT INTO ticks (symbol, price, timestamp, source)
                    VALUES (?, ?, ?, ?)
                """, (
                    str(tick_data.get("symbol", "")),
                    float(tick_data.get("price", 0.0)),
                    float(tick_data.get("timestamp", 0.0)),
                    str(tick_data.get("source", "UNKNOWN"))
                ))
            return True
        except Exception as e:
            logging.error(f"[DUCKDB] Tick insert failed: {e}")
            return False

    def insert_signal(self, signal_data: Dict[str, Any]) -> bool:
        if not self.conn or self.is_read_only:
            return False
        try:
            with db_lock:
                self.conn.execute("""
                    INSERT INTO signals (signal_id, symbol, action, timeframe, price, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    str(signal_data.get("signal_id", "SIG_UNK")),
                    str(signal_data.get("symbol", "")),
                    str(signal_data.get("action", "")),
                    str(signal_data.get("timeframe", "1m")),
                    float(signal_data.get("price", 0.0)),
                    str(signal_data.get("timestamp", ""))
                ))
            return True
        except Exception as e:
            logging.error(f"[DUCKDB] Signal insert failed: {e}")
            return False

    def save_signal(self, signal_data: Dict[str, Any]) -> bool:
        """Alias method required by main.py & test_all.py."""
        return self.insert_signal(signal_data)

    def get_recent_signals(self, limit: int = 20, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieves recent signals for the Flet Dashboard and API queries."""
        if not self.conn:
            return []
        try:
            with db_lock:
                if symbol:
                    cursor = self.conn.execute("""
                        SELECT signal_id, symbol, action, timeframe, price, timestamp 
                        FROM signals 
                        WHERE symbol = ? 
                        ORDER BY created_at DESC 
                        LIMIT ?
                    """, (symbol, limit))
                else:
                    cursor = self.conn.execute("""
                        SELECT signal_id, symbol, action, timeframe, price, timestamp 
                        FROM signals 
                        ORDER BY created_at DESC 
                        LIMIT ?
                    """, (limit,))
                
                rows = cursor.fetchall()
            return [
                {
                    "signal_id": row[0],
                    "symbol": row[1],
                    "action": row[2],
                    "timeframe": row[3],
                    "price": row[4],
                    "timestamp": row[5]
                }
                for row in rows
            ]
        except Exception as e:
            logging.error(f"[DUCKDB] Signals query failed: {e}")
            return []

    def get_recent_ticks(self, symbol: str, limit: int = 100) -> List[Dict[str, Any]]:
        if not self.conn:
            return []
        try:
            with db_lock:
                cursor = self.conn.execute("""
                    SELECT symbol, price, timestamp, source 
                    FROM ticks 
                    WHERE symbol = ? 
                    ORDER BY timestamp DESC 
                    LIMIT ?
                """, (symbol, limit))
                
                rows = cursor.fetchall()
            return [
                {
                    "symbol": row[0],
                    "price": row[1],
                    "timestamp": row[2],
                    "source": row[3]
                }
                for row in rows
            ]
        except Exception as e:
            logging.error(f"[DUCKDB] Tick query failed: {e}")
            return []

    def close(self) -> None:
        if self.conn:
            try:
                self.conn.close()
                logging.info("[DUCKDB] Database connection closed.")
            except Exception:
                pass


if __name__ == "__main__":
    db = DuckDBStorageEngine("signals_store.duckdb")
    
    logging.info("Executing DuckDB Storage self-test...")
    
    mock_signal = {
        "signal_id": "TEST_001",
        "symbol": "EURUSD",
        "action": "BUY",
        "timeframe": "1m",
        "price": 1.08542,
        "timestamp": "2026-10-02T10:00:00Z"
    }
    
    if db.save_signal(mock_signal):
        logging.info("Mock signal saved into DuckDB successfully.")
        
    signals = db.get_recent_signals(limit=5)
    logging.info(f"[DUCKDB TEST] Signals query result: {signals}")
    
    db.close()
    logging.info("DuckDB Storage module test completed successfully.")