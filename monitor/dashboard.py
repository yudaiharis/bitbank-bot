from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.layout import Layout
from rich.panel import Panel
from rich.text import Text
from datetime import datetime

console = Console()


def make_dashboard(state: dict) -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body"),
        Layout(name="footer", size=3),
    )
    layout["body"].split_row(
        Layout(name="left"),
        Layout(name="right"),
    )

    # ヘッダー
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    loop = state.get("loop_num", 1)
    mode = state.get("mode", "paper").upper()
    layout["header"].update(Panel(
        f"[bold]bitbank ペーパートレードbot[/bold]  [{now}]  Loop {loop}  Mode: {mode}",
        style="blue"
    ))

    # 左パネル: スキャナー上位3銘柄
    scan_table = Table(title="ボラティリティ TOP3", show_header=True, header_style="bold cyan")
    scan_table.add_column("ペア", width=12)
    scan_table.add_column("スコア", justify="right")
    scan_table.add_column("価格", justify="right")
    for r in state.get("ranked", [])[:3]:
        mark = " ◀" if r["pair"] == state.get("active_pair") else ""
        scan_table.add_row(
            r["pair"] + mark,
            f"{r['score']:.4f}",
            f"{r['last']:,.0f}",
        )
    layout["left"].update(Panel(scan_table, title="スキャナー"))

    # 右パネル: ポジション＋統計
    pos = state.get("position")
    pos_text = Text()
    if pos:
        price_now = state.get("current_price", 0)
        unreal = (price_now - pos["entry_price"]) / pos["entry_price"] * 100
        if pos["side"] == "sell":
            unreal = -unreal
        color = "green" if unreal >= 0 else "red"
        pos_text.append(f"ペア: {pos['pair']}\n")
        pos_text.append(f"方向: {pos['side'].upper()}\n")
        pos_text.append(f"エントリー: {pos['entry_price']:,.0f}\n")
        pos_text.append(f"含み損益: ", style="bold")
        pos_text.append(f"{unreal:+.2f}%\n", style=color)
    else:
        pos_text.append("ポジションなし", style="dim")

    stats = state.get("stats", {})
    stats_text = (
        f"残高: ¥{state.get('balance', 0):,.0f}\n"
        f"取引数: {stats.get('total', 0)}\n"
        f"勝率: {stats.get('win_rate', 0)*100:.1f}%\n"
        f"総損益: ¥{stats.get('total_pnl', 0):+,.0f}\n"
        f"最大DD: {stats.get('max_dd', 0)*100:.1f}%\n"
        f"銘柄切替: {stats.get('switches', 0)}回"
    )
    layout["right"].update(Panel(
        f"{pos_text}\n{stats_text}",
        title="ポジション / 統計"
    ))

    # フッター
    last_action = state.get("last_action", "待機中...")
    layout["footer"].update(Panel(f"最終アクション: {last_action}", style="dim"))

    return layout


def print_loop_summary(result: dict):
    console.rule(f"[bold blue]Loop {result['loop_num']} 完了[/bold blue]")
    color = "green" if result.get("target_achieved") else "yellow"
    console.print(f"勝率: [{color}]{result['win_rate']*100:.1f}%[/{color}]  "
                  f"最大DD: {result['max_drawdown']*100:.1f}%  "
                  f"最終残高: ¥{result['final_balance']:,.0f}  "
                  f"総損益: ¥{result['total_pnl']:+,.0f}")
    if result.get("improvements"):
        console.print(f"[cyan]改善内容:[/cyan] {result['improvements']}")
