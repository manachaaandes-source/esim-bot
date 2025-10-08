import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ForceReply
import json
import os

# === 基本設定 ===
with open("config.json", "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

DATA_FILE = "data.json"

# ✅ デフォルトリンク（これを先に置く）
DEFAULT_LINKS = {
    "通話可能": {"url": "https://qr.paypay.ne.jp/p2p01_uMrph5YFDveRCFmw", "price": 3000},
    "データ": {"url": "https://qr.paypay.ne.jp/p2p01_RSC8W9GG2ZcIso1I", "price": 1500},
}

# === データ保存・読み込み関数 ===
def load_data():
    """起動時に保存データを読み込む"""
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                print("💾 data.json を読み込みました。")
                return data.get("STOCK", {"通話可能": [], "データ": []}), data.get("LINKS", DEFAULT_LINKS)
        except Exception as e:
            print(f"⚠️ データ読み込み失敗: {e}")
    return {"通話可能": [], "データ": []}, DEFAULT_LINKS


def save_data():
    """現在の在庫・リンクを保存"""
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump({"STOCK": STOCK, "LINKS": LINKS}, f, ensure_ascii=False, indent=4)
        print("💾 data.json に保存しました。")
    except Exception as e:
        print(f"⚠️ データ保存失敗: {e}")

bot = Bot(token=CONFIG["TELEGRAM_TOKEN"])
dp = Dispatcher()

ADMIN_ID = 5397061486  # あなたのTelegram ID
STATE = {}
STOCK = {"通話可能": [], "データ": []}

DEFAULT_LINKS = {
    "通話可能": {"url": "https://qr.paypay.ne.jp/p2p01_uMrph5YFDveRCFmw", "price": 3000},
    "データ": {"url": "https://qr.paypay.ne.jp/p2p01_RSC8W9GG2ZcIso1I", "price": 1500},
}

# JSON から在庫とリンクを復元
STOCK, LINKS = load_data()

NOTICE = (
    "⚠️ ご注意\n"
    "eSIMご利用時は必ず【読み取り画面を録画】してください。\n"
    "使用できなかった場合でも、録画がないと保証対象外になります。"
)


def is_admin(uid):
    return uid == ADMIN_ID


# === /start ===
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    STATE[message.from_user.id] = {"stage": "select"}

    commands_text = (
        "🧭 コマンド一覧\n\n"
        "【ユーザー向け】\n"
        "/start - 購入メニューを開く\n"
        "/保証 - 保証申請を行う\n\n"
        "【管理者専用】\n"
        "/addstock 通話可能|データ - 在庫を追加\n"
        "/stock - 在庫確認\n"
        "/config - 設定変更（価格・リンク）\n"
        "/help - この一覧を表示\n"
    )
    await message.answer(commands_text)

    stock_info = f"📦 在庫状況\n通話可能: {len(STOCK['通話可能'])}枚\nデータ: {len(STOCK['データ'])}枚\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"📞 通話可能 ({len(STOCK['通話可能'])}枚)", callback_data="type_通話可能")],
        [InlineKeyboardButton(text=f"💾 データ ({len(STOCK['データ'])}枚)", callback_data="type_データ")]
    ])
    await message.answer("こんにちは！PayPay支払いBotです。\nどちらにしますか？\n\n" + stock_info, reply_markup=kb)


# === 商品タイプ選択 ===
@dp.callback_query(F.data.startswith("type_"))
async def select_type(callback: types.CallbackQuery):
    uid = callback.from_user.id
    choice = callback.data.split("_")[1]

    if len(STOCK[choice]) == 0:
        await callback.message.answer(f"⚠️ 現在「{choice}」の在庫がありません。")
        await callback.answer()
        return

    STATE[uid] = {"stage": "waiting_payment", "type": choice}
    product = LINKS[choice]

    await callback.message.answer(
        f"{choice}ですね。\nお支払い金額は {product['price']} 円です💰\n\n"
        f"こちらのPayPayリンクからお支払いください👇\n{product['url']}\n\n"
        "支払いが完了したら『完了』と送ってください。"
    )
    await callback.answer()


# === 支払い完了報告 ===
@dp.message(F.text.lower().contains("完了"))
async def handle_done(message: types.Message):
    uid = message.from_user.id
    state = STATE.get(uid)
    if not state or state["stage"] != "waiting_payment":
        await message.answer("⚠️ まず /start から始めてください。")
        return

    STATE[uid]["stage"] = "waiting_screenshot"
    await message.answer(
        "💴 支払いありがとうございます！\n\n"
        "⚠️ お手数ですが、**支払い完了画面のスクリーンショット**を送ってください。\n"
        "（金額や相手名が確認できるようにお願いします）"
    )


# === 支払いスクショ受信 ===
@dp.message(F.photo)
async def handle_payment_photo(message: types.Message):
    uid = message.from_user.id
    state = STATE.get(uid)

    # 管理者：在庫追加モード
    if state and state.get("stage") == "adding_stock":
        choice = state["type"]
        file_id = message.photo[-1].file_id
        STOCK[choice].append(file_id)
        save_data()
        await message.answer(f"✅ {choice} に在庫を追加しました。現在 {len(STOCK[choice])}枚")
        STATE.pop(uid, None)
        return

    # ユーザー：支払いスクショ提出中
    if not state or state.get("stage") != "waiting_screenshot":
        return

    choice = state["type"]
    STATE[uid]["stage"] = "pending_confirm"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ 確認完了", callback_data=f"confirm_{uid}"),
            InlineKeyboardButton(text="❌ 確認拒否", callback_data=f"deny_{uid}")
        ]
    ])

    await bot.send_photo(
        ADMIN_ID,
        message.photo[-1].file_id,
        caption=(
            f"📩 支払いスクリーンショット受信\n\n"
            f"👤 ユーザー: {message.from_user.full_name}\n"
            f"🆔 ユーザーID: `{uid}`\n"
            f"📦 タイプ: {choice}\n"
            f"💴 金額: {LINKS[choice]['price']}円\n\n"
            "支払い内容を確認して、以下のボタンで処理してください。"
        ),
        parse_mode="Markdown",
        reply_markup=kb
    )
    await message.answer("🕐 スクリーンショットを受け取りました。管理者の確認をお待ちください。")


# === 管理者：確認完了 ===
@dp.callback_query(F.data.startswith("confirm_"))
async def confirm_send(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return await callback.answer("権限がありません。", show_alert=True)

    target_id = int(callback.data.split("_")[1])
    state = STATE.get(target_id)
    if not state:
        return await callback.message.answer("⚠️ ユーザーデータが見つかりません。")

    choice = state["type"]
    if not STOCK[choice]:
        await bot.send_message(target_id, "⚠️ 現在この商品の在庫がありません。")
        return await callback.answer("❌ 在庫なし。", show_alert=True)

    file_id = STOCK[choice].pop(0)
    save_data()
    await bot.send_photo(target_id, file_id, caption=f"✅ {choice} を送信しました。ありがとうございました！")
    await bot.send_message(target_id, NOTICE)
    await callback.message.edit_caption(f"✅ {choice} 送信済み。残り在庫: {len(STOCK[choice])}枚")
    STATE.pop(target_id, None)
    await callback.answer("✅ 完了。")


# === 管理者：拒否（理由付き） ===
@dp.callback_query(F.data.startswith("deny_"))
async def deny_payment(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return await callback.answer("権限がありません。", show_alert=True)

    target_id = int(callback.data.split("_")[1])
    STATE[callback.from_user.id] = {"stage": "awaiting_reason", "target": target_id}

    await callback.message.answer(
        "💬 拒否理由を入力してください。\n例：金額不足 / 不明瞭なスクショ など。",
        reply_markup=ForceReply(selective=True)
    )
    await callback.answer("拒否理由を入力してください。")


# === 拒否理由返信 ===
@dp.message(F.reply_to_message)
async def handle_reason_reply(message: types.Message):
    admin_state = STATE.get(message.from_user.id)
    if not admin_state or admin_state.get("stage") != "awaiting_reason":
        return

    target_id = admin_state["target"]
    reason = message.text.strip()
    await bot.send_message(
        target_id,
        f"⚠️ 支払い内容が確認できませんでした。\n理由：{reason}\n\n再度『完了』と送信してください。"
    )
    await message.answer("❌ 拒否理由を送信しました。")
    STATE.pop(message.from_user.id, None)
    STATE.pop(target_id, None)


# === /config ===
@dp.message(Command("config"))
async def config_menu(message: types.Message):
    if not is_admin(message.from_user.id):
        return await message.answer("権限がありません。")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💴 価格を変更", callback_data="cfg_price")],
        [InlineKeyboardButton(text="🔗 支払いリンクを変更", callback_data="cfg_link")]
    ])
    await message.answer("⚙️ 設定メニュー\nどの設定を変更しますか？", reply_markup=kb)


# === 設定タイプ選択 ===
@dp.callback_query(F.data.startswith("cfg_"))
async def cfg_select(callback: types.CallbackQuery):
    mode = callback.data.split("_")[1]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💾 データ", callback_data=f"cfgsel_{mode}_データ")],
        [InlineKeyboardButton(text="📞 通話可能", callback_data=f"cfgsel_{mode}_通話可能")]
    ])
    await callback.message.answer(
        f"🛠 どちらのタイプの{'価格' if mode=='price' else 'リンク'}を変更しますか？",
        reply_markup=kb
    )
    await callback.answer()


# === 設定対象選択 ===
@dp.callback_query(F.data.startswith("cfgsel_"))
async def cfgsel_type(callback: types.CallbackQuery):
    _, mode, target = callback.data.split("_")
    uid = callback.from_user.id
    STATE[uid] = {"stage": f"config_{mode}", "target": target}
    await callback.message.answer(
        f"✏️ 新しい{'価格(数字)' if mode=='price' else '支払いリンク(URL)'}を入力してください。\n対象: {target}"
    )
    await callback.answer()


# === /addstock ===
@dp.message(Command("addstock"))
async def addstock(message: types.Message):
    if not is_admin(message.from_user.id):
        return await message.answer("権限がありません。")

    parts = message.text.split()
    if len(parts) < 2 or parts[1] not in STOCK:
        return await message.answer("使い方: /addstock 通話可能 または /addstock データ")

    STATE[message.from_user.id] = {"stage": "adding_stock", "type": parts[1]}
    await message.answer(f"🖼️ {parts[1]} の在庫画像を送ってください。")


# === /stock ===
@dp.message(Command("stock"))
async def stock(message: types.Message):
    if not is_admin(message.from_user.id):
        return await message.answer("権限がありません。")
    info = "\n".join([f"{k}: {len(v)}枚" for k, v in STOCK.items()])
    await message.answer(f"📦 現在の在庫\n{info}")


# === /保証 ===
@dp.message(Command("保証"))
async def warranty_start(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💾 データタイプ", callback_data="warranty_データ")],
        [InlineKeyboardButton(text="📞 通話可能タイプ", callback_data="warranty_通話可能")]
    ])
    await message.answer("どちらのタイプの保証ですか？", reply_markup=kb)


# === 保証タイプ選択 ===
@dp.callback_query(F.data.startswith("warranty_"))
async def warranty_select(callback: types.CallbackQuery):
    uid = callback.from_user.id
    choice = callback.data.split("_")[1]
    STATE[uid] = {"stage": "waiting_video", "type": choice}
    await callback.message.answer("保証対象の動画を送信してください。")
    await callback.answer()


# === 保証動画受信 ===
@dp.message(F.video)
async def handle_video(message: types.Message):
    uid = message.from_user.id
    state = STATE.get(uid)
    if not state or state["stage"] != "waiting_video":
        return

    choice = state["type"]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ 保証する", callback_data=f"approve_{uid}"),
         InlineKeyboardButton(text="❌ 却下", callback_data=f"deny_{uid}")]
    ])
    await bot.send_video(
        ADMIN_ID,
        message.video.file_id,
        caption=f"🎥 保証リクエスト\nユーザー: {message.from_user.full_name}\nID: {uid}\nタイプ: {choice}",
        reply_markup=kb
    )
    await message.answer("🎞️ 動画を受け取りました。管理者の確認をお待ちください。")
    STATE[uid]["stage"] = "warranty_pending"


# === /help ===
@dp.message(Command("help"))
async def help_cmd(message: types.Message):
    await message.answer(
        "🧭 コマンド一覧\n\n"
        "【ユーザー】\n"
        "/start - 購入を開始\n"
        "/保証 - 保証申請を行う\n"
        "/contact - 管理者に問い合わせ\n\n"
        "【管理者】\n"
        "/addstock 通話可能|データ - 在庫を追加\n"
        "/stock - 在庫確認\n"
        "/config - 価格やリンクを変更\n"
        "/reply <ID> <本文> - 問い合わせへの返信\n"
        "/help - この一覧を表示"
    )

# === /contact ===
@dp.message(Command("contact"))
async def contact_start(message: types.Message):
    uid = message.from_user.id
    STATE[uid] = {"stage": "contact"}
    await message.answer(
        "📞 お問い合わせモードを開始しました。\n"
        "ご質問・不具合・購入後の相談などを送ってください。\n"
        "（送信した内容は管理者に転送されます）\n\n"
        "終了するには /cancel と入力してください。"
    )


# === /cancel ===
@dp.message(Command("cancel"))
async def cancel_mode(message: types.Message):
    uid = message.from_user.id
    if uid in STATE:
        STATE.pop(uid)
        await message.answer("🟢 お問い合わせモードを終了しました。")
    else:
        await message.answer("⚠️ 現在アクティブなモードはありません。")


# === 管理者がボタンで返信選択 ===
@dp.callback_query(F.data.startswith("reply_"))
async def admin_reply_button(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("権限がありません。", show_alert=True)
        return

    target_id = int(callback.data.split("_")[1])
    STATE[callback.from_user.id] = {"stage": "replying", "target": target_id}

    await callback.message.answer(
        f"✏️ ユーザー {target_id} への返信内容を入力してください。\n"
        "このままメッセージを送信するとユーザーに転送されます。"
    )
    await callback.answer()


# === 管理者が /reply コマンドで返信 ===
@dp.message(Command("reply"))
async def admin_reply_cmd(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("権限がありません。")
        return

    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("使い方: /reply <ユーザーID> <本文>")
        return

    target_id = int(parts[1])
    text = parts[2]
    await bot.send_message(target_id, f"👨‍💼 管理者からの返信:\n{text}")
    await message.answer("✅ 返信を送信しました。")


# === 拒否理由返信（ForceReply） ===
@dp.message(F.reply_to_message)
async def handle_reason_reply(message: types.Message):
    admin_state = STATE.get(message.from_user.id)
    if not admin_state:
        return

    # 🔹 拒否理由モード
    if admin_state.get("stage") == "awaiting_reason":
        target_id = admin_state["target"]
        reason = message.text.strip()
        await bot.send_message(
            target_id,
            f"⚠️ 支払い内容が確認できませんでした。\n理由：{reason}\n\n再度『完了』と送信してください。"
        )
        await message.answer("❌ 拒否理由を送信しました。")
        STATE.pop(message.from_user.id, None)
        STATE.pop(target_id, None)
        return

    # 🔹 管理者返信モード（ForceReply経由）
    if (
        admin_state.get("stage") == "replying"
        and message.reply_to_message
        and getattr(message.reply_to_message.from_user, "is_bot", False)
    ):
        target_id = admin_state["target"]
        text = message.text.strip()
        await bot.send_message(target_id, f"👨‍💼 管理者からの返信:\n{text}")
        await message.answer("✅ ユーザーに返信を送信しました。")
        STATE.pop(message.from_user.id, None)
        return


# === 問い合わせ / config / 管理者返信 統合ハンドラ ===
@dp.message(F.text)
async def handle_text_message(message: types.Message):
    uid = message.from_user.id
    state = STATE.get(uid)

    # 🟢 管理者が返信中
    if state and state.get("stage") == "replying" and is_admin(uid):
        target_id = state["target"]
        text = message.text.strip()
        await bot.send_message(target_id, f"👨‍💼 管理者からの返信:\n{text}")
        await message.answer("✅ 返信を送信しました。")
        STATE.pop(uid, None)
        return

    # 🟢 ユーザーが問い合わせ中
    if state and state.get("stage") == "contact":
        text = message.text.strip()
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🗣️ この人に返信", callback_data=f"reply_{uid}")]
            ]
        )
        await bot.send_message(
            ADMIN_ID,
            f"📩 お問い合わせ受信\n\n"
            f"👤 {message.from_user.full_name}\n"
            f"🆔 {uid}\n"
            f"💬 内容:\n{text}",
            reply_markup=kb
        )
        await message.answer("📨 管理者に送信しました。返信をお待ちください。")
        return

    # 🟢 管理者が /config モード中
    if is_admin(uid) and state and state.get("stage", "").startswith("config_"):
        target = state["target"]
        mode = state["stage"].split("_")[1]
        new_value = message.text.strip()

        if mode == "price":
            if not new_value.isdigit():
                return await message.answer("⚠️ 数値のみを入力してください。")
            LINKS[target]["price"] = int(new_value)
            save_data()
            msg = f"💴 {target} の価格を {new_value} 円に更新しました。"
        else:
            if not (new_value.startswith("http://") or new_value.startswith("https://")):
                return await message.answer("⚠️ 有効なURLを入力してください。")
            LINKS[target]["url"] = new_value
            save_data()
            msg = f"🔗 {target} のリンクを更新しました。\n{new_value}"

        CONFIG["LINKS"] = LINKS
        with open("config.json", "w", encoding="utf-8") as f:
            json.dump(CONFIG, f, ensure_ascii=False, indent=4)

        STATE.pop(uid, None)
        await message.answer(f"✅ {msg}\n\n変更内容は即時反映されます。")
        return

    # その他メッセージは無視
    return

# === 起動 ===
async def main():
    print("🤖 eSIM自販機Bot 起動中...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
