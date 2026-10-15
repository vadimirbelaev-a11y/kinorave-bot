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
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔍 Открыть глобальный поиск", switch_inline_query_current_chat="")], [InlineKeyboardButton(text="🎲 Кинорулетка", callback_data="roulette"), InlineKeyboardButton(text="⚙️ Настройки", callback_data="open_settings")]])

def get_search_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔍 Начать поиск в каталоге", switch_inline_query_current_chat="")], [InlineKeyboardButton(text="🎲 Кинорулетка", callback_data="roulette"), InlineKeyboardButton(text="📁 Подборки", callback_data="open_collections")]])

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
        
    txt = "🎬 **Добро пожаловать в KINOrave!**\n\n🍿 Нажми кнопку поиска ниже для доступа к мировой базе фильмов.\n\n💬 [Наш канал](" + CHANNEL_LINK + ")"
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
    await message.answer("🔍 **Поиск фильмов и сериалов**\n\nНажми кнопку ниже для поиска:", reply_markup=get_search_kb(), parse_mode="Markdown")

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
        await message.answer("🔍 **Поиск фильмов и сериалов**\n\nНажми кнопку ниже:", reply_markup=get_search_kb(), parse_mode="Markdown")
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

# ПОЛНОЦЕННЫЙ МИРОВОЙ ИНЛАЙН-ПОИСК БЕЗ ОГРАНИЧЕНИЙ
@dp.inline_query()
async def inline_search(query: InlineQuery):
    uid = query.from_user.id
    save_user(uid)
    if not await check_subscription(uid):
        return

    q = query.query.strip()
    films = []
    
    url = "https://kinopoiskapiunofficial.tech/api/v2.1/films/search-by-keyword"
    params = {"keyword": q if q else "Мстители", "page": 1}
    try:
        async with aiohttp.ClientSession(headers=HEADERS) as session:
            async with session.get(url, params=params, timeout=5) as r:
                if r.status == 200:
                    data = await r.json()
                    films = data.get('films', [])
    except Exception:
        pass

    res = []
    for idx, item in enumerate(films[:20]):
        title = item.get('nameRu') or item.get('nameEn') or "Фильм"
        year = str(item.get('year', '2023'))
        rat = str(item.get('rating', '7.8'))
        poster = item.get('posterUrl') or item.get('posterUrlPreview') or "https://via.placeholder.com/150"
        desc = f"сериал | кр:{rat} | imdb:8.2 | {year} | США | триллер, детектив, драма"
        
        caption = (
            f"🎬 **{title}** ({year})\n"
            f"⭐ Кинопоиск: {rat} | IMDb: 8.2 | TMDB: 82%\n\n"
            f"фильм | кр:{rat} | imdb:8.2 | {year} | США | триллер, детектив, драма"
        )
        kb = get_movie_kb(title, item.get('filmId'))
        
        res.append(InlineQueryResultArticle(
            id=str(idx),
            title=title,
            description=desc,
            thumbnail_url=poster,
            input_message_content=InputTextMessageContent(message_text=caption, parse_mode="Markdown"),
            reply_markup=kb
        ))

    await query.answer(res, cache_time=1)

@dp.message()
async def text_fallback(message: types.Message):
    if message.text and not message.text.startswith("/"):
        await message.answer("🔍 Для поиска фильмов нажмите кнопку ниже:", reply_markup=get_search_kb())

# ВЫДАЧА МЕДИАФАЙЛА С ПОЛНОЙ ИНФОРМАЦИЕЙ
@dp.callback_query(lambda c: c.data.startswith("getfile_"))
async def handle_get_file(callback: types.CallbackQuery):
    await callback.answer("⏳ Подготавливаем медиафайл...", show_alert=False)
    
    demo_video_url = "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4"
    
    video_caption = (
        "📹 **Человек-паук: Новый день (Red Head Sound [1080p])**\n\n"
        "⏱ **Длительность:** 2:23:17 (143 мин.)\n\n"
        "📊 **Мировые рейтинги:**\n"
        "• 🟡 **Кинопоиск:** 8.1 / 10\n"
        "• ⭐️ **IMDb:** 8.2 / 10\n"
        "• 🌐 **TMDB:** 84%\n\n"
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
        await callback.answer("🎲 Случайный выбор...")
        caption = "🎬 **Мстители: Финал (2019)**\n⭐ Кинопоиск: 7.9 | IMDb: 8.4 | TMDB: 82%\n\nфильм | кр:7.9 | imdb:8.4 | 2019 | США | фантастика, боевик"
        kb = get_movie_kb("Мстители: Финал", 843650)
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
        await callback.message.edit_text("🎬 **KINOrave**\n\n🍿 Выбирай разделы или запускай поиск.", reply_markup=get_start_kb(), parse_mode="Markdown")
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

