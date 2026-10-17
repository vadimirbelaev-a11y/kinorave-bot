# ==========================================
# ЧАСТЬ 1: БАЗА ДАННЫХ, ЯЗЫКИ И ГРУППЫ
# ==========================================
import os
import asyncio
import logging
import sqlite3
import yt_dlp
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandStart, ChatMemberUpdatedFilter, IS_MEMBER, IS_NOT_MEMBER
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, 
    InlineKeyboardMarkup, InlineKeyboardButton, 
    FSInputFile, ChatMemberUpdated
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

init_db()

# --- СЛОВАРЬ ПЕРЕВОДОВ ---
LOCALES = {
    "ru": {
        "btn_dl": "📥 Скачать медиа",
        "btn_profile": "👤 Мой профиль",
        "btn_settings": "⚙️ Настройки",
        "btn_ref": "🎁 Бесплатный VIP за друзей",
        "btn_about": "ℹ️ О боте и правилах",
        "btn_restart": "🔄 Перезапустить бота",
        "start": "👋 Привет, {name}!\n\nДобро пожаловать в **PulseFetch** — бот для скачивания медиа из TikTok, YouTube, Instagram и других сервисов!\n\nВоспользуйся меню ниже для выбора нужного действия 👇",
        "group_welcome": "👋 **Всем привет! Я бот PulseFetch!**\n\nЯ умею скачивать видео из **TikTok, YouTube / Shorts, Instagram Reels** и других сервисов прямо в этот чат!\n\n💡 **Как скачать:** просто отправьте ссылку на видео в чат, и я пришлю его готовым файлом!",
        "restart": "🔄 Бот успешно перезапущен!\n\n👇 Нажми кнопку «📥 Скачать медиа», чтобы выбрать платформу!",
        "step1": "📁 **Шаг 1 из 2: Выбери платформу, с которой хочешь скачать контент:**",
        "step2": "📥 **Шаг 2 из 2: Отправь ссылку на видео или контент**\n\nПросто вставь и отправь ссылку в этот чат!",
        "format_title": "🎛 **Выбери, что именно нужно скачать:**",
        "dl_loading": "⏳ **Загрузка медиа... Пожалуйста, подожди.**",
        "dl_sending": "🚀 **Отправка файла в чат...**",
        "dl_error": "❌ **Ошибка при скачивании.** Убедитесь, что ссылка правильная и видео не превышает 50 МБ.",
        "lang_changed": "✅ **Язык успешно изменен!**",
        "guide": "📖 **Как пользоваться ботом PulseFetch:**\n\n1️⃣ Нажми кнопку «📥 Скачать медиа» в главном меню.\n2️⃣ Выбери нужную платформу.\n3️⃣ Отправь боту ссылку на видео.\n4️⃣ Выбери формат (видео или MP3) — бот пришлет готовый файл!"
    },
    "ua": {
        "btn_dl": "📥 Завантажити медіа",
        "btn_profile": "👤 Мій профіль",
        "btn_settings": "⚙️ Налаштування",
        "btn_ref": "🎁 Безкоштовний VIP за друзів",
        "btn_about": "ℹ️ Про бота та правила",
        "btn_restart": "🔄 Перезапустити бота",
        "start": "👋 Привіт, {name}!\n\nЛаскаво просимо до **PulseFetch** — бота для завантаження медіа з TikTok, YouTube, Instagram та інших сервісів!\n\nСкористайся меню нижче 👇",
        "group_welcome": "👋 **Усім привіт! Я бот PulseFetch!**\n\nЯ вмію завантажувати відео з **TikTok, YouTube / Shorts, Instagram Reels** та інших сервісів прямо у цей чат!\n\n💡 **Як завантажити:** просто надішліть посилання на відео в чат, і я надішлю готовий файл!",
        "restart": "🔄 Бот успішно перезапущено!\n\n👇 Натисни кнопку «📥 Завантажити медіа», щоб обрати платформу!",
        "step1": "📁 **Крок 1 з 2: Обери платформу для завантаження:**",
        "step2": "📥 **Крок 2 з 2: Надішли посилання на відео або контент**\n\nПросто вставити та надішли посилання у цей чат!",
        "format_title": "🎛 **Обери, що саме потрібно завантажити:**",
        "dl_loading": "⏳ **Завантаження медіа... Зачекайте, будь ласка.**",
        "dl_sending": "🚀 **Надсилання файлу в чат...**",
        "dl_error": "❌ **Помилка завантаження.** Перевірте посилання та розмір файлу (до 50 МБ).",
        "lang_changed": "✅ **Мову успішно змінено!**",
        "guide": "📖 **Як користуватися ботом PulseFetch:**\n\n1️⃣ Натисни кнопку «📥 Завантажити медіа».\n2️⃣ Обери потрібну платформу.\n3️⃣ Надішли посилання на відео.\n4️⃣ Обери формат (відео чи MP3) — бот надішле файл!"
    },
    "en": {
        "btn_dl": "📥 Download media",
        "btn_profile": "👤 My profile",
        "btn_settings": "⚙️ Settings",
        "btn_ref": "🎁 Free VIP for friends",
        "btn_about": "ℹ️ About & Rules",
        "btn_restart": "🔄 Restart bot",
        "start": "👋 Hello, {name}!\n\nWelcome to **PulseFetch** — your bot for downloading media from TikTok, YouTube, Instagram and more!\n\nUse the menu below 👇",
        "group_welcome": "👋 **Hello everyone! I'm PulseFetch Bot!**\n\nI can download videos from **TikTok, YouTube / Shorts, Instagram Reels** and other platforms directly to this chat!\n\n💡 **How to download:** just send a video link into this chat, and I'll send you the file!",
        "restart": "🔄 Bot restarted successfully!\n\n👇 Click «📥 Download media» to choose platform!",
        "step1": "📁 **Step 1 of 2: Select platform:**",
        "step2": "📥 **Step 2 of 2: Send video link**\n\nJust paste and send link in this chat!",
        "format_title": "🎛 **Choose format to download:**",
        "dl_loading": "⏳ **Downloading media... Please wait.**",
        "dl_sending": "🚀 **Sending file...**",
        "dl_error": "❌ **Download error.** Make sure the link is correct and under 50 MB.",
        "lang_changed": "✅ **Language changed successfully!**",
        "guide": "📖 **How to use PulseFetch:**\n\n1️⃣ Click «📥 Download media».\n2️⃣ Choose platform.\n3️⃣ Send link.\n4️⃣ Choose format (video or MP3) — bot will send the file!"
    }
}

def t(user_id, key, **kwargs):
    user = get_user(user_id)
    lang = user[2] if user else "ru"
    text = LOCALES.get(lang, LOCALES["ru"]).get(key, LOCALES["ru"].get(key, ""))
    return text.format(**kwargs) if kwargs else text
# ==========================================
# ЧАСТЬ 2: КЛАВИАТУРЫ И МЕНЮ
# ==========================================

def get_main_keyboard(user_id: int):
    kb = [
        [KeyboardButton(text=t(user_id, "btn_dl"))],
        [KeyboardButton(text=t(user_id, "btn_profile")), KeyboardButton(text=t(user_id, "btn_settings"))],
        [KeyboardButton(text=t(user_id, "btn_ref"))],
        [KeyboardButton(text=t(user_id, "btn_about")), KeyboardButton(text=t(user_id, "btn_restart"))]
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

def get_format_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Только видео", callback_data="fmt_video")],
        [InlineKeyboardButton(text="🎵 Только озвучка (MP3)", callback_data="fmt_audio")],
        [InlineKeyboardButton(text="📦 Всё вместе (видео + звук)", callback_data="fmt_both")],
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

async def download_media(url: str, user_id: int, mode: str = "video", is_group: bool = False) -> str:
    os.makedirs("downloads", exist_ok=True)
    
    # В группах качаем всегда в обычном качестве (до 720p)
    if is_group:
        fmt_str = 'bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720][ext=mp4]/b'
    elif mode == "audio":
        fmt_str = 'bestaudio/best'
    else:
        fmt_str = 'bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b'

    ydl_opts = {
        'format': fmt_str,
        'outtmpl': f'downloads/{user_id}_%(id)s.%(ext)s',
        'max_filesize': 50 * 1024 * 1024,  # Лимит 50 МБ
        'quiet': True,
        'no_warnings': True
    }

    if mode == "audio":
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]

    loop = asyncio.get_event_loop()

    def _extract():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if mode == "audio":
                base, _ = os.path.splitext(ydl.prepare_filename(info))
                return base + ".mp3"
            return ydl.prepare_filename(info)

    filename = await loop.run_in_executor(None, _extract)
    return filename
# ==========================================
# ЧАСТЬ 4: ЛОГИКА БОТА, ГРУППЫ И ХЭНДЛЕРЫ
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

# --- ОБРАБОТКА ДОБАВЛЕНИЯ БОТА В ГРУППЫ ---
@dp.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=IS_NOT_MEMBER >> IS_MEMBER))
async def on_bot_added_to_group(event: ChatMemberUpdated):
    await event.answer(
        t(event.from_user.id, "group_welcome"),
        parse_mode="Markdown"
    )

# --- ЛОГИКА АВТОМАТИЧЕСКОГО ПЕРЕХВАТА ССЫЛОК В ГРУППАХ ---
@dp.message(F.chat.type.in_({"group", "supergroup"}) & F.text.contains("http"))
async def handle_group_link(message: types.Message):
    url = message.text.strip()
    status_msg = await message.reply("⏳ **Загрузка медиа для группы...**", parse_mode="Markdown")
    filename = None

    try:
        # Для групп всегда включаем режим обычного качества и водяного знака
        filename = await download_media(url, message.from_user.id, mode="video", is_group=True)
        file_input = FSInputFile(filename)
        await message.reply_video(video=file_input, caption="✅ Скачано через @PulseFetchBot")
        increment_downloads(message.from_user.id)
        await status_msg.delete()
    except Exception as e:
        logging.error(f"Group download error: {e}")
        await status_msg.edit_text("❌ Не удалось скачать медиа по этой ссылке.")
    finally:
        if filename and os.path.exists(filename):
            os.remove(filename)

# --- КОМАНДА /start В ЛИЧНЫХ СООБЩЕНИЯХ ---
@dp.message(CommandStart(), F.chat.type == "private")
async def start_cmd(message: types.Message):
    args = message.text.split()
    ref_id = int(args[1].replace("ref_", "")) if len(args) > 1 and args[1].startswith("ref_") else None
    
    add_user(message.from_user.id, message.from_user.username, referred_by=ref_id)
    
    await message.answer(
        t(message.from_user.id, "start", name=message.from_user.first_name),
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(message.from_user.id)
    )

# --- 🔄 ПЕРЕЗАПУСК БОТА ---
@dp.message(F.text.in_({"🔄 Перезапустить бота", "🔄 Перезапустити бота", "🔄 Restart bot"}))
async def restart_cmd(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        t(message.from_user.id, "restart"),
        reply_markup=get_main_keyboard(message.from_user.id)
    )

# --- ℹ️ О БОТЕ И ПРАВИЛАХ ---
@dp.message(F.text.in_({"ℹ️ О боте и правилах", "ℹ️ Про бота та правила", "ℹ️ About & Rules"}))
async def about_cmd(message: types.Message):
    text = (
        "🤖 **О боте PulseFetch / About PulseFetch:**\n\n"
        "⚡️ **СРАВНЕНИЕ ТАРИФОВ / TARIFS:**\n\n"
        "👤 **Обычный тариф / Free:**\n"
        "• Max size: 50 MB\n"
        "• Quality: up to 720p\n"
        "• Watermark: YES\n\n"
        "🌟 **VIP Subscription:**\n"
        "• Max size: 50 MB\n"
        "• Quality: Max (1080p+)\n"
        "• MP3 audio extraction: YES\n"
        "• Watermark: NO"
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=get_back_to_menu_keyboard())

# --- 🎁 БЕСПЛАТНЫЙ VIP ---
@dp.message(F.text.in_({"🎁 Бесплатный VIP за друзей", "🎁 Безкоштовний VIP за друзів", "🎁 Free VIP for friends"}))
async def ref_cmd(message: types.Message):
    user = get_user(message.from_user.id)
    ref_count = user[6] if user else 0
    bonus_count = user[7] if user else 0
    left_to_vip = max(0, 3 - (ref_count % 3))
    bot_info = await bot.get_me()

    text = (
        "🎁 **Получи VIP на 24 часа бесплатно!**\n\n"
        f"🔗 **Твоя ссылка:**\nhttps://t.me/{bot_info.username}?start=ref_{message.from_user.id}\n\n"
        "📊 **Статистика:**\n"
        f"• Приглашено: {ref_count}\n"
        f"• Бонусов: {bonus_count} / 3\n"
        f"🎯 **До VIP осталось:** {left_to_vip}"
    )
    await message.answer(text, parse_mode="Markdown")

# --- 👤 ПРОФИЛЬ ---
@dp.message(F.text.in_({"👤 Мой профиль", "👤 Мій профіль", "👤 My profile"}))
async def profile_cmd(message: types.Message):
    user = get_user(message.from_user.id)
    downloads = user[5] if user else 0
    ref_count = user[6] if user else 0
    is_vip = user[3] if user else 0
    vip_status = "🌟 VIP" if is_vip else "👤 Free"

    text = (
        f"👤 **Профиль:** {message.from_user.first_name}\n"
        f"🆔 **ID:** `{message.from_user.id}`\n"
        f"Статус: {vip_status}\n\n"
        f"• Скачано: `{downloads}`\n"
        f"• Друзей: `{ref_count}`"
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=get_profile_keyboard())

# --- ⚙️ НАСТРОЙКИ ---
@dp.message(F.text.in_({"⚙️ Настройки", "⚙️ Налаштування", "⚙️ Settings"}))
async def settings_cmd(message: types.Message):
    user = get_user(message.from_user.id)
    lang_code = user[2] if user else "ru"
    lang_map = {"ru": "Русский 🇷🇺", "ua": "Українська 🇺🇦", "en": "English 🇬🇧"}

    text = (
        "⚙️ **Настройки / Settings**\n\n"
        f"🌐 **Текущий язык:** {lang_map.get(lang_code, 'Русский 🇷🇺')}"
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=get_settings_keyboard())

# --- 📥 СКАЧАТЬ МЕДИА (ЛИЧНЫЕ СООБЩЕНИЯ) ---
@dp.message(F.text.in_({"📥 Скачать медиа", "📥 Завантажити медіа", "📥 Download media"}))
async def choose_platform(message: types.Message):
    await message.answer(
        t(message.from_user.id, "step1"),
        parse_mode="Markdown",
        reply_markup=get_platforms_keyboard()
    )

@dp.callback_query(F.data.startswith("plat_"))
async def platform_selected(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(DownloadState.waiting_for_link)
    await callback.message.edit_text(
        t(callback.from_user.id, "step2"),
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
        await message.answer("⚠️ Пожалуйста, отправь корректную ссылку!")
        return

    await state.update_data(url=url)
    await message.answer(
        t(message.from_user.id, "format_title"),
        parse_mode="Markdown",
        reply_markup=get_format_keyboard()
    )

@dp.callback_query(F.data.startswith("fmt_"))
async def process_format_choice(callback: types.CallbackQuery, state: FSMContext):
    format_type = callback.data.split("_")[1]
    data = await state.get_data()
    url = data.get("url")

    if not url:
        await callback.message.edit_text("❌ Ошибка: ссылка не найдена.")
        await state.clear()
        return

    status_msg = await callback.message.edit_text(t(callback.from_user.id, "dl_loading"), parse_mode="Markdown")
    filename = None

    try:
        mode = "audio" if format_type == "audio" else "video"
        filename = await download_media(url, callback.from_user.id, mode=mode)
        
        await status_msg.edit_text(t(callback.from_user.id, "dl_sending"), parse_mode="Markdown")
        file_input = FSInputFile(filename)
        
        if format_type == "audio":
            await callback.message.answer_audio(audio=file_input, caption="🎵 @PulseFetchBot")
        else:
            await callback.message.answer_video(video=file_input, caption="✅ @PulseFetchBot")
        
        increment_downloads(callback.from_user.id)
        await status_msg.delete()

    except Exception as e:
        logging.error(f"Download error: {e}")
        await status_msg.edit_text(t(callback.from_user.id, "dl_error"))
    
    finally:
        if filename and os.path.exists(filename):
            os.remove(filename)
        await state.clear()

# --- СМЕНА ЯЗЫКА ---
@dp.callback_query(F.data == "change_lang")
async def change_lang_menu(callback: types.CallbackQuery):
    await callback.message.edit_text("🌐 Выбери язык / Choose language:", reply_markup=get_languages_keyboard())

@dp.callback_query(F.data.startswith("setlang_"))
async def set_language(callback: types.CallbackQuery):
    lang = callback.data.split("_")[1]
    set_user_language(callback.from_user.id, lang)
    
    await callback.answer("✅ Done")
    await callback.message.edit_text(
        t(callback.from_user.id, "lang_changed"),
        parse_mode="Markdown"
    )
    # Обновляем главное меню под новый язык
    await callback.message.answer("Menu updated:", reply_markup=get_main_keyboard(callback.from_user.id))

@dp.callback_query(F.data == "show_guide")
async def show_guide(callback: types.CallbackQuery):
    await callback.message.edit_text(
        t(callback.from_user.id, "guide"),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_settings")]
        ])
    )

@dp.callback_query(F.data == "back_to_settings")
async def back_to_settings_handler(callback: types.CallbackQuery):
    await settings_cmd(callback.message)

@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu_handler(callback: types.CallbackQuery):
    await callback.message.delete()
    await callback.message.answer("Menu:", reply_markup=get_main_keyboard(callback.from_user.id))

# --- АДМИНКА ---
@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    users_count = get_all_users_count()
    await message.answer(f"👑 **Админ-панель**\n\n👥 Всего пользователей: `{users_count}`", parse_mode="Markdown", reply_markup=get_admin_keyboard())

@dp.callback_query(F.data == "admin_broadcast")
async def start_broadcast(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminState.waiting_for_broadcast)
    await callback.message.edit_text("💬 Отправь сообщение для рассылки:")
    await callback.answer()

@dp.message(AdminState.waiting_for_broadcast)
async def process_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    user_ids = get_all_user_ids()
    success, failed = 0, 0
    status_msg = await message.answer("🚀 Рассылка...")

    for uid in user_ids:
        try:
            await bot.copy_message(chat_id=uid, from_chat_id=message.chat.id, message_id=message.message_id)
            success += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1

    await status_msg.edit_text(f"✅ Готово!\nУспешно: `{success}`\nОшибок: `{failed}`", parse_mode="Markdown")
    await state.clear()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
