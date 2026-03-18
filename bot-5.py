import asyncio
import logging
import json
import os
import aiohttp
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
)
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPER_ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
TON_API_KEY = os.getenv("TON_API_KEY", "")
FRAGMENT_COOKIES = os.getenv("FRAGMENT_COOKIES", "")
WEB_URL = os.getenv("WEB_URL", "")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ═══════════════════════════════════
# DATABASE
# ═══════════════════════════════════
DB = "database.json"

def db():
    if os.path.exists(DB):
        with open(DB, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "users": {}, "orders": [], "admins": {}, "promo_codes": {},
        "settings": {
            "markup": 20, "min_stars": 50, "bot_active": True,
            "referral_active": False, "promo_active": False,
            "referral_bonus": 5000, "cards": [],
            "required_channels": [], "logs_channel": None
        }
    }

def sdb(data):
    with open(DB, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_user(uid): return db()["users"].get(str(uid), {})

def set_user(uid, data):
    d = db()
    if str(uid) not in d["users"]: d["users"][str(uid)] = {}
    d["users"][str(uid)].update(data)
    sdb(d)

def is_admin(uid): return uid == SUPER_ADMIN_ID or str(uid) in db().get("admins", {})
def is_super(uid): return uid == SUPER_ADMIN_ID
def fmt(n): return f"{int(n):,}".replace(",", " ")

# ═══════════════════════════════════
# TILLAR
# ═══════════════════════════════════
L = {
    "uz": {
        "welcome": "👋 <b>U-Gift Bot ga xush kelibsiz!</b>\n\n✨ Premium Gift, Stars va NFT yuborish xizmati.\n\n💡 Quyidagi xizmatlardan birini tanlang:",
        "premium": "⭐ Premium Gift", "stars": "🌟 Stars", "nft": "🖼 NFT",
        "balance": "💰 Balans", "history": "📋 Tarix", "topup": "➕ Hisob to'ldirish",
        "referral": "👥 Referral", "promo": "🎁 Promo kod",
        "settings": "⚙️ Sozlamalar", "webapp": "🌐 Web ilova",
        "cancel": "❌ Bekor", "self": "👤 O'zimga", "other": "👥 Boshqaga",
        "menu": "🏠 Asosiy menyu",
    },
    "ru": {
        "welcome": "👋 <b>Добро пожаловать в U-Gift Bot!</b>\n\n✨ Сервис отправки Premium Gift, Stars и NFT.\n\n💡 Выберите одну из услуг ниже:",
        "premium": "⭐ Premium Gift", "stars": "🌟 Stars", "nft": "🖼 NFT",
        "balance": "💰 Баланс", "history": "📋 История", "topup": "➕ Пополнить",
        "referral": "👥 Реферал", "promo": "🎁 Промо код",
        "settings": "⚙️ Настройки", "webapp": "🌐 Веб приложение",
        "cancel": "❌ Отмена", "self": "👤 Себе", "other": "👥 Другому",
        "menu": "🏠 Главное меню",
    },
    "en": {
        "welcome": "👋 <b>Welcome to U-Gift Bot!</b>\n\n✨ Premium Gift, Stars and NFT sending service.\n\n💡 Choose a service below:",
        "premium": "⭐ Premium Gift", "stars": "🌟 Stars", "nft": "🖼 NFT",
        "balance": "💰 Balance", "history": "📋 History", "topup": "➕ Top up",
        "referral": "👥 Referral", "promo": "🎁 Promo code",
        "settings": "⚙️ Settings", "webapp": "🌐 Web app",
        "cancel": "❌ Cancel", "self": "👤 Myself", "other": "👥 Someone else",
        "menu": "🏠 Main menu",
    }
}

def lang(uid): return get_user(uid).get("lang", "uz")
def tx(uid, key): return L[lang(uid)].get(key, L["uz"].get(key, key))

# ═══════════════════════════════════
# STATES
# ═══════════════════════════════════
class Order(StatesGroup):
    username = State(); months = State(); stars = State(); nft = State(); promo = State()

class Topup(StatesGroup):
    amount = State(); receipt = State()

class Admin(StatesGroup):
    card = State(); markup = State(); min_stars = State()
    channel = State(); logs = State(); broadcast = State()
    promo_code = State(); promo_discount = State(); promo_limit = State()
    admin_id = State(); ban_id = State(); ref_bonus = State()

# ═══════════════════════════════════
# KLAVIATURA
# ═══════════════════════════════════
def main_kb(uid):
    d = db(); s = d["settings"]; l = lang(uid)
    rows = [
        [KeyboardButton(text=L[l]["premium"]), KeyboardButton(text=L[l]["stars"])],
        [KeyboardButton(text=L[l]["nft"]), KeyboardButton(text=L[l]["balance"])],
        [KeyboardButton(text=L[l]["topup"]), KeyboardButton(text=L[l]["history"])],
    ]
    if WEB_URL and WEB_URL.startswith("https://"):
        rows.append([KeyboardButton(text=L[l]["webapp"], web_app=WebAppInfo(url=WEB_URL))])
    elif WEB_URL:
        rows.append([KeyboardButton(text=L[l]["webapp"])])
    extra = []
    if s.get("referral_active"): extra.append(KeyboardButton(text=L[l]["referral"]))
    if s.get("promo_active"): extra.append(KeyboardButton(text=L[l]["promo"]))
    if extra: rows.append(extra)
    rows.append([KeyboardButton(text=L[l]["settings"])])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

def cancel_kb(uid):
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=tx(uid, "cancel"))]], resize_keyboard=True)

def back_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔙 Orqaga", callback_data="adm_main")
    ]])

# ═══════════════════════════════════
# RATES
# ═══════════════════════════════════
_rate = {"val": 44800.0, "ts": 0}

async def get_rate():
    now = asyncio.get_event_loop().time()
    if now - _rate["ts"] < 3600: return _rate["val"]
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get("https://api.coingecko.com/api/v3/simple/price?ids=the-open-network&vs_currencies=usd",
                             timeout=aiohttp.ClientTimeout(total=5)) as r:
                td = await r.json(); ton_usd = td["the-open-network"]["usd"]
            async with s.get("https://cbu.uz/uz/arkhiv-kursov-valyut/json/USD/",
                             timeout=aiohttp.ClientTimeout(total=5)) as r:
                cd = await r.json(); usd_uzs = float(cd[0]["Rate"])
        _rate["val"] = ton_usd * usd_uzs; _rate["ts"] = now
    except: pass
    return _rate["val"]

async def calc_price(ton):
    d = db(); rate = await get_rate()
    return round(ton * rate * (1 + d["settings"]["markup"] / 100))

# ═══════════════════════════════════
# YORDAMCHILAR
# ═══════════════════════════════════
async def send_log(text):
    d = db(); ch = d["settings"].get("logs_channel")
    if ch:
        try: await bot.send_message(ch, text, parse_mode="HTML")
        except: pass

async def notify_admins(text, kb=None, photo=None):
    d = db(); admins = [SUPER_ADMIN_ID] + [int(a) for a in d.get("admins", {}).keys()]
    for aid in admins:
        try:
            if photo: await bot.send_photo(aid, photo, caption=text, reply_markup=kb, parse_mode="HTML")
            else: await bot.send_message(aid, text, reply_markup=kb, parse_mode="HTML")
        except: pass

async def check_sub(uid):
    d = db(); channels = d["settings"]["required_channels"]
    if not channels: return True
    for ch in channels:
        try:
            m = await bot.get_chat_member(ch, uid)
            if m.status in ["left", "kicked"]: return False
        except: pass
    return True

# ═══════════════════════════════════
# /START
# ═══════════════════════════════════
@dp.message(Command("start"))
async def cmd_start(msg: types.Message, state: FSMContext):
    await state.clear()
    d = db(); uid = str(msg.from_user.id)
    if not d["settings"]["bot_active"] and not is_admin(msg.from_user.id):
        await msg.answer("🔧 Bot hozirda texnik ishlar uchun o'chirilgan."); return
    if uid not in d["users"]:
        d["users"][uid] = {"lang": "uz", "balance": 0, "orders": [], "referrals": 0,
                           "ref_earned": 0, "joined": datetime.now().isoformat(),
                           "banned": False, "promo_used": []}
        args = msg.text.split()
        if len(args) > 1 and args[1].startswith("ref_"):
            ref_id = args[1][4:]
            if ref_id in d["users"] and d["settings"].get("referral_active"):
                bonus = d["settings"]["referral_bonus"]
                d["users"][ref_id]["balance"] = d["users"][ref_id].get("balance", 0) + bonus
                d["users"][ref_id]["referrals"] = d["users"][ref_id].get("referrals", 0) + 1
                d["users"][ref_id]["ref_earned"] = d["users"][ref_id].get("ref_earned", 0) + bonus
                try: await bot.send_message(int(ref_id), f"🎉 Yangi referral! +{fmt(bonus)} so'm!\n💰 Balans: {fmt(d['users'][ref_id]['balance'])} so'm")
                except: pass
        sdb(d)
    d = db()
    if d["users"][uid].get("banned"):
        await msg.answer("🚫 Siz botdan bloklangansiz."); return
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

# ═══════════════════════════════════
# BALANS
# ═══════════════════════════════════
@dp.message(F.text.in_(["💰 Balans", "💰 Баланс", "💰 Balance"]))
async def cmd_balance(msg: types.Message):
    u = get_user(msg.from_user.id); bal = u.get("balance", 0)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="➕ To'ldirish", callback_data="go_topup")
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

# ═══════════════════════════════════
# HISOB TO'LDIRISH
# ═══════════════════════════════════
@dp.message(F.text.in_(["➕ Hisob to'ldirish", "➕ Пополнить", "➕ Top up"]))
async def cmd_topup(msg: types.Message, state: FSMContext):
    d = db()
    if not d["settings"]["cards"]:
        await msg.answer("❌ Hozirda to'lov qabul qilinmayapti."); return
    await msg.answer(
        "💰 <b>Hisob to'ldirish</b>\n\n"
        "Qancha so'm kiritmoqchisiz?\n"
        "<i>Minimum: 1 000 so'm</i>",
        parse_mode="HTML", reply_markup=cancel_kb(msg.from_user.id)
    )
    await state.set_state(Topup.amount)

@dp.message(Topup.amount)
async def topup_amount(msg: types.Message, state: FSMContext):
    if msg.text in ["❌ Bekor", "❌ Отмена", "❌ Cancel"]:
        await state.clear(); await msg.answer("🏠", reply_markup=main_kb(msg.from_user.id)); return
    try:
        amount = int(msg.text.replace(" ", "").replace(",", ""))
        if amount < 1000:
            await msg.answer("❌ Minimum 1 000 so'm!"); return
        d = db(); cards = "\n".join([f"💳 <code>{c}</code>" for c in d["settings"]["cards"]])
        await state.update_data(amount=amount)
        await msg.answer(
            f"💳 <b>To'lov ma'lumotlari</b>\n\n"
            f"{cards}\n\n"
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
        await state.clear(); await msg.answer("🏠", reply_markup=main_kb(msg.from_user.id)); return
    if not msg.photo:
        await msg.answer("📸 Iltimos chek rasmini yuboring!"); return
    data = await state.get_data(); amount = data["amount"]; uid = msg.from_user.id
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"tok_{uid}_{amount}"),
        InlineKeyboardButton(text="❌ Rad etish", callback_data=f"tno_{uid}"),
    ]])
    await notify_admins(
        f"💳 <b>Balans to'ldirish so'rovi</b>\n\n"
        f"👤 {msg.from_user.full_name}\n"
        f"🆔 <code>{uid}</code>\n"
        f"📱 @{msg.from_user.username or 'username yoq'}\n"
        f"💰 <b>{fmt(amount)} so'm</b>",
        kb=kb, photo=msg.photo[-1].file_id
    )
    await msg.answer(
        "✅ <b>Chekingiz yuborildi!</b>\n\n"
        "⏳ Admin tasdiqlaguncha kuting...",
        parse_mode="HTML", reply_markup=main_kb(msg.from_user.id)
    )
    await state.clear()

@dp.callback_query(F.data.startswith("tok_"))
async def topup_ok(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): return
    parts = cb.data.split("_"); uid, amount = int(parts[1]), int(parts[2])
    d = db(); suid = str(uid)
    if suid in d["users"]:
        d["users"][suid]["balance"] = d["users"][suid].get("balance", 0) + amount; sdb(d)
    bal = d["users"].get(suid, {}).get("balance", 0)
    await bot.send_message(uid,
        f"✅ <b>Balansingiz to'ldirildi!</b>\n\n"
        f"➕ Qo'shildi: <b>{fmt(amount)} so'm</b>\n"
        f"💰 Joriy balans: <b>{fmt(bal)} so'm</b>",
        parse_mode="HTML"
    )
    await cb.message.edit_caption(caption=cb.message.caption + f"\n\n✅ <b>Tasdiqlandi</b> — {cb.from_user.full_name}", parse_mode="HTML")
    await send_log(f"✅ Balans +{fmt(amount)} so'm | ID: {uid}")

@dp.callback_query(F.data.startswith("tno_"))
async def topup_no(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): return
    uid = int(cb.data.split("_")[1])
    await bot.send_message(uid, "❌ To'lovingiz tasdiqlanmadi.\nAdmin bilan bog'laning.")
    await cb.message.edit_caption(caption=cb.message.caption + f"\n\n❌ <b>Rad etildi</b> — {cb.from_user.full_name}", parse_mode="HTML")

# ═══════════════════════════════════
# XIZMATLAR
# ═══════════════════════════════════
SVC_MAP = {"⭐ Premium Gift": "premium", "🌟 Stars": "stars", "🖼 NFT": "nft"}
PREM_PRICES = {3: 3.0, 6: 5.5, 12: 10.0}

@dp.message(F.text.in_(["⭐ Premium Gift", "🌟 Stars", "🖼 NFT"]))
async def cmd_service(msg: types.Message, state: FSMContext):
    svc = SVC_MAP[msg.text]; await state.update_data(service=svc)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=tx(msg.from_user.id, "self"), callback_data="rec_self"),
        InlineKeyboardButton(text=tx(msg.from_user.id, "other"), callback_data="rec_other"),
    ]])
    icons = {"premium": "⭐", "stars": "🌟", "nft": "🖼"}
    await msg.answer(f"{icons[svc]} <b>Kimga yuboramiz?</b>", parse_mode="HTML", reply_markup=kb)

@dp.callback_query(F.data == "rec_self")
async def rec_self(cb: types.CallbackQuery, state: FSMContext):
    if not cb.from_user.username:
        await cb.answer("❌ Telegram username ingiz yo'q! Sozlamalarda o'rnating.", show_alert=True); return
    await state.update_data(username=cb.from_user.username)
    await cb.message.delete()
    data = await state.get_data()
    await ask_details(cb.message, state, data["service"], cb.from_user.id)

@dp.callback_query(F.data == "rec_other")
async def rec_other(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.edit_text("👤 <b>Username kiriting:</b>\n\n<i>Masalan: @username</i>", parse_mode="HTML")
    await state.set_state(Order.username)

@dp.message(Order.username)
async def enter_username(msg: types.Message, state: FSMContext):
    if msg.text in ["❌ Bekor", "❌ Отмена", "❌ Cancel"]:
        await state.clear(); await msg.answer("🏠", reply_markup=main_kb(msg.from_user.id)); return
    await state.update_data(username=msg.text.strip().lstrip("@"))
    data = await state.get_data()
    await ask_details(msg, state, data["service"], msg.from_user.id)

async def ask_details(msg, state, svc, uid):
    d = db()
    if svc == "premium":
        p3, p6, p12 = await calc_price(3.0), await calc_price(5.5), await calc_price(10.0)
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=f"3 oy — {fmt(p3)} so'm", callback_data="m_3"),
        ], [
            InlineKeyboardButton(text=f"6 oy — {fmt(p6)} so'm 🔥", callback_data="m_6"),
        ], [
            InlineKeyboardButton(text=f"12 oy — {fmt(p12)} so'm", callback_data="m_12"),
        ]])
        await msg.answer("⭐ <b>Premium muddatini tanlang:</b>", parse_mode="HTML", reply_markup=kb)
    elif svc == "stars":
        min_s = d["settings"]["min_stars"]
        await msg.answer(
            f"🌟 <b>Nechta Stars?</b>\n\n"
            f"Minimum: <b>{min_s}</b> Stars\n"
            f"<i>Masalan: 100, 250, 500...</i>",
            parse_mode="HTML", reply_markup=cancel_kb(uid)
        )
        await state.set_state(Order.stars)
    elif svc == "nft":
        await msg.answer(
            "🖼 <b>Fragment NFT linkini yuboring:</b>\n\n"
            "<i>https://fragment.com/username/...</i>",
            parse_mode="HTML", reply_markup=cancel_kb(uid)
        )
        await state.set_state(Order.nft)

@dp.callback_query(F.data.startswith("m_"))
async def cb_months(cb: types.CallbackQuery, state: FSMContext):
    months = int(cb.data[2:]); p = await calc_price(PREM_PRICES[months])
    await state.update_data(months=months, price=p, ton=PREM_PRICES[months])
    await cb.message.delete()
    await show_confirm(cb.message, state, cb.from_user.id)

@dp.message(Order.stars)
async def enter_stars(msg: types.Message, state: FSMContext):
    if msg.text in ["❌ Bekor", "❌ Отмена", "❌ Cancel"]:
        await state.clear(); await msg.answer("🏠", reply_markup=main_kb(msg.from_user.id)); return
    d = db(); min_s = d["settings"]["min_stars"]
    try:
        stars = int(msg.text)
        if stars < min_s:
            await msg.answer(f"❌ Minimum <b>{min_s}</b> Stars kiriting!", parse_mode="HTML"); return
        p = await calc_price(stars / 50)
        await state.update_data(stars=stars, price=p, ton=stars/50)
        await show_confirm(msg, state, msg.from_user.id)
    except:
        await msg.answer("❌ Faqat raqam kiriting!")

@dp.message(Order.nft)
async def enter_nft(msg: types.Message, state: FSMContext):
    if msg.text in ["❌ Bekor", "❌ Отмена", "❌ Cancel"]:
        await state.clear(); await msg.answer("🏠", reply_markup=main_kb(msg.from_user.id)); return
    if "fragment.com" not in msg.text:
        await msg.answer("❌ <b>fragment.com</b> dan link yuboring!", parse_mode="HTML"); return
    await msg.answer("⏳ NFT narxi aniqlanmoqda...")
    try:
        from FragmentAPI import SyncFragmentAPI
        api = SyncFragmentAPI(cookies=FRAGMENT_COOKIES, wallet_api_key=TON_API_KEY)
        nft = api.get_nft_info(msg.text)
        ton_p = nft.price if hasattr(nft, 'price') else 5.0
        nft_name = nft.name if hasattr(nft, 'name') else "NFT"
    except:
        ton_p = 5.0; nft_name = "NFT"
    p = await calc_price(ton_p)
    await state.update_data(nft_link=msg.text, price=p, ton=ton_p, nft_name=nft_name)
    await show_confirm(msg, state, msg.from_user.id)

async def show_confirm(msg, state, uid):
    data = await state.get_data(); d = db()
    bal = d["users"].get(str(uid), {}).get("balance", 0)
    p = data.get("price", 0); uname = data.get("username", "?"); svc = data.get("service", "")
    svc_txt = {
        "premium": f"⭐ Premium {data.get('months',3)} oy",
        "stars": f"🌟 {data.get('stars',50)} Stars",
        "nft": f"🖼 {data.get('nft_name','NFT')}"
    }.get(svc, svc)
    enough = bal >= p
    status = "✅ Balans yetarli" if enough else f"❌ Balans yetarli emas!\nKerak: <b>{fmt(p)}</b> | Sizda: <b>{fmt(bal)}</b>"
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data="ord_ok"),
        InlineKeyboardButton(text="❌ Bekor", callback_data="ord_no"),
    ]])
    await msg.answer(
        f"📋 <b>Buyurtma tasdiqlash</b>\n\n"
        f"<code>━━━━━━━━━━━━━━━━</code>\n"
        f"🛍 Xizmat: <b>{svc_txt}</b>\n"
        f"👤 Kimga: <b>@{uname}</b>\n"
        f"💰 Narx: <b>{fmt(p)} so'm</b>\n"
        f"💳 Balansingiz: <b>{fmt(bal)} so'm</b>\n"
        f"<code>━━━━━━━━━━━━━━━━</code>\n"
        f"{status}",
        parse_mode="HTML", reply_markup=kb
    )

@dp.callback_query(F.data == "ord_ok")
async def order_ok(cb: types.CallbackQuery, state: FSMContext):
    data = await state.get_data(); d = db(); uid = str(cb.from_user.id)
    bal = d["users"].get(uid, {}).get("balance", 0); p = data.get("price", 0)
    if bal < p:
        await cb.answer("❌ Balans yetarli emas!", show_alert=True); return
    await cb.message.edit_text("⏳ <b>Buyurtma bajarilmoqda...</b>\n\nIltimos kuting ☕", parse_mode="HTML")
    d["users"][uid]["balance"] -= p
    order = {
        "id": len(d["orders"]) + 1, "user_id": uid,
        "service": data.get("service"), "username": data.get("username"),
        "months": data.get("months"), "stars": data.get("stars"),
        "nft_link": data.get("nft_link"), "nft_name": data.get("nft_name"),
        "price": p, "ton": data.get("ton"), "status": "processing",
        "created_at": datetime.now().isoformat()
    }
    d["orders"].append(order); d["users"][uid].setdefault("orders", []).append(order["id"]); sdb(d)
    success = await fragment_send(order); d = db()
    svc_txt = {
        "premium": f"⭐ Premium {order.get('months',3)} oy",
        "stars": f"🌟 {order.get('stars',50)} Stars",
        "nft": f"🖼 {order.get('nft_name','NFT')}"
    }.get(order["service"], order["service"])
    if success:
        for o in d["orders"]:
            if o["id"] == order["id"]: o["status"] = "completed"
        sdb(d)
        await cb.message.edit_text(
            f"🎉 <b>Muvaffaqiyatli yuborildi!</b>\n\n"
            f"<code>━━━━━━━━━━━━━━━━</code>\n"
            f"🛍 {svc_txt}\n"
            f"👤 @{order['username']}\n"
            f"💰 {fmt(p)} so'm\n"
            f"<code>━━━━━━━━━━━━━━━━</code>\n\n"
            f"✨ Xarid uchun rahmat!",
            parse_mode="HTML"
        )
        await send_log(f"✅ #{order['id']} | {svc_txt} → @{order['username']} | {fmt(p)} so'm")
    else:
        d["users"][uid]["balance"] += p
        for o in d["orders"]:
            if o["id"] == order["id"]: o["status"] = "failed"
        sdb(d)
        await cb.message.edit_text(
            "❌ <b>Xato yuz berdi!</b>\n\n"
            "Balans qaytarildi. Admin bilan bog'laning.",
            parse_mode="HTML"
        )
        await send_log(f"❌ #{order['id']} | {svc_txt} → @{order['username']} | XATO")
    await state.clear()

@dp.callback_query(F.data == "ord_no")
async def order_no(cb: types.CallbackQuery, state: FSMContext):
    await state.clear(); await cb.message.edit_text("❌ Buyurtma bekor qilindi.")

# ═══════════════════════════════════
# FRAGMENT API
# ═══════════════════════════════════
async def fragment_send(order):
    try:
        from FragmentAPI import SyncFragmentAPI
        api = SyncFragmentAPI(cookies=FRAGMENT_COOKIES, wallet_api_key=TON_API_KEY)
        if order["service"] == "premium": r = api.buy_premium(order["username"], order["months"])
        elif order["service"] == "stars": r = api.buy_stars(order["username"], order["stars"])
        elif order["service"] == "nft": r = api.buy_nft(order["nft_link"])
        else: return False
        return bool(r)
    except Exception as e:
        log.error(f"Fragment: {e}"); return False

# ═══════════════════════════════════
# TARIX
# ═══════════════════════════════════
@dp.message(F.text.in_(["📋 Tarix", "📋 История", "📋 History"]))
async def cmd_history(msg: types.Message):
    d = db(); uid = str(msg.from_user.id)
    orders = [o for o in d["orders"] if o["user_id"] == uid][-10:]
    if not orders:
        await msg.answer("📋 Hali buyurtmalar yo'q.\n\nXizmatlardan birini tanlang! 👆"); return
    st = {"completed": "✅", "failed": "❌", "processing": "⏳"}
    svc_n = lambda o: {"premium": f"Premium {o.get('months',3)}oy", "stars": f"{o.get('stars',0)}⭐", "nft": "NFT"}.get(o["service"], o["service"])
    text = "📋 <b>Buyurtmalaringiz:</b>\n<code>━━━━━━━━━━━━━━━━</code>\n\n"
    for o in reversed(orders):
        text += f"{st.get(o['status'],'❓')} <b>#{o['id']}</b> — {svc_n(o)} — {fmt(o['price'])} so'm\n"
    await msg.answer(text, parse_mode="HTML")

# ═══════════════════════════════════
# WEB ILOVA
# ═══════════════════════════════════
@dp.message(F.text.in_(["🌐 Web ilova", "🌐 Веб приложение", "🌐 Web app"]))
async def cmd_webapp(msg: types.Message):
    if WEB_URL and WEB_URL.startswith("https://"):
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🌐 Web ilovani ochish", web_app=WebAppInfo(url=WEB_URL))
        ]])
    elif WEB_URL:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🌐 Web ilovani ochish", url=WEB_URL)
        ]])
    else:
        await msg.answer("⚙️ Web ilova hali sozlanmagan."); return
    await msg.answer("🌐 <b>Web ilova</b>\n\nTo'liq funksional interfeys:", parse_mode="HTML", reply_markup=kb)

# ═══════════════════════════════════
# REFERRAL
# ═══════════════════════════════════
@dp.message(F.text.in_(["👥 Referral", "👥 Реферал"]))
async def cmd_referral(msg: types.Message):
    d = db()
    if not d["settings"].get("referral_active"): return
    uid = str(msg.from_user.id); u = d["users"].get(uid, {})
    me = await bot.get_me(); link = f"https://t.me/{me.username}?start=ref_{uid}"
    bonus = d["settings"]["referral_bonus"]
    await msg.answer(
        f"👥 <b>Referral tizimi</b>\n\n"
        f"Do'stlarni taklif qiling va bonus oling!\n\n"
        f"<code>━━━━━━━━━━━━━━━━</code>\n"
        f"🔗 Sizning havolangiz:\n<code>{link}</code>\n\n"
        f"👥 Taklif qilganlar: <b>{u.get('referrals',0)}</b>\n"
        f"💰 Jami bonus: <b>{fmt(u.get('ref_earned',0))} so'm</b>\n"
        f"🎁 Har bir do'st uchun: <b>{fmt(bonus)} so'm</b>\n"
        f"<code>━━━━━━━━━━━━━━━━</code>",
        parse_mode="HTML"
    )

# ═══════════════════════════════════
# PROMO KOD
# ═══════════════════════════════════
@dp.message(F.text.in_(["🎁 Promo kod", "🎁 Промо код", "🎁 Promo code"]))
async def cmd_promo(msg: types.Message, state: FSMContext):
    d = db()
    if not d["settings"].get("promo_active"): return
    await msg.answer("🎁 <b>Promo kodingizni kiriting:</b>", parse_mode="HTML", reply_markup=cancel_kb(msg.from_user.id))
    await state.set_state(Order.promo)

@dp.message(Order.promo)
async def enter_promo(msg: types.Message, state: FSMContext):
    if msg.text in ["❌ Bekor", "❌ Отмена", "❌ Cancel"]:
        await state.clear(); await msg.answer("🏠", reply_markup=main_kb(msg.from_user.id)); return
    d = db(); uid = str(msg.from_user.id); code = msg.text.strip().upper()
    promos = d.get("promo_codes", {})
    if code not in promos:
        await msg.answer("❌ Noto'g'ri promo kod!", reply_markup=main_kb(msg.from_user.id)); await state.clear(); return
    promo = promos[code]
    if promo.get("limit") and promo.get("used", 0) >= promo["limit"]:
        await msg.answer("❌ Bu promo kodning limiti tugagan!", reply_markup=main_kb(msg.from_user.id)); await state.clear(); return
    if code in d["users"].get(uid, {}).get("promo_used", []):
        await msg.answer("❌ Bu promo kodni allaqachon ishlatgansiz!", reply_markup=main_kb(msg.from_user.id)); await state.clear(); return
    await msg.answer(
        f"✅ <b>Promo kod qo'llandi!</b>\n\n"
        f"🎁 Kod: <code>{code}</code>\n"
        f"📉 Chegirma: <b>-{promo['discount']}%</b>",
        parse_mode="HTML", reply_markup=main_kb(msg.from_user.id)
    )
    await state.clear()

# ═══════════════════════════════════
# SOZLAMALAR
# ═══════════════════════════════════
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
    l = cb.data[3:]; set_user(cb.from_user.id, {"lang": l})
    await cb.message.delete()
    await cb.message.answer(L[l]["welcome"], parse_mode="HTML", reply_markup=main_kb(cb.from_user.id))

# ═══════════════════════════════════
# ADMIN PANEL
# ═══════════════════════════════════
def admin_kb(uid):
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
            [InlineKeyboardButton(text=f"🤖 Bot {'O\'CHIRISH ❌' if d['settings']['bot_active'] else 'YOQISH ✅'}", callback_data="adm_toggle_bot")],
        ]
    if WEB_URL and WEB_URL.startswith("https://"):
        rows.append([InlineKeyboardButton(text="🌐 Web Admin Panel", web_app=WebAppInfo(url=WEB_URL + "?admin=1"))])
    elif WEB_URL:
        rows.append([InlineKeyboardButton(text="🌐 Web Admin Panel", url=WEB_URL + "?admin=1")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

async def adm_text():
    d = db(); total = len(d["users"]); orders = len(d["orders"])
    done = len([o for o in d["orders"] if o["status"] == "completed"])
    rev = sum(o["price"] for o in d["orders"] if o["status"] == "completed")
    today = datetime.now().date().isoformat()
    today_rev = sum(o["price"] for o in d["orders"] if o["status"] == "completed" and o["created_at"][:10] == today)
    return (
        f"👨‍💼 <b>Admin Panel — U-Gift Bot</b>\n\n"
        f"<code>━━━━━━━━━━━━━━━━</code>\n"
        f"👥 Foydalanuvchilar: <b>{total}</b>\n"
        f"📋 Jami buyurtmalar: <b>{orders}</b>\n"
        f"✅ Bajarilgan: <b>{done}</b>\n"
        f"<code>━━━━━━━━━━━━━━━━</code>\n"
        f"📅 Bugungi daromad: <b>{fmt(today_rev)} so'm</b>\n"
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
        f"📋 Jami buyurtmalar: <b>{len(d['orders'])}</b>\n"
        f"✅ Bajarilgan: <b>{len([o for o in d['orders'] if o['status']=='completed'])}</b>\n"
        f"❌ Xato: <b>{len([o for o in d['orders'] if o['status']=='failed'])}</b>\n"
        f"<code>━━━━━━━━━━━━━━━━</code>\n"
        f"📅 Bugun: <b>{len(t_ord)}</b> ta buyurtma\n"
        f"💰 Bugungi daromad: <b>{fmt(t_rev)} so'm</b>\n"
        f"💰 Jami daromad: <b>{fmt(total_rev)} so'm</b>\n"
        f"<code>━━━━━━━━━━━━━━━━</code>",
        parse_mode="HTML", reply_markup=back_kb()
    )

@dp.callback_query(F.data == "adm_users")
async def cb_users(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): return
    d = db(); total = len(d["users"]); banned = len([u for u in d["users"].values() if u.get("banned")])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚫 Bloklash", callback_data="adm_ban"),
         InlineKeyboardButton(text="✅ Ochish", callback_data="adm_unban")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="adm_main")],
    ])
    await cb.message.edit_text(
        f"👥 <b>Foydalanuvchilar</b>\n\n"
        f"Jami: <b>{total}</b>\n"
        f"Banlangan: <b>{banned}</b>",
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
            await msg.answer("❌ Asosiy adminni o'zgartirish mumkin emas!"); await state.clear(); return
        data = await state.get_data(); d = db()
        if bid in d["users"]:
            d["users"][bid]["banned"] = data.get("ban_action") == "adm_ban"; sdb(d)
            action = "Bloklandi 🚫" if data.get("ban_action") == "adm_ban" else "Ochildi ✅"
            await msg.answer(f"{action}: <code>{bid}</code>", parse_mode="HTML")
        else:
            await msg.answer("❌ Foydalanuvchi topilmadi!")
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
        svc = {"premium": f"P{o.get('months',3)}oy", "stars": f"{o.get('stars',0)}⭐", "nft": "NFT"}.get(o["service"], o["service"])
        text += f"{st.get(o['status'],'❓')} <b>#{o['id']}</b> @{o.get('username','?')} — {svc} — {fmt(o['price'])} so'm\n"
    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=back_kb())

@dp.callback_query(F.data == "adm_broadcast")
async def cb_broadcast(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    await cb.message.edit_text("📢 <b>Xabar yozing:</b>\n\n<i>Bu xabar barcha foydalanuvchilarga yuboriladi</i>", parse_mode="HTML")
    await state.set_state(Admin.broadcast)

@dp.message(Admin.broadcast)
async def enter_broadcast(msg: types.Message, state: FSMContext):
    d = db(); sent = failed = 0
    progress = await msg.answer(f"⏳ Yuborilmoqda... (0/{len(d['users'])})")
    for i, uid in enumerate(d["users"]):
        try: await bot.send_message(int(uid), f"📢 <b>Xabar:</b>\n\n{msg.text}", parse_mode="HTML"); sent += 1
        except: failed += 1
        if i % 20 == 0:
            try: await progress.edit_text(f"⏳ Yuborilmoqda... ({i}/{len(d['users'])})")
            except: pass
        await asyncio.sleep(0.05)
    await progress.edit_text(f"✅ <b>Xabar yuborildi!</b>\n\n✅ Muvaffaqiyatli: <b>{sent}</b>\n❌ Xato: <b>{failed}</b>", parse_mode="HTML")
    await state.clear(); await cmd_admin(msg, state)

@dp.callback_query(F.data == "adm_settings")
async def cb_settings(cb: types.CallbackQuery):
    if not is_super(cb.from_user.id): return
    d = db(); s = d["settings"]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"📈 Foiz: {s['markup']}%", callback_data="adm_set_markup")],
        [InlineKeyboardButton(text=f"⭐ Min Stars: {s['min_stars']}", callback_data="adm_set_minstars")],
        [InlineKeyboardButton(text=f"👥 Referral: {'✅ Yoqilgan' if s.get('referral_active') else '❌ O\'chirilgan'}", callback_data="adm_toggle_ref")],
        [InlineKeyboardButton(text=f"🎁 Promo kod: {'✅ Yoqilgan' if s.get('promo_active') else '❌ O\'chirilgan'}", callback_data="adm_toggle_promo")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="adm_main")],
    ])
    await cb.message.edit_text("⚙️ <b>Bot sozlamalari</b>", parse_mode="HTML", reply_markup=kb)

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
    await cb.answer(f"Referral {'yoqildi ✅' if d['settings']['referral_active'] else 'o\'chirildi ❌'}", show_alert=True)
    await cb_settings(cb)

@dp.callback_query(F.data == "adm_toggle_promo")
async def toggle_promo(cb: types.CallbackQuery):
    if not is_super(cb.from_user.id): return
    d = db(); d["settings"]["promo_active"] = not d["settings"]["promo_active"]; sdb(d)
    await cb.answer(f"Promo {'yoqildi ✅' if d['settings']['promo_active'] else 'o\'chirildi ❌'}", show_alert=True)
    await cb_settings(cb)

@dp.callback_query(F.data == "adm_set_markup")
async def set_markup(cb: types.CallbackQuery, state: FSMContext):
    if not is_super(cb.from_user.id): return
    await cb.message.edit_text("📈 Yangi foizni kiriting:\n\n<i>Masalan: 20</i>", parse_mode="HTML")
    await state.set_state(Admin.markup)

@dp.message(Admin.markup)
async def enter_markup(msg: types.Message, state: FSMContext):
    try:
        v = int(msg.text); d = db(); d["settings"]["markup"] = v; sdb(d)
        await msg.answer(f"✅ Foiz: <b>{v}%</b>", parse_mode="HTML")
        await state.clear(); await cmd_admin(msg, state)
    except: await msg.answer("❌ Faqat raqam!")

@dp.callback_query(F.data == "adm_set_minstars")
async def set_minstars(cb: types.CallbackQuery, state: FSMContext):
    if not is_super(cb.from_user.id): return
    await cb.message.edit_text("⭐ Minimum Stars kiriting:\n\n<i>Masalan: 50</i>", parse_mode="HTML")
    await state.set_state(Admin.min_stars)

@dp.message(Admin.min_stars)
async def enter_minstars(msg: types.Message, state: FSMContext):
    try:
        v = int(msg.text)
        if v < 50: await msg.answer("❌ Minimum 50 bo'lishi kerak!"); return
        d = db(); d["settings"]["min_stars"] = v; sdb(d)
        await msg.answer(f"✅ Min Stars: <b>{v}</b>", parse_mode="HTML")
        await state.clear(); await cmd_admin(msg, state)
    except: await msg.answer("❌ Faqat raqam!")

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
    await cb.message.edit_text(f"💳 <b>To'lov kartalari:</b>\n\n{ct}", parse_mode="HTML", reply_markup=kb)

@dp.callback_query(F.data == "adm_add_card")
async def add_card(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.edit_text("💳 Karta raqamini kiriting:"); await state.set_state(Admin.card)

@dp.message(Admin.card)
async def enter_card(msg: types.Message, state: FSMContext):
    d = db(); d["settings"]["cards"].append(msg.text.strip()); sdb(d)
    await msg.answer(f"✅ Karta qo'shildi: <code>{msg.text.strip()}</code>", parse_mode="HTML")
    await state.clear(); await cmd_admin(msg, state)

@dp.callback_query(F.data == "adm_clear_cards")
async def clear_cards(cb: types.CallbackQuery):
    d = db(); d["settings"]["cards"] = []; sdb(d)
    await cb.answer("✅ Kartalar tozalandi!")
    await cb_cards(cb)

@dp.callback_query(F.data == "adm_channels")
async def cb_channels(cb: types.CallbackQuery):
    if not is_super(cb.from_user.id): return
    d = db(); chs = d["settings"]["required_channels"]; logs = d["settings"].get("logs_channel", "Yo'q")
    ct = "\n".join([f"• {c}" for c in chs]) if chs else "Kanallar yo'q"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Kanal qo'shish", callback_data="adm_add_ch")],
        [InlineKeyboardButton(text="📝 Logs kanali", callback_data="adm_set_logs")],
        [InlineKeyboardButton(text="🗑 Kanallarni tozalash", callback_data="adm_clear_ch")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="adm_main")],
    ])
    await cb.message.edit_text(
        f"📢 <b>Majburiy kanallar:</b>\n{ct}\n\n📝 <b>Logs kanali:</b> {logs}",
        parse_mode="HTML", reply_markup=kb
    )

@dp.callback_query(F.data == "adm_add_ch")
async def add_ch(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.edit_text("📢 Kanal username kiriting (@channel):"); await state.set_state(Admin.channel)

@dp.message(Admin.channel)
async def enter_channel(msg: types.Message, state: FSMContext):
    d = db(); d["settings"]["required_channels"].append(msg.text.strip()); sdb(d)
    await msg.answer(f"✅ Kanal qo'shildi: {msg.text.strip()}")
    await state.clear(); await cmd_admin(msg, state)

@dp.callback_query(F.data == "adm_clear_ch")
async def clear_ch(cb: types.CallbackQuery):
    d = db(); d["settings"]["required_channels"] = []; sdb(d)
    await cb.answer("✅ Tozalandi!"); await cb_channels(cb)

@dp.callback_query(F.data == "adm_set_logs")
async def set_logs(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.edit_text("📝 Logs kanali username kiriting (@logs):"); await state.set_state(Admin.logs)

@dp.message(Admin.logs)
async def enter_logs(msg: types.Message, state: FSMContext):
    d = db(); d["settings"]["logs_channel"] = msg.text.strip(); sdb(d)
    await msg.answer(f"✅ Logs kanali: {msg.text.strip()}")
    await state.clear(); await cmd_admin(msg, state)

@dp.callback_query(F.data == "adm_admins")
async def cb_admins(cb: types.CallbackQuery):
    if not is_super(cb.from_user.id): return
    d = db(); admins = d.get("admins", {})
    at = "\n".join([f"• <code>{a}</code>" for a in admins.keys()]) if admins else "Adminlar yo'q"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Admin qo'shish", callback_data="adm_add_admin"),
         InlineKeyboardButton(text="➖ O'chirish", callback_data="adm_del_admin")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="adm_main")],
    ])
    await cb.message.edit_text(f"👑 <b>Adminlar:</b>\n\n{at}", parse_mode="HTML", reply_markup=kb)

@dp.callback_query(F.data.in_({"adm_add_admin", "adm_del_admin"}))
async def manage_admin(cb: types.CallbackQuery, state: FSMContext):
    action = "qo'shish" if cb.data == "adm_add_admin" else "o'chirish"
    await cb.message.edit_text(f"👑 Admin ID ({action}):")
    await state.update_data(admin_action=cb.data); await state.set_state(Admin.admin_id)

@dp.message(Admin.admin_id)
async def enter_admin(msg: types.Message, state: FSMContext):
    try:
        aid = int(msg.text.strip())
        if aid == SUPER_ADMIN_ID:
            await msg.answer("❌ Asosiy adminni o'zgartirish mumkin emas!"); await state.clear(); return
        data = await state.get_data(); d = db()
        if data.get("admin_action") == "adm_add_admin":
            d["admins"][str(aid)] = {"added": datetime.now().isoformat()}; sdb(d)
            await msg.answer(f"✅ Admin qo'shildi: <code>{aid}</code>", parse_mode="HTML")
        else:
            if str(aid) in d["admins"]:
                del d["admins"][str(aid)]; sdb(d); await msg.answer(f"✅ Admin o'chirildi: {aid}")
            else: await msg.answer("❌ Admin topilmadi!")
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
    await cb.message.edit_text("🎁 Promo kod nomi:\n\n<i>Masalan: SALE20</i>", parse_mode="HTML")
    await state.set_state(Admin.promo_code)

@dp.message(Admin.promo_code)
async def enter_promo_code(msg: types.Message, state: FSMContext):
    await state.update_data(promo_code=msg.text.strip().upper())
    await msg.answer("📈 Chegirma foizi:\n\n<i>Masalan: 20</i>", parse_mode="HTML")
    await state.set_state(Admin.promo_discount)

@dp.message(Admin.promo_discount)
async def enter_promo_discount(msg: types.Message, state: FSMContext):
    try:
        await state.update_data(promo_discount=int(msg.text))
        await msg.answer("🔢 Foydalanish limiti:\n\n<i>0 = cheksiz</i>", parse_mode="HTML")
        await state.set_state(Admin.promo_limit)
    except: await msg.answer("❌ Faqat raqam!")

@dp.message(Admin.promo_limit)
async def enter_promo_limit(msg: types.Message, state: FSMContext):
    try:
        limit = int(msg.text); data = await state.get_data(); d = db()
        code = data["promo_code"]
        d["promo_codes"][code] = {"discount": data["promo_discount"],
                                   "limit": limit if limit > 0 else None,
                                   "used": 0, "created_at": datetime.now().isoformat()}
        sdb(d)
        await msg.answer(
            f"✅ <b>Promo kod yaratildi!</b>\n\n"
            f"🎁 Kod: <code>{code}</code>\n"
            f"📈 Chegirma: <b>{data['promo_discount']}%</b>\n"
            f"🔢 Limit: <b>{limit if limit > 0 else 'Cheksiz'}</b>",
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
        [InlineKeyboardButton(text=f"👥 {'✅ Yoqilgan' if s.get('referral_active') else '❌ O\'chirilgan'}", callback_data="adm_toggle_ref")],
        [InlineKeyboardButton(text=f"💰 Bonus: {fmt(s.get('referral_bonus',5000))} so'm", callback_data="adm_set_ref_bonus")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="adm_main")],
    ])
    await cb.message.edit_text("👥 <b>Referral tizimi</b>", parse_mode="HTML", reply_markup=kb)

@dp.callback_query(F.data == "adm_set_ref_bonus")
async def set_ref_bonus(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.edit_text("💰 Referral bonus miqdori (so'mda):\n\n<i>Masalan: 5000</i>", parse_mode="HTML")
    await state.set_state(Admin.ref_bonus)

@dp.message(Admin.ref_bonus)
async def enter_ref_bonus(msg: types.Message, state: FSMContext):
    try:
        v = int(msg.text); d = db(); d["settings"]["referral_bonus"] = v; sdb(d)
        await msg.answer(f"✅ Referral bonus: <b>{fmt(v)} so'm</b>", parse_mode="HTML")
        await state.clear(); await cmd_admin(msg, state)
    except: await msg.answer("❌ Faqat raqam!")

# ═══════════════════════════════════
# MAIN
# ═══════════════════════════════════
async def main():
    log.info("🚀 U-Gift Bot ishga tushmoqda...")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
