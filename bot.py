import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ForceReply
import json

# === 基本設定 ===
with open("config.json", "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

bot = Bot(token=CONFIG["TELEGRAM_TOKEN"])
dp = Dispatcher()

ADMIN_ID = 5397061486  # あなたのTelegram ID
STATE = {}
STOCK = {"通話可能": [], "データ": []}

LINKS = {
    "通話可能": {"url": "https://qr.paypay.ne.jp/p2p01_uMrph5YFDveRCFmw", "price": 3000},
    "データ": {"url": "https://qr.paypay.ne.jp/p2p01_RSC8W9GG2ZcIso1I", "price": 1500},
}

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
        await callback.message.answer(f"⚠️ 現在「{choice}」の在庫がありません。追加されるまでお待ちください。")
        await callback.answer()
        return

    STATE[uid] = {"stage": "waiting_payment", "type": choice}
    product = LINKS[choice]

    await callback.message.answer(
        f"{choice}ですね。\nお支払い金額は {product['price']} 円です💰\n\n"
        f"こちらのPayPayリンクからお支払いください👇\n{product['url']}\n\n"
        f"支払いが完了したら『完了』と送ってください。"
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
    choice = state["type"]
    price = LINKS[choice]["price"]

    await message.answer(
        f"💴 支払いありがとうございます！\n\n"
        f"⚠️ お手数ですが、**支払い完了画面のスクリーンショット**を送ってください。\n"
        f"（金額や相手名が確認できるようにお願いします）"
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
        await message.answer(f"✅ {choice} に在庫を追加しました。現在 {len(STOCK[choice])}枚")
        STATE.pop(uid, None)
        return

    # ユーザー：支払いスクショ提出中
    if not state or state.get("stage") != "waiting_screenshot":
        return

    choice = state["type"]
    price = LINKS[choice]["price"]
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
        caption=(f"📩 支払いスクリーンショット受信\n\n"
                 f"👤 ユーザー: {message.from_user.full_name}\n"
                 f"🆔 ユーザーID: `{uid}`\n"
                 f"📦 タイプ: {choice}\n"
                 f"💴 金額: {price}円\n\n"
                 f"支払い内容を確認して、以下のボタンで処理してください。"),
        parse_mode="Markdown",
        reply_markup=kb
    )
    await message.answer("🕐 スクリーンショットを受け取りました。管理者の確認をお待ちください。")


# === 管理者：支払い確認完了 ===
@dp.callback_query(F.data.startswith("confirm_"))
async def confirm_send(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("権限がありません。", show_alert=True)
        return

    target_id = int(callback.data.split("_")[1])
    state = STATE.get(target_id)
    if not state:
        await callback.message.answer("⚠️ ユーザーデータが見つかりません。")
        return

    choice = state["type"]

    if not STOCK[choice]:
        await bot.send_message(target_id, "⚠️ 現在この商品の在庫がありません。後ほど再送します。")
        await callback.answer("❌ 在庫がありません。", show_alert=True)
        return

    file_id = STOCK[choice].pop(0)
    await bot.send_photo(target_id, file_id, caption=f"✅ {choice}の商品をお送りします。ありがとうございました！")
    await bot.send_message(target_id, NOTICE)
    await callback.message.edit_caption(f"✅ {choice} の商品を送信しました。残り在庫: {len(STOCK[choice])}枚")
    STATE.pop(target_id, None)
    await callback.answer("✅ 商品を送信しました。")


# === 管理者：支払い確認拒否（理由入力対応） ===
@dp.callback_query(F.data.startswith("deny_"))
async def deny_payment(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("権限がありません。", show_alert=True)
        return

    target_id = int(callback.data.split("_")[1])
    state = STATE.get(target_id)
    if not state:
        await callback.message.answer("⚠️ ユーザー情報が見つかりません。")
        return

    # 理由入力待ち状態を記録
    STATE[callback.from_user.id] = {"stage": "awaiting_reason", "target": target_id}
    await callback.message.answer(
        "💬 拒否理由を入力してください。\n例：金額不足、スクショ不明瞭、別アカウント名など。",
        reply_markup=ForceReply(selective=True)
    )
    await callback.answer("拒否理由の入力を待っています。")


# === 管理者が拒否理由を送信したとき ===
@dp.message(F.reply_to_message)
async def handle_reason_reply(message: types.Message):
    admin_state = STATE.get(message.from_user.id)
    if not admin_state or admin_state.get("stage") != "awaiting_reason":
        return

    target_id = admin_state["target"]
    reason = message.text.strip()

    # ユーザーに理由を送信
    await bot.send_message(
        target_id,
        f"⚠️ お支払い内容が確認できませんでした。\n理由：{reason}\n\n"
        "再度ご確認のうえ、『完了』と送信してください。"
    )

    await message.answer("❌ 拒否理由をユーザーに送信しました。")
    STATE.pop(message.from_user.id, None)
    STATE.pop(target_id, None)

# === 管理者: 設定メニュー (/config) ===
@dp.message(Command("config"))
async def config_menu(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("権限がありません。")
        return

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


# === 各タイプ選択後の入力待機 ===
@dp.callback_query(F.data.startswith("cfgsel_"))
async def cfgsel_type(callback: types.CallbackQuery):
    _, mode, target = callback.data.split("_")
    uid = callback.from_user.id
    STATE[uid] = {"stage": f"config_{mode}", "target": target}
    await callback.message.answer(
        f"✏️ 新しい{'価格(数値のみ)' if mode=='price' else '支払いリンク(URL)'}を入力してください。\n\n"
        f"対象: {target}"
    )
    await callback.answer()


# === 管理者の入力処理 ===
@dp.message(F.text)
async def handle_config_input(message: types.Message):
    uid = message.from_user.id
    state = STATE.get(uid)

    # ✅ 管理者かつ設定変更モード以外はスルー
    if not is_admin(uid) or not state or not state.get("stage", "").startswith("config_"):
        return

    target = state["target"]
    mode = state["stage"].split("_")[1]
    new_value = message.text.strip()

    # 価格変更
    if mode == "price":
        if not new_value.isdigit():
            await message.answer("⚠️ 数値のみを入力してください。")
            return
        LINKS[target]["price"] = int(new_value)
        msg = f"💴 {target} の価格を {new_value} 円に更新しました。"

    # リンク変更
    elif mode == "link":
        if not (new_value.startswith("http://") or new_value.startswith("https://")):
            await message.answer("⚠️ 有効なURLを入力してください。")
            return
        LINKS[target]["url"] = new_value
        msg = f"🔗 {target} のリンクを更新しました。\n{new_value}"

    # config.json に保存
    CONFIG["LINKS"] = LINKS
    with open("config.json", "w", encoding="utf-8") as f:
        json.dump(CONFIG, f, ensure_ascii=False, indent=4)

    STATE.pop(uid, None)
    await message.answer(f"✅ {msg}\n\n変更内容は即時反映されます。")

# === 管理者：在庫追加 ===
@dp.message(Command("addstock"))
async def addstock(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("権限がありません。")
        return

    parts = message.text.split()
    if len(parts) < 2 or parts[1] not in STOCK:
        await message.answer("使い方: /addstock 通話可能 または /addstock データ")
        return

    STATE[message.from_user.id] = {"stage": "adding_stock", "type": parts[1]}
    await message.answer(f"🖼️ {parts[1]} の在庫画像を送ってください。")


# === /stock ===
@dp.message(Command("stock"))
async def stock(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("権限がありません。")
        return
    info = "\n".join([f"{k}: {len(v)}枚" for k, v in STOCK.items()])
    await message.answer(f"📦 現在の在庫\n{info}")


# === /保証 ===
@dp.message(Command("保証"))
async def warranty_start(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💾 データタイプ", callback_data=f"warranty_データ")],
        [InlineKeyboardButton(text="📞 通話可能タイプ", callback_data=f"warranty_通話可能")]
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
    if not state or state.get("stage") != "waiting_video":
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
    text = (
        "🧭 コマンド一覧\n\n"
        "【ユーザー】\n"
        "/start - 購入を開始\n"
        "/保証 - 保証申請を行う\n\n"
        "【管理者専用】\n"
        "/addstock 通話可能|データ - 在庫を登録\n"
        "/stock - 在庫確認\n"
        "/help - この一覧を表示"
    )
    await message.answer(text)


# === 起動 ===
async def main():
    print("🤖 eSIM自販機Bot 起動中...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
