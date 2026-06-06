#!/usr/bin/env python3
"""
bitbank-bot MCP サーバー
Claude Code から自然言語でボットを操作・デバッグできる。

インストール:
  pip install mcp

Claude Code への接続（~/.claude/settings.json または プロジェクトの .claude/settings.json）:
  {
    "mcpServers": {
      "bitbank-bot": {
        "command": "python",
        "args": ["mcp_server/server.py"],
        "cwd": "/path/to/bitbank-bot",
        "env": { "TRADES_DB": "/path/to/trades.db" }
      }
    }
  }
"""

import os
import sys
import json
import sqlite3
import yaml
import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path

# プロジェクトルートを sys.path に追加
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, CallToolResult

# ── 設定 ──────────────────────────────────────────────────────
DB_PATH  = os.environ.get("TRADES_DB", str(ROOT / "trades.db"))
CFG_PATH = ROOT / "config.yaml"

server = Server("bitbank-bot")


# ── ユーティリティ ────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def load_cfg() -> dict:
    with open(CFG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)

def save_cfg(cfg: dict):
    with open(CFG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False)

def jst_now() -> str:
    return datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M JST")

def ok(text: str) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=text)])


# ── ツール定義 ────────────────────────────────────────────────

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_status",
            description="ボットの現在状態を取得する。残高・総損益・勝率・最大DD・ループ番号を返す。",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="get_positions",
            description="現在保有中のすべてのポジションと含み損益を返す。現在価格が必要な場合は bitbank API から取得する。",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="get_signal",
            description="指定ペアの現在シグナル（buy/sell/hold）と1時間足トレンドを返す。",
            inputSchema={
                "type": "object",
                "properties": {
                    "pair": {"type": "string", "description": "例: xlm_jpy, xrp_jpy"}
                },
                "required": ["pair"],
            },
        ),
        Tool(
            name="evaluate_risk",
            description=(
                "現在のポートフォリオリスクを評価する。"
                "含み損合計・相関リスク・ドローダウン状況・エントリー可否を返す。"
            ),
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="get_trade_history",
            description="直近のクローズ済みトレード履歴を返す。",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "取得件数（デフォルト20）"},
                    "loop_num": {"type": "integer", "description": "ループ番号でフィルタ（省略可）"},
                },
                "required": [],
            },
        ),
        Tool(
            name="force_close_position",
            description=(
                "指定ペアのオープンポジションを強制決済する（ペーパートレード）。"
                "障害時・手動介入時に使用する。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "pair": {"type": "string", "description": "例: xlm_jpy"},
                    "reason": {"type": "string", "description": "決済理由（例: MANUAL_CLOSE）"},
                },
                "required": ["pair"],
            },
        ),
        Tool(
            name="get_config",
            description="現在の config.yaml を返す。戦略パラメータ・リスク管理設定を確認できる。",
            inputSchema={
                "type": "object",
                "properties": {
                    "section": {
                        "type": "string",
                        "description": "取得するセクション: all / strategy / risk / pairs / htf（デフォルト: all）",
                    }
                },
                "required": [],
            },
        ),
        Tool(
            name="update_config_param",
            description=(
                "config.yaml の1つのパラメータを変更する。"
                "例: rsi_oversold=20, stop_loss_pct=0.015"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "key":   {"type": "string",  "description": "パラメータ名（例: rsi_oversold）"},
                    "value": {"description": "新しい値（数値・文字列・真偽値）"},
                },
                "required": ["key", "value"],
            },
        ),
        Tool(
            name="place_paper_order",
            description=(
                "ペーパートレードで手動注文を発注する。"
                "シグナル確認後に手動でエントリーしたいとき、または障害時の代替エントリーに使用する。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "pair":       {"type": "string",  "description": "例: xlm_jpy"},
                    "side":       {"type": "string",  "description": "buy または sell"},
                    "amount_jpy": {"type": "number",  "description": "発注額（円）。省略時は position_size_pct で自動計算"},
                    "reason":     {"type": "string",  "description": "発注理由（例: MANUAL_ENTRY）"},
                },
                "required": ["pair", "side"],
            },
        ),
        Tool(
            name="run_quick_backtest",
            description="指定ペアの直近N日間バックテストを実行し、結果サマリーを返す。",
            inputSchema={
                "type": "object",
                "properties": {
                    "pair":   {"type": "string",  "description": "例: xlm_jpy"},
                    "days":   {"type": "integer", "description": "期間（デフォルト30）"},
                    "candle": {"type": "string",  "description": "足種（デフォルト 5min）"},
                },
                "required": ["pair"],
            },
        ),
    ]


# ── ツール実装 ────────────────────────────────────────────────

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> CallToolResult:

    # ── get_status ───────────────────────────────────────────
    if name == "get_status":
        cfg = load_cfg()
        try:
            conn = get_db()
            trades = conn.execute(
                "SELECT pnl, balance_after FROM trades WHERE status='closed' ORDER BY timestamp"
            ).fetchall()
            open_pos = conn.execute(
                "SELECT pair, side, entry_price, amount_jpy FROM trades WHERE status='open'"
            ).fetchall()
            conn.close()

            initial = cfg.get("initial_balance_jpy", 1_000_000)
            pnls    = [t["pnl"] for t in trades if t["pnl"] is not None]
            wins    = [p for p in pnls if p > 0]
            balance = trades[-1]["balance_after"] if trades else initial
            total_pnl = sum(pnls)
            win_rate  = len(wins) / len(pnls) * 100 if pnls else 0

            # 最大DD計算
            peak = initial
            max_dd = 0.0
            running = initial
            for t in trades:
                running += t["pnl"] or 0
                peak = max(peak, running)
                dd = (peak - running) / peak if peak > 0 else 0
                max_dd = max(max_dd, dd)

            lines = [
                f"📊 ボット状態 ({jst_now()})",
                f"  残高:     ¥{balance:,.0f}",
                f"  総損益:   ¥{total_pnl:+,.0f}",
                f"  勝率:     {win_rate:.1f}% ({len(wins)}/{len(pnls)}件)",
                f"  最大DD:   {max_dd*100:.1f}%",
                f"  Loop:     {cfg.get('pdca_loop', 1)}",
                f"  保有中:   {len(open_pos)}ポジション",
            ]
            if open_pos:
                for p in open_pos:
                    lines.append(f"    - {p['pair']} {p['side'].upper()} ¥{p['entry_price']:,.0f} ({p['amount_jpy']:,.0f}円)")
        except Exception as e:
            lines = [f"❌ DB 接続エラー: {e}", f"  DB_PATH: {DB_PATH}"]

        return ok("\n".join(lines))

    # ── get_positions ────────────────────────────────────────
    elif name == "get_positions":
        try:
            conn = get_db()
            rows = conn.execute(
                "SELECT * FROM trades WHERE status='open' ORDER BY timestamp"
            ).fetchall()
            conn.close()

            if not rows:
                return ok("📭 現在保有中のポジションはありません。")

            from data.fetcher import get_ticker
            lines = [f"📋 保有ポジション一覧 ({jst_now()})"]
            for r in rows:
                try:
                    ticker = get_ticker(r["pair"])
                    current = ticker["last"]
                    ep = r["entry_price"]
                    qty = r["amount_jpy"] / ep
                    unreal = (current - ep) * qty if r["side"] == "buy" else (ep - current) * qty
                    lines.append(
                        f"\n  {r['pair']} {r['side'].upper()}"
                        f"\n    エントリー: ¥{ep:,.2f}  現在: ¥{current:,.2f}"
                        f"\n    含み損益:   ¥{unreal:+,.0f}  ({unreal/r['amount_jpy']*100:+.2f}%)"
                        f"\n    発注額:     ¥{r['amount_jpy']:,.0f}"
                    )
                except Exception as e:
                    lines.append(f"\n  {r['pair']} {r['side'].upper()} — 価格取得失敗: {e}")
        except Exception as e:
            return ok(f"❌ エラー: {e}")

        return ok("\n".join(lines))

    # ── get_signal ───────────────────────────────────────────
    elif name == "get_signal":
        pair = arguments["pair"]
        try:
            from data.fetcher import get_ticker, get_candlestick
            from strategy.signals import get_signal as _get_signal

            cfg     = load_cfg()
            pair_cfg = {**cfg, **(cfg.get("pair_params", {}).get(pair, {}))}

            ticker  = get_ticker(pair)
            df_5min = get_candlestick(pair, candle_type=cfg.get("candle_type", "5min"), count=60)
            df_1h   = get_candlestick(pair, candle_type="1hour", count=25)

            signal = _get_signal(df_5min, pair_cfg, df_1h) if not df_5min.empty else "hold"
            trend  = pair_cfg.get("_htf_trend", "N/A")
            adx_slope = pair_cfg.get("_htf_slope_pct", 0)

            lines = [
                f"📡 {pair} シグナル ({jst_now()})",
                f"  現在価格: ¥{ticker['last']:,.4f}",
                f"  5分足シグナル: {signal.upper()}",
                f"  1時間足トレンド: {trend}（EMAスロープ: {adx_slope:+.4f}%）",
                f"  RSI閾値: {pair_cfg.get('rsi_oversold')} / {pair_cfg.get('rsi_overbought')}",
                f"  SL: {pair_cfg.get('stop_loss_pct',0)*100:.1f}%  TP: {pair_cfg.get('take_profit_pct',0)*100:.1f}%",
            ]
        except Exception as e:
            return ok(f"❌ シグナル取得エラー: {e}")

        return ok("\n".join(lines))

    # ── evaluate_risk ────────────────────────────────────────
    elif name == "evaluate_risk":
        try:
            from data.fetcher import get_ticker
            cfg  = load_cfg()
            conn = get_db()
            open_pos = [dict(r) for r in conn.execute(
                "SELECT * FROM trades WHERE status='open'"
            ).fetchall()]
            closed = conn.execute(
                "SELECT pnl, balance_after FROM trades WHERE status='closed' ORDER BY timestamp"
            ).fetchall()
            conn.close()

            initial = cfg.get("initial_balance_jpy", 1_000_000)
            balance = closed[-1]["balance_after"] if closed else initial

            # 含み損益計算
            total_unreal = 0.0
            pos_details  = []
            for p in open_pos:
                try:
                    t = get_ticker(p["pair"])
                    ep  = p["entry_price"]
                    qty = p["amount_jpy"] / ep
                    unreal = (t["last"] - ep) * qty if p["side"] == "buy" else (ep - t["last"]) * qty
                    total_unreal += unreal
                    pos_details.append((p["pair"], p["side"], unreal))
                except Exception:
                    pass

            loss_ratio = -total_unreal / balance if total_unreal < 0 else 0
            max_loss   = cfg.get("max_unrealized_loss_pct", 0.05)
            can_enter  = loss_ratio < max_loss and len(open_pos) < cfg.get("max_simultaneous_positions", 4)

            # 相関リスク
            corr_groups = cfg.get("correlation_groups", [])
            corr_risks  = []
            for group in corr_groups:
                in_group = [(p["pair"], p["side"]) for p in open_pos if p["pair"] in group]
                if len(in_group) >= 2:
                    sides = [s for _, s in in_group]
                    if len(set(sides)) == 1:
                        corr_risks.append(f"⚠️ {' + '.join(p for p,_ in in_group)} 同方向({sides[0]})で保有中")

            lines = [
                f"🛡️ リスク評価 ({jst_now()})",
                f"  残高:           ¥{balance:,.0f}",
                f"  含み損益合計:   ¥{total_unreal:+,.0f}  ({-loss_ratio*100:.2f}%)",
                f"  含み損上限:     {max_loss*100:.0f}%",
                f"  新規エントリー: {'✅ 可能' if can_enter else '❌ 停止中'}",
                f"  保有ポジション: {len(open_pos)}/{cfg.get('max_simultaneous_positions',4)}",
            ]
            for pair, side, unreal in pos_details:
                lines.append(f"    {pair} {side.upper()}: ¥{unreal:+,.0f}")
            if corr_risks:
                lines.append("\n  相関リスク:")
                lines.extend(f"    {r}" for r in corr_risks)
            else:
                lines.append("  相関リスク: なし")
        except Exception as e:
            return ok(f"❌ リスク評価エラー: {e}")

        return ok("\n".join(lines))

    # ── get_trade_history ────────────────────────────────────
    elif name == "get_trade_history":
        limit    = arguments.get("limit", 20)
        loop_num = arguments.get("loop_num")
        try:
            conn  = get_db()
            query = "SELECT * FROM trades WHERE status='closed'"
            params: list = []
            if loop_num:
                query += " AND loop_num=?"
                params.append(loop_num)
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            rows = [dict(r) for r in conn.execute(query, params).fetchall()]
            conn.close()

            if not rows:
                return ok("📭 クローズ済みトレードはありません。")

            wins  = sum(1 for r in rows if (r.get("pnl") or 0) > 0)
            total_pnl = sum(r.get("pnl") or 0 for r in rows)
            lines = [
                f"📜 直近{len(rows)}件 ({jst_now()})",
                f"  勝率: {wins}/{len(rows)}  総損益: ¥{total_pnl:+,.0f}",
                "",
                f"{'日時':16} {'ペア':10} {'方向':5} {'損益':>10} {'結果':5}",
                "-" * 55,
            ]
            for r in rows:
                ts  = (r.get("timestamp") or "")[:16]
                pnl = r.get("pnl") or 0
                lines.append(
                    f"{ts:16} {r['pair']:10} {r['side'].upper():5} "
                    f"¥{pnl:>+8,.0f} {r.get('reason',''):5}"
                )
        except Exception as e:
            return ok(f"❌ エラー: {e}")

        return ok("\n".join(lines))

    # ── force_close_position ─────────────────────────────────
    elif name == "force_close_position":
        pair   = arguments["pair"]
        reason = arguments.get("reason", "MANUAL_CLOSE")
        try:
            from data.fetcher import get_ticker
            conn = get_db()
            pos  = conn.execute(
                "SELECT * FROM trades WHERE pair=? AND status='open'", (pair,)
            ).fetchone()
            if not pos:
                conn.close()
                return ok(f"❌ {pair} のオープンポジションは存在しません。")

            ticker     = get_ticker(pair)
            exit_price = ticker["last"]
            ep  = pos["entry_price"]
            qty = pos["amount_jpy"] / ep
            gross = (exit_price - ep) * qty if pos["side"] == "buy" else (ep - exit_price) * qty

            # 手数料（簡易）
            cfg = load_cfg()
            fee = pos["amount_jpy"] * cfg.get("taker_fee", 0.0012)
            pnl = gross - fee

            conn.execute("""
                UPDATE trades SET exit_price=?, pnl=?, status='closed', reason=?
                WHERE id=?
            """, (exit_price, pnl, reason, pos["id"]))
            conn.commit()
            conn.close()

            lines = [
                f"✅ {pair} を強制決済しました ({jst_now()})",
                f"  決済価格: ¥{exit_price:,.4f}",
                f"  損益:     ¥{pnl:+,.0f}",
                f"  理由:     {reason}",
            ]
        except Exception as e:
            return ok(f"❌ 強制決済エラー: {e}")

        return ok("\n".join(lines))

    # ── get_config ───────────────────────────────────────────
    elif name == "get_config":
        section = arguments.get("section", "all")
        cfg = load_cfg()

        sections = {
            "strategy": ["strategy", "rsi_period", "rsi_oversold", "rsi_overbought",
                         "bb_period", "bb_std", "candle_type"],
            "risk":     ["stop_loss_pct", "take_profit_pct", "position_size_pct",
                         "max_simultaneous_positions", "max_unrealized_loss_pct",
                         "max_consecutive_sl", "sl_cooldown_minutes", "correlation_groups"],
            "htf":      ["use_htf_filter", "htf_ema_period", "htf_flat_threshold"],
            "pairs":    ["pairs", "excluded_pairs", "pair_params"],
        }

        if section != "all" and section in sections:
            data = {k: cfg.get(k) for k in sections[section]}
        else:
            data = cfg

        return ok(f"⚙️ config.yaml ({section}):\n\n" + yaml.dump(data, allow_unicode=True, default_flow_style=False))

    # ── update_config_param ──────────────────────────────────
    elif name == "update_config_param":
        key   = arguments["key"]
        value = arguments["value"]
        try:
            cfg = load_cfg()
            old_val = cfg.get(key, "（未設定）")

            # 型変換（文字列で渡された数値・真偽値を適切に変換）
            if isinstance(value, str):
                if value.lower() in ("true", "false"):
                    value = value.lower() == "true"
                else:
                    try:
                        value = int(value) if "." not in value else float(value)
                    except ValueError:
                        pass  # 文字列のまま

            cfg[key] = value
            save_cfg(cfg)
            return ok(
                f"✅ config.yaml を更新しました\n"
                f"  {key}: {old_val} → {value}\n"
                f"  ※ 変更を反映するにはボットを再起動してください"
            )
        except Exception as e:
            return ok(f"❌ 更新エラー: {e}")

    # ── place_paper_order ────────────────────────────────────
    elif name == "place_paper_order":
        pair       = arguments["pair"]
        side       = arguments["side"].lower()
        reason     = arguments.get("reason", "MANUAL_ENTRY")
        if side not in ("buy", "sell"):
            return ok(f"❌ side は buy または sell を指定してください: {side}")
        try:
            from data.fetcher import get_ticker
            cfg    = load_cfg()
            ticker = get_ticker(pair)
            price  = ticker["last"]

            conn = get_db()
            # 既存オープンポジション確認
            existing = conn.execute(
                "SELECT id FROM trades WHERE pair=? AND status='open'", (pair,)
            ).fetchone()
            if existing:
                conn.close()
                return ok(f"⚠️ {pair} のオープンポジションが既に存在します。先に force_close_position で決済してください。")

            # 残高取得
            closed = conn.execute(
                "SELECT balance_after FROM trades WHERE status='closed' ORDER BY timestamp DESC LIMIT 1"
            ).fetchone()
            balance = closed["balance_after"] if closed else cfg.get("initial_balance_jpy", 1_000_000)

            amount_jpy = arguments.get("amount_jpy") or balance * cfg.get("position_size_pct", 0.05)
            if amount_jpy > balance:
                conn.close()
                return ok(f"❌ 発注額 ¥{amount_jpy:,.0f} が残高 ¥{balance:,.0f} を超えています。")

            loop_num = cfg.get("pdca_loop", 1)
            conn.execute("""
                INSERT INTO trades (pair, side, entry_price, amount_jpy, status, loop_num, timestamp, reason)
                VALUES (?, ?, ?, ?, 'open', ?, ?, ?)
            """, (pair, side, price, amount_jpy, loop_num,
                  datetime.now(timezone(timedelta(hours=9))).isoformat(), reason))
            conn.commit()
            conn.close()

            lines = [
                f"✅ {pair} 手動注文を発注しました ({jst_now()})",
                f"  方向:     {side.upper()}",
                f"  価格:     ¥{price:,.4f}",
                f"  発注額:   ¥{amount_jpy:,.0f}",
                f"  理由:     {reason}",
                f"  ※ SL/TP の自動管理はボット実行中のみ有効です",
            ]
        except Exception as e:
            return ok(f"❌ 発注エラー: {e}")

        return ok("\n".join(lines))

    # ── run_quick_backtest ───────────────────────────────────
    elif name == "run_quick_backtest":
        pair   = arguments["pair"]
        days   = arguments.get("days", 30)
        candle = arguments.get("candle", "5min")
        try:
            import subprocess
            result = subprocess.run(
                [sys.executable, str(ROOT / "backtest" / "engine.py"),
                 "--pair", pair, "--days", str(days), "--candle", candle],
                capture_output=True, text=True, cwd=str(ROOT), timeout=300
            )
            output = result.stdout + result.stderr
            # 結果行だけ抽出
            lines = [l for l in output.split("\n")
                     if any(k in l for k in ["取引件数", "勝率", "総損益", "最大DD", "シャープ", "完了", "エラー"])]
            return ok(f"📊 {pair} バックテスト ({days}日/{candle})\n\n" + "\n".join(lines))
        except Exception as e:
            return ok(f"❌ バックテストエラー: {e}")

    return ok(f"❌ 未知のツール: {name}")


# ── メイン ────────────────────────────────────────────────────

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())
