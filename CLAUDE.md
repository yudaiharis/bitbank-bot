# bitbank-bot: 自律PDCAトレードシステム

## 目標
ペーパートレードで仮想資産1,000,000円を右肩上がりにする。
- 勝率55%以上
- 最大ドローダウン10%以内
- 上記を3ループ連続達成、または最大5ループで終了

## スタック
Python 3.11, requests, pandas, pandas-ta, rich, pyyaml, sqlite3, matplotlib

## プロジェクト構造
main.py           # エントリーポイント
config.yaml       # パラメータ（自律改善で自動更新）
CLAUDE.md         # この指示書（変更しない）
data/fetcher.py   # bitbank Public API クライアント
data/store.py     # SQLite管理
scanner/volatility.py  # 全銘柄ボラティリティスキャン
strategy/features.py   # テクニカル指標計算
strategy/signals.py    # 売買シグナル生成
execution/paper.py     # ペーパートレード執行
execution/risk.py      # リスク管理
monitor/dashboard.py   # richターミナル表示
reports/               # 各ループのレポートが自動生成される

## 自律PDCAループの実行手順（人間の介入なし）

### STEP 1: 初回のみ環境確認
pip install -r requirements.txt
python main.py --mode check  # API接続確認

### STEP 2: ペーパートレード実行（D）
python main.py --mode paper --trades 50
50件蓄積で自動停止 → STEP 3へ

### STEP 3: 自己分析（C）
python main.py --mode analyze --loop N
reports/report_N.md を生成

### STEP 4: 自律改善（A）
report_N.mdの診断に基づきconfig.yamlを自動更新
改善ルール:
- 勝率 < 50% → rsi_oversold +5 / rsi_overbought -5
- ドローダウン > 10% → stop_loss_pct -0.005 / position_size_pct -0.01
- 特定ペアの損失率 > 60% → そのペアをexcluded_pairsに追加
- シャープレシオ < 0.5 → scan_interval_sec を半分に短縮

### STEP 5: ループ判定
目標達成 → reports/final_report.md生成して終了
未達成かつループ < 5 → STEP 2へ戻る

## API制約（Proプラン対応）
- bitbank APIアクセス: 最大1回/分
- スキャン対象: config.yamlのpairsリスト（最大10銘柄）
- 1ループ内のファイル生成は最小限に

## エラー処理の原則
- エラーが出たら自分で診断・修正して続行
- 人間に聞かない
- 修正内容はreports/report_N.mdのerror_logセクションに記録
