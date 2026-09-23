import pandas as pd

class CandleBuilder:
    def __init__(self, timeframe='1m'):
        self.timeframe = timeframe

    def build_candles_from_ticks(self, ticks_df: pd.DataFrame) -> pd.DataFrame:
        if ticks_df.empty:
            return pd.DataFrame()

        df = ticks_df.copy()
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df.set_index('timestamp', inplace=True)

        resample_rule = self.timeframe.replace('m', 'min')
        
        ohlcv = df['price'].resample(resample_rule).ohlc()
        if 'volume' in df.columns:
            ohlcv['volume'] = df['volume'].resample(resample_rule).sum()
        else:
            ohlcv['volume'] = 0

        ohlcv.dropna(inplace=True)
        ohlcv.reset_index(inplace=True)

        # [4. Fake Shadow & Candle Block Metrics Calculation]
        ohlcv['body_size'] = (ohlcv['close'] - ohlcv['open']).abs()
        ohlcv['upper_wick'] = ohlcv['high'] - ohlcv[['open', 'close']].max(axis=1)
        ohlcv['lower_wick'] = ohlcv[['open', 'close']].min(axis=1) - ohlcv['low']
        
        # Wick >= 2x Body or Doji Check
        ohlcv['is_fake_shadow'] = (ohlcv['upper_wick'] >= 2 * ohlcv['body_size']) | \
                                  (ohlcv['lower_wick'] >= 2 * ohlcv['body_size']) | \
                                  (ohlcv['body_size'] == 0)

        return ohlcv

if __name__ == "__main__":
    data = {
        'timestamp': pd.date_range(start='2026-09-19 10:00:00', periods=10, freq='10s'),
        'price': [100.5, 100.8, 100.2, 101.0, 100.9, 101.2, 101.5, 101.1, 101.8, 102.0],
        'volume': [10, 20, 15, 30, 25, 40, 35, 20, 50, 45]
    }
    ticks = pd.DataFrame(data)
    builder = CandleBuilder(timeframe='1m')
    candles = builder.build_candles_from_ticks(ticks)
    print("Generated Candles with Fake Shadow Detection:")
    print(candles[['timestamp', 'open', 'high', 'low', 'close', 'is_fake_shadow']])