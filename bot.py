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
    uid = message.from_user.id
    save_user(uid)
    try: await message.delete()
    except Exception: pass
    if not await check_subscription(uid):
        await message.answer("Подпишись на канал!", reply_markup=get_sub_kb())
        return
        
    me = await bot.get_me()
    ref = "https://t.me/" + str(me.username) + "?start=ref_" + str(uid)
    refs_count = get_referral_count(uid)
    
    txt = (
        "🎁 **Приглашай друзей в KINOrave!**\n\n"
        "👥 Приглашено друзей: **" + str(refs_count) + "**\n\n"
        "🔗 Твоя персональная ссылка:\n`" + ref + "`\n\n"
        "📌 *Делись ссылкой с друзьями и следи за своими бонусами!*"
    )
    await message.answer(txt, reply_markup=get_share_kb(me.username, uid), parse_mode="Markdown")

@dp.message(Command("stats"))
async def stats_cmd(message: types.Message):
    try: await message.delete()
    except Exception: pass
    await message.answer("📊 **Статистика KINOrave:**\n\n👥 Всего зрителей в боте: **" + str(get_users_count()) + "**\n🆔 Ваш ID: `" + str(message.from_user.id) + "`", parse_mode="Markdown")

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
        await message.answer("🌪 **Выбери параметры поиска:**", reply_markup=get_filter_kb(), parse_mode="Markdown")
    elif txt == "⚙️ Настройки":
        await message.answer("⚙️ **Настройки**\n🆔 `" + str(uid) + "`", reply_markup=get_settings_kb(), parse_mode="Markdown")
    elif txt == "🎁 Поделиться":
        me = await bot.get_me()
        ref = "https://t.me/" + str(me.username) + "?start=ref_" + str(uid)
        refs_count = get_referral_count(uid)
        txt_share = "🎁 **Приглашай друзей в KINOrave!**\n\n👥 Приглашено: **" + str(refs_count) + "**\n\n🔗 Ссылка:\n`" + ref + "`"
        await message.answer(txt_share, reply_markup=get_share_kb(me.username, uid), parse_mode="Markdown")

@dp.callback_query(lambda c: c.data == "check_sub")
async def sub_callback(callback: types.CallbackQuery):
    if await check_subscription(callback.from_user.id):
        await callback.message.delete()
        await callback.message.answer("🎉 Подписка подтверждена!", reply_markup=get_main_kb())
        await callback.message.answer("🎬 Добро пожаловать в KINOrave!", reply_markup=get_start_kb(), parse_mode="Markdown")
    else:
        await callback.answer("❌ Подпишись на канал для доступа!", show_alert=True)

# Функция для отправки случайного фильма (Кинорулетка)
async def send_random_movie(message_or_callback):
    url = "https://api.themoviedb.org/3/movie/top_rated"
    page = random.randint(1, 5) # Берем случайную страницу из топовых
    params = {"api_key": TMDB_API_KEY, "language": "ru-RU", "page": page}
    
    try:
        async with aiohttp.ClientSession(headers=HEADERS) as session:
            async with session.get(url, params=params, timeout=5) as r:
                if r.status == 200:
                    data = await r.json()
                    results = data.get('results', [])
                    if results:
                        item = random.choice(results)
                        t = item.get('title') or item.get('name') or "Фильм"
                        rat = item.get('vote_average', 0)
                        date = item.get('release_date') or item.get('first_air_date') or "0000"
                        year = date.split('-')[0]
                        poster = item.get('poster_path')
                        overview = item.get('overview') or "Описание пока отсутствует."
                        
                        caption = "🎲 **Кинорулетка KINOrave**\n\n🎬 **" + str(t) + "** (" + str(year) + ")\n⭐ Рейтинг: " + str(round(rat, 1)) + " / 10\n\n" + str(overview)[:350] + "..."
                        kb = get_movie_kb(t)
                        
                        target_msg = message_or_callback.message if isinstance(message_or_callback, types.CallbackQuery) else message_or_callback
                        
                        if poster:
                            try:
                                await target_msg.answer_photo(photo="https://image.tmdb.org/t/p/w500" + str(poster), caption=caption, reply_markup=kb, parse_mode="Markdown")
                                return
                            except Exception:
                                pass
                        await target_msg.answer(caption, reply_markup=kb, parse_mode="Markdown")
    except Exception as e:
        logging.error("Ошибка рулетки: " + str(e))

# Функция для вывода ТОП-10 фильмов недели
async def send_top_movies(callback: types.CallbackQuery):
    url = "https://api.themoviedb.org/3/trending/movie/week"
    params = {"api_key": TMDB_API_KEY, "language": "ru-RU"}
    
    try:
        async with aiohttp.ClientSession(headers=HEADERS) as session:
            async with session.get(url, params=params, timeout=5) as r:
                if r.status == 200:
                    data = await r.json()
                    items = data.get('results', [])[:10]
                    text = "🏆 **ТОП-10 фильмов недели по версии KINOrave:**\n\n"
                    for idx, item in enumerate(items, 1):
                        t = item.get('title') or item.get('name') or "Фильм"
                        rat = item.get('vote_average', 0)
                        text += f"{idx}. **{t}** ⭐ {round(rat, 1)}\n"
                    text += "\n💡 *Просто напиши название любого фильма из списка в чат для просмотра!*"
                    
                    await callback.message.edit_text(text, reply_markup=get_collections_kb(), parse_mode="Markdown")
    except Exception:
        await callback.answer("⚠️ Не удалось загрузить топ.", show_alert=True)

@dp.callback_query()
async def callbacks(callback: types.CallbackQuery):
    d = callback.data
    uid = callback.from_user.id
    
    if d == "roulette":
        await callback.answer("🎲 Крутим кинорулетку...")
        await send_random_movie(callback)
    elif d == "top_list":
        await send_top_movies(callback)
    elif d == "open_settings":
        await callback.message.edit_text("⚙️ **Настройки**\n🆔 `" + str(uid) + "`", reply_markup=get_settings_kb(), parse_mode="Markdown")
    elif d == "open_collections":
        await callback.message.edit_text("📁 **Выбери категорию подборки:**", reply_markup=get_collections_kb(), parse_mode="Markdown")
    elif d == "open_filter":
        await callback.message.edit_text("🌪 **Выбери параметры поиска:**", reply_markup=get_filter_kb(), parse_mode="Markdown")
    elif d == "open_share":
        me = await bot.get_me()
        ref = "https://t.me/" + str(me.username) + "?start=ref_" + str(uid)
        refs_count = get_referral_count(uid)
        txt = "🎁 **Приглашай друзей в KINOrave!**\n\n👥 Приглашено: **" + str(refs_count) + "**\n\n🔗 Ссылка:\n`" + ref + "`"
        await callback.message.edit_text(txt, reply_markup=get_share_kb(me.username, uid), parse_mode="Markdown")
    elif d == "back_start":
        await callback.message.edit_text("🎬 **KINOrave**\n\n🍿 Выбирай разделы или пиши название фильма.", reply_markup=get_start_kb(), parse_mode="Markdown")
    elif d.startswith("genre_") or d.startswith("col_"):
        await callback.answer("✅ Параметр применен! Нажми «Искать по каталогу» выше.", show_alert=True)
    elif d == "f_reset":
        await callback.answer("🔄 Фильтры сброшены!", show_alert=True)
    else:
        await callback.answer("Готово!", show_alert=True)

@dp.inline_query()
async def inline_search(query: InlineQuery):
    uid = query.from_user.id
    save_user(uid)
    if not await check_subscription(uid):
        return

    q = query.query.strip()
    if not q:
        url = "https://api.themoviedb.org/3/trending/all/day"
        params = {"api_key": TMDB_API_KEY, "language": "ru-RU"}
    else:
        url = "https://api.themoviedb.org/3/search/multi"
        params = {"api_key": TMDB_API_KEY, "language": "ru-RU", "query": q}

    res = []
    try:
        async with aiohttp.ClientSession(headers=HEADERS) as session:
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
                        caption = "🎬 **" + str(t) + "** (" + str(year) + ")\n⭐ Рейтинг: " + str(round(rat, 1)) + " / 10\n\n" + str(item.get('overview', 'Описание пока отсутствует.'))[:350]
                        res.append(InlineQueryResultArticle(
                            id=str(idx), title=t, description=desc, thumbnail_url=thumb,
                            input_message_content=InputTextMessageContent(message_text=caption, parse_mode="Markdown"),
                            reply_markup=get_movie_kb(t)
                        ))
        await query.answer(res, cache_time=1)
    except Exception as e:
        logging.error("Ошибка inline_search: " + str(e))

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
        async with aioh