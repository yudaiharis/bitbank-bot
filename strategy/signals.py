import pandas as pd
from strategy.features import add_indicators


def get_signal(df: pd.DataFrame, cfg: dict) -> str:
    """
    最新バーのシグナルを返す: 'buy' / 'sell' / 'hold'
    条件:
      buy  : RSI < rsi_oversold  かつ close < bb_lower
      sell : RSI > rsi_overbought かつ close > bb_upper
    """
    df = add_indicators(df, cfg)
    required = ["rsi", "bb_upper", "bb_lower"]
    if df.empty or not all(c in df.columns for c in required):
        return "hold"

    last = df.iloc[-1]
    if pd.isna(last["rsi"]) or pd.isna(last["bb_lower"]):
        return "hold"

    oversold   = cfg.get("rsi_oversold",   30)
    overbought = cfg.get("rsi_overbought", 70)

    if last["rsi"] < oversold  and last["close"] < last["bb_lower"]:
        return "buy"
    if last["rsi"] > overbought and last["close"] > last["bb_upper"]:
        return "sell"
    return "hold"
