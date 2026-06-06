#!/bin/bash
# ==============================================================
# Cloudflare Tunnel セットアップスクリプト
# ドメイン不要・証明書不要・完全無料でHTTPS公開
# 前提: setup_gcp.sh 実行済み、Cloudflareアカウント取得済み
# 使い方: bash deploy/setup_cloudflare.sh
# ==============================================================
set -e

read -p "CloudflareのTunnelトークン（DEPLOY.mdのStep3で取得）: " CF_TOKEN

echo ""
echo "========================================"
echo "  Cloudflare Tunnel セットアップ開始"
echo "========================================"

# ---------- 1. cloudflared インストール ----------
echo ""
echo "[1/3] cloudflared をインストール中..."
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg \
  | sudo tee /usr/share/keyrings/cloudflare-main.gpg > /dev/null
echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] \
  https://pkg.cloudflare.com/cloudflared any main" \
  | sudo tee /etc/apt/sources.list.d/cloudflared.list
sudo apt-get update -qq
sudo apt-get install -y -qq cloudflared
echo "  cloudflared インストール完了: $(cloudflared --version)"

# ---------- 2. nginx をシンプル設定に変更 ----------
# Cloudflare Tunnelを使う場合、nginxは80/443を外部に開けず
# 127.0.0.1:5000へのリバースプロキシだけでよい
echo ""
echo "[2/3] nginx をローカル専用設定に更新中..."
sudo tee /etc/nginx/sites-available/bitbank > /dev/null << 'EOF'
server {
    listen 127.0.0.1:8080;
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $http_cf_connecting_ip;
        proxy_read_timeout 30;
    }
}
EOF
sudo nginx -t
sudo systemctl restart nginx

# ---------- 3. cloudflared systemdサービス ----------
echo ""
echo "[3/3] cloudflared をサービスとして登録中..."
sudo cloudflared service install "$CF_TOKEN"
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
sleep 3

# 状態確認
if sudo systemctl is-active --quiet cloudflared; then
    echo "  cloudflared 起動成功"
else
    echo "  [警告] cloudflared の起動に失敗しました"
    sudo journalctl -u cloudflared --no-pager -n 20
    exit 1
fi

echo ""
echo "========================================"
echo "  Cloudflare Tunnel 設定完了！"
echo "========================================"
echo ""
echo "  ダッシュボードURL は Cloudflareコンソールで確認："
echo "  https://one.dash.cloudflare.com/"
echo "  → Zero Trust → Networks → Tunnels"
echo "  → 該当トンネルの Public Hostname タブ"
echo ""
echo "  ★ GCPのファイアウォール設定:"
echo "    ポート80/443の外部公開は不要です（Cloudflareが終端）"
echo "    既存のallow-httpルールは残しても問題ありません"
echo ""
echo "  ログ確認:"
echo "    sudo journalctl -u cloudflared -f"
echo "    sudo journalctl -u bitbank-bot -f"
echo "    sudo journalctl -u bitbank-web -f"
echo "========================================"
