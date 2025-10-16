import os
import json
import requests
from aiohttp import web

# =========================
# 設定・環境変数の読み込み
# =========================
CONFIG_PATH = "config.json"

if not os.path.exists(CONFIG_PATH):
    raise FileNotFoundError("config.json が見つかりません。Zeaburに含めてください。")

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

BOT_TOKEN = os.getenv("TELEGRAM_TOKEN", CONFIG.get("TELEGRAM_TOKEN"))
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", CONFIG.get("STRIPE_SECRET_KEY", ""))
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", CONFIG.get("STRIPE_WEBHOOK_SECRET", ""))
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", CONFIG.get("PUBLIC_BASE_URL", "https://esim.zeabur.app"))

ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "5397061486"))  # あなたのTelegram ID

BOT_API = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"


# =========================
# Stripe Webhook
# =========================
async def stripe_webhook(request):
    try:
        payload = await request.read()
        sig = request.headers.get("Stripe-Signature", "")

        # Stripe SDK使用（無ければ単純JSONとして処理）
        import stripe
        stripe.api_key = STRIPE_SECRET_KEY

        try:
            event = stripe.Webhook.construct_event(
                payload=payload, sig_header=sig, secret=STRIPE_WEBHOOK_SECRET
            )
        except Exception as e:
            print(f"⚠️ Webhook署名検証失敗: {e}")
            return web.Response(status=400, text="Invalid signature")

        event_type = event.get("type")
        if event_type == "checkout.session.completed":
            session = event["data"]["object"]
            metadata = session.get("metadata", {})
            uid = metadata.get("tg_uid", "不明")
            choice = metadata.get("choice", "不明")
            count = metadata.get("count", "1")
            amount = metadata.get("amount", "0")

            msg = (
                f"💳 Stripe 決済完了通知\n"
                f"🆔 Telegram ID: {uid}\n"
                f"📦 タイプ: {choice}\n"
                f"🧾 枚数: {count}\n"
                f"💴 支払金額: {amount}円"
            )
            requests.post(BOT_API, data={"chat_id": ADMIN_CHAT_ID, "text": msg})

        return web.Response(text="ok")

    except Exception as e:
        print(f"❌ Stripe Webhookエラー: {e}")
        return web.Response(status=400, text="error")


# =========================
# Stripe 成功／キャンセル
# =========================
async def stripe_success(request):
    return web.Response(text="✅ 決済が完了しました。TelegramにeSIMが届きます。")

async def stripe_cancel(request):
    return web.Response(text="❌ 決済がキャンセルされました。再度お試しください。")


# =========================
# PayPay Webhook
# =========================
async def paypay_callback(request):
    try:
        data = await request.json()
        print("💰 PayPay Webhook受信:", data)

        event = data.get("eventType")
        payment_id = data.get("data", {}).get("merchantPaymentId")

        if event == "PAYMENT_COMPLETED":
            msg = f"✅ PayPay支払い完了を確認しました！\n注文ID: {payment_id}"
            requests.post(BOT_API, data={"chat_id": ADMIN_CHAT_ID, "text": msg})

        return web.Response(text="OK")

    except Exception as e:
        print(f"❌ PayPayコールバックエラー: {e}")
        return web.Response(status=400, text="error")


# =========================
# Webサーバ起動
# =========================
async def start_web_app():
    app = web.Application()
    app.router.add_post("/stripe/webhook", stripe_webhook)
    app.router.add_get("/stripe/success", stripe_success)
    app.router.add_get("/stripe/cancel", stripe_cancel)
    app.router.add_post("/paypay/callback", paypay_callback)

    port = int(os.getenv("PORT", "8080"))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    print(f"🌐 Web server started at http://0.0.0.0:{port}")
    print(f"🔗 Stripe Webhook: {PUBLIC_BASE_URL}/stripe/webhook")
    print(f"🔗 PayPay Callback: {PUBLIC_BASE_URL}/paypay/callback")

    # サーバを常駐
    while True:
        await web.AppRunner(app).cleanup()


if __name__ == "__main__":
    import asyncio
    asyncio.run(start_web_app())
