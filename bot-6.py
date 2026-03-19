"""
U-Gift Bot — To'liq professional bot
Fragment API dan narxlar avtomatik olinadi
Narxlar buyurtma vaqtida qotib qoladi (price lock)
TON → UZS avtomatik konvertatsiya
"""

import asyncio
import logging
import json
import os
import time
import aiohttp
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton
)
from dotenv import load_dotenv

load_dotenv()

# ═══════════════════════════════════════════
# SOZLAMALAR
# ═══════════════════════════════════════════
BOT_TOKEN      = os.getenv("BOT_TOKEN")
SUPER_ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
TON_API_KEY    = os.getenv("TON_API_KEY", "")
FRAGMENT_COOKIES = os.getenv("FRAGMENT_COOKIES", "")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher(storage=MemoryStorage())

# ═══════════════════════════════════════════
# NARX TIZIMI (PRICE ENGINE)
# ═══════════════════════════════════════════
# Narxlar keshi — har 30 daqiqada yangilanadi
PRICE_CACHE = {
    "ton_usd"    : 0.0,
    "usd_uzs"    : 0.0,
    "ton_uzs"    : 0.0,
    "stars_ton"  : 0.0,   # 1 Star = ? TON
    "premium"    : {       # Premium narxlari TON da
        3 : 0.0,
        6 : 0.0,
        12: 0.0,
    },
    "last_update": 0,
    "updating"   : False,
}

CACHE_TTL = 30 * 60  # 30 daqiqa

async def fetch_ton_rate() -> tuple[float, float]:
    """1 TON = ? USD va 1 USD = ? UZS"""
    async with aiohttp.ClientSession() as s:
        # TON/USD — CoinGecko
        async with s.get(
            "https://api.coingecko.com/api/v3/simple/price"
            "?ids=the-open-network&vs_currencies=usd",
            timeout=aiohttp.ClientTimeout(total=8)
        ) as r:
            d = await r.json()
            ton_usd = float(d["the-open-network"]["usd"])

        # USD/UZS — O'zbekiston Markaziy Banki
        async with s.get(
            "https://cbu.uz/uz/arkhiv-kursov-valyut/json/USD/",
            timeout=aiohttp.ClientTimeout(total=8)
        ) as r:
            d = await r.json()
            usd_uzs = float(d[0]["Rate"])

    return ton_usd, usd_uzs

async def fetch_fragment_prices() -> dict:
    """Fragment API dan haqiqiy narxlarni olish"""
    prices = {"stars_ton": 0.0, "premium": {3: 0.0, 6: 0.0, 12: 0.0}}
    try:
        from FragmentAPI import SyncFragmentAPI
        api = SyncFragmentAPI(
            cookies=FRAGMENT_COOKIES,
            wallet_api_key=TON_API_KEY
        )
        # Stars narxi
        try:
            stars_info = api.get_stars_price(50)
            if stars_info and hasattr(stars_info, 'ton'):
                prices["stars_ton"] = float(stars_info.ton) / 50  # 1 Star = ? TON
                log.info(f"Stars narxi: 50 Stars = {stars_info.ton} TON")
        except Exception as e:
            log.warning(f"Stars narxi olinmadi: {e}")
            prices["stars_ton"] = 0.01  # fallback: 1 Star ≈ 0.01 TON

        # Premium narxlari
        for months in [3, 6, 12]:
            try:
                prem_info = api.get_premium_price(months)
                if prem_info and hasattr(prem_info, 'ton'):
                    prices["premium"][months] = float(prem_info.ton)
                    log.info(f"Premium {months}oy: {prem_info.ton} TON")
            except Exception as e:
                log.warning(f"Premium {months}oy narxi olinmadi: {e}")
                # Fallback narxlar
                fallback = {3: 3.75, 6: 7.50, 12: 15.00}
                prices["premium"][months] = fallback[months]

    except Exception as e:
        log.error(f"Fragment API narx xatosi: {e}")
        # Fallback
        prices["stars_ton"] = 0.01
        prices["premium"] = {3: 3.75, 6: 7.50, 12: 15.00}

    return prices

async def update_prices(force: bool = False):
    """Narxlarni yangilash"""
    now = time.time()
    if PRICE_CACHE["updating"]:
        return
    if not force and now - PRICE_CACHE["last_update"] < CACHE_TTL:
        return
    if PRICE_CACHE["ton_uzs"] > 0 and not force and now - PRICE_CACHE["last_update"] < CACHE_TTL:
        return

    PRICE_CACHE["updating"] = True
    try:
        # TON kursi
        ton_usd, usd_uzs = await fetch_ton_rate()
        PRICE_CACHE["ton_usd"]  = ton_usd
        PRICE_CACHE["usd_uzs"]  = usd_uzs
        PRICE_CACHE["ton_uzs"]  = ton_usd * usd_uzs

        # Fragment narxlari
        frag = await fetch_fragment_prices()
        PRICE_CACHE["stars_ton"]  = frag["stars_ton"]
        PRICE_CACHE["premium"]    = frag["premium"]
        PRICE_CACHE["last_update"] = now

        log.info(
            f"Narxlar yangilandi: "
            f"1 TON = ${ton_usd:.2f} = {int(ton_usd * usd_uzs):,} UZS | "
            f"1 Star = {frag['stars_ton']:.4f} TON"
        )
    except Exception as e:
        log.error(f"Narx yangilashda xato: {e}")
        if PRICE_CACHE["ton_uzs"] == 0:
            PRICE_CACHE["ton_usd"]  = 3.5
            PRICE_CACHE["usd_uzs"]  = 12800.0
            PRICE_CACHE["ton_uzs"]  = 44800.0
            PRICE_CACHE["stars_ton"] = 0.01
            PRICE_CACHE["premium"]   = {3: 3.75, 6: 7.50, 12: 15.00}
    finally:
        PRICE_CACHE["updating"] = False

def ton_to_uzs_now(ton: float) -> int:
    """TON ni hozirgi kurs bilan UZS ga o'tkazadi (markup bilan)"""
    d = db()
    markup = d["settings"]["markup"]
    rate   = PRICE_CACHE["ton_uzs"]
    if rate == 0:
        rate = 44800.0
    return round(ton * rate * (1 + markup / 100))

def get_stars_price_uzs(count: int) -> dict:
    """Stars narxini hozirgi kurs bilan qaytaradi"""
    stars_ton = PRICE_CACHE["stars_ton"]
    if stars_ton == 0:
        stars_ton = 0.01
    ton   = count * stars_ton
    uzs   = ton_to_uzs_now(ton)
    return {
        "count"    : count,
        "ton"      : round(ton, 4),
        "uzs"      : uzs,
        "rate_ton" : stars_ton,
        "rate_uzs" : PRICE_CACHE["ton_uzs"],
        "locked_at": time.time(),
    }

def get_premium_price_uzs(months: int) -> dict:
    """Premium narxini hozirgi kurs bilan qaytaradi"""
    ton = PRICE_CACHE["premium"].get(months, 3.75)
    if ton == 0:
        ton = {3: 3.75, 6: 7.50, 12: 15.00}.get(months, 3.75)
    uzs = ton_to_uzs_now(ton)
    return {
        "months"   : months,
        "ton"      : ton,
        "uzs"      : uzs,
        "rate_uzs" : PRICE_CACHE["ton_uzs"],
        "locked_at": time.time(),
    }

async def price_updater_loop():
    """Har 30 daqiqada narxlarni yangilaydi"""
    while True:
        try:
            await update_prices(force=True)
        except Exception as e:
            log.error(f"Price updater: {e}")
        await asyncio.sleep(CACHE_TTL)

# ═══════════════════════════════════════════
# DATABASE
# ═══════════════════════════════════════════
DB_FILE = "database.json"

def db() -> dict:
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "users": {}, "orders": [], "admins": {}, "promo_codes": {},
        "settings": {
            "markup": 20,
            "min_stars": 50,
            "bot_active": True,
            "referral_active": False,
            "promo_active": False,
            "referral_bonus": 5000,
            "cards": [],
            "required_channels": [],
            "logs_channel": None,
            "order_timeout_min": 15,
        }
    }

def sdb(data: dict):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_user(uid) -> dict:
    return db()["users"].get(str(uid), {})

def set_user(uid, data: dict):
    d = db()
    if str(uid) not in d["users"]:
        d["users"][str(uid)] = {}
    d["users"][str(uid)].update(data)
    sdb(d)

def is_admin(uid: int) -> bool:
    return uid == SUPER_ADMIN_ID or str(uid) in db().get("admins", {})

def is_super(uid: int) -> bool:
    return uid == SUPER_ADMIN_ID

def fmt(n) -> str:
    return f"{int(n):,}".replace(",", " ")

def fmt_ton(n: float) -> str:
    return f"{n:.4f}".rstrip("0").rstrip(".")

# ═══════════════════════════════════════════
# TILLAR
# ═══════════════════════════════════════════
L = {
    "uz": {
        "welcome": (
            "👋 <b>U-Gift Bot ga xush kelibsiz!</b>\n\n"
            "✨ Telegram Premium, Stars, Gifts va NFT yuborish xizmati.\n\n"
            "💡 Xizmat tanlang:"
        ),
        "premium": "⭐ Premium Gift",
        "stars"  : "🌟 Stars",
        "gifts"  : "🎁 Gifts",
        "nft"    : "🖼 NFT",
        "balance": "💰 Balans",
        "history": "📋 Tarix",
        "topup"  : "➕ Hisob to'ldirish",
        "referral": "👥 Referral",
        "promo"  : "🎁 Promo kod",
        "settings": "⚙️ Sozlamalar",
        "cancel" : "❌ Bekor",
        "self"   : "👤 O'zimga",
        "other"  : "👥 Boshqaga",
    },
    "ru": {
        "welcome": (
            "👋 <b>Добро пожаловать в U-Gift Bot!</b>\n\n"
            "✨ Сервис отправки Telegram Premium, Stars, Gifts и NFT.\n\n"
            "💡 Выберите услугу:"
        ),
        "premium": "⭐ Premium Gift",
        "stars"  : "🌟 Stars",
        "gifts"  : "🎁 Gifts",
        "nft"    : "🖼 NFT",
        "balance": "💰 Баланс",
        "history": "📋 История",
        "topup"  : "➕ Пополнить",
        "referral": "👥 Реферал",
        "promo"  : "🎁 Промо код",
        "settings": "⚙️ Настройки",
        "cancel" : "❌ Отмена",
        "self"   : "👤 Себе",
        "other"  : "👥 Другому",
    },
    "en": {
        "welcome": (
            "👋 <b>Welcome to U-Gift Bot!</b>\n\n"
            "✨ Telegram Premium, Stars, Gifts and NFT sending service.\n\n"
            "💡 Choose a service:"
        ),
        "premium": "⭐ Premium Gift",
        "stars"  : "🌟 Stars",
        "gifts"  : "🎁 Gifts",
        "nft"    : "🖼 NFT",
        "balance": "💰 Balance",
        "history": "📋 History",
        "topup"  : "➕ Top up",
        "referral": "👥 Referral",
        "promo"  : "🎁 Promo code",
        "settings": "⚙️ Settings",
        "cancel" : "❌ Cancel",
        "self"   : "👤 Myself",
        "other"  : "👥 Someone else",
    }
}

def lang(uid) -> str:
    return get_user(uid).get("lang", "uz")

def tx(uid, key: str) -> str:
    return L[lang(uid)].get(key, L["uz"].get(key, key))

# ═══════════════════════════════════════════
# STATES
# ═══════════════════════════════════════════
class Order(StatesGroup):
    username        = State()
    stars_amount    = State()
    nft_link        = State()
    confirm         = State()
    promo_input     = State()

class Topup(StatesGroup):
    amount  = State()
    receipt = State()

class Admin(StatesGroup):
    card           = State()
    markup         = State()
    min_stars      = State()
    channel        = State()
    logs           = State()
    broadcast      = State()
    promo_code     = State()
    promo_discount = State()
    promo_limit    = State()
    admin_id       = State()
    ban_id         = State()
    ref_bonus      = State()

# ═══════════════════════════════════════════
# KLAVIATURA
# ═══════════════════════════════════════════
def main_kb(uid) -> ReplyKeyboardMarkup:
    d = db(); s = d["settings"]; l = lang(uid)
    rows = [
        [KeyboardButton(text=L[l]["premium"]), KeyboardButton(text=L[l]["stars"])],
        [KeyboardButton(text=L[l]["gifts"]),   KeyboardButton(text=L[l]["nft"])],
        [KeyboardButton(text=L[l]["balance"]), KeyboardButton(text=L[l]["history"])],
        [KeyboardButton(text=L[l]["topup"])],
    ]
    extra = []
    if s.get("referral_active"):
        extra.append(KeyboardButton(text=L[l]["referral"]))
    if s.get("promo_active"):
        extra.append(KeyboardButton(text=L[l]["promo"]))
    if extra:
        rows.append(extra)
    rows.append([KeyboardButton(text=L[l]["settings"])])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

def cancel_kb(uid) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=tx(uid, "cancel"))]],
        resize_keyboard=True
    )

def back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔙 Orqaga", callback_data="adm_main")
    ]])

# ═══════════════════════════════════════════
# YORDAMCHI FUNKSIYALAR
# ═══════════════════════════════════════════
async def send_log(text: str):
    d = db()
    ch = d["settings"].get("logs_channel")
    if ch:
        try:
            await bot.send_message(ch, text, parse_mode="HTML")
        except:
            pass

async def notify_admins(text: str, kb=None, photo=None):
    d = db()
    admins = [SUPER_ADMIN_ID] + [int(a) for a in d.get("admins", {}).keys()]
    for aid in admins:
        try:
            if photo:
                await bot.send_photo(aid, photo, caption=text, reply_markup=kb, parse_mode="HTML")
            else:
                await bot.send_message(aid, text, reply_markup=kb, parse_mode="HTML")
        except:
            pass

async def check_sub(uid: int) -> bool:
    d = db()
    for ch in d["settings"]["required_channels"]:
        try:
            m = await bot.get_chat_member(ch, uid)
            if m.status in ["left", "kicked"]:
                return False
        except:
            pass
    return True

def price_info_text() -> str:
    """Joriy kurs ma'lumoti"""
    if PRICE_CACHE["ton_uzs"] == 0:
        return "⏳ Narxlar yuklanmoqda..."
    last = datetime.fromtimestamp(PRICE_CACHE["last_update"]).strftime("%H:%M")
    return (
        f"<code>━━━━━━━━━━━━━━━━</code>\n"
        f"💎 1 TON = <b>{fmt(PRICE_CACHE['ton_uzs'])} so'm</b>\n"
        f"💵 1 USD = <b>{fmt(PRICE_CACHE['usd_uzs'])} so'm</b>\n"
        f"🕐 Oxirgi yangilanish: <b>{last}</b>\n"
        f"<code>━━━━━━━━━━━━━━━━</code>"
    )

# ═══════════════════════════════════════════
# START
# ═══════════════════════════════════════════
@dp.message(Command("start"))
async def cmd_start(msg: types.Message, state: FSMContext):
    await state.clear()
    d = db(); uid = str(msg.from_user.id)

    if not d["settings"]["bot_active"] and not is_admin(msg.from_user.id):
        await msg.answer("🔧 Bot hozirda texnik ishlar uchun o'chirilgan.")
        return

    if uid not in d["users"]:
        d["users"][uid] = {
            "lang": "uz", "balance": 0, "orders": [],
            "referrals": 0, "ref_earned": 0,
            "joined": datetime.now().isoformat(),
            "banned": False, "promo_used": []
        }
        args = msg.text.split()
        if len(args) > 1 and args[1].startswith("ref_"):
            ref_id = args[1][4:]
            if ref_id in d["users"] and d["settings"].get("referral_active"):
                bonus = d["settings"]["referral_bonus"]
                d["users"][ref_id]["balance"] = d["users"][ref_id].get("balance", 0) + bonus
                d["users"][ref_id]["referrals"] = d["users"][ref_id].get("referrals", 0) + 1
                d["users"][ref_id]["ref_earned"] = d["users"][ref_id].get("ref_earned", 0) + bonus
                try:
                    await bot.send_message(
                        int(ref_id),
                        f"🎉 Yangi referral! +{fmt(bonus)} so'm!\n"
                        f"💰 Balans: {fmt(d['users'][ref_id]['balance'])} so'm"
                    )
                except:
                    pass
        sdb(d)

    d = db()
    if d["users"][uid].get("banned"):
        await msg.answer("🚫 Siz botdan bloklangansiz.")
        return

    args = msg.text.split()
    if len(args) > 1 and args[1] == "admin" and is_admin(msg.from_user.id):
        await cmd_admin(msg, state); return
    if len(args) > 1 and args[1] == "topup":
        await cmd_topup(msg, state); return

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🇺🇿 O'zbek", callback_data="lang_uz"),
        InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru"),
        InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en"),
    ]])
    await msg.answer("🌐 Tilni tanlang / Выберите язык / Choose language:", reply_markup=kb)

@dp.callback_query(F.data.startswith("lang_"))
async def cb_lang(cb: types.CallbackQuery):
    l = cb.data[5:]
    set_user(cb.from_user.id, {"lang": l})
    if not await check_sub(cb.from_user.id):
        d = db(); chs = d["settings"]["required_channels"]
        btns = [[InlineKeyboardButton(text=f"📢 {ch}", url=f"https://t.me/{ch.lstrip('@')}")] for ch in chs]
        btns.append([InlineKeyboardButton(text="✅ Tekshirish", callback_data="check_sub")])
        await cb.message.edit_text("📢 Kanallarga obuna bo'ling:", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))
        return
    await cb.message.delete()
    await cb.message.answer(L[l]["welcome"], parse_mode="HTML", reply_markup=main_kb(cb.from_user.id))

@dp.callback_query(F.data == "check_sub")
async def cb_check_sub(cb: types.CallbackQuery):
    if await check_sub(cb.from_user.id):
        l = lang(cb.from_user.id)
        await cb.message.delete()
        await cb.message.answer(L[l]["welcome"], parse_mode="HTML", reply_markup=main_kb(cb.from_user.id))
    else:
        await cb.answer("❌ Hali obuna bo'lmadingiz!", show_alert=True)

# ═══════════════════════════════════════════
# BALANS
# ═══════════════════════════════════════════
@dp.message(F.text.in_(["💰 Balans", "💰 Баланс", "💰 Balance"]))
async def cmd_balance(msg: types.Message):
    u = get_user(msg.from_user.id)
    bal = u.get("balance", 0)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="➕ Hisob to'ldirish", callback_data="go_topup")
    ]])
    await msg.answer(
        f"💰 <b>Balansingiz</b>\n\n"
        f"<code>━━━━━━━━━━━━━━━━</code>\n"
        f"💵 Joriy balans: <b>{fmt(bal)} so'm</b>\n"
        f"<code>━━━━━━━━━━━━━━━━</code>",
        parse_mode="HTML", reply_markup=kb
    )

@dp.callback_query(F.data == "go_topup")
async def go_topup(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.delete()
    await cmd_topup(cb.message, state)

# ═══════════════════════════════════════════
# HISOB TO'LDIRISH
# ═══════════════════════════════════════════
@dp.message(F.text.in_(["➕ Hisob to'ldirish", "➕ Пополнить", "➕ Top up"]))
async def cmd_topup(msg: types.Message, state: FSMContext):
    d = db()
    if not d["settings"]["cards"]:
        await msg.answer("❌ Hozirda to'lov qabul qilinmayapti.")
        return
    await msg.answer(
        "💰 <b>Hisob to'ldirish</b>\n\n"
        "Qancha so'm kiritmoqchisiz?\n"
        "<i>Minimum: 5 000 so'm</i>",
        parse_mode="HTML", reply_markup=cancel_kb(msg.from_user.id)
    )
    await state.set_state(Topup.amount)

@dp.message(Topup.amount)
async def topup_amount(msg: types.Message, state: FSMContext):
    if msg.text in ["❌ Bekor", "❌ Отмена", "❌ Cancel"]:
        await state.clear()
        await msg.answer("🏠", reply_markup=main_kb(msg.from_user.id))
        return
    try:
        amount = int(msg.text.replace(" ", "").replace(",", ""))
        if amount < 5000:
            await msg.answer("❌ Minimum 5 000 so'm!")
            return
        d = db()
        cards = "\n".join([f"💳 <code>{c}</code>" for c in d["settings"]["cards"]])
        await state.update_data(amount=amount)
        await msg.answer(
            f"💳 <b>To'lov kartasi:</b>\n\n{cards}\n\n"
            f"<code>━━━━━━━━━━━━━━━━</code>\n"
            f"💰 To'lov miqdori: <b>{fmt(amount)} so'm</b>\n"
            f"<code>━━━━━━━━━━━━━━━━</code>\n\n"
            f"✅ To'lovdan so'ng <b>chek (screenshot)</b> yuboring:",
            parse_mode="HTML", reply_markup=cancel_kb(msg.from_user.id)
        )
        await state.set_state(Topup.receipt)
    except:
        await msg.answer("❌ Faqat raqam kiriting!")

@dp.message(Topup.receipt)
async def topup_receipt(msg: types.Message, state: FSMContext):
    if msg.text in ["❌ Bekor", "❌ Отмена", "❌ Cancel"]:
        await state.clear()
        await msg.answer("🏠", reply_markup=main_kb(msg.from_user.id))
        return
    if not msg.photo:
        await msg.answer("📸 Chek rasmini yuboring!")
        return
    data = await state.get_data()
    amount = data["amount"]
    uid = msg.from_user.id
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"tok_{uid}_{amount}"),
        InlineKeyboardButton(text="❌ Rad etish", callback_data=f"tno_{uid}"),
    ]])
    await notify_admins(
        f"💳 <b>Balans to'ldirish</b>\n\n"
        f"👤 {msg.from_user.full_name}\n"
        f"🆔 <code>{uid}</code>\n"
        f"📱 @{msg.from_user.username or 'yoq'}\n"
        f"💰 <b>{fmt(amount)} so'm</b>",
        kb=kb, photo=msg.photo[-1].file_id
    )
    await msg.answer(
        "✅ <b>Chekingiz yuborildi!</b>\n\n⏳ Admin tasdiqlaguncha kuting...",
        parse_mode="HTML", reply_markup=main_kb(msg.from_user.id)
    )
    await state.clear()

@dp.callback_query(F.data.startswith("tok_"))
async def topup_ok(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): return
    parts = cb.data.split("_")
    uid, amount = int(parts[1]), int(parts[2])
    d = db(); suid = str(uid)
    if suid in d["users"]:
        d["users"][suid]["balance"] = d["users"][suid].get("balance", 0) + amount
        sdb(d)
    bal = d["users"].get(suid, {}).get("balance", 0)
    await bot.send_message(uid,
        f"✅ <b>Balansingiz to'ldirildi!</b>\n\n"
        f"➕ Qo'shildi: <b>{fmt(amount)} so'm</b>\n"
        f"💰 Joriy balans: <b>{fmt(bal)} so'm</b>",
        parse_mode="HTML"
    )
    await cb.message.edit_caption(
        caption=cb.message.caption + f"\n\n✅ <b>Tasdiqlandi</b> — {cb.from_user.full_name}",
        parse_mode="HTML"
    )
    await send_log(f"✅ Balans +{fmt(amount)} so'm | ID: {uid}")

@dp.callback_query(F.data.startswith("tno_"))
async def topup_no(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): return
    uid = int(cb.data.split("_")[1])
    await bot.send_message(uid, "❌ To'lovingiz tasdiqlanmadi.")
    await cb.message.edit_caption(
        caption=cb.message.caption + f"\n\n❌ <b>Rad etildi</b> — {cb.from_user.full_name}",
        parse_mode="HTML"
    )

# ═══════════════════════════════════════════
# KIMGA YUBORISH
# ═══════════════════════════════════════════
def recipient_kb(uid) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=tx(uid, "self"), callback_data="rec_self"),
        InlineKeyboardButton(text=tx(uid, "other"), callback_data="rec_other"),
    ]])

# ═══════════════════════════════════════════
# PREMIUM GIFT
# ═══════════════════════════════════════════
@dp.message(F.text.in_(["⭐ Premium Gift"]))
async def cmd_premium(msg: types.Message, state: FSMContext):
    # Narxlar hozirgi kurs bilan (price lock)
    p = {m: get_premium_price_uzs(m) for m in [3, 6, 12]}

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"3 oy — {fmt(p[3]['uzs'])} so'm",
            callback_data="pm_3"
        )],
        [InlineKeyboardButton(
            text=f"6 oy — {fmt(p[6]['uzs'])} so'm 🔥",
            callback_data="pm_6"
        )],
        [InlineKeyboardButton(
            text=f"12 oy — {fmt(p[12]['uzs'])} so'm",
            callback_data="pm_12"
        )],
    ])

    await msg.answer(
        f"⭐ <b>Telegram Premium Gift</b>\n\n"
        f"{price_info_text()}\n"
        f"Muddatni tanlang:\n\n"
        f"<i>⚠️ Narx {db()['settings'].get('order_timeout_min', 15)} daqiqa davomida qotib qoladi</i>",
        parse_mode="HTML", reply_markup=kb
    )
    await state.update_data(service="premium", price_data=p)

@dp.callback_query(F.data.startswith("pm_"))
async def cb_premium_months(cb: types.CallbackQuery, state: FSMContext):
    months = int(cb.data[3:])
    data = await state.get_data()

    # Agar narx ma'lumoti yo'q bo'lsa qayta olish
    price_data = data.get("price_data", {})
    if not price_data or months not in price_data:
        pd = get_premium_price_uzs(months)
    else:
        pd = price_data[months]

    await state.update_data(
        months=months,
        price=pd["uzs"],
        ton=pd["ton"],
        locked_at=pd["locked_at"],
        locked_rate=pd["rate_uzs"]
    )
    await cb.message.delete()
    await cb.message.answer(
        f"⭐ <b>Premium {months} oy</b>\n"
        f"💎 {fmt_ton(pd['ton'])} TON = <b>{fmt(pd['uzs'])} so'm</b>\n\n"
        f"Kimga yuboramiz?",
        parse_mode="HTML", reply_markup=recipient_kb(cb.from_user.id)
    )

# ═══════════════════════════════════════════
# STARS
# ═══════════════════════════════════════════
@dp.message(F.text.in_(["🌟 Stars"]))
async def cmd_stars(msg: types.Message, state: FSMContext):
    await state.update_data(service="stars")

    # Narxlar hozirgi kurs bilan
    counts = [50, 100, 250, 500, 1000]
    prices = {c: get_stars_price_uzs(c) for c in counts}

    buttons = []
    row = []
    for i, c in enumerate(counts):
        row.append(InlineKeyboardButton(
            text=f"⭐{c}\n{fmt(prices[c]['uzs'])} so'm",
            callback_data=f"st_{c}"
        ))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="✏️ Boshqa miqdor", callback_data="st_custom")])

    await msg.answer(
        f"🌟 <b>Telegram Stars</b>\n\n"
        f"{price_info_text()}\n"
        f"Miqdorni tanlang:\n\n"
        f"<i>⚠️ Narx {db()['settings'].get('order_timeout_min', 15)} daqiqa davomida qotib qoladi</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.update_data(price_data=prices)

@dp.callback_query(F.data.startswith("st_"))
async def cb_stars_select(cb: types.CallbackQuery, state: FSMContext):
    val = cb.data[3:]
    data = await state.get_data()

    if val == "custom":
        d = db()
        min_s = d["settings"]["min_stars"]
        await cb.message.edit_text(
            f"🌟 Nechta Stars?\n\n"
            f"<i>Minimum: {min_s} | Maksimum: 100 000</i>\n\n"
            f"{price_info_text()}",
            parse_mode="HTML"
        )
        await state.set_state(Order.stars_amount)
        return

    stars = int(val)
    price_data = data.get("price_data", {})
    if stars in price_data:
        pd = price_data[stars]
    else:
        pd = get_stars_price_uzs(stars)

    await state.update_data(
        stars=stars,
        price=pd["uzs"],
        ton=pd["ton"],
        locked_at=pd["locked_at"],
        locked_rate=pd["rate_uzs"]
    )
    await cb.message.delete()
    await cb.message.answer(
        f"🌟 <b>{stars} Stars</b>\n"
        f"💎 {fmt_ton(pd['ton'])} TON = <b>{fmt(pd['uzs'])} so'm</b>\n\n"
        f"Kimga yuboramiz?",
        parse_mode="HTML", reply_markup=recipient_kb(cb.from_user.id)
    )

@dp.message(Order.stars_amount)
async def enter_stars_amount(msg: types.Message, state: FSMContext):
    if msg.text in ["❌ Bekor", "❌ Отмена", "❌ Cancel"]:
        await state.clear()
        await msg.answer("🏠", reply_markup=main_kb(msg.from_user.id))
        return
    d = db()
    min_s = d["settings"]["min_stars"]
    try:
        stars = int(msg.text.replace(" ", ""))
        if stars < min_s:
            await msg.answer(f"❌ Minimum <b>{min_s}</b> Stars!", parse_mode="HTML")
            return
        if stars > 100000:
            await msg.answer("❌ Maksimum 100 000 Stars!")
            return
        pd = get_stars_price_uzs(stars)
        await state.update_data(
            stars=stars,
            price=pd["uzs"],
            ton=pd["ton"],
            locked_at=pd["locked_at"],
            locked_rate=pd["rate_uzs"]
        )
        await msg.answer(
            f"🌟 <b>{fmt(stars)} Stars</b>\n"
            f"💎 {fmt_ton(pd['ton'])} TON = <b>{fmt(pd['uzs'])} so'm</b>\n\n"
            f"Kimga yuboramiz?",
            parse_mode="HTML", reply_markup=recipient_kb(msg.from_user.id)
        )
    except:
        await msg.answer("❌ Faqat raqam kiriting!")

# ═══════════════════════════════════════════
# GIFTS
# ═══════════════════════════════════════════
@dp.message(F.text.in_(["🎁 Gifts"]))
async def cmd_gifts(msg: types.Message, state: FSMContext):
    await state.update_data(service="gifts")
    await msg.answer(
        "🎁 <b>Telegram Gifts</b>\n\n"
        "Fragment.com da mavjud gift linkini yuboring:\n\n"
        "<i>https://fragment.com/gift/...</i>",
        parse_mode="HTML", reply_markup=cancel_kb(msg.from_user.id)
    )
    await state.set_state(Order.nft_link)

# ═══════════════════════════════════════════
# NFT
# ═══════════════════════════════════════════
@dp.message(F.text.in_(["🖼 NFT"]))
async def cmd_nft(msg: types.Message, state: FSMContext):
    await state.update_data(service="nft")
    await msg.answer(
        "🖼 <b>Fragment NFT</b>\n\n"
        "Fragment.com da NFT linkini yuboring:\n\n"
        "<i>https://fragment.com/username/...</i>\n"
        "<i>https://fragment.com/number/...</i>",
        parse_mode="HTML", reply_markup=cancel_kb(msg.from_user.id)
    )
    await state.set_state(Order.nft_link)

@dp.message(Order.nft_link)
async def enter_nft_link(msg: types.Message, state: FSMContext):
    if msg.text in ["❌ Bekor", "❌ Отмена", "❌ Cancel"]:
        await state.clear()
        await msg.answer("🏠", reply_markup=main_kb(msg.from_user.id))
        return
    if "fragment.com" not in msg.text:
        await msg.answer(
            "❌ <b>Noto'g'ri link!</b>\n\nfragment.com dan link yuboring.",
            parse_mode="HTML"
        )
        return

    wait = await msg.answer("⏳ Ma'lumotlar olinmoqda...")
    data = await state.get_data()
    service = data.get("service", "nft")

    try:
        from FragmentAPI import SyncFragmentAPI
        api = SyncFragmentAPI(cookies=FRAGMENT_COOKIES, wallet_api_key=TON_API_KEY)
        info = api.get_nft_info(msg.text)
        ton_price = float(info.price) if hasattr(info, 'price') and info.price else 5.0
        item_name = str(info.name) if hasattr(info, 'name') and info.name else "NFT"
    except Exception as e:
        log.error(f"NFT info: {e}")
        ton_price = 5.0
        item_name = "NFT/Gift"

    # Narxni hozirgi kurs bilan qotirish
    d_settings = db()
    markup = d_settings["settings"]["markup"]
    rate   = PRICE_CACHE["ton_uzs"] or 44800.0
    uzs    = round(ton_price * rate * (1 + markup / 100))
    locked_at = time.time()

    await state.update_data(
        nft_link=msg.text,
        nft_name=item_name,
        price=uzs,
        ton=ton_price,
        locked_at=locked_at,
        locked_rate=rate
    )

    await wait.delete()
    await msg.answer(
        f"{'🎁' if service=='gifts' else '🖼'} <b>{item_name}</b>\n\n"
        f"💎 Fragment narxi: <b>{fmt_ton(ton_price)} TON</b>\n"
        f"💰 Sizga narx: <b>{fmt(uzs)} so'm</b>\n\n"
        f"Kimga yuboramiz?",
        parse_mode="HTML", reply_markup=recipient_kb(msg.from_user.id)
    )

# ═══════════════════════════════════════════
# RECIPIENT
# ═══════════════════════════════════════════
@dp.callback_query(F.data == "rec_self")
async def rec_self(cb: types.CallbackQuery, state: FSMContext):
    if not cb.from_user.username:
        await cb.answer(
            "❌ Username ingiz yo'q!\nTelegram sozlamalaridan o'rnating.",
            show_alert=True
        )
        return
    await state.update_data(username=cb.from_user.username)
    await cb.message.delete()
    await show_confirm(cb.message, state, cb.from_user.id)

@dp.callback_query(F.data == "rec_other")
async def rec_other(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.edit_text(
        "👤 <b>Username kiriting:</b>\n\n<i>Masalan: @username</i>",
        parse_mode="HTML"
    )
    await state.set_state(Order.username)

@dp.message(Order.username)
async def enter_username(msg: types.Message, state: FSMContext):
    if msg.text in ["❌ Bekor", "❌ Отмена", "❌ Cancel"]:
        await state.clear()
        await msg.answer("🏠", reply_markup=main_kb(msg.from_user.id))
        return
    await state.update_data(username=msg.text.strip().lstrip("@"))
    await show_confirm(msg, state, msg.from_user.id)

# ═══════════════════════════════════════════
# TASDIQLASH (PRICE LOCK TEKSHIRUVI)
# ═══════════════════════════════════════════
async def show_confirm(msg, state, uid):
    data    = await state.get_data()
    d       = db()
    bal     = d["users"].get(str(uid), {}).get("balance", 0)
    price   = data.get("price", 0)
    uname   = data.get("username", "?")
    svc     = data.get("service", "")
    locked_at  = data.get("locked_at", time.time())
    locked_rate = data.get("locked_rate", PRICE_CACHE["ton_uzs"])
    timeout = d["settings"].get("order_timeout_min", 15)

    # Price lock muddati tekshiruvi
    elapsed = (time.time() - locked_at) / 60
    if elapsed > timeout:
        # Narx eskirgan — qayta hisoblash
        if svc == "premium":
            months = data.get("months", 3)
            pd = get_premium_price_uzs(months)
            price = pd["uzs"]
            await state.update_data(
                price=price, ton=pd["ton"],
                locked_at=pd["locked_at"], locked_rate=pd["rate_uzs"]
            )
        elif svc == "stars":
            stars = data.get("stars", 50)
            pd = get_stars_price_uzs(stars)
            price = pd["uzs"]
            await state.update_data(
                price=price, ton=pd["ton"],
                locked_at=pd["locked_at"], locked_rate=pd["rate_uzs"]
            )
        note = "⚠️ <i>Narx yangilandi (eski narx eskirgan edi)</i>\n\n"
    else:
        remaining = int(timeout - elapsed)
        note = f"🔒 <i>Narx {remaining} daqiqa davomida qotib turibdi</i>\n\n"

    # Xizmat nomi
    svc_names = {
        "premium": f"⭐ Premium {data.get('months', 3)} oy",
        "stars"  : f"🌟 {fmt(data.get('stars', 50))} Stars",
        "gifts"  : f"🎁 {data.get('nft_name', 'Gift')}",
        "nft"    : f"🖼 {data.get('nft_name', 'NFT')}",
    }
    svc_txt = svc_names.get(svc, svc)
    ton     = data.get("ton", 0)
    enough  = bal >= price

    status = (
        "✅ Balans yetarli" if enough
        else f"❌ Balans yetarli emas!\nKerak: <b>{fmt(price)}</b> | Sizda: <b>{fmt(bal)}</b> so'm"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data="ord_ok"),
        InlineKeyboardButton(text="❌ Bekor", callback_data="ord_no"),
    ]])

    await msg.answer(
        f"📋 <b>Buyurtma tasdiqlash</b>\n\n"
        f"{note}"
        f"<code>━━━━━━━━━━━━━━━━</code>\n"
        f"🛍 Xizmat: <b>{svc_txt}</b>\n"
        f"👤 Kimga: <b>@{uname}</b>\n"
        f"💎 TON: <b>{fmt_ton(ton)} TON</b>\n"
        f"💰 Narx: <b>{fmt(price)} so'm</b>\n"
        f"💳 Balansingiz: <b>{fmt(bal)} so'm</b>\n"
        f"<code>━━━━━━━━━━━━━━━━</code>\n"
        f"{status}",
        parse_mode="HTML", reply_markup=kb
    )

@dp.callback_query(F.data == "ord_ok")
async def order_ok(cb: types.CallbackQuery, state: FSMContext):
    data    = await state.get_data()
    d       = db()
    uid     = str(cb.from_user.id)
    bal     = d["users"].get(uid, {}).get("balance", 0)
    price   = data.get("price", 0)
    timeout = d["settings"].get("order_timeout_min", 15)

    # Price lock muddati tekshiruvi (oxirgi)
    locked_at = data.get("locked_at", time.time())
    elapsed   = (time.time() - locked_at) / 60
    if elapsed > timeout:
        await cb.answer(
            "⚠️ Narx muddati tugadi!\nIltimos buyurtmani qayta bering.",
            show_alert=True
        )
        await state.clear()
        await cb.message.edit_text("⏰ Narx muddati tugadi. /start dan qayta boshlang.")
        return

    if bal < price:
        await cb.answer(
            f"❌ Balans yetarli emas!\nKerak: {fmt(price)} | Sizda: {fmt(bal)} so'm",
            show_alert=True
        )
        return

    await cb.message.edit_text(
        "⏳ <b>Buyurtma bajarilmoqda...</b>\n\nFragment API ga so'rov yuborilmoqda...",
        parse_mode="HTML"
    )

    # Balansdan yechish
    d["users"][uid]["balance"] -= price

    svc = data.get("service", "")
    svc_names = {
        "premium": f"⭐ Premium {data.get('months', 3)} oy",
        "stars"  : f"🌟 {fmt(data.get('stars', 50))} Stars",
        "gifts"  : f"🎁 {data.get('nft_name', 'Gift')}",
        "nft"    : f"🖼 {data.get('nft_name', 'NFT')}",
    }
    svc_txt = svc_names.get(svc, svc)
    ton     = data.get("ton", 0)

    order = {
        "id"        : len(d["orders"]) + 1,
        "user_id"   : uid,
        "service"   : svc,
        "username"  : data.get("username"),
        "months"    : data.get("months"),
        "stars"     : data.get("stars"),
        "nft_link"  : data.get("nft_link"),
        "nft_name"  : data.get("nft_name"),
        "price"     : price,
        "ton"       : ton,
        "locked_rate": data.get("locked_rate"),
        "status"    : "processing",
        "created_at": datetime.now().isoformat(),
    }
    d["orders"].append(order)
    d["users"][uid].setdefault("orders", []).append(order["id"])
    sdb(d)

    success = await fragment_send(order)
    d = db()

    if success:
        for o in d["orders"]:
            if o["id"] == order["id"]:
                o["status"] = "completed"
        sdb(d)
        await cb.message.edit_text(
            f"🎉 <b>Muvaffaqiyatli yuborildi!</b>\n\n"
            f"<code>━━━━━━━━━━━━━━━━</code>\n"
            f"🛍 {svc_txt}\n"
            f"👤 @{order['username']}\n"
            f"💎 {fmt_ton(ton)} TON\n"
            f"💰 {fmt(price)} so'm\n"
            f"<code>━━━━━━━━━━━━━━━━</code>\n\n"
            f"✨ Xarid uchun rahmat!",
            parse_mode="HTML"
        )
        await send_log(
            f"✅ <b>Buyurtma #{order['id']}</b>\n"
            f"🛍 {svc_txt}\n"
            f"👤 @{order['username']}\n"
            f"💎 {fmt_ton(ton)} TON = {fmt(price)} so'm\n"
            f"🆔 UserID: {uid}"
        )
    else:
        d["users"][uid]["balance"] += price
        for o in d["orders"]:
            if o["id"] == order["id"]:
                o["status"] = "failed"
        sdb(d)
        await cb.message.edit_text(
            "❌ <b>Xato yuz berdi!</b>\n\n"
            "Balans qaytarildi.\n"
            "Sabab: Fragment API xatosi.\n"
            "Admin bilan bog'laning.",
            parse_mode="HTML"
        )
        await send_log(
            f"❌ <b>Buyurtma #{order['id']} XATO</b>\n"
            f"🛍 {svc_txt}\n👤 @{order['username']}\n🆔 {uid}"
        )
    await state.clear()

@dp.callback_query(F.data == "ord_no")
async def order_no(cb: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text("❌ Buyurtma bekor qilindi.")

# ═══════════════════════════════════════════
# FRAGMENT API
# ═══════════════════════════════════════════
async def fragment_send(order: dict) -> bool:
    try:
        from FragmentAPI import SyncFragmentAPI
        api = SyncFragmentAPI(cookies=FRAGMENT_COOKIES, wallet_api_key=TON_API_KEY)
        svc = order["service"]
        if svc == "premium":
            r = api.buy_premium(order["username"], order["months"])
        elif svc == "stars":
            r = api.buy_stars(order["username"], order["stars"])
        elif svc in ("nft", "gifts"):
            r = api.buy_nft(order["nft_link"])
        else:
            return False
        return bool(r)
    except Exception as e:
        log.error(f"Fragment send error: {e}")
        return False

# ═══════════════════════════════════════════
# TARIX
# ═══════════════════════════════════════════
@dp.message(F.text.in_(["📋 Tarix", "📋 История", "📋 History"]))
async def cmd_history(msg: types.Message):
    d = db(); uid = str(msg.from_user.id)
    orders = [o for o in d["orders"] if o["user_id"] == uid][-10:]
    if not orders:
        await msg.answer(
            "📋 <b>Buyurtmalar tarixi</b>\n\nHali buyurtmalar yo'q.",
            parse_mode="HTML"
        )
        return
    st = {"completed": "✅", "failed": "❌", "processing": "⏳"}
    svc_n = lambda o: {
        "premium": f"Premium {o.get('months', 3)}oy",
        "stars"  : f"{fmt(o.get('stars', 0))} ⭐",
        "gifts"  : f"Gift",
        "nft"    : f"NFT",
    }.get(o["service"], o["service"])

    text = "📋 <b>Buyurtmalaringiz:</b>\n<code>━━━━━━━━━━━━━━━━</code>\n\n"
    for o in reversed(orders):
        text += (
            f"{st.get(o['status'], '❓')} <b>#{o['id']}</b> — {svc_n(o)}\n"
            f"   👤 @{o.get('username', '?')} | "
            f"💎 {fmt_ton(o.get('ton', 0))} TON | "
            f"💰 {fmt(o['price'])} so'm\n\n"
        )
    await msg.answer(text, parse_mode="HTML")

# ═══════════════════════════════════════════
# REFERRAL
# ═══════════════════════════════════════════
@dp.message(F.text.in_(["👥 Referral", "👥 Реферал"]))
async def cmd_referral(msg: types.Message):
    d = db()
    if not d["settings"].get("referral_active"): return
    uid = str(msg.from_user.id); u = d["users"].get(uid, {})
    me = await bot.get_me()
    link  = f"https://t.me/{me.username}?start=ref_{uid}"
    bonus = d["settings"]["referral_bonus"]
    await msg.answer(
        f"👥 <b>Referral tizimi</b>\n\n"
        f"Do'stlarni taklif qiling va bonus oling!\n\n"
        f"<code>━━━━━━━━━━━━━━━━</code>\n"
        f"🔗 Havola:\n<code>{link}</code>\n\n"
        f"👥 Taklif qilganlar: <b>{u.get('referrals', 0)}</b>\n"
        f"💰 Jami bonus: <b>{fmt(u.get('ref_earned', 0))} so'm</b>\n"
        f"🎁 Har bir do'st: <b>{fmt(bonus)} so'm</b>\n"
        f"<code>━━━━━━━━━━━━━━━━</code>",
        parse_mode="HTML"
    )

# ═══════════════════════════════════════════
# PROMO KOD
# ═══════════════════════════════════════════
@dp.message(F.text.in_(["🎁 Promo kod", "🎁 Промо код", "🎁 Promo code"]))
async def cmd_promo(msg: types.Message, state: FSMContext):
    d = db()
    if not d["settings"].get("promo_active"): return
    await msg.answer("🎁 <b>Promo kodingizni kiriting:</b>", parse_mode="HTML", reply_markup=cancel_kb(msg.from_user.id))
    await state.set_state(Order.promo_input)

@dp.message(Order.promo_input)
async def enter_promo(msg: types.Message, state: FSMContext):
    if msg.text in ["❌ Bekor", "❌ Отмена", "❌ Cancel"]:
        await state.clear()
        await msg.answer("🏠", reply_markup=main_kb(msg.from_user.id))
        return
    d = db(); uid = str(msg.from_user.id)
    code = msg.text.strip().upper()
    promos = d.get("promo_codes", {})
    if code not in promos:
        await msg.answer("❌ Noto'g'ri promo kod!", reply_markup=main_kb(msg.from_user.id))
        await state.clear(); return
    promo = promos[code]
    if promo.get("limit") and promo.get("used", 0) >= promo["limit"]:
        await msg.answer("❌ Bu promo kodning limiti tugagan!", reply_markup=main_kb(msg.from_user.id))
        await state.clear(); return
    if code in d["users"].get(uid, {}).get("promo_used", []):
        await msg.answer("❌ Bu promo kodni allaqachon ishlatgansiz!", reply_markup=main_kb(msg.from_user.id))
        await state.clear(); return
    await msg.answer(
        f"✅ <b>Promo kod qo'llandi!</b>\n\n"
        f"🎁 Kod: <code>{code}</code>\n"
        f"📉 Chegirma: <b>-{promo['discount']}%</b>",
        parse_mode="HTML", reply_markup=main_kb(msg.from_user.id)
    )
    await state.clear()

# ═══════════════════════════════════════════
# SOZLAMALAR
# ═══════════════════════════════════════════
@dp.message(F.text.in_(["⚙️ Sozlamalar", "⚙️ Настройки", "⚙️ Settings"]))
async def cmd_settings(msg: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🇺🇿 O'zbek", callback_data="sl_uz"),
        InlineKeyboardButton(text="🇷🇺 Русский", callback_data="sl_ru"),
        InlineKeyboardButton(text="🇬🇧 English", callback_data="sl_en"),
    ]])
    await msg.answer("🌐 <b>Tilni tanlang:</b>", parse_mode="HTML", reply_markup=kb)

@dp.callback_query(F.data.startswith("sl_"))
async def cb_setlang(cb: types.CallbackQuery):
    l = cb.data[3:]
    set_user(cb.from_user.id, {"lang": l})
    await cb.message.delete()
    await cb.message.answer(L[l]["welcome"], parse_mode="HTML", reply_markup=main_kb(cb.from_user.id))

# ═══════════════════════════════════════════
# ADMIN PANEL
# ═══════════════════════════════════════════
def admin_kb(uid) -> InlineKeyboardMarkup:
    d = db(); sup = is_super(uid)
    rows = [
        [InlineKeyboardButton(text="📊 Statistika", callback_data="adm_stats"),
         InlineKeyboardButton(text="👥 Foydalanuvchilar", callback_data="adm_users")],
        [InlineKeyboardButton(text="📋 Buyurtmalar", callback_data="adm_orders"),
         InlineKeyboardButton(text="📢 Xabar yuborish", callback_data="adm_broadcast")],
    ]
    if sup:
        rows += [
            [InlineKeyboardButton(text="💳 Kartalar", callback_data="adm_cards"),
             InlineKeyboardButton(text="⚙️ Sozlamalar", callback_data="adm_settings")],
            [InlineKeyboardButton(text="👑 Adminlar", callback_data="adm_admins"),
             InlineKeyboardButton(text="📢 Kanallar", callback_data="adm_channels")],
            [InlineKeyboardButton(text="🎁 Promo", callback_data="adm_promos"),
             InlineKeyboardButton(text="👥 Referral", callback_data="adm_referral")],
            [InlineKeyboardButton(
                text=f"🤖 Bot {'O\'CHIRISH ❌' if d['settings']['bot_active'] else 'YOQISH ✅'}",
                callback_data="adm_toggle_bot"
            )],
            [InlineKeyboardButton(text="🔄 Narxlarni yangilash", callback_data="adm_refresh_prices")],
        ]
    return InlineKeyboardMarkup(inline_keyboard=rows)

async def adm_text() -> str:
    d = db()
    total = len(d["users"])
    orders = len(d["orders"])
    done  = len([o for o in d["orders"] if o["status"] == "completed"])
    rev   = sum(o["price"] for o in d["orders"] if o["status"] == "completed")
    today = datetime.now().date().isoformat()
    t_rev = sum(o["price"] for o in d["orders"] if o["status"] == "completed" and o["created_at"][:10] == today)

    rate_ton = PRICE_CACHE.get("ton_uzs", 0)
    stars_ton = PRICE_CACHE.get("stars_ton", 0)
    last_upd = PRICE_CACHE.get("last_update", 0)
    last_str = datetime.fromtimestamp(last_upd).strftime("%H:%M") if last_upd else "—"
    markup = d["settings"]["markup"]

    return (
        f"👨‍💼 <b>Admin Panel — U-Gift Bot</b>\n\n"
        f"<code>━━━━━━━━━━━━━━━━</code>\n"
        f"💎 1 TON = <b>{fmt(rate_ton)} so'm</b>\n"
        f"⭐ 1 Star = <b>{fmt_ton(stars_ton)} TON</b>\n"
        f"📈 Ustiga foiz: <b>{markup}%</b>\n"
        f"🕐 Narx yangilangan: <b>{last_str}</b>\n"
        f"<code>━━━━━━━━━━━━━━━━</code>\n"
        f"👥 Foydalanuvchilar: <b>{total}</b>\n"
        f"📋 Jami buyurtmalar: <b>{orders}</b>\n"
        f"✅ Bajarilgan: <b>{done}</b>\n"
        f"<code>━━━━━━━━━━━━━━━━</code>\n"
        f"📅 Bugungi daromad: <b>{fmt(t_rev)} so'm</b>\n"
        f"💰 Jami daromad: <b>{fmt(rev)} so'm</b>\n"
        f"<code>━━━━━━━━━━━━━━━━</code>"
    )

@dp.message(Command("admin"))
async def cmd_admin(msg: types.Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    await state.clear()
    await msg.answer(await adm_text(), parse_mode="HTML", reply_markup=admin_kb(msg.from_user.id))

@dp.callback_query(F.data == "adm_main")
async def cb_adm_main(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    if state: await state.clear()
    try:
        await cb.message.edit_text(await adm_text(), parse_mode="HTML", reply_markup=admin_kb(cb.from_user.id))
    except:
        await cb.message.answer(await adm_text(), parse_mode="HTML", reply_markup=admin_kb(cb.from_user.id))

@dp.callback_query(F.data == "adm_refresh_prices")
async def adm_refresh_prices(cb: types.CallbackQuery):
    if not is_super(cb.from_user.id): return
    await cb.answer("⏳ Narxlar yangilanmoqda...", show_alert=False)
    PRICE_CACHE["last_update"] = 0
    await update_prices(force=True)
    await cb.answer(f"✅ Narxlar yangilandi! 1 TON = {fmt(PRICE_CACHE['ton_uzs'])} so'm", show_alert=True)
    await cb_adm_main(cb, None)

@dp.callback_query(F.data == "adm_stats")
async def cb_stats(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): return
    d = db(); today = datetime.now().date().isoformat()
    t_ord = [o for o in d["orders"] if o["created_at"][:10] == today]
    t_rev = sum(o["price"] for o in t_ord if o["status"] == "completed")
    total_rev = sum(o["price"] for o in d["orders"] if o["status"] == "completed")
    await cb.message.edit_text(
        f"📊 <b>To'liq statistika</b>\n\n"
        f"<code>━━━━━━━━━━━━━━━━</code>\n"
        f"👥 Foydalanuvchilar: <b>{len(d['users'])}</b>\n"
        f"📋 Jami: <b>{len(d['orders'])}</b>\n"
        f"✅ Bajarilgan: <b>{len([o for o in d['orders'] if o['status']=='completed'])}</b>\n"
        f"❌ Xato: <b>{len([o for o in d['orders'] if o['status']=='failed'])}</b>\n"
        f"<code>━━━━━━━━━━━━━━━━</code>\n"
        f"📅 Bugun: <b>{len(t_ord)}</b> ta\n"
        f"💰 Bugungi daromad: <b>{fmt(t_rev)} so'm</b>\n"
        f"💰 Jami daromad: <b>{fmt(total_rev)} so'm</b>\n"
        f"<code>━━━━━━━━━━━━━━━━</code>",
        parse_mode="HTML", reply_markup=back_kb()
    )

@dp.callback_query(F.data == "adm_users")
async def cb_users(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): return
    d = db()
    total  = len(d["users"])
    banned = len([u for u in d["users"].values() if u.get("banned")])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚫 Bloklash", callback_data="adm_ban"),
         InlineKeyboardButton(text="✅ Ochish", callback_data="adm_unban")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="adm_main")],
    ])
    await cb.message.edit_text(
        f"👥 <b>Foydalanuvchilar</b>\n\nJami: <b>{total}</b>\nBanlangan: <b>{banned}</b>",
        parse_mode="HTML", reply_markup=kb
    )

@dp.callback_query(F.data.in_({"adm_ban", "adm_unban"}))
async def cb_ban(cb: types.CallbackQuery, state: FSMContext):
    action = "bloklash" if cb.data == "adm_ban" else "ochish"
    await cb.message.edit_text(f"ID kiriting ({action}):")
    await state.update_data(ban_action=cb.data)
    await state.set_state(Admin.ban_id)

@dp.message(Admin.ban_id)
async def enter_ban(msg: types.Message, state: FSMContext):
    try:
        bid = str(int(msg.text.strip()))
        if bid == str(SUPER_ADMIN_ID):
            await msg.answer("❌ Asosiy adminni o'zgartirish mumkin emas!")
            await state.clear(); return
        data = await state.get_data(); d = db()
        if bid in d["users"]:
            d["users"][bid]["banned"] = data.get("ban_action") == "adm_ban"
            sdb(d)
            act = "Bloklandi 🚫" if data.get("ban_action") == "adm_ban" else "Ochildi ✅"
            await msg.answer(f"{act}: <code>{bid}</code>", parse_mode="HTML")
        else:
            await msg.answer("❌ Foydalanuvchi topilmadi!")
        await state.clear()
        await cmd_admin(msg, state)
    except:
        await msg.answer("❌ Noto'g'ri ID!")

@dp.callback_query(F.data == "adm_orders")
async def cb_orders(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): return
    d = db(); orders = d["orders"][-8:]
    if not orders:
        await cb.answer("Buyurtmalar yo'q!", show_alert=True); return
    st = {"completed": "✅", "failed": "❌", "processing": "⏳"}
    text = "📋 <b>So'nggi buyurtmalar:</b>\n<code>━━━━━━━━━━━━━━━━</code>\n\n"
    for o in reversed(orders):
        svc = {"premium": f"P{o.get('months',3)}oy", "stars": f"{fmt(o.get('stars',0))}⭐", "gifts": "🎁", "nft": "NFT"}.get(o["service"], o["service"])
        text += f"{st.get(o['status'],'❓')} <b>#{o['id']}</b> @{o.get('username','?')} — {svc} — {fmt(o['price'])} so'm\n"
    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=back_kb())

@dp.callback_query(F.data == "adm_broadcast")
async def cb_broadcast(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    await cb.message.edit_text("📢 <b>Xabar yozing:</b>", parse_mode="HTML")
    await state.set_state(Admin.broadcast)

@dp.message(Admin.broadcast)
async def enter_broadcast(msg: types.Message, state: FSMContext):
    d = db(); sent = failed = 0
    prog = await msg.answer(f"⏳ Yuborilmoqda... 0/{len(d['users'])}")
    for i, uid in enumerate(d["users"]):
        try:
            await bot.send_message(int(uid), f"📢 <b>Xabar:</b>\n\n{msg.text}", parse_mode="HTML")
            sent += 1
        except:
            failed += 1
        if i % 20 == 0:
            try: await prog.edit_text(f"⏳ {i}/{len(d['users'])}")
            except: pass
        await asyncio.sleep(0.05)
    await prog.edit_text(f"✅ Yuborildi! ✅{sent} ❌{failed}", parse_mode="HTML")
    await state.clear()
    await cmd_admin(msg, state)

@dp.callback_query(F.data == "adm_settings")
async def cb_settings(cb: types.CallbackQuery):
    if not is_super(cb.from_user.id): return
    d = db(); s = d["settings"]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"📈 Foiz: {s['markup']}%", callback_data="adm_set_markup")],
        [InlineKeyboardButton(text=f"⭐ Min Stars: {s['min_stars']}", callback_data="adm_set_minstars")],
        [InlineKeyboardButton(text=f"⏰ Narx qulfi: {s.get('order_timeout_min', 15)} daqiqa", callback_data="adm_set_timeout")],
        [InlineKeyboardButton(text=f"👥 Referral: {'✅' if s.get('referral_active') else '❌'}", callback_data="adm_toggle_ref")],
        [InlineKeyboardButton(text=f"🎁 Promo: {'✅' if s.get('promo_active') else '❌'}", callback_data="adm_toggle_promo")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="adm_main")],
    ])
    await cb.message.edit_text(
        f"⚙️ <b>Bot sozlamalari</b>\n\n"
        f"💎 1 TON = {fmt(PRICE_CACHE.get('ton_uzs', 0))} so'm",
        parse_mode="HTML", reply_markup=kb
    )

@dp.callback_query(F.data == "adm_toggle_bot")
async def toggle_bot(cb: types.CallbackQuery):
    if not is_super(cb.from_user.id): return
    d = db(); d["settings"]["bot_active"] = not d["settings"]["bot_active"]; sdb(d)
    await cb.answer(f"Bot {'YOQILDI ✅' if d['settings']['bot_active'] else 'O\'CHIRILDI ❌'}", show_alert=True)
    await cb_adm_main(cb, None)

@dp.callback_query(F.data == "adm_toggle_ref")
async def toggle_ref(cb: types.CallbackQuery):
    if not is_super(cb.from_user.id): return
    d = db(); d["settings"]["referral_active"] = not d["settings"]["referral_active"]; sdb(d)
    await cb.answer(f"Referral {'✅' if d['settings']['referral_active'] else '❌'}", show_alert=True)
    await cb_settings(cb)

@dp.callback_query(F.data == "adm_toggle_promo")
async def toggle_promo(cb: types.CallbackQuery):
    if not is_super(cb.from_user.id): return
    d = db(); d["settings"]["promo_active"] = not d["settings"]["promo_active"]; sdb(d)
    await cb.answer(f"Promo {'✅' if d['settings']['promo_active'] else '❌'}", show_alert=True)
    await cb_settings(cb)

@dp.callback_query(F.data == "adm_set_markup")
async def set_markup(cb: types.CallbackQuery, state: FSMContext):
    if not is_super(cb.from_user.id): return
    await cb.message.edit_text("📈 Yangi foizni kiriting (0-200):")
    await state.set_state(Admin.markup)

@dp.message(Admin.markup)
async def enter_markup(msg: types.Message, state: FSMContext):
    try:
        v = int(msg.text)
        if v < 0 or v > 200:
            await msg.answer("❌ 0 dan 200 gacha!"); return
        d = db(); d["settings"]["markup"] = v; sdb(d)
        await msg.answer(f"✅ Foiz: <b>{v}%</b>", parse_mode="HTML")
        await state.clear(); await cmd_admin(msg, state)
    except: await msg.answer("❌ Faqat raqam!")

@dp.callback_query(F.data == "adm_set_minstars")
async def set_minstars(cb: types.CallbackQuery, state: FSMContext):
    if not is_super(cb.from_user.id): return
    await cb.message.edit_text("⭐ Minimum Stars kiriting (min: 50):")
    await state.set_state(Admin.min_stars)

@dp.message(Admin.min_stars)
async def enter_minstars(msg: types.Message, state: FSMContext):
    try:
        v = int(msg.text)
        if v < 50:
            await msg.answer("❌ Minimum 50!"); return
        d = db(); d["settings"]["min_stars"] = v; sdb(d)
        await msg.answer(f"✅ Min Stars: <b>{v}</b>", parse_mode="HTML")
        await state.clear(); await cmd_admin(msg, state)
    except: await msg.answer("❌ Faqat raqam!")

@dp.callback_query(F.data == "adm_set_timeout")
async def set_timeout(cb: types.CallbackQuery, state: FSMContext):
    if not is_super(cb.from_user.id): return
    await cb.message.edit_text("⏰ Narx qulfi muddati (daqiqada, 5-60):")
    await state.set_state(Admin.ref_bonus)  # reuse state

@dp.callback_query(F.data == "adm_cards")
async def cb_cards(cb: types.CallbackQuery):
    if not is_super(cb.from_user.id): return
    d = db(); cards = d["settings"]["cards"]
    ct = "\n".join([f"• <code>{c}</code>" for c in cards]) if cards else "Kartalar yo'q"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Karta qo'shish", callback_data="adm_add_card")],
        [InlineKeyboardButton(text="🗑 Hammasini o'chirish", callback_data="adm_clear_cards")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="adm_main")],
    ])
    await cb.message.edit_text(f"💳 <b>Kartalar:</b>\n\n{ct}", parse_mode="HTML", reply_markup=kb)

@dp.callback_query(F.data == "adm_add_card")
async def add_card(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.edit_text("💳 Karta raqamini kiriting:")
    await state.set_state(Admin.card)

@dp.message(Admin.card)
async def enter_card(msg: types.Message, state: FSMContext):
    d = db(); d["settings"]["cards"].append(msg.text.strip()); sdb(d)
    await msg.answer(f"✅ Karta: <code>{msg.text.strip()}</code>", parse_mode="HTML")
    await state.clear(); await cmd_admin(msg, state)

@dp.callback_query(F.data == "adm_clear_cards")
async def clear_cards(cb: types.CallbackQuery):
    d = db(); d["settings"]["cards"] = []; sdb(d)
    await cb.answer("✅ Tozalandi!"); await cb_cards(cb)

@dp.callback_query(F.data == "adm_channels")
async def cb_channels(cb: types.CallbackQuery):
    if not is_super(cb.from_user.id): return
    d = db(); chs = d["settings"]["required_channels"]; logs = d["settings"].get("logs_channel", "Yo'q")
    ct = "\n".join([f"• {c}" for c in chs]) if chs else "Kanallar yo'q"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Kanal qo'shish", callback_data="adm_add_ch")],
        [InlineKeyboardButton(text="📝 Logs kanali", callback_data="adm_set_logs")],
        [InlineKeyboardButton(text="🗑 Tozalash", callback_data="adm_clear_ch")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="adm_main")],
    ])
    await cb.message.edit_text(
        f"📢 <b>Kanallar:</b>\n{ct}\n\n📝 <b>Logs:</b> {logs}",
        parse_mode="HTML", reply_markup=kb
    )

@dp.callback_query(F.data == "adm_add_ch")
async def add_ch(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.edit_text("📢 Kanal username (@channel):")
    await state.set_state(Admin.channel)

@dp.message(Admin.channel)
async def enter_channel(msg: types.Message, state: FSMContext):
    d = db(); d["settings"]["required_channels"].append(msg.text.strip()); sdb(d)
    await msg.answer(f"✅ Kanal: {msg.text.strip()}")
    await state.clear(); await cmd_admin(msg, state)

@dp.callback_query(F.data == "adm_clear_ch")
async def clear_ch(cb: types.CallbackQuery):
    d = db(); d["settings"]["required_channels"] = []; sdb(d)
    await cb.answer("✅ Tozalandi!"); await cb_channels(cb)

@dp.callback_query(F.data == "adm_set_logs")
async def set_logs(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.edit_text("📝 Logs kanal (@logs):")
    await state.set_state(Admin.logs)

@dp.message(Admin.logs)
async def enter_logs(msg: types.Message, state: FSMContext):
    d = db(); d["settings"]["logs_channel"] = msg.text.strip(); sdb(d)
    await msg.answer(f"✅ Logs: {msg.text.strip()}")
    await state.clear(); await cmd_admin(msg, state)

@dp.callback_query(F.data == "adm_admins")
async def cb_admins(cb: types.CallbackQuery):
    if not is_super(cb.from_user.id): return
    d = db(); admins = d.get("admins", {})
    at = "\n".join([f"• <code>{a}</code>" for a in admins.keys()]) if admins else "Adminlar yo'q"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Qo'shish", callback_data="adm_add_admin"),
         InlineKeyboardButton(text="➖ O'chirish", callback_data="adm_del_admin")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="adm_main")],
    ])
    await cb.message.edit_text(f"👑 <b>Adminlar:</b>\n\n{at}", parse_mode="HTML", reply_markup=kb)

@dp.callback_query(F.data.in_({"adm_add_admin", "adm_del_admin"}))
async def manage_admin(cb: types.CallbackQuery, state: FSMContext):
    action = "qo'shish" if cb.data == "adm_add_admin" else "o'chirish"
    await cb.message.edit_text(f"👑 Admin ID ({action}):")
    await state.update_data(admin_action=cb.data)
    await state.set_state(Admin.admin_id)

@dp.message(Admin.admin_id)
async def enter_admin(msg: types.Message, state: FSMContext):
    try:
        aid = int(msg.text.strip())
        if aid == SUPER_ADMIN_ID:
            await msg.answer("❌ Asosiy adminni o'zgartirish mumkin emas!")
            await state.clear(); return
        data = await state.get_data(); d = db()
        if data.get("admin_action") == "adm_add_admin":
            d["admins"][str(aid)] = {"added": datetime.now().isoformat()}; sdb(d)
            await msg.answer(f"✅ Admin: <code>{aid}</code>", parse_mode="HTML")
        else:
            if str(aid) in d["admins"]:
                del d["admins"][str(aid)]; sdb(d)
                await msg.answer(f"✅ O'chirildi: {aid}")
            else:
                await msg.answer("❌ Admin topilmadi!")
        await state.clear(); await cmd_admin(msg, state)
    except: await msg.answer("❌ Noto'g'ri ID!")

@dp.callback_query(F.data == "adm_promos")
async def cb_promos(cb: types.CallbackQuery):
    if not is_super(cb.from_user.id): return
    d = db(); promos = d.get("promo_codes", {})
    pt = "\n".join([f"• <code>{k}</code> — {v['discount']}% ({v.get('used',0)}/{v.get('limit','∞')})" for k, v in promos.items()]) if promos else "Yo'q"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Yaratish", callback_data="adm_new_promo"),
         InlineKeyboardButton(text="🗑 Tozalash", callback_data="adm_clear_promos")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="adm_main")],
    ])
    await cb.message.edit_text(f"🎁 <b>Promo kodlar:</b>\n\n{pt}", parse_mode="HTML", reply_markup=kb)

@dp.callback_query(F.data == "adm_new_promo")
async def new_promo(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.edit_text("🎁 Promo kod nomi (masalan: SALE20):")
    await state.set_state(Admin.promo_code)

@dp.message(Admin.promo_code)
async def enter_promo_code(msg: types.Message, state: FSMContext):
    await state.update_data(promo_code=msg.text.strip().upper())
    await msg.answer("📈 Chegirma foizi (1-90):")
    await state.set_state(Admin.promo_discount)

@dp.message(Admin.promo_discount)
async def enter_promo_discount(msg: types.Message, state: FSMContext):
    try:
        v = int(msg.text)
        if v < 1 or v > 90:
            await msg.answer("❌ 1 dan 90 gacha!"); return
        await state.update_data(promo_discount=v)
        await msg.answer("🔢 Limit (0 = cheksiz):")
        await state.set_state(Admin.promo_limit)
    except: await msg.answer("❌ Faqat raqam!")

@dp.message(Admin.promo_limit)
async def enter_promo_limit(msg: types.Message, state: FSMContext):
    try:
        limit = int(msg.text); data = await state.get_data(); d = db()
        code = data["promo_code"]
        d["promo_codes"][code] = {
            "discount": data["promo_discount"],
            "limit": limit if limit > 0 else None,
            "used": 0, "created_at": datetime.now().isoformat()
        }
        sdb(d)
        await msg.answer(
            f"✅ <b>Promo yaratildi!</b>\n\n"
            f"🎁 <code>{code}</code>\n"
            f"📈 {data['promo_discount']}%\n"
            f"🔢 {limit if limit > 0 else 'Cheksiz'}",
            parse_mode="HTML"
        )
        await state.clear(); await cmd_admin(msg, state)
    except: await msg.answer("❌ Faqat raqam!")

@dp.callback_query(F.data == "adm_clear_promos")
async def clear_promos(cb: types.CallbackQuery):
    d = db(); d["promo_codes"] = {}; sdb(d)
    await cb.answer("✅ Tozalandi!"); await cb_promos(cb)

@dp.callback_query(F.data == "adm_referral")
async def cb_referral_admin(cb: types.CallbackQuery):
    if not is_super(cb.from_user.id): return
    d = db(); s = d["settings"]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"👥 {'✅ Yoqilgan' if s.get('referral_active') else '❌ O\'chirilgan'}",
            callback_data="adm_toggle_ref"
        )],
        [InlineKeyboardButton(
            text=f"💰 Bonus: {fmt(s.get('referral_bonus', 5000))} so'm",
            callback_data="adm_set_ref_bonus"
        )],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="adm_main")],
    ])
    await cb.message.edit_text("👥 <b>Referral tizimi</b>", parse_mode="HTML", reply_markup=kb)

@dp.callback_query(F.data == "adm_set_ref_bonus")
async def set_ref_bonus(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.edit_text("💰 Referral bonus (so'mda):")
    await state.set_state(Admin.ref_bonus)

@dp.message(Admin.ref_bonus)
async def enter_ref_bonus(msg: types.Message, state: FSMContext):
    try:
        v = int(msg.text)
        d = db(); d["settings"]["referral_bonus"] = v; sdb(d)
        await msg.answer(f"✅ Bonus: <b>{fmt(v)} so'm</b>", parse_mode="HTML")
        await state.clear(); await cmd_admin(msg, state)
    except: await msg.answer("❌ Faqat raqam!")

# ═══════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════
async def main():
    log.info("🚀 U-Gift Bot ishga tushmoqda...")

    # Narxlarni oldindan yuklash
    log.info("📊 Narxlar yuklanmoqda...")
    await update_prices(force=True)
    log.info(f"✅ 1 TON = {fmt(PRICE_CACHE['ton_uzs'])} so'm")

    # Narx yangilash loop ni background da ishga tushirish
    asyncio.create_task(price_updater_loop())

    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
