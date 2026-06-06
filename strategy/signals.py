import pandas as pd
from strategy.features import add_indicators


def get_signal(df: pd.DataFrame, cfg: dict) -> str:
    """
    RSI + ボリンジャーバンド 逆張り戦略 + EMAトレンドフィルター。

    Returns: 'buy' / 'sell' / 'hold'

    ── シグナル条件 ────────────────────────────────────────────
    buy  : RSI < rsi_oversold  かつ close < BB下限
           かつ use_ema_filter=true なら close > EMA50（上昇トレンド内の押し目のみ）
    sell : RSI > rsi_overbought かつ close > BB上限
           かつ use_ema_filter=true なら close < EMA50（下落トレンド内の戻りのみ）

    ── EMAフィルターの効果 ──────────────────────────────────────
    下落トレンド中（close < EMA50）に RSI 売られすぎが出ても買いシグナルを出さない。
    → 連続SL（トレンド方向への逆張り）を防止する。
    """
    df = add_indicators(df, cfg)
    required = ["rsi", "bb_upper", "bb_lower", "ema_filter"]
    if df.empty or not all(c in df.columns for c in required):
        return "hold"

    last = df.iloc[-1]
    if pd.isna(last["rsi"]) or pd.isna(last["bb_lower"]) or pd.isna(last["ema_filter"]):
        return "hold"

    oversold    = cfg.get("rsi_oversold",   25)
    overbought  = cfg.get("rsi_overbought", 65)
    use_filter  = cfg.get("use_ema_filter", True)
    close       = last["close"]
    ema         = last["ema_filter"]

    # ── BUY 判定 ──────────────────────────────────
    if last["rsi"] < oversold and close < last["bb_lower"]:
        if use_filter and close < ema:
            # 下落トレンド中 → 逆張りBUY禁止
            return "hold"
        return "buy"

    # ── SELL 判定 ─────────────────────────────────
    if last["rsi"] > overbought and close > last["bb_upper"]:
        if use_filter and close > ema:
            # 上昇トレンド中 → 逆張りSELL禁止
            return "hold"
        return "sell"

    return "hold"
