# -*- coding: utf-8 -*-
"""AQUA HOME — hammom jihozlari uchun Telegram bot + Mini App."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import html
import json
import logging
import os
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from flask import Flask, jsonify, request, Response
from waitress import serve
from telegram import (
    InlineKeyboardButton, InlineKeyboardMarkup, MenuButtonWebApp, ReplyKeyboardMarkup,
    KeyboardButton, WebAppInfo, BotCommand, Update,
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ConversationHandler,
    MessageHandler, ContextTypes, filters,
)

load_dotenv()

APP_NAME = os.getenv("APP_NAME", "AQUA HOME")
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS = {int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()}
HOST_PORT = int(os.getenv("PORT", "10000"))
DB_PATH = os.getenv("DB_PATH", str(Path(__file__).with_name("aqua_home.db")))
RENDER_HOST = os.getenv("RENDER_EXTERNAL_HOSTNAME", "").strip()
WEBAPP_URL = (os.getenv("WEBAPP_URL", "").strip() or (f"https://{RENDER_HOST}" if RENDER_HOST else "")).rstrip("/")
WEBHOOK_PATH_SECRET = hashlib.sha256(BOT_TOKEN.encode()).hexdigest()[:32] if BOT_TOKEN else "not-configured"
BOT_APPLICATION = None
BOT_LOOP = None
if WEBAPP_URL and not WEBAPP_URL.startswith("https://"):
    logging.warning("WEBAPP_URL HTTPS bilan boshlanishi kerak. Mini App tugmasi o'chirildi.")
    WEBAPP_URL = ""

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=os.getenv("LOG_LEVEL", "INFO"),
)
log = logging.getLogger("aqua_home")
web = Flask(__name__)
web.config["MAX_CONTENT_LENGTH"] = 128 * 1024

# Namuna katalog. Mahsulotlar keyinchalik Telegram'dagi /addproduct orqali qo'shiladi.
SEED_PRODUCTS = [
    ("AquaLine bir richagli kran", "Kranlar", 389000, "Oshxona va hammom uchun zamonaviy, xrom qoplamali kran. Oson tozalanadi.", "https://images.unsplash.com/photo-1620626011761-996317b8d101?auto=format&fit=crop&w=900&q=85", "TOP"),
    ("RainPro yomg'ir dushi", "Dush tizimlari", 890000, "Keng boshli yomg'ir dushi, mustahkam metall konstruksiya va minimal dizayn.", "https://images.unsplash.com/photo-1620626011761-996317b8d101?auto=format&fit=crop&w=900&q=85", "HIT"),
    ("Ceramix oq rakvina", "Rakvinalar", 650000, "Silliq keramika, zamonaviy shakl va kundalik foydalanish uchun qulay o'lcham.", "https://images.unsplash.com/photo-1600566753086-00f18fb6b3ea?auto=format&fit=crop&w=900&q=85", "YANGI"),
    ("Nord unitaz komplekti", "Unitazlar", 1450000, "Oson parvarishlanadigan keramika va tejamkor suv chiqarish tizimi.", "https://images.unsplash.com/photo-1584622650111-993a426fbf0a?auto=format&fit=crop&w=900&q=85", "TOP"),
    ("Luna hammom tumba-rakvinasi", "Hammom mebeli", 1890000, "Namlikka chidamli material, saqlash uchun keng joy va ixcham dizayn.", "https://images.unsplash.com/photo-1600566753190-17f0baa2a6c3?auto=format&fit=crop&w=900&q=85", "YANGI"),
    ("SteelFlex dush shlangi", "Dush tizimlari", 99000, "Moslashuvchan mustahkam shlang, standart ulanish va xrom rang.", "https://images.unsplash.com/photo-1620626011761-996317b8d101?auto=format&fit=crop&w=900&q=85", ""),
    ("SoftClose unitaz qopqog'i", "Unitazlar", 245000, "Sekin yopiladigan mexanizm, mustahkam material va qulay o'rnatish.", "https://images.unsplash.com/photo-1584622650111-993a426fbf0a?auto=format&fit=crop&w=900&q=85", ""),
    ("Minimal oynali javon", "Hammom mebeli", 520000, "Ko'zgu va yopiq javon bir mahsulotda. Kichik hammomlar uchun mos.", "https://images.unsplash.com/photo-1600566753086-00f18fb6b3ea?auto=format&fit=crop&w=900&q=85", "HIT"),
    ("BrassMix dush krani", "Kranlar", 475000, "Issiq va sovuq suv haroratini qulay boshqarish uchun ixcham kran.", "https://images.unsplash.com/photo-1620626011761-996317b8d101?auto=format&fit=crop&w=900&q=85", ""),
    ("Hammom aksessuarlari to'plami", "Aksessuarlar", 319000, "Sochiq ilgichi, qog'oz ushlagichi va ilgaklar to'plami.", "https://images.unsplash.com/photo-1600566753190-17f0baa2a6c3?auto=format&fit=crop&w=900&q=85", "CHEGIRMA"),
    ("Square qora rakvina krani", "Kranlar", 429000, "Qora mat qoplama va geometrik shakl zamonaviy interyerga mos tushadi.", "https://images.unsplash.com/photo-1600566753086-00f18fb6b3ea?auto=format&fit=crop&w=900&q=85", "YANGI"),
    ("Termo dush paneli", "Dush tizimlari", 1290000, "Dush rejimlarini tanlash va suv haroratini barqaror ushlash uchun panel.", "https://images.unsplash.com/photo-1620626011761-996317b8d101?auto=format&fit=crop&w=900&q=85", "TOP"),
]

STATUSES = {
    "new": "🆕 Yangi",
    "accepted": "✅ Qabul qilindi",
    "delivery": "🚚 Yetkazilmoqda",
    "done": "🏁 Yakunlandi",
    "cancelled": "❌ Bekor qilindi",
}


def db_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    with db_connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            price INTEGER NOT NULL CHECK(price >= 0),
            description TEXT NOT NULL DEFAULT '',
            image_url TEXT NOT NULL DEFAULT '',
            badge TEXT NOT NULL DEFAULT '',
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER NOT NULL,
            username TEXT NOT NULL DEFAULT '',
            customer_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            address TEXT NOT NULL,
            comment TEXT NOT NULL DEFAULT '',
            total INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'new',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
            product_id INTEGER,
            product_name TEXT NOT NULL,
            unit_price INTEGER NOT NULL,
            quantity INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_orders_telegram_id ON orders(telegram_id);
        """)
        count = db.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        if count == 0:
            db.executemany(
                "INSERT INTO products(name, category, price, description, image_url, badge) VALUES (?, ?, ?, ?, ?, ?)",
                SEED_PRODUCTS,
            )
        db.commit()


def money(amount: int | float) -> str:
    return f"{int(amount):,}".replace(",", " ") + " so'm"


def validate_init_data(init_data: str) -> dict | None:
    """Telegram Mini App initData imzosini tekshiradi; ishonchsiz user ma'lumotini qabul qilmaydi."""
    if not BOT_TOKEN or not init_data or len(init_data) > 10000:
        return None
    try:
        values = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=False))
        received_hash = values.pop("hash", None)
        if not received_hash:
            return None
        check_string = "\n".join(f"{key}={value}" for key, value in sorted(values.items()))
        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calculated_hash, received_hash):
            return None
        auth_date = int(values.get("auth_date", "0"))
        if auth_date <= 0 or time.time() - auth_date > 86400 or auth_date - time.time() > 60:
            return None
        user = json.loads(values.get("user", "{}"))
        if not isinstance(user, dict) or not user.get("id"):
            return None
        return user
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def telegram_api(method: str, payload: dict, timeout: int = 7) -> bool:
    if not BOT_TOKEN:
        return False
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/{method}", data=data,
        headers={"Content-Type": "application/json; charset=utf-8"}, method="POST",
    )
    try:
        with urlopen(req, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
            return bool(body.get("ok"))
    except Exception as exc:
        log.warning("Telegram API xabari yuborilmadi (%s): %s", method, exc)
        return False


def notify_admins(text: str, order_id: int | None = None) -> None:
    buttons = []
    if order_id:
        buttons = [[
            {"text": "✅ Qabul qilish", "callback_data": f"status:{order_id}:accepted"},
            {"text": "🚚 Yetkazilmoqda", "callback_data": f"status:{order_id}:delivery"},
        ], [
            {"text": "🏁 Yakunlash", "callback_data": f"status:{order_id}:done"},
            {"text": "❌ Bekor qilish", "callback_data": f"status:{order_id}:cancelled"},
        ]]
    for admin_id in ADMIN_IDS:
        payload = {"chat_id": admin_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
        if buttons:
            payload["reply_markup"] = {"inline_keyboard": buttons}
        telegram_api("sendMessage", payload)


@web.get("/")
def mini_app() -> Response:
    return Response(MINI_APP_HTML, mimetype="text/html; charset=utf-8")


@web.get("/health")
def health() -> tuple:
    return jsonify({"ok": True, "app": APP_NAME}), 200


@web.post("/telegram-webhook/<secret_path>")
def telegram_webhook(secret_path: str):
    """Render/webhook rejimida Telegram update'larini bot event loop'iga uzatadi."""
    supplied_header = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not hmac.compare_digest(secret_path, WEBHOOK_PATH_SECRET) or not hmac.compare_digest(supplied_header, WEBHOOK_PATH_SECRET):
        return jsonify({"ok": False}), 403
    if BOT_APPLICATION is None or BOT_LOOP is None:
        return jsonify({"ok": False, "error": "Bot hali ishga tushmoqda"}), 503
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"ok": False}), 400
    try:
        update = Update.de_json(payload, BOT_APPLICATION.bot)
        future = asyncio.run_coroutine_threadsafe(BOT_APPLICATION.update_queue.put(update), BOT_LOOP)
        future.result(timeout=5)
        return jsonify({"ok": True}), 200
    except Exception as exc:
        log.warning("Webhook update qabul qilinmadi: %s", exc)
        return jsonify({"ok": False}), 500


@web.get("/api/products")
def api_products():
    with db_connect() as db:
        rows = db.execute(
            "SELECT id, name, category, price, description, image_url, badge FROM products WHERE active = 1 ORDER BY id DESC"
        ).fetchall()
    products = [dict(row) for row in rows]
    return jsonify({"products": products, "categories": sorted({p["category"] for p in products}), "store": APP_NAME})


@web.post("/api/order")
def api_create_order():
    body = request.get_json(silent=True) or {}
    user = validate_init_data(str(body.get("init_data", "")))
    if not user:
        return jsonify({"ok": False, "error": "Buyurtma yuborish uchun mini app'ni Telegram ichidan oching."}), 401

    customer_name = str(body.get("customer_name", "")).strip()
    phone = str(body.get("phone", "")).strip()
    address = str(body.get("address", "")).strip()
    comment = str(body.get("comment", "")).strip()[:1000]
    items = body.get("items")
    if not (2 <= len(customer_name) <= 100):
        return jsonify({"ok": False, "error": "Ism-familiyani to'g'ri kiriting."}), 400
    digits = "".join(c for c in phone if c.isdigit())
    if not 9 <= len(digits) <= 15:
        return jsonify({"ok": False, "error": "Telefon raqamni to'g'ri kiriting."}), 400
    if not (4 <= len(address) <= 300):
        return jsonify({"ok": False, "error": "Yetkazib berish manzilini kiriting."}), 400
    if not isinstance(items, list) or not 1 <= len(items) <= 40:
        return jsonify({"ok": False, "error": "Savat bo'sh yoki mahsulotlar soni noto'g'ri."}), 400

    quantities: dict[int, int] = {}
    try:
        for item in items:
            product_id = int(item.get("product_id"))
            qty = int(item.get("quantity"))
            if product_id <= 0 or not 1 <= qty <= 20:
                raise ValueError
            quantities[product_id] = quantities.get(product_id, 0) + qty
        if any(qty > 20 for qty in quantities.values()):
            raise ValueError
    except (ValueError, AttributeError, TypeError):
        return jsonify({"ok": False, "error": "Savatdagi mahsulot miqdori noto'g'ri."}), 400

    with db_connect() as db:
        ids = list(quantities.keys())
        placeholders = ",".join("?" for _ in ids)
        product_rows = db.execute(
            f"SELECT id, name, price FROM products WHERE active = 1 AND id IN ({placeholders})", ids
        ).fetchall()
        products = {row["id"]: row for row in product_rows}
        if len(products) != len(ids):
            return jsonify({"ok": False, "error": "Ba'zi mahsulotlar endi mavjud emas. Katalogni yangilang."}), 409
        total = sum(int(products[pid]["price"]) * qty for pid, qty in quantities.items())
        username = str(user.get("username", ""))[:80]
        cursor = db.execute(
            "INSERT INTO orders(telegram_id, username, customer_name, phone, address, comment, total) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (int(user["id"]), username, customer_name, phone, address, comment, total),
        )
        order_id = int(cursor.lastrowid)
        for product_id, qty in quantities.items():
            product = products[product_id]
            db.execute(
                "INSERT INTO order_items(order_id, product_id, product_name, unit_price, quantity) VALUES (?, ?, ?, ?, ?)",
                (order_id, product_id, product["name"], int(product["price"]), qty),
            )
        db.commit()

    lines = [f"🛍 <b>Yangi buyurtma #{order_id}</b>", f"👤 Ism: {html.escape(customer_name)}"]
    if username:
        lines.append(f"Telegram: @{html.escape(username)}")
    lines += [f"📞 Telefon: {html.escape(phone)}", f"📍 Manzil: {html.escape(address)}", "", "<b>Mahsulotlar:</b>"]
    for pid, qty in quantities.items():
        product = products[pid]
        lines.append(f"• {html.escape(product['name'])} × {qty} — {money(int(product['price']) * qty)}")
    lines.append(f"\n💳 <b>Jami: {money(total)}</b>")
    lines.append("💬 Izoh: " + (html.escape(comment) if comment else "—"))
    lines.append("\nTo'lov mini app orqali olinmaydi. Buyurtma telefon orqali tasdiqlanadi.")
    notify_admins("\n".join(lines), order_id)
    log.info("New order #%s from Telegram user %s", order_id, user["id"])
    return jsonify({"ok": True, "order_id": order_id, "total": total})


# Mini App mijoz interfeysi — HTML/CSS/JS bot.py ichida, qo'shimcha frontend fayli talab qilinmaydi.
MINI_APP_HTML = r'''<!doctype html>
<html lang="uz">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<meta name="theme-color" content="#f5f7fb"><title>AQUA HOME — Hammom jihozlari</title>
<script src="https://telegram.org/js/telegram-web-app.js?63"></script>
<style>
:root{--ink:#142b3a;--muted:#71818c;--blue:#126e75;--blue2:#0b535a;--mint:#dff5ef;--bg:#f5f7fb;--card:#fff;--line:#e7edf1;--gold:#f5b94c;--radius:22px}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;padding-bottom:92px}button,input,textarea,select{font:inherit}button{cursor:pointer} .app{max-width:900px;margin:0 auto;padding:0 16px}.top{display:flex;align-items:center;justify-content:space-between;padding:17px 0 13px}.brand{display:flex;gap:10px;align-items:center}.logo{width:43px;height:43px;border-radius:15px;display:grid;place-items:center;color:#fff;background:linear-gradient(145deg,#16878b,#103a51);box-shadow:0 8px 18px #126e7526;font-size:22px}.brand b{font-size:17px;letter-spacing:.7px}.brand small{display:block;color:var(--muted);font-size:11px;letter-spacing:1.4px;margin-top:1px}.iconbtn{border:1px solid var(--line);background:white;border-radius:14px;width:42px;height:42px;position:relative;font-size:19px;color:var(--ink)}.badgecount{position:absolute;right:-5px;top:-5px;background:#ef6a50;color:white;border-radius:30px;font-size:10px;min-width:18px;height:18px;display:grid;place-items:center;border:2px solid var(--bg)}
.hero{margin-top:8px;border-radius:27px;padding:23px 21px;color:white;background:radial-gradient(circle at 90% 8%,#4bc7b0 0,transparent 33%),linear-gradient(120deg,#103c51,#137a7c);position:relative;overflow:hidden;min-height:185px}.hero:after{content:'◌';position:absolute;right:9px;bottom:-65px;font-size:230px;line-height:1;color:#ffffff12}.eyebrow{font-size:11px;letter-spacing:1.8px;text-transform:uppercase;color:#b8f0e3;font-weight:800}.hero h1{font-size:27px;line-height:1.1;max-width:275px;margin:11px 0 8px;letter-spacing:-.6px}.hero p{max-width:285px;margin:0;color:#d1e8eb;font-size:13px}.hero .pill{display:inline-flex;align-items:center;gap:7px;margin-top:16px;background:#ffffff18;border:1px solid #ffffff28;padding:8px 11px;border-radius:100px;font-size:11px;font-weight:700;position:relative;z-index:1}
.searchbox{margin:17px 0 15px;display:flex;align-items:center;gap:9px;background:#fff;border:1px solid var(--line);padding:0 14px;height:51px;border-radius:16px;box-shadow:0 4px 12px #18374805}.searchbox span{font-size:19px;color:var(--muted)}.searchbox input{border:0;outline:0;min-width:0;flex:1;background:transparent;color:var(--ink)}.sectionhead{display:flex;align-items:center;justify-content:space-between;margin:21px 0 12px}.sectionhead h2{margin:0;font-size:18px;letter-spacing:-.3px}.subtle{color:var(--muted);font-size:12px}.categories{display:flex;gap:8px;overflow:auto;padding:1px 0 5px;scrollbar-width:none}.categories::-webkit-scrollbar{display:none}.cat{white-space:nowrap;background:white;color:#5f707b;border:1px solid var(--line);padding:9px 13px;border-radius:100px;font-size:12px;font-weight:700}.cat.active{background:var(--ink);border-color:var(--ink);color:white}.tools{display:flex;align-items:center;justify-content:space-between;margin:18px 0 12px}.tools strong{font-size:17px}.tools select{border:1px solid var(--line);background:#fff;border-radius:12px;padding:8px 10px;color:#526772;max-width:155px;font-size:12px;outline:0}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.product{border:1px solid #edf0f2;background:white;border-radius:19px;padding:9px;min-width:0;box-shadow:0 3px 15px #122d3d04;position:relative}.photo{height:151px;border-radius:14px;overflow:hidden;background:#eaf2f2;position:relative;cursor:pointer}.photo img{width:100%;height:100%;object-fit:cover;display:block;transition:transform .25s}.photo:hover img{transform:scale(1.04)}.tag{position:absolute;left:8px;top:8px;background:#f7fbfaeF;color:#176b66;border-radius:8px;padding:5px 7px;font-size:9px;font-weight:900;letter-spacing:.5px}.heart{position:absolute;right:7px;top:7px;width:31px;height:31px;border:0;border-radius:50%;background:#ffffffed;color:#566b74;font-size:16px}.heart.on{color:#eb6556}.pname{font-weight:750;font-size:13px;line-height:1.3;margin:10px 1px 5px;min-height:34px;cursor:pointer}.pcat{font-size:10px;color:var(--muted);margin:0 1px 8px}.pricebar{display:flex;align-items:center;justify-content:space-between;gap:6px}.price{font-size:13px;font-weight:850;letter-spacing:-.2px;white-space:nowrap}.add{flex-shrink:0;border:0;border-radius:11px;background:var(--mint);color:#0f6763;font-size:20px;width:34px;height:34px;font-weight:500}.add:active{transform:scale(.95)}.empty{padding:35px 14px;text-align:center;background:white;border:1px dashed #cbd9dd;border-radius:20px;grid-column:1/-1}.empty .emoji{font-size:35px}.empty b{display:block;margin:10px 0 5px}.empty p{color:var(--muted);font-size:13px;margin:0}
.bottomnav{position:fixed;bottom:0;left:0;right:0;z-index:20;background:#ffffffee;backdrop-filter:blur(14px);border-top:1px solid var(--line);padding:9px max(14px,env(safe-area-inset-right)) calc(9px + env(safe-area-inset-bottom));display:flex;justify-content:center}.navinner{display:grid;grid-template-columns:repeat(3,1fr);width:min(500px,100%);gap:6px}.navitem{position:relative;border:0;background:transparent;color:#7c8b94;padding:7px 4px;border-radius:13px;font-size:10px;font-weight:700}.navitem span{display:block;font-size:21px;margin-bottom:3px}.navitem.active{background:#e4f5f0;color:#126e75}.navcount{position:absolute;top:1px;left:calc(50% + 6px);background:#ef6a50;color:#fff;border-radius:50px;min-width:16px;height:16px;font-size:9px;display:grid;place-items:center;border:2px solid white}
.scrim{position:fixed;inset:0;background:#0d2634a8;z-index:30;display:none;align-items:flex-end;justify-content:center;padding:0}.scrim.show{display:flex}.sheet{background:var(--bg);width:min(660px,100%);max-height:92vh;overflow:auto;border-radius:25px 25px 0 0;padding:16px 17px calc(22px + env(safe-area-inset-bottom));animation:rise .2s ease}.sheethead{display:flex;align-items:center;justify-content:space-between;margin-bottom:13px}.sheethead h2{font-size:19px;margin:0}.close{border:0;background:#e8eef0;border-radius:50%;width:34px;height:34px;font-size:20px;color:#526872}.cartrow{display:grid;grid-template-columns:67px 1fr auto;gap:11px;align-items:center;background:#fff;padding:9px;border:1px solid var(--line);border-radius:16px;margin:9px 0}.cartrow img{width:67px;height:67px;border-radius:12px;object-fit:cover;background:#edf4f5}.cartrow b{display:block;font-size:12px;line-height:1.3}.cartrow small{display:block;font-size:12px;color:var(--muted);margin-top:5px}.qty{display:flex;align-items:center;gap:8px;margin-top:7px}.qty button{width:25px;height:25px;border:1px solid var(--line);border-radius:8px;background:white;color:var(--ink)}.qty span{font-size:12px;font-weight:800;min-width:12px;text-align:center}.remove{border:0;background:transparent;color:#df7669;font-size:15px;margin-left:3px}.totalrow{display:flex;justify-content:space-between;align-items:center;border-top:1px dashed #cddadd;padding:15px 2px 12px;margin-top:15px}.totalrow span{color:var(--muted);font-size:13px}.totalrow b{font-size:20px}.primary{display:block;width:100%;border:0;border-radius:15px;background:var(--blue);color:white;font-weight:800;padding:15px 18px;box-shadow:0 8px 18px #126e7526}.primary:active{background:var(--blue2);transform:translateY(1px)}.secondary{border:1px solid var(--line);background:white;color:var(--ink);padding:12px 15px;border-radius:13px;font-weight:700}.formlabel{display:block;color:#60727c;font-size:12px;font-weight:750;margin:14px 0 6px}.field{width:100%;border:1px solid #dce6e9;background:white;color:var(--ink);border-radius:13px;padding:13px 13px;outline:0}.field:focus{border-color:#56aaa3;box-shadow:0 0 0 3px #56aaa31a}.field::placeholder{color:#a2afb5}.formnote{color:var(--muted);font-size:11px;margin:10px 0 15px}.detailimg{width:100%;height:230px;object-fit:cover;border-radius:17px;background:#e9f1f1}.detaildesc{color:#697b84;font-size:13px}.detailprice{font-size:23px;font-weight:900;margin:14px 0}.toast{position:fixed;left:50%;bottom:102px;transform:translate(-50%,10px);background:#152e3b;color:#fff;border-radius:13px;padding:11px 16px;font-size:12px;opacity:0;pointer-events:none;transition:.2s;z-index:60;white-space:nowrap;max-width:90vw}.toast.show{opacity:1;transform:translate(-50%,0)}.success{padding:25px 12px;text-align:center}.success .tick{margin:auto;width:70px;height:70px;background:#dff5eb;border-radius:25px;display:grid;place-items:center;font-size:34px}.success h2{margin:15px 0 7px}.success p{font-size:13px;color:var(--muted);line-height:1.6}.footnote{text-align:center;font-size:10px;color:#9aa7ad;margin:22px 0 8px}
@keyframes rise{from{transform:translateY(30px);opacity:.6}to{transform:translateY(0);opacity:1}}
@media(min-width:620px){.hero{padding:31px 32px;min-height:210px}.hero h1{font-size:34px;max-width:400px}.hero p{max-width:390px}.grid{grid-template-columns:repeat(3,minmax(0,1fr));gap:15px}.photo{height:180px}.app{padding:0 22px}.scrim{align-items:center;padding:18px}.sheet{border-radius:25px;max-height:88vh}.product{padding:10px}.pname{font-size:14px}}
</style></head><body>
<div class="app">
<header class="top"><div class="brand"><div class="logo">◈</div><div><b>AQUA HOME</b><small>HAMMOM UCHUN YANGI NAFAS</small></div></div><button class="iconbtn" onclick="openCart()" aria-label="Savat">🛍️<span class="badgecount" id="topCount" style="display:none">0</span></button></header>
<section class="hero"><div class="eyebrow">Qulaylik har kuni</div><h1>Hammomingizga yangi ko'rinish bering.</h1><p>Kranlar, dush tizimlari va zamonaviy hammom jihozlari — bir joyda.</p><span class="pill">✦ Sifatli tanlov · Qulay buyurtma</span></section>
<div class="searchbox"><span>⌕</span><input id="search" placeholder="Mahsulot qidirish..." autocomplete="off"><span style="font-size:13px">↵</span></div>
<div class="sectionhead"><h2>Kategoriyalar</h2><span class="subtle" id="catCount"></span></div><div class="categories" id="categories"></div>
<div class="tools"><strong id="catalogTitle">Tanlangan mahsulotlar</strong><select id="sort" aria-label="Saralash"><option value="popular">Mashhurlar avval</option><option value="price_asc">Arzonidan boshlab</option><option value="price_desc">Qimmatidan boshlab</option><option value="name">Nomi bo'yicha</option></select></div>
<section class="grid" id="products"><div class="empty"><div class="emoji">🚿</div><b>Katalog yuklanmoqda</b><p>Bir oz kuting...</p></div></section>
<div class="footnote">AQUA HOME · Buyurtma telefon orqali tasdiqlanadi</div>
</div>
<nav class="bottomnav"><div class="navinner"><button class="navitem active" id="navHome" onclick="showHome()"><span>⌂</span>Bosh sahifa</button><button class="navitem" id="navFav" onclick="showFavorites()"><span>♡</span>Sevimlilar</button><button class="navitem" id="navCart" onclick="openCart()"><span>🛍</span>Savat<i class="navcount" id="navCount" style="display:none">0</i></button></div></nav>
<div class="scrim" id="cartLayer" onclick="outsideClose(event,'cartLayer')"><div class="sheet"><div class="sheethead"><h2>🛍 Savatingiz</h2><button class="close" onclick="closeLayer('cartLayer')">×</button></div><div id="cartItems"></div><div class="totalrow"><span>Jami summa</span><b id="cartTotal">0 so'm</b></div><button class="primary" id="checkoutBtn" onclick="openCheckout()">Buyurtma berish →</button><p class="formnote">To'lov olinmaydi — operator buyurtmangizni telefon orqali tasdiqlaydi.</p></div></div>
<div class="scrim" id="detailLayer" onclick="outsideClose(event,'detailLayer')"><div class="sheet"><div class="sheethead"><h2>Mahsulot haqida</h2><button class="close" onclick="closeLayer('detailLayer')">×</button></div><div id="detailContent"></div></div></div>
<div class="scrim" id="checkoutLayer" onclick="outsideClose(event,'checkoutLayer')"><div class="sheet"><div class="sheethead"><h2>📦 Buyurtmani rasmiylashtirish</h2><button class="close" onclick="closeLayer('checkoutLayer')">×</button></div><div id="checkoutForm"><label class="formlabel" for="customerName">Ism-familiya *</label><input class="field" id="customerName" placeholder="Masalan, Ali Valiyev" maxlength="100"><label class="formlabel" for="customerPhone">Telefon raqam *</label><input class="field" id="customerPhone" type="tel" placeholder="+998 90 123 45 67" maxlength="24"><label class="formlabel" for="customerAddress">Yetkazib berish manzili *</label><input class="field" id="customerAddress" placeholder="Tuman, ko'cha, uy" maxlength="300"><label class="formlabel" for="customerComment">Izoh (ixtiyoriy)</label><textarea class="field" id="customerComment" rows="3" placeholder="Mo'ljal yoki qo'shimcha ma'lumot" maxlength="1000"></textarea><p class="formnote">🔒 Buyurtma Telegram orqali xavfsiz yuboriladi. Bu bosqichda karta yoki to'lov ma'lumotlari so'ralmaydi.</p><button class="primary" onclick="submitOrder()">Buyurtmani yuborish ✓</button></div><div id="orderSuccess" class="success" style="display:none"><div class="tick">✓</div><h2>Buyurtma yuborildi!</h2><p id="successText"></p><button class="primary" onclick="finishOrder()">Katalogga qaytish</button></div></div></div>
<div class="toast" id="toast"></div>
<script>
const tg = window.Telegram?.WebApp;
if(tg){tg.ready();tg.expand();try{tg.setHeaderColor('#f5f7fb');tg.setBackgroundColor('#f5f7fb')}catch(e){}}
let products=[],activeCategory='Barchasi',favorites=new Set(),cart={},favoritesMode=false;
const fmt=n=>new Intl.NumberFormat('uz-UZ').format(Number(n)||0)+' so\'m';
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function toast(msg){const el=document.getElementById('toast');el.textContent=msg;el.classList.add('show');clearTimeout(window._toastTimer);window._toastTimer=setTimeout(()=>el.classList.remove('show'),2300)}
async function loadProducts(){try{const r=await fetch('/api/products');if(!r.ok)throw Error('API');const data=await r.json();products=data.products||[];renderCategories(data.categories||[]);renderProducts()}catch(e){document.getElementById('products').innerHTML='<div class="empty"><div class="emoji">📡</div><b>Ulanishda muammo</b><p>Sahifani yangilab ko‘ring.</p></div>'}}
function renderCategories(cats){const el=document.getElementById('categories');const all=['Barchasi',...cats];el.innerHTML=all.map(c=>`<button class="cat ${c===activeCategory?'active':''}" onclick="setCategory(${JSON.stringify(c).replace(/"/g,'&quot;')})">${esc(c)}</button>`).join('');document.getElementById('catCount').textContent=cats.length+' tur'}
function setCategory(c){activeCategory=c;favoritesMode=false;document.getElementById('catalogTitle').textContent='Tanlangan mahsulotlar';renderCategories(products.map(p=>p.category).filter((v,i,a)=>a.indexOf(v)===i));renderProducts();setNav('home')}
function filteredProducts(){const q=document.getElementById('search').value.toLowerCase().trim();let list=products.filter(p=>(activeCategory==='Barchasi'||p.category===activeCategory)&&(!q||(p.name+' '+p.category+' '+p.description).toLowerCase().includes(q))&&(!favoritesMode||favorites.has(p.id)));const sort=document.getElementById('sort').value;if(sort==='price_asc')list.sort((a,b)=>a.price-b.price);else if(sort==='price_desc')list.sort((a,b)=>b.price-a.price);else if(sort==='name')list.sort((a,b)=>a.name.localeCompare(b.name));else list.sort((a,b)=>((b.badge==='TOP'||b.badge==='HIT')?1:0)-((a.badge==='TOP'||a.badge==='HIT')?1:0));return list}
function renderProducts(){const list=filteredProducts();const el=document.getElementById('products');if(!list.length){el.innerHTML=`<div class="empty"><div class="emoji">${favoritesMode?'♡':'🔎'}</div><b>${favoritesMode?'Sevimlilar hozircha bo‘sh':'Mahsulot topilmadi'}</b><p>${favoritesMode?'Yoqtirgan mahsulotingizdagi yurakchani bosing.':'Boshqa so‘z bilan qidirib ko‘ring.'}</p></div>`;return}el.innerHTML=list.map(p=>`<article class="product"><div class="photo" onclick="openDetail(${p.id})"><img src="${esc(p.image_url)}" alt="${esc(p.name)}" loading="lazy" onerror="this.src='https://images.unsplash.com/photo-1584622650111-993a426fbf0a?auto=format&fit=crop&w=800&q=80'"><span class="tag" style="${p.badge?'':'display:none'}">${esc(p.badge)}</span><button class="heart ${favorites.has(p.id)?'on':''}" onclick="event.stopPropagation();toggleFav(${p.id})">${favorites.has(p.id)?'♥':'♡'}</button></div><div class="pname" onclick="openDetail(${p.id})">${esc(p.name)}</div><div class="pcat">${esc(p.category)}</div><div class="pricebar"><span class="price">${fmt(p.price)}</span><button class="add" onclick="addCart(${p.id})" aria-label="Savatga qo‘shish">+</button></div></article>`).join('')}
function setNav(nav){['Home','Fav','Cart'].forEach(x=>document.getElementById('nav'+x).classList.toggle('active',x.toLowerCase()===nav))}
function showHome(){favoritesMode=false;activeCategory='Barchasi';document.getElementById('search').value='';document.getElementById('catalogTitle').textContent='Tanlangan mahsulotlar';renderCategories(products.map(p=>p.category).filter((v,i,a)=>a.indexOf(v)===i));renderProducts();setNav('home')}
function showFavorites(){favoritesMode=true;activeCategory='Barchasi';document.getElementById('catalogTitle').textContent='Sevimlilar';renderCategories(products.map(p=>p.category).filter((v,i,a)=>a.indexOf(v)===i));renderProducts();setNav('fav')}
function toggleFav(id){if(favorites.has(id))favorites.delete(id);else favorites.add(id);renderProducts();if(favoritesMode)renderProducts()}
function addCart(id){cart[id]=(cart[id]||0)+1;updateCartCount();toast('Savatga qo‘shildi ✓');if(tg?.HapticFeedback)tg.HapticFeedback.impactOccurred('light')}
function updateCartCount(){const n=Object.values(cart).reduce((a,b)=>a+b,0);for(const id of ['topCount','navCount']){const el=document.getElementById(id);el.textContent=n;el.style.display=n?'grid':'none'}}
function cartTotal(){return Object.entries(cart).reduce((sum,[id,qty])=>{const p=products.find(x=>x.id===Number(id));return sum+(p?p.price*qty:0)},0)}
function openCart(){setNav('cart');renderCart();document.getElementById('cartLayer').classList.add('show')}
function renderCart(){const entries=Object.entries(cart).filter(([id,q])=>q>0&&products.some(p=>p.id===Number(id)));const el=document.getElementById('cartItems');if(!entries.length)el.innerHTML='<div class="empty"><div class="emoji">🛍️</div><b>Savatingiz hozircha bo‘sh</b><p>Katalogdan kerakli jihozlarni qo‘shing.</p><button class="secondary" style="margin-top:14px" onclick="closeLayer(\'cartLayer\')">Katalogga qaytish</button></div>';else el.innerHTML=entries.map(([id,q])=>{const p=products.find(x=>x.id===Number(id));return `<div class="cartrow"><img src="${esc(p.image_url)}" alt=""><div><b>${esc(p.name)}</b><small>${fmt(p.price)}</small><div class="qty"><button onclick="changeQty(${p.id},-1)">−</button><span>${q}</span><button onclick="changeQty(${p.id},1)">+</button><button class="remove" onclick="removeCart(${p.id})">O‘chirish</button></div></div><b style="font-size:11px;white-space:nowrap">${fmt(p.price*q)}</b></div>`}).join('');document.getElementById('cartTotal').textContent=fmt(cartTotal());document.getElementById('checkoutBtn').style.display=entries.length?'block':'none'}
function changeQty(id,d){cart[id]=(cart[id]||0)+d;if(cart[id]<=0)delete cart[id];updateCartCount();renderCart()}
function removeCart(id){delete cart[id];updateCartCount();renderCart()}
function openDetail(id){const p=products.find(x=>x.id===id);if(!p)return;document.getElementById('detailContent').innerHTML=`<img class="detailimg" src="${esc(p.image_url)}" alt="${esc(p.name)}"><div class="pcat" style="margin-top:15px">${esc(p.category)}${p.badge?' · '+esc(p.badge):''}</div><h2 style="margin:5px 0 0;font-size:22px">${esc(p.name)}</h2><div class="detailprice">${fmt(p.price)}</div><p class="detaildesc">${esc(p.description)}</p><button class="primary" onclick="addCart(${p.id});closeLayer('detailLayer')">Savatga qo‘shish +</button>`;document.getElementById('detailLayer').classList.add('show')}
function openCheckout(){if(!Object.keys(cart).length){toast('Avval savatga mahsulot qo‘shing');return}closeLayer('cartLayer');document.getElementById('checkoutForm').style.display='block';document.getElementById('orderSuccess').style.display='none';const u=tg?.initDataUnsafe?.user;if(u&&!document.getElementById('customerName').value)document.getElementById('customerName').value=[u.first_name,u.last_name].filter(Boolean).join(' ');document.getElementById('checkoutLayer').classList.add('show')}
async function submitOrder(){const name=document.getElementById('customerName').value.trim(),phone=document.getElementById('customerPhone').value.trim(),address=document.getElementById('customerAddress').value.trim(),comment=document.getElementById('customerComment').value.trim();if(name.length<2||phone.replace(/\D/g,'').length<9||address.length<4){toast('Ism, telefon va manzilni to‘ldiring');return}if(!tg?.initData){toast('Buyurtma uchun Telegram ichidan oching');return}const btn=document.querySelector('#checkoutForm .primary');btn.disabled=true;btn.textContent='Yuborilmoqda...';try{const r=await fetch('/api/order',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({init_data:tg.initData,customer_name:name,phone,address,comment,items:Object.entries(cart).map(([product_id,quantity])=>({product_id:Number(product_id),quantity}))})});const data=await r.json();if(!r.ok||!data.ok)throw Error(data.error||'Xatolik');document.getElementById('checkoutForm').style.display='none';document.getElementById('orderSuccess').style.display='block';document.getElementById('successText').innerHTML=`Buyurtma raqami: <b>#${data.order_id}</b><br>Jami: <b>${fmt(data.total)}</b><br><br>Operatorimiz tez orada siz bilan bog‘lanadi.`;cart={};updateCartCount();if(tg?.HapticFeedback)tg.HapticFeedback.notificationOccurred('success')}catch(e){toast(e.message||'Buyurtma yuborilmadi')}finally{btn.disabled=false;btn.textContent='Buyurtmani yuborish ✓'}}
function finishOrder(){closeLayer('checkoutLayer');showHome();toast('Rahmat! Buyurtmangiz qabul qilindi.')}
function closeLayer(id){document.getElementById(id).classList.remove('show')}
function outsideClose(e,id){if(e.target.id===id)closeLayer(id)}
document.getElementById('search').addEventListener('input',()=>{favoritesMode=false;renderProducts()});document.getElementById('sort').addEventListener('change',renderProducts);
loadProducts();updateCartCount();
</script></body></html>'''

# --- Telegram bot buyruqlari ---
ADD_NAME, ADD_CATEGORY, ADD_PRICE, ADD_DESCRIPTION, ADD_IMAGE = range(5)


def is_admin(user_id: int | None) -> bool:
    return user_id in ADMIN_IDS if user_id is not None else False


def catalog_keyboard():
    if WEBAPP_URL:
        return InlineKeyboardMarkup([[InlineKeyboardButton("🛍 Katalogni ochish", web_app=WebAppInfo(url=WEBAPP_URL))]])
    return InlineKeyboardMarkup([[InlineKeyboardButton("🌐 Sayt manzili sozlanmagan", callback_data="show_setup")]])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    name = update.effective_user.first_name if update.effective_user else ""
    greeting = f"Salom, {html.escape(name)}! 👋\n\n" if name else "Assalomu alaykum! 👋\n\n"
    message = (
        greeting + f"<b>{html.escape(APP_NAME)}</b> do'koniga xush kelibsiz!\n\n"
        "🚿 Kranlar va dush tizimlari\n🛁 Rakvina, unitaz va hammom mebellari\n"
        "📦 Savat, onlayn buyurtma va buyurtma holatini kuzatish\n\n"
        "Mahsulotlarni ko'rish uchun katalogni oching. To'lov bot ichida olinmaydi."
    )
    await update.effective_message.reply_text(
        message, parse_mode="HTML", reply_markup=catalog_keyboard(),
        disable_web_page_preview=True,
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lines = ["<b>AQUA HOME — yordam</b>", "/start — bosh menyu", "/catalog — katalogni ochish", "/myorders — buyurtmalarim"]
    if is_admin(update.effective_user.id if update.effective_user else None):
        lines += ["", "<b>Admin buyruqlari</b>", "/admin — admin panel", "/orders — so'nggi buyurtmalar", "/addproduct — mahsulot qo'shish", "/cancel — amaldagi amalni bekor qilish"]
    await update.effective_message.reply_text("\n".join(lines), parse_mode="HTML", reply_markup=catalog_keyboard())


async def catalog_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text("Katalogni ochish uchun quyidagi tugmani bosing:", reply_markup=catalog_keyboard())


async def webapp_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query:
        await query.answer()
        if query.data == "show_setup":
            await query.message.reply_text("Mini App URL hali sozlanmagan. Render'ga joylagach WEBAPP_URL avtomatik aniqlanadi; lokal ishga tushirishda esa HTTPS tunnel manzili kerak.")


async def my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return
    with db_connect() as db:
        rows = db.execute("SELECT id, total, status, created_at FROM orders WHERE telegram_id=? ORDER BY id DESC LIMIT 10", (user.id,)).fetchall()
    if not rows:
        await update.effective_message.reply_text("Sizda hali buyurtma yo'q. Katalogdan mahsulot tanlashingiz mumkin.", reply_markup=catalog_keyboard())
        return
    lines = ["<b>📦 Buyurtmalaringiz</b>"]
    for row in rows:
        status = STATUSES.get(row["status"], row["status"])
        lines.append(f"\n<b>#{row['id']}</b> · {money(row['total'])}\n{html.escape(status)} · {html.escape(row['created_at'])}")
    await update.effective_message.reply_text("\n".join(lines), parse_mode="HTML", reply_markup=catalog_keyboard())


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id if update.effective_user else None):
        await update.effective_message.reply_text("Bu bo'lim faqat admin uchun.")
        return
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 Buyurtmalar", callback_data="admin_orders")],
        [InlineKeyboardButton("➕ Mahsulot qo'shish", callback_data="admin_add")],
        [InlineKeyboardButton("📊 Statistika", callback_data="admin_stats")],
    ])
    await update.effective_message.reply_text("<b>🛠 AQUA HOME — admin panel</b>", parse_mode="HTML", reply_markup=keyboard)


async def show_orders(update: Update, context: ContextTypes.DEFAULT_TYPE, edit: bool = False) -> None:
    user = update.effective_user
    if not is_admin(user.id if user else None):
        if update.callback_query:
            await update.callback_query.answer("Ruxsat yo'q", show_alert=True)
        return
    with db_connect() as db:
        rows = db.execute("SELECT id, customer_name, phone, total, status, created_at FROM orders ORDER BY id DESC LIMIT 8").fetchall()
    if not rows:
        text = "Hozircha buyurtmalar yo'q."
        if update.callback_query:
            await update.callback_query.edit_message_text(text)
        else:
            await update.effective_message.reply_text(text)
        return
    for row in rows:
        with db_connect() as db:
            items = db.execute("SELECT product_name, quantity FROM order_items WHERE order_id=?", (row["id"],)).fetchall()
        text = (
            f"<b>Buyurtma #{row['id']}</b> · {html.escape(STATUSES.get(row['status'], row['status']))}\n"
            f"👤 {html.escape(row['customer_name'])}\n📞 {html.escape(row['phone'])}\n"
            f"🧾 " + ", ".join(f"{html.escape(i['product_name'])} × {i['quantity']}" for i in items) +
            f"\n💰 <b>{money(row['total'])}</b>\n🕒 {html.escape(row['created_at'])}"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Qabul", callback_data=f"status:{row['id']}:accepted"), InlineKeyboardButton("🚚 Yetkazilmoqda", callback_data=f"status:{row['id']}:delivery")],
            [InlineKeyboardButton("🏁 Yakunlash", callback_data=f"status:{row['id']}:done"), InlineKeyboardButton("❌ Bekor", callback_data=f"status:{row['id']}:cancelled")],
        ])
        if update.callback_query:
            await update.callback_query.message.reply_text(text, parse_mode="HTML", reply_markup=kb)
        else:
            await update.effective_message.reply_text(text, parse_mode="HTML", reply_markup=kb)
    if update.callback_query:
        await update.callback_query.answer("Buyurtmalar yuborildi")


async def admin_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    uid = query.from_user.id
    if query.data.startswith("status:"):
        if not is_admin(uid):
            await query.answer("Ruxsat yo'q", show_alert=True)
            return
        try:
            _, raw_id, status = query.data.split(":", 2)
            order_id = int(raw_id)
            if status not in STATUSES:
                raise ValueError
        except ValueError:
            await query.answer("Noto'g'ri so'rov", show_alert=True)
            return
        with db_connect() as db:
            db.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))
            db.commit()
            row = db.execute("SELECT telegram_id FROM orders WHERE id=?", (order_id,)).fetchone()
        await query.answer("Holat yangilandi")
        await query.message.reply_text(f"Buyurtma #{order_id} holati: {STATUSES[status]}")
        if row:
            telegram_api("sendMessage", {"chat_id": row["telegram_id"], "text": f"📦 <b>#{order_id}</b> buyurtmangiz holati yangilandi: {html.escape(STATUSES[status])}", "parse_mode": "HTML"})
        return
    if not is_admin(uid) and query.data.startswith("admin_"):
        await query.answer("Faqat admin uchun", show_alert=True)
        return
    if query.data == "admin_orders":
        await show_orders(update, context, edit=True)
    elif query.data == "admin_add":
        await query.answer()
        await query.message.reply_text("Mahsulot qo'shish uchun /addproduct buyrug'ini yuboring.")
    elif query.data == "admin_stats":
        with db_connect() as db:
            total_products = db.execute("SELECT COUNT(*) FROM products WHERE active=1").fetchone()[0]
            total_orders = db.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
            pending = db.execute("SELECT COUNT(*) FROM orders WHERE status='new'").fetchone()[0]
            turnover = db.execute("SELECT COALESCE(SUM(total),0) FROM orders WHERE status='done'").fetchone()[0]
        await query.answer()
        await query.message.reply_text(f"📊 <b>Statistika</b>\nMahsulotlar: {total_products}\nBuyurtmalar: {total_orders}\nYangi buyurtmalar: {pending}\nYakunlangan buyurtmalar summasi: {money(turnover)}", parse_mode="HTML")


async def orders_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id if update.effective_user else None):
        await update.effective_message.reply_text("Bu buyruq faqat admin uchun.")
        return
    await show_orders(update, context)


async def add_product_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update.effective_user.id if update.effective_user else None):
        await update.effective_message.reply_text("Bu buyruq faqat admin uchun.")
        return ConversationHandler.END
    context.user_data["new_product"] = {}
    await update.effective_message.reply_text("Yangi mahsulot nomini yuboring. Bekor qilish uchun /cancel")
    return ADD_NAME


async def add_product_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = update.effective_message.text.strip()
    if not 2 <= len(name) <= 120:
        await update.effective_message.reply_text("Nom 2–120 belgi bo'lsin. Qayta kiriting:")
        return ADD_NAME
    context.user_data["new_product"]["name"] = name
    await update.effective_message.reply_text("Kategoriya nomini yuboring (masalan: Kranlar, Rakvinalar, Unitazlar):")
    return ADD_CATEGORY


async def add_product_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    category = update.effective_message.text.strip()
    if not 2 <= len(category) <= 60:
        await update.effective_message.reply_text("Kategoriya 2–60 belgi bo'lsin. Qayta kiriting:")
        return ADD_CATEGORY
    context.user_data["new_product"]["category"] = category
    await update.effective_message.reply_text("Narxini faqat raqam bilan yuboring (so'mda), masalan: 390000")
    return ADD_PRICE


async def add_product_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.effective_message.text.strip().replace(" ", "").replace(",", "")
    if not raw.isdigit() or not 0 < int(raw) <= 2_000_000_000:
        await update.effective_message.reply_text("Narx musbat son bo'lishi kerak. Masalan: 390000")
        return ADD_PRICE
    context.user_data["new_product"]["price"] = int(raw)
    await update.effective_message.reply_text("Mahsulot tavsifini yuboring:")
    return ADD_DESCRIPTION


async def add_product_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    desc = update.effective_message.text.strip()
    if len(desc) > 1000:
        await update.effective_message.reply_text("Tavsif 1000 belgidan oshmasin. Qisqartirib qayta yuboring:")
        return ADD_DESCRIPTION
    context.user_data["new_product"]["description"] = desc
    await update.effective_message.reply_text("Rasm URL manzilini yuboring yoki rasm bo'lmasa — skip deb yozing:")
    return ADD_IMAGE


async def add_product_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    image = update.effective_message.text.strip()
    if image.lower() == "skip":
        image = "https://images.unsplash.com/photo-1584622650111-993a426fbf0a?auto=format&fit=crop&w=900&q=80"
    elif not (image.startswith("https://") and len(image) <= 1000):
        await update.effective_message.reply_text("Rasm manzili https:// bilan boshlansin yoki skip deb yozing:")
        return ADD_IMAGE
    data = context.user_data.pop("new_product", {})
    try:
        with db_connect() as db:
            db.execute(
                "INSERT INTO products(name, category, price, description, image_url, badge) VALUES (?, ?, ?, ?, ?, ?)",
                (data["name"], data["category"], data["price"], data["description"], image, "YANGI"),
            )
            db.commit()
        await update.effective_message.reply_text(f"✅ Mahsulot katalogga qo'shildi!\n\n<b>{html.escape(data['name'])}</b>\nKategoriya: {html.escape(data['category'])}\nNarx: {money(data['price'])}\n\nMini App'da katalogni yangilash kifoya.", parse_mode="HTML", reply_markup=catalog_keyboard())
    except Exception:
        log.exception("Product add failed")
        await update.effective_message.reply_text("Mahsulot qo'shishda xatolik yuz berdi. Qayta urinib ko'ring.")
    return ConversationHandler.END


async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("new_product", None)
    await update.effective_message.reply_text("Amal bekor qilindi.")
    return ConversationHandler.END


async def post_init(application: Application) -> None:
    await application.bot.set_my_commands([
        BotCommand("start", "Bosh menyu"), BotCommand("catalog", "Katalogni ochish"),
        BotCommand("myorders", "Buyurtmalarim"), BotCommand("help", "Yordam"),
    ])
    if WEBAPP_URL:
        try:
            await application.bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="🛍 Katalog", web_app=WebAppInfo(url=WEBAPP_URL)))
            log.info("Mini App menu URL: %s", WEBAPP_URL)
        except Exception as exc:
            log.warning("Mini App menu button sozlanmadi: %s", exc)
    else:
        log.warning("WEBAPP_URL yo'q. Telegram Mini App tugmasi HTTPS URL kiritilgach ishlaydi.")


def run_web_server() -> None:
    log.info("Web server 0.0.0.0:%s portda ishga tushmoqda", HOST_PORT)
    serve(web, host="0.0.0.0", port=HOST_PORT, threads=8)


def build_application() -> Application:
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("catalog", catalog_command))
    app.add_handler(CommandHandler("myorders", my_orders))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("orders", orders_command))
    app.add_handler(CallbackQueryHandler(webapp_callback, pattern="^show_setup$"))
    app.add_handler(CallbackQueryHandler(admin_callbacks, pattern="^(admin_|status:)"))
    product_conversation = ConversationHandler(
        entry_points=[CommandHandler("addproduct", add_product_start)],
        states={
            ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_product_name)],
            ADD_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_product_category)],
            ADD_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_product_price)],
            ADD_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_product_description)],
            ADD_IMAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_product_image)],
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
        allow_reentry=True,
    )
    app.add_handler(product_conversation)
    app.add_handler(CommandHandler("cancel", cancel_conversation))
    return app


def run_webhook_bot(application: Application) -> None:
    """Render uchun webhook: Telegram update kelganda web service'ni ishga uyg'otadi."""
    global BOT_LOOP
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    BOT_LOOP = loop
    try:
        loop.run_until_complete(application.initialize())
        if application.post_init:
            loop.run_until_complete(application.post_init(application))
        loop.run_until_complete(application.start())
        webhook_url = f"{WEBAPP_URL}/telegram-webhook/{WEBHOOK_PATH_SECRET}"
        loop.run_until_complete(application.bot.set_webhook(
            url=webhook_url,
            secret_token=WEBHOOK_PATH_SECRET,
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=False,
        ))
        log.info("Telegram webhook faol: %s/telegram-webhook/[maxfiy yo'l]", WEBAPP_URL)
        loop.run_forever()
    except Exception:
        log.exception("Webhook bot loop xatolik bilan to'xtadi")
    finally:
        try:
            if application.running:
                loop.run_until_complete(application.stop())
            loop.run_until_complete(application.shutdown())
        except Exception:
            log.exception("Bot yopilishida xatolik")
        loop.close()


def main() -> None:
    global BOT_APPLICATION
    if not BOT_TOKEN or BOT_TOKEN == "PASTE_BOTFATHER_TOKEN_HERE":
        raise SystemExit("BOT_TOKEN topilmadi. .env faylida BotFather tokenini kiriting.")
    init_db()
    application = build_application()
    render_mode = bool(os.getenv("RENDER_EXTERNAL_HOSTNAME") or os.getenv("RENDER"))
    requested_mode = os.getenv("BOT_MODE", "").strip().lower()
    use_webhook = requested_mode == "webhook" or (render_mode and requested_mode != "polling")

    if use_webhook:
        if not WEBAPP_URL:
            raise SystemExit("Webhook/Mini App uchun HTTPS WEBAPP_URL kerak. Render'da u avtomatik aniqlanishi kerak.")
        BOT_APPLICATION = application
        threading.Thread(target=run_webhook_bot, args=(application,), name="telegram-webhook-bot", daemon=True).start()
        # Main thread web serverni ushlab turadi; Telegram update'lari shu serverga keladi.
        run_web_server()
    else:
        # Lokal kompyuterda oson sozlash uchun polling; web sahifa esa alohida thread'da ishlaydi.
        threading.Thread(target=run_web_server, name="miniapp-web", daemon=True).start()
        log.info("%s bot polling rejimida ishga tushmoqda...", APP_NAME)
        application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
