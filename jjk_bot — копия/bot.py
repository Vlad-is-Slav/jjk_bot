"""
Главный файл бота Jujutsu Battle
"""
import asyncio
import logging
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.filters import Command
from sqlalchemy import select

from config import BOT_TOKEN, EXP_PER_MESSAGE, EXP_COOLDOWN, POINTS_PER_LEVEL_UP
from models import init_db, async_session, User
from handlers import (
    start_router,
    profile_router,
    inventory_router,
    battle_router,
    pve_router,
    pvp_router,
    tops_router,
    friends_router,
    daily_router,
    achievements_router,
    campaign_router,
    academy_router,
    promocode_router,
    admin_router,
    market_router
)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Хранилище кулдаунов для опыта
exp_cooldowns = {}

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Подключаем роутеры
dp.include_router(start_router)
dp.include_router(profile_router)
dp.include_router(inventory_router)
dp.include_router(battle_router)
dp.include_router(pve_router)
dp.include_router(pvp_router)
dp.include_router(tops_router)
dp.include_router(friends_router)
dp.include_router(daily_router)
dp.include_router(achievements_router)
dp.include_router(campaign_router)
dp.include_router(academy_router)
dp.include_router(promocode_router)
dp.include_router(admin_router)
dp.include_router(market_router)

async def main():
    """Главная функция"""
    # Инициализируем БД
    await init_db()
    logger.info("Database initialized")
    
    # Удаляем вебхук и запускаем polling
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Bot started")
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
