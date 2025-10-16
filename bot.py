import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ForceReply
import json
import os
import random
import string
import shutil

# =========================
# 基本設定 / 永続ファイル準備
# =========================
CONFIG_PATH = "config.json"
if not os.path.exists(CONFIG_PATH):
    raise FileNotFoundError("config.json が見つかりません。Zeabur のリポジトリに含めるか、環境変数で TELEGRAM_TOKEN を設定してください。")

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

# 環境変数優先（Zeabur推奨）。無ければ config.json を使う
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", CONFIG.get("TELEGRAM_TOKEN", ""))
if not TELEGRAM_TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN が未設定です。環境変数または config.json で設定してください。")

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

ADMIN_ID = 5397061486  # あなたのTelegram ID（依頼者確認済み）
STATE: dict[int, dict] = {}

# 永続化パス
DATA_DIR = "/app/data"
os.makedirs(DATA_DIR, exist_ok=True)
DATA_FILE = os.path.join(DATA_DIR, "data.json")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
BACKUP_DIR = os.path.join(DATA_DIR, "backup")
os.makedirs(BACKUP_DIR, exist_ok=True)

DEFAULT_LINKS = {
    "通話可能": {"url": "https://qr.paypay.ne.jp/p2p01_uMrph5YFDveRCFmw", "price": 3000},
    "データ": {"url": "https://qr.paypay.ne.jp/p2p01_RSC8W9GG2ZcIso1I", "price": 1500},
}

# 固定価格（フォールバック）
FIXED_PRICES = {
    "データ": {"normal": 1500, "discount": 1250},
    "通話可能": {"normal": 3000, "discount": 2500}
}

def ensure_data_file():
    """data.json がない場合に初期化"""
    if not os.path.exists(DATA_FILE):
        data = {"STOCK": {"通話可能": [], "データ": []}, "LINKS": DEFAULT_LINKS, "CODES": {}}
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print("🆕 data.json を新規作成しました。")
        return data
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def load_data():
    """data.jsonをロードして3値を返す（STOCK, LINKS, CODES）"""
    global STOCK, LINKS, CODES
    try:
        if not os.path.exists(DATA_FILE):
            ensure_data_file()

        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        STOCK = data.get("STOCK", {"通話可能": [], "データ": []})
        LINKS = data.get("LINKS", DEFAULT_LINKS)
        CODES = data.get("CODES", {})
        return STOCK, LINKS, CODES

    except Exception as e:
        print(f"⚠️ data.json読み込み失敗: {e}")
        STOCK, LINKS, CODES = {"通話可能": [], "データ": []}, DEFAULT_LINKS, {}
        return STOCK, LINKS, CODES

def save_data():
    try:
        data = {"STOCK": STOCK, "LINKS": LINKS, "CODES": CODES}
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
            f.flush()
            os.fsync(f.fileno())
        print("💾 data.json 保存完了 ✅")
    except Exception as e:
        print(f"⚠️ data保存失敗: {e}")

def auto_backup():
    """在庫減少など重要操作後に自動バックアップ"""
    try:
        # 1つだけ最新の自動バックアップにする（古いもの削除）
        for f in os.listdir(BACKUP_DIR):
            if f.startswith("data_auto") and f.endswith(".json"):
                os.remove(os.path.join(BACKUP_DIR, f))

        backup_path = os.path.join(BACKUP_DIR, "data_auto.json")
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

def is_admin(uid: int) -> bool:
    return uid == ADMIN_ID

# ===============
# コマンド: /start
# ===============
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    STATE[message.from_user.id] = {"stage": "select"}

    # コマンド一覧
    if is_admin(message.from_user.id):
        commands_text = (
            "🧭 <b>コマンド一覧</b>\n\n"
            "【🧑‍💻 ユーザー向け】\n"
            "/start - 購入メニューを開く\n"
            "/保証 - 保証申請を行う\n"
            "/問い合わせ - 管理者に直接メッセージを送る\n"
            "/help - コマンド一覧を表示\n\n"
            "【👑 管理者専用】\n"
            "/addstock &lt;商品名&gt; - 在庫を追加\n"
            "/addproduct &lt;商品名&gt; - 新しい商品カテゴリを追加\n"
            "/stock - 在庫確認\n"
            "/config - 設定変更（価格・リンク・割引）\n"
            "/code &lt;タイプ&gt; - 割引コードを発行（通話可能 / データなど）\n"
            "/codes - コード一覧を表示\n"
            "/resetcodes - 割引コードをリセット（未使用に戻す / 全削除）\n"
            "/backup - データをバックアップ保存\n"
            "/restore - 手動バックアップから復元\n"
            "/restore_auto - 自動バックアップから復元\n"
            "/status - 現在のBotステータス確認\n"
            "/stats - 販売統計レポートを表示\n"
            "/history - 直近の購入履歴を表示\n"
            "/broadcast &lt;内容&gt; - 全ユーザーに一斉通知\n"
            "/返信 &lt;ユーザーID&gt; &lt;内容&gt; - 問い合わせに返信を送信\n"
            "/help - このコマンド一覧を再表示\n"
        )
    else:
        commands_text = (
            "🧭 <b>コマンド一覧（ユーザー用）</b>\n\n"
            "/start - 購入メニューを開く\n"
            "/保証 - 保証申請を行う\n"
            "/問い合わせ - 管理者に直接メッセージを送る\n"
            "/help - コマンド一覧を表示\n\n"
            "ℹ️ 一部コマンドは管理者専用です。"
        )

    await message.answer(commands_text, parse_mode="HTML")

    # 商品選択メニュー
    stock_info_lines = [f"{k}: {len(v)}枚" for k, v in STOCK.items()]
    stock_info = "📦 在庫状況\n" + "\n".join(stock_info_lines)

    buttons = [
        [InlineKeyboardButton(text=f"{k} ({len(v)}枚)", callback_data=f"type_{k}")]
        for k, v in STOCK.items()
    ]
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    await message.answer(
        "こんにちは！ eSIM半自販機Botです。\nどちらにしますか？\n\n" + stock_info,
        reply_markup=kb
    )

# ================================
# 商品タイプ選択 → 枚数入力ステップ
# ================================
@dp.callback_query(F.data.startswith("type_"))
async def select_type(callback: types.CallbackQuery):
    uid = callback.from_user.id
    type_name = callback.data.split("_", 1)[1]

    STATE[uid] = {"stage": "input_count", "type": type_name}

    stock_len = len(STOCK.get(type_name, []))
    if stock_len == 0:
        await callback.message.answer(f"⚠️ 「{type_name}」は在庫がありません。")
        await callback.answer()
        return

    await callback.message.answer(
        f"「{type_name}」を選択しました。\n"
        f"何枚購入しますか？（1〜{min(stock_len, 9)}）"
    )
    await callback.answer()

@dp.message(F.text.regexp(r"^\d+$"))
async def handle_count_input(message: types.Message):
    uid = message.from_user.id
    state = STATE.get(uid)
    if not state or state.get("stage") not in ["input_count", "select_count"]:
        return

    count = int(message.text.strip())
    choice = state["type"]

    available_stock = STOCK.get(choice, [])
    if len(available_stock) == 0:
        return await message.answer(f"⚠️ 現在「{choice}」の在庫がありません。")
    if count <= 0:
        return await message.answer("⚠️ 1以上の枚数を入力してください。")
    if count > len(available_stock):
        return await message.answer(f"⚠️ 在庫不足です（最大 {len(available_stock)} 枚まで）。")

    link_info = LINKS.get(choice)
    if not link_info:
        return await message.answer(f"⚠️ 「{choice}」のリンク情報が未設定です。\n/config で設定してください。")

    base_price = link_info.get("price", 0) or FIXED_PRICES.get(choice, {}).get("normal", 0)

    # まとめ買い割引
    discount_rate = 0
    discount_type = None
    if 10 <= count:
        discount_rate = 0.10; discount_type = "10%"
    elif 6 <= count <= 9:
        discount_rate = 0.05; discount_type = "5%"
    total_price = int(base_price * count * (1 - discount_rate))

    STATE[uid] = {
        "stage": "waiting_payment",
        "type": choice,
        "count": count,
        "final_price": total_price,
        "discount_rate": discount_rate,
        "discount_type": discount_type
    }

    msg = f"🧾 {choice} を {count} 枚購入ですね。\n💴 合計金額: {total_price:,} 円"
    if discount_type:
        msg += f"\n🎉 まとめ買い割引（{discount_type}OFF）が適用されました。"
    else:
        msg += (
            "\n🎟️ 割引コードをお持ちの場合は今入力できます。\n"
            "⚠️ 2〜5枚の購入時は1枚分のみ割引価格（1250/2500円）になります。"
        )

    pay_url = link_info.get("url") or DEFAULT_LINKS.get(choice, {}).get("url", "未設定")
    msg += f"\n\nこちらのPayPayリンク👇\n{pay_url}\n\n支払い後に『完了』と送ってください。"

    await message.answer(msg)

    # 💳 ここでカード決済を提案
    await _send_card_pay_offer(uid, choice, count, total_price)

# =====================
# 支払い完了 → スクショ待ち
# =====================
@dp.message(F.text.lower().contains("完了"))
async def handle_done(message: types.Message):
    uid = message.from_user.id
    state = STATE.get(uid)
    if not state or state.get("stage") != "waiting_payment":
        return await message.answer("⚠️ まず /start から始めてください。")

    STATE[uid]["stage"] = "waiting_screenshot"

    discount_price = state.get("final_price")
    price_text = f"（支払金額 {discount_price}円）" if discount_price else ""
    await message.answer(f"💴 支払い完了ありがとうございます{price_text}。\nスクリーンショットを送ってください。")

# =====================
# 割引コード認証
# =====================
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
    code_data = CODES[code]

    if code_data["type"] != choice:
        return await message.answer("⚠️ このコードは別タイプ用です。")

    base_price = FIXED_PRICES[choice]["normal"]
    discount_price = FIXED_PRICES[choice]["discount"]
    total_price = base_price * count

    if "discount_value" in code_data:
        off = code_data["discount_value"]
        total_price = max(0, total_price - off)
        msg = f"🎟️ クーポンコードが適用されました！\n💸 {off:,}円引き\n💴 支払金額: {total_price:,}円"
    else:
        if count == 1:
            total_price = discount_price
        elif 2 <= count <= 5:
            total_price = discount_price + base_price * (count - 1)
        else:
            total_price = base_price * count
        msg = (
            f"🎉 割引コードが承認されました！\n"
            f"⚠️ 2〜5枚購入時は1枚分のみ割引適用です。\n\n"
            f"💸 支払金額: {total_price:,}円\n"
            f"💴 割引価格: {discount_price}円（1枚目のみ）"
        )

    CODES[code]["used"] = True
    save_data()

    STATE[uid]["discount_code"] = code
    STATE[uid]["final_price"] = total_price

    link_info = LINKS.get(choice, {})
    pay_link = link_info.get("discount_link") or link_info.get("url", "リンク未設定")

    await message.answer(f"{msg}\n\nこちらのリンク👇\n{pay_link}\n\n支払い後に『完了』と送ってください。")

# ==========================
# 支払いスクショ → 管理者へ送信
# ==========================
@dp.message(F.photo)
async def handle_payment_photo(message: types.Message):
    uid = message.from_user.id
    state = STATE.get(uid)

    # 在庫追加時
    if state and state.get("stage") == "adding_stock":
        choice = state["type"]
        STOCK[choice].append(message.photo[-1].file_id)
        save_data()
        await message.answer(f"✅ {choice} に在庫追加（{len(STOCK[choice])}枚）")
        STATE.pop(uid, None)
        return

    # 支払い確認時
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

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ 承認", callback_data=f"confirm_{uid}"),
        InlineKeyboardButton(text="❌ 拒否", callback_data=f"deny_{uid}")
    ]])

    await bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=caption, reply_markup=kb)
    await message.answer("🕐 管理者確認中です。")

# ============
# 手動 承認/拒否
# ============
@dp.callback_query(F.data.startswith("confirm_"))
async def confirm_send(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return await callback.answer("権限なし", show_alert=True)
    target_id = int(callback.data.split("_")[1])
    state = STATE.get(target_id)
    if not state:
        return await callback.message.answer("⚠️ ユーザーデータなし")

    choice = state["type"]
    if not STOCK.get(choice):
        await bot.send_message(target_id, "⚠️ 在庫なし。後ほど送信します。")
        return await callback.answer("在庫なし")

    count = state.get("count", 1)
    if len(STOCK[choice]) < count:
        await bot.send_message(target_id, f"⚠️ 在庫が不足しています（{len(STOCK[choice])}枚しか残っていません）。")
        return await callback.answer("在庫不足")

    for i in range(count):
        file_id = STOCK[choice].pop(0)
        await bot.send_photo(target_id, file_id, caption=f"✅ {choice} #{i+1}/{count} を送信しました！")
        await log_purchase(target_id, callback.from_user.full_name, choice, state.get("count", 1), state.get("final_price") or LINKS[choice]["price"], state.get("discount_code"))

    save_data(); auto_backup()
    await bot.send_message(target_id, NOTICE)
    STATE.pop(target_id, None)
    await callback.answer("完了")

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
    if not admin_state or admin_state.get("stage") != "awaiting_reason": 
        return
    target_id = admin_state["target"]
    reason = message.text.strip()
    await bot.send_message(target_id, f"⚠️ 支払い確認できませんでした。\n理由：{reason}\n\n再度『完了』と送ってください。")
    await message.answer("❌ 拒否理由送信完了")
    STATE.pop(message.from_user.id, None)
    STATE.pop(target_id, None)

# ============
# 各種ユーティリティ
# ============
@dp.message(Command("help"))
async def help_cmd(message: types.Message):
    await start_cmd(message)

@dp.message(Command("addstock"))
async def addstock(message: types.Message):
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

@dp.message(Command("stock"))
async def stock_cmd(message: types.Message):
    if not is_admin(message.from_user.id): 
        return await message.answer("権限なし")
    info = "\n".join([f"{k}: {len(v)}枚" for k, v in STOCK.items()])
    await message.answer(f"📦 在庫状況\n{info}")

@dp.message(Command("code"))
async def create_code(message: types.Message):
    if not is_admin(message.from_user.id):
        return await message.answer("権限なし")
    parts = message.text.split()
    if len(parts) < 2:
        return await message.answer("⚙️ 使い方:\n/code 通話可能\n/code データ\n/code 通話可能 1500円off")

    ctype = parts[1]
    if ctype not in STOCK:
        return await message.answer(f"⚠️ 『{ctype}』 は存在しません。")

    discount_value = None
    if len(parts) >= 3:
        raw = parts[2].replace("円", "").replace("OFF", "").replace("off", "")
        if raw.isdigit():
            discount_value = int(raw)
        else:
            return await message.answer("⚠️ 金額指定は『1500円off』のように入力してください。")

    code = "RKTN-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    if discount_value:
        CODES[code] = {"used": False, "type": ctype, "discount_value": discount_value}
        msg = f"🎟️ 金額クーポン発行完了\n<code>{code}</code>\n対象: {ctype}\n💴 割引額: {discount_value:,}円OFF"
    else:
        CODES[code] = {"used": False, "type": ctype}
        msg = f"🎟️ 通常割引コード発行\n<code>{code}</code>\n対象: {ctype}"
    save_data()
    await message.answer(msg, parse_mode="HTML")

@dp.message(Command("addproduct"))
async def add_product(message: types.Message):
    if not is_admin(message.from_user.id):
        return await message.answer("権限なし")
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.answer("⚙️ 使い方: /addproduct <商品名>\n例: /addproduct 1日eSIM（500MB）")
    new_type = parts[1].strip()
    if new_type in STOCK or new_type in LINKS:
        return await message.answer(f"⚠️ 「{new_type}」はすでに登録済みです。")
    STOCK[new_type] = []
    LINKS[new_type] = {"url": "未設定", "price": 0, "discount_link": "未設定", "discount_price": 0}
    save_data()
    await message.answer(
        f"✅ 新しい商品カテゴリ「{new_type}」を追加しました。\n"
        f"🧾 現在の設定:\n"
        f"　価格: 0円\n"
        f"　リンク: 未設定\n"
        f"　割引価格: 0円\n"
        f"　割引リンク: 未設定\n\n"
        f"📸 在庫を追加するには：\n/addstock {new_type}"
    )

@dp.message(Command("codes"))
async def list_codes(message: types.Message):
    if not is_admin(message.from_user.id):
        return await message.answer("権限なし")
    if not CODES:
        return await message.answer("コードなし")
    lines = []
    for k, v in CODES.items():
        status = "✅使用済" if v["used"] else "🟢未使用"
        if "discount_value" in v:
            lines.append(f"{k} | {v['type']} | 💴{v['discount_value']}円OFF | {status}")
        else:
            lines.append(f"{k} | {v['type']} | 通常割引 | {status}")
    await message.answer("🎟️ コード一覧\n" + "\n".join(lines))

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

@dp.callback_query(F.data.startswith("cfg_"))
async def cfg_select(callback: types.CallbackQuery):
    uid = callback.from_user.id
    mode = callback.data.split("_", 1)[1]
    label = "リンク" if "link" in mode else ("価格" if "price" in mode else "設定")
    if not LINKS:
        return await callback.message.answer("⚠️ 商品データが存在しません。")
    buttons = [[InlineKeyboardButton(text=f"{name}", callback_data=f"cfgsel_{mode}_{name}")] for name in LINKS.keys()]
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.answer(f"🛠 どの商品カテゴリの{label}を変更しますか？", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("cfgsel_"))
async def cfgsel_type(callback: types.CallbackQuery):
    uid = callback.from_user.id
    data = callback.data
    parts = data.split("_", 2)
    if len(parts) < 3:
        await callback.message.answer("⚠️ 無効な設定データを受信しました。")
        await callback.answer()
        return
    mode, target = parts[1], parts[2]
    STATE[uid] = {"stage": f"config_{mode}", "target": target}
    if "price" in mode:
        await callback.message.answer(f"💴 新しい価格を入力してください。\n対象: {target}")
    elif "link" in mode:
        await callback.message.answer(f"🔗 新しいリンク(URL)を入力してください。\n対象: {target}")
    else:
        await callback.message.answer("⚠️ 不明な設定モードです。")
    try:
        await callback.answer()
    except:
        pass

@dp.message(Command("backup"))
async def backup_data(message: types.Message):
    if not is_admin(message.from_user.id):
        return await message.answer("権限なし")
    import datetime
    filename = os.path.join(BACKUP_DIR, f"data_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    shutil.copy(DATA_FILE, filename)
    await message.answer(f"💾 バックアップ作成完了:\n<code>{filename}</code>", parse_mode="HTML")

@dp.message(Command("restore"))
async def restore_backup(message: types.Message):
    if not is_admin(message.from_user.id):
        return await message.answer("権限なし")
    files = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith("data_") and f.endswith(".json")], reverse=True)
    if not files:
        return await message.answer("⚠️ バックアップファイルがありません。")
    recent_files = files[:5]
    buttons = [[InlineKeyboardButton(text=f.replace('data_', '').replace('.json', ''), callback_data=f"restore_{f}")] for f in recent_files]
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer("📂 復元したいバックアップを選んでください：", reply_markup=kb)

@dp.callback_query(F.data.startswith("restore_"))
async def confirm_restore(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return await callback.answer("権限なし", show_alert=True)
    filename = callback.data.replace("restore_", "")
    backup_path = os.path.join(BACKUP_DIR, filename)
    if not os.path.exists(backup_path):
        return await callback.message.answer("⚠️ 指定されたバックアップが見つかりません。")
    shutil.copy(backup_path, DATA_FILE)
    global STOCK, LINKS, CODES
    STOCK, LINKS, CODES = load_data()
    await callback.message.answer(f"✅ バックアップを復元しました：\n<code>{filename}</code>", parse_mode="HTML")
    await callback.answer("復元完了")

@dp.message(Command("restore_auto"))
async def restore_auto_backup(message: types.Message):
    if not is_admin(message.from_user.id):
        return await message.answer("権限なし")
    backup_path = os.path.join(BACKUP_DIR, "data_auto.json")
    if not os.path.exists(backup_path):
        return await message.answer("⚠️ 自動バックアップが見つかりません。")
    shutil.copy(backup_path, DATA_FILE)
    global STOCK, LINKS, CODES
    STOCK, LINKS, CODES = load_data()
    await message.answer("✅ 自動バックアップを復元しました。")

@dp.message(Command("status"))
async def status_cmd(message: types.Message):
    if not is_admin(message.from_user.id): 
        return await message.answer("権限なし")
    info = (
        f"📊 Botステータス\n"
        f"在庫: 通話可能={len(STOCK.get('通話可能', []))} / データ={len(STOCK.get('データ', []))}\n"
        f"割引コード数: {len(CODES)}\n"
        f"保存先: {DATA_FILE}\n"
        f"稼働中: ✅ 正常"
    )
    await message.answer(info)

@dp.message(Command("stats"))
async def stats_cmd(message: types.Message):
    if not is_admin(message.from_user.id):
        return await message.answer("権限なし")
    total_codes_used = sum(1 for v in CODES.values() if v["used"])
    text = (
        f"📊 **販売統計レポート**\n\n"
        f"🎟️ 使用済み割引コード: {total_codes_used}件\n"
        f"📦 在庫残数:\n"
        f"　📞 通話可能: {len(STOCK.get('通話可能', []))}枚\n"
        f"　💾 データ: {len(STOCK.get('データ', []))}枚\n"
    )
    await message.answer(text, parse_mode="HTML")

PURCHASE_LOG = []
async def log_purchase(uid, username, choice, count, price, code=None):
    PURCHASE_LOG.append({"uid": uid, "name": username, "type": choice, "count": count, "price": price, "code": code})

@dp.message(Command("history"))
async def show_history(message: types.Message):
    if not is_admin(message.from_user.id):
        return await message.answer("権限なし")
    if not PURCHASE_LOG:
        return await message.answer("📄 購入履歴はまだありません。")
    lines = [
        f"👤 {p['name']} ({p['uid']})\n📦 {p['type']} x{p['count']}枚 | 💴 {p['price']}円" + (f" | 🎟️ {p['code']}" if p['code'] else "")
        for p in PURCHASE_LOG[-10:]
    ]
    await message.answer("🧾 <b>直近の購入履歴（最大10件）</b>\n\n" + "\n\n".join(lines), parse_mode="HTML")

@dp.message(Command("問い合わせ"))
async def inquiry_start(message: types.Message):
    STATE[message.from_user.id] = {"stage": "inquiry_waiting"}
    await message.answer("💬 お問い合わせ内容を入力してください。\n（送信後、管理者に転送されます）")

@dp.message(Command("返信"))
async def reply_to_user(message: types.Message):
    if not is_admin(message.from_user.id):
        return await message.answer("権限なし")
    try:
        parts = message.text.split(maxsplit=2)
        if len(parts) < 3:
            return await message.answer("⚙️ 使い方: /返信 <ユーザーID> <内容>\n例: /返信 5397061486 こんにちは！")
        target_id_str = parts[1].strip()
        reply_text = parts[2].strip()
        if not target_id_str.isdigit():
            return await message.answer("⚠️ ユーザーIDは数字で指定してください。")
        target_id = int(target_id_str)
        await bot.send_message(target_id, f"💬 管理者からのお知らせ:\n\n{reply_text}", parse_mode="HTML")
        await message.answer(f"✅ ユーザー {target_id} に返信を送信しました。")
    except Exception as e:
        await message.answer(f"⚠️ 返信に失敗しました。\nエラー内容: {e}")

# ユーザー記録 & 設定入力
def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()

def save_users(users):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(list(users), f, ensure_ascii=False, indent=2)

USERS = load_users()

@dp.message(F.text)
async def handle_text_input(message: types.Message):
    uid = message.from_user.id
    text = message.text.strip()
    state = STATE.get(uid)

    # 管理者設定（価格/リンク）
    if is_admin(uid) and state and "config_" in state.get("stage", ""):
        stage = state["stage"]; target = state["target"]; new_value = text
        LINKS.setdefault(target, {"url": "未設定", "price": 0, "discount_link": "未設定", "discount_price": 0})

        if "price" in stage and "link" not in stage:
            if not new_value.isdigit():
                return await message.answer("⚠️ 数値を入力してください（例: 1500）")
            val = int(new_value)
            if "discount" in stage:
                LINKS[target]["discount_price"] = val; msg = f"💴 {target} の割引価格を {val} 円に更新しました。"
            else:
                LINKS[target]["price"] = val; msg = f"💴 {target} の通常価格を {val} 円に更新しました。"
        elif "link" in stage:
            if not (new_value.startswith("http://") or new_value.startswith("https://")):
                return await message.answer("⚠️ 有効なURLを入力してください。")
            if "discount" in stage:
                LINKS[target]["discount_link"] = new_value; msg = f"🔗 {target} の割引リンクを更新しました。"
            else:
                LINKS[target]["url"] = new_value; msg = f"🔗 {target} の通常リンクを更新しました。"
        else:
            return await message.answer("⚠️ 不明な設定モードです。")

        save_data()
        STATE.pop(uid, None)
        return await message.answer(f"✅ {msg}")

    if state and state.get("stage") == "inquiry_waiting":
        await bot.send_message(ADMIN_ID, f"📩 新しいお問い合わせ\n👤 {message.from_user.full_name}\n🆔 {uid}\n\n📝 内容:\n{text}")
        await message.answer("✅ お問い合わせを送信しました。返信までお待ちください。")
        STATE.pop(uid, None)
        return

    # ユーザー登録
    if uid not in USERS:
        USERS.add(uid); save_users(USERS)
        print(f"👤 新規ユーザー登録: {uid} ({message.from_user.full_name})")

# =========================
# 💳 Stripe Checkout 連携
# =========================
try:
    import stripe
    from aiohttp import web
except Exception as e:
    print("⚠️ stripe / aiohttp が未インストールです。requirements.txt に 'stripe' と 'aiohttp' を追加してください。", e)
    stripe = None
    web = None

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", CONFIG.get("STRIPE_SECRET_KEY", ""))
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", CONFIG.get("STRIPE_WEBHOOK_SECRET", ""))
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", CONFIG.get("PUBLIC_BASE_URL", "https://esim.zeabur.app"))

if stripe and STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY
else:
    print("⚠️ Stripeの秘密鍵(STRIPE_SECRET_KEY)が未設定です。カード決済機能は無効。")

SESS_FILE = os.path.join(DATA_DIR, "sessions.json")
def load_sessions():
    try:
        if os.path.exists(SESS_FILE):
            with open(SESS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"⚠️ セッション読み込み失敗: {e}")
    return {}

def save_sessions():
    try:
        with open(SESS_FILE, "w", encoding="utf-8") as f:
            json.dump(SESSIONS, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ セッション保存失敗: {e}")

SESSIONS = load_sessions()

async def _send_card_pay_offer(chat_id: int, choice: str, count: int, amount: int):
    """合計金額表示後にカード決済ボタンを提示"""
    try:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="💳 カードで支払う（Stripe）", callback_data=f"ccpay_{choice}_{count}_{amount}")
        ]])
        await bot.send_message(chat_id, "💳 クレジットカード決済をご希望の方はこちら👇", reply_markup=kb)
    except Exception as e:
        print(f"⚠️ _send_card_pay_offer error: {e}")

@dp.callback_query(F.data.startswith("ccpay_"))
async def create_checkout(callback: types.CallbackQuery):
    if not (stripe and STRIPE_SECRET_KEY):
        await callback.message.answer("⚠️ カード決済は現在利用できません（設定未完了）。")
        return await callback.answer()

    try:
        _, choice, count_str, amount_str = callback.data.split("_", 3)
        count = int(count_str); amount = int(amount_str)
        uid = callback.from_user.id

        success_url = f"{PUBLIC_BASE_URL}/stripe/success?session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = f"{PUBLIC_BASE_URL}/stripe/cancel"

        session = stripe.checkout.Session.create(
            mode="payment",
            success_url=success_url,
            cancel_url=cancel_url,
            line_items=[{
                "price_data": {
                    "currency": "jpy",
                    "product_data": {"name": f"{choice} x{count}"},
                    "unit_amount": amount * 100
                },
                "quantity": 1
            }],
            metadata={
                "tg_uid": str(uid),
                "choice": choice,
                "count": str(count),
                "amount": str(amount)
            }
        )

        SESSIONS[session.id] = {"uid": uid, "choice": choice, "count": count, "amount": amount}
        save_sessions()

        await callback.message.answer("✅ カード決済ページを開いてお支払いください👇\n" + session.url)
        await callback.answer()

    except Exception as e:
        await callback.message.answer(f"⚠️ セッション作成に失敗しました: {e}")
        try:
            await callback.answer("エラー")
        except:
            pass

# ------ Webhook / 成功/キャンセル エンドポイント ------
async def stripe_webhook(request):
    try:
        payload = await request.read()
        sig = request.headers.get("Stripe-Signature", "")
        if STRIPE_WEBHOOK_SECRET and stripe:
            try:
                event = stripe.Webhook.construct_event(payload=payload, sig_header=sig, secret=STRIPE_WEBHOOK_SECRET)
            except Exception as e:
                print(f"⚠️ Webhook検証失敗: {e}")
                return web.Response(status=400, text="Bad signature")
        else:
            event = json.loads(payload.decode("utf-8"))

        etype = event.get("type")
        if etype == "checkout.session.completed":
            session = event["data"]["object"]
            session_id = session["id"]
            meta = session.get("metadata", {})

            info = SESSIONS.get(session_id) or {
                "uid": int(meta.get("tg_uid", 0)),
                "choice": meta.get("choice"),
                "count": int(meta.get("count", "1")),
                "amount": int(meta.get("amount", "0"))
            }

            uid = info.get("uid"); choice = info.get("choice")
            count = int(info.get("count", 1) or 1)
            amount = int(info.get("amount", 0) or 0)

            if not uid or not choice:
                print(f"⚠️ セッション情報不備: {session_id}")
                return web.Response(text="ok")

            # 管理者へ決済通知（何枚・いくら・誰）
            try:
                await bot.send_message(
                    ADMIN_ID,
                    ("💳 Stripe 決済完了通知\n"
                     f"🆔 Telegram ID: {uid}\n"
                     f"📦 タイプ: {choice}\n"
                     f"🧾 枚数: {count}\n"
                     f"💴 支払金額: {amount}円\n"
                     f"🪪 セッションID: {session_id}")
                )
            except Exception as e:
                print("⚠️ 管理者通知失敗:", e)

            # 在庫チェック & 自動送付
            try:
                if len(STOCK.get(choice, [])) < count:
                    await bot.send_message(uid, "⚠️ 決済完了しましたが在庫不足のため、後ほどお送りいたします。")
                else:
                    for i in range(count):
                        file_id = STOCK[choice].pop(0)
                        await bot.send_photo(uid, file_id, caption=f"✅ {choice} #{i+1}/{count} を送信しました！（カード決済）")
                    save_data(); auto_backup()
                    await bot.send_message(uid, NOTICE)
                    try:
                        await log_purchase(uid, "Stripe-Checkout", choice, count, amount, code=None)
                    except Exception:
                        pass
            except Exception as e:
                print(f"❌ 自動承認・送付エラー: {e}")

            if session_id in SESSIONS:
                SESSIONS.pop(session_id, None)
                save_sessions()

        return web.Response(text="ok")

    except Exception as e:
        print(f"❌ Webhook処理失敗: {e}")
        return web.Response(status=400, text="bad request")

async def stripe_success(request):
    return web.Response(text="✅ 決済が完了しました。TelegramにeSIMが届きます。")

async def stripe_cancel(request):
    return web.Response(text="❌ 決済がキャンセルされました。再度お試しください。")

async def start_web_app():
    if not web:
        print("⚠️ aiohttp が無いためWebhookサーバを起動できません。requirements.txt に 'aiohttp' を追加してください。")
        return
    app = web.Application()
    app.router.add_post("/stripe/webhook", stripe_webhook)
    app.router.add_get("/stripe/success", stripe_success)
    app.router.add_get("/stripe/cancel", stripe_cancel)

    port = int(os.getenv("PORT", "8080"))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"🌐 Web server started at http://0.0.0.0:{port}")

# ==============
# アプリ起動部
# ==============
async def telegram_polling():
    print("🤖 eSIM自販機Bot 起動中...")
    await dp.start_polling(bot)

async def main():
    # Telegram と Webhook を並列起動
    web_task = asyncio.create_task(start_web_app())
    tg_task = asyncio.create_task(telegram_polling())
    await asyncio.gather(web_task, tg_task)

if __name__ == "__main__":
    asyncio.run(main())
