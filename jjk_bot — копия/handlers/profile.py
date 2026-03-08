from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from models import async_session, User, UserCard
from keyboards import get_profile_menu, get_deck_keyboard, get_difficulty_menu

router = Router()

@router.message(Command("profile"))
async def cmd_profile(message: Message):
    """Команда /profile"""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one_or_none()

        if not user:
            await message.answer("Сначала используй /start")
            return

        await message.answer(
            f"👤 <b>Профиль: {user.first_name or 'Маг'}</b>\n\n"
            f"⭐ Уровень: {user.level}\n"
            f"📈 Опыт: {user.experience}/{user.experience_to_next}\n"
            f"💎 Очки: {user.points}\n"
            f"🪙 Монеты: {user.coins}",
            reply_markup=get_profile_menu(),
            parse_mode="HTML"
        )

@router.callback_query(F.data == "profile")
async def profile_callback(callback: CallbackQuery):
    """Профиль игрока"""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Сначала используй /start", show_alert=True)
            return
        
        # Получаем экипированные карты
        main_card = None
        support_card = None
        
        if user.slot_1_card_id:
            result = await session.execute(
                select(UserCard)
                .options(selectinload(UserCard.card_template))
                .where(UserCard.id == user.slot_1_card_id)
            )
            main_card = result.scalar_one_or_none()
        
        if user.slot_2_card_id:
            result = await session.execute(
                select(UserCard)
                .options(selectinload(UserCard.card_template))
                .where(UserCard.id == user.slot_2_card_id)
            )
            support_card = result.scalar_one_or_none()
        
        # Рассчитываем общую силу
        total_power = 0
        if main_card:
            total_power += main_card.get_total_power()
        if support_card:
            total_power += support_card.get_total_power()
        
        profile_text = (
            f"👤 <b>Профиль: {user.first_name or 'Маг'}</b>\n"
            f"@{user.username or 'Нет username'}\n\n"
            f"📊 <b>Статистика:</b>\n"
            f"⭐ Уровень: {user.level}\n"
            f"📈 Опыт: {user.experience}/{user.experience_to_next}\n"
            f"💎 Очки: {user.points}\n"
            f"💪 Общая сила: {total_power}\n\n"
            f"⚔️ <b>Боевая статистика:</b>\n"
            f"🏆 PvP побед: {user.pvp_wins}\n"
            f"💀 PvP поражений: {user.pvp_losses}\n"
            f"📊 Winrate: {user.get_win_rate()}%\n"
            f"👹 PvE побед: {user.pve_wins}\n"
            f"📊 Всего боев: {user.total_battles}\n\n"
            f"🎴 <b>Колода:</b>\n"
        )
        
        if main_card and main_card.card_template:
            profile_text += f"👑 {main_card.card_template.name} (Lv.{main_card.level})\n"
        else:
            profile_text += "👑 Не выбрано\n"
        
        if support_card and support_card.card_template:
            profile_text += f"🛡️ {support_card.card_template.name} (Lv.{support_card.level})\n"
        else:
            profile_text += "🛡️ Не выбрано\n"
        
        await callback.message.edit_text(profile_text, reply_markup=get_profile_menu(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "profile_stats")
async def profile_stats_callback(callback: CallbackQuery):
    """Детальная статистика"""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Сначала используй /start", show_alert=True)
            return
        
        stats_text = (
            f"📊 <b>Детальная статистика</b>\n\n"
            f"<b>Основное:</b>\n"
            f"⭐ Уровень: {user.level}\n"
            f"📈 Опыт: {user.experience}/{user.experience_to_next}\n"
            f"💎 Очки: {user.points}\n"
            f"📅 Зарегистрирован: {user.created_at.strftime('%d.%m.%Y') if user.created_at else 'Неизвестно'}\n\n"
            f"<b>PvP:</b>\n"
            f"🏆 Побед: {user.pvp_wins}\n"
            f"💀 Поражений: {user.pvp_losses}\n"
            f"📊 Winrate: {user.get_win_rate()}%\n\n"
            f"<b>PvE:</b>\n"
            f"👹 Побед: {user.pve_wins}\n"
            f"💀 Поражений: {user.pve_losses}\n\n"
            f"<b>Общее:</b>\n"
            f"⚔️ Всего боев: {user.total_battles}"
        )
        
        from keyboards.main_menu import get_back_button
        await callback.message.edit_text(stats_text, reply_markup=get_back_button("profile"), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "my_deck")
async def my_deck_callback(callback: CallbackQuery):
    """Моя колода"""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Сначала используй /start", show_alert=True)
            return
        
        # Получаем экипированные карты
        main_card = None
        support_card = None
        
        if user.slot_1_card_id:
            result = await session.execute(
                select(UserCard).options(selectinload(UserCard.card_template)).where(UserCard.id == user.slot_1_card_id)
            )
            main_card = result.scalar_one_or_none()
        
        if user.slot_2_card_id:
            result = await session.execute(
                select(UserCard).options(selectinload(UserCard.card_template)).where(UserCard.id == user.slot_2_card_id)
            )
            support_card = result.scalar_one_or_none()
        
        deck_text = "🎴 <b>Моя колода</b>\n\n"
        
        if main_card and main_card.card_template:
            deck_text += (
                f"👑 <b>Главный персонаж:</b>\n"
                f"{main_card.card_template.name} (Lv.{main_card.level})\n"
                f"❤️ HP: {main_card.max_hp} | ⚔️ АТК: {main_card.attack}\n"
                f"🛡️ ЗЩТ: {main_card.defense} | 💨 СКР: {main_card.speed}\n\n"
            )
        else:
            deck_text += "👑 <b>Главный персонаж:</b> Не выбран\n\n"
        
        if support_card and support_card.card_template:
            deck_text += (
                f"🛡️ <b>Поддержка:</b>\n"
                f"{support_card.card_template.name} (Lv.{support_card.level})\n"
                f"❤️ HP: {support_card.max_hp} | ⚔️ АТК: {support_card.attack}\n"
                f"🛡️ ЗЩТ: {support_card.defense} | 💨 СКР: {support_card.speed}\n\n"
            )
        else:
            deck_text += "🛡️ <b>Поддержка:</b> Не выбран\n\n"
        
        if main_card or support_card:
            total_power = 0
            if main_card:
                total_power += main_card.get_total_power()
            if support_card:
                total_power += support_card.get_total_power()
            deck_text += f"💪 <b>Общая сила колоды:</b> {total_power}"
        
        await callback.message.edit_text(
            deck_text, 
            reply_markup=get_deck_keyboard(main_card, support_card),
            parse_mode="HTML"
        )
    await callback.answer()

@router.callback_query(F.data.startswith("select_main_card"))
async def select_main_card_callback(callback: CallbackQuery):
    """Выбор главной карты"""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Сначала используй /start", show_alert=True)
            return
        
        # Получаем все карты пользователя
        result = await session.execute(
            select(UserCard).options(selectinload(UserCard.card_template)).where(UserCard.user_id == user.id)
        )
        cards = result.scalars().all()
        
        # Фильтруем только персонажей
        character_cards = [c for c in cards if c.card_template and c.card_template.card_type == "character"]
        
        if not character_cards:
            await callback.answer("У тебя нет карт персонажей!", show_alert=True)
            return
        
        from keyboards.cards import get_card_selection_keyboard
        await callback.message.edit_text(
            "👑 <b>Выбери главного персонажа:</b>",
            reply_markup=get_card_selection_keyboard(character_cards, "main"),
            parse_mode="HTML"
        )
    await callback.answer()

@router.callback_query(F.data.startswith("select_support_card"))
async def select_support_card_callback(callback: CallbackQuery):
    """Выбор карты поддержки"""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Сначала используй /start", show_alert=True)
            return
        
        # Получаем все карты пользователя
        result = await session.execute(
            select(UserCard).options(selectinload(UserCard.card_template)).where(UserCard.user_id == user.id)
        )
        cards = result.scalars().all()
        
        # Фильтруем только поддержку
        support_cards = [c for c in cards if c.card_template and c.card_template.card_type in ["support", "weapon"]]
        
        if not support_cards:
            await callback.answer("У тебя нет карт поддержки!", show_alert=True)
            return
        
        from keyboards.cards import get_card_selection_keyboard
        await callback.message.edit_text(
            "🛡️ <b>Выбери карту поддержки:</b>",
            reply_markup=get_card_selection_keyboard(support_cards, "support"),
            parse_mode="HTML"
        )
    await callback.answer()

@router.callback_query(F.data.startswith("select_card_"))
async def confirm_card_selection_callback(callback: CallbackQuery):
    """Подтверждение выбора карты"""
    parts = callback.data.split("_")
    slot_type = parts[2]  # main или support
    card_id = int(parts[3])
    
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Сначала используй /start", show_alert=True)
            return
        
        # Проверяем, что карта принадлежит пользователю
        result = await session.execute(
            select(UserCard).where(UserCard.id == card_id, UserCard.user_id == user.id)
        )
        card = result.scalar_one_or_none()
        
        if not card:
            await callback.answer("Карта не найдена!", show_alert=True)
            return
        
        # Снимаем экипировку с предыдущей карты
        if slot_type == "main" and user.slot_1_card_id:
            result = await session.execute(
                select(UserCard).where(UserCard.id == user.slot_1_card_id)
            )
            old_card = result.scalar_one_or_none()
            if old_card:
                old_card.is_equipped = False
                old_card.slot_number = None
        
        elif slot_type == "support" and user.slot_2_card_id:
            result = await session.execute(
                select(UserCard).where(UserCard.id == user.slot_2_card_id)
            )
            old_card = result.scalar_one_or_none()
            if old_card:
                old_card.is_equipped = False
                old_card.slot_number = None
        
        # Экипируем новую карту
        card.is_equipped = True
        card.slot_number = 1 if slot_type == "main" else 2
        
        if slot_type == "main":
            user.slot_1_card_id = card_id
        else:
            user.slot_2_card_id = card_id
        
        await session.commit()
        
        await callback.answer(f"Карта экипирована!" if slot_type == "main" else "Поддержка выбрана!")
        
        # Обновляем отображение колоды
        await my_deck_callback(callback)


@router.callback_query(F.data.startswith("select_page_"))
async def select_page_callback(callback: CallbackQuery):
    """Пагинация выбора карты для слота"""
    parts = callback.data.split("_")
    slot_type = parts[2]
    page = int(parts[3])

    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()

        if not user:
            await callback.answer("Сначала используй /start", show_alert=True)
            return

        result = await session.execute(
            select(UserCard).options(selectinload(UserCard.card_template)).where(UserCard.user_id == user.id)
        )
        cards = result.scalars().all()

        from keyboards.cards import get_card_selection_keyboard
        title = "👑 <b>Выбери главного персонажа:</b>" if slot_type == "main" else "🛡️ <b>Выбери карту поддержки:</b>"
        await callback.message.edit_text(
            title,
            reply_markup=get_card_selection_keyboard(cards, slot_type, page),
            parse_mode="HTML"
        )
    await callback.answer()

@router.callback_query(F.data.startswith("unequip_card_"))
async def unequip_card_callback(callback: CallbackQuery):
    """Снять карту"""
    card_id = int(callback.data.split("_")[2])
    
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Сначала используй /start", show_alert=True)
            return
        
        result = await session.execute(
            select(UserCard).where(UserCard.id == card_id, UserCard.user_id == user.id)
        )
        card = result.scalar_one_or_none()
        
        if card:
            card.is_equipped = False
            card.slot_number = None
            
            if user.slot_1_card_id == card_id:
                user.slot_1_card_id = None
            elif user.slot_2_card_id == card_id:
                user.slot_2_card_id = None
            
            await session.commit()
            await callback.answer("Карта снята!")
        
        await my_deck_callback(callback)

@router.callback_query(F.data == "difficulty_menu")
async def difficulty_menu_callback(callback: CallbackQuery):
    """Меню выбора сложности"""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Сначала используй /start", show_alert=True)
            return
        
        diff_emojis = {
            "easy": "🟢",
            "normal": "🔵",
            "hard": "🟠",
            "hardcore": "🔴"
        }
        
        current = diff_emojis.get(user.difficulty, "🔵")
        
        await callback.message.edit_text(
            f"⚙️ <b>Уровень Сложности</b>\n\n"
            f"Текущий: {current} <b>{user.difficulty.upper()}</b>\n"
            f"Множитель наград: {user.get_difficulty_multiplier()}x\n\n"
            f"🟢 <b>Легкий</b> - 0.5x награды, нет штрафов\n"
            f"🔵 <b>Нормальный</b> - 1x награды (стандарт)\n"
            f"🟠 <b>Сложный</b> - 1.5x награды, сильные враги\n"
            f"🔴 <b>Хардкор</b> - 2x награды, смерть = конец\n\n"
            f"Выбери новый уровень:",
            reply_markup=get_difficulty_menu(),
            parse_mode="HTML"
        )
    await callback.answer()

@router.callback_query(F.data.startswith("set_difficulty_"))
async def set_difficulty_callback(callback: CallbackQuery):
    """Установить уровень сложности"""
    difficulty = callback.data.split("_")[2]
    
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Сначала используй /start", show_alert=True)
            return
        
        user.difficulty = difficulty
        user.hardcore_mode = (difficulty == "hardcore")
        
        await session.commit()
        
        await callback.answer(f"Сложность изменена на {difficulty.upper()}!")
        await difficulty_menu_callback(callback)
