import os
import json
import logging
import random
import re
import html
import aiohttp
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, BotCommand, BotCommandScopeDefault
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ================= CONFIGURATION =================
BOT_TOKEN = "8410105070:AAHUuktDtUm_ICmRiRx0HghwsNkfYcNYD0Y"
KINOPOISK_API_KEY = "8c1e3d22-0321-4952-a86f-37f3d9d3000f"
ADMIN_ID = 6444735646
REQUIRED_CHANNEL = "@kinorave_tg"
VPN_LINK = "https://t.me/FastFive_VPN_shop_bot"

USERS_FILE = "users.txt"
FAVORITES_FILE = "favorites.json"
MAINTENANCE_FILE = "maintenance.txt"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

last_request_time = {}

# ================= STATES =================
class SearchStates(StatesGroup):
    waiting_for_query = State()

# ================= DATABASE & SECURITY HELPERS =================
def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    users = {}
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split(";")
            if len(parts) >= 2:
                users[int(parts[0])] = parts[1]
    return users

def save_user(user_id, reg_date):
    users = load_users()
    if user_id not in users:
        users[user_id] = reg_date
        with open(USERS_FILE, "a", encoding="utf-8") as f:
            f.write(f"{user_id};{reg_date}\n")

def is_maintenance_on():
    if not os.path.exists(MAINTENANCE_FILE):
        return False
    with open(MAINTENANCE_FILE, "r", encoding="utf-8") as f:
        return f.read().strip() == "ON"

def set_maintenance(status: bool):
    with open(MAINTENANCE_FILE, "w", encoding="utf-8") as f:
        f.write("ON" if status else "OFF")

def load_favorites():
    if not os.path.exists(FAVORITES_FILE):
        return {}
    try:
        with open(FAVORITES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_favorites(favs):
    with open(FAVORITES_FILE, "w", encoding="utf-8") as f:
        json.dump(favs, f, ensure_ascii=False, indent=4)

def add_to_favorites(user_id, movie_id, movie_title):
    favs = load_favorites()
    user_str = str(user_id)
    if user_str not in favs:
        favs[user_str] = {}
    favs[user_str][str(movie_id)] = html.escape(movie_title)
    save_favorites(favs)

def remove_from_favorites(user_id, movie_id):
    favs = load_favorites()
    user_str = str(user_id)
    if user_str in favs and str(movie_id) in favs[user_str]:
        del favs[user_str][str(movie_id)]
        save_favorites(favs)

# ================= SECURITY MIDDLEWARE (ЗАЩИТА ОТ КИБЕРАТАК) =================
@dp.message.outer_middleware()
@dp.callback_query.outer_middleware()
async def security_middleware(handler, event, data):
    user_id = event.from_user.id if event.from_user else 0
    
    import time
    now = time.time()
    if user_id != ADMIN_ID:
        last_time = last_request_time.get(user_id, 0)
        if now - last_time < 0.5:
            if isinstance(event, types.CallbackQuery):
                await event.answer("⚠️ Слишком частые запросы!", show_alert=True)
            return
        last_request_time[user_id] = now

    if is_maintenance_on() and user_id != ADMIN_ID:
        text = "⚠️ <b>Внимание!</b> В боте проводятся технические работы и исправление ошибок. Пожалуйста, зайдите позже."
        if isinstance(event, types.CallbackQuery):
            await event.answer("⚠️ Ведутся техработы!", show_alert=True)
        elif isinstance(event, types.Message):
            await event.answer(text, parse_html="HTML")
        return

    return await handler(event, data)

def get_reply_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🔍"),
                KeyboardButton(text="📦"),
                KeyboardButton(text="🌪"),
                KeyboardButton(text="⚙️"),
                KeyboardButton(text="⭐")
            ]
        ],
        resize_keyboard=True
    )

async def search_kinopoisk(query: str):
    cleaned_query = re.sub(r'[^\w\sа-яА-ЯёЁіІїЇєЄґҐ]', '', query).strip().lower()
    if not cleaned_query:
        cleaned_query = query.strip()

    url = f"https://api.kinopoisk.dev/v1.4/movie/search?page=1&limit=5&query={cleaned_query}"
    headers = {"X-API-KEY": KINOPOISK_API_KEY, "accept": "application/json"}
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("docs", [])
        except Exception as e:
            logging.error(f"API Error: {e}")
    return []

async def get_collection(category: str):
    url = f"https://api.kinopoisk.dev/v1.4/movie?page=1&limit=10&sortField=rating.kp&sortType=-1"
    headers = {"X-API-KEY": KINOPOISK_API_KEY, "accept": "application/json"}
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("docs", [])
        except Exception as e:
            logging.error(f"Collection API Error: {e}")
    return []

async def check_sub(user_id: int):
    try:
        member = await bot.get_chat_member(chat_id=REQUIRED_CHANNEL, user_id=user_id)
        return member.status not in ["left", "kicked"]
    except:
        return True

def get_main_menu_keyboard():
    kb = [
        [InlineKeyboardButton(text="💡 Инструкция", callback_data="help"), InlineKeyboardButton(text="⤴️ Поделиться", callback_data="share")],
        [InlineKeyboardButton(text="🕘 История", callback_data="history"), InlineKeyboardButton(text="⭐ Избранное", callback_data="favorites")],
        [InlineKeyboardButton(text="📦 Подборки", callback_data="collections"), InlineKeyboardButton(text="🌪 Фильтр", callback_data="filter")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")],
        [InlineKeyboardButton(text="🔍 Начать поиск", callback_data="start_search")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)
# ================= HANDLERS: /start & ADMIN =================
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    reg_date = datetime.now().strftime("%d.%m.%Y %H:%M")
    save_user(user_id, reg_date)

    if not await check_sub(user_id):
        sub_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Подписаться на канал", url=f"https://t.me/{REQUIRED_CHANNEL[1:]}")],
            [InlineKeyboardButton(text="🔄 Проверить подписку", callback_data="check_sub")]
        ])
        await message.answer("⚠️ Для использования бота необходимо подписаться на наш канал!", reply_markup=sub_kb)
        return

    await show_welcome(message)

async def show_welcome(message: types.Message, edit=False):
    text = (
        "🍿 <b>Привет, киноман!</b>\n\n"
        "🔍 Для поиска используй кнопки ниже или отправь в сообщении название кино\n\n"
        f"Подписывайся на наш канал — <a href=\"https://t.me/{REQUIRED_CHANNEL[1:]}\">Кинорейв</a>"
    )
    kb = get_main_menu_keyboard()
    reply_kb = get_reply_keyboard()
    
    if edit and isinstance(message, types.CallbackQuery):
        await message.message.edit_text(text, parse_html="HTML", reply_markup=kb, disable_web_page_preview=True)
    else:
        await message.answer(text, parse_html="HTML", reply_markup=reply_kb)
        await message.answer("👇 Главное меню:", reply_markup=kb)

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    status = "🔴 ВКЛЮЧЕНЫ (Бот на техобслуживании)" if is_maintenance_on() else "🟢 ОТКЛЮЧЕНЫ (Бот работает штатно)"
    text = f"🛠 <b>Админ-панель</b>\n\nСтатус техработ: {status}"
    
    builder = InlineKeyboardBuilder()
    if is_maintenance_on():
        builder.row(InlineKeyboardButton(text="🟢 Выключить техработы", callback_data="admin_maint_off"))
    else:
        builder.row(InlineKeyboardButton(text="🔴 Включить техработы", callback_data="admin_maint_on"))
    builder.row(InlineKeyboardButton(text="⬅️ Закрыть", callback_data="back_to_main"))
    
    await message.answer(text, parse_html="HTML", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "admin_maint_on")
async def cb_maint_on(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    set_maintenance(True)
    await callback.message.edit_text("🔴 Режим технических работ успешно активирован!", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ В админку", callback_data="admin_back")]]))

@dp.callback_query(F.data == "admin_maint_off")
async def cb_maint_off(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    set_maintenance(False)
    await callback.message.edit_text("🟢 Технические работы завершены!", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ В админку", callback_data="admin_back")]]))

@dp.callback_query(F.data == "admin_back")
async def cb_admin_back(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    await cmd_admin(callback.message)

@dp.callback_query(F.data == "check_sub")
async def cb_check_sub(callback: types.CallbackQuery, state: FSMContext):
    if await check_sub(callback.from_user.id):
        await callback.message.delete()
        await show_welcome(callback.message)
    else:
        await callback.answer("❌ Вы еще не подписались на канал!", show_alert=True)

# Нижняя панель (Reply)
@dp.message(F.text == "🔍")
async def reply_search(message: types.Message, state: FSMContext):
    await cmd_search_handler(message, state)

@dp.message(F.text == "📦")
async def reply_collections(message: types.Message):
    await cmd_collections(message)

@dp.message(F.text == "🌪")
async def reply_filter(message: types.Message):
    await cmd_filter(message)

@dp.message(F.text == "⚙️")
async def reply_settings(message: types.Message):
    await cmd_settings(message)

@dp.message(F.text == "⭐")
async def reply_favorites(message: types.Message):
    await cb_favorites_list(message)

# ================= SEARCH HANDLER =================
@dp.message(Command("search"))
@dp.callback_query(F.data == "start_search")
async def cmd_search_handler(event: types.Message | types.CallbackQuery, state: FSMContext):
    if not await check_sub(event.from_user.id):
        await event.answer("⚠️ Подпишитесь на канал @kinorave_tg !")
        return
    await state.set_state(SearchStates.waiting_for_query)
    text = "🔍 Введите название фильма или сериала для поиска (можно с маленькой буквы):"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")]])
    
    if isinstance(event, types.CallbackQuery):
        await event.message.edit_text(text, reply_markup=kb)
    else:
        await event.answer(text, reply_markup=kb)

@dp.message(SearchStates.waiting_for_query)
async def process_search_query(message: types.Message, state: FSMContext):
    query = message.text
    movies = await search_kinopoisk(query)
    
    if not movies:
        await message.answer("❌ Ничего не найдено по вашему запросу. Попробуйте написать название точнее.")
        return

    for movie in movies[:3]:
        movie_id = movie.get("id")
        title = html.escape(movie.get("name") or movie.get("alternativeName") or "Без названия")
        year = movie.get("year", "Н/Д")
        rating = movie.get("rating", {}).get("kp", "Н/Д")
        desc = html.escape(movie.get("description", "Описание отсутствует.")[:200]) + "..."
        poster = movie.get("poster", {}).get("url")
        
        caption = f"🎬 <b>{title}</b> ({year})\n⭐ Рейтинг: {rating}\n\n📝 {desc}"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="▶️ Смотреть", callback_data=f"watch_{movie_id}")],
            [InlineKeyboardButton(text="⭐ В избранное", callback_data=f"fav_add_{movie_id}_{title[:15]}")],
            [InlineKeyboardButton(text="⬅️ В меню", callback_data="back_to_main")]
        ])
        
        if poster:
            await message.answer_photo(photo=poster, caption=caption, parse_html="HTML", reply_markup=kb)
        else:
            await message.answer(text=caption, parse_html="HTML", reply_markup=kb)
    
    await state.clear()
# ================= FAVORITES HANDLERS =================
@dp.callback_query(F.data.startswith("fav_add_"))
async def cb_add_favorites(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    movie_id = parts[2]
    movie_title = "_".join(parts[3:])
    add_to_favorites(callback.from_user.id, movie_id, movie_title)
    await callback.answer("⭐ Фильм успешно добавлен в Избранное!", show_alert=True)

@dp.message(Command("favorites"))
@dp.callback_query(F.data == "favorites")
async def cb_favorites_list(event: types.Message | types.CallbackQuery):
    user_id = event.from_user.id
    favs = load_favorites()
    user_favs = favs.get(str(user_id), {})
    
    if not user_favs:
        text = "⭐ <b>Ваше избранное</b>\n\nПока пусто. Добавляйте фильмы во время поиска!"
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")]])
    else:
        text = "⭐ <b>Ваши сохраненные фильмы:</b>"
        buttons = []
        for m_id, m_title in user_favs.items():
            buttons.append([
                InlineKeyboardButton(text=f"🎬 {m_title}", callback_data=f"watch_{m_id}"),
                InlineKeyboardButton(text="❌ Удалить", callback_data=f"fav_del_{m_id}")
            ])
        buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")])
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        
    if isinstance(event, types.CallbackQuery):
        await event.message.edit_text(text, parse_html="HTML", reply_markup=kb)
    else:
        await event.answer(text, parse_html="HTML", reply_markup=kb)

@dp.callback_query(F.data.startswith("fav_del_"))
async def cb_del_favorite(callback: types.CallbackQuery):
    movie_id = callback.data.split("_")[2]
    remove_from_favorites(callback.from_user.id, movie_id)
    await callback.answer("🗑 Фильм удален из Избранного", show_alert=False)
    await cb_favorites_list(callback)

# ================= MOVIE PLAYER & INTERACTIVE INTERFACE =================
@dp.callback_query(F.data.startswith("watch_"))
async def movie_player_interface(callback: types.CallbackQuery):
    movie_id = callback.data.split("_")[1]
    text = (
        "🎬 <b>Плеер фильма / сериала</b>\n\n"
        "1 сезон 1 серия\n\n"
        "▶️ Жми кнопку ниже для просмотра."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="▶️ Смотреть видео", callback_data=f"play_{movie_id}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data=f"watch_{movie_id}"), InlineKeyboardButton(text="🎞 Серии", callback_data=f"seasons_{movie_id}"), InlineKeyboardButton(text="Вперед ▶️", callback_data=f"watch_{movie_id}")],
        [InlineKeyboardButton(text="⚙️ Озвучка", callback_data=f"audio_{movie_id}"), InlineKeyboardButton(text="🎛 Качество", callback_data=f"qual_{movie_id}")],
        [InlineKeyboardButton(text="🔔 Уведомлять", callback_data="notify"), InlineKeyboardButton(text="⭐ В избранное", callback_data=f"fav_add_{movie_id}_Фильм")],
        [InlineKeyboardButton(text="🔍 Поиск", callback_data="start_search")]
    ])
    try:
        await callback.message.edit_caption(caption=text, parse_html="HTML", reply_markup=kb)
    except:
        await callback.message.edit_text(text=text, parse_html="HTML", reply_markup=kb)

@dp.callback_query(F.data.startswith("play_"))
async def play_video_action(callback: types.CallbackQuery):
    await callback.answer("🎬 Запуск видео...", show_alert=False)

@dp.callback_query(F.data.startswith("seasons_"))
async def select_seasons(callback: types.CallbackQuery):
    movie_id = callback.data.split("_")[1]
    text = "🎬 <b>Выбор сезона:</b>"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1 Сезон", callback_data=f"episodes_{movie_id}_1")],
        [InlineKeyboardButton(text="2 Сезон", callback_data=f"episodes_{movie_id}_2")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"watch_{movie_id}")]
    ])
    await callback.message.edit_caption(caption=text, parse_html="HTML", reply_markup=kb)

@dp.callback_query(F.data.startswith("qual_"))
async def select_quality(callback: types.CallbackQuery):
    movie_id = callback.data.split("_")[1]
    text = "🎛 <b>Выберите качество видео:</b>"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="720p HD", callback_data=f"set_q_{movie_id}_720")],
        [InlineKeyboardButton(text="1080p Full HD", callback_data=f"set_q_{movie_id}_1080")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"watch_{movie_id}")]
    ])
    await callback.message.edit_caption(caption=text, parse_html="HTML", reply_markup=kb)

@dp.callback_query(F.data.startswith("audio_"))
async def select_audio(callback: types.CallbackQuery):
    movie_id = callback.data.split("_")[1]
    text = "⚙️ <b>Выберите вариант озвучки:</b>"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Дубляж", callback_data=f"set_a_{movie_id}_dub")],
        [InlineKeyboardButton(text="Многоголосый", callback_data=f"set_a_{movie_id}_mvo")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"watch_{movie_id}")]
    ])
    await callback.message.edit_caption(caption=text, parse_html="HTML", reply_markup=kb)

@dp.callback_query(F.data.startswith("set_q_") | F.data.startswith("set_a_"))
async def apply_player_setting(callback: types.CallbackQuery):
    await callback.answer("Параметр успешно применен!", show_alert=False)
    parts = callback.data.split("_")
    movie_id = parts[2]
    await movie_player_interface(callback)

# ================= COLLECTIONS & FILTER =================
@dp.message(Command("collections"))
@dp.callback_query(F.data == "collections")
async def cmd_collections(event: types.Message | types.CallbackQuery):
    text = "📦 <b>Подборки фильмов и сериалов</b>\n🍿 <b>Приятного просмотра!</b>"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="▶️ Смотрят сегодня", callback_data="coll_today")],
        [InlineKeyboardButton(text="🔥 Популярное", callback_data="coll_pop")],
        [InlineKeyboardButton(text="🎬 Новинки фильмов", callback_data="coll_new_movies")],
        [InlineKeyboardButton(text="🔍 Поиск подборок", callback_data="start_search")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")]
    ])
    if isinstance(event, types.CallbackQuery):
        await event.message.edit_text(text, parse_html="HTML", reply_markup=kb)
    else:
        await message.answer(text, parse_html="HTML", reply_markup=kb)

@dp.callback_query(F.data.startswith("coll_"))
async def show_collection_items(callback: types.CallbackQuery):
    movies = await get_collection(callback.data)
    if not movies:
        await callback.answer("Ничего не найдено в этой подборке.", show_alert=True)
        return
    
    movie = random.choice(movies)
    movie_id = movie.get("id")
    title = html.escape(movie.get("name") or movie.get("alternativeName", "Фильм"))
    rating = movie.get("rating", {}).get("kp", "—")
    poster = movie.get("poster", {}).get("url")
    
    text = f"🎬 <b>{title}</b>\n⭐ Рейтинг: {rating}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="▶️ Смотреть", callback_data=f"watch_{movie_id}")],
        [InlineKeyboardButton(text="⭐ В избранное", callback_data=f"fav_add_{movie_id}_{title[:15]}")],
        [InlineKeyboardButton(text="⬅️ Назад к подборкам", callback_data="collections")]
    ])
    
    if poster:
        await callback.message.answer_photo(photo=poster, caption=text, parse_html="HTML", reply_markup=kb)
    else:
        await callback.message.answer(text=text, parse_html="HTML", reply_markup=kb)
    await callback.answer()

@dp.message(Command("filter"))
@dp.callback_query(F.data == "filter")
async def cmd_filter(event: types.Message | types.CallbackQuery):
    text = (
        "🌪 <b>Фильтр поиска</b>\n\n"
        "<b>Выбрано:</b>\n"
        "📊 Рейтинг: 5.0 - 10.0\n"
        "📅 Год: все\n"
        "🎬 Тип: все"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Искать по фильтру", callback_data="f_search")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")]
    ])
    if isinstance(event, types.CallbackQuery):
        await event.message.edit_text(text, parse_html="HTML", reply_markup=kb)
    else:
        await message.answer(text, parse_html="HTML", reply_markup=kb)

@dp.callback_query(F.data == "f_search")
async def filter_search_action(callback: types.CallbackQuery):
    await callback.answer("Поиск по фильтру выполнен!", show_alert=False)

# ================= SETTINGS & UTILS =================
@dp.message(Command("settings"))
@dp.callback_query(F.data == "settings")
async def cmd_settings(event: types.Message | types.CallbackQuery):
    user_id = event.from_user.id
    users = load_users()
    reg_date = users.get(user_id, "29.08.2026")
    
    text = (
        f"⚙️ <b>Настройки бота</b>\n\n"
        f"🆔 <code>{user_id}</code>\n"
        f"📅 Дата регистрации: {reg_date}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⤴️ Поделиться", callback_data="share")],
        [InlineKeyboardButton(text="🎧 Поддержка", callback_data="help")],
        [InlineKeyboardButton(text="🛡 Подключить VPN", url=VPN_LINK)],
        [InlineKeyboardButton(text="🔍 Поиск", callback_data="start_search")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")]
    ])
    if isinstance(event, types.CallbackQuery):
        await event.message.edit_text(text, parse_html="HTML", reply_markup=kb)
    else:
        await message.answer(text, parse_html="HTML", reply_markup=kb)

@dp.callback_query(F.data == "help")
async def cb_help(callback: types.CallbackQuery):
    text = (
        "💡 <b>Инструкция по использованию:</b>\n\n"
        "Отправь название фильма или сериала в чат для быстрого поиска.\n\n"
        f"Поддержка: {REQUIRED_CHANNEL}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="settings")]])
    await callback.message.edit_text(text, parse_html="HTML", reply_markup=kb)

@dp.callback_query(F.data == "share")
async def cb_share(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    ref_link = f"https://t.me/kinorave_tg?start=ref_{user_id}"
    text = (
        "⤴️ <b>Поделиться ссылкой</b>\n\n"
        "📌 <b>Приглашай друзей в нашего бота!</b>\n\n"
        "🔗 <b>Твоя персональная ссылка:</b>\n"
        f"<code>{ref_link}</code>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⤴️ Поделиться", url=f"https://t.me/share/url?url={ref_link}&text=Смотри%20фильмы%20в%20Кинорейв!")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="settings")]
    ])
    await callback.message.edit_text(text, parse_html="HTML", reply_markup=kb)

@dp.callback_query(F.data == "back_to_main")
async def cb_back_to_main(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await show_welcome(callback, edit=True)

# ================= BOT COMMANDS MENU & STARTUP =================
async def set_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="🔄 Перезапустить"),
        BotCommand(command="search", description="🔍 Поиск"),
        BotCommand(command="collections", description="📦 Подборки"),
        BotCommand(command="filter", description="🌪 Фильтр"),
        BotCommand(command="settings", description="⚙️ Настройки"),
        BotCommand(command="share", description="⤴️ Поделиться"),
        BotCommand(command="help", description="💡 Помощь"),
        BotCommand(command="admin", description="🛠 Админ-панель")
    ]
    await bot.set_my_commands(commands, scope=BotCommandScopeDefault())

async def main():
    # Удаляем вебхук перед запуском поллинга, чтобы избежать конфликтов на Render
    await bot.delete_webhook(drop_pending_updates=True)
    await set_commands(bot)
    logging.info("Bot KINOrave successfully started!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
