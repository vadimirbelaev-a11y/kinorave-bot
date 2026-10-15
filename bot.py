import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart

# Вставляем твои ключи
BOT_TOKEN = "8410105070:AAE-J_2eT1RzJ9C6vGzJ0m3e8vR4xQ_9yL0"
TMDB_API_KEY = "e2d7e4ba3b610d32bb5826f04d026bd6"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer("Привет! Я бот Кинораев. Напиши мне название фильма или сериала, и я найду его для тебя!")

@dp.message()
async def search_movie(message: types.Message):
    query = message.text
    import aiohttp
    url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_API_KEY}&language=ru-RU&query={query}"
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status != 200:
                await message.answer("Ошибка при поиске. Попробуй позже.")
                return
            data = await response.json()
            
    results = data.get("results", [])
    if not results:
        await message.answer("Ничего не найдено 😔")
        return

    item = results[0]
    title = item.get("title") or item.get("name") or "Без названия"
    overview = item.get("overview") or "Описание отсутствует."
    release_date = item.get("release_date") or item.get("first_air_date") or ""
    year = release_date.split("-")[0] if release_date else ""
    poster_path = item.get("poster_path")

    caption = f"<b>{title}</b> ({year})\n\n{overview}"
    
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text="🔍 Смотреть онлайн",
                    url=f"https://www.google.com/search?q=смотреть+{title}+{year}"
                )
            ]
        ]
    )

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

async def main():
    logging.basicConfig(level=logging.INFO)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
