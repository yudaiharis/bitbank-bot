#!/usr/bin/env python3
"""
bitbank 自律PDCAペーパートレードボット
使い方:
  python main.py --mode check    # API接続確認
  python main.py --mode paper    # 自律PDCAループ開始
"""

import argparse
import time
import yaml
import os
import sys
import signal
from datetime import datetime
from rich.console import Console
from rich.live import Live

from data.store import init_db, save_loop_result, get_all_loop_results
from data.fetcher import get_ticker, get_candlestick
from scanner.volatility import scan_pairs, should_switch
from strategy.signals import get_signal
from execution.paper import PaperEngine
from monitor.dashboard import make_dashboard, print_loop_summary
from backtest.analyzer import analyze, decide_improvements, write_report, write_final_report
from monitor import slack_notify

console = Console()
CONFIG_PATH = "config.yaml"
_running = True


def load_cfg() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_cfg(cfg: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False)


def handle_sigint(sig, frame):
    global _running
    console.print("\n[yellow]停止シグナルを受信。安全に終了します...[/yellow]")
    _running = False


signal.signal(signal.SIGINT, handle_sigint)


def mode_check():
    """API接続確認"""
    console.print("[cyan]API接続確認中...[/cyan]")
    cfg = load_cfg()
    for pair in cfg["pairs"][:3]:
        try:
            t = get_ticker(pair)
            console.print(f"  ✅ {pair}: ¥{t['last']:,.0f}")
            time.sleep(1)
        except Exception as e:
            console.print(f"  ❌ {pair}: {e}")
    console.print("[green]確認完了。python main.py --mode paper で開始できます。[/green]")


def run_paper_loop(cfg: dict, loop_num: int) -> dict:
    """1ループ分のペーパートレードを実行"""
    console.rule(f"[bold blue]Loop {loop_num} 開始[/bold blue]")

    trades_target = cfg.get("trades_per_loop", 50)
    scan_interval = cfg.get("scan_interval_sec", 900)
    trade_interval = cfg.get("trade_interval_sec", 180)

    engine = PaperEngine(cfg, loop_num)
    ranked = []
    active_pair = cfg["pairs"][0]
    last_scan = 0.0
    last_switch_time = 0.0
    switch_count = 0
    last_action = "起動完了"

    state = {
        "loop_num": loop_num,
        "mode": "paper",
        "ranked": [],
        "active_pair": active_pair,
        "position": None,
        "balance": engine.balance,
        "current_price": 0,
        "stats": {},
        "last_action": last_action,
    }

    with Live(make_dashboard(state), refresh_per_second=0.5, console=console) as live:
        while _running and engine.trade_count < trades_target:
            now = time.time()

            # スキャン（15分ごと）
            if now - last_scan > scan_interval:
                try:
                    ranked = scan_pairs(
                        cfg["pairs"],
                        cfg.get("excluded_pairs", []),
                        cfg
                    )
                    state["ranked"] = ranked
                    last_scan = now

                    # 銘柄切替判定
                    new_pair = should_switch(active_pair, ranked, engine.position, cfg, last_switch_time)
                    if new_pair:
                        console.log(f"銘柄切替: {active_pair} → {new_pair}")
                        active_pair = new_pair
                        last_switch_time = now
                        switch_count += 1
                        state["active_pair"] = active_pair
                except Exception as e:
                    console.log(f"[yellow]スキャンエラー: {e}[/yellow]")

            # シグナル確認（3分ごと）
            try:
                ticker = get_ticker(active_pair)
                current_price = ticker["last"]
                state["current_price"] = current_price

                df = get_candlestick(active_pair, count=60)
                signal = get_signal(df, cfg) if not df.empty else "hold"

                action = engine.on_signal(signal, active_pair, current_price)
                if action:
                    last_action = f"[{datetime.now().strftime('%H:%M:%S')}] {active_pair} {action}"
                    state["last_action"] = last_action

                state["position"] = engine.position
                state["balance"]  = engine.balance
                state["stats"] = {
                    "total":     engine.trade_count,
                    "win_rate":  _calc_win_rate(loop_num),
                    "total_pnl": engine.balance - cfg.get("initial_balance_jpy", 1_000_000),
                    "max_dd":    engine.max_drawdown,
                    "switches":  switch_count,
                }
                live.update(make_dashboard(state))

            except Exception as e:
                console.log(f"[yellow]シグナルエラー: {e}[/yellow]")

            time.sleep(trade_interval)

        # ループ終了 → 強制クローズ
        if engine.position:
            try:
                t = get_ticker(active_pair)
                engine.force_close(t["last"])
            except Exception:
                engine.force_close(engine.position["entry_price"])

    return {"balance": engine.balance, "max_drawdown": engine.max_drawdown}


def _calc_win_rate(loop_num: int) -> float:
    from data.store import get_trades
    trades = get_trades(loop_num)
    if not trades:
        return 0.0
    wins = sum(1 for t in trades if t.get("pnl", 0) > 0)
    return wins / len(trades)


def mode_paper():
    """自律PDCAメインエントリー"""
    init_db()
    cfg = load_cfg()
    max_loops  = cfg.get("max_loops", 5)
    target_wr  = cfg.get("target_win_rate", 0.55)
    target_dd  = cfg.get("target_max_drawdown", 0.10)
    target_con = cfg.get("target_consecutive", 3)
    consecutive = 0

    console.print("[bold green]自律PDCAペーパートレード開始[/bold green]")
    slack_notify.notify_bot_started("paper", cfg["pairs"][0], cfg.get("initial_balance_jpy", 1_000_000))
    console.print(f"目標: 勝率{target_wr*100:.0f}%以上 かつ DD{target_dd*100:.0f}%以内 を{target_con}連続達成")

    for loop_num in range(cfg.get("pdca_loop", 1), max_loops + 1):
        if not _running:
            break

        # --- D: 実行 ---
        loop_result = run_paper_loop(cfg, loop_num)
        if not _running:
            break

        # --- C: 分析 ---
        from data.store import get_trades
        trades = get_trades(loop_num)
        result = analyze(loop_num, loop_result["balance"], loop_result["max_drawdown"], cfg)

        # --- A: 改善 ---
        new_cfg, improvement_summary = decide_improvements(result, trades, cfg)
        result["improvements"] = improvement_summary
        save_loop_result(result)
        write_report(loop_num, result, improvement_summary, new_cfg)
        print_loop_summary(result)
        slack_notify.notify_loop_complete(loop_num, result)

        # 連続達成カウント
        if result["target_achieved"]:
            consecutive += 1
            console.print(f"[green]✅ 目標達成！（{consecutive}/{target_con}連続）[/green]")
        else:
            consecutive = 0

        # 収束判定
        if consecutive >= target_con:
            console.print("[bold green]🎉 目標を達成しました！[/bold green]")
            slack_notify.notify_target_achieved(result["final_balance"], loop_num)
            break
        if loop_num >= max_loops:
            console.print(f"[yellow]最大ループ数({max_loops})に到達[/yellow]")
            break

        # 次ループ準備
        new_cfg["pdca_loop"]           = loop_num + 1
        new_cfg["initial_balance_jpy"] = result["final_balance"]  # 残高を引き継ぐ
        save_cfg(new_cfg)
        cfg = new_cfg

        console.print(f"[cyan]{cfg.get('scan_interval_sec', 900)//60}分後にLoop {loop_num+1}を開始...[/cyan]")
        time.sleep(10)  # 少し待ってから次ループ

    # --- 最終レポート ---
    write_final_report(cfg)


def main():
    parser = argparse.ArgumentParser(description="bitbank 自律PDCAペーパートレードbot")
    parser.add_argument("--mode", choices=["check", "paper"], default="paper")
    args = parser.parse_args()

    if args.mode == "check":
        mode_check()
    else:
        mode_paper()


if __name__ == "__main__":
    main()
