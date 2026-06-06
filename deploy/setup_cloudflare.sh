#!/bin/bash
# ==============================================================
# Cloudflare Tunnel セットアップ（Docker Compose 版）
# ドメイン不要・証明書不要・完全無料でHTTPS公開
# 前提: setup_gcp_docker.sh 実行済み、Cloudflareアカウント取得済み
#
# 使い方: bash deploy/setup_cloudflare.sh
# ==============================================================
set -e

BOT_DIR="/opt/bitbank-bot"
ENV_FILE="$BOT_DIR/.env"

echo "========================================"
echo "  Cloudflare Tunnel セットアップ（Docker版）"
echo "========================================"
echo ""
echo "  事前準備："
echo "  1. https://one.dash.cloudflare.com/ にログイン"
echo "  2. Zero Trust → Networks → Tunnels → 「Create a tunnel」"
echo "  3. Connector: Docker を選択"
echo "  4. トークン文字列（eyJ... で始まる）をコピー"
echo "  5. Public Hostname を設定："
echo "     Subdomain: bitbank（任意）"
echo "     Domain: 自分のドメイン"
echo "     Service: http://web:5000"
echo ""

# ---------- トークン入力 ----------
if grep -q "^CF_TUNNEL_TOKEN=.\+$" "$ENV_FILE" 2>/dev/null; then
    echo "  .env に CF_TUNNEL_TOKEN がすでに設定されています。"
    read -p "  上書きしますか？ [y/N]: " OVERWRITE
    if [[ "$OVERWRITE" != "y" && "$OVERWRITE" != "Y" ]]; then
        echo "  既存の設定を使用します。"
    else
        read -p "  Cloudflare Tunnel トークン: " CF_TOKEN
        sed -i "s|^CF_TUNNEL_TOKEN=.*|CF_TUNNEL_TOKEN=$CF_TOKEN|" "$ENV_FILE"
        echo "  .env を更新しました。"
    fi
else
    read -p "  Cloudflare Tunnel トークン: " CF_TOKEN
    if [ -z "$CF_TOKEN" ]; then
        echo "  ❌ トークンが空です。中断します。"
        exit 1
    fi
    # .env に CF_TUNNEL_TOKEN を追記または更新
    if grep -q "^CF_TUNNEL_TOKEN=" "$ENV_FILE" 2>/dev/null; then
        sed -i "s|^CF_TUNNEL_TOKEN=.*|CF_TUNNEL_TOKEN=$CF_TOKEN|" "$ENV_FILE"
    else
        echo "CF_TUNNEL_TOKEN=$CF_TOKEN" >> "$ENV_FILE"
    fi
    echo "  .env に CF_TUNNEL_TOKEN を保存しました。"
fi

# ---------- cloudflared コンテナを起動 ----------
echo ""
echo "  cloudflared コンテナを起動中..."
cd "$BOT_DIR"
docker compose --profile cloudflare up -d cloudflared
sleep 3

# ---------- 状態確認 ----------
if docker compose ps cloudflared | grep -q "Up\|running"; then
    echo "  ✅ cloudflared 起動成功"
else
    echo "  ❌ 起動に失敗しました。ログを確認してください："
    docker compose logs --tail=30 cloudflared
    exit 1
fi

echo ""
echo "========================================"
echo "  Cloudflare Tunnel 設定完了！"
echo "========================================"
echo ""
echo "  HTTPS URL は Cloudflare コンソールで確認："
echo "  https://one.dash.cloudflare.com/"
echo "  → Zero Trust → Networks → Tunnels → 該当トンネル"
echo "  → Public Hostname タブ"
echo ""
echo "  ★ GCP ファイアウォール："
echo "    8080/443/80 の外部公開は不要です（Cloudflare が終端）"
echo ""
echo "  よく使うコマンド："
echo "    docker compose --profile cloudflare ps"
echo "    docker compose logs -f cloudflared"
echo "    docker compose --profile cloudflare restart cloudflared"
echo "========================================"
