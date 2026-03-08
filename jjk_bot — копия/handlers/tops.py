from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select, func, desc
from sqlalchemy.orm import selectinload

from models import async_session, User, UserCard
from keyboards.main_menu import get_tops_menu, get_back_button

router = Router()

@router.message(Command("tops"))
async def cmd_tops(message: Message):
    """Команда /tops"""
    await message.answer(
        "🏆 <b>Топы игроков</b>\n\n"
        "Выбери категорию:",
        reply_markup=get_tops_menu(),
        parse_mode="HTML"
    )

@router.callback_query(F.data == "tops")
async def tops_callback(callback: CallbackQuery):
    """Меню топов"""
    await callback.message.edit_text(
        "🏆 <b>Топы игроков</b>\n\n"
        "Выбери категорию:",
        reply_markup=get_tops_menu(),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data == "top_level")
async def top_level_callback(callback: CallbackQuery):
    """Топ по уровню"""
    async with async_session() as session:
        result = await session.execute(
            select(User)
            .order_by(desc(User.level), desc(User.experience))
            .limit(10)
        )
        users = result.scalars().all()
        
        top_text = "🏆 <b>Топ игроков по уровню:</b>\n\n"
        
        for i, user in enumerate(users, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            name = user.first_name or user.username or f"Игрок #{user.id}"
            top_text += f"{medal} {name} - Уровень {user.level}\n"
        
        await callback.message.edit_text(
            top_text,
            reply_markup=get_back_button("tops"),
            parse_mode="HTML"
        )
    await callback.answer()

@router.callback_query(F.data == "top_pvp")
async def top_pvp_callback(callback: CallbackQuery):
    """Топ по PvP"""
    async with async_session() as session:
        # Сортируем по количеству побед
        result = await session.execute(
            select(User)
            .where(User.pvp_wins > 0)
            .order_by(desc(User.pvp_wins), desc(User.pvp_wins / (User.pvp_wins + User.pvp_losses)))
            .limit(10)
        )
        users = result.scalars().all()
        
        top_text = "⚔️ <b>Топ PvP игроков:</b>\n\n"
        
        if not users:
            top_text += "Пока никто не участвовал в PvP боях."
        else:
            for i, user in enumerate(users, 1):
                medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
                name = user.first_name or user.username or f"Игрок #{user.id}"
                winrate = user.get_win_rate()
                top_text += f"{medal} {name} - {user.pvp_wins} побед ({winrate}%)\n"
        
        await callback.message.edit_text(
            top_text,
            reply_markup=get_back_button("tops"),
            parse_mode="HTML"
        )
    await callback.answer()

@router.callback_query(F.data == "top_exp")
async def top_exp_callback(callback: CallbackQuery):
    """Топ по опыту"""
    async with async_session() as session:
        # Рассчитываем общий опыт (уровень * 1000 + текущий опыт)
        result = await session.execute(
            select(User)
            .order_by(desc(User.level), desc(User.experience))
            .limit(10)
        )
        users = result.scalars().all()
        
        top_text = "⭐ <b>Топ игроков по опыту:</b>\n\n"
        
        for i, user in enumerate(users, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            name = user.first_name or user.username or f"Игрок #{user.id}"
            total_exp = (user.level - 1) * 1000 + user.experience  # Приблизительно
            top_text += f"{medal} {name} - {total_exp} опыта\n"
        
        await callback.message.edit_text(
            top_text,
            reply_markup=get_back_button("tops"),
            parse_mode="HTML"
        )
    await callback.answer()

@router.callback_query(F.data == "top_power")
async def top_power_callback(callback: CallbackQuery):
    """Топ по силе колоды"""
    async with async_session() as session:
        result = await session.execute(
            select(User)
            .options(selectinload(User.cards).selectinload(UserCard.card_template))
            .limit(50)  # Берем больше для фильтрации
        )
        users = result.scalars().all()
        
        # Считаем силу колоды для каждого
        user_powers = []
        for user in users:
            total_power = 0
            for card in user.cards:
                if card.is_equipped:
                    total_power += card.get_total_power()
            user_powers.append((user, total_power))
        
        # Сортируем по силе
        user_powers.sort(key=lambda x: x[1], reverse=True)
        user_powers = user_powers[:10]
        
        top_text = "💪 <b>Топ игроков по силе колоды:</b>\n\n"
        
        for i, (user, power) in enumerate(user_powers, 1):
            if power == 0:
                continue
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            name = user.first_name or user.username or f"Игрок #{user.id}"
            top_text += f"{medal} {name} - Сила {power}\n"
        
        await callback.message.edit_text(
            top_text,
            reply_markup=get_back_button("tops"),
            parse_mode="HTML"
        )
    await callback.answer()
