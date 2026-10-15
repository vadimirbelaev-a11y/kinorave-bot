import os
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

def save_user(user_id):
    users = set()
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            users = set(line.strip() for line in f if line.strip())
    if str(user_id) not in users:
        with open(USERS_FILE, "a") as f:
            f.write(str(user_id) + "\n")

def get_users_count():
    if not os.path.exists(USERS_FILE):
        return 0
    with open(USERS_FILE, "r") as f:
        return len(set(line.strip() for line in f if line.strip()))

async def check_subscription(user_id):
    try:
        m = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        return m.status in ["creator", "administrator", "member"]
    except Exception:
        return True

def get_sub_kb():
    b1 = InlineKeyboardButton(text="📢 Подписаться на KINOrave", url=CHANNEL_LINK)
    b2 = InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check_sub")
    return InlineKeyboardMarkup(inline_keyboard=[[b1], [b2]])

def get_main_kb():
    r1 = [KeyboardButton(text="🔍 Поиск"), KeyboardButton(text="📁 Подборки"), KeyboardButton(text="🌪 Фильтр")]
    r2 = [KeyboardButton(text="⚙️ Настройки"), KeyboardButton(text="🎁 Поделиться")]
    return ReplyKeyboardMarkup(keyboard=[r1, r2], resize_keyboard=True)

def get_start_kb():
    b1 = InlineKeyboardButton(text="💡 Инструкция", callback_data="guide")
    b2 = InlineKeyboardButton(text="⚙️ Настройки", callback_data="open_settings")
    b3 = InlineKeyboardButton(text="🔍 Начать поиск", switch_inline_query_current_chat="")
    return InlineKeyboardMarkup(inline_keyboard=[[b1, b2], [b3]])

def get_search_kb():
    b1 = InlineKeyboardButton(text="💡 Инструкция", callback_data="guide")
    b2 = InlineKeyboardButton(text="⤴️ Поделиться", callback_data="open_share")
    b3 = InlineKeyboardButton(text="📁 Подборки", callback_data="open_collections")
    b4 = InlineKeyboardButton(text="🌪 Фильтры", callback_data="open_filter")
    b5 = InlineKeyboardButton(text="⚙️ Настройки", callback_data="open_settings")
    b6 = InlineKeyboardButton(text="🔍 Начать поиск", switch_inline_query_current_chat="")
    return InlineKeyboardMarkup(inline_keyboard=[[b1, b2], [b3, b4], [b5], [b6]])

def get_collections_kb():
    b1 = InlineKeyboardButton(text="🔥 Тренды дня", callback_data="col_trend")
    b2 = InlineKeyboardButton(text="🌟 Популярное", callback_data="col_pop")
    b3 = InlineKeyboardButton(text="🎬 Новинки фильмов", callback_data="col_movies")
    b4 = InlineKeyboardButton(text="📺 Новинки сериалов", callback_data="col_shows")
    b5 = InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_start")
    return InlineKeyboardMarkup(inline_keyboard=[[b1, b2], [b3, b4], [b5]])

def get_filter_kb():
    b1 = InlineKeyboardButton(text="💥 Боевики", callback_data="genre_action")
    b2 = InlineKeyboardButton(text="😂 Комедии", callback_data="genre_comedy")
    b3 = InlineKeyboardButton(text="🎭 Драмы", callback_data="genre_drama")
    b4 = InlineKeyboardButton(text="👻 Ужасы", callback_data="genre_horror")
    b5 = InlineKeyboardButton(text="🚀 Фантастика", callback_data="genre_scifi")
    b6 = InlineKeyboardButton(text="❤️ Мелодрамы", callback_data="genre_romance")
    b7 = InlineKeyboardButton(text="🔄 Сбросить фильтр", callback_data="f_reset")
    b8 = InlineKeyboardButton(text="🔍 Искать по каталогу", switch_inline_query_current_chat="")
    b9 = InlineKeyboardButton(text="◀️ Назад", callback_data="back_start")
    return InlineKeyboardMarkup(inline_keyboard=[[b1, b2], [b3, b4], [b5, b6], [b7], [b8], [b9]])

def get_settings_kb():
    b1 = InlineKeyboardButton(text="
