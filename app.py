from flask import Flask, request, jsonify, render_template, send_from_directory
import json, os, asyncio, aiohttp
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
DB = "database.json"

SUPER_ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
TON_API_KEY = os.getenv("TON_API_KEY", "")
FRAGMENT_COOKIES = os.getenv("FRAGMENT_COOKIES", "")

def db():
    if os.path.exists(DB):
        with open(DB, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"users": {}, "orders": [], "admins": {}, "promo_codes": {},
            "settings": {"markup": 20, "min_stars": 50, "bot_active": True,
                         "referral_active": False, "promo_active": False,
                         "referral_bonus": 5000, "cards": [],
                         "required_channels": [], "logs_channel": None}}

def sdb(data):
    with open(DB, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def fmt(n): return f"{int(n):,}".replace(",", " ")

def is_admin(uid):
    d = db()
    return int(uid) == SUPER_ADMIN_ID or str(uid) in d.get("admins", {})

# ═══════════════════════════════════
# RATES
# ═══════════════════════════════════
_rate_cache = {"val": 44800.0, "usd": 12800.0, "ton": 3.5, "ts": 0}

async def fetch_rates():
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get("https://api.coingecko.com/api/v3/simple/price?ids=the-open-network&vs_currencies=usd",
                             timeout=aiohttp.ClientTimeout(total=5)) as r:
                td = await r.json(); ton_usd = td["the-open-network"]["usd"]
            async with s.get("https://cbu.uz/uz/arkhiv-kursov-valyut/json/USD/",
                             timeout=aiohttp.ClientTimeout(total=5)) as r:
                cd = await r.json(); usd_uzs = float(cd[0]["Rate"])
        _rate_cache.update({"val": ton_usd * usd_uzs, "usd": usd_uzs, "ton": ton_usd, "ts": 1})
    except: pass
    return _rate_cache

def get_rates_sync():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result = loop.run_until_complete(fetch_rates())
    loop.close()
    return result

# ═══════════════════════════════════
# ROUTES
# ═══════════════════════════════════
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/settings")
def api_settings():
    d = db()
    s = d["settings"]
    uid = request.args.get("uid", "0")
    user = d["users"].get(str(uid), {})
    return jsonify({
        "markup": s["markup"],
        "min_stars": s["min_stars"],
        "referral_active": s.get("referral_active", False),
        "promo_active": s.get("promo_active", False),
        "referral_bonus": s.get("referral_bonus", 5000),
        "balance": user.get("balance", 0),
        "referrals": user.get("referrals", 0),
        "ref_earned": user.get("ref_earned", 0),
    })

@app.route("/api/rates")
def api_rates():
    rates = get_rates_sync()
    d = db()
    markup = d["settings"]["markup"]
    return jsonify({
        "ton_usd": rates["ton"],
        "usd_uzs": rates["usd"],
        "ton_uzs": rates["val"],
        "markup": markup
    })

@app.route("/api/send", methods=["POST"])
def api_send():
    data = request.json
    d = db()
    uid = str(data.get("user_id", "0"))
    service = data.get("service")
    username = data.get("username")
    price = data.get("price", 0)
    months = data.get("months")
    stars = data.get("stars")
    nft_link = data.get("nft_link")

    # Balans tekshirish
    if uid not in d["users"]:
        return jsonify({"success": False, "error": "Foydalanuvchi topilmadi"})
    bal = d["users"][uid].get("balance", 0)
    if bal < price:
        return jsonify({"success": False, "error": "Balans yetarli emas"})

    # Balansdan yechish
    d["users"][uid]["balance"] -= price

    # Buyurtma yaratish
    order = {
        "id": len(d["orders"]) + 1, "user_id": uid,
        "service": service, "username": username,
        "months": months, "stars": stars, "nft_link": nft_link,
        "price": price, "status": "processing",
        "created_at": datetime.now().isoformat(), "source": "webapp"
    }
    d["orders"].append(order)
    d["users"][uid].setdefault("orders", []).append(order["id"])
    sdb(d)

    # Fragment API
    success = send_fragment(order)
    d = db()
    if success:
        for o in d["orders"]:
            if o["id"] == order["id"]: o["status"] = "completed"
        sdb(d)
        return jsonify({"success": True, "order_id": order["id"]})
    else:
        d["users"][uid]["balance"] += price
        for o in d["orders"]:
            if o["id"] == order["id"]: o["status"] = "failed"
        sdb(d)
        return jsonify({"success": False, "error": "Fragment API xatosi"})

def send_fragment(order):
    try:
        from FragmentAPI import SyncFragmentAPI
        api = SyncFragmentAPI(cookies=FRAGMENT_COOKIES, wallet_api_key=TON_API_KEY)
        if order["service"] == "premium": r = api.buy_premium(order["username"], order["months"])
        elif order["service"] == "stars": r = api.buy_stars(order["username"], order["stars"])
        elif order["service"] == "nft": r = api.buy_nft(order["nft_link"])
        else: return False
        return bool(r)
    except Exception as e:
        print(f"Fragment error: {e}"); return False

@app.route("/api/nft-price", methods=["POST"])
def api_nft_price():
    data = request.json; link = data.get("link", "")
    if "fragment.com" not in link:
        return jsonify({"success": False, "error": "Noto'g'ri link"})
    try:
        from FragmentAPI import SyncFragmentAPI
        api = SyncFragmentAPI(cookies=FRAGMENT_COOKIES, wallet_api_key=TON_API_KEY)
        nft = api.get_nft_info(link)
        return jsonify({
            "success": True,
            "ton_price": nft.price if hasattr(nft, 'price') else 5.0,
            "name": nft.name if hasattr(nft, 'name') else "NFT"
        })
    except:
        return jsonify({"success": False, "error": "NFT ma'lumotlari topilmadi"})

@app.route("/api/promo", methods=["POST"])
def api_promo():
    data = request.json; code = data.get("code", "").upper()
    d = db(); promos = d.get("promo_codes", {})
    if code not in promos:
        return jsonify({"success": False, "error": "Noto'g'ri promo kod"})
    promo = promos[code]
    if promo.get("limit") and promo.get("used", 0) >= promo["limit"]:
        return jsonify({"success": False, "error": "Limit tugagan"})
    return jsonify({"success": True, "discount": promo["discount"]})

@app.route("/api/topup", methods=["POST"])
def api_topup():
    # Bot orqali to'ldirish uchun yo'naltirish
    return jsonify({"success": True, "bot_url": f"https://t.me/UGiftBot?start=topup"})

@app.route("/api/history")
def api_history():
    uid = request.args.get("uid", "0")
    d = db()
    orders = [o for o in d["orders"] if o["user_id"] == str(uid)][-20:]
    return jsonify({"orders": list(reversed(orders))})

# ═══════════════════════════════════
# ADMIN API
# ═══════════════════════════════════
@app.route("/api/admin/stats")
def api_admin_stats():
    admin_id = request.args.get("admin_id", "0")
    if not is_admin(admin_id):
        return jsonify({"error": "Unauthorized"}), 401
    d = db(); today = datetime.now().date().isoformat()
    t_rev = sum(o["price"] for o in d["orders"] if o["status"] == "completed" and o["created_at"][:10] == today)
    total_rev = sum(o["price"] for o in d["orders"] if o["status"] == "completed")
    return jsonify({
        "users": len(d["users"]),
        "orders": len(d["orders"]),
        "completed": len([o for o in d["orders"] if o["status"] == "completed"]),
        "revenue": total_rev,
        "today_revenue": t_rev,
        "markup": d["settings"]["markup"],
        "referral_active": d["settings"].get("referral_active", False),
        "promo_active": d["settings"].get("promo_active", False),
    })

@app.route("/api/admin/markup", methods=["POST"])
def api_admin_markup():
    data = request.json; admin_id = data.get("admin_id", 0)
    if not is_admin(admin_id): return jsonify({"error": "Unauthorized"}), 401
    d = db(); d["settings"]["markup"] = data.get("markup", 20); sdb(d)
    return jsonify({"success": True})

@app.route("/api/admin/settings", methods=["POST"])
def api_admin_settings():
    data = request.json; admin_id = data.get("admin_id", 0)
    if not is_admin(admin_id): return jsonify({"error": "Unauthorized"}), 401
    d = db()
    if "referral_active" in data: d["settings"]["referral_active"] = data["referral_active"]
    if "promo_active" in data: d["settings"]["promo_active"] = data["promo_active"]
    if "referral_bonus" in data: d["settings"]["referral_bonus"] = data["referral_bonus"]
    if "markup" in data: d["settings"]["markup"] = data["markup"]
    sdb(d)
    return jsonify({"success": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
