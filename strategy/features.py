import pandas as pd
import ta


def add_indicators(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """
    テクニカル指標を追加する。
    RSI + ボリンジャーバンド（逆張り戦略）
    EMA50（トレンドフィルター用）
    """
    if len(df) < max(cfg.get('bb_period', 20), 50) + 5:
        return df
    df = df.copy()

    # ── 逆張り戦略用 ──────────────────────────────
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

    # ── トレンドフィルター用（EMA50） ────────────
    ema_period = cfg.get('ema_filter_period', 50)
    df['ema_filter'] = ta.trend.EMAIndicator(
        df['close'], window=ema_period
    ).ema_indicator()

    return df
