import os
import json
import numpy as np
from datetime import datetime
from data.store import get_trades, save_loop_result, get_all_loop_results


def analyze(loop_num: int, balance: float, max_drawdown: float, cfg: dict) -> dict:
    """取引ログを分析してresultを返す"""
    trades = get_trades(loop_num)
    if not trades:
        return {"loop_num": loop_num, "total_trades": 0, "win_rate": 0,
                "total_pnl": 0, "max_drawdown": max_drawdown,
                "sharpe_ratio": 0, "final_balance": balance,
                "target_achieved": False, "win_trades": 0}

    pnls = [t["pnl"] for t in trades if t["pnl"] is not None]
    wins = [p for p in pnls if p > 0]
    win_rate = len(wins) / len(pnls) if pnls else 0
    total_pnl = sum(pnls)

    # シャープレシオ（簡易版）
    if len(pnls) > 1:
        mean_pnl = np.mean(pnls)
        std_pnl  = np.std(pnls)
        sharpe   = mean_pnl / std_pnl if std_pnl > 0 else 0
    else:
        sharpe = 0

    target_wr = cfg.get("target_win_rate", 0.55)
    target_dd = cfg.get("target_max_drawdown", 0.10)
    achieved  = win_rate >= target_wr and max_drawdown <= target_dd

    result = {
        "loop_num": loop_num,
        "total_trades": len(pnls),
        "win_trades": len(wins),
        "win_rate": round(win_rate, 4),
        "total_pnl": round(total_pnl, 0),
        "max_drawdown": round(max_drawdown, 4),
        "sharpe_ratio": round(sharpe, 4),
        "final_balance": round(balance, 0),
        "target_achieved": achieved,
    }
    return result


def decide_improvements(result: dict, trades: list, cfg: dict) -> tuple[dict, str]:
    """
    分析結果から改善内容を決定してcfgを更新する。
    Returns: (updated_cfg, improvement_summary)
    """
    improvements = []
    new_cfg = cfg.copy()

    win_rate = result.get("win_rate", 0)
    max_dd   = result.get("max_drawdown", 0)
    target_wr = cfg.get("target_win_rate", 0.55)
    target_dd = cfg.get("target_max_drawdown", 0.10)

    # 1. 勝率が低い → RSI閾値を調整
    if win_rate < target_wr:
        new_cfg["rsi_oversold"]   = min(cfg.get("rsi_oversold",  30) + 5, 40)
        new_cfg["rsi_overbought"] = max(cfg.get("rsi_overbought",70) - 5, 60)
        improvements.append(f"RSI閾値調整: {cfg['rsi_oversold']}→{new_cfg['rsi_oversold']}")

    # 2. ドローダウンが大きい → リスク縮小
    if max_dd > target_dd:
        new_cfg["stop_loss_pct"]    = max(cfg.get("stop_loss_pct",    0.02) - 0.005, 0.01)
        new_cfg["position_size_pct"] = max(cfg.get("position_size_pct", 0.05) - 0.01,  0.02)
        improvements.append(
            f"SL縮小: {cfg['stop_loss_pct']*100:.1f}%→{new_cfg['stop_loss_pct']*100:.1f}%"
        )

    # 3. 損失多発ペアを除外
    if trades:
        from collections import defaultdict
        pair_stats = defaultdict(lambda: {"wins": 0, "total": 0})
        for t in trades:
            pair_stats[t["pair"]]["total"] += 1
            if t["pnl"] and t["pnl"] > 0:
                pair_stats[t["pair"]]["wins"] += 1

        excluded = list(cfg.get("excluded_pairs", []))
        for pair, s in pair_stats.items():
            if s["total"] >= 3:
                wr = s["wins"] / s["total"]
                if wr < 0.35 and pair not in excluded:
                    excluded.append(pair)
                    improvements.append(f"除外: {pair}（勝率{wr*100:.0f}%）")
        new_cfg["excluded_pairs"] = excluded

    # 4. シャープレシオが低い → スキャン頻度を上げる
    if result.get("sharpe_ratio", 0) < 0.5:
        new_cfg["scan_interval_sec"] = max(cfg.get("scan_interval_sec", 900) // 2, 300)
        improvements.append("スキャン間隔を短縮")

    summary = " / ".join(improvements) if improvements else "変更なし"
    return new_cfg, summary


def write_report(loop_num: int, result: dict, improvements: str, cfg: dict):
    """reports/report_N.md を生成"""
    os.makedirs("reports", exist_ok=True)
    path = f"reports/report_{loop_num}.md"
    trades = get_trades(loop_num)

    # 損失トレードのパターン分析
    loss_trades = [t for t in trades if t.get("pnl", 0) < 0]
    loss_pairs  = {}
    for t in loss_trades:
        loss_pairs[t["pair"]] = loss_pairs.get(t["pair"], 0) + 1
    loss_pattern = ", ".join([f"{p}({n}件)" for p, n in sorted(
        loss_pairs.items(), key=lambda x: -x[1]
    )]) or "なし"

    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# Loop {loop_num} レポート\n\n")
        f.write(f"生成日時: {datetime.now().isoformat()}\n\n")
        f.write("## 結果サマリー\n")
        f.write(f"| 指標 | 値 | 目標 |\n|---|---|---|\n")
        f.write(f"| 勝率 | {result['win_rate']*100:.1f}% | {cfg.get('target_win_rate',0.55)*100:.0f}% |\n")
        f.write(f"| 最大ドローダウン | {result['max_drawdown']*100:.1f}% | {cfg.get('target_max_drawdown',0.10)*100:.0f}% |\n")
        f.write(f"| 総損益 | ¥{result['total_pnl']:+,.0f} | ー |\n")
        f.write(f"| 最終残高 | ¥{result['final_balance']:,.0f} | ー |\n")
        f.write(f"| シャープレシオ | {result['sharpe_ratio']:.2f} | >0.5 |\n")
        f.write(f"| 取引件数 | {result['total_trades']} | ー |\n\n")
        f.write(f"**目標達成: {'✅' if result['target_achieved'] else '❌'}**\n\n")
        f.write(f"## 負けトレードのパターン\n{loss_pattern}\n\n")
        f.write(f"## 自律改善内容\n{improvements}\n\n")
        f.write(f"## 次ループのconfig\n```yaml\n")
        import yaml
        f.write(yaml.dump(cfg, allow_unicode=True, default_flow_style=False))
        f.write("```\n")


def write_final_report(cfg: dict):
    """reports/final_report.md を生成"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    os.makedirs("reports", exist_ok=True)
    results = get_all_loop_results()

    # 資産推移グラフ
    loops    = [r["loop_num"]     for r in results]
    balances = [r["final_balance"] for r in results]
    win_rates = [r["win_rate"] * 100 for r in results]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7))
    ax1.plot(loops, balances, "b-o", linewidth=2)
    ax1.axhline(cfg.get("initial_balance_jpy", 1_000_000), color="gray", linestyle="--", label="初期残高")
    ax1.set_title("仮想資産推移")
    ax1.set_ylabel("残高 (円)")
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    ax2.bar(loops, win_rates, color=["green" if w >= cfg.get("target_win_rate", 0.55)*100 else "salmon" for w in win_rates])
    ax2.axhline(cfg.get("target_win_rate", 0.55)*100, color="red", linestyle="--", label="目標勝率")
    ax2.set_title("ループ別勝率")
    ax2.set_ylabel("勝率 (%)")
    ax2.legend()
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig("reports/asset_chart.png", dpi=120)
    plt.close()

    with open("reports/final_report.md", "w", encoding="utf-8") as f:
        f.write("# 自律PDCA 最終レポート\n\n")
        f.write(f"生成日時: {datetime.now().isoformat()}\n\n")
        f.write("## ループ別結果\n")
        f.write("| Loop | 勝率 | 最大DD | 総損益 | 最終残高 | 達成 |\n|---|---|---|---|---|---|\n")
        for r in results:
            f.write(f"| {r['loop_num']} | {r['win_rate']*100:.1f}% | {r['max_drawdown']*100:.1f}% "
                    f"| ¥{r['total_pnl']:+,.0f} | ¥{r['final_balance']:,.0f} "
                    f"| {'✅' if r['target_achieved'] else '❌'} |\n")
        f.write("\n![資産推移](asset_chart.png)\n\n")
        f.write("## 採用した改善内容\n")
        for r in results:
            if r.get("improvements"):
                f.write(f"- Loop {r['loop_num']}: {r['improvements']}\n")
        f.write("\n## 推奨 config.yaml（本番移行用）\n```yaml\n")
        import yaml
        f.write(yaml.dump(cfg, allow_unicode=True, default_flow_style=False))
        f.write("```\n")
    print("\n✅ 最終レポート生成: reports/final_report.md")
    print("✅ 資産推移グラフ: reports/asset_chart.png")
