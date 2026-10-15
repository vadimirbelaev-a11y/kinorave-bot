import os
import random
import logging
import aiohttp
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiogram.types import (
    BotCommand,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    ReplyKeyboardMarkup,
    KeyboardButton
)

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = "8410105070:AAHUuktDtUm_ICmRiRx0HghwsNkfYcNYD0Y"
TMDB_API_KEY = "e2d7e4ba3b610d32bb5826f04d026bd6"
CHANNEL_LINK = "https://t.me/kinorave_tg"
CHANNEL_USERNAME = "@kinorave_tg"

RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "")
WEBHOOK_PATH = "/bot/" + BOT_TOKEN
WEBHOOK_URL = RENDER_EXTERNAL_URL + WEBHOOK_PATH
PORT = int(os.environ.get("PORT", 10000))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
USERS_FILE = "users.txt"
REFS_FILE = "referrals.txt"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def save_user(user_id: int, referrer_id: int = None):
    users = set()
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            users = set(line.strip() for line in f if line.strip())
    
    is_new = str(user_id) not in users
    if is_new:
        with open(USERS_FILE, "a") as f:
            f.write(str(user_id) + "\n")
            
        # Если пришел по реферальной ссылке и это не он сам
        if referrer_id and referrer_id != user_id:
            with open(REFS_FILE, "a") as f:
                f.write(f"{referrer_id}:{user_id}\n")

def get_users_count():
    if not os.path.exists(USERS_FILE):
        return 0
    with open(USERS_FILE, "r") as f:
        return len(set(line.strip() for line in f if line.strip()))

def get_referral_count(user_id: int) -> int:
    if not os.path.exists(REFS_FILE):
        return 0
    count = 0
    with open(REFS_FILE, "r") as f:
        for line in f:
            parts = line.strip().split(":")
            if len(parts) == 2 and parts[0] == str(user_id):
                count += 1
    return count

async def check_subscription(user_id):
    try:
        m = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        return m.status in ["creator", "administrator", "member"]
    except Exception:
        return True

def get_sub_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📢 Подписаться на KINOrave", url=CHANNEL_LINK)], [InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check_sub")]])

def get_main_kb():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🔍 Поиск"), KeyboardButton(text="📁 Подборки"), KeyboardButton(text="🌪 Фильтр")], [KeyboardButton(text="⚙️ Настройки"), KeyboardButton(text="🎁 Поделиться")]], resize_keyboard=True)

def get_start_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎲 Кинорулетка", callback_data="roulette"), InlineKeyboardButton(text="🏆 ТОП KINOrave", callback_data="top_list")], [InlineKeyboardButton(text="⚙️ Настройки", callback_data="open_settings"), InlineKeyboardButton(text="🔍 Начать поиск", switch_inline_query_current_chat="")]])

def get_search_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎲 Кинорулетка", callback_data="roulette"), InlineKeyboardButton(text="🏆 ТОП KINOrave", callback_data="top_list")], [InlineKeyboardButton(text="📁 Подборки", callback_data="open_collections"), InlineKeyboardButton(text="🌪 Фильтры", callback_data="open_filter")], [InlineKeyboardButton(text="⚙️ Настройки", callback_data="open_settings")], [InlineKeyboardButton(text="🔍 Начать поиск", switch_inline_query_current_chat="")]])

def get_collections_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏆 ТОП-10 KINOrave", callback_data="top_list"), InlineKeyboardButton(text="🎲 Кинорулетка", callback_data="roulette")], [InlineKeyboardButton(text="🔥 Тренды дня", callback_data="col_trend"), InlineKeyboardButton(text="🌟 Популярное", callback_data="col_pop")], [InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_start")]])

def get_filter_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💥 Боевики", callback_data="genre_action"), InlineKeyboardButton(text="😂 Комедии", callback_data="genre_comedy")], [InlineKeyboardButton(text="🎭 Драмы", callback_data="genre_drama"), InlineKeyboardButton(text="👻 Ужасы", callback_data="genre_horror")], [InlineKeyboardButton(text="🎲 Кинорулетка", callback_data="roulette")], [InlineKeyboardButton(text="🔄 Сбросить фильтр", callback_data="f_reset")], [InlineKeyboardButton(text="🔍 Искать по каталогу", switch_inline_query_current_chat="")], [InlineKeyboardButton(text="◀️ Назад", callback_data="back_start")]])

def get_settings_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⤴️ Пригласить друга", callback_data="open_share")], [InlineKeyboardButton(text="👨‍💻 Наш канал", url=CHANNEL_LINK)], [InlineKeyboardButton(text="🛡 Подключить VPN", url="https://t.me/StableVPN")], [InlineKeyboardButton(text="🔍 Найти кино", switch_inline_query_current_chat="")]])

def get_share_kb(username, uid):
    ref = "https://t.me/" + str(username) + "?start=ref_" + str(uid)
    share_url = "https://t.me/share/url?url=" + ref + "&text=Смотри+лучшие+фильмы+в+KINOrave!"
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📧 Отправить ссылку", url=share_url)], [InlineKeyboardButton(text="🔍 К поиску", switch_inline_query_current_chat="")]])

def get_movie_kb(title):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎙 Озвучка", callback_data="voice"), InlineKeyboardButton(text="🔮 Качество", callback_data="quality")], [InlineKeyboardButton(text="💬 Наш канал", url=CHANNEL_LINK), InlineKeyboardButton(text="⤴️ Поделиться", switch_inline_query=title)], [InlineKeyboardButton(text="📺 Трансляция TV", callback_data="tv"), InlineKeyboardButton(text="🎲 Ещё фильм", callback_data="roulette")], [InlineKeyboardButton(text="🔍 Искать дальше", switch_inline_query_current_chat="")]])

@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    
    # Обработка реферального параметра вида /start ref_123456
    args = message.text.split()
    referrer_id = None
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            referrer_id = int(args[1].replace("ref_", ""))
        except ValueError:
            pass

    save_user(user_id, referrer_id)
    
    try: await message.delete()
    except Exception: pass
    
    if not await check_subscription(user_id):
        await message.answer("👋 Привет, " + str(message.from_user.first_name) + "!\n\n🔒 Для доступа к каталогу подпишись на канал KINOrave:", reply_markup=get_sub_kb())
        return
        
    txt = "🎬 **Добро пожаловать в KINOrave!**\n\n🍿 Твой персональный гид по миру кино. Выбирай категории ниже или пиши название фильма в чат.\n\n💬 [Наш канал](" + CHANNEL_LINK + ")"
    await message.answer(txt, reply_markup=get_start_kb(), parse_mode="Markdown", disable_web_page_preview=True)
    await message.answer("Главное меню управления:", reply_markup=get_main_kb())

@dp.message(Command("search"))
async def search_cmd(message: types.Message):
    save_user(message.from_user.id)
    try: await message.delete()
    except Exception: pass
    if not await check_subscription(message.from_user.id):
        await message.answer("Подпишись на канал!", reply_markup=get_sub_kb())
        return
    await message.answer("🔍 **Поиск фильмов и сериалов**\n\nВведи запрос прямо в чат или нажми «Начать поиск».", reply_markup=get_search_kb(), parse_mode="Markdown")

@dp.message(Command("collections"))
async def collections_cmd(message: types.Message):
    save_user(message.from_user.id)
    try: await message.delete()
    except Exception: pass
    if not await check_subscription(message.from_user.id):
        await message.answer("Подпишись на канал!", reply_markup=get_sub_kb())
        return
    await message.answer("📁 **Выбери категорию подборки:**", reply_markup=get_collections_kb(), parse_mode="Markdown")

@dp.message(Command("filter"))
async def filter_cmd(message: types.Message):
    save_user(message.from_user.id)
    try: await message.delete()
    except Exception: pass
    if not await check_subscription(message.from_user.id):
        await message.answer("Подпишись на канал!", reply_markup=get_sub_kb())
        return
    await message.answer("🌪 **Выбери параметры поиска:**", reply_markup=get_filter_kb(), parse_mode="Markdown")

@dp.message(Command("settings"))
async def settings_cmd(message: types.Message):
    save_user(message.from_user.id)
    try: await message.delete()
    except Exception: pass
    if not await check_subscription(message.from_user.id):
        await message.answer("Подпишись на канал!", reply_markup=get_sub_kb())
        return
    await message.answer("⚙️ **Настройки бота**\n\n🆔 Твой ID: `" + str(message.from_user.id) + "`", reply_markup=get_settings_kb(), parse_mode="Markdown")

@dp.message(Command("share"))
async def share_cmd(message: types.Message):
    uid
