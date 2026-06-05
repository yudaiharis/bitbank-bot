from datetime import datetime
from data import store
from execution.risk import (
    calc_order_size, calc_entry_price,
    check_stop_loss, check_take_profit, calc_pnl
)


class PaperEngine:
    def __init__(self, cfg: dict, loop_num: int):
        self.cfg        = cfg
        self.loop_num   = loop_num
        self.balance    = cfg.get("initial_balance_jpy", 1_000_000)
        self.position   = None
        self.trade_count = 0
        self.peak_balance = self.balance
        self.max_drawdown = 0.0
        self._entry_ticker = None   # スプレッド計算用

    def _update_drawdown(self):
        self.peak_balance = max(self.peak_balance, self.balance)
        dd = (self.peak_balance - self.balance) / self.peak_balance
        self.max_drawdown = max(self.max_drawdown, dd)

    def on_signal(self, signal: str, pair: str, ticker: dict) -> str | None:
        """
        シグナルを受け取り執行。ticker はbid/ask含む完全なTickerを渡す。
        """
        current_price = float(ticker.get("last", 0))
        action = None

        # ポジションあり → SL/TP確認
        if self.position:
            pos = self.position
            sl_hit = check_stop_loss(pos["entry_price"], current_price, pos["side"], self.cfg)
            tp_hit = check_take_profit(pos["entry_price"], current_price, pos["side"], self.cfg)

            if sl_hit or tp_hit:
                reason = "SL" if sl_hit else "TP"
                # 決済価格（成行想定）
                exit_price = calc_entry_price(ticker, "sell" if pos["side"] == "buy" else "buy", "market")
                pnl, fee_total, breakdown = calc_pnl(
                    pos["entry_price"], exit_price,
                    pos["amount_jpy"], pos["side"],
                    self.cfg,
                    entry_ticker=self._entry_ticker,
                    exit_ticker=ticker,
                )
                self.balance += pnl
                self._update_drawdown()
                store.close_trade(pos["trade_id"], exit_price, pnl, self.balance, reason)
                self.position = None
                self._entry_ticker = None
                self.trade_count += 1
                action = (
                    f"CLOSE({reason}) 約定:{exit_price:,.0f} "
                    f"pnl={pnl:+.0f}円 "
                    f"[手数料:{breakdown['exit_fee']:+.0f} "
                    f"スプレッド:{breakdown['spread_cost']:.0f}]"
                )

        # ポジションなし → エントリー判定
        if not self.position and signal in ("buy", "sell"):
            amount = calc_order_size(self.balance, current_price, self.cfg)
            if amount < 1000:
                return action
            # エントリー価格（指値・ask/bid考慮）
            entry_price = calc_entry_price(ticker, signal, "limit")
            tid = store.save_trade({
                "loop_num":    self.loop_num,
                "pair":        pair,
                "side":        signal,
                "entry_price": entry_price,
                "amount_jpy":  amount,
                "fee":         amount * self.cfg.get("maker_fee", -0.0002),
            })
            self.position = {
                "trade_id":    tid,
                "pair":        pair,
                "side":        signal,
                "entry_price": entry_price,
                "amount_jpy":  amount,
            }
            self._entry_ticker = ticker
            action = f"ENTRY({signal.upper()}) 約定:{entry_price:,.0f}"

        return action

    def force_close(self, ticker: dict):
        """ループ終了時に強制クローズ"""
        if self.position:
            pos = self.position
            exit_price = float(ticker.get("last", pos["entry_price"]))
            pnl, fee_total, _ = calc_pnl(
                pos["entry_price"], exit_price,
                pos["amount_jpy"], pos["side"],
                self.cfg,
                entry_ticker=self._entry_ticker,
                exit_ticker=ticker,
            )
            self.balance += pnl
            store.close_trade(pos["trade_id"], exit_price, pnl, self.balance, "LOOP_END")
            self.position = None
            self.trade_count += 1
