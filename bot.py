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

    # --- コマンド一覧 ---
    commands_text = (
        "🧭 コマンド一覧\n\n"
        "【ユーザー向け】\n"
        "/start - 購入メニューを開く\n"
        "/保証 - 保証申請を行う\n"
        "/問い合わせ - 管理者に直接メッセージを送る\n\n"
        "【管理者専用】\n"
        "/addstock 通話可能|データ - 在庫を追加\n"
        "/stock - 在庫確認\n"
        "/config - 設定変更（価格・リンク）\n"
        "/code - 割引コードを発行\n"
        "/codes - コード一覧表示\n"
        "/help - この一覧を表示\n"
    )
    await message.answer(commands_text)

    # --- 商品選択 ---
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
    product = LINKS.get(choice, DEFAULT_LINKS[choice])

    # --- 正規料金メッセージ ---
    await callback.message.answer(
        f"{choice}ですね。\n"
        f"お支払い金額は {product['price']} 円です💰\n\n"
        f"こちらのPayPayリンクからお支払いください👇\n"
        f"{product['url']}\n\n"
        "支払い完了後に『完了』と送ってください。"
    )

    # --- 割引コード案内 ---
    await callback.message.answer(
        "🎟️ 割引コードをお持ちの場合は、今ここで入力してください。\n"
        "（例：RKTN-ABC123）\n"
        "※持っていない場合は無視して『完了』と送ってください。"
    )

    await callback.answer()


# === 割引コード認証 ===
@dp.message(F.text.regexp(r"RKTN-[A-Z0-9]{6}"))
async def check_code(message: types.Message):
    uid = message.from_user.id
    state = STATE.get(uid)
    if not state or state.get("stage") != "waiting_payment":
        return

    code = message.text.strip().upper()
    if code not in CODES:
        return await message.answer("⚠️ 無効なコードです。")
    if CODES[code]["used"]:
        return await message.answer("⚠️ このコードはすでに使用されています。")

    choice = state["type"]
    if CODES[code]["type"] != choice:
        return await message.answer("⚠️ このコードは別タイプ用です。")

    # コード承認
    CODES[code]["used"] = True
    save_data()

    # 割引価格・リンクを反映
    product = LINKS.get(choice, DEFAULT_LINKS[choice])
    price = product.get("discount_price") or product.get("price")
    link = product.get("discount_link") or product.get("url")

    # 状態保存（支払い確認に渡す）
    STATE[uid]["discount_code"] = code
    STATE[uid]["discount_price"] = price

    await message.answer("🎉 割引コードが承認されました！特別価格が適用されます✨")
    await message.answer(
        f"💸 割引後の支払い金額は {price} 円です。\n\n"
        f"こちらのPayPayリンクからお支払いください👇\n"
        f"{link}\n\n"
        "支払い完了後に『完了』と送ってください。"
    )


# === 支払いスクショ（管理者送信改良版） ===
@dp.message(F.photo)
async def handle_payment_photo(message: types.Message):
    uid = message.from_user.id
    state = STATE.get(uid)

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
    # 割引使用時はそちらを優先表示
    price = state.get("discount_price") or LINKS[choice]["price"]
    discount_code = state.get("discount_code")

    caption = (
        f"📩 支払い確認\n"
        f"👤 {message.from_user.full_name}\n"
        f"🆔 {uid}\n"
        f"📦 {choice}\n"
        f"💴 {price}円"
    )
    if discount_code:
        caption += f"\n🎟️ 割引コード: {discount_code}"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ 承認", callback_data=f"confirm_{uid}"),
         InlineKeyboardButton(text="❌ 拒否", callback_data=f"deny_{uid}")]
    ])

    await bot.send_photo(
        ADMIN_ID, message.photo[-1].file_id,
        caption=caption,
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


# === /config ===
@dp.message(Command("config"))
async def config_menu(message: types.Message):
    if not is_admin(message.from_user.id):
        return await message.answer("権限なし。")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💴 価格変更", callback_data="cfg_price")],
        [InlineKeyboardButton(text="💸 割引価格設定", callback_data="cfg_discount_price")],
        [InlineKeyboardButton(text="🔗 リンク変更", callback_data="cfg_link")],
        [InlineKeyboardButton(text="🔗 割引リンク設定", callback_data="cfg_discount_link")]
    ])
    await message.answer("⚙️ どの設定を変更しますか？", reply_markup=kb)


# === 設定カテゴリ選択 ===
@dp.callback_query(F.data.startswith("cfg_"))
async def cfg_select(callback: types.CallbackQuery):
    uid = callback.from_user.id
    mode = callback.data.split("_", 1)[1]  # ← discount_price, discount_link もそのまま取る

    # 種類に応じてラベルを変える
    if "link" in mode:
        label = "URL"
    elif "price" in mode:
        label = "価格"
    else:
        label = "設定"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💾 データ", callback_data=f"cfgsel_{mode}_データ")],
        [InlineKeyboardButton(text="📞 通話可能", callback_data=f"cfgsel_{mode}_通話可能")]
    ])
    await callback.message.answer(f"🛠 どちらの{label}を変更しますか？", reply_markup=kb)
    await callback.answer()


# === 設定対象（データ or 通話可能）選択 ===
@dp.callback_query(F.data.startswith("cfgsel_"))
async def cfgsel_type(callback: types.CallbackQuery):
    uid = callback.from_user.id
    parts = callback.data.split("_")

    # ["cfgsel", "discount", "price", "データ"] or ["cfgsel", "price", "データ"]
    if len(parts) < 3:
        await callback.message.answer("⚠️ 無効な設定データを受信しました。")
        await callback.answer()
        return

    # モードと対象抽出
    if parts[1] == "discount" and len(parts) >= 4:
        mode = f"discount_{parts[2]}"
        target = parts[3]
    else:
        mode = parts[1]
        target = parts[2]

    STATE[uid] = {"stage": f"config_{mode}", "target": target}

    # 入力促しメッセージ
    if "price" in mode:
        await callback.message.answer(f"💴 新しい価格を入力してください。\n対象: {target}")
    elif "link" in mode:
        await callback.message.answer(f"🔗 新しいリンク(URL)を入力してください。\n対象: {target}")
    else:
        await callback.message.answer("⚠️ 不明な設定モードです。")

    await callback.answer()


# === 管理者の入力反映 ===
@dp.message(F.text)
async def admin_config_edit(message: types.Message):
    uid = message.from_user.id
    if not is_admin(uid):
        return

    state = STATE.get(uid)
    if not state or not state["stage"].startswith("config_"):
        return

    stage = state["stage"]
    target = state["target"]
    new_value = message.text.strip()

    mode = stage.replace("config_", "")  # price / discount_price / link / discount_link

    # --- 価格関連 ---
    if "price" in mode:
        if not new_value.isdigit():
            return await message.answer("⚠️ 数値のみ入力してください。")

        LINKS.setdefault(target, {})
        LINKS[target][mode] = int(new_value)
        kind = "割引価格" if "discount" in mode else "通常価格"
        msg = f"💴 {target} の{kind}を {new_value} 円に更新しました。"

    # --- リンク関連 ---
    elif "link" in mode:
        if not (new_value.startswith("http://") or new_value.startswith("https://")):
            return await message.answer("⚠️ URL形式で入力してください。")

        LINKS.setdefault(target, {})
        LINKS[target][mode] = new_value
        kind = "割引リンク" if "discount" in mode else "通常リンク"
        msg = f"🔗 {target} の{kind}を更新しました。"

    else:
        return await message.answer("⚠️ 不明なモードです。")

    save_data()
    STATE.pop(uid, None)
    await message.answer(f"✅ {msg}")

# === /help ===
@dp.message(Command("help"))
async def help_cmd(message: types.Message):
    await message.answer(
        "🧭 コマンド一覧\n\n"
        "【ユーザー】\n/start - 購入を開始\n/保証 - 保証申請\n\n"
        "【管理者】\n/addstock 通話可能|データ\n/stock\n/code\n/codes\n/config\n/help"
    )

# === /問い合わせ ===
@dp.message(Command("問い合わせ"))
async def inquiry_start(message: types.Message):
    STATE[message.from_user.id] = {"stage": "inquiry_waiting"}
    await message.answer("💬 お問い合わせ内容を入力してください。\n（送信後、管理者に転送されます）")

@dp.message(F.text)
async def inquiry_message(message: types.Message):
    state = STATE.get(message.from_user.id)
    if state and state.get("stage") == "inquiry_waiting":
        await bot.send_message(
            ADMIN_ID,
            f"📩 新しいお問い合わせ\n👤 {message.from_user.full_name}\n🆔 {message.from_user.id}\n\n📝 内容:\n{message.text}"
        )
        await message.answer("✅ お問い合わせを送信しました。返信までお待ちください。")
        STATE.pop(message.from_user.id, None)

# === 起動 ===
async def main():
    print("🤖 eSIM自販機Bot 起動中...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
