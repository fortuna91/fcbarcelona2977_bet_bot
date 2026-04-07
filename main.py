import asyncio
import os
from aiogram import Bot, Dispatcher
from database import init_db
from handlers import router
from scheduler import setup_scheduler, sync_matches
from dotenv import load_dotenv

load_dotenv()

async def main():
    await init_db()
    bot = Bot(token=os.getenv("BOT_TOKEN"))
    dp = Dispatcher()
    dp.include_router(router)
    
    setup_scheduler(bot)
    await sync_matches() # Initial sync
    
    print("Bot is starting...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
