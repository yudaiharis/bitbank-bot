# GCP Docker デプロイ手順

## 全体の流れ（所要時間：約20分）

```
Step 1: GCPでVMを作成（5分）
Step 2: SSHでVMに接続しセットアップ（10分）
Step 3: Cloudflare TunnelでHTTPS公開（5分）※任意
```

---

## Step 1: GCPでVMを作成

1. [Google Cloud Console](https://console.cloud.google.com/) → **Compute Engine** → **VMインスタンス**
2. **「インスタンスを作成」**

### 推奨設定（無料枠）

| 項目 | 設定値 |
|---|---|
| 名前 | `bitbank-bot` |
| リージョン | `us-west1`（オレゴン）|
| マシンタイプ | `e2-micro` |
| OS | Ubuntu 22.04 LTS **Minimal** |
| ディスク | 標準永続ディスク 30GB |
| バックアップ | なし |

3. **「作成」** → 起動まで1〜2分待つ

---

## Step 2: VMセットアップ

GCPコンソールの **「SSH」ボタン** → ブラウザターミナルが開く

```bash
# セットアップスクリプトをダウンロードして実行
curl -fsSL https://raw.githubusercontent.com/yudaiharis/bitbank-bot/main/deploy/setup_gcp_docker.sh | bash
```

初回実行後、`.env` の設定が必要と表示されます：

```bash
nano /opt/bitbank-bot/.env
```

以下を入力：

```
GITHUB_TOKEN=ghp_xxxx   # GitHubのread-only PAT（後述）
GITHUB_REPO=yudaiharis/bitbank-bot
SLACK_WEBHOOK_URL=       # 任意
```

設定後、再実行：

```bash
bash /opt/bitbank-bot/deploy/setup_gcp_docker.sh
```

---

## GitHub PAT の作成（read-only）

1. https://github.com/settings/tokens/new を開く
2. 設定：
   - Note: `bitbank-bot-gcp`
   - Expiration: `No expiration`
   - Scope: **`repo`** にチェック
3. **「Generate token」** → `ghp_...` をコピー
4. `.env` の `GITHUB_TOKEN=` に貼り付け

---

## Step 3: Cloudflare Tunnel（HTTPS公開）

### 3-1. Cloudflare コンソールでトンネルを作成

1. https://one.dash.cloudflare.com/ → **Zero Trust** → **Networks** → **Tunnels**
2. **「Create a tunnel」** → Connector: **Docker** を選択
3. トークン（`eyJ...` で始まる文字列）をコピーしておく
4. **Public Hostname** を設定：
   - Subdomain: `bitbank`（任意）
   - Domain: 自分のドメイン
   - Service: `http://web:5000` ← **ここが重要（Docker内部ネットワーク経由）**

### 3-2. VM 上でセットアップスクリプトを実行

```bash
bash /opt/bitbank-bot/deploy/setup_cloudflare.sh
```

→ トークンを貼り付けると `cloudflared` コンテナが起動し HTTPS URL が発行されます。
→ GCP のファイアウォール開放は不要です（Cloudflare が終端処理）。

---

## GCPファイアウォール設定

ブラウザから `http://VM_IP:8080` でアクセスする場合：

1. GCPコンソール → **VPCネットワーク** → **ファイアウォール**
2. **「ファイアウォールルールを作成」**
   - 名前: `allow-bitbank-dashboard`
   - ターゲット: `すべてのインスタンス`
   - ソースIPの範囲: `0.0.0.0/0`（または自分のIPのみ）
   - プロトコルとポート: `TCP 8080`

※ Cloudflare Tunnel を使う場合はこの設定不要

---

## よく使うコマンド

```bash
cd /opt/bitbank-bot

# 状態確認
docker compose ps

# ログ確認
docker compose logs -f paper    # ペーパートレード
docker compose logs -f web      # ダッシュボード

# 最新コードに更新
git pull origin main
docker compose build --quiet
docker compose up -d

# バックテスト実行（手動）
docker compose run --rm backtest

# GitHub Actionsが自動更新した後の反映
git pull origin main && docker compose up -d
```

---

## GitHub Actions との連携

毎週日曜 JST 02:00 に GitHub Actions が自動でバックテストを実行し、
閾値合格時は `config.yaml` を git commit します。

GCPコンテナに反映するには：

```bash
# GCP VM 上で実行（手動）
cd /opt/bitbank-bot && git pull origin main && docker compose up -d
```

または GitHub Actions の `deploy-gcp` ジョブに SSH デプロイを設定することで自動化できます。
（`GCP_HOST`、`GCP_USER`、`GCP_SSH_KEY`、`GCP_BOT_DIR` を GitHub Secrets に設定）
