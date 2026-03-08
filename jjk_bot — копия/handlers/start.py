import random
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from sqlalchemy import select

from models import async_session, User, Card, UserCard
from keyboards import get_main_menu
from utils.card_data import ALL_CARDS, RARITY_CHANCES

router = Router()

def get_random_card_by_rarity():
    """Получить случайную карту с учетом шансов редкости"""
    rand = random.uniform(0, 100)
    cumulative = 0
    selected_rarity = "common"
    
    for rarity, chance in RARITY_CHANCES.items():
        cumulative += chance
        if rand <= cumulative:
            selected_rarity = rarity
            break
    
    # Получаем карты этой редкости
    cards_of_rarity = [c for c in ALL_CARDS if c["rarity"] == selected_rarity]
    if not cards_of_rarity:
        cards_of_rarity = [c for c in ALL_CARDS if c["rarity"] == "common"]
    
    return random.choice(cards_of_rarity)

@router.message(Command("start"))
async def cmd_start(message: Message):
    """Обработчик команды /start"""
    async with async_session() as session:
        # Проверяем, есть ли пользователь в БД
        result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        is_new_user = False
        starter_card = None
        
        if not user:
            # Создаем нового пользователя
            user = User(
                telegram_id=message.from_user.id,
                username=message.from_user.username,
                first_name=message.from_user.first_name
            )
            session.add(user)
            await session.flush()  # Получаем ID пользователя
            
            # Выдаем стартовую карту
            card_data = get_random_card_by_rarity()
            
            # Создаем шаблон карты если его нет
            result = await session.execute(
                select(Card).where(Card.name == card_data["name"])
            )
            card_template = result.scalar_one_or_none()
            
            if not card_template:
                card_template = Card(
                    name=card_data["name"],
                    description=card_data["description"],
                    card_type="character" if card_data in [c for c in ALL_CARDS if c.get("base_attack", 0) > 50] else "support",
                    rarity=card_data["rarity"],
                    base_attack=card_data["base_attack"],
                    base_defense=card_data["base_defense"],
                    base_speed=card_data["base_speed"],
                    base_hp=card_data["base_hp"],
                    growth_multiplier=card_data["growth_multiplier"]
                )
                session.add(card_template)
                await session.flush()
            
            # Создаем карту пользователя
            user_card = UserCard(
                user_id=user.id,
                card_id=card_template.id,
                level=1,
                attack=card_template.base_attack,
                defense=card_template.base_defense,
                speed=card_template.base_speed,
                hp=card_template.base_hp,
                max_hp=card_template.base_hp,
                upgrade_cost=5,
                is_equipped=True,
                slot_number=1
            )
            session.add(user_card)
            await session.flush()
            
            user.slot_1_card_id = user_card.id
            
            await session.commit()
            
            is_new_user = True
            starter_card = card_template
        
        # Приветственное сообщение
        if is_new_user:
            rarity_emojis = {
                "common": "⚪",
                "rare": "🔵",
                "epic": "🟣",
                "legendary": "🟡",
                "mythical": "🔴"
            }
            rarity = starter_card.rarity
            emoji = rarity_emojis.get(rarity, "⚪")
            
            welcome_text = (
                f"🎌 <b>Добро пожаловать в мир Магической Битвы!</b>\n\n"
                f"Ты стал магом и получаешь свою первую карту:\n\n"
                f"{emoji} <b>{starter_card.name}</b>\n"
                f"📊 Редкость: {rarity.upper()}\n"
                f"❤️ HP: {starter_card.base_hp}\n"
                f"⚔️ Атака: {starter_card.base_attack}\n"
                f"🛡️ Защита: {starter_card.base_defense}\n"
                f"💨 Скорость: {starter_card.base_speed}\n\n"
                f"<i>{starter_card.description}</i>\n\n"
                f"Используй меню ниже, чтобы начать своё путешествие!"
            )
        else:
            welcome_text = (
                f"👋 <b>С возвращением, {user.first_name or 'Маг'}!</b>\n\n"
                f"📊 Уровень: {user.level}\n"
                f"⭐ Опыт: {user.experience}/{user.experience_to_next}\n"
                f"💎 Очки: {user.points}\n\n"
                f"Выбери действие в меню ниже:"
            )
        
        await message.answer(welcome_text, reply_markup=get_main_menu(), parse_mode="HTML")

@router.callback_query(F.data == "main_menu")
async def main_menu_callback(callback: CallbackQuery):
    """Возврат в главное меню"""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        if user:
            text = (
                f"👋 <b>Привет, {user.first_name or 'Маг'}!</b>\n\n"
                f"📊 Уровень: {user.level}\n"
                f"⭐ Опыт: {user.experience}/{user.experience_to_next}\n"
                f"💎 Очки: {user.points}\n\n"
                f"Выбери действие:"
            )
        else:
            text = "👋 <b>Главное меню</b>\n\nВыбери действие:"
        
        await callback.message.edit_text(text, reply_markup=get_main_menu(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "help")
async def help_callback(callback: CallbackQuery):
    """Помощь"""
    help_text = (
        "📚 <b>Помощь по игре</b>\n\n"
        "<b>Основные команды:</b>\n"
        "/start - Начать игру\n"
        "/profile - Твой профиль\n"
        "/inventory - Твои карты\n"
        "/battle - Меню боев\n\n"
        
        "<b>Как играть:</b>\n"
        "1️⃣ Получи стартовую карту при регистрации\n"
        "2️⃣ Экипируй карты в колоду (1 персонаж + 1 поддержка)\n"
        "3️⃣ Сражайся на арене проклятий для прокачки\n"
        "4️⃣ Используй очки для улучшения карт\n"
        "5️⃣ Бросай вызов другим игрокам в PvP!\n\n"
        
        "<b>Система боя:</b>\n"
        "• Первым атакует тот, у кого больше скорости\n"
        "• Атака уменьшается защитой противника\n"
        "• Побеждает тот, кто first опустит HP врага до 0\n\n"
        
        "<b>Прокачка:</b>\n"
        "• Опыт дается за бои и сообщения\n"
        "• Очки даются за победы и уровни\n"
        "• Улучшай карты за очки!"
    )
    
    from keyboards.main_menu import get_back_button
    await callback.message.edit_text(help_text, reply_markup=get_back_button(), parse_mode="HTML")
    await callback.answer()