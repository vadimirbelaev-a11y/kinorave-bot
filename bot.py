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

# --- ОСНОВНЫЕ НАСТРОЙКИ ---
BOT_TOKEN = "8410105070:AAHUuktDtUm_ICmRiRx0HghwsNkfYcNYD0Y"
TMDB_API_KEY = "e2d7e4ba3b610d32bb5826f04d026bd6"

# Твой канал KINOrave
CHANNEL_LINK = "https://t.me/kinorave_tg"
CHANNEL_USERNAME = "@kinorave_tg"

RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "")
WEBHOOK_PATH = f"/bot/{BOT_TOKEN}"
WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}"
PORT = int(os.environ.get("PORT", 10000))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- БАЗА ПОЛЬЗОВАТЕЛЕЙ И СТАТИСТИКА ---
USERS_FILE = "users.txt"

def save_user(user_id: int):
    users = set()
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            users = set(line.strip() for line in f if line.strip())
    if str(user_id) not in users:
        with open(USERS_FILE, "a") as f:
            f.write(f"{user_id}\n")

def get_users_count() -> int:
    if not os.path.exists(USERS_FILE):
        return 0
    with open(USERS_FILE, "r") as f:
        return len(set(line.strip() for line in f if line.strip()))

# --- ПРОВЕРКА ПОДПИСКИ ---
async def check_subscription(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        return member.status in ["creator", "administrator", "member"]
    except Exception as e:
        logging.error(f"Ошибка проверки подписки: {e}")
        # Если бот еще не админ в канале, не блокируем поиск жестко
        return True

def get_sub_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Подписаться на KINOrave", url=CHANNEL_LINK)],
        [InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check_sub")]
    ])

# Нижняя панель (Reply Keyboard)
def get_main_reply_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🔍 Поиск"),
                KeyboardButton(text="📁 Подборки"),
                KeyboardButton(text="🌪 Фильтр")
            ],
            [
                KeyboardButton(text="⚙️ Настройки"),
                KeyboardButton(text="🎁 Поделиться")
            ]
        ],
        resize_keyboard=True
    )

# --- ИНЛАЙН-КЛАВИАТУРЫ (ПЕРЕРАБОТАННЫЙ ДИЗАЙН) ---

def get_start_inline_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎬 Руководство", callback_data="video_guide"),
            InlineKeyboardButton(text="⚙️ Настройки", callback_data="open_settings")
        ],
        [
            InlineKeyboardButton(text="🔍 Начать поиск", switch_inline_query_current_chat="")
        ]
    ])

def get_search_inline_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💡 Как искать", callback_data="video_guide"),
            InlineKeyboardButton(text="⤴️ Поделиться", callback_data="open_share")
        ],
        [
            InlineKeyboardButton(text="🕒 История", callback_data="history"),
            InlineKeyboardButton(text="⭐ Мой список", callback_data="fav")
        ],
        [
            InlineKeyboardButton(text="📁 Коллекции", callback_data="open_collections"),
            InlineKeyboardButton(text="🌪 Фильтры", callback_data="open_filter")
        ],
        [
            InlineKeyboardButton(text="⚙️ Настройки", callback_data="open_settings")
        ],
        [
            InlineKeyboardButton(text="🔍 Начать поиск", switch_inline_query_current_chat="")
        ]
    ])

def get_collections_inline_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔥 Тренды дня", callback_data="col_today")],
        [InlineKeyboardButton(text="🌟 Хиты и популярное", callback_data="col_pop")],
        [InlineKeyboardButton(text="🎬 Свежие фильмы", callback_data="col_new_movies")],
        [InlineKeyboardButton(text="📺 Свежие сериалы", callback_data="col_new_shows")],
        [InlineKeyboardButton(text="⏳ Скоро в кино", callback_data="col_soon_movies")],
        [InlineKeyboardButton(text="⏳ Скоро на экранах (сериалы)", callback_data="col_soon_shows")],
        [InlineKeyboardButton(text="🔎 Поиск коллекций", callback_data="col_search")],
        [InlineKeyboardButton(text="📂 Мои сохраненные", callback_data="col_my")],
        [InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_start")]
    ])

def get_filter_inline_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 Рейтинг от", callback_data="f_rat_from"),
            InlineKeyboardButton(text="📊 Рейтинг до", callback_data="f_rat_to")
        ],
        [
            InlineKeyboardButton(text="📅 Год от", callback_data="f_year_from"),
            InlineKeyboardButton(text="📅 Год до", callback_data="f_year_to")
        ],
        [InlineKeyboardButton(text="📁 Категория", callback_data="f_type")],
        [InlineKeyboardButton(text="🏷 Жанр", callback_data="f_genre")],
        [InlineKeyboardButton(text="🌍 Страна", callback_data="f_country")],
        [InlineKeyboardButton(text="🎲 Случайный выбор", callback_data="f_random")],
        [InlineKeyboardButton(text="🔄 Сбросить параметры", callback_data="f_reset")],
        [InlineKeyboardButton(text="🔍 Начать поиск", switch_inline_query_current_chat="")],
        [InlineKeyboardButton(text="🔍 Применить фильтр", callback_data="f_apply")]
    ])

def get_settings_inline_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎟 Ввести промокод", callback_data="promos"),
            InlineKeyboardButton(text="⤴️ Пригласить друга", callback_data="open_share")
        ],
        [
            InlineKeyboardButton(text="👨‍💻 Поддержка и обратная связь", url=CHANNEL_LINK),
            InlineKeyboardButton(text="🤝 Сотрудничество", callback_data="partners")
        ],
        [
            InlineKeyboardButton(text="🛡 Подключить VPN", url="https://t.me/StableVPN")
        ],
        [InlineKeyboardButton(text="🔲 Отображение ID", callback_data="toggle_id")],
        [InlineKeyboardButton(text="🔍 Найти кино", switch_inline_query_current_chat="")]
    ])

def get_share_inline_keyboard(bot_username: str, user_id: int):
    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📧 Отправить ссылку", url=f"https://t.me/share/url?url={ref_link}&text=Смотри+любые+фильмы+в+KINOrave!")],
        [InlineKeyboardButton(text="🎞 Промо-материалы", callback_data="promo_video")],
        [
            InlineKeyboardButton(text="🔗 Поделиться фильмом", switch_inline_query_current_chat=""),
            InlineKeyboardButton(text="🔗 Поделиться подборкой", callback_data="open_collections")
        ],
        [InlineKeyboardButton(text="🔍 К поиску", switch_inline_query_current_chat="")]
    ])

def get_movie_keyboard(title: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎙 Выбор озвучки", callback_data="voice"),
            InlineKeyboardButton(text="🔮 Качество видео", callback_data="quality")
        ],
        [
            InlineKeyboardButton(text="🔔 Уведомления", callback_data="notify"),
            InlineKeyboardButton(text="⭐ В избранное", callback_data="fav")
        ],
        [
            InlineKeyboardButton(text="💬 Наш канал", url=CHANNEL_LINK),
            InlineKeyboardButton(text="⤴️ Поделиться", switch_inline_query=title)
        ],
        [InlineKeyboardButton(text="❤️ Оценить плеер", callback_data="rate")],
        [InlineKeyboardButton(text="😭 Сообщить о проблеме", callback_data="report")],
        [
            InlineKeyboardButton(text="📺 Трансляция на TV", callback_data="tv"),
            InlineKeyboardButton(text="ℹ️ Детали", callback_data="more")
        ],
        [InlineKeyboardButton(text="🔍 Искать дальше", switch_inline_query_current_chat="")]
    ])

# --- ОБРАБОТЧИКИ КОМАНД С АВТОУДАЛЕНИЕМ ---

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    save_user(user_id)
    
    try:
        await message.delete()
    except Exception:
        pass

    if not await check_subscription(user_id):
        await message.answer(
            f"👋 Салют, {message.from_user.first_name}!\n\n"
            f"🔒 Чтобы открыть полный доступ к поиску фильмов и сериалов, подпишись на наш официальный канал KINOrave:",
            reply_markup=get_sub_keyboard()
        )
        return

    text = (
        "🎬 **Добро пожаловать в KINOrave!**\n\n"
        "🍿 Жми кнопки меню ниже или отправь название нужного фильма прямым сообщением в чат.\n\n"
        f"💬 Нужна помощь? [Переходи в наше сообщество]({CHANNEL_LINK})"
    )
    await message.answer(
        text, 
        reply_markup=get_start_inline_keyboard(), 
        parse_mode="Markdown", 
        disable_web_page_preview=True
    )
    await message.answer("Главное меню:", reply_markup=get_main_reply_keyboard())

@dp.message(Command("search"))
async def cmd_search(message: types.Message):
    user_id = message.from_user.id
    save_user(user_id)
    try:
        await message.delete()
    except Exception:
        pass

    if not await check_subscription(user_id):
        await message.answer("Для использования бота подпишитесь на канал!", reply_markup=get_sub_keyboard())
        return

    text = "🔍 **Поиск фильмов и сериалов**\n\nНажми «Начать поиск» для инлайн-режима или просто напиши название фильма прямо в этот чат!"
    await message.answer(text, reply_markup=get_search_inline_keyboard(), parse_mode="Markdown")

@dp.message(Command("collections"))
async def cmd_collections(message: types.Message):
    user_id = message.from_user.id
    save_user(user_id)
    try:
        await message.delete()
    except Exception:
        pass

    if not await check_subscription(user_id):
        await message.answer("Для использования бота подпишитесь на канал!", reply_markup=get_sub_keyboard())
        return

    await message.answer("📁 **Тематические коллекции и киноподборки**\n\n✨ *Выбирай лучшее для вечернего просмотра!*", reply_markup=get_collections_inline_keyboard(), parse_mode="Markdown")

@dp.message(Command("filter"))
async def cmd_filter(message: types.Message):
    user_id = message.from_user.id
    save_user(user_id)
    try:
        await message.delete()
    except Exception:
        pass

    if not await check_subscription(user_id):
        await message.answer("Для использования бота подпишитесь на канал!", reply_markup=get_sub_keyboard())
        return

    text = (
        "⚙️ **Текущие параметры фильтрации:**\n\n"
        "🔹 **Оценка:** от 5.0 до 10.0\n"
        "🔹 **Период:** Все года\n"
        "🔹 **Формат:** Фильмы и Сериалы\n"
        "🔹 **Жанры:** Любые\n"
        "🔹 **Страна:** Все страны"
    )
    await message.answer(text, reply_markup=get_filter_inline_keyboard(), parse_mode="Markdown")

@dp.message(Command("settings"))
async def cmd_settings(message: types.Message):
    user_id = message.from_user.id
    save_user(user_id)
    try:
        await message.delete()
    except Exception:
        pass

    if not await check_subscription(user_id):
        await message.answer("Для использования бота подпишитесь на канал!", reply_markup=get_sub_keyboard())
        return

    text = (
        "⚙️ **Персональные настройки**\n\n"
        f"🆔 Твой ID: `{user_id}`\n"
        "📅 Статус профиля: Активен"
    )
    await message.answer(text, reply_markup=get_settings_inline_keyboard(), parse_mode="Markdown")

@dp.message(Command("share"))
async def cmd_share(message: types.Message):
    user_id = message.from_user.id
    save_user(user_id)
    try:
        await message.delete()
    except Exception:
        pass

    if not await check_subscription(user_id):
        await message.answer("Для использования бота подпишитесь на канал!", reply_markup=get_sub_keyboard())
        return

    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"

    text = (
        "🎁 **Приглашай друзей в KINOrave!**\n\n"
        "Делись индивидуальной ссылкой с друзьями и знакомыми:\n\n"
        f"🔗 `{ref_link}`\n\n"
        "📌 *Примечание: засчитываются только новые пользователи, ранее не запускавшие бота.*"
    )
    await message.answer(text, reply_markup=get_share_inline_keyboard(bot_info.username, user_id), parse_mode="Markdown")

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    user_id = message.from_user.id
    try:
        await message.delete()
    except Exception:
        pass
    count = get_users_count()
    await message.answer(f"📊 **Статистика KINOrave:**\n\n👥 Всего уникальных зрителей: **{count}**\n🆔 Ваш ID: `{user_id}`", parse_mode="Markdown")

# ОБРАБОТКА НИЖНЕЙ ПАНЕЛИ
@dp.message(lambda m: m.text in ["🔍 Поиск", "📁 Подборки", "🌪 Фильтр", "⚙️ Настройки", "🎁 Поделиться"])
async def reply_buttons_handler(message: types.Message):
    user_id = message.from_user.id
    save_user(user_id)
    
    if not await check_subscription(user_id):
        await message.answer("Для использования бота подпишитесь на канал!", reply_markup=get_sub_keyboard())
        return

    text = message.text
    if text == "🔍 Поиск":
        await message.answer("🔍 **Поиск фильмов и сериалов**\n\nНажми «Начать поиск» для инлайн-режима или просто напиши название фильма прямо в этот чат!", reply_markup=get_search_inline_keyboard(), parse_mode="Markdown")
    elif text == "📁 Подборки":
        await message.answer("📁 **Тематические коллекции и киноподборки**\n\n✨ *Выбирай лучшее для вечернего просмотра!*", reply_markup=get_collections_inline_keyboard(), parse_mode="Markdown")
    elif text == "🌪 Фильтр":
        await message.answer("⚙️ **Текущие параметры фильтрации:**\n\n🔹 **Оценка:** от 5.0 до 10.0\n🔹 **Период:** Все года\n🔹 **Формат:** Фильмы и Сериалы", reply_markup=get_filter_inline_keyboard(), parse_mode="Markdown")
    elif text == "⚙️ Настройки":
        await message.answer(f"⚙️ **Персональные настройки**\n\n🆔 Твой ID: `{user_id}`", reply_markup=get_settings_inline_keyboard(), parse_mode="Markdown")
    elif text == "🎁 Поделиться":
        bot_info = await bot.get_me()
        ref_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"
        await message.answer(f"🎁 **Приглашай друзей в KINOrave!**\n\n🔗 Твоя ссылка:\n`{ref_link}`", reply_markup=get_share_inline_keyboard(bot_info.username, user_id), parse_mode="Markdown")

@dp.callback_query(lambda c: c.data == "check_sub")
async def process_check_sub(callback: types.CallbackQuery):
    if await check_subscription(callback.from_user.id):
        await callback.message.delete()
        await callback.message.answer("🎉 Подписка подтверждена! Приятного пользования.", reply_markup=get_main_reply_keyboard())
        
        text = "🎬 **Добро пожаловать в KINOrave!**\n\n🍿 Выбирай разделы в меню или пиши название фильма."
        await callback.message.answer(text, reply_markup=get_start_inline_keyboard(), parse_mode="Markdown")
    else:
        await callback.answer("❌ Вы всё ещё не подписались на канал KINOrave!", show_alert=True)

# ИНЛАЙН-ПОИСК
@dp.inline_query()
async def inline_search(inline_query: InlineQuery):
    user_id = inline_query.from_user.id
    save_user(user_id)
    
    if not await check_subscription(user_id):
        return

    query = inline_query.query.strip()
    if not query:
        return

    headers = {"User-Agent": "Mozilla/5.0"}
    url = "https://api.themoviedb.org/3/search/multi"
    params = {"api_key": TMDB_API_KEY, "language": "ru-RU", "query": query}

    results = []
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, params=params, timeout=5) as response:
                if response.status == 200:
                    data = await response.json()
                    items = data.get('results', [])[:10]

                    for idx, item in enumerate(items):
                        media_type = "сериал" if item.get('media_type') == 'tv' else "фильм"
                        title = item.get('title') or item.get('name') or "Без названия"
                        orig_title = item.get('original_title') or item.get('original_name') or ""
                        rating = item.get('vote_average', 0)
                        release_date = item.get('release_date') or item.get('first_air_date') or ""
                        year = release_date.split('-')[0] if release_date else "Н/Д"
                        poster_path = item.get('poster_path')
                        overview = item.get('overview') or "Описание отсутствует."

                        description = f"{media_type} | tmdb:{rating:.1f} | {year}"
                        if orig_title:
                            description = f"{orig_title}\n{description}"

                        thumb_url = f"https://image.tmdb.org/t/p/w185{poster_path}" if poster_path else "https://via.placeholder.com/150"

                        caption = (
                            f"🎬 **{title}** ({year})\n"
                            f"📝 *{orig_title}*\n\n"
                            f"⭐ **Рейтинг:** {rating:.1f} / 10\n\n"
                            f"📖 **Описание:**\n{overview[:350]}..."
                        )

                        results.append(
                            InlineQueryResultArticle(
                                id=str(idx),
                                title=title,
                                description=description,
                                thumbnail_url=thumb_url,
                                input_message_content=InputTextMessageContent(
                                    message_text=caption,
                                    parse_mode="Markdown"
                                ),
                                reply_markup=get_movie_keyboard(title)
                            )
                        )
        await inline_query.answer(results, cache_time=1)
    except Exception as e:
        logging.error(f"Ошибка в inline_search: {e}")

# ПОИСК ИЗ ЧАТА
@dp.message()
async def search_movie(message: types.Message):
    user_id = message.from_user.id
    save_user(user_id)
    
    if not await check_subscription(user_id):
        await message.answer("Для поиска необходимо быть подписанным на канал KINOrave!", reply_markup=get_sub_keyboard())
        return

    query = message.text
    if not query or query.startswith("/"):
        return

    headers = {"User-Agent": "Mozilla/5.0"}
    url = "https://api.themoviedb.org/3/search/multi"
    params = {"api_key": TMDB_API_KEY, "language": "ru-RU", "query": query}

    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, params=params, timeout=10) as response:
                if response.status != 200:
                    await message.answer("⚠️ Ошибка базы данных TMDB. Повторите попытку позже!")
                    return

                data = await response.json()
                results = data.get('results', [])

                if not results:
                    await message.answer("😔 По вашему запросу ничего не найдено. Проверьте правильность названия.")
                    return

                item = results[0]
                title = item.get('title') or item.get('na