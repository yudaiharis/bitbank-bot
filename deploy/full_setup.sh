#!/bin/bash
# ==============================================================
# bitbank-bot フルセットアップ（GCP e2-micro + Docker + Cloudflare Tunnel）
# Ubuntu 22.04 LTS Minimal で 1コマンド実行するだけで完結
#
# 使い方:
#   curl -fsSL https://raw.githubusercontent.com/yudaiharis/bitbank-bot/main/deploy/full_setup.sh | bash
# ==============================================================
set -e

REPO_URL="https://github.com/yudaiharis/bitbank-bot.git"
BOT_DIR="/opt/bitbank-bot"
SERVICE_USER="$(whoami)"
DEFAULT_BRANCH="main"

# ── カラー定義 ─────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

step()  { echo -e "\n${CYAN}${BOLD}[$1] $2${NC}"; }
ok()    { echo -e "  ${GREEN}✅ $1${NC}"; }
warn()  { echo -e "  ${YELLOW}⚠️  $1${NC}"; }
die()   { echo -e "  ${RED}❌ $1${NC}"; exit 1; }

echo -e "${BOLD}"
echo "  ╔══════════════════════════════════════════╗"
echo "  ║   bitbank-bot フルセットアップ           ║"
echo "  ║   GCP e2-micro + Docker + Cloudflare     ║"
echo "  ╚══════════════════════════════════════════╝"
echo -e "${NC}"

# ════════════════════════════════════════════════════════════
# Step 0: 事前情報入力
# ════════════════════════════════════════════════════════════
step "0/6" "セットアップ情報を入力"

echo ""
echo "  以下の情報を準備してください："
echo "  ① GitHub Personal Access Token（read-only）"
echo "     → https://github.com/settings/tokens/new?scopes=repo"
echo "  ② Slack Webhook URL（起動時に HTTPS URL が通知されます）"
echo "     → https://api.slack.com/messaging/webhooks"
echo ""
echo "  ※ Cloudflare のドメイン・トンネル設定は不要です"
echo "     起動時に *.trycloudflare.com の URL が自動発行され"
echo "     Slack に通知されます"
echo ""

read -p "  GitHub Personal Access Token (ghp_...): " GITHUB_TOKEN
[ -z "$GITHUB_TOKEN" ] && die "GITHUB_TOKEN が空です"

read -p "  Slack Webhook URL（任意・不要なら Enter）: " SLACK_WEBHOOK_URL

# ════════════════════════════════════════════════════════════
# Step 1: 基本ツール
# ════════════════════════════════════════════════════════════
step "1/6" "基本ツールをインストール"
sudo apt-get update -qq
sudo apt-get install -y -qq curl git ca-certificates
ok "curl / git インストール済み"

# ════════════════════════════════════════════════════════════
# Step 2: SWAP（e2-micro OOM対策）
# ════════════════════════════════════════════════════════════
step "2/6" "SWAP 1GB を設定（e2-micro OOM対策）"
if [ ! -f /swapfile ]; then
    sudo fallocate -l 1G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab > /dev/null
    ok "SWAP 1GB 設定完了"
else
    ok "SWAP はすでに設定済み"
fi
free -h | grep Swap | sed 's/^/    /'

# ════════════════════════════════════════════════════════════
# Step 3: Docker インストール
# ════════════════════════════════════════════════════════════
step "3/6" "Docker をインストール"
if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker "$SERVICE_USER"
    ok "Docker インストール完了"
else
    ok "Docker はすでにインストール済み: $(docker --version)"
fi

if ! sudo docker compose version &>/dev/null; then
    sudo apt-get install -y docker-compose-plugin
fi
ok "$(sudo docker compose version)"

# 以降の docker コマンドはすべて sudo 経由で実行（グループ反映不要）
DOCKER="sudo docker"
DOCKER_COMPOSE="sudo docker compose"

# ════════════════════════════════════════════════════════════
# Step 4: リポジトリをクローン
# ════════════════════════════════════════════════════════════
step "4/6" "リポジトリをクローン"
if [ -d "$BOT_DIR/.git" ]; then
    echo "  既存ディレクトリを更新中..."
    cd "$BOT_DIR"
    git pull origin "$DEFAULT_BRANCH"
else
    sudo git clone "$REPO_URL" "$BOT_DIR"
    sudo chown -R "$SERVICE_USER:$SERVICE_USER" "$BOT_DIR"
fi
ok "リポジトリ準備完了: $BOT_DIR"

# ════════════════════════════════════════════════════════════
# Step 5: .env 設定
# ════════════════════════════════════════════════════════════
step "5/6" ".env を設定"
cat > "$BOT_DIR/.env" <<EOF
GITHUB_TOKEN=$GITHUB_TOKEN
GITHUB_REPO=yudaiharis/bitbank-bot
SLACK_WEBHOOK_URL=$SLACK_WEBHOOK_URL
EOF
chmod 600 "$BOT_DIR/.env"
ok ".env を作成しました"

# ════════════════════════════════════════════════════════════
# Step 6: Docker Compose でコンテナを起動
# ════════════════════════════════════════════════════════════
step "6/6" "Docker イメージをビルドしてコンテナを起動"
cd "$BOT_DIR"

echo "  イメージをビルド中（数分かかります）..."
$DOCKER_COMPOSE build --quiet
ok "ビルド完了"

echo "  コンテナを起動中..."
$DOCKER_COMPOSE up -d
sleep 5
ok "コンテナ起動完了"

# ── systemd で VM 再起動時の自動起動を設定 ─────────────
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
ok "VM再起動時の自動起動を設定しました"

# ════════════════════════════════════════════════════════════
# 完了メッセージ
# ════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}${GREEN}"
echo "  ╔══════════════════════════════════════════╗"
echo "  ║   🎉 セットアップ完了！                  ║"
echo "  ╚══════════════════════════════════════════╝"
echo -e "${NC}"

echo "  コンテナ状態:"
$DOCKER_COMPOSE ps | sed 's/^/    /'

EXTERNAL_IP=$(curl -s -m 5 \
    "http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip" \
    -H "Metadata-Flavor: Google" 2>/dev/null || echo "（GCPメタデータ取得失敗）")

echo ""
echo -e "  ${BOLD}ダッシュボード確認:${NC}"
echo "    ローカル（VM内）: http://localhost:8080"
echo "    外部IP（HTTP）:   http://$EXTERNAL_IP:8080"
echo "    HTTPS URL:        Cloudflare コンソールで確認"
echo "                      → https://one.dash.cloudflare.com/"
echo "                      → Zero Trust → Networks → Tunnels"
echo ""
echo -e "  ${BOLD}よく使うコマンド:${NC}"
echo "    docker compose ps          # 状態確認"
echo "    docker compose logs -f paper                    # ボットログ"
echo "    docker compose logs -f cloudflared              # トンネルログ"
echo "    docker compose restart     # 全体再起動"
echo "    cd $BOT_DIR && git pull origin main && docker compose up -d"
echo "                                                     # コード更新"
echo ""
echo "  ★ GCPファイアウォールはポート開放不要（Cloudflare Tunnelが終端処理）"
echo ""
