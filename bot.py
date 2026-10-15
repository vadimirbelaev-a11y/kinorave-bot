import asyncio
import logging
import os
import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiohttp import web

# Вставляем твои ключи
BOT_TOKEN = "8410105070:AAHG_21VHz26hQge2-_pvUipMEtxgz57xuc"
TMDB_API_KEY = "e2d7e4ba3b610d32bb5826f04d026bd6"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer("Привет! Я бот Кинораев. Напиши мне название фильма или сериала, и я найду его для тебя!")

@dp.message()
async def search_movie(message: types.Message):
    query = message.text
    url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_API_KEY}&language=ru-RU&query={query}"
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            data = await response.json()
            
            if not data.get('results'):
                await message.answer("Ничего не найдено, попробуй другое название!")
                return
            
            item = data['results'][0]
            title = item.get('title') or item.get('name') or "Без названия"
            overview = item.get('overview') or "Описание отсутствует."
            poster_path = item.get('poster_path')
            
            text = f"🍿 **{title}**\n\n{overview[:300]}..."
            
            keyboard = types.InlineKeyboardMarkup(
                inline_keyboard=[[
                    types.InlineKeyboardButton(text="🎬 Смотреть", url=f"https://www.google.com/search?q={title}+смотреть+онлайн")
                ]]
            )
            
            if poster_path:
                poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}"
                await message.answer_photo(photo=poster_url, caption=text, reply_markup=keyboard, parse_mode="Markdown")
            else:
                await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

# Заглушка веб-сервера для Render (чтобы бесплатный Web Service не падал)
async def handle_ping(request):
    return web.Response(text="Bot is running!")

async def main():
    logging.basicConfig(level=logging.INFO)
    
    # Сбрасываем старый вебхук Livegram
    await bot.delete_webhook(drop_pending_updates=True)
    
    # Запускаем фоновый веб-сервер на порту, который запрашивает Render
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    asyncio.create_task(site.start())
    
    # Запускаем самого бота
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
