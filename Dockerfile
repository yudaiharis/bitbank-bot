FROM python:3.12-slim

WORKDIR /app

# 依存パッケージを先にインストール（キャッシュ効率化）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ソースをコピー
COPY . .

# reports・backtest/data ディレクトリを作成（ボリューム未マウント時のフォールバック）
RUN mkdir -p reports backtest/data

# デフォルトはwebダッシュボード起動
CMD ["python", "monitor/web_dashboard.py"]
