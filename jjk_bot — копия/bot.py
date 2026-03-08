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

@dp.message(F.text)
async def gain_exp_from_messages(message: Message):
    """Начисление опыта за обычные сообщения с кулдауном"""
    if not message.from_user or message.from_user.is_bot:
        return
    if message.text and message.text.startswith("/"):
        return

    tg_id = message.from_user.id
    now = datetime.utcnow()
    last_time = exp_cooldowns.get(tg_id)
    if last_time and (now - last_time).total_seconds() < EXP_COOLDOWN:
        return

    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == tg_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            return

        leveled_up, actual_exp = user.add_experience(EXP_PER_MESSAGE)
        await session.commit()
        exp_cooldowns[tg_id] = now

        if leveled_up:
            await message.answer(
                f"🎉 Новый уровень: <b>{user.level}</b>!\n"
                f"⭐ Получено опыта: +{actual_exp}",
                parse_mode="HTML"
            )

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
