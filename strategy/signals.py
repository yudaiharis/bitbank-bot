import pandas as pd
from strategy.features import add_indicators, add_htf_trend


def get_signal(df: pd.DataFrame, cfg: dict,
               df_htf: pd.DataFrame = None) -> str:
    """
    マルチタイムフレーム対応シグナル生成。

    ── 戦略ロジック ─────────────────────────────────────────────
    5分足シグナル（RSI+BB 逆張り）に 1時間足トレンドフィルターを重ねる。

    HTF（1時間足）トレンド判定:
      up   → BUY のみ許可（押し目買い）。SELL は "flat" のみ許可
      down → SELL のみ許可（戻り売り）。BUY は "flat" のみ許可
      flat → BUY / SELL どちらも許可

    ── シグナル条件 ─────────────────────────────────────────────
    BUY  : RSI < rsi_oversold かつ close < BB下限
           かつ HTF trend が "up" または "flat"

    SELL : RSI > rsi_overbought かつ close > BB上限
           かつ HTF trend が "down" または "flat"

    ── フォールバック ────────────────────────────────────────────
    df_htf が None または use_htf_filter=False の場合:
      旧来の単一足 EMA フィルター（ema_filter_period）を使用。
      これにより後方互換性を維持。
    """
    df = add_indicators(df, cfg)
    required = ["rsi", "bb_upper", "bb_lower"]
    if df.empty or not all(c in df.columns for c in required):
        return "hold"

    last = df.iloc[-1]
    if pd.isna(last["rsi"]) or pd.isna(last["bb_lower"]):
        return "hold"

    oversold   = cfg.get("rsi_oversold",   25)
    overbought = cfg.get("rsi_overbought", 65)
    close      = last["close"]

    # ── HTFフィルター（マルチタイムフレーム） ────────────────────
    use_htf = cfg.get("use_htf_filter", True) and df_htf is not None

    if use_htf:
        htf = add_htf_trend(df_htf, cfg)
        trend = htf["trend"]
        cfg['_htf_trend']     = trend          # ダッシュボード表示用
        cfg['_htf_ema']       = htf["ema"]
        cfg['_htf_slope_pct'] = htf["slope_pct"]

        buy_ok  = trend in ("up",   "flat")
        sell_ok = trend in ("down", "flat")

    else:
        # フォールバック: 同一足EMAフィルター（後方互換）
        use_ema = cfg.get("use_ema_filter", True)
        if use_ema and "ema_filter" not in df.columns:
            # ema_filter が未計算なら簡易追加
            import ta as _ta
            period = cfg.get("ema_filter_period", 200)
            if len(df) >= period:
                df["ema_filter"] = _ta.trend.EMAIndicator(
                    df["close"], window=period
                ).ema_indicator()

        ema_val = df.iloc[-1].get("ema_filter") if "ema_filter" in df.columns else None
        if use_ema and ema_val is not None and not pd.isna(ema_val):
            buy_ok  = close > ema_val
            sell_ok = close < ema_val
        else:
            buy_ok  = True
            sell_ok = True

        cfg['_htf_trend'] = "N/A (single-TF)"

    # ── BUY 判定 ─────────────────────────────────────────────────
    if last["rsi"] < oversold and close < last["bb_lower"]:
        return "buy" if buy_ok else "hold"

    # ── SELL 判定 ────────────────────────────────────────────────
    if last["rsi"] > overbought and close > last["bb_upper"]:
        return "sell" if sell_ok else "hold"

    return "hold"
