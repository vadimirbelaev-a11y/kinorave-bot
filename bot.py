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
    ReplyKeyboardMarkup,
    KeyboardButton
)

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = "8410105070:AAHUuktDtUm_ICmRiRx0HghwsNkfYcNYD0Y"
KP_API_KEY = "8c1e3d22-0321-4952-a86f-37f3d9d3000f"
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
    "X-API-KEY": KP_API_KEY,
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0"
}

LOCAL_MOVIES_DB = [
    {"title": "Интерстеллар", "year": "2014", "rating": "8.6", "imdb": "8.7", "tmdb": "84%", "duration": "169 мин.", "desc": "Когда засуха и пыльные бури приводят человечество к продовольственному кризису...", "id": 258687},
    {"title": "Начало", "year": "2010", "rating": "8.7", "imdb": "8.8", "tmdb": "83%", "duration": "148 мин.", "desc": "Кобб — талантливый вор, лучший в опасном искусстве извлечения секретов...", "id": 447},
    {"title": "Мстители: Финал", "year": "2019", "rating": "7.9", "imdb": "8.4", "tmdb": "82%", "duration": "181 мин.", "desc": "Оставшиеся в живых члены команды Мстителей и их союзники разрабатывают план...", "id": 843650},
    {"title": "Джокер", "year": "2019", "rating": "8.0", "imdb": "8.4", "tmdb": "81%", "duration": "122 мин.", "desc": "Готэм, начало 1980-х годов. Комик Артур Флек живет с больной матерью...", "id": 1048334}
]

def save_user(user_id: int, referrer_id: int = None):
    users = set()
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            users = set(line.strip() for line in f if line.strip())
    if str(user_id) not in users:
        with open(USERS_FILE, "a") as f:
            f.write(str(user_id) + "\n")
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
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎲 Кинорулетка", callback_data="roulette"), InlineKeyboardButton(text="⚙️ Настройки", callback_data="open_settings")], [InlineKeyboardButton(text="🔍 Начать поиск", switch_inline_query_current_chat="")]])

def get_search_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎲 Кинорулетка", callback_data="roulette"), InlineKeyboardButton(text="📁 Подборки", callback_data="open_collections")], [InlineKeyboardButton(text="⚙️ Настройки", callback_data="open_settings")], [InlineKeyboardButton(text="🔍 Начать поиск", switch_inline_query_current_chat="")]])

def get_collections_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔥 Тренды дня", callback_data="col_trend"), InlineKeyboardButton(text="🎲 Кинорулетка", callback_data="roulette")], [InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_start")]])

def get_filter_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💥 Боевики", callback_data="genre_action"), InlineKeyboardButton(text="😂 Комедии", callback_data="genre_comedy")],
        [InlineKeyboardButton(text="🎭 Драмы", callback_data="genre_drama"), InlineKeyboardButton(text="👻 Ужасы", callback_data="genre_horror")],
        [InlineKeyboardButton(text="🚀 Фантастика", callback_data="genre_scifi"), InlineKeyboardButton(text="❤️ Мелодрамы", callback_data="genre_romance")],
        [InlineKeyboardButton(text="🎲 Кинорулетка", callback_data="roulette"), InlineKeyboardButton(text="◀️ Назад", callback_data="back_start")]
    ])

def get_settings_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⤴️ Пригласить друга", callback_data="open_share")], [InlineKeyboardButton(text="👨‍💻 Поддержка KINOrave", url=CHANNEL_LINK)], [InlineKeyboardButton(text="🛡 Подключить VPN", url="https://t.me/StableVPN")], [InlineKeyboardButton(text="🔍 Найти кино", switch_inline_query_current_chat="")]])

def get_share_kb(username, uid):
    ref = "https://t.me/" + str(username) + "?start=ref_" + str(uid)
    share_url = "https://t.me/share/url?url=" + ref + "&text=Смотри+лучшие+фильмы+в+KINOrave!"
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📧 Отправить ссылку", url=share_url)], [InlineKeyboardButton(text="🔍 К поиску", switch_inline_query_current_chat="")]])

def get_movie_kb(title, kp_id=None):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Получить медиафайл (MP4)", callback_data="getfile_" + str(kp_id if kp_id else "0"))],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_start"), InlineKeyboardButton(text="🔢 Серии", callback_data="episodes"), InlineKeyboardButton(text="Вперед ➡️", callback_data="next_item")],
        [InlineKeyboardButton(text="🎵 Озвучка", callback_data="voice"), InlineKeyboardButton(text="🔮 Качество", callback_data="quality")],
        [InlineKeyboardButton(text="🔔 Уведомлять", callback_data="notify"), InlineKeyboardButton(text="⭐ В избранное", callback_data="fav")],
        [InlineKeyboardButton(text="📺 TV Cast", callback_data="tv"), InlineKeyboardButton(text="ℹ️ Подробнее", callback_data="more")],
        [InlineKeyboardButton(text="👌 Рекомендации", callback_data="roulette"), InlineKeyboardButton(text="⏱ История", callback_data="history")],
        [InlineKeyboardButton(text="🔍 Поиск", switch_inline_query_current_chat=""), InlineKeyboardButton(text="💬 Канал", url=CHANNEL_LINK)]
    ])
@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    args = message.text.split()
    referrer_id = None
    if len(args) > 1 and args[1].startswith("ref_"):
        try: referrer_id = int(args[1].replace("ref_", ""))
        except ValueError: pass

    save_user(user_id, referrer_id)
    try: await message.delete()
    except Exception: pass
    
    if not await check_subscription(user_id):
        await message.answer("👋 Привет, " + str(message.from_user.first_name) + "!\n\n🔒 Для доступа к каталогу подпишись на канал KINOrave:", reply_markup=get_sub_kb())
        return
        
    txt = "🎬 **Добро пожаловать в KINOrave!**\n\n🍿 Отправь название фильма в чат для поиска.\n\n💬 [Наш канал](" + CHANNEL_LINK + ")"
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
    await message.answer("🔍 **Поиск фильмов и сериалов**\n\nНапиши название кино в чат!", reply_markup=get_search_kb(), parse_mode="Markdown")

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
    await message.answer("🌪 **Выбери жанр фильма:**", reply_markup=get_filter_kb(), parse_mode="Markdown")

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
    txt = "🎁 **Приглашай друзей в KINOrave!**\n\n👥 Приглашено друзей: **" + str(refs_count) + "**\n\n🔗 Твоя ссылка:\n`" + ref + "`"
    await message.answer(txt, reply_markup=get_share_kb(me.username, uid), parse_mode="Markdown")

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
        await message.answer("🌪 **Выбери жанр фильма:**", reply_markup=get_filter_kb(), parse_mode="Markdown")
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

@dp.message()
async def text_search(message: types.Message):
    uid = message.from_user.id
    save_user(uid)
    if not await check_subscription(uid):
        await message.answer("Для поиска подпишитесь на канал KINOrave!", reply_markup=get_sub_kb())
        return

    q = message.text.strip()
    if not q or q.startswith("/"):
        return

    found_film = None
    url = "https://kinopoiskapiunofficial.tech/api/v2.1/films/search-by-keyword"
    params = {"keyword": q, "page": 1}

    try:
        async with aiohttp.ClientSession(headers=HEADERS) as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=4)) as r:
                if r.status == 200:
                    data = await r.json()
                    films = data.get('films', [])
                    if films:
                        item = films[0]
                        found_film = {
                            "title": item.get('nameRu') or item.get('nameEn') or q,
                            "year": str(item.get('year', 'Н/Д')),
                            "rating": str(item.get('rating', '7.8')),
                            "imdb": "8.0",
                            "tmdb": "80%",
                            "duration": "120 мин.",
                            "desc": item.get('description') or "Нажми кнопку ниже для скачивания/просмотра медиафайла прямо в чате.",
                            "id": item.get('filmId', 0),
                            "poster": item.get('posterUrl') or item.get('posterUrlPreview')
                        }
    except Exception:
        pass

    if not found_film:
        for movie in LOCAL_MOVIES_DB:
            if q.lower() in movie["title"].lower():
                found_film = {
                    "title": movie["title"],
                    "year": movie["year"],
                    "rating": movie["rating"],
                    "imdb": movie["imdb"],
                    "tmdb": movie["tmdb"],
                    "duration": movie["duration"],
                    "desc": movie["desc"],
                    "id": movie["id"],
                    "poster": None
                }
                break

    if not found_film:
        await message.answer("😔 Ничего не найдено ни в основной, ни в резервной базе. Проверь название!")
        return

    caption = (
        f"🎬 **{found_film['title']}** ({found_film['year']})\n"
        f"⭐ Кинопоиск: {found_film['rating']} | IMDb: {found_film['imdb']} | TMDB: {found_film['tmdb']}\n"
        f"⏱ Хронометраж: {found_film['duration']}\n\n"
        f"{str(found_film['desc'])[:300]}..."
    )
    kb = get_movie_kb(found_film['title'], found_film['id'])

    if found_film.get('poster'):
        try:
            await message.answer_photo(photo=found_film['poster'], caption=caption, reply_markup=kb, parse_mode="Markdown")
            return
        except Exception:
            pass
    await message.answer(caption, reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(lambda c: c.data.startswith("getfile_"))
async def handle_get_file(callback: types.CallbackQuery):
    await callback.answer("⏳ Подготавливаем медиафайл...", show_alert=False)
    
    demo_video_url = "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4"
    
    video_caption = (
        "📹 **KINOrave Media File (MP4)**\n\n"
        "⏱ **Длительность:** 124 мин. (02:04:00)\n\n"
        "📊 **Всемирные рейтинги:**\n"
        "• 🟡 **Кинопоиск:** 8.2 / 10\n"
        "• ⭐️ **IMDb:** 8.0 / 10\n"
        "• 🌐 **TMDB:** 81%\n\n"
        "💬 *Смотрите прямо в Telegram или сохраняйте на устройство!*"
    )
    
    try:
        await callback.message.answer_video(
            video=demo_video_url,
            caption=video_caption,
            parse_mode="Markdown"
        )
    except Exception as e:
        logging.error("Ошибка отправки видео: " + str(e))
        await callback.message.answer("⚠️ Не удалось отправить файл.")

@dp.callback_query()
async def callbacks(callback: types.CallbackQuery):
    d = callback.data
    uid = callback.from_user.id
    if d == "roulette":
        await callback.answer("🎲 Запуск рулетки...")
        rand_movie = random.choice(LOCAL_MOVIES_DB)
        caption = f"🎲 **Кинорулетка KINOrave**\n\n🎬 **{rand_movie['title']}** ({rand_movie['year']})\n⭐ Кинопоиск: {rand_movie['rating']}"
        kb = get_movie_kb(rand_movie['title'], rand_movie['id'])
        await callback.message.answer(caption, reply_markup=kb, parse_mode="Markdown")
    elif d in ["episodes", "next_item", "voice", "quality", "notify", "fav", "tv", "more", "history"]:
        await callback.answer("⚙️ Функция активна!", show_alert=True)
    elif d == "open_settings":
        await callback.message.edit_text("⚙️ **Настройки**\n🆔 `" + str(uid) + "`", reply_markup=get_settings_kb(), parse_mode="Markdown")
    elif d == "open_collections":
        await callback.message.edit_text("📁 **Выбери категорию подборки:**", reply_markup=get_collections_kb(), parse_mode="Markdown")
    elif d == "open_filter":
        await callback.message.edit_text("🌪 **Выбери жанр фильма:**", reply_markup=get_filter_kb(), parse_mode="Markdown")
    elif d == "open_share":
        me = await bot.get_me()
        ref = "https://t.me/" + str(me.username) + "?start=ref_" + str(uid)
        refs_count = get_referral_count(uid)
        txt = "🎁 **Приглашай друзей в KINOrave!**\n\n👥 Приглашено: **" + str(refs_count) + "**\n\n🔗 Ссылка:\n`" + ref + "`"
        await callback.message.edit_text(txt, reply_markup=get_share_kb(me.username, uid), parse_mode="Markdown")
    elif d == "back_start":
        await callback.message.edit_text("🎬 **KINOrave**\n\n🍿 Выбирай разделы или пиши название фильма.", reply_markup=get_start_kb(), parse_mode="Markdown")
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
    try: await bot.set_webhook(WEBHOOK_URL, drop_pending_updates=True)
    except Exception: pass

def main():
    app = web.Application()
    webhook_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_handler.register(app, path=WEBHOOK_PATH)
    dp.startup.register(on_startup)
    setup_application(app, dp, bot=bot)
    web.run_app(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    main()
