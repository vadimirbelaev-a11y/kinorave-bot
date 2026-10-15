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
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Подписаться на KINOrave", url=CHANNEL_LINK)],
        [InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check_sub")]
    ])

def get_main_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔍 Поиск"), KeyboardButton(text="📁 Подборки"), KeyboardButton(text="🌪 Фильтр")],
            [KeyboardButton(text="⚙️ Настройки"), KeyboardButton(text="🎁 Поделиться")]
        ],
        resize_keyboard=True
    )

def get_start_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💡 Инструкция", callback_data="guide"), InlineKeyboardButton(text="⚙️ Настройки", callback_data="open_settings")],
        [InlineKeyboardButton(text="🔍 Начать поиск", switch_inline_query_current_chat="")]
    ])

def get_search_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💡 Инструкция", callback_data="guide"), InlineKeyboardButton(text="⤴️ Поделиться", callback_data="open_share")],
        [InlineKeyboardButton(text="📁 Подборки", callback_data="open_collections"), InlineKeyboardButton(text="🌪 Фильтры", callback_data="open_filter")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="open_settings")],
        [InlineKeyboardButton(text="🔍 Начать поиск", switch_inline_query_current_chat="")]
    ])

def get_collections_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔥 Тренды дня", callback_data="col_trend"), InlineKeyboardButton(text="🌟 Популярное", callback_data="col_pop")],
        [InlineKeyboardButton(text="🎬 Новинки фильмов", callback_data="col_movies"), Inline
