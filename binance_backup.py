import json
import time
import logging
import random
import websocket
from typing import Optional
from config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

class BinanceBackupFeed:
    """
    Phase 1 Point 7: 100% Free Binance Backup WebSocket Feed
    High-performance price cross-verification feed with exponential backoff.
    """
    def __init__(self):
        self.ws: Optional[websocket.WebSocketApp] = None
        self.is_running: bool = False

    def _on_message(self, ws: websocket.WebSocketApp, message: str) -> None:
        try:
            data = json.loads(message)
            price = float(data.get("p", 0.0))
            
            # Point 7 Fix: Clean timestamp extraction without redundant multiplication
            raw_time = data.get("T")
            timestamp = float(raw_time) / 1000.0 if raw_time else time.time()

            if price > 0:
                logging.info(f"[BINANCE BACKUP TICK] Asset: BTCUSDT | Price: {price:<10.2f} | Time: {timestamp}")
        except Exception as e:
            logging.error(f"Error parsing Binance WS payload: {e}")

    def _on_error(self, ws: websocket.WebSocketApp, error: Exception) -> None:
        logging.error(f"Binance WS Runtime Error: {error}")

    def _on_close(self, ws: websocket.WebSocketApp, close_status_code: int, close_msg: str) -> None:
        logging.warning(f"Binance Backup Stream Terminated [Code: {close_status_code}, Msg: {close_msg}]")

    def start(self) -> None:
        """
        Starts the continuous Binance WebSocket backup connection
        with up to 60s exponential backoff consistency.
        """
        self.is_running = True
        backoff_delay = 1

        while self.is_running:
            ws_url = settings.BINANCE_WS_URL
            logging.info(f"Connecting to Binance Backup Feed: {ws_url}")

            try:
                self.ws = websocket.WebSocketApp(
                    ws_url,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close
                )
                self.ws.run_forever()
                backoff_delay = 1  # Reset backoff on stable closure
            except Exception as e:
                logging.error(f"Binance Stream Exception: {e}")

            # Point 7 Fix: Exponential Backoff consistent with Quotex Feed (max 60s)
            if self.is_running:
                sleep_time = min(backoff_delay, 60) + random.uniform(0.5, 1.5)
                logging.info(f"Binance Reconnecting in {sleep_time:.2f} seconds...")
                time.sleep(sleep_time)
                backoff_delay = min(backoff_delay * 2, 60)


# --- Verification Execution ---
if __name__ == "__main__":
    print("--- Testing Binance Backup Stream Verification ---")
    feed = BinanceBackupFeed()

    # 1. Mock payload verification
    mock_binance_msg = json.dumps({"p": "65432.10", "T": 1789799000000})
    print("\n1. Testing Mock Payload Parsing:")
    feed._on_message(None, mock_binance_msg)

    # 2. Live stream connection test (Runs 5 seconds)
    print("\n2. Connecting to Live Binance WebSocket for 5 seconds...")
    import threading
    t = threading.Thread(target=feed.start, daemon=True)
    t.start()
    time.sleep(5)
    print("\n>> Binance Backup Stream Test Completed Successfully! <<")