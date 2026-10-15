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
    InputTextMessageContent
)

logging.basicConfig(level=logging.INFO)

# Твои данные
BOT_TOKEN = "8410105070:AAHUuktDtUm_ICmRiRx0HghwsNkfYcNYD0Y"
TMDB_API_KEY = "e2d7e4ba3b610d32bb5826f04d026bd6"
CHANNEL_USERNAME = "@PodslushanoZalutino"
ADMIN_ID = 8410105070  # Твой Telegram ID для команды /stats

RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "")
WEBHOOK_PATH = f"/bot/{BOT_TOKEN}"
WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}"
PORT = int(os.environ.get("PORT", 10000))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- СИСТЕМА УЧЕТА ПОЛЬЗОВАТЕЛЕЙ ---
USERS_FILE = "users.txt"

def save_user(user_id: int):
    """Сохраняет уникального пользователя в файл"""
    users = set()
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            users = set(line.strip() for line in f if line.strip())
    
    if str(user_id) not in users:
        with open(USERS_FILE, "a") as f:
            f.write(f"{user_id}\n")

def get_users_count() -> int:
    """Возвращает количество уникальных пользователей"""
    if not os.path.exists(USERS_FILE):
        return 0
    with open(USERS_FILE, "r") as f:
        return len(set(line.strip() for line in f if line.strip()))

# --- ПРОВЕРКА ПОДПИСКИ ---
async def check_subscription(user_id: int) -> bool:
    if not CHANNEL_USERNAME or CHANNEL_USERNAME == "@твой_канал":
        return True
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        return member.status in ["creator", "administrator", "member"]
    except Exception as e:
        logging.error(f"Ошибка проверки подписки: {e}")
        return True

def get_sub_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Подписаться на канал", url=f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}")],
        [InlineKeyboardButton(text="✅ Я подписался", callback_data="check_sub")]
    ])

def get_movie_keyboard(title: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎙 Озвучка", callback_data="voice"),
            InlineKeyboardButton(text="🔮 Качество", callback_data="quality")
        ],
        [
            InlineKeyboardButton(text="🔔 Уведомлять", callback_data="notify"),
            InlineKeyboardButton(text="⭐ В избранное", callback_data="fav")
        ],
        [
            InlineKeyboardButton(text="💬 Обсуждения", url=f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}"),
            InlineKeyboardButton(text="⤴️ Поделиться", switch_inline_query=title)
        ],
        [
            InlineKeyboardButton(text="❤️ Оценить текущую озвучку", callback_data="rate")
        ],
        [
            InlineKeyboardButton(text="😭 Ошибка в видео", callback_data="report")
        ],
        [
            InlineKeyboardButton(text="📱 Наши проекты", url=f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}")
        ],
        [
            InlineKeyboardButton(text="📺 TV Cast", callback_data="tv"),
            InlineKeyboardButton(text="ℹ️ Подробнее", callback_data="more")
        ],
        [
            InlineKeyboardButton(text="🔍 Искать ещё", switch_inline_query_current_chat="")
        ]
    ])

# --- КОМАНДЫ БОТА ---

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    save_user(message.from_user.id)
    
    if not await check_subscription(message.from_user.id):
        await message.answer(
            f"👋 Привет, {message.from_user.first_name}!\n\n"
            f"Чтобы пользоваться ботом и искать фильмы, подпишись на наш канал:",
            reply_markup=get_sub_keyboard()
        )
        return

    text = (
        f"🎬 **Добро пожаловать в KINOrave!**\n\n"
        f"Здесь ты можешь найти любой фильм или сериал.\n\n"
        f"🔍 Напиши название в чат или используй инлайн-поиск: `@KINOravebot название`"
    )
    await message.answer(text, parse_mode="Markdown")

# Команда статистики (только для админа)
@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        count = get_users_count()
        await message.answer(f"📊 **Статистика бота:**\n\n👥 Всего пользователей: **{count}**", parse_mode="Markdown")
    else:
        await message.answer("У вас нет доступа к этой команде.")

@dp.callback_query(lambda c: c.data == "check_sub")
async def process_check_sub(callback: types.CallbackQuery):
    if await check_subscription(callback.from_user.id):
        await callback.message.delete()
        await callback.message.answer("🎉 Спасибо за подписку! Теперь напиши название фильма для поиска.")
    else:
        await callback.answer("❌ Вы всё ещё не подписаны на канал!", show_alert=True)

# ИНЛАЙН-ПОИСК
@dp.inline_query()
async def inline_search(inline_query: InlineQuery):
    save_user(inline_query.from_user.id)
    query = inline_query.query.strip()
    if not query:
        return

    headers = {"User-Agent": "Mozilla/5.0"}
    url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_API_KEY}&language=ru-RU&query={query}"

    results = []
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=5) as response:
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

# ОБЫЧНЫЙ ПОИСК
@dp.message()
async def search_movie(message: types.Message):
    save_user(message.from_user.id)
    
    if not await check_subscription(message.from_user.id):
        await message.answer(
            "Для поиска фильмов необходимо быть подписанным на наш канал!",
            reply_markup=get_sub_keyboard()
        )
        return

    query = message.text
    if not query or query.startswith("/"):
        return

    headers = {"User-Agent": "Mozilla/5.0"}
    url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_API_KEY}&language=ru-RU&query={query}"

    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=10) as response:
                if response.status != 200:
                    await message.answer("⚠️ Ошибка сервера кинобазы. Попробуй еще раз!")
                    return

                data = await response.json()
                results = data.get('results', [])

                if not results:
                    await message.answer("😔 Ничего не найдено. Проверь название и напиши еще раз!")
                    return

                item = results[0]
                title = item.get('title') or item.get('name') or "Без названия"
                orig_title = item.get('original_title') or item.get('original_name') or ""
                overview = item.get('overview') or "Описание пока отсутствует."
                rating = item.get('vote_average', 0)
                release_date = item.get('release_date') or item.get('first_air_date') or ""
                year = release_date.split('-')[0] if release_date else "Н/Д"
                poster_path = item.get('poster_path')

                caption = (
                    f"🎬 **{title}** ({year})\n"
                    f"📝 *{orig_title}*\n\n"
                    f"⭐ **Рейтинг:** {rating:.1f} / 10\n\n"
                    f"📖 **Описание:**\n{overview[:350]}..."
                )

                keyboard = get_movie_keyboard(title)

                if poster_path:
                    poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}"
                    try:
                        await message.answer_photo(photo=poster_url, caption=caption, reply_markup=keyboard, parse_mode="Markdown")
                    except Exception:
                        await message.answer(caption, reply_markup=keyboard, parse_mode="Markdown")
                else:
                    await message.answer(caption, reply_markup=keyboard, parse_mode="Markdown")

    except Exception as e:
        logging.error(f"Ошибка при поиске: {e}")
        await message.answer("Произошла ошибка при поиске. Попробуй еще раз!")

@dp.callback_query()
async def process_callbacks(callback: types.CallbackQuery):
    if callback.data in ["voice", "quality", "notify", "fav", "rate", "report", "tv", "more"]:
        await callback.answer("Функция находится в разработке!", show_alert=True)

async def on_startup(bot: Bot):
    commands = [
        BotCommand(command="start", description="Перезапустить бота"),
        BotCommand(command="search", description="Начать поиск"),
        BotCommand(command="stats", description="Статистика бота"),
        BotCommand(command="collections", description="Подборки"),
        BotCommand(command="filter", description="Фильтр поиска"),
        BotCommand(command="settings", description="Настройки"),
        BotCommand(command="share", description="Поделиться ботом"),
        BotCommand(command="help", description="Помощь"),
    ]
    await bot.set_my_commands(commands)

    try:
        await bot.set_webhook(WEBHOOK_URL, drop_pending_updates=True)
        logging.info(f"Вебхук успешно установлен: {WEBHOOK_URL}")
    except Exception as e:
        logging.error(f"Не удалось установить вебхук: {e}")

def main():
    app = web.Application()
    webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    dp.startup.register(on_startup)
    setup_application(app, dp, bot=bot)
    web.run_app(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    main()
