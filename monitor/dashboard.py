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

    # ── ヘッダー ─────────────────────────────────────────────
    now  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    loop = state.get("loop_num", 1)
    mode = state.get("mode", "paper").upper()
    open_pos = len(state.get("positions", {}))
    layout["header"].update(Panel(
        f"[bold]bitbank ペーパートレードbot[/bold]  [{now}]  "
        f"Loop {loop}  Mode: {mode}  "
        f"[cyan]ポジション: {open_pos}[/cyan]",
        style="blue"
    ))

    # ── 左パネル: スキャナー上位3銘柄 ────────────────────────
    scan_table = Table(title="ボラティリティ TOP3", show_header=True, header_style="bold cyan")
    scan_table.add_column("ペア", width=12)
    scan_table.add_column("スコア", justify="right")
    scan_table.add_column("価格", justify="right")
    for r in state.get("ranked", [])[:3]:
        has_pos = r["pair"] in state.get("positions", {})
        mark = " 🔵" if has_pos else ""
        scan_table.add_row(
            r["pair"] + mark,
            f"{r['score']:.4f}",
            f"{r['last']:,.0f}",
        )
    layout["left"].update(Panel(scan_table, title="スキャナー"))

    # ── 右パネル: 複数ポジション一覧 ＋ 統計 ─────────────────
    positions = state.get("positions", {})

    pos_table = Table(show_header=True, header_style="bold green", box=None, padding=(0, 1))
    pos_table.add_column("ペア",       width=10)
    pos_table.add_column("方向",       width=5)
    pos_table.add_column("エントリー", justify="right", width=12)

    if positions:
        for pair, pos in positions.items():
            side_color = "green" if pos["side"] == "buy" else "red"
            pos_table.add_row(
                pair,
                f"[{side_color}]{pos['side'].upper()}[/{side_color}]",
                f"¥{pos['entry_price']:,.0f}",
            )
    else:
        pos_table.add_row("[dim]ポジションなし[/dim]", "", "")

    stats = state.get("stats", {})
    stats_text = (
        f"残高: ¥{state.get('balance', 0):,.0f}\n"
        f"取引数: {stats.get('total', 0)}\n"
        f"勝率: {stats.get('win_rate', 0)*100:.1f}%\n"
        f"総損益: ¥{stats.get('total_pnl', 0):+,.0f}\n"
        f"最大DD: {stats.get('max_dd', 0)*100:.1f}%\n"
        f"同時保有: {stats.get('open_positions', 0)}件"
    )

    right_content = Text()
    right_content.append(stats_text)

    layout["right"].update(Panel(
        f"{right_content}\n",
        title="統計",
    ))
    # ポジションテーブルを左パネル下部に追加
    layout["left"].update(Panel(
        f"{scan_table}\n{pos_table}",
        title="スキャナー / ポジション"
    ))

    # ── フッター ─────────────────────────────────────────────
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
