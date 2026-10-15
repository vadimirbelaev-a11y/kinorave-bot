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
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📢 Подписаться на KINOrave", url=CHANNEL_LINK)], [InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check_sub")]])

def get_main_kb():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🔍 Поиск"), KeyboardButton(text="📁 Подборки"), KeyboardButton(text="🌪 Фильтр")], [KeyboardButton(text="⚙️ Настройки"), KeyboardButton(text="🎁 Поделиться")]], resize_keyboard=True)

def get_start_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💡 Инструкция", callback_data="guide"), InlineKeyboardButton(text="⚙️ Настройки", callback_data="open_settings")], [InlineKeyboardButton(text="🔍 Начать поиск", switch_inline_query_current_chat="")]])

def get_search_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💡 Инструкция", callback_data="guide"), InlineKeyboardButton(text="⤴️ Поделиться", callback_data="open_share")], [InlineKeyboardButton(text="📁 Подборки", callback_data="open_collections"), InlineKeyboardButton(text="🌪 Фильтры", callback_data="open_filter")], [InlineKeyboardButton(text="⚙️ Настройки", callback_data="open_settings")], [InlineKeyboardButton(text="🔍 Начать поиск", switch_inline_query_current_chat="")]])

def get_collections_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔥 Тренды дня", callback_data="col_trend"), InlineKeyboardButton(text="🌟 Популярное", callback_data="col_pop")], [InlineKeyboardButton(text="🎬 Новинки фильмов", callback_data="col_movies"), InlineKeyboardButton(text="📺 Новинки сериалов", callback_data="col_shows")], [InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_start")]])

def get_filter_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💥 Боевики", callback_data="genre_action"), InlineKeyboardButton(text="😂 Комедии", callback_data="genre_comedy")], [InlineKeyboardButton(text="🎭 Драмы", callback_data="genre_drama"), InlineKeyboardButton(text="👻 Ужасы", callback_data="genre_horror")], [InlineKeyboardButton(text="🚀 Фантастика", callback_data="genre_scifi"), InlineKeyboardButton(text="❤️ Мелодрамы", callback_data="genre_romance")], [InlineKeyboardButton(text="🔄 Сбросить фильтр", callback_data="f_reset")], [InlineKeyboardButton(text="🔍 Искать по каталогу", switch_inline_query_current_chat="")], [InlineKeyboardButton(text="◀️ Назад", callback_data="back_start")]])

def get_settings_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⤴️ Пригласить друга", callback_data="open_share")], [InlineKeyboardButton(text="👨‍💻 Наш канал", url=CHANNEL_LINK)], [InlineKeyboardButton(text="🛡 Подключить VPN", url="https://t.me/StableVPN")], [InlineKeyboardButton(text="🔍 Найти кино", switch_inline_query_current_chat="")]])

def get_share_kb(username, uid):
    ref = "https://t.me/" + str(username) + "?start=ref_" + str(uid)
    share_url = "https://t.me/share/url?url=" + ref + "&text=Смотри+фильмы+в+KINOrave!"
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📧 Отправить ссылку", url=share_url)], [InlineKeyboardButton(text="🔍 К поиску", switch_inline_query_current_chat="")]])

def get_movie_kb(title):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎙 Озвучка", callback_data="voice"), InlineKeyboardButton(text="🔮 Качество", callback_data="quality")], [InlineKeyboardButton(text="💬 Наш канал", url=CHANNEL_LINK), InlineKeyboardButton(text="⤴️ Поделиться", switch_inline_query=title)], [InlineKeyboardButton(text="📺 Трансляция TV", callback_data="tv"), InlineKeyboardButton(text="ℹ️ Подробнее", callback_data="more")], [InlineKeyboardButton(text="🔍 Искать дальше", switch_inline_query_current_chat="")]])

@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    save_user(message.from_user.id)
    try: await message.delete()
    except Exception: pass
    if not await check_subscription(message.from_user.id):
        await message.answer("👋 Привет, " + str(message.from_user.first_name) + "!\n\n🔒 Для доступа к поиску подпишись на канал KINOrave:", reply_markup=get_sub_kb())
        return
    await message.answer("🎬 **Добро пожаловать в KINOrave!**\n\n🍿 Нажми кнопку поиска ниже или просто отправь название фильма в чат.\n\n💬 [Наш канал](" + CHANNEL_LINK + ")", reply_markup=get_start_kb(), parse_mode="Markdown", disable_web_page_preview=True)
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
    await message.answer("🌪 **Выбери жанр для фильтрации:**", reply_markup=get_filter_kb(), parse_mode="Markdown")

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
    save_user(message.from_user.id)
    try: await message.delete()
    except Exception: pass
    if not await check_subscription(message.from_user.id):
        await message.answer("Подпишись на канал!", reply_markup=get_sub_kb())
        return
    me = await bot.get_me()
    ref = "https://t.me/" + str(me.username) + "?start=ref_" + str(message.from_user.id)
    await message.answer("🎁 **Приглашай друзей в KINOrave!**\n\n🔗 Твоя персональная ссылка:\n`" + ref + "`", reply_markup=get_share_kb(me.username, message.from_user.id), parse_mode="Markdown")

@dp.message(Command("stats"))
async def stats_cmd(message: types.Message):
    try: await message.delete()
    except Exception: pass
    await message.answer("📊 **Статистика KINOrave:**\n\n👥 Всего зрителей: **" + str(get_users_count()) + "**\n🆔 Ваш ID: `" + str(message.from_user.id) + "`", parse_mode="Markdown")

@dp.message(lambda m: m.text in ["🔍 Поиск", "📁 Подборки", "🌪 Фильтр", "⚙️ Настройки", "🎁 Поделиться"])
async def reply_handler(message: types.Message):
    uid = message.from_user.id
    save_user(uid)
    if not await check_subscription(uid):
        await message.answer("Подпишись на канал!", reply_markup=get_sub_kb())
        return
    txt = message.text
    if txt == "🔍 Поиск":
        await message.answer("🔍 **Поиск фильмов и сериалов**\n\nНапиши название кино в чат!", reply_markup=get_search_kb(), parse_mode="Markdown")
    elif txt == "📁 Подборки":
        await message.answer("📁 **Выбери категорию подборки:**", reply_markup=get_collections_kb(), parse_mode="Markdown")
    elif txt == "🌪 Фильтр":
        await message.answer("🌪 **Выбери жанр для фильтрации:**", reply_markup=get_filter_kb(), parse_mode="Markdown")
    elif txt == "⚙️ Настройки":
        await message.answer("⚙️ **Настройки**\n🆔 `" + str(uid) + "`", reply_markup=get_settings_kb(), parse_mode="Markdown")
    elif txt == "🎁 Поделиться":
        me = await bot.get_me()
        ref = "https://t.me/" + str(me.username) + "?start=ref_" + str(uid)
        await message.answer("🎁 **Твоя ссылка:**\n`" + ref + "`", reply_markup=get_share_kb(me.username, uid), parse_mode="Markdown")

@dp.callback_query(lambda c: c.data == "check_sub")
async def sub_callback(callback: types.CallbackQuery):
    if await check_subscription(callback.from_user.id):
        await callback.message.delete()
        await callback.message.answer("🎉 Подписка подтверждена!", reply_markup=get_main_kb())
        await callback.message.answer("🎬 Добро пожаловать в KINOrave!", reply_markup=get_start_kb(), parse_mode="Markdown")
    else:
        await callback.answer("❌ Подпишись на канал для доступа!", show_alert=True)

@dp.inline_query()
async def inline_search(query: InlineQuery):
    uid = query.from_user.id
    save_user(uid)
    if not await check_subscription(uid):
        return

    q = query.query.strip()
    url = "https://api.themoviedb.org/3/search/multi"
    params = {"api_key": TMDB_API_KEY, "language": "ru-RU", "query": q if q else "popular"}

    res = []
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=5) as r:
                if r.status == 200:
                    data = await r.json()
                    for idx, item in enumerate(data.get('results', [])[:12]):
                        t = item.get('title') or item.get('name') or "Фильм"
                        rat = item.get('vote_average', 0)
                        date = item.get('release_date') or item.get('first_air_date') or "0000"
                        year = date.split('-')[0]
                        poster = item.get('poster_path')
                        desc = "tmdb: " + str(round(rat, 1)) + " | " + str(year)
                        thumb = "https://image.tmdb.org/t/p/w185" + str(poster) if poster else "https://via.placeholder.com/150"
                        caption = "🎬 **" + str(t) + "** (" + str(year) + ")\n⭐ Рейтинг: " + str(round(rat, 1)) + " / 10\n\n" + str(item.get('overview', 'Нет описания.'))[:350]
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
        await message.answer("Для поиска подпишитесь на канал KINOrave!", reply_markup=get_sub_kb())
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
                    await message.answer("⚠️ Ошибка сервера кинобазы. Попробуй еще раз!")
                    return
                data = await r.json()
                items = data.get('results', [])
                if not items:
                    await message.answer("😔 Ничего не найдено. Проверь название и попробуй снова!")
                    return
                item = items[0]
                t = item.get('title') or item.get('name') or "Фильм"
                rat = item.get('vote_average', 0)
                date = item.get('release_date') or item.get('first_air_date') or "0000"
                year = date.split('-')[0]
                poster = item.get('poster_path')
                caption = "🎬 **" + str(t) + "** (" + str(year) + ")\n⭐ Рейтинг: " + str(round(rat, 1)) + " / 10\n\n" + str(item.get('overview', 'Нет описания.'))[:350]
                kb = get_movie_kb(t)
                if poster:
                    try:
                        await message.answer_photo(photo="https://image.tmdb.org/t/p/w500" + str(poster), caption=caption, reply_markup=kb, parse_mode="Markdown")
                        return
                    except Exception:
                        pass
                await message.answer(caption, reply_markup=kb, parse_mode="Markdown")
    except Exception:
        await message.answer("⚠️ Произошла ошибка при поиске.")

@dp.callback_query()
async def callbacks(callback: types.CallbackQuery):
    d = callback.data
    uid = callback.from_user.id
    if d == "open_settings":
        await callback.message.edit_text("⚙️ **Настройки**\n🆔 `" + str(uid) + "`", reply_markup=get_settings_kb(), parse_mode="Markdown")
    elif d == "open_collections":
        await callback.message.edit_text("📁 **Выбери категорию подборки:**", reply_markup=get_collections_kb(), parse_mode="Markdown")
    elif d == "open_filter":
        await callback.message.edit_text("🌪 **Выбери жанр для фильтрации:**", reply_markup=get_filter_kb(), parse_mode="Markdown")
    elif d == "open_share":
        me = await bot.get_me()
        ref = "https://t.me/" + str(me.username) + "?start=ref_" + str(uid)
        await callback.message.edit_text("🎁 **Твоя ссылка:**\n`" + ref + "`", reply_markup=get_share_kb(me.username, uid), parse_mode="Markdown")
    elif d == "back_start":
        await callback.message.edit_text("🎬 **KINOrave**\n\n🍿 Выбирай разделы или пиши название фильма.", reply_markup=get_start_kb(), parse_mode="Markdown")
    elif d.startswith("genre_") or d.startswith("col_"):
        await callback.answer("✅ Категория выбрана! Нажми «Искать по каталогу» выше.", show_alert=True)
    elif d == "f_reset":
        await callback.answer("🔄 Фильтры сброшены!", show_alert=True)
    else:
        await callback.answer("Готово!", show_alert=True)

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
