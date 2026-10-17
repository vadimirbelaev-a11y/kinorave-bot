# =====================================================================
# PULSEFETCH BOT — PART 1 OF 4: CONFIG, WEB SERVER, DATABASE
# =====================================================================
import os
import re
import glob
import html
import uuid
import time
import shutil
import asyncio
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import yt_dlp
import aiohttp
from aiohttp import web
from aiogram import Bot, Dispatcher, F, types
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramRetryAfter, TelegramBadRequest
from aiogram.filters import Command, CommandStart, ChatMemberUpdatedFilter, IS_MEMBER, IS_NOT_MEMBER
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    FSInputFile, ChatMemberUpdated
)
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

ADMIN_ID = 6444735646
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise RuntimeError("Переменная окружения BOT_TOKEN не задана!")
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "").strip()

# Удерживаем ссылки на фоновые задачи (иначе их может собрать GC)
BACKGROUND_TASKS = set()

def spawn(coro):
    task = asyncio.create_task(coro)
    BACKGROUND_TASKS.add(task)
    task.add_done_callback(BACKGROUND_TASKS.discard)
    return task

def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)

# --- 1. ВЕБ-СЕРВЕР И АВТОПИНГ 24/7 (АВТОПИНГ КАЖДЫЕ 60 СЕКУНД) ---
async def handle_ping(request):
    return web.Response(text="PulseFetch Bot is active 24/7 online!")

async def self_ping_loop():
    await asyncio.sleep(5)
    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        while True:
            started = time.monotonic()
            if RENDER_EXTERNAL_URL:
                try:
                    async with session.get(RENDER_EXTERNAL_URL) as resp:
                        logging.info(f"Self-ping 60s status: {resp.status}")
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logging.error(f"Self-ping error: {e}")
            # ровно 60 секунд между стартами запросов
            await asyncio.sleep(max(1.0, 60 - (time.monotonic() - started)))

async def start_web_server():
    port = int(os.getenv("PORT", 8080))
    app = web.Application()
    app.router.add_get("/", handle_ping)
    app.router.add_get("/health", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    spawn(self_ping_loop())
    return runner

# --- 2. БАЗА ДАННЫХ И АВТО-VIP ДЛЯ ADMIN_ID (6444735646) ---
# Для Render укажи DB_PATH на persistent disk (например /data/bot_database.db),
# иначе база обнуляется при каждом деплое.
DB_NAME = os.getenv("DB_PATH", "bot_database.db")

# Явный порядок колонок => индексы user[3], user[5], user[6], user[9], user[10] всегда валидны
USER_COLUMNS = ("user_id, username, language, is_vip, vip_until, download_count, "
                "referrals_count, bonus_received, referred_by, stars_balance, joined_date")

MIGRATIONS = {
    "username": "TEXT",
    "language": "TEXT DEFAULT 'ru'",
    "is_vip": "INTEGER DEFAULT 0",
    "vip_until": "TEXT DEFAULT NULL",
    "download_count": "INTEGER DEFAULT 0",
    "referrals_count": "INTEGER DEFAULT 0",
    "bonus_received": "INTEGER DEFAULT 0",
    "referred_by": "INTEGER DEFAULT NULL",
    "stars_balance": "INTEGER DEFAULT 0",
    "joined_date": "TIMESTAMP",
}

@contextmanager
def db():
    conn = sqlite3.connect(DB_NAME, timeout=15)
    try:
        cur = conn.cursor()
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    folder = os.path.dirname(DB_NAME)
    if folder:
        os.makedirs(folder, exist_ok=True)
    try:
        c = sqlite3.connect(DB_NAME, timeout=15)
        c.execute("PRAGMA journal_mode=WAL")
        c.close()
    except Exception as e:
        logging.warning(f"WAL not enabled: {e}")

    with db() as cur:
        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                language TEXT DEFAULT 'ru',
                is_vip INTEGER DEFAULT 0,
                vip_until TEXT DEFAULT NULL,
                download_count INTEGER DEFAULT 0,
                referrals_count INTEGER DEFAULT 0,
                bonus_received INTEGER DEFAULT 0,
                referred_by INTEGER DEFAULT NULL,
                stars_balance INTEGER DEFAULT 0,
                joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Миграция старых баз: добавляем недостающие колонки
        cur.execute("PRAGMA table_info(users)")
        existing = {row[1] for row in cur.fetchall()}
        for col, ddl in MIGRATIONS.items():
            if col not in existing:
                cur.execute(f"ALTER TABLE users ADD COLUMN {col} {ddl}")
        cur.execute("UPDATE users SET joined_date = datetime('now') WHERE joined_date IS NULL")
        cur.execute("UPDATE users SET language = 'ru' WHERE language IS NULL OR language NOT IN ('ru','ua','en')")
        for col in ("download_count", "referrals_count", "bonus_received", "stars_balance", "is_vip"):
            cur.execute(f"UPDATE users SET {col} = 0 WHERE {col} IS NULL")
        # Принудительно гарантируем VIP статус для ADMIN_ID
        cur.execute("INSERT OR IGNORE INTO users (user_id, language, is_vip) VALUES (?, 'ru', 1)", (ADMIN_ID,))
        cur.execute("UPDATE users SET is_vip = 1 WHERE user_id = ?", (ADMIN_ID,))

def get_user(user_id):
    with db() as cur:
        cur.execute(f"SELECT {USER_COLUMNS} FROM users WHERE user_id = ?", (user_id,))
        return cur.fetchone()

def _vip_until_str(hours, current=None):
    base = utcnow()
    if current:
        try:
            cur_dt = datetime.fromisoformat(current)
            if cur_dt > base:
                base = cur_dt
        except ValueError:
            pass
    return (base + timedelta(hours=hours)).isoformat(sep=" ", timespec="seconds")

def add_user(user_id, username=None, referred_by=None):
    """Возвращает (is_new, referrer_id, bonus_granted_to_referrer)."""
    is_admin = user_id == ADMIN_ID
    bonus_granted = False
    with db() as cur:
        cur.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        exists = cur.fetchone()

        if not exists:
            if referred_by == user_id:
                referred_by = None
            if referred_by:
                cur.execute("SELECT 1 FROM users WHERE user_id = ?", (referred_by,))
                if not cur.fetchone():
                    referred_by = None
            cur.execute(
                "INSERT INTO users (user_id, username, language, is_vip, referred_by) VALUES (?, ?, 'ru', ?, ?)",
                (user_id, username, 1 if is_admin else 0, referred_by)
            )
            if referred_by:
                cur.execute("UPDATE users SET referrals_count = referrals_count + 1 WHERE user_id = ?", (referred_by,))
                cur.execute("SELECT referrals_count, bonus_received, vip_until FROM users WHERE user_id = ?", (referred_by,))
                refs, bonuses, vip_until = cur.fetchone()
                # каждые 3 друга = VIP на 24 часа (максимум 3 цикла)
                if refs % 3 == 0 and (bonuses or 0) < 3:
                    cur.execute(
                        "UPDATE users SET bonus_received = bonus_received + 1, vip_until = ? WHERE user_id = ?",
                        (_vip_until_str(24, vip_until), referred_by)
                    )
                    bonus_granted = True
            return True, referred_by, bonus_granted

        if username is not None:
            cur.execute("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))
        if is_admin:
            cur.execute("UPDATE users SET is_vip = 1 WHERE user_id = ?", (ADMIN_ID,))
        return False, None, False

def is_user_vip(user_id) -> bool:
    if user_id == ADMIN_ID:
        return True
    user = get_user(user_id)
    if not user:
        return False
    if user[3] == 1:
        return True
    if user[4]:
        try:
            return datetime.fromisoformat(user[4]) > utcnow()
        except ValueError:
            return False
    return False

def set_user_language(user_id, lang):
    with db() as cur:
        cur.execute("UPDATE users SET language = ? WHERE user_id = ?", (lang, user_id))

def increment_downloads(user_id):
    with db() as cur:
        cur.execute("UPDATE users SET download_count = download_count + 1 WHERE user_id = ?", (user_id,))

def set_user_vip(user_id, status: int):
    if user_id == ADMIN_ID:
        status = 1  # админ всегда VIP
    with db() as cur:
        if status:
            cur.execute("UPDATE users SET is_vip = 1 WHERE user_id = ?", (user_id,))
        else:
            cur.execute("UPDATE users SET is_vip = 0, vip_until = NULL WHERE user_id = ?", (user_id,))

def get_all_users_count():
    with db() as cur:
        cur.execute("SELECT COUNT(*) FROM users")
        return cur.fetchone()[0]

def get_total_downloads_sum():
    with db() as cur:
        cur.execute("SELECT SUM(download_count) FROM users")
        res = cur.fetchone()[0]
        return res if res else 0

def get_vip_users_count():
    now = utcnow().isoformat(sep=" ", timespec="seconds")
    with db() as cur:
        cur.execute("SELECT COUNT(*) FROM users WHERE is_vip = 1 OR (vip_until IS NOT NULL AND vip_until > ?)", (now,))
        return cur.fetchone()[0]

def get_all_user_ids():
    with db() as cur:
        cur.execute("SELECT user_id FROM users")
        return [row[0] for row in cur.fetchall()]

init_db()
# =====================================================================
# PULSEFETCH BOT — PART 2 OF 4: LOCALES, KEYBOARDS, URL HELPERS
# =====================================================================

# --- 3. СЛОВАРИ ЛОКАЛИЗАЦИИ ---
LOCALES = {
    "ru": {
        "btn_dl": "📥 Скачать медиа",
        "btn_profile": "👤 Мой профиль",
        "btn_settings": "⚙️ Настройки",
        "btn_ref": "🎁 Бесплатный VIP за друзей",
        "btn_about": "ℹ️ О боте и правилах",
        "btn_restart": "🔄 Перезапустить бота",
        "start": "👋 Привет, {name}!\n\nДобро пожаловать в **PulseFetch** — бот для скачивания контента из TikTok, YouTube/Shorts, Instagram, Pinterest и других платформ!\n\nВоспользуйся меню ниже 👇",
        "group_welcome": "👋 **Всем привет! Я бот PulseFetch!**\n\nЯ умею скачивать медиа из **TikTok, YouTube / Shorts, Instagram Reels, Pinterest** прямо в этот чат!\n\n💡 Просто отправьте ссылку сюда!",
        "restart": "🔄 Бот успешно перезапущен!\n\n👇 Нажми «📥 Скачать медиа» для выбора платформы!",
        "step1": "📁 **Шаг 1 из 3: Выбери платформу для загрузки:**",
        "step2": "🎛 **Шаг 2 из 3: Выбери формат файла:**",
        "step3": "📥 **Шаг 3 из 3: Отправь ссылку на контент**\n\nПросто вставь её в этот чат!",
        "dl_loading": "⏳ **Загрузка медиа и оптимизация под лимит... Подожди.**",
        "dl_sending": "🚀 **Файл готов! Отправка в чат...**",
        "dl_error": "❌ **Ошибка скачивания.** Убедитесь, что ссылка правильная и видео не превышает 50 МБ.",
        "dl_too_big": "📦 **Файл слишком большой** даже в минимальном качестве (лимит Telegram — 50 МБ). Попробуй более короткое видео или формат «Только аудио».",
        "dl_busy": "⏳ **У тебя уже идёт загрузка.** Дождись её завершения.",
        "group_btn": "🤖 Открыть бота",
        "ref_joined": "🎉 По твоей ссылке зарегистрировался новый друг!",
        "ref_bonus": "🌟 Ты получил **VIP на 24 часа** за приглашённых друзей!",
        "vip_info": "🌟 VIP можно получить бесплатно: пригласи 3 друзей (кнопка «🎁 Бесплатный VIP за друзей»).",
        "stars_info": "⭐ Пополнение Stars скоро будет доступно.",
        "lang_changed": "✅ **Язык успешно изменен на Русский!**",
        "guide": "📖 **Гайд по использованию PulseFetch:**\n\n1️⃣ Нажми «📥 Скачать медиа».\n2️⃣ Выбери платформу и формат.\n3️⃣ Отправь ссылку и получи файл!"
    },
    "ua": {
        "btn_dl": "📥 Завантажити медіа",
        "btn_profile": "👤 Мій профіль",
        "btn_settings": "⚙️ Налаштування",
        "btn_ref": "🎁 Безкоштовний VIP за друзів",
        "btn_about": "ℹ️ Про бота та правила",
        "btn_restart": "🔄 Перезапустити бота",
        "start": "👋 Привіт, {name}!\n\nЛаскаво просимо до **PulseFetch** — бота для завантаження контенту з TikTok, YouTube/Shorts, Instagram, Pinterest та інших платформ!\n\nСкористайся меню нижче 👇",
        "group_welcome": "👋 **Усім привіт! Я бот PulseFetch!**\n\nЯ вмію завантажувати медіа з **TikTok, YouTube / Shorts, Instagram Reels, Pinterest** прямо у цей чат!\n\n💡 Просто надішліть посилання сюди!",
        "restart": "🔄 Бот успішно перезапущено!\n\n👇 Натисни «📥 Завантажити медіа» для вибору платформи!",
        "step1": "📁 **Крок 1 з 3: Обери платформу для завантаження:**",
        "step2": "🎛 **Крок 2 з 3: Обери формат файлу:**",
        "step3": "📥 **Крок 3 з 3: Надішли посилання на контент**\n\nПросто встав його у цей чат!",
        "dl_loading": "⏳ **Завантаження медіа та оптимізація... Зачекайте.**",
        "dl_sending": "🚀 **Файл готовий! Надсилання в чат...**",
        "dl_error": "❌ **Помилка завантаження.** Перевірте посилання або розмір (до 50 МБ).",
        "dl_too_big": "📦 **Файл завеликий** навіть у мінімальній якості (ліміт Telegram — 50 МБ). Спробуй коротше відео або формат «Лише аудіо».",
        "dl_busy": "⏳ **У тебе вже триває завантаження.** Дочекайся завершення.",
        "group_btn": "🤖 Відкрити бота",
        "ref_joined": "🎉 За твоїм посиланням зареєструвався новий друг!",
        "ref_bonus": "🌟 Ти отримав **VIP на 24 години** за запрошених друзів!",
        "vip_info": "🌟 VIP можна отримати безкоштовно: запроси 3 друзів (кнопка «🎁 Безкоштовний VIP за друзів»).",
        "stars_info": "⭐ Поповнення Stars скоро буде доступне.",
        "lang_changed": "✅ **Мову успішно змінено на Українську!**",
        "guide": "📖 **Гайд з використання PulseFetch:**\n\n1️⃣ Натисни «📥 Завантажити медіа».\n2️⃣ Обери платформу та формат.\n3️⃣ Надішли посилання й отримай файл!"
    },
    "en": {
        "btn_dl": "📥 Download media",
        "btn_profile": "👤 My profile",
        "btn_settings": "⚙️ Settings",
        "btn_ref": "🎁 Free VIP for friends",
        "btn_about": "ℹ️ About & Rules",
        "btn_restart": "🔄 Restart bot",
        "start": "👋 Hello, {name}!\n\nWelcome to **PulseFetch** — a bot for downloading content from TikTok, YouTube/Shorts, Instagram, Pinterest and more!\n\nUse the menu below 👇",
        "group_welcome": "👋 **Hello everyone! I'm PulseFetch Bot!**\n\nI can download media from **TikTok, YouTube / Shorts, Instagram Reels, Pinterest** directly to this chat!\n\n💡 Just send a link here!",
        "restart": "🔄 Bot restarted successfully!\n\n👇 Click «📥 Download media» to choose platform!",
        "step1": "📁 **Step 1 of 3: Select platform:**",
        "step2": "🎛 **Step 2 of 3: Select format:**",
        "step3": "📥 **Step 3 of 3: Send content link**\n\nJust paste it into this chat!",
        "dl_loading": "⏳ **Downloading and optimizing media... Please wait.**",
        "dl_sending": "🚀 **File is ready! Sending to chat...**",
        "dl_error": "❌ **Download error.** Make sure the link is correct and under 50 MB.",
        "dl_too_big": "📦 **File is too large** even at the lowest quality (Telegram limit is 50 MB). Try a shorter video or the «Audio only» format.",
        "dl_busy": "⏳ **You already have a download in progress.** Please wait for it to finish.",
        "group_btn": "🤖 Open bot",
        "ref_joined": "🎉 A new friend has joined via your link!",
        "ref_bonus": "🌟 You got **24 hours of VIP** for inviting friends!",
        "vip_info": "🌟 You can get VIP for free: invite 3 friends (button «🎁 Free VIP for friends»).",
        "stars_info": "⭐ Stars top-up will be available soon.",
        "lang_changed": "✅ **Language successfully changed to English!**",
        "guide": "📖 **PulseFetch User Guide:**\n\n1️⃣ Click «📥 Download media».\n2️⃣ Choose platform and format.\n3️⃣ Send link and get your file!"
    }
}

def md2html(text: str) -> str:
    """**жирный** -> <b>, `код` -> <code>. Бот работает в HTML-режиме (устойчиво к спецсимволам в именах)."""
    text = html.escape(text, quote=False)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text, flags=re.S)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    return text

def get_lang(user_id) -> str:
    user = get_user(user_id)
    return user[2] if user and user[2] in LOCALES else "ru"

def t(user_id, key, **kwargs):
    lang = get_lang(user_id)
    raw = LOCALES[lang].get(key) or LOCALES["ru"].get(key, "")
    text = md2html(raw)
    if kwargs:
        text = text.format(**{k: html.escape(str(v), quote=False) for k, v in kwargs.items()})
    return text

# --- 4. КЛАВИАТУРЫ ---
def get_main_keyboard(user_id: int):
    kb = [
        [KeyboardButton(text=t(user_id, "btn_dl"))],
        [KeyboardButton(text=t(user_id, "btn_profile")), KeyboardButton(text=t(user_id, "btn_settings"))],
        [KeyboardButton(text=t(user_id, "btn_ref"))],
        [KeyboardButton(text=t(user_id, "btn_about")), KeyboardButton(text=t(user_id, "btn_restart"))]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_platforms_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎵 TikTok", callback_data="plat_tiktok"),
            InlineKeyboardButton(text="📺 YouTube / Shorts", callback_data="plat_youtube")
        ],
        [InlineKeyboardButton(text="📸✨ Instagram Reels", callback_data="plat_instagram")],
        [InlineKeyboardButton(text="🌐 Другие платформы (Pinterest, FB, X...)", callback_data="plat_other")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_download")]
    ])

def get_format_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Только видео", callback_data="fmt_video")],
        [InlineKeyboardButton(text="🎵 Только аудио (MP3)", callback_data="fmt_audio")],
        [InlineKeyboardButton(text="📦 Всё вместе (видео + звук)", callback_data="fmt_both")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_download")]
    ])

def get_settings_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Сменить язык / Change Language", callback_data="change_lang")],
        [InlineKeyboardButton(text="📖 Гайд по использованию", callback_data="show_guide")]
    ])

def get_languages_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="setlang_ru"),
            InlineKeyboardButton(text="🇺🇦 Українська", callback_data="setlang_ua"),
            InlineKeyboardButton(text="🇬🇧 English", callback_data="setlang_en")
        ],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_settings")]
    ])

def get_profile_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Продлить / Получить VIP", callback_data="buy_vip")],
        [InlineKeyboardButton(text="⭐ Купить Stars", callback_data="buy_stars")]
    ])

def get_back_to_menu_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_to_menu")]
    ])

def get_admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Сделать рассылку", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="📊 Подробная статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="⭐ Управление VIP", callback_data="admin_vip_menu")]
    ])

def get_group_welcome_keyboard(user_id, bot_username):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=LOCALES[get_lang(user_id)]["group_btn"], url=f"https://t.me/{bot_username}")]
    ])

# --- 5. ССЫЛКИ: ОПРЕДЕЛЕНИЕ, КОРОТКИЕ ССЫЛКИ (pin.it и др.) ---
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
URL_RE = re.compile(r"https?://[^\s<>\"']+", re.I)

SHORT_HOSTS = {"pin.it", "vm.tiktok.com", "vt.tiktok.com", "t.co", "fb.watch",
               "redd.it", "l.likee.video", "likee.video"}
SUPPORTED_DOMAINS = ("tiktok.com", "youtube.com", "youtu.be", "instagram.com", "pin.it",
                     "facebook.com", "fb.watch", "twitter.com", "x.com", "t.co",
                     "reddit.com", "redd.it", "likee.video", "likee.com")

def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")

def is_supported_url(url: str) -> bool:
    host = _host(url)
    if re.search(r"(^|\.)pinterest\.", host):
        return True
    return any(host == d or host.endswith("." + d) for d in SUPPORTED_DOMAINS)

def find_any_url(text):
    m = URL_RE.search(text or "")
    return m.group(0).rstrip(".,;:!?)»]}") if m else None

def find_supported_url(text):
    for m in URL_RE.finditer(text or ""):
        url = m.group(0).rstrip(".,;:!?)»]}")
        if is_supported_url(url):
            return url
    return None

def _is_pinterest(url: str) -> bool:
    host = _host(url)
    return host == "pin.it" or bool(re.search(r"(^|\.)pinterest\.", host))

def needs_resolve(url: str) -> bool:
    host, path = _host(url), urlparse(url).path
    if host in SHORT_HOSTS:
        return True
    if host.endswith("tiktok.com") and path.startswith("/t/"):
        return True
    if host.endswith("facebook.com") and path.startswith("/share/"):
        return True
    if host.endswith("instagram.com") and path.startswith("/share/"):
        return True
    if host.endswith("reddit.com") and re.search(r"/s/[A-Za-z0-9]+/?$", path):
        return True
    return False

async def resolve_url(url: str) -> str:
    """Раскрывает короткие/share-ссылки (pin.it, vm.tiktok.com, fb share, reddit /s/ ...)."""
    if needs_resolve(url):
        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout, headers={"User-Agent": UA}) as s:
                async with s.get(url, allow_redirects=True, max_redirects=8) as resp:
                    url = str(resp.url)
        except Exception as e:
            logging.warning(f"resolve_url failed for {url}: {e}")
    # Pinterest: чистим мусор (/sent/?invite_code=...)
    if _is_pinterest(url):
        m = re.search(r"/pin/(\d+)", urlparse(url).path)
        if m:
            url = f"https://www.pinterest.com/pin/{m.group(1)}/"
    return url
# =====================================================================
# PULSEFETCH BOT — PART 3 OF 4: DOWNLOADER (YT-DLP, 48 MB LIMIT, WATERMARK)
# =====================================================================

# --- 6. МОДУЛЬ ЗАГРУЗКИ (ЛИМИТ 48 МБ, VIP/ADMIN, ВОДЯНОЙ ЗНАК) ---
TG_LIMIT = 48 * 1024 * 1024
DOWNLOAD_ROOT = "downloads"
HEIGHT_LADDER = [2160, 1440, 1080, 720, 480, 360, 240, 144]
COOKIES_FILE = os.getenv("COOKIES_FILE", "cookies.txt")   # необязательно (Netscape cookies.txt)
WM_TEXT = "@PulseFetchBot"
WM_PNG = "pulsefetch_wm.png"

# Не больше N одновременных загрузок (защита RAM/CPU на Render)
DOWNLOAD_SEM = asyncio.Semaphore(int(os.getenv("MAX_PARALLEL_DOWNLOADS", "2")))
ACTIVE_USERS = set()

class FileTooBigError(Exception):
    pass

def _base_opts():
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "playlist_items": "1",
        "nocheckcertificate": True,
        "ignoreerrors": False,
        "retries": 5,
        "fragment_retries": 5,
        "socket_timeout": 30,
        "concurrent_fragment_downloads": 4,
        "merge_output_format": "mp4",
        "restrictfilenames": True,
        "max_filesize": 300 * 1024 * 1024,   # защита от гигантских файлов; точный лимит проверяем сами
    }
    if os.path.isfile(COOKIES_FILE):
        opts["cookiefile"] = COOKIES_FILE
    return opts

def _is_video(f):
    return f.get("vcodec") != "none" and bool(f.get("height") or f.get("width"))

def _is_audio_only(f):
    return f.get("vcodec") == "none" and f.get("acodec") not in (None, "none")

def _portrait(info) -> bool:
    vids = [f for f in (info.get("formats") or []) if _is_video(f) and f.get("width") and f.get("height")]
    if not vids:
        return False
    best = max(vids, key=lambda x: x["height"])
    return best["height"] > best["width"]

def _dim(f, portrait):
    # для вертикальных видео (Shorts/TikTok/Reels) «качество» считаем по ширине
    return f.get("width" if portrait else "height")

def _fsize(f, duration):
    size = f.get("filesize") or f.get("filesize_approx")
    if not size and duration:
        br = f.get("tbr") or ((f.get("vbr") or 0) + (f.get("abr") or 0))
        if br:
            size = br * 1000 / 8 * duration
    return size

def _estimate_size(info, level, portrait):
    fmts = info.get("formats") or []
    duration = info.get("duration") or 0
    vids = [f for f in fmts if _is_video(f) and (_dim(f, portrait) or 0) <= level]
    if not vids:
        return None
    best = max(vids, key=lambda f: ((_dim(f, portrait) or 0), f.get("tbr") or 0))
    size = _fsize(best, duration)
    if size is None:
        return None
    if best.get("acodec") == "none":
        auds = [f for f in fmts if _is_audio_only(f)]
        if auds:
            a = max(auds, key=lambda f: f.get("abr") or f.get("tbr") or 0)
            asz = _fsize(a, duration)
            if asz is None:
                return None
            size += asz
    return size

def _height_steps(info, cap, portrait):
    cap = cap or 10 ** 6
    dims = sorted({d for d in (_dim(f, portrait) for f in (info.get("formats") or []) if _is_video(f)) if d},
                  reverse=True)
    if not dims:
        return [h for h in HEIGHT_LADDER if h <= cap][:4] or [cap]
    steps = []
    for lvl in HEIGHT_LADDER:
        if lvl > cap:
            continue
        eff = next((d for d in dims if d <= lvl), None)
        if eff and eff not in steps:
            steps.append(eff)
    return (steps or [dims[-1]])[:4]

def _format_for(level, portrait):
    k = "width" if portrait else "height"
    f = f"[{k}<={level}]"
    return (f"bv*{f}[vcodec^=avc1]+ba[ext=m4a]/bv*{f}[ext=mp4]+ba[ext=m4a]/"
            f"bv*{f}+ba/b{f}/b")

def _extract_info(url, opts):
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.sanitize_info(ydl.extract_info(url, download=False))
    if info.get("entries"):
        entries = [e for e in info["entries"] if e]
        if entries:
            info = entries[0]
    return info

def _download(url, opts):
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if info and info.get("entries"):
            entries = [e for e in info["entries"] if e]
            info = entries[0] if entries else info
        path = None
        rd = (info or {}).get("requested_downloads") or []
        if rd and rd[0].get("filepath"):
            path = rd[0]["filepath"]
        if not path:
            path = ydl.prepare_filename(info)
        return path

async def _download_video(url, job_dir, info, cap, loop):
    portrait = _portrait(info)
    steps = _height_steps(info, cap, portrait)
    base = _base_opts()
    for level in steps:
        est = _estimate_size(info, level, portrait)
        if est and est > TG_LIMIT * 1.15:
            logging.info(f"Skip level {level}: estimated {est / 1048576:.1f} MB")
            continue
        opts = dict(base)
        opts["format"] = _format_for(level, portrait)
        opts["outtmpl"] = os.path.join(job_dir, f"v{level}_%(id)s.%(ext)s")
        path = await loop.run_in_executor(None, _download, url, opts)
        if path and os.path.isfile(path):
            if os.path.getsize(path) <= TG_LIMIT:
                return path
            logging.info(f"Level {level} too big, trying lower quality")
            os.remove(path)
    raise FileTooBigError("Видео не помещается в лимит Telegram")

async def _download_audio(url, job_dir, info, loop):
    duration = info.get("duration") or 0
    kbps = 192
    if duration:
        for k in (192, 128, 96, 64):
            kbps = k
            if duration * k * 1000 / 8 <= TG_LIMIT * 0.95:
                break
    opts = _base_opts()
    opts["format"] = "bestaudio/best"
    opts["outtmpl"] = os.path.join(job_dir, "a_%(id)s.%(ext)s")
    opts["postprocessors"] = [{
        "key": "FFmpegExtractAudio",
        "preferredcodec": "mp3",
        "preferredquality": str(kbps),
    }]
    await loop.run_in_executor(None, _download, url, opts)
    files = glob.glob(os.path.join(job_dir, "a_*.mp3"))
    if not files:
        raise RuntimeError("Аудио не было создано")
    path = files[0]
    if os.path.getsize(path) > TG_LIMIT:
        os.remove(path)
        raise FileTooBigError("Аудио не помещается в лимит Telegram")
    return path

# --- ВОДЯНОЙ ЗНАК (FFmpeg) ---
FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]

def _find_font():
    return next((p for p in FONT_CANDIDATES if os.path.isfile(p)), None)

def ensure_watermark_png() -> bool:
    """Рисует PNG с @PulseFetchBot через Pillow (не требует системных шрифтов в ffmpeg)."""
    if os.path.isfile(WM_PNG):
        return True
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return False
    try:
        fp = _find_font()
        if fp:
            font = ImageFont.truetype(fp, 30)
        else:
            try:
                font = ImageFont.load_default(size=30)
            except TypeError:
                font = ImageFont.load_default()
        probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
        l, tp, r, b = probe.textbbox((0, 0), WM_TEXT, font=font)
        pad = 10
        img = Image.new("RGBA", (r - l + pad * 2, b - tp + pad * 2), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([0, 0, img.width - 1, img.height - 1], radius=8, fill=(0, 0, 0, 140))
        d.text((pad - l, pad - tp), WM_TEXT, font=font, fill=(255, 255, 255, 235))
        img.save(WM_PNG)
        return True
    except Exception as e:
        logging.error(f"Watermark PNG error: {e}")
        return False

async def _run_ffmpeg(args, timeout=900) -> bool:
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE
        )
    except FileNotFoundError:
        logging.error("ffmpeg не найден в системе!")
        return False
    try:
        _, err = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        logging.error("ffmpeg timeout")
        return False
    if proc.returncode != 0:
        logging.error("ffmpeg error: %s", err.decode(errors="ignore")[-600:])
        return False
    return True

def _wm_attempts(src, out, crf):
    even = "scale=trunc(iw/2)*2:trunc(ih/2)*2"
    enc = ["-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf), "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", out]
    attempts = []
    if ensure_watermark_png():
        attempts.append(["-i", src, "-i", WM_PNG, "-filter_complex",
                         f"[0:v]{even}[b];[b][1:v]overlay=W-w-12:H-h-12", *enc])
    font = _find_font()
    ff = f"fontfile={font}:" if font else ""
    dt = (f"{even},drawtext={ff}text='{WM_TEXT}':fontcolor=white:fontsize=24:"
          f"x=w-tw-10:y=h-th-10:box=1:boxcolor=black@0.5:boxborderw=5")
    attempts.append(["-i", src, "-vf", dt, *enc])
    return attempts

async def process_video(src: str, watermark: bool) -> str:
    """Накладывает водяной знак (free/группы) или приводит видео к mp4 (VIP/admin)."""
    ext = os.path.splitext(src)[1].lower()
    base = os.path.splitext(src)[0]

    if not watermark:
        if ext == ".mp4":
            return src
        out = base + "_conv.mp4"
        if await _run_ffmpeg(["-i", src, "-c", "copy", "-movflags", "+faststart", out]) and os.path.isfile(out):
            return out
        if await _run_ffmpeg(["-i", src, "-c:v", "libx264", "-preset", "veryfast", "-crf", "24",
                              "-c:a", "aac", "-movflags", "+faststart", out]) and os.path.isfile(out):
            return out
        return src

    out = base + "_wm.mp4"
    too_big = False
    for crf in (26, 32):
        for args in _wm_attempts(src, out, crf):
            if await _run_ffmpeg(args) and os.path.isfile(out):
                if os.path.getsize(out) <= TG_LIMIT:
                    return out
                too_big = True
                break   # слишком большой — повторяем с более сильным сжатием
        else:
            continue
    if too_big:
        raise FileTooBigError("После наложения водяного знака файл больше лимита")
    logging.error("Водяной знак не удалось наложить — отправляем оригинал (проверь ffmpeg/Pillow)")
    return src

# --- ЗАПАСНОЙ ВАРИАНТ ДЛЯ PINTEREST (картинки/гифки, когда yt-dlp не справился) ---
async def fetch_og_media(url, job_dir):
    def og(page, prop):
        pats = [
            r'<meta[^>]+(?:property|name)=["\']%s["\'][^>]+content=["\']([^"\']+)["\']' % re.escape(prop),
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']%s["\']' % re.escape(prop),
        ]
        for p in pats:
            m = re.search(p, page, re.I)
            if m:
                return html.unescape(m.group(1))
        return None

    timeout = aiohttp.ClientTimeout(total=40)
    async with aiohttp.ClientSession(timeout=timeout, headers={"User-Agent": UA}) as s:
        async with s.get(url, allow_redirects=True) as resp:
            if resp.status != 200:
                return None
            page = await resp.text(errors="ignore")
        video = og(page, "og:video") or og(page, "og:video:url")
        image = og(page, "og:image")
        candidates = []
        if video:
            candidates.append((video, "video"))
        if image:
            candidates.append((image.replace("/736x/", "/originals/"), "photo"))
            candidates.append((image, "photo"))
        for media_url, kind in candidates:
            try:
                async with s.get(media_url) as r:
                    if r.status != 200:
                        continue
                    ext = os.path.splitext(urlparse(media_url).path)[1] or (".mp4" if kind == "video" else ".jpg")
                    path = os.path.join(job_dir, f"og_{uuid.uuid4().hex[:8]}{ext}")
                    size = 0
                    with open(path, "wb") as fh:
                        async for chunk in r.content.iter_chunked(262144):
                            size += len(chunk)
                            if size > TG_LIMIT:
                                break
                            fh.write(chunk)
                    if size > TG_LIMIT:
                        os.remove(path)
                        continue
                    return path, kind
            except Exception as e:
                logging.warning(f"og media fetch failed: {e}")
    return None

# --- ГЛАВНАЯ ФУНКЦИЯ ЗАГРУЗКИ ---
async def download_media_files(url: str, user_id: int, mode: str = "video", is_group: bool = False) -> dict:
    os.makedirs(DOWNLOAD_ROOT, exist_ok=True)

    # ADMIN_ID ВСЕГДА VIP: без водяного знака и с максимальным качеством
    is_admin = user_id == ADMIN_ID
    is_vip = True if is_admin else is_user_vip(user_id)
    if is_admin:
        watermark, cap = False, None
    else:
        watermark = (not is_vip) or is_group          # free и группы -> водяной знак
        cap = 720 if ((not is_vip) or is_group) else None

    job_dir = os.path.join(DOWNLOAD_ROOT, uuid.uuid4().hex)
    os.makedirs(job_dir, exist_ok=True)
    result = {"video": None, "audio": None, "photo": None, "dir": job_dir}
    loop = asyncio.get_running_loop()

    try:
        url = await resolve_url(url)

        try:
            info = await loop.run_in_executor(None, _extract_info, url, _base_opts())
        except Exception as e:
            if mode != "audio" and _is_pinterest(url):
                logging.info(f"yt-dlp failed for Pinterest ({e}); trying og-fallback")
                media = await fetch_og_media(url, job_dir)
                if media:
                    path, kind = media
                    result[kind] = await process_video(path, watermark) if kind == "video" else path
                    return result
            raise

        if info.get("is_live"):
            raise RuntimeError("Live streams are not supported")

        if mode in ("video", "both"):
            path = await _download_video(url, job_dir, info, cap, loop)
            result["video"] = await process_video(path, watermark)

        if mode in ("audio", "both"):
            result["audio"] = await _download_audio(url, job_dir, info, loop)

        return result
    except BaseException:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise

def cleanup_result(result):
    if result and result.get("dir"):
        shutil.rmtree(result["dir"], ignore_errors=True)
# =====================================================================
# PULSEFETCH BOT — PART 4 OF 5: SETUP, MENUS, PROFILE, PLATFORM/FORMAT
# =====================================================================

session = AiohttpSession(timeout=300)   # большие файлы грузятся дольше 60 сек
bot = Bot(token=BOT_TOKEN, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

class DownloadState(StatesGroup):
    waiting_for_format = State()
    waiting_for_link = State()

class AdminState(StatesGroup):
    waiting_for_broadcast = State()
    waiting_for_vip_user_id = State()

# --- ВСПОМОГАТЕЛЬНОЕ ---
_BOT_USERNAME = None

async def get_bot_username():
    global _BOT_USERNAME
    if not _BOT_USERNAME:
        _BOT_USERNAME = (await bot.get_me()).username
    return _BOT_USERNAME

async def safe_edit(message, text, **kwargs):
    try:
        await message.edit_text(text, **kwargs)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            raise

async def _delete_later(msg, delay=10):
    await asyncio.sleep(delay)
    try:
        await msg.delete()
    except Exception:
        pass

async def run_download(url, user_id, mode, is_group):
    async with DOWNLOAD_SEM:
        return await download_media_files(url, user_id, mode=mode, is_group=is_group)

def error_text(user_id, exc):
    if isinstance(exc, FileTooBigError):
        return t(user_id, "dl_too_big")
    return t(user_id, "dl_error")

def settings_text(user_id):
    lang_map = {"ru": "Русский 🇷🇺", "ua": "Українська 🇺🇦", "en": "English 🇬🇧"}
    return (
        "⚙️ <b>Настройки / Settings</b>\n\n"
        f"🌐 <b>Текущий язык интерфейса:</b> {lang_map.get(get_lang(user_id), 'Русский 🇷🇺')}"
    )

def admin_text(user_id):
    return (
        "👑 <b>Профессиональная Админ-панель PulseFetch</b>\n\n"
        f"👤 Ваш Telegram ID: <code>{user_id}</code> (Главный Администратор)\n\n"
        f"👥 Всего пользователей в базе: <code>{get_all_users_count()}</code>\n"
        f"🌟 Активных VIP-пользователей: <code>{get_vip_users_count()}</code>\n"
        f"📥 Всего скачано файлов ботом: <code>{get_total_downloads_sum()}</code>\n\n"
        "Выберите действие ниже:"
    )

# --- ОБРАБОТКА ДОБАВЛЕНИЯ БОТА В ГРУППЫ ---
@dp.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=IS_NOT_MEMBER >> IS_MEMBER))
async def on_bot_added_to_group(event: ChatMemberUpdated):
    try:
        uid = event.from_user.id
        username = await get_bot_username()
        await event.answer(t(uid, "group_welcome"), reply_markup=get_group_welcome_keyboard(uid, username))
    except Exception as e:
        logging.warning(f"Group welcome failed: {e}")

# --- АВТОМАТИЧЕСКИЙ ПЕРЕХВАТ ССЫЛОК В ГРУППАХ (только поддерживаемые платформы) ---
@dp.message(F.chat.type.in_({"group", "supergroup"}),
            F.text.func(lambda s: find_supported_url(s) is not None))
async def handle_group_link(message: types.Message):
    if not message.from_user or message.from_user.is_bot:
        return
    uid = message.from_user.id
    add_user(uid, message.from_user.username)
    if uid in ACTIVE_USERS:
        return
    url = find_supported_url(message.text)
    ACTIVE_USERS.add(uid)
    status_msg = await message.reply("⏳ <b>Загрузка медиа для группы...</b>")
    files = None
    try:
        files = await run_download(url, uid, "video", True)
        if files.get("video"):
            await message.reply_video(video=FSInputFile(files["video"]),
                                      caption="✅ Скачано через @PulseFetchBot", supports_streaming=True)
        elif files.get("photo"):
            await message.reply_photo(photo=FSInputFile(files["photo"]), caption="✅ Скачано через @PulseFetchBot")
        else:
            raise RuntimeError("empty result")
        increment_downloads(uid)
        await status_msg.delete()
    except Exception as e:
        logging.error(f"Group download error: {e}", exc_info=True)
        try:
            await status_msg.edit_text("❌ Не удалось скачать медиа по этой ссылке в группе.")
            spawn(_delete_later(status_msg, 10))
        except Exception:
            pass
    finally:
        ACTIVE_USERS.discard(uid)
        cleanup_result(files)

# --- КОМАНДА /start В ЛИЧНЫХ СООБЩЕНИЯХ ---
@dp.message(CommandStart(), F.chat.type == "private")
async def start_cmd(message: types.Message, state: FSMContext):
    await state.clear()
    args = (message.text or "").split(maxsplit=1)
    ref_id = None
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            ref_id = int(args[1][4:])
        except ValueError:
            ref_id = None

    is_new, referrer, bonus = add_user(message.from_user.id, message.from_user.username, referred_by=ref_id)

    await message.answer(
        t(message.from_user.id, "start", name=message.from_user.first_name),
        reply_markup=get_main_keyboard(message.from_user.id)
    )

    if is_new and referrer:
        try:
            await bot.send_message(referrer, t(referrer, "ref_joined"))
            if bonus:
                await bot.send_message(referrer, t(referrer, "ref_bonus"))
        except Exception:
            pass

# --- АДМИН-ПАНЕЛЬ (ID: 6444735646) — регистрируется ДО state-хэндлеров ---
@dp.message(Command("admin"))
async def admin_panel(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.clear()
    await message.answer(admin_text(message.from_user.id), reply_markup=get_admin_keyboard())

# --- 🔄 ПЕРЕЗАПУСК БОТА ---
@dp.message(F.text.in_({"🔄 Перезапустить бота", "🔄 Перезапустити бота", "🔄 Restart bot"}))
async def restart_cmd(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        t(message.from_user.id, "restart"),
        reply_markup=get_main_keyboard(message.from_user.id)
    )

# --- ℹ️ О БОТЕ И ПРАВИЛАХ ---
@dp.message(F.text.in_({"ℹ️ О боте и правилах", "ℹ️ Про бота та правила", "ℹ️ About & Rules"}))
async def about_cmd(message: types.Message, state: FSMContext):
    await state.clear()
    text = (
        "🤖 <b>О боте PulseFetch / About PulseFetch:</b>\n\n"
        "⚡️ <b>СРАВНЕНИЕ ТАРИФОВ / TARIFS:</b>\n\n"
        "👤 <b>Обычный тариф / Free:</b>\n"
        "• Max size: 50 MB\n"
        "• Quality: up to 720p\n"
        "• Watermark: YES (накладывается логотип)\n\n"
        "🌟 <b>VIP Subscription:</b>\n"
        "• Max size: 50 MB\n"
        "• Quality: Max (1080p+)\n"
        "• MP3 audio extraction: YES\n"
        "• Watermark: NO (чистое видео без водянки)"
    )
    await message.answer(text, reply_markup=get_back_to_menu_keyboard())

# --- 🎁 БЕСПЛАТНЫЙ VIP ЗА ДРУЗЕЙ ---
@dp.message(F.text.in_({"🎁 Бесплатный VIP за друзей", "🎁 Безкоштовний VIP за друзів", "🎁 Free VIP for friends"}))
async def ref_cmd(message: types.Message, state: FSMContext):
    await state.clear()
    add_user(message.from_user.id, message.from_user.username)
    user = get_user(message.from_user.id)
    ref_count = user[6] if user else 0
    bonus_count = user[7] if user else 0
    left_to_vip = max(0, 3 - (ref_count % 3))
    username = await get_bot_username()

    text = (
        "🎁 <b>Получи VIP на 24 часа бесплатно!</b>\n\n"
        f"🔗 <b>Твоя персональная ссылка:</b>\nhttps://t.me/{username}?start=ref_{message.from_user.id}\n\n"
        "📊 <b>Твоя статистика рефералов:</b>\n"
        f"• Приглашено друзей: {ref_count}\n"
        f"• Бонусных циклов: {bonus_count} / 3\n"
        f"🎯 <b>До VIP осталось пригласить:</b> {left_to_vip} чел."
    )
    await message.answer(text)

# --- 👤 ПРОФИЛЬ ---
@dp.message(F.text.in_({"👤 Мой профиль", "👤 Мій профіль", "👤 My profile"}))
async def profile_cmd(message: types.Message, state: FSMContext):
    await state.clear()
    add_user(message.from_user.id, message.from_user.username)
    user = get_user(message.from_user.id)

    downloads = user[5] or 0
    ref_count = user[6] or 0
    stars = user[9] or 0
    reg_date = user[10] or "Недавно"
    is_vip = is_user_vip(message.from_user.id)
    vip_status = "🌟 VIP (без водяных знаков, макс. качество)" if is_vip else "👤 Free (до 720p, с водяным знаком)"
    if is_vip and message.from_user.id != ADMIN_ID and user[3] != 1 and user[4]:
        vip_status += f"\n⏳ Действует до: {html.escape(str(user[4]))} UTC"

    text = (
        f"👤 <b>Профиль пользователя:</b> {html.escape(message.from_user.first_name or '')}\n"
        f"🆔 <b>ID:</b> <code>{message.from_user.id}</code>\n"
        f"🔰 <b>Статус аккаунта:</b> {vip_status}\n\n"
        f"📊 <b>Статистика скачиваний:</b>\n"
        f"• Успешно скачано файлов: <code>{downloads}</code>\n"
        f"• Приглашено рефералов: <code>{ref_count}</code>\n"
        f"⭐ <b>Баланс Stars:</b> <code>{stars}</code>\n"
        f"📅 <b>Дата регистрации:</b> <code>{html.escape(str(reg_date))}</code>"
    )
    await message.answer(text, reply_markup=get_profile_keyboard())

@dp.callback_query(F.data == "buy_vip")
async def buy_vip_handler(callback: types.CallbackQuery):
    await callback.answer(re.sub(r"<[^>]+>", "", t(callback.from_user.id, "vip_info")), show_alert=True)

@dp.callback_query(F.data == "buy_stars")
async def buy_stars_handler(callback: types.CallbackQuery):
    await callback.answer(re.sub(r"<[^>]+>", "", t(callback.from_user.id, "stars_info")), show_alert=True)

# --- ⚙️ НАСТРОЙКИ ---
@dp.message(F.text.in_({"⚙️ Настройки", "⚙️ Налаштування", "⚙️ Settings"}))
async def settings_cmd(message: types.Message, state: FSMContext):
    await state.clear()
    add_user(message.from_user.id, message.from_user.username)
    await message.answer(settings_text(message.from_user.id), reply_markup=get_settings_keyboard())

# --- ШАГ 1: Нажатие «Скачать медиа» -> Выбор платформы ---
@dp.message(F.text.in_({"📥 Скачать медиа", "📥 Завантажити медіа", "📥 Download media"}))
async def choose_platform(message: types.Message, state: FSMContext):
    await state.clear()
    add_user(message.from_user.id, message.from_user.username)
    await message.answer(
        t(message.from_user.id, "step1"),
        reply_markup=get_platforms_keyboard()
    )

# --- ИНФОРМАЦИЯ О ДРУГИХ ПЛАТФОРМАХ ---
@dp.callback_query(F.data == "plat_other")
async def show_other_platforms(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(platform="other")
    await state.set_state(DownloadState.waiting_for_format)
    text = (
        "🌐 <b>Поддерживаемые дополнительные платформы:</b>\n\n"
        "📌 <b>Pinterest</b> (включая ссылки <code>pin.it</code>)\n"
        "📘 <b>Facebook</b> (видео и Reels)\n"
        "🐦 <b>Twitter / X</b> (видео и GIF)\n"
        "👽 <b>Reddit</b> (видеоклипы)\n"
        "🎵 <b>Likee</b>\n\n"
        "👉 Вы можете просто выслать ссылку с любой из этих платформ в чат после выбора формата!"
    )
    await safe_edit(callback.message, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➡️ Выбрать формат", callback_data="plat_other_next")],
        [InlineKeyboardButton(text="◀️ Назад к выбору", callback_data="back_to_platforms")]
    ]))
    await callback.answer()

@dp.callback_query(F.data == "plat_other_next")
async def other_platforms_next(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(DownloadState.waiting_for_format)
    await safe_edit(callback.message, t(callback.from_user.id, "step2"), reply_markup=get_format_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "back_to_platforms")
async def back_to_platforms_handler(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await safe_edit(callback.message, t(callback.from_user.id, "step1"), reply_markup=get_platforms_keyboard())
    await callback.answer()

# --- ШАГ 2: Выбор платформы -> Выбор формата ---
@dp.callback_query(F.data.startswith("plat_") & ~F.data.in_({"plat_other", "plat_other_next"}))
async def platform_selected(callback: types.CallbackQuery, state: FSMContext):
    platform = callback.data.split("_", 1)[1]
    await state.update_data(platform=platform)
    await state.set_state(DownloadState.waiting_for_format)
    await safe_edit(callback.message, t(callback.from_user.id, "step2"), reply_markup=get_format_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "cancel_download")
async def cancel_download(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await safe_edit(callback.message, "❌ Загрузка отменена.")
    await callback.answer()

# --- ШАГ 3: Выбор формата -> Запрос ссылки ---
@dp.callback_query(F.data.startswith("fmt_"))
async def format_selected(callback: types.CallbackQuery, state: FSMContext):
    format_type = callback.data.split("_", 1)[1]
    if format_type not in ("video", "audio", "both"):
        await callback.answer()
        return
    await state.update_data(format_type=format_type)
    await state.set_state(DownloadState.waiting_for_link)
    await safe_edit(callback.message, t(callback.from_user.id, "step3"))
    await callback.answer()
# =====================================================================
# PULSEFETCH BOT — PART 5 OF 5: DOWNLOAD STEP, LANGUAGE, ADMIN, MAIN
# =====================================================================

# --- ШАГ 4: Обработка ссылки и выгрузка ---
@dp.message(DownloadState.waiting_for_link, F.text)
async def process_download_link(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    url = find_any_url(message.text)
    if not url:
        await message.answer("⚠️ Пожалуйста, отправьте корректную ссылку, начинающуюся с http:// или https://")
        return
    if uid in ACTIVE_USERS:
        await message.answer(t(uid, "dl_busy"))
        return

    add_user(uid, message.from_user.username)
    data = await state.get_data()
    format_type = data.get("format_type", "video")

    ACTIVE_USERS.add(uid)
    status_msg = await message.answer(t(uid, "dl_loading"))
    files = None
    try:
        files = await run_download(url, uid, format_type, False)
        await safe_edit(status_msg, t(uid, "dl_sending"))

        if not any(files.get(k) for k in ("video", "audio", "photo")):
            raise RuntimeError("empty result")

        if files.get("video"):
            await message.answer_video(video=FSInputFile(files["video"]),
                                       caption="🎬 Видео | @PulseFetchBot", supports_streaming=True)
        if files.get("photo"):
            await message.answer_photo(photo=FSInputFile(files["photo"]), caption="🖼 Фото | @PulseFetchBot")
        if files.get("audio"):
            await message.answer_audio(audio=FSInputFile(files["audio"]), caption="🎵 Аудио | @PulseFetchBot")

        increment_downloads(uid)
        await status_msg.delete()

    except Exception as e:
        logging.error(f"Download error: {e}", exc_info=True)
        try:
            await status_msg.edit_text(error_text(uid, e))
        except Exception:
            await message.answer(error_text(uid, e))

    finally:
        ACTIVE_USERS.discard(uid)
        cleanup_result(files)
        await state.clear()

@dp.message(DownloadState.waiting_for_link)
async def process_download_non_text(message: types.Message):
    await message.answer("⚠️ Пожалуйста, отправьте корректную ссылку, начинающуюся с http:// или https://")

# --- СМЕНА ЯЗЫКА ---
@dp.callback_query(F.data == "change_lang")
async def change_lang_menu(callback: types.CallbackQuery):
    await safe_edit(callback.message, "🌐 Выбери язык / Choose language:", reply_markup=get_languages_keyboard())
    await callback.answer()

@dp.callback_query(F.data.startswith("setlang_"))
async def set_language(callback: types.CallbackQuery, state: FSMContext):
    lang = callback.data.split("_", 1)[1]
    if lang not in LOCALES:
        await callback.answer()
        return
    add_user(callback.from_user.id, callback.from_user.username)
    set_user_language(callback.from_user.id, lang)
    await state.clear()   # сбрасываем возможные «зависшие» стейты

    await callback.answer("✅ Done")
    await safe_edit(callback.message, t(callback.from_user.id, "lang_changed"))
    # Новое сообщение с ReplyKeyboard мгновенно обновляет клавиатуру на выбранном языке
    await callback.message.answer(
        t(callback.from_user.id, "restart"),
        reply_markup=get_main_keyboard(callback.from_user.id)
    )

@dp.callback_query(F.data == "show_guide")
async def show_guide(callback: types.CallbackQuery):
    await safe_edit(
        callback.message,
        t(callback.from_user.id, "guide"),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_settings")]
        ])
    )
    await callback.answer()

@dp.callback_query(F.data == "back_to_settings")
async def back_to_settings_handler(callback: types.CallbackQuery):
    await safe_edit(callback.message, settings_text(callback.from_user.id), reply_markup=get_settings_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu_handler(callback: types.CallbackQuery):
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer("Menu:", reply_markup=get_main_keyboard(callback.from_user.id))
    await callback.answer()

# --- АДМИН: СТАТИСТИКА / VIP / РАССЫЛКА ---
@dp.callback_query(F.data == "admin_stats")
async def admin_stats_handler(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer()
        return
    text = (
        "📊 <b>Подробная статистика бота:</b>\n\n"
        f"• Всего пользователей: <code>{get_all_users_count()}</code>\n"
        f"• Количество пользователей с VIP: <code>{get_vip_users_count()}</code>\n"
        f"• Суммарно скачано файлов: <code>{get_total_downloads_sum()}</code>\n"
        f"• Сервер: 🟢 Онлайн (Автопинг 60с)"
    )
    await safe_edit(callback.message, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад в админку", callback_data="back_to_admin")]
    ]))
    await callback.answer()

@dp.callback_query(F.data == "back_to_admin")
async def back_to_admin_handler(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer()
        return
    await state.clear()
    await safe_edit(callback.message, admin_text(callback.from_user.id), reply_markup=get_admin_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "admin_vip_menu")
async def admin_vip_menu(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer()
        return
    await state.set_state(AdminState.waiting_for_vip_user_id)
    await safe_edit(
        callback.message,
        "⭐ <b>Управление VIP статусом</b>\n\n"
        "Отправьте в чат <b>Telegram ID</b> пользователя, которому хотите выдать или снять VIP статус:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="back_to_admin")]
        ])
    )
    await callback.answer()

@dp.message(AdminState.waiting_for_vip_user_id, F.text)
async def process_admin_vip_toggle(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        target_id = int(message.text.strip())
    except ValueError:
        await message.answer("⚠️ Пожалуйста, введите корректный числовой ID пользователя.")
        return   # остаёмся в состоянии — можно ввести ещё раз

    target_user = get_user(target_id)
    if not target_user:
        await message.answer("❌ Пользователь с таким ID не найден в базе данных.")
        return

    new_vip = 0 if target_user[3] == 1 else 1
    set_user_vip(target_id, new_vip)
    if target_id == ADMIN_ID:
        new_vip = 1
    status_str = "🌟 ВИП ВЫДАН" if new_vip == 1 else "👤 ВИП СНЯТ"
    await message.answer(
        f"✅ Успешно! Для пользователя <code>{target_id}</code> статус изменен: <b>{status_str}</b>"
    )
    await state.clear()

@dp.callback_query(F.data == "admin_broadcast")
async def start_broadcast(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer()
        return
    await state.set_state(AdminState.waiting_for_broadcast)
    await safe_edit(
        callback.message,
        "💬 Отправьте сообщение для рассылки всем пользователям:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="back_to_admin")]
        ])
    )
    await callback.answer()

@dp.message(AdminState.waiting_for_broadcast)
async def process_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.clear()   # сразу, чтобы второе сообщение не запустило рассылку повторно
    user_ids = get_all_user_ids()
    success, failed = 0, 0
    status_msg = await message.answer("🚀 Рассылка запущенна...")

    for uid in user_ids:
        try:
            await bot.copy_message(chat_id=uid, from_chat_id=message.chat.id, message_id=message.message_id)
            success += 1
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
            try:
                await bot.copy_message(chat_id=uid, from_chat_id=message.chat.id, message_id=message.message_id)
                success += 1
            except Exception:
                failed += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.04)

    await status_msg.edit_text(
        f"✅ Рассылка завершена!\nУспешно отправлено: <code>{success}</code>\nОшибок: <code>{failed}</code>"
    )

# --- ЗАПУСК ---
async def main():
    # чистим хвосты прошлых запусков
    shutil.rmtree(DOWNLOAD_ROOT, ignore_errors=True)
    os.makedirs(DOWNLOAD_ROOT, exist_ok=True)

    if not shutil.which("ffmpeg"):
        logging.warning("ffmpeg НЕ НАЙДЕН: водяные знаки и MP3 работать не будут!")
    if not ensure_watermark_png():
        logging.warning("Pillow не установлен — водяной знак пойдёт через drawtext (нужен шрифт в системе)")
    if not RENDER_EXTERNAL_URL:
        logging.warning("RENDER_EXTERNAL_URL не задан — автопинг отключён")

    # Веб-сервер + автопинг стартуют ДО поллинга
    runner = await start_web_server()
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        for task in list(BACKGROUND_TASKS):
            task.cancel()
        await runner.cleanup()
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())