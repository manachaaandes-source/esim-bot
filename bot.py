import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ForceReply
import json
import os
import random
import string
import shutil

# === 基本設定 ===
with open("config.json", "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

bot = Bot(token=CONFIG["TELEGRAM_TOKEN"])
dp = Dispatcher()

ADMIN_ID = 5397061486  # あなたのTelegram ID
STATE = {}

# ① 永続化パス
DATA_FILE = "/app/data/data.json"
DEFAULT_LINKS = {
    "通話可能": {"url": "https://qr.paypay.ne.jp/p2p01_uMrph5YFDveRCFmw", "price": 3000},
    "データ": {"url": "https://qr.paypay.ne.jp/p2p01_RSC8W9GG2ZcIso1I", "price": 1500},
}

# === 固定価格設定 ===
FIXED_PRICES = {
    "データ": {"normal": 1500, "discount": 1250},
    "通話可能": {"normal": 3000, "discount": 2500}
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
    global STOCK, LINKS, CODES
    try:
        if not os.path.exists(DATA_FILE):
            return ensure_data_file()

        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # メモリ上に上書き
        return (
            data.get("STOCK", {"通話可能": [], "データ": []}),
            data.get("LINKS", DEFAULT_LINKS),
            data.get("CODES", {})
        )
    except Exception as e:
        print(f"⚠️ data.json読み込み失敗: {e}")
        return {"通話可能": [], "データ": []}, DEFAULT_LINKS, {}


def save_data():
    try:
        data = {"STOCK": STOCK, "LINKS": LINKS, "CODES": CODES}
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
            f.flush()
            os.fsync(f.fileno())  # ← ファイル確実に書き込む
        print("💾 data.json 保存完了 ✅")
        print(json.dumps(LINKS, ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"⚠️ data保存失敗: {e}")

def auto_backup():
    """在庫減少など重要操作後に自動バックアップ"""
    try:
        backup_dir = "/app/data/backup"
        os.makedirs(backup_dir, exist_ok=True)

        for f in os.listdir(backup_dir):
            if f.startswith("data_auto") and f.endswith(".json"):
                os.remove(os.path.join(backup_dir, f))

        backup_path = os.path.join(backup_dir, "data_auto.json")
        shutil.copy(DATA_FILE, backup_path)
        print(f"🗂️ 自動バックアップ作成完了: {backup_path}")
    except Exception as e:
        print(f"⚠️ 自動バックアップ失敗: {e}")

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
        "/restore_auto - 自動バックアップから復元\n"
        "/broadcast メッセージ - 全ユーザーにお知らせ送信\n"
    )
    await message.answer(commands_text)

    # --- 商品選択 ---
    stock_info = f"📦 在庫状況\n通話可能: {len(STOCK['通話可能'])}枚\nデータ: {len(STOCK['データ'])}枚\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"📞 通話可能 ({len(STOCK['通話可能'])}枚)", callback_data="type_通話可能")],
        [InlineKeyboardButton(text=f"💾 データ ({len(STOCK['データ'])}枚)", callback_data="type_データ")]
    ])
    await message.answer("こんにちは！esim半自販機botです。\nどちらにしますか？\n\n" + stock_info, reply_markup=kb)


# === 商品タイプ選択 ===
@dp.callback_query(F.data.startswith("type_"))
async def select_type(callback: types.CallbackQuery):
    uid = callback.from_user.id
    choice = callback.data.split("_")[1]

    if len(STOCK[choice]) == 0:
        await callback.message.answer(f"⚠️ 現在「{choice}」の在庫がありません。")
        await callback.answer()
        return

    # 一旦、ユーザーが何を選んだかを保持
    STATE[uid] = {"stage": "input_count", "type": choice}

    await callback.message.answer(
        f"🧾 「{choice}」を選択しました。\n何枚購入しますか？（1〜{len(STOCK[choice])}）"
    )
    await callback.answer()

# --- 枚数入力 ---
@dp.message(F.text.regexp(r"^\d+$"))
async def handle_count_input(message: types.Message):
    uid = message.from_user.id
    state = STATE.get(uid)
    if not state or state.get("stage") != "input_count":
        return

    count = int(message.text.strip())
    choice = state["type"]

    if count <= 0:
        return await message.answer("⚠️ 1以上の枚数を入力してください。")
    if count > len(STOCK[choice]):
        return await message.answer(f"⚠️ 在庫不足です（最大 {len(STOCK[choice])} 枚まで）。")

    # --- 基本価格 ---
    base_price = FIXED_PRICES[choice]["normal"]

    # --- まとめ買い割引 ---
    discount_rate = 0
    if 10 <= count:
        discount_rate = 0.10
        discount_type = "10%"
    elif 6 <= count <= 9:
        discount_rate = 0.05
        discount_type = "5%"
    else:
        discount_type = None

    total_price = int(base_price * count * (1 - discount_rate))

    STATE[uid] = {
        "stage": "waiting_payment",
        "type": choice,
        "count": count,
        "final_price": total_price,
        "discount_rate": discount_rate,
        "discount_type": discount_type
    }

    msg = f"🧾 {choice} を {count} 枚購入ですね。\n合計金額は {total_price:,} 円です💰"

    if not discount_type:
        msg += (
            "\n🎟️ 割引コードをお持ちの場合は今入力できます。\n"
            "⚠️ 2〜5枚の購入時は1枚分のみ割引価格（1250/2500円）になります。"
        )
    else:
        msg += f"\n🎉 まとめ買い割引（{discount_type}OFF）が適用されました。"

    product = LINKS.get(choice, DEFAULT_LINKS[choice])
    msg += (
        f"\n\nこちらのPayPayリンク👇\n{product['url']}\n\n"
        "支払い後に『完了』と送ってください。"
    )

    await message.answer(msg)

# === 支払い完了報告 ===
@dp.message(F.text.lower().contains("完了"))
async def handle_done(message: types.Message):
    uid = message.from_user.id
    state = STATE.get(uid)

    if not state or state.get("stage") != "waiting_payment":
        return await message.answer("⚠️ まず /start から始めてください。")

    STATE[uid]["stage"] = "waiting_screenshot"

    # 割引適用表示
    discount_price = state.get("final_price")
    if discount_price:
        price_text = f"（支払金額 {discount_price}円）"
    else:
        price_text = ""

    await message.answer(
        f"💴 支払い完了ありがとうございます{price_text}。\n"
        "スクリーンショットを送ってください。"
    )


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
    count = state.get("count", 1)
    if CODES[code]["type"] != choice:
        return await message.answer("⚠️ このコードは別タイプ用です。")

    # --- 割引価格ロジック ---
    base_price = FIXED_PRICES[choice]["normal"]
    discount_price = FIXED_PRICES[choice]["discount"]

    if count == 1:
        total_price = discount_price
    elif 2 <= count <= 5:
        total_price = discount_price + base_price * (count - 1)
    else:
        total_price = base_price * count  # 6枚以上はまとめ買い割引優先

    # コード消費
    CODES[code]["used"] = True
    save_data()

    STATE[uid]["discount_code"] = code
    STATE[uid]["final_price"] = total_price

    await message.answer(
        f"🎉 割引コードが承認されました！\n"
        f"⚠️ 2〜5枚購入時は1枚分のみ割引適用です。\n\n"
        f"💸 支払金額: {total_price:,}円\n"
        f"💴 割引価格: {discount_price}円（1枚目のみ）\n\n"
        f"こちらのリンク👇\n{LINKS[choice]['discount_link']}\n\n"
        "支払い後に『完了』と送ってください。"
    )

# === 支払いスクショ（管理者送信改良版） ===
@dp.message(F.photo)
async def handle_payment_photo(message: types.Message):
    uid = message.from_user.id
    state = STATE.get(uid)

    # --- 在庫追加時 ---
    if state and state.get("stage") == "adding_stock":
        choice = state["type"]
        STOCK[choice].append(message.photo[-1].file_id)
        save_data()
        await message.answer(f"✅ {choice} に在庫追加（{len(STOCK[choice])}枚）")
        STATE.pop(uid, None)
        return

    # --- 支払い確認時 ---
    if not state or state.get("stage") != "waiting_screenshot":
        return

    choice = state["type"]
    count = state.get("count", 1)
    price = state.get("final_price") or state.get("discount_price") or (LINKS[choice]["price"] * count)
    discount_code = state.get("discount_code")

    caption = (
        f"📩 支払い確認\n"
        f"👤 {message.from_user.full_name}\n"
        f"🆔 {uid}\n"
        f"📦 {choice}\n"
        f"🧾 枚数: {count}\n"
        f"💴 支払金額: {price}円"
    )
    if discount_code:
        caption += f"\n🎟️ 割引コード: {discount_code}"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ 承認", callback_data=f"confirm_{uid}"),
            InlineKeyboardButton(text="❌ 拒否", callback_data=f"deny_{uid}")
        ]
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

    count = state.get("count", 1)

    if len(STOCK[choice]) < count:
        await bot.send_message(target_id, f"⚠️ 在庫が不足しています（{len(STOCK[choice])}枚しか残っていません）。")
        return await callback.answer("在庫不足")

    for i in range(count):
        file_id = STOCK[choice].pop(0)
        await bot.send_photo(target_id, file_id, caption=f"✅ {choice} #{i+1}/{count} を送信しました！")

        await log_purchase(
            target_id,
            callback.from_user.full_name,
            choice,
            state.get("count", 1),
            state.get("final_price") or LINKS[choice]["price"],
            state.get("discount_code")
        )

    save_data()
    auto_backup()
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

# === /help ===
@dp.message(Command("help"))
async def help_cmd(message: types.Message):
    if is_admin(message.from_user.id):
        text = (
           "🧭 コマンド一覧\n\n"
           "【ユーザー向け】\n"
           "/start - 購入メニューを開く\n"
           "/保証 - 保証申請を行う\n"
           "/問い合わせ - 管理者に直接メッセージを送る\n\n"
           "【管理者専用】\n"
           "/addstock <商品名> - 在庫を追加\n"
           "/addproduct <商品名> - 新商品カテゴリを追加\n"
           "/stock - 在庫確認\n"
           "/config - 設定変更（価格・リンク）\n"
           "/code - 割引コードを発行\n"
           "/codes - コード一覧表示\n"
           "/resetcodes - 割引コードをリセット\n"
           "/backup - データをバックアップ\n"
           "/restore - バックアップから復元\n"
           "/restore_auto - 自動バックアップから復元\n"
           "/broadcast メッセージ - 全ユーザーにお知らせ送信\n"
           "/reply <ID> <内容> - 問い合わせへの返信\n"
           "/help - この一覧を表示\n"
        )
    else:
        text = (
            "🧭 **コマンド一覧（ユーザー用）**\n\n"
            "/start - 購入メニューを開く\n"
            "/保証 - 保証申請を行う\n"
            "/問い合わせ - 管理者に直接メッセージを送る\n"
            "/help - コマンド一覧を表示\n\n"
            "ℹ️ 一部コマンドは管理者専用です。"
        )

    await message.answer(text, parse_mode="Markdown")

# === /addstock ===
@dp.message(Command("addstock"))
async def addstock(message: types.Message):
    """在庫追加（動的対応版）"""
    if not is_admin(message.from_user.id):
        return await message.answer("権限なし")

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        available = " / ".join(STOCK.keys())
        return await message.answer(f"⚙️ 使い方: /addstock <商品名>\n利用可能カテゴリ: {available}")

    product_type = parts[1].strip()
    if product_type not in STOCK:
        return await message.answer(f"⚠️ 『{product_type}』 は存在しません。まず /addproduct で作成してください。")

    STATE[message.from_user.id] = {"stage": "adding_stock", "type": product_type}
    await message.answer(f"📸 {product_type} の在庫画像を送ってください。")


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

# 🔽🔽🔽 この下に追加 🔽🔽🔽
# === /addproduct ===
@dp.message(Command("addproduct"))
async def add_product(message: types.Message):
    """新しい商品カテゴリを追加"""
    if not is_admin(message.from_user.id):
        return await message.answer("権限なし")

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.answer("⚙️ 使い方: /addproduct <商品名>\n例: /addproduct プリペイドSIM")

    new_type = parts[1].strip()

    # 既存チェック
    if new_type in STOCK:
        return await message.answer(f"⚠️ 「{new_type}」はすでに存在しています。")

    # 新しい商品カテゴリを登録
    STOCK[new_type] = []
    LINKS[new_type] = {"url": "未設定", "price": 0}
    save_data()

    await message.answer(f"✅ 新しい商品カテゴリ「{new_type}」を追加しました。\n"
                         f"在庫追加は /addstock {new_type} で行えます。")

# === /addstock（改良版） ===
@dp.message(Command("addstock"))
async def addstock(message: types.Message):
    """在庫追加（カスタム商品対応）"""
    if not is_admin(message.from_user.id):
        return await message.answer("権限なし")

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        available = " / ".join(STOCK.keys())
        return await message.answer(f"⚙️ 使い方: /addstock <商品名>\n利用可能カテゴリ: {available}")

    product_type = parts[1].strip()
    if product_type not in STOCK:
        return await message.answer(f"⚠️ 『{product_type}』 は存在しません。まず /addproduct で作成してください。")

    STATE[message.from_user.id] = {"stage": "adding_stock", "type": product_type}
    await message.answer(f"📸 {product_type} の在庫画像を送ってください。")
# 🔼🔼🔼 ここまでを追加 🔼🔼🔼

# === /codes ===
@dp.message(Command("codes"))
async def list_codes(message: types.Message):
    if not is_admin(message.from_user.id): return await message.answer("権限なし")
    if not CODES: return await message.answer("コードなし")
    text = "🎟️ コード一覧\n" + "\n".join([f"{k} | {v['type']} | {'✅使用済' if v['used'] else '🟢未使用'}" for k, v in CODES.items()])
    await message.answer(text)

# === /resetcodes ===
@dp.message(Command("resetcodes"))
async def reset_codes(message: types.Message):
    if not is_admin(message.from_user.id):
        return await message.answer("権限なし")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟢 使用状態リセット（未使用に戻す）", callback_data="reset_unused")],
        [InlineKeyboardButton(text="🔴 全削除", callback_data="reset_delete")]
    ])
    await message.answer("🎟️ 割引コードのリセット方法を選んでください：", reply_markup=kb)


@dp.callback_query(F.data == "reset_unused")
async def reset_unused(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return await callback.answer("権限なし", show_alert=True)
    for c in CODES.values():
        c["used"] = False
    save_data()
    await callback.message.answer("✅ すべてのコードを『未使用』状態に戻しました。")
    await callback.answer()


@dp.callback_query(F.data == "reset_delete")
async def reset_delete(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return await callback.answer("権限なし", show_alert=True)
    CODES.clear()
    save_data()
    await callback.message.answer("🗑️ すべての割引コードを削除しました。")
    await callback.answer()

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

    if len(parts) < 3:
        await callback.message.answer("⚠️ 無効な設定データを受信しました。")
        await callback.answer()
        return

    if parts[1] == "discount" and len(parts) >= 4:
        mode = f"discount_{parts[2]}"
        target = parts[3]
    else:
        mode = parts[1]
        target = parts[2]

    # ✅ 状態を確実に保持（Zeabur対策）
    STATE[uid] = {"stage": f"config_{mode}", "target": target}
    print(f"[CONFIG STATE SET] {uid}: stage=config_{mode}, target={target}")

    # 入力メッセージ
    if "price" in mode:
        await callback.message.answer(f"💴 新しい価格を入力してください。\n対象: {target}")
    elif "link" in mode:
        await callback.message.answer(f"🔗 新しいリンク(URL)を入力してください。\n対象: {target}")
    else:
        await callback.message.answer("⚠️ 不明な設定モードです。")

    # ✅ 遅延付きで callback.answer() 実行
    await asyncio.sleep(0.5)
    try:
        await callback.answer()
    except Exception as e:
        print(f"[WARN] callback.answer() skipped: {e}")

# === /backup ===
@dp.message(Command("backup"))
async def backup_data(message: types.Message):
    if not is_admin(message.from_user.id): 
        return await message.answer("権限なし")

    import shutil, datetime
    os.makedirs("/app/data/backup", exist_ok=True)
    filename = f"/app/data/backup/data_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    shutil.copy(DATA_FILE, filename)
    await message.answer(f"💾 バックアップ作成完了:\n<code>{filename}</code>", parse_mode="HTML")
    
# === /restore ===
@dp.message(Command("restore"))
async def restore_backup(message: types.Message):
    if not is_admin(message.from_user.id):
        return await message.answer("権限なし")

    backup_dir = "/app/data/backup"
    if not os.path.exists(backup_dir):
        return await message.answer("⚠️ バックアップフォルダが存在しません。")

    files = sorted(
        [f for f in os.listdir(backup_dir) if f.startswith("data_") and f.endswith(".json")],
        reverse=True
    )

    if not files:
        return await message.answer("⚠️ バックアップファイルがありません。")

    # 最新5件を表示
    recent_files = files[:5]
    buttons = [
        [InlineKeyboardButton(text=f.replace('data_', '').replace('.json', ''), callback_data=f"restore_{f}")]
        for f in recent_files
    ]
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer("📂 復元したいバックアップを選んでください：", reply_markup=kb)


@dp.callback_query(F.data.startswith("restore_"))
async def confirm_restore(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return await callback.answer("権限なし", show_alert=True)

    filename = callback.data.replace("restore_", "")
    backup_path = os.path.join("/app/data/backup", filename)

    if not os.path.exists(backup_path):
        return await callback.message.answer("⚠️ 指定されたバックアップが見つかりません。")

    # 復元処理
    import shutil
    shutil.copy(backup_path, DATA_FILE)

    global STOCK, LINKS, CODES
    STOCK, LINKS, CODES = load_data()

    await callback.message.answer(f"✅ バックアップを復元しました：\n<code>{filename}</code>", parse_mode="HTML")
    await callback.answer("復元完了")

# === /restore_auto ===
@dp.message(Command("restore_auto"))
async def restore_auto_backup(message: types.Message):
    if not is_admin(message.from_user.id):
        return await message.answer("権限なし")

    backup_path = "/app/data/backup/data_auto.json"
    if not os.path.exists(backup_path):
        return await message.answer("⚠️ 自動バックアップが見つかりません。")

    import shutil
    shutil.copy(backup_path, DATA_FILE)

    global STOCK, LINKS, CODES
    STOCK, LINKS, CODES = load_data()

    await message.answer("✅ 自動バックアップを復元しました。")

# === /status ===
@dp.message(Command("status"))
async def status_cmd(message: types.Message):
    if not is_admin(message.from_user.id): 
        return await message.answer("権限なし")
    info = (
        f"📊 Botステータス\n"
        f"在庫: 通話可能={len(STOCK['通話可能'])} / データ={len(STOCK['データ'])}\n"
        f"割引コード数: {len(CODES)}\n"
        f"保存先: {DATA_FILE}\n"
        f"稼働中: ✅ 正常"
    )
    await message.answer(info)

# === /stats ===
@dp.message(Command("stats"))
async def stats_cmd(message: types.Message):
    if not is_admin(message.from_user.id):
        return await message.answer("権限なし")

    total_sales = 0
    total_codes_used = sum(1 for v in CODES.values() if v["used"])
    total_stock = sum(len(v) for v in STOCK.values())

    # 売上合計計算
    for t, data in LINKS.items():
        price = data.get("price", 0)
        total_items = len(DEFAULT_LINKS[t]["url"]) if t in DEFAULT_LINKS else 0
        sold_count = max(0, total_items - len(STOCK[t]))
        total_sales += sold_count * price

    text = (
        f"📊 **販売統計レポート**\n\n"
        f"💴 推定総売上: {total_sales:,}円\n"
        f"🎟️ 使用済み割引コード: {total_codes_used}件\n"
        f"📦 在庫残数:\n"
        f"　📞 通話可能: {len(STOCK['通話可能'])}枚\n"
        f"　💾 データ: {len(STOCK['データ'])}枚\n"
    )
    await message.answer(text, parse_mode="Markdown")


# === /history ===
PURCHASE_LOG = []

async def log_purchase(uid, username, choice, count, price, code=None):
    PURCHASE_LOG.append({
        "uid": uid,
        "name": username,
        "type": choice,
        "count": count,
        "price": price,
        "code": code,
    })

@dp.message(Command("history"))
async def show_history(message: types.Message):
    if not is_admin(message.from_user.id):
        return await message.answer("権限なし")

    if not PURCHASE_LOG:
        return await message.answer("📄 購入履歴はまだありません。")

    lines = [
        f"👤 {p['name']} ({p['uid']})\n📦 {p['type']} x{p['count']}枚 | 💴 {p['price']}円"
        + (f" | 🎟️ {p['code']}" if p['code'] else "")
        for p in PURCHASE_LOG[-10:]
    ]
    await message.answer("🧾 <b>直近の購入履歴（最大10件）</b>\n\n" + "\n\n".join(lines), parse_mode="HTML")


# === /問い合わせ ===
@dp.message(Command("問い合わせ"))
async def inquiry_start(message: types.Message):
    STATE[message.from_user.id] = {"stage": "inquiry_waiting"}
    await message.answer("💬 お問い合わせ内容を入力してください。\n（送信後、管理者に転送されます）")

# ⬇⬇⬇ ここに追加 ⬇⬇⬇

# === /返信 ===
@dp.message(Command("返信"))
async def reply_to_user(message: types.Message):
    if not is_admin(message.from_user.id):
        return await message.answer("権限なし")

    try:
        parts = message.text.split(maxsplit=2)
        if len(parts) < 3:
            return await message.answer("使い方: /返信 <ユーザーID> <内容>")

        target_id = int(parts[1])
        reply_text = parts[2]

        await bot.send_message(target_id, f"💬 管理者からの返信:\n{reply_text}")
        await message.answer("✅ ユーザーに返信を送信しました。")

    except Exception as e:
        await message.answer(f"⚠️ 返信に失敗しました: {e}")

# === ユーザー問い合わせ & 管理者設定 統合ハンドラ ===
@dp.message(F.text)
async def handle_text_message(message: types.Message):
    uid = message.from_user.id
    text = message.text.strip()
    state = STATE.get(uid)

    # お問い合わせモード
    if state and state.get("stage") == "inquiry_waiting":
        await bot.send_message(
            ADMIN_ID,
            f"📩 新しいお問い合わせ\n👤 {message.from_user.full_name}\n🆔 {uid}\n\n📝 内容:\n{text}"
        )
        await message.answer("✅ お問い合わせを送信しました。返信までお待ちください。")
        STATE.pop(uid, None)
        return  # ←ここ必須！

    # 管理者設定モード
    if is_admin(uid) and state and state["stage"].startswith("config_"):
        stage = state["stage"]
        target = state["target"]
        new_value = text

        global LINKS
        if "price" in stage:
            if not new_value.isdigit():
                return await message.answer("⚠️ 数値のみ入力してください。")

            LINKS.setdefault(target, {})
            updated_link = dict(LINKS[target])
            if "discount" in stage:
                updated_link["discount_price"] = int(new_value)
                kind = "割引価格"
            else:
                updated_link["price"] = int(new_value)
                kind = "通常価格"

            LINKS[target] = updated_link
            msg = f"💴 {target} の{kind}を {new_value} 円に更新しました。"

        elif "link" in stage:
            if not (new_value.startswith("http://") or new_value.startswith("https://")):
                return await message.answer("⚠️ URL形式で入力してください。")

            LINKS.setdefault(target, {})
            if "discount" in stage:
                LINKS[target]["discount_link"] = new_value
                kind = "割引リンク"
            else:
                LINKS[target]["url"] = new_value
                kind = "通常リンク"

            msg = f"🔗 {target} の{kind}を更新しました。"

        else:
            return await message.answer("⚠️ 不明なモードです。")

        save_data()
        print(f"[CONFIG UPDATED] {target} {kind} -> {new_value}")
        STATE.pop(uid, None)
        await message.answer(f"✅ {msg}")
        
# === 全ユーザー通知機能 ===
USERS_FILE = "/app/data/users.json"

def load_users():
    """ユーザー一覧を読み込む"""
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()

def save_users():
    """ユーザー一覧を保存する"""
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(list(USERS), f, ensure_ascii=False, indent=2)

# 初期ロード
USERS = load_users()


# === /broadcast ===
@dp.message(Command("broadcast"))
async def broadcast(message: types.Message):
    """管理者専用：全ユーザーに一斉通知"""
    if not is_admin(message.from_user.id):
        return await message.answer("権限なし")

    # /broadcast の後のテキストを取得
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.answer("⚠️ 送信内容を指定してください。\n例: /broadcast メンテナンスのお知らせ")

    content = parts[1].strip()
    if not content:
        return await message.answer("⚠️ 内容が空です。")

    sent = 0
    failed = 0
    for uid in USERS:
        try:
            await bot.send_message(uid, f"📢 管理者からのお知らせ:\n{content}")
            sent += 1
        except Exception as e:
            print(f"⚠️ ユーザー {uid} への送信失敗: {e}")
            failed += 1

    await message.answer(f"✅ 通知送信完了\n成功: {sent}件 / 失敗: {failed}件")
    return  # ← 他のハンドラに流れないようにする


# === ユーザー記録（最後に配置！） ===
@dp.message(F.text & ~F.text.startswith("/") & ~F.text.regexp(r"RKTN-[A-Z0-9]{6}"))
async def track_users(message: types.Message):
    """
    全ユーザーを記録（通常メッセージのみ）
    - コマンド（/help, /broadcast など）
    - 割引コード（RKTN-xxxxxx）
    - 問い合わせモード中
    これらは除外
    """
    # 安全スキップ条件
    if not message.text:
        return

    # すでに問い合わせモード中のユーザーは除外
    if STATE.get(message.from_user.id, {}).get("stage") == "inquiry_waiting":
        return

    # コマンド以外・問い合わせ以外の普通の発言を記録
    if message.from_user.id not in USERS:
        USERS.add(message.from_user.id)
        save_users()
        print(f"👤 新規ユーザー登録: {message.from_user.id} ({message.from_user.full_name})")

# === 起動 ===
async def main():
    print("🤖 eSIM自販機Bot 起動中...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
