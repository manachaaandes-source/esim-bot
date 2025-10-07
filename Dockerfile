# ---- Python 3.11 (Railway最適) ----
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Flask or aiogram どちらにも対応
CMD ["python", "main.py"]
