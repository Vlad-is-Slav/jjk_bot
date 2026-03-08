from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from models import async_session, User, Card, UserCard, Technique, UserTechnique, Title, UserTitle
from utils.card_data import ALL_CARDS
from utils.technique_data import ALL_TECHNIQUES
from utils.achievement_data import TITLES

router = Router()

ADMIN_IDS = [1296861067]
# Проверка на админа
async def is_admin(telegram_id: int) -> bool:
    if telegram_id in ADMIN_IDS:
        return True
    
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        return user and user.is_admin

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    """Админ панель"""
    if not await is_admin(message.from_user.id):
        await message.answer("❌ У тебя нет прав администратора!")
        return
    
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎴 Выдать карту", callback_data="admin_give_card"),
            InlineKeyboardButton(text="✨ Выдать технику", callback_data="admin_give_tech")
        ],
        [
            InlineKeyboardButton(text="💰 Выдать валюту", callback_data="admin_give_currency"),
            InlineKeyboardButton(text="👑 Выдать титул", callback_data="admin_give_title")
        ],
        [
            InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"),
            InlineKeyboardButton(text="🔧 Настройки", callback_data="admin_settings")
        ]
    ])
    
    await message.answer(
        "🔧 <b>Админ Панель</b>\n\n"
        "Выбери действие:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

@router.message(Command("givecard"))
async def cmd_give_card(message: Message):
    """Выдать карту игроку"""
    if not await is_admin(message.from_user.id):
        await message.answer("❌ Нет прав!")
        return
    
    args = message.text.split()[1:]
    
    if len(args) < 2:
        await message.answer(
            "🎴 <b>Выдача карты</b>\n\n"
            "Использование:\n"
            "<code>/givecard @username Название_Карты [уровень]</code>\n"
            "<code>/givecard ID Название_Карты [уровень]</code>\n\n"
            "Пример:\n"
            "<code>/givecard @user Годжо_Сатору 10</code>"
        )
        return
    
    target = args[0]
    card_name = args[1].replace("_", " ")
    level = int(args[2]) if len(args) > 2 else 1
    
    async with async_session() as session:
        # Ищем цель
        if target.startswith("@"):
            result = await session.execute(
                select(User).where(User.username == target[1:])
            )
        else:
            try:
                target_id = int(target)
                result = await session.execute(
                    select(User).where(User.telegram_id == target_id)
                )
            except ValueError:
                await message.answer("❌ Неверный формат цели!")
                return
        
        target_user = result.scalar_one_or_none()
        
        if not target_user:
            await message.answer("❌ Игрок не найден!")
            return
        
        # Ищем карту
        card_data = None
        for c in ALL_CARDS:
            if c["name"].lower() == card_name.lower():
                card_data = c
                break
        
        if not card_data:
            await message.answer(f"❌ Карта '{card_name}' не найдена!")
            return
        
        # Создаем или получаем шаблон
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
            user_id=target_user.id,
            card_id=card_template.id,
            level=level
        )
        user_card.recalculate_stats()
        session.add(user_card)
        await session.commit()
        
        await message.answer(
            f"✅ <b>Карта выдана!</b>\n\n"
            f"Игрок: {target_user.first_name or target_user.username}\n"
            f"Карта: {card_data['name']}\n"
            f"Уровень: {level}\n"
            f"Редкость: {card_data['rarity']}"
        )

@router.message(Command("givetech"))
async def cmd_give_tech(message: Message):
    """Выдать технику игроку"""
    if not await is_admin(message.from_user.id):
        await message.answer("❌ Нет прав!")
        return
    
    args = message.text.split()[1:]
    
    if len(args) < 2:
        await message.answer(
            "✨ <b>Выдача техники</b>\n\n"
            "Использование:\n"
            "<code>/givetech @username Название_Техники</code>\n\n"
            "Пример:\n"
            "<code>/givetech @user Шесть_Глаз</code>"
        )
        return
    
    target = args[0]
    tech_name = args[1].replace("_", " ")
    
    async with async_session() as session:
        # Ищем цель
        if target.startswith("@"):
            result = await session.execute(
                select(User).where(User.username == target[1:])
            )
        else:
            try:
                target_id = int(target)
                result = await session.execute(
                    select(User).where(User.telegram_id == target_id)
                )
            except ValueError:
                await message.answer("❌ Неверный формат цели!")
                return
        
        target_user = result.scalar_one_or_none()
        
        if not target_user:
            await message.answer("❌ Игрок не найден!")
            return
        
        # Ищем технику
        tech_data = None
        for t in ALL_TECHNIQUES:
            if t["name"].lower() == tech_name.lower():
                tech_data = t
                break
        
        if not tech_data:
            await message.answer(f"❌ Техника '{tech_name}' не найдена!")
            return
        
        # Создаем или получаем шаблон
        result = await session.execute(
            select(Technique).where(Technique.name == tech_data["name"])
        )
        tech_template = result.scalar_one_or_none()
        
        if not tech_template:
            tech_template = Technique(
                name=tech_data["name"],
                description=tech_data["description"],
                technique_type=tech_data["technique_type"],
                ce_cost=tech_data.get("ce_cost", 0),
                effect_type=tech_data.get("effect_type"),
                effect_value=tech_data.get("effect_value", 0),
                icon=tech_data["icon"],
                rarity=tech_data["rarity"]
            )
            session.add(tech_template)
            await session.flush()
        
        # Проверяем, есть ли уже
        result = await session.execute(
            select(UserTechnique).where(
                UserTechnique.user_id == target_user.id,
                UserTechnique.technique_id == tech_template.id
            )
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            await message.answer("❌ У игрока уже есть эта техника!")
            return
        
        # Выдаем технику
        user_tech = UserTechnique(
            user_id=target_user.id,
            technique_id=tech_template.id,
            level=1,
            is_equipped=False
        )
        session.add(user_tech)
        await session.commit()
        
        await message.answer(
            f"✅ <b>Техника выдана!</b>\n\n"
            f"Игрок: {target_user.first_name or target_user.username}\n"
            f"Техника: {tech_data['name']}\n"
            f"Тип: {tech_data['technique_type']}\n"
            f"Редкость: {tech_data['rarity']}"
        )

@router.message(Command("givecurrency"))
async def cmd_give_currency(message: Message):
    """Выдать валюту игроку"""
    if not await is_admin(message.from_user.id):
        await message.answer("❌ Нет прав!")
        return
    
    args = message.text.split()[1:]
    
    if len(args) < 3:
        await message.answer(
            "💰 <b>Выдача валюты</b>\n\n"
            "Использование:\n"
            "<code>/givecurrency @username ТИП КОЛИЧЕСТВО</code>\n\n"
            "Типы: coins, points, exp\n\n"
            "Пример:\n"
            "<code>/givecurrency @user coins 1000</code>"
        )
        return
    
    target = args[0]
    currency_type = args[1].lower()
    amount = int(args[2])
    
    async with async_session() as session:
        # Ищем цель
        if target.startswith("@"):
            result = await session.execute(
                select(User).where(User.username == target[1:])
            )
        else:
            try:
                target_id = int(target)
                result = await session.execute(
                    select(User).where(User.telegram_id == target_id)
                )
            except ValueError:
                await message.answer("❌ Неверный формат цели!")
                return
        
        target_user = result.scalar_one_or_none()
        
        if not target_user:
            await message.answer("❌ Игрок не найден!")
            return
        
        # Выдаем валюту
        if currency_type == "coins":
            target_user.coins += amount
            currency_name = "монет"
        elif currency_type == "points":
            target_user.points += amount
            currency_name = "очков"
        elif currency_type == "exp":
            target_user.add_experience(amount)
            currency_name = "опыта"
        else:
            await message.answer("❌ Неверный тип валюты!")
            return
        
        await session.commit()
        
        await message.answer(
            f"✅ <b>Валюта выдана!</b>\n\n"
            f"Игрок: {target_user.first_name or target_user.username}\n"
            f"Тип: {currency_name}\n"
            f"Количество: +{amount}"
        )

@router.message(Command("setadmin"))
async def cmd_set_admin(message: Message):
    """Назначить админа"""
    if not await is_admin(message.from_user.id):
        await message.answer("❌ Нет прав!")
        return
    
    args = message.text.split()[1:]
    
    if not args:
        await message.answer("Использование: /setadmin @username или ID")
        return
    
    target = args[0]
    
    async with async_session() as session:
        if target.startswith("@"):
            result = await session.execute(
                select(User).where(User.username == target[1:])
            )
        else:
            try:
                target_id = int(target)
                result = await session.execute(
                    select(User).where(User.telegram_id == target_id)
                )
            except ValueError:
                await message.answer("❌ Неверный формат!")
                return
        
        target_user = result.scalar_one_or_none()
        
        if not target_user:
            await message.answer("❌ Игрок не найден!")
            return
        
        target_user.is_admin = True
        await session.commit()
        
        await message.answer(
            f"✅ {target_user.first_name or target_user.username} теперь администратор!"
        )

@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message):
    """Отправить сообщение всем игрокам"""
    if not await is_admin(message.from_user.id):
        await message.answer("❌ Нет прав!")
        return
    
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.answer("Использование: /broadcast ТЕКСТ")
        return
    
    text = args[1]
    
    async with async_session() as session:
        result = await session.execute(select(User))
        users = result.scalars().all()
        
        sent = 0
        failed = 0
        
        for user in users:
            try:
                await message.bot.send_message(
                    user.telegram_id,
                    f"📢 <b>Сообщение от администрации:</b>\n\n{text}",
                    parse_mode="HTML"
                )
                sent += 1
            except:
                failed += 1
        
        await message.answer(
            f"✅ Рассылка завершена!\n"
            f"Отправлено: {sent}\n"
            f"Не удалось: {failed}"
        )


@router.callback_query(F.data.in_({
    "admin_give_card",
    "admin_give_tech",
    "admin_give_currency",
    "admin_give_title",
    "admin_stats",
    "admin_settings"
}))
async def admin_panel_callback(callback: CallbackQuery):
    """Обработчик кнопок админ-панели"""
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав администратора!", show_alert=True)
        return

    command_help = {
        "admin_give_card": "/givecard @username Название_Карты [уровень]",
        "admin_give_tech": "/givetech @username Название_Техники",
        "admin_give_currency": "/givecurrency @username coins|points|exp количество",
        "admin_give_title": "Выдача титулов через кнопку пока в разработке.",
        "admin_stats": "Статистика админ-панели пока в разработке.",
        "admin_settings": "Настройки админ-панели пока в разработке."
    }

    await callback.answer(command_help.get(callback.data, "Функция в разработке."), show_alert=True)
