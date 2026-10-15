import os
import random
import logging
import re
import time
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
    KeyboardButton,
    FSInputFile
)

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = "8410105070:AAHUuktDtUm_ICmRiRx0HghwsNkfYcNYD0Y"
KP_API_KEY = "8c1e3d22-0321-4952-a86f-37f3d9d3000f"
CHANNEL_LINK = "https://t.me/kinorave_tg"
CHANNEL_USERNAME = "@kinorave_tg"

# ТВЯ ЖЕСТКАЯ АДМИНСКАЯ ЗАЩИТА
ADMIN_ID = 6444735646

RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "")
WEBHOOK_PATH = "/bot/" + BOT_TOKEN
WEBHOOK_URL = RENDER_EXTERNAL_URL + WEBHOOK_PATH
PORT = int(os.environ.get("PORT", 10000))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
USERS_FILE = "users.txt"
REFS_FILE = "referrals.txt"
CONFIG_FILE = "bot_mode.txt"
MAINTENANCE_FILE = "maintenance.txt"

FLOOD_CONTROL = {}
ATTACK_ALERT_COOLDOWN = {}
FLOOD_LIMIT_SECONDS = 0.8

HEADERS = {
    "X-API-KEY": KP_API_KEY,
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0"
}

LOCAL_MOVIES_DB = [
    {"title": "Интерстеллар", "year": "2014", "rating": "8.6", "imdb": "8.7", "tmdb": "84%", "duration": "169 мин.", "desc": "фильм | кр:8.6 | imdb:8.7 | 2014 | США | фантастика, драма", "poster": "https://kinorium-images.imgix.net/movie/poster/1179782/h800/v_63749718.jpg", "id": 258687},
    {"title": "Начало", "year": "2010", "rating": "8.7", "imdb": "8.8", "tmdb": "83%", "duration": "148 мин.", "desc": "фильм | кр:8.7 | imdb:8.8 | 2010 | США | фантастика, боевик", "poster": "https://kinorium-images.imgix.net/movie/poster/460317/h800/v_63749673.jpg", "id": 447},
    {"title": "Мстители: Финал", "year": "2019", "rating": "7.9", "imdb": "8.4", "tmdb": "82%", "duration": "181 мин.", "desc": "фильм | кр:7.9 | imdb:8.4 | 2019 | США | фантастика, боевик", "poster": "https://kinorium-images.imgix.net/movie/poster/1410940/h800/v_63677764.jpg", "id": 843650},
    {"title": "Джокер", "year": "2019", "rating": "8.0", "imdb": "8.4", "tmdb": "81%", "duration": "122 мин.", "desc": "фильм | кр:8.0 | imdb:8.4 | 2019 | США | драма, триллер", "poster": "https://kinorium-images.imgix.net/movie/poster/2253335/h800/v_63749679.jpg", "id": 1048334},
    {"title": "Побег из Шоушенка", "year": "1994", "rating": "9.1", "imdb": "9.3", "tmdb": "87%", "duration": "142 мин.", "desc": "фильм | кр:9.1 | imdb:9.3 | 1994 | США | драма", "poster": "https://kinorium-images.imgix.net/movie/poster/389025/h800/v_63749688.jpg", "id": 326},
    {"title": "Зеленая миля", "year": "1999", "rating": "9.1", "imdb": "8.6", "tmdb": "85%", "duration": "189 мин.", "desc": "фильм | кр:9.1 | imdb:8.6 | 1999 | США | драма, криминал", "poster": "https://kinorium-images.imgix.net/movie/poster/406180/h800/v_63749685.jpg", "id": 435},
    {"title": "Титаник", "year": "1997", "rating": "8.4", "imdb": "7.9", "tmdb": "79%", "duration": "194 мин.", "desc": "фильм | кр:8.4 | imdb:7.9 | 1997 | США | драма, мелодрама", "poster": "https://kinorium-images.imgix.net/movie/poster/393278/h800/v_63749712.jpg", "id": 597},
    {"title": "Форрест Гамп", "year": "1994", "rating": "8.9", "imdb": "8.8", "tmdb": "85%", "duration": "142 мин.", "desc": "фильм | кр:8.9 | imdb:8.8 | 1994 | США | драма, комедия", "poster": "https://kinorium-images.imgix.net/movie/poster/394145/h800/v_63749687.jpg", "id": 13},
    {"title": "Король Лев", "year": "1994", "rating": "8.8", "imdb": "8.5", "tmdb": "83%", "duration": "88 мин.", "desc": "мультфильм | кр:8.8 | imdb:8.5 | 1994 | США | анимация, драма", "poster": "https://kinorium-images.imgix.net/movie/poster/400612/h800/v_63749692.jpg", "id": 8587},
    {"title": "Гладиатор", "year": "2000", "rating": "8.6", "imdb": "8.5", "tmdb": "82%", "duration": "155 мин.", "desc": "фильм | кр:8.6 | imdb:8.5 | 2000 | США | боевик, драма", "poster": "https://kinorium-images.imgix.net/movie/poster/408993/h800/v_63749675.jpg", "id": 98},
    {"title": "Аватар", "year": "2009", "rating": "8.0", "imdb": "7.9", "tmdb": "76%", "duration": "162 мин.", "desc": "фильм | кр:8.0 | imdb:7.9 | 2009 | США | фантастика, приключения", "poster": "https://kinorium-images.imgix.net/movie/poster/447990/h800/v_63749670.jpg", "id": 199},
    {"title": "Терминатор 2: Судный день", "year": "1991", "rating": "8.3", "imdb": "8.6", "tmdb": "81%", "duration": "137 мин.", "desc": "фильм | кр:8.3 | imdb:8.6 | 1991 | США | фантастика, боевик", "poster": "https://kinorium-images.imgix.net/movie/poster/392180/h800/v_63749714.jpg", "id": 280},
    {"title": "Матрица", "year": "1999", "rating": "8.5", "imdb": "8.7", "tmdb": "82%", "duration": "136 мин.", "desc": "фильм | кр:8.5 | imdb:8.7 | 1999 | США | фантастика, боевик", "poster": "https://kinorium-images.imgix.net/movie/poster/391942/h800/v_63749710.jpg", "id": 603},
    {"title": "Темный рыцарь", "year": "2008", "rating": "8.5", "imdb": "9.0", "tmdb": "85%", "duration": "152 мин.", "desc": "фильм | кр:8.5 | imdb:9.0 | 2008 | США | боевик, триллер, драма", "poster": "https://kinorium-images.imgix.net/movie/poster/439768/h800/v_63749674.jpg", "id": 155},
    {"title": "Бойцовский клуб", "year": "1999", "rating": "8.7", "imdb": "8.8", "tmdb": "84%", "duration": "139 мин.", "desc": "фильм | кр:8.7 | imdb:8.8 | 1999 | США | триллер, драма, криминал", "poster": "https://kinorium-images.imgix.net/movie/poster/389470/h800/v_63749678.jpg", "id": 550},
    {"title": "Криминальное чтиво", "year": "1994", "rating": "8.6", "imdb": "8.9", "tmdb": "85%", "duration": "154 мин.", "desc": "фильм | кр:8.6 | imdb:8.9 | 1994 | США | криминал, драма", "poster": "https://kinorium-images.imgix.net/movie/poster/389467/h800/v_63749706.jpg", "id": 680},
    {"title": "Брат", "year": "1997", "rating": "8.3", "imdb": "8.0", "tmdb": "76%", "duration": "100 мин.", "desc": "фильм | кр:8.3 | imdb:8.0 | 1997 | Россия | драма, криминал, боевик", "poster": "https://kinorium-images.imgix.net/movie/poster/428385/h800/v_63749677.jpg", "id": 4212},
    {"title": "Брат 2", "year": "2000", "rating": "8.1", "imdb": "8.0", "tmdb": "75%", "duration": "127 мин.", "desc": "фильм | кр:8.1 | imdb:8.0 | 2000 | Россия | боевик, криминал, драма", "poster": "https://kinorium-images.imgix.net/movie/poster/431872/h800/v_63749676.jpg", "id": 4213},
    {"title": "Во все тяжкие", "year": "2008", "rating": "8.9", "imdb": "9.5", "tmdb": "89%", "duration": "49 мин.", "desc": "сериал | кр:8.9 | imdb:9.5 | 2008 | США | драма, криминал, триллер", "poster": "https://kinorium-images.imgix.net/movie/poster/982110/h800/v_63749704.jpg", "id": 5002},
    {"title": "Игра престолов", "year": "2011", "rating": "9.0", "imdb": "9.2", "tmdb": "84%", "duration": "57 мин.", "desc": "сериал | кр:9.0 | imdb:9.2 | 2011 | США | фэнтези, драма, приключения", "poster": "https://kinorium-images.imgix.net/movie/poster/1118129/h800/v_63749722.jpg", "id": 5003}
]

def clean_title(text: str) -> str:
    return re.sub(r'[^а-яa-z0-9]', '', text.lower())

def get_current_mode() -> str:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return f.read().strip()
    return "global"

def set_current_mode(mode: str):
    with open(CONFIG_FILE, "w") as f:
        f.write(mode)

def is_maintenance() -> bool:
    return os.path.exists(MAINTENANCE_FILE)

def toggle_maintenance() -> bool:
    if os.path.exists(MAINTENANCE_FILE):
        os.remove(MAINTENANCE_FILE)
        return False
    else:
        with open(MAINTENANCE_FILE, "w") as f:
            f.write("ON")
        return True

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

def get_users_list() -> list:
    if not os.path.exists(USERS_FILE):
        return []
    with open(USERS_FILE, "r") as f:
        return [int(line.strip()) for line in f if line.strip()]

def get_users_count():
    return len(get_users_list())

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
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔍 Начать поиск", switch_inline_query_current_chat="")], [InlineKeyboardButton(text="🎲 Кинорулетка", callback_data="roulette"), KeyboardButton(text="📁 Подборки", callback_data="open_collections")]])

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

def get_admin_kb():
    m_status = "🔴 Отключить техобслуживание" if is_maintenance() else "🟢 Включить техобслуживание"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Глобальный режим", callback_data="admin_global"), InlineKeyboardButton(text="📁 Локальный G-CON", callback_data="admin_local")],
        [InlineKeyboardButton(text=m_status, callback_data="admin_maint")],
        [InlineKeyboardButton(text="📤 Выгрузить базу (.txt)", callback_data="admin_export")]
    ])

def get_attack_alert_kb():
    maint_text = "🔴 Включить тех. обслуживание" if not is_maintenance() else "🟢 Выключить тех. обслуживание"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=maint_text, callback_data="alert_toggle_maint")],
        [InlineKeyboardButton(text="📁 Перевести в локальный режим", callback_data="alert_set_local")],
        [InlineKeyboardButton(text="🛡 Сбросить угрозу", callback_data="alert_dismiss")]
    ])

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
    if is_maintenance() and user_id != ADMIN_ID:
        await message.answer("🛠 **В боте проводятся плановые технические работы.**\n\nСкоро мы вернемся с обновлениями! 🎬", parse_mode="Markdown")
        return

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
        
    txt = "🎬 **Добро пожаловать в KINOrave!**\n\n🍿 Напиши название фильма прямо в чат для поиска.\n\n💬 [Наш канал](" + CHANNEL_LINK + ")"
    await message.answer(txt, reply_markup=get_start_kb(), parse_mode="Markdown", disable_web_page_preview=True)
    await message.answer("Главное меню управления:", reply_markup=get_main_kb())

@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔️ Доступ запрещен.")
        return

    mode = get_current_mode()
    maint_text = "ВКЛЮЧЕНО 🔴" if is_maintenance() else "ВЫКЛЮЧЕНО 🟢"
    txt = (
        f"🛠 **Защищенная админ-панель KINOrave**\n\n"
        f"⚙️ Режим поиска: **{mode.upper()}**\n"
        f"🛠 Тех. обслуживание: **{maint_text}**\n"
        f"👥 Всего пользователей: **{get_users_count()}**\n\n"
        f"📢 **Рассылка:** напишите `/broadcast [ваш текст]`"
    )
    await message.answer(txt, reply_markup=get_admin_kb(), parse_mode="Markdown")

@dp.message(Command("broadcast"))
async def broadcast_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    text_to_send = message.text.replace("/broadcast", "").strip()
    if not text_to_send:
        await message.answer("⚠️ Введите текст для рассылки:\n`/broadcast Ваше сообщение здесь`", parse_mode="Markdown")
        return

    users = get_users_list()
    success = 0
    blocked = 0
    
    status_msg = await message.answer(f"🚀 Запуск рассылки для {len(users)} зрителей...")

    for uid in users:
        try:
            await bot.send_message(chat_id=uid, text=text_to_send, parse_mode="Markdown")
            success += 1
        except Exception:
            blocked += 1

    await status_msg.edit_text(f"✅ **Рассылка успешно завершена!**\n\n📬 Доставлено: `{success}`\n🚫 Заблокировали бота: `{blocked}`", parse_mode="Markdown")

@dp.callback_query(lambda c: c.data.startswith("admin_"))
async def admin_switcher(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔️ Доступ запрещен!", show_alert=True)
        return

    d = callback.data
    if d == "admin_global":
        set_current_mode("global")
        await callback.answer("🌐 Включен Глобальный режим!", show_alert=True)
    elif d == "admin_local":
        set_current_mode("local")
        await callback.answer("📁 Включен Локальный режим G-CON!", show_alert=True)
    elif d == "admin_maint":
        state = toggle_maintenance()
        status_text = "включено 🔴" if state else "выключено 🟢"
        await callback.answer(f"🛠 Техническое обслуживание {status_text}!", show_alert=True)
    elif d == "admin_export":
        if os.path.exists(USERS_FILE):
            file = FSInputFile(USERS_FILE)
            await callback.message.answer_document(file, caption="📁 База пользователей KINOrave")
        else:
            await callback.answer("⚠️ Файл базы пуст.", show_alert=True)
        return

    mode = get_current_mode()
    maint_text = "ВКЛЮЧЕНО 🔴" if is_maintenance() else "ВЫКЛЮЧЕНО 🟢"
    txt = (
        f"🛠 **Защищенная админ-панель KINOrave**\n\n"
        f"⚙️ Режим поиска: **{mode.upper()}**\n"
        f"🛠 Тех. обслуживание: **{maint_text}**\n"
        f"👥 Всего пользователей: **{get_users_count()}**"
    )
    await callback.message.edit_text(txt, parse_mode="Markdown", reply_markup=get_admin_kb())

@dp.callback_query(lambda c: c.data.startswith("alert_"))
async def alert_callback_handler(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔️ Доступ запрещен!", show_alert=True)
        return
    
    d = callback.data
    if d == "alert_toggle_maint":
        state = toggle_maintenance()
        st_text = "ВКЛЮЧЕНО 🔴 (Бот изолирован)" if state else "ВЫКЛЮЧЕНО 🟢 (Бот активен)"
        await callback.message.edit_text(f"🚨 **Статус безопасности изменен!**\nТех. обслуживание: {st_text}", parse_mode="Markdown")
        await callback.answer("Готово!")
    elif d == "alert_set_local":
        set_current_mode("local")
        await callback.message.edit_text("🚨 **Режим безопасности:** Бот принудительно переведен на **локальный поиск G-CON** для защиты от внешнего штурма.", parse_mode="Markdown")
        await callback.answer("Переведено на локальный режим!")
    elif d == "alert_dismiss":
        await callback.message.edit_text("🛡 **Тревога сброшена.** Система работает в штатном режиме.", parse_mode="Markdown")
        await callback.answer("Угроза отклонена.")
@dp.message(Command("search"))
async def search_cmd(message: types.Message):
    if is_maintenance() and message.from_user.id != ADMIN_ID:
        return
    save_user(message.from_user.id)
    try: await message.delete()
    except Exception: pass
    if not await check_subscription(message.from_user.id):
        await message.answer("Подпишись на канал!", reply_markup=get_sub_kb())
        return
    await message.answer("🔍 **Поиск фильмов и сериалов**\n\nНапиши название кино в чат:", reply_markup=get_search_kb(), parse_mode="Markdown")

@dp.message(Command("collections"))
async def collections_cmd(message: types.Message):
    if is_maintenance() and message.from_user.id != ADMIN_ID:
        return
    save_user(message.from_user.id)
    try: await message.delete()
    except Exception: pass
    if not await check_subscription(message.from_user.id):
        await message.answer("Подпишись на канал!", reply_markup=get_sub_kb())
        return
    await message.answer("📁 **Выбери категорию подборки:**", reply_markup=get_collections_kb(), parse_mode="Markdown")

@dp.message(Command("filter"))
async def filter_cmd(message: types.Message):
    if is_maintenance() and message.from_user.id != ADMIN_ID:
        return
    save_user(message.from_user.id)
    try: await message.delete()
    except Exception: pass
    if not await check_subscription(message.from_user.id):
        await message.answer("Подпишись на канал!", reply_markup=get_sub_kb())
        return
    await message.answer("🌪 **Выбери жанр фильма:**", reply_markup=get_filter_kb(), parse_mode="Markdown")

@dp.message(Command("settings"))
async def settings_cmd(message: types.Message):
    if is_maintenance() and message.from_user.id != ADMIN_ID:
        return
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
    if is_maintenance() and uid != ADMIN_ID:
        return
    save_user(uid)
    try: await message.delete()
    except Exception: pass
    if not await check_subscription(uid):
        await message.answer("Подпишись на канал!", reply_markup=get_sub_kb())
        return
    me = await bot.get_me()
    ref = "https://t.me/" + str(me.username) + "?start=ref_" + str(uid)
    refs_count = get_referral_count(uid)
    txt = "🎁 **Приглашай друзей в KINOrave!**\n\n👥 Приглашено: **" + str(refs_count) + "**\n\n🔗 Ссылка:\n`" + ref + "`"
    await message.answer(txt, reply_markup=get_share_kb(me.username, uid), parse_mode="Markdown")

@dp.message(Command("stats"))
async def stats_cmd(message: types.Message):
    try: await message.delete()
    except Exception: pass
    await message.answer("📊 **Статистика KINOrave:**\n\n👥 Всего зрителей: **" + str(get_users_count()) + "**\n🆔 Ваш ID: `" + str(message.from_user.id) + "`", parse_mode="Markdown")

@dp.message(lambda m: m.text in ["🔍 Поиск", "📁 Подборки", "🌪 Фильтр", "⚙️ Настройки", "🎁 Поделиться"])
async def reply_handler(message: types.Message):
    uid = message.from_user.id
    if is_maintenance() and uid != ADMIN_ID:
        return
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
    now = time.time()
    
    if uid != ADMIN_ID:
        if uid in FLOOD_CONTROL and (now - FLOOD_CONTROL[uid]) < FLOOD_LIMIT_SECONDS:
            last_alert = ATTACK_ALERT_COOLDOWN.get(uid, 0)
            if now - last_alert > 30:
                ATTACK_ALERT_COOLDOWN[uid] = now
                try:
                    await bot.send_message(
                        chat_id=ADMIN_ID,
                        text=(
                            f"🚨 **ВНИМАНИЕ: Обнаружена попытка кибератаки / спама!**\n\n"
                            f"👤 **Пользователь ID:** `{uid}`\n"
                            f"⚡️ **Имя:** {message.from_user.full_name} (@{message.from_user.username})\n"
                            f"⏱ **Частота:** Превышен порог запросов\n"
                            f"💬 **Текст запроса:** `{message.text[:50]}`\n\n"
                            f"👇 *Выберите действие для защиты бота:*"
                        ),
                        reply_markup=get_attack_alert_kb(),
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass
            return  

    FLOOD_CONTROL[uid] = now

    if is_maintenance() and uid != ADMIN_ID:
        await message.answer("🛠 В боте проводятся плановые технические работы. Скоро вернемся!")
        return

    save_user(uid)
    if not await check_subscription(uid):
        await message.answer("Для поиска подпишитесь на канал KINOrave!", reply_markup=get_sub_kb())
        return

    q = message.text.strip()
    if not q or q.startswith("/"):
        return

    mode = get_current_mode()
    found_film = None
    clean_q = clean_title(q)

    if mode == "local":
        for movie in LOCAL_MOVIES_DB:
            if clean_q in clean_title(movie["title"]):
                found_film = movie
                break
    else:
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
                            title = item.get('nameRu') or item.get('nameEn') or q
                            year = str(item.get('year', '2023'))
                            rat = str(item.get('rating', '7.9'))
                            kp_id = item.get('filmId', 0)
                            
                            poster_url = f"https://kinorium-images.imgix.net/movie/poster/{kp_id}/h800/v_63749718.jpg" if kp_id else "https://kinorium-images.imgix.net/movie/poster/1179782/h800/v_63749718.jpg"
                            if item.get('posterUrl'):
                                poster_url = item.get('posterUrl')

                            found_film = {
                                "title": title,
                                "year": year,
                                "rating": rat,
                                "imdb": "8.2",
                                "tmdb": "82%",
                                "desc": f"фильм | кр:{rat} | imdb:8.2 | {year} | США | драма, приключения",
                                "poster": poster_url,
                                "id": kp_id
                            }
        except Exception:
            pass

    if not found_film:
        for movie in LOCAL_MOVIES_DB:
            if clean_q in clean_title(movie["title"]) or any(word in clean_title(movie["title"]) for word in clean_q.split()):
                found_film = movie
                break

    if not found_film:
        await message.answer("😔 Ничего не найдено. Проверьте правильность написания названия фильма!")
        return

    caption = (
        f"🎬 **{found_film['title']}** ({found_film['year']})\n"
        f"⭐ Кинопоиск: {found_film['rating']} | IMDb: {found_film.get('imdb', '8.2')} | TMDB: {found_film.get('tmdb', '82%')}\n\n"
        f"{found_film['desc']}"
    )
    kb = get_movie_kb(found_film['title'], found_film['id'])
    
    try:
        await message.answer_photo(photo=found_film['poster'], caption=caption, reply_markup=kb, parse_mode="Markdown")
    except Exception:
        await message.answer(caption, reply_markup=kb, parse_mode="Markdown")

@dp.inline_query()
async def inline_search(query: InlineQuery):
    q = query.query.strip().lower()
    res = []
    clean_q = clean_title(q)
    for idx, movie in enumerate(LOCAL_MOVIES_DB):
        if not q or clean_q in clean_title(movie["title"]):
            caption = f"🎬 **{movie['title']}** ({movie['year']})\n⭐ Кинопоиск: {movie['rating']} | IMDb: {movie['imdb']} | TMDB: {movie['tmdb']}\n\n{movie['desc']}"
            kb = get_movie_kb(movie['title'], movie['id'])
            res.append(InlineQueryResultArticle(
                id=str(idx),
                title=movie['title'],
                description=movie['desc'],
                input_message_content=InputTextMessageContent(message_text=caption, parse_mode="Markdown"),
                reply_markup=kb
            ))
    await query.answer(res, cache_time=1)

@dp.callback_query(lambda c: c.data.startswith("getfile_"))
async def handle_get_file(callback: types.CallbackQuery):
    await callback.answer("⏳ Подготавливаем медиафайл...", show_alert=False)
    
    demo_video_url = "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4"
    
    video_caption = (
        "📹 **Видеофайл готов!**\n\n"
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
        rand_movie = random.choice(LOCAL_MOVIES_DB)
        caption = f"🎬 **{rand_movie['title']}** ({rand_movie['year']})\n⭐ Кинопоиск: {rand_movie['rating']}\n\n{rand_movie['desc']}"
        kb = get_movie_kb(rand_movie['title'], rand_movie['id'])
        try:
            await callback.message.answer_photo(photo=rand_movie['poster'], caption=caption, reply_markup=kb, parse_mode="Markdown")
        except Exception:
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
        BotCommand(command="admin", description="Админ-панель"),
        BotCommand(command="broadcast", description="Рассылка"),
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
