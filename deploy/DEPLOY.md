# GCP + Cloudflare Tunnel デプロイ手順書

## 全体の流れ（所要時間：約25分）

```
Step 1: GCPでインスタンスを作成（5分）
Step 2: Cloudflareアカウントを作成しTunnelトークンを取得（10分）
Step 3: ファイルをアップロード（3分）
Step 4: セットアップスクリプトを実行（7分）
```

---

## Step 1: GCPでインスタンスを作成

1. [Google Cloud Console](https://console.cloud.google.com/) を開く
2. 左メニュー → **Compute Engine** → **VM インスタンス**
3. **「インスタンスを作成」** をクリック

### 設定値（無料枠に必ず合わせること）

| 項目 | 設定値 |
|---|---|
| 名前 | `bitbank-bot` |
| リージョン | `us-west1`（オレゴン）★必須 |
| ゾーン | `us-west1-a` |
| マシンタイプ | `e2-micro` ★必須 |
| ブートディスクOS | Ubuntu 22.04 LTS |
| ブートディスク種類 | **標準永続ディスク** ★必須 |
| ブートディスクサイズ | 30 GB |
| バックアップ | **なし** ★必須 |

4. **「作成」** をクリック（1〜2分で起動）

---

## Step 2: Cloudflareアカウントを作成しTunnelを設定

### 2-1. アカウント作成

1. https://www.cloudflare.com/ にアクセス
2. 右上の **「Sign Up」** → メールとパスワードで登録（無料）
3. 届いたメールの確認リンクをクリック

### 2-2. Zero TrustでTunnelを作成

1. ダッシュボードにログイン → 左メニュー **「Zero Trust」**
2. **Networks** → **Tunnels** → **「Create a tunnel」**
3. タイプ **「Cloudflared」** を選択 → 「Next」
4. Tunnel名（例: `bitbank-bot`）を入力 → 「Save tunnel」

### 2-3. トークンをコピー

OS選択で **Linux → Debian → 64-bit** を選ぶと以下が表示されます：

```
sudo cloudflared service install eyJhIjoiXX...（長いトークン）
```

**`eyJhIjoiXX...` のトークン部分だけ**をメモ帳にコピー。

### 2-4. Public Hostnameを設定

「Next」をクリックして設定：

| 項目 | 設定値 |
|---|---|
| Service Type | `HTTP` |
| URL | `localhost:8080` |

「Save tunnel」でURLが発行されます（例: `https://bitbank-xxxx.cfargotunnel.com`）

---

## Step 3: ファイルをアップロード

GCPコンソール → VMインスタンス → **「SSH」** ボタン → ブラウザターミナルが開く

```bash
# アップロードは右上の歯車アイコン →「ファイルをアップロード」
# bitbank-bot.zip をアップロード後：
sudo apt-get install -y unzip
unzip bitbank-bot.zip
```

---

## Step 4: セットアップスクリプトを順番に実行

```bash
cd bitbank-bot

# 基本セットアップ（SWAP・Python・systemd・nginx）
bash deploy/setup_gcp.sh

# Cloudflare Tunnel設定
bash deploy/setup_cloudflare.sh
# → トークンを聞かれるのでStep 2-3でコピーしたものを貼り付け
```

---

## Step 5: 完了

Cloudflareコンソールで確認したURLにアクセス：

```
https://bitbank-xxxx.cfargotunnel.com
```

鍵マークが表示されればHTTPS化成功です。

---

## よく使うコマンド

```bash
# 状態確認
sudo systemctl status bitbank-bot bitbank-web cloudflared

# ログ確認
sudo journalctl -u bitbank-bot -f
sudo journalctl -u cloudflared -f

# 再起動
sudo systemctl restart bitbank-bot

# メモリ・ディスク確認
free -h && df -h
```

---

## トラブルシューティング

### ページが開かない

```bash
sudo systemctl status cloudflared
curl http://localhost:5000   # ダッシュボードがローカルで動いているか確認
```

### トークンを間違えた

```bash
sudo systemctl stop cloudflared
sudo cloudflared service uninstall
bash deploy/setup_cloudflare.sh  # 再実行
```
