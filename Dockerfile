# ---- Python 3.11 (Zeabur最適) ----
FROM python:3.11-slim

WORKDIR /app

# ライブラリをインストール
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# ソースコードをコピー
COPY . .

# 環境変数（Zeaburが使うポート指定）
ENV PORT=8080
EXPOSE 8080

# 起動ファイルを bot.py に変更（←重要）
CMD ["python", "bot.py"]
