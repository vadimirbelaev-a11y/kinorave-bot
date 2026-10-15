import os
import logging
import aiohttp
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = "8410105070:AAHUuktDtUm_ICmRiRx0HghwsNkfYcNYD0Y"
TMDB_API_KEY = "e2d7e4ba3b610d32bb5826f04d026bd6"

RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "")
WEBHOOK_PATH = f"/bot/{BOT_TOKEN}"
WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}"

PORT = int(os.environ.get("PORT", 10000))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    try:
        await message.answer("Привет! Я бот Кинораев. Напиши мне название фильма или сериала, и я найду его для тебя!")
    except Exception as e:
        logging.error(f"Ошибка в команде старт: {e}")

@dp.message()
async def search_movie(message: types.Message):
    query = message.text
    if not query:
        return
        
    url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_API_KEY}&language=ru-RU&query={query}"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                if response.status != 200:
                    await message.answer("Ошибка связи с сервером фильмов. Попробуй позже!")
                    return
                
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
                    try:
                        await message.answer_photo(photo=poster_url, caption=text, reply_markup=keyboard, parse_mode="Markdown")
                    except Exception:
                        await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")
                else:
                    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")
                    
    except Exception as e:
        logging.error(f"Ошибка при поиске: {e}")
        await message.answer("Произошла ошибка при поиске фильма. Попробуй позже!")

async def on_startup(bot: Bot):
    try:
        await bot.set_webhook(WEBHOOK_URL, drop_pending_updates=True)
        logging.info(f"Вебхук успешно установлен: {WEBHOOK_URL}")
    except Exception as e:
        logging.error(f"Не удалось установить вебхук: {e}")

def main():
    app = web.Application()
    
    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
    )
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    
    dp.startup.register(on_startup)
    setup_application(app, dp, bot=bot)
    
    web.run_app(app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    main()
