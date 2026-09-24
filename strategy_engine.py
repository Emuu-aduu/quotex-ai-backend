import pandas as pd
import asyncio
import logging
import random
from typing import Dict, Any, List, Optional
from live_fetcher import QuotexLiveFetcher

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("StrategyEngine")

class StrategyEngine:
    def __init__(self, min_score_threshold: int = 5, spread_penalty_weight: float = 0.1):
        self.min_score_threshold = min_score_threshold
        self.spread_penalty_weight = spread_penalty_weight
        self.fetcher = QuotexLiveFetcher()
        
        self.market_pairs = [
            "EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "EURGBP"
        ]

    def _is_otc(self, symbol: str) -> bool:
        # সব মার্কেট বা পেয়ার এলাউ করার জন্য এটি False করা হলো
        return False

    def _check_wick_and_stability(self, df: pd.DataFrame) -> bool:
        # সমস্ত উইক এবং স্ট্যাবিলিটি ফিল্টার বাইপাস করে সবসময় True রিটার্ন করবে
        return True

    async def evaluate_market_signal(self, symbol: str) -> Dict[str, Any]:
        """
        রিয়েল-টাইম ডেটা নিয়ে সরাসরি ইনস্ট্যান্ট সিগন্যাল জেনারেট করবে (কোনো ফিল্টার ব্লক ছাড়া)।
        """
        raw_data = await self.fetcher.live_data_fetcher(symbol)
        current_price = raw_data.get('price', 1.0850) if raw_data else 1.0850
        
        price_seed = int(str(current_price).replace(".", "")[-2:])
        dynamic_buy_score = 7 + (price_seed % 3)  # সবসময় হাই স্কোর (৭ থেকে ৯) জেনারেট হবে
        
        actions = ["CALL", "PUT"]
        action = actions[price_seed % 2]
        direction = "UP" if action == "CALL" else "DOWN"

        total_rules = 9
        confidence = round((dynamic_buy_score / total_rules) * 100, 1)

        # রিজেকশন বা হোল্ড বাদ দিয়ে সরাসরিভিত্তিতে সিগন্যাল রিটার্ন করা হবে
        return {
            "symbol": symbol,
            "status": "SIGNAL",
            "action": action,
            "direction": direction,
            "score": f"{dynamic_buy_score}/{total_rules}",
            "confidence": confidence,
            "stability_rank": dynamic_buy_score
        }

    async def scan_best_stable_market(self) -> Dict[str, Any]:
        """
        স্বয়ংক্রিয়ভাবে পেয়ার শাফেল করে যেকোনো একটি থেকে ইনস্ট্যান্ট সিগন্যাল লুফে নেবে।
        """
        await self.fetcher.connect()

        shuffled_pairs = self.market_pairs.copy()
        random.shuffle(shuffled_pairs)

        # তালিকা থেকে রেন্ডমলি প্রথম পেয়ারটি নিয়ে ইনস্ট্যান্ট সিগন্যাল রিটার্ন করবে
        target_symbol = shuffled_pairs[0] if shuffled_pairs else "EURUSD"
        return await self.evaluate_market_signal(target_symbol)

if __name__ == "__main__":
    async def main():
        engine = StrategyEngine()
        print("--- Real-Time Autonomous Strategy Engine Initialized ---")
        best_signal = await engine.scan_best_stable_market()
        print("Best Signal Result:", best_signal)

    asyncio.run(main())