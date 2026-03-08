from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from datetime import datetime, timedelta

from models import async_session, User, DailyReward, DailyQuest, UserDailyQuest, UserStats
from utils.daily_quest_data import get_random_quests

router = Router()

@router.message(Command("daily"))
async def cmd_daily(message: Message):
    """Команда /daily"""
    await message.answer(
        "📅 <b>Ежедневные активности</b>\n\n"
        "Открой награды и задания:",
        reply_markup=get_daily_menu_keyboard(),
        parse_mode="HTML"
    )

def get_daily_menu_keyboard():
    """Клавиатура меню ежедневных наград"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎁 Ежедневная Награда", callback_data="daily_reward"),
            InlineKeyboardButton(text="📋 Задания", callback_data="daily_quests")
        ],
        [
            InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")
        ]
    ])

@router.callback_query(F.data == "daily_menu")
async def daily_menu_callback(callback: CallbackQuery):
    """Меню ежедневных наград"""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Сначала используй /start", show_alert=True)
            return
        
        # Получаем или создаем запись о ежедневных наградах
        result = await session.execute(
            select(DailyReward).where(DailyReward.user_id == user.id)
        )
        daily = result.scalar_one_or_none()
        
        if not daily:
            daily = DailyReward(user_id=user.id)
            session.add(daily)
            await session.commit()
        
        can_claim = daily.can_claim()
        reward = daily.get_today_reward()
        
        status_text = "✅ Доступно!" if can_claim else "⏳ Уже забрано"
        
        menu_text = (
            f"📅 <b>Ежедневные Награды</b>\n\n"
            f"🔥 Текущий стрик: <b>{daily.current_streak}</b> дней\n"
            f"🏆 Максимальный стрик: <b>{daily.max_streak}</b> дней\n\n"
            f"🎁 <b>Сегодняшняя награда ({reward['name']}):</b>\n"
            f"⭐ Опыт: {reward['exp']}\n"
            f"💎 Очки: {reward['points']}\n"
            f"🪙 Монеты: {reward['coins']}\n"
        )
        
        if reward.get('card_chance'):
            menu_text += "🎴 Шанс на карту: Да!\n"
        
        menu_text += f"\nСтатус: {status_text}"
        
        if not can_claim and daily.last_claim_date:
            next_claim = daily.last_claim_date + timedelta(days=1)
            time_left = next_claim - datetime.utcnow()
            hours = int(time_left.total_seconds() // 3600)
            minutes = int((time_left.total_seconds() % 3600) // 60)
            menu_text += f"\n\n⏳ Следующая награда через: {hours}ч {minutes}м"
        
        await callback.message.edit_text(
            menu_text,
            reply_markup=get_daily_menu_keyboard(),
            parse_mode="HTML"
        )
    await callback.answer()

@router.callback_query(F.data == "daily_reward")
async def daily_reward_callback(callback: CallbackQuery):
    """Получение ежедневной награды"""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Сначала используй /start", show_alert=True)
            return
        
        result = await session.execute(
            select(DailyReward).where(DailyReward.user_id == user.id)
        )
        daily = result.scalar_one_or_none()
        
        if not daily:
            daily = DailyReward(user_id=user.id)
            session.add(daily)
            await session.commit()
        
        if not daily.can_claim():
            await callback.answer("Награда уже забрана! Приходи завтра.", show_alert=True)
            return
        
        # Забираем награду
        reward = daily.claim()
        
        if reward:
            # Начисляем награды
            user.add_experience(reward['exp'])
            user.points += reward['points']
            user.coins += reward['coins']
            
            card_dropped = False
            if reward.get('card_chance'):
                import random
                if random.random() < 0.3:  # 30% шанс на карту
                    card_dropped = True
                    # Здесь можно добавить логику выпадения карты
            
            await session.commit()
            
            result_text = (
                f"🎉 <b>Награда получена!</b>\n\n"
                f"⭐ Опыт: +{reward['exp']}\n"
                f"💎 Очки: +{reward['points']}\n"
                f"🪙 Монеты: +{reward['coins']}\n"
            )
            
            if card_dropped:
                result_text += "🎴 <b>Выпала карта!</b>\n"
            
            result_text += f"\n🔥 Стрик: {daily.current_streak} дней"
            
            if daily.current_streak == 7:
                result_text += "\n\n🎊 <b>Поздравляем! 7 дней подряд!</b>"
            
            await callback.answer(result_text, show_alert=True)
            await daily_menu_callback(callback)

@router.callback_query(F.data == "daily_quests")
async def daily_quests_callback(callback: CallbackQuery):
    """Показать ежедневные задания"""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Сначала используй /start", show_alert=True)
            return
        
        # Проверяем, есть ли задания на сегодня
        result = await session.execute(
            select(UserDailyQuest)
            .options(selectinload(UserDailyQuest.quest))
            .where(UserDailyQuest.user_id == user.id)
            .order_by(UserDailyQuest.assigned_date.desc())
        )
        existing_quests = result.scalars().all()
        
        # Проверяем, нужно ли создать новые задания
        today_quests = [q for q in existing_quests if q.is_today()]
        
        if not today_quests:
            # Создаем новые задания
            quests_data = get_random_quests(4)
            
            for quest_data in quests_data:
                # Ищем или создаем шаблон задания
                result = await session.execute(
                    select(DailyQuest).where(DailyQuest.name == quest_data["name"])
                )
                quest_template = result.scalar_one_or_none()
                
                if not quest_template:
                    quest_template = DailyQuest(
                        name=quest_data["name"],
                        description=quest_data["description"],
                        quest_type=quest_data["quest_type"],
                        requirement=quest_data["requirement"],
                        exp_reward=quest_data["exp_reward"],
                        points_reward=quest_data["points_reward"],
                        coins_reward=quest_data["coins_reward"],
                        difficulty=quest_data["difficulty"]
                    )
                    session.add(quest_template)
                    await session.flush()
                
                user_quest = UserDailyQuest(
                    user_id=user.id,
                    quest_id=quest_template.id,
                    progress=0,
                    completed=False,
                    claimed=False,
                    assigned_date=datetime.utcnow()
                )
                session.add(user_quest)
            
            await session.commit()
            
            # Перезагружаем задания
            result = await session.execute(
                select(UserDailyQuest)
                .options(selectinload(UserDailyQuest.quest))
                .where(UserDailyQuest.user_id == user.id)
                .order_by(UserDailyQuest.assigned_date.desc())
            )
            today_quests = [q for q in result.scalars().all() if q.is_today()][:4]
        
        # Формируем текст
        quests_text = "📋 <b>Ежедневные Задания</b>\n\n"
        
        buttons = []
        
        for i, uq in enumerate(today_quests, 1):
            quest = uq.quest
            status = "✅" if uq.completed else "⏳"
            reward_status = "💰" if uq.completed and not uq.claimed else ""
            
            difficulty_emoji = {
                "easy": "🟢",
                "medium": "🟡",
                "hard": "🔴"
            }.get(quest.difficulty, "⚪")
            
            quests_text += (
                f"{i}. {status} {difficulty_emoji} <b>{quest.name}</b> {reward_status}\n"
                f"   {quest.description}\n"
                f"   Прогресс: {uq.progress}/{quest.requirement}\n"
                f"   🎁 Награда: {quest.exp_reward} опыта, {quest.coins_reward} монет\n\n"
            )
            
            if uq.completed and not uq.claimed:
                buttons.append([
                    InlineKeyboardButton(
                        text=f"💰 Забрать награду: {quest.name[:15]}",
                        callback_data=f"claim_quest_{uq.id}"
                    )
                ])
        
        buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="daily_menu")])
        
        await callback.message.edit_text(
            quests_text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
            parse_mode="HTML"
        )
    await callback.answer()

@router.callback_query(F.data.startswith("claim_quest_"))
async def claim_quest_reward_callback(callback: CallbackQuery):
    """Забрать награду за задание"""
    quest_id = int(callback.data.split("_")[2])
    
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Сначала используй /start", show_alert=True)
            return
        
        result = await session.execute(
            select(UserDailyQuest)
            .options(selectinload(UserDailyQuest.quest))
            .where(UserDailyQuest.id == quest_id, UserDailyQuest.user_id == user.id)
        )
        user_quest = result.scalar_one_or_none()
        
        if not user_quest:
            await callback.answer("Задание не найдено!", show_alert=True)
            return
        
        if not user_quest.completed:
            await callback.answer("Задание еще не выполнено!", show_alert=True)
            return
        
        if user_quest.claimed:
            await callback.answer("Награда уже забрана!", show_alert=True)
            return
        
        # Выдаем награду
        quest = user_quest.quest
        user.add_experience(quest.exp_reward)
        user.points += quest.points_reward
        user.coins += quest.coins_reward
        user_quest.claimed = True
        user_quest.completed_at = datetime.utcnow()
        
        await session.commit()
        
        await callback.answer(
            f"🎉 Награда получена!\n\n"
            f"⭐ Опыт: +{quest.exp_reward}\n"
            f"💎 Очки: +{quest.points_reward}\n"
            f"🪙 Монеты: +{quest.coins_reward}",
            show_alert=True
        )
        
        await daily_quests_callback(callback)
