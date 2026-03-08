from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from models import async_session, User, Achievement, UserAchievement, Title, UserTitle
from utils.achievement_data import ACHIEVEMENTS, TITLES

router = Router()

@router.message(Command("achievements"))
async def cmd_achievements(message: Message):
    """Команда /achievements"""
    await message.answer(
        "🏆 <b>Достижения и титулы</b>\n\n"
        "Нажми кнопку, чтобы открыть раздел.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏆 Открыть достижения", callback_data="achievements")]
        ]),
        parse_mode="HTML"
    )

@router.callback_query(F.data == "achievements")
async def achievements_menu_callback(callback: CallbackQuery):
    """Меню достижений"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🏆 Мои Достижения", callback_data="my_achievements"),
            InlineKeyboardButton(text="👑 Титулы", callback_data="my_titles")
        ],
        [
            InlineKeyboardButton(text="🔙 Назад", callback_data="profile")
        ]
    ])
    
    await callback.message.edit_text(
        "🏆 <b>Достижения и Титулы</b>\n\n"
        "Здесь ты можешь посмотреть свои достижения и управлять титулами.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data == "my_achievements")
async def my_achievements_callback(callback: CallbackQuery):
    """Показать достижения пользователя"""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Сначала используй /start", show_alert=True)
            return
        
        # Получаем достижения пользователя
        result = await session.execute(
            select(UserAchievement)
            .options(selectinload(UserAchievement.achievement))
            .where(UserAchievement.user_id == user.id)
        )
        user_achievements = result.scalars().all()
        
        # Считаем статистику
        completed = [ua for ua in user_achievements if ua.completed]
        in_progress = [ua for ua in user_achievements if not ua.completed]
        
        # Инициализируем недостающие достижения
        for ach_data in ACHIEVEMENTS:
            existing = [ua for ua in user_achievements if ua.achievement and ua.achievement.name == ach_data["name"]]
            if not existing:
                # Создаем шаблон достижения если нет
                result = await session.execute(
                    select(Achievement).where(Achievement.name == ach_data["name"])
                )
                ach_template = result.scalar_one_or_none()
                
                if not ach_template:
                    ach_template = Achievement(
                        name=ach_data["name"],
                        description=ach_data["description"],
                        achievement_type=ach_data["achievement_type"],
                        requirement_value=ach_data["requirement_value"],
                        exp_reward=ach_data["exp_reward"],
                        points_reward=ach_data["points_reward"],
                        title_reward=ach_data.get("title_reward"),
                        icon=ach_data["icon"],
                        rarity=ach_data["rarity"]
                    )
                    session.add(ach_template)
                    await session.flush()
                
                user_ach = UserAchievement(
                    user_id=user.id,
                    achievement_id=ach_template.id,
                    progress=0,
                    completed=False
                )
                session.add(user_ach)
        
        await session.commit()
        
        # Перезагружаем
        result = await session.execute(
            select(UserAchievement)
            .options(selectinload(UserAchievement.achievement))
            .where(UserAchievement.user_id == user.id)
        )
        user_achievements = result.scalars().all()
        completed = [ua for ua in user_achievements if ua.completed]
        in_progress = [ua for ua in user_achievements if not ua.completed][:5]  # Показываем топ 5
        
        achievements_text = (
            f"🏆 <b>Мои Достижения</b>\n\n"
            f"✅ Выполнено: <b>{len(completed)}</b>/{len(ACHIEVEMENTS)}\n"
            f"⏳ В процессе: <b>{len([ua for ua in user_achievements if not ua.completed])}</b>\n\n"
        )
        
        if completed:
            achievements_text += "<b>Последние полученные:</b>\n"
            for ua in sorted(completed, key=lambda x: x.completed_at or datetime.min, reverse=True)[:3]:
                ach = ua.achievement
                achievements_text += f"{ach.icon} {ach.name}\n"
            achievements_text += "\n"
        
        if in_progress:
            achievements_text += "<b>В процессе:</b>\n"
            for ua in in_progress:
                ach = ua.achievement
                progress_pct = min(100, int((ua.progress / ach.requirement_value) * 100))
                bar = "█" * (progress_pct // 10) + "░" * (10 - progress_pct // 10)
                achievements_text += f"{ach.icon} {ach.name}\n[{bar}] {ua.progress}/{ach.requirement_value}\n\n"
        
        await callback.message.edit_text(
            achievements_text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="achievements")]
            ]),
            parse_mode="HTML"
        )
    await callback.answer()

@router.callback_query(F.data == "my_titles")
async def my_titles_callback(callback: CallbackQuery):
    """Показать титулы пользователя"""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Сначала используй /start", show_alert=True)
            return
        
        # Получаем титулы пользователя
        result = await session.execute(
            select(UserTitle)
            .options(selectinload(UserTitle.title))
            .where(UserTitle.user_id == user.id)
        )
        user_titles = result.scalars().all()
        
        # Инициализируем стартовый титул если нет
        if not user_titles:
            result = await session.execute(
                select(Title).where(Title.name == "Новичок")
            )
            title_template = result.scalar_one_or_none()
            
            if not title_template:
                title_template = Title(
                    name="Новичок",
                    description="Только начинаешь свой путь",
                    icon="🌱",
                    requirement="Стартовый титул"
                )
                session.add(title_template)
                await session.flush()
            
            user_title = UserTitle(
                user_id=user.id,
                title_id=title_template.id,
                is_equipped=True
            )
            session.add(user_title)
            user.equipped_title_id = title_template.id
            await session.commit()
            
            # Перезагружаем
            result = await session.execute(
                select(UserTitle)
                .options(selectinload(UserTitle.title))
                .where(UserTitle.user_id == user.id)
            )
            user_titles = result.scalars().all()
        
        # Получаем экипированный титул
        equipped = [ut for ut in user_titles if ut.is_equipped]
        equipped_title = equipped[0].title if equipped else None
        
        titles_text = (
            f"👑 <b>Мои Титулы</b>\n\n"
            f"📊 Всего: <b>{len(user_titles)}</b>\n"
        )
        
        if equipped_title:
            titles_text += f"✅ Экипирован: <b>{equipped_title.icon} {equipped_title.name}</b>\n\n"
            if equipped_title.attack_bonus > 0:
                titles_text += f"⚔️ Атака: +{equipped_title.attack_bonus}\n"
            if equipped_title.defense_bonus > 0:
                titles_text += f"🛡️ Защита: +{equipped_title.defense_bonus}\n"
            if equipped_title.speed_bonus > 0:
                titles_text += f"💨 Скорость: +{equipped_title.speed_bonus}\n"
            if equipped_title.hp_bonus > 0:
                titles_text += f"❤️ HP: +{equipped_title.hp_bonus}\n"
        
        titles_text += "\n<b>Доступные титулы:</b>\n"
        
        buttons = []
        for ut in user_titles:
            title = ut.title
            status = "✅" if ut.is_equipped else ""
            titles_text += f"{status} {title.icon} {title.name}\n"
            
            if not ut.is_equipped:
                buttons.append([
                    InlineKeyboardButton(
                        text=f"👑 Надеть: {title.name}",
                        callback_data=f"equip_title_{ut.id}"
                    )
                ])
        
        buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="achievements")])
        
        await callback.message.edit_text(
            titles_text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
            parse_mode="HTML"
        )
    await callback.answer()

@router.callback_query(F.data.startswith("equip_title_"))
async def equip_title_callback(callback: CallbackQuery):
    """Экипировать титул"""
    title_id = int(callback.data.split("_")[2])
    
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Сначала используй /start", show_alert=True)
            return
        
        # Снимаем текущий титул
        result = await session.execute(
            select(UserTitle).where(
                UserTitle.user_id == user.id,
                UserTitle.is_equipped == True
            )
        )
        current = result.scalar_one_or_none()
        if current:
            current.is_equipped = False
        
        # Экипируем новый
        result = await session.execute(
            select(UserTitle).where(
                UserTitle.id == title_id,
                UserTitle.user_id == user.id
            )
        )
        new_title = result.scalar_one_or_none()
        
        if new_title:
            new_title.is_equipped = True
            user.equipped_title_id = new_title.title_id
            await session.commit()
            
            await callback.answer(f"Титул '{new_title.title.name}' экипирован!")
        
        await my_titles_callback(callback)


# Функция для проверки и выдачи достижений
async def check_achievements(user_id: int, achievement_type: str, value: int = 1):
    """Проверить достижения пользователя"""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            return []
        
        # Получаем достижения этого типа
        result = await session.execute(
            select(UserAchievement)
            .options(selectinload(UserAchievement.achievement))
            .where(
                UserAchievement.user_id == user_id,
                UserAchievement.completed == False
            )
        )
        user_achievements = result.scalars().all()
        
        unlocked = []
        
        for ua in user_achievements:
            if ua.achievement.achievement_type == achievement_type:
                ua.progress += value
                
                if ua.progress >= ua.achievement.requirement_value:
                    # Достижение выполнено!
                    ua.completed = True
                    ua.completed_at = datetime.utcnow()
                    
                    # Выдаем награды
                    user.add_experience(ua.achievement.exp_reward)
                    user.points += ua.achievement.points_reward
                    
                    # Выдаем титул если есть
                    if ua.achievement.title_reward:
                        result = await session.execute(
                            select(Title).where(Title.name == ua.achievement.title_reward)
                        )
                        title = result.scalar_one_or_none()
                        
                        if not title:
                            from utils.achievement_data import get_title_by_name
                            title_data = get_title_by_name(ua.achievement.title_reward)
                            if title_data:
                                title = Title(
                                    name=title_data["name"],
                                    description=title_data["description"],
                                    attack_bonus=title_data.get("attack_bonus", 0),
                                    defense_bonus=title_data.get("defense_bonus", 0),
                                    speed_bonus=title_data.get("speed_bonus", 0),
                                    hp_bonus=title_data.get("hp_bonus", 0),
                                    icon=title_data.get("icon", "👑"),
                                    requirement=title_data.get("requirement", "")
                                )
                                session.add(title)
                                await session.flush()
                        
                        if title:
                            # Проверяем, есть ли уже
                            result = await session.execute(
                                select(UserTitle).where(
                                    UserTitle.user_id == user_id,
                                    UserTitle.title_id == title.id
                                )
                            )
                            existing = result.scalar_one_or_none()
                            
                            if not existing:
                                user_title = UserTitle(
                                    user_id=user_id,
                                    title_id=title.id,
                                    is_equipped=False
                                )
                                session.add(user_title)
                    
                    unlocked.append(ua.achievement)
        
        await session.commit()
        return unlocked


from datetime import datetime
