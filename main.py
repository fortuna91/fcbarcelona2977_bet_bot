import asyncio
import os
import logging
from aiogram import Bot, Dispatcher
from database import init_db
from handlers import router
from scheduler import setup_scheduler, sync_matches
from dotenv import load_dotenv

load_dotenv()

# Configure logging to both file and console
log_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# File Handler
file_handler = logging.FileHandler("bot.log")
file_handler.setFormatter(log_formatter)
logger.addHandler(file_handler)

# Console Handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
logger.addHandler(console_handler)


async def main():
    logger.info("Initializing database...")
    await init_db()
    
    logger.info("Setting up Bot...")
    bot = Bot(token=os.getenv("BOT_TOKEN"))
    dp = Dispatcher()
    dp.include_router(router)
    
    logger.info("Setting up Scheduler...")
    setup_scheduler(bot)
    
    logger.info("Initial match synchronization...")
    await sync_matches() 
    
    logger.info("Bot is starting...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
