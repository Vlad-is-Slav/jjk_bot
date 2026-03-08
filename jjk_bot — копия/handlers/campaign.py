from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message
from sqlalchemy import select
from sqlalchemy.orm import selectinload
import random

from models import async_session, User, CampaignSeason, CampaignLevel, UserCampaignProgress, Card, UserCard
from utils.campaign_data import CAMPAIGN_SEASONS, CAMPAIGN_LEVELS, get_season_levels

router = Router()

@router.message(Command("campaign"))
async def cmd_campaign(message: Message):
    """Команда /campaign"""
    await message.answer(
        "📖 <b>Сюжетная кампания</b>\n\n"
        "Нажми кнопку ниже, чтобы открыть кампанию.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="▶️ Открыть кампанию", callback_data="campaign")]
        ]),
        parse_mode="HTML"
    )

@router.callback_query(F.data == "campaign")
async def campaign_menu_callback(callback: CallbackQuery):
    """Меню сюжетной кампании"""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Сначала используй /start", show_alert=True)
            return
        
        # Инициализируем сезоны если нужно
        for season_data in CAMPAIGN_SEASONS:
            result = await session.execute(
                select(CampaignSeason).where(CampaignSeason.season_number == season_data["season_number"])
            )
            season = result.scalar_one_or_none()
            
            if not season:
                season = CampaignSeason(
                    name=season_data["name"],
                    description=season_data["description"],
                    season_number=season_data["season_number"],
                    required_level=season_data["required_level"],
                    exp_reward=season_data["exp_reward"],
                    points_reward=season_data["points_reward"],
                    card_reward=season_data.get("card_reward")
                )
                session.add(season)
                await session.flush()
                
                # Добавляем уровни сезона
                levels = get_season_levels(season_data["season_number"])
                for level_data in levels:
                    level = CampaignLevel(
                        season_id=season.id,
                        level_number=levels.index(level_data) + 1,
                        name=level_data["name"],
                        description=level_data["description"],
                        level_type=level_data["level_type"],
                        enemy_name=level_data.get("enemy_name"),
                        enemy_attack=level_data.get("enemy_attack", 10),
                        enemy_defense=level_data.get("enemy_defense", 10),
                        enemy_speed=level_data.get("enemy_speed", 10),
                        enemy_hp=level_data.get("enemy_hp", 100),
                        exp_reward=level_data["exp_reward"],
                        points_reward=level_data["points_reward"],
                        coins_reward=level_data["coins_reward"],
                        card_drop_chance=level_data.get("card_drop_chance", 0),
                        card_drop_name=level_data.get("card_drop_name")
                    )
                    session.add(level)
        
        await session.commit()
        
        # Получаем все сезоны
        result = await session.execute(
            select(CampaignSeason)
            .options(selectinload(CampaignSeason.levels))
            .order_by(CampaignSeason.season_number)
        )
        seasons = result.scalars().all()
        
        # Получаем прогресс пользователя
        result = await session.execute(
            select(UserCampaignProgress)
            .where(UserCampaignProgress.user_id == user.id)
        )
        progress = result.scalars().all()
        completed_levels = [p.level_id for p in progress if p.completed]
        
        campaign_text = (
            f"📖 <b>Сюжетная Кампания</b>\n\n"
            f"👤 Твой уровень: <b>{user.level}</b>\n\n"
            f"<b>Доступные сезоны:</b>\n\n"
        )
        
        buttons = []
        
        for season in seasons:
            # Считаем прогресс
            season_levels = [l for l in season.levels]
            completed_in_season = len([l for l in season_levels if l.id in completed_levels])
            total_in_season = len(season_levels)
            
            # Проверяем доступность
            if user.level >= season.required_level:
                status = "✅" if completed_in_season == total_in_season else "🟢"
                campaign_text += f"{status} <b>{season.name}</b>\n"
                campaign_text += f"   Прогресс: {completed_in_season}/{total_in_season}\n"
                
                buttons.append([
                    InlineKeyboardButton(
                        text=f"▶️ {season.name[:20]}",
                        callback_data=f"season_{season.id}"
                    )
                ])
            else:
                campaign_text += f"🔒 <b>{season.name}</b> (Требуется уровень {season.required_level})\n"
        
        buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")])
        
        await callback.message.edit_text(
            campaign_text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
            parse_mode="HTML"
        )
    await callback.answer()

@router.callback_query(F.data.startswith("season_"))
async def season_detail_callback(callback: CallbackQuery):
    """Детали сезона"""
    season_id = int(callback.data.split("_")[1])
    
    async with async_session() as session:
        result = await session.execute(
            select(CampaignSeason)
            .options(selectinload(CampaignSeason.levels))
            .where(CampaignSeason.id == season_id)
        )
        season = result.scalar_one_or_none()
        
        if not season:
            await callback.answer("Сезон не найден!", show_alert=True)
            return
        
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        # Получаем прогресс
        result = await session.execute(
            select(UserCampaignProgress)
            .where(UserCampaignProgress.user_id == user.id)
        )
        progress = {p.level_id: p for p in result.scalars().all()}
        
        season_text = (
            f"📖 <b>{season.name}</b>\n\n"
            f"<i>{season.description}</i>\n\n"
            f"🎁 Награда за прохождение:\n"
            f"⭐ {season.exp_reward} опыта\n"
            f"💎 {season.points_reward} очков\n"
        )
        
        if season.card_reward:
            season_text += f"🎴 Карта: {season.card_reward}\n"
        
        season_text += f"\n<b>Уровни:</b>\n"
        
        buttons = []
        
        for level in sorted(season.levels, key=lambda x: x.level_number):
            level_progress = progress.get(level.id)
            
            if level_progress and level_progress.completed:
                status = "✅"
            elif level.level_number == 1 or (level.level_number > 1 and 
                   all(progress.get(l.id) and progress[l.id].completed 
                       for l in season.levels if l.level_number < level.level_number)):
                status = "🟢"
                buttons.append([
                    InlineKeyboardButton(
                        text=f"▶️ {level.name[:25]}",
                        callback_data=f"campaign_level_{level.id}"
                    )
                ])
            else:
                status = "🔒"
            
            season_text += f"{status} {level.level_number}. {level.name}\n"
        
        buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="campaign")])
        
        await callback.message.edit_text(
            season_text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
            parse_mode="HTML"
        )
    await callback.answer()

@router.callback_query(F.data.startswith("campaign_level_"))
async def campaign_level_callback(callback: CallbackQuery):
    """Начать уровень кампании"""
    level_id = int(callback.data.split("_")[2])
    
    async with async_session() as session:
        result = await session.execute(
            select(CampaignLevel)
            .options(selectinload(CampaignLevel.season).selectinload(CampaignSeason.levels))
            .where(CampaignLevel.id == level_id)
        )
        level = result.scalar_one_or_none()
        
        if not level:
            await callback.answer("Уровень не найден!", show_alert=True)
            return
        
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        # Получаем карты пользователя
        result = await session.execute(
            select(UserCard)
            .options(selectinload(UserCard.card_template))
            .where(UserCard.user_id == user.id, UserCard.is_equipped == True)
        )
        equipped_cards = result.scalars().all()
        
        if not equipped_cards:
            await callback.answer("У тебя нет экипированных карт!", show_alert=True)
            return
        
        # Простая боевая система для кампании
        main_card = [c for c in equipped_cards if c.slot_number == 1]
        if not main_card:
            main_card = equipped_cards[0]
        else:
            main_card = main_card[0]
        
        # Бой
        player_hp = main_card.max_hp
        enemy_hp = level.enemy_hp
        
        battle_log = []
        
        # Определяем первого
        player_speed = main_card.speed
        enemy_speed = level.enemy_speed
        
        while player_hp > 0 and enemy_hp > 0:
            if player_speed >= enemy_speed:
                # Игрок атакует
                damage = max(1, main_card.attack - level.enemy_defense // 2)
                enemy_hp -= damage
                battle_log.append(f"⚔️ Ты нанес {damage} урона!")
                
                if enemy_hp <= 0:
                    break
                
                # Враг атакует
                damage = max(1, level.enemy_attack - main_card.defense // 2)
                player_hp -= damage
                battle_log.append(f"💥 {level.enemy_name} нанес {damage} урона!")
            else:
                # Враг первый
                damage = max(1, level.enemy_attack - main_card.defense // 2)
                player_hp -= damage
                battle_log.append(f"💥 {level.enemy_name} нанес {damage} урона!")
                
                if player_hp <= 0:
                    break
                
                # Игрок атакует
                damage = max(1, main_card.attack - level.enemy_defense // 2)
                enemy_hp -= damage
                battle_log.append(f"⚔️ Ты нанес {damage} урона!")
        
        won = player_hp > 0
        
        # Обновляем прогресс
        result = await session.execute(
            select(UserCampaignProgress)
            .where(
                UserCampaignProgress.user_id == user.id,
                UserCampaignProgress.level_id == level.id
            )
        )
        progress = result.scalar_one_or_none()
        
        if not progress:
            progress = UserCampaignProgress(
                user_id=user.id,
                level_id=level.id
            )
            session.add(progress)
        
        progress.attempts += 1
        
        card_dropped = False

        if won and not progress.completed:
            progress.completed = True
            progress.completed_at = datetime.utcnow()
            
            # Награды
            user.add_experience(level.exp_reward)
            user.points += level.points_reward
            user.coins += level.coins_reward
            
            # Шанс на карту
            if level.card_drop_name and random.random() * 100 < level.card_drop_chance:
                card_dropped = True
                # Создаем карту
                result = await session.execute(
                    select(Card).where(Card.name == level.card_drop_name)
                )
                card_template = result.scalar_one_or_none()
                
                if card_template:
                    user_card = UserCard(
                        user_id=user.id,
                        card_id=card_template.id,
                        level=1
                    )
                    user_card.recalculate_stats()
                    session.add(user_card)
        
        await session.commit()
        
        # Результат
        if won:
            result_text = (
                f"🏆 <b>Победа!</b>\n\n"
                f"Ты победил <b>{level.enemy_name}</b>!\n\n"
                f"⭐ Опыт: +{level.exp_reward}\n"
                f"💎 Очки: +{level.points_reward}\n"
                f"🪙 Монеты: +{level.coins_reward}\n"
            )
            
            if card_dropped:
                result_text += f"🎴 <b>Получена карта: {level.card_drop_name}!</b>\n"
            
            # Проверяем, все ли уровни сезона пройдены
            result = await session.execute(
                select(UserCampaignProgress)
                .where(
                    UserCampaignProgress.user_id == user.id,
                    UserCampaignProgress.completed == True
                )
            )
            completed_level_ids = [p.level_id for p in result.scalars().all()]
            
            season_levels = [l.id for l in level.season.levels]
            if all(lid in completed_level_ids for lid in season_levels):
                # Сезон пройден!
                result_text += f"\n🎉 <b>Сезон '{level.season.name}' пройден!</b>\n"
                result_text += f"🎁 Бонус: {level.season.exp_reward} опыта\n"
                
                user.add_experience(level.season.exp_reward)
                user.points += level.season.points_reward
                
                if level.season.card_reward:
                    result_text += f"🎴 Карта: {level.season.card_reward}\n"
        else:
            result_text = (
                f"💀 <b>Поражение...</b>\n\n"
                f"{level.enemy_name} оказался сильнее.\n"
                f"Попробуй прокачать карты и вернись!"
            )
        
        result_text += f"\n📊 Попыток: {progress.attempts}"
        
        await callback.message.edit_text(
            result_text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="🔄 Повторить", callback_data=f"campaign_level_{level.id}"),
                    InlineKeyboardButton(text="📖 К сезону", callback_data=f"season_{level.season_id}")
                ],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
            ]),
            parse_mode="HTML"
        )
    await callback.answer()


from datetime import datetime
