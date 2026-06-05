import time
from data.fetcher import get_all_tickers


def calc_score(ticker: dict, weights: dict) -> float:
    """
    ボラティリティスコアを計算
    score = ATR比率 * w_atr + 出来高 * w_vol + 価格変動幅 * w_range
    """
    last = ticker["last"]
    if last <= 0:
        return 0.0
    high_low_range = (ticker["high"] - ticker["low"]) / last
    volume_score = min(ticker["vol"] * last / 100_000_000, 1.0)  # 1億円を上限に正規化
    spread = (ticker["sell"] - ticker["buy"]) / last if ticker["sell"] > 0 else 1.0
    spread_penalty = max(0, 1.0 - spread * 100)  # スプレッド広いほど減点
    raw = (
        high_low_range * weights.get("vol_weight_atr", 0.5) +
        volume_score   * weights.get("vol_weight_volume", 0.3) +
        high_low_range * weights.get("vol_weight_range", 0.2)
    )
    return raw * spread_penalty


def scan_pairs(pairs: list, excluded: list, cfg: dict) -> list:
    """
    全ペアをスキャンしてボラティリティスコア順に返す
    Returns: [{"pair": ..., "score": ..., "last": ..., "vol_jpy": ..., "spread_pct": ...}, ...]
    """
    min_vol = cfg.get("min_volume_jpy", 10_000_000)
    tickers = get_all_tickers(pairs, excluded)

    scored = []
    for t in tickers:
        last = t["last"]
        vol_jpy = t["vol"] * last
        spread_pct = (t["sell"] - t["buy"]) / last * 100 if last > 0 else 999

        # 流動性フィルタ
        if vol_jpy < min_vol:
            continue
        # スプレッドフィルタ（0.5%超は除外）
        if spread_pct > 0.5:
            continue

        score = calc_score(t, cfg)
        scored.append({
            "pair": t["pair"],
            "score": round(score, 6),
            "last": last,
            "vol_jpy": vol_jpy,
            "spread_pct": round(spread_pct, 4),
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored


def should_switch(current_pair: str, ranked: list, current_pos, cfg: dict, last_switch_time: float) -> str | None:
    """
    銘柄切り替えを判定。切り替える場合は新ペアを返す。
    """
    if not ranked:
        return None
    if current_pos is not None:  # ポジション保有中は切替しない
        return None

    min_hold = cfg.get("min_hold_minutes", 30) * 60
    if time.time() - last_switch_time < min_hold:
        return None

    top = ranked[0]
    if top["pair"] == current_pair:
        return None

    current_score = next((r["score"] for r in ranked if r["pair"] == current_pair), 0)
    threshold = cfg.get("switch_threshold", 0.20)
    if current_score <= 0 or (top["score"] - current_score) / max(current_score, 1e-9) > threshold:
        return top["pair"]
    return None
