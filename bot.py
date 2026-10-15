import asyncio
import logging
import requests
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ==================== НАСТРОЙКИ ====================
TELEGRAM_TOKEN = "8410105070:AAHG_2lVHz26hQge2-_pvUipMEtxgz57xuc"
CHANNEL_USERNAME = "@kinorave_tg"
TMDB_TOKEN = "EyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiIwM2VmZTNjMDJlNDJjZWEwMmYyNTIyMjdiYzQxNWU4MSIsIm5iZiI6MTc5MTk5NzkxMy42ODQsInN1YiI6IjZhY2ZiN2Q5NDEzMDVmM2YwZGRlYzVhNiIsInNjb3BlcyI6WyJhcGlfcmVhZCJdLCJ2ZXJzaW9uIjoxfQ.YGqDWb6NLtSavJHHU0Ks3a2JA3GjMYa9UL3Lf_9Ddq8"
# ===================================================

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# Проверка подписки на канал
async def check_subscription(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        return member.status not in ["left", "kicked"]
    except Exception as e:
        logging.error(f"Ошибка проверки подписки: {e}")
        return True

# Поиск фильма или сериала в TMDb
def search_media(query: str):
    url = "https://api.themoviedb.org/3/search/multi"
    headers = {
        "Authorization": f"Bearer {TMDB_TOKEN}",
        "accept": "application/json"
    }
    params = {
        "query": query,
        "language": "ru-RU"
    }
    try:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200:
            results = response.json().get("results", [])
            media_results = [item for item in results if item.get("media_type") in ["movie", "tv"]]
            if media_results:
                return media_results[0]
    except Exception as e:
        logging.error(f"Ошибка API: {e}")
    return None

# Получение подробностей (длительность, сезоны)
def get_media_details(media_id: int, media_type: str):
    url = f"https://api.themoviedb.org/3/{media_type}/{media_id}"
    headers = {
        "Authorization": f"Bearer {TMDB_TOKEN}",
        "accept": "application/json"
    }
    params = {
        "language": "ru-RU"
    }
    try:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        logging.error(f"Ошибка получения деталей: {e}")
    return {}

# Клавиатура со ссылкой и кнопкой проверки
def get_sub_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Подписаться на KINORAVE", url="https://t.me/kinorave_tg")],
        [InlineKeyboardButton(text="✅ Я подписался!", callback_data="check_sub")]
    ])

@dp.message(CommandStart())
async def start_handler(message: types.Message):
    is_subbed = await check_subscription(message.from_user.id)
    if not is_subbed:
        await message.answer(
            f"👋 Привет, {message.from_user.first_name}!\n\n"
            f"⚠️ Чтобы искать фильмы и сериалы через бота, подпишись на наш канал **KINORAVE**!",
            reply_markup=get_sub_keyboard(),
            parse_mode="Markdown"
        )
        return

    await message.answer(
        "👋 **Добро пожаловать в бота KINORAVE!**\n\n"
        "Напиши мне название любого **фильма** или **сериала**, и я найду всю информацию о нём!",
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "check_sub")
async def check_sub_callback(callback: types.CallbackQuery):
    is_subbed = await check_subscription(callback.from_user.id)
    if is_subbed:
        await callback.message.delete()
        await callback.message.answer(
            "🎉 **Спасибо за подписку!** Теперь просто напиши название фильма или сериала.",
            parse_mode="Markdown"
        )
    else:
        await callback.answer("❌ Вы всё ещё не подписались на канал!", show_alert=True)

@dp.message()
async def search_handler(message: types.Message):
    is_subbed = await check_subscription(message.from_user.id)
    if not is_subbed:
        await message.answer(
            "⚠️ Для использования поиска нужно быть подписанным на наш канал!",
            reply_markup=get_sub_keyboard()
        )
        return

    query = message.text.strip()
    item = search_media(query)
    
    if not item:
        await message.answer("❌ Ничего не найдено. Попробуй уточнить название.")
        return

    media_type = item.get("media_type")
    media_id = item.get("id")
    details = get_media_details(media_id, media_type)

    if media_type == "movie":
        type_str = "🎬 <b>Фильм</b>"
        title = details.get("title", "Без названия")
        orig_title = details.get("original_title", "")
        release_date = details.get("release_date", "Неизвестно")
        year = release_date[:4] if release_date else "Неизвестно"
        runtime = details.get("runtime")
        duration_str = f"{runtime} мин." if runtime else "Неизвестно"
    else:
        type_str = "📺 <b>Сериал</b>"
        title = details.get("name", "Без названия")
        orig_title = details.get("original_name", "")
        release_date = details.get("first_air_date", "Неизвестно")
        year = release_date[:4] if release_date else "Неизвестно"
        seasons = details.get("number_of_seasons", "—")
        episodes = details.get("number_of_episodes", "—")
        duration_str = f"{seasons} сез. ({episodes} сер.)"

    rating = round(details.get("vote_average", 0), 1)
    overview = details.get("overview") or "Описание отсутствует."
    poster_path = details.get("poster_path")

    caption = (
        f"{type_str}: <b>{title}</b> ({year})\n"
        f"<i>{orig_title}</i>\n\n"
        f"⏱ <b>Длительность / Формат:</b> {duration_str}\n"
        f"⭐️ <b>Рейтинг:</b> {rating}/10\n"
        f"📅 <b>Дата выхода:</b> {release_date}\n\n"
        f"📝 <b>Описание:</b>\n{overview[:500]}..."
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🔍 Смотреть онлайн", 
            url=f"https://www.google.com/search?q=смотреть+{title}+{year}"
        )]
    ])

    if poster_path:
        poster_url = f"https://image.tmdb.org/t500/p/w500{poster_path}"
        await message.answer_photo(
            photo=poster_url, 
            caption=caption, 
            parse_mode="HTML",
            reply_markup=keyboard
        )
    else:
        await message.answer(
            text=caption, 
            parse_mode="HTML",
            reply_markup=keyboard
        )

async def main():    logging.basicConfig(level=logging.INFO)                 await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
          
