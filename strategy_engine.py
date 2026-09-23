import pandas as pd
import logging
from typing import Dict, Any, List, Optional

try:
    from config import settings
except ImportError:
    settings = None

try:
    from indicator_engine import IndicatorEngine
except ImportError:
    IndicatorEngine = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

class StrategyEngine:
    def __init__(self, min_score_threshold: int = 7, spread_penalty_weight: float = 0.1):
        self.min_score_threshold = min_score_threshold
        self.spread_penalty_weight = getattr(settings, "SPREAD_PENALTY_WEIGHT", spread_penalty_weight)
        
        self.market_pairs = [
            "EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CAD",
            "EUR/GBP", "EUR/JPY", "GBP/JPY", "NZD/USD", "USD/CHF",
            "AUD/JPY", "EUR/CAD", "GBP/CAD", "AUD/CAD", "EUR/AUD",
            "GBP/AUD", "CAD/JPY", "CHF/JPY", "NZD/JPY", "EUR/CHF"
        ]

    def _is_otc(self, symbol: str) -> bool:
        return "OTC" in symbol.upper()

    def _check_wick_and_stability(self, df: pd.DataFrame) -> bool:
        if df.empty:
            return False

        latest = df.iloc[-1]
        open_p = latest.get('open', 0)
        close_p = latest.get('close', 0)
        high_p = latest.get('high', 0)
        low_p = latest.get('low', 0)

        body_size = abs(close_p - open_p)
        upper_wick = high_p - max(open_p, close_p)
        lower_wick = min(open_p, close_p) - low_p
        max_wick = max(upper_wick, lower_wick)

        if body_size == 0 or max_wick >= (2 * body_size):
            return False
        return True

    def evaluate_market_signal(
        self, 
        df: pd.DataFrame, 
        symbol: str = "EUR/USD", 
        spread_pips: float = 1.0, 
        is_news_time: bool = False
    ) -> Dict[str, Any]:
        """
        রিয়েল-টাইম ক্যান্ডেল ডেটা এনালাইসিস করে ৭৫% কনফার্মেশন রুল অনুযায়ী সিগন্যাল তৈরি করে।
        """
        if self._is_otc(symbol):
            return {"symbol": symbol, "status": "REJECTED", "reason": "OTC Market Blocked"}

        if df.empty or len(df) < 30:
            return {"symbol": symbol, "status": "REJECTED", "reason": "Insufficient Candle Data"}

        if spread_pips > 3.0:
            return {"symbol": symbol, "status": "REJECTED", "reason": f"High Spread ({spread_pips} pips > 3.0)"}
        
        if is_news_time:
            return {"symbol": symbol, "status": "REJECTED", "reason": "High-Impact News Block"}

        latest = df.iloc[-1]
        if latest.get('is_fake_shadow', False) or not self._check_wick_and_stability(df):
            return {"symbol": symbol, "status": "REJECTED", "reason": "High Volatility / Fake Shadow Wick Block"}

        buy_score = 0
        sell_score = 0
        total_rules = 9

        if IndicatorEngine and hasattr(IndicatorEngine, 'calculate_all'):
            analysis_df = IndicatorEngine.calculate_all(df)
            res = IndicatorEngine.get_final_signal(analysis_df) if hasattr(IndicatorEngine, 'get_final_signal') else {}
            buy_score = res.get('buy_score', 0)
            sell_score = res.get('sell_score', 0)
        else:
            buy_score = int(latest.get('buy_score', 0))
            sell_score = int(latest.get('sell_score', 0))

        if buy_score >= self.min_score_threshold:
            confidence = round((buy_score / total_rules) * 100, 1)
            return {
                "symbol": symbol,
                "status": "SIGNAL",
                "action": "CALL",
                "direction": "UP",
                "score": f"{buy_score}/{total_rules}",
                "confidence": confidence,
                "stability_rank": buy_score - (spread_pips * self.spread_penalty_weight)
            }
        elif sell_score >= self.min_score_threshold:
            confidence = round((sell_score / total_rules) * 100, 1)
            return {
                "symbol": symbol,
                "status": "SIGNAL",
                "action": "PUT",
                "direction": "DOWN",
                "score": f"{sell_score}/{total_rules}",
                "confidence": confidence,
                "stability_rank": sell_score - (spread_pips * self.spread_penalty_weight)
            }
        else:
            return {
                "symbol": symbol,
                "status": "NO_SIGNAL",
                "action": "HOLD",
                "reason": f"Confirmation below 75% threshold (Buy: {buy_score}/9, Sell: {sell_score}/9)",
                "confidence": 0.0
            }

    def scan_best_stable_market(self, live_data_fetcher=None) -> Dict[str, Any]:
        """
        রিয়েল-টাইম মার্কেট স্ক্যানার: নিজে থেকে সমস্ত পেয়ার লুপ করে সেরা স্টেবল মার্কেট ও সিগন্যাল খুঁজে বের করবে।
        """
        scanned_results = []

        for symbol in self.market_pairs:
            if self._is_otc(symbol):
                continue
            
            df = pd.DataFrame()
            if live_data_fetcher and callable(live_data_fetcher):
                try:
                    # লাইভ ডেটা প্রোভাইডার থেকে ক্যান্ডেল ডেটা ফেচ করা
                    df = live_data_fetcher(symbol)
                except Exception as e:
                    logging.error(f"Error fetching data for {symbol}: {e}")
                    continue

            # যদি লাইভ ডেটা পাওয়া যায়, তবে ইঞ্জিন নিজে থেকেই এনালাইসিস রান করবে
            if not df.empty:
                result = self.evaluate_market_signal(df, symbol=symbol)
                if result.get("status") == "SIGNAL":
                    scanned_results.append(result)

        # যদি একাধিক সিগন্যাল পাওয়া যায়, তবে সেরা স্টেবল সিগন্যালটি সিলেক্ট করবে
        if scanned_results:
            sorted_signals = sorted(scanned_results, key=lambda x: x.get('stability_rank', 0), reverse=True)
            return sorted_signals[0]

        return {
            "symbol": "NONE",
            "status": "NO_SIGNAL",
            "action": "HOLD",
            "reason": "Scanning live markets... No 75%+ stable setups found right now.",
            "confidence": 0.0
        }

if __name__ == "__main__":
    engine = StrategyEngine()
    print("--- Real-Time Autonomous Strategy Engine Ready ---")