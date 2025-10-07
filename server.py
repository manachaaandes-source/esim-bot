from flask import Flask, request
import json, requests

app = Flask(__name__)

with open("config.json", "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

BOT_TOKEN = CONFIG["TELEGRAM_TOKEN"]
BOT_API = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

@app.route("/paypay/callback", methods=["POST"])
def callback():
    data = request.json
    print("💰 Webhook受信:", data)

    event = data.get("eventType")
    payment_id = data.get("data", {}).get("merchantPaymentId")

    if event == "PAYMENT_COMPLETED":
        msg = f"✅ 支払い完了を確認しました！\n注文ID: {payment_id}"
        # 任意の通知先（あなたのチャットID or Bot内のDBから紐付け）
        requests.post(BOT_API, data={"chat_id": 5397061486, "text": msg})

    return "OK", 200

if __name__ == "__main__":
    app.run(port=8000)
