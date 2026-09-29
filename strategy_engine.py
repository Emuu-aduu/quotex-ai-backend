import asyncio
import logging
import random
import time
from typing import Any, Dict, List, Optional
import pandas as pd
import ta

from live_fetcher import QuotexLiveFetcher

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("StrategyEngine")


class StrategyEngine:

    def __init__(
        self, 
        fetcher: Optional[QuotexLiveFetcher] = None, 
        min_score_threshold: int = 7, 
        spread_penalty_weight: float = 0.1
    ):
        self.min_score_threshold = min_score_threshold
        self.spread_penalty_weight = spread_penalty_weight
        # Double fetcher fix: Share fetcher instance to prevent IP block
        self.fetcher = fetcher if fetcher is not None else QuotexLiveFetcher()
        self.market_pairs = ["EUR/USD", "GBP/USD", "AUD/USD", "USD/JPY", "EUR/GBP"]

    def _check_wick_and_stability(self, df: pd.DataFrame) -> bool:
        if df.empty or len(df) < 5:
            return False
        
        close_prices = df['close']
        price_diff = close_prices.iloc[-1] - close_prices.iloc[-2]
        if abs(price_diff) <= 0.00001:
            return False

        recent_volatility = close_prices.tail(5).std()
        if recent_volatility > 0.005:  
            return False
            
        return True

    def _calculate_indicators(self, df: pd.DataFrame) -> Optional[Dict[str, float]]:
        if df is None or len(df) < 30:
            return None

        close = df['close']
        ema9 = ta.ema(close, length=9)
        ema21 = ta.ema(close, length=21)
        rsi = ta.rsi(close, length=14)
        bb = ta.bbands(close, length=20, std=2)
        macd_df = ta.macd(close, fast=12, slow=26, signal=9)

        if ema9 is None or ema21 is None or rsi is None or bb is None or macd_df is None:
            return None

        return {
            "ema9": ema9.iloc[-1],
            "ema21": ema21.iloc[-1],
            "rsi": rsi.iloc[-1],
            "lower_bb": bb['BBL_20_2.0'].iloc[-1],
            "upper_bb": bb['BBU_20_2.0'].iloc[-1],
            "sma20": bb['BBM_20_2.0'].iloc[-1],
            "macd": macd_df['MACD_12_26_9'].iloc[-1],
            "macd_signal": macd_df['MACDs_12_26_9'].iloc[-1]
        }

    async def evaluate_market_signal(self, symbol: str, timeframe: str = "1m") -> Dict[str, Any]:
        try:
            candles = []
            if hasattr(self.fetcher, "get_candles"):
                candles = await self.fetcher.get_candles(symbol, timeframe, limit=100)
            elif hasattr(self.fetcher, "fetch_candles"):
                candles = await self.fetcher.fetch_candles(symbol, timeframe=timeframe, count=100)
            
            if not candles or not isinstance(candles, list):
                raw_data = await self.fetcher.live_data_fetcher(symbol)
                current_price = raw_data.get("price", 1.0850) if raw_data else 1.0850
                df = pd.DataFrame({'close': [current_price] * 35})
            else:
                df = pd.DataFrame(candles)
                if 'close' not in df.columns and 'price' in df.columns:
                    df['close'] = df['price']

            if len(df) < 30:
                return {
                    "symbol": symbol,
                    "status": "NO_SIGNAL",
                    "action": "HOLD",
                    "direction": "NONE",
                    "score": "0/10",
                    "confidence": 0.0,
                    "stability_rank": 0,
                    "reason": "Insufficient candle history data",
                }

            current_price = df['close'].iloc[-1]
            prev_price = df['close'].iloc[-2]
            price_diff = current_price - prev_price

            if not self._check_wick_and_stability(df):
                return {
                    "symbol": symbol,
                    "status": "NO_SIGNAL",
                    "action": "HOLD",
                    "direction": "NONE",
                    "score": "0/10",
                    "confidence": 0.0,
                    "stability_rank": 0,
                    "reason": "Unstable market or wick anomaly detected",
                }

            indicators = self._calculate_indicators(df)
            if not indicators:
                return {
                    "symbol": symbol,
                    "status": "NO_SIGNAL",
                    "action": "HOLD",
                    "direction": "NONE",
                    "score": "0/10",
                    "confidence": 0.0,
                    "stability_rank": 0,
                    "reason": "Indicator calculation failed",
                }

            if price_diff > 0 and indicators["ema9"] >= indicators["ema21"]:
                direction = "UP"
                action = "CALL"
            elif price_diff < 0 and indicators["ema9"] <= indicators["ema21"]:
                direction = "DOWN"
                action = "PUT"
            else:
                direction = "UP" if indicators["ema9"] > indicators["ema21"] else "DOWN"
                action = "CALL" if direction == "UP" else "PUT"

            score = 0
            total_rules = 10

            ema9 = indicators["ema9"]
            ema21 = indicators["ema21"]
            rsi = indicators["rsi"]
            macd = indicators["macd"]
            signal_line = indicators["macd_signal"]
            upper_bb = indicators["upper_bb"]
            lower_bb = indicators["lower_bb"]

            if direction == "UP":
                if ema9 > ema21: score += 2
                if 40 <= rsi <= 68: score += 2
                elif rsi < 40: score += 1
                if macd > signal_line: score += 2
                if current_price <= upper_bb: score += 2
                if price_diff > 0: score += 2
            else:
                if ema9 < ema21: score += 2
                if 32 <= rsi <= 60: score += 2
                elif rsi > 60: score += 1
                if macd < signal_line: score += 2
                if current_price >= lower_bb: score += 2
                if price_diff < 0: score += 2

            score = min(max(score, 0), total_rules)

            if score < self.min_score_threshold:
                return {
                    "symbol": symbol,
                    "status": "NO_SIGNAL",
                    "action": "HOLD",
                    "direction": "NONE",
                    "score": f"{score}/{total_rules}",
                    "confidence": 0.0,
                    "stability_rank": score,
                    "reason": f"Confluence score {score}/{total_rules} below threshold {self.min_score_threshold}",
                }

            confidence = round((score / total_rules) * 100.0, 1)

            return {
                "symbol": symbol,
                "status": "SIGNAL",
                "action": action,
                "direction": direction,
                "score": f"{score}/{total_rules}",
                "confidence": confidence,
                "stability_rank": score,
            }

        except Exception as e:
            logger.error(f"Error evaluating symbol {symbol}: {e}")
            return {
                "symbol": symbol,
                "status": "NO_SIGNAL",
                "action": "HOLD",
                "direction": "NONE",
                "score": "0/10",
                "confidence": 0.0,
                "stability_rank": 0,
                "reason": f"Fetch error: {str(e)}",
            }

    async def scan_best_stable_market(self, timeframe: str = "1m") -> Dict[str, Any]:
        try:
            await self.fetcher.connect()
        except Exception as e:
            logger.warning(f"Fetcher connection warning: {e}")

        best_signal: Optional[Dict[str, Any]] = None
        max_score = -1

        for symbol in self.market_pairs:
            signal = await self.evaluate_market_signal(symbol, timeframe=timeframe)

            if signal.get("status") == "SIGNAL":
                rank = signal.get("stability_rank", 0)
                if rank > max_score:
                    max_score = rank
                    best_signal = signal

        if not best_signal:
            return {
                "symbol": "EUR/USD",
                "status": "NO_SIGNAL",
                "action": "HOLD",
                "direction": "NONE",
                "score": "0/10",
                "confidence": 0.0,
                "stability_rank": 0,
                "reason": "65%+ indicator confirmation not met",
            }

        return best_signal