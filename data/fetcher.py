import requests
import time
import pandas as pd
from datetime import datetime

BASE = "https://public.bitbank.cc"
_last_call = 0
MIN_INTERVAL = 60  # 最低60秒間隔（Proプラン対応）


def _get(url: str, params: dict = None) -> dict:
    global _last_call
    elapsed = time.time() - _last_call
    if elapsed < 1.0:
        time.sleep(1.0 - elapsed)
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        _last_call = time.time()
        data = r.json()
        if data.get("success") != 1:
            raise ValueError(f"API error: {data}")
        return data["data"]
    except Exception as e:
        raise RuntimeError(f"fetch failed {url}: {e}")


def get_ticker(pair: str) -> dict:
    """Tickerを取得（last, sell, buy, high, low, vol, timestamp）"""
    data = _get(f"{BASE}/{pair}/ticker")
    return {
        "pair": pair,
        "last": float(data["last"]),
        "sell": float(data["sell"]),
        "buy": float(data["buy"]),
        "high": float(data["high"]),
        "low": float(data["low"]),
        "vol": float(data["vol"]),
        "timestamp": int(data["timestamp"]),
    }


def get_all_tickers(pairs: list, excluded: list = None) -> list:
    """全ペアのTickerを取得（除外ペアはスキップ）"""
    excluded = excluded or []
    results = []
    for pair in pairs:
        if pair in excluded:
            continue
        try:
            t = get_ticker(pair)
            results.append(t)
            time.sleep(0.5)  # レート制限対策
        except Exception as e:
            print(f"[fetcher] skip {pair}: {e}")
    return results


def get_candlestick(pair: str, candle_type: str = "1min", count: int = 100) -> pd.DataFrame:
    """OHLCVローソク足データを取得"""
    today = datetime.now().strftime("%Y%m%d")
    data = _get(f"{BASE}/{pair}/candlestick/{candle_type}/{today}")
    candles = data.get("candlestick", [])
    if not candles:
        return pd.DataFrame()
    ohlcv = candles[0].get("ohlcv", [])
    df = pd.DataFrame(ohlcv, columns=["open", "high", "low", "close", "volume", "timestamp"])
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df.sort_values("timestamp").tail(count).reset_index(drop=True)
    return df
