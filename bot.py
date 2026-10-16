import os
import re
import asyncio
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.enums import ParseMode, ChatType
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    FSInputFile, ReplyKeyboardMarkup, KeyboardButton, 
    InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice
)
import yt_dlp

from database import (
    init_db, db_add_user, check_vip_status_expiration, 
    db_get_user_info, db_set_user_vip_months, db_get_stats, 
    db_get_all_users, get_maintenance_mode, set_maintenance_mode
)

init_db()
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = "8945702554:AAGxV9zRNvf_iX17bh1GzHZLqh_wDap6lvE"
ADMIN_ID = 6444735646
BOT_USERNAME = "pulsefetch_bot"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

async def handle_ping(request):
    return web.Response(text="Bot is running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"Веб-сервер запущен на порту {port}.")

class DownloadStates(StatesGroup):
    waiting_for_link = State()
    waiting_for_format = State()

def get_main_keyboard(user_id: int, is_vip: int):
    vip_label = "🌟 VIP Статус (Активен)" if is_vip == 1 else "💎 Купить VIP (Без рекламы и 4K)"
    
    keyboard_rows = [
        [KeyboardButton(text="📥 Скачать медиа")],
        [KeyboardButton(text=vip_label)],
        [KeyboardButton(text="🎁 Бесплатный VIP за друзей"), KeyboardButton(text="🔄 Перезапустить бота")],
        [KeyboardButton(text="ℹ️ О боте и правилах")]
    ]
    
    if user_id == ADMIN_ID:
        keyboard_rows.insert(0, [KeyboardButton(text="👑 Админ-панель")])

    return ReplyKeyboardMarkup(keyboard=keyboard_rows, resize_keyboard=True)

def get_admin_panel_keyboard():
    is_maint = get_maintenance_mode()
    maint_text = "🟢 Выключить тех. работы" if is_maint == 'on' else "🔴 Включить тех. работы"
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Статистика бота")],
            [KeyboardButton(text=maint_text)],
            [KeyboardButton(text="📢 Сделать рассылку")],
            [KeyboardButton(text="⬅️ Выйти из админки")]
        ],
        resize_keyboard=True
    )

def get_restart_inline_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Главное меню / Перезапуск", callback_data="restart_bot")]
    ])

waiting_for_broadcast = set()

# Красивое текстовое сравнение возможностей обычного тарифа и VIP
def get_vip_comparison_text():
    return (
        "⚡️ **СРАВНЕНИЕ ТАРИФОВ И ВОЗМОЖНОСТЕЙ**\n\n"
        "👤 **Обычный тариф (Бесплатно):**\n"
        "• 📁 Максимальный размер файла: **до 500 МБ**\n"
        "• 🎬 Качество видео: **до 720p**\n"
        "• 🏷 Наличие водяных знаков / рекламы: **Да**\n"
        "• ⚡️ Скорость обработки: **Стандартная**\n\n"
        "🌟 **VIP Подписка:**\n"
        "• 📁 Максимальный размер файла: **до 2 ГБ**\n"
        "• 🎬 Качество видео: **Максимальное (1080p, 2K, 4K)**\n"
        "• 🚫 Водяные знаки и реклама: **Полностью отсутствуют**\n"
        "• ⚡️ Скорость обработки: **Приоритетная**\n"
        "• 🎵 Выгрузка чистых аудиодорожек (MP3) высочайшего качества\n\n"
        "💡 *Вы можете купить VIP за Telegram Stars или получить 24 часа бесплатно за приглашение 3 друзей!*"
    )

@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    
    if message.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
        await message.answer(f"👋 Привет! Я **PulseFetch** — бот для скачивания медиа. Просто отправь ссылку на видео в этот чат, и я скачаю его автоматически!", parse_mode=ParseMode.MARKDOWN)
        return

    if get_maintenance_mode() == 'on' and message.from_user.id != ADMIN_ID:
        await message.answer("🛠 В боте проводятся технические работы. Скоро вернемся!", parse_mode=ParseMode.MARKDOWN)
        return

    args = message.text.split()
    referrer_id = None
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            referrer_id = int(args[1].replace("ref_", ""))
        except ValueError:
            pass

    db_add_user(message.from_user.id, message.from_user.username, message.from_user.first_name, referrer_id)
    
    if referrer_id and referrer_id != message.from_user.id:
        try:
            await bot.send_message(referrer_id, f"🎉 По твоей ссылке перешел новый друг! Пригласи еще для получения 24 часов VIP.")
        except:
            pass

    is_vip = check_vip_status_expiration(message.from_user.id, ADMIN_ID)
    
    welcome_text = (
        f"👋 **Привет, {message.from_user.first_name}!**\n\n"
        f"Я универсальный бот **PulseFetch** для скачивания медиа.\n\n"
        f"📌 **Твой текущий тариф:** {'🌟 **VIP (До 2 ГБ, 4K, Без рекламы)**' if is_vip else '👤 **Обычный (До 500 МБ, 720p)**'}\n\n"
        f"👇 Нажми кнопку **«📥 Скачать медиа»**, чтобы выбрать платформу!"
    )
    
    await message.answer(welcome_text, reply_markup=get_main_keyboard(message.from_user.id, is_vip), parse_mode=ParseMode.MARKDOWN)

@dp.message(F.text == "🔄 Перезапустить бота")
async def restart_button_handler(message: types.Message, state: FSMContext):
    await state.clear()
    if message.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
        return

    if get_maintenance_mode() == 'on' and message.from_user.id != ADMIN_ID:
        await message.answer("🛠 В боте проводятся технические работы. Скоро вернемся!", parse_mode=ParseMode.MARKDOWN)
        return

    is_vip = check_vip_status_expiration(message.from_user.id, ADMIN_ID)
    welcome_text = (
        f"🔄 **Бот успешно перезапущен!**\n\n"
        f"👇 Нажми кнопку **«📥 Скачать медиа»**, чтобы выбрать платформу!"
    )
    await message.answer(welcome_text, reply_markup=get_main_keyboard(message.from_user.id, is_vip), parse_mode=ParseMode.MARKDOWN)

@dp.message(F.text == "ℹ️ О боте и правилах")
async def about_bot_handler(message: types.Message, state: FSMContext):
    await state.clear()
    if message.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
        return

    if get_maintenance_mode() == 'on' and message.from_user.id != ADMIN_ID:
        await message.answer("🛠 В боте проводятся технические работы.")
        return

    info_text = (
        f"🤖 **О боте PulseFetch:**\n\n"
        f"Бот создан для удобной и быстрой загрузки медиа из TikTok, YouTube, Instagram Reels и других платформ.\n\n"
        f"{get_vip_comparison_text()}\n\n"
        f"⚡️ Нажми кнопку ниже, чтобы вернуться в главная меню:"
    )
    await message.answer(info_text, reply_markup=get_restart_inline_keyboard(), parse_mode=ParseMode.MARKDOWN)

@dp.message(F.text == "👑 Админ-панель")
async def open_admin_panel(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.clear()
    await message.answer("👑 **Панель администратора открыта:**", reply_markup=get_admin_panel_keyboard(), parse_mode=ParseMode.MARKDOWN)

@dp.message(F.text == "⬅️ Выйти из админки")
async def exit_admin_panel(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.clear()
    is_vip = check_vip_status_expiration(message.from_user.id, ADMIN_ID)
    await message.answer("Выход из админ-панели.", reply_markup=get_main_keyboard(message.from_user.id, is_vip))

@dp.message(F.text == "📊 Статистика бота")
async def admin_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    total, vips = db_get_stats()
    maint = "Включены 🔴" if get_maintenance_mode() == 'on' else "Выключены 🟢"
    await message.answer(f"📊 **Статистика:**\n👥 Всего пользователей: `{total}`\n🌟 VIP пользователей: `{vips}`\n🛠 Тех. работы: {maint}", parse_mode=ParseMode.MARKDOWN)

@dp.message(F.text.in_({"🟢 Выключить тех. работы", "🔴 Включить тех. работы"}))
async def admin_toggle_maint(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    curr = get_maintenance_mode()
    set_maintenance_mode('off' if curr == 'on' else 'on')
    await message.answer("Состояние тех. работ изменено.", reply_markup=get_admin_panel_keyboard())

@dp.message(F.text == "📢 Сделать рассылку")
async def admin_broadcast(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    waiting_for_broadcast.add(ADMIN_ID)
    await message.answer("✍️ Отправь текст для рассылки всем пользователям:")

@dp.message(F.text == "📥 Скачать медиа")
async def choose_platform_menu(message: types.Message, state: FSMContext):
    await state.clear()
    if message.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
        return

    if get_maintenance_mode() == 'on' and message.from_user.id != ADMIN_ID:
        await message.answer("🛠 В боте проводятся технические работы.")
        return

    platforms_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎵 TikTok", callback_data="platform_tiktok"),
         InlineKeyboardButton(text="📺 YouTube / Shorts", callback_data="platform_youtube")],
        [InlineKeyboardButton(text="📸 Instagram Reels", callback_data="platform_insta")],
        [InlineKeyboardButton(text="🌐 Другие платформы", callback_data="platform_other")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_action")]
    ])
    await message.answer(
        "📂 **Шаг 1 из 2:** Выбери платформу, с которой хочешь скачать контент:",
        reply_markup=platforms_kb,
        parse_mode=ParseMode.MARKDOWN
    )

@dp.callback_query(F.data.startswith("platform_"))
async def process_platform_choice(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if get_maintenance_mode() == 'on' and callback.from_user.id != ADMIN_ID:
        await callback.message.answer("🛠 В боте проводятся технические работы.")
        return

    platform_code = callback.data.replace("platform_", "")
    platform_names = {
        "tiktok": "TikTok",
        "youtube": "YouTube / Shorts",
        "insta": "Instagram Reels",
        "other": "Другие платформы (Facebook, Pinterest, X/Twitter, SoundCloud и др.)"
    }
    selected_platform_name = platform_names.get(platform_code, "Медиа")
    
    await state.update_data(platform=platform_code)
    await state.set_state(DownloadStates.waiting_for_link)
    
    if platform_code == "other":
        hint_text = (
            f"🌐 Выбрана категория: **{selected_platform_name}**.\n\n"
            f"📌 **Поддерживаются:** Facebook, Pinterest, X (Twitter), SoundCloud, Twitch.\n"
            f"⚠️ *Ссылки на TikTok, YouTube и Instagram через этот пункт отклоняются!*\n\n"
            f"🔗 Отправь ссылку:"
        )
    else:
        hint_text = (
            f"🔗 Выбрана платформа: **{selected_platform_name}**.\n\n"
            f"⚠️ *Отправляй ссылку строго на {selected_platform_name}.*\n\n"
            f"Отправь ссылку в чат:"
        )

    await callback.message.edit_text(
        hint_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад к выбору платформ", callback_data="back_to_platforms")]
        ])
    )

@dp.callback_query(F.data == "back_to_platforms")
async def back_to_platforms(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    platforms_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎵 TikTok", callback_data="platform_tiktok"),
         InlineKeyboardButton(text="📺 YouTube / Shorts", callback_data="platform_youtube")],
        [InlineKeyboardButton(text="📸 Instagram Reels", callback_data="platform_insta")],
        [InlineKeyboardButton(text="🌐 Другие платформы", callback_data="platform_other")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_action")]
    ])
    await callback.message.edit_text(
        "📂 **Шаг 1 из 2:** Выбери платформу, с которой хочешь скачать контент:",
        reply_markup=platforms_kb,
        parse_mode=ParseMode.MARKDOWN
    )
@dp.message(DownloadStates.waiting_for_link, F.text)
async def process_link_received(message: types.Message, state: FSMContext):
    if message.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
        return

    if get_maintenance_mode() == 'on' and message.from_user.id != ADMIN_ID:
        await message.answer("🛠 В боте проводятся технические работы.")
        return

    url = message.text.strip()
    if not re.match(r'https?://[^\s]+', url):
        await message.answer("❌ Это не похоже на ссылку. Пожалуйста, отправь корректную ссылку:")
        return

    data = await state.get_data()
    chosen_platform = data.get("platform")

    url_lower = url.lower()
    is_tiktok = "tiktok.com" in url_lower or "vm.tiktok.com" in url_lower
    is_youtube = "youtube.com" in url_lower or "youtu.be" in url_lower
    is_insta = "instagram.com" in url_lower or "instagr.am" in url_lower

    if chosen_platform == "tiktok" and not is_tiktok:
        await message.answer("❌ Ошибка! Ты выбрал **TikTok**, но ссылка не принадлежит этой платформе.")
        return
    if chosen_platform == "youtube" and not is_youtube:
        await message.answer("❌ Ошибка! Ты выбрал **YouTube / Shorts**, но ссылка не принадлежит этой платформе.")
        return
    if chosen_platform == "insta" and not is_insta:
        await message.answer("❌ Ошибка! Ты выбрал **Instagram**, но ссылка не принадлежит этой платформе.")
        return
    if chosen_platform == "other" and (is_tiktok or is_youtube or is_insta):
        await message.answer("❌ Ошибка! Для TikTok, YouTube и Instagram используй соответствующие кнопки в меню.")
        return

    await state.update_data(url=url)
    await state.set_state(DownloadStates.waiting_for_format)

    format_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Только видео", callback_data="fmt_video")],
        [InlineKeyboardButton(text="🎵 Только аудио (MP3)", callback_data="fmt_audio")],
        [InlineKeyboardButton(text="📦 Всё вместе (Видео + MP3)", callback_data="fmt_both")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_action")]
    ])

    await message.answer(
        "📦 **Шаг 2 из 2:** Ссылка успешно прошла проверку!\n\n"
        "Что именно ты хочешь скачать?",
        reply_markup=format_kb,
        parse_mode=ParseMode.MARKDOWN
    )

@dp.callback_query(DownloadStates.waiting_for_format, F.data.startswith("fmt_"))
async def process_format_choice(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    action = callback.data.replace("fmt_", "")
    
    if action == "cancel":
        await state.clear()
        await callback.message.edit_text("❌ Загрузка отменена.")
        return

    data = await state.get_data()
    url = data.get("url")
    await state.clear()

    if not url:
        await callback.message.edit_text("❌ Ошибка: ссылка потеряна. Начни заново через кнопку «📥 Скачать медиа».")
        return

    is_vip = check_vip_status_expiration(callback.from_user.id, ADMIN_ID)

    if not is_vip and action != "audio":
        await callback.message.edit_text(
            "📺 **Обработка запроса...**\n"
            "📌 *Лимит обычного тарифа — до 500 МБ (Качество 720p).*\n"
            "🌟 *Хочешь скачивать файлы до 2 ГБ и в 4K? Подключи VIP!*\n\n"
            "⏳ *Скачиваем файл...*",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await callback.message.edit_text("🔄 **Загружаем медиа...** Подожди пару секунд.", parse_mode=ParseMode.MARKDOWN)

    base_name = f"media_{callback.from_user.id}_{callback.message.message_id}"
    video_path = f"{base_name}.mp4"
    audio_path = f"{base_name}.mp3"

    try:
        loop = asyncio.get_running_loop()
        success = await loop.run_in_executor(None, download_selected_media_safe, url, base_name, is_vip, action)

        if not success:
            await callback.message.answer("❌ Не удалось скачать медиа. Возможно, файл превышает лимит по размеру (500 МБ для обычных / 2 ГБ для VIP).", reply_markup=get_restart_inline_keyboard())
            return

        has_video = os.path.exists(video_path) and os.path.getsize(video_path) > 0

        final_audio_path = None
        for ext in ['.mp3', '.m4a', '.opus', '.webm', '.wav', '.aac']:
            possible_path = f"{base_name}{ext}"
            if os.path.exists(possible_path) and os.path.getsize(possible_path) > 0:
                final_audio_path = possible_path
                break
        
        if final_audio_path and not final_audio_path.endswith('.mp3'):
            try:
                os.rename(final_audio_path, audio_path)
                final_audio_path = audio_path
            except:
                pass

        has_audio = final_audio_path and os.path.exists(final_audio_path) and os.path.getsize(final_audio_path) > 0

        if not has_video and not has_audio:
            await callback.message.answer("❌ Файлы не найдены после загрузки. Попробуй еще раз.", reply_markup=get_restart_inline_keyboard())
            return

        if is_vip:
            video_caption = "🌟 **VIP Видео (4K, до 2 ГБ)**"
            audio_caption = "🎵 **VIP Аудиодорожка**"
        else:
            video_caption = f"🎥 **Видео (720p, до 500 МБ)**\n📥 Скачано через @{BOT_USERNAME}"
            audio_caption = f"🎵 **Аудиодорожка**\n📥 @{BOT_USERNAME}"

        if has_video and action in ["video", "both"]:
            video_file = FSInputFile(video_path)
            await callback.message.answer_video(video=video_file, caption=video_caption, parse_mode=ParseMode.MARKDOWN, reply_markup=get_restart_inline_keyboard())

        if has_audio and action in ["audio", "both"]:
            audio_file = FSInputFile(final_audio_path)
            await callback.message.answer_audio(audio=audio_file, caption=audio_caption, parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        logging.error(f"Критическая ошибка при отправке медиа: {e}")
        await callback.message.answer("❌ Произошла ошибка при обработке медиафайла.", reply_markup=get_restart_inline_keyboard())
    finally:
        for ext in ['.mp4', '.mp3', '.m4a', '.opus', '.webm', '.wav', '.aac', '.part']:
            temp_file = f"{base_name}{ext}"
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except:
                    pass

@dp.callback_query(F.data == "cancel_action")
async def cancel_action(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer("Отменено")
    await callback.message.edit_text("❌ Действие отменено.")

# Функция скачивания с четкими лимитами: 500 МБ (без VIP) и 2 ГБ (для VIP)
def download_selected_media_safe(url: str, base_filename: str, is_vip: int, action: str) -> bool:
    downloaded = False
    
    # Жесткое разграничение размера: 500 МБ для бесплатников, 2 ГБ (2000 МБ) для VIP
    max_bytes = (2000 * 1024 * 1024) if is_vip else (500 * 1024 * 1024)
    
    common_opts = {
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'geo_bypass': True,
        'nocheckcertificate': True,
        'socket_timeout': 60,
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'ios', 'web'],
                'skip': ['webpage', 'hls', 'dash']
            },
            'tiktok': {
                'app_version': '30.2.0',
            }
        },
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Sec-Fetch-Mode': 'navigate',
        }
    }

    if action in ["video", "both"]:
        video_format = 'best[ext=mp4]/best' if is_vip else 'best[height<=720][ext=mp4]/best[ext=mp4]/best'
        ydl_opts_video = {
            **common_opts,
            'format': video_format,
            'outtmpl': f"{base_filename}.mp4",
            'max_filesize': max_bytes,
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts_video) as ydl:
                ydl.download([url])
                if os.path.exists(f"{base_filename}.mp4") and os.path.getsize(f"{base_filename}.mp4") > 0:
                    downloaded = True
        except Exception as e:
            logging.error(f"Ошибка yt-dlp при скачивании видео: {e}")

    if action in ["audio", "both"]:
        ydl_opts_audio = {
            **common_opts,
            'format': 'bestaudio/best',
            'outtmpl': f"{base_filename}.%(ext)s",
            'max_filesize': max_bytes,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts_audio) as ydl:
                ydl.download([url])
                downloaded = True
        except Exception as e:
            logging.error(f"Ошибка yt-dlp при скачивании аудио: {e}")

    return downloaded

@dp.message(F.text)
async def handle_group_autoscanner_and_text(message: types.Message, state: FSMContext):
    text = message.text.strip()
    
    if message.from_user.id == ADMIN_ID and ADMIN_ID in waiting_for_broadcast:
        waiting_for_broadcast.remove(ADMIN_ID)
        users = db_get_all_users()
        success = 0
        for uid in users:
            try:
                await message.copy_to(chat_id=uid)
                success += 1
                await asyncio.sleep(0.05)
            except Exception as e:
                logging.error(f"Не удалось отправить рассылку пользователю {uid}: {e}")
        await message.answer(f"✅ Рассылка завершена. Успешно доставлено: {success}/{len(users)}")
        return

    if message.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
        if re.match(r'https?://[^\s]+', text):
            status_msg = await message.answer("🔄 **Автосканер:** обнаружил ссылку, скачиваю видео...", parse_mode=ParseMode.MARKDOWN)
            base_name = f"group_media_{message.chat.id}_{message.message_id}"
            video_path = f"{base_name}.mp4"
            
            try:
                loop = asyncio.get_running_loop()
                success = await loop.run_in_executor(None, download_selected_media_safe, text, base_name, 0, "video")
                
                if success and os.path.exists(video_path) and os.path.getsize(video_path) > 0:
                    video_file = FSInputFile(video_path)
                    await message.answer_video(video=video_file, caption=f"📥 Скачано через @{BOT_USERNAME}", parse_mode=ParseMode.MARKDOWN)
                    try:
                        await status_msg.delete()
                    except:
                        pass
                else:
                    await status_msg.edit_text("❌ Не удалось скачать медиа по этой ссылке в группе.")
            except Exception as e:
                logging.error(f"Ошибка автосканера в группе: {e}")
                try:
                    await status_msg.edit_text("❌ Произошла ошибка при автосканировании.")
                except:
                    pass
            finally:
                if os.path.exists(video_path):
                    try:
                        os.remove(video_path)
                    except:
                        pass
        return

    if get_maintenance_mode() == 'on' and message.from_user.id != ADMIN_ID:
        await message.answer("🛠 В боте проводятся технические работы. Скоро вернемся!")
        return
        
    await message.answer("ℹ️ Пожалуйста, используй кнопку **«📥 Скачать медиа»** в меню, чтобы начать процесс скачивания.", parse_mode=ParseMode.MARKDOWN)

@dp.message(F.text.startswith("💎 Купить VIP") | (F.text == "🌟 VIP Статус (Активен)"))
async def buy_vip_command(message: types.Message, state: FSMContext):
    await state.clear()
    if message.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
        return

    if get_maintenance_mode() == 'on' and message.from_user.id != ADMIN_ID:
        await message.answer("🛠 В боте проводятся технические работы.")
        return

    is_vip = check_vip_status_expiration(message.from_user.id, ADMIN_ID)
    
    info_text = (
        f"{get_vip_comparison_text()}\n\n"
        f"💳 **Стоимость VIP подписки на 30 дней:** 100 Telegram Stars ✨"
    )
    
    prices = [LabeledPrice(label="VIP Подписка (1 месяц)", amount=100)]
    await message.answer_invoice(
        title="🌟 VIP-статус для PulseFetch",
        description="Размер файлов до 2 ГБ, 4K качество и отсутствие рекламы!",
        prices=prices,
        payload="vip_subscription_30_days",
        currency="XTR",
        provider_token=""
    )
    await message.answer(info_text, parse_mode=ParseMode.MARKDOWN)

@dp.message(F.text == "🎁 Бесплатный VIP за друзей")
async def referral_menu(message: types.Message, state: FSMContext):
    await state.clear()
    if message.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
        return

    if get_maintenance_mode() == 'on' and message.from_user.id != ADMIN_ID:
        await message.answer("🛠 В боте проводятся технические работы.")
        return

    user_id = message.from_user.id
    refs, claimed = db_get_user_info(user_id)
    ref_link = f"https://t.me/{BOT_USERNAME}?start=ref_{user_id}"
    
    current_cycle_refs = refs % 3
    needed_for_next = 3 - current_cycle_refs
    
    if claimed >= 3:
        status_text = "🔥 **Ты полностью исчерпал все 3 бонусных активации по 24 часа!**"
    else:
        status_text = (
            f"📊 **Твоя статистика приглашений:**\n"
            f"• Приглашено друзей: `{refs}`\n"
            f"• Получено бонусов (на 24 часа): `{claimed} из 3`\n\n"
            f"🎯 До следующих 24 часов VIP осталось пригласить: **{needed_for_next} друга(-ей)**"
        )

    text = (
        f"🎁 **Получи VIP на 24 часа бесплатно!**\n\n"
        f"Приглашай друзей по своей ссылке. За каждые **3 друга** тебе автоматически выдается **VIP на 24 часа** (до 3 раз)!\n\n"
        f"🔗 **Твоя реферальная ссылка:**\n`{ref_link}`\n\n"
        f"{status_text}"
    )
    await message.answer(text, reply_markup=get_restart_inline_keyboard(), parse_mode=ParseMode.MARKDOWN)

@dp.pre_checkout_query()
async def pre_checkout_query_handler(pre_checkout_query: types.PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@dp.message(F.successful_payment)
async def successful_payment_handler(message: types.Message):
    db_set_user_vip_months(message.from_user.id, 1)
    is_vip = check_vip_status_expiration(message.from_user.id, ADMIN_ID)
    await message.answer(
        "🎉 **Оплата прошла успешно!**\n\n"
        "Тебе присвоен статус 🌟 **VIP** на 30 дней! Теперь тебе доступны файлы до 2 ГБ и максимальное качество!",
        reply_markup=get_main_keyboard(message.from_user.id, is_vip),
        parse_mode=ParseMode.MARKDOWN
    )

@dp.callback_query(F.data == "restart_bot")
async def callback_restart(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer("🔄 Бот перезапущен!")
    is_vip = check_vip_status_expiration(callback.from_user.id, ADMIN_ID)
    restart_text = f"⚡️ **Главное меню PulseFetch**\n\n👇 Нажми кнопку **«📥 Скачать медиа»**:"
    await callback.message.answer(restart_text, reply_markup=get_main_keyboard(callback.from_user.id, is_vip), parse_mode=ParseMode.MARKDOWN)

async def main():
    await start_web_server()
    print("Бот PulseFetch запущен и готов к работе!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
