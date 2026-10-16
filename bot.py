# -*- coding: utf-8 -*-
"""PulseFetch — Telegram-бот для скачивания медиа (aiogram 3 + yt-dlp + ffmpeg + мультиязычность + профиль)."""
import asyncio
import html
import json
import logging
import os
import re
import shutil
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yt_dlp
from aiohttp import web
from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.enums import ChatType, ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.filters import (ChatMemberUpdatedFilter, CommandObject,
                             CommandStart, JOIN_TRANSITION)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (CallbackQuery, ChatMemberUpdated, FSInputFile,
                           InlineKeyboardButton, InlineKeyboardMarkup,
                           KeyboardButton, LabeledPrice, Message,
                           PreCheckoutQuery, ReplyKeyboardMarkup,
                           ReplyParameters)
from aiogram.utils.chat_action import ChatActionSender

from database import (
    init_db, db_add_user, check_vip_status_expiration,
    db_get_user_info, db_set_user_vip_months, db_get_stats,
    db_get_all_users, get_maintenance_mode, set_maintenance_mode,
    db_get_user_language, db_set_user_language, db_get_user_reg_date
)

# ───────────────────────── КОНФИГ ─────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "8945702554:AAGxV9zRNvf_iX17bh1GzHZLqh_wDap6lvE")
ADMIN_ID = 6444735646
BOT_USERNAME = os.getenv("BOT_USERNAME", "pulsefetch_bot")
COOKIES_FILE = os.getenv("COOKIES_FILE", "cookies.txt")
LOCAL_API_URL = os.getenv("LOCAL_API_URL", "")

TG_CAP_MB = 2000 if LOCAL_API_URL else 50
FREE_LIMIT_MB = min(500, TG_CAP_MB)
VIP_LIMIT_MB = min(2000, TG_CAP_MB)
FREE_HEIGHTS = [720, 480, 360]
VIP_HEIGHTS = [0, 1080, 720, 480, 360]
MAX_PARALLEL = int(os.getenv("MAX_PARALLEL", "3"))
DOWNLOAD_TIMEOUT = 900
FFMPEG_TIMEOUT = 900

GROUPS = {ChatType.GROUP, ChatType.SUPERGROUP}
URL_RE = re.compile(r"https?://[^\s<>\"']+", re.I)
GROUP_HOSTS = (
    "tiktok.com", "youtube.com", "youtu.be", "instagram.com", "instagr.am",
    "twitter.com", "x.com", "facebook.com", "fb.watch", "pinterest.com", "pin.it",
    "vk.com", "vkvideo.ru", "reddit.com", "likee.video", "snapchat.com",
    "twitch.tv", "vimeo.com", "dailymotion.com", "threads.net", "soundcloud.com",
)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/141.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Sec-Fetch-Dest": "document",
}

YT_CLIENTS = ["ios", "mweb", "android", "web_safari", "tv", "web"]
VIDEO_EXT = (".mp4", ".mkv", ".webm", ".mov", ".m4v")
AUDIO_SRC_EXT = (".m4a", ".mp3", ".opus", ".webm", ".ogg", ".aac", ".mp4", ".wav", ".flac")

# ───────────────────────── СЛОВАРИ ПЕРЕВОДОВ (ЯЗЫКИ) ─────────────────────────
LANGS = {
    "ru": {
        "download": "📥 Скачать медиа",
        "profile": "👤 Мой профиль",
        "vip_active": "🌟 VIP Статус (Активен)",
        "vip_buy": "💎 Купить VIP (Без водяного знака)",
        "ref": "🎁 Бесплатный VIP за друзей",
        "restart": "🔄 Перезапустить бота",
        "settings": "⚙️ Настройки",
        "about": "ℹ️ О боте и правилах",
        "admin": "👑 Админ-панель",
        "welcome": "👋 <b>Привет, {name}!</b>\n\nЯ универсальный бот <b>PulseFetch</b> для скачивания медиа.\n\n📌 <b>Твой текущий тариф:</b> {tariff}\n\n👇 Нажми кнопку ниже:",
        "choose_platform": "📂 <b>Шаг 1 из 2:</b> Выбери платформу, с которой хочешь скачать контент:",
        "settings_title": "⚙️ <b>Настройки бота</b>\n\nВыбери язык интерфейса:",
        "lang_changed": "✅ Язык успешно изменен на Русский!",
        "profile_text": "👤 <b>Твой профиль:</b>\n\n🆔 ID: <code>{uid}</code>\n👤 Имя: <b>{name}</b>\n🌟 Тариф: <b>{tariff}</b>\n📅 Дата регистрации: <b>{reg_date}</b>\n\n👥 Приглашено друзей: <b>{refs}</b>\n🎁 Получено бонусов: <b>{claimed} из 3</b>",
    },
    "uk": {
        "download": "📥 Завантажити медіа",
        "profile": "👤 Мій профіль",
        "vip_active": "🌟 VIP Статус (Активний)",
        "vip_buy": "💎 Купити VIP (Без водяного знаку)",
        "ref": "🎁 Безкоштовний VIP за друзів",
        "restart": "🔄 Перезапустити бота",
        "settings": "⚙️ Налаштування",
        "about": "ℹ️ Про бота та правила",
        "admin": "👑 Адмін-панель",
        "welcome": "👋 <b>Привіт, {name}!</b>\n\nЯ універсальний бот <b>PulseFetch</b> для завантаження медіа.\n\n📌 <b>Твій поточний тариф:</b> {tariff}\n\n👇 Натисни кнопку нижче:",
        "choose_platform": "📂 <b>Крок 1 із 2:</b> Вибери платформу для завантаження контенту:",
        "settings_title": "⚙️ <b>Налаштування бота</b>\n\nВибери мову інтерфейсу:",
        "lang_changed": "✅ Мову успішно змінено на Українську!",
        "profile_text": "👤 <b>Твій профіль:</b>\n\n🆔 ID: <code>{uid}</code>\n👤 Ім'я: <b>{name}</b>\n🌟 Тариф: <b>{tariff}</b>\n📅 Дата реєстрації: <b>{reg_date}</b>\n\n👥 Запрошено друзів: <b>{refs}</b>\n🎁 Отримано бонусів: <b>{claimed} з 3</b>",
    },
    "en": {
        "download": "📥 Download Media",
        "profile": "👤 My Profile",
        "vip_active": "🌟 VIP Status (Active)",
        "vip_buy": "💎 Buy VIP (No watermark)",
        "ref": "🎁 Free VIP via Friends",
        "restart": "🔄 Restart Bot",
        "settings": "⚙️ Settings",
        "about": "ℹ️ About & Rules",
        "admin": "👑 Admin Panel",
        "welcome": "👋 <b>Hello, {name}!</b>\n\nI am <b>PulseFetch</b>, your universal media downloader bot.\n\n📌 <b>Current Plan:</b> {tariff}\n\n👇 Click a button below:",
        "choose_platform": "📂 <b>Step 1 of 2:</b> Choose the platform you want to download from:",
        "settings_title": "⚙️ <b>Bot Settings</b>\n\nChoose your interface language:",
        "lang_changed": "✅ Language successfully changed to English!",
        "profile_text": "👤 <b>Your Profile:</b>\n\n🆔 ID: <code>{uid}</code>\n👤 Name: <b>{name}</b>\n🌟 Plan: <b>{tariff}</b>\n📅 Registration Date: <b>{reg_date}</b>\n\n👥 Invited Friends: <b>{refs}</b>\n🎁 Bonuses Claimed: <b>{claimed} of 3</b>",
    },
    "es": {
        "download": "📥 Descargar Medios",
        "profile": "👤 Mi Perfil",
        "vip_active": "🌟 Estado VIP (Activo)",
        "vip_buy": "💎 Comprar VIP (Sin marca de agua)",
        "ref": "🎁 VIP Gratis por Amigos",
        "restart": "🔄 Reiniciar Bot",
        "settings": "⚙️ Ajustes",
        "about": "ℹ️ Acerca de & Reglas",
        "admin": "👑 Panel de Admin",
        "welcome": "👋 <b>¡Hola, {name}!</b>\n\nSoy <b>PulseFetch</b>, tu bot universal para descargar medios.\n\n📌 <b>Plan actual:</b> {tariff}\n\n👇 Elige una opción:",
        "choose_platform": "📂 <b>Paso 1 de 2:</b> Selecciona la plataforma:",
        "settings_title": "⚙️ <b>Ajustes del Bot</b>\n\nSelecciona tu idioma:",
        "lang_changed": "✅ ¡Idioma cambiado a Español!",
        "profile_text": "👤 <b>Tu Perfil:</b>\n\n🆔 ID: <code>{uid}</code>\n👤 Nombre: <b>{name}</b>\n🌟 Plan: <b>{tariff}</b>\n📅 Registro: <b>{reg_date}</b>\n\n👥 Amigos invitados: <b>{refs}</b>\n🎁 Bonos: <b>{claimed} de 3</b>",
    },
    "fr": {
        "download": "📥 Télécharger",
        "profile": "👤 Mon Profil",
        "vip_active": "🌟 Statut VIP (Actif)",
        "vip_buy": "💎 Acheter VIP (Sans filigrane)",
        "ref": "🎁 VIP Gratuit via Amis",
        "restart": "🔄 Redémarrer",
        "settings": "⚙️ Paramètres",
        "about": "ℹ️ À propos & Règles",
        "admin": "👑 Admin",
        "welcome": "👋 <b>Bonjour, {name} !</b>\n\nJe suis <b>PulseFetch</b>.\n\n📌 <b>Offre actuelle :</b> {tariff}\n\n👇 Choisissez :",
        "choose_platform": "📂 <b>Étape 1 sur 2 :</b> Choisissez la plateforme :",
        "settings_title": "⚙️ <b>Paramètres</b>\n\nChoisissez votre langue :",
        "lang_changed": "✅ Langue changée en Français !",
        "profile_text": "👤 <b>Votre Profil :</b>\n\n🆔 ID : <code>{uid}</code>\n👤 Nom : <b>{name}</b>\n🌟 Offre : <b>{tariff}</b>\n📅 Inscription : <b>{reg_date}</b>\n\n👥 Amis : <b>{refs}</b>\n🎁 Bonus : <b>{claimed} sur 3</b>",
    },
    "de": {
        "download": "📥 Medien herunterladen",
        "profile": "👤 Mein Profil",
        "vip_active": "🌟 VIP-Status (Aktiv)",
        "vip_buy": "💎 VIP kaufen (Ohne Wasserzeichen)",
        "ref": "🎁 Gratis VIP für Freunde",
        "restart": "🔄 Bot neu starten",
        "settings": "⚙️ Einstellungen",
        "about": "ℹ️ Über & Regeln",
        "admin": "👑 Admin-Bereich",
        "welcome": "👋 <b>Hallo, {name}!</b>\n\nIch bin <b>PulseFetch</b>.\n\n📌 <b>Aktueller Tarif:</b> {tariff}\n\n👇 Wähle eine Option:",
        "choose_platform": "📂 <b>Schritt 1 von 2:</b> Plattform wählen:",
        "settings_title": "⚙️ <b>Einstellungen</b>\n\nSprache auswählen:",
        "lang_changed": "✅ Sprache erfolgreich auf Deutsch geändert!",
        "profile_text": "👤 <b>Dein Profil:</b>\n\n🆔 ID: <code>{uid}</code>\n👤 Name: <b>{name}</b>\n🌟 Tarif: <b>{tariff}</b>\n📅 Registriert am: <b>{reg_date}</b>\n\n👥 Eingeladen: <b>{refs}</b>\n🎁 Boni: <b>{claimed} von 3</b>",
    },
    "pl": {
        "download": "📥 Pobierz media",
        "profile": "👤 Mój profil",
        "vip_active": "🌟 Status VIP (Aktywny)",
        "vip_buy": "💎 Kup VIP (Bez znaku wodnego)",
        "ref": "🎁 Darmowy VIP za znajomych",
        "restart": "🔄 Restartuj bota",
        "settings": "⚙️ Ustawienia",
        "about": "ℹ️ O bocie i zasadach",
        "admin": "👑 Panel admina",
        "welcome": "👋 <b>Cześć, {name}!</b>\n\nJestem <b>PulseFetch</b>.\n\n📌 <b>Twój plan:</b> {tariff}\n\n👇 Wybierz opcję:",
        "choose_platform": "📂 <b>Krok 1 z 2:</b> Wybierz platformę:",
        "settings_title": "⚙️ <b>Ustawienia</b>\n\nWybierz język:",
        "lang_changed": "✅ Język zmieniony na Polski!",
        "profile_text": "👤 <b>Twój profil:</b>\n\n🆔 ID: <code>{uid}</code>\n👤 Imię: <b>{name}</b>\n🌟 Plan: <b>{tariff}</b>\n📅 Data rejestracji: <b>{reg_date}</b>\n\n👥 Znajomi: <b>{refs}</b>\n🎁 Bonusy: <b>{claimed} z 3</b>",
    },
    "it": {
        "download": "📥 Scarica Media",
        "profile": "👤 Il mio profilo",
        "vip_active": "🌟 Stato VIP (Attivo)",
        "vip_buy": "💎 Acquista VIP (Senza filigrana)",
        "ref": "🎁 VIP Gratis con amici",
        "restart": "🔄 Riavvia Bot",
        "settings": "⚙️ Impostazioni",
        "about": "ℹ️ Info e Regole",
        "admin": "👑 Pannello Admin",
        "welcome": "👋 <b>Ciao, {name}!</b>\n\nSono <b>PulseFetch</b>.\n\n📌 <b>Piano attuale:</b> {tariff}\n\n👇 Scegli un'opzione:",
        "choose_platform": "📂 <b>Passo 1 di 2:</b> Scegli la piattaforma:",
        "settings_title": "⚙️ <b>Impostazioni</b>\n\nScegli la lingua:",
        "lang_changed": "✅ Lingua cambiata in Italiano!",
        "profile_text": "👤 <b>Il tuo profilo:</b>\n\n🆔 ID: <code>{uid}</code>\n👤 Nome: <b>{name}</b>\n🌟 Piano: <b>{tariff}</b>\n📅 Registrazione: <b>{reg_date}</b>\n\n👥 Amici: <b>{refs}</b>\n🎁 Bonus: <b>{claimed} su 3</b>",
    },
    "tr": {
        "download": "📥 Medya İndir",
        "profile": "👤 Profilim",
        "vip_active": "🌟 VIP Durumu (Aktif)",
        "vip_buy": "💎 VIP Satın Al (Filigransız)",
        "ref": "🎁 Arkadaşını Getir VIP Kazan",
        "restart": "🔄 Botu Yeniden Başlat",
        "settings": "⚙️ Ayarlar",
        "about": "ℹ️ Hakkında ve Kurallar",
        "admin": "👑 Yönetici Paneli",
        "welcome": "👋 <b>Merhaba, {name}!</b>\n\nBen <b>PulseFetch</b>.\n\n📌 <b>Mevcut Planın:</b> {tariff}\n\n👇 Seçim yap:",
        "choose_platform": "📂 <b>Adım 1 / 2:</b> Platform seçin:",
        "settings_title": "⚙️ <b>Ayarlar</b>\n\nDil seçin:",
        "lang_changed": "✅ Dil Türkçe olarak değiştirildi!",
        "profile_text": "👤 <b>Profilin:</b>\n\n🆔 ID: <code>{uid}</code>\n👤 İsim: <b>{name}</b>\n🌟 Plan: <b>{tariff}</b>\n📅 Kayıt Tarihi: <b>{reg_date}</b>\n\n👥 Davet edilen: <b>{refs}</b>\n🎁 Bonuslar: <b>{claimed} / 3</b>",
    },
    "zh": {
        "download": "📥 下载媒体",
        "profile": "👤 我的个人资料",
        "vip_active": "🌟 VIP 状态 (已激活)",
        "vip_buy": "💎 购买 VIP (无水印)",
        "ref": "🎁 邀请好友得 VIP",
        "restart": "🔄 重启机器人",
        "settings": "⚙️ 设置",
        "about": "ℹ️ 关于与规则",
        "admin": "👑 管理面板",
        "welcome": "👋 <b>你好，{name}！</b>\n\n我是 <b>PulseFetch</b>。\n\n📌 <b>当前套餐：</b> {tariff}\n\n👇 请选择：",
        "choose_platform": "📂 <b>第 1 步 (共 2 步)：</b> 选择平台：",
        "settings_title": "⚙️ <b>设置</b>\n\n选择语言：",
        "lang_changed": "✅ 语言已成功更改为中文！",
        "profile_text": "👤 <b>你的个人资料：</b>\n\n🆔 ID: <code>{uid}</code>\n👤 名字: <b>{name}</b>\n🌟 套餐: <b>{tariff}</b>\n📅 注册时间: <b>{reg_date}</b>\n\n👥 邀请好友: <b>{refs}</b>\n🎁 获得奖励: <b>{claimed} / 3</b>",
    }
}

def t(user_id: int, key: str, **kwargs) -> str:
    lang = db_get_user_language(user_id) or "ru"
    if lang not in LANGS:
        lang = "ru"
    text = LANGS[lang].get(key, LANGS["ru"].get(key, key))
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
log = logging.getLogger("pulsefetch")

DL_SEM = asyncio.Semaphore(MAX_PARALLEL)
IN_FLIGHT: set = set()
BG_TASKS: set = set()
_last_action: dict = {}

def fmt_limit(mb: int) -> str:
    return f"{mb // 1000} ГБ" if mb >= 1000 else f"{mb} МБ"

def esc(s) -> str:
    return html.escape(str(s or ""))

async def quiet(coro):
    try:
        return await coro
    except Exception:
        return None

def cooldown(uid: int, sec: float) -> bool:
    now = time.monotonic()
    if len(_last_action) > 5000:
        for k in [k for k, v in _last_action.items() if now - v > 60]:
            _last_action.pop(k, None)
    if now - _last_action.get(uid, 0) < sec:
        return False
    _last_action[uid] = now
    return True

def extract_urls(message: Message) -> list:
    text = message.text or message.caption or ""
    entities = message.entities or message.caption_entities or []
    found = []
    for e in entities:
        if e.type == "url":
            found.append(e.extract_from(text))
        elif e.type == "text_link" and e.url:
            found.append(e.url)
    found += URL_RE.findall(text)
    out, seen = [], set()
    for u in found:
        u = u.strip().rstrip(".,;:!?)»]}>\"'")
        if u.lower().startswith(("http://", "https://")) and u not in seen:
            seen.add(u)
            out.append(u)
    return out

def host_supported(url: str) -> bool:
    m = re.match(r"https?://([^/:?#]+)", url, re.I)
    if not m:
        return False
    host = m.group(1).lower()
    return any(host == h or host.endswith("." + h) for h in GROUP_HOSTS)

def all_user_ids() -> list:
    ids = []
    for r in db_get_all_users() or []:
        try:
            ids.append(int(r[0]) if isinstance(r, (tuple, list)) else int(r))
        except (TypeError, ValueError, IndexError):
            continue
    return ids

def get_vip(user_id: int) -> bool:
    try:
        return bool(check_vip_status_expiration(user_id, ADMIN_ID))
    except Exception:
        log.exception("check_vip_status_expiration")
        return False

async def safe_exit(msg, text: str, markup=None):
    try:
        await msg.edit_text(text, reply_markup=markup)
    except TelegramBadRequest:
        pass
    except Exception:
        log.exception("safe_edit")
class MediaError(Exception):
    pass

class DownloadCancelled(Exception):
    pass

@dataclass
class Result:
    tmpdir: Path
    title: str = "Media"
    video: Optional[Path] = None
    audio: Optional[Path] = None
    width: int = 0
    height: int = 0
    duration: int = 0

def build_format(h: int) -> str:
    if h == 0:
        return "bv*[vcodec^=avc1]+ba[acodec^=mp4a]/bv*[ext=mp4]+ba[ext=m4a]/bv*+ba/b"
    f = f"[height<=?{h}]"
    return (f"bv*{f}[vcodec^=avc1]+ba[acodec^=mp4a]/bv*{f}[ext=mp4]+ba[ext=m4a]/"
            f"b{f}[ext=mp4]/bv*{f}+ba/b{f}")

def _ydl_opts(
    tmp: Path,
    fmt: str,
    cancel: threading.Event,
    use_clients: bool,
    limit: int,
    *,
    use_cookies: bool = True,
    extra_headers: dict | None = None,
    impersonate: bool | str = False,
) -> dict:
    def hook(_d):
        if cancel.is_set():
            raise DownloadCancelled()

    headers = dict(HEADERS)
    if extra_headers:
        headers.update(extra_headers)

    opts = {
        "format": fmt,
        "outtmpl": str(tmp / "%(id).60B.%(ext)s"),
        "merge_output_format": "mp4",
        "noplaylist": True,
        "playlist_items": "1",
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "restrictfilenames": True,
        "retries": 8,
        "fragment_retries": 8,
        "extractor_retries": 5,
        "file_access_retries": 3,
        "socket_timeout": 30,
        "concurrent_fragment_downloads": 4,
        "geo_bypass": True,
        "http_headers": headers,
        "progress_hooks": [hook],
        "max_filesize": limit,
        "overwrites": True,
        "legacy_server_connect": True,
    }

    if use_clients:
        opts["extractor_args"] = {
            "youtube": {
                "player_client": YT_CLIENTS,
                "player_skip": ["configs"],
            }
        }

    if use_cookies:
        if COOKIES_FILE and Path(COOKIES_FILE).is_file():
            opts["cookiefile"] = COOKIES_FILE
        elif Path("cookies.txt").is_file():
            opts["cookiefile"] = "cookies.txt"

    if impersonate:
        opts["impersonate"] = impersonate

    return opts

def _download_sync(url: str, tmp: Path, fmt: str, cancel: threading.Event, limit: int):
    last_err: Optional[Exception] = None
    low = url.lower()

    clean_url = url.split('?')[0].split('&')[0]
    if "youtube.com" in low or "youtu.be" in low:
        url = clean_url

    is_tiktok = any(h in low for h in ("tiktok.com", "vt.tiktok.com", "vm.tiktok.com"))
    is_youtube = any(h in low for h in ("youtube.com", "youtu.be"))
    is_instagram = any(h in low for h in ("instagram.com", "instagr.am"))

    if is_youtube:
        strategies = [
            {"use_clients": True,  "use_cookies": True,  "impersonate": False, "clients": ["android", "ios", "mweb"]},
            {"use_clients": True,  "use_cookies": True,  "impersonate": False, "clients": ["ios", "android"]},
            {"use_clients": True,  "use_cookies": False, "impersonate": False, "clients": ["android", "ios"]},
            {"use_clients": True,  "use_cookies": True,  "impersonate": False, "clients": ["web_safari", "tv"]},
            {"use_clients": False, "use_cookies": True,  "impersonate": False, "clients": None},
            {"use_clients": False, "use_cookies": False, "impersonate": False, "clients": None},
        ]
    elif is_tiktok or is_instagram:
        strategies = [
            {"use_clients": False, "use_cookies": True,  "impersonate": "chrome", "clients": None},
            {"use_clients": False, "use_cookies": False, "impersonate": "chrome", "clients": None},
            {"use_clients": False, "use_cookies": True,  "impersonate": False, "clients": None},
            {"use_clients": False, "use_cookies": False, "impersonate": False, "clients": None},
        ]
    else:
        strategies = [
            {"use_clients": False, "use_cookies": True,  "impersonate": "chrome", "clients": None},
            {"use_clients": False, "use_cookies": False, "impersonate": "chrome", "clients": None},
        ]

    extra_headers = None
    if is_tiktok:
        extra_headers = {
            "Referer": "https://www.tiktok.com/",
            "Origin": "https://www.tiktok.com",
        }
    elif is_instagram:
        extra_headers = {
            "Referer": "https://www.instagram.com/",
            "Origin": "https://www.instagram.com",
        }

    for strat in strategies:
        original_clients = YT_CLIENTS[:]
        try:
            if strat.get("clients"):
                globals()["YT_CLIENTS"] = strat["clients"]

            opts = _ydl_opts(
                tmp, fmt, cancel,
                use_clients=strat["use_clients"],
                limit=limit,
                use_cookies=strat["use_cookies"],
                extra_headers=extra_headers,
                impersonate=strat["impersonate"],
            )
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)

            globals()["YT_CLIENTS"] = original_clients

            if info and "entries" in info:
                entries = [e for e in (info.get("entries") or []) if e]
                info = entries[0] if entries else None
            return info

        except DownloadCancelled:
            raise
        except Exception as e:
            last_err = e
            globals()["YT_CLIENTS"] = original_clients
            log.warning(
                "yt-dlp failed (clients=%s cookies=%s impersonate=%s): %s",
                strat.get("clients") or strat["use_clients"],
                strat["use_cookies"],
                strat["impersonate"],
                str(e)[:300],
            )
            _clear(tmp)

    raise MediaError(str(last_err) if last_err else "download failed")

def _find_file(tmp: Path, exts: tuple) -> Optional[Path]:
    files = [p for p in tmp.iterdir()
             if p.is_file() and p.suffix.lower() in exts
             and not p.name.endswith((".part", ".ytdl")) and p.stat().st_size > 0]
    return max(files, key=lambda p: p.stat().st_size) if files else None

async def _run(*cmd, timeout: int):
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise MediaError("ffmpeg: таймаут")
    return proc.returncode, out, err

async def _probe(path: Path) -> Optional[dict]:
    try:
        rc, out, _ = await _run("ffprobe", "-v", "error", "-print_format", "json",
                                "-show_streams", "-show_format", str(path), timeout=60)
        if rc != 0:
            return None
        data = json.loads(out.decode() or "{}")
    except (MediaError, ValueError, FileNotFoundError):
        return None
    v = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    a = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
    if not v:
        return None
    try:
        dur = int(float(data.get("format", {}).get("duration") or v.get("duration") or 0))
    except ValueError:
        dur = 0
    return {"vcodec": v.get("codec_name"), "acodec": a.get("codec_name") if a else None,
            "w": int(v.get("width") or 0), "h": int(v.get("height") or 0), "dur": dur}

async def _normalize(src: Path, tmp: Path, max_h: int, add_watermark: bool = False) -> Path:
    info = await _probe(src)
    if not info:
        raise MediaError("в файле нет видеопотока")
    out = tmp / "final.mp4"
    need_scale = bool(max_h) and info["h"] > max_h

    vf_parts = []
    if need_scale:
        vf_parts.append(f"scale=-2:{max_h}")
    else:
        vf_parts.append("scale=trunc(iw/2)*2:trunc(ih/2)*2")

    if add_watermark:
        watermark_text = f"Скачано через @{BOT_USERNAME}"
        drawtext = (
            f"drawtext=text='{watermark_text}':"
            f"fontsize=18:fontcolor=white:"
            f"x=(w-text_w)/2:y=(h-text_h)/2:"
            f"box=1:boxcolor=black@0.4:boxborderw=6"
        )
        vf_parts.append(drawtext)

    vf = ",".join(vf_parts)

    if (info["vcodec"] == "h264" and info["acodec"] in (None, "aac")
            and not need_scale and not add_watermark):
        rc, _, _ = await _run("ffmpeg", "-y", "-v", "error", "-i", str(src), "-c", "copy",
                              "-movflags", "+faststart", str(out), timeout=FFMPEG_TIMEOUT)
        if rc == 0 and out.exists() and out.stat().st_size > 0:
            if src != out:
                src.unlink(missing_ok=True)
            return out

    rc, _, err = await _run(
        "ffmpeg", "-y", "-v", "error", "-i", str(src),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(out),
        timeout=FFMPEG_TIMEOUT
    )
    if rc != 0 or not out.exists() or out.stat().st_size == 0:
        raise MediaError("ffmpeg: " + err.decode(errors="ignore")[-200:])

    if src != out:
        src.unlink(missing_ok=True)
    return out

async def _to_mp3(src: Path, tmp: Path, limit: int) -> Path:
    for br in (192, 128, 64):
        out = tmp / f"audio_{br}.mp3"
        rc, _, err = await _run("ffmpeg", "-y", "-v", "error", "-i", str(src), "-vn",
                                "-c:a", "libmp3lame", "-b:a", f"{br}k", str(out),
                                timeout=FFMPEG_TIMEOUT)
        if rc != 0 or not out.exists() or out.stat().st_size == 0:
            raise MediaError("ffmpeg: не удалось получить аудио")
        if out.stat().st_size <= limit:
            return out
    raise MediaError("слишком большой файл")

def _clear(tmp: Path):
    for f in tmp.iterdir():
        if f.is_file():
            f.unlink(missing_ok=True)

def _retryable(e: Exception) -> bool:
    s = str(e).lower()
    return any(k in s for k in ("requested format", "ffmpeg", "слишком большой", "нет видеопотока"))

async def _dl(url: str, tmp: Path, fmt: str, cancel: threading.Event, limit: int):
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_download_sync, url, tmp, fmt, cancel, limit), DOWNLOAD_TIMEOUT)
    except asyncio.TimeoutError:
        cancel.set()
        raise MediaError("таймаут загрузки")

async def fetch_media(url: str, heights: list, want_video: bool, want_audio: bool,
                      limit: int, add_watermark: bool = False) -> Result:
    tmp = Path(await asyncio.to_thread(tempfile.mkdtemp, prefix="pf_"))
    res = Result(tmpdir=tmp)
    cancel = threading.Event()
    try:
        if want_video:
            last_err: Optional[Exception] = None
            for h in heights:
                _clear(tmp)
                try:
                    info = await _dl(url, tmp, build_format(h), cancel, limit)
                    src = _find_file(tmp, VIDEO_EXT)
                    if not src:
                        raise MediaError("слишком большой файл")
                    final = await _normalize(src, tmp, h, add_watermark=add_watermark)
                    size = final.stat().st_size
                    if size <= 0:
                        raise MediaError("пустой файл")
                    if size > limit:
                        raise MediaError("слишком большой файл")
                except MediaError as e:
                    last_err = e
                    if not _retryable(e):
                        raise
                    continue
                meta = await _probe(final) or {"w": 0, "h": 0, "dur": 0}
                res.video, res.title = final, (info or {}).get("title") or "Media"
                res.width, res.height, res.duration = meta["w"], meta["h"], meta["dur"]
                break
            if not res.video:
                raise last_err or MediaError("не удалось скачать")
            if want_audio:
                try:
                    res.audio = await _to_mp3(res.video, tmp, limit)
                except MediaError as e:
                    log.warning("audio from video failed: %s", e)
        else:
            info = await _dl(url, tmp, "ba/b", cancel, limit)
            src = _find_file(tmp, AUDIO_SRC_EXT)
            if not src:
                raise MediaError("слишком большой файл")
            res.title = (info or {}).get("title") or "Audio"
            res.audio = await _to_mp3(src, tmp, limit)
        return res
    except BaseException:
        shutil.rmtree(res.tmpdir, ignore_errors=True)
        raise

def friendly_error(e: Exception, limit_mb: int) -> str:
    s = str(e).lower()
    if "слишком большой" in s:
        return f"📦 Файл слишком большой для отправки (лимит {fmt_limit(limit_mb)})."
    if any(k in s for k in ("private", "login", "sign in", "cookies", "age", "authentication")):
        return "🔒 Видео приватное, с ограничением по возрасту или требует входа в аккаунт."
    if any(k in s for k in ("unsupported url", "no video")):
        return "🤷 В этой ссылке не нашлось медиа."
    if any(k in s for k in ("not available", "removed", "unavailable")):
        return "🚫 Медиа недоступно или удалено."
    if "таймаут" in s or "timed out" in s:
        return "⏱ Сервер долго не отвечает. Попробуйте позже."
    return "❌ Не удалось скачать медиа. Проверьте ссылку или попробуйте позже."

async def _retry_send(factory):
    for _ in range(3):
        try:
            return await factory()
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
    raise MediaError("не удалось отправить файл")

async def send_video_file(bot: Bot, chat_id: int, res: Result, caption: str,
                          reply_to: Optional[int], markup):
    rp = ReplyParameters(message_id=reply_to, allow_sending_without_reply=True) if reply_to else None

    async def as_video():
        return await bot.send_video(chat_id, FSInputFile(res.video), caption=caption,
                                    width=res.width or None, height=res.height or None,
                                    duration=res.duration or None, supports_streaming=True,
                                    reply_markup=markup, reply_parameters=rp)

    async def as_doc():
        return await bot.send_document(chat_id, FSInputFile(res.video), caption=caption,
                                       reply_markup=markup, reply_parameters=rp)
    try:
        await _retry_send(as_video)
    except TelegramBadRequest as e:
        log.warning("send_video failed (%s) -> document", e)
        await _retry_send(as_doc)

async def send_audio_file(bot: Bot, chat_id: int, res: Result, caption: str,
                          reply_to: Optional[int], markup):
    rp = ReplyParameters(message_id=reply_to, allow_sending_without_reply=True) if reply_to else None
    await _retry_send(lambda: bot.send_audio(chat_id, FSInputFile(res.audio), caption=caption,
                                             title=res.title[:60], reply_markup=markup,
                                             reply_parameters=rp))

async def job(bot: Bot, chat_id: int, user_id: int, url: str, action: str, is_vip: bool, *,
              reply_to: Optional[int] = None, markup=None, silent: bool = False,
              status: Optional[Message] = None) -> bool:
    key = (chat_id, url, action)
    if key in IN_FLIGHT:
        if not silent:
            await quiet(bot.send_message(chat_id, "⏳ Эта ссылка уже обрабатывается, подожди немного."))
        return False
    IN_FLIGHT.add(key)
    res: Optional[Result] = None
    limit_mb = VIP_LIMIT_MB if is_vip else FREE_LIMIT_MB
    tail = f"\n📥 Скачано через @{BOT_USERNAME}"
    try:
        async with DL_SEM:
            async with ChatActionSender.upload_video(bot=bot, chat_id=chat_id):
                add_wm = not is_vip
                res = await fetch_media(
                    url, VIP_HEIGHTS if is_vip else FREE_HEIGHTS,
                    action in ("video", "both"), action in ("audio", "both"),
                    limit_mb * 1024 * 1024,
                    add_watermark=add_wm
                )
                q = f" {res.height}p" if res.height else ""
                if res.video:
                    cap = f"🌟 <b>VIP Видео{q}</b>" if is_vip else f"🎥 <b>Видео{q}</b>{tail}"
                    await send_video_file(bot, chat_id, res, cap, reply_to,
                                          markup if not res.audio else None)
                if res.audio:
                    cap = "🎵 <b>VIP Аудиодорожка</b>" if is_vip else f"🎵 <b>Аудиодорожка</b>{tail}"
                    await send_audio_file(bot, chat_id, res, cap,
                                          reply_to if not res.video else None, markup)
        return True
    except Exception as e:
        log.warning("job failed [%s]: %s", url, str(e)[:300])
        if not silent:
            await quiet(bot.send_message(chat_id, friendly_error(e, limit_mb), reply_markup=markup))
        return False
    finally:
        IN_FLIGHT.discard(key)
        if res:
            shutil.rmtree(res.tmpdir, ignore_errors=True)
        if status:
            await quiet(status.delete())
def get_vip_comparison_text() -> str:
    return (
        "⚡️ <b>СРАВНЕНИЕ ТАРИФОВ И ВОЗМОЖНОСТЕЙ</b>\n\n"
        "👤 <b>Обычный тариф (Бесплатно):</b>\n"
        f"• 📁 Максимальный размер файла: <b>до {fmt_limit(FREE_LIMIT_MB)}</b>\n"
        "• 🎬 Качество видео: <b>до 720p</b>\n"
        "• 🏷 Водяной знак бота: <b>есть</b>\n\n"
        "🌟 <b>VIP Подписка:</b>\n"
        f"• 📁 Максимальный размер файла: <b>до {fmt_limit(VIP_LIMIT_MB)}</b>\n"
        "• 🎬 Качество видео: <b>максимальное (1080p и выше)</b>\n"
        "• 🎵 Выгрузка аудиодорожек (MP3)\n"
        "• 🏷 Водяной знак бота: <b>отсутствует</b>\n\n"
        "💡 <i>Купи VIP за Stars или получи 24 часа бесплатно за 3 друзей!</i>"
    )

def get_main_keyboard(user_id: int, is_vip: bool) -> ReplyKeyboardMarkup:
    vip_label = t(user_id, "vip_active") if is_vip else t(user_id, "vip_buy")
    rows = [
        [KeyboardButton(text=t(user_id, "download")), KeyboardButton(text=t(user_id, "profile"))],
        [KeyboardButton(text=vip_label)],
        [KeyboardButton(text=t(user_id, "ref")), KeyboardButton(text=t(user_id, "restart"))],
        [KeyboardButton(text=t(user_id, "settings")), KeyboardButton(text=t(user_id, "about"))],
    ]
    if user_id == ADMIN_ID:
        rows.insert(0, [KeyboardButton(text=t(user_id, "admin"))])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

def get_admin_panel_keyboard() -> ReplyKeyboardMarkup:
    maint_text = ("🟢 Выключить тех. работы" if get_maintenance_mode() == "on"
                  else "🔴 Включить тех. работы")
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📊 Статистика бота")],
        [KeyboardButton(text=maint_text)],
        [KeyboardButton(text="📢 Сделать рассылку")],
        [KeyboardButton(text="⬅️ Выйти из админки")],
    ], resize_keyboard=True)

def get_restart_inline_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Главное меню / Перезапуск", callback_data="restart_bot")]])

def get_platforms_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎵 TikTok", callback_data="platform_tiktok"),
         InlineKeyboardButton(text="📺 YouTube / Shorts", callback_data="platform_youtube")],
        [InlineKeyboardButton(text="📸 Instagram Reels", callback_data="platform_insta")],
        [InlineKeyboardButton(text="🌐 Другие платформы", callback_data="platform_other")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_action")],
    ])

def get_languages_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru"), InlineKeyboardButton(text="🇺🇦 Українська", callback_data="lang_uk")],
        [InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en"), InlineKeyboardButton(text="🇪🇸 Español", callback_data="lang_es")],
        [InlineKeyboardButton(text="🇫🇷 Français", callback_data="lang_fr"), InlineKeyboardButton(text="🇩🇪 Deutsch", callback_data="lang_de")],
        [InlineKeyboardButton(text="🇵🇱 Polski", callback_data="lang_pl"), InlineKeyboardButton(text="🇮🇹 Italiano", callback_data="lang_it")],
        [InlineKeyboardButton(text="🇹🇷 Türkçe", callback_data="lang_tr"), InlineKeyboardButton(text="🇨🇳 中文", callback_data="lang_zh")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="restart_bot")]
    ])

MAINT_TEXT = "🛠 В боте проводятся технические работы. Скоро вернемся!"

class DownloadStates(StatesGroup):
    waiting_for_link = State()
    waiting_for_format = State()

class AdminStates(StatesGroup):
    waiting_for_broadcast = State()

class MaintenanceMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        if get_maintenance_mode() == "on" and (not user or user.id != ADMIN_ID):
            chat = data.get("event_chat")
            if chat and chat.type == ChatType.PRIVATE:
                if isinstance(event, CallbackQuery):
                    await quiet(event.answer(MAINT_TEXT, show_alert=True))
                elif isinstance(event, Message):
                    await quiet(event.answer(MAINT_TEXT))
            return None
        return await handler(event, data)

pay_router = Router(name="pay")

@pay_router.pre_checkout_query()
async def pre_checkout(q: PreCheckoutQuery):
    await q.answer(ok=True)

private_router = Router(name="private")
private_router.message.filter(F.chat.type == ChatType.PRIVATE)
private_router.callback_query.filter(F.message.chat.type == ChatType.PRIVATE)

@private_router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, state: FSMContext, bot: Bot):
    await state.clear()
    uid = message.from_user.id
    referrer_id = None
    arg = (command.args or "").strip()
    if arg.startswith("ref_") and arg[4:].isdigit():
        referrer_id = int(arg[4:])
        if referrer_id == uid:
            referrer_id = None

    is_new = uid not in set(all_user_ids())
    db_add_user(uid, message.from_user.username, message.from_user.first_name, referrer_id)

    if referrer_id and is_new:
        await quiet(bot.send_message(
            referrer_id, "🎉 По твоей ссылке перешел новый друг! Пригласи еще для получения 24 часов VIP."))

    is_vip = get_vip(uid)
    tariff = "🌟 VIP" if is_vip else "👤 Обычный (Free)"
    welcome_text = t(uid, "welcome", name=esc(message.from_user.first_name), tariff=tariff)
    await message.answer(welcome_text, reply_markup=get_main_keyboard(uid, is_vip))

@private_router.message(F.text.in_({"🔄 Перезапустить бота", "🔄 Restart Bot", "🔄 Рестарт", "🔄 Перезапустити бота"}))
async def restart_button_handler(message: Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    await message.answer(
        "🔄 Главное меню:",
        reply_markup=get_main_keyboard(uid, get_vip(uid)))

@private_router.callback_query(F.data == "restart_bot")
async def callback_restart(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    uid = callback.from_user.id
    await callback.answer("🔄")
    await safe_exit(callback.message, "⚡️ Главное меню PulseFetch:", get_main_keyboard(uid, get_vip(uid)))

@private_router.message(F.text.in_({"⚙️ Настройки", "⚙️ Settings", "⚙️ Налаштування", "⚙️ Ajustes", "⚙️ Paramètres", "⚙️ Einstellungen", "⚙️ Ustawienia", "⚙️ Impostazioni", "⚙️ Ayarlar", "⚙️ 设置"}))
async def settings_handler(message: Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    await message.answer(t(uid, "settings_title"), reply_markup=get_languages_keyboard())

@private_router.callback_query(F.data.startswith("lang_"))
async def set_language_callback(callback: CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    lang_code = callback.data.replace("lang_", "")
    db_set_user_language(uid, lang_code)
    await callback.answer(t(uid, "lang_changed"), show_alert=True)
    await safe_exit(callback.message, "⚡️ Главное меню:", get_main_keyboard(uid, get_vip(uid)))

@private_router.message(F.text.in_({"👤 Мой профиль", "👤 My Profile", "👤 Мій профіль", "👤 Mi Perfil", "👤 Mon Profil", "👤 Mein Profil", "👤 Mój profil", "👤 Il mio profilo", "👤 Profilim", "👤 我的个人资料"}))
async def profile_handler(message: Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    is_vip = get_vip(uid)
    tariff = "🌟 VIP" if is_vip else "👤 Обычный (Free)"
    reg_date = db_get_user_reg_date(uid) or "Неизвестно"
    refs, claimed = db_get_user_info(uid)
    
    text = t(uid, "profile_text", uid=uid, name=esc(message.from_user.first_name), tariff=tariff, reg_date=reg_date, refs=refs, claimed=claimed)
    await message.answer(text, reply_markup=get_restart_inline_keyboard(uid))
@private_router.message(F.text.in_({"ℹ️ О боте и правилах", "ℹ️ About & Rules", "ℹ️ Про бота та правила"}))
async def about_bot_handler(message: Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    await message.answer(
        "🤖 <b>О боте PulseFetch:</b>\n\n"
        "Бот создан для удобной и быстрой загрузки медиа из TikTok, YouTube, Instagram Reels и других платформ.\n\n"
        f"{get_vip_comparison_text()}\n\n"
        "⚡️ Нажми кнопку ниже, чтобы вернуться в главное меню:",
        reply_markup=get_restart_inline_keyboard(uid))

@private_router.message(F.text.in_({"👑 Админ-панель", "👑 Admin Panel", "👑 Адмін-панель"}))
async def open_admin_panel(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.clear()
    await message.answer("👑 <b>Панель администратора открыта:</b>", reply_markup=get_admin_panel_keyboard())

@private_router.message(F.text == "⬅️ Выйти из админки", F.from_user.id == ADMIN_ID)
async def exit_admin_panel(message: Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    await message.answer("Выход из админ-панели.", reply_markup=get_main_keyboard(uid, get_vip(uid)))

@private_router.message(F.text == "📊 Статистика бота", F.from_user.id == ADMIN_ID)
async def admin_stats(message: Message, state: FSMContext):
    await state.clear()
    total, vips = db_get_stats()
    maint = "Включены 🔴" if get_maintenance_mode() == "on" else "Выключены 🟢"
    await message.answer(f"📊 <b>Статистика:</b>\n👥 Всего пользователей: <code>{total}</code>\n"
                         f"🌟 VIP пользователей: <code>{vips}</code>\n🛠 Тех. работы: {maint}")

@private_router.message(F.text.in_({"🟢 Выключить тех. работы", "🔴 Включить тех. работы"}),
                        F.from_user.id == ADMIN_ID)
async def admin_toggle_maint(message: Message, state: FSMContext):
    await state.clear()
    set_maintenance_mode("off" if get_maintenance_mode() == "on" else "on")
    await message.answer("Состояние тех. работ изменено.", reply_markup=get_admin_panel_keyboard())

@private_router.message(F.text == "📢 Сделать рассылку", F.from_user.id == ADMIN_ID)
async def admin_broadcast(message: Message, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_broadcast)
    await message.answer("✍️ Отправь сообщение для рассылки всем пользователям.")

async def run_broadcast(bot: Bot, src_chat: int, src_msg: int):
    ids = all_user_ids()
    ok = 0
    for uid in ids:
        for _ in range(2):
            try:
                await bot.copy_message(uid, src_chat, src_msg)
                ok += 1
                break
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after + 1)
            except Exception:
                break
        await asyncio.sleep(0.05)
    await quiet(bot.send_message(ADMIN_ID, f"✅ Рассылка завершена. Успешно доставлено: {ok}/{len(ids)}"))

@private_router.message(F.text.in_({"📥 Скачать медиа", "📥 Download Media", "📥 Завантажити медіа"}))
async def choose_platform_menu(message: Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    await message.answer(t(uid, "choose_platform"), reply_markup=get_platforms_keyboard(uid))

@private_router.callback_query(F.data == "back_to_platforms")
async def back_to_platforms(callback: CallbackQuery):
    await callback.answer()
    uid = callback.from_user.id
    await safe_exit(callback.message, t(uid, "choose_platform"), get_platforms_keyboard(uid))

@private_router.callback_query(F.data.startswith("platform_"))
async def process_platform_choice(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    code = callback.data.replace("platform_", "")
    names = {
        "tiktok": "TikTok", "youtube": "YouTube / Shorts", "insta": "Instagram Reels",
        "other": "Другие платформы (Facebook, Pinterest, X/Twitter, SoundCloud и др.)",
    }
    name = names.get(code, "Медиа")
    await state.update_data(platform=code)
    await state.set_state(DownloadStates.waiting_for_link)
    if code == "other":
        hint = (f"🌐 Выбрана категория: <b>{name}</b>.\n\n"
                "📌 <b>Поддерживаются:</b> Facebook, Pinterest, X (Twitter), SoundCloud, Twitch.\n\n🔗 Отправь ссылку:")
    else:
        hint = (f"🔗 Выбрана платформа: <b>{name}</b>.\n\nОтправь ссылку в чат:")
    await safe_exit(callback.message, hint, InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_platforms")]]))

@private_router.message(DownloadStates.waiting_for_link, F.text)
async def process_link_received(message: Message, state: FSMContext):
    urls = extract_urls(message)
    if not urls:
        await message.answer("❌ Это не похоже на ссылку. Пожалуйста, отправь корректную ссылку:")
        return
    url = urls[0]
    platform = (await state.get_data()).get("platform")
    low = url.lower()
    is_tt = "tiktok.com" in low
    is_yt = "youtube.com" in low or "youtu.be" in low
    is_ig = "instagram.com" in low or "instagr.am" in low

    if platform == "tiktok" and not is_tt:
        await message.answer("❌ Ошибка! Ссылка не принадлежит TikTok.")
        return
    if platform == "youtube" and not is_yt:
        await message.answer("❌ Ошибка! Ссылка не принадлежит YouTube.")
        return
    if platform == "insta" and not is_ig:
        await message.answer("❌ Ошибка! Ссылка не принадлежит Instagram.")
        return

    await state.update_data(url=url)
    await state.set_state(DownloadStates.waiting_for_format)
    await message.answer(
        "📦 <b>Шаг 2 из 2:</b> Ссылка принята!\n\nЧто именно ты хочешь скачать?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎬 Только видео", callback_data="fmt_video")],
            [InlineKeyboardButton(text="🎵 Только аудио (MP3)", callback_data="fmt_audio")],
            [InlineKeyboardButton(text="📦 Всё вместе (Видео + MP3)", callback_data="fmt_both")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_action")],
        ]))

@private_router.callback_query(DownloadStates.waiting_for_format, F.data.startswith("fmt_"))
async def process_format_choice(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    action = callback.data.replace("fmt_", "")
    if action not in ("video", "audio", "both"):
        return
    url = (await state.get_data()).get("url")
    await state.clear()
    if not url:
        await safe_exit(callback.message, "❌ Ошибка: ссылка потеряна. Начни заново.")
        return
    uid = callback.from_user.id
    if not cooldown(uid, 3):
        await safe_exit(callback.message, "⏳ Слишком часто, подожди пару секунд.")
        return

    is_vip = get_vip(uid)
    text = "🔄 <b>Загружаем медиа...</b> Подожди пару секунд."
    await safe_exit(callback.message, text)
    await job(bot, callback.message.chat.id, uid, url, action, is_vip,
              markup=get_restart_inline_keyboard(uid), status=callback.message)

@private_router.callback_query(F.data == "cancel_action")
async def cancel_action(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer("Отменено")
    uid = callback.from_user.id
    await safe_exit(callback.message, "❌ Действие отменено.", get_main_keyboard(uid, get_vip(uid)))

@private_router.message(F.text.startswith("💎 Купить VIP") | F.text.startswith("🌟 VIP Статус"))
async def buy_vip_command(message: Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    await message.answer_invoice(
        title="🌟 VIP-статус для PulseFetch",
        description=f"Файлы до {fmt_limit(VIP_LIMIT_MB)}, без водяного знака, максимальное качество!",
        prices=[LabeledPrice(label="VIP Подписка (1 месяц)", amount=100)],
        payload="vip_subscription_30_days", currency="XTR", provider_token="")
    await message.answer(f"{get_vip_comparison_text()}\n\n💳 <b>Стоимость:</b> 100 Telegram Stars ✨")

@private_router.message(F.successful_payment)
async def successful_payment_handler(message: Message):
    if message.successful_payment.invoice_payload != "vip_subscription_30_days":
        return
    uid = message.from_user.id
    db_set_user_vip_months(uid, 1)
    await message.answer(
        "🎉 <b>Оплата прошла успешно!</b>\n\nТебе присвоен статус 🌟 <b>VIP</b> на 30 дней!",
        reply_markup=get_main_keyboard(uid, get_vip(uid)))

@private_router.message(F.text.in_({"🎁 Бесплатный VIP за друзей", "🎁 Free VIP via Friends", "🎁 Безкоштовний VIP за друзів"}))
async def referral_menu(message: Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    refs, claimed = db_get_user_info(uid)
    ref_link = f"https://t.me/{BOT_USERNAME}?start=ref_{uid}"
    needed = 3 - (refs % 3)
    status = f"📊 Приглашено: <code>{refs}</code> | Получено бонусов: <code>{claimed} из 3</code>"
    await message.answer(
        "🎁 <b>Получи VIP на 24 часа бесплатно!</b>\n\n"
        "Приглашай друзей по своей ссылке. За каждые <b>3 друга</b> — VIP на 24 часа!\n\n"
        f"🔗 <b>Твоя ссылка:</b>\n<code>{ref_link}</code>\n\n{status}",
        reply_markup=get_restart_inline_keyboard(uid))

@private_router.message(AdminStates.waiting_for_broadcast, F.from_user.id == ADMIN_ID)
async def admin_broadcast_send(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    task = asyncio.create_task(run_broadcast(bot, message.chat.id, message.message_id))
    BG_TASKS.add(task)
    task.add_done_callback(BG_TASKS.discard)
    await message.answer("🚀 Рассылка запущена.")

@private_router.message(F.text)
async def private_fallback(message: Message):
    uid = message.from_user.id
    await message.answer("ℹ️ Используй меню для управления ботом.", reply_markup=get_main_keyboard(uid, get_vip(uid)))

group_router = Router(name="group")

@group_router.my_chat_member(ChatMemberUpdatedFilter(JOIN_TRANSITION))
async def bot_added_to_group(event: ChatMemberUpdated, bot: Bot):
    if event.chat.type not in GROUPS:
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🤖 Открыть бота", url=f"https://t.me/{BOT_USERNAME}")],
    ])
    await quiet(bot.send_message(event.chat.id, "👋 Привет! Я PulseFetch. Отправь ссылку в чат для скачивания.", reply_markup=kb))

@group_router.message(CommandStart(), F.chat.type.in_(GROUPS))
async def group_start(message: Message):
    await message.answer("👋 Привет! Я <b>PulseFetch</b>. Отправь ссылку на видео в чат!")

@group_router.message(F.chat.type.in_(GROUPS), F.text | F.caption)
async def group_autoscan(message: Message, bot: Bot):
    if not message.from_user or message.from_user.is_bot:
        return
    urls = [u for u in extract_urls(message) if host_supported(u)]
    if not urls:
        return
    if not cooldown(message.from_user.id, 4):
        return
    task = asyncio.create_task(job(
        bot, message.chat.id, message.from_user.id, urls[0], "video", False,
        reply_to=message.message_id, silent=True))
    BG_TASKS.add(task)
    task.add_done_callback(BG_TASKS.discard)

async def handle_ping(request):
    return web.Response(text="Bot is running!")

async def start_web_server() -> web.AppRunner:
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    await web.TCPSite(runner, "0.0.0.0", port).start()
    log.info("Веб-сервер запущен на порту %s", port)
    return runner

def cleanup_stale_tmp():
    base = Path(tempfile.gettempdir())
    for p in base.glob("pf_*"):
        shutil.rmtree(p, ignore_errors=True)

async def main():
    global BOT_USERNAME
    if not BOT_TOKEN:
        raise SystemExit("Не задана переменная окружения BOT_TOKEN")
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise SystemExit("ffmpeg/ffprobe не найдены в PATH")

    init_db()
    cleanup_stale_tmp()
    runner = await start_web_server()

    if LOCAL_API_URL:
        session = AiohttpSession(api=TelegramAPIServer.from_base(LOCAL_API_URL), timeout=900)
    else:
        session = AiohttpSession(timeout=900)
    bot = Bot(BOT_TOKEN, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        me = await bot.me()
        BOT_USERNAME = me.username or BOT_USERNAME

        dp = Dispatcher(storage=MemoryStorage())
        dp.message.outer_middleware(MaintenanceMiddleware())
        dp.callback_query.outer_middleware(MaintenanceMiddleware())
        dp.include_routers(pay_router, private_router, group_router)

        @dp.errors()
        async def on_error(event):
            log.exception("Необработанная ошибка: %s", event.exception)
            return True

        await bot.delete_webhook(drop_pending_updates=True)
        log.info("Бот PulseFetch запущен как @%s", BOT_USERNAME)

        async def self_ping():
            import aiohttp
            base_url = os.getenv("RENDER_EXTERNAL_URL")
            if not base_url:
                base_url = "https://pulsefetch-bot.onrender.com"
            if not base_url.startswith("http"):
                base_url = "https://" + base_url

            while True:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(base_url, timeout=15) as resp:
                            log.info("Self-ping OK: %s", resp.status)
                except Exception as e:
                    log.warning("Self-ping failed: %s", str(e)[:100])
                await asyncio.sleep(280)

        asyncio.create_task(self_ping())
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        for t in list(BG_TASKS):
            t.cancel()
        await bot.session.close()
        await runner.cleanup()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
