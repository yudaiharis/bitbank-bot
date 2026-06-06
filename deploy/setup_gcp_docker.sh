#!/bin/bash
# ==============================================================
# bitbank-bot GCP Docker セットアップスクリプト
# Ubuntu 22.04 LTS + Docker Compose で全サービスをコンテナ管理
# 使い方: bash deploy/setup_gcp_docker.sh
# ==============================================================
set -e

REPO_URL="https://github.com/yudaiharis/bitbank-bot.git"
BOT_DIR="/opt/bitbank-bot"
SERVICE_USER="$(whoami)"

echo "========================================"
echo "  bitbank-bot GCP Docker セットアップ"
echo "========================================"

# ── 0. 最低限のツールをインストール（Minimal 対応）─────────
echo ""
echo "[0/5] 基本ツールを確認中..."
sudo apt-get update -qq
sudo apt-get install -y -qq curl git ca-certificates
echo "  curl / git インストール済み"

# ── 1. Docker インストール ──────────────────────────────────
echo ""
echo "[1/5] Docker をインストール中..."
if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker "$SERVICE_USER"
    echo "  Docker インストール完了"
else
    echo "  Docker はすでにインストール済みです"
fi

# Docker Compose v2 確認
if ! docker compose version &>/dev/null; then
    sudo apt-get install -y docker-compose-plugin
fi
echo "  $(docker compose version)"

# ── 2. リポジトリをクローン ─────────────────────────────────
echo ""
echo "[2/5] リポジトリをクローン中..."
if [ -d "$BOT_DIR" ]; then
    echo "  既存ディレクトリを更新..."
    cd "$BOT_DIR" && git pull origin master
else
    sudo git clone "$REPO_URL" "$BOT_DIR"
    sudo chown -R "$SERVICE_USER:$SERVICE_USER" "$BOT_DIR"
fi
cd "$BOT_DIR"

# ── 3. .env 設定 ────────────────────────────────────────────
echo ""
echo "[3/5] 環境変数を設定中..."
if [ ! -f "$BOT_DIR/.env" ]; then
    cp "$BOT_DIR/.env.example" "$BOT_DIR/.env"
    echo ""
    echo "  ★ .env を編集してください："
    echo "    nano $BOT_DIR/.env"
    echo ""
    echo "  設定が必要な項目:"
    echo "    GITHUB_TOKEN  = GitHubのread-only PAT"
    echo "    GITHUB_REPO   = yudaiharis/bitbank-bot"
    echo "    SLACK_WEBHOOK_URL = (任意)"
    echo ""
    echo "  編集後、このスクリプトを再実行するか"
    echo "  手動で: cd $BOT_DIR && docker compose up -d"
    exit 0
else
    echo "  .env はすでに存在します"
fi

# ── 4. イメージビルド＆起動 ─────────────────────────────────
echo ""
echo "[4/5] Dockerイメージをビルドして起動中..."
cd "$BOT_DIR"
docker compose build --quiet
docker compose up -d web paper
echo "  起動完了"

# ── 5. systemd で自動起動設定 ───────────────────────────────
echo ""
echo "[5/5] systemd で自動起動を設定中..."
sudo tee /etc/systemd/system/bitbank-bot.service > /dev/null <<EOF
[Unit]
Description=bitbank-bot Docker Compose
Requires=docker.service
After=docker.service network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$BOT_DIR
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=120

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable bitbank-bot.service
echo "  自動起動を登録しました"

# ── 完了 ────────────────────────────────────────────────────
EXTERNAL_IP=$(curl -s -m 5 \
    "http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip" \
    -H "Metadata-Flavor: Google" 2>/dev/null || echo "IPアドレスを手動で確認してください")

echo ""
echo "========================================"
echo "  セットアップ完了！"
echo "========================================"
echo ""
echo "  ダッシュボード: http://$EXTERNAL_IP:8080"
echo ""
echo "  よく使うコマンド:"
echo "    docker compose logs -f          # ログ確認"
echo "    docker compose ps               # 状態確認"
echo "    docker compose restart paper    # ボット再起動"
echo "    docker compose pull && docker compose up -d  # 更新"
echo ""
echo "  バックテスト実行:"
echo "    cd $BOT_DIR"
echo "    docker compose run --rm backtest"
echo ""
echo "  ★ HTTPS 公開は Cloudflare Tunnel を設定してください:"
echo "    bash $BOT_DIR/deploy/setup_cloudflare.sh"
echo "========================================"
