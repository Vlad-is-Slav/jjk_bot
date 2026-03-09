from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from models import async_session, User, UserCard, UserTechnique
from keyboards import get_inventory_menu, get_card_list_keyboard, get_card_detail_keyboard, get_upgrade_keyboard, get_back_button
from utils.card_rewards import is_character_template, is_support_template
from utils.daily_quest_progress import add_daily_quest_progress

router = Router()

@router.message(Command("inventory"))
async def cmd_inventory(message: Message):
    """Команда /inventory"""
    await message.answer(
        "🎒 <b>Инвентарь</b>\n\n"
        "Выбери категорию:",
        reply_markup=get_inventory_menu(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "noop")
async def noop_callback(callback: CallbackQuery):
    """Пустой callback для неактивных кнопок"""
    await callback.answer()

@router.callback_query(F.data == "inventory")
async def inventory_callback(callback: CallbackQuery):
    """Инвентарь"""
    await callback.message.edit_text(
        "🎒 <b>Инвентарь</b>\n\n"
        "Выбери категорию:",
        reply_markup=get_inventory_menu(),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data == "all_cards")
async def all_cards_callback(callback: CallbackQuery):
    """Все карты"""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Сначала используй /start", show_alert=True)
            return
        
        result = await session.execute(
            select(UserCard)
            .options(selectinload(UserCard.card_template))
            .where(UserCard.user_id == user.id)
            .order_by(UserCard.level.desc())
        )
        cards = result.scalars().all()
        
        if not cards:
            await callback.message.edit_text(
                "🎒 <b>У тебя пока нет карт!</b>\n\n"
                "Сражайся на арене, чтобы получить новые карты.",
                reply_markup=get_inventory_menu(),
                parse_mode="HTML"
            )
            return
        
        await callback.message.edit_text(
            f"🎴 <b>Твои карты ({len(cards)}):</b>\n\n"
            "Выбери карту для просмотра:",
            reply_markup=get_card_list_keyboard(list(cards)),
            parse_mode="HTML"
        )
    await callback.answer()

@router.callback_query(F.data.startswith("cards_page_"))
async def cards_page_callback(callback: CallbackQuery):
    """Пагинация списка карт"""
    page = int(callback.data.split("_")[2])
    
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Сначала используй /start", show_alert=True)
            return
        
        result = await session.execute(
            select(UserCard)
            .options(selectinload(UserCard.card_template))
            .where(UserCard.user_id == user.id)
            .order_by(UserCard.level.desc())
        )
        cards = result.scalars().all()
        
        await callback.message.edit_text(
            f"🎴 <b>Твои карты ({len(cards)}):</b>\n\n"
            "Выбери карту для просмотра:",
            reply_markup=get_card_list_keyboard(list(cards), page),
            parse_mode="HTML"
        )
    await callback.answer()

@router.callback_query(F.data.startswith("card_detail_"))
async def card_detail_callback(callback: CallbackQuery):
    """Детали карты"""
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
            select(UserCard)
            .options(selectinload(UserCard.card_template))
            .where(UserCard.id == card_id, UserCard.user_id == user.id)
        )
        card = result.scalar_one_or_none()
        
        if not card or not card.card_template:
            await callback.answer("Карта не найдена!", show_alert=True)
            return
        
        rarity_emojis = {
            "common": "⚪",
            "rare": "🔵",
            "epic": "🟣",
            "legendary": "🟡",
            "mythical": "🔴"
        }
        
        rarity = card.card_template.rarity
        emoji = rarity_emojis.get(rarity, "⚪")
        
        card_text = (
            f"{emoji} <b>{card.card_template.name}</b>\n"
            f"📊 Редкость: {rarity.upper()}\n"
            f"⭐ Уровень: {card.level}\n"
            f"💪 Сила: {card.get_total_power()}\n\n"
            f"<i>{card.card_template.description}</i>\n\n"
            f"❤️ HP: {card.max_hp}\n"
            f"⚔️ Атака: {card.attack}\n"
            f"🛡️ Защита: {card.defense}\n"
            f"💨 Скорость: {card.speed}\n\n"
        )
        
        if card.is_equipped:
            slot_names = {1: "Главный", 2: "Поддержка", 3: "Дополнительный", 4: "Техника"}
            slot_name = slot_names.get(card.slot_number, "Слот")
            card_text += f"✅ <b>Экипировано</b> ({slot_name})\n"
        
        card_text += f"⬆️ Стоимость прокачки: {card.upgrade_cost} очков"
        
        await callback.message.edit_text(
            card_text,
            reply_markup=get_card_detail_keyboard(card_id, card.is_equipped),
            parse_mode="HTML"
        )
    await callback.answer()

@router.callback_query(F.data.startswith("upgrade_card_"))
async def upgrade_card_callback(callback: CallbackQuery):
    """Меню прокачки карты"""
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
            select(UserCard)
            .options(selectinload(UserCard.card_template))
            .where(UserCard.id == card_id, UserCard.user_id == user.id)
        )
        card = result.scalar_one_or_none()
        
        if not card:
            await callback.answer("Карта не найдена!", show_alert=True)
            return
        
        can_upgrade = user.points >= card.upgrade_cost
        
        upgrade_text = (
            f"⬆️ <b>Прокачка карты</b>\n\n"
            f"🎴 {card.card_template.name} (Lv.{card.level})\n\n"
            f"📊 <b>Текущие характеристики:</b>\n"
            f"❤️ HP: {card.max_hp}\n"
            f"⚔️ Атака: {card.attack}\n"
            f"🛡️ Защита: {card.defense}\n"
            f"💨 Скорость: {card.speed}\n\n"
            f"💎 <b>Твои очки:</b> {user.points}\n"
            f"💰 <b>Стоимость:</b> {card.upgrade_cost} очков\n\n"
        )
        
        if can_upgrade:
            # Показываем будущие характеристики
            future_multiplier = card.card_template.growth_multiplier ** card.level
            future_hp = int(card.card_template.base_hp * future_multiplier)
            future_atk = int(card.card_template.base_attack * future_multiplier)
            future_def = int(card.card_template.base_defense * future_multiplier)
            future_spd = int(card.card_template.base_speed * future_multiplier)
            
            upgrade_text += (
                f"📈 <b>После прокачки:</b>\n"
                f"❤️ HP: {future_hp} (+{future_hp - card.max_hp})\n"
                f"⚔️ Атака: {future_atk} (+{future_atk - card.attack})\n"
                f"🛡️ Защита: {future_def} (+{future_def - card.defense})\n"
                f"💨 Скорость: {future_spd} (+{future_spd - card.speed})"
            )
        else:
            upgrade_text += "❌ <b>Недостаточно очков!</b>"
        
        await callback.message.edit_text(
            upgrade_text,
            reply_markup=get_upgrade_keyboard(card_id, card.upgrade_cost, user.points),
            parse_mode="HTML"
        )
    await callback.answer()


@router.callback_query(F.data.startswith("equip_card_"))
async def equip_card_callback(callback: CallbackQuery):
    """Быстро экипировать карту в подходящий слот"""
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
            select(UserCard)
            .options(selectinload(UserCard.card_template))
            .where(UserCard.id == card_id, UserCard.user_id == user.id)
        )
        card = result.scalar_one_or_none()

        if not card or not card.card_template:
            await callback.answer("Карта не найдена!", show_alert=True)
            return

        is_main = is_character_template(card.card_template)
        slot_number = 1 if is_main else 2

        old_slot_card_id = user.slot_1_card_id if is_main else user.slot_2_card_id
        if old_slot_card_id and old_slot_card_id != card.id:
            result = await session.execute(
                select(UserCard).where(UserCard.id == old_slot_card_id, UserCard.user_id == user.id)
            )
            old_card = result.scalar_one_or_none()
            if old_card:
                old_card.is_equipped = False
                old_card.slot_number = None

        card.is_equipped = True
        card.slot_number = slot_number

        if is_main:
            user.slot_1_card_id = card.id
        else:
            user.slot_2_card_id = card.id

        await session.commit()

        slot_name = "главный слот" if is_main else "слот поддержки"
        await callback.answer(f"Карта экипирована в {slot_name}!")
        await card_detail_callback(callback)

@router.callback_query(F.data.startswith("confirm_upgrade_"))
async def confirm_upgrade_callback(callback: CallbackQuery):
    """Подтверждение прокачки"""
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
            select(UserCard)
            .options(selectinload(UserCard.card_template))
            .where(UserCard.id == card_id, UserCard.user_id == user.id)
        )
        card = result.scalar_one_or_none()
        
        if not card:
            await callback.answer("Карта не найдена!", show_alert=True)
            return
        
        if user.points < card.upgrade_cost:
            await callback.answer("Недостаточно очков!", show_alert=True)
            return
        
        # Прокачиваем карту
        user.points -= card.upgrade_cost
        old_level = card.level
        card.upgrade()
        await add_daily_quest_progress(session, user.id, "upgrade_cards", amount=1)
        
        await session.commit()
        
        await callback.answer(
            f"✅ Карта прокачана!\n"
            f"Lv.{old_level} → Lv.{card.level}",
            show_alert=True
        )
        
        # Возвращаемся к деталям карты
        await card_detail_callback(callback)

@router.callback_query(F.data == "character_cards")
async def character_cards_callback(callback: CallbackQuery):
    """Только карты персонажей"""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Сначала используй /start", show_alert=True)
            return
        
        result = await session.execute(
            select(UserCard)
            .options(selectinload(UserCard.card_template))
            .where(UserCard.user_id == user.id)
            .order_by(UserCard.level.desc())
        )
        cards = result.scalars().all()
        
        character_cards = [c for c in cards if c.card_template and is_character_template(c.card_template)]
        
        if not character_cards:
            await callback.message.edit_text(
                "🎴 <b>У тебя нет карт персонажей!</b>\n\n"
                "Сражайся на арене, чтобы получить их.",
                reply_markup=get_inventory_menu(),
                parse_mode="HTML"
            )
            return
        
        await callback.message.edit_text(
            f"⭐ <b>Карты персонажей ({len(character_cards)}):</b>\n\n"
            "Выбери карту для просмотра:",
            reply_markup=get_card_list_keyboard(character_cards),
            parse_mode="HTML"
        )
    await callback.answer()

@router.callback_query(F.data == "support_cards")
async def support_cards_callback(callback: CallbackQuery):
    """Только карты поддержки"""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Сначала используй /start", show_alert=True)
            return
        
        result = await session.execute(
            select(UserCard)
            .options(selectinload(UserCard.card_template))
            .where(UserCard.user_id == user.id)
            .order_by(UserCard.level.desc())
        )
        cards = result.scalars().all()
        
        support_cards = [c for c in cards if c.card_template and is_support_template(c.card_template)]
        
        if not support_cards:
            await callback.message.edit_text(
                "🛡️ <b>У тебя нет карт поддержки!</b>\n\n"
                "Сражайся на арене, чтобы получить их.",
                reply_markup=get_inventory_menu(),
                parse_mode="HTML"
            )
            return
        
        await callback.message.edit_text(
            f"🛡️ <b>Карты поддержки ({len(support_cards)}):</b>\n\n"
            "Выбери карту для просмотра:",
            reply_markup=get_card_list_keyboard(support_cards),
            parse_mode="HTML"
        )
    await callback.answer()

@router.callback_query(F.data == "my_techniques")
async def my_techniques_callback(callback: CallbackQuery):
    """Показать техники пользователя"""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Сначала используй /start", show_alert=True)
            return
        
        result = await session.execute(
            select(UserTechnique)
            .options(selectinload(UserTechnique.technique))
            .where(UserTechnique.user_id == user.id)
        )
        techniques = result.scalars().all()
        
        if not techniques:
            await callback.message.edit_text(
                "✨ <b>У тебя пока нет техник!</b>\n\n"
                "Посещай Техникум, чтобы получить новые техники.",
                reply_markup=get_back_button("inventory"),
                parse_mode="HTML"
            )
            return
        
        tech_text = "✨ <b>Твои техники:</b>\n\n"
        
        for ut in techniques:
            tech = ut.technique
            status = "✅" if ut.is_equipped else ""
            tech_text += (
                f"{status} {tech.icon} <b>{tech.name}</b> (Lv.{ut.level})\n"
                f"   Тип: {tech.technique_type}\n"
                f"   Редкость: {tech.rarity}\n\n"
            )
        
        await callback.message.edit_text(
            tech_text,
            reply_markup=get_back_button("inventory"),
            parse_mode="HTML"
        )
    await callback.answer()
