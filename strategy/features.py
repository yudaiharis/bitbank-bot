import pandas as pd
import ta

def add_indicators(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    if len(df) < cfg.get('bb_period', 20) + 5:
        return df
    df = df.copy()
    df['rsi'] = ta.momentum.RSIIndicator(
        df['close'], window=cfg.get('rsi_period', 14)
    ).rsi()
    bb = ta.volatility.BollingerBands(
        df['close'],
        window=cfg.get('bb_period', 20),
        window_dev=cfg.get('bb_std', 2.0)
    )
    df['bb_upper'] = bb.bollinger_hband()
    df['bb_mid']   = bb.bollinger_mavg()
    df['bb_lower'] = bb.bollinger_lband()
    return df
