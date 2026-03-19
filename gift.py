"""
U-Gift Bot
- Admin TON da narx kiritadi (qo'lda)
- Karta raqami + ism familiya
- TON/USDT kurs faqat adminga
- Foydalanuvchi faqat UZS ko'radi
- Faqat Premium va Stars
"""

import asyncio
import logging
import json
import os
import time
import aiohttp
from datetime import datetime
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

BOT_TOKEN        = os.getenv("BOT_TOKEN")
SUPER_ADMIN_ID   = int(os.getenv("ADMIN_ID", "0"))
TON_API_KEY      = os.getenv("TON_API_KEY", "")
FRAGMENT_COOKIES = os.getenv("FRAGMENT_COOKIES", "")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher(storage=MemoryStorage())

# ═══════════════════════════════════════
# KURS (faqat TON/USD va USD/UZS)
# ═══════════════════════════════════════
KURS = {
    "ton_usd" : 0.0,
    "ton_usdt": 0.0,
    "usd_uzs" : 0.0,
    "ton_uzs" : 0.0,
    "last"    : 0,
}

async def update_kurs():
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://api.coingecko.com/api/v3/simple/price?ids=the-open-network&vs_currencies=usd,usdt",
                timeout=aiohttp.ClientTimeout(total=8),
                headers={"User-Agent": "Mozilla/5.0"}
            ) as r:
                d = await r.json()
                ton_usd  = float(d["the-open-network"]["usd"])
                ton_usdt = float(d["the-open-network"].get("usdt", ton_usd))
            async with s.get(
                "https://cbu.uz/uz/arkhiv-kursov-valyut/json/USD/",
                timeout=aiohttp.ClientTimeout(total=8)
            ) as r:
                d = await r.json()
                usd_uzs = float(d[0]["Rate"])
        KURS["ton_usd"]  = ton_usd
        KURS["ton_usdt"] = ton_usdt
        KURS["usd_uzs"]  = usd_uzs
        KURS["ton_uzs"]  = ton_usd * usd_uzs
        KURS["last"]     = time.time()
        log.info(f"Kurs: 1 TON = ${ton_usd:.3f} = {int(ton_usd*usd_uzs):,} UZS")
    except Exception as e:
        log.error(f"Kurs xatosi: {e}")
        if KURS["ton_uzs"] == 0:
            KURS["ton_usd"]  = 3.5
            KURS["ton_usdt"] = 3.5
            KURS["usd_uzs"]  = 12800.0
            KURS["ton_uzs"]  = 44800.0

async def kurs_loop():
    while True:
        await update_kurs()
        await asyncio.sleep(30 * 60)

def calc_uzs(ton: float) -> int:
    """TON -> UZS (markup bilan)"""
    d = db()
    markup = d["settings"]["markup"]
    rate   = KURS["ton_uzs"] or 44800.0
    return round(ton * rate * (1 + markup / 100))

def fmt(n) -> str:
    return f"{int(n):,}".replace(",", " ")

def fmt_ton(n: float) -> str:
    return f"{n:.4f}".rstrip("0").rstrip(".")

# ═══════════════════════════════════════
# DATABASE
# ═══════════════════════════════════════
DB_FILE = "database.json"

def db() -> dict:
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "users": {}, "orders": [], "admins": {}, "promo_codes": {},
        "settings": {
            "markup"           : 20,
            "min_stars"        : 50,
            "bot_active"       : True,
            "referral_active"  : False,
            "promo_active"     : False,
            "referral_bonus"   : 5000,
            "cards"            : [],   # [{"number": "...", "name": "..."}]
            "required_channels": [],
            "logs_channel"     : None,
            "price_lock_min"   : 15,
            # Admin qo'lda kiritgan TON narxlari
            "premium_ton"      : {
                "3" : 9.37,
                "6" : 12.50,
                "12": 22.67,
            },
            "stars_ton_per_50" : 0.466,  # 50 Stars = ? TON
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

# ═══════════════════════════════════════
# NARX HISOBLASH
# ═══════════════════════════════════════
def get_prem_uzs(months: int) -> tuple:
    """Premium narxi: (ton, uzs, locked_at)"""
    d   = db()
    ton = d["settings"]["premium_ton"].get(str(months), 9.37)
    return ton, calc_uzs(ton), time.time()

def get_stars_uzs(count: int) -> tuple:
    """Stars narxi: (ton, uzs, locked_at)"""
    d           = db()
    ton_per_50  = d["settings"]["stars_ton_per_50"]
    ton         = count * (ton_per_50 / 50)
    return round(ton, 4), calc_uzs(ton), time.time()

def price_lock_ok(locked_at: float) -> tuple:
    """(ok, qolgan_daqiqa)"""
    d       = db()
    timeout = d["settings"].get("price_lock_min", 15)
    elapsed = (time.time() - locked_at) / 60
    return elapsed <= timeout, max(0, int(timeout - elapsed))

# ═══════════════════════════════════════
# TILLAR
# ═══════════════════════════════════════
L = {
    "uz": {
        "welcome" : "👋 <b>U-Gift Bot ga xush kelibsiz!</b>\n\n✨ Telegram Premium va Stars yuborish xizmati.\n\n💡 Xizmat tanlang:",
        "premium" : "⭐ Premium Gift",
        "stars"   : "🌟 Stars",
        "balance" : "💰 Balans",
        "history" : "📋 Tarix",
        "topup"   : "➕ Hisob to'ldirish",
        "referral": "👥 Referral",
        "promo"   : "🎁 Promo kod",
        "settings": "⚙️ Sozlamalar",
        "cancel"  : "❌ Bekor",
        "self"    : "👤 O'zimga",
        "other"   : "👥 Boshqaga",
    },
    "ru": {
        "welcome" : "👋 <b>Добро пожаловать в U-Gift Bot!</b>\n\n✨ Отправка Telegram Premium и Stars.\n\n💡 Выберите услугу:",
        "premium" : "⭐ Premium Gift",
        "stars"   : "🌟 Stars",
        "balance" : "💰 Баланс",
        "history" : "📋 История",
        "topup"   : "➕ Пополнить",
        "referral": "👥 Реферал",
        "promo"   : "🎁 Промо код",
        "settings": "⚙️ Настройки",
        "cancel"  : "❌ Отмена",
        "self"    : "👤 Себе",
        "other"   : "👥 Другому",
    },
    "en": {
        "welcome" : "👋 <b>Welcome to U-Gift Bot!</b>\n\n✨ Telegram Premium and Stars sending service.\n\n💡 Choose a service:",
        "premium" : "⭐ Premium Gift",
        "stars"   : "🌟 Stars",
        "balance" : "💰 Balance",
        "history" : "📋 History",
        "topup"   : "➕ Top up",
        "referral": "👥 Referral",
        "promo"   : "🎁 Promo code",
        "settings": "⚙️ Settings",
        "cancel"  : "❌ Cancel",
        "self"    : "👤 Myself",
        "other"   : "👥 Someone else",
    }
}

def lang(uid) -> str:
    return get_user(uid).get("lang", "uz")

def tx(uid, key: str) -> str:
    return L[lang(uid)].get(key, L["uz"].get(key, key))

# ═══════════════════════════════════════
# STATES
# ═══════════════════════════════════════
class OS(StatesGroup):
    username    = State()
    stars_input = State()
    promo_input = State()

class TS(StatesGroup):
    amount  = State()
    receipt = State()

class AS(StatesGroup):
    card_number    = State()
    card_name      = State()
    markup         = State()
    min_stars      = State()
    channel        = State()
    logs           = State()
    broadcast      = State()
    promo_code     = State()
    promo_disc     = State()
    promo_limit    = State()
    admin_id       = State()
    ban_id         = State()
    ref_bonus      = State()
    lock_min       = State()
    prem_price     = State()
    stars_price    = State()

# ═══════════════════════════════════════
# KLAVIATURA
# ═══════════════════════════════════════
def main_kb(uid) -> ReplyKeyboardMarkup:
    d = db(); l = lang(uid); s = d["settings"]
    rows = [
        [KeyboardButton(text=L[l]["premium"]), KeyboardButton(text=L[l]["stars"])],
        [KeyboardButton(text=L[l]["balance"]), KeyboardButton(text=L[l]["history"])],
        [KeyboardButton(text=L[l]["topup"])],
    ]
    extra = []
    if s.get("referral_active"): extra.append(KeyboardButton(text=L[l]["referral"]))
    if s.get("promo_active"):    extra.append(KeyboardButton(text=L[l]["promo"]))
    if extra: rows.append(extra)
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

def recip_kb(uid) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=tx(uid, "self"),  callback_data="rec_self"),
        InlineKeyboardButton(text=tx(uid, "other"), callback_data="rec_other"),
    ]])

# ═══════════════════════════════════════
# YORDAMCHI
# ═══════════════════════════════════════
async def send_log(text: str):
    d = db(); ch = d["settings"].get("logs_channel")
    if ch:
        try: await bot.send_message(ch, text, parse_mode="HTML")
        except: pass

async def notify_admins(text: str, kb=None, photo=None):
    d = db()
    admins = [SUPER_ADMIN_ID] + [int(a) for a in d.get("admins", {}).keys()]
    for aid in admins:
        try:
            if photo: await bot.send_photo(aid, photo, caption=text, reply_markup=kb, parse_mode="HTML")
            else: await bot.send_message(aid, text, reply_markup=kb, parse_mode="HTML")
        except: pass

async def check_sub(uid: int) -> bool:
    d = db()
    for ch in d["settings"]["required_channels"]:
        try:
            m = await bot.get_chat_member(ch, uid)
            if m.status in ["left", "kicked"]: return False
        except: pass
    return True

# ═══════════════════════════════════════
# START
# ═══════════════════════════════════════
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
                try: await bot.send_message(int(ref_id), f"🎉 Yangi referral! +{fmt(bonus)} so'm!")
                except: pass
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
    l = cb.data[5:]; set_user(cb.from_user.id, {"lang": l})
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

# ═══════════════════════════════════════
# BALANS
# ═══════════════════════════════════════
@dp.message(F.text.in_(["💰 Balans", "💰 Баланс", "💰 Balance"]))
async def cmd_balance(msg: types.Message):
    u   = get_user(msg.from_user.id)
    bal = u.get("balance", 0)
    kb  = InlineKeyboardMarkup(inline_keyboard=[[
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

# ═══════════════════════════════════════
# HISOB TO'LDIRISH
# ═══════════════════════════════════════
@dp.message(F.text.in_(["➕ Hisob to'ldirish", "➕ Пополнить", "➕ Top up"]))
async def cmd_topup(msg: types.Message, state: FSMContext):
    d = db()
    if not d["settings"]["cards"]:
        await msg.answer("❌ Hozirda to'lov qabul qilinmayapti.")
        return
    await msg.answer(
        "💰 <b>Hisob to'ldirish</b>\n\nQancha so'm?\n<i>Minimum: 5 000 so'm</i>",
        parse_mode="HTML", reply_markup=cancel_kb(msg.from_user.id)
    )
    await state.set_state(TS.amount)

@dp.message(TS.amount)
async def topup_amount(msg: types.Message, state: FSMContext):
    if msg.text in ["❌ Bekor", "❌ Отмена", "❌ Cancel"]:
        await state.clear(); await msg.answer("🏠", reply_markup=main_kb(msg.from_user.id)); return
    try:
        amount = int(msg.text.replace(" ", "").replace(",", ""))
        if amount < 5000:
            await msg.answer("❌ Minimum 5 000 so'm!"); return
        d = db()
        # Kartalar — raqam va ism familiya
        cards_text = ""
        for c in d["settings"]["cards"]:
            if isinstance(c, dict):
                cards_text += f"💳 <code>{c['number']}</code>\n👤 <b>{c['name']}</b>\n\n"
            else:
                cards_text += f"💳 <code>{c}</code>\n\n"
        await state.update_data(amount=amount)
        await msg.answer(
            f"💳 <b>To'lov ma'lumotlari:</b>\n\n"
            f"{cards_text}"
            f"<code>━━━━━━━━━━━━━━━━</code>\n"
            f"💰 Miqdor: <b>{fmt(amount)} so'm</b>\n"
            f"<code>━━━━━━━━━━━━━━━━</code>\n\n"
            f"✅ To'lovdan so'ng <b>chek (screenshot)</b> yuboring:",
            parse_mode="HTML", reply_markup=cancel_kb(msg.from_user.id)
        )
        await state.set_state(TS.receipt)
    except:
        await msg.answer("❌ Faqat raqam kiriting!")

@dp.message(TS.receipt)
async def topup_receipt(msg: types.Message, state: FSMContext):
    if msg.text in ["❌ Bekor", "❌ Отмена", "❌ Cancel"]:
        await state.clear(); await msg.answer("🏠", reply_markup=main_kb(msg.from_user.id)); return
    if not msg.photo:
        await msg.answer("📸 Chek rasmini yuboring!"); return
    data = await state.get_data(); amount = data["amount"]; uid = msg.from_user.id
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"tok_{uid}_{amount}"),
        InlineKeyboardButton(text="❌ Rad etish",  callback_data=f"tno_{uid}"),
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
    parts = cb.data.split("_"); uid, amount = int(parts[1]), int(parts[2])
    d = db(); suid = str(uid)
    if suid in d["users"]:
        d["users"][suid]["balance"] = d["users"][suid].get("balance", 0) + amount
        sdb(d)
    bal = d["users"].get(suid, {}).get("balance", 0)
    await bot.send_message(uid,
        f"✅ <b>Balansingiz to'ldirildi!</b>\n\n"
        f"➕ <b>+{fmt(amount)} so'm</b>\n"
        f"💰 Joriy: <b>{fmt(bal)} so'm</b>",
        parse_mode="HTML"
    )
    await cb.message.edit_caption(
        caption=cb.message.caption + f"\n\n✅ Tasdiqlandi — {cb.from_user.full_name}",
        parse_mode="HTML"
    )
    await send_log(f"✅ Balans +{fmt(amount)} so'm | ID: {uid}")

@dp.callback_query(F.data.startswith("tno_"))
async def topup_no(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): return
    uid = int(cb.data.split("_")[1])
    await bot.send_message(uid, "❌ To'lovingiz tasdiqlanmadi.")
    await cb.message.edit_caption(
        caption=cb.message.caption + f"\n\n❌ Rad etildi — {cb.from_user.full_name}",
        parse_mode="HTML"
    )

# ═══════════════════════════════════════
# PREMIUM GIFT
# ═══════════════════════════════════════
@dp.message(F.text.in_(["⭐ Premium Gift"]))
async def cmd_premium(msg: types.Message, state: FSMContext):
    await state.update_data(service="premium")
    d = db(); lock = d["settings"].get("price_lock_min", 15)

    # Narxlar faqat UZS da (TON ko'rsatilmaydi)
    t3, p3, _ = get_prem_uzs(3)
    t6, p6, _ = get_prem_uzs(6)
    t12,p12,_ = get_prem_uzs(12)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"3 oy — {fmt(p3)} so'm",    callback_data="pm_3")],
        [InlineKeyboardButton(text=f"6 oy — {fmt(p6)} so'm 🔥", callback_data="pm_6")],
        [InlineKeyboardButton(text=f"12 oy — {fmt(p12)} so'm",  callback_data="pm_12")],
    ])
    await msg.answer(
        f"⭐ <b>Telegram Premium Gift</b>\n\n"
        f"<code>━━━━━━━━━━━━━━━━</code>\n"
        f"Muddatni tanlang:\n\n"
        f"🔒 <i>Narx {lock} daqiqa qotib qoladi</i>",
        parse_mode="HTML", reply_markup=kb
    )
    await state.update_data(prices={"3": p3, "6": p6, "12": p12, "ton3": t3, "ton6": t6, "ton12": t12})

@dp.callback_query(F.data.startswith("pm_"))
async def cb_pm(cb: types.CallbackQuery, state: FSMContext):
    months = cb.data[3:]
    data   = await state.get_data()
    prices = data.get("prices", {})
    uzs    = prices.get(months) or get_prem_uzs(int(months))[1]
    ton    = prices.get(f"ton{months}") or get_prem_uzs(int(months))[0]

    await state.update_data(months=int(months), price=uzs, ton=ton, locked_at=time.time())
    await cb.message.delete()
    await cb.message.answer(
        f"⭐ <b>Premium {months} oy</b>\n"
        f"💰 Narx: <b>{fmt(uzs)} so'm</b>\n\n"
        f"Kimga yuboramiz?",
        parse_mode="HTML", reply_markup=recip_kb(cb.from_user.id)
    )

# ═══════════════════════════════════════
# STARS
# ═══════════════════════════════════════
@dp.message(F.text.in_(["🌟 Stars"]))
async def cmd_stars(msg: types.Message, state: FSMContext):
    await state.update_data(service="stars")
    d = db(); min_s = d["settings"]["min_stars"]; lock = d["settings"].get("price_lock_min", 15)

    counts = [50, 100, 250, 500, 1000]
    prices = {}
    for c in counts:
        _, uzs, _ = get_stars_uzs(c)
        prices[c] = uzs

    btns = []
    row  = []
    for c in counts:
        row.append(InlineKeyboardButton(
            text=f"⭐ {c} — {fmt(prices[c])} so'm",
            callback_data=f"st_{c}"
        ))
        if len(row) == 2:
            btns.append(row); row = []
    if row: btns.append(row)
    btns.append([InlineKeyboardButton(text="✏️ Boshqa miqdor", callback_data="st_custom")])

    await msg.answer(
        f"🌟 <b>Telegram Stars</b>\n\n"
        f"<code>━━━━━━━━━━━━━━━━</code>\n"
        f"Miqdorni tanlang:\n\n"
        f"🔒 <i>Narx {lock} daqiqa qotib qoladi</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=btns)
    )
    await state.update_data(star_prices=prices)

@dp.callback_query(F.data.startswith("st_"))
async def cb_st(cb: types.CallbackQuery, state: FSMContext):
    val  = cb.data[3:]
    data = await state.get_data()

    if val == "custom":
        d = db(); min_s = d["settings"]["min_stars"]
        await cb.message.edit_text(
            f"🌟 Nechta Stars?\n\n<i>Minimum: {min_s}</i>",
            parse_mode="HTML"
        )
        await state.set_state(OS.stars_input)
        return

    count = int(val)
    prices = data.get("star_prices", {})
    uzs   = prices.get(count) or get_stars_uzs(count)[1]
    ton   = get_stars_uzs(count)[0]

    await state.update_data(stars=count, price=uzs, ton=ton, locked_at=time.time())
    await cb.message.delete()
    await cb.message.answer(
        f"🌟 <b>{fmt(count)} Stars</b>\n"
        f"💰 Narx: <b>{fmt(uzs)} so'm</b>\n\n"
        f"Kimga yuboramiz?",
        parse_mode="HTML", reply_markup=recip_kb(cb.from_user.id)
    )

@dp.message(OS.stars_input)
async def enter_stars(msg: types.Message, state: FSMContext):
    if msg.text in ["❌ Bekor", "❌ Отмена", "❌ Cancel"]:
        await state.clear(); await msg.answer("🏠", reply_markup=main_kb(msg.from_user.id)); return
    d = db(); min_s = d["settings"]["min_stars"]
    try:
        count = int(msg.text.replace(" ", ""))
        if count < min_s:
            await msg.answer(f"❌ Minimum <b>{min_s}</b> Stars!", parse_mode="HTML"); return
        ton, uzs, _ = get_stars_uzs(count)
        await state.update_data(stars=count, price=uzs, ton=ton, locked_at=time.time())
        await msg.answer(
            f"🌟 <b>{fmt(count)} Stars</b>\n"
            f"💰 Narx: <b>{fmt(uzs)} so'm</b>\n\n"
            f"Kimga yuboramiz?",
            parse_mode="HTML", reply_markup=recip_kb(msg.from_user.id)
        )
    except:
        await msg.answer("❌ Faqat raqam!")

# ═══════════════════════════════════════
# RECIPIENT
# ═══════════════════════════════════════
@dp.callback_query(F.data == "rec_self")
async def rec_self(cb: types.CallbackQuery, state: FSMContext):
    if not cb.from_user.username:
        await cb.answer("❌ Username ingiz yo'q! Telegram sozlamalaridan o'rnating.", show_alert=True); return
    await state.update_data(username=cb.from_user.username)
    await cb.message.delete()
    await show_confirm(cb.message, state, cb.from_user.id)

@dp.callback_query(F.data == "rec_other")
async def rec_other(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.edit_text("👤 <b>Username kiriting:</b>\n\n<i>@username yoki username</i>", parse_mode="HTML")
    await state.set_state(OS.username)

@dp.message(OS.username)
async def enter_username(msg: types.Message, state: FSMContext):
    if msg.text in ["❌ Bekor", "❌ Отмена", "❌ Cancel"]:
        await state.clear(); await msg.answer("🏠", reply_markup=main_kb(msg.from_user.id)); return
    await state.update_data(username=msg.text.strip().lstrip("@"))
    await show_confirm(msg, state, msg.from_user.id)

# ═══════════════════════════════════════
# TASDIQLASH
# ═══════════════════════════════════════
async def show_confirm(msg, state, uid):
    data      = await state.get_data()
    d         = db()
    bal       = d["users"].get(str(uid), {}).get("balance", 0)
    price     = data.get("price", 0)
    uname     = data.get("username", "?")
    svc       = data.get("service", "")
    locked_at = data.get("locked_at", time.time())

    ok, remaining = price_lock_ok(locked_at)
    if not ok:
        # Narx yangilash
        if svc == "premium":
            ton, price, la = get_prem_uzs(data.get("months", 3))
            await state.update_data(price=price, ton=ton, locked_at=la)
        else:
            ton, price, la = get_stars_uzs(data.get("stars", 50))
            await state.update_data(price=price, ton=ton, locked_at=la)
        note = "⚠️ <i>Narx yangilandi (muddati tugagan edi)</i>\n\n"
    else:
        note = f"🔒 <i>Narx {remaining} daqiqa davomida qotib turibdi</i>\n\n"

    svc_txt = {
        "premium": f"⭐ Premium {data.get('months', 3)} oy",
        "stars"  : f"🌟 {fmt(data.get('stars', 50))} Stars",
    }.get(svc, svc)

    enough = bal >= price
    status = ("✅ Balans yetarli" if enough
              else f"❌ Balans yetarli emas!\nKerak: <b>{fmt(price)}</b> | Sizda: <b>{fmt(bal)}</b> so'm")

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data="ord_ok"),
        InlineKeyboardButton(text="❌ Bekor",      callback_data="ord_no"),
    ]])
    await msg.answer(
        f"📋 <b>Buyurtma tasdiqlash</b>\n\n"
        f"{note}"
        f"<code>━━━━━━━━━━━━━━━━</code>\n"
        f"🛍 Xizmat: <b>{svc_txt}</b>\n"
        f"👤 Kimga: <b>@{uname}</b>\n"
        f"💰 To'lov: <b>{fmt(price)} so'm</b>\n"
        f"💳 Balansingiz: <b>{fmt(bal)} so'm</b>\n"
        f"<code>━━━━━━━━━━━━━━━━</code>\n"
        f"{status}",
        parse_mode="HTML", reply_markup=kb
    )

@dp.callback_query(F.data == "ord_ok")
async def order_ok(cb: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    d    = db(); uid = str(cb.from_user.id)
    bal  = d["users"].get(uid, {}).get("balance", 0)
    price = data.get("price", 0)

    # Price lock tekshiruv
    ok, _ = price_lock_ok(data.get("locked_at", time.time()))
    if not ok:
        await cb.answer("⚠️ Narx muddati tugadi! Qayta buyurtma bering.", show_alert=True)
        await state.clear()
        await cb.message.edit_text("⏰ Narx muddati tugadi. Xizmatni qaytadan tanlang.")
        return

    if bal < price:
        await cb.answer(f"❌ Balans yetarli emas!\nKerak: {fmt(price)} | Sizda: {fmt(bal)} so'm", show_alert=True)
        return

    await cb.message.edit_text("⏳ <b>Buyurtma bajarilmoqda...</b>", parse_mode="HTML")

    d["users"][uid]["balance"] -= price
    svc = data.get("service", "")
    svc_txt = {
        "premium": f"⭐ Premium {data.get('months', 3)} oy",
        "stars"  : f"🌟 {fmt(data.get('stars', 50))} Stars",
    }.get(svc, svc)

    order = {
        "id"        : len(d["orders"]) + 1,
        "user_id"   : uid,
        "service"   : svc,
        "username"  : data.get("username"),
        "months"    : data.get("months"),
        "stars"     : data.get("stars"),
        "price"     : price,
        "ton"       : data.get("ton"),
        "status"    : "processing",
        "created_at": datetime.now().isoformat(),
    }
    d["orders"].append(order)
    d["users"][uid].setdefault("orders", []).append(order["id"])
    sdb(d)

    success = await do_fragment(order)
    d = db()

    if success:
        for o in d["orders"]:
            if o["id"] == order["id"]: o["status"] = "completed"
        sdb(d)
        await cb.message.edit_text(
            f"🎉 <b>Muvaffaqiyatli yuborildi!</b>\n\n"
            f"<code>━━━━━━━━━━━━━━━━</code>\n"
            f"🛍 {svc_txt}\n"
            f"👤 @{order['username']}\n"
            f"💰 {fmt(price)} so'm\n"
            f"<code>━━━━━━━━━━━━━━━━</code>\n\n"
            f"✨ Xarid uchun rahmat!",
            parse_mode="HTML"
        )
        await send_log(
            f"✅ #{order['id']} | {svc_txt} → @{order['username']} | {fmt(price)} so'm | ID:{uid}"
        )
    else:
        d["users"][uid]["balance"] += price
        for o in d["orders"]:
            if o["id"] == order["id"]: o["status"] = "failed"
        sdb(d)
        await cb.message.edit_text(
            "❌ <b>Xato yuz berdi!</b>\n\nBalans qaytarildi.\nAdmin bilan bog'laning.",
            parse_mode="HTML"
        )
        await send_log(f"❌ #{order['id']} | {svc_txt} → @{order['username']} | XATO")
    await state.clear()

@dp.callback_query(F.data == "ord_no")
async def order_no(cb: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text("❌ Buyurtma bekor qilindi.")

# ═══════════════════════════════════════
# FRAGMENT API
# ═══════════════════════════════════════
async def do_fragment(order: dict) -> bool:
    try:
        from FragmentAPI import SyncFragmentAPI
        api = SyncFragmentAPI(cookies=FRAGMENT_COOKIES, wallet_api_key=TON_API_KEY)
        if order["service"] == "premium":
            r = api.gift_premium(order["username"], order["months"])
        elif order["service"] == "stars":
            r = api.buy_stars(order["username"], order["stars"])
        else:
            return False
        return bool(r)
    except Exception as e:
        log.error(f"Fragment: {e}"); return False

# ═══════════════════════════════════════
# TARIX
# ═══════════════════════════════════════
@dp.message(F.text.in_(["📋 Tarix", "📋 История", "📋 History"]))
async def cmd_history(msg: types.Message):
    d = db(); uid = str(msg.from_user.id)
    orders = [o for o in d["orders"] if o["user_id"] == uid][-10:]
    if not orders:
        await msg.answer("📋 <b>Buyurtmalar tarixi</b>\n\nHali buyurtmalar yo'q.", parse_mode="HTML")
        return
    st = {"completed": "✅", "failed": "❌", "processing": "⏳"}
    sn = lambda o: {
        "premium": f"Premium {o.get('months',3)}oy",
        "stars"  : f"{fmt(o.get('stars',0))} ⭐",
    }.get(o["service"], o["service"])
    text = "📋 <b>Buyurtmalaringiz:</b>\n<code>━━━━━━━━━━━━━━━━</code>\n\n"
    for o in reversed(orders):
        text += (
            f"{st.get(o['status'],'❓')} <b>#{o['id']}</b> — {sn(o)}\n"
            f"   👤 @{o.get('username','?')} | 💰 {fmt(o['price'])} so'm\n\n"
        )
    await msg.answer(text, parse_mode="HTML")

# ═══════════════════════════════════════
# REFERRAL
# ═══════════════════════════════════════
@dp.message(F.text.in_(["👥 Referral", "👥 Реферал"]))
async def cmd_referral(msg: types.Message):
    d = db()
    if not d["settings"].get("referral_active"): return
    uid = str(msg.from_user.id); u = d["users"].get(uid, {})
    me = await bot.get_me(); link = f"https://t.me/{me.username}?start=ref_{uid}"
    bonus = d["settings"]["referral_bonus"]
    await msg.answer(
        f"👥 <b>Referral tizimi</b>\n\n"
        f"<code>━━━━━━━━━━━━━━━━</code>\n"
        f"🔗 Havola:\n<code>{link}</code>\n\n"
        f"👥 Taklif qilganlar: <b>{u.get('referrals',0)}</b>\n"
        f"💰 Jami bonus: <b>{fmt(u.get('ref_earned',0))} so'm</b>\n"
        f"🎁 Har bir do'st: <b>{fmt(bonus)} so'm</b>\n"
        f"<code>━━━━━━━━━━━━━━━━</code>",
        parse_mode="HTML"
    )

# ═══════════════════════════════════════
# PROMO KOD
# ═══════════════════════════════════════
@dp.message(F.text.in_(["🎁 Promo kod", "🎁 Промо код", "🎁 Promo code"]))
async def cmd_promo(msg: types.Message, state: FSMContext):
    d = db()
    if not d["settings"].get("promo_active"): return
    await msg.answer("🎁 <b>Promo kodingizni kiriting:</b>", parse_mode="HTML",
                     reply_markup=cancel_kb(msg.from_user.id))
    await state.set_state(OS.promo_input)

@dp.message(OS.promo_input)
async def enter_promo(msg: types.Message, state: FSMContext):
    if msg.text in ["❌ Bekor", "❌ Отмена", "❌ Cancel"]:
        await state.clear(); await msg.answer("🏠", reply_markup=main_kb(msg.from_user.id)); return
    d = db(); uid = str(msg.from_user.id); code = msg.text.strip().upper()
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
        f"✅ <b>Promo kod qo'llandi!</b>\n\n🎁 <code>{code}</code>\n📉 <b>-{promo['discount']}%</b>",
        parse_mode="HTML", reply_markup=main_kb(msg.from_user.id)
    )
    await state.clear()

# ═══════════════════════════════════════
# SOZLAMALAR
# ═══════════════════════════════════════
@dp.message(F.text.in_(["⚙️ Sozlamalar", "⚙️ Настройки", "⚙️ Settings"]))
async def cmd_settings(msg: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🇺🇿 O'zbek",   callback_data="sl_uz"),
        InlineKeyboardButton(text="🇷🇺 Русский",  callback_data="sl_ru"),
        InlineKeyboardButton(text="🇬🇧 English",  callback_data="sl_en"),
    ]])
    await msg.answer("🌐 <b>Tilni tanlang:</b>", parse_mode="HTML", reply_markup=kb)

@dp.callback_query(F.data.startswith("sl_"))
async def cb_setlang(cb: types.CallbackQuery):
    l = cb.data[3:]; set_user(cb.from_user.id, {"lang": l})
    await cb.message.delete()
    await cb.message.answer(L[l]["welcome"], parse_mode="HTML", reply_markup=main_kb(cb.from_user.id))

# ═══════════════════════════════════════
# ADMIN PANEL
# ═══════════════════════════════════════
def admin_kb(uid) -> InlineKeyboardMarkup:
    d = db(); sup = is_super(uid)
    rows = [
        [InlineKeyboardButton(text="📊 Statistika",      callback_data="adm_stats"),
         InlineKeyboardButton(text="👥 Foydalanuvchilar", callback_data="adm_users")],
        [InlineKeyboardButton(text="📋 Buyurtmalar",     callback_data="adm_orders"),
         InlineKeyboardButton(text="📢 Xabar yuborish",  callback_data="adm_broadcast")],
    ]
    if sup:
        rows += [
            [InlineKeyboardButton(text="💰 Narxlarni yangilash", callback_data="adm_prices")],
            [InlineKeyboardButton(text="💳 Kartalar",    callback_data="adm_cards"),
             InlineKeyboardButton(text="⚙️ Sozlamalar",  callback_data="adm_settings")],
            [InlineKeyboardButton(text="👑 Adminlar",    callback_data="adm_admins"),
             InlineKeyboardButton(text="📢 Kanallar",    callback_data="adm_channels")],
            [InlineKeyboardButton(text="🎁 Promo",       callback_data="adm_promos"),
             InlineKeyboardButton(text="👥 Referral",    callback_data="adm_referral")],
            [InlineKeyboardButton(
                text=f"🤖 Bot {'O\'CH ❌' if d['settings']['bot_active'] else 'YOQ ✅'}",
                callback_data="adm_toggle_bot"
            )],
        ]
    return InlineKeyboardMarkup(inline_keyboard=rows)

async def adm_text() -> str:
    d = db(); s = d["settings"]
    total = len(d["users"]); orders = len(d["orders"])
    done  = len([o for o in d["orders"] if o["status"] == "completed"])
    rev   = sum(o["price"] for o in d["orders"] if o["status"] == "completed")
    today = datetime.now().date().isoformat()
    t_rev = sum(o["price"] for o in d["orders"] if o["status"] == "completed" and o["created_at"][:10] == today)
    last  = datetime.fromtimestamp(KURS["last"]).strftime("%H:%M") if KURS["last"] else "—"

    # Fragment narxlari (admin uchun)
    pt = s["premium_ton"]; st = s["stars_ton_per_50"]

    return (
        f"👨‍💼 <b>Admin Panel — U-Gift Bot</b>\n\n"
        f"<code>━━━━━━━━━━━━━━━━</code>\n"
        f"<b>📊 Kurs ma'lumotlari:</b>\n"
        f"💎 1 TON = <b>{fmt(KURS['ton_uzs'])} so'm</b>\n"
        f"💵 1 TON = <b>${KURS['ton_usd']:.3f}</b>\n"
        f"💲 1 TON = <b>{KURS['ton_usdt']:.3f} USDT</b>\n"
        f"🕐 Yangilangan: <b>{last}</b>\n"
        f"<code>━━━━━━━━━━━━━━━━</code>\n"
        f"<b>💰 Hozirgi narxlar (TON):</b>\n"
        f"⭐ Premium 3 oy = <b>{pt.get('3', 0)} TON</b> → {fmt(calc_uzs(float(pt.get('3', 0))))} so'm\n"
        f"⭐ Premium 6 oy = <b>{pt.get('6', 0)} TON</b> → {fmt(calc_uzs(float(pt.get('6', 0))))} so'm\n"
        f"⭐ Premium 12 oy = <b>{pt.get('12', 0)} TON</b> → {fmt(calc_uzs(float(pt.get('12', 0))))} so'm\n"
        f"🌟 50 Stars = <b>{st} TON</b> → {fmt(calc_uzs(st))} so'm\n"
        f"📈 Ustiga foiz: <b>{s['markup']}%</b>\n"
        f"<code>━━━━━━━━━━━━━━━━</code>\n"
        f"👥 Foydalanuvchilar: <b>{total}</b>\n"
        f"📋 Jami: <b>{orders}</b> | ✅ <b>{done}</b>\n"
        f"<code>━━━━━━━━━━━━━━━━</code>\n"
        f"📅 Bugun: <b>{fmt(t_rev)} so'm</b>\n"
        f"💰 Jami: <b>{fmt(rev)} so'm</b>"
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

# ═══ NARXLARNI YANGILASH (admin qo'lda) ═══
@dp.callback_query(F.data == "adm_prices")
async def adm_prices(cb: types.CallbackQuery):
    if not is_super(cb.from_user.id): return
    d = db(); s = d["settings"]
    pt = s["premium_ton"]; st = s["stars_ton_per_50"]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"⭐ Premium 3oy: {pt.get('3',0)} TON",  callback_data="adm_set_p3")],
        [InlineKeyboardButton(text=f"⭐ Premium 6oy: {pt.get('6',0)} TON",  callback_data="adm_set_p6")],
        [InlineKeyboardButton(text=f"⭐ Premium 12oy: {pt.get('12',0)} TON",callback_data="adm_set_p12")],
        [InlineKeyboardButton(text=f"🌟 50 Stars: {st} TON",                callback_data="adm_set_stars")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="adm_main")],
    ])
    await cb.message.edit_text(
        f"💰 <b>Narxlarni yangilash</b>\n\n"
        f"Fragment.com dan haqiqiy TON narxlarini kiriting:\n\n"
        f"<i>Hozirgi Fragment narxlari:</i>\n"
        f"• 3 oy = <b>{pt.get('3',0)} TON</b>\n"
        f"• 6 oy = <b>{pt.get('6',0)} TON</b>\n"
        f"• 12 oy = <b>{pt.get('12',0)} TON</b>\n"
        f"• 50 Stars = <b>{st} TON</b>",
        parse_mode="HTML", reply_markup=kb
    )

@dp.callback_query(F.data.in_({"adm_set_p3", "adm_set_p6", "adm_set_p12", "adm_set_stars"}))
async def adm_set_price(cb: types.CallbackQuery, state: FSMContext):
    if not is_super(cb.from_user.id): return
    labels = {
        "adm_set_p3"   : ("Premium 3 oy", "p3"),
        "adm_set_p6"   : ("Premium 6 oy", "p6"),
        "adm_set_p12"  : ("Premium 12 oy", "p12"),
        "adm_set_stars": ("50 Stars", "stars50"),
    }
    label, key = labels[cb.data]
    await cb.message.edit_text(
        f"💎 <b>{label}</b> narxini TON da kiriting:\n\n"
        f"<i>Masalan: 9.37</i>",
        parse_mode="HTML"
    )
    await state.update_data(price_key=key)
    await state.set_state(AS.prem_price)

@dp.message(AS.prem_price)
async def enter_price(msg: types.Message, state: FSMContext):
    try:
        v    = float(msg.text.replace(",", "."))
        if v <= 0: await msg.answer("❌ Narx 0 dan katta bo'lishi kerak!"); return
        data = await state.get_data()
        key  = data.get("price_key")
        d    = db()
        if key == "stars50":
            d["settings"]["stars_ton_per_50"] = v
            label = f"50 Stars = {v} TON"
        else:
            month_key = key.replace("p", "")
            d["settings"]["premium_ton"][month_key] = v
            label = f"Premium {month_key}oy = {v} TON"
        sdb(d)
        uzs = calc_uzs(v)
        await msg.answer(
            f"✅ <b>Narx yangilandi!</b>\n\n"
            f"💎 {label}\n"
            f"💰 So'mda: <b>{fmt(uzs)} so'm</b> (foiz bilan)",
            parse_mode="HTML"
        )
        await state.clear()
        await cmd_admin(msg, state)
    except:
        await msg.answer("❌ Faqat raqam kiriting! (masalan: 9.37)")

# ═══ KARTALAR ═══
@dp.callback_query(F.data == "adm_cards")
async def adm_cards(cb: types.CallbackQuery):
    if not is_super(cb.from_user.id): return
    d = db(); cards = d["settings"]["cards"]
    ct = ""
    for c in cards:
        if isinstance(c, dict):
            ct += f"💳 <code>{c['number']}</code>\n👤 <b>{c['name']}</b>\n\n"
        else:
            ct += f"💳 <code>{c}</code>\n\n"
    if not ct: ct = "Kartalar yo'q"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Karta qo'shish",    callback_data="adm_add_card")],
        [InlineKeyboardButton(text="🗑 Hammasini o'chirish", callback_data="adm_clear_cards")],
        [InlineKeyboardButton(text="🔙 Orqaga",            callback_data="adm_main")],
    ])
    await cb.message.edit_text(f"💳 <b>Kartalar:</b>\n\n{ct}", parse_mode="HTML", reply_markup=kb)

@dp.callback_query(F.data == "adm_add_card")
async def add_card(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.edit_text(
        "💳 Karta raqamini kiriting:\n\n<i>Masalan: 8600 1234 5678 9012</i>",
        parse_mode="HTML"
    )
    await state.set_state(AS.card_number)

@dp.message(AS.card_number)
async def enter_card_number(msg: types.Message, state: FSMContext):
    await state.update_data(card_number=msg.text.strip())
    await msg.answer(
        "👤 Karta egasining ism familiyasini kiriting:\n\n<i>Masalan: Nosirov Aziz</i>",
        parse_mode="HTML"
    )
    await state.set_state(AS.card_name)

@dp.message(AS.card_name)
async def enter_card_name(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    d    = db()
    d["settings"]["cards"].append({
        "number": data["card_number"],
        "name"  : msg.text.strip()
    })
    sdb(d)
    await msg.answer(
        f"✅ Karta qo'shildi!\n\n"
        f"💳 <code>{data['card_number']}</code>\n"
        f"👤 <b>{msg.text.strip()}</b>",
        parse_mode="HTML"
    )
    await state.clear()
    await cmd_admin(msg, state)

@dp.callback_query(F.data == "adm_clear_cards")
async def clear_cards(cb: types.CallbackQuery):
    d = db(); d["settings"]["cards"] = []; sdb(d)
    await cb.answer("✅ Kartalar tozalandi!")
    await adm_cards(cb)

# ═══ BOSHQA ADMIN FUNKSIYALAR ═══
@dp.callback_query(F.data == "adm_stats")
async def cb_stats(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): return
    d = db(); today = datetime.now().date().isoformat()
    t_ord = [o for o in d["orders"] if o["created_at"][:10] == today]
    t_rev = sum(o["price"] for o in t_ord if o["status"] == "completed")
    total_rev = sum(o["price"] for o in d["orders"] if o["status"] == "completed")
    await cb.message.edit_text(
        f"📊 <b>Statistika</b>\n\n"
        f"👥 Foydalanuvchilar: <b>{len(d['users'])}</b>\n"
        f"📋 Jami: <b>{len(d['orders'])}</b>\n"
        f"✅ Bajarilgan: <b>{len([o for o in d['orders'] if o['status']=='completed'])}</b>\n"
        f"❌ Xato: <b>{len([o for o in d['orders'] if o['status']=='failed'])}</b>\n\n"
        f"📅 Bugun: <b>{len(t_ord)}</b> ta\n"
        f"💰 Bugungi: <b>{fmt(t_rev)} so'm</b>\n"
        f"💰 Jami: <b>{fmt(total_rev)} so'm</b>",
        parse_mode="HTML", reply_markup=back_kb()
    )

@dp.callback_query(F.data == "adm_users")
async def cb_users(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): return
    d = db(); total = len(d["users"]); banned = len([u for u in d["users"].values() if u.get("banned")])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚫 Bloklash", callback_data="adm_ban"),
         InlineKeyboardButton(text="✅ Ochish",   callback_data="adm_unban")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="adm_main")],
    ])
    await cb.message.edit_text(
        f"👥 <b>Foydalanuvchilar</b>\n\nJami: <b>{total}</b>\nBanlangan: <b>{banned}</b>",
        parse_mode="HTML", reply_markup=kb
    )

@dp.callback_query(F.data.in_({"adm_ban", "adm_unban"}))
async def cb_ban(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.edit_text(f"ID kiriting ({'bloklash' if cb.data=='adm_ban' else 'ochish'}):")
    await state.update_data(ban_action=cb.data); await state.set_state(AS.ban_id)

@dp.message(AS.ban_id)
async def enter_ban(msg: types.Message, state: FSMContext):
    try:
        bid = str(int(msg.text.strip()))
        if bid == str(SUPER_ADMIN_ID):
            await msg.answer("❌ Asosiy adminni o'zgartirish mumkin emas!")
            await state.clear(); return
        data = await state.get_data(); d = db()
        if bid in d["users"]:
            d["users"][bid]["banned"] = data.get("ban_action") == "adm_ban"; sdb(d)
            await msg.answer(f"{'Bloklandi 🚫' if data.get('ban_action')=='adm_ban' else 'Ochildi ✅'}: <code>{bid}</code>", parse_mode="HTML")
        else: await msg.answer("❌ Foydalanuvchi topilmadi!")
        await state.clear(); await cmd_admin(msg, state)
    except: await msg.answer("❌ Noto'g'ri ID!")

@dp.callback_query(F.data == "adm_orders")
async def cb_orders(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): return
    d = db(); orders = d["orders"][-8:]
    if not orders: await cb.answer("Buyurtmalar yo'q!", show_alert=True); return
    st = {"completed": "✅", "failed": "❌", "processing": "⏳"}
    text = "📋 <b>So'nggi buyurtmalar:</b>\n<code>━━━━━━━━━━━━━━━━</code>\n\n"
    for o in reversed(orders):
        svc = {"premium": f"P{o.get('months',3)}oy", "stars": f"{fmt(o.get('stars',0))}⭐"}.get(o["service"], o["service"])
        text += f"{st.get(o['status'],'❓')} <b>#{o['id']}</b> @{o.get('username','?')} — {svc} — {fmt(o['price'])} so'm\n"
    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=back_kb())

@dp.callback_query(F.data == "adm_broadcast")
async def cb_broadcast(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    await cb.message.edit_text("📢 <b>Xabar yozing:</b>", parse_mode="HTML")
    await state.set_state(AS.broadcast)

@dp.message(AS.broadcast)
async def enter_broadcast(msg: types.Message, state: FSMContext):
    d = db(); sent = failed = 0
    prog = await msg.answer(f"⏳ 0/{len(d['users'])}")
    for i, uid in enumerate(d["users"]):
        try: await bot.send_message(int(uid), f"📢 <b>Xabar:</b>\n\n{msg.text}", parse_mode="HTML"); sent += 1
        except: failed += 1
        if i % 20 == 0:
            try: await prog.edit_text(f"⏳ {i}/{len(d['users'])}")
            except: pass
        await asyncio.sleep(0.05)
    await prog.edit_text(f"✅ Yuborildi! ✅{sent} ❌{failed}")
    await state.clear(); await cmd_admin(msg, state)

@dp.callback_query(F.data == "adm_settings")
async def cb_settings(cb: types.CallbackQuery):
    if not is_super(cb.from_user.id): return
    d = db(); s = d["settings"]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"📈 Foiz: {s['markup']}%",          callback_data="adm_set_markup")],
        [InlineKeyboardButton(text=f"⭐ Min Stars: {s['min_stars']}",    callback_data="adm_set_minstars")],
        [InlineKeyboardButton(text=f"🔒 Narx qulfi: {s.get('price_lock_min',15)} daq", callback_data="adm_set_lock")],
        [InlineKeyboardButton(text=f"👥 Referral: {'✅' if s.get('referral_active') else '❌'}", callback_data="adm_toggle_ref")],
        [InlineKeyboardButton(text=f"🎁 Promo: {'✅' if s.get('promo_active') else '❌'}",       callback_data="adm_toggle_promo")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="adm_main")],
    ])
    await cb.message.edit_text("⚙️ <b>Sozlamalar</b>", parse_mode="HTML", reply_markup=kb)

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
    await cb.message.edit_text("📈 Yangi foiz (0-200):\n\n<i>Masalan: 20</i>", parse_mode="HTML")
    await state.set_state(AS.markup)

@dp.message(AS.markup)
async def enter_markup(msg: types.Message, state: FSMContext):
    try:
        v = int(msg.text)
        if v < 0 or v > 200: await msg.answer("❌ 0-200 orasida!"); return
        d = db(); d["settings"]["markup"] = v; sdb(d)
        await msg.answer(f"✅ Foiz: <b>{v}%</b>", parse_mode="HTML")
        await state.clear(); await cmd_admin(msg, state)
    except: await msg.answer("❌ Faqat raqam!")

@dp.callback_query(F.data == "adm_set_minstars")
async def set_minstars(cb: types.CallbackQuery, state: FSMContext):
    if not is_super(cb.from_user.id): return
    await cb.message.edit_text("⭐ Min Stars (min: 50):")
    await state.set_state(AS.min_stars)

@dp.message(AS.min_stars)
async def enter_minstars(msg: types.Message, state: FSMContext):
    try:
        v = int(msg.text)
        if v < 50: await msg.answer("❌ Minimum 50!"); return
        d = db(); d["settings"]["min_stars"] = v; sdb(d)
        await msg.answer(f"✅ Min Stars: <b>{v}</b>", parse_mode="HTML")
        await state.clear(); await cmd_admin(msg, state)
    except: await msg.answer("❌ Faqat raqam!")

@dp.callback_query(F.data == "adm_set_lock")
async def set_lock(cb: types.CallbackQuery, state: FSMContext):
    if not is_super(cb.from_user.id): return
    await cb.message.edit_text("🔒 Narx qulfi (5-60 daqiqa):")
    await state.set_state(AS.lock_min)

@dp.message(AS.lock_min)
async def enter_lock(msg: types.Message, state: FSMContext):
    try:
        v = int(msg.text)
        if v < 5 or v > 60: await msg.answer("❌ 5-60 orasida!"); return
        d = db(); d["settings"]["price_lock_min"] = v; sdb(d)
        await msg.answer(f"✅ Narx qulfi: <b>{v} daqiqa</b>", parse_mode="HTML")
        await state.clear(); await cmd_admin(msg, state)
    except: await msg.answer("❌ Faqat raqam!")

@dp.callback_query(F.data == "adm_channels")
async def cb_channels(cb: types.CallbackQuery):
    if not is_super(cb.from_user.id): return
    d = db(); chs = d["settings"]["required_channels"]; logs = d["settings"].get("logs_channel", "Yo'q")
    ct = "\n".join([f"• {c}" for c in chs]) if chs else "Kanallar yo'q"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Kanal qo'shish", callback_data="adm_add_ch")],
        [InlineKeyboardButton(text="📝 Logs kanali",    callback_data="adm_set_logs")],
        [InlineKeyboardButton(text="🗑 Tozalash",        callback_data="adm_clear_ch")],
        [InlineKeyboardButton(text="🔙 Orqaga",         callback_data="adm_main")],
    ])
    await cb.message.edit_text(
        f"📢 <b>Kanallar:</b>\n{ct}\n\n📝 <b>Logs:</b> {logs}",
        parse_mode="HTML", reply_markup=kb
    )

@dp.callback_query(F.data == "adm_add_ch")
async def add_ch(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.edit_text("📢 Kanal username (@channel):")
    await state.set_state(AS.channel)

@dp.message(AS.channel)
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
    await state.set_state(AS.logs)

@dp.message(AS.logs)
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
        [InlineKeyboardButton(text="➕ Qo'shish",  callback_data="adm_add_admin"),
         InlineKeyboardButton(text="➖ O'chirish", callback_data="adm_del_admin")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="adm_main")],
    ])
    await cb.message.edit_text(f"👑 <b>Adminlar:</b>\n\n{at}", parse_mode="HTML", reply_markup=kb)

@dp.callback_query(F.data.in_({"adm_add_admin", "adm_del_admin"}))
async def manage_admin(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.edit_text(f"👑 Admin ID ({'qo\'shish' if cb.data=='adm_add_admin' else 'o\'chirish'}):")
    await state.update_data(admin_action=cb.data); await state.set_state(AS.admin_id)

@dp.message(AS.admin_id)
async def enter_admin(msg: types.Message, state: FSMContext):
    try:
        aid = int(msg.text.strip())
        if aid == SUPER_ADMIN_ID:
            await msg.answer("❌ Asosiy adminni o'zgartirish mumkin emas!"); await state.clear(); return
        data = await state.get_data(); d = db()
        if data.get("admin_action") == "adm_add_admin":
            d["admins"][str(aid)] = {"added": datetime.now().isoformat()}; sdb(d)
            await msg.answer(f"✅ Admin: <code>{aid}</code>", parse_mode="HTML")
        else:
            if str(aid) in d["admins"]:
                del d["admins"][str(aid)]; sdb(d); await msg.answer(f"✅ O'chirildi: {aid}")
            else: await msg.answer("❌ Admin topilmadi!")
        await state.clear(); await cmd_admin(msg, state)
    except: await msg.answer("❌ Noto'g'ri ID!")

@dp.callback_query(F.data == "adm_promos")
async def cb_promos(cb: types.CallbackQuery):
    if not is_super(cb.from_user.id): return
    d = db(); promos = d.get("promo_codes", {})
    pt = "\n".join([f"• <code>{k}</code> — {v['discount']}% ({v.get('used',0)}/{v.get('limit','∞')})" for k, v in promos.items()]) if promos else "Yo'q"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Yaratish",  callback_data="adm_new_promo"),
         InlineKeyboardButton(text="🗑 Tozalash",  callback_data="adm_clear_promos")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="adm_main")],
    ])
    await cb.message.edit_text(f"🎁 <b>Promo kodlar:</b>\n\n{pt}", parse_mode="HTML", reply_markup=kb)

@dp.callback_query(F.data == "adm_new_promo")
async def new_promo(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.edit_text("🎁 Promo kod nomi (masalan: SALE20):")
    await state.set_state(AS.promo_code)

@dp.message(AS.promo_code)
async def enter_promo_code(msg: types.Message, state: FSMContext):
    await state.update_data(promo_code=msg.text.strip().upper())
    await msg.answer("📈 Chegirma foizi (1-90):"); await state.set_state(AS.promo_disc)

@dp.message(AS.promo_disc)
async def enter_promo_disc(msg: types.Message, state: FSMContext):
    try:
        v = int(msg.text)
        if v < 1 or v > 90: await msg.answer("❌ 1-90 orasida!"); return
        await state.update_data(promo_disc=v)
        await msg.answer("🔢 Limit (0 = cheksiz):"); await state.set_state(AS.promo_limit)
    except: await msg.answer("❌ Faqat raqam!")

@dp.message(AS.promo_limit)
async def enter_promo_limit(msg: types.Message, state: FSMContext):
    try:
        limit = int(msg.text); data = await state.get_data(); d = db()
        code  = data["promo_code"]
        d["promo_codes"][code] = {
            "discount": data["promo_disc"],
            "limit"   : limit if limit > 0 else None,
            "used"    : 0,
            "created_at": datetime.now().isoformat()
        }
        sdb(d)
        await msg.answer(f"✅ <b>Promo yaratildi!</b>\n\n🎁 <code>{code}</code>\n📈 {data['promo_disc']}%\n🔢 {limit if limit > 0 else 'Cheksiz'}", parse_mode="HTML")
        await state.clear(); await cmd_admin(msg, state)
    except: await msg.answer("❌ Faqat raqam!")

@dp.callback_query(F.data == "adm_clear_promos")
async def clear_promos(cb: types.CallbackQuery):
    d = db(); d["promo_codes"] = {}; sdb(d)
    await cb.answer("✅ Tozalandi!"); await cb_promos(cb)

@dp.callback_query(F.data == "adm_referral")
async def cb_ref_admin(cb: types.CallbackQuery):
    if not is_super(cb.from_user.id): return
    d = db(); s = d["settings"]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"👥 {'✅ Yoqilgan' if s.get('referral_active') else '❌ O\'chirilgan'}",
            callback_data="adm_toggle_ref"
        )],
        [InlineKeyboardButton(
            text=f"💰 Bonus: {fmt(s.get('referral_bonus',5000))} so'm",
            callback_data="adm_set_ref_bonus"
        )],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="adm_main")],
    ])
    await cb.message.edit_text("👥 <b>Referral tizimi</b>", parse_mode="HTML", reply_markup=kb)

@dp.callback_query(F.data == "adm_set_ref_bonus")
async def set_ref_bonus(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.edit_text("💰 Referral bonus (so'mda):")
    await state.set_state(AS.ref_bonus)

@dp.message(AS.ref_bonus)
async def enter_ref_bonus(msg: types.Message, state: FSMContext):
    try:
        v = int(msg.text); d = db(); d["settings"]["referral_bonus"] = v; sdb(d)
        await msg.answer(f"✅ Bonus: <b>{fmt(v)} so'm</b>", parse_mode="HTML")
        await state.clear(); await cmd_admin(msg, state)
    except: await msg.answer("❌ Faqat raqam!")

# ═══════════════════════════════════════
# MAIN
# ═══════════════════════════════════════
async def main():
    log.info("🚀 U-Gift Bot ishga tushmoqda...")
    await update_kurs()
    log.info(f"✅ 1 TON = {fmt(KURS['ton_uzs'])} so'm = ${KURS['ton_usd']:.3f} = {KURS['ton_usdt']:.3f} USDT")
    asyncio.create_task(kurs_loop())
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
