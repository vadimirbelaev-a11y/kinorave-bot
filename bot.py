# -*- coding: utf-8 -*-
"""PulseFetch — Telegram-бот для скачивания медиа."""
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

import aiohttp
import yt_dlp
from aiohttp import web

# ===== 1. МГНОВЕННЫЙ ЗАПУСК ВЕБ-СЕРВЕРА ДЛЯ RENDER =====
async def handle_ping(request):
    return web.Response(text="Bot is running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    await web.TCPSite(runner, "0.0.0.0", port).start()
    print(f"WEB SERVER STARTED ON PORT {port}")

try:
    loop = asyncio.get_event_loop()
    if loop.is_running():
        asyncio.create_task(start_web_server())
    else:
        loop.run_until_complete(start_web_server())
except Exception:
    pass
# =======================================================

from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ChatType, ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.filters import CommandObject, CommandStart, JOIN_TRANSITION, ChatMemberUpdatedFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (CallbackQuery, ChatMemberUpdated, FSInputFile,
                           InlineKeyboardButton, InlineKeyboardMarkup,
                           KeyboardButton, LabeledPrice, Message,
                           PreCheckoutQuery, ReplyKeyboardMarkup, ReplyParameters)
from aiogram.utils.chat_action import ChatActionSender

from database import (
    init_db, db_add_user, check_vip_status_expiration,
    db_get_user_info, db_set_user_vip_months, db_get_stats,
    db_get_all_users, get_maintenance_mode, set_maintenance_mode,
    db_get_user_language, db_set_user_language, db_get_user_reg_date
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise SystemExit("❌ Ошибка: не найден BOT_TOKEN в настройках Render!")

ADMIN_ID = 6444735646
BOT_USERNAME = os.getenv("BOT_USERNAME", "pulsefetch_bot")
COOKIES_FILE = os.getenv("COOKIES_FILE", "cookies.txt")
PROXY_URL = os.getenv("PROXY_URL", "").strip()
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

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
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

YT_CLIENTS = ["ios", "android", "mweb", "tv", "web_safari", "web"]
VIDEO_EXT = (".mp4", ".mkv", ".webm", ".mov", ".m4v")
AUDIO_SRC_EXT = (".m4a", ".mp3", ".opus", ".webm", ".ogg", ".aac", ".mp4", ".wav", ".flac")

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
        "welcome": "👋 <b>Привет, {name}!</b>\n\nЯ универсальный бот <b>PulseFetch</b>.\n\n📌 <b>Твой тариф:</b> {tariff}\n\n👇 Нажми кнопку ниже:",
        "choose_platform": "📂 <b>Шаг 1 из 2:</b> Выбери платформу:",
        "settings_title": "⚙️ <b>Настройки бота</b>\n\nВыбери язык интерфейса:",
        "lang_changed": "✅ Язык успешно изменен на Русский!",
        "profile_text": "👤 <b>Твой профиль:</b>\n\n🆔 ID: <code>{uid}</code>\n👤 Имя: <b>{name}</b>\n🌟 Тариф: <b>{tariff}</b>\n📅 Регистрация: <b>{reg_date}</b>\n\n👥 Друзей: <b>{refs}</b>\n🎁 Бонусов: <b>{claimed} из 3</b>",
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
        "welcome": "👋 <b>Привіт, {name}!</b>\n\nЯ універсальний бот <b>PulseFetch</b>.\n\n📌 <b>Твій тариф:</b> {tariff}\n\n👇 Натисни кнопку нижче:",
        "choose_platform": "📂 <b>Крок 1 із 2:</b> Вибери платформу:",
        "settings_title": "⚙️ <b>Налаштування бота</b>\n\nВибери мову інтерфейсу:",
        "lang_changed": "✅ Мову успішно змінено на Українську!",
        "profile_text": "👤 <b>Твій профіль:</b>\n\n🆔 ID: <code>{uid}</code>\n👤 Ім'я: <b>{name}</b>\n🌟 Тариф: <b>{tariff}</b>\n📅 Реєстрація: <b>{reg_date}</b>\n\n👥 Друзей: <b>{refs}</b>\n🎁 Бонусів: <b>{claimed} з 3</b>",
    }
}

def t(user_id: int, key: str, **kwargs) -> str:
    lang = db_get_user_language(user_id) or "ru"
    text = LANGS.get(lang, LANGS["ru"]).get(key, LANGS["ru"].get(key, key))
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
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
        return False

async def safe_exit(msg, text: str, markup=None):
    try:
        await msg.edit_text(text, reply_markup=markup)
    except Exception:
        pass
# ===== 2. УСИЛЕННЫЙ МОДУЛЬ СКАЧИВАНИЯ =====
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

def _ydl_opts(tmp: Path, fmt: str, cancel: threading.Event, use_clients: bool, limit: int, *, use_cookies: bool = True, extra_headers: dict | None = None, impersonate: bool | str = False) -> dict:
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
        "retries": 15,
        "fragment_retries": 15,
        "extractor_retries": 10,
        "file_access_retries": 5,
        "socket_timeout": 60,
        "concurrent_fragment_downloads": 4,
        "geo_bypass": True,
        "http_headers": headers,
        "progress_hooks": [hook],
        "max_filesize": limit,
        "overwrites": True,
        "legacy_server_connect": True,
        "nocheckcertificate": True,
    }

    if PROXY_URL:
        opts["proxy"] = PROXY_URL

    if use_clients:
        opts["extractor_args"] = {
            "youtube": {
                "player_client": YT_CLIENTS,
                "player_skip": ["webpage", "configs"],
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

async def _download_via_invidious_api(url: str, tmp: Path) -> Optional[dict]:
    match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", url)
    if not match:
        return None
    video_id = match.group(1)
    
    instances = [
        "https://invidious.privacyredirect.com",
        "https://vid.puffyan.us",
        "https://inv.nadeko.net",
        "https://invidious.nerdvpn.de"
    ]
    
    async with aiohttp.ClientSession() as session:
        for host in instances:
            try:
                api_url = f"{host}/api/v1/videos/{video_id}"
                async with session.get(api_url, timeout=10) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json()
                    adaptive_formats = data.get("adaptiveFormats", [])
                    video_url = next((f.get("url") for f in adaptive_formats if f.get("type", "").startswith("video/mp4") and f.get("qualityLabel") in ("720p", "360p")), None)
                    if not video_url:
                        continue
                    
                    out_file = tmp / f"{video_id}.mp4"
                    async with session.get(video_url, timeout=60) as v_resp:
                        if v_resp.status == 200:
                            with open(out_file, "wb") as f:
                                f.write(await v_resp.read())
                            if out_file.exists() and out_file.stat().st_size > 0:
                                return {"title": data.get("title", "YouTube Video"), "filepath": out_file}
            except Exception:
                continue
    return None

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
            {"use_clients": True,  "use_cookies": True,  "impersonate": False, "clients": ["ios", "android", "mweb"]},
            {"use_clients": True,  "use_cookies": True,  "impersonate": False, "clients": ["tv", "web_safari"]},
            {"use_clients": True,  "use_cookies": False, "impersonate": False, "clients": ["ios", "android"]},
            {"use_clients": False, "use_cookies": True,  "impersonate": "chrome", "clients": None},
            {"use_clients": False, "use_cookies": True,  "impersonate": False, "clients": None},
        ]
    elif is_tiktok or is_instagram:
        strategies = [
            {"use_clients": False, "use_cookies": True,  "impersonate": "chrome", "clients": None},
            {"use_clients": False, "use_cookies": False, "impersonate": "chrome", "clients": None},
        ]
    else:
        strategies = [
            {"use_clients": False, "use_cookies": True,  "impersonate": "chrome", "clients": None},
        ]

    extra_headers = None
    if is_tiktok:
        extra_headers = {"Referer": "https://www.tiktok.com/", "Origin": "https://www.tiktok.com"}
    elif is_instagram:
        extra_headers = {"Referer": "https://www.instagram.com/", "Origin": "https://www.instagram.com"}

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
            log.warning("yt-dlp failed (strat=%s): %s", strat, str(e)[:300])
            _clear(tmp)

    raise MediaError(str(last_err) if last_err else "download failed")

def _find_file(tmp: Path, exts: tuple) -> Optional[Path]:
    files = [p for p in tmp.iterdir() if p.is_file() and p.suffix.lower() in exts and not p.name.endswith((".part", ".ytdl")) and p.stat().st_size > 0]
    return max(files, key=lambda p: p.stat().st_size) if files else None

async def _run(*cmd, timeout: int):
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise MediaError("ffmpeg: таймаут")
    return proc.returncode, out, err

async def _probe(path: Path) -> Optional[dict]:
    try:
        rc, out, _ = await _run("ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path), timeout=60)
        if rc != 0:
            return None
        data = json.loads(out.decode() or "{}")
    except Exception:
        return None
    v = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    a = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
    if not v:
        return None
    try:
        dur = int(float(data.get("format", {}).get("duration") or v.get("duration") or 0))
    except ValueError:
        dur = 0
    return {"vcodec": v.get("codec_name"), "acodec": a.get("codec_name") if a else None, "w": int(v.get("width") or 0), "h": int(v.get("height") or 0), "dur": dur}

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
        drawtext = f"drawtext=text='{watermark_text}':fontsize=18:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2:box=1:boxcolor=black@0.4:boxborderw=6"
        vf_parts.append(drawtext)

    vf = ",".join(vf_parts)

    if info["vcodec"] == "h264" and info["acodec"] in (None, "aac") and not need_scale and not add_watermark:
        rc, _, _ = await _run("ffmpeg", "-y", "-v", "error", "-i", str(src), "-c", "copy", "-movflags", "+faststart", str(out), timeout=FFMPEG_TIMEOUT)
        if rc == 0 and out.exists() and out.stat().st_size > 0:
            if src != out:
                src.unlink(missing_ok=True)
            return out

    rc, _, err = await _run("ffmpeg", "-y", "-v", "error", "-i", str(src), "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out), timeout=FFMPEG_TIMEOUT)
    if rc != 0 or not out.exists() or out.stat().st_size == 0:
        raise MediaError("ffmpeg: " + err.decode(errors="ignore")[-200:])

    if src != out:
        src.unlink(missing_ok=True)
    return out

async def _to_mp3(src: Path, tmp: Path, limit: int) -> Path:
    for br in (192, 128, 64):
        out = tmp / f"audio_{br}.mp3"
        rc, _, err = await _run("ffmpeg", "-y", "-v", "error", "-i", str(src), "-vn", "-c:a", "libmp3lame", "-b:a", f"{br}k", str(out), timeout=FFMPEG_TIMEOUT)
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

async def fetch_media(url: str, heights: list, want_video: bool, want_audio: bool, limit: int, add_watermark: bool = False) -> Result:
    tmp = Path(await asyncio.to_thread(tempfile.mkdtemp, prefix="pf_"))
    res = Result(tmpdir=tmp)
    cancel = threading.Event()
    low = url.lower()
    is_youtube = any(h in low for h in ("youtube.com", "youtu.be"))

    try:
        success = False
        last_err = None
        if want_video:
            for h in heights:
                _clear(tmp)
                try:
                    info = await asyncio.wait_for(asyncio.to_thread(_download_sync, url, tmp, build_format(h), cancel, limit), DOWNLOAD_TIMEOUT)
                    src = _find_file(tmp, VIDEO_EXT)
                    if not src:
                        raise MediaError("слишком большой файл")
                    final = await _normalize(src, tmp, h, add_watermark=add_watermark)
                    if final.stat().st_size > limit:
                        raise MediaError("слишком большой файл")
                    meta = await _probe(final) or {"w": 0, "h": 0, "dur": 0}
                    res.video, res.title = final, (info or {}).get("title") or "Media"
                    res.width, res.height, res.duration = meta["w"], meta["h"], meta["dur"]
                    success = True
                    break
                except Exception as e:
                    last_err = e
                    continue
        
        if not success and is_youtube and want_video:
            _clear(tmp)
            api_data = await _download_via_invidious_api(url, tmp)
            if api_data:
                src = api_data["filepath"]
                final = await _normalize(src, tmp, heights[0] if heights else 720, add_watermark=add_watermark)
                meta = await _probe(final) or {"w": 0, "h": 0, "dur": 0}
                res.video, res.title = final, api_data["title"]
                res.width, res.height, res.duration = meta["w"], meta["h"], meta["dur"]
                success = True

        if not success and not res.video:
            raise last_err or MediaError("не удалось скачать")

        if want_audio and res.video:
            try:
                res.audio = await _to_mp3(res.video, tmp, limit)
            except Exception:
                pass

        return res
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise

def friendly_error(e: Exception, limit_mb: int) -> str:
    s = str(e).lower()
    if "слишком большой" in s:
        return f"📦 Файл слишком большой для отправки (лимит {fmt_limit(limit_mb)})."
    if any(k in s for k in ("private", "login", "sign in", "cookies", "age", "authentication", "bot")):
        return "🔒 YouTube заблокировал IP дата-центра Render. Добавь PROXY_URL в настройки Render."
    if any(k in s for k in ("unsupported url", "no video")):
        return "🤷 В этой ссылке не нашлось медиа."
    return "❌ Не удалось скачать медиа. Проверьте ссылку."

async def _retry_send(factory):
    for _ in range(3):
        try:
            return await factory()
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
    raise MediaError("не удалось отправить файл")

async def send_video_file(bot: Bot, chat_id: int, res: Result, caption: str, reply_to: Optional[int], markup):
    rp = ReplyParameters(message_id=reply_to, allow_sending_without_reply=True) if reply_to else None
    async def as_video():
        return await bot.send_video(chat_id, FSInputFile(res.video), caption=caption, width=res.width or None, height=res.height or None, duration=res.duration or None, supports_streaming=True, reply_markup=markup, reply_parameters=rp)
    async def as_doc():
        return await bot.send_document(chat_id, FSInputFile(res.video), caption=caption, reply_markup=markup, reply_parameters=rp)
    try:
        await _retry_send(as_video)
    except TelegramBadRequest:
        await _retry_send(as_doc)

async def send_audio_file(bot: Bot, chat_id: int, res: Result, caption: str, reply_to: Optional[int], markup):
    rp = ReplyParameters(message_id=reply_to, allow_sending_without_reply=True) if reply_to else None
    await _retry_send(lambda: bot.send_audio(chat_id, FSInputFile(res.audio), caption=caption, title=res.title[:60], reply_markup=markup, reply_parameters=rp))

async def job(bot: Bot, chat_id: int, user_id: int, url: str, action: str, is_vip: bool, *, reply_to: Optional[int] = None, markup=None, silent: bool = False, status: Optional[Message] = None) -> bool:
    key = (chat_id, url, action)
    if key in IN_FLIGHT:
        if not silent:
            await quiet(bot.send_message(chat_id, "⏳ Ссылка уже обрабатывается."))
        return False
    IN_FLIGHT.add(key)
    res: Optional[Result] = None
    limit_mb = VIP_LIMIT_MB if is_vip else FREE_LIMIT_MB
    tail = f"\n📥 Скачано через @{BOT_USERNAME}"
    try:
        async with DL_SEM:
            async with ChatActionSender.upload_video(bot=bot, chat_id=chat_id):
                res = await fetch_media(url, VIP_HEIGHTS if is_vip else FREE_HEIGHTS, action in ("video", "both"), action in ("audio", "both"), limit_mb * 1024 * 1024, add_watermark=not is_vip)
                q = f" {res.height}p" if res.height else ""
                if res.video:
                    await send_video_file(bot, chat_id, res, f"🎥 <b>Видео{q}</b>{tail}", reply_to, markup if not res.audio else None)
                if res.audio:
                    await send_audio_file(bot, chat_id, res, f"🎵 <b>Аудиодорожка</b>{tail}", reply_to if not res.video else None, markup)
        return True
    except Exception as e:
        if not silent:
            await quiet(bot.send_message(chat_id, friendly_error(e, limit_mb), reply_markup=markup))
        return False
    finally:
        IN_FLIGHT.discard(key)
        if res:
            shutil.rmtree(res.tmpdir, ignore_errors=True)
        if status:
            await quiet(status.delete())
# ===== 3. ИНТЕРФЕЙС И КЛАВИАТУРЫ =====
def get_vip_comparison_text() -> str:
    return "⚡️ <b>ТАРИФЫ</b>\n\n👤 Обычный: до 500 МБ, 720p, с водяным знаком.\n🌟 VIP: до 2 ГБ, 1080p+, MP3, без знака."

def get_main_keyboard(user_id: int, is_vip: bool) -> ReplyKeyboardMarkup:
    vip_label = t(user_id, "vip_active") if is_vip else t(user_id, "vip_buy")
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text=t(user_id, "download")), KeyboardButton(text=t(user_id, "profile"))],
        [KeyboardButton(text=vip_label)],
        [KeyboardButton(text=t(user_id, "ref")), KeyboardButton(text=t(user_id, "restart"))],
        [KeyboardButton(text=t(user_id, "settings")), KeyboardButton(text=t(user_id, "about"))],
    ], resize_keyboard=True)

def get_restart_inline_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔄 Главное меню", callback_data="restart_bot")]])

def get_platforms_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎵 TikTok", callback_data="platform_tiktok"), InlineKeyboardButton(text="📺 YouTube / Shorts", callback_data="platform_youtube")],
        [InlineKeyboardButton(text="📸 Instagram", callback_data="platform_insta"), InlineKeyboardButton(text="🌐 Другие", callback_data="platform_other")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_action")],
    ])

def get_languages_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru"), InlineKeyboardButton(text="🇺🇦 Українська", callback_data="lang_uk")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="restart_bot")]
    ])

class DownloadStates(StatesGroup):
    waiting_for_link = State()
    waiting_for_format = State()

class AdminStates(StatesGroup):
    waiting_for_broadcast = State()

class MaintenanceMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
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
    db_add_user(uid, message.from_user.username, message.from_user.first_name, None)
    is_vip = get_vip(uid)
    await message.answer(t(uid, "welcome", name=esc(message.from_user.first_name), tariff="🌟 VIP" if is_vip else "👤 Free"), reply_markup=get_main_keyboard(uid, is_vip))

@private_router.message(F.text.in_({"🔄 Перезапустить бота", "🔄 Restart Bot", "🔄 Перезапустити бота"}))
async def restart_button(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("🔄 Меню:", reply_markup=get_main_keyboard(message.from_user.id, get_vip(message.from_user.id)))

@private_router.callback_query(F.data == "restart_bot")
async def callback_restart(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()
    await safe_exit(callback.message, "⚡️ Главное меню:", get_main_keyboard(callback.from_user.id, get_vip(callback.from_user.id)))

@private_router.message(F.text.in_({"⚙️ Настройки", "⚙️ Settings", "⚙️ Налаштування"}))
async def settings_handler(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(t(message.from_user.id, "settings_title"), reply_markup=get_languages_keyboard())

@private_router.callback_query(F.data.startswith("lang_"))
async def set_lang(callback: CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    db_set_user_language(uid, callback.data.replace("lang_", ""))
    await callback.answer(t(uid, "lang_changed"), show_alert=True)
    await safe_exit(callback.message, "⚡️ Меню:", get_main_keyboard(uid, get_vip(uid)))

@private_router.message(F.text.in_({"👤 Мой профиль", "👤 My Profile", "👤 Мій профіль"}))
async def profile_handler(message: Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    refs, claimed = db_get_user_info(uid)
    await message.answer(t(uid, "profile_text", uid=uid, name=esc(message.from_user.first_name), tariff="🌟 VIP" if get_vip(uid) else "👤 Free", reg_date=db_get_user_reg_date(uid) or "Неизвестно", refs=refs, claimed=claimed), reply_markup=get_restart_inline_keyboard(uid))

@private_router.message(F.text.in_({"📥 Скачать медиа", "📥 Download Media", "📥 Завантажити медіа"}))
async def choose_platform(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(t(message.from_user.id, "choose_platform"), reply_markup=get_platforms_keyboard(message.from_user.id))

@private_router.callback_query(F.data == "back_to_platforms")
async def back_platforms(callback: CallbackQuery):
    await callback.answer()
    await safe_exit(callback.message, t(callback.from_user.id, "choose_platform"), get_platforms_keyboard(callback.from_user.id))

@private_router.callback_query(F.data.startswith("platform_"))
async def platform_choice(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(platform=callback.data.replace("platform_", ""))
    await state.set_state(DownloadStates.waiting_for_link)
    await safe_exit(callback.message, "🔗 Отправь ссылку в чат:", InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_platforms")]]))

@private_router.message(DownloadStates.waiting_for_link, F.text)
async def link_received(message: Message, state: FSMContext):
    urls = extract_urls(message)
    if not urls:
        await message.answer("❌ Ссылка не найдена. Попробуй еще раз:")
        return
    await state.update_data(url=urls[0])
    await state.set_state(DownloadStates.waiting_for_format)
    await message.answer("📦 Выбери формат:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Только видео", callback_data="fmt_video")],
        [InlineKeyboardButton(text="🎵 Только аудио (MP3)", callback_data="fmt_audio")],
        [InlineKeyboardButton(text="📦 Всё вместе", callback_data="fmt_both")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_action")],
    ]))

@private_router.callback_query(DownloadStates.waiting_for_format, F.data.startswith("fmt_"))
async def format_choice(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    action = callback.data.replace("fmt_", "")
    data = await state.get_data()
    url = data.get("url")
    await state.clear()
    if not url:
        await safe_exit(callback.message, "❌ Ссылка потеряна.")
        return
    uid = callback.from_user.id
    if not cooldown(uid, 3):
        await safe_exit(callback.message, "⏳ Подожди пару секунд.")
        return
    await safe_exit(callback.message, "🔄 <b>Загружаем...</b>")
    await job(bot, callback.message.chat.id, uid, url, action, get_vip(uid), markup=get_restart_inline_keyboard(uid), status=callback.message)

@private_router.callback_query(F.data == "cancel_action")
async def cancel_action(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer("Отменено")
    await safe_exit(callback.message, "❌ Отменено.", get_main_keyboard(callback.from_user.id, get_vip(callback.from_user.id)))

@private_router.message(F.text)
async def fallback(message: Message):
    await message.answer("ℹ️ Используй меню:", reply_markup=get_main_keyboard(message.from_user.id, get_vip(message.from_user.id)))
# ===== 4. ГРУППЫ И ГЛАВНЫЙ ЦИКЛ MAIN =====
group_router = Router(name="group")
@group_router.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}), F.text | F.caption)
async def group_scan(message: Message, bot: Bot):
    if not message.from_user or message.from_user.is_bot:
        return
    urls = [u for u in extract_urls(message) if host_supported(u)]
    if urls and cooldown(message.from_user.id, 4):
        task = asyncio.create_task(job(bot, message.chat.id, message.from_user.id, urls[0], "video", False, reply_to=message.message_id, silent=True))
        BG_TASKS.add(task)
        task.add_done_callback(BG_TASKS.discard)

def cleanup_tmp():
    try:
        shutil.rmtree(Path(tempfile.gettempdir()) / "pf_*", ignore_errors=True)
    except Exception:
        pass

async def main():
    global BOT_USERNAME
    if not BOT_TOKEN:
        raise SystemExit("Нет BOT_TOKEN")
    init_db()
    cleanup_tmp()

    session = AiohttpSession(timeout=900)
    bot = Bot(BOT_TOKEN, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        me = await bot.me()
        BOT_USERNAME = me.username or BOT_USERNAME

        dp = Dispatcher(storage=MemoryStorage())
        dp.message.outer_middleware(MaintenanceMiddleware())
        dp.callback_query.outer_middleware(MaintenanceMiddleware())
        dp.include_routers(pay_router, private_router, group_router)

        await bot.delete_webhook(drop_pending_updates=True)
        log.info("Бот запущен как @%s", BOT_USERNAME)

        async def self_ping():
            import aiohttp
            base_url = os.getenv("RENDER_EXTERNAL_URL", "https://pulsefetch-bot.onrender.com")
            if not base_url.startswith("http"):
                base_url = "https://" + base_url
            while True:
                try:
                    async with aiohttp.ClientSession() as s:
                        async with s.get(base_url, timeout=15):
                            pass
                except Exception:
                    pass
                await asyncio.sleep(60)  # Стучимся каждую минуту (60 секунд), чтобы бот не засыпал

        asyncio.create_task(self_ping())
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        for t in list(BG_TASKS):
            t.cancel()
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
