import pandas as pd
import numpy as np

class IndicatorEngine:
    @staticmethod
    def calculate_all(df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculates 6 Core Technical Indicators + ICT/SMC BOS Signals.
        """
        if len(df) < 30:
            return df

        # 1. RSI (14)
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / (loss + 1e-9)
        df['rsi'] = 100 - (100 / (1 + rs))

        # 2. MACD (12, 26, 9)
        ema12 = df['close'].ewm(span=12, adjust=False).mean()
        ema26 = df['close'].ewm(span=26, adjust=False).mean()
        df['macd'] = ema12 - ema26
        df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()

        # 3. CCI (20)
        tp = (df['high'] + df['low'] + df['close']) / 3
        sma_tp = tp.rolling(window=20).mean()
        mad = tp.rolling(window=20).apply(lambda x: np.abs(x - x.mean()).mean())
        df['cci'] = (tp - sma_tp) / (0.015 * mad + 1e-9)

        # 4. Stochastic Oscillator (14, 3)
        low_14 = df['low'].rolling(window=14).min()
        high_14 = df['high'].rolling(window=14).max()
        df['stoch_k'] = 100 * ((df['close'] - low_14) / (high_14 - low_14 + 1e-9))
        df['stoch_d'] = df['stoch_k'].rolling(window=3).mean()

        # 5. Bollinger Bands (20, 2)
        sma20 = df['close'].rolling(window=20).mean()
        std20 = df['close'].rolling(window=20).std()
        df['bb_upper'] = sma20 + (std20 * 2)
        df['bb_lower'] = sma20 - (std20 * 2)

        # 6. ICT / SMC BOS Logic
        df['bos_bullish'] = df['close'] > df['high'].shift(1).rolling(5).max()
        df['bos_bearish'] = df['close'] < df['low'].shift(1).rolling(5).min()

        return df

    @staticmethod
    def get_final_signal(df: pd.DataFrame) -> dict:
        """
        Calculates Indicator Confluence Score and determines single entry direction.
        """
        if df.empty or len(df) < 30:
            return {"signal": "NEUTRAL", "buy_score": 0, "sell_score": 0}

        latest = df.iloc[-1]
        buy_score = 0
        sell_score = 0

        # Condition 1: RSI (< 35 for BUY, > 65 for SELL)
        if latest['rsi'] < 35:
            buy_score += 1
        elif latest['rsi'] > 65:
            sell_score += 1

        # Condition 2: MACD (MACD > Signal for BUY, MACD < Signal for SELL)
        if latest['macd'] > latest['macd_signal']:
            buy_score += 1
        elif latest['macd'] < latest['macd_signal']:
            sell_score += 1

        # Condition 3: CCI (< -100 for BUY, > 100 for SELL)
        if latest['cci'] < -100:
            buy_score += 1
        elif latest['cci'] > 100:
            sell_score += 1

        # Condition 4: Stochastic K (< 20 for BUY, > 80 for SELL)
        if latest['stoch_k'] < 20:
            buy_score += 1
        elif latest['stoch_k'] > 80:
            sell_score += 1

        # Condition 5: Bollinger Bands (Close < Lower for BUY, Close > Upper for SELL)
        if latest['close'] < latest['bb_lower']:
            buy_score += 1
        elif latest['close'] > latest['bb_upper']:
            sell_score += 1

        # Condition 6: ICT BOS (BOS Bullish for BUY, BOS Bearish for SELL)
        if latest.get('bos_bullish', False):
            buy_score += 1
        if latest.get('bos_bearish', False):
            sell_score += 1

        # Score Threshold Logic
        if buy_score >= 4:
            final_signal = "STRONG_BUY"
        elif sell_score >= 4:
            final_signal = "STRONG_SELL"
        else:
            final_signal = "NEUTRAL"

        return {
            "signal": final_signal,
            "buy_score": buy_score,
            "sell_score": sell_score,
            "price": latest['close']
        }