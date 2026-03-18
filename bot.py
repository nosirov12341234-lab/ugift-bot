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
    ReplyKeyboardMarkup, KeyboardButton,
    ReplyKeyboardRemove
)
from dotenv import load_dotenv

load_dotenv()

# ═══════════════════════════════════════
# SOZLAMALAR
# ═══════════════════════════════════════
BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPER_ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
TON_API_KEY = os.getenv("TON_API_KEY", "")
FRAGMENT_COOKIES = os.getenv("FRAGMENT_COOKIES", "")
WEB_URL = os.getenv("WEB_URL", "http://localhost:5000")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ═══════════════════════════════════════
# DATABASE
# ═══════════════════════════════════════
DB_FILE = "database.json"

def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "users": {},
        "orders": [],
        "admins": {},
        "settings": {
            "markup": 20,
            "min_stars": 50,
            "payment_timeout": 30,
            "bot_active": True,
            "referral_active": False,
            "promo_active": False,
            "referral_bonus": 5000,
            "cards": [],
            "required_channels": [],
            "logs_channel": None,
            "ton_rate": 0,
            "uzs_rate": 0
        },
        "promo_codes": {},
        "admins": {}
    }

def save_db(db):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)

# ═══════════════════════════════════════
# TILLAR
# ═══════════════════════════════════════
T = {
    "uz": {
        "welcome": "👋 <b>U-Gift Bot ga xush kelibsiz!</b>\n\nPremium Gift, Stars va NFT yuborish xizmati.",
        "choose_lang": "🌐 Tilni tanlang:",
        "main_menu": "🏠 Asosiy menyu",
        "premium": "⭐ Premium Gift",
        "stars": "🌟 Stars",
        "nft": "🖼 NFT",
        "balance": "💰 Balans",
        "history": "📋 Tarix",
        "topup": "➕ Hisob to'ldirish",
        "referral": "👥 Referral",
        "promo": "🎁 Promo kod",
        "web_app": "🌐 Web ilova",
        "settings": "⚙️ Sozlamalar",
        "back": "🔙 Orqaga",
        "cancel": "❌ Bekor qilish",
        "confirm": "✅ Tasdiqlash",
        "insufficient": "❌ Balans yetarli emas!\n\n💰 Kerakli: {price} so'm\n💳 Sizda: {bal} so'm",
        "subscribe_req": "📢 Botdan foydalanish uchun kanallarga obuna bo'ling:",
        "check_sub": "✅ Obunani tekshirish",
        "banned": "🚫 Siz botdan bloklangansiz.",
        "bot_off": "🔧 Bot hozirda texnik ishlar uchun o'chirilgan.",
        "enter_username": "👤 Username kiriting:\n\n<i>Masalan: @username yoki username</i>",
        "choose_months": "⭐ Premium muddatini tanlang:",
        "enter_stars": "🌟 Nechta Stars yuboramiz?\n\n<i>Minimum: {min} Stars</i>",
        "stars_min_err": "❌ Minimum {min} Stars kiriting!",
        "enter_nft": "🖼 Fragment NFT linkini yuboring:\n\n<i>Masalan: https://fragment.com/username/crypto</i>",
        "nft_invalid": "❌ Noto'g'ri link! fragment.com dan link yuboring.",
        "self_or_other": "👤 Kimga yuboramiz?",
        "self": "👤 O'zimga",
        "other": "👥 Boshqaga",
        "order_confirm": "📋 <b>Buyurtma tasdiqlash:</b>\n\n🛍 Xizmat: {svc}\n👤 Kimga: @{username}\n💰 Narx: {price} so'm\n💳 Balansingiz: {bal} so'm\n\n{status}",
        "balance_ok": "✅ Balans yetarli",
        "processing": "⏳ Buyurtma bajarilmoqda...",
        "success": "✅ <b>Muvaffaqiyatli yuborildi!</b>\n\n🛍 Xizmat: {svc}\n👤 Kimga: @{username}",
        "failed": "❌ Xato yuz berdi. Balans qaytarildi.\nAdmin bilan bog'laning: @admin",
        "topup_enter": "💰 Qancha so'm to'ldirmoqchisiz?\n\n<i>Minimum: 1,000 so'm</i>",
        "topup_cards": "💳 <b>To'lov uchun karta:</b>\n\n{cards}\n\n💰 Miqdor: <b>{amount} so'm</b>\n\nTo'lovdan so'ng <b>chek (screenshot)</b> yuboring:",
        "topup_sent": "✅ Chekingiz adminga yuborildi.\n⏳ Tasdiqlash kutilmoqda...",
        "topup_approved": "✅ <b>Balansingiz to'ldirildi!</b>\n\n➕ Qo'shildi: <b>{amount} so'm</b>\n💰 Joriy balans: <b>{bal} so'm</b>",
        "topup_rejected": "❌ To'lovingiz tasdiqlanmadi.\nAdmin bilan bog'laning.",
        "no_cards": "❌ Hozirda to'lov qabul qilinmayapti.",
        "ref_info": "👥 <b>Referral tizimi</b>\n\nDo'stlarni taklif qiling va bonus oling!\n\n🔗 Sizning havolangiz:\n<code>{link}</code>\n\n👥 Taklif qilganlar: <b>{count}</b>\n💰 Jami bonus: <b>{bonus} so'm</b>\n🎁 Har bir do'st uchun: <b>{per} so'm</b>",
        "copy_link": "📋 Nusxalash",
        "promo_enter": "🎁 Promo kodingizni kiriting:",
        "promo_ok": "✅ Promo kod qo'llandi! -{discount}% chegirma",
        "promo_err": "❌ Noto'g'ri yoki muddati o'tgan promo kod.",
        "balance_info": "💰 <b>Balansingiz:</b> {bal} so'm",
        "history_empty": "📋 Hali buyurtmalar yo'q.",
        "no_username": "❌ Sizning username ingiz yo'q! Telegram sozlamalaridan username o'rnating.",
    },
    "ru": {
        "welcome": "👋 <b>Добро пожаловать в U-Gift Bot!</b>\n\nСервис отправки Premium Gift, Stars и NFT.",
        "choose_lang": "🌐 Выберите язык:",
        "main_menu": "🏠 Главное меню",
        "premium": "⭐ Premium Gift",
        "stars": "🌟 Stars",
        "nft": "🖼 NFT",
        "balance": "💰 Баланс",
        "history": "📋 История",
        "topup": "➕ Пополнить счёт",
        "referral": "👥 Реферал",
        "promo": "🎁 Промо код",
        "web_app": "🌐 Веб приложение",
        "settings": "⚙️ Настройки",
        "back": "🔙 Назад",
        "cancel": "❌ Отмена",
        "confirm": "✅ Подтвердить",
        "insufficient": "❌ Недостаточно средств!\n\n💰 Нужно: {price} сум\n💳 У вас: {bal} сум",
        "subscribe_req": "📢 Подпишитесь на каналы для использования бота:",
        "check_sub": "✅ Проверить подписку",
        "banned": "🚫 Вы заблокированы.",
        "bot_off": "🔧 Бот временно отключён.",
        "enter_username": "👤 Введите username:\n\n<i>Например: @username или username</i>",
        "choose_months": "⭐ Выберите срок Premium:",
        "enter_stars": "🌟 Сколько Stars отправить?\n\n<i>Минимум: {min} Stars</i>",
        "stars_min_err": "❌ Минимум {min} Stars!",
        "enter_nft": "🖼 Отправьте ссылку Fragment NFT:\n\n<i>Например: https://fragment.com/username/crypto</i>",
        "nft_invalid": "❌ Неверная ссылка! Отправьте ссылку с fragment.com",
        "self_or_other": "👤 Кому отправить?",
        "self": "👤 Себе",
        "other": "👥 Другому",
        "order_confirm": "📋 <b>Подтверждение заказа:</b>\n\n🛍 Услуга: {svc}\n👤 Кому: @{username}\n💰 Цена: {price} сум\n💳 Ваш баланс: {bal} сум\n\n{status}",
        "balance_ok": "✅ Баланс достаточен",
        "processing": "⏳ Заказ выполняется...",
        "success": "✅ <b>Успешно отправлено!</b>\n\n🛍 Услуга: {svc}\n👤 Кому: @{username}",
        "failed": "❌ Ошибка. Баланс возвращён.\nСвяжитесь с админом: @admin",
        "topup_enter": "💰 Сколько сум пополнить?\n\n<i>Минимум: 1,000 сум</i>",
        "topup_cards": "💳 <b>Карта для оплаты:</b>\n\n{cards}\n\n💰 Сумма: <b>{amount} сум</b>\n\nПосле оплаты отправьте <b>чек (скриншот)</b>:",
        "topup_sent": "✅ Чек отправлен администратору.\n⏳ Ожидайте подтверждения...",
        "topup_approved": "✅ <b>Баланс пополнен!</b>\n\n➕ Добавлено: <b>{amount} сум</b>\n💰 Текущий баланс: <b>{bal} сум</b>",
        "topup_rejected": "❌ Оплата не подтверждена.\nСвяжитесь с администратором.",
        "no_cards": "❌ Приём платежей временно недоступен.",
        "ref_info": "👥 <b>Реферальная система</b>\n\nПриглашайте друзей и получайте бонусы!\n\n🔗 Ваша ссылка:\n<code>{link}</code>\n\n👥 Приглашено: <b>{count}</b>\n💰 Всего бонусов: <b>{bonus} сум</b>\n🎁 За каждого друга: <b>{per} сум</b>",
        "copy_link": "📋 Копировать",
        "promo_enter": "🎁 Введите промо код:",
        "promo_ok": "✅ Промо код применён! -{discount}% скидка",
        "promo_err": "❌ Неверный или просроченный промо код.",
        "balance_info": "💰 <b>Ваш баланс:</b> {bal} сум",
        "history_empty": "📋 Заказов пока нет.",
        "no_username": "❌ У вас нет username! Установите его в настройках Telegram.",
    },
    "en": {
        "welcome": "👋 <b>Welcome to U-Gift Bot!</b>\n\nPremium Gift, Stars and NFT sending service.",
        "choose_lang": "🌐 Choose language:",
        "main_menu": "🏠 Main menu",
        "premium": "⭐ Premium Gift",
        "stars": "🌟 Stars",
        "nft": "🖼 NFT",
        "balance": "💰 Balance",
        "history": "📋 History",
        "topup": "➕ Top up",
        "referral": "👥 Referral",
        "promo": "🎁 Promo code",
        "web_app": "🌐 Web app",
        "settings": "⚙️ Settings",
        "back": "🔙 Back",
        "cancel": "❌ Cancel",
        "confirm": "✅ Confirm",
        "insufficient": "❌ Insufficient balance!\n\n💰 Required: {price} UZS\n💳 You have: {bal} UZS",
        "subscribe_req": "📢 Subscribe to channels to use the bot:",
        "check_sub": "✅ Check subscription",
        "banned": "🚫 You are banned.",
        "bot_off": "🔧 Bot is temporarily disabled.",
        "enter_username": "👤 Enter username:\n\n<i>Example: @username or username</i>",
        "choose_months": "⭐ Choose Premium duration:",
        "enter_stars": "🌟 How many Stars to send?\n\n<i>Minimum: {min} Stars</i>",
        "stars_min_err": "❌ Minimum {min} Stars!",
        "enter_nft": "🖼 Send Fragment NFT link:\n\n<i>Example: https://fragment.com/username/crypto</i>",
        "nft_invalid": "❌ Invalid link! Send a link from fragment.com",
        "self_or_other": "👤 Who to send to?",
        "self": "👤 Myself",
        "other": "👥 Someone else",
        "order_confirm": "📋 <b>Order confirmation:</b>\n\n🛍 Service: {svc}\n👤 To: @{username}\n💰 Price: {price} UZS\n💳 Your balance: {bal} UZS\n\n{status}",
        "balance_ok": "✅ Balance sufficient",
        "processing": "⏳ Processing order...",
        "success": "✅ <b>Successfully sent!</b>\n\n🛍 Service: {svc}\n👤 To: @{username}",
        "failed": "❌ Error occurred. Balance refunded.\nContact admin: @admin",
        "topup_enter": "💰 How much to top up?\n\n<i>Minimum: 1,000 UZS</i>",
        "topup_cards": "💳 <b>Payment card:</b>\n\n{cards}\n\n💰 Amount: <b>{amount} UZS</b>\n\nAfter payment, send <b>receipt (screenshot)</b>:",
        "topup_sent": "✅ Receipt sent to admin.\n⏳ Waiting for confirmation...",
        "topup_approved": "✅ <b>Balance topped up!</b>\n\n➕ Added: <b>{amount} UZS</b>\n💰 Current balance: <b>{bal} UZS</b>",
        "topup_rejected": "❌ Payment not confirmed.\nContact administrator.",
        "no_cards": "❌ Payment is temporarily unavailable.",
        "ref_info": "👥 <b>Referral system</b>\n\nInvite friends and earn bonuses!\n\n🔗 Your link:\n<code>{link}</code>\n\n👥 Invited: <b>{count}</b>\n💰 Total bonus: <b>{bonus} UZS</b>\n🎁 Per friend: <b>{per} UZS</b>",
        "copy_link": "📋 Copy",
        "promo_enter": "🎁 Enter promo code:",
        "promo_ok": "✅ Promo code applied! -{discount}% discount",
        "promo_err": "❌ Invalid or expired promo code.",
        "balance_info": "💰 <b>Your balance:</b> {bal} UZS",
        "history_empty": "📋 No orders yet.",
        "no_username": "❌ You have no username! Set it in Telegram settings.",
    }
}

# ═══════════════════════════════════════
# STATES
# ═══════════════════════════════════════
class OrderState(StatesGroup):
    choosing_recipient = State()
    entering_username = State()
    choosing_months = State()
    entering_stars = State()
    entering_nft = State()
    confirming = State()
    entering_promo = State()

class TopupState(StatesGroup):
    entering_amount = State()
    waiting_receipt = State()

class AdminState(StatesGroup):
    entering_card = State()
    entering_markup = State()
    entering_min_stars = State()
    entering_channel = State()
    entering_logs_channel = State()
    entering_broadcast = State()
    entering_promo_code = State()
    entering_promo_discount = State()
    entering_promo_limit = State()
    entering_admin_id = State()
    entering_topup_user = State()
    entering_topup_amount = State()
    entering_ban_user = State()

# ═══════════════════════════════════════
# YORDAMCHI FUNKSIYALAR
# ═══════════════════════════════════════
def get_lang(user_id: int) -> str:
    db = load_db()
    uid = str(user_id)
    return db["users"].get(uid, {}).get("lang", "uz")

def t(user_id: int, key: str, **kwargs) -> str:
    lang = get_lang(user_id)
    text = T[lang].get(key, T["uz"].get(key, key))
    return text.format(**kwargs) if kwargs else text

def fmt(n: int) -> str:
    return f"{int(n):,}".replace(",", " ")

def is_admin(user_id: int) -> bool:
    db = load_db()
    return user_id == SUPER_ADMIN_ID or str(user_id) in db.get("admins", {})

def is_super_admin(user_id: int) -> bool:
    return user_id == SUPER_ADMIN_ID

def get_user(user_id: int) -> dict:
    db = load_db()
    uid = str(user_id)
    return db["users"].get(uid, {})

def update_user(user_id: int, data: dict):
    db = load_db()
    uid = str(user_id)
    if uid not in db["users"]:
        db["users"][uid] = {}
    db["users"][uid].update(data)
    save_db(db)

async def get_ton_uzs_rate() -> float:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.coingecko.com/api/v3/simple/price?ids=the-open-network&vs_currencies=usd",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as r:
                data = await r.json()
                ton_usd = data["the-open-network"]["usd"]
            async with session.get(
                "https://cbu.uz/uz/arkhiv-kursov-valyut/json/USD/",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as r:
                cbu = await r.json()
                usd_uzs = float(cbu[0]["Rate"])
        return ton_usd * usd_uzs
    except Exception as e:
        log.error(f"Rate fetch error: {e}")
        return 44800.0

async def calc_price_uzs(ton_amount: float) -> int:
    db = load_db()
    markup = db["settings"]["markup"]
    rate = await get_ton_uzs_rate()
    return round(ton_amount * rate * (1 + markup / 100))

async def check_subscription(user_id: int) -> bool:
    db = load_db()
    channels = db["settings"]["required_channels"]
    if not channels:
        return True
    for ch in channels:
        try:
            member = await bot.get_chat_member(ch, user_id)
            if member.status in ["left", "kicked"]:
                return False
        except:
            return False
    return True

async def send_log(text: str):
    db = load_db()
    ch = db["settings"].get("logs_channel")
    if ch:
        try:
            await bot.send_message(ch, text, parse_mode="HTML")
        except Exception as e:
            log.error(f"Log send error: {e}")

async def notify_admins(text: str, reply_markup=None, photo=None):
    db = load_db()
    admins = [SUPER_ADMIN_ID] + [int(a) for a in db.get("admins", {}).keys()]
    for admin_id in admins:
        try:
            if photo:
                await bot.send_photo(admin_id, photo, caption=text, reply_markup=reply_markup, parse_mode="HTML")
            else:
                await bot.send_message(admin_id, text, reply_markup=reply_markup, parse_mode="HTML")
        except Exception as e:
            log.error(f"Notify admin {admin_id} error: {e}")

# ═══════════════════════════════════════
# KLAVIATURALAR
# ═══════════════════════════════════════
def main_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    db = load_db()
    lang = get_lang(user_id)
    rows = [
        [KeyboardButton(text=T[lang]["premium"]), KeyboardButton(text=T[lang]["stars"])],
        [KeyboardButton(text=T[lang]["nft"]), KeyboardButton(text=T[lang]["balance"])],
        [KeyboardButton(text=T[lang]["topup"]), KeyboardButton(text=T[lang]["history"])],
        [KeyboardButton(text=T[lang]["web_app"])],
    ]
    if db["settings"].get("referral_active"):
        rows.append([KeyboardButton(text=T[lang]["referral"])])
    if db["settings"].get("promo_active"):
        rows[-1].append(KeyboardButton(text=T[lang]["promo"]))
    rows.append([KeyboardButton(text=T[lang]["settings"])])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

def cancel_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    lang = get_lang(user_id)
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=T[lang]["cancel"])]],
        resize_keyboard=True
    )

# ═══════════════════════════════════════
# START
# ═══════════════════════════════════════
@dp.message(Command("start"))
async def start_cmd(msg: types.Message, state: FSMContext):
    await state.clear()
    db = load_db()
    uid = str(msg.from_user.id)

    if not db["settings"]["bot_active"] and not is_admin(msg.from_user.id):
        await msg.answer(t(msg.from_user.id, "bot_off"))
        return

    # Yangi foydalanuvchi
    if uid not in db["users"]:
        db["users"][uid] = {
            "lang": "uz",
            "balance": 0,
            "orders": [],
            "referrals": 0,
            "ref_bonus_earned": 0,
            "joined": datetime.now().isoformat(),
            "banned": False,
            "promo_used": []
        }

        # Referral
        args = msg.text.split()
        if len(args) > 1 and args[1].startswith("ref_"):
            ref_id = args[1].replace("ref_", "")
            if ref_id in db["users"] and db["settings"].get("referral_active"):
                bonus = db["settings"]["referral_bonus"]
                db["users"][ref_id]["balance"] = db["users"][ref_id].get("balance", 0) + bonus
                db["users"][ref_id]["referrals"] = db["users"][ref_id].get("referrals", 0) + 1
                db["users"][ref_id]["ref_bonus_earned"] = db["users"][ref_id].get("ref_bonus_earned", 0) + bonus
                try:
                    await bot.send_message(int(ref_id), f"🎉 Yangi referral! +{fmt(bonus)} so'm bonus!\n💰 Balansingiz: {fmt(db['users'][ref_id]['balance'])} so'm")
                except:
                    pass

        save_db(db)

    db = load_db()
    if db["users"][uid].get("banned"):
        await msg.answer(t(msg.from_user.id, "banned"))
        return

    # Admin bo'lsa topup linkni tekshir
    args = msg.text.split()
    if len(args) > 1 and args[1] == "admin" and is_admin(msg.from_user.id):
        await admin_panel(msg, state)
        return

    if len(args) > 1 and args[1] == "topup":
        await topup_start(msg, state)
        return

    # Til tanlash
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🇺🇿 O'zbek", callback_data="lang_uz"),
        InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru"),
        InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en"),
    ]])
    await msg.answer(T["uz"]["choose_lang"], reply_markup=kb)

@dp.callback_query(F.data.startswith("lang_"))
async def lang_cb(cb: types.CallbackQuery):
    lang = cb.data.replace("lang_", "")
    update_user(cb.from_user.id, {"lang": lang})

    subscribed = await check_subscription(cb.from_user.id)
    if not subscribed:
        db = load_db()
        channels = db["settings"]["required_channels"]
        btns = [[InlineKeyboardButton(text=f"📢 {ch}", url=f"https://t.me/{ch.replace('@','')}")] for ch in channels]
        btns.append([InlineKeyboardButton(text=T[lang]["check_sub"], callback_data="check_sub")])
        await cb.message.edit_text(T[lang]["subscribe_req"], reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))
        return

    await cb.message.delete()
    await cb.message.answer(T[lang]["welcome"], parse_mode="HTML", reply_markup=main_keyboard(cb.from_user.id))

@dp.callback_query(F.data == "check_sub")
async def check_sub_cb(cb: types.CallbackQuery):
    subscribed = await check_subscription(cb.from_user.id)
    if subscribed:
        await cb.message.delete()
        lang = get_lang(cb.from_user.id)
        await cb.message.answer(T[lang]["welcome"], parse_mode="HTML", reply_markup=main_keyboard(cb.from_user.id))
    else:
        await cb.answer("❌ Hali obuna bo'lmadingiz!", show_alert=True)

# ═══════════════════════════════════════
# BALANS
# ═══════════════════════════════════════
@dp.message(F.text.in_(["💰 Balans", "💰 Баланс", "💰 Balance"]))
async def balance_cmd(msg: types.Message):
    db = load_db()
    uid = str(msg.from_user.id)
    bal = db["users"].get(uid, {}).get("balance", 0)
    await msg.answer(t(msg.from_user.id, "balance_info", bal=fmt(bal)), parse_mode="HTML")

# ═══════════════════════════════════════
# HISOB TO'LDIRISH
# ═══════════════════════════════════════
@dp.message(F.text.in_(["➕ Hisob to'ldirish", "➕ Пополнить счёт", "➕ Top up"]))
async def topup_start(msg: types.Message, state: FSMContext):
    db = load_db()
    if not db["settings"]["cards"]:
        await msg.answer(t(msg.from_user.id, "no_cards"))
        return
    await msg.answer(t(msg.from_user.id, "topup_enter"), parse_mode="HTML", reply_markup=cancel_keyboard(msg.from_user.id))
    await state.set_state(TopupState.entering_amount)

@dp.message(TopupState.entering_amount)
async def topup_amount(msg: types.Message, state: FSMContext):
    if msg.text in ["❌ Bekor qilish", "❌ Отмена", "❌ Cancel"]:
        await state.clear()
        await msg.answer(t(msg.from_user.id, "main_menu"), reply_markup=main_keyboard(msg.from_user.id))
        return
    try:
        amount = int(msg.text.replace(" ", "").replace(",", ""))
        if amount < 1000:
            await msg.answer("❌ Minimum 1,000 so'm!")
            return
        db = load_db()
        cards = db["settings"]["cards"]
        cards_text = "\n".join([f"💳 <code>{c}</code>" for c in cards])
        await state.update_data(amount=amount)
        await msg.answer(
            t(msg.from_user.id, "topup_cards", cards=cards_text, amount=fmt(amount)),
            parse_mode="HTML",
            reply_markup=cancel_keyboard(msg.from_user.id)
        )
        await state.set_state(TopupState.waiting_receipt)
    except:
        await msg.answer("❌ Faqat raqam kiriting!")

@dp.message(TopupState.waiting_receipt)
async def topup_receipt(msg: types.Message, state: FSMContext):
    if msg.text in ["❌ Bekor qilish", "❌ Отмена", "❌ Cancel"]:
        await state.clear()
        await msg.answer(t(msg.from_user.id, "main_menu"), reply_markup=main_keyboard(msg.from_user.id))
        return
    if not msg.photo:
        await msg.answer("📸 Iltimos, to'lov cheki (screenshot) yuboring!")
        return

    data = await state.get_data()
    amount = data["amount"]
    uid = msg.from_user.id

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"topup_ok_{uid}_{amount}"),
        InlineKeyboardButton(text="❌ Rad etish", callback_data=f"topup_no_{uid}"),
    ]])

    caption = (
        f"💳 <b>Balans to'ldirish so'rovi</b>\n\n"
        f"👤 Foydalanuvchi: {msg.from_user.full_name}\n"
        f"🆔 ID: <code>{uid}</code>\n"
        f"👤 Username: @{msg.from_user.username or 'yo\'q'}\n"
        f"💰 Miqdor: <b>{fmt(amount)} so'm</b>"
    )
    await notify_admins(caption, reply_markup=kb, photo=msg.photo[-1].file_id)
    await msg.answer(t(msg.from_user.id, "topup_sent"), parse_mode="HTML", reply_markup=main_keyboard(msg.from_user.id))
    await state.clear()

@dp.callback_query(F.data.startswith("topup_ok_"))
async def topup_approve(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        return
    parts = cb.data.split("_")
    uid = int(parts[2])
    amount = int(parts[3])
    db = load_db()
    suid = str(uid)
    if suid in db["users"]:
        db["users"][suid]["balance"] = db["users"][suid].get("balance", 0) + amount
        save_db(db)
    bal = db["users"][suid]["balance"]
    await bot.send_message(uid, t(uid, "topup_approved", amount=fmt(amount), bal=fmt(bal)), parse_mode="HTML")
    await cb.message.edit_caption(caption=cb.message.caption + f"\n\n✅ Tasdiqlandi! Admin: {cb.from_user.full_name}")
    await send_log(f"✅ Balans to'ldirildi\n👤 ID: {uid}\n💰 {fmt(amount)} so'm")

@dp.callback_query(F.data.startswith("topup_no_"))
async def topup_reject(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        return
    uid = int(cb.data.split("_")[2])
    await bot.send_message(uid, t(uid, "topup_rejected"), parse_mode="HTML")
    await cb.message.edit_caption(caption=cb.message.caption + f"\n\n❌ Rad etildi! Admin: {cb.from_user.full_name}")

# ═══════════════════════════════════════
# XIZMATLAR — PREMIUM
# ═══════════════════════════════════════
@dp.message(F.text.in_(["⭐ Premium Gift"]))
async def premium_cmd(msg: types.Message, state: FSMContext):
    await state.update_data(service="premium")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👤 O'zimga", callback_data="recip_self"),
            InlineKeyboardButton(text="👥 Boshqaga", callback_data="recip_other"),
        ]
    ])
    await msg.answer(t(msg.from_user.id, "self_or_other"), reply_markup=kb)

# ═══════════════════════════════════════
# XIZMATLAR — STARS
# ═══════════════════════════════════════
@dp.message(F.text.in_(["🌟 Stars"]))
async def stars_cmd(msg: types.Message, state: FSMContext):
    await state.update_data(service="stars")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👤 O'zimga", callback_data="recip_self"),
            InlineKeyboardButton(text="👥 Boshqaga", callback_data="recip_other"),
        ]
    ])
    await msg.answer(t(msg.from_user.id, "self_or_other"), reply_markup=kb)

# ═══════════════════════════════════════
# XIZMATLAR — NFT
# ═══════════════════════════════════════
@dp.message(F.text.in_(["🖼 NFT"]))
async def nft_cmd(msg: types.Message, state: FSMContext):
    await state.update_data(service="nft")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👤 O'zimga", callback_data="recip_self"),
            InlineKeyboardButton(text="👥 Boshqaga", callback_data="recip_other"),
        ]
    ])
    await msg.answer(t(msg.from_user.id, "self_or_other"), reply_markup=kb)

# ═══════════════════════════════════════
# RECIPIENT CALLBACK
# ═══════════════════════════════════════
@dp.callback_query(F.data == "recip_self")
async def recip_self(cb: types.CallbackQuery, state: FSMContext):
    if not cb.from_user.username:
        await cb.answer(t(cb.from_user.id, "no_username"), show_alert=True)
        return
    await state.update_data(username=cb.from_user.username)
    await cb.message.delete()
    data = await state.get_data()
    await ask_service_details(cb.message, state, data["service"], cb.from_user.id)

@dp.callback_query(F.data == "recip_other")
async def recip_other(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.edit_text(t(cb.from_user.id, "enter_username"), parse_mode="HTML")
    await state.set_state(OrderState.entering_username)

@dp.message(OrderState.entering_username)
async def enter_username(msg: types.Message, state: FSMContext):
    if msg.text in ["❌ Bekor qilish", "❌ Отмена", "❌ Cancel"]:
        await state.clear()
        await msg.answer(t(msg.from_user.id, "main_menu"), reply_markup=main_keyboard(msg.from_user.id))
        return
    username = msg.text.replace("@", "").strip()
    await state.update_data(username=username)
    data = await state.get_data()
    await ask_service_details(msg, state, data["service"], msg.from_user.id)

async def ask_service_details(msg, state, service, user_id):
    db = load_db()
    if service == "premium":
        # Narxlarni hisoblash
        prices = {}
        for m, ton in [(3, 3.0), (6, 5.5), (12, 10.0)]:
            prices[m] = await calc_price_uzs(ton)
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=f"3 oy\n{fmt(prices[3])} so'm", callback_data="months_3"),
            InlineKeyboardButton(text=f"6 oy\n{fmt(prices[6])} so'm", callback_data="months_6"),
            InlineKeyboardButton(text=f"12 oy\n{fmt(prices[12])} so'm", callback_data="months_12"),
        ]])
        await msg.answer(t(user_id, "choose_months"), reply_markup=kb)
        await state.set_state(OrderState.choosing_months)

    elif service == "stars":
        min_s = db["settings"]["min_stars"]
        await msg.answer(t(user_id, "enter_stars", min=min_s), parse_mode="HTML", reply_markup=cancel_keyboard(user_id))
        await state.set_state(OrderState.entering_stars)

    elif service == "nft":
        await msg.answer(t(user_id, "enter_nft"), parse_mode="HTML", reply_markup=cancel_keyboard(user_id))
        await state.set_state(OrderState.entering_nft)

@dp.callback_query(F.data.startswith("months_"))
async def months_cb(cb: types.CallbackQuery, state: FSMContext):
    months = int(cb.data.split("_")[1])
    prices = {3: 3.0, 6: 5.5, 12: 10.0}
    price = await calc_price_uzs(prices[months])
    await state.update_data(months=months, price=price, ton_price=prices[months])
    await cb.message.delete()
    await show_order_confirm(cb.message, state, cb.from_user.id)

@dp.message(OrderState.entering_stars)
async def enter_stars(msg: types.Message, state: FSMContext):
    if msg.text in ["❌ Bekor qilish", "❌ Отмена", "❌ Cancel"]:
        await state.clear()
        await msg.answer(t(msg.from_user.id, "main_menu"), reply_markup=main_keyboard(msg.from_user.id))
        return
    db = load_db()
    min_s = db["settings"]["min_stars"]
    try:
        stars = int(msg.text)
        if stars < min_s:
            await msg.answer(t(msg.from_user.id, "stars_min_err", min=min_s))
            return
        price = await calc_price_uzs(stars / 50)
        await state.update_data(stars=stars, price=price, ton_price=stars/50)
        await show_order_confirm(msg, state, msg.from_user.id)
    except:
        await msg.answer("❌ Faqat raqam kiriting!")

@dp.message(OrderState.entering_nft)
async def enter_nft(msg: types.Message, state: FSMContext):
    if msg.text in ["❌ Bekor qilish", "❌ Отмена", "❌ Cancel"]:
        await state.clear()
        await msg.answer(t(msg.from_user.id, "main_menu"), reply_markup=main_keyboard(msg.from_user.id))
        return
    if "fragment.com" not in msg.text:
        await msg.answer(t(msg.from_user.id, "nft_invalid"))
        return
    # Fragment API dan narx olish
    try:
        from FragmentAPI import SyncFragmentAPI
        api = SyncFragmentAPI(cookies=FRAGMENT_COOKIES, wallet_api_key=TON_API_KEY)
        # NFT narxini olish
        nft_data = api.get_nft_info(msg.text)
        ton_price = nft_data.price if hasattr(nft_data, 'price') else 5.0
        nft_name = nft_data.name if hasattr(nft_data, 'name') else "NFT"
    except:
        ton_price = 5.0
        nft_name = "NFT"

    price = await calc_price_uzs(ton_price)
    await state.update_data(nft_link=msg.text, price=price, ton_price=ton_price, nft_name=nft_name)
    await show_order_confirm(msg, state, msg.from_user.id)

async def show_order_confirm(msg, state, user_id):
    data = await state.get_data()
    db = load_db()
    uid = str(user_id)
    bal = db["users"].get(uid, {}).get("balance", 0)
    price = data.get("price", 0)
    username = data.get("username", "?")
    service = data.get("service", "")

    svc_names = {"premium": f"⭐ Premium {data.get('months', 3)} oy", "stars": f"🌟 {data.get('stars', 50)} Stars", "nft": f"🖼 {data.get('nft_name', 'NFT')}"}
    svc = svc_names.get(service, service)

    status = t(user_id, "balance_ok") if bal >= price else t(user_id, "insufficient", price=fmt(price), bal=fmt(bal))

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t(user_id, "confirm"), callback_data="order_confirm"),
        InlineKeyboardButton(text=t(user_id, "cancel"), callback_data="order_cancel"),
    ]])

    await msg.answer(
        t(user_id, "order_confirm", svc=svc, username=username, price=fmt(price), bal=fmt(bal), status=status),
        parse_mode="HTML", reply_markup=kb
    )

@dp.callback_query(F.data == "order_confirm")
async def order_confirm_cb(cb: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    db = load_db()
    uid = str(cb.from_user.id)
    bal = db["users"].get(uid, {}).get("balance", 0)
    price = data.get("price", 0)

    if bal < price:
        await cb.answer(t(cb.from_user.id, "insufficient", price=fmt(price), bal=fmt(bal)), show_alert=True)
        return

    await cb.message.edit_text(t(cb.from_user.id, "processing"), parse_mode="HTML")

    # Balansdan yechish
    db["users"][uid]["balance"] -= price

    # Buyurtma yaratish
    order = {
        "id": len(db["orders"]) + 1,
        "user_id": uid,
        "service": data.get("service"),
        "username": data.get("username"),
        "months": data.get("months"),
        "stars": data.get("stars"),
        "nft_link": data.get("nft_link"),
        "nft_name": data.get("nft_name"),
        "price": price,
        "ton_price": data.get("ton_price"),
        "status": "processing",
        "created_at": datetime.now().isoformat()
    }
    db["orders"].append(order)
    db["users"][uid].setdefault("orders", []).append(order["id"])
    save_db(db)

    # Fragment API orqali yuborish
    success = await process_fragment_order(order)

    db = load_db()
    if success:
        for o in db["orders"]:
            if o["id"] == order["id"]:
                o["status"] = "completed"
        save_db(db)

        svc_names = {"premium": f"⭐ Premium {order.get('months', 3)} oy", "stars": f"🌟 {order.get('stars', 50)} Stars", "nft": f"🖼 {order.get('nft_name', 'NFT')}"}
        svc = svc_names.get(order["service"], order["service"])

        await cb.message.edit_text(
            t(cb.from_user.id, "success", svc=svc, username=order["username"]),
            parse_mode="HTML"
        )
        await send_log(
            f"✅ <b>Buyurtma bajarildi</b>\n"
            f"🆔 #{order['id']}\n"
            f"👤 @{order['username']}\n"
            f"🛍 {svc}\n"
            f"💰 {fmt(price)} so'm"
        )
    else:
        db["users"][uid]["balance"] += price
        for o in db["orders"]:
            if o["id"] == order["id"]:
                o["status"] = "failed"
        save_db(db)
        await cb.message.edit_text(t(cb.from_user.id, "failed"), parse_mode="HTML")
        await send_log(f"❌ <b>Buyurtma bajarilmadi</b>\n🆔 #{order['id']}")

    await state.clear()

@dp.callback_query(F.data == "order_cancel")
async def order_cancel_cb(cb: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text(t(cb.from_user.id, "cancel"))

# ═══════════════════════════════════════
# FRAGMENT API
# ═══════════════════════════════════════
async def process_fragment_order(order: dict) -> bool:
    try:
        from FragmentAPI import SyncFragmentAPI
        api = SyncFragmentAPI(cookies=FRAGMENT_COOKIES, wallet_api_key=TON_API_KEY)

        if order["service"] == "premium":
            result = api.buy_premium(order["username"], order["months"])
        elif order["service"] == "stars":
            result = api.buy_stars(order["username"], order["stars"])
        elif order["service"] == "nft":
            result = api.buy_nft(order["nft_link"])
        else:
            return False

        return bool(result)
    except Exception as e:
        log.error(f"Fragment API error: {e}")
        return False

# ═══════════════════════════════════════
# TARIX
# ═══════════════════════════════════════
@dp.message(F.text.in_(["📋 Tarix", "📋 История", "📋 History"]))
async def history_cmd(msg: types.Message):
    db = load_db()
    uid = str(msg.from_user.id)
    orders = [o for o in db["orders"] if o["user_id"] == uid]
    if not orders:
        await msg.answer(t(msg.from_user.id, "history_empty"))
        return
    text = "📋 <b>Buyurtmalaringiz:</b>\n\n"
    status_map = {"completed": "✅", "failed": "❌", "processing": "⏳"}
    for o in orders[-10:][::-1]:
        st = status_map.get(o["status"], "❓")
        svc = {"premium": f"Premium {o.get('months',3)}oy", "stars": f"{o.get('stars',0)} Stars", "nft": "NFT"}.get(o["service"], o["service"])
        text += f"{st} #{o['id']} — {svc} — {fmt(o['price'])} so'm\n"
    await msg.answer(text, parse_mode="HTML")

# ═══════════════════════════════════════
# WEB ILOVA
# ═══════════════════════════════════════
@dp.message(F.text.in_(["🌐 Web ilova", "🌐 Веб приложение", "🌐 Web app"]))
async def web_app_cmd(msg: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🌐 Web ilovani ochish", url=WEB_URL)
    ]])
    await msg.answer("🌐 Web ilovani ochish uchun tugmani bosing:", reply_markup=kb)

# ═══════════════════════════════════════
# REFERRAL
# ═══════════════════════════════════════
@dp.message(F.text.in_(["👥 Referral", "👥 Реферал"]))
async def referral_cmd(msg: types.Message):
    db = load_db()
    if not db["settings"].get("referral_active"):
        return
    uid = str(msg.from_user.id)
    user = db["users"].get(uid, {})
    link = f"https://t.me/{(await bot.get_me()).username}?start=ref_{uid}"
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t(msg.from_user.id, "copy_link"), switch_inline_query=link)
    ]])
    await msg.answer(
        t(msg.from_user.id, "ref_info",
          link=link,
          count=user.get("referrals", 0),
          bonus=fmt(user.get("ref_bonus_earned", 0)),
          per=fmt(db["settings"]["referral_bonus"])),
        parse_mode="HTML", reply_markup=kb
    )

# ═══════════════════════════════════════
# PROMO KOD
# ═══════════════════════════════════════
@dp.message(F.text.in_(["🎁 Promo kod", "🎁 Промо код", "🎁 Promo code"]))
async def promo_cmd(msg: types.Message, state: FSMContext):
    db = load_db()
    if not db["settings"].get("promo_active"):
        return
    await msg.answer(t(msg.from_user.id, "promo_enter"), reply_markup=cancel_keyboard(msg.from_user.id))
    await state.set_state(OrderState.entering_promo)

@dp.message(OrderState.entering_promo)
async def enter_promo(msg: types.Message, state: FSMContext):
    if msg.text in ["❌ Bekor qilish", "❌ Отмена", "❌ Cancel"]:
        await state.clear()
        await msg.answer(t(msg.from_user.id, "main_menu"), reply_markup=main_keyboard(msg.from_user.id))
        return
    db = load_db()
    uid = str(msg.from_user.id)
    code = msg.text.strip().upper()
    promos = db.get("promo_codes", {})
    if code not in promos:
        await msg.answer(t(msg.from_user.id, "promo_err"), reply_markup=main_keyboard(msg.from_user.id))
        await state.clear()
        return
    promo = promos[code]
    if promo.get("limit") and promo.get("used", 0) >= promo["limit"]:
        await msg.answer(t(msg.from_user.id, "promo_err"), reply_markup=main_keyboard(msg.from_user.id))
        await state.clear()
        return
    if uid in db["users"].get(uid, {}).get("promo_used", []):
        await msg.answer("❌ Siz bu promo kodni allaqachon ishlatgansiz!", reply_markup=main_keyboard(msg.from_user.id))
        await state.clear()
        return
    discount = promo["discount"]
    await msg.answer(t(msg.from_user.id, "promo_ok", discount=discount), parse_mode="HTML", reply_markup=main_keyboard(msg.from_user.id))
    await state.clear()

# ═══════════════════════════════════════
# SOZLAMALAR
# ═══════════════════════════════════════
@dp.message(F.text.in_(["⚙️ Sozlamalar", "⚙️ Настройки", "⚙️ Settings"]))
async def settings_cmd(msg: types.Message):
    db = load_db()
    uid = str(msg.from_user.id)
    lang = get_lang(msg.from_user.id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇺🇿 O'zbek", callback_data="setlang_uz"),
         InlineKeyboardButton(text="🇷🇺 Русский", callback_data="setlang_ru"),
         InlineKeyboardButton(text="🇬🇧 English", callback_data="setlang_en")],
    ])
    await msg.answer("🌐 Tilni tanlang / Выберите язык / Choose language:", reply_markup=kb)

@dp.callback_query(F.data.startswith("setlang_"))
async def setlang_cb(cb: types.CallbackQuery):
    lang = cb.data.replace("setlang_", "")
    update_user(cb.from_user.id, {"lang": lang})
    await cb.message.delete()
    await cb.message.answer(T[lang]["welcome"], parse_mode="HTML", reply_markup=main_keyboard(cb.from_user.id))

# ═══════════════════════════════════════
# ADMIN PANEL
# ═══════════════════════════════════════
@dp.message(Command("admin"))
async def admin_panel(msg: types.Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return
    await state.clear()
    db = load_db()
    total_users = len(db["users"])
    total_orders = len(db["orders"])
    completed = len([o for o in db["orders"] if o["status"] == "completed"])
    revenue = sum(o["price"] for o in db["orders"] if o["status"] == "completed")

    text = (
        f"👨‍💼 <b>Admin Panel</b>\n\n"
        f"👥 Foydalanuvchilar: <b>{total_users}</b>\n"
        f"📋 Buyurtmalar: <b>{total_orders}</b>\n"
        f"✅ Bajarilgan: <b>{completed}</b>\n"
        f"💰 Daromad: <b>{fmt(revenue)} so'm</b>"
    )

    is_super = is_super_admin(msg.from_user.id)
    buttons = [
        [InlineKeyboardButton(text="📊 Statistika", callback_data="adm_stats"),
         InlineKeyboardButton(text="👥 Foydalanuvchilar", callback_data="adm_users")],
        [InlineKeyboardButton(text="📋 Buyurtmalar", callback_data="adm_orders"),
         InlineKeyboardButton(text="📢 Xabar yuborish", callback_data="adm_broadcast")],
    ]
    if is_super:
        buttons += [
            [InlineKeyboardButton(text="💳 Kartalar", callback_data="adm_cards"),
             InlineKeyboardButton(text="⚙️ Sozlamalar", callback_data="adm_settings")],
            [InlineKeyboardButton(text="👑 Adminlar", callback_data="adm_admins"),
             InlineKeyboardButton(text="📢 Kanallar", callback_data="adm_channels")],
            [InlineKeyboardButton(text="🎁 Promo kodlar", callback_data="adm_promos"),
             InlineKeyboardButton(text="👥 Referral", callback_data="adm_referral")],
            [InlineKeyboardButton(text=f"🤖 Bot {'o\'chirish' if db['settings']['bot_active'] else 'yoqish'}", callback_data="adm_toggle_bot")],
            [InlineKeyboardButton(text="🌐 Web ilova", url=WEB_URL + "?admin=1")],
        ]
    await msg.answer(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data == "adm_toggle_bot")
async def toggle_bot(cb: types.CallbackQuery):
    if not is_super_admin(cb.from_user.id):
        return
    db = load_db()
    db["settings"]["bot_active"] = not db["settings"]["bot_active"]
    save_db(db)
    status = "yoqildi ✅" if db["settings"]["bot_active"] else "o'chirildi ❌"
    await cb.answer(f"Bot {status}", show_alert=True)
    await admin_panel(cb.message, None)

@dp.callback_query(F.data == "adm_settings")
async def adm_settings(cb: types.CallbackQuery):
    if not is_super_admin(cb.from_user.id):
        return
    db = load_db()
    s = db["settings"]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"📈 Foiz: {s['markup']}%", callback_data="adm_set_markup")],
        [InlineKeyboardButton(text=f"⭐ Min Stars: {s['min_stars']}", callback_data="adm_set_minstars")],
        [InlineKeyboardButton(text=f"👥 Referral: {'✅' if s.get('referral_active') else '❌'}", callback_data="adm_toggle_ref")],
        [InlineKeyboardButton(text=f"🎁 Promo: {'✅' if s.get('promo_active') else '❌'}", callback_data="adm_toggle_promo")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="adm_back")],
    ])
    await cb.message.edit_text("⚙️ <b>Sozlamalar</b>", parse_mode="HTML", reply_markup=kb)

@dp.callback_query(F.data == "adm_toggle_ref")
async def toggle_ref(cb: types.CallbackQuery):
    if not is_super_admin(cb.from_user.id):
        return
    db = load_db()
    db["settings"]["referral_active"] = not db["settings"]["referral_active"]
    save_db(db)
    status = "yoqildi ✅" if db["settings"]["referral_active"] else "o'chirildi ❌"
    await cb.answer(f"Referral {status}", show_alert=True)
    await adm_settings(cb)

@dp.callback_query(F.data == "adm_toggle_promo")
async def toggle_promo(cb: types.CallbackQuery):
    if not is_super_admin(cb.from_user.id):
        return
    db = load_db()
    db["settings"]["promo_active"] = not db["settings"]["promo_active"]
    save_db(db)
    status = "yoqildi ✅" if db["settings"]["promo_active"] else "o'chirildi ❌"
    await cb.answer(f"Promo {status}", show_alert=True)
    await adm_settings(cb)

@dp.callback_query(F.data == "adm_set_markup")
async def adm_set_markup(cb: types.CallbackQuery, state: FSMContext):
    if not is_super_admin(cb.from_user.id):
        return
    await cb.message.edit_text("📈 Yangi foizni kiriting (masalan: 20):")
    await state.set_state(AdminState.entering_markup)

@dp.message(AdminState.entering_markup)
async def enter_markup(msg: types.Message, state: FSMContext):
    try:
        markup = int(msg.text)
        db = load_db()
        db["settings"]["markup"] = markup
        save_db(db)
        await msg.answer(f"✅ Foiz {markup}% ga o'zgartirildi!")
        await state.clear()
        await admin_panel(msg, state)
    except:
        await msg.answer("❌ Faqat raqam kiriting!")

@dp.callback_query(F.data == "adm_cards")
async def adm_cards(cb: types.CallbackQuery, state: FSMContext):
    if not is_super_admin(cb.from_user.id):
        return
    db = load_db()
    cards = db["settings"]["cards"]
    cards_text = "\n".join([f"• {c}" for c in cards]) if cards else "Kartalar yo'q"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Karta qo'shish", callback_data="adm_add_card")],
        [InlineKeyboardButton(text="🗑 Barcha kartalarni o'chirish", callback_data="adm_clear_cards")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="adm_back")],
    ])
    await cb.message.edit_text(f"💳 <b>Kartalar:</b>\n\n{cards_text}", parse_mode="HTML", reply_markup=kb)

@dp.callback_query(F.data == "adm_add_card")
async def adm_add_card(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.edit_text("💳 Yangi karta raqamini kiriting:")
    await state.set_state(AdminState.entering_card)

@dp.message(AdminState.entering_card)
async def enter_card(msg: types.Message, state: FSMContext):
    db = load_db()
    db["settings"]["cards"].append(msg.text.strip())
    save_db(db)
    await msg.answer(f"✅ Karta qo'shildi: {msg.text.strip()}")
    await state.clear()
    await admin_panel(msg, state)

@dp.callback_query(F.data == "adm_clear_cards")
async def adm_clear_cards(cb: types.CallbackQuery):
    db = load_db()
    db["settings"]["cards"] = []
    save_db(db)
    await cb.answer("✅ Barcha kartalar o'chirildi!")
    await adm_cards(cb, None)

@dp.callback_query(F.data == "adm_channels")
async def adm_channels(cb: types.CallbackQuery, state: FSMContext):
    if not is_super_admin(cb.from_user.id):
        return
    db = load_db()
    channels = db["settings"]["required_channels"]
    logs = db["settings"].get("logs_channel", "Yo'q")
    ch_text = "\n".join([f"• {c}" for c in channels]) if channels else "Kanallar yo'q"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Kanal qo'shish", callback_data="adm_add_channel")],
        [InlineKeyboardButton(text="📝 Logs kanali", callback_data="adm_set_logs")],
        [InlineKeyboardButton(text="🗑 Barcha kanallarni o'chirish", callback_data="adm_clear_channels")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="adm_back")],
    ])
    await cb.message.edit_text(
        f"📢 <b>Majburiy kanallar:</b>\n{ch_text}\n\n📝 <b>Logs kanali:</b> {logs}",
        parse_mode="HTML", reply_markup=kb
    )

@dp.callback_query(F.data == "adm_add_channel")
async def adm_add_channel(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.edit_text("📢 Kanal username kiriting (masalan: @channel):")
    await state.set_state(AdminState.entering_channel)

@dp.message(AdminState.entering_channel)
async def enter_channel(msg: types.Message, state: FSMContext):
    db = load_db()
    db["settings"]["required_channels"].append(msg.text.strip())
    save_db(db)
    await msg.answer(f"✅ Kanal qo'shildi: {msg.text.strip()}")
    await state.clear()
    await admin_panel(msg, state)

@dp.callback_query(F.data == "adm_set_logs")
async def adm_set_logs(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.edit_text("📝 Logs kanali username kiriting (masalan: @logs):")
    await state.set_state(AdminState.entering_logs_channel)

@dp.message(AdminState.entering_logs_channel)
async def enter_logs(msg: types.Message, state: FSMContext):
    db = load_db()
    db["settings"]["logs_channel"] = msg.text.strip()
    save_db(db)
    await msg.answer(f"✅ Logs kanali: {msg.text.strip()}")
    await state.clear()
    await admin_panel(msg, state)

@dp.callback_query(F.data == "adm_clear_channels")
async def adm_clear_channels(cb: types.CallbackQuery):
    db = load_db()
    db["settings"]["required_channels"] = []
    save_db(db)
    await cb.answer("✅ Kanallar o'chirildi!")

@dp.callback_query(F.data == "adm_admins")
async def adm_admins(cb: types.CallbackQuery, state: FSMContext):
    if not is_super_admin(cb.from_user.id):
        return
    db = load_db()
    admins = db.get("admins", {})
    adm_text = "\n".join([f"• ID: {a}" for a in admins.keys()]) if admins else "Adminlar yo'q"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Admin qo'shish", callback_data="adm_add_admin")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="adm_back")],
    ])
    await cb.message.edit_text(f"👑 <b>Adminlar:</b>\n\n{adm_text}", parse_mode="HTML", reply_markup=kb)

@dp.callback_query(F.data == "adm_add_admin")
async def adm_add_admin(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.edit_text("👑 Admin ID sini kiriting:")
    await state.set_state(AdminState.entering_admin_id)

@dp.message(AdminState.entering_admin_id)
async def enter_admin_id(msg: types.Message, state: FSMContext):
    try:
        new_admin_id = int(msg.text.strip())
        if new_admin_id == SUPER_ADMIN_ID:
            await msg.answer("❌ Asosiy admin allaqachon admin!")
            await state.clear()
            return
        db = load_db()
        db["admins"][str(new_admin_id)] = {"added_by": msg.from_user.id, "added_at": datetime.now().isoformat()}
        save_db(db)
        await msg.answer(f"✅ Admin qo'shildi: {new_admin_id}")
        await state.clear()
        await admin_panel(msg, state)
    except:
        await msg.answer("❌ Noto'g'ri ID!")

@dp.callback_query(F.data == "adm_broadcast")
async def adm_broadcast(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return
    await cb.message.edit_text("📢 Barcha foydalanuvchilarga yuboriladigan xabarni yozing:")
    await state.set_state(AdminState.entering_broadcast)

@dp.message(AdminState.entering_broadcast)
async def enter_broadcast(msg: types.Message, state: FSMContext):
    db = load_db()
    sent = 0
    failed = 0
    for uid in db["users"].keys():
        try:
            await bot.send_message(int(uid), f"📢 <b>Xabar:</b>\n\n{msg.text}", parse_mode="HTML")
            sent += 1
        except:
            failed += 1
        await asyncio.sleep(0.05)
    await msg.answer(f"✅ Xabar yuborildi!\n\n✅ Muvaffaqiyatli: {sent}\n❌ Xato: {failed}")
    await state.clear()

@dp.callback_query(F.data == "adm_promos")
async def adm_promos(cb: types.CallbackQuery, state: FSMContext):
    if not is_super_admin(cb.from_user.id):
        return
    db = load_db()
    promos = db.get("promo_codes", {})
    promo_text = "\n".join([f"• <code>{k}</code> — {v['discount']}% (ishlatilgan: {v.get('used',0)}/{v.get('limit','∞')})" for k, v in promos.items()]) if promos else "Promo kodlar yo'q"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Promo kod yaratish", callback_data="adm_create_promo")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="adm_back")],
    ])
    await cb.message.edit_text(f"🎁 <b>Promo kodlar:</b>\n\n{promo_text}", parse_mode="HTML", reply_markup=kb)

@dp.callback_query(F.data == "adm_create_promo")
async def adm_create_promo(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.edit_text("🎁 Promo kod nomini kiriting (masalan: SALE20):")
    await state.set_state(AdminState.entering_promo_code)

@dp.message(AdminState.entering_promo_code)
async def enter_promo_code(msg: types.Message, state: FSMContext):
    await state.update_data(promo_code=msg.text.strip().upper())
    await msg.answer("📈 Chegirma foizini kiriting (masalan: 20):")
    await state.set_state(AdminState.entering_promo_discount)

@dp.message(AdminState.entering_promo_discount)
async def enter_promo_discount(msg: types.Message, state: FSMContext):
    try:
        discount = int(msg.text)
        await state.update_data(promo_discount=discount)
        await msg.answer("🔢 Foydalanish limitini kiriting (0 = cheksiz):")
        await state.set_state(AdminState.entering_promo_limit)
    except:
        await msg.answer("❌ Faqat raqam kiriting!")

@dp.message(AdminState.entering_promo_limit)
async def enter_promo_limit(msg: types.Message, state: FSMContext):
    try:
        limit = int(msg.text)
        data = await state.get_data()
        db = load_db()
        code = data["promo_code"]
        db["promo_codes"][code] = {
            "discount": data["promo_discount"],
            "limit": limit if limit > 0 else None,
            "used": 0,
            "created_at": datetime.now().isoformat()
        }
        save_db(db)
        await msg.answer(f"✅ Promo kod yaratildi!\n\n🎁 Kod: <code>{code}</code>\n📈 Chegirma: {data['promo_discount']}%\n🔢 Limit: {limit if limit > 0 else 'Cheksiz'}", parse_mode="HTML")
        await state.clear()
        await admin_panel(msg, state)
    except:
        await msg.answer("❌ Faqat raqam kiriting!")

@dp.callback_query(F.data == "adm_users")
async def adm_users(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        return
    db = load_db()
    users = db["users"]
    total = len(users)
    banned = len([u for u in users.values() if u.get("banned")])
    text = f"👥 <b>Foydalanuvchilar:</b>\n\nJami: <b>{total}</b>\nBanlangan: <b>{banned}</b>"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚫 Foydalanuvchini bloklash", callback_data="adm_ban_user")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="adm_back")],
    ])
    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)

@dp.callback_query(F.data == "adm_ban_user")
async def adm_ban_user(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.edit_text("🚫 Bloklash uchun foydalanuvchi ID sini kiriting:")
    await state.set_state(AdminState.entering_ban_user)

@dp.message(AdminState.entering_ban_user)
async def enter_ban_user(msg: types.Message, state: FSMContext):
    try:
        ban_id = str(int(msg.text.strip()))
        db = load_db()
        if ban_id in db["users"]:
            db["users"][ban_id]["banned"] = True
            save_db(db)
            await msg.answer(f"✅ Foydalanuvchi {ban_id} bloklandi!")
        else:
            await msg.answer("❌ Foydalanuvchi topilmadi!")
        await state.clear()
        await admin_panel(msg, state)
    except:
        await msg.answer("❌ Noto'g'ri ID!")

@dp.callback_query(F.data == "adm_back")
async def adm_back(cb: types.CallbackQuery, state: FSMContext):
    await admin_panel(cb.message, state)

@dp.callback_query(F.data == "adm_stats")
async def adm_stats(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        return
    db = load_db()
    today = datetime.now().date().isoformat()
    today_orders = [o for o in db["orders"] if o["created_at"][:10] == today]
    today_revenue = sum(o["price"] for o in today_orders if o["status"] == "completed")
    total_revenue = sum(o["price"] for o in db["orders"] if o["status"] == "completed")
    text = (
        f"📊 <b>Statistika</b>\n\n"
        f"👥 Jami foydalanuvchilar: <b>{len(db['users'])}</b>\n"
        f"📋 Jami buyurtmalar: <b>{len(db['orders'])}</b>\n"
        f"✅ Bajarilgan: <b>{len([o for o in db['orders'] if o['status']=='completed'])}</b>\n"
        f"❌ Xato: <b>{len([o for o in db['orders'] if o['status']=='failed'])}</b>\n\n"
        f"📅 Bugungi buyurtmalar: <b>{len(today_orders)}</b>\n"
        f"💰 Bugungi daromad: <b>{fmt(today_revenue)} so'm</b>\n"
        f"💰 Jami daromad: <b>{fmt(total_revenue)} so'm</b>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Orqaga", callback_data="adm_back")]])
    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)

@dp.callback_query(F.data == "adm_referral")
async def adm_referral(cb: types.CallbackQuery):
    if not is_super_admin(cb.from_user.id):
        return
    db = load_db()
    s = db["settings"]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"👥 Referral: {'✅ Yoqilgan' if s.get('referral_active') else '❌ O\'chirilgan'}", callback_data="adm_toggle_ref")],
        [InlineKeyboardButton(text=f"💰 Bonus: {fmt(s.get('referral_bonus', 5000))} so'm", callback_data="adm_set_ref_bonus")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="adm_back")],
    ])
    await cb.message.edit_text("👥 <b>Referral tizimi</b>", parse_mode="HTML", reply_markup=kb)

# ═══════════════════════════════════════
# MAIN
# ═══════════════════════════════════════
async def main():
    log.info("U-Gift Bot ishga tushmoqda...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
