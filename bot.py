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
WEBHOOK_PATH = f"/bot/{BOT_TOKEN}"
WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}"
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
            f.write(f"{user_id}\n")

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
        [InlineKeyboardButton(text="🎬 Руководство", callback_data="video_guide"), InlineKeyboardButton(text="⚙️ Настройки", callback_data="open_settings")],
        [InlineKeyboardButton(text="🔍 Начать поиск", switch_inline_query_current_chat="")]
    ])

def get_search_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💡 Как искать", callback_data="video_guide"), InlineKeyboardButton(text="⤴️ Поделиться", callback_data="open_share")],
        [InlineKeyboardButton(text="🕒 История", callback_data="history"), InlineKeyboardButton(text="⭐ Избранное", callback_data="fav")],
        [InlineKeyboardButton(text="📁 Коллекции", callback_data="open_collections"), InlineKeyboardButton(text="🌪 Фильтры", callback_data="open_filter")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="open_settings")],
        [InlineKeyboardButton(text="🔍 Начать поиск", switch_inline_query_current_chat="")]
    ])

def get_collections_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔥 Тренды дня", callback_data="col_today")],
        [InlineKeyboardButton(text="🌟 Хиты", callback_data="col_pop")],
        [InlineKeyboardButton(text="🎬 Новинки фильмов", callback_data="col_new_movies")],
        [InlineKeyboardButton(text="📺 Новинки сериалов", callback_data="col_new_shows")],
        [InlineKeyboardButton(text="🔎 Поиск", callback_data="col_search")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_start")]
    ])

def get_filter_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Рейтинг от", callback_data="f_rat_from"), InlineKeyboardButton(text="📊 Рейтинг до", callback_data="f_rat_to")],
        [InlineKeyboardButton(text="📁 Категория", callback_data="f_type"), InlineKeyboardButton(text="🏷 Жанр", callback_data="f_genre")],
        [InlineKeyboardButton(text="🎲 Случайный выбор", callback_data="f_random"), InlineKeyboardButton(text="🔄 Сбросить", callback_data="f_reset")],
        [InlineKeyboardButton(text="🔍 Начать поиск", switch_inline_query_current_chat="")],
        [InlineKeyboardButton(text="🔍 Применить фильтр", callback_data="f_apply")]
    ])

def get_settings_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎟 Промокод", callback_data="promos"), InlineKeyboardButton(text="⤴️ Пригласить", callback_data="open_share")],
        [InlineKeyboardButton(text="👨‍💻 Поддержка", url=CHANNEL_LINK)],
        [InlineKeyboardButton(text="🛡 Подключить VPN", url="https://t.me/StableVPN")],
        [InlineKeyboardButton(text="🔍 Найти кино", switch_inline_query_current_chat="")]
    ])

def get_share_kb(username, uid):
    ref = f"https://t.me/{username}?start=ref_{uid}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📧 Отправить", url=f"https://t.me/share/url?url={ref}&text=Смотри+фильмы+в+KINOrave!")],
        [InlineKeyboardButton(text="🔗 Фильм", switch_inline_query_current_chat=""), InlineKeyboardButton(text="🔗 Подборка", callback_data="open_collections")],
        [InlineKeyboardButton(text="🔍 К поиску", switch_inline_query_current_chat="")]
    ])

def get_movie_kb(title):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎙 Озвучка", callback_data="voice"), InlineKeyboardButton(text="🔮 Качество", callback_data="quality")],
        [InlineKeyboardButton(text="💬 Наш канал", url=CHANNEL_LINK), InlineKeyboardButton(text="⤴️ Поделиться", switch_inline_query=title)],
        [InlineKeyboardButton(text="📺 TV", callback_data="tv"), InlineKeyboardButton(text="ℹ️ Детали", callback_data="more")],
        [InlineKeyboardButton(text="🔍 Искать дальше", switch_inline_query_current_chat="")]
    ])

@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    save_user(message.from_user.id)
    try: await message.delete()
    except Exception: pass
    if not await check_subscription(message.from_user.id):
        await message.answer(f"👋 Салют, {message.from_user.first_name}!\n\n🔒 Подпишись на канал KINOrave:", reply_markup=get_sub_kb())
        return
    await message.answer(f"🎬 **Добро пожаловать в KINOrave!**\n\n🍿 Жми кнопки или отправь название фильма.", reply_markup=get_start_kb(), parse_mode="Markdown")
    await message.answer("Главное меню:", reply_markup=get_main_kb())

@dp.message(Command("search"))
async def search_cmd(message: types.Message):
    save_user(message.from_user.id)
    try: await message.delete()
    except Exception: pass
    if not await check_subscription(message.from_user.id):
        await message.answer("Подпишись на канал!", reply_markup=get_sub_kb())
        return
    await message.answer("🔍 **Поиск фильмов и сериалов**", reply_markup=get_search_kb(), parse_mode="Markdown")

@dp.message(Command("collections"))
async def collections_cmd(message: types.Message):
    save_user(message.from_user.id)
    try: await message.delete()
    except Exception: pass
    if not await check_subscription(message.from_user.id):
        await message.answer("Подпишись на канал!", reply_markup=get_sub_kb())
        return
    await message.answer("📁 **Тематические коллекции**", reply_markup=get_collections_kb(), parse_mode="Markdown")

@dp.message(Command("filter"))
async def filter_cmd(message: types.Message):
    save_user(message.from_user.id)
    try: await message.delete()
    except Exception: pass
    if not await check_subscription(message.from_user.id):
        await message.answer("Подпишись на канал!", reply_markup=get_sub_kb())
        return
    await message.answer("⚙️ **Параметры фильтрации**", reply_markup=get_filter_kb(), parse_mode="Markdown")

@dp.message(Command("settings"))
async def settings_cmd(message: types.Message):
    save_user(message.from_user.id)
    try: await message.delete()
    except Exception: pass
    if not await check_subscription(message.from_user.id):
        await message.answer("Подпишись на канал!", reply_markup=get_sub_kb())
        return
    await message.answer(f"⚙️ **Настройки**\n🆔 `{message.from_user.id}`", reply_markup=get_settings_kb(), parse_mode="Markdown")

@dp.message(Command("share"))
async def share_cmd(message: types.Message):
    save_user(message.from_user.id)
    try: await message.delete()
    except Exception: pass
    if not await check_subscription(message.from_user.id):
        await message.answer("Подпишись на канал!", reply_markup=get_sub_kb())
        return
    me = await bot.get_me()
    ref = f"https://t.me/{me.username}?start=ref_{message.from_user.id}"
    await message.answer(f"🎁 **Твоя ссылка:**\n`{ref}`", reply_markup=get_share_kb(me.username, message.from_user.id), parse_mode="Markdown")

@dp.message(Command("stats"))
async def stats_cmd(message: types.Message):
    try: await message.delete()
    except Exception: pass
    await message.answer(f"📊 Пользователей: **{get_users_count()}**\n🆔 Ваш ID: `{message.from_user.id}`", parse_mode="Markdown")

@dp.message(lambda m: m.text in ["🔍 Поиск", "📁 Подборки", "🌪 Фильтр", "⚙️ Настройки", "🎁 Поделиться"])
async def reply_handler(message: types.Message):
    uid = message.from_user.id
    save_user(uid)
    if not await check_subscription(uid):
        await message.answer("Подпишись на канал!", reply_markup=get_sub_kb())
        return
    txt = message.text
    if txt == "🔍 Поиск":
        await message.answer("🔍 **Поиск**", reply_markup=get_search_kb(), parse_mode="Markdown")
    elif txt == "📁 Подборки":
        await message.answer("📁 **Подборки**", reply_markup=get_collections_kb(), parse_mode="Markdown")
    elif txt == "🌪 Фильтр":
        await message.answer("⚙️ **Фильтры**", reply_markup=get_filter_kb(), parse_mode="Markdown")
    elif txt == "⚙️ Настройки":
        await message.answer(f"⚙️ **Настройки**\n🆔 `{uid}`", reply_markup=get_settings_kb(), parse_mode="Markdown")
    elif txt == "🎁 Поделиться":
        me = await bot.get_me()
        ref = f"https://t.me/{me.username}?start=ref_{uid}"
        await message.answer(f"🎁 **Ссылка:**\n`{ref}`", reply_markup=get_share_kb(me.username, uid), parse_mode="Markdown")

@dp.callback_query(lambda c: c.data == "check_sub")
async def sub_callback(callback: types.CallbackQuery):
    if await check_subscription(callback.from_user.id):
        await callback.message.delete()
        await callback.message.answer("🎉 Подписка подтверждена!", reply_markup=get_main_kb())
        await callback.message.answer("🎬 Добро пожаловать!", reply_markup=get_start_kb(), parse_mode="Markdown")
    else:
        await callback.answer("❌ Вы ещё не подписаны!", show_alert=True)

@dp.inline_query()
async def inline_search(query: InlineQuery):
    uid = query.from_user.id
    save_user(uid)
    if not await check_subscription(uid) or not query.query.strip():
        return
    url = "https://api.themoviedb.org/3/search/multi"
    params = {"api_key": TMDB_API_KEY, "language": "ru-RU", "query": query.query.strip()}
    res = []
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=5) as r:
                if r.status == 200:
                    data = await r.json()
                    for idx, item in enumerate(data.get('results', [])[:10]):
                        t = item.get('title') or item.get('name') or "Фильм"
                        rat = item.get('vote_average', 0)
                        date = item.get('release_date') or item.get('first_air_date') or "0000"
                        year = date.split('-')[0]
                        poster = item.get('poster_path')
                        desc = f"tmdb: {rat:.1f} | {year}"
                        thumb = f"https://image.tmdb.org/t/p/w185{poster}" if poster else "https://via.placeholder.com/150"
                        caption = f"🎬 **{t}** ({year})\n⭐ Рейтинг: {rat:.1f}\n\n{item.get('overview', 'Нет описания.')[:300]}"
                        res.append(InlineQueryResultArticle(
                            id=str(idx), title=t, description=desc, thumbnail_url=thumb,
                            input_message_content=InputTextMessageContent(message_text=caption, parse_mode="Markdown"),
                            reply_markup=get_movie_kb(t)
                        ))
        await query.answer(res, cache_time=1)
    except Exception:
        pass

@dp.message()
async def text_search(message: types.Message):
    uid = message.from_user.id
    save_user(uid)
    if not await check_subscription(uid):
        await message.answer("Подпишись на канал!", reply_markup=get_sub_kb())
        return
    q = message.text
    if not q or q.startswith("/"):
        return
    url = "https://api.themoviedb.org/3/search/multi"
    params = {"api_key": TMDB_API_KEY, "language": "ru-RU", "query": q}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=10) as r:
                if r.status != 200:
                    return
                data = await r.json()
                items = data.get('results', [])
                if not items:
                    await message.answer("😔 Ничего не найдено.")
                    return
                item = items[0]
                t = item.get('title') or item.get('name') or "Фильм"
                rat = item.get('vote_average', 0)
                date = item.get('release_date') or item.get('first_air_date') or "0000"
                year = date.split('-')[0]
                poster = item.get('poster_path')
                caption = f"🎬 **{t}** ({year})\n⭐ Рейтинг: {rat:.1f}\n\n{item.get('overview', 'Нет описания.')[:300]}"
                kb = get_movie_kb(t)
                if poster:
                    try:
                        await message.answer_photo(photo=f"https://image.tmdb.org/t/p/w500{poster}", caption=caption, reply_markup=kb, parse_mode="Markdown")
                        return
                    except Exception:
                        pass
                await message.answer(caption, reply_markup=kb, parse_mode="Markdown")
    except Exception:
        pass

@dp.callback_query()
async def callbacks(callback: types.CallbackQuery):
    d = callback.data
    uid = callback.from_user.id
    if d == "open_settings":
        await callback.message.edit_text(f"⚙️ **Настройки**\n🆔 `{uid}`", reply_markup=get_settings_kb(), parse_mode="Markdown")
    elif d == "open_collections":
        await callback.message.edit_text("📁 **Коллекции**", reply_markup=get_collections_kb(), parse_mode="Markdown")
    elif d == "open_filter":
        await callback.message.edit_text("⚙️ **Фильтры**", reply_markup=get_filter_kb(), parse_mode="Markdown")
    elif d == "open_share":
        me = await bot.get_me()
        ref = f"https://t.me/{me.username}?start=ref_{uid}"
        await callback.message.edit_text(f"🎁 **Ссылка:**\n`{ref}`", reply_markup=get_share_kb(me.username, uid), parse_mode="Markdown")
    elif d == "back_start":
        await callback.message.edit_text("🎬 **KINOrave**", reply_markup=get_start_kb(), parse_mode="Markdown")
    else:
        await callback.answer("В разработке!", show_alert=True)

async def on_startup(bot: Bot):
    await bot.set_my_commands([
        BotCommand(command="start", description="Запустить"),
        BotCommand(command="search", description="Поиск"),
        BotCommand(command="collections", description="Подборки"),
        BotCommand(command="filter", description="Фильтр"),
        BotCommand(command="settings", description="Настройки"),
        BotCommand(command="share", description="Поделиться"),
        BotCommand(command="stats", description="Статистика")
    ])
    try:
        await bot.set_webhook(WEBHOOK_URL, drop_pending_updates=True)
    except Exception:
        pass

def main():
    app = web.Application()
    webhook_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_handler.register(app, path=WEBHOOK_PATH)
    dp.startup.register(on_startup)
    setup_application(app, dp, bot=bot)
    web.run_app(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    main()
