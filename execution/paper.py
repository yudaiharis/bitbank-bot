import time
from datetime import datetime
from data import store
from execution.risk import (
    calc_order_size, calc_entry_price,
    check_stop_loss, check_take_profit, calc_pnl
)


class PaperEngine:
    """
    複数ペア同時ポジション対応のペーパートレードエンジン。

    ── エントリーガード（can_enter / on_signal 内） ─────────────
    1. 最大同時ポジション数 (max_simultaneous_positions)
    2. 含み損合計上限 (max_unrealized_loss_pct)
       → 全ポジションの含み損合計が残高の X% 超でエントリー停止
    3. 高相関ペアの同方向重複禁止 (correlation_groups)
       → 同グループ・同方向のポジションが既に存在する場合はブロック
    4. 連続SLクールダウン (max_consecutive_sl / sl_cooldown_minutes)
    """

    def __init__(self, cfg: dict, loop_num: int):
        self.cfg              = cfg
        self.loop_num         = loop_num
        self.balance          = cfg.get("initial_balance_jpy", 1_000_000)
        self.positions        = {}   # pair -> position dict
        self._entry_tickers   = {}   # pair -> ticker at entry
        self._last_prices     = {}   # pair -> 直近価格（含み損計算用）
        self.trade_count      = 0
        self.peak_balance     = self.balance
        self.max_drawdown     = 0.0
        # 連続SLクールダウン管理
        self._consecutive_sl    = {}
        self._sl_cooldown_until = {}

    # ── ユーティリティ ──────────────────────────────────────────

    def _update_drawdown(self):
        self.peak_balance = max(self.peak_balance, self.balance)
        dd = (self.peak_balance - self.balance) / self.peak_balance
        self.max_drawdown = max(self.max_drawdown, dd)

    def has_position(self, pair: str) -> bool:
        return pair in self.positions

    def pair_cfg(self, pair: str) -> dict:
        """ベースcfg にペア固有パラメータをマージして返す"""
        overrides = self.cfg.get("pair_params", {}).get(pair, {})
        return {**self.cfg, **overrides}

    # ── 含み損計算 ──────────────────────────────────────────────

    def _calc_total_unrealized(self) -> float:
        """
        全オープンポジションの含み損益合計を計算する。
        直近価格が不明な場合はエントリー価格で代替（損益ゼロ扱い）。
        """
        total = 0.0
        for pair, pos in self.positions.items():
            last = self._last_prices.get(pair, pos["entry_price"])
            ep   = pos["entry_price"]
            qty  = pos["amount_jpy"] / ep
            if pos["side"] == "buy":
                total += (last - ep) * qty
            else:
                total += (ep - last) * qty
        return total

    def unrealized_loss_ratio(self) -> float:
        """含み損が残高に占める割合（損失は正の値で返す）"""
        unreal = self._calc_total_unrealized()
        return -unreal / self.balance if unreal < 0 else 0.0

    # ── エントリー可否チェック ──────────────────────────────────

    def can_enter(self) -> bool:
        """
        シグナル取得前の高速チェック。
        ① 最大同時ポジション数
        ② 含み損合計上限
        """
        # ① ポジション数
        if len(self.positions) >= self.cfg.get("max_simultaneous_positions", 4):
            return False

        # ② 含み損上限
        max_loss_pct = self.cfg.get("max_unrealized_loss_pct", 0.05)
        if self.unrealized_loss_ratio() >= max_loss_pct:
            return False

        return True

    def _check_correlation(self, pair: str, signal: str) -> str | None:
        """
        相関グループチェック。
        同一グループ・同方向のポジションが既にある場合は理由文字列を返す。
        問題なければ None を返す。
        """
        corr_groups = self.cfg.get("correlation_groups", [])
        for group in corr_groups:
            if pair not in group:
                continue
            for ep, epos in self.positions.items():
                if ep in group and ep != pair and epos["side"] == signal:
                    return (
                        f"SKIP {pair}（{ep} と高相関・同方向 {signal.upper()} "
                        f"→ 重複エントリー禁止）"
                    )
        return None

    # ── 連続SLクールダウン ──────────────────────────────────────

    def is_in_cooldown(self, pair: str) -> bool:
        return time.time() < self._sl_cooldown_until.get(pair, 0)

    def _record_sl(self, pair: str):
        max_sl       = self.cfg.get("max_consecutive_sl", 3)
        cooldown_min = self.cfg.get("sl_cooldown_minutes", 60)
        self._consecutive_sl[pair] = self._consecutive_sl.get(pair, 0) + 1
        if self._consecutive_sl[pair] >= max_sl:
            self._sl_cooldown_until[pair] = time.time() + cooldown_min * 60
            self._consecutive_sl[pair] = 0

    def _record_tp(self, pair: str):
        self._consecutive_sl[pair] = 0

    # ── エントリー ──────────────────────────────────────────────

    def on_signal(self, signal: str, pair: str, ticker: dict) -> str | None:
        """
        シグナルを受け取りエントリーを執行する。
        SL/TP確認は check_exit() で別途行う。

        ガード順序:
          1. 既存ポジション確認
          2. シグナル確認
          3. can_enter()（ポジション数・含み損上限）
          4. 相関チェック（同方向重複禁止）
          5. クールダウン確認
        """
        if self.has_position(pair) or signal not in ("buy", "sell"):
            return None

        # 直近価格を更新（含み損計算に使用）
        self._last_prices[pair] = float(ticker.get("last", 0))

        if not self.can_enter():
            loss_ratio = self.unrealized_loss_ratio() * 100
            return (
                f"SKIP {pair}（含み損上限 {loss_ratio:.1f}% / "
                f"最大ポジション数到達）"
                if loss_ratio >= self.cfg.get("max_unrealized_loss_pct", 0.05) * 100
                else None
            )

        corr_msg = self._check_correlation(pair, signal)
        if corr_msg:
            return corr_msg

        if self.is_in_cooldown(pair):
            remaining = int((self._sl_cooldown_until[pair] - time.time()) / 60)
            return f"COOLDOWN {pair}（連続SL後 あと{remaining}分）"

        # ── エントリー実行 ──────────────────────────────────
        pcfg          = self.pair_cfg(pair)
        current_price = float(ticker.get("last", 0))
        amount        = calc_order_size(self.balance, current_price, pcfg)
        if amount < 1000:
            return None

        entry_price = calc_entry_price(ticker, signal, "limit")
        tid = store.save_trade({
            "loop_num":    self.loop_num,
            "pair":        pair,
            "side":        signal,
            "entry_price": entry_price,
            "amount_jpy":  amount,
            "fee":         amount * pcfg.get("maker_fee", -0.0002),
        })
        self.positions[pair] = {
            "trade_id":    tid,
            "pair":        pair,
            "side":        signal,
            "entry_price": entry_price,
            "amount_jpy":  amount,
        }
        self._entry_tickers[pair] = ticker
        self._last_prices[pair]   = entry_price
        return f"ENTRY({signal.upper()}) {pair} 約定:{entry_price:,.0f}"

    # ── 決済確認 ────────────────────────────────────────────────

    def check_exit(self, pair: str, ticker: dict) -> str | None:
        """
        指定ペアのポジションの SL/TP を確認し、発動すれば決済する。
        """
        if not self.has_position(pair):
            return None

        current_price = float(ticker.get("last", 0))
        self._last_prices[pair] = current_price  # 含み損計算用に価格を更新

        pcfg = self.pair_cfg(pair)
        pos  = self.positions[pair]

        sl_hit = check_stop_loss(pos["entry_price"], current_price, pos["side"], pcfg)
        tp_hit = check_take_profit(pos["entry_price"], current_price, pos["side"], pcfg)

        if not (sl_hit or tp_hit):
            return None

        reason     = "SL" if sl_hit else "TP"
        exit_price = calc_entry_price(
            ticker,
            "sell" if pos["side"] == "buy" else "buy",
            "market"
        )
        pnl, fee_total, breakdown = calc_pnl(
            pos["entry_price"], exit_price,
            pos["amount_jpy"], pos["side"],
            pcfg,
            entry_ticker=self._entry_tickers.get(pair),
            exit_ticker=ticker,
        )
        self.balance += pnl
        self._update_drawdown()

        if sl_hit:
            self._record_sl(pair)
        else:
            self._record_tp(pair)

        store.close_trade(pos["trade_id"], exit_price, pnl, self.balance, reason)
        del self.positions[pair]
        self._entry_tickers.pop(pair, None)
        self.trade_count += 1

        return (
            f"CLOSE({reason}) {pair} 約定:{exit_price:,.0f} "
            f"pnl={pnl:+.0f}円 "
            f"[手数料:{breakdown['exit_fee']:+.0f} "
            f"スプレッド:{breakdown['spread_cost']:.0f}]"
        )

    # ── 強制クローズ ────────────────────────────────────────────

    def force_close(self, pair: str, ticker: dict):
        """指定ペアを強制決済する（ループ終了時など）"""
        if not self.has_position(pair):
            return
        pos        = self.positions[pair]
        pcfg       = self.pair_cfg(pair)
        exit_price = float(ticker.get("last", pos["entry_price"]))
        pnl, _, _  = calc_pnl(
            pos["entry_price"], exit_price,
            pos["amount_jpy"], pos["side"],
            pcfg,
            entry_ticker=self._entry_tickers.get(pair),
            exit_ticker=ticker,
        )
        self.balance += pnl
        store.close_trade(pos["trade_id"], exit_price, pnl, self.balance, "LOOP_END")
        del self.positions[pair]
        self._entry_tickers.pop(pair, None)
        self.trade_count += 1

    def force_close_all(self, tickers: dict):
        """全ポジションを強制決済する"""
        for pair in list(self.positions.keys()):
            t = tickers.get(pair, {"last": self.positions[pair]["entry_price"]})
            self.force_close(pair, t)
