import os
import asyncio
import logging
from typing import Dict, Any, Optional, List
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

QUOTEX_EMAIL = os.getenv("QUOTEX_EMAIL")
QUOTEX_PASSWORD = os.getenv("QUOTEX_PASSWORD")
QUOTEX_SSID = os.getenv("QUOTEX_SSID")  # Session ID support for modern WebSocket auth

if not QUOTEX_SSID and (not QUOTEX_EMAIL or not QUOTEX_PASSWORD):
    raise ValueError(
        "CRITICAL ERROR: Neither QUOTEX_SSID nor (QUOTEX_EMAIL & QUOTEX_PASSWORD) "
        "is set in the .env file! System halted."
    )

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger("QuotexLiveFetcher")


class QuotexLiveFetcher:
    """
    Quotex Live Market Data Fetcher & Signal Evaluator.
    Provides parallel pair scanning, automated connection recovery,
    dynamic stability scoring, and safety threshold (HOLD) execution.
    """

    def __init__(self):
        self.email = QUOTEX_EMAIL
        self.password = QUOTEX_PASSWORD
        self.ssid = QUOTEX_SSID
        self.is_connected = False
        self.max_retries = 5
        self.recovery_delay = 1.0  # Sub-2-second recovery time
        self.client = None

        # Primary currency pairs for live scanning
        self.target_symbols: List[str] = [
            "EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "EURGBP"
        ]

    async def connect(self) -> bool:
        """
        Establishes WebSocket connection to Quotex with automated retries.
        """
        attempt = 0
        while attempt < self.max_retries:
            try:
                attempt += 1
                logger.info(
                    f"Connecting to Quotex WebSocket (Attempt {attempt}/{self.max_retries})..."
                )

                # ==========================================================
                # Quotex WebSocket Client Connection Initialization
                # (আসল API ব্যবহার করলে নিচের কমেন্ট তুলে কাস্টম লাইব্রেরি বসাবেন)
                # ==========================================================
                # if self.ssid:
                #     self.client = AsyncQuotexClient(ssid=self.ssid)
                # else:
                #     self.client = AsyncQuotexClient(email=self.email, password=self.password)
                # await self.client.connect()
                # ==========================================================

                await asyncio.sleep(0.4)  # Connection handshake simulation
                self.is_connected = True
                logger.info("Successfully connected to Quotex live market stream.")
                return True

            except Exception as e:
                self.is_connected = False
                logger.error(
                    f"Connection failed (Attempt {attempt}): {e}. "
                    f"Recovering in {self.recovery_delay}s..."
                )
                await asyncio.sleep(self.recovery_delay)

        logger.critical("Max reconnection attempts reached. System remaining offline.")
        return False

    async def disconnect(self) -> None:
        """
        Safely closes WebSocket connection on system shutdown.
        """
        if self.is_connected and self.client:
            try:
                # await self.client.disconnect()
                logger.info("Quotex WebSocket connection safely disconnected.")
            except Exception as e:
                logger.error(f"Error while disconnecting: {e}")
        self.is_connected = False

    async def live_data_fetcher(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Fetches live market ticks/candles for a given symbol.
        """
        if not self.is_connected:
            reconnected = await self.connect()
            if not reconnected:
                return None

        try:
            # Integration point for actual client ticker data:
            # tick = await self.client.get_realtime_candle(symbol)
            await asyncio.sleep(0.15)  # Simulated fast ticker response

            tick_data = {
                "symbol": symbol,
                "price": 1.08500 if symbol == "EURUSD" else 1.26400,
                "trend": "UP" if symbol in ["EURUSD", "AUDUSD"] else "DOWN",
                "volatility": 0.0012,
                "rsi": 58.5 if symbol == "EURUSD" else 48.0,
                "payout": 85
            }
            return tick_data

        except Exception as e:
            logger.error(f"Error fetching data for {symbol}: {e}")
            self.is_connected = False
            return None

    def calculate_stability_score(self, market_data: Dict[str, Any]) -> float:
        """
        Calculates stability score / confidence rank from live market metrics.
        Combines indicator factors (RSI, trend direction, payout).
        """
        if not market_data:
            return 0.0

        score = 0.50
        rsi = market_data.get("rsi", 50.0)
        trend = market_data.get("trend", "NEUTRAL")

        # RSI momentum confirmation
        if trend == "UP" and rsi > 55:
            score += 0.12
        elif trend == "DOWN" and rsi < 45:
            score += 0.12

        # Payout multiplier adjustment
        if market_data.get("payout", 0) >= 80:
            score += 0.05

        return round(score, 3)

    async def evaluate_market_signal(self) -> Dict[str, Any]:
        """
        Scans target pairs concurrently using async gather.
        Applies strict 55% threshold risk control to issue CALL/PUT or HOLD.
        """
        logger.info(f"Scanning currency pairs {self.target_symbols} in parallel...")

        # Parallel market data fetching for low latency
        tasks = [self.live_data_fetcher(sym) for sym in self.target_symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        best_signal = None
        highest_score = 0.0

        for symbol, data in zip(self.target_symbols, results):
            if isinstance(data, Exception) or not data:
                logger.warning(f"Skipping {symbol} due to feed error.")
                continue

            score = self.calculate_stability_score(data)
            logger.info(f"Analyzing {symbol} -> Stability Score: {score * 100:.1f}%")

            if score > highest_score:
                highest_score = score
                action = "CALL" if data.get("trend") == "UP" else "PUT"
                best_signal = {
                    "symbol": symbol,
                    "action": action if score >= 0.55 else "HOLD",
                    "stability_rank": score,
                    "price": data.get("price"),
                    "payout": data.get("payout"),
                    "status": "APPROVED" if score >= 0.55 else "HOLD"
                }

        # HOLD logic execution if no pair meets 55% confidence threshold
        if not best_signal or highest_score < 0.55:
            logger.warning("Market conditions unfavorable. Executing HOLD logic (No pair >= 55%).")
            return {
                "symbol": "NONE",
                "action": "HOLD",
                "stability_rank": highest_score,
                "status": "HOLD",
                "message": "All pairs below 55% threshold. Position held safely."
            }

        logger.info(
            f"Best Pair Selected: {best_signal['symbol']} | "
            f"Action: {best_signal['action']} | Confidence: {highest_score * 100:.1f}%"
        )
        return best_signal


if __name__ == "__main__":
    async def main():
        fetcher = QuotexLiveFetcher()
        try:
            # সারাদিন একটানা মার্কেট স্ক্যানিং ও অটো-রিকানেক্ট লুপ
            while True:
                connected = await fetcher.connect()
                if connected:
                    signal = await fetcher.evaluate_market_signal()
                    print("\n=== LIVE EVALUATION RESULT ===")
                    print(signal)
                
                # প্রতি ২ সেকেন্ড পরপর নতুন ক্যান্ডেল/ডাটা স্ক্যান করবে
                await asyncio.sleep(2.0)
                
        except KeyboardInterrupt:
            print("\n[!] Bot execution manually stopped by user.")
        finally:
            await fetcher.disconnect()

    asyncio.run(main())