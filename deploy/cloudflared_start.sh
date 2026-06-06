#!/bin/sh
# ============================================================
# Cloudflare Quick Tunnel 起動スクリプト
# - ドメイン不要（*.trycloudflare.com の URL が自動発行）
# - 起動後に割り当て URL を Slack に通知
# ============================================================
set -e

TARGET_URL="${TUNNEL_TARGET:-http://web:5000}"

echo "[cloudflared] Quick Tunnel を起動中... -> $TARGET_URL"

# cloudflared をバックグラウンドで起動しログをファイルに書き出す
cloudflared tunnel --no-autoupdate --url "$TARGET_URL" 2>&1 | tee /tmp/cf.log &
CF_PID=$!

# URL が出現するまで最大 90 秒待つ
TUNNEL_URL=""
for i in $(seq 1 90); do
    TUNNEL_URL=$(grep -oE 'https://[a-zA-Z0-9-]+\.trycloudflare\.com' /tmp/cf.log 2>/dev/null | head -1 || true)
    if [ -n "$TUNNEL_URL" ]; then
        break
    fi
    sleep 1
done

if [ -n "$TUNNEL_URL" ]; then
    echo "[cloudflared] ✅ Tunnel URL: $TUNNEL_URL"

    # Slack 通知
    if [ -n "$SLACK_WEBHOOK_URL" ]; then
        curl -s -X POST "$SLACK_WEBHOOK_URL" \
            -H 'Content-type: application/json' \
            -d "{\"text\":\"🌐 *bitbank-bot ダッシュボード URL（更新）*\n$TUNNEL_URL\"}" \
            > /dev/null && echo "[cloudflared] Slack 通知送信完了"
    else
        echo "[cloudflared] SLACK_WEBHOOK_URL 未設定のため通知をスキップ"
    fi
else
    echo "[cloudflared] ⚠️ URL 取得タイムアウト（90秒）。ログ: /tmp/cf.log"
fi

# cloudflared をフォアグラウンドで維持（コンテナが落ちないように）
wait $CF_PID
