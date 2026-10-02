import asyncio
import logging
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd

from config import settings

logger = logging.getLogger(__name__)


class StrategyEngine:
    """Enterprise-Grade Technical Analysis & Signal Generation Engine

    Optimized for Pocket Option High-Frequency Binary/Digital Options.
    """

    TIMEFRAME_MAP = settings.TIMEFRAME_MAP

    def __init__(self, fetcher: Optional[Any] = None):
        self.fetcher = fetcher
        # Single Source of Truth from Config
        self.default_pairs = settings.DEFAULT_PAIRS

    @staticmethod
    def calculate_rsi(close_series: pd.Series, window: int = 14) -> pd.Series:
        """Calculates RSI handling zero-loss / zero-gain edge cases safely."""
        delta = close_series.diff()
        gain = delta.clip(lower=0.0)
        loss = -delta.clip(upper=0.0)

        avg_gain = gain.ewm(alpha=1.0 / window, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1.0 / window, adjust=False).mean()

        # Fix #1: Handle division by zero properly without resetting strong trend to 50
        rs = np.where(avg_loss != 0, avg_gain / avg_loss, np.nan)
        rsi = np.where(
            np.isnan(rs),
            np.where(avg_gain > 0, 100.0, 50.0),
            100.0 - (100.0 / (1.0 + rs))
        )
        return pd.Series(rsi, index=close_series.index).fillna(50.0)

    @staticmethod
    def calculate_ema(close_series: pd.Series, window: int) -> pd.Series:
        return close_series.ewm(span=window, adjust=False).mean()

    @staticmethod
    def calculate_bollinger_bands(
        close_series: pd.Series, window: int = 20, num_std: float = 2.0
    ) -> Dict[str, pd.Series]:
        sma = close_series.rolling(window=window).mean()
        std = close_series.rolling(window=window).std()
        upper = sma + (std * num_std)
        lower = sma - (std * num_std)
        return {"middle": sma, "upper": upper, "lower": lower}

    def _detect_price_action_reversal(self, df: pd.DataFrame) -> str:
        """Detects reversal patterns on the last CLOSED candle (iloc[-2])."""
        if len(df) < 3:
            return "NEUTRAL"

        # Fix #3: Inspect completed candle (iloc[-2]) instead of active unclosed bar (iloc[-1])
        closed_bar = df.iloc[-2]
        
        open_p = float(closed_bar["open"])
        close_p = float(closed_bar["close"])
        high_p = float(closed_bar["high"])
        low_p = float(closed_bar["low"])

        body = abs(close_p - open_p)
        candle_range = high_p - low_p

        if candle_range == 0 or body == 0:
            return "NEUTRAL"

        upper_wick = high_p - max(open_p, close_p)
        lower_wick = min(open_p, close_p) - low_p

        if lower_wick >= (2 * body) and upper_wick <= (0.5 * body):
            return "BULLISH_REVERSAL"

        if upper_wick >= (2 * body) and lower_wick <= (0.5 * body):
            return "BEARISH_REVERSAL"

        return "NEUTRAL"

    async def _fetch_symbol_dataframe(
        self, symbol: str, timeframe_sec: int, count: int = 60
    ) -> Optional[pd.DataFrame]:
        if not self.fetcher:
            return None

        df: Optional[pd.DataFrame] = None

        try:
            if hasattr(self.fetcher, "fetch_candles_df"):
                df = await self.fetcher.fetch_candles_df(
                    symbol=symbol, period_sec=timeframe_sec, count=count
                )
            elif hasattr(self.fetcher, "get_candles"):
                raw_candles = await self.fetcher.get_candles(
                    symbol=symbol, period_sec=timeframe_sec, count=count
                )
                if isinstance(raw_candles, pd.DataFrame):
                    df = raw_candles
                elif isinstance(raw_candles, list) and raw_candles:
                    df = pd.DataFrame(raw_candles)

            if df is None or df.empty:
                return None

            df.columns = [str(col).lower() for col in df.columns]

            required = ["open", "high", "low", "close"]
            if not all(col in df.columns for col in required):
                logger.warning(f"[{symbol}] Missing required candle columns in fetched DataFrame.")
                return None

            return df

        except Exception as err:
            logger.debug(f"Failed to fetch DataFrame for {symbol}: {err}")
            return None

    def analyze_dataframe(self, df: pd.DataFrame) -> Dict[str, Any]:
        if df is None or len(df) < 30:
            return {
                "action": "HOLD",
                "direction": "NEUTRAL",
                "score_num": 0.0,
                "score_str": "0.0/10",
                "reason": "Insufficient candle data (<30 required)",
            }

        close = df["close"].astype(float)

        rsi_series = self.calculate_rsi(close, window=14)
        ema20_series = self.calculate_ema(close, window=20)
        ema50_series = self.calculate_ema(close, window=50)
        bb = self.calculate_bollinger_bands(close, window=20, num_std=2.0)

        last_price = close.iloc[-1]
        last_rsi = rsi_series.iloc[-1]
        last_ema20 = ema20_series.iloc[-1]
        last_ema50 = ema50_series.iloc[-1]
        bb_upper = bb["upper"].iloc[-1]
        bb_lower = bb["lower"].iloc[-1]

        if any(
            pd.isna(v)
            for v in [last_price, last_rsi, last_ema20, last_ema50, bb_upper, bb_lower]
        ):
            return {
                "action": "HOLD",
                "direction": "NEUTRAL",
                "score_num": 0.0,
                "score_str": "0.0/10",
                "reason": "Indicator outputs contained NaN values",
            }

        price_action = self._detect_price_action_reversal(df)

        call_score = 0.0
        put_score = 0.0
        
        # Fix #2: Separate call and put reasons to prevent signal narrative mix-ups
        call_reasons: List[str] = []
        put_reasons: List[str] = []

        # 1. RSI Score Allocation
        if last_rsi <= 28.0:
            call_score += 3.0
            call_reasons.append(f"Extreme Oversold RSI ({last_rsi:.1f})")
        elif last_rsi <= 35.0:
            call_score += 2.0
            call_reasons.append(f"Oversold RSI ({last_rsi:.1f})")
        elif last_rsi >= 72.0:
            put_score += 3.0
            put_reasons.append(f"Extreme Overbought RSI ({last_rsi:.1f})")
        elif last_rsi >= 65.0:
            put_score += 2.0
            put_reasons.append(f"Overbought RSI ({last_rsi:.1f})")

        # 2. Bollinger Band Boundaries
        if last_price <= bb_lower:
            call_score += 3.0
            call_reasons.append("Price pierced Lower Bollinger Band")
        elif last_price >= bb_upper:
            put_score += 3.0
            put_reasons.append("Price pierced Upper Bollinger Band")

        # 3. EMA Trend Confirmation
        if last_price > last_ema20 > last_ema50:
            call_score += 2.0
            call_reasons.append("Uptrend Confluence (Price > EMA20 > EMA50)")
        elif last_price < last_ema20 < last_ema50:
            put_score += 2.0
            put_reasons.append("Downtrend Confluence (Price < EMA20 < EMA50)")

        # 4. Price Action Reversals
        if price_action == "BULLISH_REVERSAL":
            call_score += 2.0
            call_reasons.append("Bullish Pinbar Reversal Candle")
        elif price_action == "BEARISH_REVERSAL":
            put_score += 2.0
            put_reasons.append("Bearish Shooting Star Reversal Candle")

        MIN_THRESHOLD = 6.5

        if call_score >= MIN_THRESHOLD and call_score > put_score:
            return {
                "action": "CALL",
                "direction": "CALL",
                "score_num": call_score,
                "score_str": f"{call_score:.1f}/10",
                "reason": " + ".join(call_reasons[:3]),
            }
        elif put_score >= MIN_THRESHOLD and put_score > call_score:
            return {
                "action": "PUT",
                "direction": "PUT",
                "score_num": put_score,
                "score_str": f"{put_score:.1f}/10",
                "reason": " + ".join(put_reasons[:3]),
            }

        max_score = max(call_score, put_score)
        return {
            "action": "HOLD",
            "direction": "NEUTRAL",
            "score_num": max_score,
            "score_str": f"{max_score:.1f}/10",
            "reason": f"Insufficient confluence confirmation ({max_score:.1f}/10)",
        }

    async def _analyze_single_symbol_task(
        self, symbol: str, timeframe_sec: int
    ) -> Optional[Dict[str, Any]]:
        try:
            df = await self._fetch_symbol_dataframe(symbol, timeframe_sec)
            if df is None:
                return None

            analysis = self.analyze_dataframe(df)

            if analysis["action"] in ["CALL", "PUT"]:
                return {
                    "status": "SIGNAL",
                    "symbol": symbol,
                    "action": analysis["action"],
                    "direction": analysis["direction"],
                    "score": analysis["score_str"],
                    "score_num": analysis["score_num"],
                    "reason": analysis["reason"],
                }
        except Exception as err:
            logger.debug(f"Error scanning pair {symbol}: {err}")
        return None

    async def scan_best_stable_market(self, timeframe: str = "1m") -> Dict[str, Any]:
        try:
            if not self.fetcher:
                return {
                    "status": "NO_SIGNAL",
                    "action": "HOLD",
                    "reason": "Market fetcher instance is offline or missing",
                }

            timeframe_sec = self.TIMEFRAME_MAP.get(timeframe, 60)

            target_symbols = self.default_pairs
            if hasattr(self.fetcher, "get_active_symbols") and callable(self.fetcher.get_active_symbols):
                active = await self.fetcher.get_active_symbols()
                if active:
                    target_symbols = active
            elif getattr(self.fetcher, "active_symbols", None):
                target_symbols = self.fetcher.active_symbols

            tasks = [
                self._analyze_single_symbol_task(symbol, timeframe_sec)
                for symbol in target_symbols
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            valid_signals = [
                r for r in results if isinstance(r, dict) and r.get("status") == "SIGNAL"
            ]

            if not valid_signals:
                return {
                    "status": "NO_SIGNAL",
                    "action": "HOLD",
                    "reason": "65%+ confirmation pawa jayni across scanned pairs",
                }

            best_signal = max(valid_signals, key=lambda x: x.get("score_num", 0.0))
            best_signal["timeframe"] = timeframe

            logger.info(
                f"Selected Best Signal: {best_signal['symbol']} ({best_signal['action']}) - Score: {best_signal['score']}"
            )
            return best_signal

        except Exception as err:
            logger.error(f"Strategy Engine Critical Error: {err}", exc_info=True)
            return {
                "status": "NO_SIGNAL",
                "action": "HOLD",
                "reason": f"Strategy Engine Exception: {str(err)}",
            }