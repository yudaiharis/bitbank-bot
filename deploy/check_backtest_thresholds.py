#!/usr/bin/env python3
"""
バックテスト閾値チェックスクリプト
GitHub Actions の「閾値チェック」ステップから呼ばれる。

環境変数で閾値を設定:
  BT_MIN_WIN_RATE       平均勝率の下限（デフォルト 0.40）
  BT_MAX_DRAWDOWN       平均最大DDの上限（デフォルト 0.05）
  BT_MIN_POSITIVE_PAIRS プラス損益ペア数の下限（デフォルト 4）

GitHub Actions の output に書き込む:
  passed  = true / false
  summary = 判定結果の要約文
"""

import os
import sys
import re
import glob
from pathlib import Path

# ── 閾値 ──────────────────────────────────────────────────────
MIN_WIN_RATE       = float(os.environ.get("BT_MIN_WIN_RATE",       "0.40"))
MAX_DRAWDOWN       = float(os.environ.get("BT_MAX_DRAWDOWN",       "0.05"))
MIN_POSITIVE_PAIRS = int(os.environ.get("BT_MIN_POSITIVE_PAIRS",  "4"))

ROOT = Path(__file__).parent.parent


def parse_latest_reports() -> list[dict]:
    """
    reports/backtest_*.md の中から直近7ペア分（最新タイムスタンプ）を解析する。
    """
    pattern = str(ROOT / "reports" / "backtest_*.md")
    files   = sorted(glob.glob(pattern), reverse=True)  # 新しい順

    seen_pairs = {}
    for path in files:
        text = Path(path).read_text(encoding="utf-8")

        # ヘッダーからペアを取得
        m_pair = re.search(r"銘柄: (\w+) /", text)
        if not m_pair:
            continue
        pair = m_pair.group(1)
        if pair in seen_pairs:          # 同ペアの古いレポートはスキップ
            continue

        # 結果テーブルから値を抽出
        m_wr  = re.search(r"\| 勝率 \| ([\d.]+)%",  text)
        m_dd  = re.search(r"\| 最大DD \| ([\d.]+)%", text)
        m_pnl = re.search(r"\| 総損益 \| ¥([+\-\d,]+)", text)

        if not (m_wr and m_dd and m_pnl):
            continue

        win_rate    = float(m_wr.group(1))  / 100
        max_dd      = float(m_dd.group(1))  / 100
        total_pnl   = float(m_pnl.group(1).replace(",", "").replace("¥", ""))

        seen_pairs[pair] = {
            "pair":      pair,
            "win_rate":  win_rate,
            "max_dd":    max_dd,
            "total_pnl": total_pnl,
        }

    return list(seen_pairs.values())


def write_github_output(key: str, value: str):
    """GitHub Actions の output に書き込む"""
    output_file = os.environ.get("GITHUB_OUTPUT", "")
    line = f"{key}={value}\n"
    if output_file:
        with open(output_file, "a", encoding="utf-8") as f:
            f.write(line)
    else:
        print(f"[OUTPUT] {line.strip()}")


def main():
    results = parse_latest_reports()

    if not results:
        msg = "❌ バックテストレポートが見つかりません"
        print(msg)
        write_github_output("passed",  "false")
        write_github_output("summary", msg)
        sys.exit(0)

    # ── 集計 ──────────────────────────────────────────────────
    avg_win_rate  = sum(r["win_rate"]  for r in results) / len(results)
    avg_max_dd    = sum(r["max_dd"]    for r in results) / len(results)
    positive_pairs = sum(1 for r in results if r["total_pnl"] > 0)
    total_pnl_sum  = sum(r["total_pnl"] for r in results)

    # ── 閾値判定 ──────────────────────────────────────────────
    ok_win_rate  = avg_win_rate  >= MIN_WIN_RATE
    ok_dd        = avg_max_dd    <= MAX_DRAWDOWN
    ok_positive  = positive_pairs >= MIN_POSITIVE_PAIRS
    passed       = ok_win_rate and ok_dd and ok_positive

    # ── 詳細ログ ──────────────────────────────────────────────
    OK  = "[OK]"
    NG  = "[NG]"
    print("=" * 60)
    print("[BACKTEST] 閾値チェック結果")
    print("=" * 60)
    print(f"{'ペア':12} {'勝率':>7} {'最大DD':>7} {'損益':>12}")
    print("-" * 42)
    for r in sorted(results, key=lambda x: -x["total_pnl"]):
        flag = OK if r["total_pnl"] > 0 else NG
        print(f"{r['pair']:12} {r['win_rate']*100:6.1f}% "
              f"{r['max_dd']*100:6.1f}% {r['total_pnl']:+10,.0f} {flag}")
    print("=" * 60)
    print(f"平均勝率:     {avg_win_rate*100:.1f}%  "
          f"(閾値 >= {MIN_WIN_RATE*100:.0f}%) {OK if ok_win_rate else NG}")
    print(f"平均最大DD:   {avg_max_dd*100:.1f}%   "
          f"(閾値 <= {MAX_DRAWDOWN*100:.0f}%)  {OK if ok_dd else NG}")
    print(f"プラスペア数: {positive_pairs}/{len(results)}   "
          f"(閾値 >= {MIN_POSITIVE_PAIRS})    {OK if ok_positive else NG}")
    print(f"総損益合計:   {total_pnl_sum:+,.0f}円")
    print("=" * 60)
    print(f"判定: {'[PASS] 合格 -> config.yaml をコミット' if passed else '[FAIL] 不合格 -> コミットスキップ'}")
    print("=" * 60)

    # ── GitHub Actions output ──────────────────────────────────
    summary_lines = [
        f"対象{len(results)}ペア | "
        f"平均勝率{avg_win_rate*100:.1f}% | "
        f"平均DD{avg_max_dd*100:.1f}% | "
        f"プラス{positive_pairs}/{len(results)}ペア | "
        f"総損益{total_pnl_sum:+,.0f}円"
    ]
    for r in results:
        flag = "[OK]" if r["total_pnl"] > 0 else "[NG]"
        summary_lines.append(
            f"{flag} {r['pair']}: 勝率{r['win_rate']*100:.1f}% "
            f"DD{r['max_dd']*100:.1f}% {r['total_pnl']:+,.0f}円"
        )

    # output は改行を含めないため \\n で結合
    summary = "\\n".join(summary_lines)

    write_github_output("passed",  str(passed).lower())
    write_github_output("summary", summary)

    # 不合格でも exit 0（後続 Job で条件分岐するため）
    sys.exit(0)


if __name__ == "__main__":
    main()
