#!/bin/bash
# ==============================================================
# bitbank-bot GCP e2-micro セットアップスクリプト
# Ubuntu 22.04 LTS で実行してください
# 使い方: bash deploy/setup_gcp.sh
# ==============================================================
set -e

BOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BOT_USER="$(whoami)"

echo "========================================"
echo "  bitbank-bot GCP セットアップ開始"
echo "  ディレクトリ: $BOT_DIR"
echo "  ユーザー: $BOT_USER"
echo "========================================"

# ---------- 1. システムパッケージ ----------
echo ""
echo "[1/6] システムパッケージをインストール中..."
sudo apt-get update -qq
sudo apt-get install -y -qq python3-pip python3-venv nginx curl

# ---------- 2. SWAP設定（e2-micro必須） ----------
echo ""
echo "[2/6] SWAP 1GB を設定中..."
if [ ! -f /swapfile ]; then
    sudo fallocate -l 1G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
    echo "  SWAP 1GB を設定しました"
else
    echo "  SWAP はすでに設定済みです"
fi
free -h | grep Swap

# ---------- 3. Python仮想環境 ----------
echo ""
echo "[3/6] Python仮想環境を作成中..."
cd "$BOT_DIR"
python3 -m venv venv
source venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet requests pandas rich pyyaml matplotlib numpy ta flask
echo "  依存関係のインストール完了"

# ---------- 4. systemd: ボットサービス ----------
echo ""
echo "[4/6] systemdサービスを設定中..."

sudo tee /etc/systemd/system/bitbank-bot.service > /dev/null <<EOF
[Unit]
Description=bitbank Paper Trade Bot
After=network.target

[Service]
Type=simple
User=$BOT_USER
WorkingDirectory=$BOT_DIR
ExecStart=$BOT_DIR/venv/bin/python main.py --mode paper
Restart=always
RestartSec=30
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# ---------- 5. systemd: Webダッシュボードサービス ----------
sudo tee /etc/systemd/system/bitbank-web.service > /dev/null <<EOF
[Unit]
Description=bitbank Web Dashboard
After=network.target

[Service]
Type=simple
User=$BOT_USER
WorkingDirectory=$BOT_DIR
ExecStart=$BOT_DIR/venv/bin/python monitor/web_dashboard.py
Restart=always
RestartSec=10
Environment=PORT=5000
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable bitbank-bot.service
sudo systemctl enable bitbank-web.service
echo "  systemdサービスを登録しました"

# ---------- 6. nginx設定 ----------
echo ""
echo "[5/6] nginxを設定中..."

sudo tee /etc/nginx/sites-available/bitbank > /dev/null <<'EOF'
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 30;
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/bitbank /etc/nginx/sites-enabled/bitbank
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx
sudo systemctl enable nginx
echo "  nginx設定完了"

# ---------- 起動 ----------
echo ""
echo "[6/6] サービスを起動中..."
sudo systemctl start bitbank-web.service
sleep 3
sudo systemctl start bitbank-bot.service
sleep 2

echo ""
echo "========================================"
echo "  セットアップ完了！"
echo "========================================"

# 外部IPを取得
EXTERNAL_IP=$(curl -s -m 5 "http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip" -H "Metadata-Flavor: Google" 2>/dev/null || echo "取得失敗")

echo ""
echo "  ダッシュボードURL: http://$EXTERNAL_IP"
echo ""
echo "  サービス状態確認:"
echo "    sudo systemctl status bitbank-bot"
echo "    sudo systemctl status bitbank-web"
echo ""
echo "  ログ確認:"
echo "    sudo journalctl -u bitbank-bot -f"
echo "    sudo journalctl -u bitbank-web -f"
echo ""
echo "  ★ GCPコンソールでファイアウォール確認:"
echo "    VPC ネットワーク → ファイアウォール"
echo "    → HTTP (ポート80) が許可されているか確認"
echo "========================================"

# ---------- Claude Code + 週次自動分析 ----------
echo ""
echo "[追加] Claude Code と週次自動分析を設定中..."

# Node.js インストール
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - 2>/dev/null
sudo apt-get install -y -qq nodejs
npm install -g @anthropic-ai/claude-code 2>/dev/null

# APIキーの設定（後で手動設定も可）
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo ""
    echo "  ★ Anthropic APIキーを設定してください："
    echo "    https://console.anthropic.com/ でAPIキーを発行後、"
    echo "    以下を実行: echo 'export ANTHROPIC_API_KEY=sk-ant-...' >> ~/.bashrc"
    echo "    週次自動分析はAPIキー設定後に有効になります"
fi

# cronに週次分析を登録（毎週日曜 深夜2時）
BOT_DIR_ABS="$(cd "$(dirname "$0")/.." && pwd)"
CRON_JOB="0 2 * * 0 $BOT_DIR_ABS/deploy/weekly_analysis.sh"
(crontab -l 2>/dev/null | grep -v "weekly_analysis"; echo "$CRON_JOB") | crontab -
echo "  週次自動分析をcronに登録しました（毎週日曜 深夜2時）"
