# ==========================================
# ЧАСТЬ 1: БАЗА ДАННЫХ (SQLite)
# ==========================================
import os
import asyncio
import logging
import sqlite3
import yt_dlp
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, 
    InlineKeyboardMarkup, InlineKeyboardButton, 
    FSInputFile
)
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

DB_NAME = "bot_database.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            language TEXT DEFAULT 'ru',
            is_vip INTEGER DEFAULT 0,
            vip_until TEXT DEFAULT NULL,
            download_count INTEGER DEFAULT 0,
            referrals_count INTEGER DEFAULT 0,
            bonus_received INTEGER DEFAULT 0,
            referred_by INTEGER DEFAULT NULL
        )
    ''')
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def add_user(user_id, username=None, referred_by=None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO users (user_id, username, referred_by) VALUES (?, ?, ?)",
            (user_id, username, referred_by)
        )
        if referred_by and referred_by != user_id:
            cursor.execute("UPDATE users SET referrals_count = referrals_count + 1 WHERE user_id = ?", (referred_by,))
        conn.commit()
    conn.close()

def set_user_language(user_id, lang):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET language = ? WHERE user_id = ?", (lang, user_id))
    conn.commit()
    conn.close()

def increment_downloads(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET download_count = download_count + 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_all_users_count():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_all_user_ids():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    ids = [row[0] for row in cursor.fetchall()]
    conn.close()
    return ids

# Инициализируем БД при старте
init_db()
# ==========================================
# ЧАСТЬ 2: КЛАВИАТУРЫ И МЕНЮ
# ==========================================

def get_main_keyboard():
    kb = [
        [KeyboardButton(text="📥 Скачать медиа")],
        [KeyboardButton(text="👤 Мой профиль"), KeyboardButton(text="⚙️ Настройки")],
        [KeyboardButton(text="🎁 Бесплатный VIP за друзей")],
        [KeyboardButton(text="ℹ️ О боте и правилах"), KeyboardButton(text="🔄 Перезапустить бота")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_platforms_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎵 TikTok", callback_data="plat_tiktok"),
            InlineKeyboardButton(text="📺 YouTube / Shorts", callback_data="plat_youtube")
        ],
        [InlineKeyboardButton(text="📸✨ Instagram Reels", callback_data="plat_instagram")],
        [InlineKeyboardButton(text="🌐 Другие платформы", callback_data="plat_other")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_download")]
    ])

def get_settings_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Сменить язык / Change Language", callback_data="change_lang")],
        [InlineKeyboardButton(text="📖 Гайд по использованию", callback_data="show_guide")]
    ])

def get_languages_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="setlang_ru"),
            InlineKeyboardButton(text="🇺🇦 Українська", callback_data="setlang_ua"),
            InlineKeyboardButton(text="🇬🇧 English", callback_data="setlang_en")
        ],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_settings")]
    ])

def get_profile_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Продлить / Получить VIP", callback_data="buy_vip")],
        [InlineKeyboardButton(text="⭐ Купить Stars", callback_data="buy_stars")]
    ])

def get_back_to_menu_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_to_menu")]
    ])

def get_admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Сделать рассылку", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="📊 Полная статистика", callback_data="admin_stats")]
    ])
# ==========================================
# ЧАСТЬ 3: МОДУЛЬ ЗАГРУЗКИ (yt-dlp)
# ==========================================

async def download_media(url: str, user_id: int) -> str:
    os.makedirs("downloads", exist_ok=True)
    
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': f'downloads/{user_id}_%(id)s.%(ext)s',
        'max_filesize': 50 * 1024 * 1024,  # Лимит 50 МБ
        'quiet': True,
        'no_warnings': True
    }

    loop = asyncio.get_event_loop()

    def _extract():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return ydl.prepare_filename(info)

    filename = await loop.run_in_executor(None, _extract)
    return filename
# ==========================================
# ЧАСТЬ 4: ЛОГИКА БОТА И ХЭНДЛЕРЫ
# ==========================================

ADMIN_ID = 6444735646
BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=BOT_TOKEN if BOT_TOKEN else "DUMMY_TOKEN")
dp = Dispatcher(storage=MemoryStorage())
logging.basicConfig(level=logging.INFO)

class DownloadState(StatesGroup):
    waiting_for_link = State()

class AdminState(StatesGroup):
    waiting_for_broadcast = State()

@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    args = message.text.split()
    ref_id = int(args[1].replace("ref_", "")) if len(args) > 1 and args[1].startswith("ref_") else None
    
    add_user(message.from_user.id, message.from_user.username, referred_by=ref_id)
    
    await message.answer(
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        "Добро пожаловать в **PulseFetch** — бот для скачивания медиа из TikTok, YouTube, Instagram и других сервисов!\n\n"
        "Воспользуйся меню ниже для выбора нужного действия 👇",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )

@dp.message(F.text == "🔄 Перезапустить бота")
async def restart_cmd(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "🔄 Бот успешно перезапущен!\n\n👇 Нажми кнопку «📥 Скачать медиа», чтобы выбрать платформу!",
        reply_markup=get_main_keyboard()
    )

@dp.message(F.text == "ℹ️ О боте и правилах")
async def about_cmd(message: types.Message):
    text = (
        "🤖 **О боте PulseFetch:**\n\n"
        "Бот создан для удобной и быстрой загрузки медиа из TikTok, YouTube, Instagram Reels и других платформ.\n\n"
        "⚡️ **СРАВНЕНИЕ ТАРИФОВ И ВОЗМОЖНОСТЕЙ**\n\n"
        "👤 **Обычный тариф (Бесплатно):**\n"
        "• 📁 Максимальный размер файла: до 50 МБ\n"
        "• 🎬 Качество видео: до 720p\n"
        "• 🏷 Водяной знак бота: есть\n\n"
        "🌟 **VIP Подписка:**\n"
        "• 📁 Максимальный размер файла: до 50 МБ\n"
        "• 🎬 Качество видео: максимальное (1080p и выше)\n"
        "• 🎵 Выгрузка аудиодорожек (MP3)\n"
        "• 🏷 Водяной знак бота: отсутствует\n\n"
        "💡 Купи VIP за Stars или получи 24 часа бесплатно за 3 друзей!"
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=get_back_to_menu_keyboard())

@dp.message(F.text == "🎁 Бесплатный VIP за друзей")
async def ref_cmd(message: types.Message):
    user = get_user(message.from_user.id)
    ref_count = user[6] if user else 0
    bonus_count = user[7] if user else 0
    left_to_vip = max(0, 3 - (ref_count % 3))
    bot_info = await bot.get_me()

    text = (
        "🎁 **Получи VIP на 24 часа бесплатно!**\n\n"
        "Приглашай друзей. За каждые 3 друга — VIP на 24 часа (до 3 раз)!\n\n"
        f"🔗 **Твоя ссылка:**\nhttps://t.me/{bot_info.username}?start=ref_{message.from_user.id}\n\n"
        "📊 **Твоя статистика:**\n"
        f"• Приглашено: {ref_count}\n"
        f"• Получено бонусов: {bonus_count} из 3\n\n"
        f"🎯 **До следующих 24 часов VIP осталось:** {left_to_vip}"
    )
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "👤 Мой профиль")
async def profile_cmd(message: types.Message):
    user = get_user(message.from_user.id)
    downloads = user[5] if user else 0
    ref_count = user[6] if user else 0
    is_vip = user[3] if user else 0
    vip_status = "🌟 VIP-подписка (активна)" if is_vip else "👤 Обычный тариф"

    text = (
        "👤 **Твой профиль**\n\n"
        f"🆔 **ID:** `{message.from_user.id}`\n"
        f"👤 **Имя:** {message.from_user.first_name}\n"
        f"Статус: {vip_status}\n\n"
        "📊 **Твоя статистика:**\n"
        f"• 📥 Всего скачано файлов: `{downloads}`\n"
        f"• 👥 Приглашено друзей: `{ref_count}`\n"
        "• ⭐️ Баланс Stars: `0 ⭐️`"
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=get_profile_keyboard())

@dp.message(F.text == "⚙️ Настройки")
async def settings_cmd(message: types.Message):
    user = get_user(message.from_user.id)
    lang_code = user[2] if user else "ru"
    lang_map = {"ru": "Русский 🇷🇺", "ua": "Українська 🇺🇦", "en": "English 🇬🇧"}
    current_lang = lang_map.get(lang_code, "Русский 🇷🇺")

    text = (
        "⚙️ **Настройки бота**\n\n"
        "Здесь ты можешь изменить язык интерфейса или посмотреть краткую инструкцию по работе с ботом.\n\n"
        f"🌐 **Текущий язык:** {current_lang}\n"
        "📖 **Гайд по использованию:** Доступен ниже\n\n"
        "👇 Выбери нужный раздел:"
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=get_settings_keyboard())

@dp.message(F.text == "📥 Скачать медиа")
async def choose_platform(message: types.Message):
    await message.answer(
        "📁 **Шаг 1 из 2: Выбери платформу, с которой хочешь скачать контент:**",
        parse_mode="Markdown",
        reply_markup=get_platforms_keyboard()
    )

@dp.callback_query(F.data.startswith("plat_"))
async def platform_selected(callback: types.CallbackQuery, state: FSMContext):
    platform = callback.data.split("_")[1]
    await state.update_data(platform=platform)
    await state.set_state(DownloadState.waiting_for_link)
    
    await callback.message.edit_text(
        "📥 **Шаг 2 из 2: Отправь ссылку на видео или контент**\n\n"
        "Просто вставь и отправь ссылку в этот чат!",
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query(F.data == "cancel_download")
async def cancel_download(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Загрузка отменена.")
    await callback.answer()

@dp.message(DownloadState.waiting_for_link)
async def process_download_link(message: types.Message, state: FSMContext):
    url = message.text.strip()
    if not url.startswith("http"):
        await message.answer("⚠️ Пожалуйста, отправь корректную ссылку, начинающуюся с http:// или https://")
        return

    status_msg = await message.answer("⏳ **Загрузка медиа... Пожалуйста, подожди.**", parse_mode="Markdown")
    filename = None

    try:
        filename = await download_media(url, message.from_user.id)
        await status_msg.edit_text("🚀 **Отправка файла в чат...**", parse_mode="Markdown")
        
        video_file = FSInputFile(filename)
        await message.answer_video(video=video_file, caption="✅ Ваш контент успешно скачан с помощью @PulseFetchBot!")
        
        increment_downloads(message.from_user.id)
        await status_msg.delete()

    except Exception as e:
        logging.error(f"Download error: {e}")
        await status_msg.edit_text("❌ **Ошибка при скачивании.** Убедитесь, что ссылка правильная и видео не превышает 50 МБ.")
    
    finally:
        if filename and os.path.exists(filename):
            os.remove(filename)
        await state.clear()

@dp.callback_query(F.data == "change_lang")
async def change_lang_menu(callback: types.CallbackQuery):
    await callback.message.edit_text("🌐 **Выбери язык интерфейса / Select interface language:**", parse_mode="Markdown", reply_markup=get_languages_keyboard())

@dp.callback_query(F.data.startswith("setlang_"))
async def set_language(callback: types.CallbackQuery):
    lang = callback.data.split("_")[1]
    set_user_language(callback.from_user.id, lang)
    
    lang_names = {"ru": "Русский 🇷🇺", "ua": "Українська 🇺🇦", "en": "English 🇬🇧"}
    await callback.answer(f"Язык изменен на: {lang_names.get(lang)}")
    await callback.message.edit_text(f"✅ **Язык успешно изменен на {lang_names.get(lang)}!**", parse_mode="Markdown")

@dp.callback_query(F.data == "show_guide")
async def show_guide(callback: types.CallbackQuery):
    text = (
        "📖 **Как пользоваться ботом PulseFetch:**\n\n"
        "1️⃣ Нажми кнопку «📥 Скачать медиа» в главном меню.\n"
        "2️⃣ Выбери нужную платформу (TikTok, YouTube / Shorts, Instagram Reels и др.).\n"
        "3️⃣ Отправь боту ссылку на видео или пост.\n"
        "4️⃣ Подожди пару секунд — бот пришлет готовый файл прямо в чат!\n\n"
        "💡 **Совет:** если у тебя VIP-подписка, видео скачается в максимальном качестве без водяного знака, а также появится возможность скачивать аудиодорожки (MP3)."
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад в настройки", callback_data="back_to_settings")]
    ]))

@dp.callback_query(F.data == "back_to_settings")
async def back_to_settings_handler(callback: types.CallbackQuery):
    user = get_user(callback.from_user.id)
    lang_code = user[2] if user else "ru"
    lang_map = {"ru": "Русский 🇷🇺", "ua": "Українська 🇺🇦", "en": "English 🇬🇧"}
    
    text = (
        "⚙️ **Настройки бота**\n\n"
        "Здесь ты можешь изменить язык интерфейса или посмотреть краткую инструкцию по работе с ботом.\n\n"
        f"🌐 **Текущий язык:** {lang_map.get(lang_code, 'Русский 🇷🇺')}\n"
        "📖 **Гайд по использованию:** Доступен ниже\n\n"
        "👇 Выбери нужный раздел:"
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=get_settings_keyboard())

@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu_handler(callback: types.CallbackQuery):
    await callback.message.delete()
    await callback.message.answer("Главное меню:", reply_markup=get_main_keyboard())

@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    users_count = get_all_users_count()
    text = (
        "👑 **Админ-панель управления PulseFetch**\n\n"
        f"👥 Всего пользователей в базе: `{users_count}`\n\n"
        "Выбери действие ниже:"
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=get_admin_keyboard())

@dp.callback_query(F.data == "admin_broadcast")
async def start_broadcast(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminState.waiting_for_broadcast)
    await callback.message.edit_text("💬 Отправь текст или сообщение, которое необходимо разослать всем пользователям бота:")
    await callback.answer()

@dp.message(AdminState.waiting_for_broadcast)
async def process_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    user_ids = get_all_user_ids()
    success = 0
    failed = 0

    status_msg = await message.answer("🚀 **Рассылка запущена...**", parse_mode="Markdown")

    for uid in user_ids:
        try:
            await bot.copy_message(chat_id=uid, from_chat_id=message.chat.id, message_id=message.message_id)
            success += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1

    await status_msg.edit_text(
        f"✅ **Рассылка завершена!**\n\n"
        f"🟢 Успешно доставлено: `{success}`\n"
        f"🔴 Не доставлено (заблокировали бота): `{failed}`",
        parse_mode="Markdown"
    )
    await state.clear()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
