import pandas as pd
import ta


def add_indicators(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """
    5分足（メイン足）にテクニカル指標を追加する。
    RSI + ボリンジャーバンド（逆張りシグナル用）
    """
    min_len = cfg.get('bb_period', 20) + 5
    if len(df) < min_len:
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


def add_htf_trend(df_htf: pd.DataFrame, cfg: dict) -> dict:
    """
    上位足（1時間足）のトレンド方向を判定して返す。

    Returns:
        {
            "ema":       float  - 最新の HTF EMA 値
            "trend":     str    - "up" / "down" / "flat"
            "slope_pct": float  - EMA の傾き（直近2本の変化率 %）
        }
    """
    period = cfg.get('htf_ema_period', 20)
    min_len = period + 2

    if df_htf is None or df_htf.empty or len(df_htf) < min_len:
        return {"ema": None, "trend": "flat", "slope_pct": 0.0}

    df_htf = df_htf.copy()
    df_htf['ema'] = ta.trend.EMAIndicator(
        df_htf['close'], window=period
    ).ema_indicator()

    last  = df_htf.iloc[-1]
    prev  = df_htf.iloc[-2]

    ema_now  = last['ema']
    ema_prev = prev['ema']

    if pd.isna(ema_now) or pd.isna(ema_prev) or ema_prev == 0:
        return {"ema": None, "trend": "flat", "slope_pct": 0.0}

    slope_pct = (ema_now - ema_prev) / ema_prev * 100

    # 傾きが flat_threshold % 以内なら "flat"
    flat_threshold = cfg.get('htf_flat_threshold', 0.05)  # 0.05%
    if abs(slope_pct) < flat_threshold:
        trend = "flat"
    elif slope_pct > 0:
        trend = "up"
    else:
        trend = "down"

    return {
        "ema":       float(ema_now),
        "trend":     trend,
        "slope_pct": round(slope_pct, 4),
    }
