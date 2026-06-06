#!/bin/bash
# ==============================================================
# 週次自動分析スクリプト
# cronから呼ばれる or ダッシュボードの「今すぐ分析」ボタンから起動
# ==============================================================
BOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG="$BOT_DIR/reports/analysis.log"
LOCK="$BOT_DIR/reports/.analysis_running"

# 二重起動防止
if [ -f "$LOCK" ]; then
    echo "分析がすでに実行中です" >> "$LOG"
    exit 1
fi
touch "$LOCK"

cd "$BOT_DIR"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 自動分析開始" >> "$LOG"

# 最新レポートを特定
LATEST=$(ls reports/report_*.md 2>/dev/null | sort -V | tail -1)
if [ -z "$LATEST" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] レポートなし・スキップ" >> "$LOG"
    rm -f "$LOCK"
    exit 0
fi

# Claude Codeでヘッドレス分析
source venv/bin/activate
claude -p "
以下はbitbankペーパートレードボットのループレポートです。

$(cat $LATEST)

このレポートを分析して：
1. 負けトレードのパターンを特定
2. config.yamlのパラメータを改善（ファイルを直接編集）
3. 改善内容をreports/auto_improvement_$(date +%Y%m%d).mdに保存

改善後にボットを再起動してください：
sudo systemctl restart bitbank-bot
" \
--allowedTools "Edit,Read,Bash" \
--max-turns 20 \
2>> "$LOG"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] 自動分析完了" >> "$LOG"
rm -f "$LOCK"

# Slack通知（分析完了）
if [ -n "$SLACK_WEBHOOK_URL" ]; then
    source "$BOT_DIR/venv/bin/activate" 2>/dev/null
    python3 -c "
import sys, os
sys.path.insert(0, '$BOT_DIR')
from monitor.slack_notify import notify_auto_analysis
from datetime import datetime
notify_auto_analysis(datetime.now().strftime('%Y-%m-%d %H:%M'), '自動分析・改善完了 — ダッシュボードで詳細を確認してください')
" 2>/dev/null
fi
