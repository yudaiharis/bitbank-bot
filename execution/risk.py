"""
リスク管理・コスト計算モジュール

bitbank手数料（2026年2月時点）:
  Maker（指値）: -0.02%（受け取り・有利）
  Taker（成行）: +0.12%（支払い）

コスト構造:
  1. 取引手数料（Maker/Taker）
  2. スプレッド（bid/askの差）≒ 実質的な売買コスト
  3. スリッページ（大口注文時の価格ずれ）※ペーパートレードでは小さいため無視
"""


def calc_order_size(balance: float, price: float, cfg: dict) -> float:
    """発注JPY額を計算（残高の position_size_pct）"""
    size_pct = cfg.get("position_size_pct", 0.05)
    return balance * size_pct


def check_stop_loss(entry_price: float, current_price: float, side: str, cfg: dict) -> bool:
    """ストップロス判定。発動すべき場合True"""
    sl = cfg.get("stop_loss_pct", 0.02)
    if side == "buy":
        return current_price <= entry_price * (1 - sl)
    else:
        return current_price >= entry_price * (1 + sl)


def check_take_profit(entry_price: float, current_price: float, side: str, cfg: dict) -> bool:
    """テイクプロフィット判定。発動すべき場合True"""
    tp = cfg.get("take_profit_pct", 0.04)
    if side == "buy":
        return current_price >= entry_price * (1 + tp)
    else:
        return current_price <= entry_price * (1 - tp)


def calc_entry_price(ticker: dict, side: str, order_type: str = "limit") -> float:
    """
    実際の約定価格を計算（スプレッドを考慮）
    - 指値(limit)買い → ask価格で約定（板の売り注文に刺さる）
    - 指値(limit)売り → bid価格で約定（板の買い注文に刺さる）
    - 成行(market)   → スリッページも加味（より不利な価格）
    """
    ask = float(ticker.get("sell", ticker.get("last", 0)))
    bid = float(ticker.get("buy",  ticker.get("last", 0)))
    last = float(ticker.get("last", 0))

    if order_type == "market":
        # 成行：さらに0.05%不利な価格を想定
        if side == "buy":
            return ask * 1.0005
        else:
            return bid * 0.9995
    else:
        # 指値：ask/bid価格
        if side == "buy":
            return ask if ask > 0 else last
        else:
            return bid if bid > 0 else last


def calc_pnl(
    entry_price: float,
    exit_price: float,
    amount_jpy: float,
    side: str,
    cfg: dict,
    entry_ticker: dict = None,
    exit_ticker: dict = None,
) -> tuple:
    """
    純損益と手数料の内訳を計算して返す。
    Returns: (pnl_net, fee_total, cost_breakdown)

    コスト内訳:
      - entry_fee: エントリー手数料（Maker=受け取り/Taker=支払い）
      - exit_fee:  決済手数料
      - spread_cost: スプレッドコスト（bid/ask差）
    """
    maker_fee = cfg.get("maker_fee", -0.0002)   # -0.02%（マイナス=受け取り）
    taker_fee = cfg.get("taker_fee",  0.0012)   #  0.12%

    # エントリーはMaker（指値）、決済はSL/TPのためTakerを想定
    entry_fee_rate = maker_fee
    exit_fee_rate  = taker_fee

    qty = amount_jpy / entry_price

    # 粗利益
    if side == "buy":
        gross = (exit_price - entry_price) * qty
    else:
        gross = (entry_price - exit_price) * qty

    # 手数料（マイナス=受け取りなので引く→プラス）
    entry_fee = amount_jpy * entry_fee_rate   # 負の値=受け取り
    exit_fee  = amount_jpy * exit_fee_rate    # 正の値=支払い

    # スプレッドコスト（エントリー時のbid/ask差の半分を想定）
    spread_cost = 0.0
    if entry_ticker:
        ask = float(entry_ticker.get("sell", entry_price))
        bid = float(entry_ticker.get("buy",  entry_price))
        if ask > 0 and bid > 0:
            spread_pct = (ask - bid) / ask
            spread_cost = amount_jpy * spread_pct  # スプレッド分のコスト

    fee_total = entry_fee + exit_fee + spread_cost
    pnl_net   = gross - fee_total

    cost_breakdown = {
        "gross":        round(gross, 2),
        "entry_fee":    round(entry_fee, 2),    # 負=受け取り
        "exit_fee":     round(exit_fee, 2),     # 正=支払い
        "spread_cost":  round(spread_cost, 2),
        "fee_total":    round(fee_total, 2),
        "pnl_net":      round(pnl_net, 2),
    }

    return pnl_net, fee_total, cost_breakdown
