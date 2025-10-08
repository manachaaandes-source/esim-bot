import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ForceReply
import json
import os
import random
import string

# === 基本設定 ===
with open("config.json", "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

bot = Bot(token=CONFIG["TELEGRAM_TOKEN"])
dp = Dispatcher()

ADMIN_ID = 5397061486  # あなたのTelegram ID
STATE = {}

DATA_FILE = "data.json"
DEFAULT_LINKS = {
    "通話可能": {"url": "https://qr.paypay.ne.jp/p2p01_uMrph5YFDveRCFmw", "price": 3000},
    "データ": {"url": "https://qr.paypay.ne.jp/p2p01_RSC8W9GG2ZcIso1I", "price": 1500},
}


def ensure_data_file():
    """data.jsonがない場合自動生成"""
    if not os.path.exists(DATA_FILE):
        data = {"STOCK": {"通話可能": [], "データ": []}, "LINKS": DEFAULT_LINKS, "CODES": {}}
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print("🆕 data.json を新規作成しました。")
        return data
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_data():
    """安全に読み込み"""
    try:
        data = ensure_data_file()
        stock = data.get("STOCK", {"通話可能": [], "データ": []})
        links = data.get("LINKS", DEFAULT_LINKS)
        codes = data.get("CODES", {})
        return stock, links, codes
    except Exception as e:
        print(f"⚠️ data.json読み込み失敗: {e}")
        return {"通話可能": [], "データ": []}, DEFAULT_LINKS, {}


def save_data():
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump({"STOCK": STOCK, "LINKS": LINKS, "CODES": CODES}, f, ensure_ascii=False, indent=4)
        print("💾 data.json 保存完了")
    except Exception as e:
        print(f"⚠️ data保存失敗: {e}")


STOCK, LINKS, CODES = load_data()

NOTICE = (
    "⚠️ ご注意\n"
    "eSIMご利用時は必ず【読み取り画面を録画】してください。\n"
    "使用できなかった場合でも、録画がないと保証対象外になります。"
)

def is_admin(uid): return uid == ADMIN_ID


# === /start ===
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    STATE[message.from_user.id] = {"stage": "select"}
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
    STATE[uid] = {"stage": "ask_code", "type": choice}

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎟️ 割引コードあり", callback_data="has_code")],
        [InlineKeyboardButton(text="🙅‍♂️ なし", callback_data="no_code")]
    ])
    await callback.message.answer(f"{choice}ですね。割引コードはお持ちですか？", reply_markup=kb)
    await callback.answer()


# === 割引コード入力 ===
@dp.callback_query(F.data == "has_code")
async def ask_code(callback: types.CallbackQuery):
    uid = callback.from_user.id
    STATE[uid]["stage"] = "enter_code"
    await callback.message.answer("🎟️ 割引コードを入力してください（例: RKTN-ABC123）")
    await callback.answer()


# === 割引なし支払い ===
@dp.callback_query(F.data == "no_code")
async def no_code(callback: types.CallbackQuery):
    uid = callback.from_user.id
    STATE[uid]["discount"] = False
    await proceed_to_payment(callback.message, discount=False)
    await callback.answer()


async def proceed_to_payment(message, discount=False):
    uid = message.from_user.id
    state = STATE.get(uid)
    choice = state["type"]

    # LINKSが壊れている場合修復
    global LINKS
    if not LINKS or not isinstance(LINKS, dict) or not LINKS.get(choice):
        LINKS = DEFAULT_LINKS.copy()
        save_data()
        print(f"⚙️ LINKS修復: {choice}を再生成")

    product = LINKS.get(choice, DEFAULT_LINKS[choice])
    if discount:
        price = product.get("discount_price", product["price"])
        link = product.get("discount_url", product["url"])
        text = (
            f"{choice}ですね。\n💸 割引適用！ {price}円 💰\n\n"
            f"こちらのPayPayリンクからお支払いください👇\n{link}\n\n支払い完了後に『完了』と送ってください。"
        )
    else:
        price = product["price"]
        link = product["url"]
        text = (
            f"{choice}ですね。\nお支払い金額は {price} 円です💰\n\n"
            f"こちらのPayPayリンクからお支払いください👇\n{link}\n\n支払い完了後に『完了』と送ってください。"
        )

    STATE[uid] = {"stage": "waiting_payment", "type": choice}
    await message.answer(text)


# === 割引コード認証 ===
@dp.message(F.text.regexp(r"RKTN-[A-Z0-9]{6}"))
async def check_code(message: types.Message):
    uid = message.from_user.id
    state = STATE.get(uid)
    if not state or state.get("stage") != "enter_code": return
    code = message.text.strip().upper()

    if code not in CODES:
        return await message.answer("⚠️ 無効なコードです。")
    if CODES[code]["used"]:
        return await message.answer("⚠️ このコードは使用済みです。")
    if CODES[code]["type"] != state["type"]:
        return await message.answer("⚠️ このコードは別タイプ用です。")

    CODES[code]["used"] = True
    save_data()
    await message.answer("🎉 コード承認！割引適用します。")
    await proceed_to_payment(message, discount=True)


# === 支払い完了報告 ===
@dp.message(F.text.lower().contains("完了"))
async def handle_done(message: types.Message):
    uid = message.from_user.id
    state = STATE.get(uid)
    if not state or state["stage"] != "waiting_payment":
        return await message.answer("⚠️ まず /start から始めてください。")
    STATE[uid]["stage"] = "waiting_screenshot"
    await message.answer("💴 支払い完了ありがとうございます。\nスクリーンショットを送ってください。")


# === 支払いスクショ ===
@dp.message(F.photo)
async def handle_payment_photo(message: types.Message):
    uid = message.from_user.id
    state = STATE.get(uid)

    # 在庫追加中
    if state and state.get("stage") == "adding_stock":
        choice = state["type"]
        STOCK[choice].append(message.photo[-1].file_id)
        save_data()
        await message.answer(f"✅ {choice} に在庫追加（{len(STOCK[choice])}枚）")
        STATE.pop(uid, None)
        return

    if not state or state.get("stage") != "waiting_screenshot":
        return

    choice = state["type"]
    price = LINKS[choice]["price"]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ 承認", callback_data=f"confirm_{uid}"),
         InlineKeyboardButton(text="❌ 拒否", callback_data=f"deny_{uid}")]
    ])

    await bot.send_photo(
        ADMIN_ID, message.photo[-1].file_id,
        caption=f"📩 支払い確認\n👤 {message.from_user.full_name}\n🆔 {uid}\n📦 {choice}\n💴 {price}円",
        reply_markup=kb
    )
    await message.answer("🕐 管理者確認中です。")


# === 承認 ===
@dp.callback_query(F.data.startswith("confirm_"))
async def confirm_send(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return await callback.answer("権限なし", show_alert=True)
    target_id = int(callback.data.split("_")[1])
    state = STATE.get(target_id)
    if not state:
        return await callback.message.answer("⚠️ ユーザーデータなし")

    choice = state["type"]
    if not STOCK[choice]:
        await bot.send_message(target_id, "⚠️ 在庫なし。後ほど送信します。")
        return await callback.answer("在庫なし")

    file_id = STOCK[choice].pop(0)
    save_data()
    await bot.send_photo(target_id, file_id, caption=f"✅ {choice} を送信しました！")
    await bot.send_message(target_id, NOTICE)
    STATE.pop(target_id, None)
    await callback.answer("完了")


# === 拒否 ===
@dp.callback_query(F.data.startswith("deny_"))
async def deny_payment(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return await callback.answer("権限なし", show_alert=True)
    target_id = int(callback.data.split("_")[1])
    STATE[callback.from_user.id] = {"stage": "awaiting_reason", "target": target_id}
    await callback.message.answer("💬 拒否理由を入力してください。", reply_markup=ForceReply(selective=True))
    await callback.answer("入力待機")


@dp.message(F.reply_to_message)
async def handle_reason_reply(message: types.Message):
    admin_state = STATE.get(message.from_user.id)
    if not admin_state or admin_state.get("stage") != "awaiting_reason": return
    target_id = admin_state["target"]
    reason = message.text.strip()
    await bot.send_message(target_id, f"⚠️ 支払い確認できませんでした。\n理由：{reason}\n\n再度『完了』と送信してください。")
    await message.answer("❌ 拒否理由送信完了")
    STATE.pop(message.from_user.id, None)
    STATE.pop(target_id, None)


# === 管理者: 在庫追加 ===
@dp.message(Command("addstock"))
async def addstock(message: types.Message):
    if not is_admin(message.from_user.id): return await message.answer("権限なし")
    parts = message.text.split()
    if len(parts) < 2 or parts[1] not in STOCK:
        return await message.answer("使い方: /addstock 通話可能 or /addstock データ")
    STATE[message.from_user.id] = {"stage": "adding_stock", "type": parts[1]}
    await message.answer(f"{parts[1]} の在庫画像を送信してください。")


# === /stock ===
@dp.message(Command("stock"))
async def stock_cmd(message: types.Message):
    if not is_admin(message.from_user.id): return await message.answer("権限なし")
    info = "\n".join([f"{k}: {len(v)}枚" for k, v in STOCK.items()])
    await message.answer(f"📦 在庫状況\n{info}")


# === /code ===
@dp.message(Command("code"))
async def create_code(message: types.Message):
    if not is_admin(message.from_user.id): return await message.answer("権限なし")
    parts = message.text.split()
    if len(parts) < 2 or parts[1] not in STOCK:
        return await message.answer("使い方: /code 通話可能 または /code データ")
    ctype = parts[1]
    code = "RKTN-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    CODES[code] = {"used": False, "type": ctype}
    save_data()
    await message.answer(f"🎟️ コード発行完了\n`{code}` ({ctype})", parse_mode="Markdown")


# === /codes ===
@dp.message(Command("codes"))
async def list_codes(message: types.Message):
    if not is_admin(message.from_user.id): return await message.answer("権限なし")
    if not CODES: return await message.answer("コードなし")
    text = "🎟️ コード一覧\n" + "\n".join([f"{k} | {v['type']} | {'✅使用済' if v['used'] else '🟢未使用'}" for k, v in CODES.items()])
    await message.answer(text)


# === /保証 ===
@dp.message(Command("保証"))
async def warranty_start(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💾 データ", callback_data="warranty_データ")],
        [InlineKeyboardButton(text="📞 通話可能", callback_data="warranty_通話可能")]
    ])
    await message.answer("どちらのタイプの保証ですか？", reply_markup=kb)


@dp.callback_query(F.data.startswith("warranty_"))
async def warranty_select(callback: types.CallbackQuery):
    uid = callback.from_user.id
    choice = callback.data.split("_")[1]
    STATE[uid] = {"stage": "waiting_video", "type": choice}
    await callback.message.answer("保証対象の動画を送信してください。")
    await callback.answer()


@dp.message(F.video)
async def handle_video(message: types.Message):
    uid = message.from_user.id
    state = STATE.get(uid)
    if not state or state["stage"] != "waiting_video": return
    choice = state["type"]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ 保証する", callback_data=f"approve_{uid}"),
         InlineKeyboardButton(text="❌ 却下", callback_data=f"deny_{uid}")]
    ])
    await bot.send_video(ADMIN_ID, message.video.file_id, caption=f"🎥 保証申請\n{message.from_user.full_name} ({uid})\nタイプ: {choice}", reply_markup=kb)
    await message.answer("🎞️ 動画を受け取りました。管理者の確認をお待ちください。")
    STATE[uid]["stage"] = "warranty_pending"


# === /help ===
@dp.message(Command("help"))
async def help_cmd(message: types.Message):
    await message.answer(
        "🧭 コマンド一覧\n\n"
        "【ユーザー】\n/start - 購入を開始\n/保証 - 保証申請\n\n"
        "【管理者】\n/addstock 通話可能|データ\n/stock\n/code\n/codes\n/help"
    )


# === 起動 ===
async def main():
    print("🤖 eSIM自販機Bot 起動中...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
