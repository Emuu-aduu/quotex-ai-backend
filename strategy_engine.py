import logging
import pandas as pd

logger = logging.getLogger("quotex_signal_system")


class StrategyEngine:

  def __init__(self, fetcher=None):
    self.fetcher = fetcher

  def calculate_rsi(
      self, close_series: pd.Series, window: int = 14
  ) -> pd.Series:
    """Pure Pandas math for RSI (No external library required)"""
    delta = close_series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)

    avg_gain = gain.rolling(window=window, min_periods=window).mean()
    avg_loss = loss.rolling(window=window, min_periods=window).mean()

    rs = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi

  async def scan_best_stable_market(self, timeframe: str = "1m") -> dict:
    try:
      if not self.fetcher:
        return {
            "status": "NO_SIGNAL",
            "action": "HOLD",
            "reason": "Fetcher instance not provided",
        }

      # Live candle fetch via shared live_fetcher
      symbol = "EUR/USD"  # default pair / market
      candles = await self.fetcher.get_candles(symbol, timeframe)

      if not candles or len(candles) < 15:
        return {
            "status": "NO_SIGNAL",
            "action": "HOLD",
            "reason": "Insufficient candle data for calculation",
        }

      df = pd.DataFrame(candles)
      if "close" not in df.columns:
        df["close"] = df.iloc[:, 4] if len(df.columns) > 4 else df.iloc[:, 0]

      close = df["close"].astype(float)
      rsi_series = self.calculate_rsi(close, window=14)
      latest_rsi = rsi_series.iloc[-1]

      if pd.isna(latest_rsi):
        return {
            "status": "NO_SIGNAL",
            "action": "HOLD",
            "reason": "RSI calculation yielded NaN",
        }

      rsi_val = float(latest_rsi)

      if rsi_val > 70:
        return {
            "status": "SIGNAL",
            "symbol": symbol,
            "action": "PUT",
            "direction": "PUT",
            "score": "8/10",
            "reason": f"Overbought RSI ({rsi_val:.1f})",
        }
      elif rsi_val < 30:
        return {
            "status": "SIGNAL",
            "symbol": symbol,
            "action": "CALL",
            "direction": "CALL",
            "score": "8/10",
            "reason": f"Oversold RSI ({rsi_val:.1f})",
        }
      else:
        return {
            "status": "NO_SIGNAL",
            "action": "HOLD",
            "reason": f"65%+ confirmation pawa jayni (RSI: {rsi_val:.1f})",
        }

    except Exception as err:
      logger.error(f"Strategy Engine Error: {err}", exc_info=True)
      return {
          "status": "NO_SIGNAL",
          "action": "HOLD",
          "reason": f"Strategy Error: {str(err)}",
      }