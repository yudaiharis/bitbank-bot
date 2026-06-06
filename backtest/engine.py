#!/usr/bin/env python3
"""
bitbank バックテストエンジン
過去OHLCVデータを取得して戦略を検証・パラメータ最適化

使い方:
  python backtest/engine.py --pair xlm_jpy --days 365
  python backtest/engine.py --pair xlm_jpy --days 365 --optimize
  python backtest/engine.py --pair btc_jpy --days 180 --candle 1hour
"""

import os
import sys
import csv
import time
import json
import argparse
import itertools
import requests
import yaml
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from multiprocessing import Pool, cpu_count

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_URL  = "https://public.bitbank.cc"
DATA_DIR  = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
REPORT_DIR = Path(__file__).parent.parent / "reports"
REPORT_DIR.mkdir(exist_ok=True)


# ============================================================
# 1. データ取得
# ============================================================

def fetch_day(pair: str, candle_type: str, date_str: str) -> list:
    """1日分のOHLCVを取得。失敗時は空リストを返す"""
    url = f"{BASE_URL}/{pair}/candlestick/{candle_type}/{date_str}"
    try:
        r = requests.get(url, timeout=10)
        data = r.json()
        if data.get("success") != 1:
            return []
        return data["data"]["candlestick"][0]["ohlcv"]
    except Exception:
        return []


def cache_path(pair: str, candle_type: str, date_str: str) -> Path:
    return DATA_DIR / f"{pair}_{candle_type}_{date_str}.csv"


def load_or_fetch(pair: str, candle_type: str, date_str: str) -> list:
    """キャッシュがあれば読み込み、なければAPIから取得して保存"""
    cp = cache_path(pair, candle_type, date_str)
    if cp.exists():
        rows = []
        with open(cp) as f:
            for row in csv.reader(f):
                rows.append(row)
        return rows
    ohlcv = fetch_day(pair, candle_type, date_str)
    if ohlcv:
        with open(cp, "w", newline="") as f:
            csv.writer(f).writerows(ohlcv)
    return ohlcv


def fetch_ohlcv(pair: str, candle_type: str, days: int) -> pd.DataFrame:
    """過去N日間のOHLCVを取得してDataFrameで返す"""
    print(f"\n📥 データ取得中: {pair} / {candle_type} / 過去{days}日間")
    all_rows = []
    today = datetime.utcnow().date()

    for i in range(days, -1, -1):
        d = today - timedelta(days=i)
        date_str = d.strftime("%Y%m%d")
        rows = load_or_fetch(pair, candle_type, date_str)
        all_rows.extend(rows)
        if i % 30 == 0:
            print(f"  {date_str} 取得済み ({days-i}/{days}日)", end="\r")
        time.sleep(0.3)  # レート制限対策

    if not all_rows:
        print("データが取得できませんでした")
        return pd.DataFrame()

    df = pd.DataFrame(all_rows, columns=["open","high","low","close","volume","timestamp"])
    for col in ["open","high","low","close","volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["timestamp"] = pd.to_datetime(pd.to_numeric(df["timestamp"]), unit="ms")
    df = df.dropna().sort_values("timestamp").reset_index(drop=True)
    print(f"\n✅ 取得完了: {len(df):,}件 ({df['timestamp'].iloc[0].date()} 〜 {df['timestamp'].iloc[-1].date()})")
    return df


# ============================================================
# 2. シグナル生成
# ============================================================

def add_indicators(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """RSI・ボリンジャーバンド・EMAフィルターを追加"""
    import ta as _ta
    min_len = max(cfg.get("bb_period", 20), cfg.get("ema_filter_period", 50)) + 5
    if len(df) < min_len:
        return df
    df = df.copy()
    df["rsi"] = _ta.momentum.RSIIndicator(
        df["close"], window=cfg.get("rsi_period", 14)
    ).rsi()
    bb = _ta.volatility.BollingerBands(
        df["close"], window=cfg.get("bb_period", 20), window_dev=cfg.get("bb_std", 2.0)
    )
    df["bb_upper"] = bb.bollinger_hband()
    df["bb_lower"] = bb.bollinger_lband()
    df["ema_filter"] = _ta.trend.EMAIndicator(
        df["close"], window=cfg.get("ema_filter_period", 50)
    ).ema_indicator()
    return df


def get_signal(row, cfg: dict) -> str:
    """RSI+BB + EMAトレンドフィルター でシグナルを返す"""
    if pd.isna(row.get("rsi")) or pd.isna(row.get("bb_lower")):
        return "hold"

    oversold    = cfg.get("rsi_oversold",   25)
    overbought  = cfg.get("rsi_overbought", 65)
    use_filter  = cfg.get("use_ema_filter", True)
    close       = row["close"]
    ema         = row.get("ema_filter")

    if row["rsi"] < oversold and close < row["bb_lower"]:
        if use_filter and not pd.isna(ema) and close < ema:
            return "hold"  # 下落トレンド中のBUY禁止
        return "buy"

    if row["rsi"] > overbought and close > row["bb_upper"]:
        if use_filter and not pd.isna(ema) and close > ema:
            return "hold"  # 上昇トレンド中のSELL禁止
        return "sell"

    return "hold"


# ============================================================
# 3. バックテスト実行
# ============================================================

def run_backtest(df: pd.DataFrame, cfg: dict, initial_balance: float = 1_000_000) -> dict:
    """バックテストを実行して結果dictを返す"""
    df = add_indicators(df, cfg)
    sl       = cfg.get("stop_loss_pct",    0.020)
    tp       = cfg.get("take_profit_pct",  0.040)
    pos_pct  = cfg.get("position_size_pct", 0.05)
    maker    = cfg.get("maker_fee",  -0.0002)
    taker    = cfg.get("taker_fee",   0.0012)

    balance   = initial_balance
    peak      = balance
    max_dd    = 0.0
    position  = None
    trades    = []
    equity_curve = [balance]

    for i, row in df.iterrows():
        price = float(row["close"])

        # ポジションあり → SL/TP確認
        if position:
            ep   = position["entry_price"]
            side = position["side"]
            sl_hit = (price <= ep * (1-sl)) if side=="buy" else (price >= ep * (1+sl))
            tp_hit = (price >= ep * (1+tp)) if side=="buy" else (price <= ep * (1-tp))

            if sl_hit or tp_hit:
                reason = "SL" if sl_hit else "TP"
                qty    = position["amount_jpy"] / ep
                gross  = (price - ep) * qty if side=="buy" else (ep - price) * qty
                fee    = position["amount_jpy"] * maker + position["amount_jpy"] * taker
                pnl    = gross - fee
                balance += pnl
                peak    = max(peak, balance)
                dd      = (peak - balance) / peak
                max_dd  = max(max_dd, dd)
                trades.append({
                    "entry_time":  position["entry_time"],
                    "exit_time":   row["timestamp"],
                    "pair":        cfg.get("_pair", ""),
                    "side":        side,
                    "entry_price": ep,
                    "exit_price":  price,
                    "amount_jpy":  position["amount_jpy"],
                    "pnl":         round(pnl, 2),
                    "reason":      reason,
                })
                position = None
                equity_curve.append(balance)

        # ポジションなし → エントリー
        if not position:
            signal = get_signal(row, cfg)
            if signal in ("buy", "sell"):
                amount = balance * pos_pct
                position = {
                    "side":        signal,
                    "entry_price": price,
                    "amount_jpy":  amount,
                    "entry_time":  row["timestamp"],
                }

    # 強制クローズ（未決済ポジション）
    if position and len(df) > 0:
        price  = float(df.iloc[-1]["close"])
        ep     = position["entry_price"]
        side   = position["side"]
        qty    = position["amount_jpy"] / ep
        gross  = (price - ep) * qty if side=="buy" else (ep - price) * qty
        fee    = position["amount_jpy"] * (maker + taker)
        pnl    = gross - fee
        balance += pnl
        trades.append({
            "entry_time":  position["entry_time"],
            "exit_time":   df.iloc[-1]["timestamp"],
            "pair":        cfg.get("_pair", ""),
            "side":        side,
            "entry_price": ep,
            "exit_price":  price,
            "amount_jpy":  position["amount_jpy"],
            "pnl":         round(pnl, 2),
            "reason":      "END",
        })
        equity_curve.append(balance)

    wins     = [t for t in trades if t["pnl"] > 0]
    win_rate = len(wins) / len(trades) if trades else 0
    total_pnl = sum(t["pnl"] for t in trades)

    # シャープレシオ
    pnls = [t["pnl"] for t in trades]
    sharpe = (np.mean(pnls) / np.std(pnls)) if len(pnls) > 1 and np.std(pnls) > 0 else 0

    return {
        "total_trades":   len(trades),
        "win_trades":     len(wins),
        "win_rate":       round(win_rate, 4),
        "total_pnl":      round(total_pnl, 0),
        "final_balance":  round(balance, 0),
        "max_drawdown":   round(max_dd, 4),
        "sharpe_ratio":   round(sharpe, 4),
        "trades":         trades,
        "equity_curve":   equity_curve,
    }


# ============================================================
# 4. パラメータ最適化（multiprocessing 並列化）
# ============================================================

# ── ワーカー関数（トップレベルで定義 = pickle 可能）─────────
def _optimize_worker(args: tuple) -> dict:
    """
    Pool.map() から呼ばれる1パターン分のバックテストワーカー。
    args = (df, cfg_combo)
    """
    df, cfg_combo = args
    result = run_backtest(df, cfg_combo)
    score = (
        result["win_rate"] * max(result["sharpe_ratio"], 0)
        if result["total_trades"] >= 10
        else -1
    )
    return {"cfg": cfg_combo, "result": result, "score": score}


def optimize(df: pd.DataFrame, base_cfg: dict) -> dict:
    """
    グリッドサーチで最適パラメータを探索。
    multiprocessing.Pool で全組み合わせを並列実行する。
    """
    print("\n🔍 パラメータ最適化開始（並列処理）...")

    grid = {
        "rsi_oversold":   [25, 30, 35],
        "rsi_overbought": [65, 70, 75],
        "stop_loss_pct":  [0.010, 0.015, 0.020, 0.025],
        "take_profit_pct":[0.030, 0.040, 0.050],
    }

    keys   = list(grid.keys())
    combos = list(itertools.product(*grid.values()))

    # RSI閾値の矛盾パターンを事前除外
    valid_combos = []
    for combo in combos:
        cfg = base_cfg.copy()
        for k, v in zip(keys, combo):
            cfg[k] = v
        if cfg["rsi_oversold"] < cfg["rsi_overbought"]:
            valid_combos.append(cfg)

    total    = len(valid_combos)
    n_procs  = min(cpu_count(), total, 8)   # 最大8プロセス
    print(f"  組み合わせ数: {total}パターン / プロセス数: {n_procs}")

    # (df, cfg) のペアを引数リストに変換
    args_list = [(df, cfg) for cfg in valid_combos]

    with Pool(processes=n_procs) as pool:
        results = pool.map(_optimize_worker, args_list)

    results.sort(key=lambda x: -x["score"])

    best       = results[0]
    best_cfg   = best["cfg"]
    best_result= best["result"]
    best_score = best["score"]

    print(f"✅ 最適化完了")
    print(f"  最良スコア: {best_score:.4f}")
    print(f"  最良パラメータ: RSI={best_cfg['rsi_oversold']}/{best_cfg['rsi_overbought']} "
          f"SL={best_cfg['stop_loss_pct']*100:.1f}% TP={best_cfg['take_profit_pct']*100:.1f}%")
    print(f"  勝率: {best_result['win_rate']*100:.1f}% / "
          f"DD: {best_result['max_drawdown']*100:.1f}% / "
          f"総損益: ¥{best_result['total_pnl']:+,.0f}")

    return {"best_cfg": best_cfg, "best_result": best_result, "all_results": results[:10]}


# ── 複数ペア並列実行ワーカー ─────────────────────────────────
def _pair_worker(args: tuple) -> dict:
    """
    複数ペアを並列バックテストするワーカー。
    args = (pair, candle, days, cfg, do_optimize, do_update)
    """
    pair, candle, days, cfg, do_optimize, do_update = args
    cfg = {**cfg, "_pair": pair}
    pair_overrides = cfg.get("pair_params", {}).get(pair, {})
    cfg = {**cfg, **pair_overrides}

    df = fetch_ohlcv(pair, candle, days)
    if df.empty:
        return {"pair": pair, "error": "データ取得失敗"}

    base_result = run_backtest(df, cfg)
    opt_data = optimize(df, cfg) if do_optimize else None

    report_path = write_report(pair, candle, days, base_result, opt_data, cfg)

    if do_optimize and do_update and opt_data:
        update_config(opt_data["best_cfg"])

    return {
        "pair":        pair,
        "base_result": base_result,
        "opt_data":    opt_data,
        "report":      report_path,
    }


def run_all_pairs(pairs: list, candle: str, days: int, cfg: dict,
                  do_optimize: bool = True, do_update: bool = False) -> list:
    """
    全ペアを並列バックテスト（ペア数分のプロセスを同時起動）。
    """
    n_procs = min(cpu_count(), len(pairs), 4)   # Docker では最大4並列
    print(f"\n🚀 {len(pairs)}ペアを {n_procs}プロセス並列でバックテスト開始...")

    args_list = [
        (pair, candle, days, cfg, do_optimize, do_update)
        for pair in pairs
    ]

    with Pool(processes=n_procs) as pool:
        results = pool.map(_pair_worker, args_list)

    print("\n📊 全ペア完了サマリー:")
    print(f"{'ペア':12} {'勝率':>7} {'損益':>12} {'最大DD':>7}")
    print("-" * 42)
    for r in results:
        if "error" in r:
            print(f"{r['pair']:12} エラー: {r['error']}")
        else:
            br = r["base_result"]
            print(f"{r['pair']:12} {br['win_rate']*100:6.1f}% "
                  f"¥{br['total_pnl']:+10,.0f} {br['max_drawdown']*100:6.1f}%")
    return results


# ============================================================
# 5. レポート生成
# ============================================================

def write_report(pair: str, candle: str, days: int,
                 base_result: dict, opt_data: dict,
                 base_cfg: dict) -> str:
    """バックテストレポートをMarkdownで生成"""
    now  = datetime.now().strftime("%Y%m%d_%H%M")
    path = REPORT_DIR / f"backtest_{now}.md"

    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# バックテストレポート\n\n")
        f.write(f"生成日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"銘柄: {pair} / 足種: {candle} / 期間: 過去{days}日間\n\n")

        f.write("## 現在パラメータでの結果\n\n")
        f.write("| 指標 | 値 |\n|---|---|\n")
        for k, v in [
            ("取引件数", base_result["total_trades"]),
            ("勝率",     f"{base_result['win_rate']*100:.1f}%"),
            ("総損益",   f"¥{base_result['total_pnl']:+,.0f}"),
            ("最終残高", f"¥{base_result['final_balance']:,.0f}"),
            ("最大DD",   f"{base_result['max_drawdown']*100:.1f}%"),
            ("シャープ", f"{base_result['sharpe_ratio']:.2f}"),
        ]:
            f.write(f"| {k} | {v} |\n")

        if opt_data:
            best = opt_data["best_cfg"]
            br   = opt_data["best_result"]
            f.write("\n## 最適化結果（推奨パラメータ）\n\n")
            f.write("| パラメータ | 現在値 | 推奨値 |\n|---|---|---|\n")
            for k in ["rsi_oversold","rsi_overbought","stop_loss_pct","take_profit_pct"]:
                f.write(f"| {k} | {base_cfg.get(k)} | {best.get(k)} |\n")
            f.write(f"\n推奨パラメータでの結果:\n")
            f.write(f"- 勝率: {br['win_rate']*100:.1f}%\n")
            f.write(f"- 総損益: ¥{br['total_pnl']:+,.0f}\n")
            f.write(f"- 最大DD: {br['max_drawdown']*100:.1f}%\n")
            f.write(f"- シャープ: {br['sharpe_ratio']:.2f}\n")

            f.write("\n### TOP10パラメータ組み合わせ\n\n")
            f.write("| RSI買 | RSI売 | SL | TP | 勝率 | 損益 | DD |\n|---|---|---|---|---|---|---|\n")
            for r in opt_data["all_results"][:10]:
                c = r["cfg"]
                res = r["result"]
                f.write(f"| {c['rsi_oversold']} | {c['rsi_overbought']} | "
                        f"{c['stop_loss_pct']*100:.1f}% | {c['take_profit_pct']*100:.1f}% | "
                        f"{res['win_rate']*100:.1f}% | ¥{res['total_pnl']:+,.0f} | "
                        f"{res['max_drawdown']*100:.1f}% |\n")

        f.write("\n## 直近50件のトレード\n\n")
        f.write("| 日時(JST) | 方向 | エントリー | 決済 | 損益 | 結果 |\n|---|---|---|---|---|---|\n")
        for t in base_result["trades"][-50:]:
            et = t["entry_time"]
            if hasattr(et, "strftime"):
                et_jst = (et + timedelta(hours=9)).strftime("%m/%d %H:%M")
            else:
                et_jst = str(et)
            f.write(f"| {et_jst} | {t['side'].upper()} | "
                    f"¥{t['entry_price']:,.2f} | ¥{t['exit_price']:,.2f} | "
                    f"¥{t['pnl']:+,.0f} | {t['reason']} |\n")

    return str(path)


# ============================================================
# 6. config.yaml自動更新
# ============================================================

def update_config(best_cfg: dict):
    """最適パラメータをconfig.yamlに反映"""
    cfg_path = Path(__file__).parent.parent / "config.yaml"
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)
    keys = ["rsi_oversold","rsi_overbought","stop_loss_pct","take_profit_pct"]
    old_vals = {k: cfg.get(k) for k in keys}
    for k in keys:
        cfg[k] = best_cfg[k]
    with open(cfg_path, "w") as f:
        yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False)
    print("\n✅ config.yaml を更新しました:")
    for k in keys:
        print(f"  {k}: {old_vals[k]} → {best_cfg[k]}")


# ============================================================
# 7. メイン
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="bitbank バックテストエンジン")
    parser.add_argument("--pair",     default="xlm_jpy",  help="取引ペア")
    parser.add_argument("--days",     type=int, default=365, help="過去何日分")
    parser.add_argument("--candle",    default="5min",      help="足種 (1min/5min/1hour)")
    parser.add_argument("--optimize",  action="store_true", help="パラメータ最適化を実行（並列）")
    parser.add_argument("--update",    action="store_true", help="最適パラメータをconfig.yamlに反映")
    parser.add_argument("--all-pairs", action="store_true", help="config.yamlの全ペアを並列バックテスト")
    args = parser.parse_args()

    # config読み込み
    cfg_path = Path(__file__).parent.parent / "config.yaml"
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)

    # ── 全ペア並列モード ─────────────────────────────────────
    if args.all_pairs:
        pairs = cfg.get("pairs", [])
        run_all_pairs(pairs, args.candle, args.days, cfg,
                      do_optimize=args.optimize, do_update=args.update)
        print("\n✅ 全ペアバックテスト完了！")
        return

    # ── 単一ペアモード ───────────────────────────────────────
    cfg["_pair"] = args.pair
    pair_overrides = cfg.get("pair_params", {}).get(args.pair, {})
    cfg = {**cfg, **pair_overrides}

    # データ取得
    df = fetch_ohlcv(args.pair, args.candle, args.days)
    if df.empty:
        print("データが取得できませんでした")
        sys.exit(1)

    # 現在パラメータでバックテスト
    print("\n📊 現在パラメータでバックテスト実行中...")
    base_result = run_backtest(df, cfg)
    print(f"  取引件数: {base_result['total_trades']}")
    print(f"  勝率:     {base_result['win_rate']*100:.1f}%")
    print(f"  総損益:   ¥{base_result['total_pnl']:+,.0f}")
    print(f"  最大DD:   {base_result['max_drawdown']*100:.1f}%")
    print(f"  シャープ: {base_result['sharpe_ratio']:.2f}")

    # 最適化（並列）
    opt_data = None
    if args.optimize:
        opt_data = optimize(df, cfg)
        if args.update and opt_data:
            update_config(opt_data["best_cfg"])

    # レポート生成
    report_path = write_report(args.pair, args.candle, args.days,
                               base_result, opt_data, cfg)
    print(f"\n📄 レポート生成: {report_path}")
    print("\n✅ バックテスト完了！")
    if opt_data and not args.update:
        print("💡 最適パラメータをconfig.yamlに反映するには --update を追加してください")


if __name__ == "__main__":
    main()
