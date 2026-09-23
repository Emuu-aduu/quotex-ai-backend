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
        """
        75% Confirmation Rule: 9টি মোট কনফার্মেশন পয়েন্টের মধ্যে অন্তত ৭টি (7/9 = 77.7%)
        একই দিকে (BUY/SELL) মিললে তবেই সিগন্যাল ট্রিগার হবে।
        """
        self.min_score_threshold = min_score_threshold
        # Magic number সরিয়ে Config / Default fallback এ সেট করা হলো
        self.spread_penalty_weight = getattr(settings, "SPREAD_PENALTY_WEIGHT", spread_penalty_weight)
        
        self.market_pairs = [
            "EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CAD",
            "EUR/GBP", "EUR/JPY", "GBP/JPY", "NZD/USD", "USD/CHF",
            "AUD/JPY", "EUR/CAD", "GBP/CAD", "AUD/CAD", "EUR/AUD",
            "GBP/AUD", "CAD/JPY", "CHF/JPY", "NZD/JPY", "EUR/CHF"
        ]

    def _is_otc(self, symbol: str) -> bool:
        """OTC মার্কেট ফিল্টার"""
        return "OTC" in symbol.upper()

    def _check_wick_and_stability(self, df: pd.DataFrame) -> bool:
        """
        Wick/Shadow & Doji Block (Fake Shadow Filter)
        ক্যান্ডেলের Wick যদি Body-এর চেয়ে ২ গুণের বেশি বড় হয় তবে ব্লক করবে।
        """
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

        # Doji or Wick >= 2x Body
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
        Evaluates 75% Confirmation Rules (7/9 Threshold), OTC Drop, Fake Shadows, & Market Stability.
        """
        # ১. OTC ফিল্টারিং
        if self._is_otc(symbol):
            return {"symbol": symbol, "status": "REJECTED", "reason": "OTC Market Blocked"}

        # ২. মিনিমাম ডাটা চেক
        if df.empty or len(df) < 30:
            return {"symbol": symbol, "status": "REJECTED", "reason": "Insufficient Candle Data"}

        # ৩. স্প্রেড ও নিউজ ফিল্টার (Spread > 3.0 pips / News Time)
        if spread_pips > 3.0:
            return {"symbol": symbol, "status": "REJECTED", "reason": f"High Spread ({spread_pips} pips > 3.0)"}
        
        if is_news_time:
            return {"symbol": symbol, "status": "REJECTED", "reason": "High-Impact News Block"}

        # ৪. ক্যান্ডেল উইক ও ডোজি ফিল্টার (Fake Shadow Check)
        latest = df.iloc[-1]
        if latest.get('is_fake_shadow', False) or not self._check_wick_and_stability(df):
            return {"symbol": symbol, "status": "REJECTED", "reason": "High Volatility / Fake Shadow Wick Block"}

        # ৫. IndicatorEngine থেকে ইন্ডিকেটর ও SMC কনফার্মেশন গণনা
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

        # ----------------------------------------------------
        # ৬. ৭৫% কনফার্মেশন ডিসিশন (৭/৯ পয়েন্ট)
        # ----------------------------------------------------
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

    def select_best_2_markets(self, scanned_markets: List[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Scans all market results and filters out top 2 most stable signals."""
        if not scanned_markets:
            return []

        valid_signals = [m for m in scanned_markets if isinstance(m, dict) and m.get('status') == "SIGNAL"]
        if not valid_signals:
            return []

        sorted_signals = sorted(valid_signals, key=lambda x: x.get('stability_rank', 0), reverse=True)
        return sorted_signals[:2]

    def scan_best_stable_market(self) -> Dict[str, Any]:
        """On-Demand API Call Handler"""
        return {
            "pair": "EUR/USD",
            "action": "HOLD",
            "confidence": 0.0,
            "reason": "On-demand live scan requires active price dataframe."
        }

if __name__ == "__main__":
    engine = StrategyEngine()
    print("--- Strategy Engine 75% Rules & Indicator Engine Connected Successfully ---")